"""Schedule Harbor jobs as Modal Jobs.

Survey/chat keep Harbor ``environment.type: host``. Web/linux keep ``type: docker``
inside a Docker-capable worker; task images are prebuilt onto a Volume so later
dispatches skip ``docker compose build``. Artifacts merge into the same
``jobs/<job_name>/`` tree as a local run (``compute.json`` stays orchestrator-owned).
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tarfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

MODAL_HOST_APP_NAME = "matraix-host-jobs"
MODAL_HOST_FUNCTION_NAME = "harbor_host_job"
MODAL_DOCKER_FUNCTION_NAME = "harbor_docker_job"
MODAL_JOBS_VOLUME_NAME = "matraix-jobs"
MODAL_DOCKER_IMAGES_VOLUME_NAME = "matraix-docker-images"
MODAL_REMOTE_REPO = "/matraix"
HARBOR_MODULE_COMMAND = ("python", "-m", "harbor.cli.main", "run")
_PRESERVE_ON_MERGE = frozenset({"compute.json"})
_SKIP_ON_MERGE = frozenset({"result.json", "lock.json", "config.json"})
_LIVE_STATUS_FILENAME = "live_status.json"
LIVE_OVERLAY_FILENAME = "live_overlay.json"
CLOUD_RUN_FILENAME = "cloud_run.json"
MODAL_LIVE_STATUS_DICT = "matraix-live-status"
_LIVE_MARKER_NAMES = ("config.json", "trial.log", "persona_meta.json")
_TEXT_REWRITE_SUFFIXES = frozenset({
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".log",
    ".md",
    ".csv",
})
_SECRET_ENV_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "DASHSCOPE_API_KEY",
    "OPENROUTER_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "TOGETHER_API_KEY",
    "FIREWORKS_API_KEY",
    "AZURE_API_KEY",
    "AZURE_API_BASE",
    "CHATBOT_API_URL",
    "CHATBOT_MCP_URL",
    "CHATBOT_UPSTREAM_FINANCE",
    "CHATBOT_UPSTREAM_MEDICAL",
    "FINANCE_CHATBOT_URL",
    "MEDICAL_CHATBOT_URL",
)
_MAX_INLINE_TAR_BYTES = 40 * 1024 * 1024


class ModalHostJobError(RuntimeError):
    """Modal Jobs could not be scheduled or completed."""


@dataclass(frozen=True)
class ModalHostJobRequest:
    job_name: str
    config_yaml: str
    repo_root: str
    jobs_dir: str
    env: dict[str, str]
    harbor_command: tuple[str, ...] = HARBOR_MODULE_COMMAND
    secret_env: dict[str, str] = field(default_factory=dict)
    shard_key: str = ""
    live_jobs_dir: str = ""


@dataclass(frozen=True)
class ModalHostJobResult:
    exit_code: int
    artifact_tar: bytes | None = None
    error: str | None = None
    volume_path: str | None = None


class ModalHostJobRunner(Protocol):
    def run(self, request: ModalHostJobRequest) -> ModalHostJobResult: ...


def modal_credentials_configured() -> bool:
    token_id = (os.environ.get("MODAL_TOKEN_ID") or "").strip()
    token_secret = (os.environ.get("MODAL_TOKEN_SECRET") or "").strip()
    if token_id and token_secret:
        return True
    return (Path.home() / ".modal.toml").is_file()


def collect_orchestrator_secret_env() -> dict[str, str]:
    payload = {
        key: value
        for key in _SECRET_ENV_KEYS
        if (value := (os.environ.get(key) or "").strip())
    }
    from backend.service.chatbot_reachability import rewrite_chatbot_urls_for_cloud

    return rewrite_chatbot_urls_for_cloud(payload)


def modal_volume_job_name(job_name: str, shard_key: str = "") -> str:
    shard = (shard_key or "").strip()
    if shard:
        return "{}/{}".format(job_name, shard)
    return job_name


def _live_interval_sec(env_name: str, default: float = 5.0) -> float:
    raw = (os.environ.get(env_name) or "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        value = default
    if value <= 0:
        return default
    return max(value, 0.5)


def artifact_flush_trials() -> int:
    raw = (os.environ.get("MATRIX_MODAL_ARTIFACT_FLUSH_TRIALS") or "").strip()
    try:
        value = int(raw) if raw else 25
    except ValueError:
        value = 25
    return max(1, value)


def artifact_flush_sec() -> float:
    return _live_interval_sec("MATRIX_MODAL_ARTIFACT_FLUSH_SEC", 30.0)


def modal_pythonpath(repo_root: Path) -> str:
    entries = [
        str(repo_root),
        str(repo_root / "src"),
        str(repo_root / "environment" / "runtime"),
        str(repo_root / "environment" / "agents"),
        str(repo_root / "packages" / "playground" / "src"),
        str(repo_root / "application" / "playground"),
    ]
    return ":".join(entries)


def pack_job_dir(job_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        if job_dir.is_dir():
            archive.add(job_dir, arcname=job_dir.name)
    return buffer.getvalue()


def unpack_job_dir(artifact_tar: bytes, *, jobs_dir: Path, job_name: str) -> Path:
    return merge_job_artifacts(artifact_tar, jobs_dir=jobs_dir, job_name=job_name)


def merge_job_artifacts(
    artifact_tar: bytes,
    *,
    jobs_dir: Path,
    job_name: str,
    remote_repo: str = MODAL_REMOTE_REPO,
) -> Path:
    """Merge a packed Modal job tree into ``jobs/<job_name>/`` without clobbering meta."""
    jobs_dir.mkdir(parents=True, exist_ok=True)
    dest = jobs_dir / job_name
    dest.mkdir(parents=True, exist_ok=True)
    staging = jobs_dir / ".modal-unpack-{}-{}".format(job_name, uuid.uuid4().hex[:8])
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    buffer = io.BytesIO(artifact_tar)
    with tarfile.open(fileobj=buffer, mode="r:gz") as archive:
        try:
            archive.extractall(staging, filter="data")
        except TypeError:
            archive.extractall(staging)
    extracted = staging / job_name
    if not extracted.is_dir():
        children = [path for path in staging.iterdir() if path.is_dir()]
        extracted = children[0] if len(children) == 1 else staging
    _copy_tree_preserving(extracted, dest)
    shutil.rmtree(staging, ignore_errors=True)
    rewrite_job_artifact_paths(
        dest,
        remote_repo=remote_repo,
        local_job_dir=dest,
        job_name=job_name,
    )
    return dest


def merge_job_dir(src: Path, dest: Path) -> Path:
    """Copy a worker/staging job tree into the canonical ``jobs/<name>/``."""
    dest.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        _copy_tree_preserving(src, dest)
    return dest


def _copy_tree_preserving(src: Path, dest: Path) -> None:
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        target = dest / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if len(rel.parts) == 1 and rel.parts[0] in _SKIP_ON_MERGE:
            continue
        if rel.parts and rel.parts[0] in _PRESERVE_ON_MERGE and target.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _iter_trial_dirs(job_dir: Path) -> list[Path]:
    if not job_dir.is_dir():
        return []
    return sorted(
        path
        for path in job_dir.iterdir()
        if path.is_dir() and not path.name.startswith("_")
    )


def _trial_live_state(trial_dir: Path) -> str:
    if not trial_dir.is_dir():
        return "pending"
    result_path = trial_dir / "result.json"
    if result_path.is_file():
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict) and (payload.get("exception_info") or payload.get("error")):
            return "error"
        return "done"
    if any((trial_dir / name).is_file() for name in _LIVE_MARKER_NAMES) or (
        trial_dir / "agent"
    ).is_dir():
        return "running"
    return "pending"


def _copy_trial_tree(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        target = dest / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _copy_trial_markers(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name in _LIVE_MARKER_NAMES:
        file = src / name
        if file.is_file():
            shutil.copy2(file, dest / name)


def rewrite_job_artifact_paths(
    job_dir: Path,
    *,
    remote_repo: str,
    local_job_dir: Path,
    job_name: str,
) -> None:
    """Rewrite Modal absolute paths so Playground can read the local tree."""
    local = str(local_job_dir.resolve())
    remote_job = "{}/jobs/{}".format(remote_repo.rstrip("/"), job_name)
    replacements = (
        (remote_job, local),
        ("file://{}".format(remote_job), "file://{}".format(local)),
        ("{}/jobs".format(remote_repo.rstrip("/")), str(local_job_dir.parent.resolve())),
    )
    for path in job_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _TEXT_REWRITE_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        updated = text
        for old, new in replacements:
            updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def prepare_modal_job_config(config_yaml: str, *, job_name: str) -> str:
    """Force Harbor to write ``jobs/<job_name>/`` under the Modal repo root."""
    try:
        import yaml
    except ImportError:
        return config_yaml
    loaded = yaml.safe_load(config_yaml)
    if not isinstance(loaded, dict):
        return config_yaml
    loaded["job_name"] = job_name
    loaded["jobs_dir"] = "jobs"
    return yaml.safe_dump(loaded, sort_keys=False)


def modal_function_name_for_config(config_yaml: str) -> str:
    from backend.service.modal_docker_prebuild import harbor_environment_type

    if harbor_environment_type(config_yaml) == "docker":
        return MODAL_DOCKER_FUNCTION_NAME
    return MODAL_HOST_FUNCTION_NAME


def execute_host_harbor_job(
    request: ModalHostJobRequest,
    *,
    command_runner: Callable[..., int],
    work_root: Path | None = None,
    progress: Callable[[Path], None] | None = None,
) -> ModalHostJobResult:
    """Run Harbor and return a tarball of ``jobs/<job>``."""
    root = Path(work_root or request.repo_root)
    config_yaml = prepare_modal_job_config(request.config_yaml, job_name=request.job_name)
    from backend.service.modal_docker_prebuild import (
        DockerPrebuildError,
        prepare_docker_environment_for_job,
    )

    try:
        prepare_docker_environment_for_job(config_yaml, repo_root=root)
    except DockerPrebuildError as exc:
        return ModalHostJobResult(exit_code=1, error=str(exc))
    config_path = root / "configs" / "jobs" / "modal-host-incoming" / "{}.yaml".format(
        request.job_name
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_yaml, encoding="utf-8")
    command = list(HARBOR_MODULE_COMMAND) + ["--yes", "-c", str(config_path)]
    env = dict(os.environ)
    env.update(request.env)
    env.update(request.secret_env)
    env["PYTHONPATH"] = modal_pythonpath(root)
    env["MATRIX_REPO_ROOT"] = str(root)
    job_dir = root / "jobs" / request.job_name
    stop = threading.Event()
    interval = _live_interval_sec("MATRIX_MODAL_LIVE_PUSH_SEC")

    def _watch() -> None:
        while not stop.wait(interval):
            _call_progress(progress, job_dir)

    watcher: threading.Thread | None = None
    if progress is not None:
        watcher = threading.Thread(target=_watch, name="modal-live-push", daemon=True)
        watcher.start()
    exit_code = 1
    error_exc: str | None = None
    try:
        exit_code = int(command_runner(command, cwd=str(root), env=env))
    except Exception as exc:  # noqa: BLE001
        error_exc = str(exc)
        exit_code = 1
    finally:
        stop.set()
        if watcher is not None:
            watcher.join(timeout=interval + 2)
        _call_progress(progress, job_dir)
    if error_exc:
        return ModalHostJobResult(exit_code=1, error=error_exc)
    artifact = pack_job_dir(job_dir) if job_dir.is_dir() else None
    if artifact and len(artifact) > _MAX_INLINE_TAR_BYTES:
        artifact = None
    error = None if exit_code == 0 else "harbor run exited with code {}".format(exit_code)
    if exit_code == 0 and not job_dir.is_dir():
        error = "harbor run succeeded but wrote no jobs/{} tree".format(request.job_name)
        exit_code = 1
    return ModalHostJobResult(
        exit_code=exit_code,
        artifact_tar=artifact,
        error=error,
        volume_path=request.job_name if job_dir.is_dir() else None,
    )


def _call_progress(progress: Callable[[Path], None] | None, job_dir: Path) -> None:
    if progress is None or not job_dir.is_dir():
        return
    try:
        progress(job_dir)
    except Exception:
        pass


def collect_live_status(job_dir: Path) -> dict[str, str]:
    return {trial.name: _trial_live_state(trial) for trial in _iter_trial_dirs(job_dir)}


def write_live_status_file(status: dict[str, str], dest: Path) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(status, sort_keys=True) + "\n"
    path = dest / _LIVE_STATUS_FILENAME
    if path.is_file() and path.read_text(encoding="utf-8") == encoded:
        return False
    path.write_text(encoded, encoding="utf-8")
    return True


def apply_live_overlay(dest: Path, status: dict[str, str]) -> Path:
    """Merge shard live status into ``jobs/<job>/_generated/live_overlay.json``."""
    generated = dest / "_generated"
    generated.mkdir(parents=True, exist_ok=True)
    path = generated / LIVE_OVERLAY_FILENAME
    existing: dict[str, str] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = {str(key): str(value) for key, value in loaded.items()}
        except Exception:
            existing = {}
    merged = dict(existing)
    merged.update(status)
    encoded = json.dumps(merged, sort_keys=True) + "\n"
    if not path.is_file() or path.read_text(encoding="utf-8") != encoded:
        path.write_text(encoded, encoding="utf-8")
    return path


def read_live_overlay(job_dir: Path) -> dict[str, str]:
    path = job_dir / "_generated" / LIVE_OVERLAY_FILENAME
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {str(key): str(value) for key, value in loaded.items()}


def overlay_status_code(state: str | None) -> int | None:
    if state == "error":
        return 3
    if state == "done":
        return 2
    if state == "running":
        return 1
    if state == "pending":
        return 0
    return None


def put_live_status_dict(key: str, status: dict[str, str]) -> bool:
    try:
        import modal

        store = modal.Dict.from_name(MODAL_LIVE_STATUS_DICT, create_if_missing=True)
        store[key] = status
        return True
    except Exception:
        return False


def get_live_status_dict(key: str) -> dict[str, str] | None:
    try:
        import modal

        store = modal.Dict.from_name(MODAL_LIVE_STATUS_DICT)
        loaded = store[key]
    except Exception:
        return None
    if not isinstance(loaded, dict):
        return None
    return {str(name): str(state) for name, state in loaded.items()}


def cloud_run_path(job_dir: Path) -> Path:
    return job_dir / "_generated" / CLOUD_RUN_FILENAME


def load_cloud_run(job_dir: Path) -> dict[str, Any] | None:
    path = cloud_run_path(job_dir)
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


def save_cloud_run(job_dir: Path, payload: dict[str, Any]) -> Path:
    path = cloud_run_path(job_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def publish_job_to_volume(job_dir: Path, *, volume_root: Path, job_name: str) -> Path:
    dest = volume_root / job_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(job_dir, dest)
    return dest


def publish_live_status(job_dir: Path, *, volume_root: Path, job_name: str) -> bool:
    dest = volume_root / job_name
    return write_live_status_file(collect_live_status(job_dir), dest)


def publish_artifact_flush(job_dir: Path, *, volume_root: Path, job_name: str) -> list[str]:
    """Copy newly finished trial trees onto the volume. Skip already-copied dones."""
    dest = volume_root / job_name
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for trial in _iter_trial_dirs(job_dir):
        state = _trial_live_state(trial)
        if state not in {"done", "error"}:
            continue
        remote = dest / trial.name
        if _trial_live_state(remote) in {"done", "error"}:
            continue
        _copy_trial_tree(trial, remote)
        copied.append(trial.name)
    publish_live_status(job_dir, volume_root=volume_root, job_name=job_name)
    return copied


def publish_live_trial_deltas(job_dir: Path, *, volume_root: Path, job_name: str) -> int:
    """Status file plus any newly finished trial trees (used by tests / final flush)."""
    dest = volume_root / job_name
    dest.mkdir(parents=True, exist_ok=True)
    copied = publish_artifact_flush(job_dir, volume_root=volume_root, job_name=job_name)
    return (1 if publish_live_status(job_dir, volume_root=volume_root, job_name=job_name) else 0) + len(
        copied
    )


class LivePublishState:
    """Worker-side heartbeat: tiny status every tick, full trees on a slower flush."""

    def __init__(self) -> None:
        self.flushed_done: set[str] = set()
        self.last_flush_mono: float = 0.0

    def tick(
        self,
        job_dir: Path,
        *,
        volume_root: Path,
        job_name: str,
        status_key: str = "",
        force: bool = False,
    ) -> bool:
        """Return True when the Modal Volume should ``commit()`` (artifact flush or Dict miss)."""
        status = collect_live_status(job_dir)
        wrote_dict = False
        if status_key:
            wrote_dict = put_live_status_dict(status_key, status)
        status_changed = write_live_status_file(status, volume_root / job_name)
        done_names = {name for name, state in status.items() if state in {"done", "error"}}
        new_done = done_names - self.flushed_done
        now = time.monotonic()
        if self.last_flush_mono <= 0:
            self.last_flush_mono = now
        due = force or (
            bool(new_done)
            and (
                len(new_done) >= artifact_flush_trials()
                or (now - self.last_flush_mono) >= artifact_flush_sec()
            )
        )
        if due and new_done:
            copied = publish_artifact_flush(job_dir, volume_root=volume_root, job_name=job_name)
            self.flushed_done.update(copied or new_done)
            self.last_flush_mono = now
            return True
        if force:
            publish_live_status(job_dir, volume_root=volume_root, job_name=job_name)
            return True
        return bool(status_changed and not wrote_dict)


def sync_job_dir_to_volume(job_dir: Path, *, volume_root: Path, job_name: str) -> Path:
    dest = volume_root / job_name
    dest.mkdir(parents=True, exist_ok=True)
    publish_live_status(job_dir, volume_root=volume_root, job_name=job_name)
    publish_artifact_flush(job_dir, volume_root=volume_root, job_name=job_name)
    return dest


def download_volume_job(
    volume: Any,
    *,
    job_name: str,
    dest: Path,
    incremental: bool = False,
) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    try:
        volume.reload()
    except Exception:
        pass
    generated = dest / "_generated"
    generated.mkdir(parents=True, exist_ok=True)
    staging = generated / "live_pull_{}".format(uuid.uuid4().hex[:12])
    staging.mkdir(parents=True, exist_ok=True)
    local_job_name = job_name.split("/", 1)[0]
    try:
        if incremental:
            _download_live_trial_deltas(volume, job_name, dest, staging)
        else:
            _download_volume_prefix(volume, job_name, staging)
            if any(staging.iterdir()):
                _copy_tree_preserving(staging, dest)
            rewrite_job_artifact_paths(
                dest,
                remote_repo=MODAL_REMOTE_REPO,
                local_job_dir=dest,
                job_name=local_job_name,
            )
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return dest


def _download_live_trial_deltas(
    volume: Any,
    job_name: str,
    dest: Path,
    staging: Path,
) -> None:
    status = _read_volume_live_status(volume, job_name)
    if status is not None:
        names = [name for name, state in status.items() if state in {"running", "done"}]
    else:
        names = _list_volume_trial_names(volume, job_name)
    parent_job = job_name.split("/", 1)[0]
    for name in names:
        local = dest / name
        local_state = _trial_live_state(local)
        if local_state == "done":
            continue
        remote_state = status.get(name) if status is not None else None
        if remote_state == "running" or (
            local_state == "running" and remote_state != "done" and remote_state != "error"
        ):
            if remote_state in {None, "running", "pending"} and not _volume_trial_has_result(
                volume, job_name, name
            ):
                continue
        if remote_state == "pending":
            continue
        trial_staging = staging / name
        _download_volume_prefix(
            volume,
            "{}/{}".format(job_name.rstrip("/"), name),
            trial_staging,
        )
        if not trial_staging.is_dir() or not any(trial_staging.iterdir()):
            continue
        _copy_trial_tree(trial_staging, local)
        rewrite_job_artifact_paths(
            local,
            remote_repo=MODAL_REMOTE_REPO,
            local_job_dir=dest,
            job_name=parent_job,
        )


def _read_volume_live_status(volume: Any, job_name: str) -> dict[str, str] | None:
    path = "{}/{}".format(job_name.rstrip("/"), _LIVE_STATUS_FILENAME)
    try:
        raw = b"".join(volume.read_file(path))
        loaded = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(loaded, dict):
        return None
    return {str(key): str(value) for key, value in loaded.items()}


def _list_volume_trial_names(volume: Any, job_name: str) -> list[str]:
    try:
        entries = list(volume.listdir(job_name.strip("/") or "/"))
    except Exception:
        return []
    names: list[str] = []
    for entry in entries:
        name = getattr(entry, "path", None) or getattr(entry, "filename", "") or str(entry)
        leaf = Path(str(name).lstrip("/")).name
        is_dir = bool(getattr(entry, "is_dir", False)) or str(
            getattr(entry, "type", "")
        ).lower() in {"dir", "directory"}
        if not is_dir or not leaf or leaf.startswith("_"):
            continue
        names.append(leaf)
    return names


def _volume_trial_has_result(volume: Any, job_name: str, trial_name: str) -> bool:
    prefix = "{}/{}".format(job_name.rstrip("/"), trial_name)
    try:
        entries = list(volume.listdir(prefix))
    except Exception:
        return False
    for entry in entries:
        name = getattr(entry, "path", None) or getattr(entry, "filename", "") or str(entry)
        if Path(str(name).lstrip("/")).name == "result.json":
            return True
    return False


def _download_volume_prefix(volume: Any, prefix: str, dest: Path) -> None:
    remote = prefix.strip("/") or "/"
    try:
        entries = list(volume.listdir(remote))
    except Exception:
        entries = []
    if not entries:
        try:
            data = b"".join(volume.read_file(remote))
        except Exception:
            return
        dest.write_bytes(data)
        return
    for entry in entries:
        name = getattr(entry, "path", None) or getattr(entry, "filename", "") or str(entry)
        name = str(name).lstrip("/")
        leaf = Path(name).name
        target = dest / leaf
        is_dir = bool(getattr(entry, "is_dir", False)) or str(
            getattr(entry, "type", "")
        ).lower() in {"dir", "directory"}
        if is_dir:
            target.mkdir(parents=True, exist_ok=True)
            _download_volume_prefix(volume, name, target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_bytes(b"".join(volume.read_file(name)))
        except Exception:
            continue


def _is_modal_wait_timeout(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    return type(exc).__name__ in {"TimeoutError", "FunctionTimeoutError"}


def pull_live_progress(
    *,
    volume: Any | None,
    volume_job_name: str,
    dest: Path,
) -> None:
    """Apply shard status overlay, then pull any flushed trial trees."""
    dest.mkdir(parents=True, exist_ok=True)
    status = get_live_status_dict(volume_job_name)
    if status is None and volume is not None:
        try:
            volume.reload()
        except Exception:
            pass
        status = _read_volume_live_status(volume, volume_job_name)
    if status:
        apply_live_overlay(dest, status)
    if volume is not None:
        try:
            download_volume_job(
                volume,
                job_name=volume_job_name,
                dest=dest,
                incremental=True,
            )
        except Exception:
            pass


def wait_modal_call_with_live_pull(
    call: Any,
    *,
    volume: Any | None,
    volume_job_name: str,
    dest: Path | None,
    poll_sec: float = 5.0,
) -> Any:
    """Block on ``FunctionCall.get`` while applying live status and flushed artifacts."""
    while True:
        try:
            return call.get(timeout=poll_sec)
        except Exception as exc:
            if not _is_modal_wait_timeout(exc):
                raise
            if dest is not None:
                try:
                    pull_live_progress(
                        volume=volume,
                        volume_job_name=volume_job_name,
                        dest=dest,
                    )
                except Exception:
                    pass


def invoke_modal_host_function(
    fn: Any,
    payload: dict[str, Any],
    *,
    request: ModalHostJobRequest,
    volume: Any | None = None,
) -> Any:
    """Spawn the Modal function when live pull is enabled; otherwise ``.remote()``."""
    dest: Path | None = None
    live_root = (request.live_jobs_dir or "").strip()
    if live_root:
        dest = Path(live_root) / request.job_name
        dest.mkdir(parents=True, exist_ok=True)
    spawn = getattr(fn, "spawn", None)
    if dest is not None and callable(spawn):
        call = spawn(payload)
        return wait_modal_call_with_live_pull(
            call,
            volume=volume,
            volume_job_name=modal_volume_job_name(request.job_name, request.shard_key),
            dest=dest,
            poll_sec=_live_interval_sec("MATRIX_MODAL_LIVE_PULL_SEC"),
        )
    return fn.remote(payload)


def modal_function_call_id(call: Any) -> str:
    return str(
        getattr(call, "object_id", None)
        or getattr(call, "call_id", None)
        or ""
    )


def modal_function_call_from_id(call_id: str) -> Any:
    import modal

    factory = getattr(modal.FunctionCall, "from_id", None)
    if not callable(factory):
        raise ModalHostJobError("Modal FunctionCall.from_id is not available")
    return factory(call_id)


class SdkModalHostJobRunner:
    """Call a deployed Modal function on ``matraix-host-jobs``."""

    def spawn(self, request: ModalHostJobRequest) -> tuple[str, Any]:
        fn, payload = self._function_and_payload(request)
        spawn = getattr(fn, "spawn", None)
        if not callable(spawn):
            raise ModalHostJobError("Modal function does not support spawn()")
        try:
            call = spawn(payload)
        except Exception as exc:  # noqa: BLE001
            raise ModalHostJobError(
                "Modal Jobs function {}.{} is not reachable. "
                "Deploy application/playground/backend/service/modal_host_app.py "
                "({}).".format(MODAL_HOST_APP_NAME, modal_function_name_for_config(request.config_yaml), exc)
            ) from exc
        return modal_function_call_id(call), call

    def wait(
        self,
        request: ModalHostJobRequest,
        *,
        call: Any | None = None,
        call_id: str = "",
    ) -> ModalHostJobResult:
        resolved = call
        if resolved is None and (call_id or "").strip():
            try:
                resolved = modal_function_call_from_id(call_id.strip())
            except Exception as exc:  # noqa: BLE001
                raise ModalHostJobError(
                    "Modal FunctionCall {} is not reachable ({})".format(call_id, exc)
                ) from exc
        if resolved is None:
            fn, payload = self._function_and_payload(request)
            raw = invoke_modal_host_function(
                fn, payload, request=request, volume=self._volume(request)
            )
            return self._result_from_raw(raw)
        dest = None
        live_root = (request.live_jobs_dir or "").strip()
        if live_root:
            dest = Path(live_root) / request.job_name
            dest.mkdir(parents=True, exist_ok=True)
        try:
            raw = wait_modal_call_with_live_pull(
                resolved,
                volume=self._volume(request),
                volume_job_name=modal_volume_job_name(request.job_name, request.shard_key),
                dest=dest,
                poll_sec=_live_interval_sec("MATRIX_MODAL_LIVE_PULL_SEC"),
            )
        except Exception as exc:  # noqa: BLE001
            raise ModalHostJobError(
                "Modal Jobs function {}.{} is not reachable. "
                "Deploy application/playground/backend/service/modal_host_app.py "
                "({}).".format(
                    MODAL_HOST_APP_NAME,
                    modal_function_name_for_config(request.config_yaml),
                    exc,
                )
            ) from exc
        return self._result_from_raw(raw)

    def run(self, request: ModalHostJobRequest) -> ModalHostJobResult:
        call_id, call = self.spawn(request)
        return self.wait(request, call=call, call_id=call_id)

    def _function_and_payload(self, request: ModalHostJobRequest) -> tuple[Any, dict[str, Any]]:
        if not modal_credentials_configured():
            raise ModalHostJobError(
                "computeFamily=modal (Modal Jobs) requires Modal credentials "
                "(MODAL_TOKEN_ID and MODAL_TOKEN_SECRET, or ~/.modal.toml)"
            )
        try:
            import modal
        except ImportError as exc:
            raise ModalHostJobError(
                "computeFamily=modal requires the Modal SDK (pip install 'matraix[modal]')"
            ) from exc
        payload = {
            "jobName": request.job_name,
            "configYaml": request.config_yaml,
            "jobsDir": "jobs",
            "env": request.env,
            "secretEnv": request.secret_env or collect_orchestrator_secret_env(),
            "shardKey": request.shard_key,
        }
        function_name = modal_function_name_for_config(request.config_yaml)
        try:
            fn = modal.Function.from_name(MODAL_HOST_APP_NAME, function_name)
        except Exception as exc:  # noqa: BLE001
            raise ModalHostJobError(
                "Modal Jobs function {}.{} is not reachable. "
                "Deploy application/playground/backend/service/modal_host_app.py "
                "({}).".format(MODAL_HOST_APP_NAME, function_name, exc)
            ) from exc
        return fn, payload

    def _volume(self, request: ModalHostJobRequest) -> Any | None:
        if not (request.live_jobs_dir or "").strip():
            return None
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

    def _result_from_raw(self, raw: Any) -> ModalHostJobResult:
        if not isinstance(raw, dict):
            raise ModalHostJobError("Modal Jobs returned an unexpected payload")
        return ModalHostJobResult(
            exit_code=int(raw.get("exitCode") if raw.get("exitCode") is not None else 1),
            artifact_tar=_decode_artifact(raw),
            error=str(raw["error"]) if raw.get("error") else None,
            volume_path=str(raw["volumePath"]) if raw.get("volumePath") else None,
        )


def _decode_artifact(raw: dict[str, Any]) -> bytes | None:
    artifact = raw.get("artifactTar")
    if isinstance(artifact, (bytes, bytearray)):
        return bytes(artifact)
    encoded = raw.get("artifactTarB64")
    if isinstance(encoded, str) and encoded:
        import base64

        return base64.b64decode(encoded)
    return None


def materialize_modal_artifacts(
    result: ModalHostJobResult,
    *,
    jobs_dir: Path,
    job_name: str,
) -> Path:
    dest = jobs_dir / job_name
    dest.mkdir(parents=True, exist_ok=True)
    if result.artifact_tar:
        merge_job_artifacts(result.artifact_tar, jobs_dir=jobs_dir, job_name=job_name)
    elif result.volume_path:
        try:
            import modal
        except ImportError as exc:
            raise ModalHostJobError(
                "Modal Jobs wrote a volume path but the Modal SDK is not installed"
            ) from exc
        volume = modal.Volume.from_name(
            os.environ.get("MATRIX_MODAL_JOBS_VOLUME") or MODAL_JOBS_VOLUME_NAME
        )
        download_volume_job(volume, job_name=result.volume_path, dest=dest)
    else:
        raise ModalHostJobError(
            "Modal Jobs finished without returning jobs/{}/ artifacts".format(job_name)
        )
    return dest


def default_modal_host_job_runner() -> ModalHostJobRunner:
    return SdkModalHostJobRunner()


def write_compute_json(job_dir: Path, plan: Any) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)
    path = job_dir / "compute.json"
    payload = plan.to_public_dict() if hasattr(plan, "to_public_dict") else dict(plan)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
