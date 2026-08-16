from matraix.provider_credentials import (
    format_credential_preflight,
    resolve_provider_credential,
)


def test_resolve_openai_and_dashscope(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    openai = resolve_provider_credential("openai/gpt-4o-mini")
    assert openai.provider == "OpenAI"
    assert openai.env_var == "OPENAI_API_KEY"
    assert openai.present is False
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    dash = resolve_provider_credential("dashscope/deepseek-v3.2")
    assert dash.provider == "DashScope"
    assert dash.env_var == "DASHSCOPE_API_KEY"
    assert dash.present is True


def test_resolve_anthropic_default_and_bare_model() -> None:
    assert resolve_provider_credential("anthropic/claude-sonnet-4-6").env_var == (
        "ANTHROPIC_API_KEY"
    )
    assert resolve_provider_credential("claude-sonnet-4-6").provider == "Anthropic"


def test_format_preflight_never_prints_secret(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-should-not-appear")
    lines = format_credential_preflight("openai/gpt-4o-mini")
    joined = "\n".join(lines)
    assert "OPENAI_API_KEY present" in joined
    assert "sk-secret" not in joined
    assert "Credential value: not inspected" in joined
