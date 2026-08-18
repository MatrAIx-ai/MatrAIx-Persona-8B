"""Shared AppWorld evaluation dataclasses."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List

from playground.types import DEFAULT_PERSONA_MODEL, Persona


@dataclass(frozen=True)
class AppWorldEvalTask:
    """An AppWorld task available for persona-agent testing."""

    id: str
    title: str
    app_name: str
    description: str
    output_artifact: str = "appworld_result.json"
    submission_profile: str = "appworld_result"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "appName": self.app_name,
            "description": self.description,
            "outputArtifact": self.output_artifact,
            "submissionProfile": self.submission_profile,
        }


@dataclass(frozen=True)
class AppWorldEvalConfig:
    """Configuration for one AppWorld eval run."""

    persona_model: str = DEFAULT_PERSONA_MODEL
    mode: str = "local_persona_appworld"
    persona_language: str = "en"
    persona_language_source: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "personaModel": self.persona_model,
            "mode": self.mode,
            "effectiveLanguage": self.persona_language,
            "languageSource": self.persona_language_source,
        }


@dataclass(frozen=True)
class AppWorldResultArtifact:
    """Normalized AppWorld result artifact."""

    task_id: str
    success: bool
    score: float
    outcome: str
    reason: str
    created_at: str

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], *, task: AppWorldEvalTask, created_at: str
    ) -> "AppWorldResultArtifact":
        score = _score(data.get("score", 1.0 if data.get("success") else 0.0))
        return cls(
            task_id=str(data.get("task_id", data.get("taskId", task.id)) or task.id),
            success=bool(data.get("success", score >= 1.0)),
            score=score,
            outcome=str(
                data.get("outcome")
                or data.get("final_state")
                or data.get("finalState")
                or "The AppWorld task completed."
            ),
            reason=str(
                data.get("reason")
                or data.get("rationale")
                or "The AppWorld runner returned a completed task artifact."
            ),
            created_at=created_at,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "taskId": self.task_id,
            "success": self.success,
            "score": self.score,
            "outcome": self.outcome,
            "reason": self.reason,
            "createdAt": self.created_at,
        }


@dataclass(frozen=True)
class AppWorldTrace:
    """Agent trace for an AppWorld eval."""

    events: List[Dict[str, Any]]
    raw: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "events": [dict(event) for event in self.events],
            "raw": dict(self.raw),
        }


@dataclass(frozen=True)
class AppWorldEvalResult:
    """Complete AppWorld eval result."""

    config: AppWorldEvalConfig
    persona: Persona
    task: AppWorldEvalTask
    appworld_result: AppWorldResultArtifact
    trace: AppWorldTrace
    created_at: str
    prompts: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "persona": {
                "id": self.persona.id,
                "name": self.persona.name,
                "context": self.persona.context,
            },
            "task": self.task.to_dict(),
            "appworldResult": self.appworld_result.to_dict(),
            "trace": self.trace.to_dict(),
            "createdAt": self.created_at,
            "prompts": dict(self.prompts),
        }


def _score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    if not math.isfinite(score):
        return 0.0
    return max(0.0, min(1.0, score))
