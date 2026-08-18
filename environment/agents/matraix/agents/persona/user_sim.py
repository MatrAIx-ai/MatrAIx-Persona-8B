"""Host-native chat agent for the ``user_sim_chat`` Harbor trial profile."""

from __future__ import annotations

from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.agent.name import AgentName

from playground.harbor.chat_eval import (
    run_harbor_chat_eval_for_persona,
)
from playground.harbor.trial_events import TrialEventWriter
from matraix.agents.persona.mixin import PersonaMixin


class PersonaUserSim(PersonaMixin, BaseAgent):
    """Drive a multi-turn chat via UserSimulator + task sidecar (no Claude Code)."""

    SUPPORTS_WINDOWS = True

    @staticmethod
    def name() -> str:
        return AgentName.PERSONA_USER_SIM.value

    def version(self) -> str:
        return "1.0.0"

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
            AgentName.PERSONA_USER_SIM.value,
            persona_template_path=persona_template_path,
            persona_language=persona_language,
            persona_language_source=persona_language_source,
        )
        super().__init__(logs_dir=logs_dir, **kwargs)

    async def setup(self, environment: BaseEnvironment) -> None:
        return None

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        del instruction
        await self._prepare_persona_trial(environment)
        event_writer = TrialEventWriter.for_trial_dir(self.logs_dir.parent)

        def on_event(event: dict) -> None:
            event_writer.append(event)

        result, session_id = await run_harbor_chat_eval_for_persona(
            environment,
            self._persona,
            model_name=self.model_name,
            on_event=on_event,
            persona_language=self.effective_persona_language,
            persona_language_source=self.persona_language_source,
        )
        from playground.llm_usage import apply_usage_dict_to_context

        apply_usage_dict_to_context(context, getattr(result, "usage", None))
        del session_id
