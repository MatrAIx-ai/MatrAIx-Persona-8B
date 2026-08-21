from __future__ import annotations

import pathlib
import tomllib


ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_persona_agents_use_matraix_namespace() -> None:
    """Ensure no leftover 'personabench' references in agent files."""
    agent_files = [
        path
        for path in (ROOT / "environment/agents/matraix/agents").rglob("*")
        if path.is_file() and path.suffix in {".j2", ".py"}
    ]

    assert agent_files
    for path in agent_files:
        text = path.read_text(encoding="utf-8")
        assert "personabench" not in text.lower(), path


def test_persona_scripts_use_matraix_imports() -> None:
    """Persona tooling scripts must import matraix, not the retired personabench package."""
    roots = (
        ROOT / "persona" / "scripts",
        ROOT / "persona" / "reporting",
        ROOT / "persona" / "curation" / "scripts",
    )
    py_files = [
        path
        for root in roots
        if root.is_dir()
        for path in root.rglob("*.py")
        if path.is_file()
    ]
    assert py_files
    for path in py_files:
        text = path.read_text(encoding="utf-8")
        assert "personabench" not in text, path


def test_harbor_factory_registers_matraix_persona_agents() -> None:
    factory_source = (
        ROOT / "environment/runtime/harbor/agents/factory.py"
    ).read_text()

    expected_imports = [
        "matraix.agents.persona.claude_code:PersonaClaudeCode",
        "matraix.agents.persona.computer_1:PersonaComputer1",
        "matraix.agents.persona.openhands_sdk:PersonaOpenHandsSDK",
        "matraix.agents.installed.browser_use:BrowserUseHarborAgent",
        "matraix.agents.installed.cocoa:CocoaHarborAgent",
        "matraix.agents.persona.browser_use:PersonaBrowserUse",
        "matraix.agents.persona.cocoa:PersonaCocoa",
        "matraix.agents.persona.gemini_cli:PersonaGeminiCli",
        "matraix.agents.persona.codex:PersonaCodex",
        "matraix.agents.persona.uxagent:PersonaUXAgent",
    ]

    for import_path in expected_imports:
        assert import_path in factory_source


def test_persona_agent_templates_are_packaged() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert pyproject["tool"]["setuptools"]["package-data"]["matraix"] == [
        "agents/persona/templates/*.j2",
    ]


def test_installed_runtime_packages_do_not_import_environment_namespace() -> None:
    """Installed ``harbor.*`` / ``matraix.agents.*`` must not rely on repo-root ``environment.*`` imports."""
    roots = [
        ROOT / "environment/agents/matraix/agents",
        ROOT / "environment/runtime/harbor",
    ]
    for root in roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "environment.integrations" not in text, path
            assert "playground.local" not in text, path
            assert "from environment." not in text, path
            assert "import environment." not in text, path


def test_persona_loader_reads_sample_dataset() -> None:
    from matraix.agents.persona.loader import load_persona

    persona = load_persona(ROOT / "persona/datasets/matraix-persona-dev-sample/persona_0001.yaml")

    assert persona.schema_version == "v2"
    assert persona.persona_id == "0001"
    assert persona.dimensions["domain"] == "Skilled Trades"


def test_resolve_desktop_cua_provider_from_model_and_backend() -> None:
    from matraix.agents.persona.computer_1 import resolve_desktop_cua_provider

    assert resolve_desktop_cua_provider("openai/gpt-5.5") == "openai"
    assert resolve_desktop_cua_provider("gpt-5.4") == "openai"
    assert resolve_desktop_cua_provider("gemini/gemini-2.5-computer-use-preview") == "gemini"
    assert resolve_desktop_cua_provider("anthropic/claude-sonnet-4-6") == "anthropic"
    assert resolve_desktop_cua_provider(None) == "anthropic"
    assert resolve_desktop_cua_provider(
        "anthropic/claude-sonnet-4-6", cua_backend="openai"
    ) == "openai"
    assert resolve_desktop_cua_provider(
        "openai/gpt-5.5", cua_backend="anthropic"
    ) == "anthropic"


