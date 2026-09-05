"""Tests for application Harbor job config helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from matraix.application_job import (
    build_application_job_config,
    resolve_job_environment,
    resolve_harbor_task_path,
    resolve_persona_entries,
)


def test_resolve_persona_entries_from_pool(tmp_path: Path) -> None:
    repo = tmp_path
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0042.yaml").write_text(
        "persona_id: '0042'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )

    chosen = resolve_persona_entries(
        ["42", "0042"],
        persona_pool="persona/datasets/matraix-persona-dev-sample",
        repo_root=repo,
    )
    assert len(chosen) == 1
    assert chosen[0]["persona_id"] == "0042"


def test_resolve_persona_entries_accepts_persona_prefixed_ids(tmp_path: Path) -> None:
    repo = tmp_path
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0042.yaml").write_text(
        "persona_id: '0042'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )

    chosen = resolve_persona_entries(
        ["persona_0042"],
        persona_pool="persona/datasets/matraix-persona-dev-sample",
        repo_root=repo,
    )
    assert len(chosen) == 1
    assert chosen[0]["path"] == "persona/datasets/matraix-persona-dev-sample/persona_0042.yaml"


def test_resolve_persona_entries_unknown_includes_pool(tmp_path: Path) -> None:
    repo = tmp_path
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0042.yaml").write_text(
        "persona_id: '0042'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=r"unknown persona wiki-e690edb701e2 in pool persona/datasets/matraix-persona-dev-sample",
    ):
        resolve_persona_entries(
            ["wiki-e690edb701e2"],
            persona_pool="persona/datasets/matraix-persona-dev-sample",
            repo_root=repo,
        )


def test_build_application_job_config_with_explicit_persona_ids(tmp_path: Path) -> None:
    repo = tmp_path
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )

    job = build_application_job_config(
        {
            "name": "explicit-job",
            "task": "application/tasks/example-survey_product-feedback",
            "persona_pool": "persona/datasets/matraix-persona-dev-sample",
            "persona_ids": ["0001"],
            "execution_mode": "auto",
            "trial_profile": "json_survey",
            "agent": {"name": "persona-claude-code", "model_name": "anthropic/claude-haiku-4-5"},
            "job": {"job_name": "explicit-job", "jobs_dir": "jobs"},
        },
        repo_root=repo,
    )
    meta = job.pop("_job_meta")
    assert meta["selected_persona_ids"] == ["0001"]
    assert meta["execution_mode"] == "auto"
    assert meta["trial_profile"] == "json_survey"
    assert len(job["agents"]) == 1
    assert job["agents"][0]["kwargs"]["persona_path"].endswith("persona_0001.yaml")


def test_resolve_job_environment_auto_native_profiles() -> None:
    assert resolve_job_environment(execution_mode="auto", trial_profile="json_survey") == {
        "type": "host",
        "delete": True,
    }
    assert resolve_job_environment(execution_mode="auto", trial_profile="user_sim_chat") == {
        "type": "host",
        "delete": True,
    }
    assert resolve_job_environment(execution_mode="auto", trial_profile="docker_agent") == {
        "type": "docker",
        "delete": True,
    }
    assert resolve_job_environment(execution_mode="force_docker", trial_profile="json_survey") == {
        "type": "docker",
        "delete": True,
    }


def test_resolve_job_environment_use_computer_for_macos_and_ios() -> None:
    assert resolve_job_environment(
        execution_mode="auto",
        trial_profile="docker_agent",
        cua_backend="macos",
    ) == {"type": "use-computer", "delete": True}
    assert resolve_job_environment(
        execution_mode="auto",
        trial_profile="docker_agent",
        cua_backend="ios",
    ) == {"type": "use-computer", "delete": True, "kwargs": {"platform": "ios"}}
    assert resolve_job_environment(
        execution_mode="auto",
        trial_profile="docker_agent",
        cua_backend="docker",
    ) == {"type": "docker", "delete": True}


def test_resolve_job_environment_compute_family(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "MATRIX_GKE_CLUSTER",
        "MATRIX_GKE_REGION",
        "MATRIX_GKE_REGISTRY",
        "GCP_PROJECT",
        "GOOGLE_CLOUD_PROJECT",
        "MATRIX_GCP_PROJECT",
    ):
        monkeypatch.delenv(name, raising=False)
    assert resolve_job_environment(
        execution_mode="auto",
        trial_profile="json_survey",
        compute_family="local",
    ) == {"type": "host", "delete": True}
    assert resolve_job_environment(
        execution_mode="auto",
        trial_profile="json_survey",
        compute_family="modal",
    ) == {"type": "host", "delete": True}
    assert resolve_job_environment(
        execution_mode="auto",
        trial_profile="user_sim_chat",
        compute_family="modal",
    ) == {"type": "host", "delete": True}
    assert resolve_job_environment(
        execution_mode="auto",
        trial_profile="docker_agent",
        compute_family="modal",
    ) == {"type": "docker", "delete": True}
    assert resolve_job_environment(
        execution_mode="auto",
        trial_profile="docker_agent",
        compute_family="gcp",
    ) == {"type": "gke", "delete": True}


def test_build_application_job_config_macos_cua_uses_use_computer(tmp_path: Path) -> None:
    repo = tmp_path
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )

    job = build_application_job_config(
        {
            "name": "macos-cua",
            "task": "application/tasks/example-computer-use-macos_calendar-reminder-handoff",
            "persona_pool": "persona/datasets/matraix-persona-dev-sample",
            "persona_ids": ["0001"],
            "execution_mode": "auto",
            "trial_profile": "docker_agent",
            "cua_backend": "macos",
            "agent": {"name": "persona-computer-1", "model_name": "anthropic/claude-haiku-4-5"},
            "job": {"job_name": "macos-cua", "jobs_dir": "jobs"},
        },
        repo_root=repo,
    )
    job.pop("_job_meta")
    assert job["environment"] == {"type": "use-computer", "delete": True}
    assert "cua_backend" not in job["agents"][0]["kwargs"]  # injected later by harbor_job_service


def test_build_application_job_config_auto_survey_uses_host_environment(tmp_path: Path) -> None:
    repo = tmp_path
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )

    job = build_application_job_config(
        {
            "name": "auto-survey",
            "task": "application/tasks/example-survey_product-feedback",
            "persona_pool": "persona/datasets/matraix-persona-dev-sample",
            "persona_ids": ["0001"],
            "execution_mode": "auto",
            "trial_profile": "json_survey",
            "agent": {"name": "persona-json-survey", "model_name": "anthropic/claude-haiku-4-5"},
            "job": {"job_name": "auto-survey", "jobs_dir": "jobs"},
        },
        repo_root=repo,
    )
    meta = job.pop("_job_meta")
    assert meta["trial_profile"] == "json_survey"
    assert job["environment"] == {"type": "host", "delete": True}
    assert job["tasks"][0]["path"] == "application/tasks/example-survey_product-feedback"
    assert resolve_harbor_task_path(
        "application/tasks/example-survey_product-feedback",
        trial_profile="json_survey",
    ) == "application/tasks/example-survey_product-feedback"


def test_build_application_job_config_use_entire_pool(tmp_path: Path) -> None:
    repo = tmp_path
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    for pid in ("0001", "0002", "0003"):
        (pool / f"persona_{pid}.yaml").write_text(
            f"persona_id: '{pid}'\nversion: '1.0'\nsource: Nemotron\ndimensions: {{}}\n",
            encoding="utf-8",
        )

    job = build_application_job_config(
        {
            "name": "entire-pool-job",
            "task": "application/tasks/example-survey_product-feedback",
            "persona_pool": "persona/datasets/matraix-persona-dev-sample",
            "use_entire_pool": True,
            "sample_size": 1,
            "execution_mode": "auto",
            "trial_profile": "json_survey",
            "agent": {"name": "persona-claude-code", "model_name": "anthropic/claude-haiku-4-5"},
            "job": {"job_name": "entire-pool-job", "jobs_dir": "jobs"},
        },
        repo_root=repo,
    )
    meta = job.pop("_job_meta")
    assert meta["use_entire_pool"] is True
    assert sorted(meta["selected_persona_ids"]) == ["0001", "0002", "0003"]
    assert len(job["agents"]) == 3


def test_build_application_job_config_rejects_unknown_mode(tmp_path: Path) -> None:
    repo = tmp_path
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="execution_mode"):
        build_application_job_config(
            {
                "name": "bad-mode",
                "task": "application/tasks/example-survey_product-feedback",
                "persona_pool": "persona/datasets/matraix-persona-dev-sample",
                "sample_size": 1,
                "execution_mode": "turbo",
                "agent": {"name": "persona-claude-code", "model_name": "anthropic/claude-haiku-4-5"},
            },
            repo_root=repo,
        )
