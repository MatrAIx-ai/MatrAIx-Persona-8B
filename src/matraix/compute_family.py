"""Resolve Playground compute family to a Harbor environment (+ optional dispatch).

Users set ``computeFamily`` / ``MATRIX_COMPUTE_FAMILY`` (``local`` | ``modal`` | ``gcp``).
Harbor still receives a normal ``environment.type``. ``dispatch`` is set when
trials run on a cloud job runner (Modal Jobs / GKE workers), including web/linux
Docker workers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from matraix.gke_settings import gke_harbor_kwargs

COMPUTE_FAMILIES = frozenset({"local", "modal", "gcp"})
COMPUTE_FAMILY_ENV = "MATRIX_COMPUTE_FAMILY"
HOST_PACK_CONCURRENCY_ENV = "MATRIX_HOST_PACK_CONCURRENCY"
DEFAULT_HOST_PACK_CONCURRENCY = 32
_NATIVE_TRIAL_PROFILES = frozenset({"json_survey", "user_sim_chat"})


@dataclass(frozen=True)
class ComputePlan:
    family: str
    environment: str
    dispatch: str | None = None
    cua_pinned: bool = False
    environment_kwargs: dict[str, Any] | None = None

    def harbor_environment(self) -> dict[str, Any]:
        block: dict[str, Any] = {"type": self.environment, "delete": True}
        if self.environment_kwargs:
            block["kwargs"] = dict(self.environment_kwargs)
        return block

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "family": self.family,
            "environment": self.environment,
        }
        if self.dispatch:
            payload["dispatch"] = self.dispatch
        if self.cua_pinned:
            payload["cuaPinned"] = True
        return payload

    def header_comment(self) -> str:
        parts = ["family={}".format(self.family), "environment={}".format(self.environment)]
        if self.dispatch:
            parts.append("dispatch={}".format(self.dispatch))
        if self.cua_pinned:
            parts.append("cua=pinned")
        return "# matraix {}".format(" ".join(parts))

    def needs_playground_dispatch(self) -> bool:
        """True when ``matraix run`` must go through HarborJobService.

        Modal Jobs / GKE workers (and gcp web ``type: gke``) are Playground
        dispatch. CUA stays on this machine even if the family is modal/gcp.
        """
        if self.cua_pinned:
            return False
        return bool(self.dispatch) or self.family in {"modal", "gcp"}


def normalize_compute_family(
    value: str | None = None,
    *,
    default_from_env: bool = True,
) -> str:
    raw = (value or "").strip().lower().replace("-", "_")
    if raw:
        if raw not in COMPUTE_FAMILIES:
            raise ValueError("computeFamily must be one of local, modal, gcp")
        return raw
    if default_from_env:
        env_raw = os.environ.get(COMPUTE_FAMILY_ENV, "").strip().lower().replace("-", "_")
        if env_raw:
            if env_raw not in COMPUTE_FAMILIES:
                raise ValueError(
                    "{} must be one of local, modal, gcp".format(COMPUTE_FAMILY_ENV)
                )
            return env_raw
    return "local"


def host_pack_concurrency() -> int:
    """Concurrent host trials packed into one Modal Job (I/O-bound survey/chat)."""
    raw = (os.environ.get(HOST_PACK_CONCURRENCY_ENV) or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return DEFAULT_HOST_PACK_CONCURRENCY


def packed_n_concurrent_trials(requested: int, *, dispatch: str | None) -> int:
    """Return the requested Harbor concurrency.

    Playground Parallel is the job cap on every compute family. Modal/GKE
    still pack I/O-bound host processes into one worker; they do not rewrite
    the number the operator set.
    """
    del dispatch
    return max(1, int(requested or 1))


def resolve_compute_plan(
    *,
    execution_mode: str,
    trial_profile: str,
    cua_backend: str | None = None,
    compute_family: str | None = None,
) -> ComputePlan:
    """Return the Harbor environment and optional host-cloud dispatch."""
    family = normalize_compute_family(compute_family)
    cua_env = _cua_environment(cua_backend)
    if cua_env is not None and cua_env[0] == "use-computer":
        env_type, kwargs = cua_env
        return ComputePlan(
            family=family,
            environment=env_type,
            cua_pinned=True,
            environment_kwargs=kwargs,
        )

    native = trial_profile in _NATIVE_TRIAL_PROFILES
    mode = (execution_mode or "auto").strip().lower()

    if family == "modal":
        if native and mode != "force_docker":
            return ComputePlan(family=family, environment="host", dispatch="modal_jobs")
        return ComputePlan(family=family, environment="docker", dispatch="modal_jobs")

    if family == "gcp":
        if native and mode != "force_docker":
            return ComputePlan(family=family, environment="host", dispatch="gke_workers")
        return ComputePlan(
            family=family,
            environment="gke",
            environment_kwargs=gke_harbor_kwargs() or None,
        )

    if mode == "force_docker" or not native:
        return ComputePlan(family="local", environment="docker")
    return ComputePlan(family="local", environment="host")


def _cua_environment(cua_backend: str | None) -> tuple[str, dict[str, Any] | None] | None:
    if not cua_backend:
        return None
    normalized = cua_backend.strip().lower().replace("-", "_")
    if normalized in {
        "macos",
        "ios",
        "use_computer",
        "use_computer_desktop",
        "desktop",
        "anthropic",
        "anthropic_cua",
        "ubuntu",
    }:
        kwargs = {"platform": "ios"} if normalized == "ios" else None
        return "use-computer", kwargs
    if normalized in {"docker", "linux", "docker_computer1", "computer1", "computer_1"}:
        return "docker", None
    return None
