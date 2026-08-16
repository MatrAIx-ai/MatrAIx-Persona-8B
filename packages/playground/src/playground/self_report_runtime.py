"""Shared self-report completion helpers for interactive task adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Protocol

from playground.feedback import questionnaire_from_feedback
from playground.openai_client import coerce_json
from playground.types import Questionnaire
from playground.user_sim.self_report_contract import (
    DEFAULT_CHATBOT_SELF_REPORT_SCHEMA,
    SelfReportSchema,
    coerce_self_report_payload,
)


class SelfReportClient(Protocol):
    def complete_json(self, system: str, user: str) -> Dict[str, Any]: ...


def resolve_self_report_schema(schema: SelfReportSchema | None) -> SelfReportSchema:
    return schema or DEFAULT_CHATBOT_SELF_REPORT_SCHEMA


def complete_self_report_payload(
    client: SelfReportClient | Any,
    *,
    system_prompt: str,
    user_prompt: str,
    schema: SelfReportSchema | None = None,
) -> Dict[str, Any]:
    resolved_schema = resolve_self_report_schema(schema)
    raw, _usage = complete_self_report_payload_with_usage(
        client,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=resolved_schema,
    )
    return raw


def complete_self_report_payload_with_usage(
    client: SelfReportClient | Any,
    *,
    system_prompt: str,
    user_prompt: str,
    schema: SelfReportSchema | None = None,
) -> tuple[Dict[str, Any], Any]:
    """Return ``(payload, LlmUsage | None)`` for cost rollup callers."""
    resolved_schema = resolve_self_report_schema(schema)
    usage = None
    if hasattr(client, "complete_json_with_usage"):
        completion = client.complete_json_with_usage(system_prompt, user_prompt)
        raw = completion.data
        usage = completion.usage
    elif hasattr(client, "complete_json"):
        raw = client.complete_json(system_prompt, user_prompt)
    else:
        raw = coerce_json(str(client))
    return coerce_self_report_payload(raw, resolved_schema), usage


def complete_self_report_questionnaire(
    client: SelfReportClient | Any,
    *,
    system_prompt: str,
    user_prompt: str,
    schema: SelfReportSchema | None = None,
) -> Questionnaire:
    payload = complete_self_report_payload(
        client,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=schema,
    )
    return questionnaire_from_feedback(payload)


def write_self_report_artifact(payload: Dict[str, Any], *, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
