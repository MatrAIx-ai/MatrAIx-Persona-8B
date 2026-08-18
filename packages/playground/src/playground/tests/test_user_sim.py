"""Tests for the tool-driven user simulator and runner integration."""

from __future__ import annotations

import asyncio
from pathlib import Path


from playground.task_content_bundle import TaskContentBundle
from playground.types import Persona, PlaygroundConfig, Questionnaire
from playground.user_sim.runner import run_playground, run_playground_async
from playground.user_sim.session import UserSimSession
from playground.user_sim.tool_client import FakeToolStepClient
from playground.user_sim.tools import ToolCall, normalize_sim_message, parse_tool_calls


class FakeSession:
    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = []
        self._session_id = "sess-user-sim"

    @property
    def session_id(self) -> str:
        return self._session_id

    def run_turn_sync(self, message):
        self.calls.append(message)
        return self._turns.pop(0)


class AsyncFakeSession(FakeSession):
    async def run_turn_sync(self, message):
        self.calls.append(message)
        return self._turns.pop(0)


class FakeSelfReportClient:
    def __init__(self):
        self.calls = []

    def complete_json(self, system, user):
        self.calls.append({"system": system, "user": user})
        return {
            "needConstraintSatisfaction": "yes",
            "personalPreferenceSatisfaction": "yes",
            "overallExperienceRating": 8,
            "reason": "Solid chat",
            "askedUsefulClarificationQuestions": True,
            "clarifyingNotes": "Asked about genre",
        }


def _persona():
    return Persona(
        id="p1",
        name="Alex",
        summary="Movie fan",
        context="Name: Alex\nLikes thoughtful dramas.",
    )


def test_normalize_sim_message_strips_tool_syntax_leaks():
    leaked = (
        "Tool send_message: Tool send_message: I'd rather avoid intense violence."
    )
    assert normalize_sim_message(leaked) == "I'd rather avoid intense violence."
    end_leak = (
        'Tool end_conversation: The app is stuck.'
        '<parameter name="reason">give_up</parameter>'
        '<parameter name="note">No progress</parameter>'
    )
    assert normalize_sim_message(end_leak) == "The app is stuck."


def test_parse_tool_calls_strips_leaked_prefix():
    action = parse_tool_calls(
        [ToolCall("send_message", {"message": "Tool send_message: Something warm"})]
    )
    assert action.message == "Something warm"


def test_user_sim_session_stores_natural_assistant_memory():
    client = FakeToolStepClient(
        [[ToolCall("send_message", {"message": "Hi, need a movie recommendation"})]]
    )
    session = UserSimSession(
        client,
        _persona(),
        persona_language="zh-Hans",
        persona_language_source="follow_ui",
    )
    session.opening_action()
    assistant_turn = session.messages[-1]
    assert assistant_turn["role"] == "assistant"
    assert assistant_turn["content"] == "Hi, need a movie recommendation"
    assert "Tool send_message" not in assistant_turn["content"]
    assert session.effective_persona_language == "zh-Hans"
    assert session.persona_language_source == "follow_ui"
    assert "Simplified Chinese (zh-Hans)" in session.system_prompt


def test_parse_tool_calls_send_and_end():
    action = parse_tool_calls(
        [
            ToolCall("send_message", {"message": "Looking for something warm"}),
            ToolCall("end_conversation", {"reason": "satisfied", "note": "found it"}),
        ]
    )
    assert action.message == "Looking for something warm"
    assert action.end_reason == "satisfied"
    assert action.decision == "satisfied"


def test_user_sim_session_opening_action():
    client = FakeToolStepClient(
        [[ToolCall("send_message", {"message": "Hi, need a movie recommendation"})]]
    )
    session = UserSimSession(client, _persona())
    action = session.opening_action()
    assert action.message == "Hi, need a movie recommendation"
    assert len(client.calls) == 1
    assert client.calls[0][0]["role"] == "system"


