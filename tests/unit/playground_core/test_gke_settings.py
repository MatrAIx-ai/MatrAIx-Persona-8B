"""Tests for GKE / GCP environment settings."""

from __future__ import annotations

import pytest

from matraix.gke_settings import (
    gke_can_authenticate,
    gke_harbor_kwargs,
    gke_host_workers_ready,
    missing_gke_harbor_keys,
)

_GKE_ENV = (
    "MATRIX_GKE_CLUSTER",
    "MATRIX_GKE_REGION",
    "MATRIX_GKE_NAMESPACE",
    "MATRIX_GKE_REGISTRY",
    "MATRIX_GKE_REGISTRY_LOCATION",
    "MATRIX_GKE_HOST_IMAGE",
    "MATRIX_GKE_JOBS_PVC",
    "MATRIX_GCP_PROJECT",
    "GCP_PROJECT",
    "GOOGLE_CLOUD_PROJECT",
    "KUBECONFIG",
    "KUBERNETES_SERVICE_HOST",
)


def _clear_gke(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _GKE_ENV:
        monkeypatch.delenv(name, raising=False)


def test_gke_harbor_kwargs_empty_without_cluster(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_gke(monkeypatch)
    assert gke_harbor_kwargs() == {}
    assert missing_gke_harbor_keys() == [
        "cluster_name",
        "region",
        "registry_name",
        "registry_location",
    ]


def test_gke_harbor_kwargs_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_gke(monkeypatch)
    monkeypatch.setenv("MATRIX_GKE_CLUSTER", "demo")
    monkeypatch.setenv("MATRIX_GKE_REGION", "us-central1")
    monkeypatch.setenv("MATRIX_GKE_REGISTRY", "matraix")
    monkeypatch.setenv("GCP_PROJECT", "proj-1")
    assert gke_harbor_kwargs() == {
        "cluster_name": "demo",
        "region": "us-central1",
        "namespace": "default",
        "registry_name": "matraix",
        "registry_location": "us-central1",
        "project_id": "proj-1",
    }
    assert missing_gke_harbor_keys() == []


def test_gke_host_workers_ready(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _clear_gke(monkeypatch)
    monkeypatch.setattr("matraix.gke_settings.Path.home", lambda: tmp_path)
    assert not gke_can_authenticate()
    assert not gke_host_workers_ready()
    monkeypatch.setenv("MATRIX_GKE_CLUSTER", "demo")
    monkeypatch.setenv("MATRIX_GKE_REGION", "us-central1")
    assert gke_can_authenticate()
    assert not gke_host_workers_ready()
    monkeypatch.setenv("MATRIX_GKE_HOST_IMAGE", "us-central1-docker.pkg.dev/p/r/host:latest")
    assert gke_host_workers_ready()
