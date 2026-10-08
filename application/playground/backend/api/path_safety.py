"""Guards for client-supplied names and paths that end up joined onto the repo."""

from __future__ import annotations

from typing import Optional

__all__ = ["is_safe_segment", "is_safe_relative_path", "check_task_path"]


def is_safe_segment(value: str) -> bool:
    """A single path component: non-empty, no separators, not ``.`` / ``..``."""
    if not value or value in {".", ".."}:
        return False
    return not any(ch in value for ch in ("/", "\\", "\x00"))


def is_safe_relative_path(value: str) -> bool:
    """A repo-relative path that cannot climb out via ``..`` segments."""
    if "\x00" in value:
        return False
    parts = value.replace("\\", "/").split("/")
    return ".." not in parts


def check_task_path(value: Optional[str]) -> Optional[str]:
    if value is not None and not is_safe_relative_path(value):
        raise ValueError("taskPath must stay inside the repository")
    return value
