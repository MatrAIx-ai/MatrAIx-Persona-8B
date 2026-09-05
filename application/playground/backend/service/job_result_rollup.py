"""Write one Harbor-compatible ``jobs/<job>/result.json`` after shard fan-out.

Does not embed per-trial results (that payload does not scale). Counts come
from trial directories already merged into the canonical job tree.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.service.cohort_shard_planner import _agent_persona_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def expected_trial_count(job_config: dict[str, Any] | None) -> int:
    if not isinstance(job_config, dict):
        return 0
    agents = [row for row in (job_config.get("agents") or []) if isinstance(row, dict)]
    tasks = [row for row in (job_config.get("tasks") or []) if isinstance(row, dict)]
    attempts = max(1, int(job_config.get("n_attempts") or 1))
    return max(len(agents), 1) * max(len(tasks), 1) * attempts if agents else 0


def trial_persona_id(trial_dir: Path) -> str:
    meta_path = trial_dir / "persona_meta.json"
    if meta_path.is_file():
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            payload = None
        if isinstance(payload, dict):
            pid = str(payload.get("persona_id") or payload.get("personaId") or "").strip()
            if pid:
                return pid
    config_path = trial_dir / "config.json"
    if config_path.is_file():
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            payload = None
        if isinstance(payload, dict):
            agent = payload.get("agent") if isinstance(payload.get("agent"), dict) else {}
            return _agent_persona_id(agent, 0)
    return ""


def synthesize_job_result(
    job_dir: Path,
    *,
    job_config: dict[str, Any] | None = None,
    started_at: str | None = None,
    finished: bool = True,
    job_id: str | None = None,
) -> Path:
    """Write a compact job-level ``result.json`` from merged trial dirs."""
    job_dir.mkdir(parents=True, exist_ok=True)
    trial_dirs = [
        path
        for path in sorted(job_dir.iterdir())
        if path.is_dir() and not path.name.startswith("_")
    ]
    completed = 0
    errored = 0
    cancelled = 0
    for trial_dir in trial_dirs:
        result_path = trial_dir / "result.json"
        if not result_path.is_file():
            continue
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        completed += 1
        exc = payload.get("exception_info")
        if isinstance(exc, dict) and exc.get("exception_type"):
            errored += 1
            if exc.get("exception_type") == "CancelledError":
                cancelled += 1
    expected = expected_trial_count(job_config) or completed
    if finished and expected > completed:
        errored += expected - completed
    running = 0 if finished else max(expected - completed, 0)
    now = _utc_now()
    result = {
        "id": job_id or str(uuid.uuid4()),
        "started_at": started_at or now,
        "updated_at": now,
        "finished_at": now if finished else None,
        "n_total_trials": expected,
        "stats": {
            "n_completed_trials": completed,
            "n_errored_trials": errored,
            "n_running_trials": running,
            "n_pending_trials": max(expected - completed - running, 0),
            "n_cancelled_trials": cancelled,
            "n_retries": 0,
            "evals": {},
        },
    }
    path = job_dir / "result.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path
