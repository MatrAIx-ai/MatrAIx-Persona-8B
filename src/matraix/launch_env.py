"""Shared Harbor launch environment for Playground and ``matraix run``.

Both launchers start ``harbor run`` processes that import monorepo packages
(``backend``, ``matraix.agents``, ``playground``, …). Keeping the required
``PYTHONPATH`` entries here prevents the GUI and CLI from drifting apart.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

# Relative to the repository root; "." is the root itself. Order matters:
# earlier entries win on import conflicts.
REQUIRED_PYTHONPATH_SUBDIRS: tuple[str, ...] = (
    ".",
    "src",
    "environment/runtime",
    "environment/agents",
    "packages/playground/src",
    "application/playground",
)

_REPO_ROOT_MARKER = Path("environment") / "runtime" / "harbor"

# Runtime/persona language is deliberately carried on MATRIX_* fields. Remote
# dispatch already admits the MATRIX_* namespace, so this feature does not
# need to change remote-runner environment policy.
PERSONA_LANGUAGE_ENV = "MATRIX_PERSONA_LANGUAGE"
PERSONA_LANGUAGE_SOURCE_ENV = "MATRIX_PERSONA_LANGUAGE_SOURCE"
# CLI-only authority marker. The normal language/source pair remains the
# persisted runtime contract; this field only establishes override precedence.
PERSONA_LANGUAGE_OVERRIDE_ENV = "MATRIX_PERSONA_LANGUAGE_OVERRIDE"
PERSONA_LANGUAGE_TOKENS: tuple[str, ...] = (
    "en",
    "ko",
    "zh-Hans",
    "zh-Hant",
    "ja",
    "pt-BR",
    "es",
)
PERSONA_LANGUAGE_SOURCE_TOKENS: tuple[str, ...] = ("follow_ui", "explicit")

_PERSONA_LANGUAGE_ALIASES: dict[str, str] = {
    "en": "en",
    "en-us": "en",
    "en-gb": "en",
    "ko": "ko",
    "ko-kr": "ko",
    "zh": "zh-Hans",
    "zh-cn": "zh-Hans",
    "zh-hans": "zh-Hans",
    "zh-hans-cn": "zh-Hans",
    "zh-tw": "zh-Hant",
    "zh-hk": "zh-Hant",
    "zh-hant": "zh-Hant",
    "ja": "ja",
    "ja-jp": "ja",
    "pt": "pt-BR",
    "pt-br": "pt-BR",
    "es": "es",
    "es-es": "es",
    "es-419": "es",
}


def canonicalize_persona_language(language: str | None) -> str | None:
    """Return the canonical runtime token, or ``None`` if unsupported."""
    if language is None:
        return None
    candidate = str(language).strip().replace("_", "-").casefold()
    return _PERSONA_LANGUAGE_ALIASES.get(candidate)


def normalize_persona_language(language: str | None) -> str | None:
    """Validate and return a canonical runtime language token."""
    if language is None:
        return None
    canonical = canonicalize_persona_language(language)
    if canonical is None:
        supported = ", ".join(PERSONA_LANGUAGE_TOKENS)
        raise ValueError(
            f"persona language must be one of: {supported}; received {language!r}"
        )
    return canonical


def normalize_persona_language_source(source: str | None) -> str | None:
    """Validate the caller-owned language provenance contract."""
    if source is None:
        return None
    normalized = str(source).strip().casefold()
    if normalized in PERSONA_LANGUAGE_SOURCE_TOKENS:
        return normalized
    supported = ", ".join(PERSONA_LANGUAGE_SOURCE_TOKENS)
    raise ValueError(
        f"persona language source must be one of: {supported}; received {source!r}"
    )


def build_persona_language_env(language: str | None) -> dict[str, str]:
    """Build the explicit runtime-language env contract for a CLI override."""
    normalized = normalize_persona_language(language)
    if normalized is None:
        return {}
    return {
        PERSONA_LANGUAGE_ENV: normalized,
        PERSONA_LANGUAGE_SOURCE_ENV: "explicit",
    }


def build_persona_language_override_env(language: str | None) -> dict[str, str]:
    """Build the highest-precedence language contract for a CLI override."""
    env = build_persona_language_env(language)
    if env:
        env[PERSONA_LANGUAGE_OVERRIDE_ENV] = env[PERSONA_LANGUAGE_ENV]
    return env


def required_pythonpath_entries(repo_root: Path | str) -> list[str]:
    """Absolute ``PYTHONPATH`` entries every Harbor launcher must inject."""
    root = Path(repo_root)
    return [
        str(root) if subdir == "." else str(root / subdir)
        for subdir in REQUIRED_PYTHONPATH_SUBDIRS
    ]


def merge_pythonpath(existing: str | None, repo_root: Path | str) -> str:
    """Prepend the required entries to ``existing``, deduplicated."""
    entries = [entry for entry in (existing or "").split(os.pathsep) if entry]
    for path in reversed(required_pythonpath_entries(repo_root)):
        if path not in entries:
            entries.insert(0, path)
    return os.pathsep.join(entries)


def build_launch_env(
    repo_root: Path | str,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return ``base_env`` (default: ``os.environ``) with ``PYTHONPATH`` set.

    Pass ``base_env={}`` for remote dispatch payloads that must not inherit
    the local process environment.
    """
    env = dict(os.environ if base_env is None else base_env)
    env["PYTHONPATH"] = merge_pythonpath(env.get("PYTHONPATH"), repo_root)
    return env


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default: cwd) to the MatrAIx repository root."""
    origin = (start or Path.cwd()).resolve()
    for candidate in (origin, *origin.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / _REPO_ROOT_MARKER
        ).is_dir():
            return candidate
    # Editable installs place this module at <root>/src/matraix/launch_env.py.
    fallback = Path(__file__).resolve().parents[2]
    if (fallback / _REPO_ROOT_MARKER).is_dir():
        return fallback
    raise FileNotFoundError(
        "Could not locate the MatrAIx repository root from "
        f"{origin}. Run inside a repository checkout or pass --repo-root."
    )
