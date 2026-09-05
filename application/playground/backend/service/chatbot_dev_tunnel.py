"""Public URL for a local chatbot sidecar (Modal/GKE chat).

Production already has ``CHATBOT_API_URL``. Local sidecars bind localhost, which
Modal and GKE cannot call. ``MATRIX_CHATBOT_TUNNEL=auto`` starts cloudflared or
ngrok and stores the URL in ``MATRIX_CHATBOT_PUBLIC_URL`` for this API process.
"""

from __future__ import annotations

import atexit
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Callable
from urllib.parse import urlparse

from backend.service.chatbot_reachability import (
    CHATBOT_PUBLIC_URL_ENV,
    CHATBOT_URL_ENV_KEYS,
    is_loopback_chatbot_url,
    public_chatbot_url,
)

logger = logging.getLogger(__name__)

CHATBOT_TUNNEL_ENV = "MATRIX_CHATBOT_TUNNEL"
_CLOUDFLARED_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)
_NGROK_URL_RE = re.compile(
    r"https://[a-z0-9.-]+\.ngrok(?:-free|-http)?\.(?:app|io)",
    re.I,
)

_lock = threading.Lock()
_tunnels: dict[str, tuple[subprocess.Popen[str], str]] = {}


class ChatbotTunnelError(RuntimeError):
    """Could not open a public tunnel to the local sidecar."""


def tunnel_mode() -> str:
    raw = (os.environ.get(CHATBOT_TUNNEL_ENV) or "off").strip().lower()
    if raw in {"", "0", "false", "no", "off", "disable", "disabled"}:
        return "off"
    if raw in {"ngrok"}:
        return "ngrok"
    if raw in {"cloudflared", "cloudflare"}:
        return "cloudflared"
    if raw in {"1", "true", "yes", "on", "enable", "enabled", "auto"}:
        return "auto"
    return "off"


def loopback_origin(url: str) -> str:
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "127.0.0.1").strip()
    if host in {"0.0.0.0", "[::]", "::"}:
        host = "127.0.0.1"
    port = parsed.port
    if port is None:
        port = 443 if (parsed.scheme or "http").lower() == "https" else 80
    return "http://{}:{}".format(host, port)


def first_loopback_chatbot_url() -> str:
    for key in CHATBOT_URL_ENV_KEYS:
        value = (os.environ.get(key) or "").strip()
        if is_loopback_chatbot_url(value):
            return value
    return ""


def ensure_dev_chatbot_tunnel(
    *,
    which: Callable[[str], str | None] = shutil.which,
    popen: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
) -> str:
    """Return a worker-reachable chatbot URL, starting a tunnel if needed."""
    existing = public_chatbot_url()
    if existing and not is_loopback_chatbot_url(existing):
        return existing
    if tunnel_mode() == "off":
        return ""
    local = first_loopback_chatbot_url()
    if not local:
        return ""
    origin = loopback_origin(local)
    with _lock:
        cached = _tunnels.get(origin)
        if cached is not None:
            proc, url = cached
            if proc.poll() is None:
                os.environ[CHATBOT_PUBLIC_URL_ENV] = url
                return url
            _tunnels.pop(origin, None)
        url, proc = _start_tunnel(origin, which=which, popen=popen)
        _tunnels[origin] = (proc, url)
        os.environ[CHATBOT_PUBLIC_URL_ENV] = url
        logger.info("Chat sidecar tunnel %s -> %s", origin, url)
        return url


def _start_tunnel(
    origin: str,
    *,
    which: Callable[[str], str | None],
    popen: Callable[..., subprocess.Popen[str]],
) -> tuple[str, subprocess.Popen[str]]:
    mode = tunnel_mode()
    errors: list[str] = []
    order = ("ngrok",) if mode == "ngrok" else ("cloudflared", "ngrok")
    if mode == "cloudflared":
        order = ("cloudflared",)
    for name in order:
        try:
            if name == "cloudflared":
                return _start_cloudflared(origin, which=which, popen=popen)
            return _start_ngrok(origin, which=which, popen=popen)
        except FileNotFoundError:
            errors.append("{} not on PATH".format(name))
        except ChatbotTunnelError as exc:
            errors.append(str(exc))
    hint = (
        "Install cloudflared (`brew install cloudflared`) so Playground can "
        "publish a URL to your local chat sidecar, or set {}, "
        "or use computeFamily=local."
    ).format(CHATBOT_PUBLIC_URL_ENV)
    detail = "; ".join(errors) if errors else "no tunnel backend"
    raise ChatbotTunnelError("{} ({})".format(hint, detail))


def _start_cloudflared(
    origin: str,
    *,
    which: Callable[[str], str | None],
    popen: Callable[..., subprocess.Popen[str]],
) -> tuple[str, subprocess.Popen[str]]:
    binary = which("cloudflared")
    if not binary:
        raise FileNotFoundError("cloudflared")
    proc = popen(
        [binary, "tunnel", "--url", origin, "--no-autoupdate"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url = _wait_for_url(proc, _CLOUDFLARED_URL_RE, timeout_sec=30.0)
    return url, proc


def _start_ngrok(
    origin: str,
    *,
    which: Callable[[str], str | None],
    popen: Callable[..., subprocess.Popen[str]],
) -> tuple[str, subprocess.Popen[str]]:
    binary = which("ngrok")
    if not binary:
        raise FileNotFoundError("ngrok")
    port = urlparse(origin).port or 80
    proc = popen(
        [binary, "http", str(port), "--log", "stdout", "--log-format", "json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url = _wait_for_url(proc, _NGROK_URL_RE, timeout_sec=30.0)
    return url, proc


def _wait_for_url(
    proc: subprocess.Popen[str],
    pattern: re.Pattern[str],
    *,
    timeout_sec: float,
) -> str:
    chunks: list[str] = []

    def _read() -> None:
        stream = proc.stdout
        if stream is None:
            return
        try:
            for line in stream:
                chunks.append(line)
        except Exception:
            return

    reader = threading.Thread(target=_read, name="chatbot-tunnel-log", daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        match = pattern.search("".join(chunks))
        if match:
            return match.group(0).rstrip("/")
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    log = "".join(chunks).strip()
    raise ChatbotTunnelError(
        "tunnel started but no public URL appeared{}".format(
            ": " + log[-400:] if log else ""
        )
    )


def _stop_tunnels() -> None:
    with _lock:
        items = list(_tunnels.values())
        _tunnels.clear()
    for proc, _url in items:
        try:
            proc.terminate()
        except Exception:
            pass


atexit.register(_stop_tunnels)
