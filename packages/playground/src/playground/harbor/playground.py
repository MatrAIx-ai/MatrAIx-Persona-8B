"""Harbor-backed playground helpers.

This module keeps the Harbor-specific artifact contract out of the generic
``PlaygroundService``. Harbor owns the persona system prompt injection; the
application supplies a task-specific chatbot simulation instruction and then
maps Harbor artifacts back to the existing Studio UI shape.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import yaml

from backend.service.config import harbor_persona_model
from playground.structured_exposure import coerce_turn_view
from playground.feedback import questionnaire_from_feedback
from playground.persona_language import persona_language_contract
from playground.types import Persona, PlaygroundConfig
from matraix.persona_agent_context import apply_persona_context_to_agent_spec

SCORER_PACKAGE_TARGET = "/app/playground"
SCORER_PACKAGE_PARENT = "/app"
SCORER_OUTPUT_PATH = "/logs/verifier/user_feedback.json"


def _path_prefix(parts: Sequence[str], end: int) -> Path:
    return Path(*parts[:end]) if end > 0 else Path(".")


def resolve_repo_root(file_path: Path) -> Path:
    """Resolve the repo/app root for local and containerized layouts."""
    path = Path(file_path).resolve()
    parts = path.parts
    for index in range(len(parts) - 1):
        if parts[index] == "application" and parts[index + 1] == "playground":
            return _path_prefix(parts, index)
        if parts[index] == "applications" and parts[index + 1] == "playground":
            return _path_prefix(parts, index)
    for index in range(len(parts) - 2):
        if (
            parts[index] == "packages"
            and parts[index + 1] == "playground"
            and parts[index + 2] == "src"
        ):
            return _path_prefix(parts, index)
    for index in range(len(parts) - 2):
        if (
            parts[index] == "environment"
            and parts[index + 1] == "integrations"
            and parts[index + 2] == "playground"
        ):
            return _path_prefix(parts, index)
    for index in range(len(parts) - 2):
        if (
            parts[index] == "environment"
            and parts[index + 1] == "agents"
            and parts[index + 2] == "matraix"
        ):
            return _path_prefix(parts, index)
    for index in range(len(parts) - 1):
        if parts[index] == "backend" and parts[index + 1] == "service":
            return _path_prefix(parts, index)
    raise ValueError("cannot resolve repo root from {}".format(path))


def _repo_root() -> Path:
    return resolve_repo_root(Path(__file__))


def _normalize_chat_task_path(task_path: str | None) -> str | None:
    raw = str(task_path or "").strip()
    return raw.replace("\\", "/") or None


def _default_harbor_runs_root() -> Path:
    return (
        _repo_root()
        / "data"
        / "cache"
        / "playground"
        / "harbor_playground"
    )


def _run_subprocess(command: Sequence[str], *, cwd: Path, env: Dict[str, str]) -> int:
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        env=env,
        check=False,
    ).returncode


def _read_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_harbor_command() -> Sequence[str]:
    command = os.environ.get("MATRIX_HARBOR_COMMAND") or os.environ.get(
        "HARBOR_COMMAND"
    )
    if command:
        return tuple(shlex.split(command))

    binary = os.environ.get("MATRIX_HARBOR_BIN") or os.environ.get("HARBOR_BIN")
    if binary:
        return (binary, "run")

    # Persona agents and optional extras live in this project environment. Use
    # `uv run` before falling back to a globally installed Harbor CLI so local
    # Playground jobs see the repo's PYTHONPATH and synced extras.
    try:
        venv_harbor = _repo_root() / ".venv" / "bin" / "harbor"
        if venv_harbor.is_file():
            return (str(venv_harbor), "run")
        if (_repo_root() / "pyproject.toml").is_file():
            return ("uv", "run", "python", "-m", "harbor.cli.main", "run")
    except ValueError:
        pass

    found = shutil.which("harbor")
    return (found or "harbor", "run")


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("{} must contain a JSON object".format(path.name))
    return data


def _coerce_score(value: Any, default: int) -> int:
    text = str(value or "").strip().lower()
    if text == "yes":
        return 5
    if text == "partially":
        return 3
    if text == "no":
        return 1
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(1, min(5, n))


def _coerce_overall(value: Any, default: int = 5) -> int:
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(1, min(10, n))


def _item_id(item: Dict[str, Any]) -> str:
    return str(item.get("itemId", item.get("id", "")))


def harbor_persona_system_prompt(persona: Persona) -> str:
    """Return the exact system prompt text written into Harbor persona YAML."""
    return persona.context or persona.summary or persona.name


def _prompt_bundle(
    persona: Persona,
    task_prompt: str,
    *,
    persona_language: str | None = None,
) -> Dict[str, str]:
    harbor_prompt = harbor_persona_system_prompt(persona)
    if persona_language:
        harbor_prompt = "{}\n\n{}".format(
            harbor_prompt,
            persona_language_contract(persona_language),
        )
    return {
        "harborPrompt": harbor_prompt,
        "taskPrompt": task_prompt,
    }


def _scorer_mount(repo_root: Path) -> Dict[str, Any]:
    return {
        "type": "bind",
        "source": str(repo_root / "packages" / "playground" / "src" / "playground"),
        "target": SCORER_PACKAGE_TARGET,
        "read_only": True,
    }


def _file_mount(source: Path, target: str) -> Dict[str, Any]:
    return {
        "type": "bind",
        "source": str(source),
        "target": target,
        "read_only": True,
    }


def _json_env(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _verifier_env_assignments(
    *, persona: Persona, sut_description: str, config: PlaygroundConfig
) -> Dict[str, str]:
    persona_language = config.effective_language or "en"
    persona_language_source = config.language_source or "default"
    return {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "OPENAI_BASE_URL": "${OPENAI_BASE_URL:-https://api.openai.com/v1}",
        "MATRIX_PERSONA_LANGUAGE": persona_language,
        "MATRIX_PERSONA_LANGUAGE_SOURCE": persona_language_source,
        "MATRIX_SCORER_PACKAGE_PARENT": SCORER_PACKAGE_PARENT,
        "MATRIX_SCORER_MODULE": "playground.scoring",
        "MATRIX_SCORER_OUTPUT_PATH": SCORER_OUTPUT_PATH,
        "MATRIX_SCORER_PERSONA_JSON": _json_env(persona.to_dict()),
        "MATRIX_SCORER_CONFIG_JSON": _json_env(config.to_dict()),
        "MATRIX_SCORER_SUT_DESCRIPTION": sut_description,
    }


def _verifier_env_args(assignments: Dict[str, str]) -> List[str]:
    args: List[str] = []
    for key, value in assignments.items():
        args.extend(["--verifier-env", "{}={}".format(key, value)])
    return args


def _agent_env_args(assignments: Dict[str, str]) -> List[str]:
    args: List[str] = []
    for key, value in assignments.items():
        args.extend(["--agent-env", "{}={}".format(key, value)])
    return args


def _normalize_prompts(
    prompts: Optional[Dict[str, Any]],
    *,
    persona: Persona,
    persona_language: str | None = None,
) -> Dict[str, str]:
    data = prompts or {}
    harbor_prompt = str(data.get("harborPrompt") or "").strip()
    if not harbor_prompt:
        harbor_prompt = _prompt_bundle(
            persona,
            "",
            persona_language=persona_language,
        )["harborPrompt"]
    return {
        "harborPrompt": harbor_prompt,
        "taskPrompt": str(data.get("taskPrompt") or ""),
    }


def write_harbor_persona_yaml(base_dir: Path, persona: Persona) -> Path:
    """Write a v0 Harbor persona YAML file for ``persona`` and return its path."""
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / "persona.yaml"
    system_prompt = harbor_persona_system_prompt(persona)
    payload = {
        "persona_id": persona.id,
        "display_name": persona.name,
        "summary": persona.summary,
        "system_prompt": system_prompt,
    }
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def build_chatbot_simulation_prompt(
    *,
    application_id: str,
    application_context: str,
    max_turns: int | None,
    sut_description: str,
) -> str:
    """Build the application-owned generic chatbot task prompt."""
    system_label = _chatbot_system_label(
        application_id=application_id,
        application_context=application_context,
    )
    turn_limit = (
        "\n\nFinish within {} user turns.".format(max_turns)
        if max_turns is not None
        else ""
    )
    return """You are a user of a {system_label}.

