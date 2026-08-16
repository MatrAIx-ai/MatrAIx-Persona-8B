import pytest
from playground.openai_client import OpenAIChatClient, coerce_json


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeUsage:
    def __init__(self, prompt_tokens=11, completion_tokens=3):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.prompt_tokens_details = None


class _FakeCompletion:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()
        self.id = "chatcmpl-test"


class _FakeCompletions:
    def __init__(self, content):
        self._c = content
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeCompletion(self._c)


class _FakeChat:
    def __init__(self, content):
        self.completions = _FakeCompletions(content)


class _FakeOpenAI:
    def __init__(self, content):
        self.chat = _FakeChat(content)


def test_coerce_json_plain_and_fenced():
    assert coerce_json('{"a": 1}') == {"a": 1}
    assert coerce_json('```json\n{"a": 2}\n```') == {"a": 2}


def test_complete_json_parses_and_requests_json_mode():
    fake = _FakeOpenAI('{"message": "hi", "decision": "continue"}')
    client = OpenAIChatClient(model="gpt-4o-mini", client=fake)
    out = client.complete_json("sys", "user")
    assert out == {"message": "hi", "decision": "continue"}
    kw = fake.chat.completions.last_kwargs
    assert kw["model"] == "gpt-4o-mini"
    assert kw["response_format"] == {"type": "json_object"}
    assert kw["temperature"] == 0.7
    assert kw["messages"][0]["role"] == "system" and kw["messages"][1]["role"] == "user"


def test_complete_json_omits_temperature_for_gpt5():
    fake = _FakeOpenAI('{"ok": true}')
    client = OpenAIChatClient(model="gpt-5.5", client=fake, temperature=0.1)
    assert client.complete_json("sys", "user") == {"ok": True}
    kw = fake.chat.completions.last_kwargs
    assert "temperature" not in kw
    assert kw["model"] == "gpt-5.5"


def test_complete_json_omits_temperature_for_claude_opus_4_8():
    fake = _FakeOpenAI('{"ok": true}')
    client = OpenAIChatClient(
        model="anthropic/claude-opus-4-8", client=fake, temperature=0.1
    )
    assert client.complete_json("sys", "user") == {"ok": True}
    kw = fake.chat.completions.last_kwargs
    assert "temperature" not in kw
    assert kw["model"] == "anthropic/claude-opus-4-8"


def test_openai_model_supports_custom_temperature_opus_rules():
    from playground.openai_client import openai_model_supports_custom_temperature

    assert openai_model_supports_custom_temperature("anthropic/claude-haiku-4-5")
    assert openai_model_supports_custom_temperature("anthropic/claude-sonnet-4-6")
    assert openai_model_supports_custom_temperature("claude-opus-4-1")
    assert not openai_model_supports_custom_temperature("anthropic/claude-opus-4-8")
    assert not openai_model_supports_custom_temperature("claude-opus-4-7")


def test_complete_json_raises_on_unparseable():
    client = OpenAIChatClient(model="gpt-4o-mini", client=_FakeOpenAI("not json at all"))
    with pytest.raises(ValueError):
        client.complete_json("s", "u")


def test_complete_json_with_usage_returns_token_counts():
    fake = _FakeOpenAI('{"ok": true}')
    client = OpenAIChatClient(model="gpt-4o-mini", client=fake, provider="openai")
    result = client.complete_json_with_usage("sys", "user")
    assert result.data == {"ok": True}
    assert result.usage is not None
    assert result.usage.n_input_tokens == 11
    assert result.usage.n_output_tokens == 3
    assert result.usage.request_id == "chatcmpl-test"
    assert result.usage.provider == "openai"
