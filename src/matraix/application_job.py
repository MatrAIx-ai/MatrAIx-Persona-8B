"""Build multi-persona Harbor job configs for application task runs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from matraix.compute_family import resolve_compute_plan
from matraix.persona_agent_context import apply_persona_context_to_agent_spec
from matraix.persona_job import (
    load_manifest,
    sample_personas,
    sample_personas_stratified,
)

DEFAULT_APPLICATION_JOBS_DIR = "configs/jobs/application-task-job-recipe"
_EXECUTION_MODES = frozenset({"auto", "force_docker", "smoke"})


def resolve_harbor_task_path(task_path: str, *, trial_profile: str) -> str:
    """Return the Harbor task path for a job (same as the configured task path)."""
    _ = trial_profile
    return task_path


def collect_run_env_exports(
    *,
    trial_profile: str,
    task_path: str,
    repo_root: Path,
) -> list[tuple[str, str]]:
    """Return ``(VAR, value)`` pairs to export before ``matraix run``."""
    _ = repo_root
    exports: list[tuple[str, str]] = []
    if trial_profile == "json_survey":
        exports.append(("MATRIX_SURVEY_TASK_PATH", task_path))
    elif trial_profile == "user_sim_chat":
        exports.append(("MATRIX_CHATBOT_TASK_PATH", task_path))
    return exports


def resolve_job_environment(
    *,
    execution_mode: str,
    trial_profile: str,
    cua_backend: str | None = None,
    compute_family: str | None = None,
) -> dict[str, Any]:
    """Pick the Harbor environment block for a job spec.

    ``compute_family`` (``local`` / ``modal`` / ``gcp``) selects the provider.
    Survey/chat on ``modal`` keep Harbor ``type: host`` (Modal Function).
    Web/linux on ``modal`` keep Harbor ``type: docker`` and run in a Sandbox
    (task images cached on a Volume). CUA macOS/iOS still pins ``use-computer``.
    """
    return resolve_compute_plan(
        execution_mode=execution_mode,
        trial_profile=trial_profile,
        cua_backend=cua_backend,
        compute_family=compute_family,
    ).harbor_environment()


def select_personas(
    pool: list[dict[str, Any]],
    *,
    sample_size: int | None,
    sample_size_per_value_group: int,
    seed: int,
    stratify_fields: list[str] | None,
    repo_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (matched pool, chosen personas)."""
    matched = pool
    if stratify_fields:
        chosen = sample_personas_stratified(
            pool,
            stratify_fields=stratify_fields,
            sample_size_per_value_group=sample_size_per_value_group,
            seed=seed,
            repo_root=repo_root,
        )
    else:
        total = int(
            sample_size if sample_size is not None else sample_size_per_value_group
        )
        chosen = sample_personas(matched, sample_size=total, seed=seed)
    return matched, chosen


def _normalize_pool_persona_id(value: str) -> str:
    text = value.strip()
    if re.fullmatch(r"\d+", text):
        return text.zfill(4)
    if text.startswith("persona_"):
        return text.removeprefix("persona_").zfill(4) if text[8:].isdigit() else text
    return text


