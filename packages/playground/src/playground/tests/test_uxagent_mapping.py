import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from playground.chatbot_task_config import (
    ChatbotProtocolConfig,
    ChatbotRuntimeDefaults,
    ChatbotTaskConfig,
)
from playground.uxagent.mapping import build_chat_request, build_persona_session_request
from playground.uxagent.models import (
    SendMessageAction,
    UXMemory,
    UXObservation,
    VoiceLabAgentChatRequest,
    VoiceLabAgentChatResponse,
)


def _persona() -> SimpleNamespace:
    return SimpleNamespace(
        display_name="Anh Hải",
        summary="Bận rộn, thích câu trả lời ngắn.",
        system_prompt=None,
        communication={"style": "ngắn, tự nhiên"},
        psychology={"traits": ["thích sự riêng tư"]},
        preferences={"temperature": 22, "music": "nhạc nhẹ"},
        behavior={},
        data={"context": {"mood": "mệt", "fatigueLevel": "high"}},
    )


def _runtime() -> ChatbotTaskConfig:
    return ChatbotTaskConfig(
        runtime_defaults=ChatbotRuntimeDefaults(max_turns=4),
        protocol=ChatbotProtocolConfig(
            static_body={
                "scenarioId": "climate-temperature",
                "runtimeContext": {
                    "vehicleMotion": "driving",
                    "language": "vi",
                    "roadSituation": "đường đông",
                },
            }
        ),
    )


def test_send_message_action_rejects_blank_message() -> None:
    with pytest.raises(ValidationError):
        SendMessageAction(message="   ")


def test_agent_chat_response_requires_reply_and_evidence_shape() -> None:
    response = VoiceLabAgentChatResponse.model_validate(
        {
            "reply": "Đã đặt 22 độ.",
            "decision": "executed",
            "vehicleState": {"temperature": 22},
            "action": {"tool": "set_temperature"},
            "toolResult": {"ok": True},
            "capabilityIds": ["climate.set_temperature"],
            "runtimeContext": {"vehicleMotion": "driving"},
        }
    )
    assert response.reply == "Đã đặt 22 độ."
    assert response.model_dump(by_alias=True)["vehicleState"] == {"temperature": 22}

def test_agent_chat_response_rejects_blank_or_missing_reply() -> None:
    with pytest.raises(ValidationError):
        VoiceLabAgentChatResponse(reply="   ")
    with pytest.raises(ValidationError):
        VoiceLabAgentChatResponse.model_validate({})


def test_agent_chat_response_accepts_aliases_and_internal_field_names() -> None:
    response = VoiceLabAgentChatResponse(
        reply="Đã đặt 22 độ.",
        vehicle_state={"temperature": 22},
        tool_result={"ok": True},
        capability_ids=["climate.set_temperature"],
        runtime_context={"vehicleMotion": "driving"},
    )

    assert response.vehicle_state == {"temperature": 22}
    dumped = response.model_dump()
    assert dumped["vehicleState"] == {"temperature": 22}
    assert dumped["toolResult"] == {"ok": True}
    assert dumped["capabilityIds"] == ["climate.set_temperature"]
    assert dumped["runtimeContext"] == {"vehicleMotion": "driving"}
    assert json.loads(response.model_dump_json())["vehicleState"] == {"temperature": 22}


def test_agent_chat_response_preserves_extra_provider_fields() -> None:
    response = VoiceLabAgentChatResponse.model_validate(
        {"reply": "ok", "providerTraceId": "trace-123"}
    )

    assert response.model_extra == {"providerTraceId": "trace-123"}
    assert response.model_dump()["providerTraceId"] == "trace-123"

def test_maps_available_persona_and_runtime_fields() -> None:
    payload = build_persona_session_request(
        persona=_persona(), runtime=_runtime(), session_id="trial-001"
    ).model_dump(exclude_none=True)

    assert payload["sessionId"] == "trial-001"
    assert payload["source"] == "matraix-uxagent"
    assert payload["driver"] == {
        "name": "Anh Hải",
        "persona": "Bận rộn, thích câu trả lời ngắn.",
        "communicationStyle": "ngắn, tự nhiên",
        "traits": ["thích sự riêng tư"],
        "preferences": {"temperature": 22, "music": "nhạc nhẹ"},
    }
    assert payload["context"] == {
        "mood": "mệt",
        "fatigueLevel": "high",
        "roadSituation": "đường đông",
    }
    assert "stressLevel" not in payload["context"]
    assert payload["notes"] == []

