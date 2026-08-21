"""Context budgets for the four Playground persona application types.

Types (see ``DEFAULT_AGENT_BY_TYPE``):
  survey  → persona-json-survey
  chatbot → persona-user-sim (generic chat); Vita chat selects persona-uxagent
  web     → persona-openhands-sdk (and other web agents)
  os-app  → persona-computer-1

Full 1290-dim profiles (null/default skipped) are typically ~2–8k tokens and can
approach ~12k on dense personas. Task docs append on top of that. These budgets
reserve headroom so agents do not truncate the persona block to fit the task.
"""

from __future__ import annotations

from typing import Any

# Persona attribute text — never soft-truncate; size after null/default skipping.
PERSONA_PROFILE_TOKEN_BUDGET = 16_000
# Task instruction / questionnaire / tool docs appended beside the persona.
TASK_APPEND_TOKEN_BUDGET = 8_000
# Multi-turn dialogue, screenshots, tool results.
TURN_HEADROOM_TOKEN_BUDGET = 48_000

# Floor for max_input_tokens when launching persona agents (72k).
# Prefer the model's native window when litellm reports a higher value.
RECOMMENDED_MAX_INPUT_TOKENS = (
    PERSONA_PROFILE_TOKEN_BUDGET + TASK_APPEND_TOKEN_BUDGET + TURN_HEADROOM_TOKEN_BUDGET
)

# Output ceilings (not input context) — keep large enough for survey envelopes /
# tool-call replies once the system prompt already carries the full persona.
SURVEY_MAX_OUTPUT_TOKENS = 16_384
CHATBOT_MAX_OUTPUT_TOKENS = 4_096

# computer-1 compaction: keep enough free tokens that persona+task in
# ``original_instruction`` plus the next screenshot still fit.
COMPUTER1_PROACTIVE_FREE_TOKENS = 20_000
COMPUTER1_UNWIND_TARGET_FREE_TOKENS = 12_000


def recommended_max_input_tokens(model_name: str | None = None) -> int:
    """Return a safe max_input_tokens floor for persona agents."""
    _ = model_name
    try:
        from litellm.utils import get_model_info

        if model_name:
            info = get_model_info(model_name)
            reported = info.get("max_input_tokens") or info.get("max_tokens")
            if isinstance(reported, int) and reported > 0:
                return max(reported, RECOMMENDED_MAX_INPUT_TOKENS)
    except Exception:
        pass
    return RECOMMENDED_MAX_INPUT_TOKENS


def persona_llm_model_info(model_name: str | None = None) -> dict[str, Any]:
    """LiteLLM / Harbor ``model_info`` kwargs for persona agent launches."""
    return {
        "max_input_tokens": recommended_max_input_tokens(model_name),
        "max_output_tokens": SURVEY_MAX_OUTPUT_TOKENS,
    }


def apply_persona_context_to_agent_spec(
    agent: dict[str, Any],
    *,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Ensure agent kwargs carry persona-aware ``model_info`` (idempotent)."""
    if not isinstance(agent, dict):
        return agent
    kwargs = agent.setdefault("kwargs", {})
    if not isinstance(kwargs, dict):
        return agent
    model = model_name or agent.get("model_name")
    existing = kwargs.get("model_info")
    recommended = persona_llm_model_info(str(model) if model else None)
    if isinstance(existing, dict):
        merged = dict(existing)
        for key, value in recommended.items():
            current = merged.get(key)
            if not isinstance(current, int) or current < value:
                merged[key] = value
        kwargs["model_info"] = merged
    else:
        kwargs["model_info"] = recommended
    return agent
