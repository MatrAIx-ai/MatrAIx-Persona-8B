from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.service.survey_types import SurveyEvalConfig, SurveyInstrument, SurveyQuestion
from matraix.agents.persona.loader import load_persona
from playground.inprocess.survey_eval import InprocessSurveyEvalRunner
from playground.task_content_bundle import TaskContentBundle
from playground.types import Persona
from playground.user_sim.prompt import (
    persona_language_scope,
    prompt_bundle,
    render_persona_block,
)


ROOT = Path(__file__).resolve().parents[3]
PERSONA_PATH = ROOT / "persona/datasets/matraix-persona-dev-sample/persona_0001.yaml"


@pytest.mark.parametrize(
    ("explicit", "env", "marker"),
    [
        ("en", "zh", "You are "),
        (None, "zh", "你是 "),
        (None, None, "You are "),
    ],
)
def test_render_persona_block_resolves_explicit_env_and_default(
    monkeypatch: pytest.MonkeyPatch,
    explicit: str | None,
    env: str | None,
    marker: str,
) -> None:
    if env is None:
        monkeypatch.delenv("MATRAIX_PERSONA_LANGUAGE", raising=False)
    else:
        monkeypatch.setenv("MATRAIX_PERSONA_LANGUAGE", env)

    prompt = render_persona_block(
        Persona(id="p1", name="Test"),
        persona_yaml_path=str(PERSONA_PATH),
        persona_language=explicit,
    )

    assert marker in prompt


def test_chat_agent_scope_reaches_real_chat_persona_prompt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The agent's Harbor call renders the same YAML persona in Chinese."""
    from matraix.agents.persona.user_sim import PersonaUserSim
    from playground.harbor import chat_eval

    captured: dict[str, object] = {}

    async def fake_chat_eval(environment, harbor_persona, **kwargs):
        del environment, kwargs
        eval_persona = chat_eval._eval_persona(harbor_persona)
        prompts = prompt_bundle(
            eval_persona,
            persona_yaml_path=str(harbor_persona.persona_path),
            task_bundle=TaskContentBundle(
                instruction_markdown="Original chat task body; keep this text unchanged."
            ),
        )
        captured["prompts"] = prompts
        return object(), "session"

    monkeypatch.setattr(
        "matraix.agents.persona.user_sim.run_harbor_chat_eval_for_persona",
        fake_chat_eval,
    )

    agent = PersonaUserSim.__new__(PersonaUserSim)
    agent._persona = load_persona(str(PERSONA_PATH))
    agent._persona_language = "zh"
    agent._persona_language_source = "explicit"
    agent.model_name = "test-model"
    agent.logs_dir = tmp_path / "trial" / "agent"
    agent.logs_dir.mkdir(parents=True)

    async def fake_prepare(environment):
        del environment

    agent._prepare_persona_trial = fake_prepare

    asyncio.run(agent.run("ignored", object(), None))

    prompts = captured["prompts"]
    assert isinstance(prompts, dict)
    assert "你是 " in prompts["personaPrompt"]
    assert "Original chat task body; keep this text unchanged." in prompts["taskPrompt"]


def test_survey_runner_uses_zh_persona_prompt_and_raw_task_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    class FakeJsonClient:
        def complete_json(self, system: str, user: str) -> dict[str, object]:
            captured["system"] = system
            captured["user"] = user
            return {"answers": [{"questionId": "q1", "value": "A clear answer"}]}

    monkeypatch.setattr(
        "playground.inprocess.survey_eval.build_json_client",
        lambda _model: FakeJsonClient(),
    )
    instrument = SurveyInstrument(
        id="runtime-language-test",
        title="Runtime language test",
        questions=[
            SurveyQuestion(
                id="q1",
                prompt="Original survey task body; keep this text unchanged.",
                type="free_text",
            )
        ],
    )

    result = InprocessSurveyEvalRunner()(
        Persona(id="p1", name="Test"),
        instrument,
        config=SurveyEvalConfig(persona_model="test-model"),
        created_at="2026-08-11T00:00:00Z",
        persona_yaml_path=str(PERSONA_PATH),
        persona_language="zh",
    )

    assert "你是 " in captured["system"]
    assert "Original survey task body; keep this text unchanged." in captured["user"]
    assert result.prompts["personaPrompt"] == captured["system"]
    assert result.prompts["taskPrompt"] == captured["user"]


def test_persona_language_scope_is_request_local() -> None:
    persona = Persona(id="p1", name="Test")
    with persona_language_scope("zh"):
        prompt = prompt_bundle(
            persona,
            persona_yaml_path=str(PERSONA_PATH),
            task_bundle=TaskContentBundle(
                instruction_markdown="Do not translate this task body."
            ),
        )
    after_scope = prompt_bundle(
        persona,
        persona_yaml_path=str(PERSONA_PATH),
    )

    assert "你是 " in prompt["personaPrompt"]
    assert "You are " in after_scope["personaPrompt"]
    assert "Do not translate this task body." in prompt["taskPrompt"]