def _persona_entry_from_path(path: Path, *, repo_root: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("persona file is not a mapping: {}".format(path))
    persona_id = str(raw.get("persona_id") or raw.get("id") or path.stem)
    return {
        "persona_id": persona_id,
        "path": str(path.relative_to(repo_root)),
        **raw,
    }


def resolve_persona_entries(
    persona_ids: list[str],
    *,
    persona_pool: str,
    repo_root: Path,
) -> list[dict[str, Any]]:
    """Resolve explicit persona ids to manifest-style entries."""
    if not persona_ids:
        raise ValueError("persona_ids must not be empty")

    pool = load_manifest(repo_root / persona_pool, repo_root=repo_root)
    by_id: dict[str, dict[str, Any]] = {}
    for entry in pool:
        for key in (
            str(entry.get("persona_id") or ""),
            str(entry.get("id") or ""),
            Path(str(entry.get("path", ""))).stem,
        ):
            if not key:
                continue
            by_id[key] = entry
            normalized = _normalize_pool_persona_id(key)
            if normalized != key:
                by_id[normalized] = entry

    chosen: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for raw_id in persona_ids:
        persona_id = raw_id.strip()
        if not persona_id:
            raise ValueError("persona_ids must not contain empty values")

        entry = by_id.get(persona_id) or by_id.get(_normalize_pool_persona_id(persona_id))
        if entry is None:
            pool_path = (
                repo_root
                / persona_pool
                / "persona_{}.yaml".format(_normalize_pool_persona_id(persona_id))
            )
            if pool_path.is_file():
                entry = _persona_entry_from_path(pool_path, repo_root=repo_root)
            else:
                raise ValueError(
                    "unknown persona {} in pool {}".format(persona_id, persona_pool)
                )

        path = str(entry.get("path") or "")
        if path in seen_paths:
            continue
        seen_paths.add(path)
        chosen.append(entry)
    return chosen


def build_application_job_config(
    spec: dict[str, Any], *, repo_root: Path
) -> dict[str, Any]:
    pool_dir = repo_root / spec["persona_pool"]
    per_value_group = int(spec.get("sample_size_per_value_group", 1))
    sample_size_total = spec.get("sample_size")
    seed = int(spec.get("seed", 42))
    stratify_fields = list(spec.get("stratify_fields") or [])
    persona_ids = list(spec.get("persona_ids") or [])
    execution_mode = str(spec.get("execution_mode") or "auto").strip().lower()
    trial_profile = str(spec.get("trial_profile") or "docker_agent").strip()
    cua_backend = spec.get("cua_backend")
    if execution_mode not in _EXECUTION_MODES:
        raise ValueError(
            "execution_mode must be one of {}".format(sorted(_EXECUTION_MODES))
        )

    pool = load_manifest(pool_dir, repo_root=repo_root)
    use_entire_pool = bool(spec.get("use_entire_pool"))
    if persona_ids:
        matched = pool
        chosen = resolve_persona_entries(
            persona_ids,
            persona_pool=spec["persona_pool"],
            repo_root=repo_root,
        )
    elif use_entire_pool:
        matched = pool
        chosen = list(pool)
        if not chosen:
            raise ValueError(
                "use_entire_pool=True but persona pool is empty: {}".format(
                    spec["persona_pool"]
                )
            )
    else:
        matched, chosen = select_personas(
            pool,
            sample_size=sample_size_total,
            sample_size_per_value_group=per_value_group,
            seed=seed,
            stratify_fields=stratify_fields or None,
            repo_root=repo_root,
        )

    agent_spec = spec["agent"]
    job_spec = spec.get("job", {})
    job_slug = spec.get("name", "application-task-job")

    agents = [
        apply_persona_context_to_agent_spec(
            {
                "name": agent_spec["name"],
                "model_name": agent_spec["model_name"],
                "kwargs": {"persona_path": entry["path"]},
            },
            model_name=str(agent_spec.get("model_name") or ""),
        )
        for entry in chosen
    ]

    job: dict[str, Any] = {
        "job_name": job_spec.get("job_name", job_slug),
        "jobs_dir": job_spec.get("jobs_dir", "jobs"),
        "n_attempts": job_spec.get("n_attempts", 1),
        "timeout_multiplier": job_spec.get("timeout_multiplier", 1.0),
        "n_concurrent_trials": job_spec.get("n_concurrent_trials", 1),
        "quiet": job_spec.get("quiet", False),
        "environment": job_spec.get(
            "environment",
            resolve_job_environment(
                execution_mode=execution_mode,
                trial_profile=trial_profile,
                cua_backend=str(cua_backend) if cua_backend else None,
                compute_family=(
                    str(spec.get("compute_family")).strip()
                    if spec.get("compute_family")
                    else None
                ),
            ),
        ),
        "agents": agents,
        "tasks": [{"path": resolve_harbor_task_path(spec["task"], trial_profile=trial_profile)}],
        "_job_meta": {
            "job_slug": job_slug,
            "task": spec["task"],
            "sample_size": len(chosen),
            "sample_size_per_value_group": per_value_group,
            "seed": seed,
            "stratify_fields": stratify_fields,
            "matched_pool_size": len(matched),
            "selected_persona_ids": [entry["persona_id"] for entry in chosen],
            "persona_ids": persona_ids,
            "use_entire_pool": use_entire_pool,
            "execution_mode": execution_mode,
            "trial_profile": trial_profile,
        },
    }
    verifier = spec.get("verifier")
    if verifier:
        job["verifier"] = verifier
    return job
