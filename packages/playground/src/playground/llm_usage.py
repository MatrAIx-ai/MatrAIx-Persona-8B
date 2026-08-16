"""LLM usage / cost metadata for JSON-mode Survey (and similar) clients.

Harbor trial results already roll up ``AgentContext.n_*_tokens`` and
``cost_usd``. Survey clients historically returned only parsed JSON; this
module is the shared shape they now populate so those fields stop staying null
(issue #78 P1-A).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class LlmUsage:
    """Token and cost metadata for one LLM completion."""

    n_input_tokens: int | None = None
    n_output_tokens: int | None = None
    n_cache_tokens: int | None = None
    cost_usd: float | None = None
    request_id: str | None = None
    model: str | None = None
    provider: str | None = None
    # "provider" when the API/SDK reported cost; "estimated" when derived from
    # a local price table; None when cost is unknown.
    cost_source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class JsonCompletion:
    """Parsed JSON payload plus optional usage metadata."""

    data: dict[str, Any]
    usage: LlmUsage | None = None


def usage_from_openai_completion(
    completion: Any,
    *,
    model: str,
    provider: str,
) -> LlmUsage:
    """Extract usage from an OpenAI SDK ``ChatCompletion`` (or compatible)."""
    usage_obj = getattr(completion, "usage", None)
    n_input = _maybe_int(getattr(usage_obj, "prompt_tokens", None) if usage_obj else None)
    n_output = _maybe_int(
        getattr(usage_obj, "completion_tokens", None) if usage_obj else None
    )
    n_cache = None
    if usage_obj is not None:
        details = getattr(usage_obj, "prompt_tokens_details", None)
        if details is not None:
            n_cache = _maybe_int(getattr(details, "cached_tokens", None))
        # Some OpenAI-compatible providers put cache under usage.directly.
        if n_cache is None:
            n_cache = _maybe_int(getattr(usage_obj, "prompt_cache_hit_tokens", None))

    request_id = getattr(completion, "id", None)
    if request_id is not None:
        request_id = str(request_id)

    cost_usd, cost_source = estimate_completion_cost_usd(
        model=model,
        n_input_tokens=n_input,
        n_output_tokens=n_output,
        n_cache_tokens=n_cache,
        completion=completion,
    )
    return LlmUsage(
        n_input_tokens=n_input,
        n_output_tokens=n_output,
        n_cache_tokens=n_cache,
        cost_usd=cost_usd,
        request_id=request_id,
        model=model,
        provider=provider,
        cost_source=cost_source,
    )


def usage_from_anthropic_payload(
    payload: Mapping[str, Any],
    *,
    model: str,
) -> LlmUsage:
    """Extract usage from an Anthropic Messages API JSON body."""
    usage_obj = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    n_input = _maybe_int(usage_obj.get("input_tokens"))
    n_output = _maybe_int(usage_obj.get("output_tokens"))
    cache_read = _maybe_int(usage_obj.get("cache_read_input_tokens")) or 0
    cache_create = _maybe_int(usage_obj.get("cache_creation_input_tokens")) or 0
    n_cache = (cache_read + cache_create) or None
    request_id = payload.get("id")
    if request_id is not None:
        request_id = str(request_id)
    cost_usd, cost_source = estimate_completion_cost_usd(
        model=f"anthropic/{model}" if "/" not in model else model,
        n_input_tokens=n_input,
        n_output_tokens=n_output,
        n_cache_tokens=n_cache,
    )
    return LlmUsage(
        n_input_tokens=n_input,
        n_output_tokens=n_output,
        n_cache_tokens=n_cache,
        cost_usd=cost_usd,
        request_id=request_id,
        model=model,
        provider="anthropic",
        cost_source=cost_source,
    )


def estimate_completion_cost_usd(
    *,
    model: str,
    n_input_tokens: int | None,
    n_output_tokens: int | None,
    n_cache_tokens: int | None = None,
    completion: Any = None,
) -> tuple[float | None, str | None]:
    """Return ``(cost_usd, cost_source)`` using LiteLLM when possible.

    Returns ``(None, None)`` when pricing is unknown — never invents ``0.0``.
    """
    if completion is not None:
        hidden = getattr(completion, "_hidden_params", None)
        if isinstance(hidden, dict):
            response_cost = hidden.get("response_cost")
            if response_cost is not None:
                try:
                    value = float(response_cost)
                except (TypeError, ValueError):
                    value = None
                if value is not None and value > 0:
                    return value, "provider"
        try:
            import litellm

            cost = litellm.completion_cost(completion_response=completion)
            if cost is not None and float(cost) > 0:
                return float(cost), "estimated"
        except Exception:
            pass

    if n_input_tokens is None and n_output_tokens is None:
        return None, None
    try:
        import litellm

        model_cost = getattr(litellm, "model_cost", None) or {}
        rates = _lookup_model_rates(model_cost, model)
        if rates is None:
            return None, None
        prompt_rate = float(rates.get("input_cost_per_token") or 0.0)
        completion_rate = float(rates.get("output_cost_per_token") or 0.0)
        cache_rate = float(
            rates.get("cache_read_input_token_cost")
            or rates.get("cache_creation_input_token_cost")
            or prompt_rate
        )
        cost = 0.0
        if n_input_tokens:
            # Harbor convention: n_input includes cache; subtract cache before
            # applying the full prompt rate when both are present.
            billable_input = n_input_tokens
            if n_cache_tokens:
                billable_input = max(0, n_input_tokens - n_cache_tokens)
                cost += n_cache_tokens * cache_rate
            cost += billable_input * prompt_rate
        if n_output_tokens:
            cost += n_output_tokens * completion_rate
        if cost <= 0:
            return None, None
        return cost, "estimated"
    except Exception:
        return None, None


def _lookup_model_rates(model_cost: Mapping[str, Any], model: str) -> dict[str, Any] | None:
    candidates = [model]
    if "/" in model:
        candidates.append(model.split("/", 1)[1])
        # LiteLLM often keys Claude as anthropic/claude-...
        bare = model.split("/", 1)[1]
        if not model.startswith("anthropic/") and bare.startswith("claude"):
            candidates.append(f"anthropic/{bare}")
    for key in candidates:
        rates = model_cost.get(key)
        if isinstance(rates, dict) and (
            rates.get("input_cost_per_token") is not None
            or rates.get("output_cost_per_token") is not None
        ):
            return rates
    return None


def _maybe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
