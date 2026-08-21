"""Schema-driven persona narrative covers non-default dims and skips nulls."""

from __future__ import annotations

from matraix.agents.persona.loader import load_persona
from matraix.persona_agent_context import (
    RECOMMENDED_MAX_INPUT_TOKENS,
    apply_persona_context_to_agent_spec,
    persona_llm_model_info,
)
from matraix.persona_dimension_catalog import (
    build_dimension_narrative,
    collect_dimension_items,
)


def test_communication_style_uses_label_value_pairs():
    persona = load_persona(
        "persona/datasets/matraix-persona-dev-sample/persona_0018.yaml"
    )
    paragraphs = build_dimension_narrative(persona.dimensions)
    joined = "\n".join(paragraphs).lower()

    assert "verbosity: concise" in joined
    assert "formality: neutral" in joined
    assert "visual vs verbal thinking: mixed" in joined


def test_primary_language_adds_output_instruction_to_language_section():
    paragraphs = build_dimension_narrative({"primary_language": "Mandarin"})
    text = "\n\n".join(paragraphs)

    assert "### Language & communication" in text
    assert (
        "Default written language: use your primary language for outputs."
        in text
    )
    assert text.index("### Language & communication") < text.index(
        "Default written language: use your primary language for outputs."
    )


def test_missing_primary_language_does_not_add_output_instruction():
    paragraphs = build_dimension_narrative({"primary_language": None})
    text = "\n\n".join(paragraphs)

    assert (
        "Default written language: use your primary language for outputs."
        not in text
    )


def test_full_schema_render_skips_null_and_default_without_truncation():
    persona = load_persona(
        "persona/datasets/matraix-persona-dev-sample/persona_0182.yaml"
    )
    grouped = collect_dimension_items(persona.dimensions)
    all_items = [item for items in grouped.values() for item in items]
    assert len(all_items) > 100

    values = {value.lower() for _dim_id, _label, value in all_items}
    assert "none" not in values
    assert "n/a" not in values
    assert "not applicable" not in values
    assert "no coding activity" not in values

    paragraphs = build_dimension_narrative(persona.dimensions)
    text = "\n\n".join(paragraphs)
    assert "### Identity" in text
    assert "### Language & communication" in text
    assert "omitted to fit the context budget" not in text
    assert any(
        heading in text
        for heading in (
            "### Interests",
            "### Skills & expertise",
            "### Personality & values",
        )
    )


def test_explicit_budget_still_omits_when_requested():
    persona = load_persona(
        "persona/datasets/matraix-persona-dev-sample/persona_0182.yaml"
    )
    tight = build_dimension_narrative(persona.dimensions, max_chars=2_500)
    full = build_dimension_narrative(persona.dimensions)
    tight_text = "\n\n".join(tight)
    full_text = "\n\n".join(full)

    assert len(tight_text) < len(full_text)
    assert "omitted to fit the context budget" in tight_text
    assert "### Identity" in tight_text


def test_coding_style_dimensions_appear_in_skills_section():
    # Preserve #334: code_* dims must reach the agent narrative (schema sections).
    dims = {
        "age_bracket": "25-34",
        "code_comment_style": "Extensive inline comments",
        "code_naming_verbosity": "Single-letter names",
        "code_summary_documentation": "Never includes TLDR",
    }
    paragraphs = build_dimension_narrative(dims)
    text = "\n".join(paragraphs).lower()
    assert "### skills & expertise" in text
    assert "code comment style: extensive inline comments" in text
    assert "code naming verbosity: single-letter names" in text
    assert "code summary/tldr documentation: never includes tldr" in text


def test_persona_agent_context_floor():
    info = persona_llm_model_info("anthropic/claude-sonnet-4-5")
    assert info["max_input_tokens"] >= RECOMMENDED_MAX_INPUT_TOKENS
    agent = apply_persona_context_to_agent_spec(
        {
            "name": "persona-openhands-sdk",
            "model_name": "anthropic/claude-sonnet-4-5",
            "kwargs": {"persona_path": "x.yaml"},
        }
    )
    assert agent["kwargs"]["model_info"]["max_input_tokens"] >= RECOMMENDED_MAX_INPUT_TOKENS
