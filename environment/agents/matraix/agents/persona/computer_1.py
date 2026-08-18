"""Persona-backed computer-use agent with platform-aware CUA routing."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.agent.name import AgentName

from matraix.agents.persona.cua_submission import materialize_final_answer_file
from matraix.agents.persona.mixin import PersonaMixin

CuaBackendKind = Literal["use_computer_desktop", "ios", "docker_computer1"]
DesktopCuaProvider = Literal["anthropic", "openai", "gemini"]


def resolve_cua_backend_kind(
    environment: BaseEnvironment,
    *,
    override: str | None = None,
) -> CuaBackendKind:
    """Pick the CUA runtime for this environment."""
    if override:
        normalized = override.strip().lower().replace("-", "_")
        if normalized in {"ios", "ios_cua"}:
            return "ios"
        if normalized in {
            "use_computer",
            "use_computer_desktop",
            "desktop",
            "anthropic",
            "anthropic_cua",
            "openai",
            "openai_cua",
            "gemini",
            "gemini_cua",
            "macos",
            "ubuntu",
        }:
            return "use_computer_desktop"
        if normalized in {
            "docker",
            "docker_computer1",
            "computer1",
            "computer_1",
            "linux",
        }:
            return "docker_computer1"
        raise ValueError(
            f"Unknown cua_backend {override!r}; use ios, use-computer, or docker."
        )

    from harbor.environments.use_computer import UseComputerEnvironment

    if isinstance(environment, UseComputerEnvironment):
        platform = getattr(environment, "_platform", "macos")
        if platform == "ios":
            return "ios"
        return "use_computer_desktop"

    return "docker_computer1"


def resolve_desktop_cua_provider(
    model_name: str | None,
    *,
    cua_backend: str | None = None,
) -> DesktopCuaProvider:
    """Pick the use.computer desktop CUA provider from model / backend hint."""
    if cua_backend:
        normalized = cua_backend.strip().lower().replace("-", "_")
        if normalized in {"openai", "openai_cua"}:
            return "openai"
        if normalized in {"gemini", "gemini_cua"}:
            return "gemini"
        if normalized in {"anthropic", "anthropic_cua"}:
            return "anthropic"

    lowered = (model_name or "").strip().lower()
    if lowered.startswith("openai/") or "gpt-5.4" in lowered or "gpt-5.5" in lowered:
        return "openai"
    if lowered.startswith(("gemini/", "vertex_ai/")):
        return "gemini"
    return "anthropic"


def _build_cua_delegate(
    kind: CuaBackendKind,
    *,
    logs_dir: Path,
    model_name: str | None,
    logger,
    mcp_servers,
    skills_dir: str | None,
    delegate_kwargs: dict[str, Any],
    cua_backend: str | None = None,
) -> BaseAgent:
    common: dict[str, Any] = {
        "logs_dir": logs_dir,
        "model_name": model_name,
        "logger": logger,
        "mcp_servers": mcp_servers,
        "skills_dir": skills_dir,
        **delegate_kwargs,
    }

    if kind == "ios":
        try:
            from use_computer.harbor.agents import IOSAgent
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "persona-computer-1 iOS CUA requires "
                "`uv sync --extra use-computer` (installs use-computer[harbor,agents])."
            ) from exc
        return IOSAgent(**common)

    if kind == "use_computer_desktop":
        provider = resolve_desktop_cua_provider(
            model_name, cua_backend=cua_backend
        )
        try:
            from use_computer.harbor.agents import (
                AnthropicCUAAgent,
                GeminiCUAAgent,
                OpenAICUAAgent,
            )
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "persona-computer-1 use.computer CUA requires "
                "`uv sync --extra use-computer` (installs use-computer[harbor,agents])."
            ) from exc
        if provider == "openai":
            return OpenAICUAAgent(**common)
        if provider == "gemini":
            return GeminiCUAAgent(**common)
        from matraix.agents.persona.use_computer_cua_protocol import (
            apply_use_computer_anthropic_cua_protocol_patch,
        )

        apply_use_computer_anthropic_cua_protocol_patch()
        return AnthropicCUAAgent(**common)

    from harbor.agents.computer_1 import Computer1

    # Shared Playground / job YAML often uses max_steps (use.computer); Docker
    # Computer1 only accepts max_turns. Remap so mixed configs do not TypeError.
    docker_kwargs = dict(common)
    if "max_steps" in docker_kwargs:
        if "max_turns" not in docker_kwargs:
            docker_kwargs["max_turns"] = docker_kwargs.pop("max_steps")
        else:
            docker_kwargs.pop("max_steps")

    try:
        return Computer1(**docker_kwargs)
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "persona-computer-1 Docker CUA requires "
            "`uv sync --extra computer-1` for native Anthropic computer-use."
        ) from exc


class PersonaComputer1(PersonaMixin, BaseAgent):
    """Route persona CUA to use.computer (macOS/iOS) or Docker Computer1."""

    SUPPORTS_ATIF = True

    @staticmethod
    def name() -> str:
        return AgentName.PERSONA_COMPUTER_1.value

    def __init__(
        self,
        logs_dir: Path,
        model_name: str | None = None,
        persona_path: str | None = None,
        persona_template_path: str | None = None,
        persona_language: str | None = None,
        persona_language_source: str | None = None,
        cua_backend: str | None = None,
        cua_submission_profile: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            logs_dir=logs_dir,
            model_name=model_name,
            mcp_servers=kwargs.get("mcp_servers"),
            skills_dir=kwargs.get("skills_dir"),
        )
        self._init_persona(
            persona_path,
            AgentName.PERSONA_COMPUTER_1.value,
            persona_template_path=persona_template_path,
            persona_language=persona_language,
            persona_language_source=persona_language_source,
        )
        self._cua_backend_override = cua_backend
        # Accepted for backward-compatible Harbor YAML / --ak, but ignored:
        # task schema recovery lives in task tests + host_verifier, not agent infra.
        if cua_submission_profile:
            logger = getattr(self, "logger", None)
            if logger is not None:
                logger.warning(
                    "cua_submission_profile=%r is deprecated and ignored; "
                    "use task-local verifier recovery from final_answer/trajectory",
                    cua_submission_profile,
                )
        self._delegate_kwargs = dict(kwargs)
        self._delegate: BaseAgent | None = None
        self._delegate_kind: CuaBackendKind | None = None

    def version(self) -> str | None:
        if self._delegate is not None:
            return self._delegate.version()
        return "1.0.0"

    def _get_delegate(self, environment: BaseEnvironment) -> BaseAgent:
        kind = resolve_cua_backend_kind(
            environment,
            override=self._cua_backend_override,
        )
        if self._delegate is None or self._delegate_kind != kind:
            self._delegate = _build_cua_delegate(
                kind,
                logs_dir=self.logs_dir,
                model_name=self.model_name,
                logger=self.logger,
                mcp_servers=self.mcp_servers,
                skills_dir=self.skills_dir,
                delegate_kwargs=self._delegate_kwargs,
                cua_backend=self._cua_backend_override,
            )
            self._delegate_kind = kind
            provider = (
                resolve_desktop_cua_provider(
                    self.model_name, cua_backend=self._cua_backend_override
                )
                if kind == "use_computer_desktop"
                else None
            )
            self.logger.info(
                "persona-computer-1 backend=%s%s for environment %s",
                kind,
                f" provider={provider}" if provider else "",
                type(environment).__name__,
            )
        return self._delegate

    async def setup(self, environment: BaseEnvironment) -> None:
        await self._get_delegate(environment).setup(environment)

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        await self._prepare_persona_trial(environment)
        identity = self._render_persona_system()
        delegate = self._get_delegate(environment)
        if self._delegate_kind == "docker_computer1":
            # Dedicated identity channel: keep task instruction.md pure.
            setattr(delegate, "_identity_prompt", identity)
            await delegate.run(instruction, environment, context)
        else:
            # use.computer / iOS backends only accept one user-text channel.
            composed = self._render_persona_instruction(instruction)
            await delegate.run(composed, environment, context)
        # Task-agnostic hand-in for every CUA backend (macOS/iOS/Docker):
        # mirror final_answer.txt into host logs + /app/output. Named JSON
        # schema recovery belongs in the task verifier, not agent infra.
        await materialize_final_answer_file(
            environment,
            self.logs_dir,
            logger=self.logger,
        )
