from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic import ValidationError

from playground.uxagent.models import (
    VoiceLabAgentChatRequest,
    VoiceLabAgentChatResponse,
    VoiceLabPersonaSessionRequest,
)


_DEFAULT_BASE_URL = "http://localhost:3001"
_SESSION_PATH = "/api/persona/session"
_CHAT_PATH = "/api/agent/chat"


class VoiceLabContractError(RuntimeError):
    """Raised when VoiceLab cannot satisfy the client contract."""


class VoiceLabPersonaClient:
    """Strict, non-retrying asynchronous client for VoiceLab persona APIs."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        app_password: str | None = None,
        timeout_seconds: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        configured_base_url = (
            base_url or os.getenv("VOICELAB_API_URL") or _DEFAULT_BASE_URL
        )
        self._base_url = configured_base_url.rstrip("/")
        self._app_password = (
            app_password
            if app_password is not None
            else os.getenv("APP_PASSWORD", "")
        )
        self._http_client = http_client or httpx.AsyncClient(
            base_url=f"{self._base_url}/",
            timeout=timeout_seconds,
        )
        self._owns_http_client = http_client is None

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self._app_password:
            headers["x-app-password"] = self._app_password
        return headers

    async def _post(
        self, operation: str, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            response = await self._http_client.post(
                f"{self._base_url}{path}",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError:
            raise VoiceLabContractError(
                f"{operation} POST {path} failed"
            ) from None
        except ValueError:
            raise VoiceLabContractError(
                f"{operation} POST {path} returned invalid JSON"
            ) from None

        if not isinstance(body, dict):
            raise VoiceLabContractError(
                f"{operation} POST {path} returned a non-object JSON body"
            )
        return body

    async def create_session(self, request: VoiceLabPersonaSessionRequest) -> str:
        body = await self._post(
            "create_session",
            _SESSION_PATH,
            request.model_dump(exclude_none=True),
        )
        active = body.get("active")
        if not isinstance(active, dict) or active.get("sessionId") != request.sessionId:
            raise VoiceLabContractError(
                f"create_session POST {_SESSION_PATH} returned an invalid active session"
            )
        return request.sessionId

    async def agent_chat(
        self, request: VoiceLabAgentChatRequest
    ) -> VoiceLabAgentChatResponse:
        body = await self._post("agent_chat", _CHAT_PATH, request.model_dump())
        try:
            return VoiceLabAgentChatResponse.model_validate(body)
        except ValidationError:
            raise VoiceLabContractError(
                f"agent_chat POST {_CHAT_PATH} returned an invalid response"
            ) from None

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()
