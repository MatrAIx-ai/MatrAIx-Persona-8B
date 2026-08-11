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


def test_zh_rendering_uses_chinese_labels_and_values():
    persona = load_persona(
        "persona/datasets/matraix-persona-dev-sample/persona_0018.yaml"
    )
    paragraphs = build_dimension_narrative(persona.dimensions, language="zh")
    text = "\n".join(paragraphs)

    assert "### 身份" in text
    assert "### 语言与沟通" in text
    assert "年龄" in text or "年龄段" in text
    assert "每天" in text


def test_zh_rendering_follows_environment(monkeypatch):
    persona = load_persona(
        "persona/datasets/matraix-persona-dev-sample/persona_0018.yaml"
    )
    monkeypatch.setenv("MATRAIX_PERSONA_LANGUAGE", "zh")

    text = "\n".join(build_dimension_narrative(persona.dimensions))

    assert "### 身份" in text
    assert "每天" in text


def test_zh_unknown_dimension_falls_back_to_english():
    paragraphs = build_dimension_narrative(
        {"zzz_fake_dim": "Fake value"}, language="zh"
    )
    text = "\n".join(paragraphs)

    assert "zzz fake dim" in text
    assert "Fake value" in text


def test_zh_missing_labels_file_returns_empty(tmp_path):
    from matraix import persona_dimension_catalog as cat

    assert cat.load_zh_labels(str(tmp_path / "missing.json")) == {}
    assert cat.resolve_persona_language(None) == "en"
    assert cat.resolve_persona_language("zh") == "zh"
    assert cat.resolve_persona_language("ZH ") == "zh"


def test_zh_template_preserves_task_instruction_verbatim():
    from matraix.agents.persona.templating import (
        PERSONA_INSTRUCTION_TEMPLATE,
        render_persona_template,
        resolve_persona_template,
    )

    persona = load_persona(
        "persona/datasets/matraix-persona-dev-sample/persona_0018.yaml"
    )
    task = "Keep this English task exactly as written."
    text = render_persona_template(
        resolve_persona_template(persona, None, PERSONA_INSTRUCTION_TEMPLATE),
        persona,
        instruction=task,
        language="zh",
    )

    assert "你是 Ethan Brooks。" in text
    assert "## 你是谁" in text
    assert "## Task instruction" in text
    assert task in text
