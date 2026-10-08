"""Job/trial names and task paths must not be able to climb out of their directory."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

pytest.importorskip("fastapi")

from backend.api import schemas
from backend.api.path_safety import is_safe_relative_path, is_safe_segment


@pytest.mark.parametrize("value", ["pg-demo-1a2b", "trial__abc", "a.b", "..x", "x.."])
def test_safe_segments(value):
    assert is_safe_segment(value)


@pytest.mark.parametrize("value", ["", ".", "..", "a/b", "a\\b", "a\x00b"])
def test_unsafe_segments(value):
    assert not is_safe_segment(value)


@pytest.mark.parametrize(
    "value",
    ["application/tasks/demo", "application/tasks/demo/", "a..b/c", ""],
)
def test_safe_relative_paths(value):
    assert is_safe_relative_path(value)


@pytest.mark.parametrize(
    "value",
    ["../outside", "application/../../outside", "application\\..\\..\\outside", ".."],
)
def test_unsafe_relative_paths(value):
    assert not is_safe_relative_path(value)


def test_task_detail_rejects_parent_traversal(client):
    resp = client.get("/api/tasks/detail", params={"taskPath": "../outside"})
    assert resp.status_code == 400


def test_persona_strategy_rejects_parent_traversal(client):
    resp = client.get(
        "/api/tasks/persona-strategy", params={"taskPath": "application/../../outside"}
    )
    assert resp.status_code == 400


@pytest.mark.parametrize(
    "path",
    [
        "/api/harbor/jobs/%2e%2e/trials/t/recording",
        "/api/harbor/jobs/demo/trials/%2e%2e/recording",
    ],
)
def test_dot_segments_in_job_and_trial_names_are_rejected(client, path):
    assert client.get(path).status_code == 400


def test_launch_request_rejects_parent_traversal():
    with pytest.raises(ValidationError):
        schemas.HarborJobLaunchRequest(taskPath="../outside")
    ok = schemas.HarborJobLaunchRequest(taskPath="application/tasks/demo")
    assert ok.taskPath == "application/tasks/demo"
