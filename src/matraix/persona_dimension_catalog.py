"""Render persona YAML dimensions into agent profile text via dimensions.json.

Covers the full ~1290-dim schema adaptively:
- skip null / empty / placeholder values
- skip schema ``defaultValue`` (uninformative)
- skip external/source dump dimensions
- group remaining attrs into taxonomy sections
- soft-truncate low-priority sections when over a char budget
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_CATALOG_PATH = "persona/schema/dimensions.json"

# Soft budget for the persona block inside agent system/instruction prompts.
# Default is unlimited — full non-null / non-default attributes are always kept
# so task append never forces persona truncation. Override with
# MATRAIX_PERSONA_PROFILE_MAX_CHARS only for emergency local debugging.
DEFAULT_PROFILE_MAX_CHARS: int | None = None

_NULLISH = frozenset(
    {
        "",
        "none",
        "n/a",
        "na",
        "null",
        "undefined",
        "none notable",
        "not applicable",
        "prefer not to say",
        "no coding activity",
        "not a developer",
        "no interest",
        "unknown",
    }
)

_EXCLUDE_PREFIXES = (
    "apple_primex_dimension_",
    "personahub_dimension_",
    "oasis_dimension_",
    "horizonbench_dimension_",
    "wildchat_",
    "pandora_",
    "personachat_",
    "synthetic_persona_chat_dimension_",
    "nemotron_",
    "wiki_",
)

_EXCLUDE_CATEGORY_PREFIXES = ("External",)

# Ordered sections — earlier = higher priority when soft-truncating.
# Each entry: (heading, category matchers). A matcher matches if category == it
# or category.startswith(it) when it ends with ":".
_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Identity",
        (
            "Demographic: Core",
            "Demographic: Cultural",
            "Demographic: Family",
            "Demographic: Life Events",
        ),
    ),
    (
        "Career & education",
        (
            "Professional: Career",
            "Professional: Industry",
            "Learning: Academic",
            "Learning: Style",
        ),
    ),
    (
        "Language & communication",
        ("Linguistic: Language", "Linguistic: Communication"),
    ),
    (
        "Personality & values",
        (
            "Personality: Big Five",
            "Personality: Character",
            "Personality: MBTI",
            "Personality: Relationships",
            "Values & Motivation",
            "Risk & Decision",
        ),
    ),
    (
        "Current interaction state",
        ("State: Emotional", "Behavior: Time", "Behavior: Work"),
    ),
    ("Worldview", ("Worldview: Beliefs",)),
    (
        "Interests",
        (
            "Interests: Topics",
            "Interests: Hobbies",
            "Interests: Media",
            "Interests: Culture",
            "Interests: Sports",
            "Interests: Food",
        ),
    ),
    (
        "Skills & expertise",
        (
            "Expertise: Domains",
            "Expertise: Skills",
            "Skills: Tools",
            "Skills: Programming",
        ),
    ),
    (
        "Lifestyle & health",
        (
            "Health: Physical",
            "Health: Fitness",
            "Health: Lifestyle",
            "Behavior: Preferences",
            "Behavior: Habits",
        ),
    ),
    ("Developer & AI", ("Developer:",)),
)

# Interaction-session dims always surface in "Current interaction state"
# even if category metadata drifts.
_STATE_IDS = frozenset(
    {
        "emotional_state",
        "intent",
        "query_complexity",
        "expertise_gap",
        "tone_expected",
        "trust_level",
        "safety_sensitivity",
        "time_pressure",
        "prior_context",
        "device_context",
        "modality_pref",
        "accessibility_needs",
    }
)

PRIMARY_LANGUAGE_OUTPUT_INSTRUCTION = (
    "Default written language: use your primary language for outputs."
)


def _primary_language_output_instruction(
    dimensions: dict[str, Any],
) -> str | None:
    primary_language = _dim_value(dimensions, "primary_language")
    if primary_language is None:
        return None
    return PRIMARY_LANGUAGE_OUTPUT_INSTRUCTION


@lru_cache(maxsize=4)
def load_dimension_catalog(catalog_path: str) -> dict[str, Any]:
    path = Path(catalog_path)
    if not path.is_file():
        path = _repo_root() / catalog_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    by_id: dict[str, dict[str, Any]] = {}
    for row in payload.get("dimensions") or []:
        if isinstance(row, dict) and row.get("id"):
            by_id[str(row["id"])] = row
    return {
        "schema_version": payload.get("schemaVersion"),
        "by_id": by_id,
        "probe_fields": payload.get("personaYamlProbeFields") or {},
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def dimension_meta(
    dimension_id: str, *, catalog_path: str = DEFAULT_CATALOG_PATH
) -> dict[str, Any] | None:
    return load_dimension_catalog(catalog_path)["by_id"].get(dimension_id)


def probe_path_for_dimension(
    dimension_id: str, *, catalog_path: str = DEFAULT_CATALOG_PATH
) -> str:
    catalog = load_dimension_catalog(catalog_path)
    for path, meta in catalog["probe_fields"].items():
        if isinstance(meta, dict) and meta.get("dimensionId") == dimension_id:
            return str(path)
    return f"dimensions.{dimension_id}"


def values_for_dimension(
    dimension_id: str, *, catalog_path: str = DEFAULT_CATALOG_PATH
) -> list[str]:
    meta = dimension_meta(dimension_id, catalog_path=catalog_path)
    if not meta:
        return []
    return [str(v) for v in meta.get("values") or []]


def _dim_value(dimensions: dict[str, Any], key: str) -> str | None:
    raw = dimensions.get(key)
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        parts = [str(item).strip() for item in raw if str(item).strip()]
        text = ", ".join(parts)
    else:
        text = str(raw).strip()
    if not text or text.lower() in _NULLISH:
        return None
    return text


def _is_default(value: Any, default: Any) -> bool:
    if default is None:
        return False
    if isinstance(default, list):
        return value in default
    return value == default


def _should_skip_dim(dim_id: str, meta: dict[str, Any] | None) -> bool:
    if dim_id.startswith(_EXCLUDE_PREFIXES):
        return True
    if not meta:
        return False
    category = str(meta.get("category") or "")
    return any(category.startswith(prefix) for prefix in _EXCLUDE_CATEGORY_PREFIXES)


def _category_matches(category: str, matchers: tuple[str, ...]) -> bool:
    for matcher in matchers:
        if matcher.endswith(":"):
            if category.startswith(matcher):
                return True
        elif category == matcher or category.startswith(f"{matcher}:"):
            return True
    return False


def _section_for(dim_id: str, category: str) -> str:
    if dim_id in _STATE_IDS:
        return "Current interaction state"
    for heading, matchers in _SECTIONS:
        if _category_matches(category, matchers):
            return heading
    return "Other attributes"


def _label_for(dim_id: str, meta: dict[str, Any] | None) -> str:
    if meta and meta.get("label"):
        return str(meta["label"]).strip()
    return dim_id.replace("_", " ")


def _format_section(heading: str, items: list[tuple[str, str]]) -> str:
    lines = [f"### {heading}"]
    for label, value in items:
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def resolve_profile_max_chars(max_chars: int | None = None) -> int | None:
    """Return char budget for persona profile text (None = unlimited)."""
    if max_chars is not None:
        return None if max_chars <= 0 else max_chars
    raw = os.environ.get("MATRAIX_PERSONA_PROFILE_MAX_CHARS", "").strip()
    if raw:
        if raw.lower() in {"0", "none", "unlimited", "-1"}:
            return None
        try:
            value = int(raw)
        except ValueError:
            return DEFAULT_PROFILE_MAX_CHARS
        return None if value <= 0 else value
    return DEFAULT_PROFILE_MAX_CHARS


def collect_dimension_items(
    dimensions: dict[str, Any],
    *,
    catalog_path: str = DEFAULT_CATALOG_PATH,
) -> dict[str, list[tuple[str, str, str]]]:
    """Group keepable dims into section -> [(dim_id, label, value), ...]."""
    catalog = load_dimension_catalog(catalog_path)
    by_id: dict[str, dict[str, Any]] = catalog["by_id"]
    grouped: dict[str, list[tuple[str, str, str]]] = {h: [] for h, _ in _SECTIONS}
    grouped["Other attributes"] = []

    # Stable order: known catalog ids first (schema order), then extras.
    ordered_ids = [dim_id for dim_id in by_id if dim_id in dimensions]
    ordered_ids.extend(dim_id for dim_id in dimensions if dim_id not in by_id)

    for dim_id in ordered_ids:
        meta = by_id.get(dim_id)
        if _should_skip_dim(dim_id, meta):
            continue
        text = _dim_value(dimensions, dim_id)
        if text is None:
            continue
        raw = dimensions.get(dim_id)
        if meta and _is_default(raw, meta.get("defaultValue")):
            continue
        # Also skip when string form equals stringified default.
        if meta and _is_default(text, meta.get("defaultValue")):
            continue

        category = str((meta or {}).get("category") or "")
        heading = _section_for(dim_id, category)
        label = _label_for(dim_id, meta)
        grouped.setdefault(heading, []).append((dim_id, label, text))

    return {key: value for key, value in grouped.items() if value}


def build_dimension_narrative(
    dimensions: dict[str, Any],
    *,
    catalog_path: str = DEFAULT_CATALOG_PATH,
    max_chars: int | None = None,
) -> list[str]:
    """Schema-driven profile sections for agent roleplay (full 1290, adaptive).

    Returns a list of markdown section blocks for the Jinja persona macros.
    """
    budget = resolve_profile_max_chars(max_chars)
    grouped = collect_dimension_items(dimensions, catalog_path=catalog_path)
    if not grouped:
        return []

    section_order = [heading for heading, _ in _SECTIONS] + ["Other attributes"]
    rendered: list[str] = []
    omitted = 0
    used_chars = 0

    for heading in section_order:
        items = grouped.get(heading) or []
        if not items:
            continue
        # Prefer keeping high-priority sections intact; trim from the end of
        # lower-priority sections when over budget.
        if budget is not None:
            # Reserve room for an omission note.
            remaining = budget - used_chars - 80
            if remaining <= 0:
                omitted += len(items)
                continue
            # Keep a contiguous prefix so section ordering stays stable.
            fitted: list[tuple[str, str]] = []
            probe = len(f"### {heading}\n")
            for index, (_dim_id, label, value) in enumerate(items):
                line_len = len(f"- {label}: {value}\n")
                if probe + line_len > remaining:
                    omitted += len(items) - index
                    break
                fitted.append((label, value))
                probe += line_len
            if not fitted:
                omitted += len(items)
                continue
            block = _format_section(heading, fitted)
        else:
            block = _format_section(
                heading, [(label, value) for _dim_id, label, value in items]
            )
            required_instruction = (
                _primary_language_output_instruction(dimensions)
                if heading == "Language & communication"
                else None
            )
            if required_instruction and required_instruction not in block:
                block = f"{block}\n{required_instruction}"

        rendered.append(block)
        used_chars += len(block) + 2  # blank line between sections

    if omitted > 0:
        rendered.append(
            f"_…and {omitted} more attributes omitted to fit the context budget._"
        )

    return rendered


def build_template_context_extras(
    dimensions: dict[str, Any],
    *,
    catalog_path: str = DEFAULT_CATALOG_PATH,
    max_chars: int | None = None,
) -> dict[str, Any]:
    return {
        "dimension_profile_narrative": build_dimension_narrative(
            dimensions, catalog_path=catalog_path, max_chars=max_chars
        ),
        "dimension_catalog_path": catalog_path,
    }
