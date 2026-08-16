"""Tests for ``matraix results`` job summary / export."""

from __future__ import annotations

import json
from pathlib import Path

from matraix.job_results import (
    SCHEMA_VERSION,
    collect_job_results,
    format_csv_report,
    format_json_report,
    format_text_report,
    parse_formats,
    resolve_job_dir,
)


def _write_trial_shell(
    job: Path,
    trial_name: str,
    *,
    stats: dict | None = None,
    reward: float = 1.0,
    persona: dict | None = None,
    cost_usd: float = 0.012,
) -> Path:
    trial = job / trial_name
    output = trial / "artifacts" / "app" / "output"
    output.mkdir(parents=True)
    if not (job / "result.json").is_file():
        (job / "result.json").write_text(
            json.dumps(
                {
                    "stats": stats
                    or {
                        "n_completed_trials": 1,
                        "n_errored_trials": 0,
                        "n_input_tokens": 1200,
                        "n_output_tokens": 80,
                        "cost_usd": cost_usd,
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
                    "cost_usd": cost_usd,
                },
                "verifier_result": {"rewards": {"reward": reward}},
                "exception_info": None,
            }
        ),
        encoding="utf-8",
    )
    (trial / "persona_meta.json").write_text(
        json.dumps(
            persona
            or {
                "persona_id": "0042",
                "display_name": "Siti Rahman",
                "dimensions": {"life_stage": "early_career"},
            }
        ),
        encoding="utf-8",
    )
    return trial


def _write_survey_job(tmp_path: Path, *, via_structured: bool = False) -> Path:
    job = tmp_path / "jobs" / "demo-survey"
    trial = _write_trial_shell(job, "survey_demo__abc123")
    output = trial / "artifacts" / "app" / "output"
    if via_structured:
        verifier = trial / "verifier"
        verifier.mkdir(parents=True, exist_ok=True)
        (verifier / "structured_output.json").write_text(
            json.dumps(
                {
                    "taskType": "survey",
                    "contexts": [
                        {
                            "contextType": "question_response",
                            "key": "question.q0",
                            "facets": [{"key": "response", "value": "option_a"}],
                        },
                        {
                            "contextType": "question_response",
                            "key": "question.overall_interest",
                            "facets": [{"key": "response", "value": 4}],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
    else:
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


def _write_web_job(tmp_path: Path) -> Path:
    job = tmp_path / "jobs" / "demo-web"
    trial = _write_trial_shell(job, "web_demo__xyz")
    verifier = trial / "verifier"
    verifier.mkdir(parents=True)
    (verifier / "structured_output.json").write_text(
        json.dumps(
            {
                "taskType": "web",
                "contexts": [
                    {
                        "contextType": "task_outcome",
                        "key": "task_outcome.primary",
                        "facets": [{"key": "outcome_status", "value": "passed"}],
                    },
                    {
                        "contextType": "web_artifact",
                        "key": "web_artifact.primary",
                        "facets": [
                            {"key": "artifact_subject_label", "value": "Plus"},
                            {"key": "artifact_subject_id", "value": "plus"},
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return job


def _write_chat_job(tmp_path: Path) -> Path:
    job = tmp_path / "jobs" / "demo-chat"
    trial = _write_trial_shell(job, "chat_demo__xyz")
    verifier = trial / "verifier"
    verifier.mkdir(parents=True)
    (verifier / "structured_output.json").write_text(
        json.dumps(
            {
                "taskType": "chatbot",
                "contexts": [
                    {
                        "contextType": "task_outcome",
                        "key": "task_outcome.primary",
                        "facets": [
                            {"key": "outcome_status", "value": "partially_resolved"}
                        ],
                    },
                    {
                        "contextType": "conversation_summary",
                        "key": "conversation_summary.primary",
                        "facets": [
                            {"key": "conversation_path", "value": "clarify_then_partial"}
                        ],
                    },
                    {
                        "contextType": "user_feedback",
                        "key": "user_feedback.primary",
                        "facets": [
                            {"key": "overall_experience_rating", "value": 4}
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return job


def _write_os_app_job(tmp_path: Path) -> Path:
    job = tmp_path / "jobs" / "demo-os-app"
    trial = _write_trial_shell(job, "os_demo__xyz")
    verifier = trial / "verifier"
    verifier.mkdir(parents=True)
    (verifier / "structured_output.json").write_text(
        json.dumps(
            {
                "taskType": "os-app",
                "contexts": [
                    {
                        "contextType": "task_outcome",
                        "key": "task_outcome.primary",
                        "facets": [{"key": "outcome_status", "value": "passed"}],
                    },
                    {
                        "contextType": "goal_component",
                        "key": "goal_component.viewed_chart",
                        "facets": [
                            {"key": "goal_component_key", "value": "viewed_chart"},
                            {"key": "goal_component_status", "value": "passed"},
                        ],
                    },
                    {
                        "contextType": "decision",
                        "key": "decision.sentiment",
                        "facets": [
                            {"key": "decision_outcome", "value": "hold"},
                            {
                                "key": "decision_subject_label",
                                "value": "Micron Technology (MU)",
                            },
                        ],
                    },
                ],
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
    assert report.app_type == "survey"
    assert report.usage.cost_usd == 0.012
    assert report.trials[0].reward == 1.0
    assert report.question_distributions["q0"] == {"option_a": 1}
    assert report.lens is not None
    assert report.lens.kind == "survey"
    assert "life_stage" in report.grouped_distributions
    assert "early_career" in report.grouped_distributions["life_stage"]


def test_survey_prefers_structured_output(tmp_path: Path) -> None:
    job = _write_survey_job(tmp_path, via_structured=True)
    report = collect_job_results(job)
    assert report.app_type == "survey"
    assert report.lens is not None
    assert report.lens.source == "structured_output"
    assert report.question_distributions["q0"] == {"option_a": 1}


def test_web_chat_os_primary_summaries(tmp_path: Path) -> None:
    web = collect_job_results(_write_web_job(tmp_path))
    assert web.app_type == "web"
    assert web.lens is not None
    assert "Plus" in web.lens.primary_summary
    text = format_text_report(web)
    assert "App: web" in text
    assert "Primary:" in text
    assert "Health:" in text

    chat = collect_job_results(_write_chat_job(tmp_path))
    assert chat.app_type == "chatbot"
    assert chat.lens is not None
    assert "partially_resolved" in chat.lens.primary_summary
    assert any(metric.key == "avg_overall_experience_rating" for metric in chat.lens.metrics)

    os_app = collect_job_results(_write_os_app_job(tmp_path))
    assert os_app.app_type == "os-app"
    assert os_app.lens is not None
    assert "Pass rate" in os_app.lens.primary_summary
    assert any(dist.key == "decision_outcome" for dist in os_app.lens.distributions)


def test_formatters_include_usage_and_answers(tmp_path: Path) -> None:
    job = _write_survey_job(tmp_path)
    report = collect_job_results(job)
    text = format_text_report(report)
    assert "demo-survey" in text
    assert "App: survey" in text
    assert "0.012" in text
    assert "q0" in text
    payload = json.loads(format_json_report(report))
    assert payload["schemaVersion"] == SCHEMA_VERSION
    assert payload["appType"] == "survey"
    assert payload["ledger"]["trials"][0]["survey_answers"]["overall_interest"] == 4
    assert payload["lens"]["kind"] == "survey"
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
