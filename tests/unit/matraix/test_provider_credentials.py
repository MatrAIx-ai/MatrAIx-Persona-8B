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


def test_resolve_gemini(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cred = resolve_provider_credential("gemini/gemini-2.5-pro")
    assert cred.provider == "Gemini"
    assert cred.env_var == "GEMINI_API_KEY"
    assert cred.present is False
    monkeypatch.setenv("GEMINI_API_KEY", "sk-test")
    assert resolve_provider_credential("google/gemini-2.5-flash").present is True


def test_resolve_xai(monkeypatch) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    cred = resolve_provider_credential("xai/grok-4.5")
    assert cred.provider == "xAI"
    assert cred.env_var == "XAI_API_KEY"
    assert cred.present is False
    monkeypatch.setenv("XAI_API_KEY", "sk-test")
    assert resolve_provider_credential("xai/grok-3-mini").present is True


def test_resolve_deepseek_and_zai(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    deepseek = resolve_provider_credential("deepseek/deepseek-v4-pro")
    assert deepseek.provider == "DeepSeek"
    assert deepseek.env_var == "DEEPSEEK_API_KEY"
    assert deepseek.present is False
    zai = resolve_provider_credential("zai/glm-4.7")
    assert zai.provider == "Z.ai"
    assert zai.env_var == "ZAI_API_KEY"
    assert zai.present is False
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("ZAI_API_KEY", "sk-test")
    assert resolve_provider_credential("deepseek/deepseek-chat").present is True
    assert resolve_provider_credential("zai/glm-5").present is True


def test_resolve_openrouter_and_orcarouter(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ORCAROUTER_API_KEY", raising=False)
    openrouter = resolve_provider_credential("openrouter/z-ai/glm-4.7")
    assert openrouter.provider == "OpenRouter"
    assert openrouter.env_var == "OPENROUTER_API_KEY"
    assert openrouter.present is False
    orcarouter = resolve_provider_credential("orcarouter/auto")
    assert orcarouter.provider == "OrcaRouter"
    assert orcarouter.env_var == "ORCAROUTER_API_KEY"
    assert orcarouter.present is False
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-test")
    assert resolve_provider_credential("openrouter/anthropic/claude-haiku-4.5").present is True
    assert (
        resolve_provider_credential("orcarouter/anthropic/claude-haiku-4.5").present
        is True
    )


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
