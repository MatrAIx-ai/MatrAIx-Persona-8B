"""Map Harbor ``jobs/<job>/<trial>/`` artifacts into Playground debrief shapes."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from backend.service import run_store
from backend.service.application_types import normalize_metadata_type
from backend.service.import_paths import ensure_harbor_source_imports
from backend.service.survey_types import build_survey_eval_result_from_artifacts
from backend.service.survey_types import survey_result_view
from backend.service.survey_types import SurveyEvalConfig, SurveyInstrument, SurveyQuestion
from matraix.persona_dimension_catalog import normalize_persona_language
from playground.types import Persona, PlaygroundConfig

if TYPE_CHECKING:
    from backend.service.survey_types import SurveyMetrics
    from backend.service.web_types import WebEvalTask


_DEBRIEF_PERSONA_COPY: dict[str, dict[str, str]] = {
    "en": {"who": "Who you are", "profile": "Profile", "guidance": "Behavioral guidance", "you_are": "You are ", "you_are_suffix": "."},
    "ko": {"who": "당신은 누구인가요", "profile": "개인 소개", "guidance": "행동 지침", "you_are": "당신은 ", "you_are_suffix": "입니다."},
    "zh": {"who": "你是谁", "profile": "个人简介", "guidance": "行为准则", "you_are": "你是 ", "you_are_suffix": "。"},
    "zh-Hant": {"who": "你是誰", "profile": "個人簡介", "guidance": "行為準則", "you_are": "你是 ", "you_are_suffix": "。"},
    "ja": {"who": "あなたについて", "profile": "プロフィール", "guidance": "行動指針", "you_are": "あなたは ", "you_are_suffix": "です。"},
    "pt": {"who": "Quem você é", "profile": "Perfil", "guidance": "Diretrizes de comportamento", "you_are": "Você é ", "you_are_suffix": "."},
    "es": {"who": "Quién eres", "profile": "Resumen personal", "guidance": "Pautas de comportamiento", "you_are": "Eres ", "you_are_suffix": "."},
}


def _debrief_persona_copy(language: str | None) -> dict[str, str]:
    normalized = normalize_persona_language(language) or "en"
    return _DEBRIEF_PERSONA_COPY.get(normalized, _DEBRIEF_PERSONA_COPY["en"])


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("{} must contain a JSON object".format(path.name))
    return data


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


def find_trial_output_dir(trial_dir: Path) -> Path | None:
    """Return the directory holding task submission artifacts."""
    matches = sorted(trial_dir.glob("artifacts/app/output"))
    if not matches:
        matches = sorted(trial_dir.rglob("artifacts/app/output"))
    if matches:
        return matches[0]

    artifacts_root = trial_dir / "artifacts"
    if not artifacts_root.is_dir():
        return None

    for name in (
        "decision.json",
        "book_interest.json",
        "quote_choice.json",
        "laptop_choice.json",
        "plan_choice.json",
    ):
        for path in sorted(artifacts_root.rglob(name)):
            return path.parent

    tmp_root = artifacts_root / "tmp"
    if tmp_root.is_dir():
        for path in sorted(tmp_root.iterdir()):
            if path.is_dir() and any(path.glob("*.json")):
                return path
    return None


def find_trial_logs_dir(trial_dir: Path) -> Path | None:
    logs = trial_dir / "agent"
    return logs if logs.is_dir() else None


def _persona_path_from_trial(trial_dir: Path, repo_root: Path) -> str | None:
    result_path = trial_dir / "result.json"
    if result_path.is_file():
        try:
            payload = _read_json(result_path)
        except Exception:  # noqa: BLE001
            payload = {}
        config = payload.get("config")
        if isinstance(config, dict):
            agent = config.get("agent")
            if isinstance(agent, dict):
                kwargs = agent.get("kwargs")
                if isinstance(kwargs, dict):
                    rel = kwargs.get("persona_path")
                    if isinstance(rel, str) and rel.strip():
                        return rel.strip()
    config_path = trial_dir / "config.json"
    if config_path.is_file():
        try:
            payload = _read_json(config_path)
        except Exception:  # noqa: BLE001
            payload = {}
        agent = payload.get("agent")
        if isinstance(agent, dict):
            kwargs = agent.get("kwargs")
            if isinstance(kwargs, dict):
                rel = kwargs.get("persona_path")
                if isinstance(rel, str) and rel.strip():
                    return rel.strip()
    return None


def _persona_from_catalog_stem(stem: str) -> Persona | None:
    """Lookup a curated catalog persona by stem/id. Avoid on path-backed loads."""
    try:
        from playground.persona_catalog import get_persona

        return get_persona(stem)
    except KeyError:
        return None


def _load_playground_persona(repo_root: Path, persona_rel: str | None) -> Persona:
    if persona_rel:
        abs_path = (repo_root / persona_rel).resolve()
        stem = abs_path.stem if abs_path.name else Path(persona_rel).stem
        # Path-backed personas (wiki cohorts, trial snapshots): load that file
        # only. Never scan the curated catalog first — get_persona() reloads
        # every curated YAML and dominated trail-report open latency (~3s).
        if abs_path.is_file():
            try:
                from matraix.agents.persona.loader import load_persona as load_harbor_persona

                prev = os.getcwd()
                try:
                    os.chdir(repo_root)
                    loaded = load_harbor_persona(persona_rel)
                finally:
                    os.chdir(prev)
            except Exception:  # noqa: BLE001
                loaded = None
            if loaded is not None:
                raw = loaded.data
                context = loaded.system_prompt or loaded.summary or ""
                if not context and loaded.has_dimensions_schema():
                    context = "Persona {}".format(loaded.persona_id or stem)
                return Persona(
                    id=str(loaded.persona_id or stem),
                    name=str(loaded.display_name or loaded.persona_id or stem),
                    source=str(raw.get("source") or ""),
                    context=context,
                )
            try:
                raw = yaml.safe_load(abs_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                raw = None
            if isinstance(raw, dict):
                pid = str(raw.get("persona_id") or raw.get("id") or stem)
                return Persona(
                    id=pid,
                    name=str(raw.get("display_name") or raw.get("name") or pid),
                    source=str(raw.get("source") or ""),
                    context=str(raw.get("system_prompt") or raw.get("summary") or pid),
                )
        catalog = _persona_from_catalog_stem(stem)
        if catalog is not None:
            return catalog
    return Persona(id="unknown", name="Persona", source="", context="")

def _task_path_from_trial(trial_dir: Path) -> str | None:
    config_path = trial_dir / "config.json"
    if not config_path.is_file():
        return None
    try:
        payload = _read_json(config_path)
    except Exception:  # noqa: BLE001
        return None
    task = payload.get("task")
    if not isinstance(task, dict):
        return None
    path = task.get("path")
    if isinstance(path, str) and path.strip():
        return path.strip().replace("\\", "/")
    return None


def _task_title_from_trial(repo_root: Path, trial_dir: Path) -> str | None:
    """UI title for the trial's task, derived from ``[task].name`` in task.toml."""
    from backend.service.application_task_metadata import title_from_harbor_task_name

    task_rel = _task_path_from_trial(trial_dir)
    if not task_rel:
        return None
    toml_path = repo_root / task_rel / "task.toml"
    if not toml_path.is_file():
        return None
    try:
        import tomllib

        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    task_block = data.get("task")
    name = task_block.get("name") if isinstance(task_block, dict) else None
    if isinstance(name, str) and name.strip():
        return title_from_harbor_task_name(name.strip()) or None
    return None