{sut_description}

Silently decide what you realistically want from this system and which
constraints or preferences matter to you. Start the conversation naturally.
Do not reveal everything at once. Let the system ask follow-up questions,
answer as yourself, and give feedback when a response does not fit. Keep messages short and conversational (1-3 sentences), and avoid analytical
monologues or explaining your hidden reasoning. Continue until you can judge
whether the system satisfied your need.{turn_limit}

""".format(
        system_label=system_label,
        sut_description=sut_description,
        turn_limit=turn_limit,
    )


def _chatbot_system_label(*, application_id: str, application_context: str) -> str:
    context = application_context.replace("_", " ").strip() or "chatbot"
    if application_id == "finance_openbb":
        return "financial research system"
    if application_id == "meal_planning_nutrition":
        return "meal planning nutrition assistant"
    if application_id in {"acme_support_api", "acme_support_mcp"}:
        return "customer support system"
    return "{} system".format(context)


class HarborPlaygroundRunner:
    """Callable runner that executes a Harbor persona-agent job."""

    def __init__(
        self,
        *,
        repo_root: Optional[Path] = None,
        runs_root: Optional[Path] = None,
        command_runner: Callable[[Sequence[str]], int] = _run_subprocess,
        harbor_command: Optional[Sequence[str]] = None,
        chat_task_path: Optional[str] = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else _repo_root()
        self.runs_root = (
            Path(runs_root) if runs_root is not None else _default_harbor_runs_root()
        )
        self.command_runner = command_runner
        self.harbor_command = tuple(harbor_command or _default_harbor_command())
        self.chat_task_path = _normalize_chat_task_path(chat_task_path)

    def __call__(
        self,
        session: Any,
        persona: Persona,
        sut_description: str,
        config: PlaygroundConfig,
        _simulator: Any,
        *,
        created_at: str,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> HarborPlaygroundResult:
        def emit(event: Dict[str, Any]) -> None:
            if on_event is not None:
                on_event(event)

        chat_task_path = self.chat_task_path or _normalize_chat_task_path(
            os.environ.get("MATRIX_CHATBOT_TASK_PATH")
        )
        if not chat_task_path:
            raise ValueError(
                "chat task path is required; pass chat_task_path or set MATRIX_CHATBOT_TASK_PATH"
            )
        task_path_obj = Path(chat_task_path)
        if not task_path_obj.is_absolute():
            task_path_obj = self.repo_root / task_path_obj

        job_name = "playground-{}".format(uuid.uuid4().hex[:12])
        run_dir = self.runs_root / job_name / "_inputs"
        run_dir.mkdir(parents=True, exist_ok=True)
        persona_path = write_harbor_persona_yaml(run_dir, persona)
        task_prompt_path = run_dir / "task_prompt.md"
        application_context = config.application_context or config.domain
        task_prompt = build_chatbot_simulation_prompt(
            application_id=config.application_id,
            application_context=application_context,
            max_turns=config.max_turns,
            sut_description=sut_description,
        )
        task_prompt_path.write_text(task_prompt, encoding="utf-8")
        prompts = _prompt_bundle(
            persona,
            task_prompt,
            persona_language=config.effective_language,
        )

        job_config_path = run_dir / "harbor_job.yaml"
        job_config = {
            "job_name": job_name,
            "jobs_dir": str(self.runs_root),
            "n_attempts": 1,
            "timeout_multiplier": 1.0,
            "n_concurrent_trials": 1,
            "quiet": False,
            "environment": {
                "type": "docker",
                "delete": _env_bool("MATRIX_HARBOR_DELETE", False),
                "force_build": _env_bool("MATRIX_HARBOR_FORCE_BUILD", False),
                "mounts": [
                    _scorer_mount(self.repo_root),
                    _file_mount(task_prompt_path, "/app/input/task_prompt.md"),
                ],
            },
            "agents": [
                apply_persona_context_to_agent_spec(
                    {
                        "name": "persona-claude-code",
                        "model_name": config.persona_model or harbor_persona_model(),
                        "kwargs": {
                            "persona_path": str(persona_path),
                            "persona_language": config.effective_language or "en",
                            "persona_language_source": config.language_source
                            or "default",
                        },
                    }
                )
            ],
            "tasks": [
                {
                    "path": str(task_path_obj)
                }
            ],
            "extra_instruction_paths": [str(task_prompt_path)],
        }
        job_config_path.write_text(
            yaml.safe_dump(job_config, sort_keys=False),
            encoding="utf-8",
        )

        env = os.environ.copy()
        env_file = self.repo_root / ".env.local"
        for key, value in _read_env_file(env_file).items():
            env.setdefault(key, value)
        env["INTERECAGENT_ENGINE"] = config.engine
        env["MATRIX_CHATBOT_APPLICATION_ID"] = config.application_id
        env["MATRIX_CHATBOT_APPLICATION_CONTEXT"] = application_context
        env["MATRIX_CHATBOT_TASK_PATH"] = chat_task_path
        if config.application_id == "finance_openbb":
            env["COMPOSE_PROFILES"] = "finance"
            env.setdefault("FINANCE_AGENT_MODEL", config.engine)
        elif config.application_id == "meal_planning_nutrition":
            env.pop("COMPOSE_PROFILES", None)
        elif config.application_id in {"acme_support_api", "acme_support_mcp"}:
            env.pop("COMPOSE_PROFILES", None)
        else:
            env.pop("COMPOSE_PROFILES", None)
        project_env = Path("/tmp/matraix-harbor-project-venv")
        if project_env.exists():
            env.setdefault("UV_PROJECT_ENVIRONMENT", str(project_env))
        agent_env = {
            "MATRIX_CHATBOT_APPLICATION_ID": config.application_id,
            "MATRIX_CHATBOT_APPLICATION_CONTEXT": application_context,
            "MATRIX_CHATBOT_TASK_PATH": chat_task_path,
            "MATRIX_CHATBOT_TASK_PROMPT_PATH": "/app/input/task_prompt.md",
            "MATRIX_CHATBOT_PERSONA_PATH": "/app/input/persona.yaml",
            "MATRIX_CHATBOT_OUTPUT_DIR": "/app/output",
            "MATRIX_CHATBOT_API_URL": "http://chatbot-api:8000",
            "MATRIX_CHATBOT_PERSONA_MODEL": config.persona_model
            or harbor_persona_model(),
            "MATRIX_PERSONA_LANGUAGE": config.effective_language or "en",
            "MATRIX_PERSONA_LANGUAGE_SOURCE": config.language_source
            or "default",
        }
        if config.max_turns is not None:
            agent_env["MATRIX_CHATBOT_MAX_TURNS"] = str(config.max_turns)
            agent_env["MATRIX_CHATBOT_MIN_TURNS"] = str(min(3, config.max_turns))

        command = [
            *self.harbor_command,
            "-c",
            str(job_config_path),
            "--agent-env",
            "CLAUDE_CODE_TMPDIR=/logs/agent/claude-tmp",
            *_agent_env_args(agent_env),
            *_verifier_env_args(
                _verifier_env_assignments(
                    persona=persona,
                    sut_description=sut_description,
                    config=config,
                )
            ),
            "-y",
        ]
        if env_file.is_file():
            command.extend(["--env-file", str(env_file)])

        emit({"type": "prompts", "prompts": dict(prompts)})
        emit({"type": "phase", "phase": "harbor_starting"})
        code = self.command_runner(command, cwd=self.repo_root, env=env)
        if code != 0:
            raise RuntimeError("Harbor run failed with exit code {}".format(code))

        emit({"type": "phase", "phase": "harbor_collecting_artifacts"})
        output_dir = self._find_output_dir(job_name)
        result = build_result_from_harbor_artifacts(
            output_dir=output_dir,
            config=config,
            persona=persona,
            sut_description=sut_description,
            created_at=created_at,
            prompts=prompts,
        )
        session.turns = list(result.turn_views)
        return result

    def _find_output_dir(self, job_name: str) -> Path:
        job_dir = self.runs_root / job_name
        matches = sorted(job_dir.glob("*/artifacts/app/output"))
        if not matches:
            matches = sorted(job_dir.rglob("artifacts/app/output"))
        if not matches:
            failure = _harbor_failure_summary(job_dir)
            if failure:
                raise RuntimeError(
                    "Harbor run did not produce output artifacts: {}".format(failure)
                )
            raise FileNotFoundError(
                "Harbor output artifacts not found under {}".format(job_dir)
            )
        output_dir = matches[0]
        missing = _missing_required_output_artifacts(output_dir)
        if missing:
            failure = _harbor_failure_summary(job_dir)
            detail = failure or "missing required artifacts: {}".format(
                ", ".join(missing)
            )
            raise RuntimeError(
                "Harbor run did not produce required artifacts ({}): {}".format(
                    ", ".join(missing), detail
                )
            )
        return output_dir


def _missing_required_output_artifacts(output_dir: Path) -> List[str]:
    missing: List[str] = []
    if not (output_dir / "transcript.json").is_file():
        missing.append("transcript.json")
    if not (output_dir / "application_result.json").is_file():
        missing.append("application_result.json")
    return missing


def _application_result_path(output_dir: Path) -> Path:
    return output_dir / "application_result.json"


def _application_result_payload(output_dir: Path) -> Dict[str, Any]:
    """Read the slim eval-run summary written by the Playground harness."""
    path = _application_result_path(output_dir)
    if not path.is_file():
        return {}
    payload = _read_json(path)
    summary: Dict[str, Any] = {}
    for key in (
        "sessionId",
        "applicationId",
        "applicationContext",
        "turnCount",
        "config",
        "prompts",
    ):
        if key in payload:
            summary[key] = payload[key]
    return summary


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _content_text(value.get("content"))
    if isinstance(value, list):
        parts = []
        for entry in value:
            if isinstance(entry, dict):
                text = entry.get("text", entry.get("content"))
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            elif isinstance(entry, str) and entry.strip():
                parts.append(entry.strip())
        return " ".join(parts)
    return ""


def _compact_log_text(value: str, *, max_chars: int = 1000) -> str:
    return " ".join(str(value or "").split())[:max_chars]


def _message_contains_error(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    content = value.get("content")
    if not isinstance(content, list):
        return False
    return any(isinstance(entry, dict) and bool(entry.get("is_error")) for entry in content)


def _agent_error_summary(job_dir: Path) -> str:
    for path in sorted(job_dir.glob("*/agent/claude-code.txt")):
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            tool_result = event.get("tool_use_result")
            if isinstance(tool_result, str) and (
                "Error:" in tool_result or "Exit code" in tool_result
            ):
                return "Agent failed: {}".format(_compact_log_text(tool_result))
            error = event.get("error")
            status = event.get("api_error_status")
            message_has_error = _message_contains_error(event.get("message"))
            if not (event.get("is_error") or error or status or message_has_error):
                continue
            result = event.get("result")
            message = _content_text(event.get("message"))
            text = str(result or message or error or "").strip()
            if not text:
                continue
            meta = []
            if error:
                meta.append(str(error))
            if status:
                meta.append("status {}".format(status))
            return "Agent failed: {}{}".format(
                _compact_log_text(text),
                " ({})".format(", ".join(meta)) if meta else "",
            )
    return ""


def _harbor_failure_summary(job_dir: Path) -> str:
    agent_error = _agent_error_summary(job_dir)
    if agent_error:
        return agent_error

    for path in sorted(job_dir.glob("*/exception.txt")):
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            return " ".join(text.split())[:1000]

    result_path = job_dir / "result.json"
    if not result_path.is_file():
        return ""
    try:
        result = _read_json(result_path)
    except Exception:
        return ""
    stats = result.get("stats") or {}
    errored = stats.get("n_errored_trials")
    if errored:
        details: List[str] = []
        evals = stats.get("evals") or {}
        if isinstance(evals, dict):
            for value in evals.values():
                if not isinstance(value, dict):
                    continue
                exception_stats = value.get("exception_stats") or {}
                if isinstance(exception_stats, dict):
                    for exc_type, trials in exception_stats.items():
                        details.append("{}: {}".format(exc_type, trials))
        suffix = "; ".join(details[:3])
        return "n_errored_trials={}".format(errored) + (
            "; {}".format(suffix) if suffix else ""
        )
    return ""


def _build_turns_from_messages(transcript: Dict[str, Any]) -> List[Dict[str, Any]]:
    messages = transcript.get("messages") or []
    if not isinstance(messages, list):
        return []

    turns: List[Dict[str, Any]] = []
    pending_user: Optional[str] = None
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = str(message.get("content") or "")
        if role == "user":
            pending_user = content
        elif role == "assistant" and pending_user is not None:
            index = len(turns)
            turns.append(
                {
                    "turnId": str(index),
                    "conversationId": transcript.get("sessionId"),
                    "backend": "interecagent",
                    "userMessage": pending_user,
                    "assistantMessage": content,
                    "plan": [],
                    "nativeRaw": None,
                    "rawToolOutputs": None,
                }
            )
            pending_user = None
    return turns


def _normalize_harbor_turn(
    turn: Dict[str, Any], *, transcript: Dict[str, Any], fallback_index: int
) -> Dict[str, Any]:
    normalized = dict(turn)

    turn_id = normalized.get("turnId")
    if turn_id is None:
        legacy_turn_id = normalized.get("turn_id")
        if legacy_turn_id is None:
            legacy_turn_id = normalized.get("index", fallback_index)
        normalized["turnId"] = str(legacy_turn_id)
    elif not isinstance(turn_id, str):
        normalized["turnId"] = str(turn_id)

    conversation_id = normalized.get("conversationId")
    if conversation_id is None:
        session_id = transcript.get("sessionId")
        if session_id is not None:
            normalized["conversationId"] = str(session_id)
    elif not isinstance(conversation_id, str):
        normalized["conversationId"] = str(conversation_id)

    assistant_message = normalized.get("assistantMessage")
    if not isinstance(assistant_message, str) or not assistant_message.strip():
        legacy_assistant = normalized.get("assistantReply")
        if isinstance(legacy_assistant, str):
            normalized["assistantMessage"] = legacy_assistant
        elif assistant_message is None:
            normalized["assistantMessage"] = ""

    if "userMessage" not in normalized:
        legacy_user = normalized.get("user_message")
        if isinstance(legacy_user, str):
            normalized["userMessage"] = legacy_user

    if "durationSeconds" not in normalized and normalized.get("duration_seconds") is not None:
        normalized["durationSeconds"] = normalized.get("duration_seconds")

    return coerce_turn_view(normalized)


def _turn_views(transcript: Dict[str, Any]) -> List[Dict[str, Any]]:
    turns = transcript.get("turns")
    if isinstance(turns, list) and turns and all(isinstance(t, dict) for t in turns):
        return [
            _normalize_harbor_turn(turn, transcript=transcript, fallback_index=index)
            for index, turn in enumerate(turns)
        ]
    return _build_turns_from_messages(transcript)


def _questionnaire(feedback: Dict[str, Any]) -> Dict[str, Any]:
    return questionnaire_from_feedback(feedback).to_dict()


def _feedback_path(output_dir: Path) -> Optional[Path]:
    app_feedback = output_dir / "user_feedback.json"
    if app_feedback.is_file():
        return app_feedback
    try:
        verifier_feedback = output_dir.parents[2] / "verifier" / "user_feedback.json"
    except IndexError:
        return None
    return verifier_feedback if verifier_feedback.is_file() else None


@dataclass
class HarborPlaygroundResult:
    config: PlaygroundConfig
    persona: Persona
    sut_description: str
    turn_views: List[Dict[str, Any]]
    questionnaire: Dict[str, Any]
    metric_scores: Dict[str, Any]
    created_at: str
    prompts: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "persona": self.persona.to_dict(),
            "sutDescription": self.sut_description,
            "transcript": [dict(t) for t in self.turn_views],
            "questionnaire": dict(self.questionnaire),
            "metricScores": dict(self.metric_scores),
            "createdAt": self.created_at,
            "prompts": dict(self.prompts),
        }


def build_result_from_harbor_artifacts(
    *,
    output_dir: Path,
    config: PlaygroundConfig,
    persona: Persona,
    sut_description: str,
    created_at: str,
    prompts: Optional[Dict[str, Any]] = None,
) -> HarborPlaygroundResult:
    """Map Harbor task artifacts into the existing Playground UI result."""
    transcript = _read_json(output_dir / "transcript.json")
    turn_views = _turn_views(transcript)
    application_result = _application_result_payload(output_dir)
    feedback_path = _feedback_path(output_dir)
    feedback = _read_json(feedback_path) if feedback_path is not None else {}
    artifact_prompts = application_result.get("prompts")
    if prompts is None and isinstance(artifact_prompts, dict):
        result_prompts = {
            str(key): str(value)
            for key, value in artifact_prompts.items()
            if isinstance(key, str) and isinstance(value, str) and value.strip()
        }
    else:
        result_prompts = _normalize_prompts(
            prompts,
            persona=persona,
            persona_language=config.effective_language,
        )

    metric_scores = {
        "numTurns": len(turn_views),
    }
    return HarborPlaygroundResult(
        config=config,
        persona=persona,
        sut_description=sut_description,
        turn_views=turn_views,
        questionnaire=_questionnaire(feedback),
        metric_scores=metric_scores,
        created_at=created_at,
        prompts=result_prompts,
    )
