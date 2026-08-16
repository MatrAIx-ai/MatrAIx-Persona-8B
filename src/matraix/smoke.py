"""Zero-cost host Survey smoke for ``matraix smoke``.

Exercises the same ``json_survey`` / ``InprocessSurveyEvalRunner`` path as
production with a deterministic fake JSON client — no Docker, no provider calls.
"""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SMOKE_PERSONA = (
    "persona/datasets/matraix-persona-dev-sample/persona_0042.yaml"
)


@dataclass
class SmokeReport:
    ok: bool
    task_path: str
    app_type: str = "survey"
    trial_profile: str = "json_survey"
    agent: str = "persona-json-survey"
    mode: str = "fake"
    cost_usd: float = 0.0
    n_personas: int = 0
    logical_calls: int = 0
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    artifact_dirs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "taskPath": self.task_path,
            "appType": self.app_type,
            "trialProfile": self.trial_profile,
            "agent": self.agent,
            "mode": self.mode,
            "costUsd": self.cost_usd,
            "nPersonas": self.n_personas,
            "logicalCalls": self.logical_calls,
            "errors": list(self.errors),
            "notes": list(self.notes),
            "artifactDirs": list(self.artifact_dirs),
        }


def ensure_launch_imports(repo_root: Path) -> None:
    """Inject the same PYTHONPATH entries ``matraix run`` uses."""
    from matraix.launch_env import required_pythonpath_entries

    for entry in reversed(required_pythonpath_entries(repo_root)):
        if entry not in sys.path:
            sys.path.insert(0, entry)


def resolve_task_dir(task: str | Path, *, repo_root: Path) -> Path:
    raw = Path(task).expanduser()
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append((Path.cwd() / raw).resolve())
        candidates.append((repo_root / raw).resolve())
    for path in candidates:
        if path.is_dir() and (path / "task.toml").is_file():
            return path
        if path.is_file() and path.name == "task.toml":
            return path.parent
    raise FileNotFoundError(f"survey task directory not found: {task}")


