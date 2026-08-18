"""Local deterministic AppWorld evaluation runner."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Dict, Optional

from backend.service.appworld_types import (
    AppWorldEvalConfig,
    AppWorldEvalResult,
    AppWorldEvalTask,
    AppWorldResultArtifact,
    AppWorldTrace,
)
from playground.persona_language import resolve_persona_language_with_source
from playground.types import Persona
from playground.user_sim.prompt import render_persona_block


def build_appworld_task_prompt(task: AppWorldEvalTask) -> str:
    """Prompt contract for AppWorld-hosted agents."""
    return "\n".join(
        [
            "You are evaluating an AppWorld task as a realistic persona user.",
            "Application: {}".format(task.app_name),
            "Task: {}".format(task.title),
            "Task context: {}".format(task.description),
            "",
            "Interact only through AppWorld-style application APIs.",
            "Return `appworld_result.json` and `trace.json` artifacts.",
            "The result artifact must include task_id, success, score, outcome, and reason.",
        ]
    )


class LocalAppWorldEvalRunner:
    """Run a small deterministic AppWorld-style eval without external services."""

    def __call__(
        self,
        persona: Persona,
        task: AppWorldEvalTask,
        config: Optional[AppWorldEvalConfig] = None,
        *,
        created_at: str,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        persona_language: str | None = None,
        persona_language_source: str | None = None,
    ) -> AppWorldEvalResult:
        config = config or AppWorldEvalConfig()

        def emit(event: Dict[str, Any]) -> None:
            if on_event is not None:
                on_event(event)

        language = resolve_persona_language_with_source(
            persona_language if persona_language is not None else config.persona_language,
            requested_source=(
                persona_language_source
                if persona_language_source is not None
                else config.persona_language_source
            ),
            environ={},
        )
        config = replace(
            config,
            persona_language=language.language,
            persona_language_source=language.source,
        )
        persona_prompt = render_persona_block(
            persona,
            persona_language=language.language,
        ).strip()
        task_prompt = build_appworld_task_prompt(task)
        prompts = {
            "personaPrompt": persona_prompt,
            "harborPrompt": persona_prompt,
            "taskPrompt": task_prompt,
        }
        emit({"type": "prompts", "prompts": dict(prompts)})
        emit({"type": "phase", "phase": "appworld_simulating"})
        artifact = {
            "task_id": task.id,
            "success": True,
            "score": 1.0,
            "outcome": "Calendar invite and email draft completed.",
            "reason": "The deterministic local runner completed the AppWorld-style API task.",
        }
        trace = {
            "events": [
                {
                    "step": 1,
                    "source": "agent",
                    "message": "Inspected the available AppWorld apps.",
                    "actions": [
                        {
                            "name": "appworld_api_call",
                            "arguments": {"app": "system", "method": "list_apps"},
                        }
                    ],
                },
                {
                    "step": 2,
                    "source": "agent",
                    "message": "Updated the target app state and checked completion.",
                    "actions": [
                        {
                            "name": "appworld_api_call",
                            "arguments": {"app": "calendar", "method": "create_event"},
                        }
                    ],
                },
            ],
            "raw": {
                "mode": "local",
                "trajectory": [
                    {"observation": "available apps", "action": "list_apps"},
                    {"observation": "target state", "action": "create_event"},
                ],
            },
        }
        result = AppWorldEvalResult(
            config=config,
            persona=persona,
            task=task,
            appworld_result=AppWorldResultArtifact.from_dict(
                artifact,
                task=task,
                created_at=created_at,
            ),
            trace=AppWorldTrace(
                events=[dict(e) for e in trace["events"]],
                raw=dict(trace["raw"]),
            ),
            created_at=created_at,
            prompts=prompts,
        )
        emit({"type": "done", "result": result.to_dict()})
        return result