def test_run_playground_tool_loop(monkeypatch):
    monkeypatch.delenv("MATRIX_PERSONA_LANGUAGE", raising=False)
    report_client = FakeSelfReportClient()
    monkeypatch.setattr(
        "playground.user_sim.runner.build_json_client",
        lambda *_args, **_kwargs: report_client,
    )
    session = FakeSession(
        [
            {"assistantMessage": "What genre?", "recommendedItems": []},
            {
                "assistantMessage": "Try Past Lives",
                "recommendedItems": [{"itemId": "movie-1", "title": "Past Lives"}],
            },
        ]
    )
    client = FakeToolStepClient(
        [
            [ToolCall("send_message", {"message": "Hi, looking for a warm drama"})],
            [ToolCall("send_message", {"message": "Something character-driven"})],
            [ToolCall("end_conversation", {"reason": "satisfied"})],
        ]
    )
    monkeypatch.setattr(
        "playground.user_sim.runner.build_tool_step_client",
        lambda *_args, **_kwargs: client,
    )
    repo = Path(__file__).resolve().parents[5]
    result = run_playground(
        session,
        _persona(),
        "Meal planning assistant",
        PlaygroundConfig(domain="meal_planning", max_turns=5),
        created_at="2026-06-30T00:00:00Z",
        task_path="application/tasks/chat_meal-planning-nutrition",
        repo_root=repo,
    )
    assert len(result.transcript) == 2
    assert result.transcript[0].user_message == "Hi, looking for a warm drama"
    assert result.transcript[-1].decision == "satisfied"
    assert result.metric_scores.num_turns == 2
    assert result.transcript[-1].structured_exposure[0]["value"] == [
        {"itemId": "movie-1", "title": "Past Lives"}
    ]
    assert isinstance(result.questionnaire, Questionnaire)
    assert result.prompts["taskPrompt"]
    assert len(client.calls) >= 3
    assert "Effective persona language: English (en)." in client.calls[0][0]["content"]
    assert "Effective persona language: English (en)." in report_client.calls[0]["system"]
    second_step = client.calls[1]
    assert second_step[-1]["role"] == "user"
    assert 'Meal Planning Nutrition Answer:\n"""What genre?"""' in second_step[-1]["content"]
    third_step = client.calls[2]
    assert "Visible structured details" in third_step[-1]["content"]
    assert "Meal plans or suggestions: Past Lives (movie-1)" in third_step[-1]["content"]


def test_prompt_bundle_separates_persona_and_task():
    from playground.user_sim.prompt import (
        assemble_report_system_prompt,
        prompt_bundle,
    )

    persona = Persona(id="p1", name="Test", source="", context="Bio line")
    task_bundle = TaskContentBundle(
        instruction_markdown="Judge the chatbot honestly.",
        context_markdown="The chatbot helps a user discover products.",
        output_schema_markdown="Write transcript.json and user_feedback.json.",
    )
    bundle = prompt_bundle(
        persona,
        task_bundle=task_bundle,
        task_prompt="Kickoff instruction.",
        persona_language="zh-Hans",
    )
    report_prompt = assemble_report_system_prompt(
        persona,
        task_bundle=task_bundle,
        persona_language="zh-Hans",
    )
    assert "Progressive disclosure" not in bundle["personaPrompt"]
    assert "Bio line" in bundle["personaPrompt"]
    assert "## Persona" not in bundle["personaPrompt"]
    assert "Simulated person" not in bundle["personaPrompt"]
    assert "## Task instruction" not in bundle["personaPrompt"]
    assert "## Task instruction" in bundle["taskPrompt"]
    assert "## Task context" in bundle["taskPrompt"]
    assert "Kickoff instruction." in bundle["taskPrompt"]
    assert "Progressive disclosure" in bundle["harborPrompt"]
    assert "Today is " in bundle["harborPrompt"]
    assert "Today is " in report_prompt
    assert bundle["harborPrompt"].index("Bio line") < bundle["harborPrompt"].index(
        "Progressive disclosure"
    )
    assert "Keep messages short and natural (usually 1-3 sentences)." in bundle["harborPrompt"]
    assert "Simplified Chinese (zh-Hans)" in bundle["personaPrompt"]
    assert "Simplified Chinese (zh-Hans)" in report_prompt
    assert "Judge the chatbot honestly." in bundle["taskPrompt"]
    assert "do not translate" not in bundle["taskPrompt"]
    assert "Prefer plainspoken end-user language" in bundle["harborPrompt"]
    assert "simulating" not in bundle["harborPrompt"].lower()
    assert "assigned persona" not in bundle["harborPrompt"].lower()

    english_bundle = prompt_bundle(
        persona,
        task_bundle=task_bundle,
        task_prompt="Kickoff instruction.",
        persona_language="en",
    )
    assert bundle["taskPrompt"] == english_bundle["taskPrompt"]
    assert "stay in character" not in bundle["harborPrompt"].lower()
    assert "## Task instruction" in bundle["harborPrompt"]
    assert "## Task context" in bundle["harborPrompt"]
    assert "## Task instruction" in report_prompt
    assert "## Task context" in report_prompt
    assert "## Output schema" not in report_prompt


