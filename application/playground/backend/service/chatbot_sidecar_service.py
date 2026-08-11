"""Probe and start local chatbot HTTP sidecars for Playground."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from playground.harbor.playground import _repo_root
from playground.inprocess.chatbot_eval import _sidecar_base_url


@dataclass(frozen=True)
class SidecarSpec:
    application_id: str
    compose_dir: str | None
    service_name: str | None
    build_context: str | None
    host_port: int
    primary_env: str
    legacy_env: str | None = None
    probe: Literal["http", "tcp"] = "http"


_SIDECAR_SPECS: dict[str, SidecarSpec] = {
    "finance_openbb": SidecarSpec(
        application_id="finance_openbb",
        compose_dir=(
            "environment/task-environments/application/chatbot-api-sidecar_openbb"
        ),
        service_name="finance-chatbot",
        build_context="finance-chatbot",
        host_port=8901,
        primary_env="CHATBOT_UPSTREAM_FINANCE",
        legacy_env="FINANCE_CHATBOT_URL",
    ),
    "acme_support_api": SidecarSpec(
        application_id="acme_support_api",
        compose_dir=(
            "environment/task-environments/application/chatbot-api-sidecar_acme-support-api"
        ),
        service_name="support-api",
        build_context="support-api",
        host_port=8904,
        primary_env="CHATBOT_API_URL",
        legacy_env=None,
    ),
    "acme_support_mcp": SidecarSpec(
        application_id="acme_support_mcp",
        compose_dir=(
            "environment/task-environments/application/chatbot-mcp-sidecar_acme-support"
        ),
        service_name="support-bot",
        build_context="support-bot",
        host_port=8903,
        primary_env="CHATBOT_MCP_URL",
        legacy_env=None,
        probe="tcp",
    ),
    "meal_planning_nutrition": SidecarSpec(
        application_id="meal_planning_nutrition",
        compose_dir=(
            "environment/task-environments/application/chatbot-api-sidecar_meal-plan-api"
        ),
        service_name="meal-plan-api",
        build_context="meal-plan-api",
        host_port=8905,
        primary_env="CHATBOT_API_URL",
        legacy_env=None,
    ),
    "multilingual_telco_support": SidecarSpec(
        application_id="multilingual_telco_support",
        compose_dir=(
            "environment/task-environments/application/"
            "chatbot-api-sidecar_multilingual-telco-support"
        ),
        service_name="telco-support-api",
        build_context="telco-support-api",
        host_port=8907,
        primary_env="CHATBOT_API_URL",
        legacy_env=None,
    ),
}


def _default_health_url(spec: SidecarSpec) -> str:
    return "http://127.0.0.1:{}".format(spec.host_port)


def resolve_health_url(application_id: str) -> str:
    spec = _SIDECAR_SPECS.get(application_id)
    if spec is None:
        raise ValueError("unknown chatbot application: {}".format(application_id))
    if spec.application_id == "acme_support_mcp":
        return (
            os.environ.get(spec.primary_env, "").strip() or _default_health_url(spec)
        )
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
    while time.monotonic() < deadline:
        if _sidecar_probe_ok(spec, health_url, timeout=5.0):
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
    except Exception:  # noqa: BLE001
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
    return bool(spec and spec.compose_dir and spec.service_name and spec.build_context)


def sidecar_status(application_id: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    spec = _SIDECAR_SPECS.get(application_id)
    if spec is None:
        raise ValueError("unknown chatbot application: {}".format(application_id))
    health_url = resolve_health_url(application_id)
    ok = _sidecar_probe_ok(spec, health_url, timeout=5.0)
    can_start = bool(spec.compose_dir and spec.service_name and spec.build_context)
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


def start_sidecar(application_id: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    spec = _SIDECAR_SPECS.get(application_id)
    if spec is None:
        raise ValueError("unknown chatbot application: {}".format(application_id))
    if not spec.compose_dir or not spec.service_name or not spec.build_context:
        raise RuntimeError(
            "chatbot application {} does not provide a local startable sidecar".format(
                application_id
            )
        )

    root = repo_root or _repo_root()
    compose_dir = (root / spec.compose_dir).resolve()
    compose_path = _standalone_compose_path(spec, compose_dir)
    command = [
        "docker",
        "compose",
        "--project-name",
        _compose_project(application_id),
        "--project-directory",
        str(compose_dir),
        "-f",
        str(compose_path),
        "up",
        "-d",
        "--build",
        spec.service_name,
    ]
    compose_timeout = 900 if application_id == "finance_openbb" else 300
    result = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=compose_timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            detail or "docker compose failed to start {}".format(application_id)
        )

    health_url = resolve_health_url(application_id)
    wait_sec = 120.0 if application_id == "finance_openbb" else 30.0
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