def _chat_application_id_from_trial(repo_root: Path, trial_dir: Path) -> str:
    """The task-declared chat applicationId (``input/chatbot.yaml``), or ""."""
    task_rel = _task_path_from_trial(trial_dir)
    if not task_rel:
        return ""
    ensure_harbor_source_imports()
    try:
        from playground.chatbot_task_config import load_chatbot_task_config_for_task_path

        cfg = load_chatbot_task_config_for_task_path(task_rel, repo_root=repo_root)
    except Exception:  # noqa: BLE001
        return ""
    if cfg is None:
        return ""
    return cfg.runtime_defaults.application_id or cfg.application_id or ""


def _application_type_from_task_toml(repo_root: Path, task_rel: str) -> str | None:
    toml_path = repo_root / task_rel / "task.toml"
    if not toml_path.is_file():
        return None
    try:
        import tomllib

        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return None
    app_type = metadata.get("type")
    if isinstance(app_type, str) and app_type.strip():
        mapped = normalize_metadata_type(app_type)
        if mapped in {"web", "survey", "chatbot", "os-app"}:
            return mapped
    return None


def _resolve_application_type(
    repo_root: Path,
    trial_dir: Path,
    output_dir: Path,
) -> str:
    from_trial = _application_type_from_trial(repo_root, trial_dir)
    if from_trial:
        return from_trial
    return _detect_application_type(output_dir)


def _application_type_from_trial(repo_root: Path, trial_dir: Path) -> str | None:
    task_path = _task_path_from_trial(trial_dir)
    if not task_path:
        return None
    return _application_type_from_task_toml(repo_root, task_path)


def _read_trial_failure_message(trial_dir: Path) -> str | None:
    result_path = trial_dir / "result.json"
    if result_path.is_file():
        try:
            trial_error = _trial_result_error(_read_json(result_path))
            if trial_error:
                return trial_error
        except Exception:  # noqa: BLE001
            pass
    exception_path = trial_dir / "exception.txt"
    if exception_path.is_file():
        raw = exception_path.read_text(encoding="utf-8", errors="replace").strip()
        if not raw:
            return None
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        for line in reversed(lines):
            if any(token in line for token in ("Error", "Exception", "Timeout", "Failed")):
                return line
        return lines[-1]
    return None


def _trial_created_at(trial_dir: Path) -> str:
    created_at = _utc_now()
    result_path = trial_dir / "result.json"
    if result_path.is_file():
        try:
            finished = _read_json(result_path).get("finished_at")
            if isinstance(finished, str) and finished:
                created_at = finished
        except Exception:  # noqa: BLE001
            pass
    return created_at


def _map_failed_trial_debrief(
    *,
    trial_dir: Path,
    persona: Persona,
    created_at: str,
    job_name: str,
    trial_name: str,
    trial_error: str,
    app_type: str,
    persona_rel: str | None,
) -> dict[str, Any]:
    debrief: dict[str, Any] = {
        "id": "harbor-trial",
        "applicationType": app_type,
        "createdAt": created_at,
        "persona": run_store.persona_summary(persona),
        "error": trial_error,
        "status": "error",
        "harbor": {
            "jobName": job_name,
            "trialName": trial_name,
            "outputDir": None,
            "personaPath": persona_rel,
            "failed": True,
        },
    }
    if app_type == "os-app":
        ensure_harbor_source_imports()
        logs_dir = find_trial_logs_dir(trial_dir)
        trace: dict[str, Any] | None = None
        if logs_dir is not None:
            trajectory_path = logs_dir / "trajectory.json"
            if trajectory_path.is_file():
                try:
                    from playground.harbor.web_eval import _trace_from_trajectory

                    mapped = _trace_from_trajectory(_read_json(trajectory_path))
                    trace = mapped.to_dict()
                except Exception:  # noqa: BLE001
                    trace = {"events": [], "raw": {}}
        if trace is not None:
            from backend.service.harbor_web_trace import attach_harbor_trace_screenshot_urls

            trace = attach_harbor_trace_screenshot_urls(
                trace,
                job_name=job_name,
                trial_name=trial_name,
            )
            debrief["osAppTrace"] = trace
            debrief["trace"] = trace
        debrief["osAppResult"] = {
            "success": False,
            "score": 0.0,
            "artifactName": None,
            "artifact": None,
            "createdAt": created_at,
        }
    verifier = _verifier_summary(trial_dir)
    if verifier is not None:
        debrief["verifier"] = verifier
    return debrief


def _detect_application_type(output_dir: Path) -> str:
    if (output_dir / "transcript.json").is_file():
        return "chatbot"
    if (output_dir / "survey_result.json").is_file():
        return "survey"
    if (output_dir / "survey_responses.json").is_file():
        return "survey"
    for path in output_dir.glob("*.json"):
        name = path.name.lower()
        if name in {"decision.json", "book_interest.json"}:
            return "os-app"
        if "notification" in name and "preference" in name:
            return "os-app"
        if "web" in name or "ecommerce" in name or "interaction" in name:
            return "web"
    return "unknown"


def _instrument_from_answer_guess(payload: dict[str, Any]) -> SurveyInstrument:
    """Last-resort instrument when task registry and instrument id are unavailable."""
    instrument = payload.get("instrument")
    answers = payload.get("answers")
    if isinstance(answers, list) and answers:
        questions = []
        for index, entry in enumerate(answers):
            if not isinstance(entry, dict):
                continue
            qid = str(entry.get("questionId") or entry.get("question_id") or "q{}".format(index))
            questions.append(
                SurveyQuestion(
                    id=qid,
                    prompt=str(entry.get("prompt") or entry.get("question") or qid),
                    type=str(entry.get("type") or "free_text"),
                )
            )
        if questions:
            title = ""
            if isinstance(instrument, dict):
                title = str(instrument.get("title") or instrument.get("id") or "Survey")
            return SurveyInstrument(
                id=str((instrument or {}).get("id") if isinstance(instrument, dict) else "harbor_survey"),
                title=title or "Harbor survey",
                questions=questions,
            )
    return SurveyInstrument(
        id="harbor_survey",
        title="Harbor survey",
        questions=[SurveyQuestion(id="response", prompt="Survey response", type="free_text")],
    )


