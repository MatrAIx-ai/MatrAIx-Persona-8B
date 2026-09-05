"""Modal app for Harbor jobs.

Survey and chat use the ``harbor_host_job`` Function. Web and Linux use a
Sandbox from this app’s Docker image (task images cached on
``matraix-docker-images``). Deploy once from a MatrAIx checkout:

    uv run --extra modal modal deploy application/playground/backend/service/modal_host_app.py

Optional: ``modal secret create matraix-llm ANTHROPIC_API_KEY=...``
(or set ``MATRIX_MODAL_SECRET``). Orchestrator env keys are also passed per call.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path

import modal

# Modal hydrates this file as /root/modal_host_app.py, so PYTHONPATH from
# local deploy is gone. Put the baked-in playground (or this checkout) first.
for _path in (
    Path("/matraix/application/playground"),
    Path(__file__).resolve().parent.parent.parent,
):
    if _path.is_dir() and (_path / "backend").is_dir():
        _text = str(_path)
        if _text not in sys.path:
            sys.path.insert(0, _text)
        break

from backend.service.modal_host_job import (  # noqa: E402
    HARBOR_MODULE_COMMAND,
    MODAL_DOCKER_IMAGES_VOLUME_NAME,
    MODAL_HOST_APP_NAME,
    MODAL_JOBS_VOLUME_NAME,
    MODAL_REMOTE_REPO,
    LivePublishState,
    ModalHostJobRequest,
    execute_host_harbor_job,
    modal_volume_job_name,
    publish_job_to_volume,
)


def _resolve_repo_root() -> str:
    env = (os.environ.get("MATRIX_REPO_ROOT") or "").strip()
    if env and Path(env).is_dir():
        return env
    remote = Path(MODAL_REMOTE_REPO)
    if remote.is_dir():
        return str(remote)
    here = Path(__file__).resolve()
    if len(here.parents) > 4:
        return str(here.parents[4])
    return MODAL_REMOTE_REPO


_REPO_ROOT = _resolve_repo_root()
_SECRET_NAME = os.environ.get("MATRIX_MODAL_SECRET") or "matraix-llm"
_VOLUME_NAME = os.environ.get("MATRIX_MODAL_JOBS_VOLUME") or MODAL_JOBS_VOLUME_NAME
_DOCKER_VOLUME_NAME = (
    os.environ.get("MATRIX_MODAL_DOCKER_IMAGES_VOLUME") or MODAL_DOCKER_IMAGES_VOLUME_NAME
)
_REPO_IGNORE = [
    "**/.git/**",
    "**/node_modules/**",
    "**/.venv/**",
    "**/jobs/**",
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "**/.mypy_cache/**",
    "**/.env*",
    "**/docs/**",
    "**/*.pdf",
    "**/persona/datasets/generated*/**",
]
_PYTHONPATH = (
    "{root}/application/playground:{root}:{root}/src:"
    "{root}/environment/runtime:{root}/environment/agents:"
    "{root}/packages/playground/src"
).format(root=MODAL_REMOTE_REPO)
_WORKER_ENV = {
    "MATRIX_REPO_ROOT": MODAL_REMOTE_REPO,
    "PYTHONPATH": _PYTHONPATH,
}


def _install_repo(image: modal.Image) -> modal.Image:
    return (
        image.add_local_dir(
            _REPO_ROOT,
            remote_path=MODAL_REMOTE_REPO,
            copy=True,
            ignore=_REPO_IGNORE,
        ).run_commands(
            "cd {} && uv pip install --system --compile-bytecode -e '.[modal]'".format(
                MODAL_REMOTE_REPO
            )
        )
    )


image = _install_repo(
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "build-essential", "ca-certificates")
    .pip_install("uv")
)

docker_image = _install_repo(
    modal.Image.debian_slim(python_version="3.12")
    .apt_install(
        "git",
        "build-essential",
        "ca-certificates",
        "curl",
        "docker.io",
        "iptables",
        "fuse-overlayfs",
    )
    .pip_install("uv")
    .run_commands(
        "mkdir -p /usr/libexec/docker/cli-plugins",
        "curl -fsSL "
        "https://github.com/docker/compose/releases/download/v2.29.7/"
        "docker-compose-linux-x86_64 "
        "-o /usr/libexec/docker/cli-plugins/docker-compose",
        "chmod +x /usr/libexec/docker/cli-plugins/docker-compose",
    )
)

volume = modal.Volume.from_name(_VOLUME_NAME, create_if_missing=True)
docker_images_volume = modal.Volume.from_name(_DOCKER_VOLUME_NAME, create_if_missing=True)
_secrets: list[modal.Secret] = []
try:
    _secrets.append(modal.Secret.from_name(_SECRET_NAME))
except Exception:
    pass

app = modal.App(MODAL_HOST_APP_NAME, image=image)


def _run_command(command: list[str], *, cwd: str, env: dict[str, str]) -> int:
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    return int(completed.returncode)


def _complete_harbor_job(payload: dict) -> dict:
    shard_key = str(payload.get("shardKey") or "").strip()
    request = ModalHostJobRequest(
        job_name=str(payload["jobName"]),
        config_yaml=str(payload["configYaml"]),
        repo_root=MODAL_REMOTE_REPO,
        jobs_dir="jobs",
        env=dict(payload.get("env") or {}),
        harbor_command=HARBOR_MODULE_COMMAND,
        secret_env=dict(payload.get("secretEnv") or {}),
        shard_key=shard_key,
    )
    volume_name = modal_volume_job_name(request.job_name, shard_key)
    volume_root = Path("/modal-jobs")
    live = LivePublishState()

    def _live_publish(job_dir: Path) -> None:
        if live.tick(
            job_dir,
            volume_root=volume_root,
            job_name=volume_name,
            status_key=volume_name,
        ):
            volume.commit()

    result = execute_host_harbor_job(
        request,
        command_runner=_run_command,
        work_root=Path(MODAL_REMOTE_REPO),
        progress=_live_publish,
    )
    job_dir = Path(MODAL_REMOTE_REPO) / "jobs" / request.job_name
    volume_path = None
    if job_dir.is_dir():
        publish_job_to_volume(job_dir, volume_root=volume_root, job_name=volume_name)
        volume.commit()
        volume_path = volume_name
    artifact_b64 = None
    if result.artifact_tar:
        artifact_b64 = base64.b64encode(result.artifact_tar).decode("ascii")
    return {
        "exitCode": result.exit_code,
        "error": result.error,
        "artifactTarB64": artifact_b64,
        "volumePath": volume_path,
    }


@app.function(
    timeout=60 * 60,
    cpu=1.0,
    memory=4096,
    volumes={"/modal-jobs": volume},
    secrets=_secrets,
    env=_WORKER_ENV,
)
def harbor_host_job(payload: dict) -> dict:
    return _complete_harbor_job(payload)


@app.function(image=docker_image, timeout=60, cpu=0.125, memory=256)
def harbor_docker_image() -> str:
    """Docker image for web/linux Sandboxes."""
    return "ok"
