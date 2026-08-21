"""Persona-backed Harbor agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "Persona",
    "PersonaBrowserUse",
    "PersonaClaudeCode",
    "PersonaCocoa",
    "PersonaCodex",
    "PersonaComputer1",
    "PersonaGeminiCli",
    "PersonaOpenHandsSDK",
    "PersonaUXAgent",
    "load_persona",
    "resolve_persona_path",
]

if TYPE_CHECKING:
    from matraix.agents.persona.browser_use import PersonaBrowserUse
    from matraix.agents.persona.claude_code import PersonaClaudeCode
    from matraix.agents.persona.cocoa import PersonaCocoa
    from matraix.agents.persona.codex import PersonaCodex
    from matraix.agents.persona.computer_1 import PersonaComputer1
    from matraix.agents.persona.gemini_cli import PersonaGeminiCli
    from matraix.agents.persona.loader import (
        Persona,
        load_persona,
        resolve_persona_path,
    )
    from matraix.agents.persona.openhands_sdk import PersonaOpenHandsSDK
    from matraix.agents.persona.uxagent import PersonaUXAgent

_LAZY_IMPORTS = {
    "Persona": ("matraix.agents.persona.loader", "Persona"),
    "PersonaBrowserUse": (
        "matraix.agents.persona.browser_use",
        "PersonaBrowserUse",
    ),
    "PersonaClaudeCode": (
        "matraix.agents.persona.claude_code",
        "PersonaClaudeCode",
    ),
    "PersonaCocoa": ("matraix.agents.persona.cocoa", "PersonaCocoa"),
    "PersonaCodex": ("matraix.agents.persona.codex", "PersonaCodex"),
    "PersonaComputer1": (
        "matraix.agents.persona.computer_1",
        "PersonaComputer1",
    ),
    "PersonaGeminiCli": (
        "matraix.agents.persona.gemini_cli",
        "PersonaGeminiCli",
    ),
    "PersonaOpenHandsSDK": (
        "matraix.agents.persona.openhands_sdk",
        "PersonaOpenHandsSDK",
    ),
    "PersonaUXAgent": (
        "matraix.agents.persona.uxagent",
        "PersonaUXAgent",
    ),
    "load_persona": ("matraix.agents.persona.loader", "load_persona"),
    "resolve_persona_path": (
        "matraix.agents.persona.loader",
        "resolve_persona_path",
    ),
}


def __getattr__(name: str):
    if name not in _LAZY_IMPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_path, attr_name = _LAZY_IMPORTS[name]
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, attr_name)
