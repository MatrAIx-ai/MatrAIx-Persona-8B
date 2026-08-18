from __future__ import annotations

import time

from backend.service.appworld_eval_service import AppWorldEvalService
from backend.service.appworld_tasks import (
    get_appworld_eval_task,
    list_appworld_eval_tasks,
)
from backend.service.local_appworld_eval import LocalAppWorldEvalRunner
from playground.types import Persona


def _persona(_persona_id: str) -> Persona:
    return Persona(
        id="p1",
        name="Persona One",
        context="Occupation: operations manager\nNeeds a careful assistant.",
    )


def test_appworld_eval_service_persists_trace_and_reloads_view(tmp_path):
    service = AppWorldEvalService(
        get_persona=_persona,
        get_task=get_appworld_eval_task,
        list_tasks=list_appworld_eval_tasks,
        runner=LocalAppWorldEvalRunner(),
        runs_dir=tmp_path,
    )

    job_id = service.start(
        persona_id="p1",
        task_id="appworld-demo-personal-admin",
        persona_model="openai/gpt-4o-mini",
        now=lambda: "2026-06-29T00:00:00Z",
    )
    view = _wait_done(service, job_id)

    assert view["applicationType"] == "appworld"
    assert view["appworldResult"]["success"] is True
    assert view["trace"]["events"][0]["actions"][0]["name"] == "appworld_api_call"

    reloaded = AppWorldEvalService(
        get_persona=_persona,
        get_task=get_appworld_eval_task,
        list_tasks=list_appworld_eval_tasks,
        runner=LocalAppWorldEvalRunner(),
        runs_dir=tmp_path,
    )
    persisted = reloaded.view(job_id)

    assert persisted is not None
    assert persisted["status"] == "done"
    assert persisted["trace"]["raw"]["trajectory"][0]["action"] == "list_apps"


def test_local_appworld_eval_localizes_persona_prompt_only() -> None:
    persona = _persona("p1")
    task = get_appworld_eval_task("appworld-demo-personal-admin")
    result = LocalAppWorldEvalRunner()(
        persona,
        task,
        created_at="2026-06-29T00:00:00Z",
        persona_language="zh-Hans",
        persona_language_source="explicit",
    )

    assert result.config.persona_language == "zh-Hans"
    assert result.config.persona_language_source == "explicit"
    assert result.config.to_dict()["effectiveLanguage"] == "zh-Hans"
    assert result.config.to_dict()["languageSource"] == "explicit"
    assert "Write persona narrative" in result.prompts["personaPrompt"]
    assert "Application: AppWorld" in result.prompts["taskPrompt"]
    assert "Write persona narrative" not in result.prompts["taskPrompt"]


def test_local_appworld_eval_legacy_defaults_to_english() -> None:
    result = LocalAppWorldEvalRunner()(
        _persona("p1"),
        get_appworld_eval_task("appworld-demo-personal-admin"),
        created_at="2026-06-29T00:00:00Z",
    )

    assert result.config.persona_language == "en"
    assert result.config.persona_language_source == "default"


def _wait_done(service: AppWorldEvalService, job_id: str) -> dict[str, object]:
    deadline = time.time() + 5
    while True:
        view = service.view(job_id)
        assert view is not None
        if view["status"] in {"done", "error"}:
            assert view["status"] == "done", view
            return view
        assert time.time() < deadline
        time.sleep(0.01)