def test_build_cua_delegate_remaps_max_steps_to_max_turns_for_docker(monkeypatch) -> None:
    """Playground historically injects max_steps; Docker Computer1 wants max_turns."""
    from matraix.agents.persona import computer_1 as computer_1_mod

    captured: dict[str, object] = {}

    class _FakeComputer1:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "harbor.agents.computer_1.Computer1",
        _FakeComputer1,
    )

    agent = computer_1_mod._build_cua_delegate(
        "docker_computer1",
        logs_dir=pathlib.Path("/tmp/logs"),
        model_name="anthropic/claude-sonnet-4-6",
        logger=None,
        mcp_servers=None,
        skills_dir=None,
        delegate_kwargs={"max_steps": 100, "temperature": 0.2},
    )
    assert isinstance(agent, _FakeComputer1)
    assert captured["max_turns"] == 100
    assert "max_steps" not in captured
    assert captured["temperature"] == 0.2


def test_build_cua_delegate_prefers_explicit_max_turns_over_max_steps(monkeypatch) -> None:
    from matraix.agents.persona import computer_1 as computer_1_mod

    captured: dict[str, object] = {}

    class _FakeComputer1:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "harbor.agents.computer_1.Computer1",
        _FakeComputer1,
    )

    computer_1_mod._build_cua_delegate(
        "docker_computer1",
        logs_dir=pathlib.Path("/tmp/logs"),
        model_name="anthropic/claude-sonnet-4-6",
        logger=None,
        mcp_servers=None,
        skills_dir=None,
        delegate_kwargs={"max_steps": 100, "max_turns": 45},
    )
    assert captured["max_turns"] == 45
    assert "max_steps" not in captured


def test_correct_anthropic_cua_create_kwargs_opus_4_8_uses_new_tool() -> None:
    from matraix.agents.persona.use_computer_cua_protocol import (
        correct_anthropic_cua_create_kwargs,
    )

    # use-computer 0.0.44 would have sent the legacy tool for opus-4-8.
    corrected = correct_anthropic_cua_create_kwargs(
        {
            "model": "claude-opus-4-8",
            "betas": ["computer-use-2025-01-24"],
            "tools": [
                {
                    "type": "computer_20250124",
                    "name": "computer",
                    "display_width_px": 1280,
                    "display_height_px": 800,
                }
            ],
        }
    )
    assert corrected["betas"] == ["computer-use-2025-11-24"]
    assert corrected["tools"][0]["type"] == "computer_20251124"
    assert corrected["tools"][0]["name"] == "computer"


def test_correct_anthropic_cua_create_kwargs_haiku_4_5_stays_legacy() -> None:
    from matraix.agents.persona.use_computer_cua_protocol import (
        correct_anthropic_cua_create_kwargs,
    )

    corrected = correct_anthropic_cua_create_kwargs(
        {
            "model": "claude-haiku-4-5",
            "betas": ["computer-use-2025-01-24"],
            "tools": [{"type": "computer_20250124", "name": "computer"}],
        }
    )
    assert corrected["betas"] == ["computer-use-2025-01-24"]
    assert corrected["tools"][0]["type"] == "computer_20250124"


def test_apply_use_computer_anthropic_cua_protocol_patch_is_idempotent() -> None:
    from matraix.agents.persona.use_computer_cua_protocol import (
        apply_use_computer_anthropic_cua_protocol_patch,
    )

    first = apply_use_computer_anthropic_cua_protocol_patch()
    second = apply_use_computer_anthropic_cua_protocol_patch()
    # First call may be True (newly applied) or False if another test already
    # patched; second must always be False (idempotent).
    assert second is False
    assert first in {True, False}


