"""Shared Harbor launch environment for Playground and ``matraix run``.

Both launchers start ``harbor run`` processes that import monorepo packages
(``backend``, ``matraix.agents``, ``playground``, …). Keeping the required
``PYTHONPATH`` entries here prevents the GUI and CLI from drifting apart.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

# Relative to the repository root; "." is the root itself. Order matters:
# earlier entries win on import conflicts.
REQUIRED_PYTHONPATH_SUBDIRS: tuple[str, ...] = (
    ".",
    "src",
    "environment/runtime",
    "environment/agents",
    "packages/playground/src",
    "application/playground",
)

_REPO_ROOT_MARKER = Path("environment") / "runtime" / "harbor"


def required_pythonpath_entries(repo_root: Path | str) -> list[str]:
    """Absolute ``PYTHONPATH`` entries every Harbor launcher must inject."""
    root = Path(repo_root)
    return [
        str(root) if subdir == "." else str(root / subdir)
        for subdir in REQUIRED_PYTHONPATH_SUBDIRS
    ]


def merge_pythonpath(existing: str | None, repo_root: Path | str) -> str:
    """Prepend the required entries to ``existing``, deduplicated."""
    entries = [entry for entry in (existing or "").split(os.pathsep) if entry]
    for path in reversed(required_pythonpath_entries(repo_root)):
        if path not in entries:
            entries.insert(0, path)
    return os.pathsep.join(entries)


def build_launch_env(
    repo_root: Path | str,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return ``base_env`` (default: ``os.environ``) with ``PYTHONPATH`` set.

    Pass ``base_env={}`` for remote dispatch payloads that must not inherit
    the local process environment.
    """
    env = dict(os.environ if base_env is None else base_env)
    env["PYTHONPATH"] = merge_pythonpath(env.get("PYTHONPATH"), repo_root)
    return env


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default: cwd) to the MatrAIx repository root."""
    origin = (start or Path.cwd()).resolve()
    for candidate in (origin, *origin.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / _REPO_ROOT_MARKER
        ).is_dir():
            return candidate
    # Editable installs place this module at <root>/src/matraix/launch_env.py.
    fallback = Path(__file__).resolve().parents[2]
    if (fallback / _REPO_ROOT_MARKER).is_dir():
        return fallback
    raise FileNotFoundError(
        "Could not locate the MatrAIx repository root from "
        f"{origin}. Run inside a repository checkout or pass --repo-root."
    )
