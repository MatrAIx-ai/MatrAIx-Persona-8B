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


_SESSION_PATH = "/api/persona/session"
_CHAT_PATH = "/v1/agent/chat"


class VoiceLabContractError(RuntimeError):
    """Raised when VoiceLab cannot satisfy the client contract."""


class VoiceLabPersonaClient:
    """Strict, non-retrying asynchronous client for VoiceLab persona APIs."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        bearer_token: str | None = None,
        timeout_seconds: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        configured_base_url = base_url or os.getenv("VITA_AGENT_API_URL")
        if not configured_base_url:
            raise ValueError("VITA_AGENT_API_URL is required")
        configured_bearer_token = bearer_token or os.getenv("VITA_AGENT_BEARER_TOKEN")
        if not configured_bearer_token:
            raise ValueError("VITA_AGENT_BEARER_TOKEN is required")
        self._base_url = configured_base_url.rstrip("/")
        self._bearer_token = configured_bearer_token
        self._http_client = http_client or httpx.AsyncClient(
            base_url=f"{self._base_url}/",
            timeout=timeout_seconds,
        )
        self._owns_http_client = http_client is None

    def _headers(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "Authorization": f"Bearer {self._bearer_token}",
        }

    async def _post(
        self, operation: str, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        contract_error: VoiceLabContractError | None = None
        try:
            response = await self._http_client.post(
                f"{self._base_url}{path}",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError:
            contract_error = VoiceLabContractError(f"{operation} POST {path} failed")
        except ValueError:
            contract_error = VoiceLabContractError(
                f"{operation} POST {path} returned invalid JSON"
            )

        if contract_error is not None:
            raise contract_error
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
        validation_error: VoiceLabContractError | None = None
        try:
            response = VoiceLabAgentChatResponse.model_validate(body)
        except ValidationError:
            validation_error = VoiceLabContractError(
                f"agent_chat POST {_CHAT_PATH} returned an invalid response"
            )

        if validation_error is not None:
            raise validation_error
        return response

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()
