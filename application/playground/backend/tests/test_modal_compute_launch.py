"""Tests for Modal compute-family Harbor launches."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.service.harbor_job_service import HarborJobService


def test_launch_modal_family_survey_uses_modal_jobs(tmp_path, monkeypatch) -> None:
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample").mkdir(parents=True)
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)

    class _FakeModalRunner:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def run(self, request):
            from backend.service.modal_host_job import ModalHostJobResult, pack_job_dir

            self.calls.append(request)
            trial = jobs_dir / request.job_name / "survey__trial"
            trial.mkdir(parents=True)
            (trial / "result.json").write_text("{}", encoding="utf-8")
            return ModalHostJobResult(exit_code=0, artifact_tar=pack_job_dir(jobs_dir / request.job_name))

    fake = _FakeModalRunner()
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=lambda *args, **kwargs: 0,
        harbor_command=("echo", "harbor"),
        modal_host_job_runner=fake,
    )
    job_name = service.launch(
        task_path="application/tasks/example-survey_product-feedback",
        persona_ids=["0001"],
        persona_pool="persona/datasets/matraix-persona-dev-sample",
        job_name="modal-survey",
        compute_family="modal",
        execution_plane="harbor",
    )
    service._executor.shutdown(wait=True)
    launch = service._launches[job_name]
    assert launch.compute_family == "modal"
    assert launch.compute_environment == "host"
    assert launch.compute_dispatch == "modal_jobs"
    assert fake.calls
    assert fake.calls[0].live_jobs_dir == str(jobs_dir.resolve())
    config_text = (repo / "configs" / "jobs" / "application-task-job-recipe" / "modal-survey.yaml").read_text(
        encoding="utf-8"
    )
    assert "type: host" in config_text
    assert "dispatch=modal_jobs" in config_text
    compute = (jobs_dir / job_name / "compute.json").read_text(encoding="utf-8")
    assert '"dispatch": "modal_jobs"' in compute
    assert '"family": "modal"' in compute
    assert (jobs_dir / job_name / "survey__trial" / "result.json").is_file()


def test_launch_modal_family_survey_fans_out_shards(tmp_path, monkeypatch) -> None:
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    for index in range(1, 5):
        pid = f"{index:04d}"
        (pool / f"persona_{pid}.yaml").write_text(
            f"persona_id: '{pid}'\nversion: '1.0'\nsource: Nemotron\ndimensions: {{}}\n",
            encoding="utf-8",
        )
    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)
    monkeypatch.setenv("MATRIX_HOST_PACK_CONCURRENCY", "1")
    monkeypatch.setenv("MATRIX_SHARD_CONCURRENCY", "2")

    class _FakeModalRunner:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def run(self, request):
            from backend.service.modal_host_job import ModalHostJobResult, pack_job_dir

            self.calls.append(request)
            isolated = repo / "worker" / (request.shard_key or "s0") / request.job_name
            trial = isolated / "survey__{}".format(request.shard_key or "s0")
            trial.mkdir(parents=True)
            (trial / "result.json").write_text("{}", encoding="utf-8")
            (isolated / "result.json").write_text('{"shard": true}\n', encoding="utf-8")
            return ModalHostJobResult(exit_code=0, artifact_tar=pack_job_dir(isolated))

    fake = _FakeModalRunner()
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=lambda *args, **kwargs: 0,
        harbor_command=("echo", "harbor"),
        modal_host_job_runner=fake,
    )
    job_name = service.launch(
        task_path="application/tasks/example-survey_product-feedback",
        persona_ids=["0001", "0002", "0003", "0004"],
        persona_pool="persona/datasets/matraix-persona-dev-sample",
        job_name="modal-sharded",
        compute_family="modal",
        execution_plane="harbor",
    )
    service._executor.shutdown(wait=True)
    launch = service._launches[job_name]
    assert launch.status == "completed"
    assert launch.compute_dispatch == "modal_jobs"
    assert len(fake.calls) == 2
    assert {call.job_name for call in fake.calls} == {"modal-sharded"}
    assert {call.shard_key for call in fake.calls} == {"s0", "s1"}
    job_dir = jobs_dir / job_name
    assert (job_dir / "compute.json").is_file()
    assert (job_dir / "survey__s0" / "result.json").is_file()
    assert (job_dir / "survey__s1" / "result.json").is_file()
    rolled = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    assert rolled["n_total_trials"] == 4
    assert rolled["stats"]["n_completed_trials"] == 2
    assert rolled.get("finished_at")
    assert (job_dir / "_generated" / "shards.json").is_file()
    parent = (repo / "configs" / "jobs" / "application-task-job-recipe" / "modal-sharded.yaml").read_text(
        encoding="utf-8"
    )
    shard0 = (
        repo / "configs" / "jobs" / "application-task-job-recipe" / "modal-sharded.shard-00.yaml"
    ).read_text(encoding="utf-8")
    assert parent.count("persona_path:") == 4
    assert shard0.count("persona_path:") == 2
    assert "job_name: modal-sharded" in shard0
    assert "n_concurrent_trials: 2" in parent
    assert "n_concurrent_trials: 1" in shard0


def test_retry_failed_only_rediscovers_failed_shards(tmp_path, monkeypatch) -> None:
    import time

    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    for index in range(1, 5):
        pid = f"{index:04d}"
        (pool / f"persona_{pid}.yaml").write_text(
            f"persona_id: '{pid}'\nversion: '1.0'\nsource: Nemotron\ndimensions: {{}}\n",
            encoding="utf-8",
        )
    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)
    monkeypatch.setenv("MATRIX_HOST_PACK_CONCURRENCY", "1")

    class _FakeModalRunner:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def run(self, request):
            import shutil

            import yaml

            from backend.service.modal_host_job import ModalHostJobResult, pack_job_dir

            self.calls.append(request)
            loaded = yaml.safe_load(request.config_yaml) or {}
            agents = [row for row in (loaded.get("agents") or []) if isinstance(row, dict)]
            isolated = repo / "worker" / (request.shard_key or "s0") / request.job_name
            if isolated.exists():
                shutil.rmtree(isolated)
            fail_ids = {"0003", "0004"} if len(self.calls) <= 2 else set()
            for agent in agents:
                path = str((agent.get("kwargs") or {}).get("persona_path") or "")
                pid = Path(path).stem.replace("persona_", "") or "x"
                trial = isolated / "survey__{}".format(pid)
                trial.mkdir(parents=True)
                (trial / "persona_meta.json").write_text(
                    json.dumps({"persona_id": pid}) + "\n",
                    encoding="utf-8",
                )
                payload = (
                    {"exception_info": {"exception_type": "TimeoutError"}}
                    if pid in fail_ids
                    else {}
                )
                (trial / "result.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
            return ModalHostJobResult(exit_code=0, artifact_tar=pack_job_dir(isolated))

    fake = _FakeModalRunner()
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=lambda *args, **kwargs: 0,
        harbor_command=("echo", "harbor"),
        modal_host_job_runner=fake,
    )

    def _wait() -> None:
        for _ in range(100):
            status = service._launches[job_name].status
            if status in {"completed", "failed"}:
                return
            time.sleep(0.02)
        raise AssertionError("launch did not finish")

    job_name = service.launch(
        task_path="application/tasks/example-survey_product-feedback",
        persona_ids=["0001", "0002", "0003", "0004"],
        persona_pool="persona/datasets/matraix-persona-dev-sample",
        job_name="modal-retry",
        compute_family="modal",
        execution_plane="harbor",
    )
    _wait()
    first_calls = len(fake.calls)
    assert first_calls == 2
    retried = service.retry_failed(job_name)
    assert retried["retried"] == 2
    _wait()
    service._executor.shutdown(wait=True)
    assert len(fake.calls) == first_calls + 1
    assert fake.calls[-1].shard_key == "s1"
    assert fake.calls[-1].config_yaml.count("persona_path:") == 2


def test_launch_modal_family_web_writes_harbor_docker(tmp_path, monkeypatch) -> None:
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample").mkdir(parents=True)
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    task = repo / "application" / "tasks" / "example-web_bookshop"
    task.mkdir(parents=True)
    (task / "task.toml").write_text(
        '[task]\nname = "web-demo"\n[metadata]\ntype = "web"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)

    class _FakeModalRunner:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def run(self, request):
            from backend.service.modal_host_job import ModalHostJobResult, pack_job_dir

            self.calls.append(request)
            trial = jobs_dir / request.job_name / "web__trial"
            trial.mkdir(parents=True)
            (trial / "result.json").write_text("{}", encoding="utf-8")
            return ModalHostJobResult(
                exit_code=0, artifact_tar=pack_job_dir(jobs_dir / request.job_name)
            )

    fake = _FakeModalRunner()
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=lambda *args, **kwargs: 0,
        harbor_command=("echo", "harbor"),
        modal_host_job_runner=fake,
    )
    job_name = service.launch(
        task_path="application/tasks/example-web_bookshop",
        persona_ids=["0001"],
        persona_pool="persona/datasets/matraix-persona-dev-sample",
        agent_name="persona-computer-1",
        job_name="modal-web",
        compute_family="modal",
        execution_plane="harbor",
    )
    service._executor.shutdown(wait=True)
    launch = service._launches[job_name]
    assert launch.compute_family == "modal"
    assert launch.compute_environment == "docker"
    assert launch.compute_dispatch == "modal_jobs"
    assert fake.calls
    config_text = (repo / "configs" / "jobs" / "application-task-job-recipe" / "modal-web.yaml").read_text(
        encoding="utf-8"
    )
    assert "type: docker" in config_text
    assert "dispatch=modal_jobs" in config_text
    compute = (jobs_dir / job_name / "compute.json").read_text(encoding="utf-8")
    assert '"dispatch": "modal_jobs"' in compute
    assert '"environment": "docker"' in compute


def test_launch_modal_family_web_fans_out_modal_jobs(tmp_path, monkeypatch) -> None:
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    for index in range(1, 5):
        pid = f"{index:04d}"
        (pool / f"persona_{pid}.yaml").write_text(
            f"persona_id: '{pid}'\nversion: '1.0'\nsource: Nemotron\ndimensions: {{}}\n",
            encoding="utf-8",
        )
    task = repo / "application" / "tasks" / "example-web_bookshop"
    task.mkdir(parents=True)
    (task / "task.toml").write_text(
        '[task]\nname = "web-demo"\n[metadata]\ntype = "web"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)
    monkeypatch.setenv("MATRIX_WEB_PACK_CONCURRENCY", "1")
    monkeypatch.setenv("MATRIX_SHARD_CONCURRENCY", "2")

    class _FakeModalRunner:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def run(self, request):
            from backend.service.modal_host_job import ModalHostJobResult, pack_job_dir

            self.calls.append(request)
            isolated = repo / "worker" / (request.shard_key or "s0") / request.job_name
            trial = isolated / "web__{}".format(request.shard_key or "s0")
            trial.mkdir(parents=True)
            (trial / "result.json").write_text("{}\n", encoding="utf-8")
            (isolated / "result.json").write_text('{"shard": true}\n', encoding="utf-8")
            return ModalHostJobResult(exit_code=0, artifact_tar=pack_job_dir(isolated))

    fake = _FakeModalRunner()
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=lambda *args, **kwargs: 0,
        harbor_command=("echo", "harbor"),
        modal_host_job_runner=fake,
    )
    job_name = service.launch(
        task_path="application/tasks/example-web_bookshop",
        persona_ids=["0001", "0002", "0003", "0004"],
        persona_pool="persona/datasets/matraix-persona-dev-sample",
        agent_name="persona-computer-1",
        job_name="modal-web-shards",
        compute_family="modal",
        execution_plane="harbor",
    )
    service._executor.shutdown(wait=True)
    launch = service._launches[job_name]
    assert launch.status == "completed"
    assert launch.compute_environment == "docker"
    assert launch.compute_dispatch == "modal_jobs"
    assert len(fake.calls) == 2
    job_dir = jobs_dir / job_name
    assert (job_dir / "compute.json").is_file()
    assert (job_dir / "web__s0" / "result.json").is_file()
    assert (job_dir / "web__s1" / "result.json").is_file()
    rolled = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    assert rolled["n_total_trials"] == 4
    assert rolled.get("finished_at")
    shard0 = (
        repo / "configs" / "jobs" / "application-task-job-recipe" / "modal-web-shards.shard-00.yaml"
    ).read_text(encoding="utf-8")
    assert "type: docker" in shard0
    assert "job_name: modal-web-shards" in shard0


def test_launch_modal_survey_requires_credentials(tmp_path, monkeypatch) -> None:
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample").mkdir(parents=True)
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    monkeypatch.setattr(
        "backend.service.modal_host_job.modal_credentials_configured",
        lambda: False,
    )

    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=lambda *args, **kwargs: 0,
        harbor_command=("echo", "harbor"),
    )
    try:
        service.launch(
            task_path="application/tasks/example-survey_product-feedback",
            persona_ids=["0001"],
            persona_pool="persona/datasets/matraix-persona-dev-sample",
            compute_family="modal",
        )
        raise AssertionError("expected missing Modal credentials to fail")
    except ValueError as exc:
        assert "Modal" in str(exc)


def test_launch_gcp_survey_requires_host_workers(tmp_path, monkeypatch) -> None:
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample").mkdir(parents=True)
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)
    monkeypatch.setattr("matraix.gke_settings.gke_host_workers_ready", lambda: False)
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=lambda *args, **kwargs: 0,
        harbor_command=("echo", "harbor"),
    )
    with pytest.raises(ValueError, match="MATRIX_GKE_HOST_IMAGE"):
        service.launch(
            task_path="application/tasks/example-survey_product-feedback",
            persona_ids=["0001"],
            persona_pool="persona/datasets/matraix-persona-dev-sample",
            compute_family="gcp",
        )


def test_launch_gcp_family_survey_uses_gke_workers(tmp_path, monkeypatch) -> None:
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample").mkdir(parents=True)
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)

    class _FakeGkeRunner:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def run(self, request):
            from backend.service.modal_host_job import ModalHostJobResult, pack_job_dir

            self.calls.append(request)
            trial = jobs_dir / request.job_name / "survey__trial"
            trial.mkdir(parents=True)
            (trial / "result.json").write_text("{}", encoding="utf-8")
            return ModalHostJobResult(exit_code=0, artifact_tar=pack_job_dir(jobs_dir / request.job_name))

    fake = _FakeGkeRunner()
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=lambda *args, **kwargs: 0,
        harbor_command=("echo", "harbor"),
        gke_host_job_runner=fake,
    )
    job_name = service.launch(
        task_path="application/tasks/example-survey_product-feedback",
        persona_ids=["0001"],
        persona_pool="persona/datasets/matraix-persona-dev-sample",
        job_name="gke-survey",
        compute_family="gcp",
        execution_plane="harbor",
    )
    service._executor.shutdown(wait=True)
    launch = service._launches[job_name]
    assert launch.compute_family == "gcp"
    assert launch.compute_environment == "host"
    assert launch.compute_dispatch == "gke_workers"
    assert fake.calls
    config_text = (repo / "configs" / "jobs" / "application-task-job-recipe" / "gke-survey.yaml").read_text(
        encoding="utf-8"
    )
    assert "type: host" in config_text
    assert "dispatch=gke_workers" in config_text
    compute = (jobs_dir / job_name / "compute.json").read_text(encoding="utf-8")
    assert '"dispatch": "gke_workers"' in compute
    assert '"family": "gcp"' in compute
    assert (jobs_dir / job_name / "survey__trial" / "result.json").is_file()


def test_launch_gcp_family_web_writes_harbor_gke(tmp_path, monkeypatch) -> None:
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample").mkdir(parents=True)
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    task = repo / "application" / "tasks" / "example-web_bookshop"
    task.mkdir(parents=True)
    (task / "task.toml").write_text(
        '[task]\nname = "web-demo"\n[metadata]\ntype = "web"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)
    monkeypatch.setenv("MATRIX_GKE_CLUSTER", "demo")
    monkeypatch.setenv("MATRIX_GKE_REGION", "us-central1")
    monkeypatch.setenv("MATRIX_GKE_REGISTRY", "matraix")
    monkeypatch.setenv("GCP_PROJECT", "proj-1")

    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=lambda *args, **kwargs: 0,
        harbor_command=("echo", "harbor"),
    )
    job_name = service.launch(
        task_path="application/tasks/example-web_bookshop",
        persona_ids=["0001"],
        persona_pool="persona/datasets/matraix-persona-dev-sample",
        agent_name="persona-computer-1",
        job_name="gke-web",
        compute_family="gcp",
        execution_plane="harbor",
    )
    service._executor.shutdown(wait=True)
    launch = service._launches[job_name]
    assert launch.compute_family == "gcp"
    assert launch.compute_environment == "gke"
    assert launch.compute_dispatch is None
    config_text = (repo / "configs" / "jobs" / "application-task-job-recipe" / "gke-web.yaml").read_text(
        encoding="utf-8"
    )
    assert "type: gke" in config_text
    assert "cluster_name: demo" in config_text
    assert "registry_name: matraix" in config_text
    assert '"dispatch"' not in (jobs_dir / job_name / "compute.json").read_text(encoding="utf-8")


def test_launch_gcp_web_requires_cluster_settings(tmp_path, monkeypatch) -> None:
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample").mkdir(parents=True)
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    task = repo / "application" / "tasks" / "example-web_bookshop"
    task.mkdir(parents=True)
    (task / "task.toml").write_text(
        '[task]\nname = "web-demo"\n[metadata]\ntype = "web"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)
    for name in (
        "MATRIX_GKE_CLUSTER",
        "MATRIX_GKE_REGION",
        "MATRIX_GKE_REGISTRY",
        "MATRIX_GKE_REGISTRY_LOCATION",
        "GCP_PROJECT",
        "GOOGLE_CLOUD_PROJECT",
        "MATRIX_GCP_PROJECT",
    ):
        monkeypatch.delenv(name, raising=False)

    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=lambda *args, **kwargs: 0,
        harbor_command=("echo", "harbor"),
    )
    with pytest.raises(ValueError, match="GKE"):
        service.launch(
            task_path="application/tasks/example-web_bookshop",
            persona_ids=["0001"],
            persona_pool="persona/datasets/matraix-persona-dev-sample",
            agent_name="persona-computer-1",
            compute_family="gcp",
        )


def test_launch_modal_spawns_all_shards_before_wait(tmp_path, monkeypatch) -> None:
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    for index in range(1, 5):
        pid = f"{index:04d}"
        (pool / f"persona_{pid}.yaml").write_text(
            f"persona_id: '{pid}'\nversion: '1.0'\nsource: Nemotron\ndimensions: {{}}\n",
            encoding="utf-8",
        )
    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)
    monkeypatch.setenv("MATRIX_HOST_PACK_CONCURRENCY", "1")

    class _SpawnRunner:
        def __init__(self) -> None:
            self.spawned: list[str] = []
            self.waited: list[str] = []

        def spawn(self, request):
            previous = list(self.spawned)
            self.spawned.append(request.shard_key)
            from backend.service.modal_host_job import load_cloud_run

            cloud = load_cloud_run(jobs_dir / request.job_name) or {}
            recorded = {
                str(row.get("key") or "")
                for row in cloud.get("shards") or []
                if isinstance(row, dict)
            }
            # Earlier shards must already be recorded before this spawn returns
            # (save happens after spawn; check previous keys on next call).
            assert set(previous) <= recorded
            return "fc-{}".format(request.shard_key), object()

        def wait(self, request, *, call=None, call_id=""):
            del call
            self.waited.append(call_id)
            from backend.service.modal_host_job import ModalHostJobResult, pack_job_dir

            isolated = repo / "worker" / (request.shard_key or "s0") / request.job_name
            trial = isolated / "survey__{}".format(request.shard_key or "s0")
            trial.mkdir(parents=True)
            (trial / "result.json").write_text("{}\n", encoding="utf-8")
            return ModalHostJobResult(exit_code=0, artifact_tar=pack_job_dir(isolated))

    fake = _SpawnRunner()
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=lambda *args, **kwargs: 0,
        harbor_command=("echo", "harbor"),
        modal_host_job_runner=fake,
    )
    job_name = service.launch(
        task_path="application/tasks/example-survey_product-feedback",
        persona_ids=["0001", "0002", "0003", "0004"],
        persona_pool="persona/datasets/matraix-persona-dev-sample",
        job_name="modal-spawn-all",
        compute_family="modal",
        execution_plane="harbor",
    )
    service._executor.shutdown(wait=True)
    assert fake.spawned == ["s0", "s1"]
    assert set(fake.waited) == {"fc-s0", "fc-s1"}
    cloud = json.loads(
        (jobs_dir / job_name / "_generated" / "cloud_run.json").read_text(encoding="utf-8")
    )
    assert cloud["status"] == "completed"
    assert {row["callId"] for row in cloud["shards"]} == {"fc-s0", "fc-s1"}
    assert (jobs_dir / job_name / "survey__s0" / "result.json").is_file()
    assert (jobs_dir / job_name / "survey__s1" / "result.json").is_file()


def test_launch_modal_chat_rejects_localhost_sidecar(tmp_path, monkeypatch) -> None:
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0042.yaml").write_text(
        "persona_id: '0042'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    task_dir = repo / "application" / "tasks" / "chat_meal-planning-nutrition"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text("metadata:\n  type: chat\n", encoding="utf-8")
    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)
    monkeypatch.setenv("CHATBOT_API_URL", "http://127.0.0.1:8905")
    monkeypatch.delenv("MATRIX_CHATBOT_PUBLIC_URL", raising=False)
    monkeypatch.setenv("MATRIX_CHATBOT_TUNNEL", "0")

    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=lambda *args, **kwargs: 0,
        harbor_command=("echo", "harbor"),
        modal_host_job_runner=object(),
    )
    with pytest.raises(ValueError, match="localhost is not visible|needs a chatbot URL"):
        service.launch(
            task_path="application/tasks/chat_meal-planning-nutrition",
            persona_ids=["0042"],
            job_name="modal-chat-local",
            compute_family="modal",
            execution_plane="harbor",
        )
