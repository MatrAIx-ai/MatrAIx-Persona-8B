"""Run one VoiceLab-backed UXAgent persona trial."""

from __future__ import annotations

import inspect
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from playground.harbor.chat_eval import harbor_output_artifacts_from_result
from playground.structured_exposure import normalize_transcript_payload
from playground.types import (
    MetricScores,
    Persona,
    PlaygroundConfig,
    PlaygroundResult,
    PlaygroundTurn,
    Questionnaire,
)
from playground.user_sim.port import normalize_agent_turn
from playground.uxagent.mapping import build_chat_request, build_persona_session_request
from playground.uxagent.models import VoiceLabAgentChatResponse, UXObservation

_TERMINAL_DECISIONS = {"cancelled", "denied", "executed", "failed", "unsupported"}
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(app[_ -]?password|x-app-password|api[_ -]?key|authorization|bearer|token|secret|password)"
    r"\s*[:=]\s*([^\s,;]+)"
)


QuestionnaireBuilder = Callable[
    [Persona, Sequence[PlaygroundTurn], PlaygroundConfig, str], Questionnaire
]
"""Build a questionnaire from ``persona``, ``transcript``, ``config``, and ``task_intent``.

The runner calls the injected synchronous callable with keyword arguments:
``persona=Persona``, ``transcript=list[PlaygroundTurn]``,
``config=PlaygroundConfig``, and ``task_intent=str``.
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _redact_text(value: object) -> str:
    text = str(value)
    return _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    return value


def _persona_from_loaded(persona: object) -> Persona:
    data = getattr(persona, "data", {}) or {}
    if not isinstance(data, Mapping):
        data = {}
    return Persona(
        id=str(getattr(persona, "persona_id", None) or data.get("persona_id") or "persona"),
        name=str(getattr(persona, "display_name", None) or data.get("name") or "Persona"),
        summary=str(getattr(persona, "summary", None) or data.get("summary") or ""),
        context=str(
            getattr(persona, "system_prompt", None)
            or data.get("context")
            or getattr(persona, "summary", "")
            or ""
        ),
        source=str(data.get("source") or ""),
    )


def _config_from_runtime(runtime: Any) -> PlaygroundConfig:
    defaults = runtime.runtime_defaults
    domain = str(defaults.domain or defaults.application_context or "")
    application_context = str(defaults.application_context or domain)
    return PlaygroundConfig(
        domain=domain,
        application_id=str(defaults.application_id or "recai"),
        application_context=application_context,
        max_turns=defaults.max_turns,
    )


def _terminal(response: Mapping[str, Any], structured_exposure: Sequence[Mapping[str, Any]]) -> bool:
    decision = str(response.get("decision") or "").strip().lower()
    if decision in _TERMINAL_DECISIONS:
        return True
    return any(
        item.get("key") == "decision"
        and str(item.get("value") or "").strip().lower() in _TERMINAL_DECISIONS
        for item in structured_exposure
    )


class UXAgentTrialRunner:
    """Own the per-trial VoiceLab session, policy loop, and output artifacts."""

    def __init__(
        self,
        *,
        client: Any,
        policy: Any,
        questionnaire_builder: QuestionnaireBuilder,
    ) -> None:
        self.client = client
        self.policy = policy
        self.questionnaire_builder = questionnaire_builder

    async def run(
        self,
        *,
        environment: Any,
        persona: object,
        runtime: Any,
        task_intent: str,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> PlaygroundResult:
        """Run a trial and upload its transcript, feedback, result, and UX memory.

        ``questionnaire_builder`` is synchronous and receives the converted
        ``Persona``, the completed ``PlaygroundTurn`` sequence, the generated
        ``PlaygroundConfig``, and the task intent as keyword arguments.
        """
        session_id = str(environment.trial_paths.trial_dir.name)
        config = _config_from_runtime(runtime)
        eval_persona = _persona_from_loaded(persona)
        turns: list[PlaygroundTurn] = []
        operation = "create_session"
        primary_error: BaseException | None = None

        def emit(event: dict[str, Any]) -> None:
            if on_event is not None:
                on_event(event)

        def emit_error(error_operation: str, error: BaseException) -> None:
            error_type = type(error).__name__
            safe_message = (
                "invalid response schema"
                if error_type == "ValidationError"
                else _redact_text(error)
            )
            emit(
                {
                    "type": "error",
                    "operation": error_operation,
                    "error": {
                        "type": error_type,
                        "message": safe_message,
                    },
                }
            )

        try:
            emit({"type": "phase", "phase": "persona_session"})
            session_request = build_persona_session_request(
                persona=persona,
                runtime=runtime,
                session_id=session_id,
            )
            await self.client.create_session(session_request)

            self.policy.start_slow_loop()
            observation = UXObservation(task_intent=task_intent, turn_index=0)
            max_turns = runtime.runtime_defaults.max_turns or 4
            for index in range(1, max_turns + 1):
                operation = "uxagent_policy"
                emit({"type": "phase", "phase": "persona_thinking", "turnIndex": index})
                action = await self.policy.next_action(observation)
                message = str(action.message or "").strip()
                emit({"type": "user_message", "turnIndex": index, "message": _redact_text(message)})
                emit({"type": "phase", "phase": "application_thinking", "userMessage": _redact_text(message)})

                operation = "voicelab_agent_chat"
                request = build_chat_request(
                    message=message,
                    runtime=runtime,
                    session_id=session_id,
                )
                response = await self.client.agent_chat(request)
                if not isinstance(response, VoiceLabAgentChatResponse):
                    response = VoiceLabAgentChatResponse.model_validate(response, strict=True)
                response_fields = response.model_dump(by_alias=True)
                view = normalize_agent_turn(
                    response_fields,
                    message,
                    structured_exposure_fields=runtime.structured_exposure,
                )
                assistant = str(view.get("assistantMessage") or "")
                structured_exposure = list(view.get("structuredExposure") or [])
                emit(
                    {
                        "type": "assistant_message",
                        "turnIndex": index,
                        "userMessage": _redact_text(message),
                        "assistantMessage": _redact_text(assistant),
                        "structuredExposure": _redact_value(structured_exposure),
                        "durationSeconds": view.get("durationSeconds"),
                    }
                )

                terminal = _terminal(response_fields, structured_exposure)
                decision = str(
                    response_fields.get("decision")
                    or action.end_reason
                    or ("satisfied" if terminal else "continue")
                )
                turn = PlaygroundTurn(
                    turn_index=index,
                    user_message=message,
                    assistant_message=assistant,
                    structured_exposure=structured_exposure,
                    decision=decision,
                    duration_seconds=view.get("durationSeconds"),
                )
                turns.append(turn)
                emit({"type": "turn", "turn": _redact_value(turn.to_dict())})

                observation = UXObservation(
                    task_intent=task_intent,
                    turn_index=index,
                    assistant_reply=str(response_fields.get("reply") or ""),
                    decision=response_fields.get("decision"),
                    vehicle_state=response_fields.get("vehicleState"),
                    action=response_fields.get("action"),
                    tool_result=response_fields.get("toolResult"),
                    capability_ids=list(response_fields.get("capabilityIds") or []),
                    runtime_context=dict(response_fields.get("runtimeContext") or {}),
                )
                await self.policy.enqueue_slow_observation(observation)
                if terminal or action.end_reason:
                    break

            operation = "uxagent_policy_slow_loop"
            wait_idle = getattr(self.policy, "wait_until_slow_idle", None)
            if callable(wait_idle):
                result = wait_idle()
                if inspect.isawaitable(result):
                    await result

            operation = "questionnaire_builder"
            questionnaire = self.questionnaire_builder(
                persona=eval_persona,
                transcript=list(turns),
                config=config,
                task_intent=task_intent,
            )
            if not isinstance(questionnaire, Questionnaire):
                raise TypeError("questionnaire_builder must return Questionnaire")

            result = PlaygroundResult(
                config=config,
                persona=eval_persona,
                sut_description=task_intent,
                transcript=turns,
                questionnaire=questionnaire,
                metric_scores=MetricScores(num_turns=len(turns)),
                created_at=_utc_now(),
            )
            transcript_payload = normalize_transcript_payload(
                {
                    "sessionId": session_id,
                    "applicationId": config.application_id,
                    "applicationContext": config.application_context or config.domain,
                    "domain": config.domain or config.application_context,
                    "turns": [turn.to_dict() for turn in turns],
                },
                fields=runtime.structured_exposure,
            )
            artifacts = harbor_output_artifacts_from_result(
                result,
                session_id=session_id,
                transcript_payload=transcript_payload,
            )
            artifacts["uxagent_memory.json"] = self._memory_payload(session_id)
            operation = "artifact_upload"
            await self._upload_artifacts(environment, artifacts)
            emit({"type": "done", "result": _redact_value(result.to_dict())})
            return result
        except BaseException as error:
            primary_error = error
            emit_error(operation, error)
            if turns:
                try:
                    await self._upload_partial(environment, session_id, config, turns)
                except BaseException as cleanup_error:
                    emit_error("partial_artifact_upload", cleanup_error)
            raise
        finally:
            close_errors: list[tuple[str, BaseException]] = []
            try:
                await self.policy.close()
            except BaseException as error:
                close_errors.append(("policy_close", error))
            try:
                await self.client.close()
            except BaseException as error:
                close_errors.append(("client_close", error))
            for close_operation, close_error in close_errors:
                if primary_error is not None:
                    emit_error(close_operation, close_error)
                else:
                    emit_error(close_operation, close_error)
                    raise close_error

    def _memory_payload(self, session_id: str) -> dict[str, Any]:
        memories = []
        for memory in self.policy.memories:
            if hasattr(memory, "model_dump"):
                payload = memory.model_dump(mode="json")
            elif isinstance(memory, Mapping):
                payload = dict(memory)
            else:
                payload = {"content": str(memory)}
            memories.append(_redact_value(payload))
        return {"sessionId": session_id, "memories": memories}

    async def _upload_partial(
        self,
        environment: Any,
        session_id: str,
        config: PlaygroundConfig,
        turns: Sequence[PlaygroundTurn],
    ) -> None:
        transcript_payload = normalize_transcript_payload(
            {
                "sessionId": session_id,
                "applicationId": config.application_id,
                "applicationContext": config.application_context or config.domain,
                "domain": config.domain or config.application_context,
                "turns": [turn.to_dict() for turn in turns],
            },
            fields=None,
        )
        await self._upload_artifacts(
            environment,
            {
                "transcript.json": transcript_payload,
                "uxagent_memory.json": self._memory_payload(session_id),
            },
        )

    async def _upload_artifacts(
        self,
        environment: Any,
        artifacts: Mapping[str, Mapping[str, Any]],
    ) -> None:
        for filename, payload in artifacts.items():
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", suffix=".json", delete=False
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                temp_path = Path(handle.name)
            try:
                uploaded = environment.upload_file(temp_path, f"/app/output/{filename}")
                if inspect.isawaitable(uploaded):
                    await uploaded
            finally:
                temp_path.unlink(missing_ok=True)
