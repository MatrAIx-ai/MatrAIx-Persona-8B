"""Persona-backed Codex agent."""

from __future__ import annotations

from pathlib import Path

from harbor.agents.installed.codex import Codex
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.agent.name import AgentName

from matraix.agents.persona.mixin import PersonaMixin


class PersonaCodex(PersonaMixin, Codex):
    @staticmethod
    def name() -> str:
        return AgentName.PERSONA_CODEX.value

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
            AgentName.PERSONA_CODEX.value,
            persona_template_path=persona_template_path,
            persona_language=persona_language,
            persona_language_source=persona_language_source,
        )
        super().__init__(logs_dir=logs_dir, **kwargs)

    def render_instruction(self, instruction: str) -> str:
        rendered = super().render_instruction(instruction)
        return self._render_persona_instruction(rendered)

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        await self._prepare_persona_trial(environment)
        await super().run(instruction, environment, context)
