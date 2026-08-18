import json
from pathlib import Path

import pytest
import yaml

from playground.harbor import playground as harbor_playground_module
from playground.harbor.playground import (
    HarborPlaygroundRunner,
    _default_harbor_command,
    _harbor_failure_summary,
    build_chatbot_simulation_prompt,
    build_result_from_harbor_artifacts,
    resolve_repo_root,
    write_harbor_persona_yaml,
)
from playground.types import Persona, PlaygroundConfig


def test_build_result_from_harbor_artifacts_maps_transcript_feedback_and_metrics(
    tmp_path,
):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "transcript.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "domain": "movie",
                "messages": [
                    {
                        "role": "user",
                        "content": "I want something tense but not graphic.",
                    },
                    {
                        "role": "assistant",
                        "content": "Do you prefer mainstream or lesser-known films?",
                    },
                    {"role": "user", "content": "Lesser-known is fine if it fits."},
                    {"role": "assistant", "content": "Try Movie A."},
                ],
                "turns": [
                    {
                        "turnId": "0",
                        "conversationId": "ses_123",
                        "backend": "interecagent",
                        "userMessage": "I want something tense but not graphic.",
                        "assistantMessage": "Do you prefer mainstream or lesser-known films?",
                        "plan": [],
                        "structuredExposure": [],
                        "nativeRaw": None,
                        "rawToolOutputs": None,
                    },
                    {
                        "turnId": "1",
                        "conversationId": "ses_123",
                        "backend": "interecagent",
                        "userMessage": "Lesser-known is fine if it fits.",
                        "assistantMessage": "Try Movie A.",
                        "plan": [],
                        "structuredExposure": [
                            {
                                "key": "recommendedItems",
                                "label": "Recommended items",
                                "format": "item_list",
                                "value": [
                                    {"itemId": "42", "title": "Movie A", "rank": 1}
                                ],
                            }
                        ],
                        "nativeRaw": None,
                        "rawToolOutputs": None,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "application_result.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "domain": "movie",
                "recommendedItems": [{"itemId": "42", "title": "Movie A"}],
                "turnsToResult": 2,
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "user_feedback.json").write_text(
        json.dumps(
            {
                "needConstraintSatisfaction": "partially",
                "personalPreferenceSatisfaction": "yes",
                "overallExperienceRating": 8,
                "reason": "The final choice fit, but the first response was broad.",
                "askedUsefulClarificationQuestions": True,
            }
        ),
        encoding="utf-8",
    )

    result = build_result_from_harbor_artifacts(
        output_dir=output_dir,
        config=PlaygroundConfig(domain="movie", engine="gpt-4o-mini", max_turns=8),
        persona=Persona(id="p1", name="Persona One", source="fixture"),
        sut_description="Movie recommender.",
        created_at="2026-06-23T00:00:00Z",
        prompts={
            "harborPrompt": "Persona system prompt.",
            "taskPrompt": "Task prompt.",
        },
    )

    assert result.turn_views[1]["structuredExposure"][0]["value"] == [
        {"itemId": "42", "title": "Movie A", "rank": 1}
    ]
    payload = result.to_dict()
    assert payload["config"]["domain"] == "movie"
    assert payload["persona"]["name"] == "Persona One"
    assert payload["transcript"][1]["assistantMessage"] == "Try Movie A."
    assert payload["prompts"] == {
        "harborPrompt": "Persona system prompt.",
        "taskPrompt": "Task prompt.",
    }
    assert payload["questionnaire"] == {
        "constraintSatisfaction": 3,
        "constraintRationale": "",
        "preferenceSatisfaction": 5,
        "preferenceRationale": "",
        "overallRating": 8,
        "ratingReason": "The final choice fit, but the first response was broad.",
        "askedUsefulClarifyingQuestions": True,
        "clarifyingNotes": "",
    }
    assert payload["metricScores"] == {"numTurns": 2}


def test_build_result_from_harbor_artifacts_maps_persona_self_report_keys(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "transcript.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "domain": "movie",
                "messages": [
                    {"role": "user", "content": "I want a movie."},
                    {"role": "assistant", "content": "Try Movie A."},
                ],
                "turns": [
                    {
                        "turnId": "0",
                        "userMessage": "I want a movie.",
                        "assistantMessage": "Try Movie A.",
                        "structuredExposure": [{"key": "recommendedItems", "label": "Recommended items", "format": "item_list", "value": [{"itemId": "42", "title": "Movie A"}]}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "application_result.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "domain": "movie",
                "recommendedItems": [{"itemId": "42", "title": "Movie A"}],
                "turnsToResult": 1,
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "user_feedback.json").write_text(
        json.dumps(
            {
                "needConstraintSatisfaction": "partially",
                "personalPreferenceSatisfaction": "no",
                "overallExperienceRating": 6,
                "reason": "Legacy persona self-report.",
                "askedUsefulClarificationQuestions": True,
            }
        ),
        encoding="utf-8",
    )

    result = build_result_from_harbor_artifacts(
        output_dir=output_dir,
        config=PlaygroundConfig(domain="movie"),
        persona=Persona(id="p1", name="Persona One", source="fixture"),
        sut_description="Movie recommender.",
        created_at="2026-06-23T00:00:00Z",
    )

    questionnaire = result.to_dict()["questionnaire"]
    assert questionnaire["constraintSatisfaction"] == 3
    assert questionnaire["preferenceSatisfaction"] == 1
    assert questionnaire["overallRating"] == 6


def test_build_result_from_harbor_artifacts_normalizes_legacy_turn_fields(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "transcript.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_legacy",
                "domain": "movie",
                "turns": [
                    {
                        "index": 1,
                        "userMessage": "I want a thoughtful movie.",
                        "assistantReply": "Try Movie A.",
                        "structuredExposure": [{"key": "recommendedItems", "label": "Recommended items", "format": "item_list", "value": [{"itemId": "42", "title": "Movie A"}]}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "application_result.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_legacy",
                "domain": "movie",
                "recommendedItems": [{"itemId": "42", "title": "Movie A"}],
                "turnsToResult": 1,
            }
        ),
        encoding="utf-8",
    )

    result = build_result_from_harbor_artifacts(
        output_dir=output_dir,
        config=PlaygroundConfig(domain="movie"),
        persona=Persona(id="p1", name="Persona One", source="fixture"),
        sut_description="Movie recommender.",
        created_at="2026-06-23T00:00:00Z",
    )

    turn = result.to_dict()["transcript"][0]
    assert turn["turnId"] == "1"
    assert turn["conversationId"] == "ses_legacy"
    assert turn["assistantMessage"] == "Try Movie A."


def test_build_result_from_harbor_artifacts_fills_application_result_from_transcript(
    tmp_path,
):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "transcript.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "domain": "movie",
                "turns": [
                    {
                        "turnId": "0",
                        "userMessage": "I want a movie.",
                        "assistantMessage": "Try Movie A.",
                        "structuredExposure": [{"key": "recommendedItems", "label": "Recommended items", "format": "item_list", "value": [{"itemId": "42", "title": "Movie A"}]}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "application_result.json").write_text("{}", encoding="utf-8")

    result = build_result_from_harbor_artifacts(
        output_dir=output_dir,
        config=PlaygroundConfig(domain="movie"),
        persona=Persona(id="p1", name="Persona One", source="fixture"),
        sut_description="Movie recommender.",
        created_at="2026-06-23T00:00:00Z",
    )

    payload = result.to_dict()
    assert payload["metricScores"]["numTurns"] == 1


def test_build_result_from_harbor_artifacts_allows_general_chatbot_without_items(
    tmp_path,
):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "transcript.json").write_text(
        json.dumps(
            {
                "sessionId": "fin_ses_123",
                "applicationId": "finance_openbb",
                "applicationContext": "financial_research",
                "domain": "financial_research",
                "messages": [
                    {"role": "user", "content": "Can you help me compare bank stocks?"},
                    {
                        "role": "assistant",
                        "content": "What time horizon and risk constraints matter?",
                    },
                ],
                "turns": [
                    {
                        "turnId": "0",
                        "userMessage": "Can you help me compare bank stocks?",
                        "assistantMessage": (
                            "What time horizon and risk constraints matter?"
                        ),
                        "structuredExposure": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "application_result.json").write_text(
        json.dumps(
            {
                "sessionId": "fin_ses_123",
                "applicationId": "finance_openbb",
                "applicationContext": "financial_research",
                "domain": "financial_research",
                "recommendedItems": [],
                "turnsToResult": 1,
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "user_feedback.json").write_text(
        json.dumps(
            {
                "needConstraintSatisfaction": 2,
                "personalPreferenceSatisfaction": 2,
                "overallExperienceRating": 3,
                "reason": "The chatbot only asked a clarifying question.",
                "askedUsefulClarificationQuestions": True,
            }
        ),
        encoding="utf-8",
    )

    result = build_result_from_harbor_artifacts(
        output_dir=output_dir,
        config=PlaygroundConfig(
            application_id="finance_openbb",
            application_context="financial_research",
            domain="movie",
            engine="gpt-4o-mini",
            max_turns=1,
        ),
        persona=Persona(id="p1", name="Persona One", source="fixture"),
        sut_description="Finance chatbot.",
        created_at="2026-06-23T00:00:00Z",
    )

    payload = result.to_dict()
    assert payload["metricScores"]["numTurns"] == 1
    assert payload["questionnaire"]["overallRating"] == 3


def test_build_result_from_harbor_artifacts_accepts_application_scorer_questionnaire(
    tmp_path,
):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "transcript.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "domain": "movie",
                "messages": [
                    {"role": "user", "content": "I want a movie."},
                    {"role": "assistant", "content": "Try Movie A."},
                ],
                "turns": [
                    {
                        "turnId": "0",
                        "conversationId": "ses_123",
                        "backend": "interecagent",
                        "userMessage": "I want a movie.",
                        "assistantMessage": "Try Movie A.",
                        "structuredExposure": [{"key": "recommendedItems", "label": "Recommended items", "format": "item_list", "value": [{"itemId": "42", "title": "Movie A"}]}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "application_result.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "domain": "movie",
                "recommendedItems": [{"itemId": "42", "title": "Movie A"}],
                "turnsToResult": 1,
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "user_feedback.json").write_text(
        json.dumps(
            {
                "needConstraintSatisfaction": "partially",
                "personalPreferenceSatisfaction": 5,
                "overallExperienceRating": 8,
                "reason": "Good grounded recommendation.",
                "askedUsefulClarificationQuestions": True,
                "clarifyingNotes": "The agent asked about tone.",
            }
        ),
        encoding="utf-8",
    )

    result = build_result_from_harbor_artifacts(
        output_dir=output_dir,
        config=PlaygroundConfig(domain="movie"),
        persona=Persona(id="p1", name="Persona One"),
        sut_description="Movie recommender.",
        created_at="2026-06-23T00:00:00Z",
    )

    assert result.to_dict()["questionnaire"] == {
        "constraintSatisfaction": 3,
        "constraintRationale": "",
        "preferenceSatisfaction": 5,
        "preferenceRationale": "",
        "overallRating": 8,
        "ratingReason": "Good grounded recommendation.",
        "askedUsefulClarifyingQuestions": True,
        "clarifyingNotes": "The agent asked about tone.",
    }


def test_build_result_from_harbor_artifacts_maps_turns_to_result(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "transcript.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "applicationId": "meal_planning_nutrition",
                "applicationContext": "meal_planning",
                "domain": "movie",
                "messages": [
                    {"role": "user", "content": "I want a movie."},
                    {"role": "assistant", "content": "Try Movie A."},
                ],
                "turns": [
                    {
                        "turnId": "0",
                        "userMessage": "I want a movie.",
                        "assistantMessage": "Try Movie A.",
                        "structuredExposure": [{"key": "recommendedItems", "label": "Recommended items", "format": "item_list", "value": [{"itemId": "42", "title": "Movie A"}]}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "application_result.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "applicationId": "meal_planning_nutrition",
                "applicationContext": "meal_planning",
                "domain": "movie",
                "recommendedItems": [{"itemId": "42", "title": "Movie A"}],
                "turnsToResult": 1,
            }
        ),
        encoding="utf-8",
    )

    result = build_result_from_harbor_artifacts(
        output_dir=output_dir,
        config=PlaygroundConfig(
            domain="movie",
            application_id="meal_planning_nutrition",
            application_context="meal_planning",
            engine="gpt-4o-mini",
            max_turns=3,
        ),
        persona=Persona(id="p1", name="Persona One", source="fixture"),
        sut_description="Movie chatbot.",
        created_at="2026-06-23T00:00:00Z",
    )

    assert result.to_dict()["metricScores"]["numTurns"] == 1


def test_build_result_from_harbor_artifacts_reads_verifier_feedback(tmp_path):
    trial_dir = tmp_path / "trial"
    output_dir = trial_dir / "artifacts" / "app" / "output"
    verifier_dir = trial_dir / "verifier"
    output_dir.mkdir(parents=True)
    verifier_dir.mkdir()
    (output_dir / "transcript.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "domain": "movie",
                "messages": [
                    {"role": "user", "content": "I want a movie."},
                    {"role": "assistant", "content": "Try Movie A."},
                ],
                "turns": [
                    {
                        "turnId": "0",
                        "userMessage": "I want a movie.",
                        "assistantMessage": "Try Movie A.",
                        "structuredExposure": [{"key": "recommendedItems", "label": "Recommended items", "format": "item_list", "value": [{"itemId": "42", "title": "Movie A"}]}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "application_result.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "domain": "movie",
                "recommendedItems": [{"itemId": "42", "title": "Movie A"}],
                "turnsToResult": 1,
            }
        ),
        encoding="utf-8",
    )
    (verifier_dir / "user_feedback.json").write_text(
        json.dumps(
            {
                "needConstraintSatisfaction": "partially",
                "personalPreferenceSatisfaction": 5,
                "overallExperienceRating": 8,
                "reason": "Verifier scorer output.",
                "askedUsefulClarificationQuestions": True,
                "clarifyingNotes": "The agent asked about tone.",
            }
        ),
        encoding="utf-8",
    )

    result = build_result_from_harbor_artifacts(
        output_dir=output_dir,
        config=PlaygroundConfig(domain="movie"),
        persona=Persona(id="p1", name="Persona One"),
        sut_description="Movie recommender.",
        created_at="2026-06-23T00:00:00Z",
    )

    questionnaire = result.to_dict()["questionnaire"]
    assert questionnaire["overallRating"] == 8
    assert questionnaire["ratingReason"] == "Verifier scorer output."
    assert questionnaire["constraintRationale"] == ""
    assert questionnaire["preferenceRationale"] == ""
    assert questionnaire["clarifyingNotes"] == "The agent asked about tone."


def test_build_result_from_harbor_artifacts_ignores_legacy_application_result_fields(
    tmp_path,
):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "transcript.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "domain": "movie",
                "messages": [
                    {"role": "user", "content": "I want a thoughtful movie."},
                    {"role": "assistant", "content": "What tone do you prefer?"},
                    {"role": "user", "content": "Quiet and reflective."},
                    {"role": "assistant", "content": "Any settings you like?"},
                    {"role": "user", "content": "Asian cinema would be good."},
                    {"role": "assistant", "content": "Here are some ideas."},
                ],
                "turns": [],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "application_result.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "domain": "movie",
                "recommendedItems": [
                    {"itemId": "movie_0001", "title": "Invented Movie"}
                ],
                "turnsToResult": 3,
            }
        ),
        encoding="utf-8",
    )

    result = build_result_from_harbor_artifacts(
        output_dir=output_dir,
        config=PlaygroundConfig(domain="movie", engine="gpt-4o-mini", max_turns=8),
        persona=Persona(id="p1", name="Persona One", source="fixture"),
        sut_description="Movie recommender.",
        created_at="2026-06-23T00:00:00Z",
    )

    assert result.to_dict()["metricScores"]["numTurns"] == 3


def test_write_harbor_persona_yaml_uses_persona_context_as_system_prompt(tmp_path):
    persona = Persona(
        id="p1",
        name="Persona One",
        source="fixture",
        summary="A careful viewer.",
        context="Name: Persona One\nHow you talk: concise and skeptical",
    )

    path = write_harbor_persona_yaml(tmp_path, persona)

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data == {
        "persona_id": "p1",
        "display_name": "Persona One",
        "summary": "A careful viewer.",
        "system_prompt": "Name: Persona One\nHow you talk: concise and skeptical",
    }


def test_build_chatbot_simulation_prompt_uses_generic_application_contract():
    prompt = build_chatbot_simulation_prompt(
        application_id="finance_openbb",
        application_context="financial_research",
        max_turns=7,
        sut_description="A financial research chatbot exposed through a chat API.",
    )

    assert prompt.startswith("You are a user of a financial research system")
    assert "# Controller input" not in prompt
    assert "This section is consumed by the chatbot task controller." not in prompt
    assert "Harbor supplies your persona" not in prompt
    assert "You are a user of a financial research system" in prompt
    assert "Application id:" not in prompt
    assert "Application context:" not in prompt
    assert "finance_openbb" not in prompt
    assert "financial_research" not in prompt
    assert '"applicationId": "finance_openbb"' not in prompt
    assert '"applicationContext": "financial_research"' not in prompt
    assert "Required behavior" not in prompt
    assert "at least three user turns and three assistant turns" not in prompt
    assert "application_result.json" not in prompt
    assert "recommendation_result.json" not in prompt
    assert "recommender" not in prompt.lower()
    assert "Finish within 7 user turns." in prompt


def test_build_chatbot_simulation_prompt_labels_meal_planning():
    prompt = build_chatbot_simulation_prompt(
        application_id="meal_planning_nutrition",
        application_context="meal_planning",
        max_turns=7,
        sut_description="A meal-planning chatbot exposed through a chat API.",
    )

    assert prompt.startswith("You are a user of a meal planning nutrition assistant")
    assert "meal_planning_nutrition" not in prompt
    assert "Do not reveal everything at once" in prompt
    assert "Keep messages short and conversational (1-3 sentences)" in prompt


def test_build_chatbot_simulation_prompt_omits_turn_limit_when_unset():
    prompt = build_chatbot_simulation_prompt(
        application_id="meal_planning_nutrition",
        application_context="meal_planning",
        max_turns=None,
        sut_description="A movie recommender exposed through a chat API.",
    )

    assert "There is no fixed turn cap unless the controller applies one." not in prompt
    assert "Finish within" not in prompt


def test_harbor_failure_summary_reports_controller_tool_errors(tmp_path):
    job_dir = tmp_path / "runs" / "playground-tool-error"
    agent_dir = job_dir / "chatbot_chat_api__fake" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "claude-code.txt").write_text(
        json.dumps(
            {
                "type": "user",
                "tool_use_result": (
                    "Error: Exit code 1\n"
                    "ERROR: HTTP 503 from http://chatbot-api:8000/ready"
                ),
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "is_error": True,
                            "content": (
                                "Exit code 1\n"
                                "ERROR: HTTP 503 from http://chatbot-api:8000/ready"
                            ),
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    assert "HTTP 503" in _harbor_failure_summary(job_dir)


def test_resolve_repo_root_handles_local_and_container_layouts():
    assert resolve_repo_root(
        Path(
            "/workspace/packages/playground/src/playground/harbor/playground.py"
        )
    ) == Path("/workspace")
    assert resolve_repo_root(
        Path("/app/packages/playground/src/playground/harbor/playground.py")
    ) == Path("/app")


def test_harbor_runner_writes_run_inputs_invokes_harbor_and_maps_artifacts(
    tmp_path, monkeypatch
):
    calls = []
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env.local").write_text(
        "OPENAI_API_KEY=sk-test-openai\nANTHROPIC_API_KEY=sk-test-anthropic\n",
        encoding="utf-8",
    )

    def fake_command(command, *, cwd, env):
        calls.append((command, cwd, env))
        config_path = command[command.index("-c") + 1]
        config = yaml.safe_load(open(config_path, encoding="utf-8"))
        assert config["agents"][0]["name"] == "persona-claude-code"
        assert config["agents"][0]["model_name"] == "anthropic/claude-haiku-4-5"
        assert config["environment"]["force_build"] is False
        assert config["environment"]["delete"] is False
        assert config["agents"][0]["kwargs"]["persona_path"].endswith("persona.yaml")
        assert config["agents"][0]["kwargs"]["persona_language"] == "zh-Hant"
        assert (
            config["agents"][0]["kwargs"]["persona_language_source"]
            == "follow_ui"
        )
        assert config["tasks"][0]["path"].endswith(
            "application/tasks/chat_meal-planning-nutrition"
        )
        prompt_path = config["extra_instruction_paths"][0]
        assert prompt_path.endswith("task_prompt.md")
        assert (
            "You are a user of a meal planning nutrition assistant"
            in open(prompt_path, encoding="utf-8").read()
        )
        assert env["INTERECAGENT_ENGINE"] == "gpt-4o"
        assert env["MATRIX_CHATBOT_APPLICATION_ID"] == "meal_planning_nutrition"
        assert env["MATRIX_CHATBOT_APPLICATION_CONTEXT"] == "meal_planning"
        assert env["MATRIX_CHATBOT_TASK_PATH"] == "application/tasks/chat_meal-planning-nutrition"
        assert "COMPOSE_PROFILES" not in env
        assert env["OPENAI_API_KEY"] == "sk-test-openai"
        assert env["ANTHROPIC_API_KEY"] == "sk-test-anthropic"
        mounts = config["environment"]["mounts"]
        assert {
            "type": "bind",
            "source": str(
                tmp_path
                / "packages"
                / "playground"
                / "src"
                / "playground"
            ),
            "target": "/app/playground",
            "read_only": True,
        } in mounts
        assert {
            "type": "bind",
            "source": prompt_path,
            "target": "/app/input/task_prompt.md",
            "read_only": True,
        } in mounts
        agent_env = {
            command[index + 1].split("=", 1)[0]: command[index + 1].split("=", 1)[1]
            for index, value in enumerate(command)
            if value == "--agent-env"
        }
        verifier_env = {
            command[index + 1].split("=", 1)[0]: command[index + 1].split("=", 1)[1]
            for index, value in enumerate(command)
            if value == "--verifier-env"
        }
        assert agent_env["MATRIX_CHATBOT_APPLICATION_ID"] == "meal_planning_nutrition"
        assert agent_env["MATRIX_CHATBOT_APPLICATION_CONTEXT"] == "meal_planning"
        assert agent_env["MATRIX_CHATBOT_TASK_PATH"] == "application/tasks/chat_meal-planning-nutrition"
        assert agent_env["MATRIX_CHATBOT_MAX_TURNS"] == "5"
        assert agent_env["MATRIX_CHATBOT_MIN_TURNS"] == "3"
        assert agent_env["MATRIX_CHATBOT_TASK_PROMPT_PATH"] == "/app/input/task_prompt.md"
        assert agent_env["MATRIX_CHATBOT_PERSONA_MODEL"] == "anthropic/claude-haiku-4-5"
        assert agent_env["MATRIX_PERSONA_LANGUAGE"] == "zh-Hant"
        assert agent_env["MATRIX_PERSONA_LANGUAGE_SOURCE"] == "follow_ui"
        assert verifier_env["MATRIX_PERSONA_LANGUAGE"] == "zh-Hant"
        assert verifier_env["MATRIX_PERSONA_LANGUAGE_SOURCE"] == "follow_ui"
        scorer_config = json.loads(verifier_env["MATRIX_SCORER_CONFIG_JSON"])
        assert scorer_config["effectiveLanguage"] == "zh-Hant"
        assert scorer_config["languageSource"] == "follow_ui"

        output_dir = (
            tmp_path
            / "runs"
            / config["job_name"]
            / "chat_meal_planning__fake"
            / "artifacts"
            / "app"
            / "output"
        )
        output_dir.mkdir(parents=True)
        (output_dir / "transcript.json").write_text(
            json.dumps(
                {
                    "sessionId": "ses_123",
                    "domain": "movie",
                    "messages": [
                        {"role": "user", "content": "I want a movie."},
                        {"role": "assistant", "content": "Try Movie A."},
                    ],
                    "turns": [
                        {
                            "turnId": "0",
                            "userMessage": "I want a movie.",
                            "assistantMessage": "Try Movie A.",
                            "structuredExposure": [{"key": "recommendedItems", "label": "Recommended items", "format": "item_list", "value": [{"itemId": "42", "title": "Movie A"}]}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "application_result.json").write_text(
            json.dumps(
                {
                    "sessionId": "ses_123",
                    "domain": "movie",
                    "recommendedItems": [{"itemId": "42", "title": "Movie A"}],
                    "turnsToResult": 1,
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "user_feedback.json").write_text(
            json.dumps(
                {
                    "needConstraintSatisfaction": "yes",
                    "personalPreferenceSatisfaction": "yes",
                    "overallExperienceRating": 9,
                    "reason": "Good fit.",
                    "askedUsefulClarificationQuestions": False,
                }
            ),
            encoding="utf-8",
        )
        return 0

    class Session:
        turns = []

    runner = HarborPlaygroundRunner(
        repo_root=tmp_path,
        runs_root=tmp_path / "runs",
        command_runner=fake_command,
        harbor_command=("uv", "run", "--frozen", "harbor", "run"),
        chat_task_path="application/tasks/chat_meal-planning-nutrition",
    )
    session = Session()
    events = []

    result = runner(
        session,
        Persona(id="p1", name="Persona One", context="A careful viewer."),
        "Movie recommender.",
        PlaygroundConfig(
            domain="meal_planning",
            application_id="meal_planning_nutrition",
            application_context="meal_planning",
            engine="gpt-4o",
            max_turns=5,
            persona_language="zh-Hant",
            persona_language_source="follow_ui",
        ),
        object(),
        created_at="2026-06-23T00:00:00Z",
        on_event=events.append,
    )

    assert calls
    assert "--agent-env" in calls[0][0]
    assert "--verifier-env" in calls[0][0]
    assert "--env-file" in calls[0][0]
    assert session.turns[0]["structuredExposure"][0]["value"][0]["itemId"] == "42"
    payload = result.to_dict()
    assert payload["questionnaire"]["overallRating"] == 9
    assert payload["prompts"]["harborPrompt"].startswith("A careful viewer.")
    assert "Effective persona language: Traditional Chinese (zh-Hant)." in payload[
        "prompts"
    ]["harborPrompt"]
    assert (
        "You are a user of a meal planning nutrition assistant"
        in payload["prompts"]["taskPrompt"]
    )
    assert "Runtime persona language contract" not in payload["prompts"]["taskPrompt"]
    assert {"type": "phase", "phase": "harbor_starting"} in events
    assert any(
        event.get("type") == "prompts"
        and event["prompts"]["harborPrompt"].startswith("A careful viewer.")
        and "Effective persona language: Traditional Chinese (zh-Hant)."
        in event["prompts"]["harborPrompt"]
        and "You are a user of a meal planning nutrition assistant"
        in event["prompts"]["taskPrompt"]
        for event in events
    )
    assert {"type": "phase", "phase": "harbor_collecting_artifacts"} in events


def test_harbor_runner_uses_finance_compose_profile(tmp_path):
    calls = []

    def fake_command(command, *, cwd, env):
        calls.append((command, cwd, env))
        config = yaml.safe_load(
            open(command[command.index("-c") + 1], encoding="utf-8")
        )
        output_dir = (
            tmp_path
            / "runs"
            / config["job_name"]
            / "chatbot_chat_api__fake"
            / "artifacts"
            / "app"
            / "output"
        )
        output_dir.mkdir(parents=True)
        (output_dir / "transcript.json").write_text(
            json.dumps(
                {
                    "sessionId": "fin_ses_1",
                    "applicationId": "finance_openbb",
                    "applicationContext": "financial_research",
                    "domain": "financial_research",
                    "messages": [
                        {"role": "user", "content": "Compare fintech securities."},
                        {"role": "assistant", "content": "I used OpenBB data."},
                    ],
                    "turns": [
                        {
                            "turnId": "fin_turn_1",
                            "userMessage": "Compare fintech securities.",
                            "assistantMessage": "I used OpenBB data.",
                            "structuredExposure": [
                                {
                                    "key": "recommendedItems",
                                    "label": "Recommended items",
                                    "format": "item_list",
                                    "value": [
                                {
                                    "itemId": "finance:openbb:equity_screener:0",
                                    "title": "OpenBB equity_screener",
                                }
                                    ]
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "application_result.json").write_text(
            json.dumps(
                {
                    "sessionId": "fin_ses_1",
                    "applicationId": "finance_openbb",
                    "applicationContext": "financial_research",
                    "recommendedItems": [
                        {
                            "itemId": "finance:openbb:equity_screener:0",
                            "title": "OpenBB equity_screener",
                        }
                    ],
                    "turnsToResult": 1,
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "user_feedback.json").write_text(
            json.dumps(
                {
                    "overallExperienceRating": 8,
                    "reason": "Useful finance result.",
                    "needConstraintSatisfaction": "partially",
                    "personalPreferenceSatisfaction": 4,
                    "askedUsefulClarificationQuestions": True,
                }
            ),
            encoding="utf-8",
        )
        return 0

    class Session:
        turns = []

    runner = HarborPlaygroundRunner(
        repo_root=tmp_path,
        runs_root=tmp_path / "runs",
        command_runner=fake_command,
        harbor_command=("uv", "run", "--frozen", "harbor", "run"),
        chat_task_path="application/tasks/chat_openbb-corporate-action-honesty",
    )
    result = runner(
        Session(),
        Persona(id="p1", name="Persona One", context="A careful analyst."),
        "Finance chatbot.",
        PlaygroundConfig(
            application_id="finance_openbb",
            application_context="financial_research",
            engine="gpt-4o-mini",
            max_turns=3,
        ),
        object(),
        created_at="2026-06-23T00:00:00Z",
    )

    env = calls[0][2]
    assert env["COMPOSE_PROFILES"] == "finance"
    assert env["MATRIX_CHATBOT_APPLICATION_ID"] == "finance_openbb"
    assert env["MATRIX_CHATBOT_APPLICATION_CONTEXT"] == "financial_research"
    assert env["MATRIX_CHATBOT_TASK_PATH"] == "application/tasks/chat_openbb-corporate-action-honesty"
    assert env["FINANCE_AGENT_MODEL"] == "gpt-4o-mini"
    assert result.to_dict()["metricScores"]["numTurns"] == 1


def test_harbor_runner_uses_support_api_without_compose_profile(tmp_path):
    calls = []

    def fake_command(command, *, cwd, env):
        calls.append((command, cwd, env))
        config = yaml.safe_load(
            open(command[command.index("-c") + 1], encoding="utf-8")
        )
        prompt_path = config["extra_instruction_paths"][0]
        assert "You are a user of a customer support system" in open(
            prompt_path,
            encoding="utf-8",
        ).read()
        output_dir = (
            tmp_path
            / "runs"
            / config["job_name"]
            / "chatbot_chat_api__fake"
            / "artifacts"
            / "app"
            / "output"
        )
        output_dir.mkdir(parents=True)
        (output_dir / "transcript.json").write_text(
            json.dumps(
                {
                    "sessionId": "support_ses_1",
                    "applicationId": "acme_support_api",
                    "applicationContext": "customer_support",
                    "domain": "customer_support",
                    "messages": [
                        {"role": "user", "content": "Where is my order?"},
                        {
                            "role": "assistant",
                            "content": "I can help check the order status.",
                        },
                    ],
                    "turns": [
                        {
                            "turnId": "support_turn_1",
                            "userMessage": "Where is my order?",
                            "assistantMessage": (
                                "I can help check the order status."
                            ),
                            "structuredExposure": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "application_result.json").write_text(
            json.dumps(
                {
                    "sessionId": "support_ses_1",
                    "applicationId": "acme_support_api",
                    "applicationContext": "customer_support",
                    "recommendedItems": [],
                    "turnsToResult": 1,
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "user_feedback.json").write_text(
            json.dumps(
                {
                    "overallExperienceRating": 8,
                    "reason": "Clear support guidance.",
                    "needConstraintSatisfaction": "partially",
                    "personalPreferenceSatisfaction": 4,
                    "askedUsefulClarificationQuestions": True,
                }
            ),
            encoding="utf-8",
        )
        return 0

    class Session:
        turns = []

    runner = HarborPlaygroundRunner(
        repo_root=tmp_path,
        runs_root=tmp_path / "runs",
        command_runner=fake_command,
        harbor_command=("uv", "run", "--frozen", "harbor", "run"),
        chat_task_path="application/tasks/example-chat-api_support_chatbot",
    )
    result = runner(
        Session(),
        Persona(id="p1", name="Persona One", context="A careful shopper."),
        "Support chatbot.",
        PlaygroundConfig(
            application_id="acme_support_api",
            application_context="customer_support",
            engine="gpt-4o-mini",
            max_turns=3,
        ),
        object(),
        created_at="2026-06-23T00:00:00Z",
    )

    command, _cwd, env = calls[0]
    agent_env = {
        command[index + 1].split("=", 1)[0]: command[index + 1].split("=", 1)[1]
        for index, value in enumerate(command)
        if value == "--agent-env"
    }
    assert "COMPOSE_PROFILES" not in env
    assert env["MATRIX_CHATBOT_APPLICATION_ID"] == "acme_support_api"
    assert env["MATRIX_CHATBOT_APPLICATION_CONTEXT"] == "customer_support"
    assert "FINANCE_AGENT_MODEL" not in env
    assert agent_env["MATRIX_CHATBOT_APPLICATION_ID"] == "acme_support_api"
    assert agent_env["MATRIX_CHATBOT_APPLICATION_CONTEXT"] == "customer_support"
    assert agent_env["MATRIX_CHATBOT_TASK_PATH"] == "application/tasks/example-chat-api_support_chatbot"
    assert result.to_dict()["metricScores"]["numTurns"] == 1


def test_harbor_runner_reads_feedback_written_by_application_scorer_artifact(tmp_path):
    def fake_command(command, *, cwd, env):
        config = yaml.safe_load(
            open(command[command.index("-c") + 1], encoding="utf-8")
        )
        output_dir = (
            tmp_path
            / "runs"
            / config["job_name"]
            / "chat_meal_planning__fake"
            / "artifacts"
            / "app"
            / "output"
        )
        output_dir.mkdir(parents=True)
        (output_dir / "transcript.json").write_text(
            json.dumps(
                {
                    "sessionId": "ses_123",
                    "domain": "movie",
                    "messages": [
                        {"role": "user", "content": "I want a movie."},
                        {"role": "assistant", "content": "Try Movie A."},
                    ],
                    "turns": [
                        {
                            "turnId": "0",
                            "userMessage": "I want a movie.",
                            "assistantMessage": "Try Movie A.",
                            "structuredExposure": [{"key": "recommendedItems", "label": "Recommended items", "format": "item_list", "value": [{"itemId": "42", "title": "Movie A"}]}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "application_result.json").write_text(
            json.dumps(
                {
                    "sessionId": "ses_123",
                    "domain": "movie",
                    "recommendedItems": [{"itemId": "42", "title": "Movie A"}],
                    "turnsToResult": 1,
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "user_feedback.json").write_text(
            json.dumps(
                {
                    "needConstraintSatisfaction": "partially",
                    "personalPreferenceSatisfaction": 4,
                    "overallExperienceRating": 8,
                    "reason": "Original scoring prompt output.",
                    "askedUsefulClarificationQuestions": True,
                    "clarifyingNotes": "The recommender adapted after feedback.",
                }
            ),
            encoding="utf-8",
        )
        return 0

    class Session:
        turns = []

    runner = HarborPlaygroundRunner(
        repo_root=tmp_path,
        runs_root=tmp_path / "runs",
        command_runner=fake_command,
        chat_task_path="application/tasks/chat_meal-planning-nutrition",
    )
    result = runner(
        Session(),
        Persona(id="p1", name="Persona One", context="A careful viewer."),
        "Movie recommender.",
        PlaygroundConfig(domain="movie", persona_model="anthropic/claude-sonnet-4-6"),
        object(),
        created_at="2026-06-23T00:00:00Z",
    )

    assert result.to_dict()["questionnaire"]["overallRating"] == 8


def test_harbor_runner_persona_model_can_be_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv("MATRIX_HARBOR_PERSONA_MODEL", "anthropic/claude-haiku-4-5")
    calls = []

    def fake_command(command, *, cwd, env):
        calls.append(command)
        config = yaml.safe_load(
            open(command[command.index("-c") + 1], encoding="utf-8")
        )
        output_dir = (
            tmp_path
            / "runs"
            / config["job_name"]
            / "chat_meal_planning__fake"
            / "artifacts"
            / "app"
            / "output"
        )
        output_dir.mkdir(parents=True)
        (output_dir / "transcript.json").write_text(
            json.dumps(
                {
                    "sessionId": "ses_123",
                    "domain": "movie",
                    "messages": [
                        {"role": "user", "content": "I want a movie."},
                        {"role": "assistant", "content": "Try Movie A."},
                    ],
                    "turns": [
                        {
                            "turnId": "0",
                            "userMessage": "I want a movie.",
                            "assistantMessage": "Try Movie A.",
                            "structuredExposure": [{"key": "recommendedItems", "label": "Recommended items", "format": "item_list", "value": [{"itemId": "42", "title": "Movie A"}]}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "application_result.json").write_text(
            json.dumps(
                {
                    "sessionId": "ses_123",
                    "domain": "movie",
                    "recommendedItems": [{"itemId": "42", "title": "Movie A"}],
                    "turnsToResult": 1,
                }
            ),
            encoding="utf-8",
        )
        return 0

    class Session:
        turns = []

    runner = HarborPlaygroundRunner(
        repo_root=tmp_path,
        runs_root=tmp_path / "runs",
        command_runner=fake_command,
        chat_task_path="application/tasks/chat_meal-planning-nutrition",
    )
    runner(
        Session(),
        Persona(id="p1", name="Persona One", context="A careful viewer."),
        "Movie recommender.",
        PlaygroundConfig(domain="movie", persona_model="anthropic/claude-sonnet-4-6"),
        object(),
        created_at="2026-06-23T00:00:00Z",
    )

    config = yaml.safe_load(open(calls[0][calls[0].index("-c") + 1], encoding="utf-8"))
    assert config["agents"][0]["model_name"] == "anthropic/claude-sonnet-4-6"


def test_harbor_runner_cache_flags_can_be_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv("MATRIX_HARBOR_FORCE_BUILD", "0")
    monkeypatch.setenv("MATRIX_HARBOR_DELETE", "1")

    def fake_command(command, *, cwd, env):
        config = yaml.safe_load(
            open(command[command.index("-c") + 1], encoding="utf-8")
        )
        assert config["environment"]["type"] == "docker"
        assert config["environment"]["delete"] is True
        assert config["environment"]["force_build"] is False
        output_dir = (
            tmp_path
            / "runs"
            / config["job_name"]
            / "chat_meal_planning__fake"
            / "artifacts"
            / "app"
            / "output"
        )
        output_dir.mkdir(parents=True)
        (output_dir / "transcript.json").write_text(
            json.dumps(
                {
                    "sessionId": "ses_123",
                    "domain": "movie",
                    "messages": [
                        {"role": "user", "content": "I want a movie."},
                        {"role": "assistant", "content": "Try Movie A."},
                    ],
                    "turns": [
                        {
                            "turnId": "0",
                            "userMessage": "I want a movie.",
                            "assistantMessage": "Try Movie A.",
                            "structuredExposure": [{"key": "recommendedItems", "label": "Recommended items", "format": "item_list", "value": [{"itemId": "42", "title": "Movie A"}]}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "application_result.json").write_text(
            json.dumps(
                {
                    "sessionId": "ses_123",
                    "domain": "movie",
                    "recommendedItems": [{"itemId": "42", "title": "Movie A"}],
                    "turnsToResult": 1,
                }
            ),
            encoding="utf-8",
        )
        return 0

    class Session:
        turns = []

    runner = HarborPlaygroundRunner(
        repo_root=tmp_path,
        runs_root=tmp_path / "runs",
        command_runner=fake_command,
        chat_task_path="application/tasks/chat_meal-planning-nutrition",
    )
    runner(
        Session(),
        Persona(id="p1", name="Persona One", context="A careful viewer."),
        "Movie recommender.",
        PlaygroundConfig(domain="movie"),
        object(),
        created_at="2026-06-23T00:00:00Z",
    )


def test_harbor_runner_default_command_uses_configured_harbor_command(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "MATRIX_HARBOR_COMMAND",
        "uv --directory /opt/harbor run --frozen harbor run",
    )
    calls = []

    def fake_command(command, *, cwd, env):
        calls.append(command)
        config = yaml.safe_load(
            open(command[command.index("-c") + 1], encoding="utf-8")
        )
        output_dir = (
            tmp_path
            / "runs"
            / config["job_name"]
            / "chat_meal_planning__fake"
            / "artifacts"
            / "app"
            / "output"
        )
        output_dir.mkdir(parents=True)
        (output_dir / "transcript.json").write_text(
            json.dumps(
                {
                    "sessionId": "ses_123",
                    "domain": "movie",
                    "messages": [
                        {"role": "user", "content": "I want a movie."},
                        {"role": "assistant", "content": "Try Movie A."},
                    ],
                    "turns": [
                        {
                            "turnId": "0",
                            "userMessage": "I want a movie.",
                            "assistantMessage": "Try Movie A.",
                            "structuredExposure": [{"key": "recommendedItems", "label": "Recommended items", "format": "item_list", "value": [{"itemId": "42", "title": "Movie A"}]}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "application_result.json").write_text(
            json.dumps(
                {
                    "sessionId": "ses_123",
                    "domain": "movie",
                    "recommendedItems": [{"itemId": "42", "title": "Movie A"}],
                    "turnsToResult": 1,
                }
            ),
            encoding="utf-8",
        )
        return 0

    class Session:
        turns = []

    runner = HarborPlaygroundRunner(
        repo_root=tmp_path,
        runs_root=tmp_path / "runs",
        command_runner=fake_command,
        chat_task_path="application/tasks/chat_meal-planning-nutrition",
    )
    runner(
        Session(),
        Persona(id="p1", name="Persona One", context="A careful viewer."),
        "Movie recommender.",
        PlaygroundConfig(domain="movie"),
        object(),
        created_at="2026-06-23T00:00:00Z",
    )

    assert calls[0][:6] == [
        "uv",
        "--directory",
        "/opt/harbor",
        "run",
        "--frozen",
        "harbor",
    ]


def test_default_harbor_command_prefers_project_uv_run_without_venv_script(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("MATRIX_HARBOR_COMMAND", raising=False)
    monkeypatch.delenv("HARBOR_COMMAND", raising=False)
    monkeypatch.delenv("MATRIX_HARBOR_BIN", raising=False)
    monkeypatch.delenv("HARBOR_BIN", raising=False)
    monkeypatch.setattr(harbor_playground_module, "_repo_root", lambda: tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")

    assert _default_harbor_command() == (
        "uv",
        "run",
        "python",
        "-m",
        "harbor.cli.main",
        "run",
    )


def test_harbor_runner_surfaces_trial_errors_when_artifacts_are_missing(tmp_path):
    def fake_command(command, *, cwd, env):
        config = yaml.safe_load(
            open(command[command.index("-c") + 1], encoding="utf-8")
        )
        job_dir = tmp_path / "runs" / config["job_name"]
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "result.json").write_text(
            json.dumps(
                {
                    "stats": {
                        "n_errored_trials": 1,
                        "evals": {
                            "persona-claude-code__claude-sonnet-4-6__adhoc": {
                                "exception_stats": {
                                    "RuntimeError": ["chat_meal_planning__fake"]
                                }
                            }
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        trial_dir = job_dir / "chat_meal_planning__fake"
        trial_dir.mkdir()
        (trial_dir / "exception.txt").write_text(
            "Docker build failed: No space left on device",
            encoding="utf-8",
        )
        return 0

    class Session:
        turns = []

    runner = HarborPlaygroundRunner(
        repo_root=tmp_path,
        runs_root=tmp_path / "runs",
        command_runner=fake_command,
        chat_task_path="application/tasks/chat_meal-planning-nutrition",
    )

    with pytest.raises(RuntimeError, match="No space left on device"):
        runner(
            Session(),
            Persona(id="p1", name="Persona One", context="A careful viewer."),
            "Movie recommender.",
            PlaygroundConfig(domain="movie"),
            object(),
            created_at="2026-06-23T00:00:00Z",
        )


def test_harbor_runner_surfaces_agent_error_when_output_dir_is_empty(tmp_path):
    def fake_command(command, *, cwd, env):
        config = yaml.safe_load(
            open(command[command.index("-c") + 1], encoding="utf-8")
        )
        job_dir = tmp_path / "runs" / config["job_name"]
        trial_dir = job_dir / "chat_meal_planning__fake"
        output_dir = trial_dir / "artifacts" / "app" / "output"
        output_dir.mkdir(parents=True)
        (job_dir / "result.json").write_text(
            json.dumps(
                {
                    "stats": {
                        "n_errored_trials": 1,
                        "evals": {
                            "persona-claude-code__claude-sonnet-4-6__adhoc": {
                                "exception_stats": {
                                    "NonZeroAgentExitCodeError": [
                                        "chat_meal_planning__fake"
                                    ]
                                }
                            }
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        (trial_dir / "agent").mkdir()
        (trial_dir / "agent" / "claude-code.txt").write_text(
            "\n".join(
                [
                    json.dumps({"type": "system", "subtype": "init"}),
                    json.dumps(
                        {
                            "type": "assistant",
                            "error": "billing_error",
                            "api_error_status": 400,
                            "message": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Credit balance is too low",
                                    }
                                ]
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "result",
                            "is_error": True,
                            "api_error_status": 400,
                            "result": "Credit balance is too low",
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )
        return 0

    class Session:
        turns = []

    runner = HarborPlaygroundRunner(
        repo_root=tmp_path,
        runs_root=tmp_path / "runs",
        command_runner=fake_command,
        chat_task_path="application/tasks/chat_meal-planning-nutrition",
    )

    with pytest.raises(RuntimeError, match="Credit balance is too low"):
        runner(
            Session(),
            Persona(id="p1", name="Persona One", context="A careful viewer."),
            "Movie recommender.",
            PlaygroundConfig(domain="movie"),
            object(),
            created_at="2026-06-23T00:00:00Z",
        )