def test_mapping_does_not_alias_persona_containers() -> None:
    persona = _persona()
    persona.preferences["audio"] = {"volume": 5}

    request = build_persona_session_request(
        persona=persona, runtime=_runtime(), session_id="trial-006"
    )
    request.driver["traits"].append("new trait")
    request.driver["preferences"]["audio"]["volume"] = 10

    assert persona.psychology["traits"] == ["thích sự riêng tư"]
    assert persona.preferences["audio"] == {"volume": 5}


def test_chat_request_uses_vita_runtime_and_scenario() -> None:
    payload = build_chat_request(
        message="Cho anh 22 độ.", runtime=_runtime(), session_id="trial-001"
    )

    assert payload.model_dump() == {
        "message": "Cho anh 22 độ.",
        "drivingContext": "driving",
        "intent": "climate-temperature",
        "personaSessionId": "trial-001",
    }


def test_mapping_omits_missing_optional_values() -> None:
    persona = SimpleNamespace(
        display_name="",
        summary=None,
        system_prompt="",
        communication={},
        psychology={},
        preferences={},
        data={"context": {}},
    )
    runtime = ChatbotTaskConfig(
        runtime_defaults=ChatbotRuntimeDefaults(),
        protocol=ChatbotProtocolConfig(static_body={}),
    )

    session = build_persona_session_request(
        persona=persona, runtime=runtime, session_id="trial-002"
    ).model_dump()
    assert session["driver"] == {}
    assert session["context"] == {}

def test_mapping_prefers_persona_road_situation() -> None:
    persona = _persona()
    persona.data["context"]["roadSituation"] = "bãi đỗ xe"

    session = build_persona_session_request(
        persona=persona, runtime=_runtime(), session_id="trial-004"
    ).model_dump()

    assert session["context"]["roadSituation"] == "bãi đỗ xe"


def test_chat_request_does_not_fabricate_missing_intent() -> None:
    runtime = ChatbotTaskConfig(
        runtime_defaults=ChatbotRuntimeDefaults(),
        protocol=ChatbotProtocolConfig(static_body={}),
    )

    assert build_chat_request(
        message="Xin chào", runtime=runtime, session_id="trial-005"
    ).model_dump() == {
        "message": "Xin chào",
        "drivingContext": "unknown",
        "intent": "",
        "personaSessionId": "trial-005",
    }



def test_chat_request_uses_unknown_without_vehicle_motion() -> None:
    runtime = ChatbotTaskConfig(
        runtime_defaults=ChatbotRuntimeDefaults(
            application_context="fallback-context",
            application_id="fallback-id",
        ),
        protocol=ChatbotProtocolConfig(static_body={}),
    )

    assert build_chat_request(
        message="Xin chào", runtime=runtime, session_id="trial-003"
    ).model_dump() == {
        "message": "Xin chào",
        "drivingContext": "unknown",
        "intent": "fallback-context",
        "personaSessionId": "trial-003",
    }

def test_agent_chat_request_constructs_with_wire_fields() -> None:
    request = VoiceLabAgentChatRequest(
        message="Set the temperature to 22 degrees.",
        drivingContext="driving",
        intent="climate",
        personaSessionId="session-123",
    )

    assert request.model_dump() == {
        "message": "Set the temperature to 22 degrees.",
        "drivingContext": "driving",
        "intent": "climate",
        "personaSessionId": "session-123",
    }


def test_memory_and_observation_models_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        UXMemory(
            kind="observation",
            content="The driver sounds rushed.",
            importance=0.5,
            turn_index=1,
            unexpected=True,
        )
    with pytest.raises(ValidationError):
        UXObservation(task_intent="climate", turn_index=1, unexpected=True)


def test_clean_room_notice_records_unlicensed_upstream_revision() -> None:
    root = Path(__file__).resolve().parents[5]
    notice = (root / "docs/third-party/uxagent-clean-room-notice.txt").read_text()
    assert "https://github.com/neuhai/UXAgent" in notice
    assert "4d3b1f1c1fef93c5e2ea7d104153ea164ba1acbd" in notice
    assert "No source code or prompt text was copied" in notice