def _resolve_survey_instrument(
    *,
    repo_root: Path,
    trial_dir: Path,
    payload: dict[str, Any],
) -> SurveyInstrument:
    """Prefer the registered instrument (with question types) over answer-shape guesses."""
    instrument = payload.get("instrument")
    if isinstance(instrument, dict) and instrument.get("questions"):
        return SurveyInstrument.from_dict(instrument)

    instrument_id: str | None = None
    if isinstance(instrument, dict):
        raw_id = str(instrument.get("id") or "").strip()
        instrument_id = raw_id or None
    if not instrument_id:
        task_rel = _task_path_from_trial(trial_dir)
        if task_rel:
            from backend.service.survey_task_registry import survey_questionnaire_id_for_task_path

            instrument_id = survey_questionnaire_id_for_task_path(task_rel)
    if instrument_id:
        from backend.service.survey_questionnaire_catalog import get_survey_questionnaire

        try:
            return get_survey_questionnaire(instrument_id, repo_root=repo_root)
        except (KeyError, FileNotFoundError, ValueError):
            pass
    return _instrument_from_answer_guess(payload)


def _survey_metrics(
    instrument: SurveyInstrument,
    answers: list,
) -> "SurveyMetrics":
    from backend.service.survey_types import SurveyMetrics

    question_by_id = {question.id: question for question in instrument.questions}
    likert_values: list[float] = []
    for answer in answers:
        question_id = getattr(answer, "question_id", None) or (
            answer.get("questionId") if isinstance(answer, dict) else None
        )
        question = question_by_id.get(str(question_id or ""))
        if question is None or question.type != "likert":
            continue
        raw_value = getattr(answer, "value", None) if not isinstance(answer, dict) else answer.get("value")
        try:
            likert_values.append(float(raw_value))
        except (TypeError, ValueError):
            continue
    mean = sum(likert_values) / len(likert_values) if likert_values else None
    return SurveyMetrics(
        num_questions=len(instrument.questions),
        num_answered=len(answers),
        mean_likert=mean,
    )


def _read_prompts_event(trial_dir: Path) -> dict[str, str] | None:
    """First ``prompts`` event from ``events.jsonl`` (authoritative runtime prompt bundle)."""
    events_path = trial_dir / "events.jsonl"
    if not events_path.is_file():
        return None
    for line in events_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "prompts":
            continue
        raw = event.get("prompts")
        if not isinstance(raw, dict):
            continue
        prompts = {
            str(key): str(value).strip()
            for key, value in raw.items()
            if isinstance(key, str) and isinstance(value, str) and str(value).strip()
        }
        return prompts or None
    return None


def _read_chat_done_event(trial_dir: Path) -> dict[str, Any] | None:
    """Last ``done`` event from ``events.jsonl`` (live stream fallback when artifacts are missing)."""
    events_path = trial_dir / "events.jsonl"
    if not events_path.is_file():
        return None
    done: dict[str, Any] | None = None
    for line in events_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "done":
            result = event.get("result")
            if isinstance(result, dict):
                done = result
    return done


def _read_trial_instruction_markdown(trial_dir: Path, repo_root: Path) -> str | None:
    """Harbor task instruction document for the trial.

    Prefer the live task ``instruction.md`` so debrief rails track authoring
    edits. Fall back to the trial snapshot when the task path is unavailable.
    """
    task_rel = _task_path_from_trial(trial_dir)
    if task_rel:
        task_instruction = repo_root / task_rel / "instruction.md"
        if task_instruction.is_file():
            text = task_instruction.read_text(encoding="utf-8").strip()
            if text:
                return text
    task_instruction = _read_trial_snapshot_doc(trial_dir, "task_instruction.md")
    if task_instruction:
        return task_instruction
    return _read_trial_snapshot_doc(trial_dir, "instruction.md")


def _read_trial_snapshot_doc(trial_dir: Path, filename: str) -> str | None:
    candidate = trial_dir / filename
    if not candidate.is_file():
        return None
    text = candidate.read_text(encoding="utf-8").strip()
    return text or None


_TASK_DOC_DETAIL_KEYS = {
    "task_instruction.md": "instructionMarkdown",
    "context.md": "contextMarkdown",
    "questionnaire.md": "questionnaireMarkdown",
    "output_schema.md": "outputSchemaMarkdown",
}


def _live_task_detail_for_trial(trial_dir: Path, repo_root: Path) -> dict[str, Any] | None:
    """Load live task detail once per debrief (shared by rail doc readers)."""
    task_rel = _task_path_from_trial(trial_dir)
    if not task_rel:
        return None
    from backend.service.task_detail_service import get_task_detail

    try:
        detail = get_task_detail(task_rel, repo_root=repo_root)
    except (FileNotFoundError, ValueError, OSError):
        return None
    return detail if isinstance(detail, dict) else None


def _read_trial_task_doc(
    trial_dir: Path,
    filename: str,
    repo_root: Path,
    *,
    task_detail: dict[str, Any] | None = None,
) -> str | None:
    """Read a task doc for debrief rails.

    For contributor-facing docs (``context.md``, questionnaire, instruction),
    prefer the live task definition via ``get_task_detail`` so Playground
    reflects authoring edits. Trial snapshots are only a fallback.
    """
    key = _TASK_DOC_DETAIL_KEYS.get(filename)
    detail = task_detail
    if detail is None and key:
        detail = _live_task_detail_for_trial(trial_dir, repo_root)
    if isinstance(detail, dict) and key:
        value = str(detail.get(key) or "").strip()
        if value:
            return value
    return _read_trial_snapshot_doc(trial_dir, filename)
def _persona_prompt_abs_path(repo_root: Path, persona_rel: str | None) -> str | None:
    if not persona_rel:
        return None
    abs_path = (repo_root / persona_rel).resolve()
    return str(abs_path) if abs_path.is_file() else None


def _humanize_dimension_key(key: str) -> str:
    return " ".join(part.capitalize() for part in str(key).replace("-", "_").split("_") if part)


def _format_persona_dimensions_from_yaml(
    raw: dict[str, Any], *, persona_language: str | None = None
) -> str:
    language = normalize_persona_language(persona_language) or "en"
    localized = language != "en"
    labels = _debrief_persona_copy(language)
    display_name = str(raw.get("display_name") or "").strip()
    lines: list[str] = []
    if display_name:
        lines.append("{}{}{}".format(labels["you_are"], display_name, labels["you_are_suffix"]))
        lines.append("")
    dims = raw.get("dimensions")
    if isinstance(dims, dict) and dims:
        lines.append("## {}".format(labels["who"]) if localized else "## Who you are")
        lines.append("")
        for key in sorted(dims.keys()):
            value = dims.get(key)
            if value is None or str(value).strip() == "":
                continue
            lines.append("- {}: {}".format(_humanize_dimension_key(key), value))
    elif raw.get("system_prompt"):
        if localized and raw.get("summary"):
            lines.append("## {}".format(labels["profile"]))
            lines.append("")
        if localized:
            lines.append("## {}".format(labels["guidance"]))
            lines.append("")
        lines.append(str(raw.get("system_prompt")).strip())
    elif raw.get("summary"):
        if localized:
            lines.append("## {}".format(labels["profile"]))
            lines.append("")
        lines.append(str(raw.get("summary")).strip())
    return "\n".join(lines).strip()


