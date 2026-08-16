"""Deterministic job result summary and export for ``matraix results``.

Reads Harbor ``jobs/<job>/`` trees only — no extra LLM calls. Complements
Playground PDF / aggregation with a CLI path from run to insight (#78 P2).
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


_SKIP_DIR_NAMES = frozenset(
    {
        "_generated",
        "agent",
        "artifacts",
        "verifier",
        "logs",
        "__pycache__",
    }
)


@dataclass
class TrialUsage:
    n_input_tokens: int | None = None
    n_output_tokens: int | None = None
    n_cache_tokens: int | None = None
    cost_usd: float | None = None


@dataclass
class TrialSummary:
    trial_name: str
    persona_id: str | None = None
    persona_name: str | None = None
    reward: float | None = None
    error: str | None = None
    usage: TrialUsage = field(default_factory=TrialUsage)
    artifact_paths: list[str] = field(default_factory=list)
    survey_answers: dict[str, Any] = field(default_factory=dict)
    group_values: dict[str, str] = field(default_factory=dict)


@dataclass
class JobResultsReport:
    job_name: str
    job_dir: str
    n_trials: int = 0
    n_completed: int | None = None
    n_errored: int | None = None
    n_running: int | None = None
    n_pending: int | None = None
    usage: TrialUsage = field(default_factory=TrialUsage)
    trials: list[TrialSummary] = field(default_factory=list)
    question_distributions: dict[str, dict[str, int]] = field(default_factory=dict)
    group_by: list[str] = field(default_factory=list)
    grouped_distributions: dict[str, dict[str, dict[str, dict[str, int]]]] = field(
        default_factory=dict
    )
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_job_dir(job: str | Path, *, repo_root: Path | None = None) -> Path:
    """Resolve a job name or path to ``jobs/<job>/``."""
    raw = Path(job).expanduser()
    candidates: list[Path] = []
    if raw.is_absolute() or raw.exists():
        candidates.append(raw.resolve())
    else:
        cwd = Path.cwd()
        candidates.append((cwd / raw).resolve())
        candidates.append((cwd / "jobs" / raw).resolve())
        if repo_root is not None:
            candidates.append((repo_root / raw).resolve())
            candidates.append((repo_root / "jobs" / raw).resolve())
    for path in candidates:
        if path.is_dir() and (path / "result.json").is_file():
            return path
        if path.is_dir() and any(
            (child / "result.json").is_file() for child in path.iterdir() if child.is_dir()
        ):
            return path
    raise FileNotFoundError(f"job directory not found: {job}")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _usage_from_mapping(mapping: dict[str, Any] | None) -> TrialUsage:
    if not mapping:
        return TrialUsage()
    return TrialUsage(
        n_input_tokens=_as_int(mapping.get("n_input_tokens")),
        n_output_tokens=_as_int(mapping.get("n_output_tokens")),
        n_cache_tokens=_as_int(mapping.get("n_cache_tokens")),
        cost_usd=_as_float(mapping.get("cost_usd")),
    )


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value.strip()))
        except ValueError:
            return None
    return None


def _as_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _reward_from_trial_result(result: dict[str, Any] | None) -> float | None:
    if not result:
        return None
    verifier = result.get("verifier_result")
    if isinstance(verifier, dict):
        rewards = verifier.get("rewards")
        if isinstance(rewards, dict) and "reward" in rewards:
            return _as_float(rewards.get("reward"))
        if "reward" in verifier:
            return _as_float(verifier.get("reward"))
    return None


def _trial_error(result: dict[str, Any] | None) -> str | None:
    if not result:
        return None
    exc = result.get("exception_info")
    if isinstance(exc, dict):
        msg = exc.get("exception_message") or exc.get("exception_type")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
    return None


def _list_trial_dirs(job_dir: Path) -> list[Path]:
    trials: list[Path] = []
    for child in sorted(job_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name in _SKIP_DIR_NAMES or child.name.startswith("."):
            continue
        if (child / "result.json").is_file() or (child / "artifacts").is_dir():
            trials.append(child)
    return trials


def _find_output_dir(trial_dir: Path) -> Path | None:
    candidates = [
        trial_dir / "artifacts" / "app" / "output",
        trial_dir / "artifacts" / "output",
        trial_dir / "output",
    ]
    for path in candidates:
        if path.is_dir():
            return path
    return None


def _artifact_paths(trial_dir: Path, *, job_dir: Path) -> list[str]:
    output = _find_output_dir(trial_dir)
    if output is None:
        return []
    paths: list[str] = []
    for path in sorted(output.glob("*.json")):
        try:
            paths.append(str(path.relative_to(job_dir)))
        except ValueError:
            paths.append(str(path))
    return paths


def _survey_answers(trial_dir: Path) -> dict[str, Any]:
    output = _find_output_dir(trial_dir)
    if output is None:
        return {}
    for name in ("survey_result.json", "survey_responses.json"):
        payload = _read_json(output / name)
        if not payload:
            continue
        answers = payload.get("answers")
        if not isinstance(answers, list):
            continue
        out: dict[str, Any] = {}
        for entry in answers:
            if not isinstance(entry, dict):
                continue
            qid = entry.get("questionId") or entry.get("question_id")
            if qid is None:
                continue
            out[str(qid)] = entry.get("value")
        return out
    return {}


def _persona_meta(trial_dir: Path) -> dict[str, Any]:
    return _read_json(trial_dir / "persona_meta.json") or {}


def _group_values_for_trial(
    trial_dir: Path,
    *,
    group_by: list[str],
    persona_meta: dict[str, Any],
) -> dict[str, str]:
    if not group_by:
        return {}
    dimensions: dict[str, Any] = {}
    raw_dims = persona_meta.get("dimensions")
    if isinstance(raw_dims, dict):
        dimensions.update(raw_dims)
    persona_path = persona_meta.get("persona_path")
    if isinstance(persona_path, str) and persona_path.strip():
        path = Path(persona_path)
        if path.is_file():
            try:
                import yaml

                loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                loaded = None
            if isinstance(loaded, dict):
                dims = loaded.get("dimensions")
                if isinstance(dims, dict):
                    dimensions.update(dims)
    out: dict[str, str] = {}
    for key in group_by:
        if key in persona_meta and persona_meta[key] is not None:
            out[key] = str(persona_meta[key])
        elif key in dimensions and dimensions[key] is not None:
            out[key] = str(dimensions[key])
        else:
            out[key] = "unknown"
    return out


def _summarize_trial(
    trial_dir: Path,
    *,
    job_dir: Path,
    group_by: list[str],
) -> TrialSummary:
    result = _read_json(trial_dir / "result.json")
    agent_result = result.get("agent_result") if isinstance(result, dict) else None
    if not isinstance(agent_result, dict):
        agent_result = None
    meta = _persona_meta(trial_dir)
    return TrialSummary(
        trial_name=trial_dir.name,
        persona_id=(
            str(meta["persona_id"])
            if meta.get("persona_id") is not None
            else None
        ),
        persona_name=(
            str(meta["display_name"])
            if meta.get("display_name") is not None
            else (str(meta["persona_name"]) if meta.get("persona_name") is not None else None)
        ),
        reward=_reward_from_trial_result(result),
        error=_trial_error(result),
        usage=_usage_from_mapping(agent_result),
        artifact_paths=_artifact_paths(trial_dir, job_dir=job_dir),
        survey_answers=_survey_answers(trial_dir),
        group_values=_group_values_for_trial(
            trial_dir, group_by=group_by, persona_meta=meta
        ),
    )


def _question_distributions(trials: Iterable[TrialSummary]) -> dict[str, dict[str, int]]:
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    for trial in trials:
        for qid, value in trial.survey_answers.items():
            counters[qid][str(value)] += 1
    return {
        qid: dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))
        for qid, counter in sorted(counters.items())
    }


def _grouped_distributions(
    trials: list[TrialSummary],
    *,
    group_by: list[str],
) -> dict[str, dict[str, dict[str, dict[str, int]]]]:
    if not group_by:
        return {}
    # group_key -> group_value -> question -> answer -> count
    nested: dict[str, dict[str, dict[str, Counter[str]]]] = {
        key: defaultdict(lambda: defaultdict(Counter)) for key in group_by
    }
    for trial in trials:
        for key in group_by:
            group_value = trial.group_values.get(key, "unknown")
            for qid, value in trial.survey_answers.items():
                nested[key][group_value][qid][str(value)] += 1
    out: dict[str, dict[str, dict[str, dict[str, int]]]] = {}
    for key, by_group in nested.items():
        out[key] = {}
        for group_value, by_q in sorted(by_group.items()):
            out[key][group_value] = {
                qid: dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))
                for qid, counter in sorted(by_q.items())
            }
    return out


def collect_job_results(
    job_dir: Path,
    *,
    group_by: list[str] | None = None,
) -> JobResultsReport:
    """Build a deterministic report for one Harbor job directory."""
    job_dir = job_dir.resolve()
    group_keys = [key.strip() for key in (group_by or []) if key.strip()]
    job_result = _read_json(job_dir / "result.json") or {}
    stats = job_result.get("stats") if isinstance(job_result.get("stats"), dict) else {}
    trials = [
        _summarize_trial(trial_dir, job_dir=job_dir, group_by=group_keys)
        for trial_dir in _list_trial_dirs(job_dir)
    ]
    notes = [
        "Deterministic export from jobs/<job>/ — no additional LLM calls.",
        "Trial reward comes from result.json verifier_result; survey answers "
        "from artifacts/app/output/survey_result.json when present.",
    ]
    if group_keys and not any(trial.group_values for trial in trials):
        notes.append(
            "group-by keys were requested but no matching persona fields were found."
        )
    return JobResultsReport(
        job_name=job_dir.name,
        job_dir=str(job_dir),
        n_trials=len(trials),
        n_completed=_as_int(stats.get("n_completed_trials")),
        n_errored=_as_int(stats.get("n_errored_trials")),
        n_running=_as_int(stats.get("n_running_trials")),
        n_pending=_as_int(stats.get("n_pending_trials")),
        usage=_usage_from_mapping(stats),
        trials=trials,
        question_distributions=_question_distributions(trials),
        group_by=group_keys,
        grouped_distributions=_grouped_distributions(trials, group_by=group_keys),
        notes=notes,
    )


def format_text_report(report: JobResultsReport) -> str:
    lines: list[str] = []
    lines.append(f"Job: {report.job_name}")
    lines.append(f"Path: {report.job_dir}")
    completed = report.n_completed if report.n_completed is not None else sum(
        1 for trial in report.trials if trial.error is None and trial.reward is not None
    )
    errored = report.n_errored if report.n_errored is not None else sum(
        1 for trial in report.trials if trial.error
    )
    lines.append(
        f"Trials: {report.n_trials} total · {completed} completed · {errored} errored"
    )
    usage_bits: list[str] = []
    if report.usage.cost_usd is not None:
        usage_bits.append(f"cost ${report.usage.cost_usd:g}")
    if report.usage.n_input_tokens is not None:
        usage_bits.append(f"{report.usage.n_input_tokens:,} in")
    if report.usage.n_output_tokens is not None:
        usage_bits.append(f"{report.usage.n_output_tokens:,} out")
    if report.usage.n_cache_tokens is not None and report.usage.n_cache_tokens > 0:
        usage_bits.append(f"{report.usage.n_cache_tokens:,} cache")
    if usage_bits:
        lines.append("Usage: " + " · ".join(usage_bits))
    else:
        lines.append("Usage: (not recorded on job result.json)")

    if report.question_distributions:
        lines.append("")
        lines.append("Question distributions")
        for qid, counts in report.question_distributions.items():
            total = sum(counts.values())
            top = ", ".join(f"{value}={count}" for value, count in list(counts.items())[:5])
            lines.append(f"  {qid} (n={total}): {top}")

    if report.grouped_distributions:
        lines.append("")
        lines.append("Grouped distributions")
        for key, by_group in report.grouped_distributions.items():
            lines.append(f"  by {key}:")
            for group_value, by_q in by_group.items():
                lines.append(f"    {group_value}:")
                for qid, counts in list(by_q.items())[:8]:
                    top = ", ".join(
                        f"{value}={count}" for value, count in list(counts.items())[:4]
                    )
                    lines.append(f"      {qid}: {top}")

    lines.append("")
    lines.append("Trials")
    for trial in report.trials:
        persona = trial.persona_name or trial.persona_id or "-"
        reward = "-" if trial.reward is None else f"{trial.reward:g}"
        status = "error" if trial.error else "ok"
        cost = (
            f"${trial.usage.cost_usd:g}"
            if trial.usage.cost_usd is not None
            else "-"
        )
        artifact = trial.artifact_paths[0] if trial.artifact_paths else "-"
        lines.append(
            f"  {trial.trial_name} · {persona} · reward={reward} · "
            f"{status} · cost={cost} · {artifact}"
        )

    lines.append("")
    lines.append("Notes")
    for note in report.notes:
        lines.append(f"  - {note}")
    return "\n".join(lines) + "\n"


def format_json_report(report: JobResultsReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n"


def format_csv_report(report: JobResultsReport) -> str:
    """One row per trial; survey answers expand as answer_<qid> columns."""
    answer_keys = sorted(
        {qid for trial in report.trials for qid in trial.survey_answers}
    )
    group_keys = report.group_by
    fieldnames = [
        "job_name",
        "trial_name",
        "persona_id",
        "persona_name",
        "reward",
        "error",
        "n_input_tokens",
        "n_output_tokens",
        "n_cache_tokens",
        "cost_usd",
        "artifact_paths",
        *[f"group_{key}" for key in group_keys],
        *[f"answer_{qid}" for qid in answer_keys],
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for trial in report.trials:
        row: dict[str, Any] = {
            "job_name": report.job_name,
            "trial_name": trial.trial_name,
            "persona_id": trial.persona_id or "",
            "persona_name": trial.persona_name or "",
            "reward": "" if trial.reward is None else trial.reward,
            "error": trial.error or "",
            "n_input_tokens": trial.usage.n_input_tokens
            if trial.usage.n_input_tokens is not None
            else "",
            "n_output_tokens": trial.usage.n_output_tokens
            if trial.usage.n_output_tokens is not None
            else "",
            "n_cache_tokens": trial.usage.n_cache_tokens
            if trial.usage.n_cache_tokens is not None
            else "",
            "cost_usd": trial.usage.cost_usd if trial.usage.cost_usd is not None else "",
            "artifact_paths": ";".join(trial.artifact_paths),
        }
        for key in group_keys:
            row[f"group_{key}"] = trial.group_values.get(key, "")
        for qid in answer_keys:
            value = trial.survey_answers.get(qid, "")
            row[f"answer_{qid}"] = "" if value is None else value
        writer.writerow(row)
    return buf.getvalue()


def parse_formats(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return ["text"]
    formats = [part.strip().lower() for part in raw.split(",") if part.strip()]
    allowed = {"text", "json", "csv"}
    unknown = [fmt for fmt in formats if fmt not in allowed]
    if unknown:
        raise ValueError(
            f"unsupported format(s): {', '.join(unknown)} (allowed: text,json,csv)"
        )
    return formats or ["text"]
