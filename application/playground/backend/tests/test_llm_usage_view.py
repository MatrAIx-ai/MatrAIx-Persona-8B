"""Tests for Harbor token/cost usage normalization."""

from __future__ import annotations

import json
from pathlib import Path

from backend.service.llm_usage_view import (
    format_cost_usd,
    usage_from_job_result,
    usage_from_trial_dir,
    usage_from_trial_result,
    usage_meta_lines,
)


def test_usage_from_trial_agent_result():
    usage = usage_from_trial_result(
        {
            "agent_result": {
                "n_input_tokens": 1200,
                "n_output_tokens": 340,
                "n_cache_tokens": 100,
                "cost_usd": 0.0123,
            }
        }
    )
    assert usage == {
        "nInputTokens": 1200,
        "nOutputTokens": 340,
        "nCacheTokens": 100,
        "costUsd": 0.0123,
    }


def test_usage_from_trial_step_results_sums():
    usage = usage_from_trial_result(
        {
            "step_results": [
                {"agent_result": {"n_input_tokens": 100, "cost_usd": 0.01}},
                {"agent_result": {"n_input_tokens": 50, "n_output_tokens": 20, "cost_usd": 0.02}},
            ]
        }
    )
    assert usage == {
        "nInputTokens": 150,
        "nOutputTokens": 20,
        "costUsd": 0.03,
    }


def test_usage_from_job_result_stats():
    usage = usage_from_job_result(
        {
            "stats": {
                "n_input_tokens": 5000,
                "n_output_tokens": 900,
                "cost_usd": 1.25,
            }
        }
    )
    assert usage == {
        "nInputTokens": 5000,
        "nOutputTokens": 900,
        "costUsd": 1.25,
    }


def test_usage_from_trial_dir(tmp_path: Path):
    trial = tmp_path / "trial"
    trial.mkdir()
    (trial / "result.json").write_text(
        json.dumps({"agent_result": {"n_input_tokens": 10, "cost_usd": 0.001}}),
        encoding="utf-8",
    )
    assert usage_from_trial_dir(trial) == {"nInputTokens": 10, "costUsd": 0.001}


def test_usage_meta_lines_and_cost_format():
    assert format_cost_usd(1.2) == "$1.20"
    assert format_cost_usd(0.0123) == "$0.012"
    lines = usage_meta_lines(
        {"nInputTokens": 1200, "nOutputTokens": 40, "costUsd": 0.05}
    )
    assert lines[0] == "Cost: $0.050"
    assert "1,200 in" in lines[1]
    assert "40 out" in lines[1]
