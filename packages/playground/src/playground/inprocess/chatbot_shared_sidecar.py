"""Shared Playground chatbot sidecars for Harbor host trials.

Harbor host used to ``docker compose up`` a fresh stack per trial. Heavy
products (finance) then OOM under batch concurrency. Trials now
reuse the same fixed-port ``playground-<app>`` compose project that Cockpit
"Service up" starts, so a cohort shares one sidecar.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from playground.inprocess.chatbot_sidecar_compose import write_standalone_sidecar_compose


def _sidecar_base_url(primary_env: str, legacy_env: str, default: str) -> str:
    return (
        os.environ.get(primary_env)
        or os.environ.get(legacy_env)
        or os.environ.get("CHATBOT_API_URL")
        or default
    )


@dataclass(frozen=True)
class SharedSidecarSpec:
    application_id: str
    service_name: str
    build_context: str
    host_port: int
    primary_env: str
    legacy_env: str | None = None
    probe: Literal["http", "tcp"] = "http"
    container_port: int = 8000


# Prefer these names when a compose file lists multiple non-main services.
_PRIMARY_SERVICE_ORDER: tuple[str, ...] = (
    "finance-chatbot",
    "support-api",
    "support-bot",
    "meal-plan-api",
    "telco-support-api",
)

_SHARED_BY_SERVICE: dict[str, SharedSidecarSpec] = {
    "finance-chatbot": SharedSidecarSpec(
        application_id="finance_openbb",
        service_name="finance-chatbot",
        build_context="finance-chatbot",
        host_port=8901,
        primary_env="CHATBOT_UPSTREAM_FINANCE",
        legacy_env="FINANCE_CHATBOT_URL",
    ),
    "support-api": SharedSidecarSpec(
        application_id="acme_support_api",
        service_name="support-api",
        build_context="support-api",
        host_port=8904,
        primary_env="CHATBOT_API_URL",
    ),
    "support-bot": SharedSidecarSpec(
        application_id="acme_support_mcp",
        service_name="support-bot",
        build_context="support-bot",
        host_port=8903,
        primary_env="CHATBOT_MCP_URL",
        probe="tcp",
    ),
    "meal-plan-api": SharedSidecarSpec(
        application_id="meal_planning_nutrition",
        service_name="meal-plan-api",
        build_context="meal-plan-api",
        host_port=8905,
        primary_env="CHATBOT_API_URL",
    ),
    # Safe to share across a cohort: conversation state is session-scoped, so one
    # process serving many trials does not merge their transcripts.
    "telco-support-api": SharedSidecarSpec(
        application_id="multilingual_telco_support",
        service_name="telco-support-api",
        build_context="telco-support-api",
        host_port=8907,
        primary_env="CHATBOT_API_URL",
    ),
}


def pick_primary_sidecar_service(service_names: list[str]) -> str | None:
    if not service_names:
        return None
    for name in _PRIMARY_SERVICE_ORDER:
        if name in service_names:
            return name
    return service_names[0]


def shared_spec_for_service(service_name: str) -> SharedSidecarSpec | None:
    return _SHARED_BY_SERVICE.get(service_name)


def compose_project_name(application_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", application_id.lower()).strip("-")
    return "playground-{}".format(slug or "chatbot")


def shared_base_url(spec: SharedSidecarSpec) -> str:
    default = "http://127.0.0.1:{}".format(spec.host_port)
    if spec.application_id in {"acme_support_mcp", "acme_support_api"}:
        return os.environ.get(spec.primary_env, "").strip() or default
    return _sidecar_base_url(spec.primary_env, spec.legacy_env or "", default)


def sidecar_port_reachable(host: str, port: int, *, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def sidecar_ready(base_url: str, *, timeout: float = 5.0) -> bool:
    url = "{}/ready".format(base_url.rstrip("/"))
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            return 200 <= int(status) < 300
    except Exception:  # noqa: BLE001
        return False


def probe_shared_sidecar(spec: SharedSidecarSpec, *, timeout: float | None = None) -> bool:
    base = shared_base_url(spec)
    if timeout is None:
        timeout = 5.0
    if spec.probe == "tcp":
        return sidecar_port_reachable("127.0.0.1", spec.host_port, timeout=min(timeout, 2.0))
    return sidecar_ready(base, timeout=timeout)


def _wait_until_ready(spec: SharedSidecarSpec, *, timeout_sec: float) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if probe_shared_sidecar(spec):
            return True
        time.sleep(0.5)
    return False


def _flock_path(compose_dir: Path, application_id: str) -> Path:
    lock_dir = compose_dir / ".playground_sidecar"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / "shared-{}.lock".format(application_id)


def _with_file_lock(lock_path: Path, fn):  # noqa: ANN001
    try:
        import fcntl
    except ImportError:
        return fn()

    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            return fn()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def start_shared_sidecar(
    *,
    compose_dir: Path,
    spec: SharedSidecarSpec,
    force_build: bool = False,
) -> str:
    """Ensure the shared playground sidecar is up; return its base URL."""
    compose_dir = compose_dir.resolve()
    base_url = shared_base_url(spec)

    def _ensure() -> str:
        if probe_shared_sidecar(spec):
            return base_url

        compose_path = write_standalone_sidecar_compose(
            compose_dir=compose_dir,
            service_name=spec.service_name,
            build_context=spec.build_context,
            host_port=spec.host_port,
            container_port=spec.container_port,
        )
        command = [
            "docker",
            "compose",
            "--project-name",
            compose_project_name(spec.application_id),
            "--project-directory",
            str(compose_dir),
            "-f",
            str(compose_path),
            "up",
            "-d",
            spec.service_name,
        ]
        if force_build:
            command.append("--build")
        result = subprocess.run(
            command,
            cwd=str(compose_dir),
            capture_output=True,
            text=True,
            timeout=900 if spec.application_id == "finance_openbb" else 300,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(
                "failed to start shared chatbot sidecar {}: {}".format(
                    spec.application_id,
                    detail or "docker compose failed",
                )
            )

        wait_sec = 180.0 if spec.application_id == "finance_openbb" else 60.0
        if not _wait_until_ready(spec, timeout_sec=wait_sec):
            raise RuntimeError(
                "shared chatbot sidecar {} started but is not ready at {}".format(
                    spec.application_id,
                    base_url,
                )
            )
        return base_url

    return _with_file_lock(_flock_path(compose_dir, spec.application_id), _ensure)


def ensure_shared_sidecar_for_services(
    *,
    compose_dir: Path,
    service_names: list[str],
    force_build: bool = False,
) -> tuple[str, SharedSidecarSpec] | None:
    """If services map to a known shared sidecar, ensure it and return (url, spec)."""
    primary = pick_primary_sidecar_service(service_names)
    if primary is None:
        return None
    spec = shared_spec_for_service(primary)
    if spec is None:
        return None
    url = start_shared_sidecar(
        compose_dir=compose_dir,
        spec=spec,
        force_build=force_build,
    )
    return url, spec
