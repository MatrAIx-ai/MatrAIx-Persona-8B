from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SendMessageAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["send_message"] = "send_message"
    message: str
    end_reason: str | None = None

    @field_validator("message")
    @classmethod
    def non_blank_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class VoiceLabPersonaSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessionId: str
    source: Literal["matraix-uxagent"] = "matraix-uxagent"
    driver: dict[str, Any]
    context: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class VoiceLabAgentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessionId: str
    message: str

class VoiceLabAgentChatResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
    )

    reply: str
    decision: str | None = None
    vehicle_state: dict[str, Any] | None = Field(default=None, alias="vehicleState")
    action: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = Field(default=None, alias="toolResult")
    capability_ids: list[str] = Field(default_factory=list, alias="capabilityIds")
    runtime_context: dict[str, Any] = Field(default_factory=dict, alias="runtimeContext")

    @field_validator("reply")
    @classmethod
    def non_blank_reply(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reply must not be blank")
        return value


class UXMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["observation", "reflection", "wonder", "plan", "action"]
    content: str
    importance: float = Field(ge=0.0, le=1.0)
    turn_index: int = Field(ge=0)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class UXObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_intent: str
    turn_index: int = Field(ge=0)
    assistant_reply: str = ""
    decision: str | None = None
    vehicle_state: dict[str, Any] | None = None
    action: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None
    capability_ids: list[str] = Field(default_factory=list)
    runtime_context: dict[str, Any] = Field(default_factory=dict)
