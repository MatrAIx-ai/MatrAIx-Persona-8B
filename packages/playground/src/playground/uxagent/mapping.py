from __future__ import annotations

from copy import deepcopy

from typing import Any, Mapping

from playground.chatbot_task_config import ChatbotTaskConfig
from playground.uxagent.models import VoiceLabAgentChatRequest, VoiceLabPersonaSessionRequest


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _without_empty(values: Mapping[str, object]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in (None, "", [], {})}


def build_persona_session_request(
    *, persona: object, runtime: ChatbotTaskConfig, session_id: str
) -> VoiceLabPersonaSessionRequest:
    data = _mapping(getattr(persona, "data", {}))
    communication = _mapping(getattr(persona, "communication", {}))
    psychology = _mapping(getattr(persona, "psychology", {}))
    preferences = _mapping(getattr(persona, "preferences", {}))
    persona_context = _mapping(data.get("context"))
    runtime_context = _mapping(runtime.protocol.static_body.get("runtimeContext"))
    driver = _without_empty(
        {
            "name": _text(getattr(persona, "display_name", None)),
            "persona": _text(getattr(persona, "summary", None))
            or _text(getattr(persona, "system_prompt", None)),
            "communicationStyle": _text(communication.get("style")),
            "traits": deepcopy(psychology.get("traits")),
            "preferences": deepcopy(preferences),
        }
    )
    context = _without_empty(
        {
            "mood": persona_context.get("mood"),
            "tripPurpose": persona_context.get("tripPurpose"),
            "stressLevel": persona_context.get("stressLevel"),
            "fatigueLevel": persona_context.get("fatigueLevel"),
            "roadSituation": persona_context.get("roadSituation")
            or runtime_context.get("roadSituation"),
        }
    )
    return VoiceLabPersonaSessionRequest(
        sessionId=session_id,
        driver=driver,
        context=context,
        notes=[],
    )


def build_chat_request(
    *, message: str, runtime: ChatbotTaskConfig, session_id: str
) -> VoiceLabAgentChatRequest:
    del runtime
    return VoiceLabAgentChatRequest(sessionId=session_id, message=message)