def _task_relpath(task_dir: Path, *, repo_root: Path) -> str:
    try:
        return str(task_dir.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(task_dir.resolve())


def _read_task_type(task_dir: Path) -> str | None:
    import tomllib

    toml_path = task_dir / "task.toml"
    if not toml_path.is_file():
        return None
    try:
        payload = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and metadata.get("type"):
        return str(metadata["type"]).strip().lower()
    task = payload.get("task")
    if isinstance(task, dict) and task.get("type"):
        return str(task["type"]).strip().lower()
    return None


def _is_survey_task(task_dir: Path) -> bool:
    task_type = _read_task_type(task_dir)
    if task_type in {"survey", "json_survey"}:
        return True
    return (task_dir / "input" / "questionnaire.yaml").is_file() or (
        task_dir / "content" / "questionnaire.yaml"
    ).is_file()


def _default_answer_value(question: Any) -> Any:
    from playground.inprocess.survey_eval import _default_value

    return _default_value(question)


class DeterministicSurveyJsonClient:
    """Schema-valid synthetic answers — not persona-faithful."""

    def __init__(self, instrument: Any) -> None:
        self.instrument = instrument
        self.calls = 0

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        del system, user
        self.calls += 1
        answers: list[dict[str, Any]] = []
        for question in self.instrument.questions:
            entry: dict[str, Any] = {
                "questionId": question.id,
                "value": _default_answer_value(question),
            }
            if question.resolves_ask_rationale(self.instrument):
                entry["rationale"] = (
                    "Synthetic smoke rationale — not a real persona judgment."
                )
            if question.resolves_ask_confidence(self.instrument):
                entry["confidence"] = 0.5
            answers.append(entry)
        return {"answers": answers}


def _persona_paths(
    *,
    repo_root: Path,
    persona: str | None,
    n_personas: int,
) -> list[Path]:
    if persona:
        path = Path(persona).expanduser()
        if not path.is_absolute():
            candidates = [(Path.cwd() / path).resolve(), (repo_root / path).resolve()]
        else:
            candidates = [path]
        for candidate in candidates:
            if candidate.is_file():
                return [candidate]
        raise FileNotFoundError(f"persona file not found: {persona}")

    sample_dir = repo_root / "persona" / "datasets" / "matraix-persona-dev-sample"
    default = repo_root / DEFAULT_SMOKE_PERSONA
    if n_personas <= 1:
        if not default.is_file():
            raise FileNotFoundError(f"default smoke persona missing: {default}")
        return [default]

    if not sample_dir.is_dir():
        raise FileNotFoundError(f"persona sample dir missing: {sample_dir}")
    ranked = sorted(sample_dir.glob("persona_*.yaml"))
    # Prefer 0042 first when present.
    preferred = sample_dir / "persona_0042.yaml"
    ordered: list[Path] = []
    if preferred.is_file():
        ordered.append(preferred)
    for path in ranked:
        if path not in ordered:
            ordered.append(path)
    if len(ordered) < n_personas:
        raise ValueError(
            f"requested --personas {n_personas} but only {len(ordered)} available "
            f"under {sample_dir}"
        )
    return ordered[:n_personas]


def _eval_persona(persona_yaml: Path) -> Any:
    from playground.types import Persona as EvalPersona

    try:
        import yaml

        payload = yaml.safe_load(persona_yaml.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    persona_id = str(
        payload.get("persona_id")
        or payload.get("id")
        or persona_yaml.stem.replace("persona_", "")
    )
    name = str(payload.get("display_name") or payload.get("name") or persona_id)
    return EvalPersona(id=persona_id, name=name, source=str(payload.get("source") or ""))


def _check_envelope(payload: dict[str, Any], *, instrument: Any) -> list[str]:
    errors: list[str] = []
    answers = payload.get("answers")
    if not isinstance(answers, list) or not answers:
        errors.append("survey_result.answers must be a non-empty list")
        return errors
    trajectory = payload.get("trajectory")
    if not isinstance(trajectory, list) or not trajectory:
        errors.append("survey_result.trajectory must be a non-empty list")
    answered = {
        str(entry.get("questionId") or entry.get("question_id") or "")
        for entry in answers
        if isinstance(entry, dict)
    }
    for question in instrument.questions:
        if question.required and question.id not in answered:
            errors.append(f"missing required answer for question {question.id}")
    return errors


def _survey_result_payload(result: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "instrument": {
            "id": result.instrument.id,
            "title": result.instrument.title,
        },
        "answers": [answer.to_dict() for answer in result.answers],
        "trajectory": [event.to_dict() for event in result.trajectory],
        "smoke": {
            "mode": "fake",
            "costUsd": 0.0,
            "note": "Synthetic answers from matraix smoke — not persona-faithful.",
        },
    }
    if getattr(result, "usage", None):
        payload["usage"] = dict(result.usage)
    return payload


def run_survey_smoke(
    task: str | Path,
    *,
    repo_root: Path,
    personas: int = 1,
    persona: str | None = None,
    keep_artifacts: bool = False,
) -> SmokeReport:
    """Run the host Survey smoke for one task directory."""
    ensure_launch_imports(repo_root)
    notes = [
        "Host Survey smoke — no Docker, no provider calls.",
        "Answers are synthetic (fake client), not persona-faithful.",
    ]
    errors: list[str] = []
    try:
        task_dir = resolve_task_dir(task, repo_root=repo_root)
    except FileNotFoundError as exc:
        return SmokeReport(
            ok=False,
            task_path=str(task),
            errors=[str(exc)],
            notes=notes,
        )

    task_rel = _task_relpath(task_dir, repo_root=repo_root)
    if not _is_survey_task(task_dir):
        return SmokeReport(
            ok=False,
            task_path=task_rel,
            app_type="unknown",
            trial_profile="",
            agent="",
            errors=[
                "matraix smoke currently supports Survey tasks only "
                "(host json_survey). For Docker/Harbor stack smoke use: "
                "uv run matraix run -c configs/jobs/example-job-recipe/harbor-smoke-local.yaml"
            ],
            notes=notes,
        )

    from backend.service.survey_types import SurveyEvalConfig
    from playground.inprocess.survey_eval import InprocessSurveyEvalRunner
    from playground.survey_task_content import load_survey_task_content_for_task_path
    from playground.user_sim.prompt import render_persona_block

    content = load_survey_task_content_for_task_path(task_rel, repo_root=repo_root)
    instrument = content.instrument
    if instrument is None:
        return SmokeReport(
            ok=False,
            task_path=task_rel,
            errors=["task is missing a loadable input/questionnaire.yaml"],
            notes=notes,
        )

    if not content.output_schema_markdown.strip():
        errors.append("could not derive answer envelope / output schema markdown")

    try:
        persona_paths = _persona_paths(
            repo_root=repo_root, persona=persona, n_personas=max(1, personas)
        )
    except (FileNotFoundError, ValueError) as exc:
        return SmokeReport(
            ok=False,
            task_path=task_rel,
            errors=[str(exc)],
            notes=notes,
        )

    for persona_yaml in persona_paths:
        eval_persona = _eval_persona(persona_yaml)
        try:
            block = render_persona_block(
                eval_persona, persona_yaml_path=str(persona_yaml)
            ).strip()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"persona render failed for {persona_yaml.name}: {exc}")
            continue
        if not block:
            errors.append(f"empty persona render for {persona_yaml.name}")

    if errors:
        return SmokeReport(
            ok=False,
            task_path=task_rel,
            errors=errors,
            notes=notes,
            n_personas=len(persona_paths),
        )

    client = DeterministicSurveyJsonClient(instrument)
    runner = InprocessSurveyEvalRunner()
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    artifact_dirs: list[str] = []
    logical_calls = 0

    base_tmp = Path(tempfile.mkdtemp(prefix="matraix-smoke-"))
    notes.append(f"Artifacts under {base_tmp}" if keep_artifacts else f"Temp dir {base_tmp}")

    for index, persona_yaml in enumerate(persona_paths):
        trial_dir = base_tmp / f"persona_{index:02d}_{persona_yaml.stem}"
        out_dir = trial_dir / "artifacts" / "app" / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        eval_persona = _eval_persona(persona_yaml)
        try:
            result = runner(
                eval_persona,
                instrument,
                config=SurveyEvalConfig(persona_model="smoke/fake"),
                created_at=created_at,
                persona_yaml_path=str(persona_yaml),
                job_dir=None,
                client=client,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"runner failed for {persona_yaml.name}: {exc}")
            continue
        payload = _survey_result_payload(result)
        envelope_errors = _check_envelope(payload, instrument=instrument)
        errors.extend(
            f"{persona_yaml.name}: {message}" for message in envelope_errors
        )
        out_path = out_dir / "survey_result.json"
        out_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        artifact_dirs.append(str(trial_dir))
        logical_calls += 1

    if not keep_artifacts and not errors:
        # Leave artifacts when debugging failures; otherwise clean up.
        import shutil

        shutil.rmtree(base_tmp, ignore_errors=True)
        artifact_dirs = []
        notes.append("Temp artifacts removed after successful smoke.")

    notes.append(
        f"Resolved auto profile: json_survey / persona-json-survey · "
        f"logical calls={logical_calls} · cost $0"
    )
    return SmokeReport(
        ok=not errors and logical_calls == len(persona_paths),
        task_path=task_rel,
        n_personas=len(persona_paths),
        logical_calls=logical_calls,
        errors=errors,
        notes=notes,
        artifact_dirs=artifact_dirs,
    )


def format_smoke_report(report: SmokeReport) -> str:
    status = "ok" if report.ok else "FAILED"
    lines = [
        f"Smoke: {status}",
        f"Task: {report.task_path}",
        f"App: {report.app_type}",
        f"Runtime: host {report.trial_profile} / {report.agent}",
        f"Mode: {report.mode} · personas {report.n_personas} · "
        f"calls {report.logical_calls} · cost ${report.cost_usd:g}",
    ]
    if report.artifact_dirs:
        lines.append("Artifacts:")
        for path in report.artifact_dirs:
            lines.append(f"  {path}")
    if report.errors:
        lines.append("Errors:")
        for error in report.errors:
            lines.append(f"  - {error}")
    lines.append("Notes:")
    for note in report.notes:
        lines.append(f"  - {note}")
    return "\n".join(lines) + "\n"
