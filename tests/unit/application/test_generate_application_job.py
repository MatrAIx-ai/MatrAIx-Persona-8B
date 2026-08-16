"""Tests for application job generation helpers."""

from __future__ import annotations

from pathlib import Path

from matraix.application_job import collect_run_env_exports
from matraix.provider_credentials import export_hint_lines, resolve_provider_credential

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_collect_run_env_exports_survey() -> None:
    exports = collect_run_env_exports(
        trial_profile="json_survey",
        task_path="application/tasks/example-survey_product-feedback",
        repo_root=REPO_ROOT,
    )
    assert exports == [("MATRIX_SURVEY_TASK_PATH", "application/tasks/example-survey_product-feedback")]


def test_collect_run_env_exports_chat() -> None:
    exports = collect_run_env_exports(
        trial_profile="user_sim_chat",
        task_path="application/tasks/chat_meal-planning-nutrition",
        repo_root=REPO_ROOT,
    )
    assert exports == [
        ("MATRIX_CHATBOT_TASK_PATH", "application/tasks/chat_meal-planning-nutrition")
    ]


def test_export_hint_lines_are_provider_aware() -> None:
    assert export_hint_lines("openai/gpt-4o-mini") == ["export OPENAI_API_KEY=..."]
    assert export_hint_lines("dashscope/deepseek-v3.2") == [
        "export DASHSCOPE_API_KEY=..."
    ]
    assert resolve_provider_credential("openai/gpt-4o-mini").env_var != "ANTHROPIC_API_KEY"
