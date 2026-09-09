"""Harbor web trace helpers: screenshot discovery and API URL attachment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from backend.service.import_paths import ensure_harbor_source_imports

_ALLOWED_SUFFIXES = {".png", ".webp", ".jpg", ".jpeg", ".svg"}


def _is_safe_relative_path(path: str) -> bool:
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts:
        return False
    return rel.suffix.lower() in _ALLOWED_SUFFIXES


def _rel_screenshot_path(path: str) -> str | None:
    raw = path.strip().replace("\\", "/")
    if raw.startswith("file://"):
        raw = raw[7:]
    if _is_safe_relative_path(raw):
        return raw
    parts = Path(raw).parts
    if "images" in parts:
        rel = "/".join(parts[parts.index("images") :])
        if _is_safe_relative_path(rel):
            return rel
    name = Path(raw).name
    if name and _is_safe_relative_path(name):
        return name
    return None


def screenshot_file_from_step(step: dict[str, Any]) -> str | None:
    """Return a logs-dir-relative screenshot path for one ATIF trajectory step."""
    observation = step.get("observation")
    if isinstance(observation, dict):
        results = observation.get("results")
        if isinstance(results, list):
            for result in results:
                if not isinstance(result, dict):
                    continue
                content = result.get("content")
                if not isinstance(content, list):
                    continue
                for item in content:
                    if not isinstance(item, dict) or item.get("type") != "image":
                        continue
                    source = item.get("source")
                    if not isinstance(source, dict):
                        continue
                    path = source.get("path")
                    if isinstance(path, str):
                        rel = _rel_screenshot_path(path)
                        if rel:
                            return rel

    message = step.get("message")
    if isinstance(message, list):
        for item in message:
            if not isinstance(item, dict) or item.get("type") != "image":
                continue
            source = item.get("source")
            if not isinstance(source, dict):
                continue
            path = source.get("path")
            if isinstance(path, str):
                rel = _rel_screenshot_path(path)
                if rel:
                    return rel

    return None


def harbor_screenshot_url(job_name: str, trial_name: str, rel_path: str) -> str:
    return "/api/harbor/jobs/{}/trials/{}/screenshots/{}".format(
        quote(job_name, safe=""),
        quote(trial_name, safe=""),
        quote(rel_path, safe="/"),
    )


def attach_harbor_trace_screenshot_urls(
    trace: dict[str, Any] | None,
    *,
    job_name: str,
    trial_name: str,
) -> dict[str, Any] | None:
    if trace is None:
        return None
    view = dict(trace)
    events: list[dict[str, Any]] = []
    raw_events = trace.get("events")
    if isinstance(raw_events, list):
        for event in raw_events:
            if not isinstance(event, dict):
                continue
            event_view = dict(event)
            if event_view.get("screenshotUrl"):
                events.append(event_view)
                continue
            screenshot_file = event_view.get("screenshotFile")
            if isinstance(screenshot_file, str) and screenshot_file.strip():
                event_view["screenshotUrl"] = harbor_screenshot_url(
                    job_name,
                    trial_name,
                    screenshot_file.strip(),
                )
            events.append(event_view)
    view["events"] = events
    return view


def resolve_trial_screenshot_path(logs_dir: Path, rel_path: str) -> Path:
    safe = Path(rel_path)
    if not _is_safe_relative_path(rel_path):
        raise ValueError("invalid screenshot path")
    base = logs_dir.resolve()
    path = (logs_dir / safe).resolve()
    if not str(path).startswith(str(base)):
        raise ValueError("invalid screenshot path")
    if not path.is_file():
        raise FileNotFoundError(rel_path)
    return path


def latest_trial_screenshot_bytes(trial_dir: Path) -> bytes | None:
    """Newest image under the trial logs tree (Harbor modal/gke flush or docker)."""
    from backend.service.harbor_trial_debrief import find_trial_logs_dir

    logs_dir = find_trial_logs_dir(trial_dir)
    if logs_dir is None or not logs_dir.is_dir():
        return None
    newest: Path | None = None
    newest_mtime = -1.0
    for path in logs_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _ALLOWED_SUFFIXES:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= newest_mtime:
            newest = path
            newest_mtime = mtime
    if newest is None:
        return None
    return newest.read_bytes()


def read_harbor_web_trace(
    logs_dir: Path | None,
    *,
    job_name: str,
    trial_name: str,
) -> dict[str, Any]:
    if logs_dir is None:
        return {"events": [], "raw": {}}
    trajectory_path = logs_dir / "trajectory.json"
    if not trajectory_path.is_file():
        return {"events": [], "raw": {}}
    ensure_harbor_source_imports()
    from playground.harbor.web_eval import _trace_from_trajectory

    trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
    if not isinstance(trajectory, dict):
        return {"events": [], "raw": {}}
    trace = _trace_from_trajectory(trajectory).to_dict()
    return attach_harbor_trace_screenshot_urls(
        trace,
        job_name=job_name,
        trial_name=trial_name,
    ) or {"events": [], "raw": {}}
