"""Assemble tool-driven user simulator prompts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from playground.persona_language import (
    persona_language_contract,
    resolve_persona_language,
)
from playground.task_content_bundle import TaskContentBundle
from playground.types import Persona

_GUIDELINES_PATH = Path(__file__).resolve().parent / "sim_guidelines.md"
def load_sim_guidelines() -> str:
    return _GUIDELINES_PATH.read_text(encoding="utf-8").strip()


def current_date_block(*, now: datetime | None = None) -> str:
    """Tell the persona what today/now is (host clock)."""
    moment = now or datetime.now().astimezone()
    return "Today is {weekday}, {month} {day}, {year}, {time}.".format(
        weekday=moment.strftime("%A"),
        month=moment.strftime("%B"),
        day=moment.day,
        year=moment.year,
        time=moment.strftime("%H:%M %Z").strip(),
    )


def _persona_context(persona: Persona) -> str:
    if persona.context:
        return persona.context
    parts = [
        "Name: {}".format(persona.name),
        "Who you are: {}".format(persona.summary or "(a typical user)"),
        "What you want (preferences): {}".format(", ".join(persona.preferences) or "(open)"),
        "What you dislike: {}".format(", ".join(persona.dislikes) or "(none stated)"),
        "Your constraints: {}".format(", ".join(persona.constraints) or "(flexible)"),
        "Your goal: {}".format(persona.goal or "(find something suitable)"),
        "How you talk: {}".format(persona.communication_style or "natural and conversational"),
    ]
    return "\n".join(parts)


def render_persona_block(
    persona: Persona,
    *,
    persona_yaml_path: Optional[str] = None,
    persona_language: Optional[str] = None,
) -> str:
    effective_language = resolve_persona_language(persona_language)
    if persona_yaml_path:
        try:
            from matraix.agents.persona.loader import load_persona
            from matraix.agents.persona.templating import (
                PERSONA_SYSTEM_TEMPLATE,
                render_persona_template,
                resolve_persona_template,
            )

            loaded = load_persona(persona_yaml_path)
            template = resolve_persona_template(loaded, None, PERSONA_SYSTEM_TEMPLATE)
            return render_persona_template(
                template,
                loaded,
                language=effective_language,
            ).strip()
        except Exception:
            pass
    return "{}\n\n{}".format(
        _persona_context(persona),
        persona_language_contract(effective_language),
    ).strip()


def _section(title: str, body: str) -> str:
    text = (body or "").strip()
    if not text:
        return ""
    return "## {}\n{}".format(title, text)


def assemble_system_prompt(
    persona: Persona,
    *,
    persona_yaml_path: Optional[str] = None,
    task_bundle: Optional[TaskContentBundle] = None,
    persona_language: Optional[str] = None,
) -> str:
    task_bundle = task_bundle or TaskContentBundle()
    blocks = [
        render_persona_block(
            persona,
            persona_yaml_path=persona_yaml_path,
            persona_language=persona_language,
        ),
        current_date_block(),
        load_sim_guidelines(),
        _section("Task instruction", task_bundle.instruction_markdown),
        _section("Task context", task_bundle.context_markdown),
    ]
    return "\n\n".join(block for block in blocks if block.strip())


def assemble_report_system_prompt(
    persona: Persona,
    *,
    persona_yaml_path: Optional[str] = None,
    task_bundle: Optional[TaskContentBundle] = None,
    persona_language: Optional[str] = None,
) -> str:
    task_bundle = task_bundle or TaskContentBundle()
    blocks = [
        render_persona_block(
            persona,
            persona_yaml_path=persona_yaml_path,
            persona_language=persona_language,
        ),
        current_date_block(),
        _section("Task instruction", task_bundle.instruction_markdown),
        _section("Task context", task_bundle.context_markdown),
    ]
    return "\n\n".join(block for block in blocks if block.strip())


def prompt_bundle(
    persona: Persona,
    *,
    persona_yaml_path: Optional[str] = None,
    task_bundle: Optional[TaskContentBundle] = None,
    task_prompt: str = "",
    persona_language: Optional[str] = None,
) -> dict[str, str]:
    task_bundle = task_bundle or TaskContentBundle()
    persona_block = render_persona_block(
        persona,
        persona_yaml_path=persona_yaml_path,
        persona_language=persona_language,
    )
    system = assemble_system_prompt(
        persona,
        persona_yaml_path=persona_yaml_path,
        task_bundle=task_bundle,
        persona_language=persona_language,
    )

    task_parts: list[str] = []
    instruction_block = _section("Task instruction", task_bundle.instruction_markdown)
    context_block = _section("Task context", task_bundle.context_markdown)
    if instruction_block:
        task_parts.append(instruction_block)
    if context_block:
        task_parts.append(context_block)
    kickoff = (task_prompt or "").strip()
    if kickoff:
        task_parts.append("## Application kickoff\n{}".format(kickoff))

    return {
        "personaPrompt": persona_block.strip(),
        "harborPrompt": system,
        "taskPrompt": "\n\n".join(task_parts).strip(),
    }
