"""Launch and inspect Harbor batch jobs from Playground."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
import tomllib
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from backend.service.application_types import normalize_metadata_type
from backend.service.config import persona_model as default_persona_model
from backend.service.job_aggregation import (
    DEFAULT_REPORTING_LLM_MODEL,
    REPORTING_LLM_ENABLE_ENV,
    REPORTING_LLM_MODEL_ENV,
    build_job_aggregation,
    job_aggregation_artifact_is_fresh,
    read_job_aggregation_artifact,
    read_reporting_status_artifact,
    reporting_status_artifact_path,
    write_reporting_status_artifact,
)
from playground.harbor.playground import (
    _default_harbor_command,
    _repo_root,
    _run_subprocess,
)
from playground.remote_runner.dispatch import filter_remote_harbor_payload_env
from matraix.application_job import (
    DEFAULT_APPLICATION_JOBS_DIR,
    build_application_job_config,
    resolve_job_environment,
)
from matraix.launch_env import build_launch_env

DEFAULT_AGENT_BY_TYPE: dict[str, str] = {
    # Keys here stay canonical; ``normalize_metadata_type()`` handles legacy
    # task metadata aliases before these lookup tables are consulted.
    "survey": "persona-json-survey",
    "chatbot": "persona-user-sim",
    "web": "persona-openhands-sdk",
    "os-app": "persona-computer-1",
}

AUTO_TRIAL_PROFILE_BY_TYPE: dict[str, str] = {
    "survey": "json_survey",
    "chatbot": "user_sim_chat",
    "web": "docker_agent",
    "os-app": "docker_agent",
}

logger = logging.getLogger(__name__)


def _should_use_local_distributed_harbor(
    *,
    execution_mode: str,
    execution_plane: str,
    trial_profile: str | None,
) -> bool:
    return (
        (execution_mode or "auto").strip().lower() == "auto"
        and execution_plane == "harbor"
        and trial_profile in {"json_survey", "user_sim_chat"}
    )


def _read_task_metadata_type(task_path: str, *, repo_root: Path | None = None) -> str | None:
    root = repo_root or _repo_root()
    toml_path = Path(task_path)
    if toml_path.is_absolute() and toml_path.is_dir():
        toml_path = toml_path / "task.toml"
    elif toml_path.is_absolute() and toml_path.is_file():
        pass
    elif toml_path.is_dir():
        toml_path = toml_path / "task.toml"
    elif str(task_path).endswith(".toml"):
        toml_path = Path(task_path)
    else:
        toml_path = root / task_path / "task.toml"
    if not toml_path.is_file():
        return None
    raw = toml_path.read_text(encoding="utf-8")
    payload: dict[str, Any] | None = None
    try:
        loaded = tomllib.loads(raw)
        payload = loaded if isinstance(loaded, dict) else None
    except Exception:  # noqa: BLE001
        try:
            loaded = yaml.safe_load(raw)
            payload = loaded if isinstance(loaded, dict) else None
        except Exception:  # noqa: BLE001
            payload = None
    if payload is None:
        return None
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and metadata.get("type"):
        return str(metadata["type"])
    task = payload.get("task")
    if isinstance(task, dict) and task.get("type"):
        return str(task["type"])
    return None


def resolve_trial_profile(
    task_path: str,
    *,
    mode: str = "auto",
    repo_root: Path | None = None,
) -> str:
    """Return the Harbor trial profile label for a task + execution mode."""
    normalized_mode = (mode or "auto").strip().lower()
    if normalized_mode == "smoke":
        return "smoke"
    if normalized_mode == "force_docker":
        return "docker_agent"
    task_type = normalize_metadata_type(_read_task_metadata_type(task_path, repo_root=repo_root))
    if not task_type and repo_root is not None:
        _ = repo_root
    return AUTO_TRIAL_PROFILE_BY_TYPE.get(task_type or "survey", "docker_agent")


def resolve_agent_name(
    task_path: str,
    *,
    repo_root: Path,
    explicit: str | None = None,
    mode: str = "auto",
    trial_profile: str | None = None,
) -> str:
    if explicit:
        return explicit
    profile = trial_profile or resolve_trial_profile(
        task_path, mode=mode, repo_root=repo_root
    )
    if profile == "json_survey":
        return "persona-json-survey"
    if profile == "user_sim_chat":
        return "persona-user-sim"
    normalized_mode = (mode or "auto").strip().lower()
    if normalized_mode == "smoke":
        return DEFAULT_AGENT_BY_TYPE.get("survey", "persona-claude-code")
    normalized = task_path.replace("\\", "/").lower()
    if "browser-use" in normalized:
        return "persona-browser-use"
    if "cocoa" in normalized:
        return "persona-cocoa"
    if "computer-use" in normalized or "os-app" in normalized or "cua" in normalized:
        return "persona-computer-1"
    task_type = normalize_metadata_type(_read_task_metadata_type(task_path, repo_root=repo_root))
    if task_type == "web":
        return "persona-openhands-sdk"
    if normalized_mode == "force_docker" or profile == "docker_agent":
        return "persona-claude-code"
    return DEFAULT_AGENT_BY_TYPE.get(task_type or "survey", "persona-claude-code")


def _map_task_metadata_type(task_type: str | None) -> str:
    if not task_type:
        return "unknown"
    mapped = normalize_metadata_type(task_type)
    if mapped in {"web", "survey", "chatbot", "os-app"}:
        return mapped
    return "unknown"


def _task_path_from_generated_config(config_path: Path) -> str | None:
    if not config_path.is_file():
        return None
    try:
        for line in config_path.read_text(encoding="utf-8").splitlines()[:24]:
            if line.startswith("# Task:"):
                task_path = line[len("# Task:") :].strip()
                return task_path or None
    except OSError:
        return None
    return None


def _task_path_from_trial_config(trial_dir: Path) -> str | None:
    config_path = trial_dir / "config.json"
    if not config_path.is_file():
        return None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    task_block = config.get("task") if isinstance(config.get("task"), dict) else {}
    task_path = str(task_block.get("path") or "").strip()
    return task_path or None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _trial_result_error(result: dict[str, Any] | None) -> str | None:
    if not result:
        return None
    exc = result.get("exception_info")
    if not exc:
        return None
    if isinstance(exc, dict):
        return str(
            exc.get("exception_message")
            or exc.get("exception_type")
            or "Harbor trial failed"
        )
    return "Harbor trial failed"


def _read_vnc_url(trial_dir: Path) -> str | None:
    vnc_path = trial_dir / "vnc_url.txt"
    if vnc_path.is_file():
        url = vnc_path.read_text(encoding="utf-8").strip()
        return url or None
    return None


def _read_sandbox_id(trial_dir: Path) -> str | None:
    path = trial_dir / "sandbox_id.txt"
    if path.is_file():
        value = path.read_text(encoding="utf-8").strip()
        return value or None
    return None


def _trial_live_phase(trial_dir: Path) -> str | None:
    from playground.harbor.trial_events import (
        EVENTS_FILENAME,
        read_events_after,
    )

    events, _ = read_events_after(trial_dir / EVENTS_FILENAME, 0)
    for event in reversed(events):
        if event.get("type") == "phase" and event.get("phase"):
            return str(event["phase"])
    return None


_PHASE_TO_STAGE: dict[str, str] = {
    "harbor_starting": "starting_env",
    "persona_kickoff": "agent_running",
    "application_thinking": "agent_running",
    "persona_thinking": "agent_running",
    "web_simulating": "agent_running",
    "survey_answering": "agent_running",
    "appworld_simulating": "agent_running",
    "harbor_collecting_artifacts": "verifying",
    "persona_feedback": "verifying",
}


def _stage_from_phase(phase: str | None) -> str | None:
    if not phase:
        return None
    return _PHASE_TO_STAGE.get(phase)


def _trial_live_stage(trial_dir: Path) -> str | None:
    """Infer Harbor trial lifecycle stage from on-disk artifacts."""
    if not trial_dir.is_dir():
        return "queued"
    if (trial_dir / "result.json").is_file():
        return None

    verifier_dir = trial_dir / "verifier"
    if verifier_dir.is_dir():
        verifier_markers = (
            "test-stdout.txt",
            "reward.txt",
            "reward.json",
            "ctrf.json",
        )
        if any((verifier_dir / name).is_file() for name in verifier_markers):
            return "verifying"
        try:
            if any(verifier_dir.iterdir()):
                return "verifying"
        except OSError:
            pass

    agent_dir = trial_dir / "agent"
    if agent_dir.is_dir():
        try:
            for path in agent_dir.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(agent_dir)
                if rel.parts and rel.parts[0] == "setup":
                    continue
                return "agent_running"
        except OSError:
            pass

    if (trial_dir / "trial.log").is_file() or (trial_dir / "config.json").is_file():
        return "starting_env"

    return "starting_env"


def _resolve_trial_stage(trial_dir: Path, *, phase: str | None, completed: bool) -> str | None:
    if completed:
        return None
    from_phase = _stage_from_phase(phase)
    if from_phase:
        return from_phase
    return _trial_live_stage(trial_dir)


def _persona_meta_from_trial(trial_dir: Path) -> dict[str, Any]:
    meta_path = trial_dir / "persona_meta.json"
    if not meta_path.is_file():
        return {}
    try:
        import json

        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _parse_iso_timestamp(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


# Harbor lock.json is a reproducibility snapshot and is left on disk after the
# run ends, so it is not a liveness signal. External CLI jobs (no in-memory
# launch record) are "running" only while result.json still looks in-flight
# AND something on disk has moved recently.
EXTERNAL_RUN_STALE_AFTER_SEC = 10 * 60


def _stats_in_flight(stats: dict[str, Any]) -> bool:
    try:
        running = int(stats.get("n_running_trials") or 0)
        pending = int(stats.get("n_pending_trials") or 0)
    except (TypeError, ValueError):
        return False
    return running > 0 or pending > 0


def _job_result_activity_ts(job_result: dict[str, Any] | None) -> float | None:
    if not isinstance(job_result, dict):
        return None
    return _parse_iso_timestamp(job_result.get("updated_at")) or _parse_iso_timestamp(
        job_result.get("started_at")
    )


def _path_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _external_run_activity_ts(
    job_dir: Path,
    *,
    job_result: dict[str, Any] | None,
    trial_names: list[str],
) -> float | None:
    """Latest evidence that an externally driven job is still writing artifacts."""
    latest = _job_result_activity_ts(job_result)
    for path in (job_dir / "result.json", job_dir / "job.log"):
        mtime = _path_mtime(path)
        if mtime is not None:
            latest = mtime if latest is None else max(latest, mtime)
    for trial_name in trial_names:
        trial_dir = job_dir / trial_name
        if (trial_dir / "result.json").is_file():
            continue
        for path in (trial_dir, trial_dir / "trial.log"):
            mtime = _path_mtime(path)
            if mtime is not None:
                latest = mtime if latest is None else max(latest, mtime)
    return latest


def _activity_is_live(*, activity_ts: float | None, now_ts: float) -> bool:
    if activity_ts is None:
        return False
    return (now_ts - activity_ts) <= EXTERNAL_RUN_STALE_AFTER_SEC


def _job_list_status(
    *,
    trial_count: int,
    completed_trials: int,
    failed_trials_on_disk: int,
    job_result: dict[str, Any] | None,
    launch: HarborLaunchRecord | None,
    activity_ts: float | None = None,
    now_ts: float | None = None,
) -> tuple[str, int]:
    """Return ``(status, failedTrials)`` for a Harbor job list row."""
    failed_trials = failed_trials_on_disk
    if isinstance(job_result, dict):
        stats = job_result.get("stats")
        if isinstance(stats, dict):
            try:
                failed_trials = int(stats.get("n_errored_trials") or 0)
            except (TypeError, ValueError):
                failed_trials = failed_trials_on_disk
        if job_result.get("finished_at"):
            if failed_trials > 0:
                return "failed", failed_trials
            if launch is not None and launch.status == "failed":
                return "failed", failed_trials
            return "success", 0

    # An in-memory launch record only exists while THIS backend process is
    # driving the run (records are created at launch and never expire until the
    # process ends). So a live "queued"/"running" record is the only reliable
    # signal that the job is actually progressing right now.
    if launch is not None and launch.status in {"queued", "running"}:
        return "running", 0
    if launch is not None and launch.status == "failed":
        return "failed", failed_trials

    # Externally driven runs (matraix run / docker exec) have no launch record.
    # Trust in-flight stats from result.json only while artifacts are still
    # fresh — a killed process leaves n_running_trials > 0 with no finished_at.
    if isinstance(job_result, dict):
        stats = job_result.get("stats")
        if isinstance(stats, dict) and _stats_in_flight(stats):
            clock = time.time() if now_ts is None else now_ts
            observed = activity_ts if activity_ts is not None else _job_result_activity_ts(
                job_result
            )
            if _activity_is_live(activity_ts=observed, now_ts=clock):
                return "running", failed_trials

    # Nothing is actively driving the job: either the launch finished without a
    # job-level result.json, or the backend was restarted / the run was killed
    # (the in-memory record is gone). Derive a terminal status from on-disk trial
    # completion instead of reporting a stale, never-ending "running".
    if trial_count > 0 and completed_trials >= trial_count:
        return ("failed", failed_trials) if failed_trials > 0 else ("success", 0)
    return "failed", failed_trials


def _job_listing_times(job_dir: Path) -> tuple[str | None, str | None, str | None, float]:
    """Return (startedAt, updatedAt, finishedAt, sortTimestamp) for a job directory."""
    result_path = job_dir / "result.json"
    lock_path = job_dir / "lock.json"
    started_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None
    sort_ts: float | None = None

    if result_path.is_file():
        try:
            import json

            result = json.loads(result_path.read_text(encoding="utf-8"))
            if isinstance(result, dict):
                started_at = result.get("started_at")
                updated_at = result.get("updated_at")
                finished_at = result.get("finished_at")
                sort_ts = _parse_iso_timestamp(updated_at) or _parse_iso_timestamp(started_at)
        except Exception:  # noqa: BLE001
            pass

    if started_at is None and lock_path.is_file():
        try:
            import json

            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            if isinstance(lock, dict):
                started_at = lock.get("created_at")
                sort_ts = sort_ts or _parse_iso_timestamp(started_at)
        except Exception:  # noqa: BLE001
            pass

    if sort_ts is None:
        try:
            sort_ts = job_dir.stat().st_mtime
        except OSError:
            sort_ts = 0.0

    return started_at, updated_at, finished_at, sort_ts


def _validate_job_name(job_name: str) -> None:
    if not job_name or job_name in {".", ".."}:
        raise ValueError("Invalid job name")
    if "/" in job_name or "\\" in job_name or ".." in job_name:
        raise ValueError("Invalid job name")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "harbor-job"


# Coarse trial status codes for the lightweight, incremental status feed.
# Kept as small ints so deltas stay tiny for tens-of-thousands cohorts.
STATUS_CODE_PENDING = 0
STATUS_CODE_RUNNING = 1
STATUS_CODE_DONE = 2
STATUS_CODE_ERROR = 3
_TRIAL_DEBRIEF_CACHE_MAX = 128


@dataclass
class _TrialDebriefCacheEntry:
    fingerprint: tuple[tuple[str, int, int], ...]
    payload: dict[str, Any]


@dataclass
class _JobStatusState:
    """In-memory incremental status snapshot for one job.

    Trials are append-only and identified by their sorted directory name, so a
    positional ``codes`` array is stable. Finalized trials (done/error) are never
    re-read from disk, making steady-state polling O(active trials). ``history``
    records the per-version code deltas so late-joining clients can catch up
    without a full payload.
    """

    trial_names: list[str] = field(default_factory=list)
    persona_ids: list[str | None] = field(default_factory=list)
    persona_names: list[str | None] = field(default_factory=list)
    codes: list[int] = field(default_factory=list)
    version: int = 0
    # history[v] holds the (index, code) changes that advanced version v -> v+1.
    history: list[list[tuple[int, int]]] = field(default_factory=list)


@dataclass
class HarborLaunchRecord:
    job_name: str
    status: str = "queued"
    config_path: str | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    execution_plane: str = "harbor"
    remote_run_id: str | None = None


@dataclass
class HarborJobService:
    """Spawn ``harbor run`` jobs and read ``jobs_dir`` for trial progress."""

    repo_root: Path
    jobs_dir: Path
    generated_configs_dir: Path
    command_runner: Callable[..., int] = _run_subprocess
    harbor_command: tuple[str, ...] = field(default_factory=lambda: tuple(_default_harbor_command()))
    remote_runner_client: Any | None = None
    _executor: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(max_workers=2))
    _launches: dict[str, HarborLaunchRecord] = field(default_factory=dict)
    _reporting_jobs: set[str] = field(default_factory=set)
    _guard: threading.Lock = field(default_factory=threading.Lock)
    _status_states: dict[str, "_JobStatusState"] = field(default_factory=dict)
    _status_guard: threading.Lock = field(default_factory=threading.Lock)
    _debrief_cache: dict[tuple[str, str], _TrialDebriefCacheEntry] = field(default_factory=dict)
    _debrief_cache_guard: threading.Lock = field(default_factory=threading.Lock)
    # Poll interval for per-trial host scoring while Harbor is still running.
    _host_score_poll_sec: float = 2.0
    _host_score_join_timeout_sec: float = 600.0

    @classmethod
    def from_repo(cls, *, repo_root: Path | None = None, jobs_dir: Path | None = None) -> "HarborJobService":
        root = Path(repo_root) if repo_root is not None else _repo_root()
        resolved_jobs = Path(jobs_dir) if jobs_dir is not None else root / "jobs"
        return cls(
            repo_root=root,
            jobs_dir=resolved_jobs,
            generated_configs_dir=root / DEFAULT_APPLICATION_JOBS_DIR,
        )

    def _list_job_names(self) -> list[str]:
        if not self.jobs_dir.is_dir():
            return []
        return sorted(
            [d.name for d in self.jobs_dir.iterdir() if d.is_dir()],
            reverse=True,
        )

    def _list_trial_names(self, job_name: str) -> list[str]:
        job_dir = self.jobs_dir / job_name
        if not job_dir.is_dir():
            return []
        skip = {"_inputs", "_generated"}
        return sorted(
            [
                d.name
                for d in job_dir.iterdir()
                if d.is_dir() and d.name not in skip and not d.name.startswith(".")
            ]
        )

    def _trial_has_result(self, job_name: str, trial_name: str) -> bool:
        return (self.jobs_dir / job_name / trial_name / "result.json").is_file()

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:  # noqa: BLE001
            return None

    def _job_task_path(self, job_name: str, job_dir: Path) -> str | None:
        task_path = _task_path_from_generated_config(
            self.generated_configs_dir / "{}.yaml".format(job_name),
        )
        if task_path:
            return task_path
        for trial_name in self._list_trial_names(job_name):
            task_path = _task_path_from_trial_config(job_dir / trial_name)
            if task_path:
                return task_path
        return None

    def _job_application_type(self, job_name: str, job_dir: Path) -> str:
        task_path = self._job_task_path(job_name, job_dir)
        if not task_path:
            return "unknown"
        return _map_task_metadata_type(
            _read_task_metadata_type(task_path, repo_root=self.repo_root),
        )

    def _job_task_meta(self, job_name: str, job_dir: Path) -> dict[str, Any]:
        """Resolve ``[task].name`` + ``[metadata]`` for job list labels."""
        task_path = self._job_task_path(job_name, job_dir)
        if not task_path:
            return {}
        try:
            from backend.service.task_detail_service import get_task_detail

            detail = get_task_detail(task_path, repo_root=self.repo_root)
        except (FileNotFoundError, ValueError, OSError):
            detail = None
        if isinstance(detail, dict) and detail.get("title"):
            questionnaire = detail.get("questionnaire")
            instrument_title = None
            if isinstance(questionnaire, dict):
                raw = questionnaire.get("title")
                if isinstance(raw, str) and raw.strip():
                    instrument_title = raw.strip()
            return {
                "taskTitle": instrument_title
                or (str(detail.get("title") or "").strip() or None),
                "taskName": str(detail.get("taskName") or "").strip() or None,
                "domain": str(detail.get("domain") or "").strip() or None,
                "difficulty": str(detail.get("difficulty") or "").strip() or None,
                "tags": detail.get("tags") if isinstance(detail.get("tags"), list) else [],
                "metaType": str(detail.get("metaType") or "").strip() or None,
                "description": str(detail.get("description") or "").strip() or None,
                "personaStrategy": detail.get("personaStrategy")
                if isinstance(detail.get("personaStrategy"), dict)
                else None,
            }
        try:
            from backend.service.application_task_metadata import parse_application_task

            normalized = str(task_path).replace("\\", "/").strip("/")
            record = parse_application_task(self.repo_root / normalized)
        except Exception:  # noqa: BLE001
            record = None
        if record is None:
            return {}
        return {
            "taskTitle": record.title,
            "taskName": record.task_name,
            "domain": record.domain or None,
            "difficulty": record.difficulty or None,
            "tags": list(record.tags),
            "metaType": record.meta_type or None,
            "description": None,
            "personaStrategy": None,
        }

    def _job_task_title(self, job_name: str, job_dir: Path) -> str | None:
        meta = self._job_task_meta(job_name, job_dir)
        title = meta.get("taskTitle")
        return str(title).strip() if title else None

    def _reporting_enabled(self) -> bool:
        raw = os.environ.get(REPORTING_LLM_ENABLE_ENV, "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def _reporting_model(self) -> str:
        return (
            os.environ.get(REPORTING_LLM_MODEL_ENV, "").strip()
            or DEFAULT_REPORTING_LLM_MODEL
        )

    def _job_reporting_ready(self, job_name: str, trials: list[str] | None = None) -> bool:
        trial_names = trials if trials is not None else self._list_trial_names(job_name)
        if not trial_names:
            return False
        return all(self._trial_has_result(job_name, trial_name) for trial_name in trial_names)

    def _aggregation_reporting_status(
        self,
        aggregation: dict[str, Any] | None,
    ) -> str | None:
        if not isinstance(aggregation, dict):
            return None
        reporting = aggregation.get("reporting")
        if not isinstance(reporting, dict):
            return None
        status = reporting.get("status")
        return str(status) if status else None

    def _merge_reporting_status(
        self,
        aggregation: dict[str, Any] | None,
        *,
        job_dir: Path,
    ) -> dict[str, Any] | None:
        if aggregation is None:
            return None
        live = read_reporting_status_artifact(job_dir)
        if not isinstance(live, dict):
            return aggregation
        live_status = str(live.get("status") or "").strip().lower()
        if live_status not in {"queued", "running", "failed"}:
            return aggregation
        merged = dict(aggregation)
        reporting = dict(merged.get("reporting") or {})
        reporting["status"] = live_status
        reporting["liveStatus"] = live_status
        for key in ("queuedAt", "startedAt", "finishedAt", "error", "model"):
            value = live.get(key)
            if value is not None:
                reporting[key] = value
        merged["reporting"] = reporting
        return merged

    def _build_job_aggregation_view(
        self,
        job_name: str,
        job_dir: Path,
        *,
        trials: list[str] | None = None,
    ) -> dict[str, Any] | None:
        cached = read_job_aggregation_artifact(job_dir)
        if job_aggregation_artifact_is_fresh(job_dir, cached):
            aggregation = cached
        else:
            aggregation = build_job_aggregation(
                job_dir,
                repo_root=self.repo_root,
                enable_llm=False,
            )
        self._maybe_schedule_reporting(
            job_name,
            job_dir,
            trials=trials,
            aggregation=aggregation,
        )
        return self._merge_reporting_status(aggregation, job_dir=job_dir)

    def _maybe_schedule_reporting(
        self,
        job_name: str,
        job_dir: Path,
        *,
        trials: list[str] | None = None,
        aggregation: dict[str, Any] | None = None,
    ) -> None:
        if not self._reporting_enabled():
            return
        # Prefer on-disk aggregation. Terminal reporting must not rebuild
        # (list_jobs used to call build_job_aggregation for every finished
        # large job on every Runs refresh — multi-minute / 100% CPU).
        if aggregation is None:
            aggregation = read_job_aggregation_artifact(job_dir)
        cached_status = self._aggregation_reporting_status(aggregation)
        if cached_status in {"completed", "completed_with_errors", "failed"}:
            return
        if not self._job_reporting_ready(job_name, trials):
            return
        with self._guard:
            actively_tracked = job_name in self._reporting_jobs
        live = read_reporting_status_artifact(job_dir)
        if isinstance(live, dict):
            live_status = str(live.get("status") or "").strip().lower()
            # "failed" is terminal until inputs change. "queued"/"running" only
            # block re-scheduling when THIS process is actually running the job;
            # otherwise the artifact is orphaned from a prior process (e.g. a
            # restart killed the worker) and would wedge reporting forever.
            if live_status == "failed":
                return
            if live_status in {"queued", "running"} and actively_tracked:
                return
        if aggregation is None or not job_aggregation_artifact_is_fresh(job_dir, aggregation):
            aggregation = build_job_aggregation(
                job_dir,
                repo_root=self.repo_root,
                enable_llm=False,
            )
        status = self._aggregation_reporting_status(aggregation)
        if status not in {"ready", "partial", "partial_with_errors"}:
            return
        should_submit = False
        with self._guard:
            if job_name not in self._reporting_jobs:
                self._reporting_jobs.add(job_name)
                should_submit = True
        if not should_submit:
            return
        write_reporting_status_artifact(
            job_dir,
            {
                "status": "queued",
                "queuedAt": _utc_now(),
                "model": self._reporting_model(),
            },
        )
        self._executor.submit(self._run_job_reporting, job_name)

    def _run_job_reporting(self, job_name: str) -> None:
        job_dir = self.jobs_dir / job_name
        model = self._reporting_model()
        try:
            write_reporting_status_artifact(
                job_dir,
                {
                    "status": "running",
                    "queuedAt": _utc_now(),
                    "startedAt": _utc_now(),
                    "model": model,
                },
            )
            build_job_aggregation(
                job_dir,
                repo_root=self.repo_root,
                enable_llm=True,
            )
            status_path = reporting_status_artifact_path(job_dir)
            if status_path.is_file():
                status_path.unlink()
        except Exception as exc:  # noqa: BLE001
            write_reporting_status_artifact(
                job_dir,
                {
                    "status": "failed",
                    "startedAt": _utc_now(),
                    "finishedAt": _utc_now(),
                    "model": model,
                    "error": str(exc),
                },
            )
        finally:
            with self._guard:
                self._reporting_jobs.discard(job_name)

    def list_jobs(self) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for job_name in self._list_job_names():
            job_dir = self.jobs_dir / job_name
            # The listing does NOT embed each job's full aggregation — that is a
            # multi-MB payload per job the Runs list never reads (fetched on
            # demand via GET /api/harbor/jobs/{job}/aggregation). We still drive
            # the reporting scheduler here, but never rebuild aggregation just to
            # discover a terminal reporting status.
            self._maybe_schedule_reporting(job_name, job_dir)
            started_at, updated_at, finished_at, sort_ts = _job_listing_times(job_dir)
            job_result = self._read_json(job_dir / "result.json")
            stats = (
                job_result.get("stats")
                if isinstance(job_result, dict) and isinstance(job_result.get("stats"), dict)
                else None
            )
            # Finished jobs already carry authoritative counts in result.json —
            # avoid scandir + per-trial result.json reads across 1k-trial cohorts.
            finished_total = (
                int(job_result.get("n_total_trials") or 0)
                if isinstance(job_result, dict)
                else 0
            )
            if (
                isinstance(job_result, dict)
                and job_result.get("finished_at")
                and isinstance(stats, dict)
                and finished_total > 0
            ):
                trial_count = finished_total
                completed_trials = int(stats.get("n_completed_trials") or 0)
                failed_trials_on_disk = int(stats.get("n_errored_trials") or 0)
                activity_ts = None
            else:
                trials = self._list_trial_names(job_name)
                trial_count = len(trials)
                completed_trials = sum(
                    1 for trial_name in trials if self._trial_has_result(job_name, trial_name)
                )
                failed_trials_on_disk = sum(
                    1
                    for trial_name in trials
                    if _trial_result_error(
                        self._read_json(job_dir / trial_name / "result.json")
                    )
                    is not None
                )
                activity_ts = _external_run_activity_ts(
                    job_dir,
                    job_result=job_result,
                    trial_names=trials,
                )
            with self._guard:
                launch = self._launches.get(job_name)
            status, failed_trials = _job_list_status(
                trial_count=trial_count,
                completed_trials=completed_trials,
                failed_trials_on_disk=failed_trials_on_disk,
                job_result=job_result,
                launch=launch,
                activity_ts=activity_ts,
            )
            task_meta = self._job_task_meta(job_name, job_dir)
            summaries.append(
                {
                    "jobName": job_name,
                    "applicationType": self._job_application_type(job_name, job_dir),
                    "taskTitle": task_meta.get("taskTitle"),
                    "taskName": task_meta.get("taskName"),
                    "domain": task_meta.get("domain"),
                    "difficulty": task_meta.get("difficulty"),
                    "tags": task_meta.get("tags") or [],
                    "metaType": task_meta.get("metaType"),
                    "trialCount": trial_count,
                    "completedTrials": completed_trials,
                    "startedAt": started_at,
                    "updatedAt": updated_at,
                    "finishedAt": finished_at,
                    "jobResult": job_result,
                    "status": status,
                    "failedTrials": failed_trials,
                    "launchStatus": launch.status if launch is not None else None,
                    "_sortTs": sort_ts,
                }
            )
        summaries.sort(key=lambda row: row.get("_sortTs") or 0.0, reverse=True)
        for row in summaries:
            row.pop("_sortTs", None)
        return summaries

    def delete_job(self, job_name: str) -> None:
        _validate_job_name(job_name)
        job_dir = self.jobs_dir / job_name
        if job_dir.is_dir():
            shutil.rmtree(job_dir)
        else:
            with self._guard:
                if job_name not in self._launches:
                    raise ValueError("Job not found: {}".format(job_name))
        with self._guard:
            self._launches.pop(job_name, None)
        with self._status_guard:
            self._status_states.pop(job_name, None)
        config_path = self.generated_configs_dir / "{}.yaml".format(job_name)
        if config_path.is_file():
            config_path.unlink()
        self._launch_meta_path(job_name).unlink(missing_ok=True)

    def get_job(self, job_name: str) -> dict[str, Any] | None:
        job_dir = self.jobs_dir / job_name
        if not job_dir.is_dir():
            with self._guard:
                launch = self._launches.get(job_name)
            if launch is None:
                return None
            return {
                "jobName": job_name,
                "launch": _launch_view(launch),
                "trials": [],
                "aggregation": None,
            }

        trials: list[dict[str, Any]] = []
        for trial_name in self._list_trial_names(job_name):
            trial_dir = job_dir / trial_name
            result = self._read_json(trial_dir / "result.json")
            completed = self._trial_has_result(job_name, trial_name)
            error = _trial_result_error(result)
            persona_meta = _persona_meta_from_trial(trial_dir)
            vnc_url = _read_vnc_url(trial_dir)
            sandbox_id = _read_sandbox_id(trial_dir)
            trials.append(
                {
                    "trialName": trial_name,
                    "personaId": persona_meta.get("persona_id"),
                    "personaName": persona_meta.get("display_name"),
                    "completed": completed,
                    "succeeded": completed and error is None,
                    "error": error,
                    "result": result,
                    "vncUrl": vnc_url,
                    "sandboxId": sandbox_id,
                }
            )

        with self._guard:
            launch = self._launches.get(job_name)

        # Job detail stays lightweight: the Runs UI loads the multi-MB batch
        # report separately via GET /api/harbor/jobs/{job}/aggregation (which
        # also drives the reporting scheduler). Embedding aggregation here made
        # every job-detail poll rebuild and ship the full report payload.
        task_meta = self._job_task_meta(job_name, job_dir)
        return {
            "jobName": job_name,
            "jobsDir": _rel_path(self.jobs_dir, self.repo_root),
            "applicationType": self._job_application_type(job_name, job_dir),
            "taskPath": self._job_task_path(job_name, job_dir),
            "taskTitle": task_meta.get("taskTitle"),
            "taskName": task_meta.get("taskName"),
            "domain": task_meta.get("domain"),
            "difficulty": task_meta.get("difficulty"),
            "tags": task_meta.get("tags") or [],
            "metaType": task_meta.get("metaType"),
            "description": task_meta.get("description"),
            "personaStrategy": task_meta.get("personaStrategy"),
            "config": self._read_json(job_dir / "config.json"),
            "result": self._read_json(job_dir / "result.json"),
            "trials": trials,
            "launch": _launch_view(launch) if launch else None,
            "aggregation": None,
        }

    def get_job_aggregation(self, job_name: str) -> dict[str, Any]:
        job_dir = self.jobs_dir / job_name
        if not job_dir.is_dir():
            raise ValueError("Job not found: {}".format(job_name))
        aggregation = self._build_job_aggregation_view(job_name, job_dir)
        if aggregation is None:
            raise ValueError("Aggregation not available for job: {}".format(job_name))
        return aggregation

    def launch(
        self,
        *,
        task_path: str,
        sample_size: int = 1,
        seed: int = 42,
        persona_pool: str = "persona/datasets/matraix-persona-dev-sample",
        persona_ids: list[str] | None = None,
        agent_name: str | None = None,
        persona_model: str | None = None,
        n_concurrent_trials: int = 2,
        execution_mode: str = "auto",
        job_name: str | None = None,
        chat_domain: str | None = None,
        chat_application_id: str | None = None,
        chat_application_context: str | None = None,
        chat_max_turns: int | None = None,
        persona_sources: list[str] | None = None,
        persona_filters: dict[str, str] | None = None,
        cohort_id: str | None = None,
        use_entire_pool: bool = False,
        os_app_submission_profile: str | None = None,
        os_app_backend: str | None = None,
        cua_backend: str | None = None,
        execution_plane: str | None = None,
    ) -> str:
        from backend.service.execution_plane import (
            ExecutionPlaneError,
            default_execution_plane,
            normalize_execution_plane,
            remote_runner_configured,
        )

        try:
            resolved_plane = normalize_execution_plane(
                execution_plane or default_execution_plane()
            )
        except ExecutionPlaneError as exc:
            raise ValueError(str(exc)) from exc
        if resolved_plane == "remote" and not remote_runner_configured():
            raise ValueError(
                "execution plane 'remote' requires REMOTE_RUNNER_API_URL"
            )
        if os_app_backend is None and cua_backend is not None:
            os_app_backend = cua_backend
        if persona_ids is not None and len(persona_ids) == 0:
            raise ValueError("persona_ids must not be empty when provided")
        if not persona_ids and not use_entire_pool and sample_size < 1:
            raise ValueError("sample_size must be >= 1")

        resolved_persona_ids = list(persona_ids or [])
        resolved_pool = persona_pool
        resolved_seed = seed
        resolved_sources = persona_sources
        resolved_filters = persona_filters
        resolved_use_entire_pool = bool(use_entire_pool)

        if cohort_id:
            from backend.service.persona_pool_service import PersonaPoolService

            resolved = PersonaPoolService.from_repo(repo_root=self.repo_root).resolve_cohort_launch(
                cohort_id,
                sample_size_override=sample_size if not resolved_persona_ids else None,
            )
            resolved_pool = str(resolved.get("pool") or persona_pool)
            resolved_seed = int(resolved.get("seed") or seed)
            resolved_sources = list(resolved.get("sources") or []) or None
            resolved_filters = dict(resolved.get("dimensionFilters") or {}) or None
            if resolved.get("personaIds"):
                resolved_persona_ids = list(resolved["personaIds"])

        if (
            not resolved_persona_ids
            and not resolved_use_entire_pool
            and (resolved_sources or resolved_filters)
        ):
            from backend.service.persona_pool_service import PersonaPoolService

            sampled = PersonaPoolService.from_repo(repo_root=self.repo_root).sample_pool(
                persona_pool=resolved_pool,
                sample_size=sample_size,
                seed=resolved_seed,
                sources=resolved_sources,
                dimension_filters=resolved_filters,
                task_path=task_path,
                include_persona_ids=True,
            )
            resolved_persona_ids = list(sampled["personaIds"])
            resolved_pool = str(sampled.get("pool") or resolved_pool)

        # Hand-picked ids from the 1M root are preview-only until materialized.
        # Mirror sample_production_1m: write a cohort, then launch against it.
        from backend.service.persona_1m_pool import (
            is_production_1m_root,
            materialize_production_1m_persona_ids,
        )

        if is_production_1m_root(resolved_pool) and resolved_persona_ids:
            materialized = materialize_production_1m_persona_ids(
                repo_root=self.repo_root,
                persona_ids=resolved_persona_ids,
                seed=resolved_seed,
            )
            resolved_pool = str(materialized["pool"])
            resolved_persona_ids = list(materialized["personaIds"])

        task_slug = _slug(Path(task_path).name)
        resolved_job_name = job_name or "pg-{}-{}".format(task_slug, uuid.uuid4().hex[:8])
        model = persona_model or default_persona_model()
        trial_profile = resolve_trial_profile(
            task_path,
            mode=execution_mode,
            repo_root=self.repo_root,
        )
        resolved_survey_task_path: str | None = None
        resolved_chat_task_path: str | None = None
        if trial_profile == "json_survey":
            normalized_task_path = task_path.strip().replace("\\", "/")
            resolved_survey_task_path = normalized_task_path
        elif trial_profile == "user_sim_chat":
            resolved_chat_task_path = task_path.strip().replace("\\", "/")
        agent = resolve_agent_name(
            task_path,
            repo_root=self.repo_root,
            explicit=agent_name,
            mode=execution_mode,
            trial_profile=trial_profile,
        )
        from matraix.web_task_environment import resolve_web_harbor_task_path

        harbor_task_path = resolve_web_harbor_task_path(
            task_path,
            agent_name=agent,
            repo_root=self.repo_root,
        )

        spec = {
            "name": resolved_job_name,
            "task": harbor_task_path,
            "persona_pool": resolved_pool,
            "sample_size": len(resolved_persona_ids) if resolved_persona_ids else sample_size,
            "seed": resolved_seed,
            "persona_ids": resolved_persona_ids,
            "use_entire_pool": resolved_use_entire_pool and not resolved_persona_ids,
            "execution_mode": execution_mode,
            "trial_profile": trial_profile,
            "cua_backend": os_app_backend,
            "agent": {"name": agent, "model_name": model},
            "job": {
                "job_name": resolved_job_name,
                "jobs_dir": _rel_path(self.jobs_dir, self.repo_root),
                "n_concurrent_trials": n_concurrent_trials,
            },
        }
        from matraix.application_job import resolve_harbor_task_path

        resolved_task_path = resolve_harbor_task_path(harbor_task_path, trial_profile=trial_profile)
        job_config = build_application_job_config(spec, repo_root=self.repo_root)
        from matraix.persona_agent_context import apply_persona_context_to_agent_spec

        for agent_cfg in job_config.get("agents", []):
            if isinstance(agent_cfg, dict):
                apply_persona_context_to_agent_spec(
                    agent_cfg,
                    model_name=str(agent_cfg.get("model_name") or model),
                )
        # os_app_submission_profile / cua_submission_profile are no longer injected:
        # agents mirror final_answer only; task verifiers recover named JSON.
        if os_app_backend:
            job_config["environment"] = resolve_job_environment(
                execution_mode=execution_mode,
                trial_profile=trial_profile,
                cua_backend=os_app_backend,
            )
            env_type = ""
            env_block = job_config.get("environment")
            if isinstance(env_block, dict):
                env_type = str(env_block.get("type") or "")
            for agent in job_config.get("agents", []):
                if isinstance(agent, dict):
                    kwargs = agent.setdefault("kwargs", {})
                    if isinstance(kwargs, dict):
                        kwargs["cua_backend"] = os_app_backend
                        # use.computer CUA agents take max_steps (default 50);
                        # Docker Computer1 takes max_turns. Give both more
                        # headroom for stocks/news-style browse+decide tasks.
                        if env_type == "use-computer":
                            kwargs.setdefault("max_steps", 100)
                        else:
                            kwargs.setdefault("max_turns", 100)
        # use-computer OS-app tasks hand in JSON; sandbox path remap makes
        # *remote* in-VM verify flaky. Disable Harbor's per-trial verifier and
        # score on the Playground host as each trial finishes (watcher), with a
        # job-end rescue sweep (see playground.host_verifier).
        env_block = job_config.get("environment")
        if isinstance(env_block, dict) and env_block.get("type") == "use-computer":
            existing_verifier = job_config.get("verifier")
            verifier_cfg = dict(existing_verifier) if isinstance(existing_verifier, dict) else {}
            verifier_cfg["disable"] = True
            job_config["verifier"] = verifier_cfg
            for agent in job_config.get("agents", []):
                if isinstance(agent, dict):
                    kwargs = agent.setdefault("kwargs", {})
                    if isinstance(kwargs, dict):
                        kwargs.setdefault("max_steps", 100)
        job_meta = job_config.pop("_job_meta", None)

        self.generated_configs_dir.mkdir(parents=True, exist_ok=True)
        config_path = self.generated_configs_dir / "{}.yaml".format(resolved_job_name)
        header = (
            "# Generated by Playground POST /api/harbor/jobs\n"
            "# Task: {}\n"
            "# Harbor task: {}\n"
            "# Mode: {}\n"
            "# Trial profile: {}\n"
            "# Seed: {}\n"
            "# Persona pool: {}\n"
            "# Cohort: {}\n"
            "# Persona sources: {}\n"
            "# Persona filters: {}\n"
            "# Personas: {}\n"
            "# Jobs output: {}/\n\n".format(
                task_path,
                resolved_task_path,
                job_meta.get("execution_mode", "auto") if job_meta else "auto",
                job_meta.get("trial_profile", "docker_agent") if job_meta else "docker_agent",
                seed,
                resolved_pool,
                cohort_id or "(none)",
                ", ".join(resolved_sources or []) or "(all)",
                ", ".join(
                    "{}={}".format(key, value)
                    for key, value in sorted((resolved_filters or {}).items())
                )
                or "(none)",
                ", ".join(job_meta.get("selected_persona_ids", []) if job_meta else []),
                _rel_path(self.jobs_dir, self.repo_root),
            )
        )
        config_path.write_text(
            header + yaml.safe_dump(job_config, sort_keys=False),
            encoding="utf-8",
        )

        record = HarborLaunchRecord(
            job_name=resolved_job_name,
            status="queued",
            config_path=_rel_path(config_path, self.repo_root),
            started_at=_utc_now(),
            execution_plane=resolved_plane,
        )
        with self._guard:
            self._launches[resolved_job_name] = record

        use_local_distributed = _should_use_local_distributed_harbor(
            execution_mode=execution_mode,
            execution_plane=resolved_plane,
            trial_profile=trial_profile,
        )

        # Persist the exact dispatch inputs so "retry failed" can replay the
        # identical run in-place (Harbor resumes and only re-runs deleted trials).
        self._persist_launch_meta(
            resolved_job_name,
            {
                "configPath": _rel_path(config_path, self.repo_root),
                "executionPlane": resolved_plane,
                "executionMode": execution_mode,
                "useLocalDistributed": use_local_distributed,
                "trialProfile": trial_profile,
                "surveyTaskPath": resolved_survey_task_path,
                "chatTaskPath": resolved_chat_task_path,
                "osAppSubmissionProfile": os_app_submission_profile,
                "chatDomain": chat_domain,
                "chatApplicationId": chat_application_id,
                "chatApplicationContext": chat_application_context,
                "chatMaxTurns": chat_max_turns,
                "jobConfig": job_config,
            },
        )

        if use_local_distributed:
            self._executor.submit(
                self._run_local_distributed,
                resolved_job_name,
                job_config,
                resolved_survey_task_path,
                resolved_chat_task_path,
                chat_domain,
                chat_application_id,
                chat_application_context,
                chat_max_turns,
                trial_profile,
            )
        else:
            dispatch_kwargs = (
                resolved_job_name,
                config_path,
                resolved_survey_task_path,
                resolved_chat_task_path,
                os_app_submission_profile,
                chat_domain,
                chat_application_id,
                chat_application_context,
                chat_max_turns,
                trial_profile,
            )
            if resolved_plane == "remote":
                self._executor.submit(self._dispatch_remote, *dispatch_kwargs)
            else:
                self._executor.submit(self._run_harbor, *dispatch_kwargs)
        return resolved_job_name

    def _build_harbor_launch_env(
        self,
        *,
        survey_task_path: str | None,
        chat_task_path: str | None,
        trial_profile: str | None,
        chat_domain: str | None,
        chat_application_id: str | None,
        chat_application_context: str | None,
        chat_max_turns: int | None,
        for_remote: bool = False,
    ) -> dict[str, str]:
        # PYTHONPATH entries are shared with the `matraix run` CLI so GUI and
        # CLI launches cannot drift apart (issue #78).
        env = build_launch_env(self.repo_root, base_env={} if for_remote else None)
        if survey_task_path:
            env["MATRIX_SURVEY_TASK_PATH"] = survey_task_path
        if trial_profile == "user_sim_chat":
            if chat_task_path:
                env["MATRIX_CHATBOT_TASK_PATH"] = chat_task_path
            if chat_domain:
                env["MATRIX_CHATBOT_DOMAIN"] = chat_domain
            if chat_application_id:
                env["MATRIX_CHATBOT_APPLICATION_ID"] = chat_application_id
            if chat_application_context:
                env["MATRIX_CHATBOT_APPLICATION_CONTEXT"] = chat_application_context
            if chat_max_turns is not None:
                env["MATRIX_CHATBOT_MAX_TURNS"] = str(chat_max_turns)
        return env

    def _remote_client(self):
        if self.remote_runner_client is not None:
            return self.remote_runner_client
        from playground.remote_runner.client import (
            RemoteRunnerClient,
        )

        return RemoteRunnerClient()

    def _run_local_distributed(
        self,
        job_name: str,
        job_config_payload: dict[str, Any],
        survey_task_path: str | None = None,
        chat_task_path: str | None = None,
        chat_domain: str | None = None,
        chat_application_id: str | None = None,
        chat_application_context: str | None = None,
        chat_max_turns: int | None = None,
        trial_profile: str | None = None,
    ) -> None:
        with self._guard:
            record = self._launches[job_name]
            record.status = "running"

        env = self._build_harbor_launch_env(
            survey_task_path=survey_task_path,
            chat_task_path=chat_task_path,
            trial_profile=trial_profile,
            chat_domain=chat_domain,
            chat_application_id=chat_application_id,
            chat_application_context=chat_application_context,
            chat_max_turns=chat_max_turns,
        )
        try:
            from backend.service.local_distributed_harbor import (
                LocalDistributedHarborCoordinator,
            )

            coordinator = LocalDistributedHarborCoordinator(
                repo_root=self.repo_root,
                job_name=job_name,
                job_config=job_config_payload,
                launch_env=env,
                command_runner=self.command_runner,
                harbor_command=self.harbor_command,
            )
            self._run_with_trial_host_scoring(job_name, coordinator.run)
            status = "completed"
            error = None
            exit_code = 0
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            error = str(exc)
            exit_code = 1

        with self._guard:
            record = self._launches[job_name]
            record.status = status
            record.exit_code = exit_code
            record.error = error
            record.finished_at = _utc_now()
        # Rescue anything the per-trial watcher missed (idempotent).
        self._maybe_run_host_verifier(job_name)
        self._maybe_generate_post_run_feedback(job_name)
        self._maybe_schedule_reporting(job_name, self.jobs_dir / job_name)

    def _run_harbor(
        self,
        job_name: str,
        config_path: Path,
        survey_task_path: str | None = None,
        chat_task_path: str | None = None,
        os_app_submission_profile: str | None = None,
        chat_domain: str | None = None,
        chat_application_id: str | None = None,
        chat_application_context: str | None = None,
        chat_max_turns: int | None = None,
        trial_profile: str | None = None,
    ) -> None:
        with self._guard:
            record = self._launches[job_name]
            record.status = "running"

        command = list(self.harbor_command) + [
            "--yes",
            "-c",
            _rel_path(config_path, self.repo_root),
        ]
        env = self._build_harbor_launch_env(
            survey_task_path=survey_task_path,
            chat_task_path=chat_task_path,
            trial_profile=trial_profile,
            chat_domain=chat_domain,
            chat_application_id=chat_application_id,
            chat_application_context=chat_application_context,
            chat_max_turns=chat_max_turns,
        )
        try:
            held: dict[str, Any] = {}

            def _invoke() -> None:
                code = self.command_runner(
                    command,
                    cwd=self.repo_root,
                    env=env,
                )
                held["exit_code"] = code

            self._run_with_trial_host_scoring(job_name, _invoke)
            exit_code = int(held.get("exit_code", 1))
            error = None if exit_code == 0 else "harbor run exited with code {}".format(exit_code)
            status = "completed" if exit_code == 0 else "failed"
        except Exception as exc:  # noqa: BLE001
            exit_code = 1
            error = str(exc)
            status = "failed"

        with self._guard:
            record = self._launches[job_name]
            record.status = status
            record.exit_code = exit_code
            record.error = error
            record.finished_at = _utc_now()
        # Rescue anything the per-trial watcher missed (idempotent).
        self._maybe_run_host_verifier(job_name)
        self._maybe_generate_post_run_feedback(job_name)
        self._maybe_schedule_reporting(job_name, self.jobs_dir / job_name)

    def _dispatch_remote(
        self,
        job_name: str,
        config_path: Path,
        survey_task_path: str | None = None,
        chat_task_path: str | None = None,
        os_app_submission_profile: str | None = None,
        chat_domain: str | None = None,
        chat_application_id: str | None = None,
        chat_application_context: str | None = None,
        chat_max_turns: int | None = None,
        trial_profile: str | None = None,
    ) -> None:
        del os_app_submission_profile
        with self._guard:
            record = self._launches[job_name]
            record.status = "running"

        env = self._build_harbor_launch_env(
            survey_task_path=survey_task_path,
            chat_task_path=chat_task_path,
            trial_profile=trial_profile,
            chat_domain=chat_domain,
            chat_application_id=chat_application_id,
            chat_application_context=chat_application_context,
            chat_max_turns=chat_max_turns,
            for_remote=True,
        )
        payload = {
            "jobName": job_name,
            "configYaml": config_path.read_text(encoding="utf-8"),
            "repoRoot": str(self.repo_root.resolve()),
            "jobsDir": _rel_path(self.jobs_dir, self.repo_root),
            "env": filter_remote_harbor_payload_env(env),
        }
        try:
            client = self._remote_client()
            run = client.create_run(task_type="harbor_job", payload=payload)
            with self._guard:
                record = self._launches[job_name]
                record.remote_run_id = run.id
            client.wait_for_run(run.id)
            status = "completed"
            error = None
            exit_code = 0
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            error = str(exc)
            exit_code = 1

        with self._guard:
            record = self._launches[job_name]
            record.status = status
            record.exit_code = exit_code
            record.error = error
            record.finished_at = _utc_now()
        # Remote trials land locally after wait; job-end scoring is the primary path.
        self._maybe_run_host_verifier(job_name)
        self._maybe_generate_post_run_feedback(job_name)
        self._maybe_schedule_reporting(job_name, self.jobs_dir / job_name)

    def _iter_scorable_trial_dirs(self, job_name: str) -> list[Path]:
        job_dir = self.jobs_dir / job_name
        if not job_dir.is_dir():
            return []
        trials: list[Path] = []
        for trial_dir in sorted(job_dir.iterdir()):
            if not trial_dir.is_dir() or trial_dir.name.startswith("_"):
                continue
            if not (trial_dir / "config.json").is_file():
                continue
            trials.append(trial_dir)
        return trials

    def _score_finished_trial_on_host(self, trial_dir: Path) -> None:
        """Run host verify + optional post-run feedback for one finished trial.

        Idempotent: host_verifier skips already-passed rewards; feedback skips
        when the artifact already exists.
        """
        try:
            from playground.host_verifier import maybe_run_host_verifier

            maybe_run_host_verifier(repo_root=self.repo_root, trial_dir=trial_dir)
        except Exception:
            logger.exception("host_verifier failed for trial %s", trial_dir)
        try:
            from playground.post_run_feedback import maybe_write_trial_user_feedback

            maybe_write_trial_user_feedback(repo_root=self.repo_root, trial_dir=trial_dir)
        except Exception:
            logger.exception("post_run_feedback failed for trial %s", trial_dir)

    def _score_new_finished_trials_on_host(
        self, job_name: str, *, already_scored: set[str]
    ) -> None:
        """Score trials that have ``result.json`` and have not been attempted yet."""
        for trial_dir in self._iter_scorable_trial_dirs(job_name):
            if trial_dir.name in already_scored:
                continue
            if not (trial_dir / "result.json").is_file():
                continue
            self._score_finished_trial_on_host(trial_dir)
            already_scored.add(trial_dir.name)

    def _watch_and_score_trials_on_host(
        self, job_name: str, stop_event: threading.Event
    ) -> None:
        """Poll for finished trials and score them while Harbor is still running."""
        already_scored: set[str] = set()
        poll_sec = max(0.05, float(self._host_score_poll_sec))
        while not stop_event.wait(poll_sec):
            self._score_new_finished_trials_on_host(
                job_name, already_scored=already_scored
            )
        # Final sweep after Harbor exits (catch the last finishing trials).
        self._score_new_finished_trials_on_host(job_name, already_scored=already_scored)

    def _run_with_trial_host_scoring(
        self, job_name: str, run_fn: Callable[[], None]
    ) -> None:
        """Run Harbor (or local distributed) with a per-trial host-scoring watcher."""
        stop_event = threading.Event()
        watcher = threading.Thread(
            target=self._watch_and_score_trials_on_host,
            args=(job_name, stop_event),
            name="host-score-{}".format(job_name),
            daemon=True,
        )
        watcher.start()
        try:
            run_fn()
        finally:
            stop_event.set()
            watcher.join(timeout=float(self._host_score_join_timeout_sec))

    def _maybe_run_host_verifier(self, job_name: str) -> None:
        """Job-end rescue: host-score any trial still missing a reward."""
        from playground.host_verifier import maybe_run_host_verifier

        for trial_dir in self._iter_scorable_trial_dirs(job_name):
            try:
                maybe_run_host_verifier(repo_root=self.repo_root, trial_dir=trial_dir)
            except Exception:
                logger.exception("host_verifier rescue failed for trial %s", trial_dir)
                continue

    def _maybe_generate_post_run_feedback(self, job_name: str) -> None:
        """Job-end rescue: write user_feedback for trials still missing it."""
        from playground.post_run_feedback import (
            maybe_write_trial_user_feedback,
        )

        for trial_dir in self._iter_scorable_trial_dirs(job_name):
            try:
                maybe_write_trial_user_feedback(repo_root=self.repo_root, trial_dir=trial_dir)
            except Exception:
                logger.exception("post_run_feedback rescue failed for trial %s", trial_dir)
                continue

    def get_trial_events(
        self,
        job_name: str,
        trial_name: str,
        *,
        after: int = 0,
    ) -> dict[str, Any]:
        trial_dir = self.jobs_dir / job_name / trial_name
        if not trial_dir.is_dir():
            raise ValueError("Trial not found: {}/{}".format(job_name, trial_name))
        from playground.harbor.trial_events import (
            EVENTS_FILENAME,
            read_events_after,
        )

        events, offset = read_events_after(trial_dir / EVENTS_FILENAME, after)
        return {"events": events, "offset": offset}

    def get_trial_web_trace(self, job_name: str, trial_name: str) -> dict[str, Any]:
        from backend.service.harbor_trial_debrief import find_trial_logs_dir
        from backend.service.harbor_web_trace import read_harbor_web_trace

        trial_dir = self.jobs_dir / job_name / trial_name
        if not trial_dir.is_dir():
            raise ValueError("Trial not found: {}/{}".format(job_name, trial_name))
        trace = read_harbor_web_trace(
            find_trial_logs_dir(trial_dir),
            job_name=job_name,
            trial_name=trial_name,
        )
        return {"trace": trace}

    def trial_screenshot_path(self, job_name: str, trial_name: str, filename: str) -> Path:
        from backend.service.harbor_trial_debrief import find_trial_logs_dir
        from backend.service.harbor_web_trace import resolve_trial_screenshot_path

        trial_dir = self.jobs_dir / job_name / trial_name
        if not trial_dir.is_dir():
            raise ValueError("Trial not found: {}/{}".format(job_name, trial_name))
        logs_dir = find_trial_logs_dir(trial_dir)
        if logs_dir is None:
            raise FileNotFoundError("trial logs not found")
        return resolve_trial_screenshot_path(logs_dir, filename)

    def trial_recording_path(self, job_name: str, trial_name: str) -> Path:
        from backend.service.harbor_trial_debrief import find_trial_logs_dir

        trial_dir = self.jobs_dir / job_name / trial_name
        if not trial_dir.is_dir():
            raise ValueError("Trial not found: {}/{}".format(job_name, trial_name))
        logs_dir = find_trial_logs_dir(trial_dir)
        if logs_dir is None:
            raise FileNotFoundError("trial logs not found")
        path = logs_dir / "recording.mp4"
        if not path.is_file():
            raise FileNotFoundError("recording not found")
        return path

    def get_job_live(self, job_name: str) -> dict[str, Any]:
        job = self.get_job(job_name)
        if job is None:
            raise ValueError("Job not found: {}".format(job_name))
        live_trials: list[dict[str, Any]] = []
        for trial in job.get("trials", []):
            if not isinstance(trial, dict):
                continue
            trial_name = str(trial.get("trialName") or "")
            if not trial_name:
                continue
            trial_dir = self.jobs_dir / job_name / trial_name
            persona_meta = _persona_meta_from_trial(trial_dir)
            instruction_path = trial_dir / "instruction.md"
            phase = _trial_live_phase(trial_dir) if trial_dir.is_dir() else None
            completed = bool(trial.get("completed"))
            vnc_url = _read_vnc_url(trial_dir) if trial_dir.is_dir() else None
            sandbox_id = _read_sandbox_id(trial_dir) if trial_dir.is_dir() else None
            live_trials.append(
                {
                    "trialName": trial_name,
                    "personaId": persona_meta.get("persona_id"),
                    "personaName": persona_meta.get("display_name"),
                    "completed": completed,
                    "succeeded": trial.get("succeeded"),
                    "error": trial.get("error"),
                    "phase": phase,
                    "stage": _resolve_trial_stage(trial_dir, phase=phase, completed=completed),
                    "hasInstruction": instruction_path.is_file(),
                    "vncUrl": vnc_url,
                    "sandboxId": sandbox_id,
                }
            )
        launch = job.get("launch") if isinstance(job.get("launch"), dict) else None
        launch_status = launch.get("status") if launch else None
        completed_count = sum(1 for trial in live_trials if trial.get("completed"))
        return {
            "jobName": job_name,
            "launchStatus": launch_status,
            "trialCount": len(live_trials),
            "completedTrials": completed_count,
            "trials": live_trials,
        }

    def _coarse_trial_code(self, job_dir: Path, trial_name: str) -> int:
        """Cheap per-trial status from on-disk markers (no event parsing).

        Only called for trials not yet finalized, so the single ``result.json``
        parse happens at most once per trial across the job's lifetime.
        """
        trial_dir = job_dir / trial_name
        result_path = trial_dir / "result.json"
        if result_path.is_file():
            error = _trial_result_error(self._read_json(result_path))
            return STATUS_CODE_ERROR if error else STATUS_CODE_DONE
        if (
            (trial_dir / "config.json").is_file()
            or (trial_dir / "trial.log").is_file()
            or (trial_dir / "agent").is_dir()
        ):
            return STATUS_CODE_RUNNING
        return STATUS_CODE_PENDING

    def _refresh_status_state(self, job_name: str) -> _JobStatusState:
        """Recompute coarse statuses, appending new trials and recording deltas."""
        job_dir = self.jobs_dir / job_name
        names = self._list_trial_names(job_name)
        state = self._status_states.get(job_name)
        if state is None:
            state = _JobStatusState()
            self._status_states[job_name] = state

        # Directory names are sorted; on any order/shrink drift, rebuild from scratch.
        prefix = names[: len(state.trial_names)]
        if prefix != state.trial_names:
            state = _JobStatusState()
            self._status_states[job_name] = state

        changes: list[tuple[int, int]] = []

        # Append newly created trial dirs (persona meta parsed once, then cached).
        for index in range(len(state.trial_names), len(names)):
            name = names[index]
            meta = _persona_meta_from_trial(job_dir / name)
            code = self._coarse_trial_code(job_dir, name)
            state.trial_names.append(name)
            state.persona_ids.append(meta.get("persona_id"))
            state.persona_names.append(meta.get("display_name"))
            state.codes.append(code)
            changes.append((index, code))

        # Re-check only trials that have not finalized yet.
        for index, name in enumerate(state.trial_names):
            if state.codes[index] >= STATUS_CODE_DONE:
                continue
            new_code = self._coarse_trial_code(job_dir, name)
            if new_code != state.codes[index]:
                state.codes[index] = new_code
                changes.append((index, new_code))

        if changes:
            state.history.append(changes)
            state.version += 1
        return state

    def get_job_status(self, job_name: str, *, since: int = 0) -> dict[str, Any]:
        """Lightweight, incremental cohort status: aggregate counts + coarse codes.

        Designed for very large cohorts (thousands to tens of thousands). Returns
        a full snapshot when ``since`` is 0 or stale, otherwise only the code
        deltas since that version. Finalized trials are frozen, so steady-state
        cost is O(active trials).
        """
        job_dir = self.jobs_dir / job_name
        with self._guard:
            launch = self._launches.get(job_name)
        if not job_dir.is_dir() and launch is None:
            raise ValueError("Job not found: {}".format(job_name))
        launch_status = launch.status if launch else None

        with self._status_guard:
            state = self._refresh_status_state(job_name)
            counts = {"pending": 0, "running": 0, "done": 0, "error": 0}
            for code in state.codes:
                if code == STATUS_CODE_ERROR:
                    counts["error"] += 1
                elif code == STATUS_CODE_DONE:
                    counts["done"] += 1
                elif code == STATUS_CODE_RUNNING:
                    counts["running"] += 1
                else:
                    counts["pending"] += 1

            payload: dict[str, Any] = {
                "jobName": job_name,
                "launchStatus": launch_status,
                "version": state.version,
                "trialCount": len(state.trial_names),
                "counts": counts,
            }

            if 1 <= since <= state.version:
                merged: list[tuple[int, int]] = []
                for batch in state.history[since : state.version]:
                    merged.extend(batch)
                payload["full"] = False
                payload["changes"] = [[index, code] for index, code in merged]
            else:
                payload["full"] = True
                payload["statuses"] = list(state.codes)
                payload["trialNames"] = list(state.trial_names)
                payload["personaIds"] = list(state.persona_ids)
                payload["personaNames"] = list(state.persona_names)
            return payload

    def _launch_meta_path(self, job_name: str) -> Path:
        return self.generated_configs_dir / "{}.launch.json".format(job_name)

    def _persist_launch_meta(self, job_name: str, meta: dict[str, Any]) -> None:
        try:
            self.generated_configs_dir.mkdir(parents=True, exist_ok=True)
            self._launch_meta_path(job_name).write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001
            # Retry is a convenience; never let metadata persistence break a launch.
            pass

    def failed_trial_count(self, job_name: str) -> int:
        job_dir = self.jobs_dir / job_name
        if not job_dir.is_dir():
            return 0
        count = 0
        for trial_name in self._list_trial_names(job_name):
            result = self._read_json(job_dir / trial_name / "result.json")
            if _trial_result_error(result) is not None:
                count += 1
        return count

    def retry_failed(self, job_name: str) -> dict[str, Any]:
        """Re-run only the failed trials in-place.

        Failed trials also write ``result.json``, so Harbor's resume would skip
        them. We delete the failed trial dirs, reset job-level completion and
        reporting, then re-dispatch the *identical* generated config — Harbor
        preserves the succeeded trials and re-runs just the deleted ones.
        """
        _validate_job_name(job_name)
        job_dir = self.jobs_dir / job_name
        if not job_dir.is_dir():
            raise ValueError("Job not found: {}".format(job_name))

        with self._guard:
            record = self._launches.get(job_name)
        if record is not None and record.status in {"queued", "running"}:
            raise ValueError("Job is still running")

        failed_dirs = [
            job_dir / trial_name
            for trial_name in self._list_trial_names(job_name)
            if _trial_result_error(self._read_json(job_dir / trial_name / "result.json"))
            is not None
        ]
        if not failed_dirs:
            return {"jobName": job_name, "retried": 0}

        meta = self._read_json(self._launch_meta_path(job_name))
        if not meta:
            raise ValueError(
                "Cannot retry: launch metadata is unavailable for {}".format(job_name)
            )
        config_rel = str(meta.get("configPath") or "")
        config_path = self.repo_root / config_rel if config_rel else None
        if config_path is None or not config_path.is_file():
            raise ValueError(
                "Cannot retry: generated config is unavailable for {}".format(job_name)
            )

        for trial_dir in failed_dirs:
            shutil.rmtree(trial_dir, ignore_errors=True)
        # Reset job-level completion + reporting so status and reporting recompute.
        (job_dir / "result.json").unlink(missing_ok=True)
        reporting_status_artifact_path(job_dir).unlink(missing_ok=True)
        with self._status_guard:
            self._status_states.pop(job_name, None)

        plane = str(meta.get("executionPlane") or "harbor")
        with self._guard:
            self._launches[job_name] = HarborLaunchRecord(
                job_name=job_name,
                status="queued",
                config_path=config_rel or None,
                started_at=_utc_now(),
                execution_plane=plane,
            )

        if meta.get("useLocalDistributed"):
            self._executor.submit(
                self._run_local_distributed,
                job_name,
                meta.get("jobConfig") or {},
                meta.get("surveyTaskPath"),
                meta.get("chatTaskPath"),
                meta.get("chatDomain"),
                meta.get("chatApplicationId"),
                meta.get("chatApplicationContext"),
                meta.get("chatMaxTurns"),
                meta.get("trialProfile"),
            )
        else:
            dispatch_kwargs = (
                job_name,
                config_path,
                meta.get("surveyTaskPath"),
                meta.get("chatTaskPath"),
                meta.get("osAppSubmissionProfile"),
                meta.get("chatDomain"),
                meta.get("chatApplicationId"),
                meta.get("chatApplicationContext"),
                meta.get("chatMaxTurns"),
                meta.get("trialProfile"),
            )
            if plane == "remote":
                self._executor.submit(self._dispatch_remote, *dispatch_kwargs)
            else:
                self._executor.submit(self._run_harbor, *dispatch_kwargs)

        return {"jobName": job_name, "retried": len(failed_dirs)}

    def _trial_debrief_fingerprint(
        self,
        job_name: str,
        trial_name: str,
    ) -> tuple[tuple[str, int, int], ...] | None:
        """Stable cache key for completed trial debrief inputs."""
        trial_dir = self.jobs_dir / job_name / trial_name
        if not (trial_dir / "result.json").is_file():
            return None

        entries: list[tuple[str, int, int]] = []

        def add_file(path: Path) -> None:
            try:
                stat = path.stat()
            except OSError:
                return
            if not path.is_file():
                return
            try:
                label = str(path.relative_to(self.repo_root))
            except ValueError:
                label = str(path)
            entries.append((label.replace("\\", "/"), stat.st_mtime_ns, stat.st_size))

        for rel in (
            "config.json",
            "result.json",
            "events.jsonl",
            "exception.txt",
            "reward.txt",
            "persona_meta.json",
            "instruction.md",
            "task_instruction.md",
            "context.md",
            "questionnaire.md",
            "output_schema.md",
            "verifier/reward.txt",
            "verifier/test-stdout.txt",
            "verifier/structured_output.json",
            "verifier/user_feedback.json",
            "logs/verifier/reward.txt",
            "logs/verifier/test-stdout.txt",
            "logs/verifier/structured_output.json",
            "logs/verifier/user_feedback.json",
            "agent/trajectory.json",
        ):
            add_file(trial_dir / rel)

        output_dir = trial_dir / "artifacts" / "app" / "output"
        if output_dir.is_dir():
            for path in sorted(output_dir.iterdir()):
                if path.is_file():
                    add_file(path)

        task_path = _task_path_from_trial_config(trial_dir)
        if task_path:
            task_dir = self.repo_root / task_path
            for rel in (
                "task.toml",
                "instruction.md",
                "input/context.md",
                "input/questionnaire.yaml",
                "input/self_report_schema.yaml",
                "input/chatbot.yaml",
                "reporting.json",
            ):
                add_file(task_dir / rel)

        return tuple(sorted(entries))

    def _cached_trial_debrief(
        self,
        key: tuple[str, str],
        fingerprint: tuple[tuple[str, int, int], ...] | None,
    ) -> dict[str, Any] | None:
        if fingerprint is None:
            return None
        with self._debrief_cache_guard:
            entry = self._debrief_cache.get(key)
            if entry is None or entry.fingerprint != fingerprint:
                return None
            self._debrief_cache.pop(key, None)
            self._debrief_cache[key] = entry
            return entry.payload

    def _store_trial_debrief(
        self,
        key: tuple[str, str],
        fingerprint: tuple[tuple[str, int, int], ...] | None,
        payload: dict[str, Any],
    ) -> None:
        if fingerprint is None:
            return
        with self._debrief_cache_guard:
            self._debrief_cache[key] = _TrialDebriefCacheEntry(
                fingerprint=fingerprint,
                payload=payload,
            )
            while len(self._debrief_cache) > _TRIAL_DEBRIEF_CACHE_MAX:
                oldest = next(iter(self._debrief_cache))
                self._debrief_cache.pop(oldest, None)

    def get_trial_debrief(self, job_name: str, trial_name: str) -> dict[str, Any]:
        from backend.service.harbor_trial_debrief import map_trial_debrief

        key = (job_name, trial_name)
        fingerprint = self._trial_debrief_fingerprint(job_name, trial_name)
        cached = self._cached_trial_debrief(key, fingerprint)
        if cached is not None:
            return cached

        try:
            payload = map_trial_debrief(
                repo_root=self.repo_root,
                jobs_dir=self.jobs_dir,
                job_name=job_name,
                trial_name=trial_name,
            )
            # Mapping can materialize missing artifacts, so cache the final
            # on-disk state that produced this payload.
            self._store_trial_debrief(
                key,
                self._trial_debrief_fingerprint(job_name, trial_name),
                payload,
            )
            return payload
        except FileNotFoundError as exc:
            raise ValueError(str(exc)) from exc

    def get_trial_instruction(self, job_name: str, trial_name: str) -> dict[str, Any]:
        trial_dir = self.jobs_dir / job_name / trial_name
        if not trial_dir.is_dir():
            raise ValueError("Trial not found: {}/{}".format(job_name, trial_name))
        task_instruction_markdown = ""
        context_markdown = ""
        questionnaire_markdown = ""
        output_schema_markdown = ""
        self_report_markdown = ""
        instruction_path = trial_dir / "instruction.md"
        task_instruction_path = trial_dir / "task_instruction.md"
        context_path = trial_dir / "context.md"
        questionnaire_path = trial_dir / "questionnaire.md"
        output_schema_path = trial_dir / "output_schema.md"
        task_path = ""
        config_path = trial_dir / "config.json"
        if config_path.is_file():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                task_block = config.get("task") if isinstance(config.get("task"), dict) else {}
                task_path = str(task_block.get("path") or "")
            except Exception:  # noqa: BLE001
                task_path = ""
        detail = None
        # Prefer live task docs so Playground debrief tracks authoring edits.
        if task_path:
            from backend.service.task_detail_service import get_task_detail

            try:
                detail = get_task_detail(task_path, repo_root=self.repo_root)
            except (FileNotFoundError, ValueError, OSError):
                detail = None
            if isinstance(detail, dict):
                task_instruction_markdown = str(detail.get("instructionMarkdown") or "").strip()
                context_markdown = str(detail.get("contextMarkdown") or "").strip()
                questionnaire_markdown = str(detail.get("questionnaireMarkdown") or "").strip()
                output_schema_markdown = str(detail.get("outputSchemaMarkdown") or "").strip()
                self_report_markdown = str(detail.get("selfReportMarkdown") or "").strip()
        if not task_instruction_markdown and task_instruction_path.is_file():
            task_instruction_markdown = task_instruction_path.read_text(encoding="utf-8").strip()
        if not context_markdown and context_path.is_file():
            context_markdown = context_path.read_text(encoding="utf-8").strip()
        if not questionnaire_markdown and questionnaire_path.is_file():
            questionnaire_markdown = questionnaire_path.read_text(encoding="utf-8").strip()
        if not output_schema_markdown and output_schema_path.is_file():
            output_schema_markdown = output_schema_path.read_text(encoding="utf-8").strip()
        if task_instruction_markdown or context_markdown or questionnaire_markdown:
            title = str((detail or {}).get("title") or "") if isinstance(detail, dict) else ""
            if not title and task_instruction_markdown:
                for line in task_instruction_markdown.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("# "):
                        title = stripped.lstrip("# ").strip()
                        break
            return {
                "title": title or None,
                "markdown": task_instruction_markdown
                or (
                    instruction_path.read_text(encoding="utf-8").strip()
                    if instruction_path.is_file()
                    else ""
                ),
                "instructionMarkdown": task_instruction_markdown or None,
                "contextMarkdown": context_markdown or None,
                "questionnaireMarkdown": questionnaire_markdown or None,
                "outputSchemaMarkdown": output_schema_markdown or None,
                "selfReportMarkdown": self_report_markdown or None,
            }
        if instruction_path.is_file():
            markdown = instruction_path.read_text(encoding="utf-8").strip()
            title = ""
            for line in markdown.splitlines():
                stripped = line.strip()
                if stripped.startswith("# "):
                    title = stripped.lstrip("# ").strip()
                    break
            return {
                "title": title or None,
                "markdown": markdown,
                "instructionMarkdown": task_instruction_markdown or None,
                "contextMarkdown": context_markdown or None,
                "questionnaireMarkdown": questionnaire_markdown or None,
                "outputSchemaMarkdown": output_schema_markdown or None,
                "selfReportMarkdown": self_report_markdown or None,
            }
        if task_path:
            from backend.service.task_detail_service import get_task_detail

            detail = detail or get_task_detail(task_path, repo_root=self.repo_root)
            markdown = str(detail.get("instructionMarkdown") or detail.get("profileMarkdown") or "").strip()
            if markdown:
                return {
                    "title": detail.get("title"),
                    "markdown": markdown,
                    "instructionMarkdown": detail.get("instructionMarkdown") or None,
                    "contextMarkdown": detail.get("contextMarkdown") or None,
                    "questionnaireMarkdown": detail.get("questionnaireMarkdown") or None,
                    "outputSchemaMarkdown": detail.get("outputSchemaMarkdown") or None,
                    "selfReportMarkdown": detail.get("selfReportMarkdown") or None,
                }
        raise FileNotFoundError("instruction not found for trial {}/{}".format(job_name, trial_name))

    def trial_live_screenshot(self, job_name: str, trial_name: str) -> bytes:
        """Proxy the live screenshot from use.computer for an active trial."""
        import httpx

        trial_dir = self.jobs_dir / job_name / trial_name
        sandbox_id = _read_sandbox_id(trial_dir)
        if not sandbox_id:
            raise FileNotFoundError("no active sandbox for this trial")
        api_key = (os.environ.get("USE_COMPUTER_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("USE_COMPUTER_API_KEY not configured")
        base_url = os.environ.get("USE_COMPUTER_BASE_URL", "https://api.use.computer").rstrip("/")
        url = "{}/v1/sandboxes/{}/screenshot".format(base_url, sandbox_id)
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers={"Authorization": "Bearer {}".format(api_key)})
            resp.raise_for_status()
            return resp.content

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def _launch_view(record: HarborLaunchRecord | None) -> dict[str, Any] | None:
    if record is None:
        return None
    return {
        "status": record.status,
        "configPath": record.config_path,
        "error": record.error,
        "startedAt": record.started_at,
        "finishedAt": record.finished_at,
        "exitCode": record.exit_code,
        "executionPlane": record.execution_plane,
        "remoteRunId": record.remote_run_id,
    }


def _rel_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
