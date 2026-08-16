"""Tests for ``matraix results`` job summary / export."""

from __future__ import annotations

import json
from pathlib import Path

from matraix.job_results import (
    collect_job_results,
    format_csv_report,
    format_json_report,
    format_text_report,
    parse_formats,
    resolve_job_dir,
)


def _write_survey_job(tmp_path: Path) -> Path:
    job = tmp_path / "jobs" / "demo-survey"
    trial = job / "survey_demo__abc123"
    output = trial / "artifacts" / "app" / "output"
    output.mkdir(parents=True)
    (job / "result.json").write_text(
        json.dumps(
            {
                "stats": {
                    "n_completed_trials": 1,
                    "n_errored_trials": 0,
                    "n_input_tokens": 1200,
                    "n_output_tokens": 80,
                    "cost_usd": 0.012,
                }
            }
        ),
        encoding="utf-8",
    )
    (trial / "result.json").write_text(
        json.dumps(
            {
                "agent_result": {
                    "n_input_tokens": 1200,
                    "n_output_tokens": 80,
                    "cost_usd": 0.012,
                },
                "verifier_result": {"rewards": {"reward": 1.0}},
                "exception_info": None,
            }
        ),
        encoding="utf-8",
    )
    (trial / "persona_meta.json").write_text(
        json.dumps(
            {
                "persona_id": "0042",
                "display_name": "Siti Rahman",
                "dimensions": {"life_stage": "early_career"},
            }
        ),
        encoding="utf-8",
    )
    (output / "survey_result.json").write_text(
        json.dumps(
            {
                "answers": [
                    {"questionId": "q0", "value": "option_a"},
                    {"questionId": "overall_interest", "value": 4},
                ]
            }
        ),
        encoding="utf-8",
    )
    return job


def test_resolve_job_dir_by_name(tmp_path: Path, monkeypatch) -> None:
    job = _write_survey_job(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert resolve_job_dir("demo-survey", repo_root=tmp_path) == job.resolve()


def test_collect_job_results_survey_distributions(tmp_path: Path) -> None:
    job = _write_survey_job(tmp_path)
    report = collect_job_results(job, group_by=["life_stage"])
    assert report.n_trials == 1
    assert report.usage.cost_usd == 0.012
    assert report.trials[0].reward == 1.0
    assert report.question_distributions["q0"] == {"option_a": 1}
    assert "life_stage" in report.grouped_distributions
    assert "early_career" in report.grouped_distributions["life_stage"]


def test_formatters_include_usage_and_answers(tmp_path: Path) -> None:
    job = _write_survey_job(tmp_path)
    report = collect_job_results(job)
    text = format_text_report(report)
    assert "demo-survey" in text
    assert "0.012" in text
    assert "q0" in text
    payload = json.loads(format_json_report(report))
    assert payload["trials"][0]["survey_answers"]["overall_interest"] == 4
    csv_text = format_csv_report(report)
    assert "answer_q0" in csv_text
    assert "option_a" in csv_text


def test_parse_formats_rejects_unknown() -> None:
    assert parse_formats("json,csv") == ["json", "csv"]
    try:
        parse_formats("html")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "html" in str(exc)
