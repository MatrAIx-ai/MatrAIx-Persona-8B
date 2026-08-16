"""Host-native chat eval for the ``user_sim_chat`` Harbor trial profile."""

from __future__ import annotations

import base64
import json
import os
import shlex
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

from playground.chatbot_task_config import (
    ChatbotTaskConfig,
    load_chatbot_task_config_for_task_path,
)
from playground.harbor.chat_mcp_session import (
    HarborMcpChatSession,
    harbor_chat_mcp_url_from_task_path,
)
from playground.harbor.chat_sidecar_io import parse_json_stdout
from playground.inprocess.chatbot_eval import config_context
from playground.structured_exposure import (
    build_structured_exposure,
    normalize_transcript_payload,
)
from playground.task_content_bundle import (
    load_task_content_bundle_for_task_path,
)
from playground.persona_model import resolve_persona_model
from playground.types import (
    Persona,
    PlaygroundConfig,
    PlaygroundResult,
)

if TYPE_CHECKING:
    from harbor.environments.base import BaseEnvironment


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def harbor_chat_task_path_from_env() -> str | None:
    raw = os.environ.get("MATRIX_CHATBOT_TASK_PATH", "").strip()
    return raw.replace("\\", "/") or None


def harbor_chat_task_config_from_env(
    *, repo_root: Path | None
) -> ChatbotTaskConfig | None:
    if repo_root is None:
        return None
    task_path = harbor_chat_task_path_from_env()
    if not task_path:
        return None
    return load_chatbot_task_config_for_task_path(
        task_path,
        repo_root=repo_root,
    )


def harbor_chat_config_from_env(
    *,
    repo_root: Path | None = None,
    model_name: str | None = None,
) -> PlaygroundConfig:
    task_config = harbor_chat_task_config_from_env(repo_root=repo_root)
    runtime = task_config.runtime_defaults if task_config is not None else None
    protocol_static_body = (
        task_config.protocol.static_body if task_config is not None else {}
    )
    static_application_id = str(protocol_static_body.get("applicationId") or "").strip()
    static_application_context = str(
        protocol_static_body.get("applicationContext") or ""
    ).strip()
    static_domain = str(protocol_static_body.get("domain") or "").strip()

    application_id = (
        os.environ.get("MATRIX_CHATBOT_APPLICATION_ID", "").strip()
        or (runtime.application_id if runtime is not None else "")
        or static_application_id
        or "chatbot"
    )
    application_context = os.environ.get(
        "MATRIX_CHATBOT_APPLICATION_CONTEXT", ""
    ).strip() or (
        (runtime.application_context if runtime is not None else "")
        or static_application_context
    )
    domain = (
        os.environ.get("MATRIX_CHATBOT_DOMAIN", "").strip()
        or (runtime.domain if runtime is not None else "")
        or static_domain
    )
    max_turns_raw = os.environ.get("MATRIX_CHATBOT_MAX_TURNS", "").strip()
    try:
        max_turns = max(1, int(max_turns_raw)) if max_turns_raw else None
    except ValueError:
        max_turns = None
    persona_model = resolve_persona_model(
        model_name=model_name,
        include_chat_env=True,
    )
    engine = (
        os.environ.get("MATRIX_CHATBOT_ENGINE", "gpt-4o-mini").strip()
        or "gpt-4o-mini"
    )
    resolved_context = application_context or domain or "chatbot"
    resolved_domain = domain
    return PlaygroundConfig(
        domain=resolved_domain,
        application_id=application_id,
        application_context=resolved_context,
        engine=engine,
        persona_model=persona_model,
        max_turns=max_turns,
    )


def default_chat_api_url(application_id: str) -> str:
    if application_id == "finance_openbb":
        return "http://finance-chatbot:8000"
    if application_id == "meal_planning_nutrition":
        return "http://meal-plan-api:8000"
    if application_id == "acme_support_api":
        return "http://support-api:8000"
    return "http://chatbot-api:8000"


def chat_api_url_from_env(
    application_id: str,
    *,
    task_config: ChatbotTaskConfig | None = None,
) -> str:
    if task_config is not None:
        resolved = task_config.connection.resolve_base_url(os.environ)
        if resolved:
            return resolved
    return (
        os.environ.get("MATRIX_CHATBOT_API_URL", "").strip()
        or default_chat_api_url(application_id)
    )


def _fallback_sut_description(domain: str) -> str:
    label = str(domain or "").replace("_", " ").strip() or "chatbot"
    return "You are chatting with an interactive {} application.".format(label)


