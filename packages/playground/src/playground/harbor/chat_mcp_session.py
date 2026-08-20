"""Drive MCP-backed chatbot sidecars from the Harbor main container."""

from __future__ import annotations

import asyncio
import json
import shlex
import textwrap
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

import tomllib

from playground.chatbot_task_config import ChatbotTaskConfig
from playground.harbor.chat_sidecar_io import parse_json_stdout
from playground.types import PlaygroundConfig

if TYPE_CHECKING:
    from harbor.environments.base import BaseEnvironment

_MCP_CALL_SCRIPT = textwrap.dedent(
    """
    import asyncio
    import json
    import sys

    async def main() -> None:
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        mcp_url = sys.argv[1]
        tool_name = sys.argv[2]
        arguments = json.loads(sys.argv[3])
        async with streamable_http_client(mcp_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                chunks = []
                for block in result.content or []:
                    text = getattr(block, "text", None)
                    if text:
                        chunks.append(text)
                payload = {
                    "text": "".join(chunks),
                    "isError": bool(
                        getattr(result, "is_error", getattr(result, "isError", False))
                    ),
                }
                print(json.dumps(payload))

    asyncio.run(main())
    """
).strip()


def harbor_chat_mcp_url_from_task_path(task_path: str, *, repo_root: Path) -> str | None:
    """Read the first ``environment.mcp_servers[].url`` from a task's ``task.toml``."""
    normalized = task_path.strip().replace("\\", "/").strip("/")
    if not normalized:
        return None
    toml_path = repo_root / normalized / "task.toml"
    if not toml_path.is_file():
        return None
    raw = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    env = raw.get("environment") if isinstance(raw.get("environment"), dict) else {}
    servers = env.get("mcp_servers")
    if not isinstance(servers, list) or not servers:
        return None
    first = servers[0] if isinstance(servers[0], dict) else {}
    url = str(first.get("url") or "").strip()
    return url or None


class HarborMcpChatSession:
    """Drive an MCP chat sidecar via ``environment.exec`` + ``uvx --with mcp``."""

    def __init__(
        self,
        environment: "BaseEnvironment",
        config: PlaygroundConfig,
        *,
        runtime: ChatbotTaskConfig,
        mcp_url: str,
        send_message_tool: str = "send_message",
        history_tool: str = "get_conversation_history",
    ) -> None:
        self._environment = environment
        self.config = config
        self.runtime = runtime
        self._mcp_url = mcp_url.rstrip("/")
        self._send_message_tool = send_message_tool
        self._history_tool = history_tool
        self._session_id = "mcp-{}".format(uuid.uuid4().hex[:12])
        self.turns: List[Dict[str, Any]] = []

    async def _call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        timeout_sec: int = 200,
    ) -> Dict[str, Any]:
        command = "uvx --with mcp python3 -c {} {} {} {}".format(
            shlex.quote(_MCP_CALL_SCRIPT),
            shlex.quote(self._mcp_url),
            shlex.quote(tool_name),
            shlex.quote(json.dumps(arguments, ensure_ascii=False)),
        )
        last_error = ""
        for attempt in range(3):
            result = await self._environment.exec(command, timeout_sec=timeout_sec)
            if result.return_code == 0:
                parsed = parse_json_stdout((result.stdout or "").strip())
                if parsed.get("isError"):
                    raise RuntimeError(
                        "chat MCP tool {} returned an error: {}".format(
                            tool_name,
                            parsed.get("text") or "unknown error",
                        )
                    )
                return parsed
            last_error = (result.stderr or result.stdout or "").strip()
            transient = any(
                token in last_error
                for token in (
                    "ConnectError",
                    "RemoteProtocolError",
                    "Connection refused",
                    "Server disconnected",
                )
            )
            if not transient or attempt == 2:
                break
            await asyncio.sleep(1.0 * (attempt + 1))
        raise RuntimeError(
            "chat MCP tool call failed ({}): {}".format(tool_name, last_error)
        )

    async def run_turn_sync(self, message: str) -> Dict[str, Any]:
        result = await self._call_tool(
            self._send_message_tool,
            {"message": message},
        )
        assistant = str(result.get("text") or "").strip()
        view = {
            "assistantMessage": assistant,
            "userMessage": message,
            "structuredExposure": [],
        }
        self.turns.append(view)
        return view

    @property
    def session_id(self) -> str:
        return self._session_id

    async def fetch_conversation_artifact(self) -> Dict[str, Any]:
        result = await self._call_tool(self._history_tool, {})
        raw_text = str(result.get("text") or "").strip()
        if not raw_text:
            raise RuntimeError("MCP get_conversation_history returned empty response")
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "MCP conversation history is not valid JSON: {}".format(raw_text[:500])
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError("MCP conversation history must be a JSON object")
        if "turns" not in payload and self.turns:
            payload["turns"] = [
                {
                    "turnIndex": index + 1,
                    "userMessage": turn["userMessage"],
                    "assistantMessage": turn["assistantMessage"],
                }
                for index, turn in enumerate(self.turns)
            ]
        return payload
