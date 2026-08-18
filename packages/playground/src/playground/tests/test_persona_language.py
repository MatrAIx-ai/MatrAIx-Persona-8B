from __future__ import annotations

from pathlib import Path

import pytest

from matraix.agents.persona.loader import load_persona
from matraix.agents.persona.templating import (
    PERSONA_INSTRUCTION_TEMPLATE,
    render_persona_template,
    resolve_persona_template,
)
from matraix.launch_env import canonicalize_persona_language
from playground.persona_language import (
    PERSONA_LANGUAGE_SOURCES,
    SUPPORTED_PERSONA_LANGUAGES,
    normalize_persona_language,
    persona_language_contract,
    resolve_persona_language_with_source,
)


@pytest.mark.parametrize("source", ["follow_ui", "explicit", "env", "default"])
def test_direct_agent_language_precedes_environment_and_preserves_source(
    source: str,
) -> None:
    resolution = resolve_persona_language_with_source(
        "zh-CN",
        requested_source=source,
        environ={
            "MATRIX_PERSONA_LANGUAGE": "ja",
            "MATRIX_PERSONA_LANGUAGE_SOURCE": "cli",
        },
    )
    assert resolution.language == "zh-Hans"
    assert resolution.source == source


def test_api_agent_follow_ui_source_is_preserved() -> None:
    resolution = resolve_persona_language_with_source(
        "zh-CN",
        requested_source="follow_ui",
        environ={"MATRIX_PERSONA_LANGUAGE": "ja"},
    )
    assert resolution.language == "zh-Hans"
    assert resolution.source == "follow_ui"


def test_cli_source_companion_is_explicit() -> None:
    resolution = resolve_persona_language_with_source(
        environ={
            "MATRIX_PERSONA_LANGUAGE": "zh",
            "MATRIX_PERSONA_LANGUAGE_SOURCE": "explicit",
        }
    )
    assert resolution.language == "zh-Hans"
    assert resolution.source == "explicit"


def test_unknown_env_source_is_derived_as_env() -> None:
    resolution = resolve_persona_language_with_source(
        environ={
            "MATRIX_PERSONA_LANGUAGE": "pt",
            "MATRIX_PERSONA_LANGUAGE_SOURCE": "cli",
        }
    )
    assert resolution.language == "pt-BR"
    assert resolution.source == "env"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("en", "en"),
        ("en-US", "en"),
        ("ko", "ko"),
        ("ko-KR", "ko"),
        ("zh", "zh-Hans"),
        ("zh-CN", "zh-Hans"),
        ("zh-Hans-CN", "zh-Hans"),
        ("zh-Hant", "zh-Hant"),
        ("zh-TW", "zh-Hant"),
        ("zh-HK", "zh-Hant"),
        ("ja", "ja"),
        ("ja-JP", "ja"),
        ("pt", "pt-BR"),
        ("pt-BR", "pt-BR"),
        ("es", "es"),
        ("es-ES", "es"),
        ("es-419", "es"),
    ],
)
def test_canonical_tags_and_legacy_aliases_share_one_resolver(
    value: str, expected: str
) -> None:
    assert normalize_persona_language(value) == expected
    assert canonicalize_persona_language(value) == expected


def test_supported_language_and_source_sets_are_canonical() -> None:
    assert SUPPORTED_PERSONA_LANGUAGES == {
        "en",
        "ko",
        "zh-Hans",
        "zh-Hant",
        "ja",
        "pt-BR",
        "es",
    }
    assert PERSONA_LANGUAGE_SOURCES == {
        "follow_ui",
        "explicit",
        "env",
        "default",
    }


@pytest.mark.parametrize("value", [None, "", "fr", "pt-PT", "zh-XX"])
def test_unknown_languages_are_not_silently_relabelled(value: object) -> None:
    assert normalize_persona_language(value) is None


def test_plain_env_and_default_provenance() -> None:
    env_resolution = resolve_persona_language_with_source(
        environ={"MATRIX_PERSONA_LANGUAGE": "pt-BR"}
    )
    assert env_resolution.language == "pt-BR"
    assert env_resolution.source == "env"

    default_resolution = resolve_persona_language_with_source(environ={})
    assert default_resolution.language == "en"
    assert default_resolution.source == "default"


def test_paired_environment_source_is_preserved() -> None:
    resolution = resolve_persona_language_with_source(
        environ={
            "MATRIX_PERSONA_LANGUAGE": "ja-JP",
            "MATRIX_PERSONA_LANGUAGE_SOURCE": "follow_ui",
        }
    )
    assert resolution.language == "ja"
    assert resolution.source == "follow_ui"


def test_contract_keeps_task_content_outside_persona_language_scope() -> None:
    contract = persona_language_contract("zh")
    assert "Simplified Chinese (zh-Hans)" in contract
    assert "do not translate" in contract
    assert "JSON keys" in contract


def test_single_channel_contract_stays_in_identity_before_task_body() -> None:
    repo_root = Path(__file__).resolve().parents[5]
    persona = load_persona(
        repo_root / "persona/datasets/matraix-persona-dev-sample/persona_0001.yaml"
    )
    template = resolve_persona_template(
        persona,
        None,
        PERSONA_INSTRUCTION_TEMPLATE,
    )
    rendered = render_persona_template(
        template,
        persona,
        instruction="TASK_BODY_SENTINEL",
        language="zh-Hans",
    )

    assert rendered.index("## Runtime persona language contract") < rendered.index(
        "## Task instruction"
    )
    assert "TASK_BODY_SENTINEL" in rendered


def test_custom_template_fallback_contract_precedes_task_body(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[5]
    persona = load_persona(
        repo_root / "persona/datasets/matraix-persona-dev-sample/persona_0001.yaml"
    )
    template = tmp_path / "custom_persona.md.j2"
    template.write_text(
        "Persona: {{ display_name }}\n\nTask: {{ instruction }}",
        encoding="utf-8",
    )

    rendered = render_persona_template(
        template,
        persona,
        instruction="TASK_BODY_SENTINEL",
        language="zh-Hans",
    )

    assert rendered.index("## Runtime persona language contract") < rendered.index(
        "TASK_BODY_SENTINEL"
    )