def _eval_persona(persona: object) -> Persona:
    data = getattr(persona, "data", {}) or {}
    return Persona(
        id=str(getattr(persona, "persona_id", None) or data.get("persona_id") or "persona"),
        name=str(getattr(persona, "display_name", None) or data.get("name") or "Persona"),
        summary=str(getattr(persona, "summary", None) or data.get("summary") or ""),
        context=str(
            getattr(persona, "system_prompt", None)
            or data.get("context")
            or getattr(persona, "summary", "")
            or ""
        ),
        source=str(data.get("source") or ""),
    )


def _normalize_turn_view(
    response: Dict[str, Any],
    user_message: str,
    runtime: ChatbotTaskConfig,
) -> Dict[str, Any]:
    protocol = runtime.protocol
    turn = dict(response.get(protocol.response_turn_field) or {})
    assistant = str(
        turn.get("assistantMessage")
        or turn.get("assistantReply")
        or response.get(protocol.response_reply_field)
        or ""
    )
    merged = {**response, **turn, "userMessage": user_message}
    exposure = build_structured_exposure(merged, runtime.structured_exposure)
    return {
        "assistantMessage": assistant,
        "userMessage": user_message,
        "structuredExposure": exposure,
    }


class HarborSidecarChatSession:
    """Drive a chat sidecar from the Harbor main container via ``environment.exec``."""

    def __init__(
        self,
        environment: "BaseEnvironment",
        config: PlaygroundConfig,
        *,
        runtime: ChatbotTaskConfig,
        api_url: str,
    ) -> None:
        self._environment = environment
        self.config = config
        self.runtime = runtime
        self._api_url = api_url.rstrip("/")
        self._session_id: Optional[str] = None
        self.turns: List[Dict[str, Any]] = []

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: Optional[Dict[str, Any]] = None,
        timeout_sec: int = 200,
    ) -> Dict[str, Any]:
        import asyncio

        url = "{}{}".format(self._api_url, path)
        payload = json.dumps(body or {}, ensure_ascii=False, separators=(",", ":"))
        encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
        script = textwrap.dedent(
            """
            import base64, json, urllib.error, urllib.request
            body = base64.b64decode({encoded!r})
            req = urllib.request.Request(
                {url!r},
                data=body if {method!r} != "GET" else None,
                headers={{"Content-Type": "application/json", "Accept": "application/json"}},
                method={method!r},
            )
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    print(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise SystemExit("HTTP {{}}: {{}}".format(exc.code, detail)) from exc
            """
        ).format(encoded=encoded, url=url, method=method)
        command = "python3 -c {}".format(shlex.quote(script.strip()))
        # Retry transient sidecar/upstream failures (e.g. OpenAI connection blips
        # under batch concurrency) instead of failing the whole trial.
        attempts = 3 if method.upper() == "POST" else 1
        last_detail = ""
        for attempt in range(attempts):
            result = await self._environment.exec(command, timeout_sec=timeout_sec)
            if result.return_code == 0:
                return parse_json_stdout((result.stdout or "").strip())
            last_detail = (result.stderr or result.stdout or "").strip()
            transient = any(
                token in last_detail.lower()
                for token in (
                    "http 503",
                    "connection error",
                    "timed out",
                    "timeout",
                    "temporarily unavailable",
                    "rate limit",
                )
            )
            if attempt + 1 >= attempts or not transient:
                break
            await asyncio.sleep(min(6.0, 0.8 * (2**attempt)))
        raise RuntimeError(
            "chat sidecar request failed ({} {}): {}".format(
                method, path, last_detail
            )
        )

    async def run_turn_sync(self, message: str) -> Dict[str, Any]:
        protocol = self.runtime.protocol
        context_value = config_context(self.config)
        body: Dict[str, Any] = dict(protocol.static_body)
        if protocol.session_id_field:
            body[protocol.session_id_field] = self._session_id
        if protocol.message_field:
            body[protocol.message_field] = message
        if protocol.title_field:
            body[protocol.title_field] = "playground"
        if protocol.bot_type_field:
            body[protocol.bot_type_field] = "chat"
        if protocol.engine_field and self.config.engine:
            body[protocol.engine_field] = self.config.engine
        if protocol.domain_field and context_value:
            body[protocol.domain_field] = context_value
        if protocol.context_field:
            body[protocol.context_field] = context_value
        response = await self._request_json(protocol.method, protocol.path, body=body)
        session_id = response.get(protocol.response_session_id_field)
        if session_id:
            self._session_id = str(session_id)
        view = _normalize_turn_view(response, message, self.runtime)
        self.turns.append(view)
        return view

    async def run_capability_sync(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        from playground.chatbot_capabilities import capability_by_tool

        capability = capability_by_tool(self.runtime.capabilities, tool_name)
        if capability is None or capability.http is None or not capability.http.path:
            fallback = str(
                arguments.get("text")
                or arguments.get("message")
                or "[Used tool `{}`]".format(tool_name)
            )
            return await self.run_turn_sync(fallback)

        context_value = config_context(self.config)
        body: Dict[str, Any] = dict(self.runtime.protocol.static_body)
        if self._session_id:
            body["sessionId"] = self._session_id
        if tool_name == "upload_image":
            body["imagePath"] = str(arguments.get("image_path") or "")
            body["text"] = str(arguments.get("text") or "")
            user_message = str(arguments.get("text") or "").strip() or "[Uploaded image]"
        elif tool_name == "validate_output":
            body["validationResult"] = str(arguments.get("validation_result") or "yes")
            body["comments"] = str(arguments.get("comments") or "")
            user_message = "[Validation: {}]".format(body["validationResult"])
        else:
            body.update({key: value for key, value in arguments.items() if value is not None})
            user_message = "[Used tool `{}`]".format(tool_name)
        if self.runtime.protocol.context_field:
            body[self.runtime.protocol.context_field] = context_value
        body.setdefault("applicationId", self.config.application_id)
        body.setdefault("applicationContext", context_value)

        response = await self._request_json(
            capability.http.method,
            capability.http.path,
            body=body,
        )
        session_id = response.get(self.runtime.protocol.response_session_id_field)
        if session_id:
            self._session_id = str(session_id)
        view = _normalize_turn_view(response, user_message, self.runtime)
        self.turns.append(view)
        return view

    @property
    def session_id(self) -> str:
        return self._session_id or ""

    async def fetch_conversation_artifact(self) -> Dict[str, Any]:
        query = (
            "?{}".format(urlencode({"sessionId": self._session_id}))
            if self._session_id
            else ""
        )
        return await self._request_json("GET", "/v1/conversation{}".format(query))


HarborChatSession = HarborSidecarChatSession | HarborMcpChatSession


def _uses_mcp_transport(runtime: ChatbotTaskConfig) -> bool:
    return runtime.transport.strip().lower() == "mcp"


def _mcp_path_suffix(task_path: str | None, *, repo_root: Path) -> str:
    """Return the MCP HTTP path suffix from task metadata (defaults to ``/mcp``)."""
    from urllib.parse import urlparse

    url = harbor_chat_mcp_url_from_task_path(task_path or "", repo_root=repo_root) or ""
    if not url:
        return "/mcp"
    path = urlparse(url).path.rstrip("/")
    return path or "/mcp"


def _local_mcp_sidecar_url(application_id: str) -> str | None:
    """Use a cockpit-started local MCP sidecar when trial markers are unavailable."""
    import os
    import socket
    from urllib.parse import urlparse

    defaults: dict[str, tuple[str, str]] = {
        "acme_support_mcp": ("CHATBOT_MCP_URL", "http://127.0.0.1:8903"),
    }
    spec = defaults.get(application_id.strip())
    if spec is None:
        return None
    env_key, default_base = spec
    base = os.environ.get(env_key, "").strip() or default_base
    parsed = urlparse(base if "://" in base else "http://{}".format(base))
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8903
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return "http://{}:{}/mcp".format(host, port)
    except OSError:
        return None


def _resolve_harbor_mcp_url(
    *,
    application_id: str,
    task_path: str | None,
    repo_root: Path,
    trial_dir: Path,
) -> str:
    """Resolve the MCP endpoint for Docker trials and host-native sidecars."""
    mcp_marker = trial_dir / ".sidecar_mcp_url"
    if mcp_marker.is_file():
        explicit = mcp_marker.read_text(encoding="utf-8").strip()
        if explicit:
            return explicit

    api_marker = trial_dir / ".sidecar_api_url"
    if api_marker.is_file():
        base = api_marker.read_text(encoding="utf-8").strip().rstrip("/")
        if base:
            return base + _mcp_path_suffix(task_path, repo_root=repo_root)

    local_url = _local_mcp_sidecar_url(application_id)
    if local_url:
        return local_url

    return harbor_chat_mcp_url_from_task_path(task_path or "", repo_root=repo_root) or ""


def create_harbor_chat_session(
    environment: "BaseEnvironment",
    config: PlaygroundConfig,
    *,
    runtime: ChatbotTaskConfig,
    task_path: str | None,
    repo_root: Path,
    trial_dir: Path,
) -> HarborChatSession:
    if _uses_mcp_transport(runtime):
        mcp_url = _resolve_harbor_mcp_url(
            application_id=config.application_id,
            task_path=task_path,
            repo_root=repo_root,
            trial_dir=trial_dir,
        )
        if not mcp_url:
            raise RuntimeError(
                "chatbot task declares transport=mcp but no MCP server URL was found"
            )
        return HarborMcpChatSession(environment, config, runtime=runtime, mcp_url=mcp_url)

    api_url = chat_api_url_from_env(config.application_id, task_config=runtime)
    marker = trial_dir / ".sidecar_api_url"
    if marker.is_file():
        api_url = marker.read_text(encoding="utf-8").strip() or api_url
    return HarborSidecarChatSession(environment, config, runtime=runtime, api_url=api_url)


def harbor_output_artifacts_from_result(
    result: PlaygroundResult,
    *,
    session_id: str,
    transcript_payload: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    application_context = result.config.application_context or result.config.domain
    application_result_payload = {
        "sessionId": session_id,
        "applicationId": result.config.application_id,
        "applicationContext": application_context,
        "turnCount": len(result.transcript),
    }
    return {
        "transcript.json": transcript_payload,
        "application_result.json": application_result_payload,
        "user_feedback.json": result.questionnaire.artifact_dict(),
    }


async def _write_output_artifacts(
    environment: "BaseEnvironment",
    *,
    session: HarborChatSession,
    result: PlaygroundResult,
) -> None:
    transcript_payload = await session.fetch_conversation_artifact()
    if not isinstance(transcript_payload, dict):
        raise RuntimeError("/v1/conversation must return a JSON object")
    transcript_payload = {
        **transcript_payload,
        "sessionId": str(
            transcript_payload.get("sessionId") or session.session_id or "harbor-chat"
        ),
        "applicationId": result.config.application_id,
        "applicationContext": result.config.application_context
        or result.config.domain,
        "domain": str(transcript_payload.get("domain") or "").strip()
        or result.config.domain
        or result.config.application_context,
    }
    transcript_payload = normalize_transcript_payload(
        transcript_payload,
        fields=session.runtime.structured_exposure,
    )
    artifacts = harbor_output_artifacts_from_result(
        result,
        session_id=session.session_id or "harbor-chat",
        transcript_payload=transcript_payload,
    )
    for filename, payload in artifacts.items():
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            temp_path = Path(handle.name)
        try:
            await environment.upload_file(temp_path, "/app/output/{}".format(filename))
        finally:
            temp_path.unlink(missing_ok=True)


async def run_harbor_chat_eval(
    session: HarborChatSession,
    persona: Persona,
    sut_description: str,
    config: PlaygroundConfig,
    *,
    created_at: str,
    on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    task_path: Optional[str] = None,
    persona_yaml_path: Optional[str] = None,
    repo_root: Optional[Any] = None,
    job_dir: Optional[Any] = None,
) -> PlaygroundResult:
    """Async chat eval loop using a Harbor sidecar session."""
    from playground.user_sim.runner import run_playground_async

    return await run_playground_async(
        session,
        persona,
        sut_description,
        config,
        created_at=created_at,
        on_event=on_event,
        task_path=task_path,
        persona_yaml_path=persona_yaml_path,
        repo_root=repo_root,
        job_dir=job_dir,
    )


async def run_harbor_chat_eval_for_persona(
    environment: "BaseEnvironment",
    persona: object,
    *,
    model_name: str | None = None,
    on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> tuple[PlaygroundResult, str]:
    """End-to-end Harbor chat eval for one loaded Harbor persona object."""
    from playground.harbor.playground import _repo_root

    repo_root = _repo_root()
    task_path = harbor_chat_task_path_from_env()
    runtime = harbor_chat_task_config_from_env(repo_root=repo_root) or ChatbotTaskConfig()
    bundle = (
        load_task_content_bundle_for_task_path(task_path, repo_root=repo_root)
        if task_path
        else None
    )
    config = harbor_chat_config_from_env(
        repo_root=repo_root,
        model_name=model_name,
    )
    eval_persona = _eval_persona(persona)
    sut_description = (
        (bundle.context_markdown if bundle is not None else "")
        or (bundle.instruction_markdown if bundle is not None else "")
        or _fallback_sut_description(config.application_context or config.domain)
    )
    session = create_harbor_chat_session(
        environment,
        config,
        runtime=runtime,
        task_path=task_path,
        repo_root=repo_root,
        trial_dir=environment.trial_paths.trial_dir,
    )
    persona_path = str(getattr(persona, "persona_path", "") or "") or None
    trial_dir = environment.trial_paths.trial_dir
    result = await run_harbor_chat_eval(
        session,
        eval_persona,
        sut_description,
        config,
        created_at=_utc_now(),
        on_event=on_event,
        task_path=task_path,
        persona_yaml_path=persona_path,
        repo_root=repo_root,
        job_dir=trial_dir.parent,
    )
    if on_event is not None:
        on_event({"type": "phase", "phase": "harbor_collecting_artifacts"})
    await _write_output_artifacts(environment, session=session, result=result)
    return result, session.session_id
