from __future__ import annotations

import re
from dataclasses import dataclass

from matraix.vita.models import Decision, VehicleState

_TEMPERATURE_PATTERN = re.compile(
    r"(?<!\d)(1[6-9]|2[0-9]|30)\s*(?:°?\s*c|độ)?",
    re.IGNORECASE,
)
_CLIMATE_TERMS = ("điều hòa", "nhiệt độ", "lạnh", "nóng", "temperature", "cabin")


@dataclass(frozen=True, slots=True)
class ClimateSkillResult:
    decision: Decision
    target_temperature_c: int | None
    state_after: VehicleState


def evaluate_climate(message: str, state: VehicleState) -> ClimateSkillResult:
    normalized = message.casefold()
    matches = {int(value) for value in _TEMPERATURE_PATTERN.findall(normalized)}
    if len(matches) == 1:
        temperature_c = matches.pop()
        return ClimateSkillResult(
            decision=Decision.EXECUTED,
            target_temperature_c=temperature_c,
            state_after=VehicleState(cabinTemperatureC=temperature_c),
        )
    has_climate_intent = any(term in normalized for term in _CLIMATE_TERMS)
    if has_climate_intent or len(matches) > 1:
        return ClimateSkillResult(
            decision=Decision.CLARIFICATION_REQUIRED,
            target_temperature_c=None,
            state_after=state,
        )
    return ClimateSkillResult(
        decision=Decision.UNSUPPORTED,
        target_temperature_c=None,
        state_after=state,
    )
