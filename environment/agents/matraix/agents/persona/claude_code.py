"""Persona-backed Claude Code agent."""

from __future__ import annotations

from pathlib import Path

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.agent.name import AgentName

from matraix.agents.persona.mixin import PersonaMixin


def _merge_append_system_prompt(existing: str | None, persona_prompt: str) -> str:
    persona_prompt = persona_prompt.strip()
    if not existing:
        return persona_prompt
    existing = existing.strip()
    if not existing:
        return persona_prompt
    return f"{persona_prompt}\n\n{existing}"


class PersonaClaudeCode(PersonaMixin, ClaudeCode):
    @staticmethod
    def name() -> str:
        return AgentName.PERSONA_CLAUDE_CODE.value

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
            AgentName.PERSONA_CLAUDE_CODE.value,
            persona_template_path=persona_template_path,
            persona_language=persona_language,
            persona_language_source=persona_language_source,
        )
        kwargs["append_system_prompt"] = _merge_append_system_prompt(
            kwargs.get("append_system_prompt"),
            self._render_persona_system(),
        )
        super().__init__(logs_dir=logs_dir, **kwargs)

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        await self._prepare_persona_trial(environment)
        await super().run(instruction, environment, context)
