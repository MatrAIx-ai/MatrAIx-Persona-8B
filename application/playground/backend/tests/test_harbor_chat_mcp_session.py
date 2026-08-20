"""Tests for Harbor MCP chat session helpers."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import playground.harbor.chat_eval as chat_eval_module
from playground.chatbot_task_config import ChatbotTaskConfig
from playground.harbor.chat_eval import create_harbor_chat_session
from playground.harbor.chat_mcp_session import (
    HarborMcpChatSession,
    _MCP_CALL_SCRIPT,
    harbor_chat_mcp_url_from_task_path,
)
from playground.types import PlaygroundConfig


def test_mcp_call_script_uses_current_streamable_http_client_name() -> None:
    assert "streamable_http_client" in _MCP_CALL_SCRIPT
    assert "streamablehttp_client" not in _MCP_CALL_SCRIPT
    assert "as (read, write):" in _MCP_CALL_SCRIPT
    assert "as (read, write, _):" not in _MCP_CALL_SCRIPT
    assert 'getattr(result, "is_error"' in _MCP_CALL_SCRIPT


def test_harbor_chat_mcp_url_from_task_path_reads_task_toml(tmp_path: Path) -> None:
    task_dir = tmp_path / "application" / "tasks" / "example-chat-mcp_support_chatbot"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        "\n".join(
            [
                "[environment]",
                'definition = "application/shared-chat-persona"',
                'local_compose = "application/chatbot-mcp-sidecar_acme-support"',
                "[[environment.mcp_servers]]",
                'name = "acme-support"',
                'transport = "streamable-http"',
                'url = "http://support-bot:8000/mcp"',
            ]
        ),
        encoding="utf-8",
    )

    url = harbor_chat_mcp_url_from_task_path(
        "application/tasks/example-chat-mcp_support_chatbot",
        repo_root=tmp_path,
    )
    assert url == "http://support-bot:8000/mcp"


def test_create_harbor_chat_session_selects_mcp(tmp_path: Path) -> None:
    task_dir = tmp_path / "application" / "tasks" / "example-chat-mcp_support_chatbot"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        "\n".join(
            [
                "[[environment.mcp_servers]]",
                'url = "http://support-bot:8000/mcp"',
            ]
        ),
        encoding="utf-8",
    )
    environment = SimpleNamespace(
        trial_paths=SimpleNamespace(trial_dir=tmp_path / "trial"),
    )
    environment.trial_paths.trial_dir.mkdir(parents=True)

    session = create_harbor_chat_session(
        environment,
        PlaygroundConfig(application_id="acme_support_mcp"),
        runtime=ChatbotTaskConfig(transport="mcp"),
        task_path="application/tasks/example-chat-mcp_support_chatbot",
        repo_root=tmp_path,
        trial_dir=environment.trial_paths.trial_dir,
    )

    assert isinstance(session, HarborMcpChatSession)


def test_create_harbor_chat_session_uses_host_sidecar_api_marker_for_mcp(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "application" / "tasks" / "example-chat-mcp_support_chatbot"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        "\n".join(
            [
                "[[environment.mcp_servers]]",
                'url = "http://support-bot:8000/mcp"',
            ]
        ),
        encoding="utf-8",
    )
    trial_dir = tmp_path / "trial"
    trial_dir.mkdir(parents=True)
    (trial_dir / ".sidecar_api_url").write_text("http://127.0.0.1:54321\n", encoding="utf-8")
    environment = SimpleNamespace(trial_paths=SimpleNamespace(trial_dir=trial_dir))

    session = create_harbor_chat_session(
        environment,
        PlaygroundConfig(application_id="acme_support_mcp"),
        runtime=ChatbotTaskConfig(transport="mcp"),
        task_path="application/tasks/example-chat-mcp_support_chatbot",
        repo_root=tmp_path,
        trial_dir=trial_dir,
    )

    assert isinstance(session, HarborMcpChatSession)
    assert session._mcp_url == "http://127.0.0.1:54321/mcp"


def test_create_harbor_chat_session_uses_local_mcp_sidecar_when_reachable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_dir = tmp_path / "application" / "tasks" / "example-chat-mcp_support_chatbot"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        "\n".join(
            [
                "[[environment.mcp_servers]]",
                'url = "http://support-bot:8000/mcp"',
            ]
        ),
        encoding="utf-8",
    )
    trial_dir = tmp_path / "trial"
    trial_dir.mkdir(parents=True)
    environment = SimpleNamespace(trial_paths=SimpleNamespace(trial_dir=trial_dir))
    monkeypatch.setattr(
        chat_eval_module,
        "_local_mcp_sidecar_url",
        lambda application_id: "http://127.0.0.1:8903/mcp"
        if application_id == "acme_support_mcp"
        else None,
    )

    session = create_harbor_chat_session(
        environment,
        PlaygroundConfig(application_id="acme_support_mcp"),
        runtime=ChatbotTaskConfig(transport="mcp"),
        task_path="application/tasks/example-chat-mcp_support_chatbot",
        repo_root=tmp_path,
        trial_dir=trial_dir,
    )

    assert isinstance(session, HarborMcpChatSession)
    assert session._mcp_url == "http://127.0.0.1:8903/mcp"


@pytest.mark.anyio
async def test_harbor_mcp_chat_session_calls_tools_via_environment_exec(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    class FakeEnvironment:
        async def exec(self, command: str, timeout_sec: int = 200):
            del timeout_sec
            assert "uvx --with mcp python3 -c" in command
            if "send_message" in command:
                calls.append(("send_message", {"message": "Hello there"}))
                payload = {"text": "Hi, how can I help?", "isError": False}
            else:
                calls.append(("get_conversation_history", {}))
                payload = {
                    "text": json.dumps(
                        {
                            "messages": [
                                {"role": "customer", "content": "Hello there"},
                                {"role": "support", "content": "Hi, how can I help?"},
                            ]
                        }
                    ),
                    "isError": False,
                }
            return SimpleNamespace(return_code=0, stdout=json.dumps(payload), stderr="")

    session = HarborMcpChatSession(
        FakeEnvironment(),
        PlaygroundConfig(application_id="acme_support_mcp"),
        runtime=ChatbotTaskConfig(transport="mcp"),
        mcp_url="http://support-bot:8000/mcp",
    )

    view = await session.run_turn_sync("Hello there")
    assert view["assistantMessage"] == "Hi, how can I help?"
    transcript = await session.fetch_conversation_artifact()
    assert transcript["messages"][0]["role"] == "customer"
    assert transcript["turns"][0]["assistantMessage"] == "Hi, how can I help?"
    assert calls[0][0] == "send_message"
    assert calls[1][0] == "get_conversation_history"


@pytest.mark.anyio
async def test_run_harbor_chat_eval_for_persona_uses_mcp_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: dict[str, object] = {}

    class FakeEnvironment:
        def __init__(self) -> None:
            self.trial_paths = SimpleNamespace(trial_dir=tmp_path / "trial")
            self.trial_paths.trial_dir.mkdir(parents=True, exist_ok=True)

        async def upload_file(self, source: Path, destination: str) -> None:
            del source, destination

    class FakePersona:
        persona_id = "p1"
        display_name = "Persona One"
        summary = ""
        system_prompt = "Persona context"
        persona_path = ""
        data = {"source": "fixture"}

    async def fake_run_harbor_chat_eval(session, *args, **kwargs):
        del args, kwargs
        created["session"] = session
        session._session_id = "mcp-session"
        return SimpleNamespace(
            config=PlaygroundConfig(application_id="acme_support_mcp"),
            metric_scores=SimpleNamespace(turns_to_recommendation=1),
        )

    async def fake_fetch_conversation(self):
        return {
            "messages": [
                {"role": "customer", "content": "Hello"},
                {"role": "support", "content": "Hi"},
            ]
        }

    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        chat_eval_module,
        "harbor_chat_task_config_from_env",
        lambda **_kwargs: ChatbotTaskConfig(transport="mcp"),
    )
    monkeypatch.setattr(
        chat_eval_module,
        "harbor_chat_config_from_env",
        lambda **_kwargs: PlaygroundConfig(application_id="acme_support_mcp"),
    )
    monkeypatch.setattr(
        chat_eval_module,
        "load_task_content_bundle_for_task_path",
        lambda *_args, **_kwargs: SimpleNamespace(
            context_markdown="Support chat.",
            instruction_markdown="",
        ),
    )
    monkeypatch.setattr(
        chat_eval_module,
        "harbor_chat_mcp_url_from_task_path",
        lambda *_args, **_kwargs: "http://support-bot:8000/mcp",
    )
    monkeypatch.setattr(chat_eval_module, "run_harbor_chat_eval", fake_run_harbor_chat_eval)
    monkeypatch.setattr(
        HarborMcpChatSession,
        "fetch_conversation_artifact",
        fake_fetch_conversation,
    )
    async def fake_write_output_artifacts(*args, **kwargs):
        del args, kwargs

    monkeypatch.setattr(chat_eval_module, "_write_output_artifacts", fake_write_output_artifacts)
    monkeypatch.setenv(
        "MATRIX_CHATBOT_TASK_PATH",
        "application/tasks/example-chat-mcp_support_chatbot",
    )

    _, session_id = await chat_eval_module.run_harbor_chat_eval_for_persona(
        FakeEnvironment(),
        FakePersona(),
    )

    assert isinstance(created["session"], HarborMcpChatSession)
    assert session_id == "mcp-session"
