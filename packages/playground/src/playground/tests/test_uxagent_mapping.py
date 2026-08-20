import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from playground.uxagent.models import (
    SendMessageAction,
    UXMemory,
    UXObservation,
    VoiceLabAgentChatRequest,
    VoiceLabAgentChatResponse,
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