def _read_persona_yaml_raw(repo_root: Path, persona_rel: str | None) -> dict[str, Any] | None:
    yaml_path = _persona_prompt_abs_path(repo_root, persona_rel)
    if not yaml_path:
        return None
    try:
        raw = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return raw if isinstance(raw, dict) else None


def _recorded_persona_language(trial_dir: Path) -> str | None:
    """Return the effective runtime language recorded for this trial."""
    try:
        meta = _read_json(trial_dir / "persona_meta.json")
    except (OSError, ValueError):
        return None
    raw_language = meta.get("effective_language")
    if not raw_language:
        return None
    return normalize_persona_language(str(raw_language))


def _render_persona_prompt(
    repo_root: Path,
    persona_rel: str | None,
    persona: Persona,
    *,
    persona_language: str | None = None,
) -> str:
    from playground.user_sim.prompt import render_persona_block

    yaml_path = _persona_prompt_abs_path(repo_root, persona_rel)
    raw = _read_persona_yaml_raw(repo_root, persona_rel)
    normalized_language = normalize_persona_language(persona_language)
    if (
        normalized_language is not None
        and normalized_language != "en"
        and raw
        and not any(
            raw.get(key)
            for key in (
                "dimensions",
                "demographics",
                "psychology",
                "communication",
                "preferences",
                "behavior",
            )
        )
    ):
        localized_v0 = _format_persona_dimensions_from_yaml(
            raw, persona_language=persona_language
        )
        if localized_v0 and not _is_thin_persona_prompt(localized_v0, persona=persona):
            return localized_v0
    block = render_persona_block(
        persona,
        persona_yaml_path=yaml_path,
        persona_language=persona_language,
    ).strip()
    if block and not _is_thin_persona_prompt(block, persona=persona):
        return block
    if raw:
        fallback = _format_persona_dimensions_from_yaml(
            raw, persona_language=persona_language
        )
        if fallback and not _is_thin_persona_prompt(fallback, persona=persona):
            return fallback
    return block


def _is_thin_persona_prompt(text: str, *, persona: Persona) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if "You are a simulated user with predefined persona attributes" in stripped:
        return True
    body = stripped
    if body.startswith("## Who you are"):
        pass
    elif body.startswith("## Persona"):
        body = body.split("\n", 1)[1].strip() if "\n" in body else ""
    if not body:
        return True
    placeholders = {
        "Persona {}".format(persona.id or "").strip(),
        "Persona {}".format(persona.name or "").strip(),
        str(persona.name or "").strip(),
        str(persona.id or "").strip(),
    }
    placeholders.discard("")
    if body in placeholders:
        return True
    compact = "\n".join(line.strip() for line in body.splitlines() if line.strip())
    if compact.lower().startswith("persona:") and len(compact.splitlines()) <= 2:
        tail = compact.split(":", 1)[-1].strip().lower()
        if tail in {str(persona.id or "").lower(), str(persona.name or "").lower()}:
            return True
        if tail.startswith("persona-"):
            return True
    return len(body) < 40 and "\n" not in body


def _merge_prompt_dicts(
    base: dict[str, str] | None, overlay: dict[str, str] | None
) -> dict[str, str]:
    merged: dict[str, str] = dict(base or {})
    for key, value in (overlay or {}).items():
        if value.strip():
            merged[key] = value.strip()
    return merged


def _enrich_debrief_prompts(
    debrief: dict[str, Any],
    *,
    trial_dir: Path,
    repo_root: Path,
    persona_rel: str | None,
    persona: Persona,
) -> None:
    """Ensure debrief rails have persona profile + task instruction text."""
    existing = debrief.get("prompts")
    prompts = dict(existing) if isinstance(existing, dict) else {}

    event_prompts = _read_prompts_event(trial_dir)
    done = _read_chat_done_event(trial_dir)
    done_prompts = done.get("prompts") if isinstance(done, dict) else None
    if isinstance(done_prompts, dict):
        done_prompts = {
            str(key): str(value).strip()
            for key, value in done_prompts.items()
            if isinstance(key, str) and isinstance(value, str) and str(value).strip()
        }
    else:
        done_prompts = None

    prompts = _merge_prompt_dicts(prompts, done_prompts)
    prompts = _merge_prompt_dicts(prompts, event_prompts)

    # Prompts already produced by the debrief mapper can be derived from the
    # lightweight Persona object. Runtime event prompts are the authoritative
    # artifact, so only those can suppress a language-aware reconstruction.
    runtime_persona_prompt = ""
    runtime_harbor_prompt = ""
    for runtime_prompts in (event_prompts, done_prompts):
        if not isinstance(runtime_prompts, dict):
            continue
        candidate = str(runtime_prompts.get("personaPrompt") or "").strip()
        if (
            candidate
            and not runtime_persona_prompt
            and not _is_thin_persona_prompt(candidate, persona=persona)
        ):
            runtime_persona_prompt = candidate
        candidate = str(runtime_prompts.get("harborPrompt") or "").strip()
        if (
            candidate
            and not runtime_harbor_prompt
            and not _is_thin_persona_prompt(candidate, persona=persona)
        ):
            runtime_harbor_prompt = candidate

    if runtime_persona_prompt:
        prompts["personaPrompt"] = runtime_persona_prompt
    elif runtime_harbor_prompt:
        prompts["personaPrompt"] = runtime_harbor_prompt
    else:
        # Reconstruct only when runtime artifacts did not carry a usable
        # persona prompt, using the language persisted for this exact trial.
        rendered = _render_persona_prompt(
            repo_root,
            persona_rel,
            persona,
            persona_language=_recorded_persona_language(trial_dir),
        )
        if rendered and not _is_thin_persona_prompt(rendered, persona=persona):
            prompts["personaPrompt"] = rendered

    task_prompt = str(prompts.get("taskPrompt") or "").strip()
    instruction = _read_trial_instruction_markdown(trial_dir, repo_root)
    # One live task-detail fetch for all rails — avoid 3× questionnaire scans.
    task_detail = _live_task_detail_for_trial(trial_dir, repo_root)
    context_markdown = _read_trial_task_doc(
        trial_dir, "context.md", repo_root, task_detail=task_detail
    )
    questionnaire_markdown = _read_trial_task_doc(
        trial_dir, "questionnaire.md", repo_root, task_detail=task_detail
    )
    output_schema_markdown = _read_trial_task_doc(
        trial_dir, "output_schema.md", repo_root, task_detail=task_detail
    )
    if instruction:
        if not task_prompt:
            prompts["taskPrompt"] = instruction
        elif len(task_prompt) < 160 and instruction not in task_prompt:
            prompts["taskPrompt"] = "{}\n\n---\n\n{}".format(instruction, task_prompt)

    if prompts:
        debrief["prompts"] = prompts
    if instruction:
        debrief["instructionMarkdown"] = instruction
    if context_markdown:
        debrief["contextMarkdown"] = context_markdown
    if questionnaire_markdown:
        debrief["questionnaireMarkdown"] = questionnaire_markdown
    if output_schema_markdown:
        debrief["outputSchemaMarkdown"] = output_schema_markdown

    task_rel = _task_path_from_trial(trial_dir)
    if task_rel:
        try:
            from playground.self_report_task_config import (
                load_self_report_schema_for_task_path,
            )
            from playground.user_sim.self_report_contract import schema_to_public_dict

            schema = load_self_report_schema_for_task_path(
                task_rel,
                repo_root=repo_root,
                fallback_to_default=True,
            )
            if schema is not None:
                debrief["selfReportSchema"] = schema_to_public_dict(schema)
        except Exception:  # noqa: BLE001
            pass

    persona_view = debrief.get("persona")
    if isinstance(persona_view, dict):
        context = str(persona_view.get("context") or "").strip()
        display = str(prompts.get("personaPrompt") or "").strip()
        if display.startswith("## Persona"):
            display = display.split("\n", 1)[1].strip() if "\n" in display else ""
        if display and (_is_thin_persona_prompt(context, persona=persona) or not context):
            persona_view["context"] = display
        raw = _read_persona_yaml_raw(repo_root, persona_rel)
        if raw and isinstance(raw.get("dimensions"), dict):
            persona_view["dimensions"] = {
                str(key): str(value)
                for key, value in raw["dimensions"].items()
                if value is not None and str(value).strip()
            }


