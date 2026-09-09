"""Tests for compute family resolution."""

from __future__ import annotations

import pytest

from matraix.compute_family import (
    packed_n_concurrent_trials,
    normalize_compute_family,
    resolve_compute_plan,
)


def test_normalize_compute_family(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MATRIX_COMPUTE_FAMILY", raising=False)
    assert normalize_compute_family(None) == "local"
    assert normalize_compute_family("modal") == "modal"
    monkeypatch.setenv("MATRIX_COMPUTE_FAMILY", "modal")
    assert normalize_compute_family(None) == "modal"


def test_resolve_compute_plan_modal_family() -> None:
    survey = resolve_compute_plan(
        execution_mode="auto",
        trial_profile="json_survey",
        compute_family="modal",
    )
    assert survey.to_public_dict() == {
        "family": "modal",
        "environment": "host",
        "dispatch": "modal_jobs",
    }
    web = resolve_compute_plan(
        execution_mode="auto",
        trial_profile="docker_agent",
        compute_family="modal",
    )
    assert web.to_public_dict() == {
        "family": "modal",
        "environment": "docker",
        "dispatch": "modal_jobs",
    }
    assert web.harbor_environment() == {"type": "docker", "delete": True}


def test_packed_n_concurrent_trials_keeps_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MATRIX_HOST_PACK_CONCURRENCY", raising=False)
    assert packed_n_concurrent_trials(2, dispatch="modal_jobs") == 2
    assert packed_n_concurrent_trials(8, dispatch="modal_jobs") == 8
    assert packed_n_concurrent_trials(2, dispatch="gke_workers") == 2
    assert packed_n_concurrent_trials(1, dispatch="modal_jobs") == 1
    assert packed_n_concurrent_trials(2, dispatch=None) == 2
    monkeypatch.setenv("MATRIX_HOST_PACK_CONCURRENCY", "48")
    assert packed_n_concurrent_trials(2, dispatch="modal_jobs") == 2
    assert packed_n_concurrent_trials(2, dispatch="gke_workers") == 2


def test_resolve_compute_plan_gcp_family(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "MATRIX_GKE_CLUSTER",
        "MATRIX_GKE_REGION",
        "MATRIX_GKE_REGISTRY",
        "MATRIX_GCP_PROJECT",
        "GCP_PROJECT",
        "GOOGLE_CLOUD_PROJECT",
    ):
        monkeypatch.delenv(name, raising=False)
    survey = resolve_compute_plan(
        execution_mode="auto",
        trial_profile="json_survey",
        compute_family="gcp",
    )
    assert survey.to_public_dict() == {
        "family": "gcp",
        "environment": "host",
        "dispatch": "gke_workers",
    }
    web = resolve_compute_plan(
        execution_mode="auto",
        trial_profile="docker_agent",
        compute_family="gcp",
    )
    assert web.to_public_dict() == {"family": "gcp", "environment": "gke"}
    assert web.harbor_environment() == {"type": "gke", "delete": True}


def test_resolve_compute_plan_gcp_web_injects_gke_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MATRIX_GKE_CLUSTER", "demo")
    monkeypatch.setenv("MATRIX_GKE_REGION", "us-central1")
    monkeypatch.setenv("MATRIX_GKE_REGISTRY", "matraix")
    monkeypatch.setenv("GCP_PROJECT", "proj-1")
    web = resolve_compute_plan(
        execution_mode="auto",
        trial_profile="docker_agent",
        compute_family="gcp",
    )
    assert web.harbor_environment() == {
        "type": "gke",
        "delete": True,
        "kwargs": {
            "cluster_name": "demo",
            "region": "us-central1",
            "namespace": "default",
            "registry_name": "matraix",
            "registry_location": "us-central1",
            "project_id": "proj-1",
        },
    }


def test_resolve_compute_plan_cua_pins_use_computer_on_modal() -> None:
    plan = resolve_compute_plan(
        execution_mode="auto",
        trial_profile="docker_agent",
        cua_backend="macos",
        compute_family="modal",
    )
    assert plan.to_public_dict() == {
        "family": "modal",
        "environment": "use-computer",
        "cuaPinned": True,
    }
    assert plan.dispatch is None
    assert plan.harbor_environment() == {"type": "use-computer", "delete": True}


def test_resolve_compute_plan_linux_cua_uses_modal_jobs() -> None:
    plan = resolve_compute_plan(
        execution_mode="auto",
        trial_profile="docker_agent",
        cua_backend="linux",
        compute_family="modal",
    )
    assert plan.to_public_dict() == {
        "family": "modal",
        "environment": "docker",
        "dispatch": "modal_jobs",
    }
    assert not plan.cua_pinned


def test_needs_playground_dispatch() -> None:
    from matraix.compute_family import ComputePlan

    assert not ComputePlan(family="local", environment="host").needs_playground_dispatch()
    assert ComputePlan(
        family="modal", environment="host", dispatch="modal_jobs"
    ).needs_playground_dispatch()
    assert ComputePlan(
        family="modal", environment="docker", dispatch="modal_jobs"
    ).needs_playground_dispatch()
    assert ComputePlan(family="gcp", environment="gke").needs_playground_dispatch()
    assert not ComputePlan(
        family="modal", environment="use-computer", cua_pinned=True
    ).needs_playground_dispatch()
