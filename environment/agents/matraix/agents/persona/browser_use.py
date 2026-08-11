"""Persona-backed browser-use agent."""

from __future__ import annotations

from pathlib import Path

from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.agent.name import AgentName

from matraix.agents.installed.browser_use import BrowserUseHarborAgent
from matraix.agents.persona.mixin import PersonaMixin


class PersonaBrowserUse(PersonaMixin, BrowserUseHarborAgent):
    """Inject persona via browser-use ``extend_system_message``; task stays separate."""

    @staticmethod
    def name() -> str:
        return AgentName.PERSONA_BROWSER_USE.value

    def __init__(
        self,
        logs_dir: Path,
        persona_path: str | None = None,
        persona_template_path: str | None = None,
        persona_language: str | None = None,
        persona_language_source: str | None = None,
        **kwargs,
    ) -> None:
        self._init_persona(
            persona_path,
            AgentName.PERSONA_BROWSER_USE.value,
            persona_template_path=persona_template_path,
            persona_language=persona_language,
            persona_language_source=persona_language_source,
        )
        super().__init__(logs_dir=logs_dir, **kwargs)

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        await self._prepare_persona_trial(environment)
        self._extra_env = {
            **getattr(self, "_extra_env", {}),
            "PERSONA_SYSTEM": self._render_persona_system(),
        }
        await super().run(instruction, environment, context)
