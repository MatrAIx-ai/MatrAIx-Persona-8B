"""Tests for Modal Jobs host-agent helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.service.modal_host_job import (
    HARBOR_MODULE_COMMAND,
    ModalHostJobError,
    ModalHostJobRequest,
    ModalHostJobResult,
    apply_live_overlay,
    download_volume_job,
    execute_host_harbor_job,
    invoke_modal_host_function,
    LivePublishState,
    materialize_modal_artifacts,
    merge_job_artifacts,
    modal_volume_job_name,
    overlay_status_code,
    pack_job_dir,
    prepare_modal_job_config,
    publish_live_trial_deltas,
    read_live_overlay,
    rewrite_job_artifact_paths,
    sync_job_dir_to_volume,
    unpack_job_dir,
    wait_modal_call_with_live_pull,
)


def test_pack_and_unpack_job_dir(tmp_path: Path) -> None:
    src = tmp_path / "jobs" / "demo"
    trial = src / "t1"
    trial.mkdir(parents=True)
    (trial / "result.json").write_text("{\"ok\": true}", encoding="utf-8")
    blob = pack_job_dir(src)
    dest = tmp_path / "out"
    unpacked = unpack_job_dir(blob, jobs_dir=dest, job_name="demo")
    assert (unpacked / "t1" / "result.json").read_text(encoding="utf-8") == "{\"ok\": true}"


def test_merge_preserves_compute_json_and_rewrites_paths(tmp_path: Path) -> None:
    dest_jobs = tmp_path / "jobs"
    dest = dest_jobs / "demo"
    dest.mkdir(parents=True)
    (dest / "compute.json").write_text(
        '{"family": "modal", "environment": "host", "dispatch": "modal_jobs"}\n',
        encoding="utf-8",
    )
    src = tmp_path / "remote" / "demo"
    trial = src / "survey__abc"
    (trial / "agent").mkdir(parents=True)
    (trial / "verifier").mkdir()
    (trial / "result.json").write_text(
        '{"trial_uri": "file:///matraix/jobs/demo/survey__abc"}',
        encoding="utf-8",
    )
    (src / "compute.json").write_text('{"family": "wrong"}\n', encoding="utf-8")
    (src / "job.log").write_text("ok\n", encoding="utf-8")
    blob = pack_job_dir(src)
    merged = merge_job_artifacts(blob, jobs_dir=dest_jobs, job_name="demo")
    assert '"dispatch": "modal_jobs"' in (merged / "compute.json").read_text(encoding="utf-8")
    result = (merged / "survey__abc" / "result.json").read_text(encoding="utf-8")
    assert "/matraix/jobs/demo" not in result
    assert str(merged.resolve()) in result
    assert (merged / "survey__abc" / "agent").is_dir()
    assert (merged / "job.log").read_text(encoding="utf-8") == "ok\n"


def test_merge_skips_shard_job_result_json(tmp_path: Path) -> None:
    dest_jobs = tmp_path / "jobs"
    dest = dest_jobs / "demo"
    dest.mkdir(parents=True)
    (dest / "compute.json").write_text('{"family": "modal"}\n', encoding="utf-8")
    src = tmp_path / "remote" / "demo"
    src.mkdir(parents=True)
    (src / "result.json").write_text('{"shardOnly": true}\n', encoding="utf-8")
    (src / "survey__a" / "result.json").parent.mkdir(parents=True)
    (src / "survey__a" / "result.json").write_text("{}\n", encoding="utf-8")
    merged = merge_job_artifacts(pack_job_dir(src), jobs_dir=dest_jobs, job_name="demo")
    assert not (merged / "result.json").is_file()
    assert (merged / "survey__a" / "result.json").is_file()
    assert '"family": "modal"' in (merged / "compute.json").read_text(encoding="utf-8")


def test_rewrite_job_artifact_paths(tmp_path: Path) -> None:
    job_dir = tmp_path / "jobs" / "j1"
    job_dir.mkdir(parents=True)
    (job_dir / "note.txt").write_text("root=/matraix/jobs/j1/trial\n", encoding="utf-8")
    rewrite_job_artifact_paths(
        job_dir,
        remote_repo="/matraix",
        local_job_dir=job_dir,
        job_name="j1",
    )
    assert "/matraix/" not in (job_dir / "note.txt").read_text(encoding="utf-8")


def test_prepare_modal_job_config_forces_jobs_dir() -> None:
    text = prepare_modal_job_config(
        "job_name: other\njobs_dir: /Users/me/jobs\n",
        job_name="j1",
    )
    assert "job_name: j1" in text
    assert "jobs_dir: jobs" in text


def test_execute_host_harbor_job_uses_module_command(tmp_path: Path) -> None:
    request = ModalHostJobRequest(
        job_name="j1",
        config_yaml="job_name: j1\njobs_dir: /tmp/elsewhere\n",
        repo_root=str(tmp_path),
        jobs_dir="jobs",
        env={},
        harbor_command=("/Users/me/.venv/bin/harbor", "run"),
    )
    seen: dict[str, object] = {}

    def _runner(command, *, cwd, env):
        seen["command"] = command
        seen["env"] = env
        job_dir = Path(cwd) / "jobs" / "j1"
        (job_dir / "agent").mkdir(parents=True)
        (job_dir / "result.json").write_text("{}", encoding="utf-8")
        return 0

    result = execute_host_harbor_job(request, command_runner=_runner, work_root=tmp_path)
    assert result.exit_code == 0
    assert result.artifact_tar
    command = seen["command"]
    assert command[:4] == list(HARBOR_MODULE_COMMAND)
    assert "/Users/me/.venv/bin/harbor" not in command
    env = seen["env"]
    assert str(tmp_path / "packages" / "playground" / "src") in str(env["PYTHONPATH"])


def test_execute_host_harbor_job_calls_progress(tmp_path: Path) -> None:
    request = ModalHostJobRequest(
        job_name="j1",
        config_yaml="job_name: j1\n",
        repo_root=str(tmp_path),
        jobs_dir="jobs",
        env={},
    )
    hits: list[str] = []

    def _runner(command, *, cwd, env):
        del command, env
        trial = Path(cwd) / "jobs" / "j1" / "survey__a"
        trial.mkdir(parents=True)
        (trial / "result.json").write_text("{}\n", encoding="utf-8")
        return 0

    def _progress(job_dir: Path) -> None:
        hits.append(job_dir.name)
        assert (job_dir / "survey__a" / "result.json").is_file()

    result = execute_host_harbor_job(
        request,
        command_runner=_runner,
        work_root=tmp_path,
        progress=_progress,
    )
    assert result.exit_code == 0
    assert hits


def test_sync_job_dir_to_volume_is_incremental(tmp_path: Path) -> None:
    src = tmp_path / "src" / "j1"
    (src / "survey__a").mkdir(parents=True)
    (src / "survey__a" / "result.json").write_text("{}\n", encoding="utf-8")
    (src / "result.json").write_text('{"job": true}\n', encoding="utf-8")
    vol = tmp_path / "vol"
    sync_job_dir_to_volume(src, volume_root=vol, job_name="j1")
    (vol / "j1" / "survey__a" / "keep.txt").write_text("stay\n", encoding="utf-8")
    (src / "survey__b").mkdir()
    (src / "survey__b" / "config.json").write_text("{}\n", encoding="utf-8")
    dest = sync_job_dir_to_volume(src, volume_root=vol, job_name="j1")
    assert dest == vol / "j1"
    assert (dest / "survey__a" / "keep.txt").read_text(encoding="utf-8") == "stay\n"
    status = json.loads((dest / "live_status.json").read_text(encoding="utf-8"))
    assert status["survey__b"] == "running"
    assert not (dest / "survey__b").exists()
    assert not (dest / "result.json").is_file()


def test_live_delta_skips_unchanged_trials(tmp_path: Path) -> None:
    src = tmp_path / "src" / "j1"
    trial = src / "survey__a"
    trial.mkdir(parents=True)
    (trial / "result.json").write_text("{}\n", encoding="utf-8")
    (trial / "agent" / "trace.json").parent.mkdir(parents=True)
    (trial / "agent" / "trace.json").write_text("{}\n", encoding="utf-8")
    vol = tmp_path / "vol"
    first = publish_live_trial_deltas(src, volume_root=vol, job_name="j1")
    (vol / "j1" / "survey__a" / "agent" / "extra.txt").write_text("keep\n", encoding="utf-8")
    second = publish_live_trial_deltas(src, volume_root=vol, job_name="j1")
    assert first > 0
    assert second == 0
    assert (vol / "j1" / "survey__a" / "agent" / "extra.txt").read_text(encoding="utf-8") == "keep\n"


class _MemVolume:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = {key.strip("/"): value for key, value in files.items()}
        self.reads: list[str] = []

    def reload(self) -> None:
        return None

    def listdir(self, prefix: str):
        remote = prefix.strip("/")
        found = []
        seen: set[str] = set()
        for path in self.files:
            if remote:
                if path == remote:
                    continue
                if not path.startswith(remote + "/"):
                    continue
                rest = path[len(remote) + 1 :]
            else:
                rest = path
            leaf = rest.split("/", 1)[0]
            child = "{}/{}".format(remote, leaf) if remote else leaf
            if child in seen:
                continue
            seen.add(child)
            found.append(type("Ent", (), {"path": child, "is_dir": "/" in rest})())
        return found

    def read_file(self, name: str):
        key = name.strip("/")
        self.reads.append(key)
        yield self.files[key]


def test_download_volume_job_merges_without_clobbering_compute_json(tmp_path: Path) -> None:
    dest = tmp_path / "jobs" / "demo"
    dest.mkdir(parents=True)
    (dest / "compute.json").write_text('{"family": "modal"}\n', encoding="utf-8")
    volume = _MemVolume(
        {
            "demo/s0/compute.json": b'{"family": "wrong"}\n',
            "demo/s0/result.json": b'{"shardOnly": true}\n',
            "demo/s0/survey__a/result.json": b'{"trial_uri": "file:///matraix/jobs/demo/survey__a"}\n',
        }
    )
    download_volume_job(volume, job_name="demo/s0", dest=dest)
    assert '"family": "modal"' in (dest / "compute.json").read_text(encoding="utf-8")
    assert not (dest / "result.json").is_file()
    result = (dest / "survey__a" / "result.json").read_text(encoding="utf-8")
    assert "/matraix/jobs/demo" not in result
    assert str(dest.resolve()) in result
    leftover = list((dest / "_generated").glob("live_pull_*"))
    assert leftover == []


def test_download_live_skips_already_completed_trials(tmp_path: Path) -> None:
    dest = tmp_path / "jobs" / "demo"
    done = dest / "survey__a"
    done.mkdir(parents=True)
    (done / "result.json").write_text("{}\n", encoding="utf-8")
    (dest / "compute.json").write_text('{"family": "modal"}\n', encoding="utf-8")
    volume = _MemVolume(
        {
            "demo/s0/live_status.json": b'{"survey__a": "done", "survey__b": "done"}\n',
            "demo/s0/survey__a/result.json": b'{"old": true}\n',
            "demo/s0/survey__a/agent/trace.json": b"big\n",
            "demo/s0/survey__b/result.json": b"{}\n",
        }
    )
    download_volume_job(volume, job_name="demo/s0", dest=dest, incremental=True)
    assert (dest / "survey__a" / "result.json").read_text(encoding="utf-8") == "{}\n"
    assert not (dest / "survey__a" / "agent").exists()
    assert (dest / "survey__b" / "result.json").is_file()
    assert "demo/s0/survey__a/agent/trace.json" not in volume.reads
    assert "demo/s0/survey__b/result.json" in volume.reads


def test_wait_modal_call_with_live_pull_merges_before_return(tmp_path: Path) -> None:
    dest = tmp_path / "jobs" / "demo"
    dest.mkdir(parents=True)
    (dest / "compute.json").write_text('{"family": "modal"}\n', encoding="utf-8")
    volume = _MemVolume(
        {
            "demo/s0/survey__a/result.json": b"{}\n",
        }
    )

    class _Call:
        def __init__(self) -> None:
            self.n = 0

        def get(self, timeout=None):
            del timeout
            self.n += 1
            if self.n < 2:
                raise TimeoutError()
            return {"exitCode": 0}

    raw = wait_modal_call_with_live_pull(
        _Call(),
        volume=volume,
        volume_job_name="demo/s0",
        dest=dest,
        poll_sec=0.01,
    )
    assert raw["exitCode"] == 0
    assert (dest / "survey__a" / "result.json").is_file()
    assert '"family": "modal"' in (dest / "compute.json").read_text(encoding="utf-8")


def test_invoke_modal_host_function_spawns_when_live_jobs_dir_set(tmp_path: Path) -> None:
    request = ModalHostJobRequest(
        job_name="demo",
        config_yaml="job_name: demo\n",
        repo_root=str(tmp_path),
        jobs_dir="jobs",
        env={},
        shard_key="s0",
        live_jobs_dir=str(tmp_path / "jobs"),
    )

    class _Call:
        def get(self, timeout=None):
            del timeout
            return {"exitCode": 0, "volumePath": "demo/s0"}

    class _Fn:
        def __init__(self) -> None:
            self.spawned: list[dict] = []
            self.remote_calls = 0

        def spawn(self, payload):
            self.spawned.append(payload)
            return _Call()

        def remote(self, payload):
            del payload
            self.remote_calls += 1
            raise AssertionError("live pull should spawn, not remote")

    fn = _Fn()
    raw = invoke_modal_host_function(fn, {"jobName": "demo"}, request=request, volume=None)
    assert raw["exitCode"] == 0
    assert fn.spawned
    assert fn.remote_calls == 0
    assert modal_volume_job_name("demo", "s0") == "demo/s0"


def test_invoke_modal_host_function_uses_remote_without_live_dir(tmp_path: Path) -> None:
    request = ModalHostJobRequest(
        job_name="demo",
        config_yaml="job_name: demo\n",
        repo_root=str(tmp_path),
        jobs_dir="jobs",
        env={},
    )

    class _Fn:
        def remote(self, payload):
            del payload
            return {"exitCode": 0}

        def spawn(self, payload):
            del payload
            raise AssertionError("should not spawn without live_jobs_dir")

    raw = invoke_modal_host_function(_Fn(), {"jobName": "demo"}, request=request)
    assert raw["exitCode"] == 0


def test_live_overlay_merges_shard_status(tmp_path: Path) -> None:
    dest = tmp_path / "jobs" / "demo"
    apply_live_overlay(dest, {"survey__a": "running"})
    apply_live_overlay(dest, {"survey__b": "done"})
    overlay = read_live_overlay(dest)
    assert overlay["survey__a"] == "running"
    assert overlay["survey__b"] == "done"
    assert overlay_status_code("done") == 2
    assert overlay_status_code("error") == 3


def test_live_publish_state_defers_full_trees_until_flush(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MATRIX_MODAL_ARTIFACT_FLUSH_TRIALS", "50")
    monkeypatch.setenv("MATRIX_MODAL_ARTIFACT_FLUSH_SEC", "3600")
    monkeypatch.setattr(
        "backend.service.modal_host_job.put_live_status_dict",
        lambda key, status: True,
    )
    src = tmp_path / "src" / "j1"
    trial = src / "survey__a"
    trial.mkdir(parents=True)
    (trial / "config.json").write_text("{}\n", encoding="utf-8")
    vol = tmp_path / "vol"
    live = LivePublishState()
    live.tick(src, volume_root=vol, job_name="j1", status_key="j1")
    assert (vol / "j1" / "live_status.json").is_file()
    assert not (vol / "j1" / "survey__a").exists()
    (trial / "result.json").write_text("{}\n", encoding="utf-8")
    (trial / "agent" / "trace.json").parent.mkdir(parents=True)
    (trial / "agent" / "trace.json").write_text("big\n", encoding="utf-8")
    commit = live.tick(src, volume_root=vol, job_name="j1", status_key="j1")
    assert commit is False
    assert not (vol / "j1" / "survey__a" / "agent").exists()
    live.tick(src, volume_root=vol, job_name="j1", status_key="j1", force=True)
    assert (vol / "j1" / "survey__a" / "agent" / "trace.json").is_file()


def test_materialize_requires_artifacts(tmp_path: Path) -> None:
    with pytest.raises(ModalHostJobError, match="without returning"):
        materialize_modal_artifacts(
            ModalHostJobResult(exit_code=0),
            jobs_dir=tmp_path / "jobs",
            job_name="missing",
        )


def test_collect_orchestrator_secret_env_rewrites_loopback_chatbot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHATBOT_API_URL", "http://127.0.0.1:8905")
    monkeypatch.setenv("MATRIX_CHATBOT_PUBLIC_URL", "https://tunnel.example")
    from backend.service.modal_host_job import collect_orchestrator_secret_env

    env = collect_orchestrator_secret_env()
    assert env["CHATBOT_API_URL"] == "https://tunnel.example"
