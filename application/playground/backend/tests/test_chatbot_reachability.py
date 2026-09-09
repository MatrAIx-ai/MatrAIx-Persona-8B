"""Tests for chatbot URLs that Modal / GKE workers can reach."""

from __future__ import annotations

import os

import pytest

from backend.service.chatbot_dev_tunnel import (
    CHATBOT_TUNNEL_ENV,
    ensure_dev_chatbot_tunnel,
    loopback_origin,
)
from backend.service.chatbot_reachability import (
    CHATBOT_PUBLIC_URL_ENV,
    is_loopback_chatbot_url,
    require_cloud_reachable_chatbot_url,
    rewrite_chatbot_urls_for_cloud,
)


def test_is_loopback_chatbot_url() -> None:
    assert is_loopback_chatbot_url("http://127.0.0.1:8905")
    assert is_loopback_chatbot_url("http://localhost:8000/v1")
    assert is_loopback_chatbot_url("http://host.docker.internal:8905")
    assert not is_loopback_chatbot_url("https://chat.example.com")
    assert not is_loopback_chatbot_url("http://10.0.0.8:8905")


def test_loopback_origin_maps_unspecified_to_localhost() -> None:
    assert loopback_origin("http://0.0.0.0:8905/v1") == "http://127.0.0.1:8905"
    assert loopback_origin("http://127.0.0.1:8905") == "http://127.0.0.1:8905"


def test_rewrite_replaces_loopback_with_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CHATBOT_PUBLIC_URL_ENV, "https://abc.ngrok-free.app")
    rewritten = rewrite_chatbot_urls_for_cloud(
        {"CHATBOT_API_URL": "http://127.0.0.1:8905"}
    )
    assert rewritten["CHATBOT_API_URL"] == "https://abc.ngrok-free.app"


def test_require_cloud_reachable_rejects_localhost_when_tunnel_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(CHATBOT_PUBLIC_URL_ENV, raising=False)
    monkeypatch.setenv(CHATBOT_TUNNEL_ENV, "0")
    monkeypatch.setenv("CHATBOT_API_URL", "http://127.0.0.1:8905")
    with pytest.raises(ValueError, match="localhost is not visible|needs a chatbot URL"):
        require_cloud_reachable_chatbot_url()


def test_require_cloud_reachable_defaults_to_no_tunnel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(CHATBOT_PUBLIC_URL_ENV, raising=False)
    monkeypatch.delenv(CHATBOT_TUNNEL_ENV, raising=False)
    monkeypatch.setenv("CHATBOT_API_URL", "http://127.0.0.1:8905")
    with pytest.raises(ValueError, match="needs a chatbot URL"):
        require_cloud_reachable_chatbot_url()


def test_require_cloud_reachable_accepts_public(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CHATBOT_PUBLIC_URL_ENV, raising=False)
    monkeypatch.setenv("CHATBOT_API_URL", "https://chat.prod.example")
    require_cloud_reachable_chatbot_url()


def test_ensure_dev_chatbot_tunnel_sets_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.service import chatbot_dev_tunnel as tunnel

    tunnel._tunnels.clear()
    monkeypatch.delenv(CHATBOT_PUBLIC_URL_ENV, raising=False)
    monkeypatch.setenv(CHATBOT_TUNNEL_ENV, "auto")
    monkeypatch.setenv("CHATBOT_API_URL", "http://127.0.0.1:8905")

    class _FakeProc:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

    def _fake_start(origin: str, **kwargs: object) -> tuple[str, _FakeProc]:
        assert origin == "http://127.0.0.1:8905"
        return "https://demo.trycloudflare.com", _FakeProc()

    monkeypatch.setattr(tunnel, "_start_tunnel", _fake_start)
    url = ensure_dev_chatbot_tunnel()
    assert url == "https://demo.trycloudflare.com"
    assert os.environ[CHATBOT_PUBLIC_URL_ENV] == url
    require_cloud_reachable_chatbot_url()
    tunnel._tunnels.clear()


def test_require_seeds_sidecar_url_then_tunnels(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.service import chatbot_dev_tunnel as tunnel
    from backend.service.chatbot_sidecar_service import ensure_sidecar_url_env

    tunnel._tunnels.clear()
    monkeypatch.delenv(CHATBOT_PUBLIC_URL_ENV, raising=False)
    monkeypatch.delenv("CHATBOT_API_URL", raising=False)
    monkeypatch.setenv(CHATBOT_TUNNEL_ENV, "auto")
    ensure_sidecar_url_env("meal_planning_nutrition")
    assert os.environ["CHATBOT_API_URL"] == "http://127.0.0.1:8905"

    class _FakeProc:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

    def _fake_start(origin: str, **kwargs: object) -> tuple[str, _FakeProc]:
        assert origin == "http://127.0.0.1:8905"
        return "https://demo.trycloudflare.com", _FakeProc()

    monkeypatch.setattr(tunnel, "_start_tunnel", _fake_start)
    require_cloud_reachable_chatbot_url()
    assert os.environ[CHATBOT_PUBLIC_URL_ENV] == "https://demo.trycloudflare.com"
    tunnel._tunnels.clear()
