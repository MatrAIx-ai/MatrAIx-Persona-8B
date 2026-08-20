from pathlib import Path

import pytest
from pydantic import ValidationError

from playground.uxagent.models import SendMessageAction, VoiceLabAgentChatResponse


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


def test_clean_room_notice_records_unlicensed_upstream_revision() -> None:
    root = Path(__file__).resolve().parents[5]
    notice = (root / "docs/third-party/uxagent-clean-room-notice.txt").read_text()
    assert "https://github.com/neuhai/UXAgent" in notice
    assert "4d3b1f1c1fef93c5e2ea7d104153ea164ba1acbd" in notice
    assert "No source code or prompt text was copied" in notice
