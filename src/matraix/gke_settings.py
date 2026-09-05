"""Read GKE / GCP settings from the environment for Harbor ``type: gke``."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

GKE_CLUSTER_ENV = "MATRIX_GKE_CLUSTER"
GKE_REGION_ENV = "MATRIX_GKE_REGION"
GKE_NAMESPACE_ENV = "MATRIX_GKE_NAMESPACE"
GKE_REGISTRY_ENV = "MATRIX_GKE_REGISTRY"
GKE_REGISTRY_LOCATION_ENV = "MATRIX_GKE_REGISTRY_LOCATION"
GKE_HOST_IMAGE_ENV = "MATRIX_GKE_HOST_IMAGE"
GKE_JOBS_PVC_ENV = "MATRIX_GKE_JOBS_PVC"
GCP_PROJECT_ENVS = ("MATRIX_GCP_PROJECT", "GCP_PROJECT", "GOOGLE_CLOUD_PROJECT")


def _first_env(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def gke_namespace() -> str:
    return _first_env(GKE_NAMESPACE_ENV) or "default"


def gke_project_id() -> str:
    return _first_env(*GCP_PROJECT_ENVS)


def gke_harbor_kwargs() -> dict[str, Any]:
    """Constructor kwargs Harbor's GKE environment expects.

    Empty until a cluster is configured so job YAML does not emit a
    namespace-only stub.
    """
    cluster = _first_env(GKE_CLUSTER_ENV)
    region = _first_env(GKE_REGION_ENV)
    registry = _first_env(GKE_REGISTRY_ENV)
    registry_location = _first_env(GKE_REGISTRY_LOCATION_ENV) or region
    if not cluster:
        return {}
    kwargs: dict[str, Any] = {
        "cluster_name": cluster,
        "region": region,
        "namespace": gke_namespace(),
        "registry_name": registry,
        "registry_location": registry_location,
    }
    project = gke_project_id()
    if project:
        kwargs["project_id"] = project
    return {key: value for key, value in kwargs.items() if value}


def missing_gke_harbor_keys() -> list[str]:
    kwargs = gke_harbor_kwargs()
    required = ("cluster_name", "region", "registry_name", "registry_location")
    return [key for key in required if not kwargs.get(key)]


def gke_host_image() -> str:
    return _first_env(GKE_HOST_IMAGE_ENV)


def kubeconfig_path() -> Path:
    raw = (os.environ.get("KUBECONFIG") or "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".kube" / "config"


def gke_kube_configured() -> bool:
    path = kubeconfig_path()
    return path.is_file() or bool((os.environ.get("KUBERNETES_SERVICE_HOST") or "").strip())


def gke_can_authenticate() -> bool:
    if gke_kube_configured():
        return True
    kwargs = gke_harbor_kwargs()
    return bool(kwargs.get("cluster_name") and kwargs.get("region"))


def ensure_gke_kubeconfig() -> None:
    """Fetch cluster credentials with gcloud when kubeconfig is missing."""
    if gke_kube_configured():
        return
    kwargs = gke_harbor_kwargs()
    cluster = str(kwargs.get("cluster_name") or "")
    region = str(kwargs.get("region") or "")
    project = str(kwargs.get("project_id") or gke_project_id())
    if not cluster or not region:
        raise RuntimeError(
            "computeFamily=gcp needs kubeconfig or "
            "{} + {}".format(GKE_CLUSTER_ENV, GKE_REGION_ENV)
        )
    command = [
        "gcloud",
        "container",
        "clusters",
        "get-credentials",
        cluster,
        "--region",
        region,
    ]
    if project:
        command.extend(["--project", project])
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "gcloud container clusters get-credentials failed: {}".format(
                (result.stderr or result.stdout or "").strip() or result.returncode
            )
        )


def gke_host_workers_ready() -> bool:
    return gke_can_authenticate() and bool(gke_host_image())
