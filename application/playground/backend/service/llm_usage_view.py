"""Normalize Harbor token/cost receipts for Playground UI and PDF reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value.strip()))
        except ValueError:
            return None
    return None


def _as_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _first_int(mapping: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = _as_int(mapping.get(key))
        if value is not None:
            return value
    return None


def _first_float(mapping: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _as_float(mapping.get(key))
        if value is not None:
            return value
    return None


def _usage_payload(
    *,
    n_input_tokens: int | None,
    n_output_tokens: int | None,
    n_cache_tokens: int | None,
    cost_usd: float | None,
) -> dict[str, int | float] | None:
    payload: dict[str, int | float] = {}
    if n_input_tokens is not None:
        payload["nInputTokens"] = n_input_tokens
    if n_output_tokens is not None:
        payload["nOutputTokens"] = n_output_tokens
    if n_cache_tokens is not None:
        payload["nCacheTokens"] = n_cache_tokens
    if cost_usd is not None:
        payload["costUsd"] = cost_usd
    return payload or None


def _sum_optional_ints(values: list[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def _sum_optional_floats(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return float(sum(present))


def usage_from_agent_context(ctx: object) -> dict[str, int | float] | None:
    """Extract usage from one AgentContext-like mapping."""
    if not isinstance(ctx, dict):
        return None
    return _usage_payload(
        n_input_tokens=_first_int(ctx, "n_input_tokens", "nInputTokens"),
        n_output_tokens=_first_int(ctx, "n_output_tokens", "nOutputTokens"),
        n_cache_tokens=_first_int(ctx, "n_cache_tokens", "nCacheTokens"),
        cost_usd=_first_float(ctx, "cost_usd", "costUsd"),
    )


def usage_from_trial_result(result: object) -> dict[str, int | float] | None:
    """Aggregate usage from a Harbor trial ``result.json`` payload."""
    if not isinstance(result, dict):
        return None

    agent_result = result.get("agent_result")
    if isinstance(agent_result, dict):
        direct = usage_from_agent_context(agent_result)
        if direct is not None:
            return direct

    step_results = result.get("step_results")
    if not isinstance(step_results, list):
        return None

    contexts = [
        step.get("agent_result")
        for step in step_results
        if isinstance(step, dict) and isinstance(step.get("agent_result"), dict)
    ]
    if not contexts:
        return None

    typed_contexts = [ctx for ctx in contexts if isinstance(ctx, dict)]
    return _usage_payload(
        n_input_tokens=_sum_optional_ints(
            [_first_int(ctx, "n_input_tokens", "nInputTokens") for ctx in typed_contexts]
        ),
        n_output_tokens=_sum_optional_ints(
            [_first_int(ctx, "n_output_tokens", "nOutputTokens") for ctx in typed_contexts]
        ),
        n_cache_tokens=_sum_optional_ints(
            [_first_int(ctx, "n_cache_tokens", "nCacheTokens") for ctx in typed_contexts]
        ),
        cost_usd=_sum_optional_floats(
            [_first_float(ctx, "cost_usd", "costUsd") for ctx in typed_contexts]
        ),
    )


def usage_from_job_result(result: object) -> dict[str, int | float] | None:
    """Extract rolled-up usage from a Harbor job ``result.json`` payload."""
    if not isinstance(result, dict):
        return None
    stats = result.get("stats")
    if not isinstance(stats, dict):
        return None
    return _usage_payload(
        n_input_tokens=_as_int(stats.get("n_input_tokens")),
        n_output_tokens=_as_int(stats.get("n_output_tokens")),
        n_cache_tokens=_as_int(stats.get("n_cache_tokens")),
        cost_usd=_as_float(stats.get("cost_usd")),
    )


def usage_from_trial_dir(trial_dir: Path) -> dict[str, int | float] | None:
    path = trial_dir / "result.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return usage_from_trial_result(payload)


def format_cost_usd(value: float) -> str:
    if abs(value) >= 1:
        return f"${value:,.2f}"
    if abs(value) >= 0.01:
        return f"${value:,.3f}"
    return f"${value:.4f}"


def format_token_count(value: int) -> str:
    return f"{value:,}"


def usage_meta_lines(usage: dict[str, int | float] | None) -> list[str]:
    """Human-readable usage lines for PDF / CLI meta blocks."""
    if not usage:
        return []
    lines: list[str] = []
    cost = usage.get("costUsd")
    if isinstance(cost, (int, float)):
        lines.append(f"Cost: {format_cost_usd(float(cost))}")
    bits: list[str] = []
    n_in = usage.get("nInputTokens")
    n_out = usage.get("nOutputTokens")
    n_cache = usage.get("nCacheTokens")
    if isinstance(n_in, int):
        bits.append(f"{format_token_count(n_in)} in")
    if isinstance(n_out, int):
        bits.append(f"{format_token_count(n_out)} out")
    if isinstance(n_cache, int) and n_cache > 0:
        bits.append(f"{format_token_count(n_cache)} cache")
    if bits:
        lines.append(f"Tokens: {' · '.join(bits)}")
    return lines
