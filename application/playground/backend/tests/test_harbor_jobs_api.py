"""API contract tests for Harbor batch jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")


class _FakeHarborJobService:
    def __init__(self) -> None:
        self.repo_root = Path.cwd()
        self.launches: list[dict[str, Any]] = []
        self.debrief_calls: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        self._jobs: dict[str, dict[str, Any]] = {
            "demo-job": {
                "jobName": "demo-job",
                "jobsDir": "jobs",
                "trials": [{"trialName": "trial-0", "result": None}],
                "launch": {"status": "completed"},
            }
        }

    def list_jobs(self) -> list[dict[str, Any]]:
        return [
            {
                "jobName": name,
                "trialCount": 1,
                "completedTrials": 1,
                "startedAt": "2026-07-01T12:00:00Z",
                "updatedAt": "2026-07-01T12:05:00Z",
                "status": "success",
                "failedTrials": 0,
            }
            for name in self._jobs
        ]

    def delete_job(self, job_name: str) -> None:
        if job_name not in self._jobs:
            raise ValueError("Job not found: {}".format(job_name))
        del self._jobs[job_name]
        self.deleted.append(job_name)

    def get_job(self, job_name: str) -> dict[str, Any] | None:
        return self._jobs.get(job_name)

    def get_job_aggregation(self, job_name: str) -> dict[str, Any]:
        if job_name not in self._jobs:
            raise ValueError("Job not found")
        return {
            "schemaVersion": "1.0",
            "artifactType": "job_aggregation",
            "generatedAt": "2026-07-01T12:06:00Z",
            "reporting": {
                "status": "completed",
                "totalUnits": 2,
                "summaryUnits": 1,
                "judgeUnits": 1,
                "readyUnits": 0,
                "completedUnits": 2,
                "failedUnits": 0,
            },
            "coverage": {
                "trialCount": 1,
                "completedTrials": 1,
                "pendingTrials": 0,
                "artifactReadyTrials": 1,
                "completedWithoutArtifactTrials": 0,
            },
            "fields": [],
            "contexts": [],
        }

    def launch(self, **kwargs: Any) -> str:
        self.launches.append(kwargs)
        job_name = kwargs.get("job_name") or "pg-launched"
        launch = {"status": "queued"}
        if kwargs.get("language") is not None:
            launch["effectiveLanguage"] = kwargs["language"]
            launch["languageSource"] = kwargs["language_source"]
        self._jobs[job_name] = {
            "jobName": job_name,
            "trials": [],
            "launch": launch,
        }
        return job_name

    def get_trial_events(self, job_name: str, trial_name: str, *, after: int = 0) -> dict[str, Any]:
        if (job_name, trial_name) != ("demo-job", "trial-0"):
            raise ValueError("Trial not found")
        events = [
            {"type": "phase", "phase": "persona_kickoff"},
            {"type": "turn", "turn": {"turnIndex": 1, "userMessage": "hi", "assistantMessage": "hello"}},
        ]
        return {"events": events[after:], "offset": len(events)}

    def get_job_live(self, job_name: str) -> dict[str, Any]:
        job = self.get_job(job_name)
        if job is None:
            raise ValueError("Job not found")
        return {
            "jobName": job_name,
            "launchStatus": job.get("launch", {}).get("status"),
            "trialCount": len(job.get("trials", [])),
            "completedTrials": 0,
            "trials": [
                {
                    "trialName": "trial-0",
                    "personaId": "p1",
                    "personaName": "Persona",
                    "completed": False,
                    "phase": "persona_kickoff",
                }
            ],
        }

    def get_trial_debrief(self, job_name: str, trial_name: str) -> dict[str, Any]:
        self.debrief_calls.append((job_name, trial_name))
        return {
            "applicationType": "chatbot",
            "transcript": [],
            "persona": {"id": "p1", "name": "Persona"},
        }

    def shutdown(self) -> None:
        return None


@pytest.fixture()
def fake_harbor_jobs(app):
    fake = _FakeHarborJobService()
    app.state.services.harbor_jobs = fake
    return fake


def test_list_harbor_jobs(client, fake_harbor_jobs):
    resp = client.get("/api/harbor/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert "jobs" in body
    assert any(entry["jobName"] == "demo-job" for entry in body["jobs"])


def test_get_harbor_job(client, fake_harbor_jobs):
    resp = client.get("/api/harbor/jobs/demo-job")
    assert resp.status_code == 200
    assert resp.json()["jobName"] == "demo-job"


def test_get_harbor_job_aggregation(client, fake_harbor_jobs):
    resp = client.get("/api/harbor/jobs/demo-job/aggregation")
    assert resp.status_code == 200
    assert resp.json()["artifactType"] == "job_aggregation"
    assert resp.json()["reporting"]["status"] == "completed"


def test_get_harbor_job_missing(client, fake_harbor_jobs):
    resp = client.get("/api/harbor/jobs/missing-job")
    assert resp.status_code == 404


def test_delete_harbor_job(client, fake_harbor_jobs):
    resp = client.delete("/api/harbor/jobs/demo-job")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert fake_harbor_jobs.deleted == ["demo-job"]
    assert client.get("/api/harbor/jobs/demo-job").status_code == 404


def test_delete_harbor_job_missing(client, fake_harbor_jobs):
    resp = client.delete("/api/harbor/jobs/missing-job")
    assert resp.status_code == 404


def test_launch_harbor_job(client, fake_harbor_jobs):
    resp = client.post(
        "/api/harbor/jobs",
        json={
            "taskPath": "application/tasks/example-survey_product-feedback",
            "sampleSize": 2,
            "personaModel": "anthropic/claude-haiku-4-5",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["jobName"] == "pg-launched"
    assert fake_harbor_jobs.launches[0]["sample_size"] == 2


def test_launch_harbor_job_with_persona_ids(client, fake_harbor_jobs):
    resp = client.post(
        "/api/harbor/jobs",
        json={
            "taskPath": "application/tasks/example-survey_product-feedback",
            "personaIds": ["0042"],
            "personaModel": "anthropic/claude-haiku-4-5",
            "mode": "auto",
        },
    )
    assert resp.status_code == 200
    assert fake_harbor_jobs.launches[-1]["persona_ids"] == ["0042"]
    assert fake_harbor_jobs.launches[-1]["execution_mode"] == "auto"


def test_launch_harbor_job_passes_and_returns_runtime_language(client, fake_harbor_jobs):
    resp = client.post(
        "/api/harbor/jobs",
        json={
            "taskPath": "application/tasks/example-survey_product-feedback",
            "language": "zh-CN",
            "languageSource": "follow_ui",
        },
    )

    assert resp.status_code == 200
    assert fake_harbor_jobs.launches[-1]["language"] == "zh-Hans"
    assert fake_harbor_jobs.launches[-1]["language_source"] == "follow_ui"
    assert resp.json()["effectiveLanguage"] == "zh-Hans"
    assert resp.json()["languageSource"] == "follow_ui"


def test_launch_harbor_job_prefers_chat_application_context(client, fake_harbor_jobs):
    resp = client.post(
        "/api/harbor/jobs",
        json={
            "taskPath": "application/tasks/chat_meal-planning-nutrition",
            "chatApplicationId": "meal_planning_nutrition",
            "chatApplicationContext": "meal_planning",
        },
    )
    assert resp.status_code == 200
    assert fake_harbor_jobs.launches[-1]["chat_application_context"] == "meal_planning"
    assert fake_harbor_jobs.launches[-1]["chat_domain"] is None


def test_get_harbor_trial_debrief(client, fake_harbor_jobs):
    resp = client.get("/api/harbor/jobs/demo-job/trials/trial-0/debrief")
    assert resp.status_code == 200
    assert resp.json()["applicationType"] == "chatbot"
    assert fake_harbor_jobs.debrief_calls == [("demo-job", "trial-0")]


def test_get_harbor_trial_events(client, fake_harbor_jobs):
    resp = client.get("/api/harbor/jobs/demo-job/trials/trial-0/events")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["events"]) == 2
    assert body["events"][0]["phase"] == "persona_kickoff"
    assert body["offset"] == 2


def test_get_harbor_trial_events_missing(client, fake_harbor_jobs):
    resp = client.get("/api/harbor/jobs/demo-job/trials/missing/events")
    assert resp.status_code == 404


def test_get_harbor_job_live(client, fake_harbor_jobs):
    resp = client.get("/api/harbor/jobs/demo-job/live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["jobName"] == "demo-job"
    assert len(body["trials"]) == 1
