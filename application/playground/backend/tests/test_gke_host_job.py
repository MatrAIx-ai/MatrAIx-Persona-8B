"""Tests for GKE host-worker helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.service.gke_host_job import (
    GKE_REMOTE_REPO,
    GkeHostJobError,
    GkeHostJobRequest,
    build_gke_job_manifest,
    gke_host_worker_script,
    gke_job_name,
    materialize_gke_artifacts,
)
from backend.service.modal_host_job import ModalHostJobResult, pack_job_dir


def test_gke_job_name_is_dns_safe() -> None:
    assert gke_job_name("pg-Example_Survey 1") == "matraix-host-pg-example-survey-1"
    assert gke_job_name("pg-Example_Survey 1", "s1").endswith("-s1")
    assert gke_job_name("pg-Example_Survey 1", "s0") != gke_job_name("pg-Example_Survey 1", "s1")


def test_gke_host_worker_script_packs_job_tree() -> None:
    script = gke_host_worker_script("demo-job")
    assert "python -m harbor.cli.main run --yes -c /config/job.yaml" in script
    assert "/tmp/matraix-exit" in script
    assert "tar czf /tmp/matraix-job.tgz" in script
    assert "python -c" in script
    assert "/tmp/matraix-live.json" in script
    assert "demo-job" in script


def test_build_gke_job_manifest_uses_host_image_and_configmap() -> None:
    request = GkeHostJobRequest(
        job_name="demo-job",
        config_yaml="job_name: demo-job\n",
        env={"MATRIX_SURVEY_TASK_PATH": "application/tasks/example"},
        secret_env={"ANTHROPIC_API_KEY": "sk-test"},
    )
    manifest = build_gke_job_manifest(
        request,
        image="us-central1-docker.pkg.dev/p/r/host:latest",
        namespace="matraix",
        pvc_name="jobs-pvc",
    )
    assert manifest["kind"] == "Job"
    assert manifest["metadata"]["name"] == "matraix-host-demo-job"
    assert manifest["metadata"]["namespace"] == "matraix"
    container = manifest["spec"]["template"]["spec"]["containers"][0]
    assert container["image"].endswith("host:latest")
    assert container["command"] == ["/bin/sh", "-c"]
    assert container["resources"]["requests"] == {"cpu": "1", "memory": "4Gi"}
    env_names = {item["name"]: item["value"] for item in container["env"]}
    assert env_names["ANTHROPIC_API_KEY"] == "sk-test"
    assert env_names["MATRIX_REPO_ROOT"] == GKE_REMOTE_REPO
    volumes = {item["name"]: item for item in manifest["spec"]["template"]["spec"]["volumes"]}
    assert "configMap" in volumes["config"]
    assert volumes["jobs"]["persistentVolumeClaim"]["claimName"] == "jobs-pvc"


def test_materialize_gke_artifacts_preserves_compute_json(tmp_path: Path) -> None:
    dest_jobs = tmp_path / "jobs"
    dest = dest_jobs / "demo"
    dest.mkdir(parents=True)
    (dest / "compute.json").write_text(
        '{"family": "gcp", "environment": "host", "dispatch": "gke_workers"}\n',
        encoding="utf-8",
    )
    src = tmp_path / "remote" / "demo"
    trial = src / "survey__abc"
    trial.mkdir(parents=True)
    (trial / "result.json").write_text(
        '{"trial_uri": "file:///matraix/jobs/demo/survey__abc"}',
        encoding="utf-8",
    )
    (src / "compute.json").write_text('{"family": "wrong"}\n', encoding="utf-8")
    result = ModalHostJobResult(exit_code=0, artifact_tar=pack_job_dir(src))
    merged = materialize_gke_artifacts(result, jobs_dir=dest_jobs, job_name="demo")
    assert '"dispatch": "gke_workers"' in (merged / "compute.json").read_text(encoding="utf-8")
    text = (merged / "survey__abc" / "result.json").read_text(encoding="utf-8")
    assert "/matraix/jobs/demo" not in text
    assert str(merged.resolve()) in text


def test_materialize_gke_artifacts_requires_tree(tmp_path: Path) -> None:
    with pytest.raises(GkeHostJobError, match="without returning"):
        materialize_gke_artifacts(
            ModalHostJobResult(exit_code=0),
            jobs_dir=tmp_path / "jobs",
            job_name="missing",
        )


def test_apply_gke_live_status_writes_overlay(tmp_path: Path) -> None:
    from backend.service.gke_host_job import apply_gke_live_status
    from backend.service.modal_host_job import read_live_overlay

    dest = tmp_path / "jobs" / "demo"
    dest.mkdir(parents=True)
    status = apply_gke_live_status(dest, b'{"survey__a": "running", "survey__b": "done"}\n')
    assert status == {"survey__a": "running", "survey__b": "done"}
    assert read_live_overlay(dest)["survey__a"] == "running"
    assert read_live_overlay(dest)["survey__b"] == "done"