def test_persona_system_template_is_identity_only() -> None:
    from matraix.agents.persona.loader import load_persona
    from matraix.agents.persona.templating import (
        PERSONA_INSTRUCTION_TEMPLATE,
        PERSONA_SYSTEM_TEMPLATE,
        render_persona_template,
        resolve_persona_template,
    )

    persona = load_persona(
        ROOT / "persona/datasets/matraix-persona-dev-sample/persona_0042.yaml"
    )
    system = render_persona_template(
        resolve_persona_template(persona, None, PERSONA_SYSTEM_TEMPLATE),
        persona,
    )
    instruction = render_persona_template(
        resolve_persona_template(persona, None, PERSONA_INSTRUCTION_TEMPLATE),
        persona,
        instruction="Pick a book on the site.",
    )

    assert "You are Casey Brooks." in system
    assert "## Who you are" in system
    assert "## Task instruction" not in system
    assert "Pick a book on the site." not in system
    assert "Simulated person" not in system
    assert "schema" not in system.lower()
    assert "stay in character" not in system.lower()
    assert "embody" not in system.lower()

    assert "You are Casey Brooks." in instruction
    assert "## Task instruction" in instruction
    assert "Pick a book on the site." in instruction
    assert "Simulated person" not in instruction
    assert instruction.index("You are Casey Brooks.") < instruction.index(
        "## Task instruction"
    )


def test_generic_json_prompt_keeps_identity_outside_task_instructions() -> None:
    from harbor.agents.computer_1.providers.generic import GenericJsonProvider

    provider = GenericJsonProvider(
        model_name="openai/gpt-4o",
        desktop_width=1024,
        desktop_height=900,
        identity_prompt="You are Casey Brooks.\n\n## Who you are\nA careful shopper.",
    )
    text = provider._prompt_text("Open the bookstore and choose a novel.")

    assert text.startswith("You are Casey Brooks.")
    assert "You are using a desktop computer." in text
    assert "You are computer-1" not in text
    assert "acting as" not in text.lower()
    assert "stay in character" not in text.lower()
    assert "Simulated person" not in text
    assert "Task instructions:\nOpen the bookstore and choose a novel." in text
    task_idx = text.index("Task instructions:")
    assert text.index("You are Casey Brooks.") < task_idx


def test_generic_json_prompt_without_identity_keeps_computer_1_opening() -> None:
    from harbor.agents.computer_1.providers.generic import GenericJsonProvider

    provider = GenericJsonProvider(
        model_name="openai/gpt-4o",
        desktop_width=1024,
        desktop_height=900,
    )
    text = provider._prompt_text("Click the Start button.")
    assert text.startswith("You are computer-1")
    assert "Task instructions:\nClick the Start button." in text


def test_persona_computer_1_docker_uses_identity_channel(monkeypatch, tmp_path) -> None:
    """Docker Computer1 gets identity_prompt + raw task, not persona stuffed into task."""
    import asyncio
    from types import SimpleNamespace

    from matraix.agents.persona.computer_1 import PersonaComputer1

    captured: dict[str, object] = {}

    class _FakeComputer1:
        def __init__(self, **kwargs):
            captured["init_kwargs"] = kwargs
            self._identity_prompt = kwargs.get("identity_prompt")
            self.logs_dir = kwargs.get("logs_dir")

        def version(self):
            return "fake"

        async def setup(self, environment):
            return None

        async def run(self, instruction, environment, context):
            captured["instruction"] = instruction
            captured["identity_prompt"] = getattr(self, "_identity_prompt", None)

    monkeypatch.setattr(
        "harbor.agents.computer_1.Computer1",
        _FakeComputer1,
    )

    async def _noop_materialize(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "matraix.agents.persona.computer_1.materialize_final_answer_file",
        _noop_materialize,
    )

    logs_dir = tmp_path / "agent"
    logs_dir.mkdir()
    agent = PersonaComputer1(
        logs_dir=logs_dir,
        model_name="openai/gpt-4o",
        persona_path=str(
            ROOT / "persona/datasets/matraix-persona-dev-sample/persona_0042.yaml"
        ),
        cua_backend="docker",
    )
    agent.logger = SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    )

    class _Env:
        async def upload_file(self, *args, **kwargs):
            return None

    async def _run():
        await agent.run(
            "Open Settings and enable Do Not Disturb.",
            _Env(),
            SimpleNamespace(),
        )

    asyncio.run(_run())

    assert captured["instruction"] == "Open Settings and enable Do Not Disturb."
    identity = captured["identity_prompt"]
    assert isinstance(identity, str)
    assert "You are Casey Brooks." in identity
    assert "Simulated person" not in identity
    assert "schema" not in identity.lower()
    assert "Open Settings and enable Do Not Disturb." not in identity



