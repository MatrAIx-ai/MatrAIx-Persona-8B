from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from playground.chatbot_task_config import (
    ChatbotProtocolConfig,
    ChatbotRuntimeDefaults,
    ChatbotStructuredExposureField,
    ChatbotTaskConfig,
)
from playground.types import Questionnaire
from playground.uxagent.client import VoiceLabContractError
from playground.uxagent.models import SendMessageAction, UXMemory, VoiceLabAgentChatResponse
from playground.uxagent import runner as runner_module
from playground.uxagent.runner import UXAgentTrialRunner


class FakeVoiceLabClient:
    def __init__(
        self,
        responses: list[VoiceLabAgentChatResponse],
        *,
        create_error: BaseException | None = None,
        chat_errors: list[BaseException | None] | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self.responses = list(responses)
        self.create_error = create_error
        self.chat_errors = list(chat_errors or ())
        self.close_error = close_error
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    async def create_session(self, request):
        self.calls.append(("create_session", request.sessionId))
        if self.create_error is not None:
            raise self.create_error
        return request.sessionId

    async def agent_chat(self, request):
        self.calls.append(("agent_chat", request.personaSessionId))
        error = self.chat_errors.pop(0) if self.chat_errors else None
        if error is not None:
            raise error
        return self.responses.pop(0)

    async def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class FakePolicy:
    def __init__(
        self,
        actions: list[SendMessageAction],
        *,
        next_errors: list[BaseException | None] | None = None,
        wait_error: BaseException | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self.actions = list(actions)
        self.next_errors = list(next_errors or ())
        self.wait_error = wait_error
        self.close_error = close_error
        self.closed = False
        self.slow_started = False
        self.observations = []
        self.queued = []
        self._memories = ()

    @property
    def memories(self):
        return self._memories

    def start_slow_loop(self) -> None:
        self.slow_started = True

    async def next_action(self, observation):
        self.observations.append(observation)
        error = self.next_errors.pop(0) if self.next_errors else None
        if error is not None:
            raise error
        return self.actions.pop(0)

    async def enqueue_slow_observation(self, observation) -> None:
        self.queued.append(observation)

    async def wait_until_slow_idle(self) -> None:
        if self.wait_error is not None:
            raise self.wait_error

    async def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error

class FakeEnvironment:
    def __init__(
        self,
        root: Path,
        trial_name: str,
        *,
        upload_error: BaseException | None = None,
        fail_destinations: set[str] | None = None,
    ) -> None:
        self.trial_paths = SimpleNamespace(trial_dir=root / trial_name)
        self.upload_error = upload_error
        self.fail_destinations = set(fail_destinations or ())
        self.uploads: dict[str, str] = {}

    async def upload_file(self, source: Path, destination: str) -> None:
        if self.upload_error is not None and (
            not self.fail_destinations or destination in self.fail_destinations
        ):
            raise self.upload_error
        self.uploads[destination] = source.read_text(encoding="utf-8")


def test_create_failure_is_redacted_and_closes_policy_then_client(tmp_path: Path) -> None:
    secret_error = VoiceLabContractError("create_session APP_PASSWORD=top-secret")
    client = FakeVoiceLabClient([], create_error=secret_error)
    policy = FakePolicy([])
    events: list[dict] = []
    with pytest.raises(VoiceLabContractError) as raised:
        asyncio.run(
            _runner(client, policy).run(
                environment=FakeEnvironment(tmp_path, "trial-create-fail"),
                persona=_persona(),
                runtime=_runtime(),
                task_intent="intent",
                on_event=events.append,
            )
        )
    assert raised.value is secret_error
    assert policy.closed is True
    assert client.closed is True
    assert events[-1]["type"] == "error"
    assert events[-1]["operation"] == "create_session"
    assert events[-1]["error"]["type"] == "VoiceLabContractError"
    assert "top-secret" not in json.dumps(events)
    assert "APP_PASSWORD=top-secret" not in json.dumps(events)


def test_chat_failure_uploads_completed_turn_and_memory_without_questionnaire(
    tmp_path: Path,
) -> None:
    secret_error = VoiceLabContractError("agent_chat APP_PASSWORD=top-secret")
    client = FakeVoiceLabClient(
        [_response(vehicleState={"speed": 10})],
        chat_errors=[None, secret_error],
    )
    policy = FakePolicy(
        [SendMessageAction(message="one"), SendMessageAction(message="two")]
    )
    policy._memories = (
        UXMemory(
            kind="action",
            content="APP_PASSWORD=top-secret",
            importance=0.5,
            turn_index=1,
        ),
    )
    environment = FakeEnvironment(tmp_path, "trial-chat-fail")
    events: list[dict] = []
    with pytest.raises(VoiceLabContractError) as raised:
        asyncio.run(
            _runner(client, policy).run(
                environment=environment,
                persona=_persona(),
                runtime=_runtime(max_turns=3),
                task_intent="intent",
                on_event=events.append,
            )
        )
    assert raised.value is secret_error
    assert json.loads(environment.uploads["/app/output/transcript.json"])[
        "turns"
    ][0]["assistantMessage"] == "assistant"
    memory = json.loads(environment.uploads["/app/output/uxagent_memory.json"])
    assert memory["sessionId"] == "trial-chat-fail"
    assert "top-secret" not in json.dumps(memory)
    assert "user_feedback.json" not in environment.uploads
    assert "top-secret" not in json.dumps(events)
    assert policy.closed is True
    assert client.closed is True


def test_questionnaire_failure_preserves_partial_evidence_and_cleanup(tmp_path: Path) -> None:
    primary = RuntimeError("questionnaire schema invalid")
    client = FakeVoiceLabClient([_response(decision="executed")])
    policy = FakePolicy([SendMessageAction(message="one")])
    environment = FakeEnvironment(tmp_path, "trial-questionnaire-fail")

    def builder(**kwargs):
        raise primary

    with pytest.raises(RuntimeError) as raised:
        asyncio.run(
            _runner(client, policy, builder).run(
                environment=environment,
                persona=_persona(),
                runtime=_runtime(),
                task_intent="intent",
            )
        )
    assert raised.value is primary
    assert "/app/output/transcript.json" in environment.uploads
    assert "/app/output/uxagent_memory.json" in environment.uploads
    assert "user_feedback.json" not in environment.uploads
    assert policy.closed is True
    assert client.closed is True


def test_partial_upload_error_does_not_mask_primary_error(tmp_path: Path) -> None:
    primary = VoiceLabContractError("agent_chat failed")
    cleanup = RuntimeError("disk full")
    client = FakeVoiceLabClient(
        [_response(decision="continue")],
        chat_errors=[None, primary],
    )
    policy = FakePolicy(
        [SendMessageAction(message="one"), SendMessageAction(message="two")]
    )
    events: list[dict] = []
    with pytest.raises(VoiceLabContractError) as raised:
        asyncio.run(
            _runner(client, policy).run(
                environment=FakeEnvironment(
                    tmp_path,
                    "trial-upload-fail",
                    upload_error=cleanup,
                ),
                persona=_persona(),
                runtime=_runtime(max_turns=3),
                task_intent="intent",
                on_event=events.append,
            )
        )
    assert raised.value is primary
    assert [event["operation"] for event in events if event["type"] == "error"] == [
        "voicelab_agent_chat",
        "partial_artifact_upload",
    ]
    assert policy.closed is True
    assert client.closed is True


def test_cleanup_errors_do_not_replace_active_primary_error(tmp_path: Path) -> None:
    primary = VoiceLabContractError("agent_chat failed")
    client = FakeVoiceLabClient(
        [],
        chat_errors=[primary],
        close_error=RuntimeError("client close failed"),
    )
    policy = FakePolicy(
        [SendMessageAction(message="one")],
        close_error=RuntimeError("policy close failed"),
    )
    events: list[dict] = []
    with pytest.raises(VoiceLabContractError) as raised:
        asyncio.run(
            _runner(client, policy).run(
                environment=FakeEnvironment(tmp_path, "trial-close-fail"),
                persona=_persona(),
                runtime=_runtime(),
                task_intent="intent",
                on_event=events.append,
            )
        )
    assert raised.value is primary
    assert {event["operation"] for event in events if event["type"] == "error"} == {
        "voicelab_agent_chat",
        "policy_close",
        "client_close",
    }


def test_nested_sensitive_mapping_values_are_redacted_in_events_artifacts_and_memory(
    tmp_path: Path,
) -> None:
    nested = {
        "APP_PASSWORD": "app-password-secret",
        "api_key": "api-key-secret",
        "authorization": "Bearer authorization-secret",
        "token": "token-secret",
        "password": "password-secret",
        "secret": {"deep": "secret-secret"},
        "message": "Authorization: Bearer scheme-secret",
    }
    client = FakeVoiceLabClient(
        [_response(decision="executed", toolResult={"nested": nested})]
    )
    policy = FakePolicy([SendMessageAction(message="one")])
    policy._memories = ({"nested": nested},)
    environment = FakeEnvironment(tmp_path, "trial-redaction")
    events: list[dict] = []

    asyncio.run(
        _runner(client, policy).run(
            environment=environment,
            persona=_persona(),
            runtime=_runtime(max_turns=1),
            task_intent="intent",
            on_event=events.append,
        )
    )

    serialized_events = json.dumps(events)
    serialized_artifacts = json.dumps(environment.uploads)
    assert "app-password-secret" not in serialized_events + serialized_artifacts
    assert "api-key-secret" not in serialized_events + serialized_artifacts
    assert "authorization-secret" not in serialized_events + serialized_artifacts
    assert "token-secret" not in serialized_events + serialized_artifacts
    assert "password-secret" not in serialized_events + serialized_artifacts
    assert "secret-secret" not in serialized_events + serialized_artifacts
    assert "scheme-secret" not in serialized_events + serialized_artifacts
    memory = json.loads(environment.uploads["/app/output/uxagent_memory.json"])
    redacted_nested = memory["memories"][0]["nested"]
    assert {
        key: redacted_nested[key]
        for key in ("APP_PASSWORD", "api_key", "authorization", "token", "password", "secret")
    } == {
        "APP_PASSWORD": "[REDACTED]",
        "api_key": "[REDACTED]",
        "authorization": "[REDACTED]",
        "token": "[REDACTED]",
        "password": "[REDACTED]",
        "secret": "[REDACTED]",
    }


def test_upload_dump_failure_removes_created_temp_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    created_path: Path | None = None

    def fail_dump(payload, handle, **kwargs) -> None:
        nonlocal created_path
        created_path = Path(handle.name)
        assert created_path.exists()
        raise RuntimeError("serialization failed")

    monkeypatch.setattr(runner_module.json, "dump", fail_dump)
    runner = _runner(FakeVoiceLabClient([]), FakePolicy([]))
    with pytest.raises(RuntimeError, match="serialization failed"):
        asyncio.run(
            runner._upload_artifacts(
                FakeEnvironment(tmp_path, "trial-dump-fail"),
                {"artifact.json": {"value": "payload"}},
            )
        )
    assert created_path is not None
    assert not created_path.exists()


def test_success_does_not_emit_done_when_both_close_operations_fail(tmp_path: Path) -> None:
    policy_error = RuntimeError("policy close Authorization: Bearer policy-secret")
    client_error = RuntimeError("client close APP_PASSWORD=client-secret")
    client = FakeVoiceLabClient(
        [_response(decision="executed")],
        close_error=client_error,
    )
    policy = FakePolicy(
        [SendMessageAction(message="one")],
        close_error=policy_error,
    )
    events: list[dict] = []

    with pytest.raises(RuntimeError) as raised:
        asyncio.run(
            _runner(client, policy).run(
                environment=FakeEnvironment(tmp_path, "trial-close-only"),
                persona=_persona(),
                runtime=_runtime(max_turns=1),
                task_intent="intent",
                on_event=events.append,
            )
        )

    assert raised.value is policy_error
    assert [event["operation"] for event in events if event["type"] == "error"][-2:] == [
        "policy_close",
        "client_close",
    ]
    assert not any(event["type"] == "done" for event in events)
    assert "policy-secret" not in json.dumps(events)
    assert "client-secret" not in json.dumps(events)


def test_primary_error_precedes_both_close_errors_and_never_emits_done(
    tmp_path: Path,
) -> None:
    primary = VoiceLabContractError("agent_chat APP_PASSWORD=primary-secret")
    policy_error = RuntimeError("policy close token=policy-secret")
    client_error = RuntimeError("client close Authorization: Bearer client-secret")
    client = FakeVoiceLabClient([], chat_errors=[primary], close_error=client_error)
    policy = FakePolicy(
        [SendMessageAction(message="one")],
        close_error=policy_error,
    )
    events: list[dict] = []

    with pytest.raises(VoiceLabContractError) as raised:
        asyncio.run(
            _runner(client, policy).run(
                environment=FakeEnvironment(tmp_path, "trial-primary-close"),
                persona=_persona(),
                runtime=_runtime(max_turns=1),
                task_intent="intent",
                on_event=events.append,
            )
        )

    assert raised.value is primary
    assert [event["operation"] for event in events if event["type"] == "error"] == [
        "voicelab_agent_chat",
        "policy_close",
        "client_close",
    ]
    assert not any(event["type"] == "done" for event in events)
    assert "primary-secret" not in json.dumps(events)
    assert "policy-secret" not in json.dumps(events)
    assert "client-secret" not in json.dumps(events)


def _persona():
    return SimpleNamespace(
        persona_id="persona-1",
        display_name="Anh Hải",
        summary="Thích câu ngắn.",
        system_prompt=None,
        communication={"style": "ngắn"},
        psychology={},
        preferences={},
        behavior={},
        data={},
    )


def _runtime(max_turns: int | None = 4) -> ChatbotTaskConfig:
    return ChatbotTaskConfig(
        runtime_defaults=ChatbotRuntimeDefaults(
            application_id="vita_climate",
            application_context="automotive",
            domain="automotive",
            max_turns=max_turns,
        ),
        protocol=ChatbotProtocolConfig(
            static_body={
                "scenarioId": "climate-temperature",
                "runtimeContext": {"vehicleMotion": "driving"},
            }
        ),
        structured_exposure=(
            ChatbotStructuredExposureField("decision", "Decision", "decision"),
            ChatbotStructuredExposureField("vehicle_state", "Vehicle", "vehicleState", "json"),
            ChatbotStructuredExposureField("tool_result", "Tool", "toolResult", "json"),
        ),
    )


def _questionnaire(**kwargs) -> Questionnaire:
    assert kwargs["task_intent"] == "Đặt điều hòa 22 độ."
    assert kwargs["config"].application_id == "vita_climate"
    assert kwargs["persona"].id == "persona-1"
    assert len(kwargs["transcript"]) == 1
    return Questionnaire(5, "ok", 5, "ok", 5, "ok", False, "")


def test_runner_creates_one_session_and_preserves_voicelab_evidence(tmp_path: Path) -> None:
    client = FakeVoiceLabClient(
        [
            VoiceLabAgentChatResponse.model_validate(
                {
                    "reply": "Đã đặt 22 độ.",
                    "decision": "executed",
                    "vehicleState": {"temperature": 22},
                    "action": {"tool": "set_temperature"},
                    "toolResult": {"ok": True},
                    "capabilityIds": ["climate.set_temperature"],
                    "runtimeContext": {"vehicleMotion": "driving"},
                }
            )
        ]
    )
    policy = FakePolicy([SendMessageAction(message="Cho anh 22 độ.")])
    environment = FakeEnvironment(tmp_path, trial_name="trial-abc")
    runner = UXAgentTrialRunner(
        client=client,
        policy=policy,
        questionnaire_builder=_questionnaire,
    )

    result = asyncio.run(
        runner.run(
            environment=environment,
            persona=_persona(),
            runtime=_runtime(),
            task_intent="Đặt điều hòa 22 độ.",
            on_event=None,
        )
    )

    assert client.calls == [("create_session", "trial-abc"), ("agent_chat", "trial-abc")]
    transcript = json.loads(environment.uploads["/app/output/transcript.json"])
    assert transcript["sessionId"] == "trial-abc"
    assert transcript["applicationId"] == "vita_climate"
    assert transcript["turns"][0]["structuredExposure"][0]["value"] == "executed"
    assert transcript["turns"][0]["structuredExposure"][1]["value"] == {"temperature": 22}
    assert result.metric_scores.num_turns == 1
    assert policy.slow_started is True
    assert len(policy.queued) == 1
    assert policy.closed is True
    assert client.closed is True
    assert "/app/output/application_result.json" in environment.uploads
    assert "/app/output/user_feedback.json" in environment.uploads
    assert "/app/output/uxagent_memory.json" in environment.uploads
def _response(**values) -> VoiceLabAgentChatResponse:
    return VoiceLabAgentChatResponse.model_validate({"reply": "assistant", **values})


def _any_questionnaire(**kwargs) -> Questionnaire:
    return Questionnaire(3, "ok", 3, "ok", 3, "ok", False, "")


def _runner(client, policy, builder=_any_questionnaire) -> UXAgentTrialRunner:
    return UXAgentTrialRunner(
        client=client,
        policy=policy,
        questionnaire_builder=builder,
    )


def test_runner_respects_max_turns_and_passes_full_response_to_next_observation(
    tmp_path: Path,
) -> None:
    client = FakeVoiceLabClient(
        [
            _response(
                vehicleState={"speed": 10},
                action={"name": "keep"},
                toolResult={"ok": True},
                capabilityIds=["drive.read"],
                runtimeContext={"road": "city"},
            ),
            _response(
                vehicleState={"speed": 11},
                action={"name": "keep"},
                toolResult={"ok": True},
                capabilityIds=["drive.read"],
                runtimeContext={"road": "city"},
            ),
            _response(reply="must not be called"),
        ]
    )
    policy = FakePolicy(
        [
            SendMessageAction(message="one"),
            SendMessageAction(message="two"),
            SendMessageAction(message="three"),
        ]
    )
    result = asyncio.run(
        _runner(client, policy).run(
            environment=FakeEnvironment(tmp_path, "trial-max"),
            persona=_persona(),
            runtime=_runtime(max_turns=2),
            task_intent="intent",
        )
    )
    assert result.metric_scores.num_turns == 2
    assert len(client.calls) == 3
    assert policy.observations[0].turn_index == 0
    assert policy.observations[0].assistant_reply == ""
    assert policy.observations[1].assistant_reply == "assistant"
    assert policy.observations[1].vehicle_state == {"speed": 10}
    assert policy.observations[1].action == {"name": "keep"}
    assert policy.observations[1].tool_result == {"ok": True}
    assert policy.observations[1].capability_ids == ["drive.read"]
    assert policy.observations[1].runtime_context == {"road": "city"}


def test_terminal_decisions_and_action_end_reason_stop_after_one_turn(tmp_path: Path) -> None:
    for decision in ("cancelled", "denied", "executed", "failed", "unsupported"):
        client = FakeVoiceLabClient([_response(decision=decision), _response()])
        policy = FakePolicy(
            [SendMessageAction(message="one"), SendMessageAction(message="two")]
        )
        result = asyncio.run(
            _runner(client, policy).run(
                environment=FakeEnvironment(tmp_path, f"trial-{decision}"),
                persona=_persona(),
                runtime=_runtime(max_turns=4),
                task_intent="intent",
            )
        )
        assert result.metric_scores.num_turns == 1
        assert len(client.calls) == 2

    client = FakeVoiceLabClient([_response(), _response()])
    policy = FakePolicy([SendMessageAction(message="one", end_reason="user_done")])
    result = asyncio.run(
        _runner(client, policy).run(
            environment=FakeEnvironment(tmp_path, "trial-end-reason"),
            persona=_persona(),
            runtime=_runtime(max_turns=4),
            task_intent="intent",
        )
    )
    assert result.metric_scores.num_turns == 1
    assert len(client.calls) == 2


def test_policy_failure_is_redacted_and_closes_resources(tmp_path: Path) -> None:
    primary = RuntimeError("invalid policy response APP_PASSWORD=top-secret")
    client = FakeVoiceLabClient([])
    policy = FakePolicy(
        [SendMessageAction(message="one")],
        next_errors=[primary],
    )
    events: list[dict] = []
    with pytest.raises(RuntimeError) as raised:
        asyncio.run(
            _runner(client, policy).run(
                environment=FakeEnvironment(tmp_path, "trial-policy-fail"),
                persona=_persona(),
                runtime=_runtime(),
                task_intent="intent",
                on_event=events.append,
            )
        )
    assert raised.value is primary
    assert events[-1]["operation"] == "uxagent_policy"
    assert "top-secret" not in json.dumps(events)
    assert policy.closed is True
    assert client.closed is True


def test_malformed_chat_response_has_safe_schema_error(tmp_path: Path) -> None:
    policy = FakePolicy([SendMessageAction(message="one")])
    client = FakeVoiceLabClient([{"vehicleState": {"APP_PASSWORD": "top-secret"}}])
    events: list[dict] = []
    with pytest.raises(Exception):
        asyncio.run(
            _runner(client, policy).run(
                environment=FakeEnvironment(tmp_path, "trial-schema-fail"),
                persona=_persona(),
                runtime=_runtime(max_turns=1),
                task_intent="intent",
                on_event=events.append,
            )
        )
    error_event = next(event for event in events if event["type"] == "error")
    assert error_event["operation"] == "voicelab_agent_chat"
    assert error_event["error"]["message"] == "invalid response schema"
    assert "top-secret" not in json.dumps(events)
    assert policy.closed is True
    assert client.closed is True