def _map_chatbot_debrief_from_done_event(
    *,
    done: dict[str, Any],
    persona: Persona,
    created_at: str,
) -> dict[str, Any]:
    payload = dict(done)
    payload["id"] = "harbor-trial"
    payload["applicationType"] = "chatbot"
    payload["createdAt"] = str(payload.get("createdAt") or created_at)
    payload["persona"] = run_store.persona_summary(persona)
    return payload


def _map_chatbot_debrief(
    *,
    output_dir: Path,
    persona: Persona,
    created_at: str,
    trial_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    ensure_harbor_source_imports()
    from playground.harbor.playground import (
        build_result_from_harbor_artifacts,
    )

    transcript = _read_json(output_dir / "transcript.json")
    domain = str(transcript.get("domain") or "movie")
    config = PlaygroundConfig(domain=domain, engine="gpt-4o-mini")
    # The task declares which chat app is under test; never leave a generic
    # PlaygroundConfig default in the debrief when it is unknown.
    config.application_id = _chat_application_id_from_trial(repo_root, trial_dir)
    result = build_result_from_harbor_artifacts(
        output_dir=output_dir,
        config=config,
        persona=persona,
        sut_description="Chat application under test.",
        created_at=created_at,
    )
    payload = result.to_dict()
    payload["id"] = "harbor-trial"
    payload["applicationType"] = "chatbot"
    payload["createdAt"] = created_at
    payload["persona"] = run_store.persona_summary(persona)
    return payload


def _map_survey_debrief(
    *,
    output_dir: Path,
    trial_dir: Path,
    repo_root: Path,
    persona: Persona,
    created_at: str,
) -> dict[str, Any]:
    if (output_dir / "survey_result.json").is_file():
        raw = _read_json(output_dir / "survey_result.json")
        instrument = _resolve_survey_instrument(
            repo_root=repo_root,
            trial_dir=trial_dir,
            payload=raw,
        )
        result = build_survey_eval_result_from_artifacts(
            output_dir=output_dir,
            config=SurveyEvalConfig(mode="harbor_persona_survey"),
            persona=persona,
            instrument=instrument,
            created_at=created_at,
        )
        result_view = survey_result_view(result)
    else:
        responses_path = output_dir / "survey_responses.json"
        if not responses_path.is_file():
            raise FileNotFoundError(
                "survey output not found in {} (expected survey_result.json or survey_responses.json)".format(
                    output_dir
                )
            )
        raw = _read_json(responses_path)
        responses = raw.get("responses")
        if not isinstance(responses, list):
            responses = raw.get("answers") if isinstance(raw.get("answers"), list) else []
        answers = []
        for index, entry in enumerate(responses):
            if not isinstance(entry, dict):
                continue
            answers.append(
                {
                    "questionId": str(
                        entry.get("question_id")
                        or entry.get("questionId")
                        or "q{}".format(index)
                    ),
                    "value": entry.get("choice_id")
                    or entry.get("value")
                    or entry.get("response")
                    or "",
                    "rationale": entry.get("rationale"),
                }
            )
        instrument = _resolve_survey_instrument(
            repo_root=repo_root,
            trial_dir=trial_dir,
            payload={"answers": answers},
        )
        from backend.service.survey_types import (
            SurveyAnswer,
            SurveyEvalResult,
        )

        typed_answers = [
            SurveyAnswer(
                question_id=str(a["questionId"]),
                value=a["value"],
                rationale=str(a.get("rationale") or ""),
            )
            for a in answers
        ]
        metrics = _survey_metrics(instrument, typed_answers)
        result = SurveyEvalResult(
            config=SurveyEvalConfig(),
            persona=persona,
            instrument=instrument,
            answers=typed_answers,
            trajectory=[],
            metrics=metrics,
            created_at=created_at,
            prompts={},
        )
        result_view = survey_result_view(result)

    return {
        "id": "harbor-trial",
        "applicationType": "survey",
        "createdAt": created_at,
        "persona": run_store.persona_summary(persona),
        "instrumentTitle": result_view.get("instrument", {}).get("title"),
        "surveyResult": result_view,
    }


def _map_survey_debrief_from_done_event(
    *,
    done: dict[str, Any],
    persona: Persona,
    created_at: str,
) -> dict[str, Any]:
    """Build survey debrief from the live ``done`` event when artifact files are missing."""
    metrics = done.get("metrics") if isinstance(done.get("metrics"), dict) else {}
    answers = done.get("answers") if isinstance(done.get("answers"), list) else []
    instrument = done.get("instrument") if isinstance(done.get("instrument"), dict) else {}
    num_answered = int(metrics.get("numAnswered") or len(answers))
    num_questions = int(metrics.get("numQuestions") or len(answers))
    result_view = {
        "instrument": instrument,
        "answers": answers,
        "trajectory": done.get("trajectory") if isinstance(done.get("trajectory"), list) else [],
        "completion": {
            "numQuestions": num_questions,
            "numAnswered": num_answered,
            "missingQuestionIds": [],
            "valid": num_answered >= num_questions and num_questions > 0,
            "meanLikert": metrics.get("meanLikert"),
        },
        "createdAt": str(done.get("createdAt") or created_at),
        "prompts": done.get("prompts") if isinstance(done.get("prompts"), dict) else {},
    }
    return {
        "id": "harbor-trial",
        "applicationType": "survey",
        "createdAt": created_at,
        "persona": run_store.persona_summary(persona),
        "instrumentTitle": instrument.get("title"),
        "surveyResult": result_view,
    }


def _map_debrief_from_done_event(
    *,
    trial_dir: Path,
    persona: Persona,
    created_at: str,
    app_type: str,
) -> dict[str, Any] | None:
    """Build a debrief payload from ``events.jsonl`` when disk artifacts are absent."""
    done = _read_chat_done_event(trial_dir)
    if done is None:
        return None
    if app_type == "survey" and isinstance(done.get("answers"), list):
        return _map_survey_debrief_from_done_event(
            done=done,
            persona=persona,
            created_at=created_at,
        )
    if app_type == "chatbot":
        return _map_chatbot_debrief_from_done_event(
            done=done,
            persona=persona,
            created_at=created_at,
        )
    return None


def _survey_answers_from_debrief(debrief: dict[str, Any]) -> list[Any]:
    survey = debrief.get("surveyResult")
    if not isinstance(survey, dict):
        return []
    answers = survey.get("answers")
    return answers if isinstance(answers, list) else []


def _enrich_survey_debrief_from_events(
    debrief: dict[str, Any],
    *,
    trial_dir: Path,
    persona: Persona,
    created_at: str,
) -> dict[str, Any]:
    """Prefer ``events.jsonl`` answers when artifact mapping produced none."""
    if _survey_answers_from_debrief(debrief):
        return debrief
    done = _read_chat_done_event(trial_dir)
    if done is None or not isinstance(done.get("answers"), list) or not done.get("answers"):
        return debrief
    return _map_survey_debrief_from_done_event(
        done=done,
        persona=persona,
        created_at=created_at,
    )


def _resolve_web_eval_task(
    repo_root: Path,
    trial_dir: Path,
    output_dir: Path,
) -> "WebEvalTask":
    from backend.service.web_tasks import list_web_eval_tasks
    from backend.service.web_types import WebEvalTask

    task_rel = _task_path_from_trial(trial_dir)
    if task_rel:
        folder = Path(task_rel.replace("\\", "/")).name
        for task in list_web_eval_tasks():
            if Path(str(task.task_path)).name == folder:
                return task
    artifact_name = next(
        (
            path.name
            for path in sorted(output_dir.glob("*.json"))
            if path.name not in {"survey_result.json", "survey_responses.json", "transcript.json"}
        ),
        "web_result.json",
    )
    return WebEvalTask(
        id="harbor_web",
        title="Website task",
        site_name="Website",
        site_url="https://example.com",
        task_path=repo_root / task_rel if task_rel else output_dir,
        description="Harbor web trial",
        output_artifact=artifact_name,
    )


def _web_result_from_book_interest(data: dict[str, Any], *, created_at: str) -> dict[str, Any]:
    title = str(data.get("title", "")).strip() or "Book"
    reason = str(data.get("reason", "")).strip() or "Book selection recorded."
    interested = bool(data.get("interested", True))
    score = 8 if interested else 5
    return {
        "selectedProductId": title,
        "selectedProductName": title,
        "needSatisfaction": score,
        "easeOfUse": score,
        "overallExperienceRating": score,
        "reason": reason,
        "createdAt": created_at,
        "valid": len(reason) >= 20,
    }


def _clamp_web_score(value: Any, *, default: int) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = default
    return max(1, min(10, score))


def _decision_outcome_score(outcome: str) -> int:
    mapping = {
        "selected": 8,
        "considered": 6,
        "deferred": 4,
        "rejected": 3,
        "skipped": 2,
    }
    return mapping.get(outcome, 5)


def _decision_satisfaction_score(value: Any) -> int | None:
    mapping = {
        "yes": 9,
        "partially": 6,
        "no": 3,
    }
    return mapping.get(str(value or "").strip().lower())


def _web_result_from_decision_artifact(
    data: dict[str, Any],
    *,
    created_at: str,
    user_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_product_id = str(data.get("decision_subject_id", "")).strip()
    selected_product_name = str(data.get("decision_subject_label", "")).strip()
    if not selected_product_id and not selected_product_name:
        raise ValueError("decision_subject_id or decision_subject_label is required")
    if not selected_product_id:
        selected_product_id = selected_product_name
    if not selected_product_name:
        selected_product_name = selected_product_id

    reason = str(data.get("reason", "")).strip()
    if not reason:
        raise ValueError("reason is required")

    outcome = str(data.get("decision_outcome", "")).strip().lower()
    default_score = _decision_outcome_score(outcome)
    feedback = user_feedback or {}

    overall = _clamp_web_score(
        feedback.get("overallExperienceRating"),
        default=default_score,
    )
    need_satisfaction = _decision_satisfaction_score(
        feedback.get("needConstraintSatisfaction")
    )
    if need_satisfaction is None:
        need_satisfaction = overall

    effort = feedback.get("effortRating")
    if effort is None:
        ease_of_use = overall
    else:
        effort_score = _clamp_web_score(effort, default=5)
        ease_of_use = max(1, min(10, 11 - effort_score))

    return {
        "selectedProductId": selected_product_id,
        "selectedProductName": selected_product_name,
        "needSatisfaction": need_satisfaction,
        "easeOfUse": ease_of_use,
        "overallExperienceRating": overall,
        "reason": reason,
        "createdAt": created_at,
        "valid": len(reason) >= 20,
    }


def _map_web_debrief(
    *,
    output_dir: Path,
    logs_dir: Path | None,
    persona: Persona,
    created_at: str,
    job_name: str,
    trial_name: str,
    trial_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    ensure_harbor_source_imports()
    from playground.harbor.web_eval import (
        HarborWebEvalConfig,
        WebEvalResultArtifact,
        _extract_web_submission_from_logs,
        _materialize_missing_web_artifact,
        build_result_from_harbor_web_artifacts,
    )

    task = _resolve_web_eval_task(repo_root, trial_dir, output_dir)
    _materialize_missing_web_artifact(
        output_dir=output_dir,
        logs_dir=logs_dir,
        task=task,
    )
    from backend.service.harbor_web_trace import read_harbor_web_trace

    trace = read_harbor_web_trace(
        logs_dir,
        job_name=job_name,
        trial_name=trial_name,
    )
    feedback = _read_user_feedback_artifact(trial_dir, output_dir=output_dir)
    web_result: dict[str, Any] | None = None
    prompts: dict[str, Any] | None = None
    try:
        result = build_result_from_harbor_web_artifacts(
            output_dir=output_dir,
            logs_dir=logs_dir,
            config=HarborWebEvalConfig(),
            persona=persona,
            task=task,
            created_at=created_at,
        )
        payload = result.to_dict()
        web_result = payload.get("webResult")
        prompts = payload.get("prompts")
    except (ValueError, FileNotFoundError):
        artifact_path = output_dir / task.output_artifact
        if artifact_path.is_file():
            artifact_data = _read_json(artifact_path)
            if (
                artifact_data.get("decision_subject_id")
                or artifact_data.get("decision_subject_label")
            ):
                web_result = _web_result_from_decision_artifact(
                    artifact_data,
                    created_at=created_at,
                    user_feedback=feedback,
                )
            elif artifact_path.name == "book_interest.json":
                web_result = _web_result_from_book_interest(
                    artifact_data,
                    created_at=created_at,
                )
        elif web_result is None:
            recovered = _extract_web_submission_from_logs(logs_dir)
            if recovered is not None:
                if (
                    recovered.get("decision_subject_id")
                    or recovered.get("decision_subject_label")
                ):
                    web_result = _web_result_from_decision_artifact(
                        recovered,
                        created_at=created_at,
                        user_feedback=feedback,
                    )
                else:
                    try:
                        web_result = WebEvalResultArtifact.from_dict(
                            recovered,
                            created_at=created_at,
                        ).to_dict()
                    except ValueError:
                        web_result = None
    return {
        "id": "harbor-trial",
        "applicationType": "web",
        "createdAt": created_at,
        "persona": run_store.persona_summary(persona),
        "siteName": task.site_name,
        "taskTitle": task.title,
        "webResult": web_result,
        "webTrace": trace,
        "prompts": prompts,
    }


def _read_reward_score(trial_dir: Path) -> float | None:
    for rel in ("reward.txt", "verifier/reward.txt", "logs/verifier/reward.txt"):
        reward_path = trial_dir / rel
        if not reward_path.is_file():
            continue
        try:
            return float(reward_path.read_text(encoding="utf-8").strip())
        except ValueError:
            continue
    result_path = trial_dir / "result.json"
    if result_path.is_file():
        try:
            payload = _read_json(result_path)
            verifier = payload.get("verifier_result")
            if isinstance(verifier, dict):
                rewards = verifier.get("rewards")
                if isinstance(rewards, dict) and rewards.get("reward") is not None:
                    return float(rewards["reward"])
        except (ValueError, TypeError):
            pass
    return None


def _verifier_summary(trial_dir: Path) -> dict[str, Any] | None:
    reward = _read_reward_score(trial_dir)
    if reward is None:
        return None
    detail: str | None = None
    detail_path = trial_dir / "verifier" / "test-stdout.txt"
    if detail_path.is_file():
        raw = detail_path.read_text(encoding="utf-8", errors="replace").strip()
        if raw:
            detail = raw[:2000]
    return {
        "passed": reward >= 1.0,
        "reward": reward,
        "detail": detail,
    }


def _read_trial_evaluation_artifact(trial_dir: Path) -> dict[str, Any] | None:
    for rel in ("verifier/structured_output.json", "logs/verifier/structured_output.json"):
        artifact_path = trial_dir / rel
        if not artifact_path.is_file():
            continue
        try:
            payload = _read_json(artifact_path)
        except Exception:  # noqa: BLE001
            continue
        contexts = payload.get("contexts")
        if isinstance(contexts, list):
            payload["contexts"] = [item for item in contexts if isinstance(item, dict)]
        return payload
    return None


def _read_user_feedback_artifact(
    trial_dir: Path,
    *,
    output_dir: Path | None = None,
) -> dict[str, Any] | None:
    candidates: list[Path] = []
    if output_dir is not None:
        candidates.append(output_dir / "user_feedback.json")
    candidates.extend(
        [
            trial_dir / "verifier" / "user_feedback.json",
            trial_dir / "logs" / "verifier" / "user_feedback.json",
        ]
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            return _read_json(path)
        except Exception:  # noqa: BLE001
            continue
    return None


def _attach_verifier_artifacts(debrief: dict[str, Any], trial_dir: Path) -> None:
    verifier = _verifier_summary(trial_dir)
    if verifier is not None:
        debrief["verifier"] = verifier
    trial_evaluation = _read_trial_evaluation_artifact(trial_dir)
    if trial_evaluation is not None:
        debrief["trialEvaluation"] = trial_evaluation


def _map_cua_debrief(
    *,
    output_dir: Path,
    logs_dir: Path | None,
    trial_dir: Path,
    persona: Persona,
    created_at: str,
    job_name: str,
    trial_name: str,
) -> dict[str, Any]:
    artifact_path = next(
        (
            path
            for path in sorted(output_dir.glob("*.json"))
            if path.name.lower() in {"decision.json", "book_interest.json"}
            or "notification" in path.name.lower()
        ),
        None,
    )
    if artifact_path is None:
        artifacts = sorted(path.name for path in output_dir.glob("*.json"))
        artifact_path = output_dir / artifacts[0] if artifacts else None
    artifact: dict[str, Any] | None = None
    if artifact_path is not None and artifact_path.is_file():
        artifact = _read_json(artifact_path)

    trace: dict[str, Any] | None = None
    if logs_dir is not None:
        trajectory_path = logs_dir / "trajectory.json"
        if trajectory_path.is_file():
            try:
                ensure_harbor_source_imports()
                from playground.harbor.web_eval import _trace_from_trajectory

                mapped = _trace_from_trajectory(_read_json(trajectory_path))
                trace = mapped.to_dict()
            except Exception:  # noqa: BLE001
                trace = {"events": [], "raw": {}}

    from backend.service.harbor_web_trace import attach_harbor_trace_screenshot_urls

    trace = attach_harbor_trace_screenshot_urls(
        trace,
        job_name=job_name,
        trial_name=trial_name,
    )

    reward = _read_reward_score(trial_dir)
    if reward is not None:
        success = reward >= 1.0
        score = reward
    else:
        # Artifact alone is not a pass — host verifiers may have crashed
        # before writing reward.txt (common on macOS system Python 3.9).
        success = False
        score = 0.0
    return {
        "id": "harbor-trial",
        "applicationType": "os-app",
        "createdAt": created_at,
        "persona": run_store.persona_summary(persona),
        "osAppResult": {
            "success": success,
            "score": score,
            "artifactName": artifact_path.name if artifact_path is not None else None,
            "artifact": artifact,
            "createdAt": created_at,
        },
        "osAppTrace": trace,
        "trace": trace,
    }


def _ensure_host_verifier_scored(*, repo_root: Path, trial_dir: Path) -> None:
    """Score on the host before debrief when sandbox verifier was disabled.

    Playground os-app jobs disable in-sandbox verification and score from
    downloaded artifacts on the host. ``harbor_job_service`` also runs the host
    verifier after ``harbor run`` exits, but the UI can request debrief first;
    without this guard the cockpit briefly shows 0% until a refresh.
    """
    if _read_reward_score(trial_dir) is not None:
        return
    try:
        from playground.host_verifier import maybe_run_host_verifier

        maybe_run_host_verifier(repo_root=repo_root, trial_dir=trial_dir)
    except Exception:  # noqa: BLE001
        return


def map_trial_debrief(
    *,
    repo_root: Path,
    jobs_dir: Path,
    job_name: str,
    trial_name: str,
) -> dict[str, Any]:
    """Build a Playground-compatible debrief payload for one Harbor trial."""
    trial_dir = jobs_dir / job_name / trial_name
    if not trial_dir.is_dir():
        raise FileNotFoundError("trial not found")

    output_dir = find_trial_output_dir(trial_dir)
    persona_rel = _persona_path_from_trial(trial_dir, repo_root)
    persona = _load_playground_persona(repo_root, persona_rel)
    created_at = _trial_created_at(trial_dir)

    if output_dir is None:
        trial_error = _read_trial_failure_message(trial_dir)
        app_type = _application_type_from_trial(repo_root, trial_dir) or "unknown"
        if not trial_error:
            debrief = _map_debrief_from_done_event(
                trial_dir=trial_dir,
                persona=persona,
                created_at=created_at,
                app_type=app_type,
            )
            if debrief is not None:
                debrief["harbor"] = {
                    "jobName": job_name,
                    "trialName": trial_name,
                    "outputDir": None,
                    "personaPath": persona_rel,
                }
                task_title = _task_title_from_trial(repo_root, trial_dir)
                if task_title and not debrief.get("taskTitle"):
                    debrief["taskTitle"] = task_title
                _enrich_debrief_prompts(
                    debrief,
                    trial_dir=trial_dir,
                    repo_root=repo_root,
                    persona_rel=persona_rel,
                    persona=persona,
                )
                _attach_verifier_artifacts(debrief, trial_dir)
                return debrief
            raise FileNotFoundError("trial output artifacts not found")
        debrief = _map_failed_trial_debrief(
            trial_dir=trial_dir,
            persona=persona,
            created_at=created_at,
            job_name=job_name,
            trial_name=trial_name,
            trial_error=trial_error,
            app_type=app_type,
            persona_rel=persona_rel,
        )
        task_title = _task_title_from_trial(repo_root, trial_dir)
        if task_title and not debrief.get("taskTitle"):
            debrief["taskTitle"] = task_title
        _enrich_debrief_prompts(
            debrief,
            trial_dir=trial_dir,
            repo_root=repo_root,
            persona_rel=persona_rel,
            persona=persona,
        )
        _attach_verifier_artifacts(debrief, trial_dir)
        return debrief

    app_type = _resolve_application_type(repo_root, trial_dir, output_dir)
    if app_type == "chatbot":
        transcript_path = output_dir / "transcript.json"
        if transcript_path.is_file():
            debrief = _map_chatbot_debrief(
                output_dir=output_dir,
                persona=persona,
                created_at=created_at,
                trial_dir=trial_dir,
                repo_root=repo_root,
            )
        else:
            done = _read_chat_done_event(trial_dir)
            if done is not None:
                debrief = _map_chatbot_debrief_from_done_event(
                    done=done,
                    persona=persona,
                    created_at=created_at,
                )
            else:
                debrief = {
                    "id": "harbor-trial",
                    "applicationType": "chatbot",
                    "createdAt": created_at,
                    "persona": run_store.persona_summary(persona),
                    "transcript": [],
                    "config": {},
                }
    elif app_type == "survey":
        result_path = output_dir / "survey_result.json"
        responses_path = output_dir / "survey_responses.json"
        if result_path.is_file() or responses_path.is_file():
            debrief = _map_survey_debrief(
                output_dir=output_dir,
                trial_dir=trial_dir,
                repo_root=repo_root,
                persona=persona,
                created_at=created_at,
            )
            debrief = _enrich_survey_debrief_from_events(
                debrief,
                trial_dir=trial_dir,
                persona=persona,
                created_at=created_at,
            )
        else:
            done = _read_chat_done_event(trial_dir)
            if done is not None and isinstance(done.get("answers"), list):
                debrief = _map_survey_debrief_from_done_event(
                    done=done,
                    persona=persona,
                    created_at=created_at,
                )
            else:
                debrief = {
                    "id": "harbor-trial",
                    "applicationType": "survey",
                    "createdAt": created_at,
                    "persona": run_store.persona_summary(persona),
                    "surveyResult": None,
                    "error": "Survey output file was not saved to disk.",
                }
    elif app_type == "web":
        debrief = _map_web_debrief(
            output_dir=output_dir,
            logs_dir=find_trial_logs_dir(trial_dir),
            persona=persona,
            created_at=created_at,
            job_name=job_name,
            trial_name=trial_name,
            trial_dir=trial_dir,
            repo_root=repo_root,
        )
    elif app_type == "os-app":
        _ensure_host_verifier_scored(repo_root=repo_root, trial_dir=trial_dir)
        debrief = _map_cua_debrief(
            output_dir=output_dir,
            logs_dir=find_trial_logs_dir(trial_dir),
            trial_dir=trial_dir,
            persona=persona,
            created_at=created_at,
            job_name=job_name,
            trial_name=trial_name,
        )
    else:
        artifacts = sorted(path.name for path in output_dir.glob("*") if path.is_file())
        debrief = {
            "id": "harbor-trial",
            "applicationType": "unknown",
            "createdAt": created_at,
            "persona": run_store.persona_summary(persona),
            "artifacts": artifacts,
        }

    debrief["harbor"] = {
        "jobName": job_name,
        "trialName": trial_name,
        "outputDir": str(output_dir.relative_to(repo_root)),
        "personaPath": persona_rel,
    }
    task_title = _task_title_from_trial(repo_root, trial_dir)
    if task_title and not debrief.get("taskTitle"):
        debrief["taskTitle"] = task_title
    user_feedback = _read_user_feedback_artifact(trial_dir, output_dir=output_dir)
    if user_feedback is not None:
        debrief["userFeedback"] = user_feedback
        try:
            from playground.feedback import questionnaire_from_feedback

            debrief["questionnaire"] = questionnaire_from_feedback(user_feedback).to_dict()
        except Exception:  # noqa: BLE001
            pass
    trial_error: str | None = None
    result_path = trial_dir / "result.json"
    if result_path.is_file():
        try:
            trial_error = _trial_result_error(_read_json(result_path))
        except Exception:  # noqa: BLE001
            trial_error = None
    if trial_error:
        debrief["error"] = trial_error
        debrief["status"] = "error"
        if isinstance(debrief.get("harbor"), dict):
            debrief["harbor"]["failed"] = True
    _attach_verifier_artifacts(debrief, trial_dir)
    _enrich_debrief_prompts(
        debrief,
        trial_dir=trial_dir,
        repo_root=repo_root,
        persona_rel=persona_rel,
        persona=persona,
    )
    return debrief
