from pathlib import Path

import pytest

from playground.budget import (
    BudgetExceededError,
    assert_budget_allows_request,
    max_cost_usd_from_env,
    read_spent_usd,
    record_trial_cost,
)
from playground.llm_usage import (
    usage_from_anthropic_payload,
    usage_from_openai_completion,
)


class _Usage:
    def __init__(self, prompt_tokens, completion_tokens, cached_tokens=None):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        if cached_tokens is None:
            self.prompt_tokens_details = None
        else:
            self.prompt_tokens_details = type(
                "Details", (), {"cached_tokens": cached_tokens}
            )()


class _Completion:
    def __init__(self, *, prompt_tokens, completion_tokens, cached_tokens=None, id="chatcmpl-1"):
        self.usage = _Usage(prompt_tokens, completion_tokens, cached_tokens)
        self.id = id


def test_usage_from_openai_completion_extracts_tokens() -> None:
    usage = usage_from_openai_completion(
        _Completion(prompt_tokens=100, completion_tokens=20, cached_tokens=10),
        model="gpt-4o-mini",
        provider="openai",
    )
    assert usage.n_input_tokens == 100
    assert usage.n_output_tokens == 20
    assert usage.n_cache_tokens == 10
    assert usage.request_id == "chatcmpl-1"
    assert usage.provider == "openai"


def test_usage_from_anthropic_payload_extracts_tokens() -> None:
    usage = usage_from_anthropic_payload(
        {
            "id": "msg_123",
            "usage": {
                "input_tokens": 50,
                "output_tokens": 12,
                "cache_read_input_tokens": 5,
            },
        },
        model="claude-sonnet-4-6",
    )
    assert usage.n_input_tokens == 50
    assert usage.n_output_tokens == 12
    assert usage.n_cache_tokens == 5
    assert usage.request_id == "msg_123"
    assert usage.provider == "anthropic"


def test_budget_gate_refuses_when_spent_meets_max(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MATRIX_MAX_COST_USD", "0.01")
    record_trial_cost(tmp_path, 0.01)
    assert read_spent_usd(tmp_path) == pytest.approx(0.01)
    with pytest.raises(BudgetExceededError):
        assert_budget_allows_request(tmp_path)


def test_budget_record_raises_when_trial_pushes_over(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MATRIX_MAX_COST_USD", "0.05")
    record_trial_cost(tmp_path, 0.04)
    with pytest.raises(BudgetExceededError):
        record_trial_cost(tmp_path, 0.02)


def test_merge_usage_sums_tokens_and_costs() -> None:
    from playground.llm_usage import LlmUsage, merge_usage

    total = merge_usage(
        LlmUsage(
            n_input_tokens=10,
            n_output_tokens=2,
            cost_usd=0.01,
            cost_source="estimated",
            provider="openai",
            model="gpt-4o-mini",
        ),
        LlmUsage(
            n_input_tokens=5,
            n_output_tokens=3,
            cost_usd=0.02,
            cost_source="provider",
            provider="openai",
            model="gpt-4o-mini",
            request_id="req-2",
        ),
    )
    assert total is not None
    assert total.n_input_tokens == 15
    assert total.n_output_tokens == 5
    assert total.cost_usd == pytest.approx(0.03)
    assert total.cost_source == "estimated"
    assert total.request_id == "req-2"


def test_max_cost_usd_from_env_none_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("MATRIX_MAX_COST_USD", raising=False)
    assert max_cost_usd_from_env() is None
