"""Probe and start local chatbot HTTP sidecars for Playground."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, assert_never

from backend.service.apple_container_sidecar import (
    AppleContainerStartError,
    start_apple_container,
)
from backend.service.chatbot_sidecar_catalog import (
    SIDECAR_SPECS,
    SidecarRuntime,
    SidecarSpec,
)
from playground.harbor.playground import _repo_root
from playground.inprocess.chatbot_eval import _sidecar_base_url

_SIDECAR_SPECS = SIDECAR_SPECS


@dataclass(frozen=True, slots=True)
class SidecarStartError(RuntimeError):
    command: tuple[str, ...]
    detail: str

    def __str__(self) -> str:
        return "{}: {}".format(" ".join(self.command), self.detail)


def _default_health_url(spec: SidecarSpec) -> str:
    return "http://127.0.0.1:{}".format(spec.host_port)


def resolve_health_url(application_id: str) -> str:
    spec = _SIDECAR_SPECS.get(application_id)
    if spec is None:
        raise ValueError("unknown chatbot application: {}".format(application_id))
    if spec.application_id == "recai":
        return (
            os.environ.get(spec.primary_env, "").strip() or _default_health_url(spec)
        )
    if spec.application_id == "acme_support_mcp":
        return (
            os.environ.get(spec.primary_env, "").strip() or _default_health_url(spec)
        )
    if spec.application_id == "prescreening_assistant":
        # Scoped envs only - never the generic CHATBOT_API_URL fallback, which
        # belongs to recai and would silently point the probe at a different
        # sidecar when both are configured.
        return (
            os.environ.get(spec.primary_env, "").strip()
            or os.environ.get(spec.legacy_env or "", "").strip()
            or _default_health_url(spec)
        )
    if spec.application_id == "vita_climate":
        return os.environ.get(spec.primary_env, "").strip() or _default_health_url(spec)
    return _sidecar_base_url(
        spec.primary_env,
        spec.legacy_env or "",
        _default_health_url(spec),
    )


def sidecar_port_reachable(host: str, port: int, *, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _sidecar_probe_ok(spec: SidecarSpec, health_url: str, *, timeout: float = 5.0) -> bool:
    if spec.probe == "tcp":
        return sidecar_port_reachable("127.0.0.1", spec.host_port, timeout=timeout)
    return sidecar_reachable(health_url, timeout=timeout)


def _wait_for_sidecar_probe(
    spec: SidecarSpec,
    health_url: str,
    *,
    timeout_sec: float = 30.0,
) -> bool:
    deadline = time.monotonic() + timeout_sec
    # Medical /ready may cold-import heavy RAG deps on first call.
    probe_timeout = 10.0 if spec.application_id == "medical_assistant" else 5.0
    while time.monotonic() < deadline:
        if _sidecar_probe_ok(spec, health_url, timeout=probe_timeout):
            return True
        time.sleep(0.5)
    return False


def sidecar_reachable(base_url: str, *, timeout: float = 5.0) -> bool:
    """True when the sidecar answers ``GET /ready`` with 2xx (full capability ready).

    Prefer ``/ready`` over ``/health`` so Playground "Service up" means the chatbot
    can exercise its declared paths, not merely that the process is listening.
    """
    url = "{}/ready".format(base_url.rstrip("/"))
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            return 200 <= int(status) < 300
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _compose_project(application_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", application_id.lower()).strip("-")
    return "playground-{}".format(slug or "chatbot")


def _standalone_compose_path(spec: SidecarSpec, compose_dir: Path) -> Path:
    from playground.inprocess.chatbot_sidecar_compose import (
        write_standalone_sidecar_compose,
    )

    return write_standalone_sidecar_compose(
        compose_dir=compose_dir,
        service_name=spec.service_name,
        build_context=spec.build_context,
        host_port=spec.host_port,
    )


def sidecar_can_start(application_id: str) -> bool:
    spec = _SIDECAR_SPECS.get(application_id)
    if spec is None:
        return False
    match spec.runtime:
        case SidecarRuntime.DOCKER_COMPOSE:
            return bool(spec.compose_dir and spec.service_name and spec.build_context)
        case SidecarRuntime.APPLE_CONTAINER:
            return bool(spec.containerfile and spec.image_name and spec.service_name)
        case unreachable:
            assert_never(unreachable)


def sidecar_status(application_id: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    spec = _SIDECAR_SPECS.get(application_id)
    if spec is None:
        raise ValueError("unknown chatbot application: {}".format(application_id))
    health_url = resolve_health_url(application_id)
    probe_timeout = 10.0 if application_id == "medical_assistant" else 5.0
    ok = _sidecar_probe_ok(spec, health_url, timeout=probe_timeout)
    can_start = sidecar_can_start(application_id)
    service_label = "MCP server" if spec.probe == "tcp" else "Chat API"
    return {
        "applicationId": application_id,
        "ok": ok,
        "healthUrl": health_url,
        "canStart": can_start,
        "detail": (
            "{} ready at {}.".format(service_label, health_url)
            if ok
            else (
                "{} not ready at {}. Start the local sidecar to run this task.".format(
                    service_label,
                    health_url,
                )
                if can_start
                else "{} not ready at {}. Configure the upstream endpoint for this task.".format(
                    service_label,
                    health_url,
                )
            )
        ),
    }


def list_sidecar_statuses(*, repo_root: Path | None = None) -> list[dict[str, Any]]:
    return [sidecar_status(application_id, repo_root=repo_root) for application_id in _SIDECAR_SPECS]


def _run_required(
    command: list[str],
    *,
    root: Path,
    timeout_sec: int,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise SidecarStartError(tuple(command), str(exc)) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise SidecarStartError(tuple(command), detail)
    return result


def _start_docker_compose(spec: SidecarSpec, root: Path) -> None:
    if not spec.compose_dir or not spec.service_name or not spec.build_context:
        raise SidecarStartError(("docker", "compose"), "incomplete Compose sidecar spec")
    compose_dir = (root / spec.compose_dir).resolve()
    compose_path = _standalone_compose_path(spec, compose_dir)
    timeout_sec = 900 if spec.application_id in {"medical_assistant", "finance_openbb"} else 300
    _run_required(
        [
            "docker",
            "compose",
            "--project-name",
            _compose_project(spec.application_id),
            "--project-directory",
            str(compose_dir),
            "-f",
            str(compose_path),
            "up",
            "-d",
            "--build",
            spec.service_name,
        ],
        root=root,
        timeout_sec=timeout_sec,
    )


def start_sidecar(application_id: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    spec = _SIDECAR_SPECS.get(application_id)
    if spec is None:
        raise ValueError("unknown chatbot application: {}".format(application_id))
    if not sidecar_can_start(application_id):
        raise RuntimeError(
            "chatbot application {} does not provide a local startable sidecar".format(
                application_id
            )
        )

    root = repo_root or _repo_root()
    match spec.runtime:
        case SidecarRuntime.DOCKER_COMPOSE:
            _start_docker_compose(spec, root)
        case SidecarRuntime.APPLE_CONTAINER:
            try:
                start_apple_container(spec, root)
            except AppleContainerStartError as exc:
                raise SidecarStartError(exc.command, exc.detail) from exc
        case unreachable:
            assert_never(unreachable)

    health_url = resolve_health_url(application_id)
    wait_sec = 120.0 if application_id in {"medical_assistant", "finance_openbb"} else 30.0
    ok = _wait_for_sidecar_probe(spec, health_url, timeout_sec=wait_sec)
    status = sidecar_status(application_id, repo_root=root)
    status["started"] = True
    if not ok:
        service_label = "MCP server" if spec.probe == "tcp" else "sidecar"
        status["detail"] = (
            "{} started but capability readiness failed at {}. "
            "Check sidecar logs, then retry.".format(
                service_label.capitalize(),
                health_url,
            )
        )
    return status
