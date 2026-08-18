"""Runtime persona-language resolution and prompt contract helpers.

This module deliberately owns runtime language only.  It does not translate
persona dimension labels, task content, artifact keys, or protocol fields.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from matraix.launch_env import (
    PERSONA_LANGUAGE_ENV as MATRIX_PERSONA_LANGUAGE_ENV,
    PERSONA_LANGUAGE_OVERRIDE_ENV as MATRIX_PERSONA_LANGUAGE_OVERRIDE_ENV,
    PERSONA_LANGUAGE_SOURCE_ENV as MATRIX_PERSONA_LANGUAGE_SOURCE_ENV,
    PERSONA_LANGUAGE_TOKENS,
    canonicalize_persona_language,
)

SUPPORTED_PERSONA_LANGUAGES = frozenset(PERSONA_LANGUAGE_TOKENS)
PERSONA_LANGUAGE_SOURCES = frozenset(
    {"follow_ui", "explicit", "env", "default"}
)

_LANGUAGE_NAMES = {
    "en": "English",
    "ko": "Korean",
    "zh-Hans": "Simplified Chinese",
    "zh-Hant": "Traditional Chinese",
    "ja": "Japanese",
    "pt-BR": "Brazilian Portuguese",
    "es": "Spanish",
}


@dataclass(frozen=True)
class PersonaLanguageResolution:
    language: str
    source: str


def normalize_persona_language(value: object) -> str | None:
    """Return a supported canonical runtime language, or ``None``."""
    if value is None:
        return None
    return canonicalize_persona_language(str(value))


def _runtime_environment(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def _normalize_source_hint(value: object) -> str | None:
    raw = str(value or "").strip().lower()
    return raw if raw in PERSONA_LANGUAGE_SOURCES else None


def _environment_language(environ: Mapping[str, str]) -> tuple[str | None, str | None]:
    """Resolve language env values without trusting a provenance label."""
    language = normalize_persona_language(environ.get(MATRIX_PERSONA_LANGUAGE_ENV))
    if language is None:
        return None, None
    source_hint = _normalize_source_hint(
        environ.get(MATRIX_PERSONA_LANGUAGE_SOURCE_ENV)
    )
    return language, source_hint or "env"


def resolve_persona_language_with_source(
    requested_language: object = None,
    *,
    requested_source: object = None,
    environ: Mapping[str, str] | None = None,
) -> PersonaLanguageResolution:
    """Resolve runtime language with explicit values taking precedence.

    A CLI override marker has highest precedence so ``matraix run
    --persona-language`` can replace language kwargs in an existing generated
    job. ``requested_language`` otherwise represents a direct runtime/agent
    argument. A valid source supplied with a direct agent argument is retained.
    This is how Harbor preserves ``follow_ui``, ``explicit``, ``env``, and
    ``default`` from launch metadata through the trial artifact. A direct
    language without a source is an explicit override. Environment provenance
    is read only from a paired runtime value; legacy language-only values are
    marked ``env``.
    """
    runtime_environment = _runtime_environment(environ)
    cli_override = normalize_persona_language(
        runtime_environment.get(MATRIX_PERSONA_LANGUAGE_OVERRIDE_ENV)
    )
    if cli_override is not None:
        return PersonaLanguageResolution(language=cli_override, source="explicit")

    explicit = normalize_persona_language(requested_language)
    if explicit is not None:
        requested_source_hint = _normalize_source_hint(requested_source)
        return PersonaLanguageResolution(
            language=explicit,
            source=requested_source_hint or "explicit",
        )

    env_language, env_source = _environment_language(runtime_environment)
    if env_language is not None:
        return PersonaLanguageResolution(language=env_language, source=env_source or "env")
    return PersonaLanguageResolution(language="en", source="default")


def resolve_persona_language(
    requested_language: object = None,
    *,
    requested_source: object = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve and return only the canonical runtime language value."""
    return resolve_persona_language_with_source(
        requested_language,
        requested_source=requested_source,
        environ=environ,
    ).language


def persona_language_contract(language: object) -> str:
    """Stable system/persona instruction contract for model-facing prompts."""
    resolved = normalize_persona_language(language) or "en"
    display = _LANGUAGE_NAMES.get(resolved, "English")
    return "\n".join(
        [
            "## Runtime persona language contract",
            "",
            f"Effective persona language: {display} ({resolved}).",
            "Write persona narrative, simulated user messages, and persona self-reports in this language.",
            "Keep task instructions, task context, questionnaires, quoted task content, JSON keys, and protocol fields in their task-owned/original form; do not translate or couple task content to this persona-language setting.",
            "If the task explicitly requires another language for task content, follow that task requirement only for the required task content.",
        ]
    )
