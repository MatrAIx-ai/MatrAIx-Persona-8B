"""Machine-readable self-report contract for interactive tasks."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Tuple


@dataclass(frozen=True)
class SelfReportField:
    key: str
    prompt: str
    kind: str = "string"
    required: bool = True
    minimum: int | None = None
    maximum: int | None = None
    choices: Tuple[str, ...] = ()
    # Key of the field this textual field explains. When set, reporting groups
    # this explanation by that target field (no heuristic axis guessing).
    explains: str | None = None


@dataclass(frozen=True)
class SelfReportSchema:
    artifact_name: str = "user_feedback.json"
    instructions: str = ""
    fields: Tuple[SelfReportField, ...] = field(default_factory=tuple)


DEFAULT_CHATBOT_SELF_REPORT_SCHEMA = SelfReportSchema(
    artifact_name="user_feedback.json",
    instructions=(
        "Reflect honestly from your own point of view as this persona. "
        "Use only what you actually saw in the interaction."
    ),
    fields=(
        SelfReportField(
            key="needConstraintSatisfaction",
            prompt="How well did the chatbot satisfy your core need or constraints?",
            kind="enum",
            choices=("yes", "partially", "no"),
        ),
        SelfReportField(
            key="personalPreferenceSatisfaction",
            prompt="How well did the chatbot match your personal preferences or taste?",
            kind="enum",
            choices=("yes", "partially", "no"),
        ),
        SelfReportField(
            key="overallExperienceRating",
            prompt="Overall, how would you rate the experience from 1 to 10?",
            kind="integer",
            minimum=1,
            maximum=10,
        ),
        SelfReportField(
            key="reason",
            prompt="Briefly explain the rating in your own voice.",
            explains="overallExperienceRating",
        ),
        SelfReportField(
            key="askedUsefulClarificationQuestions",
            prompt="Did the chatbot ask useful clarification questions?",
            kind="boolean",
        ),
        SelfReportField(
            key="clarifyingNotes",
            prompt="Which clarifying questions helped, or why they did not.",
            explains="askedUsefulClarificationQuestions",
        ),
        SelfReportField(
            key="trustLevel",
            prompt="Optional: how much did you trust the chatbot on a scale from 1 to 10?",
            kind="integer",
            minimum=1,
            maximum=10,
            required=False,
        ),
        SelfReportField(
            key="feltUnderstood",
            prompt="Optional: did you feel understood by the chatbot?",
            kind="boolean",
            required=False,
        ),
    ),
)


def schema_prompt_block(schema: SelfReportSchema) -> str:
    lines = [
        "Return one JSON object with these fields:",
    ]
    for schema_field in schema.fields:
        details = []
        if schema_field.kind == "integer":
            bounds = []
            if schema_field.minimum is not None:
                bounds.append("min {}".format(schema_field.minimum))
            if schema_field.maximum is not None:
                bounds.append("max {}".format(schema_field.maximum))
            if bounds:
                details.append(", ".join(bounds))
        elif schema_field.kind == "enum" and schema_field.choices:
            details.append("choices: {}".format(", ".join(schema_field.choices)))
        details.append("required" if schema_field.required else "optional")
        lines.append(
            '- `{}`: {} ({})'.format(
                schema_field.key,
                schema_field.prompt,
                "; ".join(details),
            )
        )
    return "\n".join(lines)


_LEADING_WORD = re.compile(r"[a-z0-9]+")
_NUMBER = r"-?\d+(?:\.\d+)?"
_SCORE_OUT_OF = re.compile(r"\s*({0})\s*(?:/|out of)\s*{0}\s*".format(_NUMBER), re.IGNORECASE)


def _leading_word(text: str) -> str:
    """First word of an answer such as ``"Yes."`` or ``"no, it did not"``."""
    match = _LEADING_WORD.match(text.strip().lower())
    return match.group(0) if match else ""


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = _leading_word(str(value if value is not None else ""))
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0"}:
        return False
    return default


def _parse_number(value: Any) -> float | None:
    """Number from ``8``, ``"8"``, ``"8/10"``, ``"8 out of 10"`` or ``"rating: 8"``."""
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    text = str(value if value is not None else "")
    scored = _SCORE_OUT_OF.fullmatch(text)
    if scored:
        return float(scored.group(1))
    numbers = re.findall(_NUMBER, text)
    if len(numbers) == 1:
        return float(numbers[0])
    return None


def _match_choice(text: str, choices: Tuple[str, ...]) -> str | None:
    """Choice for an answer like ``"No."`` or ``"partially, it missed my budget"``."""
    cleaned = text.strip().lower()
    if cleaned in choices:
        return cleaned
    trimmed = cleaned.rstrip(".!?;:")
    if trimmed in choices:
        return trimmed
    # Longest choice the answer starts with, followed by a non-word character.
    for choice in sorted(choices, key=len, reverse=True):
        if cleaned.startswith(choice) and not cleaned[len(choice) : len(choice) + 1].isalnum():
            return choice
    return None


def _coerce_int(
    value: Any,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    if value in (None, ""):
        return None
    parsed = _parse_number(value)
    if parsed is None or not math.isfinite(parsed):
        return None
    number = int(round(parsed))
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def coerce_self_report_payload(
    raw: Dict[str, Any],
    schema: SelfReportSchema,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for schema_field in schema.fields:
        value = raw.get(schema_field.key)
        if schema_field.kind == "integer":
            coerced = _coerce_int(
                value, minimum=schema_field.minimum, maximum=schema_field.maximum
            )
            if coerced is not None or schema_field.required:
                payload[schema_field.key] = coerced if coerced is not None else (
                    schema_field.minimum if schema_field.minimum is not None else 0
                )
        elif schema_field.kind == "boolean":
            payload[schema_field.key] = _coerce_bool(value, default=False)
        elif schema_field.kind == "enum":
            text = str(value if value is not None else "").strip().lower()
            choices = tuple(choice.lower() for choice in schema_field.choices)
            matched = _match_choice(text, choices)
            if matched is not None:
                payload[schema_field.key] = matched
            elif (
                _leading_word(text) in {"true", "false", "yes", "no", "1", "0"}
                and "yes" in choices
                and "no" in choices
            ):
                payload[schema_field.key] = "yes" if _coerce_bool(text, default=False) else "no"
            elif schema_field.required and schema_field.choices:
                payload[schema_field.key] = schema_field.choices[0]
            elif text:
                payload[schema_field.key] = text
        else:
            text = str(value or "").strip()
            if text or schema_field.required:
                payload[schema_field.key] = text
    return payload


def schema_to_public_dict(schema: SelfReportSchema) -> Dict[str, Any]:
    """Serialize a self-report schema for debrief / UI (task-agnostic)."""
    return {
        "artifactName": schema.artifact_name,
        "instructions": schema.instructions,
        "fields": [
            {
                "key": schema_field.key,
                "prompt": schema_field.prompt,
                "kind": schema_field.kind,
                "required": schema_field.required,
                "minimum": schema_field.minimum,
                "maximum": schema_field.maximum,
                "choices": list(schema_field.choices),
                "explains": schema_field.explains,
            }
            for schema_field in schema.fields
        ],
    }


def field_keys(schema: SelfReportSchema) -> Tuple[str, ...]:
    return tuple(schema_field.key for schema_field in schema.fields)


def schema_has_field(schema: SelfReportSchema, key: str) -> bool:
    return key in set(field_keys(schema))


def merge_extra_fields(
    payload: Dict[str, Any],
    *,
    exclude: Iterable[str],
) -> Dict[str, Any]:
    excluded = set(exclude)
    return {key: value for key, value in payload.items() if key not in excluded}
