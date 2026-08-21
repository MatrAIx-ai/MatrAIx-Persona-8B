"""Harbor adapter for VoiceLab-backed conversational UXAgent trials."""

from __future__ import annotations

from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.agent.name import AgentName
from playground.harbor.chat_eval import harbor_chat_task_path_from_env
from playground.harbor.playground import _repo_root
from playground.chatbot_task_config import load_chatbot_task_config_for_task_path
from playground.model_client import build_json_client
from playground.persona_model import resolve_persona_model
from playground.task_content_bundle import load_task_content_bundle_for_task_path
from playground.user_sim.prompt import assemble_report_system_prompt
from playground.user_sim.self_report import final_self_report
from playground.self_report_task_config import load_self_report_schema_for_task_path
from playground.harbor.trial_events import TrialEventWriter
from playground.uxagent.client import VoiceLabPersonaClient
from playground.uxagent.policy import ConversationalUXPolicy
from playground.uxagent.runner import UXAgentTrialRunner

from matraix.agents.persona.mixin import PersonaMixin


class PersonaUXAgent(PersonaMixin, BaseAgent):
    """Run one persona-conditioned VoiceLab UXAgent trial."""

    SUPPORTS_WINDOWS = True

    @staticmethod
    def name() -> str:
        return AgentName.PERSONA_UXAGENT.value

    def version(self) -> str:
        return "1.0.0"

    def __init__(
        self,
        logs_dir: Path,
        persona_path: str | None = None,
        persona_template_path: str | None = None,
        **kwargs,
    ) -> None:
        self._init_persona(
            persona_path,
            AgentName.PERSONA_UXAGENT.value,
            persona_template_path=persona_template_path,
        )
        super().__init__(logs_dir=logs_dir, **kwargs)

    async def setup(self, environment: BaseEnvironment) -> None:
        del environment
        return None

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        del instruction, context
        await self._prepare_persona_trial(environment)

        task_path = harbor_chat_task_path_from_env()
        if not task_path:
            raise RuntimeError("MATRIX_CHATBOT_TASK_PATH is required for persona-uxagent")

        repo_root = _repo_root()
        runtime = load_chatbot_task_config_for_task_path(task_path, repo_root=repo_root)
        if runtime is None:
            raise RuntimeError(f"Missing chatbot config for {task_path}")

        task_bundle = load_task_content_bundle_for_task_path(
            task_path,
            repo_root=repo_root,
        )
        task_parts = [
            task_bundle.instruction_markdown.strip(),
            task_bundle.context_markdown.strip(),
        ]
        task_intent = "\n\n".join(part for part in task_parts if part)
        if not task_intent:
            raise RuntimeError(
                f"Task {task_path} must define instruction.md or context.md"
            )

        model_name = resolve_persona_model(
            model_name=self.model_name,
            include_chat_env=True,
        )
        policy_client = build_json_client(model_name)
        questionnaire_client = build_json_client(model_name)
        policy = ConversationalUXPolicy(
            persona_system=self._render_persona_system(),
            task_intent=task_intent,
            json_client=policy_client,
        )
        schema = load_self_report_schema_for_task_path(
            task_path,
            repo_root=repo_root,
            fallback_to_default=False,
        )
        persona_yaml_path = str(self._persona.persona_path)

        def questionnaire_builder(*, persona, transcript, config, task_intent):
            del config, task_intent
            report_prompt = assemble_report_system_prompt(
                persona,
                persona_yaml_path=persona_yaml_path,
                task_bundle=task_bundle,
            )
            return final_self_report(
                questionnaire_client,
                system_prompt=report_prompt,
                persona=persona,
                transcript=transcript,
                schema=schema,
            )

        runner = UXAgentTrialRunner(
            client=VoiceLabPersonaClient(),
            policy=policy,
            questionnaire_builder=questionnaire_builder,
        )
        await runner.run(
            environment=environment,
            persona=self._persona,
            runtime=runtime,
            task_intent=task_intent,
            on_event=TrialEventWriter.for_trial_dir(self.logs_dir.parent).append,
        )
