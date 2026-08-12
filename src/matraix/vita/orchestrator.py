from __future__ import annotations

import threading
import uuid

from matraix.vita.contracts import (
    AgentState,
    Outcome,
    ResponseType,
    ToolResult,
    ToolStatus,
)
from matraix.vita.models import (
    ActionEvent,
    ChatMessage,
    ConversationResponse,
    Decision,
    MessageRequest,
    MessageResponse,
    TurnEvidence,
    VehicleState,
)
from matraix.vita.skills.climate import evaluate_climate

_TURN_LIFECYCLE = (
    AgentState.LISTENING,
    AgentState.USER_SPEAKING,
    AgentState.THINKING,
    AgentState.ANSWERING,
    AgentState.IDLE,
)


class _SessionRecord:
    __slots__ = ("events", "messages", "scenario_id", "state", "turn_evidence")

    def __init__(self, scenario_id: str) -> None:
        self.scenario_id = scenario_id
        self.state = VehicleState()
        self.messages: list[ChatMessage] = []
        self.events: list[ActionEvent] = []
        self.turn_evidence: list[TurnEvidence] = []


class VitaOrchestrator:
    def __init__(self) -> None:
        self._records: dict[str, _SessionRecord] = {}
        self._lock = threading.Lock()

    def handle_message(self, request: MessageRequest) -> MessageResponse:
        with self._lock:
            session_id, record = self._resolve_record(request)
            state_before = record.state
            record.messages.append(
                ChatMessage(role="customer", content=request.message)
            )
            response = self._handle_climate(session_id, record, request)
            record.messages.append(ChatMessage(role="support", content=response.reply))
            record.turn_evidence.append(
                TurnEvidence(
                    turnId=str(uuid.uuid4()),
                    featureId=response.feature_id,
                    capabilityIds=response.capability_ids,
                    context=request.runtime_context,
                    outcome=response.outcome,
                    responseType=response.response_type,
                    lifecycle=response.lifecycle,
                    toolResult=response.tool_result,
                    stateBefore=state_before,
                    stateAfter=record.state,
                )
            )
            return response

    def conversation(self, session_id: str) -> ConversationResponse | None:
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                return None
            return ConversationResponse(
                sessionId=session_id,
                scenarioId=record.scenario_id,
                messages=tuple(record.messages),
                vehicleState=record.state,
                events=tuple(record.events),
                turnEvidence=tuple(record.turn_evidence),
            )

    def _resolve_record(self, request: MessageRequest) -> tuple[str, _SessionRecord]:
        if request.session_id:
            existing = self._records.get(request.session_id)
            if existing is not None:
                return request.session_id, existing
        session_id = request.session_id or str(uuid.uuid4())
        record = _SessionRecord(request.scenario_id)
        self._records[session_id] = record
        return session_id, record

    def _handle_climate(
        self,
        session_id: str,
        record: _SessionRecord,
        request: MessageRequest,
    ) -> MessageResponse:
        result = evaluate_climate(request.message, record.state)
        if result.decision is Decision.EXECUTED:
            return self._executed_response(session_id, record, request, result)
        if result.decision is Decision.CLARIFICATION_REQUIRED:
            return self._base_response(
                session_id=session_id,
                request=request,
                record=record,
                reply="Bạn muốn đặt nhiệt độ khoang xe ở bao nhiêu độ C?",
                decision=result.decision,
                capabilities=("clarification_disambiguation",),
                response_type=ResponseType.VERIFY,
                outcome=Outcome.NEEDS_INPUT,
            )
        return self._base_response(
            session_id=session_id,
            request=request,
            record=record,
            reply="Yêu cầu này chưa thuộc capability điều khiển nhiệt độ của Vita.",
            decision=result.decision,
            capabilities=("guardrail_refusal",),
            response_type=ResponseType.INFORM,
            outcome=Outcome.UNSUPPORTED,
            feature_id=None,
        )

    def _executed_response(self, session_id, record, request, result):
        temperature_c = result.target_temperature_c
        assert temperature_c is not None
        record.state = result.state_after
        action = ActionEvent(
            sequence=len(record.events) + 1,
            action="set_cabin_temperature",
            status="executed",
            temperatureC=temperature_c,
        )
        record.events.append(action)
        return self._base_response(
            session_id=session_id,
            request=request,
            record=record,
            reply=f"Đã đặt nhiệt độ khoang xe ở {temperature_c}°C.",
            decision=Decision.EXECUTED,
            capabilities=(
                "one_shot_interaction",
                "action_orchestration",
                "execution_status",
            ),
            response_type=ResponseType.STATUS,
            outcome=Outcome.SUCCESS,
            action=action,
            tool_result=ToolResult(
                tool="set_cabin_temperature",
                status=ToolStatus.SUCCEEDED,
                arguments={"temperatureC": temperature_c},
            ),
        )

    def _base_response(
        self,
        *,
        session_id: str,
        request: MessageRequest,
        record: _SessionRecord,
        reply: str,
        decision: Decision,
        capabilities: tuple[str, ...],
        response_type: ResponseType,
        outcome: Outcome,
        feature_id: str | None = "climate_control",
        action: ActionEvent | None = None,
        tool_result: ToolResult | None = None,
    ) -> MessageResponse:
        return MessageResponse(
            sessionId=session_id,
            reply=reply,
            decision=decision,
            action=action,
            vehicleState=record.state,
            featureId=feature_id,
            capabilityIds=capabilities,
            responseType=response_type,
            outcome=outcome,
            lifecycle=_TURN_LIFECYCLE,
            toolResult=tool_result,
            runtimeContext=request.runtime_context,
        )
