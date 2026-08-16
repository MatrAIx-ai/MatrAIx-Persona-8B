"""Provider-aware credential helpers for MatrAIx job preflight.

Mirrors the prefix rules in ``playground.model_client.build_json_client`` so the
job generator and CLI can tell users which API key a job needs — without
printing secret values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCredential:
    """Resolved provider + credential env var for a persona ``model_name``."""

    provider: str
    env_var: str
    model_name: str

    @property
    def present(self) -> bool:
        return bool((os.environ.get(self.env_var) or "").strip())


def resolve_provider_credential(model_name: str) -> ProviderCredential:
    """Infer the credential env var for a Harbor/MatrAIx ``model_name`` string."""
    value = (model_name or "").strip() or "anthropic/claude-sonnet-4-6"
    lowered = value.lower()

    if lowered.startswith("openai/") or lowered.startswith("gpt-"):
        return ProviderCredential("OpenAI", "OPENAI_API_KEY", value)
    if lowered.startswith("dashscope/"):
        return ProviderCredential("DashScope", "DASHSCOPE_API_KEY", value)
    if lowered.startswith("openrouter/"):
        return ProviderCredential("OpenRouter", "OPENROUTER_API_KEY", value)
    if lowered.startswith("anthropic/"):
        return ProviderCredential("Anthropic", "ANTHROPIC_API_KEY", value)
    if "/" not in value:
        # Bare Anthropic model ids (historical default for Survey).
        return ProviderCredential("Anthropic", "ANTHROPIC_API_KEY", value)
    # Unknown prefix: fall back to Anthropic so existing docs stay coherent,
    # but label the provider from the prefix for the preflight printout.
    prefix = value.split("/", 1)[0]
    return ProviderCredential(prefix, "ANTHROPIC_API_KEY", value)


def format_credential_preflight(
    model_name: str,
    *,
    extra_env_hints: list[tuple[str, str]] | None = None,
) -> list[str]:
    """Human-readable preflight lines (no secret values).

    ``extra_env_hints`` is a list of ``(env_var, reason)`` for secondary keys
    (e.g. user-sim chatbot engine still needing ``OPENAI_API_KEY``).
    """
    cred = resolve_provider_credential(model_name)
    status = "present" if cred.present else "missing"
    lines = [
        f"Provider: {cred.provider}",
        f"Model: {cred.model_name}",
        f"Credential: {cred.env_var} {status}",
        "Credential value: not inspected",
    ]
    for env_var, reason in extra_env_hints or []:
        if env_var == cred.env_var:
            continue
        extra_status = "present" if (os.environ.get(env_var) or "").strip() else "missing"
        lines.append(f"Also required: {env_var} {extra_status} ({reason})")
    return lines


def export_hint_lines(model_name: str) -> list[str]:
    """Shell export stubs for the primary (and only) model credential."""
    cred = resolve_provider_credential(model_name)
    return [f"export {cred.env_var}=..."]
