import json

import pytest

from playground.model_client import (
    DASHSCOPE_DEFAULT_BASE_URL,
    GEMINI_DEFAULT_BASE_URL,
    build_json_client,
    dashscope_openai_client_kwargs,
    gemini_openai_client_kwargs,
)
from playground.openai_client import OpenAIChatClient
from playground.user_sim.tool_client import OpenAIToolStepClient, build_tool_step_client


class _FakeOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = object()


def test_dashscope_openai_client_kwargs_reads_env(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope-test")
    monkeypatch.delenv("DASHSCOPE_API_BASE", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    kwargs = dashscope_openai_client_kwargs("dashscope/qwen3.7-max")
    assert kwargs == {
        "model": "qwen3.7-max",
        "api_key": "sk-dashscope-test",
        "base_url": DASHSCOPE_DEFAULT_BASE_URL,
    }


def test_build_json_client_routes_dashscope_to_openai_compatible(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope-test")
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = build_json_client("dashscope/qwen3.6-plus-2026-04-02")
    assert isinstance(client, OpenAIChatClient)
    assert client.model == "qwen3.6-plus-2026-04-02"
    assert created == [
        {
            "api_key": "sk-dashscope-test",
            "base_url": DASHSCOPE_DEFAULT_BASE_URL,
        }
    ]


def test_build_tool_step_client_routes_dashscope(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope-test")
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = build_tool_step_client("dashscope/deepseek-v4-pro")
    assert isinstance(client, OpenAIToolStepClient)
    assert client.model == "deepseek-v4-pro"
    assert created == [
        {
            "api_key": "sk-dashscope-test",
            "base_url": DASHSCOPE_DEFAULT_BASE_URL,
        }
    ]


def test_build_json_client_requires_dashscope_key(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        build_json_client("dashscope/qwen-plus")


def test_gemini_openai_client_kwargs_reads_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "sk-gemini-test")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_BASE", raising=False)

    kwargs = gemini_openai_client_kwargs("gemini/gemini-2.5-pro")
    assert kwargs == {
        "model": "gemini-2.5-pro",
        "api_key": "sk-gemini-test",
        "base_url": GEMINI_DEFAULT_BASE_URL,
    }


def test_build_json_client_routes_gemini_to_openai_compatible(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "sk-gemini-test")
    monkeypatch.delenv("GEMINI_API_BASE", raising=False)
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = build_json_client("gemini/gemini-2.5-flash")
    assert isinstance(client, OpenAIChatClient)
    assert client.model == "gemini-2.5-flash"
    assert created == [
        {
            "api_key": "sk-gemini-test",
            "base_url": GEMINI_DEFAULT_BASE_URL,
        }
    ]


def test_build_tool_step_client_routes_gemini(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "sk-google-test")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_BASE", raising=False)
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = build_tool_step_client("google/gemini-2.5-pro")
    assert isinstance(client, OpenAIToolStepClient)
    assert client.model == "gemini-2.5-pro"
    assert created == [
        {
            "api_key": "sk-google-test",
            "base_url": GEMINI_DEFAULT_BASE_URL,
        }
    ]


def test_build_json_client_requires_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        build_json_client("gemini/gemini-2.5-pro")


def test_xai_openai_client_kwargs_reads_env(monkeypatch):
    from playground.model_client import XAI_DEFAULT_BASE_URL, xai_openai_client_kwargs

    monkeypatch.setenv("XAI_API_KEY", "sk-xai-test")
    monkeypatch.delenv("XAI_API_BASE", raising=False)

    kwargs = xai_openai_client_kwargs("xai/grok-4.5")
    assert kwargs == {
        "model": "grok-4.5",
        "api_key": "sk-xai-test",
        "base_url": XAI_DEFAULT_BASE_URL,
    }


def test_build_json_client_routes_xai_to_openai_compatible(monkeypatch):
    from playground.model_client import XAI_DEFAULT_BASE_URL

    monkeypatch.setenv("XAI_API_KEY", "sk-xai-test")
    monkeypatch.delenv("XAI_API_BASE", raising=False)
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = build_json_client("xai/grok-3-mini")
    assert isinstance(client, OpenAIChatClient)
    assert client.model == "grok-3-mini"
    assert created == [
        {
            "api_key": "sk-xai-test",
            "base_url": XAI_DEFAULT_BASE_URL,
        }
    ]


def test_build_tool_step_client_routes_xai(monkeypatch):
    from playground.model_client import XAI_DEFAULT_BASE_URL

    monkeypatch.setenv("XAI_API_KEY", "sk-xai-test")
    monkeypatch.delenv("XAI_API_BASE", raising=False)
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = build_tool_step_client("xai/grok-4.5")
    assert isinstance(client, OpenAIToolStepClient)
    assert client.model == "grok-4.5"
    assert created == [
        {
            "api_key": "sk-xai-test",
            "base_url": XAI_DEFAULT_BASE_URL,
        }
    ]


def test_build_json_client_requires_xai_key(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="XAI_API_KEY"):
        build_json_client("xai/grok-4.5")


def test_deepseek_openai_client_kwargs_reads_env(monkeypatch):
    from playground.model_client import DEEPSEEK_DEFAULT_BASE_URL, deepseek_openai_client_kwargs

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    monkeypatch.delenv("DEEPSEEK_API_BASE", raising=False)

    kwargs = deepseek_openai_client_kwargs("deepseek/deepseek-v4-pro")
    assert kwargs == {
        "model": "deepseek-v4-pro",
        "api_key": "sk-deepseek-test",
        "base_url": DEEPSEEK_DEFAULT_BASE_URL,
    }


def test_build_json_client_routes_deepseek_to_openai_compatible(monkeypatch):
    from playground.model_client import DEEPSEEK_DEFAULT_BASE_URL

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    monkeypatch.delenv("DEEPSEEK_API_BASE", raising=False)
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = build_json_client("deepseek/deepseek-chat")
    assert isinstance(client, OpenAIChatClient)
    assert client.model == "deepseek-chat"
    assert created == [
        {
            "api_key": "sk-deepseek-test",
            "base_url": DEEPSEEK_DEFAULT_BASE_URL,
        }
    ]


def test_build_tool_step_client_routes_deepseek(monkeypatch):
    from playground.model_client import DEEPSEEK_DEFAULT_BASE_URL

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    monkeypatch.delenv("DEEPSEEK_API_BASE", raising=False)
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = build_tool_step_client("deepseek/deepseek-v4-pro")
    assert isinstance(client, OpenAIToolStepClient)
    assert client.model == "deepseek-v4-pro"
    assert created == [
        {
            "api_key": "sk-deepseek-test",
            "base_url": DEEPSEEK_DEFAULT_BASE_URL,
        }
    ]


def test_build_json_client_requires_deepseek_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        build_json_client("deepseek/deepseek-chat")


def test_zai_openai_client_kwargs_reads_env(monkeypatch):
    from playground.model_client import ZAI_DEFAULT_BASE_URL, zai_openai_client_kwargs

    monkeypatch.setenv("ZAI_API_KEY", "sk-zai-test")
    monkeypatch.delenv("ZAI_API_BASE", raising=False)

    kwargs = zai_openai_client_kwargs("zai/glm-4.7")
    assert kwargs == {
        "model": "glm-4.7",
        "api_key": "sk-zai-test",
        "base_url": ZAI_DEFAULT_BASE_URL,
    }


def test_build_json_client_routes_zai_to_openai_compatible(monkeypatch):
    from playground.model_client import ZAI_DEFAULT_BASE_URL

    monkeypatch.setenv("ZAI_API_KEY", "sk-zai-test")
    monkeypatch.delenv("ZAI_API_BASE", raising=False)
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = build_json_client("zai/glm-5")
    assert isinstance(client, OpenAIChatClient)
    assert client.model == "glm-5"
    assert created == [
        {
            "api_key": "sk-zai-test",
            "base_url": ZAI_DEFAULT_BASE_URL,
        }
    ]


def test_build_tool_step_client_routes_zai(monkeypatch):
    from playground.model_client import ZAI_DEFAULT_BASE_URL

    monkeypatch.setenv("ZAI_API_KEY", "sk-zai-test")
    monkeypatch.delenv("ZAI_API_BASE", raising=False)
    created: list[dict[str, str]] = []

    def fake_openai(**kwargs):
        created.append(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", fake_openai)

    client = build_tool_step_client("zai/glm-4.7")
    assert isinstance(client, OpenAIToolStepClient)
    assert client.model == "glm-4.7"
    assert created == [
        {
            "api_key": "sk-zai-test",
            "base_url": ZAI_DEFAULT_BASE_URL,
        }
    ]


def test_build_json_client_requires_zai_key(monkeypatch):
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ZAI_API_KEY"):
        build_json_client("zai/glm-5")


class _FakeAnthropicResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _capture_anthropic_body(monkeypatch, model):
    sent = {}

    def fake_urlopen(request, timeout=None):
        sent.update(json.loads(request.data.decode("utf-8")))
        return _FakeAnthropicResponse(
            {
                "content": [{"type": "text", "text": '{"ok": true}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr("playground.model_client.urllib.request.urlopen", fake_urlopen)
    client = build_json_client(model, temperature=0.7)
    assert client.complete_json("sys", "user") == {"ok": True}
    return sent


@pytest.mark.parametrize(
    "model",
    [
        "anthropic/claude-haiku-5-5",
        "anthropic/claude-sonnet-5",
        "anthropic/claude-opus-5-5",
        "anthropic/claude-fable-5-2",
    ],
)
def test_anthropic_json_client_omits_temperature_for_claude_5(monkeypatch, model):
    # Claude 5 models answer HTTP 400 "`temperature` is deprecated for this model".
    assert "temperature" not in _capture_anthropic_body(monkeypatch, model)


def test_anthropic_json_client_keeps_temperature_for_claude_4(monkeypatch):
    sent = _capture_anthropic_body(monkeypatch, "anthropic/claude-haiku-4-5-20251001")
    assert sent["temperature"] == 0.7
