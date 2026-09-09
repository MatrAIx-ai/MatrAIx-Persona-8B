"""Tests for sharded job-level result.json rollup."""

from __future__ import annotations

from pathlib import Path

from backend.service.job_result_rollup import expected_trial_count, synthesize_job_result


def test_expected_trial_count() -> None:
    assert expected_trial_count({"agents": [{}, {}, {}], "tasks": [{}], "n_attempts": 1}) == 3


def test_synthesize_job_result_counts_trials(tmp_path: Path) -> None:
    job_dir = tmp_path / "jobs" / "demo"
    ok = job_dir / "t_ok"
    bad = job_dir / "t_bad"
    ok.mkdir(parents=True)
    bad.mkdir(parents=True)
    (ok / "result.json").write_text("{}\n", encoding="utf-8")
    (bad / "result.json").write_text(
        '{"exception_info": {"exception_type": "TimeoutError"}}\n',
        encoding="utf-8",
    )
    (job_dir / "_generated").mkdir()
    path = synthesize_job_result(
        job_dir,
        job_config={"agents": [{}, {}, {}, {}], "tasks": [{}]},
        started_at="2026-01-01T00:00:00Z",
        finished=True,
    )
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))
    assert payload["n_total_trials"] == 4
    assert payload["stats"]["n_completed_trials"] == 2
    assert payload["stats"]["n_errored_trials"] == 3
    assert payload["finished_at"]
    assert "trial_results" not in payload
