from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

OUTPUT_DIR = Path(
    os.environ.get("HARBOR_OUTPUT_DIR")
    or os.environ.get("MATRIX_OUTPUT_DIR")
    or "/app/output"
)
TRANSCRIPT_PATH = OUTPUT_DIR / "transcript.json"
EXPECTED_TEMPERATURE_C = 24


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str
    content: str


class VehicleState(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    cabin_temperature_c: int = Field(alias="cabinTemperatureC")


class Event(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    action: str
    status: str
    temperature_c: int = Field(alias="temperatureC")


class RuntimeContext(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    vehicle_motion: str = Field(alias="vehicleMotion")
    network: str
    language: str


class ToolResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool: str
    status: str


class TurnEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    feature_id: str | None = Field(alias="featureId")
    capability_ids: tuple[str, ...] = Field(alias="capabilityIds")
    context: RuntimeContext
    outcome: str
    response_type: str = Field(alias="responseType")
    tool_result: ToolResult | None = Field(alias="toolResult")
    state_before: VehicleState = Field(alias="stateBefore")
    state_after: VehicleState = Field(alias="stateAfter")


class Transcript(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    messages: tuple[Message, ...]
    vehicle_state: VehicleState = Field(alias="vehicleState")
    events: tuple[Event, ...]
    turn_evidence: tuple[TurnEvidence, ...] = Field(alias="turnEvidence")


def load_transcript() -> Transcript:
    return Transcript.model_validate_json(TRANSCRIPT_PATH.read_text(encoding="utf-8"))


def state_change_succeeded(transcript: Transcript) -> bool:
    evidence = transcript.turn_evidence[-1] if transcript.turn_evidence else None
    return bool(
        transcript.events
        and evidence
        and transcript.vehicle_state.cabin_temperature_c == EXPECTED_TEMPERATURE_C
        and transcript.events[-1].action == "set_cabin_temperature"
        and transcript.events[-1].status == "executed"
        and transcript.events[-1].temperature_c == EXPECTED_TEMPERATURE_C
        and evidence.feature_id == "climate_control"
        and set(evidence.capability_ids)
        >= {"one_shot_interaction", "action_orchestration", "execution_status"}
        and evidence.context.vehicle_motion == "driving"
        and evidence.context.network == "offline"
        and evidence.context.language == "vi"
        and evidence.outcome == "success"
        and evidence.response_type == "status"
        and evidence.tool_result is not None
        and evidence.tool_result.tool == "set_cabin_temperature"
        and evidence.tool_result.status == "succeeded"
        and evidence.state_before.cabin_temperature_c == 22
        and evidence.state_after.cabin_temperature_c == EXPECTED_TEMPERATURE_C
    )


def write_structured_output(transcript: Transcript) -> None:
    success = state_change_succeeded(transcript)
    evidence = transcript.turn_evidence[-1]
    user_turns = sum(message.role == "customer" for message in transcript.messages)
    assistant_turns = sum(message.role == "support" for message in transcript.messages)
    payload = {
        "schemaVersion": "1.0",
        "artifactType": "matraix.trial_evaluation",
        "taskType": "chatbot",
        "contexts": [
            {
                "key": "task_outcome.primary",
                "label": "Task outcome",
                "contextType": "task_outcome",
                "facets": [
                    {
                        "key": "outcome_status",
                        "label": "Outcome status",
                        "role": "primary",
                        "kind": "categorical",
                        "value": "resolved" if success else "unresolved",
                    },
                    {
                        "key": "resolution_basis",
                        "label": "Resolution basis",
                        "role": "primary",
                        "kind": "categorical",
                        "value": "tool_state",
                    },
                    {
                        "key": "outcome_reason",
                        "label": "Outcome reason",
                        "role": "explanation",
                        "kind": "textual",
                        "explainsFacetKey": "outcome_status",
                        "value": "Vehicle state and action event matched the requested temperature."
                        if success
                        else "Vehicle state did not match the requested temperature.",
                    },
                    {
                        "key": "next_step_owner",
                        "label": "Next step owner",
                        "role": "evidence",
                        "kind": "categorical",
                        "value": "none" if success else "agent",
                    },
                ],
            },
            {
                "key": "conversation_summary.primary",
                "label": "Conversation summary",
                "contextType": "conversation_summary",
                "facets": [
                    {
                        "key": "conversation_path",
                        "label": "Conversation path",
                        "role": "primary",
                        "kind": "categorical",
                        "value": "direct_resolution"
                        if user_turns == 1
                        else "clarify_then_resolve",
                    },
                    {
                        "key": "user_turn_count",
                        "label": "User turn count",
                        "role": "score",
                        "kind": "numerical",
                        "value": user_turns,
                    },
                    {
                        "key": "assistant_turn_count",
                        "label": "Assistant turn count",
                        "role": "score",
                        "kind": "numerical",
                        "value": assistant_turns,
                    },
                    {
                        "key": "message_count",
                        "label": "Message count",
                        "role": "score",
                        "kind": "numerical",
                        "value": len(transcript.messages),
                    },
                ],
            },
            {
                "key": "vehicle_state_transition.climate",
                "label": "Climate state transition",
                "contextType": "vehicle_state_transition",
                "facets": [
                    {
                        "key": "requested_temperature_c",
                        "label": "Requested temperature",
                        "role": "evidence",
                        "kind": "numerical",
                        "value": EXPECTED_TEMPERATURE_C,
                    },
                    {
                        "key": "observed_temperature_c",
                        "label": "Observed temperature",
                        "role": "score",
                        "kind": "numerical",
                        "value": transcript.vehicle_state.cabin_temperature_c,
                    },
                    {
                        "key": "state_match",
                        "label": "State match",
                        "role": "primary",
                        "kind": "categorical",
                        "value": "yes" if success else "no",
                    },
                    {
                        "key": "unsafe_action_present",
                        "label": "Unsafe action present",
                        "role": "evidence",
                        "kind": "categorical",
                        "value": "no",
                    },
                ],
            },
            {
                "key": "vita_coverage.climate_temperature",
                "label": "Vita Feature × Capability × Context coverage",
                "contextType": "vita_coverage",
                "facets": [
                    {
                        "key": "feature_id",
                        "label": "Feature",
                        "role": "primary",
                        "kind": "categorical",
                        "value": evidence.feature_id,
                    },
                    {
                        "key": "capability_ids",
                        "label": "Capabilities exercised",
                        "role": "evidence",
                        "kind": "textual",
                        "value": ",".join(evidence.capability_ids),
                    },
                    {
                        "key": "runtime_context",
                        "label": "Runtime context",
                        "role": "evidence",
                        "kind": "textual",
                        "value": (
                            f"{evidence.context.vehicle_motion}/"
                            f"{evidence.context.network}/{evidence.context.language}"
                        ),
                    },
                    {
                        "key": "capability_compliance",
                        "label": "Capability compliance",
                        "role": "score",
                        "kind": "categorical",
                        "value": "pass" if success else "fail",
                    },
                ],
            },
        ],
    }
    verifier_dir = Path(os.environ.get("HARBOR_VERIFIER_DIR") or "/logs/verifier")
    verifier_dir.mkdir(parents=True, exist_ok=True)
    (verifier_dir / "structured_output.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_expected_temperature_was_applied() -> None:
    transcript = load_transcript()
    write_structured_output(transcript)
    assert state_change_succeeded(transcript)