def test_persona_uxagent_is_registered_and_lazy_exported() -> None:
    from harbor.agents.factory import AgentFactory
    from harbor.models.agent.name import AgentName
    from matraix.agents.persona import PersonaUXAgent

    assert AgentName.PERSONA_UXAGENT.value == "persona-uxagent"
    assert (
        AgentFactory._AGENT_MAP[AgentName.PERSONA_UXAGENT]
        == "matraix.agents.persona.uxagent:PersonaUXAgent"
    )
    assert AgentFactory.get_agent_class(AgentName.PERSONA_UXAGENT) is PersonaUXAgent


def test_persona_uxagent_adapter_metadata_and_missing_task_config(
    monkeypatch, tmp_path
) -> None:
    import asyncio
    from types import SimpleNamespace

    from matraix.agents.persona.uxagent import PersonaUXAgent

    agent = PersonaUXAgent(
        logs_dir=tmp_path / "agent",
        model_name="openai/gpt-4o-mini",
        persona_path=str(
            ROOT / "persona/datasets/matraix-persona-dev-sample/persona_0042.yaml"
        ),
    )
    assert agent.name() == "persona-uxagent"
    assert agent.version() == "1.0.0"
    assert agent.SUPPORTS_WINDOWS is True
    asyncio.run(agent.setup(SimpleNamespace()))

    monkeypatch.setattr(agent, "_prepare_persona_trial", _async_noop)
    monkeypatch.setattr(
        "matraix.agents.persona.uxagent.harbor_chat_task_path_from_env",
        lambda: None,
    )

    async def _run():
        await agent.run("ignored", SimpleNamespace(), SimpleNamespace())

    try:
        asyncio.run(_run())
    except RuntimeError as exc:
        assert "MATRIX_CHATBOT_TASK_PATH is required" in str(exc)
    else:
        raise AssertionError("missing task path must fail explicitly")

    monkeypatch.setattr(
        "matraix.agents.persona.uxagent.harbor_chat_task_path_from_env",
        lambda: "application/tasks/example-chat",
    )
    monkeypatch.setattr(
        "matraix.agents.persona.uxagent.load_chatbot_task_config_for_task_path",
        lambda *args, **kwargs: None,
    )

    try:
        asyncio.run(_run())
    except RuntimeError as exc:
        assert "Missing chatbot config" in str(exc)
    else:
        raise AssertionError("missing chatbot config must fail explicitly")


