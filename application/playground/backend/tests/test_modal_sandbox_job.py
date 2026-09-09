"""Tests for Modal Sandbox web/linux workers."""

from __future__ import annotations

import json
from pathlib import Path

from backend.service.modal_host_job import (
    ModalHostJobRequest,
    ModalHostJobResult,
    SdkModalDispatchRunner,
    encode_modal_sandbox_call_id,
    is_modal_sandbox_call_id,
    modal_sandbox_object_id,
    read_live_overlay,
)
from backend.service.modal_sandbox_job import (
    SANDBOX_RESULT_FILENAME,
    run_sandbox_worker,
    sandbox_payload_remote_path,
    wait_sandbox_with_live_pull,
    write_sandbox_live_status,
)


def _request(tmp_path: Path, config_yaml: str, live: bool = True) -> ModalHostJobRequest:
    return ModalHostJobRequest(
        job_name="demo-job",
        config_yaml=config_yaml,
        repo_root=str(tmp_path),
        jobs_dir="jobs",
        env={},
        shard_key="s0",
        live_jobs_dir=str(tmp_path / "jobs") if live else "",
    )


def test_sandbox_call_id_round_trip() -> None:
    encoded = encode_modal_sandbox_call_id("sb-abc")
    assert is_modal_sandbox_call_id(encoded)
    assert modal_sandbox_object_id(encoded) == "sb-abc"
    assert not is_modal_sandbox_call_id("fc-123")


def test_sandbox_payload_path_uses_shard() -> None:
    assert sandbox_payload_remote_path("demo-job", "s0") == "_payloads/demo-job/s0.json"


def test_write_sandbox_live_status(tmp_path: Path) -> None:
    job_dir = tmp_path / "jobs" / "demo-job"
    trial = job_dir / "web__a"
    trial.mkdir(parents=True)
    (trial / "config.json").write_text("{}\n", encoding="utf-8")
    dest = tmp_path / "live.json"
    status = write_sandbox_live_status(job_dir, dest=dest)
    assert status["web__a"] == "running"
    assert json.loads(dest.read_text(encoding="utf-8"))["web__a"] == "running"


def test_dispatch_runner_uses_sandbox_for_docker(monkeypatch, tmp_path: Path) -> None:
    spawned: list[str] = []

    class _FakeSandbox:
        def spawn(self, request):
            spawned.append("sandbox")
            return encode_modal_sandbox_call_id("sb-1"), object()

        def wait(self, request, **kwargs):
            return ModalHostJobResult(exit_code=0, volume_path="demo-job/s0")

    class _FakeHost:
        def spawn(self, request):
            spawned.append("host")
            return "fc-1", object()

        def wait(self, request, **kwargs):
            return ModalHostJobResult(exit_code=0)

    monkeypatch.setattr(
        "backend.service.modal_sandbox_job.SdkModalSandboxJobRunner",
        _FakeSandbox,
    )
    monkeypatch.setattr(
        "backend.service.modal_host_job.SdkModalHostJobRunner",
        _FakeHost,
    )
    runner = SdkModalDispatchRunner()
    docker = _request(tmp_path, "environment:\n  type: docker\n")
    call_id, _ = runner.spawn(docker)
    assert spawned == ["sandbox"]
    assert is_modal_sandbox_call_id(call_id)
    host = _request(tmp_path, "environment:\n  type: host\n")
    host_id, _ = runner.spawn(host)
    assert spawned == ["sandbox", "host"]
    assert host_id == "fc-1"


def test_wait_sandbox_applies_live_overlay(tmp_path: Path) -> None:
    dest = tmp_path / "jobs" / "demo-job"
    dest.mkdir(parents=True)

    class _Stdout:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    class _Proc:
        def __init__(self, payload: bytes) -> None:
            self.stdout = _Stdout(payload)

        def wait(self) -> int:
            return 0

    class _Sandbox:
        def __init__(self) -> None:
            self._polls = 0

        def poll(self) -> int | None:
            self._polls += 1
            if self._polls < 2:
                return None
            return 0

        def exec(self, *command: str):
            del command
            return _Proc(b'{"web__a": "running"}\n')

    request = _request(tmp_path, "environment:\n  type: docker\n")
    code = wait_sandbox_with_live_pull(_Sandbox(), request=request, volume=None, poll_sec=0.01)
    assert code == 0
    assert read_live_overlay(dest)["web__a"] == "running"


def test_run_sandbox_worker_writes_result(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "matraix"
    job_dir = repo / "jobs" / "demo-job"
    trial = job_dir / "web__a"
    trial.mkdir(parents=True)
    (trial / "result.json").write_text("{}\n", encoding="utf-8")
    volume_root = tmp_path / "modal-jobs"
    live_path = tmp_path / "live.json"
    monkeypatch.setattr(
        "backend.service.modal_sandbox_job.MODAL_REMOTE_REPO",
        str(repo),
    )
    monkeypatch.setattr(
        "backend.service.modal_sandbox_job.sandbox_jobs_volume_root",
        lambda: volume_root,
    )
    monkeypatch.setattr(
        "backend.service.modal_sandbox_job._LIVE_PATH",
        live_path,
    )
    monkeypatch.setattr(
        "backend.service.modal_docker_prebuild.ensure_docker_daemon",
        lambda: None,
    )
    monkeypatch.setattr(
        "backend.service.modal_docker_prebuild.prepare_docker_environment_for_job",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "backend.service.modal_sandbox_job._mounted_volume",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "backend.service.modal_sandbox_job._commit_volume",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "backend.service.modal_sandbox_job._run_command",
        lambda command, *, cwd, env: 0,
    )
    payload = {
        "jobName": "demo-job",
        "configYaml": "environment:\n  type: docker\njob_name: demo-job\n",
        "env": {},
        "shardKey": "s0",
    }
    code = run_sandbox_worker(payload)
    assert code == 0
    stored = json.loads(
        (volume_root / "demo-job" / "s0" / SANDBOX_RESULT_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    assert stored["exitCode"] == 0
    assert (volume_root / "demo-job" / "s0" / "web__a" / "result.json").is_file()
    assert json.loads(live_path.read_text(encoding="utf-8"))["web__a"] == "done"
