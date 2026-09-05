"""Run web/linux Harbor jobs in a Modal Sandbox with Docker.

Playground starts the sandbox, persists its id in ``cloud_run.json``, and
reattaches after an API restart. Artifacts land on the jobs Volume so a
finished sandbox can still be pulled after it exits.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from backend.service.modal_host_job import (
    MODAL_DOCKER_IMAGES_VOLUME_NAME,
    MODAL_HOST_APP_NAME,
    MODAL_JOBS_VOLUME_NAME,
    MODAL_REMOTE_REPO,
    ModalHostJobError,
    ModalHostJobRequest,
    ModalHostJobResult,
    apply_worker_live_status,
    collect_live_status,
    collect_orchestrator_secret_env,
    execute_host_harbor_job,
    LivePublishState,
    modal_credentials_configured,
    modal_sandbox_object_id,
    modal_volume_job_name,
    pull_live_progress,
    publish_job_to_volume,
    encode_modal_sandbox_call_id,
)

SANDBOX_LIVE_PATH = "/tmp/matraix-live.json"
SANDBOX_RESULT_FILENAME = "_sandbox_result.json"
SANDBOX_PAYLOAD_ENV = "MATRIX_SANDBOX_PAYLOAD"
_SANDBOX_TIMEOUT_SEC = 2 * 60 * 60
_LIVE_PATH = Path(SANDBOX_LIVE_PATH)


def sandbox_jobs_volume_root() -> Path:
    return Path("/modal-jobs")


def sandbox_payload_remote_path(job_name: str, shard_key: str = "") -> str:
    return "_payloads/{}.json".format(modal_volume_job_name(job_name, shard_key))


def write_sandbox_live_status(job_dir: Path, dest: Path | None = None) -> dict[str, str]:
    status = collect_live_status(job_dir) if job_dir.is_dir() else {}
    target = dest if dest is not None else _LIVE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(status, sort_keys=True) + "\n", encoding="utf-8")
    return status


def load_sandbox_payload(path: Path | None = None) -> dict[str, Any]:
    raw_path = path or Path(
        (os.environ.get(SANDBOX_PAYLOAD_ENV) or "").strip() or "/modal-jobs/_payloads/job.json"
    )
    last_error = "payload not found"
    for _ in range(20):
        try:
            loaded = json.loads(raw_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            time.sleep(0.5)
            continue
        if isinstance(loaded, dict):
            return loaded
        last_error = "payload is not a JSON object"
        break
    raise ModalHostJobError(
        "sandbox worker could not read {} ({})".format(raw_path, last_error)
    )


def run_sandbox_worker(payload: dict[str, Any] | None = None) -> int:
    """Harbor + image cache inside the sandbox. Called as ``python -m``."""
    from backend.service.modal_docker_prebuild import ensure_docker_daemon

    ensure_docker_daemon()
    loaded = payload if payload is not None else load_sandbox_payload()
    request = ModalHostJobRequest(
        job_name=str(loaded.get("jobName") or ""),
        config_yaml=str(loaded.get("configYaml") or ""),
        repo_root=MODAL_REMOTE_REPO,
        jobs_dir="jobs",
        env=dict(loaded.get("env") or {}),
        secret_env={},
        shard_key=str(loaded.get("shardKey") or "").strip(),
    )
    volume_name = modal_volume_job_name(request.job_name, request.shard_key)
    volume_root = sandbox_jobs_volume_root()
    live = LivePublishState()
    jobs_volume = _mounted_volume(MODAL_JOBS_VOLUME_NAME, "MATRIX_MODAL_JOBS_VOLUME")
    docker_volume = _mounted_volume(
        MODAL_DOCKER_IMAGES_VOLUME_NAME, "MATRIX_MODAL_DOCKER_IMAGES_VOLUME"
    )
    if docker_volume is not None:
        try:
            docker_volume.reload()
        except Exception:
            pass

    def _live_publish(job_dir: Path) -> None:
        write_sandbox_live_status(job_dir)
        if live.tick(
            job_dir,
            volume_root=volume_root,
            job_name=volume_name,
            status_key=volume_name,
        ):
            _commit_volume(jobs_volume)

    result = execute_host_harbor_job(
        request,
        command_runner=_run_command,
        work_root=Path(MODAL_REMOTE_REPO),
        progress=_live_publish,
    )
    job_dir = Path(MODAL_REMOTE_REPO) / "jobs" / request.job_name
    write_sandbox_live_status(job_dir)
    volume_path = None
    if job_dir.is_dir():
        publish_job_to_volume(job_dir, volume_root=volume_root, job_name=volume_name)
        volume_path = volume_name
    _write_sandbox_result(volume_root / volume_name, result, volume_path)
    live.tick(
        job_dir,
        volume_root=volume_root,
        job_name=volume_name,
        status_key=volume_name,
        force=True,
    )
    _commit_volume(jobs_volume)
    _commit_volume(docker_volume)
    if result.error and result.exit_code == 0:
        return 1
    return int(result.exit_code)


def wait_sandbox_with_live_pull(
    sandbox: Any,
    *,
    request: ModalHostJobRequest,
    volume: Any | None,
    poll_sec: float = 5.0,
) -> int:
    dest = _live_dest(request)
    volume_job_name = modal_volume_job_name(request.job_name, request.shard_key)
    while True:
        code = sandbox_returncode(sandbox)
        if dest is not None:
            pull_sandbox_live(
                sandbox,
                dest=dest,
                volume=volume,
                volume_job_name=volume_job_name,
            )
        if code is not None:
            return int(code)
        time.sleep(poll_sec if poll_sec > 0 else 0.5)


def pull_sandbox_live(
    sandbox: Any,
    *,
    dest: Path,
    volume: Any | None,
    volume_job_name: str,
) -> None:
    raw = sandbox_exec_bytes(sandbox, "cat", SANDBOX_LIVE_PATH)
    if raw:
        apply_worker_live_status(dest, raw)
    pull_live_progress(volume=volume, volume_job_name=volume_job_name, dest=dest)


def sandbox_returncode(sandbox: Any) -> int | None:
    poll = getattr(sandbox, "poll", None)
    if callable(poll):
        try:
            code = poll()
        except Exception:
            code = None
        if code is not None:
            return int(code)
    code = getattr(sandbox, "returncode", None)
    if code is None:
        return None
    return int(code)


def sandbox_exec_bytes(sandbox: Any, *command: str) -> bytes:
    execute = getattr(sandbox, "exec", None)
    if not callable(execute):
        return b""
    try:
        proc = execute(*command)
    except Exception:
        return b""
    wait = getattr(proc, "wait", None)
    if callable(wait):
        try:
            wait()
        except Exception:
            return b""
    stdout = getattr(proc, "stdout", None)
    if stdout is None:
        return b""
    read = getattr(stdout, "read", None)
    if callable(read):
        try:
            data = read()
        except Exception:
            return b""
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        return str(data or "").encode("utf-8")
    if isinstance(stdout, (bytes, bytearray)):
        return bytes(stdout)
    return str(stdout).encode("utf-8")


def read_sandbox_result(volume: Any, volume_job_name: str) -> dict[str, Any] | None:
    path = "{}/{}".format(volume_job_name.rstrip("/"), SANDBOX_RESULT_FILENAME)
    try:
        volume.reload()
    except Exception:
        pass
    try:
        raw = b"".join(volume.read_file(path))
        loaded = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


class SdkModalSandboxJobRunner:
    """Create a Docker-capable Modal Sandbox and wait until Harbor finishes."""

    def spawn(self, request: ModalHostJobRequest) -> tuple[str, Any]:
        runtime = self._runtime(request)
        payload_path = sandbox_payload_remote_path(request.job_name, request.shard_key)
        self._upload_payload(runtime["jobs_volume"], payload_path, request)
        env = dict(runtime["worker_env"])
        env["MATRIX_DOCKER_IMAGE_CACHE"] = "/modal-docker-images"
        env[SANDBOX_PAYLOAD_ENV] = "/modal-jobs/{}".format(payload_path)
        env.update(request.env)
        env.update(request.secret_env or collect_orchestrator_secret_env())
        try:
            sandbox = runtime["modal"].Sandbox.create(
                "bash",
                "-lc",
                "cd {} && python -m backend.service.modal_sandbox_job".format(
                    MODAL_REMOTE_REPO
                ),
                app=runtime["app"],
                image=runtime["image"],
                timeout=_SANDBOX_TIMEOUT_SEC,
                cpu=2,
                memory=8192,
                volumes={
                    "/modal-jobs": runtime["jobs_volume"],
                    "/modal-docker-images": runtime["docker_volume"],
                },
                secrets=runtime["secrets"],
                env=env,
                experimental_options={"enable_docker": True},
            )
        except Exception as exc:  # noqa: BLE001
            raise ModalHostJobError(
                "Modal Sandbox for {} could not be created. "
                "Deploy application/playground/backend/service/modal_host_app.py "
                "({}).".format(MODAL_HOST_APP_NAME, exc)
            ) from exc
        object_id = str(
            getattr(sandbox, "object_id", None) or getattr(sandbox, "sandbox_id", None) or ""
        )
        if not object_id:
            raise ModalHostJobError("Modal Sandbox did not return an id")
        return encode_modal_sandbox_call_id(object_id), sandbox

    def wait(
        self,
        request: ModalHostJobRequest,
        *,
        call: Any | None = None,
        call_id: str = "",
    ) -> ModalHostJobResult:
        sandbox = call
        object_id = modal_sandbox_object_id(call_id)
        if sandbox is None and object_id:
            try:
                sandbox = self._runtime(request)["modal"].Sandbox.from_id(object_id)
            except Exception as exc:  # noqa: BLE001
                sandbox = None
                from_id_error = exc
            else:
                from_id_error = None
        else:
            from_id_error = None
        volume = self._jobs_volume()
        volume_job_name = modal_volume_job_name(request.job_name, request.shard_key)
        dest = _live_dest(request)
        exit_code: int | None = None
        if sandbox is not None:
            try:
                exit_code = wait_sandbox_with_live_pull(
                    sandbox,
                    request=request,
                    volume=volume,
                    poll_sec=_poll_sec(),
                )
            except Exception as exc:  # noqa: BLE001
                raise ModalHostJobError(
                    "Modal Sandbox {} is not reachable ({})".format(
                        object_id or call_id, exc
                    )
                ) from exc
        elif from_id_error is not None and volume is None:
            raise ModalHostJobError(
                "Modal Sandbox {} is not reachable ({})".format(object_id, from_id_error)
            ) from from_id_error
        if dest is not None:
            pull_live_progress(
                volume=volume,
                volume_job_name=volume_job_name,
                dest=dest,
            )
        stored = read_sandbox_result(volume, volume_job_name) if volume is not None else None
        if exit_code is None and stored and stored.get("exitCode") is not None:
            exit_code = int(stored["exitCode"])
        if exit_code is None:
            exit_code = 1
        error = None
        if stored and stored.get("error"):
            error = str(stored["error"])
        elif exit_code != 0:
            error = "Modal Sandbox exited with code {}".format(exit_code)
        volume_path = None
        if stored and stored.get("volumePath"):
            volume_path = str(stored["volumePath"])
        elif volume is not None:
            volume_path = volume_job_name
        return ModalHostJobResult(
            exit_code=exit_code,
            error=error,
            volume_path=volume_path,
        )

    def run(self, request: ModalHostJobRequest) -> ModalHostJobResult:
        call_id, sandbox = self.spawn(request)
        return self.wait(request, call=sandbox, call_id=call_id)

    def _runtime(self, request: ModalHostJobRequest) -> dict[str, Any]:
        del request
        if not modal_credentials_configured():
            raise ModalHostJobError(
                "computeFamily=modal requires Modal credentials "
                "(MODAL_TOKEN_ID and MODAL_TOKEN_SECRET, or ~/.modal.toml)"
            )
        try:
            import modal
        except ImportError as exc:
            raise ModalHostJobError(
                "computeFamily=modal requires the Modal SDK (pip install 'matraix[modal]')"
            ) from exc
        try:
            from backend.service import modal_host_app as host_app
        except Exception as exc:  # noqa: BLE001
            raise ModalHostJobError(
                "Modal sandbox image is not available ({})".format(exc)
            ) from exc
        try:
            app = modal.App.lookup(MODAL_HOST_APP_NAME, create_if_missing=True)
        except Exception as exc:  # noqa: BLE001
            raise ModalHostJobError(
                "Modal app {} is not reachable. "
                "Deploy application/playground/backend/service/modal_host_app.py "
                "({}).".format(MODAL_HOST_APP_NAME, exc)
            ) from exc
        return {
            "modal": modal,
            "app": app,
            "image": host_app.docker_image,
            "jobs_volume": host_app.volume,
            "docker_volume": host_app.docker_images_volume,
            "secrets": list(getattr(host_app, "_secrets", None) or []),
            "worker_env": dict(getattr(host_app, "_WORKER_ENV", None) or {}),
        }

    def _upload_payload(self, volume: Any, remote_path: str, request: ModalHostJobRequest) -> None:
        payload = {
            "jobName": request.job_name,
            "configYaml": request.config_yaml,
            "env": request.env,
            "shardKey": request.shard_key,
        }
        encoded = json.dumps(payload).encode("utf-8")
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        try:
            handle.write(encoded)
            handle.close()
            with volume.batch_upload() as batch:
                batch.put_file(handle.name, remote_path)
        except Exception as exc:  # noqa: BLE001
            raise ModalHostJobError(
                "could not upload sandbox payload ({})".format(exc)
            ) from exc
        finally:
            try:
                os.unlink(handle.name)
            except OSError:
                pass

    def _jobs_volume(self) -> Any | None:
        try:
            import modal
        except ImportError:
            return None
        try:
            return modal.Volume.from_name(
                os.environ.get("MATRIX_MODAL_JOBS_VOLUME") or MODAL_JOBS_VOLUME_NAME
            )
        except Exception:
            return None


def _live_dest(request: ModalHostJobRequest) -> Path | None:
    root = (request.live_jobs_dir or "").strip()
    if not root:
        return None
    dest = Path(root) / request.job_name
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _poll_sec() -> float:
    raw = (os.environ.get("MATRIX_MODAL_LIVE_PULL_SEC") or "").strip()
    try:
        value = float(raw) if raw else 5.0
    except ValueError:
        value = 5.0
    if value <= 0:
        return 5.0
    return max(value, 0.5)


def _run_command(command: list[str], *, cwd: str, env: dict[str, str]) -> int:
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    return int(completed.returncode)


def _mounted_volume(default_name: str, env_name: str) -> Any | None:
    try:
        import modal
    except ImportError:
        return None
    try:
        return modal.Volume.from_name(os.environ.get(env_name) or default_name)
    except Exception:
        return None


def _commit_volume(volume: Any | None) -> None:
    if volume is None:
        return
    try:
        volume.commit()
    except Exception:
        pass


def _write_sandbox_result(
    dest: Path,
    result: ModalHostJobResult,
    volume_path: str | None,
) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    payload = {
        "exitCode": int(result.exit_code),
        "error": result.error,
        "volumePath": volume_path,
    }
    (dest / SANDBOX_RESULT_FILENAME).write_text(
        json.dumps(payload) + "\n", encoding="utf-8"
    )


def main() -> int:
    try:
        return run_sandbox_worker()
    except Exception as exc:  # noqa: BLE001
        volume_name = (os.environ.get("MATRIX_SANDBOX_VOLUME_NAME") or "").strip()
        if volume_name:
            try:
                _write_sandbox_result(
                    Path("/modal-jobs") / volume_name,
                    ModalHostJobResult(exit_code=1, error=str(exc)),
                    volume_name,
                )
                _commit_volume(
                    _mounted_volume(MODAL_JOBS_VOLUME_NAME, "MATRIX_MODAL_JOBS_VOLUME")
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
