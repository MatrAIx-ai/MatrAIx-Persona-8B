import asyncio
import json
import traceback
from collections.abc import Callable

import httpx
import pytest

from playground.uxagent.client import VoiceLabContractError, VoiceLabPersonaClient
from playground.uxagent.models import (
    VoiceLabAgentChatRequest,
    VoiceLabAgentChatResponse,
    VoiceLabPersonaSessionRequest,
)


SESSION_PATH = "/api/persona/session"
CHAT_PATH = "/api/agent/chat"
PASSWORD_SECRET = "password-secret"
PAYLOAD_SECRET = "payload-secret"


def _session_request(session_id: str = "session-123") -> VoiceLabPersonaSessionRequest:
    return VoiceLabPersonaSessionRequest(
        sessionId=session_id,
        driver={"name": "Alex", "persona": "A careful driver"},
        context={"roadSituation": "highway"},
        notes=["test note"],
    )


def _chat_request(session_id: str = "session-123") -> VoiceLabAgentChatRequest:
    return VoiceLabAgentChatRequest(
        message="Set the cabin to 22 degrees",
        drivingContext="driving",
        intent="climate",
        personaSessionId=session_id,
    )


def _json_response(payload: object, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def _client_for(
    handler: Callable[[httpx.Request], httpx.Response], *, base_url: str = "http://voicelab.test"
) -> tuple[VoiceLabPersonaClient, httpx.AsyncClient]:
    transport = httpx.MockTransport(handler)
    borrowed = httpx.AsyncClient(transport=transport)
    return (
        VoiceLabPersonaClient(
            base_url=base_url,
            app_password=PASSWORD_SECRET,
            http_client=borrowed,
        ),
        borrowed,
    )


def test_create_session_and_agent_chat_use_ordered_paths_wire_bodies_and_auth() -> None:
    seen: list[tuple[str, str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.headers["content-type"] == "application/json"
        assert request.headers["x-app-password"] == PASSWORD_SECRET
        seen.append((request.method, request.url.path, body))
        if request.url.path == SESSION_PATH:
            return _json_response({"active": {"sessionId": "session-123"}})
        return _json_response({"reply": "Done", "decision": "executed"})

    client, borrowed = _client_for(handler)
    try:
        session = asyncio.run(client.create_session(_session_request()))
        response = asyncio.run(client.agent_chat(_chat_request(session_id=session)))
    finally:
        asyncio.run(client.close())
        asyncio.run(borrowed.aclose())

    assert session == "session-123"
    assert isinstance(response, VoiceLabAgentChatResponse)
    assert response.reply == "Done"
    assert seen == [
        (
            "POST",
            SESSION_PATH,
            {
                "sessionId": "session-123",
                "source": "matraix-uxagent",
                "driver": {"name": "Alex", "persona": "A careful driver"},
                "context": {"roadSituation": "highway"},
                "notes": ["test note"],
            },
        ),
        (
            "POST",
            CHAT_PATH,
            {
                "message": "Set the cabin to 22 degrees",
                "drivingContext": "driving",
                "intent": "climate",
                "personaSessionId": "session-123",
            },
        ),
    ]


def test_blank_password_is_not_sent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "x-app-password" not in request.headers
        return _json_response({"active": {"sessionId": "session-123"}})

    transport = httpx.MockTransport(handler)
    borrowed = httpx.AsyncClient(transport=transport)
    client = VoiceLabPersonaClient(
        base_url="http://voicelab.test/",
        app_password="",
        http_client=borrowed,
    )
    try:
        assert asyncio.run(client.create_session(_session_request())) == "session-123"
    finally:
        asyncio.run(client.close())
        asyncio.run(borrowed.aclose())

@pytest.mark.parametrize(
    ("explicit", "env_password", "expected_header"),
    [
        ("explicit-password", "environment-password", "explicit-password"),
        (None, "environment-password", "environment-password"),
        ("", "environment-password", None),
    ],
)
def test_app_password_precedence_and_blank_suppression(
    monkeypatch: pytest.MonkeyPatch,
    explicit: str | None,
    env_password: str,
    expected_header: str | None,
) -> None:
    monkeypatch.setenv("APP_PASSWORD", env_password)
    seen_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("x-app-password"))
        return _json_response({"active": {"sessionId": "session-123"}})

    transport = httpx.MockTransport(handler)
    borrowed = httpx.AsyncClient(transport=transport)
    kwargs = {"app_password": explicit} if explicit is not None else {}
    client = VoiceLabPersonaClient(http_client=borrowed, **kwargs)
    try:
        asyncio.run(client.create_session(_session_request()))
    finally:
        asyncio.run(client.close())
        asyncio.run(borrowed.aclose())

    assert seen_headers == [expected_header]


@pytest.mark.parametrize(
    ("explicit", "env_url", "expected"),
    [
        ("http://explicit.test/", "http://environment.test", "http://explicit.test"),
        ("", "http://environment.test/", "http://environment.test"),
        (None, "http://environment.test/", "http://environment.test"),
        (None, None, "http://localhost:3001"),
    ],
)
def test_base_url_precedence_and_trailing_slash(
    monkeypatch: pytest.MonkeyPatch,
    explicit: str | None,
    env_url: str | None,
    expected: str,
) -> None:
    if env_url is None:
        monkeypatch.delenv("VOICELAB_API_URL", raising=False)
    else:
        monkeypatch.setenv("VOICELAB_API_URL", env_url)

    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return _json_response({"active": {"sessionId": "session-123"}})

    transport = httpx.MockTransport(handler)
    borrowed = httpx.AsyncClient(transport=transport)
    kwargs = {"base_url": explicit} if explicit is not None else {}
    client = VoiceLabPersonaClient(http_client=borrowed, **kwargs)
    try:
        asyncio.run(client.create_session(_session_request()))
    finally:
        asyncio.run(client.close())
        asyncio.run(borrowed.aclose())

    assert requested == [f"{expected}{SESSION_PATH}"]

def test_connect_error_is_redacted_and_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError(PAYLOAD_SECRET, request=request)

    client, borrowed = _client_for(handler)
    try:
        with pytest.raises(VoiceLabContractError) as raised:
            asyncio.run(client.create_session(_session_request()))
    finally:
        asyncio.run(client.close())
        asyncio.run(borrowed.aclose())

    rendered = "".join(traceback.format_exception(raised.value))
    assert calls == 1
    assert raised.value.__cause__ is None
    assert PAYLOAD_SECRET not in str(raised.value)
    assert PASSWORD_SECRET not in str(raised.value)
    assert PAYLOAD_SECRET not in rendered
    assert PASSWORD_SECRET not in rendered


@pytest.mark.parametrize("status_code", [400, 500])
def test_http_status_errors_are_typed_and_redacted(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"detail": PAYLOAD_SECRET})

    client, borrowed = _client_for(handler)
    try:
        with pytest.raises(VoiceLabContractError) as raised:
            asyncio.run(client.create_session(_session_request(PAYLOAD_SECRET)))
    finally:
        asyncio.run(client.close())
        asyncio.run(borrowed.aclose())

    message = str(raised.value)
    assert "create_session" in message
    assert SESSION_PATH in message
    assert PASSWORD_SECRET not in message
    assert PAYLOAD_SECRET not in message
    assert raised.value.__cause__ is None
    assert PAYLOAD_SECRET not in "".join(traceback.format_exception(raised.value))


def test_timeout_error_is_typed_and_redacted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(PAYLOAD_SECRET, request=request)

    client, borrowed = _client_for(handler)
    try:
        with pytest.raises(VoiceLabContractError) as raised:
            asyncio.run(client.create_session(_session_request()))
    finally:
        asyncio.run(client.close())
        asyncio.run(borrowed.aclose())

    assert "create_session" in str(raised.value)
    assert SESSION_PATH in str(raised.value)
    assert raised.value.__cause__ is None
    assert PAYLOAD_SECRET not in "".join(traceback.format_exception(raised.value))
    assert PAYLOAD_SECRET not in str(raised.value)
    assert PASSWORD_SECRET not in str(raised.value)


@pytest.mark.parametrize(
    "response_factory",
    [
        lambda: httpx.Response(200, content=b"not-json"),
        lambda: httpx.Response(200, json=["not", "an", "object"]),
        lambda: httpx.Response(200, json="not-an-object"),
    ],
)
def test_non_object_or_non_json_session_responses_are_typed(response_factory) -> None:
    client, borrowed = _client_for(lambda request: response_factory())
    try:
        with pytest.raises(VoiceLabContractError) as raised:
            asyncio.run(client.create_session(_session_request()))
    finally:
        asyncio.run(client.close())
        asyncio.run(borrowed.aclose())

    assert "create_session" in str(raised.value)
    assert SESSION_PATH in str(raised.value)
    assert PAYLOAD_SECRET not in str(raised.value)
    assert PASSWORD_SECRET not in str(raised.value)


def test_wrong_active_session_is_typed_and_redacted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({"active": {"sessionId": PAYLOAD_SECRET}})

    client, borrowed = _client_for(handler)
    try:
        with pytest.raises(VoiceLabContractError) as raised:
            asyncio.run(client.create_session(_session_request()))
    finally:
        asyncio.run(client.close())
        asyncio.run(borrowed.aclose())

    assert "create_session" in str(raised.value)
    assert SESSION_PATH in str(raised.value)
    assert PAYLOAD_SECRET not in str(raised.value)

@pytest.mark.parametrize("payload", [{}, {"active": []}, {"active": "not-an-object"}])
def test_missing_or_non_object_active_session_is_typed(payload: object) -> None:
    client, borrowed = _client_for(lambda request: _json_response(payload))
    try:
        with pytest.raises(VoiceLabContractError) as raised:
            asyncio.run(client.create_session(_session_request()))
    finally:
        asyncio.run(client.close())
        asyncio.run(borrowed.aclose())

    assert "create_session" in str(raised.value)
    assert SESSION_PATH in str(raised.value)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"reply": ""},
        {"reply": PAYLOAD_SECRET, "vehicleState": "not-an-object"},
    ],
)
def test_malformed_agent_responses_are_typed_and_redacted(payload: object) -> None:
    client, borrowed = _client_for(lambda request: _json_response(payload))
    try:
        with pytest.raises(VoiceLabContractError) as raised:
            asyncio.run(client.agent_chat(_chat_request()))
    finally:
        asyncio.run(client.close())
        asyncio.run(borrowed.aclose())

    assert "agent_chat" in str(raised.value)
    assert CHAT_PATH in str(raised.value)
    assert PAYLOAD_SECRET not in str(raised.value)
    assert PASSWORD_SECRET not in str(raised.value)
    assert raised.value.__cause__ is None
    assert PAYLOAD_SECRET not in "".join(traceback.format_exception(raised.value))


def test_borrowed_client_remains_open_after_close() -> None:
    borrowed = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: _json_response({})))
    client = VoiceLabPersonaClient(http_client=borrowed)

    asyncio.run(client.close())

    assert borrowed.is_closed is False
    asyncio.run(borrowed.aclose())


def test_owned_client_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class OwnedClient:
        def __init__(self, **kwargs: object) -> None:
            self.is_closed = False

        async def aclose(self) -> None:
            self.is_closed = True

    owned = OwnedClient()
    monkeypatch.setattr(
        "playground.uxagent.client.httpx.AsyncClient",
        lambda **kwargs: owned,
    )

    client = VoiceLabPersonaClient()
    asyncio.run(client.close())

    assert owned.is_closed is True
