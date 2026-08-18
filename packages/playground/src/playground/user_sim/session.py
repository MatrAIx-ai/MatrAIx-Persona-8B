"""Tool-driven user simulator session with messages[] memory."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from playground.persona_language import resolve_persona_language_with_source
from playground.task_content_bundle import TaskContentBundle
from playground.types import Persona
from playground.user_sim.prompt import assemble_system_prompt
from playground.user_sim.tool_client import ToolStepClient
from playground.user_sim.tools import TurnAction, extract_stop_token, parse_tool_calls


_START_OBSERVATION = (
    "The conversation is starting. The application chatbot has not replied yet. "
    "Send your opening message with send_message."
)


def _format_assistant_turn(action: TurnAction) -> str:
    """Record what the simulated user did without echoing tool-call syntax."""
    parts: List[str] = []
    if action.capability_tool:
        parts.append(
            "[Used tool `{}` with {}]".format(
                action.capability_tool,
                action.capability_arguments or {},
            )
        )
    if action.message:
        parts.append(action.message)
    if action.end_reason:
        note = (action.note or "").strip()
        if note:
            parts.append("[Ended: {} — {}]".format(action.end_reason, note))
        else:
            parts.append("[Ended: {}]".format(action.end_reason))
    return "\n".join(parts) if parts else "(no action)"


class UserSimSession:
    """Tool-driven simulated user with real multi-turn ``messages[]`` memory."""

    def __init__(
        self,
        client: ToolStepClient,
        persona: Persona,
        *,
        persona_yaml_path: Optional[str] = None,
        task_bundle: Optional[TaskContentBundle] = None,
        persona_language: Optional[str] = None,
        persona_language_source: Optional[str] = None,
    ) -> None:
        self._client = client
        self._persona = persona
        self._persona_yaml_path = persona_yaml_path
        language = resolve_persona_language_with_source(
            persona_language,
            requested_source=persona_language_source,
        )
        self.effective_persona_language = language.language
        self.persona_language_source = language.source
        system = assemble_system_prompt(
            persona,
            persona_yaml_path=persona_yaml_path,
            task_bundle=task_bundle,
            persona_language=self.effective_persona_language,
        )
        self._messages: List[Dict[str, Any]] = [{"role": "system", "content": system}]
        self.system_prompt = system


    @property
    def messages(self) -> List[Dict[str, Any]]:
        return list(self._messages)

    def next_action(self, observation: str) -> TurnAction:
        self._messages.append({"role": "user", "content": observation})
        calls = self._client.complete_with_tools(self._messages)
        action = parse_tool_calls(calls)
        if action.message:
            stop = extract_stop_token(action.message)
            if stop and not action.end_reason:
                action.end_reason = stop
        self._messages.append(
            {
                "role": "assistant",
                "content": _format_assistant_turn(action),
            }
        )
        return action

    def opening_action(self) -> TurnAction:
        return self.next_action(_START_OBSERVATION)
