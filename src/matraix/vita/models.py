from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from matraix.vita.contracts import (
    AgentState,
    Outcome,
    ResponseType,
    RuntimeContext,
    ToolResult,
)


class Decision(StrEnum):
    EXECUTED = "executed"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED = "unsupported"


class VehicleState(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    cabin_temperature_c: int = Field(
        default=22, alias="cabinTemperatureC", ge=16, le=30
    )


class MessageRequest(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    message: str = Field(min_length=1)
    session_id: str | None = Field(default=None, alias="sessionId")
    scenario_id: str = Field(default="climate", alias="scenarioId")
    runtime_context: RuntimeContext = Field(
        default_factory=RuntimeContext,
        alias="runtimeContext",
    )


class ChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str
    content: str


class ActionEvent(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    sequence: int
    action: str
    status: str
    temperature_c: int = Field(alias="temperatureC")


class MessageResponse(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    reply: str
    decision: Decision
    action: ActionEvent | None
    vehicle_state: VehicleState = Field(alias="vehicleState")
    feature_id: str | None = Field(default=None, alias="featureId")
    capability_ids: tuple[str, ...] = Field(default=(), alias="capabilityIds")
    response_type: ResponseType = Field(alias="responseType")
    outcome: Outcome
    lifecycle: tuple[AgentState, ...]
    tool_result: ToolResult | None = Field(alias="toolResult")
    runtime_context: RuntimeContext = Field(alias="runtimeContext")


class TurnEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    turn_id: str = Field(alias="turnId")
    feature_id: str | None = Field(alias="featureId")
    capability_ids: tuple[str, ...] = Field(alias="capabilityIds")
    context: RuntimeContext
    outcome: Outcome
    response_type: ResponseType = Field(alias="responseType")
    lifecycle: tuple[AgentState, ...]
    tool_result: ToolResult | None = Field(alias="toolResult")
    state_before: VehicleState = Field(alias="stateBefore")
    state_after: VehicleState = Field(alias="stateAfter")


class ConversationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    scenario_id: str = Field(alias="scenarioId")
    messages: tuple[ChatMessage, ...]
    vehicle_state: VehicleState = Field(alias="vehicleState")
    events: tuple[ActionEvent, ...]
    turn_evidence: tuple[TurnEvidence, ...] = Field(alias="turnEvidence")


class ReadyResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    capabilities: tuple[str, ...]
