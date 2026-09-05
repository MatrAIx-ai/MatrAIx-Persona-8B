"""Chat sidecar URLs that Modal / GKE workers can actually call.

Production sets ``CHATBOT_API_URL`` (or a task-specific upstream) to a public
or VPC-reachable endpoint. Local sidecars on ``127.0.0.1`` are invisible from
those workers. Dev can expose the sidecar with a tunnel and set
``MATRIX_CHATBOT_PUBLIC_URL``.
"""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

CHATBOT_PUBLIC_URL_ENV = "MATRIX_CHATBOT_PUBLIC_URL"
CHATBOT_URL_ENV_KEYS = (
    "CHATBOT_API_URL",
    "CHATBOT_UPSTREAM_FINANCE",
    "CHATBOT_UPSTREAM_MEDICAL",
    "FINANCE_CHATBOT_URL",
    "MEDICAL_CHATBOT_URL",
    "CHATBOT_MCP_URL",
)

_LOOPBACK_HOSTS = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "::1",
        "[::1]",
        "0.0.0.0",
        "[::]",
        "host.docker.internal",
    }
)

_CLOUD_CHAT_ERROR = (
    "Chat on Modal/GKE needs a chatbot URL the worker can reach. "
    "Set CHATBOT_API_URL (or the task upstream) to a public endpoint, "
    "or set {public_env}, or set MATRIX_CHATBOT_TUNNEL=auto so Playground "
    "can start cloudflared (`brew install cloudflared`). "
    "Or run with computeFamily=local."
).format(public_env=CHATBOT_PUBLIC_URL_ENV)


def is_loopback_chatbot_url(url: str) -> bool:
    raw = (url or "").strip()
    if not raw:
        return False
    host = (urlparse(raw).hostname or "").strip().lower()
    if not host:
        return False
    if host in _LOOPBACK_HOSTS or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return bool(ip.is_loopback or ip.is_unspecified or ip.is_link_local)


def public_chatbot_url() -> str:
    return (os.environ.get(CHATBOT_PUBLIC_URL_ENV) or "").strip().rstrip("/")


def rewrite_chatbot_urls_for_cloud(env: dict[str, str]) -> dict[str, str]:
    """Replace loopback sidecar URLs with ``MATRIX_CHATBOT_PUBLIC_URL`` when set."""
    public = public_chatbot_url()
    rewritten = dict(env)
    if not public:
        return rewritten
    for key in CHATBOT_URL_ENV_KEYS:
        value = (rewritten.get(key) or "").strip()
        if value and is_loopback_chatbot_url(value):
            rewritten[key] = public
    if not any((rewritten.get(key) or "").strip() for key in CHATBOT_URL_ENV_KEYS):
        rewritten["CHATBOT_API_URL"] = public
    return rewritten


def collect_chatbot_url_env() -> dict[str, str]:
    payload = {
        key: value
        for key in CHATBOT_URL_ENV_KEYS
        if (value := (os.environ.get(key) or "").strip())
    }
    return rewrite_chatbot_urls_for_cloud(payload)


def _chatbot_worker_urls() -> list[str]:
    env = collect_chatbot_url_env()
    return [env[key] for key in CHATBOT_URL_ENV_KEYS if env.get(key)]


def require_cloud_reachable_chatbot_url() -> None:
    """Raise if a Modal/GKE chat worker would only see localhost.

    Set ``MATRIX_CHATBOT_PUBLIC_URL`` or ``MATRIX_CHATBOT_TUNNEL=auto``.
    """
    urls = _chatbot_worker_urls()
    if urls and not any(is_loopback_chatbot_url(url) for url in urls):
        return
    from backend.service.chatbot_dev_tunnel import ChatbotTunnelError, ensure_dev_chatbot_tunnel

    try:
        ensure_dev_chatbot_tunnel()
    except ChatbotTunnelError as exc:
        raise ValueError(str(exc)) from exc
    urls = _chatbot_worker_urls()
    if not urls or any(is_loopback_chatbot_url(url) for url in urls):
        raise ValueError(_CLOUD_CHAT_ERROR)
