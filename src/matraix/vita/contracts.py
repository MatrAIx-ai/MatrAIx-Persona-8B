from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class VehicleMotion(StrEnum):
    DRIVING = "driving"
    PARKED = "parked"


class AssistantMode(StrEnum):
    SILENT = "silent"
    NORMAL = "normal"
    PROACTIVE = "proactive"


class NetworkCondition(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class AudioState(StrEnum):
    FREE = "free"
    MEDIA = "media"
    CALL = "call"


class InputModality(StrEnum):
    VOICE = "voice"
    TOUCH = "touch"
    TEXT = "text"


class AgentState(StrEnum):
    AVAILABLE = "available"
    LISTENING = "listening"
    USER_SPEAKING = "user_speaking"
    THINKING = "thinking"
    ANSWERING = "answering"
    IDLE = "idle"


class Outcome(StrEnum):
    SUCCESS = "success"
    NEEDS_INPUT = "needs_input"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class ResponseType(StrEnum):
    INFORM = "inform"
    SUGGEST = "suggest"
    CHOOSE = "choose"
    VERIFY = "verify"
    CONFIRM = "confirm"
    STATUS = "status"


class ToolStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RuntimeContext(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    vehicle_motion: VehicleMotion = Field(
        default=VehicleMotion.PARKED, alias="vehicleMotion"
    )
    assistant_mode: AssistantMode = Field(
        default=AssistantMode.NORMAL, alias="assistantMode"
    )
    network: NetworkCondition = NetworkCondition.UNKNOWN
    language: str = "vi"
    audio_state: AudioState = Field(default=AudioState.FREE, alias="audioState")
    input_modality: InputModality = Field(
        default=InputModality.TEXT, alias="inputModality"
    )


class ToolResult(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    tool: str
    status: ToolStatus
    arguments: dict[str, int]
    execution: str = "on_device"
