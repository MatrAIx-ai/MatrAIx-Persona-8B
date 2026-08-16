"""Deterministic job result summary and export for ``matraix results``.

Reads Harbor ``jobs/<job>/`` trees only — no extra model calls. Universal
``JobLedger`` plus a thin type-aware ``OutcomeLens`` (Survey / Chat / Web /
OS-app) produce ``MatraixJobResults.v1``.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "MatraixJobResults.v1"

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

_APP_TYPES = frozenset({"survey", "chatbot", "web", "os-app", "unknown"})


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
    signals: dict[str, Any] = field(default_factory=dict)
    group_values: dict[str, str] = field(default_factory=dict)
    # Backward-compatible alias used by early Survey CSV/tests.
    survey_answers: dict[str, Any] = field(default_factory=dict)


@dataclass
class Distribution:
    key: str
    label: str
    counts: dict[str, int]


@dataclass
class Metric:
    key: str
    label: str
    value: float | int | str | None
    unit: str | None = None


@dataclass
class OutcomeLens:
    kind: str
    primary_summary: str
    distributions: list[Distribution] = field(default_factory=list)
    metrics: list[Metric] = field(default_factory=list)
    source: str = "none"


@dataclass
class JobLedger:
    coverage: dict[str, int | None]
    usage: TrialUsage
    rewards: dict[str, Any]
    trials: list[TrialSummary]


@dataclass
class JobResultsReport:
    """``MatraixJobResults.v1`` report object."""

    schema_version: str = SCHEMA_VERSION
    job_name: str = ""
    job_dir: str = ""
    generated_at: str = ""
    deterministic: bool = True
    app_type: str = "unknown"
    ledger: JobLedger | None = None
    lens: OutcomeLens | None = None
    group_by: list[str] = field(default_factory=list)
    grouped_distributions: dict[str, dict[str, dict[str, dict[str, int]]]] = field(
        default_factory=dict
    )
    notes: list[str] = field(default_factory=list)

    # Convenience mirrors for callers that still expect flat fields.
    @property
    def n_trials(self) -> int:
        return len(self.ledger.trials) if self.ledger else 0

    @property
    def n_completed(self) -> int | None:
        return None if not self.ledger else self.ledger.coverage.get("completed")

    @property
    def n_errored(self) -> int | None:
        return None if not self.ledger else self.ledger.coverage.get("errored")

    @property
    def usage(self) -> TrialUsage:
        return self.ledger.usage if self.ledger else TrialUsage()

    @property
    def trials(self) -> list[TrialSummary]:
        return self.ledger.trials if self.ledger else []

    @property
    def question_distributions(self) -> dict[str, dict[str, int]]:
        if not self.lens:
            return {}
        return {dist.key: dict(dist.counts) for dist in self.lens.distributions}

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schemaVersion": self.schema_version,
            "jobName": self.job_name,
            "jobDir": self.job_dir,
            "generatedAt": self.generated_at,
            "deterministic": self.deterministic,
            "appType": self.app_type,
            "ledger": {
                "coverage": dict(self.ledger.coverage) if self.ledger else {},
                "usage": asdict(self.usage),
                "rewards": dict(self.ledger.rewards) if self.ledger else {},
                "trials": [asdict(trial) for trial in self.trials],
            },
            "lens": {
                "kind": self.lens.kind if self.lens else "none",
                "primarySummary": self.lens.primary_summary if self.lens else "",
                "distributions": [asdict(dist) for dist in (self.lens.distributions if self.lens else [])],
                "metrics": [asdict(metric) for metric in (self.lens.metrics if self.lens else [])],
                "source": self.lens.source if self.lens else "none",
            },
            "groupBy": list(self.group_by),
            "groupedDistributions": self.grouped_distributions,
            "notes": list(self.notes),
        }
        return payload


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
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


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


def _usage_from_mapping(mapping: dict[str, Any] | None) -> TrialUsage:
    if not mapping:
        return TrialUsage()
    return TrialUsage(
        n_input_tokens=_as_int(mapping.get("n_input_tokens")),
        n_output_tokens=_as_int(mapping.get("n_output_tokens")),
        n_cache_tokens=_as_int(mapping.get("n_cache_tokens")),
        cost_usd=_as_float(mapping.get("cost_usd")),
    )


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
    for path in (
        trial_dir / "artifacts" / "app" / "output",
        trial_dir / "artifacts" / "output",
        trial_dir / "output",
    ):
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


def _persona_meta(trial_dir: Path) -> dict[str, Any]:
    return _read_json(trial_dir / "persona_meta.json") or {}


def _group_values_for_trial(
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
            if isinstance(loaded, dict) and isinstance(loaded.get("dimensions"), dict):
                dimensions.update(loaded["dimensions"])
    out: dict[str, str] = {}
    for key in group_by:
        if key in persona_meta and persona_meta[key] is not None:
            out[key] = str(persona_meta[key])
        elif key in dimensions and dimensions[key] is not None:
            out[key] = str(dimensions[key])
        else:
            out[key] = "unknown"
    return out


def _facet_map(context: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    facets = context.get("facets")
    if not isinstance(facets, list):
        return out
    for facet in facets:
        if not isinstance(facet, dict):
            continue
        key = facet.get("key")
        if key is None:
            continue
        if "value" in facet:
            out[str(key)] = facet.get("value")
    return out


def _structured_output(trial_dir: Path) -> dict[str, Any] | None:
    return _read_json(trial_dir / "verifier" / "structured_output.json")


def _signals_from_structured_output(payload: dict[str, Any]) -> dict[str, Any]:
    signals: dict[str, Any] = {}
    contexts = payload.get("contexts")
    if not isinstance(contexts, list):
        return signals
    for context in contexts:
        if not isinstance(context, dict):
            continue
        context_type = str(context.get("contextType") or "").strip()
        facets = _facet_map(context)
        if context_type == "question_response":
            qid = str(context.get("key") or context.get("label") or "question")
            if qid.startswith("question."):
                qid = qid[len("question.") :]
            if "response" in facets:
                signals[f"answer_{qid}"] = facets["response"]
        elif context_type == "task_outcome":
            if "outcome_status" in facets:
                signals["outcome_status"] = facets["outcome_status"]
            if "goal_completion_ratio" in facets:
                signals["goal_completion_ratio"] = facets["goal_completion_ratio"]
        elif context_type in {"decision", "web_artifact"}:
            label = (
                facets.get("decision_subject_label")
                or facets.get("artifact_subject_label")
                or facets.get("decision_subject_id")
                or facets.get("artifact_subject_id")
            )
            if label is not None:
                signals["decision_label"] = label
            if "decision_outcome" in facets:
                signals["decision_outcome"] = facets["decision_outcome"]
        elif context_type == "goal_component":
            key = facets.get("goal_component_key") or context.get("key")
            status = facets.get("goal_component_status")
            if key is not None and status is not None:
                signals[f"goal_{key}"] = status
        elif context_type == "user_feedback":
            for key in (
                "overall_experience_rating",
                "need_constraint_satisfaction",
                "clarification_questions_useful",
            ):
                if key in facets:
                    signals[f"feedback_{key}"] = facets[key]
        elif context_type == "conversation_summary":
            if "conversation_path" in facets:
                signals["conversation_path"] = facets["conversation_path"]
    return signals


def _survey_answers_from_artifact(trial_dir: Path) -> dict[str, Any]:
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


def _decision_label_from_artifact(trial_dir: Path) -> str | None:
    output = _find_output_dir(trial_dir)
    if output is None:
        return None
    for path in sorted(output.glob("*.json")):
        if path.name in {"user_feedback.json", "survey_result.json", "survey_responses.json", "transcript.json"}:
            continue
        payload = _read_json(path)
        if not payload:
            continue
        for key in (
            "decision_subject_label",
            "selectedProductName",
            "selected_product_name",
            "decision_subject_id",
            "selectedProductId",
        ):
            value = payload.get(key)
            if value is not None and str(value).strip():
                return str(value)
    return None


def _summarize_trial(
    trial_dir: Path,
    *,
    job_dir: Path,
    group_by: list[str],
    notes: list[str],
) -> TrialSummary | None:
    try:
        result = _read_json(trial_dir / "result.json")
        agent_result = result.get("agent_result") if isinstance(result, dict) else None
        if not isinstance(agent_result, dict):
            agent_result = None
        meta = _persona_meta(trial_dir)
        structured = _structured_output(trial_dir)
        signals: dict[str, Any] = {}
        survey_answers: dict[str, Any] = {}
        if structured:
            signals.update(_signals_from_structured_output(structured))
            for key, value in list(signals.items()):
                if key.startswith("answer_"):
                    survey_answers[key[len("answer_") :]] = value
        if not survey_answers:
            survey_answers = _survey_answers_from_artifact(trial_dir)
            for qid, value in survey_answers.items():
                signals.setdefault(f"answer_{qid}", value)
        if "decision_label" not in signals:
            label = _decision_label_from_artifact(trial_dir)
            if label is not None:
                signals["decision_label"] = label
        return TrialSummary(
            trial_name=trial_dir.name,
            persona_id=(
                str(meta["persona_id"]) if meta.get("persona_id") is not None else None
            ),
            persona_name=(
                str(meta["display_name"])
                if meta.get("display_name") is not None
                else (
                    str(meta["persona_name"])
                    if meta.get("persona_name") is not None
                    else None
                )
            ),
            reward=_reward_from_trial_result(result),
            error=_trial_error(result),
            usage=_usage_from_mapping(agent_result),
            artifact_paths=_artifact_paths(trial_dir, job_dir=job_dir),
            signals=signals,
            survey_answers=survey_answers,
            group_values=_group_values_for_trial(group_by=group_by, persona_meta=meta),
        )
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Skipped corrupt trial {trial_dir.name}: {exc}")
        return None


def _detect_app_type(job_dir: Path, trials: list[TrialSummary]) -> str:
    votes: Counter[str] = Counter()
    for trial_dir in _list_trial_dirs(job_dir):
        structured = _structured_output(trial_dir)
        if structured:
            task_type = str(structured.get("taskType") or "").strip().lower()
            if task_type in _APP_TYPES and task_type != "unknown":
                votes[task_type] += 1
                continue
        output = _find_output_dir(trial_dir)
        if output is None:
            continue
        names = {path.name.lower() for path in output.glob("*.json")}
        if "survey_result.json" in names or "survey_responses.json" in names:
            votes["survey"] += 1
        elif "transcript.json" in names:
            votes["chatbot"] += 1
        elif any("plan_comparison" in name or "choice" in name for name in names):
            votes["web"] += 1
        elif "decision.json" in names or "submission.json" in names:
            votes["os-app"] += 1
    # Config path hint from first trial.
    for trial_dir in _list_trial_dirs(job_dir)[:3]:
        config = _read_json(trial_dir / "config.json") or {}
        task = config.get("task") if isinstance(config.get("task"), dict) else {}
        path = str(task.get("path") or "").lower()
        if "/survey" in path or path.startswith("application/tasks/survey"):
            votes["survey"] += 1
        elif "/chat" in path or "chatbot" in path:
            votes["chatbot"] += 1
        elif "/web" in path or "web_" in path or "web-" in path:
            votes["web"] += 1
        elif "os-app" in path or "computer-use" in path or "os_app" in path:
            votes["os-app"] += 1
    if not votes:
        # Signal heuristics from collected trials.
        if any(trial.survey_answers for trial in trials):
            return "survey"
        if any("decision_label" in trial.signals for trial in trials):
            return "web"
        if any("outcome_status" in trial.signals for trial in trials):
            return "chatbot"
        return "unknown"
    return votes.most_common(1)[0][0]


def _count_signal(trials: Iterable[TrialSummary], key: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for trial in trials:
        value = trial.signals.get(key)
        if value is None and key.startswith("answer_"):
            value = trial.survey_answers.get(key[len("answer_") :])
        if value is None:
            continue
        counter[str(value)] += 1
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def _top_mix_summary(counts: dict[str, int], *, limit: int = 4) -> str:
    if not counts:
        return "n/a"
    total = sum(counts.values()) or 1
    parts: list[str] = []
    for value, count in list(counts.items())[:limit]:
        pct = 100.0 * count / total
        parts.append(f"{value} {pct:.0f}%")
    return " · ".join(parts)


def _mean_numeric(trials: Iterable[TrialSummary], key: str) -> float | None:
    values: list[float] = []
    for trial in trials:
        raw = trial.signals.get(key)
        number = _as_float(raw)
        if number is not None:
            values.append(number)
    if not values:
        return None
    return sum(values) / len(values)


def _survey_answer_keys(trials: list[TrialSummary]) -> list[str]:
    keys = {
        key[len("answer_") :]
        for trial in trials
        for key in trial.signals
        if key.startswith("answer_")
    } | {qid for trial in trials for qid in trial.survey_answers}

    def sort_key(qid: str) -> tuple[int, int | str]:
        if qid.startswith("q") and qid[1:].isdigit():
            return (0, int(qid[1:]))
        return (1, qid)

    return sorted(keys, key=sort_key)


def build_outcome_lens(app_type: str, trials: list[TrialSummary]) -> OutcomeLens:
    distributions: list[Distribution] = []
    metrics: list[Metric] = []
    source = "structured_output"
    if app_type == "survey":
        answer_keys = _survey_answer_keys(trials)
        for qid in answer_keys:
            counts = _count_signal(trials, f"answer_{qid}")
            if counts:
                distributions.append(
                    Distribution(key=qid, label=f"Question {qid}", counts=counts)
                )
        if not distributions:
            source = "artifact_fallback" if any(trial.survey_answers for trial in trials) else "none"
        primary = (
            _top_mix_summary(distributions[0].counts)
            if distributions
            else "no survey answers recorded"
        )
        if distributions:
            primary = f"{distributions[0].label}: {primary}"
        answered = sum(1 for trial in trials if trial.survey_answers or any(
            key.startswith("answer_") for key in trial.signals
        ))
        metrics.append(Metric(key="answered_trials", label="Trials with answers", value=answered))
        return OutcomeLens(
            kind="survey",
            primary_summary=primary,
            distributions=distributions,
            metrics=metrics,
            source=source if distributions else "none",
        )

    if app_type == "chatbot":
        outcome_counts = _count_signal(trials, "outcome_status")
        path_counts = _count_signal(trials, "conversation_path")
        if outcome_counts:
            distributions.append(
                Distribution(key="outcome_status", label="Task outcome", counts=outcome_counts)
            )
        if path_counts:
            distributions.append(
                Distribution(key="conversation_path", label="Conversation path", counts=path_counts)
            )
        rating = _mean_numeric(trials, "feedback_overall_experience_rating")
        if rating is not None:
            metrics.append(
                Metric(
                    key="avg_overall_experience_rating",
                    label="Avg overall rating",
                    value=round(rating, 2),
                    unit="/10",
                )
            )
        primary = (
            f"Outcomes: {_top_mix_summary(outcome_counts)}"
            if outcome_counts
            else "no chat outcomes recorded"
        )
        return OutcomeLens(
            kind="chatbot",
            primary_summary=primary,
            distributions=distributions,
            metrics=metrics,
            source=source if distributions or metrics else "none",
        )

    if app_type == "web":
        decision_counts = _count_signal(trials, "decision_label")
        outcome_counts = _count_signal(trials, "outcome_status")
        if decision_counts:
            distributions.append(
                Distribution(key="decision_label", label="Choice", counts=decision_counts)
            )
        if outcome_counts:
            distributions.append(
                Distribution(key="outcome_status", label="Task outcome", counts=outcome_counts)
            )
        primary = (
            f"Choices: {_top_mix_summary(decision_counts)}"
            if decision_counts
            else (
                f"Outcomes: {_top_mix_summary(outcome_counts)}"
                if outcome_counts
                else "no web decisions recorded"
            )
        )
        return OutcomeLens(
            kind="web",
            primary_summary=primary,
            distributions=distributions,
            metrics=metrics,
            source=source if distributions else "artifact_fallback" if decision_counts else "none",
        )

    if app_type == "os-app":
        outcome_counts = _count_signal(trials, "outcome_status")
        decision_counts = _count_signal(trials, "decision_label")
        decision_outcome_counts = _count_signal(trials, "decision_outcome")
        goal_keys = sorted(
            {
                key[len("goal_") :]
                for trial in trials
                for key in trial.signals
                if key.startswith("goal_")
            }
        )
        if outcome_counts:
            distributions.append(
                Distribution(key="outcome_status", label="Task outcome", counts=outcome_counts)
            )
        if decision_outcome_counts:
            distributions.append(
                Distribution(
                    key="decision_outcome",
                    label="Decision outcome",
                    counts=decision_outcome_counts,
                )
            )
        if decision_counts:
            distributions.append(
                Distribution(key="decision_label", label="Decision", counts=decision_counts)
            )
        for goal_key in goal_keys[:8]:
            counts = _count_signal(trials, f"goal_{goal_key}")
            if counts:
                distributions.append(
                    Distribution(
                        key=f"goal_{goal_key}",
                        label=f"Goal {goal_key}",
                        counts=counts,
                    )
                )
        passed = outcome_counts.get("passed", 0)
        total = sum(outcome_counts.values()) or len(trials) or 1
        primary = (
            f"Pass rate {100.0 * passed / total:.0f}% · {_top_mix_summary(outcome_counts)}"
            if outcome_counts
            else (
                f"Decisions: {_top_mix_summary(decision_counts)}"
                if decision_counts
                else "no OS-app outcomes recorded"
            )
        )
        metrics.append(
            Metric(
                key="pass_rate",
                label="Pass rate",
                value=round(100.0 * passed / total, 1) if outcome_counts else None,
                unit="%",
            )
        )
        return OutcomeLens(
            kind="os-app",
            primary_summary=primary,
            distributions=distributions,
            metrics=metrics,
            source=source if distributions else "none",
        )

    return OutcomeLens(
        kind="unknown",
        primary_summary="app type unknown — ledger only",
        source="none",
    )


def _reward_stats(trials: list[TrialSummary]) -> dict[str, Any]:
    rewards = [trial.reward for trial in trials if trial.reward is not None]
    histogram: Counter[str] = Counter()
    for trial in trials:
        if trial.error:
            histogram["error"] += 1
        elif trial.reward is None:
            histogram["missing"] += 1
        elif trial.reward >= 1:
            histogram["pass"] += 1
        elif trial.reward <= 0:
            histogram["fail"] += 1
        else:
            histogram["partial"] += 1
    return {
        "count": len(rewards),
        "mean": (sum(rewards) / len(rewards)) if rewards else None,
        "histogram": dict(histogram),
    }


def _grouped_distributions(
    trials: list[TrialSummary],
    *,
    group_by: list[str],
    app_type: str,
) -> dict[str, dict[str, dict[str, dict[str, int]]]]:
    if not group_by:
        return {}
    signal_keys: list[str]
    if app_type == "survey":
        signal_keys = [f"answer_{qid}" for qid in _survey_answer_keys(trials)]
    elif app_type == "web":
        signal_keys = ["decision_label", "outcome_status"]
    elif app_type == "os-app":
        signal_keys = ["outcome_status", "decision_outcome", "decision_label"]
    else:
        signal_keys = ["outcome_status", "conversation_path"]

    nested: dict[str, dict[str, dict[str, Counter[str]]]] = {
        key: defaultdict(lambda: defaultdict(Counter)) for key in group_by
    }
    for trial in trials:
        for group_key in group_by:
            group_value = trial.group_values.get(group_key, "unknown")
            for signal_key in signal_keys:
                value = trial.signals.get(signal_key)
                if value is None and signal_key.startswith("answer_"):
                    value = trial.survey_answers.get(signal_key[len("answer_") :])
                if value is None:
                    continue
                dist_key = (
                    signal_key[len("answer_") :]
                    if signal_key.startswith("answer_")
                    else signal_key
                )
                nested[group_key][group_value][dist_key][str(value)] += 1
    out: dict[str, dict[str, dict[str, dict[str, int]]]] = {}
    for group_key, by_group in nested.items():
        out[group_key] = {}
        for group_value, by_signal in sorted(by_group.items()):
            out[group_key][group_value] = {
                signal: dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))
                for signal, counter in sorted(by_signal.items())
            }
    return out


def collect_job_results(
    job_dir: Path,
    *,
    group_by: list[str] | None = None,
) -> JobResultsReport:
    """Build a deterministic ``MatraixJobResults.v1`` report for one job."""
    job_dir = job_dir.resolve()
    group_keys = [key.strip() for key in (group_by or []) if key.strip()]
    notes: list[str] = [
        "Built from jobs/<job>/ on disk — no additional model calls.",
        "Ledger uses result.json; lens prefers verifier/structured_output.json.",
    ]
    job_result = _read_json(job_dir / "result.json") or {}
    stats = job_result.get("stats") if isinstance(job_result.get("stats"), dict) else {}

    trials: list[TrialSummary] = []
    for trial_dir in _list_trial_dirs(job_dir):
        summary = _summarize_trial(
            trial_dir, job_dir=job_dir, group_by=group_keys, notes=notes
        )
        if summary is not None:
            trials.append(summary)

    app_type = _detect_app_type(job_dir, trials)
    if app_type not in _APP_TYPES:
        app_type = "unknown"

    completed = _as_int(stats.get("n_completed_trials"))
    errored = _as_int(stats.get("n_errored_trials"))
    if completed is None:
        completed = sum(1 for trial in trials if trial.error is None)
    if errored is None:
        errored = sum(1 for trial in trials if trial.error)

    ledger = JobLedger(
        coverage={
            "trials": len(trials),
            "completed": completed,
            "errored": errored,
            "running": _as_int(stats.get("n_running_trials")),
            "pending": _as_int(stats.get("n_pending_trials")),
        },
        usage=_usage_from_mapping(stats),
        rewards=_reward_stats(trials),
        trials=trials,
    )
    lens = build_outcome_lens(app_type, trials)
    if group_keys and not any(trial.group_values for trial in trials):
        notes.append(
            "group-by keys were requested but no matching persona fields were found."
        )

    return JobResultsReport(
        schema_version=SCHEMA_VERSION,
        job_name=job_dir.name,
        job_dir=str(job_dir),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        deterministic=True,
        app_type=app_type,
        ledger=ledger,
        lens=lens,
        group_by=group_keys,
        grouped_distributions=_grouped_distributions(
            trials, group_by=group_keys, app_type=app_type
        ),
        notes=notes,
    )


def _format_token_line(usage: TrialUsage) -> str:
    bits: list[str] = []
    if usage.n_input_tokens is not None:
        bits.append(f"{usage.n_input_tokens:,} in")
    if usage.n_output_tokens is not None:
        bits.append(f"{usage.n_output_tokens:,} out")
    if usage.n_cache_tokens is not None and usage.n_cache_tokens > 0:
        bits.append(f"{usage.n_cache_tokens:,} cache")
    return " · ".join(bits) if bits else "(not recorded)"


def format_text_report(report: JobResultsReport) -> str:
    ledger = report.ledger
    lens = report.lens
    coverage = ledger.coverage if ledger else {}
    health_bits = [
        f"{coverage.get('trials') or 0} trials",
        f"{coverage.get('completed') or 0} ok",
        f"{coverage.get('errored') or 0} error",
    ]
    if report.usage.cost_usd is not None:
        health_bits.append(f"cost ${report.usage.cost_usd:g}")
    lines: list[str] = [
        f"Job: {report.job_name}",
        f"App: {report.app_type}",
        f"Path: {report.job_dir}",
        f"Health: {' · '.join(health_bits)}",
        f"Primary: {lens.primary_summary if lens else 'n/a'}",
        f"Usage: {_format_token_line(report.usage)}",
    ]

    if lens and lens.distributions:
        lines.append("")
        lines.append("Distributions")
        for dist in lens.distributions[:12]:
            total = sum(dist.counts.values())
            top = ", ".join(f"{value}={count}" for value, count in list(dist.counts.items())[:5])
            lines.append(f"  {dist.label} (n={total}): {top}")

    if lens and lens.metrics:
        lines.append("")
        lines.append("Metrics")
        for metric in lens.metrics:
            unit = f" {metric.unit}" if metric.unit else ""
            lines.append(f"  {metric.label}: {metric.value}{unit}")

    if report.grouped_distributions:
        lines.append("")
        lines.append("Grouped distributions")
        for key, by_group in report.grouped_distributions.items():
            lines.append(f"  by {key}:")
            for group_value, by_signal in by_group.items():
                lines.append(f"    {group_value}:")
                for signal, counts in list(by_signal.items())[:8]:
                    top = ", ".join(
                        f"{value}={count}" for value, count in list(counts.items())[:4]
                    )
                    lines.append(f"      {signal}: {top}")

    lines.append("")
    lines.append("Trials")
    for trial in report.trials:
        persona = trial.persona_name or trial.persona_id or "-"
        reward = "-" if trial.reward is None else f"{trial.reward:g}"
        status = "error" if trial.error else "ok"
        cost = f"${trial.usage.cost_usd:g}" if trial.usage.cost_usd is not None else "-"
        artifact = trial.artifact_paths[0] if trial.artifact_paths else "-"
        lines.append(
            f"  {trial.trial_name} · {persona} · reward={reward} · "
            f"{status} · cost={cost} · {artifact}"
        )

    lines.append("")
    lines.append("Notes")
    for note in report.notes:
        lines.append(f"  - {note}")
    if lens:
        lines.append(f"  - lens source: {lens.source}")
    lines.append(f"  - schema: {report.schema_version}")
    return "\n".join(lines) + "\n"


def format_json_report(report: JobResultsReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n"


def format_csv_report(report: JobResultsReport) -> str:
    """One row per trial; signals expand as columns."""
    signal_keys = sorted({key for trial in report.trials for key in trial.signals})
    # Prefer answer_* aliases for survey CSV readability.
    answer_keys = sorted(
        {qid for trial in report.trials for qid in trial.survey_answers}
    )
    group_keys = report.group_by
    fieldnames = [
        "job_name",
        "app_type",
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
        *[
            f"signal_{key}"
            for key in signal_keys
            if not key.startswith("answer_") or key[len("answer_") :] not in answer_keys
        ],
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for trial in report.trials:
        row: dict[str, Any] = {
            "job_name": report.job_name,
            "app_type": report.app_type,
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
            value = trial.survey_answers.get(qid, trial.signals.get(f"answer_{qid}", ""))
            row[f"answer_{qid}"] = "" if value is None else value
        for key in signal_keys:
            if key.startswith("answer_") and key[len("answer_") :] in answer_keys:
                continue
            value = trial.signals.get(key, "")
            row[f"signal_{key}"] = "" if value is None else value
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
