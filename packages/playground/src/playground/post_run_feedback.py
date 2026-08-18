"""Generate optional post-run self-reflection artifacts for interactive tasks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from backend.service.harbor_trial_debrief import (
    _application_type_from_task_toml,
    _load_playground_persona,
    _persona_path_from_trial,
    _recorded_persona_language,
    _task_path_from_trial,
    find_trial_logs_dir,
    find_trial_output_dir,
)
from playground.self_report_task_config import (
    load_self_report_schema_for_task_path,
)
from playground.task_content_bundle import (
    load_task_content_bundle_for_task_path,
)
from playground.model_client import build_json_client
from playground.self_report_runtime import (
    complete_self_report_payload,
    write_self_report_artifact,
)
from playground.types import DEFAULT_PERSONA_MODEL
from playground.user_sim.prompt import assemble_report_system_prompt
from playground.user_sim.self_report_contract import (
    schema_prompt_block,
)

_REFLECTION_USER = """You have just finished using this {application_label}.
Only use what you actually saw, did, or produced during this run.

## Run artifacts
{artifact_summary}

## Interaction summary
{trace_summary}

{instructions}

{schema_block}

Return strict JSON only with no prose before or after the JSON object."""


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("{} must contain a JSON object".format(path.name))
    return payload


def _persona_model_from_trial(trial_dir: Path) -> str:
    for rel in ("result.json", "config.json"):
        path = trial_dir / rel
        if not path.is_file():
            continue
        try:
            payload = _read_json(path)
        except Exception:  # noqa: BLE001
            continue
        config = payload.get("config") if rel == "result.json" else payload
        if not isinstance(config, dict):
            continue
        agent = config.get("agent")
        if isinstance(agent, dict):
            model_name = agent.get("model_name") or agent.get("modelName")
            if isinstance(model_name, str) and model_name.strip():
                return model_name.strip()
    return DEFAULT_PERSONA_MODEL


def _truncate(value: str, limit: int = 1200) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _artifact_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            payload = _read_json(path)
            return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        except Exception:  # noqa: BLE001
            return path.read_text(encoding="utf-8", errors="replace")
    if suffix in {".txt", ".csv", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def _artifact_summary(output_dir: Path, *, skip_names: Iterable[str]) -> str:
    skip = set(skip_names)
    parts: List[str] = []
    for path in sorted(output_dir.iterdir()):
        if not path.is_file() or path.name in skip:
            continue
        text = _artifact_text(path)
        if text.strip():
            parts.append("### {}\n{}".format(path.name, _truncate(text)))
        else:
            parts.append("### {}\n(binary or unsupported artifact)".format(path.name))
    return "\n\n".join(parts) if parts else "(no output artifacts found)"


def _step_message(step: Dict[str, Any]) -> str:
    message = step.get("message")
    if isinstance(message, str):
        return message.strip()
    if isinstance(message, list):
        parts: List[str] = []
        for item in message:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                text = str(item.get("text") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _trace_summary(logs_dir: Path | None) -> str:
    if logs_dir is None:
        return "(no trace logs found)"
    trajectory_path = logs_dir / "trajectory.json"
    if not trajectory_path.is_file():
        return "(no trajectory.json found)"
    try:
        payload = _read_json(trajectory_path)
    except Exception:  # noqa: BLE001
        return "(trajectory could not be parsed)"
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        return "(trajectory had no steps)"
    lines: List[str] = []
    total = len(steps)
    head = steps[:6]
    tail = steps[-2:] if total > 6 else []
    for index, step in enumerate(head, start=1):
        if not isinstance(step, dict):
            continue
        source = str(step.get("source") or "agent")
        actions = step.get("tool_calls") or []
        action_names = [
            str(call.get("function_name") or "").strip()
            for call in actions
            if isinstance(call, dict) and str(call.get("function_name") or "").strip()
        ]
        action_text = ", ".join(action_names[:3]) if action_names else "no tools"
        lines.append(
            "{}. [{}] {} ({})".format(
                index,
                source,
                _truncate(_step_message(step) or "(no message)", limit=180),
                action_text,
            )
        )
    if tail:
        lines.append("...")
        start = total - len(tail) + 1
        for offset, step in enumerate(tail, start=start):
            if not isinstance(step, dict):
                continue
            source = str(step.get("source") or "agent")
            actions = step.get("tool_calls") or []
            action_names = [
                str(call.get("function_name") or "").strip()
                for call in actions
                if isinstance(call, dict) and str(call.get("function_name") or "").strip()
            ]
            action_text = ", ".join(action_names[:3]) if action_names else "no tools"
            lines.append(
                "{}. [{}] {} ({})".format(
                    offset,
                    source,
                    _truncate(_step_message(step) or "(no message)", limit=180),
                    action_text,
                )
            )
    return "\n".join(lines) if lines else "(trajectory had no readable steps)"


def _application_label(app_type: str) -> str:
    if app_type == "web":
        return "website"
    if app_type == "os-app":
        return "desktop or mobile app"
    return "interactive application"


def maybe_write_trial_user_feedback(*, repo_root: Path, trial_dir: Path) -> Path | None:
    task_path = _task_path_from_trial(trial_dir)
    if not task_path:
        return None
    app_type = _application_type_from_task_toml(repo_root, task_path)
    if app_type not in {"web", "os-app"}:
        return None

    schema = load_self_report_schema_for_task_path(
        task_path,
        repo_root=repo_root,
        fallback_to_default=False,
    )
    if schema is None or not schema.fields:
        return None

    output_dir = find_trial_output_dir(trial_dir)
    if output_dir is None:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    feedback_path = output_dir / (schema.artifact_name or "user_feedback.json")
    if feedback_path.is_file():
        return feedback_path

    persona_rel = _persona_path_from_trial(trial_dir, repo_root)
    persona = _load_playground_persona(repo_root, persona_rel)
    task_bundle = load_task_content_bundle_for_task_path(task_path, repo_root=repo_root)
    system_prompt = assemble_report_system_prompt(
        persona,
        persona_yaml_path=persona_rel,
        task_bundle=task_bundle,
        persona_language=_recorded_persona_language(trial_dir).language,
    )
    user_prompt = _REFLECTION_USER.format(
        application_label=_application_label(app_type),
        artifact_summary=_artifact_summary(output_dir, skip_names={feedback_path.name}),
        trace_summary=_trace_summary(find_trial_logs_dir(trial_dir)),
        instructions=schema.instructions
        or "Answer honestly from your own point of view.",
        schema_block=schema_prompt_block(schema),
    )
    client = build_json_client(_persona_model_from_trial(trial_dir), temperature=0.1)
    payload = complete_self_report_payload(
        client,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=schema,
    )
    write_self_report_artifact(payload, output_path=feedback_path)
    return feedback_path
