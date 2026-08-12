from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from backend.service.chatbot_sidecar_catalog import SidecarSpec


class AppleContainerStartError(RuntimeError):
    def __init__(self, command: list[str], detail: str) -> None:
        self.command = tuple(command)
        self.detail = detail
        super().__init__("{}: {}".format(" ".join(command), detail))


def _run_required(
    command: list[str],
    *,
    root: Path,
    timeout_sec: int,
) -> None:
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
        raise AppleContainerStartError(command, str(exc)) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise AppleContainerStartError(command, detail)


def start_apple_container(spec: SidecarSpec, root: Path) -> None:
    if not spec.containerfile or not spec.image_name or not spec.service_name:
        raise AppleContainerStartError(
            ["container"],
            "incomplete Apple Container sidecar spec",
        )
    _run_required(["container", "system", "start"], root=root, timeout_sec=120)
    vendor_dir = root / ".cache" / "vita-climate-sidecar" / "vendor"
    requirements = root / "environment/task-environments/application/vita-climate-sidecar/requirements.txt"
    shutil.rmtree(vendor_dir, ignore_errors=True)
    _run_required(
        [
            "uv",
            "pip",
            "install",
            "--python-platform",
            "aarch64-manylinux_2_17",
            "--python-version",
            "3.12",
            "--target",
            str(vendor_dir),
            "-r",
            str(requirements),
        ],
        root=root,
        timeout_sec=300,
    )
    try:
        build_command = [
            "container",
            "build",
            "-t",
            spec.image_name,
            "-f",
            str((root / spec.containerfile).resolve()),
            str(root.resolve()),
        ]
        _run_required(build_command, root=root, timeout_sec=900)
    finally:
        shutil.rmtree(vendor_dir.parent, ignore_errors=True)
    for command in (
        ["container", "stop", spec.service_name],
        ["container", "rm", spec.service_name],
    ):
        subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    _run_required(
        [
            "container",
            "run",
            "-d",
            "--name",
            spec.service_name,
            "-p",
            f"{spec.host_port}:8000",
            "-c",
            "2",
            "-m",
            "2048M",
            spec.image_name,
        ],
        root=root,
        timeout_sec=120,
    )