def test_persona_uxagent_delegates_task_intent_and_events(monkeypatch, tmp_path) -> None:
    import asyncio
    import os
    from types import SimpleNamespace

    from playground.chatbot_task_config import ChatbotTaskConfig
    from playground.task_content_bundle import TaskContentBundle
    from matraix.agents.persona.uxagent import PersonaUXAgent

    captured: dict[str, object] = {}

    class FakePolicy:
        def __init__(self, **kwargs):
            captured["policy"] = kwargs

    class FakeClient:
        def __init__(self, **kwargs):
            captured["voice_client"] = kwargs

    class FakeRunner:
        def __init__(self, **kwargs):
            captured["runner"] = kwargs

        async def run(self, **kwargs):
            captured["run"] = kwargs
            kwargs["on_event"]({"type": "phase", "phase": "fake"})

    class FakeWriter:
        def append(self, event):
            captured["event"] = event

    monkeypatch.setattr(
        "matraix.agents.persona.uxagent.harbor_chat_task_path_from_env",
        lambda: "application/tasks/chat_vita-demo",
    )
    monkeypatch.setattr(
        "matraix.agents.persona.uxagent._repo_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "matraix.agents.persona.uxagent.load_chatbot_task_config_for_task_path",
        lambda *args, **kwargs: ChatbotTaskConfig(),
    )
    monkeypatch.setattr(
        "matraix.agents.persona.uxagent.load_task_content_bundle_for_task_path",
        lambda *args, **kwargs: TaskContentBundle(
            instruction_markdown="Choose a checking account.",
            context_markdown="The user needs low monthly fees.",
        ),
    )
    monkeypatch.setattr(
        "matraix.agents.persona.uxagent.build_json_client",
        lambda model: captured.setdefault("models", []).append(model) or object(),
    )
    monkeypatch.setattr(
        "matraix.agents.persona.uxagent.ConversationalUXPolicy",
        FakePolicy,
    )
    monkeypatch.setattr(
        "matraix.agents.persona.uxagent.VoiceLabPersonaClient",
        FakeClient,
    )
    monkeypatch.setattr(
        "matraix.agents.persona.uxagent.UXAgentTrialRunner",
        FakeRunner,
    )
    monkeypatch.setattr(
        "matraix.agents.persona.uxagent.TrialEventWriter.for_trial_dir",
        lambda path: FakeWriter(),
    )
    report_capture: dict[str, object] = {}
    monkeypatch.setattr(
        "matraix.agents.persona.uxagent.load_self_report_schema_for_task_path",
        lambda *args, **kwargs: "task-schema",
    )
    monkeypatch.setattr(
        "matraix.agents.persona.uxagent.assemble_report_system_prompt",
        lambda *args, **kwargs: report_capture.setdefault("prompt", kwargs) or "report",
    )
    monkeypatch.setattr(
        "matraix.agents.persona.uxagent.final_self_report",
        lambda client, **kwargs: report_capture.update(
            client=client, report=kwargs
        )
        or "questionnaire",
    )
    monkeypatch.setenv("APP_PASSWORD", "must-not-enter-prompts")

    agent = PersonaUXAgent(
        logs_dir=tmp_path / "agent",
        model_name="openai/gpt-4o-mini",
        persona_path=str(
            ROOT / "persona/datasets/matraix-persona-dev-sample/persona_0042.yaml"
        ),
    )
    monkeypatch.setattr(agent, "_prepare_persona_trial", _async_noop)

    class Env:
        trial_paths = SimpleNamespace(trial_dir=tmp_path / "trial")

    async def _run():
        await agent.run("ignored", Env(), SimpleNamespace())

    asyncio.run(_run())

    policy = captured["policy"]
    assert policy["task_intent"] == (
        "Choose a checking account.\n\nThe user needs low monthly fees."
    )
    assert "must-not-enter-prompts" not in repr(policy)
    runner = captured["runner"]
    assert runner["questionnaire_builder"]
    run_kwargs = captured["run"]
    assert run_kwargs["environment"] is not None
    assert run_kwargs["persona"] is agent._persona
    assert run_kwargs["runtime"].__class__ is ChatbotTaskConfig
    assert run_kwargs["task_intent"] == policy["task_intent"]
    assert captured["event"] == {"type": "phase", "phase": "fake"}
    assert captured["models"] == ["openai/gpt-4o-mini", "openai/gpt-4o-mini"]
    assert "must-not-enter-prompts" not in repr(run_kwargs["task_intent"])
    assert os.environ["APP_PASSWORD"] == "must-not-enter-prompts"
    runner["questionnaire_builder"](
        persona=SimpleNamespace(),
        transcript=[],
        config=None,
        task_intent=policy["task_intent"],
    )
    assert report_capture["prompt"]["task_bundle"].instruction_markdown == (
        "Choose a checking account."
    )
    assert report_capture["prompt"]["task_bundle"].context_markdown == (
        "The user needs low monthly fees."
    )
    assert "must-not-enter-prompts" not in repr(report_capture)


async def _async_noop(*args, **kwargs):
    return None
