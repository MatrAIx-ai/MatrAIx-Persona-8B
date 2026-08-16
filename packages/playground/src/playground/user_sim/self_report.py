"""Chatbot-flavored prompt adapter for post-conversation persona self-report."""

from __future__ import annotations

import json
from typing import Any, List

from playground.feedback import questionnaire_from_feedback
from playground.self_report_runtime import (
    SelfReportClient,
    complete_self_report_payload_with_usage,
    resolve_self_report_schema,
)
from playground.types import Persona, PlaygroundTurn, Questionnaire
from playground.user_sim.self_report_contract import (
    SelfReportSchema,
    schema_prompt_block,
)

_FEEDBACK_USER = """You have now FINISHED using {chatbot_label}. Here is the full conversation \
and user-visible structured information from the interaction \
(you = user, {chatbot_label} = assistant):
{transcript}

{instructions}

{schema_block}

Return strict JSON only with no prose before or after the JSON object."""


def _format_exposure_value(value: Any, *, kind: str) -> str:
    if kind == "item_list" and isinstance(value, list):
        parts = []
        for item in value:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or "").strip()
            item_id = str(item.get("itemId") or item.get("id") or "").strip()
            if title and item_id:
                parts.append("{} ({})".format(title, item_id))
            elif title:
                parts.append(title)
            elif item_id:
                parts.append(item_id)
        return ", ".join(parts) or "[]"
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _format_transcript_turns(
    transcript: List[PlaygroundTurn],
    *,
    chatbot_label: str,
) -> str:
    lines: List[str] = []
    for turn in transcript:
        lines.append("you: {}".format(turn.user_message))
        lines.append("{}: {}".format(chatbot_label, turn.assistant_message))
        for item in turn.structured_exposure:
            label = str(item.get("label") or item.get("key") or "Visible detail")
            kind = str(item.get("format") or "text")
            value = _format_exposure_value(item.get("value"), kind=kind)
            if value.strip():
                lines.append("{} visible: {}".format(label, value))
    return "\n".join(lines) if lines else "(empty)"


def final_self_report(
    client: SelfReportClient,
    *,
    system_prompt: str,
    persona: Persona,
    transcript: List[PlaygroundTurn],
    schema: SelfReportSchema | None = None,
    chatbot_label: str = "Chatbot",
) -> Questionnaire:
    questionnaire, _usage = final_self_report_with_usage(
        client,
        system_prompt=system_prompt,
        persona=persona,
        transcript=transcript,
        schema=schema,
        chatbot_label=chatbot_label,
    )
    return questionnaire


def final_self_report_with_usage(
    client: SelfReportClient,
    *,
    system_prompt: str,
    persona: Persona,
    transcript: List[PlaygroundTurn],
    schema: SelfReportSchema | None = None,
    chatbot_label: str = "Chatbot",
) -> tuple[Questionnaire, Any]:
    del persona
    schema = resolve_self_report_schema(schema)
    user = _FEEDBACK_USER.format(
        chatbot_label=chatbot_label,
        transcript=_format_transcript_turns(transcript, chatbot_label=chatbot_label),
        instructions=schema.instructions
        or "Reflect honestly from your own point of view as this persona.",
        schema_block=schema_prompt_block(schema),
    )
    payload, usage = complete_self_report_payload_with_usage(
        client,
        system_prompt=system_prompt,
        user_prompt=user,
        schema=schema,
    )
    return questionnaire_from_feedback(payload), usage
