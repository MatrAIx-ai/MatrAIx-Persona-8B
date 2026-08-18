"""Tests for Harbor user_sim_chat helpers."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import playground.harbor.chat_eval as chat_eval_module
from playground.harbor.chat_eval import (
    ChatbotTaskConfig,
    harbor_chat_config_from_env,
    harbor_output_artifacts_from_result,
    run_harbor_chat_eval_for_persona,
)
from playground.harbor.chat_sidecar_io import parse_json_stdout
from playground.types import (
    MetricScores,
    Persona,
    PlaygroundConfig,
    PlaygroundResult,
    PlaygroundTurn,
    Questionnaire,
)


def test_harbor_output_artifacts_from_result_maps_chat_contract(monkeypatch):
    monkeypatch.delenv("MATRIX_CHATBOT_DOMAIN", raising=False)
    monkeypatch.delenv("MATRIX_CHATBOT_APPLICATION_ID", raising=False)
    monkeypatch.delenv("MATRIX_CHATBOT_APPLICATION_CONTEXT", raising=False)
    config = harbor_chat_config_from_env()
    assert config.domain == ""
    assert config.application_id == "chatbot"

    persona = Persona(id="0042", name="Test", context="A movie fan.")
    result = PlaygroundResult(
        config=PlaygroundConfig(
            domain="meal_planning",
            application_id="meal_planning_nutrition",
            application_context="meal_planning",
            max_turns=5,
        ),
        persona=persona,
        sut_description="Movie recommender.",
        transcript=[
            PlaygroundTurn(
                turn_index=1,
                user_message="Hi",
                assistant_message="Hello",
                decision="continue",
            ),
            PlaygroundTurn(
                turn_index=2,
                user_message="Something warm",
                assistant_message="Try Past Lives",
                structured_exposure=[
                    {
                        "key": "recommendedItems",
                        "label": "Recommended items",
                        "format": "item_list",
                        "value": [{"id": "movie-past-lives", "title": "Past Lives"}],
                    }
                ],
                decision="satisfied",
            ),
        ],
        questionnaire=Questionnaire(
            constraint_satisfaction=4,
            constraint_rationale="Mostly met.",
            preference_satisfaction=5,
            preference_rationale="Liked it.",
            overall_rating=8,
            rating_reason="Good chat.",
            asked_useful_clarifying_questions=True,
            clarifying_notes="Asked about tone.",
        ),
        metric_scores=MetricScores(num_turns=2),
        created_at="2026-06-30T00:00:00Z",
    )

    artifacts = harbor_output_artifacts_from_result(
        result,
        session_id="sess-1",
        transcript_payload={
            "sessionId": "sess-1",
            "applicationId": "meal_planning_nutrition",
            "applicationContext": "meal_planning",
            "domain": "movie",
            "messages": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"},
                {"role": "user", "content": "Something warm"},
                {"role": "assistant", "content": "Try Past Lives"},
            ],
            "turns": [
                {
                    "turnIndex": 1,
                    "userMessage": "Hi",
                    "assistantMessage": "Hello",
                },
                {
                    "turnIndex": 2,
                    "userMessage": "Something warm",
                    "assistantMessage": "Try Past Lives",
                    "structuredExposure": [
                        {
                            "key": "recommendedItems",
                            "label": "Recommended items",
                            "format": "item_list",
                            "value": [{"id": "movie-past-lives", "title": "Past Lives"}],
                        }
                    ],
                },
            ],
        },
    )
    transcript = artifacts["transcript.json"]
    assert transcript["sessionId"] == "sess-1"
    assert len(transcript["messages"]) == 4
    assert transcript["turns"][1]["structuredExposure"][0]["value"] == [
        {"id": "movie-past-lives", "title": "Past Lives"}
    ]
    application_result = artifacts["application_result.json"]
    assert application_result == {
        "sessionId": "sess-1",
        "applicationId": "meal_planning_nutrition",
        "applicationContext": "meal_planning",
        "turnCount": 2,
        "config": result.config.to_dict(),
        "prompts": {},
    }
    feedback = artifacts["user_feedback.json"]
    assert feedback["needConstraintSatisfaction"] == "yes"
    assert feedback["personalPreferenceSatisfaction"] == "yes"
    assert feedback["overallExperienceRating"] == 8


def test_parse_json_stdout_skips_shell_profile_noise():
    raw = (
        'export JAVA_HOME=$(/usr/libexec/java_home) {"sessionId": "abc", "reply": "hi"}'
    )
    parsed = parse_json_stdout(raw)
    assert parsed["sessionId"] == "abc"
    assert parsed["reply"] == "hi"


def test_harbor_chat_config_from_env_defaults_to_unlimited_turns(tmp_path, monkeypatch):
    input_dir = (
        tmp_path
        / "application"
        / "tasks"
        / "chat_meal-planning-nutrition"
        / "input"
    )
    input_dir.mkdir(parents=True)
    (input_dir / "chatbot.yaml").write_text(
        "\n".join(
            [
                "transport: external_http",
                "runtimeDefaults:",
                "  applicationId: meal_planning_nutrition",
                "  applicationContext: meal_planning",
                "  maxTurns: 11",
                "connection:",
                "  baseUrl: http://meal-plan-api:8000",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "MATRIX_CHATBOT_TASK_PATH",
        "application/tasks/chat_meal-planning-nutrition",
    )
    monkeypatch.delenv("MATRIX_CHATBOT_APPLICATION_ID", raising=False)
    monkeypatch.delenv("MATRIX_CHATBOT_APPLICATION_CONTEXT", raising=False)
    monkeypatch.delenv("MATRIX_CHATBOT_DOMAIN", raising=False)
    monkeypatch.delenv("MATRIX_CHATBOT_MAX_TURNS", raising=False)

    config = harbor_chat_config_from_env(repo_root=tmp_path)
    assert config.application_id == "meal_planning_nutrition"
    assert config.application_context == "meal_planning"
    assert config.domain == ""
    assert config.max_turns is None


def test_harbor_chat_config_from_env_prefers_harbor_model_name(monkeypatch) -> None:
    monkeypatch.setenv("MATRIX_PERSONA_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("MATRIX_CHATBOT_PERSONA_MODEL", "anthropic/claude-haiku-4-5")

    config = harbor_chat_config_from_env(model_name="anthropic/claude-sonnet-4-6")
    assert config.persona_model == "anthropic/claude-sonnet-4-6"


def test_harbor_chat_config_from_env_records_persona_language_source(monkeypatch):
    monkeypatch.setenv("MATRIX_PERSONA_LANGUAGE", "zh-Hans")
    monkeypatch.setenv("MATRIX_PERSONA_LANGUAGE_SOURCE", "follow_ui")

    config = harbor_chat_config_from_env()

    assert config.persona_language == "zh-Hans"
    assert config.persona_language_source == "follow_ui"


@pytest.mark.anyio
async def test_run_harbor_chat_eval_passes_language_and_source_to_runner(monkeypatch):
    received: dict[str, str] = {}

    async def fake_run_playground_async(*args, **kwargs):
        del args
        received["persona_language"] = kwargs["persona_language"]
        received["persona_language_source"] = kwargs["persona_language_source"]
        return "result"

    monkeypatch.setattr(
        "playground.user_sim.runner.run_playground_async",
        fake_run_playground_async,
    )

    result = await chat_eval_module.run_harbor_chat_eval(
        object(),
        Persona(id="p1", name="Persona One"),
        "A chatbot.",
        PlaygroundConfig(),
        created_at="2026-06-30T00:00:00Z",
        persona_language="zh-Hant",
        persona_language_source="follow_ui",
    )

    assert result == "result"
    assert received == {
        "persona_language": "zh-Hant",
        "persona_language_source": "follow_ui",
    }


@pytest.mark.anyio
async def test_run_harbor_chat_eval_for_persona_writes_output_artifacts(
    tmp_path, monkeypatch
):
    uploaded: dict[str, dict] = {}
    received_config: dict[str, str] = {}

    class FakeEnvironment:
        def __init__(self) -> None:
            self.trial_paths = SimpleNamespace(trial_dir=tmp_path / "trial")
            self.trial_paths.trial_dir.mkdir(parents=True, exist_ok=True)

        async def upload_file(self, source: Path, destination: str) -> None:
            uploaded[destination] = json.loads(Path(source).read_text(encoding="utf-8"))

    class FakePersona:
        persona_id = "p1"
        display_name = "Persona One"
        summary = ""
        system_prompt = "Persona context"
        persona_path = ""
        data = {"source": "fixture"}

    async def fake_run_harbor_chat_eval(
        session,
        persona,
        sut_description,
        config,
        *,
        created_at,
        on_event=None,
        task_path=None,
        persona_yaml_path=None,
        repo_root=None,
        job_dir=None,
        persona_language=None,
        persona_language_source=None,
    ):
        del (
            persona,
            sut_description,
            created_at,
            on_event,
            task_path,
            persona_yaml_path,
            repo_root,
            job_dir,
        )
        received_config["persona_language"] = config.persona_language
        received_config["persona_language_source"] = config.persona_language_source
        assert persona_language is None
        assert persona_language_source is None
        session._session_id = "sess-1"
        return PlaygroundResult(
            config=config,
            persona=Persona(id="p1", name="Persona One", context="Persona context"),
            sut_description="Movie recommender.",
            transcript=[
                PlaygroundTurn(
                    turn_index=1,
                    user_message="Hi",
                    assistant_message="Hello",
                    decision="continue",
                ),
                PlaygroundTurn(
                    turn_index=2,
                    user_message="Something warm",
                    assistant_message="Try Past Lives",
                    structured_exposure=[
                        {
                            "key": "recommendedItems",
                            "label": "Recommended items",
                            "format": "item_list",
                            "value": [{"id": "movie-past-lives", "title": "Past Lives"}],
                        }
                    ],
                    decision="satisfied",
                ),
            ],
            questionnaire=Questionnaire(
                constraint_satisfaction=4,
                constraint_rationale="Mostly met.",
                preference_satisfaction=5,
                preference_rationale="Liked it.",
                overall_rating=8,
                rating_reason="Good chat.",
                asked_useful_clarifying_questions=True,
                clarifying_notes="Asked about tone.",
            ),
            metric_scores=MetricScores(num_turns=2),
            created_at="2026-06-30T00:00:00Z",
        )

    async def fake_fetch_conversation(self):
        return {
            "messages": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"},
                {"role": "user", "content": "Something warm"},
                {"role": "assistant", "content": "Try Past Lives"},
            ],
            "turns": [
                {
                    "turnIndex": 1,
                    "userMessage": "Hi",
                    "assistantMessage": "Hello",
                },
                {
                    "turnIndex": 2,
                    "userMessage": "Something warm",
                    "assistantMessage": "Try Past Lives",
                    "structuredExposure": [
                        {
                            "key": "recommendedItems",
                            "label": "Recommended items",
                            "format": "item_list",
                            "value": [{"id": "movie-past-lives", "title": "Past Lives"}],
                        }
                    ],
                },
            ],
        }

    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        chat_eval_module,
        "harbor_chat_task_config_from_env",
        lambda **_kwargs: ChatbotTaskConfig(),
    )
    monkeypatch.setattr(
        chat_eval_module,
        "harbor_chat_config_from_env",
        lambda **_kwargs: PlaygroundConfig(
            domain="movie",
            application_id="meal_planning_nutrition",
            application_context="meal_planning",
            engine="gpt-4o-mini",
            persona_language="zh-Hans",
            persona_language_source="follow_ui",
        ),
    )
    monkeypatch.setattr(
        chat_eval_module,
        "load_task_content_bundle_for_task_path",
        lambda *_args, **_kwargs: SimpleNamespace(
            context_markdown="Movie recommender.",
            instruction_markdown="",
        ),
    )
    monkeypatch.setattr(chat_eval_module, "run_harbor_chat_eval", fake_run_harbor_chat_eval)
    monkeypatch.setattr(
        chat_eval_module.HarborSidecarChatSession,
        "fetch_conversation_artifact",
        fake_fetch_conversation,
    )

    result, session_id = await run_harbor_chat_eval_for_persona(
        FakeEnvironment(),
        FakePersona(),
    )

    assert session_id == "sess-1"
    assert received_config == {
        "persona_language": "zh-Hans",
        "persona_language_source": "follow_ui",
    }
    assert result.metric_scores.num_turns == 2
    assert uploaded["/app/output/transcript.json"]["messages"][3]["content"] == "Try Past Lives"
    assert uploaded["/app/output/transcript.json"]["sessionId"] == "sess-1"
    assert uploaded["/app/output/application_result.json"]["turnCount"] == 2
    assert uploaded["/app/output/application_result.json"]["config"][
        "effectiveLanguage"
    ] == "zh-Hans"
    assert uploaded["/app/output/application_result.json"]["config"][
        "languageSource"
    ] == "follow_ui"
    assert uploaded["/app/output/application_result.json"]["prompts"] == result.prompts
    assert uploaded["/app/output/user_feedback.json"]["overallExperienceRating"] == 8
