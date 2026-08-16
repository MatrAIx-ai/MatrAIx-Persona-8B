"""Tests for ``matraix smoke`` (host Survey, zero-cost)."""

from __future__ import annotations

from pathlib import Path

from matraix.smoke import format_smoke_report, run_survey_smoke


def test_survey_smoke_example_task() -> None:
    root = Path(__file__).resolve().parents[3]
    report = run_survey_smoke(
        "application/tasks/example-survey_product-feedback",
        repo_root=root,
        personas=1,
        keep_artifacts=True,
    )
    assert report.ok, report.errors
    assert report.mode == "fake"
    assert report.cost_usd == 0.0
    assert report.logical_calls == 1
    assert report.trial_profile == "json_survey"
    text = format_smoke_report(report)
    assert "Smoke: ok" in text
    assert "cost $0" in text


def test_survey_smoke_rejects_non_survey(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    task = tmp_path / "not-a-survey"
    task.mkdir()
    (task / "task.toml").write_text(
        '[metadata]\ntype = "web"\n',
        encoding="utf-8",
    )
    report = run_survey_smoke(task, repo_root=root)
    assert not report.ok
    assert any("Survey" in error for error in report.errors)


def test_survey_smoke_missing_questionnaire(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    task = tmp_path / "broken-survey"
    task.mkdir()
    (task / "task.toml").write_text(
        '[metadata]\ntype = "survey"\n',
        encoding="utf-8",
    )
    report = run_survey_smoke(task, repo_root=root)
    assert not report.ok
    assert any("questionnaire" in error.lower() for error in report.errors)


def test_cli_smoke_ok(monkeypatch, capsys) -> None:
    from matraix import cli

    root = Path(__file__).resolve().parents[3]
    monkeypatch.chdir(root)
    cli.main(
        [
            "smoke",
            "application/tasks/example-survey_product-feedback",
            "--repo-root",
            str(root),
        ]
    )
    out = capsys.readouterr().out
    assert "Smoke: ok" in out
    assert "json_survey" in out