def test_runner_uses_one_effective_language_for_persona_and_self_report(monkeypatch):
    report_client = FakeSelfReportClient()
    monkeypatch.setattr(
        "playground.user_sim.runner.build_json_client",
        lambda *_args, **_kwargs: report_client,
    )
    tool_client = FakeToolStepClient(
        [
            [ToolCall("send_message", {"message": "ZH-HANS USER MESSAGE"})],
            [ToolCall("end_conversation", {"reason": "satisfied"})],
        ]
    )
    monkeypatch.setattr(
        "playground.user_sim.runner.build_tool_step_client",
        lambda *_args, **_kwargs: tool_client,
    )

    events = []
    result = run_playground(
        FakeSession([{"assistantMessage": "ZH-HANS ASSISTANT MESSAGE", "recommendedItems": []}]),
        _persona(),
        "A test chatbot",
        PlaygroundConfig(domain="movie", max_turns=1),
        created_at="2026-06-30T00:00:00Z",
        persona_language="zh-Hans",
        persona_language_source="follow_ui",
        on_event=events.append,
    )

    assert len(tool_client.calls) == 2
    persona_prompt = tool_client.calls[0][0]["content"]
    assert len(report_client.calls) == 1
    report_prompt = report_client.calls[0]["system"]
    marker = "Effective persona language: Simplified Chinese (zh-Hans)."
    assert marker in persona_prompt
    assert marker in report_prompt
    assert "Write persona narrative, simulated user messages, and persona self-reports" in report_prompt
    assert "Keep task instructions, task context, questionnaires" in report_prompt
    assert "How well did the chatbot satisfy your core need or constraints?" in report_client.calls[0]["user"]
    assert result.config.effective_language == "zh-Hans"
    assert result.config.language_source == "follow_ui"
    prompt_event = next(event for event in events if event["type"] == "prompts")
    assert prompt_event["effectiveLanguage"] == "zh-Hans"
    assert prompt_event["languageSource"] == "follow_ui"


def test_async_runner_preserves_language_provenance_and_task_prompt(monkeypatch):
    report_client = FakeSelfReportClient()
    monkeypatch.setattr(
        "playground.user_sim.runner.build_json_client",
        lambda *_args, **_kwargs: report_client,
    )
    tool_client = FakeToolStepClient(
        [
            [ToolCall("send_message", {"message": "ZH-HANS USER MESSAGE"})],
            [ToolCall("end_conversation", {"reason": "satisfied"})],
        ]
    )
    monkeypatch.setattr(
        "playground.user_sim.runner.build_tool_step_client",
        lambda *_args, **_kwargs: tool_client,
    )
    events = []

    result = asyncio.run(
        run_playground_async(
            AsyncFakeSession(
                [{"assistantMessage": "ZH-HANS ASSISTANT MESSAGE", "recommendedItems": []}]
            ),
            _persona(),
            "A test chatbot",
            PlaygroundConfig(domain="movie", max_turns=1),
            created_at="2026-06-30T00:00:00Z",
            persona_language="zh-Hant",
            persona_language_source="explicit",
            on_event=events.append,
        )
    )

    assert result.config.effective_language == "zh-Hant"
    assert result.config.language_source == "explicit"
    assert "Traditional Chinese (zh-Hant)" in tool_client.calls[0][0]["content"]
    assert "Traditional Chinese (zh-Hant)" in report_client.calls[0]["system"]
    prompt_event = next(event for event in events if event["type"] == "prompts")
    assert prompt_event["effectiveLanguage"] == "zh-Hant"
    assert prompt_event["languageSource"] == "explicit"
    assert result.prompts["taskPrompt"]


def test_current_date_block_uses_provided_moment():
    from datetime import datetime, timezone

    from playground.user_sim.prompt import current_date_block

    block = current_date_block(
        now=datetime(2026, 7, 21, 0, 20, tzinfo=timezone.utc)
    )
    assert block == "Today is Tuesday, July 21, 2026, 00:20 UTC."


def test_public_runner_delegates_to_user_sim(monkeypatch):
    from playground.runner import run_playground

    sentinel = object()
    captured = {}

    def fake_run(session, persona, sut_description, config, *, created_at, on_event, task_path, persona_yaml_path, repo_root):
        captured["session"] = session
        captured["persona"] = persona
        captured["sut_description"] = sut_description
        captured["config"] = config
        captured["created_at"] = created_at
        captured["task_path"] = task_path
        captured["persona_yaml_path"] = persona_yaml_path
        captured["repo_root"] = repo_root
        return sentinel

    monkeypatch.setattr("playground.user_sim.runner.run_playground", fake_run)
    session = FakeSession([{"assistantMessage": "Hi", "recommendedItems": []}])
    config = PlaygroundConfig(domain="movie", max_turns=3)
    result = run_playground(
        session,
        _persona(),
        "desc",
        config,
        created_at="t",
        task_path="application/tasks/chat_meal-planning-nutrition",
        persona_yaml_path="persona.yaml",
        repo_root=Path("/tmp/demo-repo"),
    )
    assert result is sentinel
    assert captured["session"] is session
    assert captured["config"] is config
    assert captured["task_path"] == "application/tasks/chat_meal-planning-nutrition"
