import pytest

from playground import model_client
from playground.openai_client import OpenAIChatClient
from playground.user_sim.tool_client import OpenAIToolStepClient, build_tool_step_client


class _FakeOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = object()


def test_orcarouter_model_id_preserves_provider_model_path():
    assert (
        model_client.orcarouter_model_id("orcarouter/z-ai/glm-4.7")
        == "z-ai/glm-4.7"
    )


def test_orcarouter_model_id_preserves_anthropic_model_path():
    assert (
        model_client.orcarouter_model_id(
            "orcarouter/anthropic/claude-haiku-4.5"
        )
        == "anthropic/claude-haiku-4.5"
    )


def test_orcarouter_model_id_keeps_auto_router_alias():
    assert model_client.orcarouter_model_id("orcarouter/auto") == "auto"


def test_orcarouter_openai_client_kwargs_requires_api_key(monkeypatch):
    monkeypatch.delenv("ORCAROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="ORCAROUTER_API_KEY"):
        model_client.orcarouter_openai_client_kwargs(
            "orcarouter/z-ai/glm-4.7"
        )


def test_orcarouter_api_base_overrides_default(monkeypatch):
    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-test")
    monkeypatch.setenv("ORCAROUTER_API_BASE", "https://orcarouter.test/v1")

    kwargs = model_client.orcarouter_openai_client_kwargs(
        "orcarouter/z-ai/glm-4.7"
    )
    assert kwargs == {
        "model": "z-ai/glm-4.7",
        "api_key": "sk-orca-test",
        "base_url": "https://orcarouter.test/v1",
    }


def test_build_json_client_routes_orcarouter_to_openai_compatible(monkeypatch):
    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-test")
    monkeypatch.delenv("ORCAROUTER_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = model_client.build_json_client("orcarouter/z-ai/glm-4.7")
    assert isinstance(client, OpenAIChatClient)
    assert client.model == "z-ai/glm-4.7"
    assert created == [
        {
            "api_key": "sk-orca-test",
            "base_url": model_client.ORCAROUTER_DEFAULT_BASE_URL,
        }
    ]


def test_build_json_client_routes_orcarouter_auto(monkeypatch):
    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-test")
    monkeypatch.delenv("ORCAROUTER_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = model_client.build_json_client("orcarouter/auto")
    assert isinstance(client, OpenAIChatClient)
    assert client.model == "auto"
    assert created == [
        {
            "api_key": "sk-orca-test",
            "base_url": model_client.ORCAROUTER_DEFAULT_BASE_URL,
        }
    ]


def test_build_tool_step_client_routes_orcarouter_to_openai_compatible(monkeypatch):
    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-test")
    monkeypatch.delenv("ORCAROUTER_API_BASE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = build_tool_step_client("orcarouter/z-ai/glm-4.7")
    assert isinstance(client, OpenAIToolStepClient)
    assert client.model == "z-ai/glm-4.7"
    assert created == [
        {
            "api_key": "sk-orca-test",
            "base_url": model_client.ORCAROUTER_DEFAULT_BASE_URL,
        }
    ]


def test_openai_base_url_does_not_change_orcarouter_routing(monkeypatch):
    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-test")
    monkeypatch.delenv("ORCAROUTER_API_BASE", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai-proxy.test/v1")
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = model_client.build_json_client("orcarouter/z-ai/glm-4.7")
    assert isinstance(client, OpenAIChatClient)
    assert client.model == "z-ai/glm-4.7"
    assert created == [
        {
            "api_key": "sk-orca-test",
            "base_url": model_client.ORCAROUTER_DEFAULT_BASE_URL,
        }
    ]
