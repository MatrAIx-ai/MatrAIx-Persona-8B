"""Shared persona injection helpers for Playground agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from matraix.agents.persona.loader import Persona, load_persona
from matraix.persona_job import SMOKE_PERSONA_PATH
from matraix.persona_dimension_catalog import (
    normalize_persona_language,
    resolve_persona_language,
)
from matraix.agents.persona.templating import (
    PERSONA_INSTRUCTION_TEMPLATE,
    PERSONA_SYSTEM_TEMPLATE,
    render_persona_template,
    resolve_persona_template,
)

if TYPE_CHECKING:
    from harbor.environments.base import BaseEnvironment


class PersonaMixin:
    """Load persona YAML and write trial-level persona_meta.json.

    Injection contract (see docs/application.md § Persona Injection):

    - Persona is **identity** (who the agent is acting as).
    - Task ``instruction.md`` is **task** (what they are trying to do).
    - Prefer a dedicated system / identity channel when the backend supports it
      (``_render_persona_system``). Only fall back to
      ``_render_persona_instruction`` when the backend has a single user-text
      channel — and even then identity must lead, never nest under a harness
      "You are <tool-agent>" + "Task instructions:" wrapper.
    """

    _persona: Persona
    _persona_agent_name: str
    _persona_template_path: Path | None
    _persona_language: str | None
    _persona_language_source: str | None

    def _init_persona(
        self,
        persona_path: str | None,
        agent_name: str,
        *,
        persona_template_path: str | None = None,
        persona_language: str | None = None,
        persona_language_source: str | None = None,
    ) -> None:
        if not persona_path:
            raise ValueError(
                f"{agent_name} requires persona_path "
                f"(pass --ak persona_path={SMOKE_PERSONA_PATH})"
            )
        self._persona = load_persona(persona_path)
        self._persona_agent_name = agent_name
        self._persona_template_path = (
            Path(persona_template_path).expanduser().resolve()
            if persona_template_path
            else None
        )
        self._persona_language = persona_language
        self._persona_language_source = persona_language_source

    @property
    def effective_persona_language(self) -> str:
        """Resolved persona/prompt language (explicit > env > en)."""
        return resolve_persona_language(self._persona_language)

    @property
    def persona_language_source(self) -> str:
        """Where the language came from: explicit | follow_ui | env | default."""
        import os

        requested = normalize_persona_language(self._persona_language)
        env_language = normalize_persona_language(
            os.environ.get("MATRAIX_PERSONA_LANGUAGE")
        )

        # An invalid env value is not provenance.  If an explicit value is
        # valid, preserve its source; otherwise use the valid env value or
        # the English default.
        if requested is not None:
            if self._persona_language_source == "env":
                return "env" if env_language == requested else "explicit"
            return self._persona_language_source or "explicit"
        if env_language is not None:
            return "env"
        return "default"

    def _render_persona_system(self) -> str:
        """Persona identity block for system / identity channels."""
        template = resolve_persona_template(
            self._persona,
            self._persona_template_path,
            PERSONA_SYSTEM_TEMPLATE,
        )
        return render_persona_template(
            template, self._persona, language=self._persona_language
        )

    def _render_persona_instruction(self, instruction: str) -> str:
        """Single-channel fallback: identity first, then the task.

        Prefer ``_render_persona_system`` + a raw task instruction when the
        backend can keep them separate.
        """
        template = resolve_persona_template(
            self._persona,
            self._persona_template_path,
            PERSONA_INSTRUCTION_TEMPLATE,
        )
        return render_persona_template(
            template,
            self._persona,
            instruction=instruction,
            language=self._persona_language,
        )

    def _write_persona_meta(self) -> None:
        logs_dir: Path = self.logs_dir  # type: ignore[attr-defined]
        meta_path = logs_dir.parent / "persona_meta.json"
        meta = self._persona.to_meta(self._persona_agent_name)
        meta["effective_language"] = self.effective_persona_language
        meta["language_source"] = self.persona_language_source
        if self._persona_template_path is not None:
            meta["persona_template_path"] = str(self._persona_template_path)
        meta_path.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    async def _prepare_persona_trial(self, environment: BaseEnvironment) -> None:
        """Write trial meta and upload persona YAML for in-container verifiers."""
        self._write_persona_meta()
        await environment.upload_file(
            self._persona.persona_path,
            "/app/input/persona.yaml",
        )
