"""Contract tests for the Acme support REST sidecar."""

from __future__ import annotations

import pytest

pytest.importorskip("flask")

import server  # noqa: E402


def test_post_message_returns_structured_turn() -> None:
    server._sessions.clear()
    client = server.app.test_client()

    response = client.post(
        "/v1/messages",
        json={"sessionId": "trial-a", "message": "Where is order #4521?"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["sessionId"] == "trial-a"
    assert payload["reply"]
    assert payload["turn"] == {
        "index": 1,
        "userMessage": "Where is order #4521?",
        "assistantReply": payload["reply"],
    }


def test_sessions_remain_isolated() -> None:
    server._sessions.clear()
    client = server.app.test_client()
    client.post(
        "/v1/messages",
        json={"sessionId": "trial-a", "message": "Order #4521 is late"},
    )
    client.post(
        "/v1/messages",
        json={"sessionId": "trial-b", "message": "Hello"},
    )

    first = client.get("/v1/conversation?sessionId=trial-a").get_json()
    second = client.get("/v1/conversation?sessionId=trial-b").get_json()

    assert len(first["messages"]) == 2
    assert len(second["messages"]) == 2
    assert first["messages"] != second["messages"]
