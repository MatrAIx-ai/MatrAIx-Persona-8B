"""Tests for ``matraix run`` Playground dispatch helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from matraix.job_run import (
    launch_kwargs_from_job_config,
    should_dispatch_via_playground,
    wait_for_harbor_job,
)


def _write_recipe(
    tmp_path: Path,
    *,
    sidecar: dict | None = None,
    yaml_body: str | None = None,
) -> Path:
    folder = tmp_path / "configs" / "jobs" / "application-task-job-recipe"
    folder.mkdir(parents=True, exist_ok=True)
    config = folder / "survey.yaml"
    config.write_text(
        yaml_body
        or (
            "job_name: cli-survey\n"
            "jobs_dir: jobs\n"
            "n_concurrent_trials: 32\n"
            "agents:\n"
            "  - name: persona-json-survey\n"
            "    model_name: anthropic/claude-haiku-4-5\n"
            "tasks:\n"
            "  - path: application/tasks/example-survey_product-feedback\n"
        ),
        encoding="utf-8",
    )
    if sidecar is not None:
        config.with_suffix(".meta.json").write_text(
            json.dumps(sidecar), encoding="utf-8"
        )
    return config


def test_should_dispatch_local_sidecar_stays_on_harbor(tmp_path: Path) -> None:
    config = _write_recipe(
        tmp_path,
        sidecar={
            "task": "application/tasks/example-survey_product-feedback",
            "trial_profile": "json_survey",
            "execution_mode": "auto",
            "computeFamily": "local",
        },
    )
    dispatch, family = should_dispatch_via_playground(
        config_path=config, cli_family=None
    )
    assert dispatch is False
    assert family == "local"


def test_should_dispatch_modal_sidecar(tmp_path: Path) -> None:
    config = _write_recipe(
        tmp_path,
        sidecar={
            "task": "application/tasks/example-survey_product-feedback",
            "trial_profile": "json_survey",
            "execution_mode": "auto",
            "computeFamily": "modal",
        },
    )
    dispatch, family = should_dispatch_via_playground(
        config_path=config, cli_family=None
    )
    assert dispatch is True
    assert family == "modal"


def test_cli_family_overrides_sidecar(tmp_path: Path) -> None:
    config = _write_recipe(
        tmp_path,
        sidecar={
            "task": "application/tasks/example-survey_product-feedback",
            "trial_profile": "json_survey",
            "execution_mode": "auto",
            "computeFamily": "modal",
        },
    )
    dispatch, family = should_dispatch_via_playground(
        config_path=config, cli_family="local"
    )
    assert dispatch is False
    assert family == "local"


def test_env_compute_family_does_not_hijack_local_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MATRIX_COMPUTE_FAMILY", "modal")
    config = _write_recipe(tmp_path)
    dispatch, family = should_dispatch_via_playground(
        config_path=config, cli_family=None
    )
    assert dispatch is False
    assert family is None


def test_launch_kwargs_from_sidecar_and_yaml(tmp_path: Path) -> None:
    config = _write_recipe(
        tmp_path,
        sidecar={
            "task": "application/tasks/example-survey_product-feedback",
            "selected_persona_ids": ["0042", "0007"],
            "seed": 42,
            "execution_mode": "auto",
            "trial_profile": "json_survey",
            "computeFamily": "modal",
            "retrieval": {"pool": "persona/datasets/matraix-persona-dev-sample"},
        },
    )
    kwargs = launch_kwargs_from_job_config(config, compute_family="modal")
    assert kwargs["task_path"] == "application/tasks/example-survey_product-feedback"
    assert kwargs["persona_ids"] == ["0042", "0007"]
    assert kwargs["persona_pool"] == "persona/datasets/matraix-persona-dev-sample"
    assert kwargs["job_name"] == "cli-survey"
    assert kwargs["n_concurrent_trials"] == 32
    assert kwargs["agent_name"] == "persona-json-survey"
    assert kwargs["persona_model"] == "anthropic/claude-haiku-4-5"
    assert kwargs["compute_family"] == "modal"
    assert kwargs["seed"] == 42


def test_launch_kwargs_requires_sidecar_task(tmp_path: Path) -> None:
    config = _write_recipe(tmp_path)
    with pytest.raises(ValueError, match="sidecar task"):
        launch_kwargs_from_job_config(config, compute_family="modal")


def test_wait_for_harbor_job_returns_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fake:
        def __init__(self) -> None:
            self.calls = 0

        def get_job(self, job_name: str) -> dict:
            self.calls += 1
            if self.calls < 2:
                return {"launch": {"status": "running"}}
            return {"launch": {"status": "completed"}}

    monkeypatch.setattr("matraix.job_run.time.sleep", lambda _s: None)
    detail = wait_for_harbor_job(Fake(), "job-1", poll_s=0)
    assert detail["launch"]["status"] == "completed"


def test_wait_for_harbor_job_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fake:
        def get_job(self, job_name: str) -> dict:
            return {"launch": {"status": "running"}}

    monkeypatch.setattr("matraix.job_run.time.sleep", lambda _s: None)
    with pytest.raises(TimeoutError, match="timed out waiting"):
        wait_for_harbor_job(Fake(), "job-1", poll_s=0, timeout_s=0)


def test_run_via_harbor_job_service_forwards_launch_kwargs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import types

    from matraix.job_run import run_via_harbor_job_service

    config = _write_recipe(
        tmp_path,
        sidecar={
            "task": "application/tasks/example-survey_product-feedback",
            "selected_persona_ids": ["0042"],
            "seed": 7,
            "execution_mode": "auto",
            "trial_profile": "json_survey",
            "computeFamily": "modal",
            "retrieval": {"pool": "persona/datasets/matraix-persona-dev-sample"},
        },
    )
    captured: dict[str, object] = {}

    class FakeService:
        def launch(self, **kwargs):
            captured.update(kwargs)
            return "launched-job"

        def get_job(self, job_name: str) -> dict:
            return {"launch": {"status": "completed"}}

        def shutdown(self) -> None:
            captured["shutdown"] = True

    class HarborJobService:
        @classmethod
        def from_repo(cls, *, repo_root, jobs_dir=None):
            captured["repo_root"] = repo_root
            captured["jobs_dir"] = jobs_dir
            return FakeService()

    for name in ("backend", "backend.service"):
        if name not in sys.modules:
            pkg = types.ModuleType(name)
            pkg.__path__ = []  # type: ignore[attr-defined]
            monkeypatch.setitem(sys.modules, name, pkg)

    fake_mod = types.ModuleType("backend.service.harbor_job_service")
    fake_mod.HarborJobService = HarborJobService
    monkeypatch.setitem(sys.modules, "backend.service.harbor_job_service", fake_mod)
    monkeypatch.setattr("matraix.job_run.time.sleep", lambda _s: None)

    code = run_via_harbor_job_service(
        config_path=config,
        repo_root=tmp_path,
        compute_family="modal",
        execution_plane="harbor",
    )
    assert code == 0
    assert captured["compute_family"] == "modal"
    assert captured["persona_ids"] == ["0042"]
    assert captured["job_name"] == "cli-survey"
    assert captured["execution_plane"] == "harbor"
    assert captured["shutdown"] is True
