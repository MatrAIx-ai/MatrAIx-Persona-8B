"""Unit tests for Harbor job launch config generation."""

from __future__ import annotations

import json

import pytest

from backend.service.harbor_job_service import HarborJobService, HarborLaunchRecord


@pytest.mark.parametrize(
    ("language", "language_source"),
    [("es", "env"), (None, "follow_ui"), ("xx", None), ("es", "ui"), ("es", "cli")],
)
def test_launch_rejects_invalid_or_caller_owned_language_provenance(
    language, language_source
):
    service = object.__new__(HarborJobService)

    with pytest.raises(ValueError, match="language|language_source"):
        service.launch(
            task_path="application/tasks/example-survey_product-feedback",
            language=language,
            language_source=language_source,
        )


def test_launch_writes_job_config(tmp_path, monkeypatch):
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample").mkdir(parents=True)
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0002.yaml").write_text(
        "persona_id: '0002'\nversion: '1.0'\nsource: OASIS\ndimensions: {}\n",
        encoding="utf-8",
    )

    calls: list[dict[str, object]] = []

    def _fake_run(command, *, cwd, env):
        calls.append({"command": list(command), "cwd": cwd, "env": dict(env)})
        return 0

    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=_fake_run,
        harbor_command=("echo", "harbor"),
    )
    service._executor = _FakeExecutor()

    job_name = service.launch(
        task_path="application/tasks/example-survey_product-feedback",
        sample_size=2,
        seed=1,
        persona_pool="persona/datasets/matraix-persona-dev-sample",
        persona_model="anthropic/claude-haiku-4-5",
        job_name="test-harbor-job",
        language="zh-Hant",
        language_source="follow_ui",
    )
    assert job_name == "test-harbor-job"
    config_path = repo / "configs" / "jobs" / "application-task-job-recipe" / "test-harbor-job.yaml"
    assert config_path.is_file()
    text = config_path.read_text(encoding="utf-8")
    assert "persona_0001.yaml" in text or "persona_0002.yaml" in text
    assert "persona_language: zh-Hant" in text
    assert "persona_language_source: follow_ui" in text
    launch_meta = json.loads(service._launch_meta_path(job_name).read_text(encoding="utf-8"))
    assert launch_meta["effective_language"] == "zh-Hant"
    assert launch_meta["language_source"] == "follow_ui"
    queued_detail = service.get_job(job_name)
    assert queued_detail is not None
    assert queued_detail["launch"]["effectiveLanguage"] == "zh-Hant"
    assert queued_detail["launch"]["languageSource"] == "follow_ui"
    assert service._executor.calls
    fn, args, kwargs = service._executor.calls[0]
    assert fn.__name__ == "_run_local_distributed"
    fn(*args, **kwargs)
    assert calls
    assert calls[0]["command"][0:4] == ["echo", "harbor", "trials", "start"]
    env = calls[0]["env"]
    assert isinstance(env, dict)
    assert env["MATRIX_SURVEY_TASK_PATH"] == "application/tasks/example-survey_product-feedback"

    detail = service.get_job("test-harbor-job")
    assert detail is not None
    assert detail["launch"]["status"] == "completed"
    assert detail["launch"]["effectiveLanguage"] == "zh-Hant"
    assert detail["launch"]["languageSource"] == "follow_ui"
    assert len(detail["trials"]) == 2

    for trial in detail["trials"]:
        # Harbor reads runtime metadata but does not synthesize persona_meta.json.
        assert not (jobs_dir / job_name / trial["trialName"] / "persona_meta.json").exists()

    service.shutdown()


def test_launch_derives_env_and_default_language_into_job_metadata(tmp_path, monkeypatch):
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)

    monkeypatch.setenv("MATRIX_PERSONA_LANGUAGE", "ja-JP")
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs",
    )
    service._executor = _FakeExecutor()
    job_name = service.launch(
        task_path="application/tasks/example-survey_product-feedback",
        persona_ids=["0001"],
        job_name="env-language-job",
    )
    meta = json.loads(service._launch_meta_path(job_name).read_text(encoding="utf-8"))
    assert meta["effective_language"] == "ja"
    assert meta["language_source"] == "env"
    config = (repo / "configs" / "jobs" / "env-language-job.yaml").read_text(
        encoding="utf-8"
    )
    assert "persona_language: ja" in config
    assert "persona_language_source: env" in config
    service.shutdown()

    monkeypatch.delenv("MATRIX_PERSONA_LANGUAGE", raising=False)
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs",
    )
    service._executor = _FakeExecutor()
    default_job = service.launch(
        task_path="application/tasks/example-survey_product-feedback",
        persona_ids=["0001"],
        job_name="default-language-job",
    )
    meta = json.loads(service._launch_meta_path(default_job).read_text(encoding="utf-8"))
    assert meta["effective_language"] == "en"
    assert meta["language_source"] == "default"
    service.shutdown()


def test_list_trial_names_is_read_only_for_persona_metadata(tmp_path):
    service = object.__new__(HarborJobService)
    service.jobs_dir = tmp_path / "jobs"
    trial_dir = service.jobs_dir / "job-read-only" / "trial-0001"
    trial_dir.mkdir(parents=True)

    assert service._list_trial_names("job-read-only") == ["trial-0001"]
    assert not (trial_dir / "persona_meta.json").exists()


def test_launch_with_frozen_cohort(tmp_path, monkeypatch):
    from application.playground.backend.tests.test_persona_pool_service import _write_pool

    repo = tmp_path
    _write_pool(repo)
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()

    from backend.service.persona_pool_service import PersonaPoolService

    pool_service = PersonaPoolService(repo_root=repo)
    pool_service.save_cohort(
        cohort_id="frozen-oasis",
        kind="frozen",
        seed=1,
        sample_size=1,
        dimension_filters={"economic_motivation": "Indifferent"},
    )

    calls: list[list[str]] = []

    def _fake_run(command, *, cwd, env):
        calls.append(list(command))
        return 0

    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=_fake_run,
        harbor_command=("echo", "harbor"),
    )
    service._executor = _FakeExecutor()

    job_name = service.launch(
        task_path="application/tasks/example-survey_product-feedback",
        cohort_id="frozen-oasis",
        persona_model="anthropic/claude-haiku-4-5",
        job_name="cohort-job",
    )
    assert job_name == "cohort-job"
    config_path = repo / "configs" / "jobs" / "application-task-job-recipe" / "cohort-job.yaml"
    text = config_path.read_text(encoding="utf-8")
    assert "persona_0002.yaml" in text
    assert "# Cohort: frozen-oasis" in text
    assert service._executor.calls
    assert service._executor.calls[0][0].__name__ == "_run_local_distributed"
    service.shutdown()


def test_launch_with_explicit_persona_ids(tmp_path, monkeypatch):
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0042.yaml").write_text(
        "persona_id: '0042'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )

    calls: list[list[str]] = []

    def _fake_run(command, *, cwd, env):
        calls.append(list(command))
        return 0

    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=_fake_run,
        harbor_command=("echo", "harbor"),
    )
    service._executor = _FakeExecutor()

    job_name = service.launch(
        task_path="application/tasks/example-survey_product-feedback",
        persona_ids=["0042"],
        persona_model="anthropic/claude-haiku-4-5",
        execution_mode="auto",
        job_name="explicit-persona-job",
    )
    assert job_name == "explicit-persona-job"
    config_path = repo / "configs" / "jobs" / "application-task-job-recipe" / "explicit-persona-job.yaml"
    text = config_path.read_text(encoding="utf-8")
    assert "persona_0042.yaml" in text
    assert "# Mode: auto" in text
    assert "# Trial profile: json_survey" in text
    assert "type: host" in text
    assert "application/tasks/example-survey_product-feedback" in text
    assert service._executor.calls
    assert service._executor.calls[0][0].__name__ == "_run_local_distributed"
    service.shutdown()


def test_retry_failed_reruns_only_failed_trials(tmp_path, monkeypatch):
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=lambda *args, **kwargs: 0,
        harbor_command=("echo", "harbor"),
    )
    service._executor = _FakeExecutor()

    job_name = service.launch(
        task_path="application/tasks/example-survey_product-feedback",
        persona_ids=["0001"],
        persona_model="anthropic/claude-haiku-4-5",
        job_name="retry-job",
        language="zh",
    )
    # Launch metadata is persisted so a retry can replay the identical dispatch.
    meta_path = service._launch_meta_path(job_name)
    assert meta_path.is_file()
    launch_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert launch_meta["effective_language"] == "zh-Hans"
    assert launch_meta["language_source"] == "explicit"
    original_config = launch_meta["configPath"]
    assert len(service._executor.calls) == 1

    # Mark the launch record finished so retry is allowed.
    service._launches[job_name].status = "completed"

    job_dir = jobs_dir / job_name
    ok_dir = job_dir / "trial-ok"
    ok_dir.mkdir(parents=True)
    (ok_dir / "result.json").write_text("{}", encoding="utf-8")
    fail_dir = job_dir / "trial-fail"
    fail_dir.mkdir(parents=True)
    (fail_dir / "result.json").write_text(
        json.dumps({"exception_info": {"exception_message": "boom"}}),
        encoding="utf-8",
    )
    (job_dir / "result.json").write_text(
        json.dumps({"finished_at": "2026-07-01T12:00:00Z", "stats": {"n_errored_trials": 1}}),
        encoding="utf-8",
    )

    assert service.failed_trial_count(job_name) == 1

    result = service.retry_failed(job_name)
    assert result == {"jobName": job_name, "retried": 1}

    # Succeeded trial preserved; failed trial removed for Harbor to re-run.
    assert ok_dir.is_dir()
    assert not fail_dir.exists()
    # Job-level completion cleared so status/reporting recompute.
    assert not (job_dir / "result.json").exists()
    # A fresh dispatch was submitted and the record is active again.
    assert len(service._executor.calls) == 2
    assert service._launches[job_name].status == "queued"
    retried_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert retried_meta["configPath"] == original_config
    assert retried_meta["effective_language"] == "zh-Hans"
    assert retried_meta["language_source"] == "explicit"
    assert service._launches[job_name].effective_language == "zh-Hans"
    assert service._launches[job_name].language_source == "explicit"

    service.shutdown()


def test_retry_failed_no_failures_is_noop(tmp_path, monkeypatch):
    repo = tmp_path
    jobs_dir = repo / "jobs"
    job_dir = jobs_dir / "clean-job"
    trial_dir = job_dir / "trial-ok"
    trial_dir.mkdir(parents=True)
    (trial_dir / "result.json").write_text("{}", encoding="utf-8")

    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs",
    )
    service._executor = _FakeExecutor()

    assert service.retry_failed("clean-job") == {"jobName": "clean-job", "retried": 0}
    assert service._executor.calls == []
    assert trial_dir.is_dir()
    service.shutdown()


def test_resolve_trial_profile_auto_survey_and_chat(tmp_path):
    repo = tmp_path
    survey_dir = repo / "application" / "tasks" / "example-survey_product-feedback"
    survey_dir.mkdir(parents=True)
    (survey_dir / "task.toml").write_text("metadata:\n  type: survey\n", encoding="utf-8")
    chat_dir = repo / "application" / "tasks" / "chat_meal-planning-nutrition"
    chat_dir.mkdir(parents=True)
    (chat_dir / "task.toml").write_text("metadata:\n  type: chat\n", encoding="utf-8")

    from backend.service.harbor_job_service import resolve_trial_profile

    assert (
        resolve_trial_profile(
            "application/tasks/example-survey_product-feedback",
            mode="auto",
            repo_root=repo,
        )
        == "json_survey"
    )
    assert (
        resolve_trial_profile(
            "application/tasks/chat_meal-planning-nutrition",
            mode="auto",
            repo_root=repo,
        )
        == "user_sim_chat"
    )
    assert (
        resolve_trial_profile(
            "application/tasks/chat_meal-planning-nutrition",
            mode="force_docker",
            repo_root=repo,
        )
        == "docker_agent"
    )


def test_resolve_agent_name_json_survey_profile(tmp_path):
    repo = tmp_path
    survey_dir = repo / "application" / "tasks" / "example-survey_product-feedback"
    survey_dir.mkdir(parents=True)
    (survey_dir / "task.toml").write_text("metadata:\n  type: survey\n", encoding="utf-8")

    from backend.service.harbor_job_service import resolve_agent_name, resolve_trial_profile

    profile = resolve_trial_profile(
        "application/tasks/example-survey_product-feedback",
        mode="auto",
        repo_root=repo,
    )
    assert profile == "json_survey"
    assert (
        resolve_agent_name(
            "application/tasks/example-survey_product-feedback",
            repo_root=repo,
            mode="auto",
            trial_profile=profile,
        )
        == "persona-json-survey"
    )
    assert (
        resolve_agent_name(
            "application/tasks/example-survey_product-feedback",
            repo_root=repo,
            mode="force_docker",
            trial_profile="docker_agent",
        )
        == "persona-claude-code"
    )


def test_resolve_agent_name_for_chat_task(tmp_path):
    repo = tmp_path
    task_dir = repo / "application" / "tasks" / "chat_meal-planning-nutrition"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        "metadata:\n  type: chat\n",
        encoding="utf-8",
    )
    from backend.service.harbor_job_service import resolve_agent_name

    assert (
        resolve_agent_name(
            "application/tasks/chat_meal-planning-nutrition",
            repo_root=repo,
            mode="auto",
        )
        == "persona-user-sim"
    )
    assert (
        resolve_agent_name(
            "application/tasks/chat_meal-planning-nutrition",
            repo_root=repo,
            mode="force_docker",
            trial_profile="docker_agent",
        )
        == "persona-claude-code"
    )


def test_launch_auto_chat_uses_local_distributed_executor(tmp_path, monkeypatch):
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0042.yaml").write_text(
        "persona_id: '0042'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    task_dir = repo / "application" / "tasks" / "chat_meal-planning-nutrition"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text("metadata:\n  type: chat\n", encoding="utf-8")

    calls: list[dict[str, object]] = []

    def _fake_run(command, *, cwd, env):
        calls.append({"command": list(command), "cwd": cwd, "env": dict(env)})
        return 0

    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=_fake_run,
        harbor_command=("echo", "harbor"),
    )
    service._executor = _FakeExecutor()

    service.launch(
        task_path="application/tasks/chat_meal-planning-nutrition",
        persona_ids=["0042"],
        persona_model="anthropic/claude-haiku-4-5",
        execution_mode="auto",
        job_name="chat-distributed-job",
    )

    assert service._executor.calls
    assert service._executor.calls[0][0].__name__ == "_run_local_distributed"
    fn, args, kwargs = service._executor.calls[0]
    assert args[3] == "application/tasks/chat_meal-planning-nutrition"
    fn(*args, **kwargs)
    assert calls
    env = calls[0]["env"]
    assert isinstance(env, dict)
    assert env["MATRIX_CHATBOT_TASK_PATH"] == "application/tasks/chat_meal-planning-nutrition"
    pythonpath = env["PYTHONPATH"].split(":")
    assert str(repo) in pythonpath
    assert str(repo / "src") in pythonpath
    assert str(repo / "environment" / "runtime") in pythonpath
    assert str(repo / "environment" / "agents") in pythonpath
    assert str(repo / "packages" / "playground" / "src") in pythonpath
    assert str(repo / "application" / "playground") in pythonpath
    service.shutdown()


class _FakeExecutor:
    def __init__(self) -> None:
        self.calls = []

    def submit(self, fn, *args, **kwargs):
        self.calls.append((fn, args, kwargs))
        return None

    def shutdown(self, wait=False, cancel_futures=True):
        return None


def test_get_job_surfaces_reporting_queue_status(tmp_path, monkeypatch):
    repo = tmp_path
    jobs_dir = repo / "jobs"
    job_dir = jobs_dir / "demo-job"
    trial_dir = job_dir / "trial-1"
    (trial_dir / "verifier").mkdir(parents=True, exist_ok=True)
    (trial_dir / "result.json").write_text("{}", encoding="utf-8")
    (trial_dir / "config.json").write_text(
        json.dumps({"task": {"path": "application/tasks/example-task"}}),
        encoding="utf-8",
    )
    (trial_dir / "verifier" / "structured_output.json").write_text(
        json.dumps(
            {
                "presenceCheck": {"passed": True},
                "contexts": [
                    {
                        "key": "question.q1",
                        "label": "Question 1",
                        "contextType": "question_response",
                        "summaryAnalyses": [
                            {
                                "id": "question.reason_summary",
                                "title": "Reason summary",
                                "targetFacetKey": "reason",
                                "groupByFacetKey": "response",
                                "groupByMode": "categorical",
                                "summaryKind": "llm_bucket_summary",
                            }
                        ],
                        "facets": [
                            {"key": "response", "label": "Response", "role": "primary", "kind": "categorical", "value": "yes"},
                            {"key": "reason", "label": "Reason", "role": "explanation", "kind": "textual", "value": "Affordable."},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PLAYGROUND_REPORTING_ENABLE_LLM", "1")
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs",
    )
    service._executor = _FakeExecutor()

    detail = service.get_job("demo-job")

    assert detail is not None
    # Job detail no longer embeds the full aggregation payload or schedules
    # reporting — that happens via get_job_aggregation / list_jobs.
    assert detail.get("aggregation") is None
    assert service._executor.calls == []

    aggregation = service.get_job_aggregation("demo-job")
    assert aggregation["reporting"]["status"] == "queued"
    assert len(service._executor.calls) == 1
    status_path = jobs_dir / "demo-job" / "reporting_status.json"
    assert status_path.is_file()
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "queued"

    service.shutdown()


def test_get_job_aggregation_reuses_fresh_artifact(tmp_path, monkeypatch):
    repo = tmp_path
    jobs_dir = repo / "jobs"
    job_dir = jobs_dir / "cached-job"
    trial_dir = job_dir / "trial-1"
    (trial_dir / "verifier").mkdir(parents=True, exist_ok=True)
    (trial_dir / "result.json").write_text("{}", encoding="utf-8")
    (trial_dir / "config.json").write_text(
        json.dumps({"task": {"path": "application/tasks/example-task"}}),
        encoding="utf-8",
    )
    (trial_dir / "verifier" / "structured_output.json").write_text(
        json.dumps(
            {
                "presenceCheck": {"passed": True},
                "contexts": [
                    {
                        "key": "question.q1",
                        "label": "Question 1",
                        "contextType": "question_response",
                        "facets": [
                            {
                                "key": "response",
                                "label": "Response",
                                "role": "primary",
                                "kind": "categorical",
                                "value": "yes",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("PLAYGROUND_REPORTING_ENABLE_LLM", raising=False)
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs",
    )
    service._executor = _FakeExecutor()

    first = service.get_job_aggregation("cached-job")
    generated_at = first["generatedAt"]
    artifact_mtime = (job_dir / "aggregation.json").stat().st_mtime_ns

    second = service.get_job_aggregation("cached-job")
    assert second["generatedAt"] == generated_at
    assert (job_dir / "aggregation.json").stat().st_mtime_ns == artifact_mtime

    # New completed trial makes the cache stale and forces a rebuild.
    trial_2 = job_dir / "trial-2"
    (trial_2 / "verifier").mkdir(parents=True, exist_ok=True)
    (trial_2 / "result.json").write_text("{}", encoding="utf-8")
    (trial_2 / "verifier" / "structured_output.json").write_text(
        (trial_dir / "verifier" / "structured_output.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    third = service.get_job_aggregation("cached-job")
    assert third["coverage"]["trialCount"] == 2
    assert third["coverage"]["completedTrials"] == 2
    assert (job_dir / "aggregation.json").stat().st_mtime_ns > artifact_mtime

    service.shutdown()


def test_launch_ios_cua_uses_use_computer_environment(tmp_path, monkeypatch):
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0020.yaml").write_text(
        "persona_id: '0020'\nversion: '1.0'\nsource: OASIS\ndimensions: {}\n",
        encoding="utf-8",
    )
    task_dir = repo / "application" / "tasks" / "example-computer-use-ios_photo-access-review"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text("metadata:\n  type: mobile\n", encoding="utf-8")

    def _fake_run(command, *, cwd, env):
        return 0

    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=_fake_run,
        harbor_command=("echo", "harbor"),
    )

    job_name = service.launch(
        task_path="application/tasks/example-computer-use-ios_photo-access-review",
        persona_ids=["0020"],
        persona_model="anthropic/claude-sonnet-4-6",
        cua_backend="ios",
        job_name="ios-cua-job",
    )
    assert job_name == "ios-cua-job"
    text = (
        repo / "configs" / "jobs" / "application-task-job-recipe" / "ios-cua-job.yaml"
    ).read_text(encoding="utf-8")
    assert "type: use-computer" in text
    assert "platform: ios" in text
    assert "cua_backend: ios" in text
    assert "max_steps: 100" in text
    assert "max_turns:" not in text
    service.shutdown()


def test_launch_docker_cua_injects_max_turns_not_max_steps(tmp_path, monkeypatch):
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0020.yaml").write_text(
        "persona_id: '0020'\nversion: '1.0'\nsource: OASIS\ndimensions: {}\n",
        encoding="utf-8",
    )
    task_dir = repo / "application" / "tasks" / "example-computer-use-linux_note-to-csv"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text("metadata:\n  type: computer\n", encoding="utf-8")

    def _fake_run(command, *, cwd, env):
        return 0

    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=_fake_run,
        harbor_command=("echo", "harbor"),
    )

    job_name = service.launch(
        task_path="application/tasks/example-computer-use-linux_note-to-csv",
        persona_ids=["0020"],
        persona_model="anthropic/claude-sonnet-4-6",
        cua_backend="docker",
        job_name="docker-cua-job",
    )
    assert job_name == "docker-cua-job"
    text = (
        repo / "configs" / "jobs" / "application-task-job-recipe" / "docker-cua-job.yaml"
    ).read_text(encoding="utf-8")
    assert "type: docker" in text
    assert "cua_backend: docker" in text
    assert "max_turns: 100" in text
    assert "max_steps:" not in text
    service.shutdown()


def test_run_harbor_passes_yes_to_skip_host_env_prompt(tmp_path):
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    config_path = repo / "configs" / "jobs" / "demo-job.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("job_name: demo-job\n", encoding="utf-8")

    calls: list[list[str]] = []

    def _fake_run(command, *, cwd, env):
        calls.append(list(command))
        return 0

    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs",
        command_runner=_fake_run,
        harbor_command=("echo", "harbor", "run"),
    )
    with service._guard:
        service._launches["demo-job"] = HarborLaunchRecord(
            job_name="demo-job",
            config_path="configs/jobs/demo-job.yaml",
        )

    service._run_harbor("demo-job", config_path)
    assert calls == [["echo", "harbor", "run", "--yes", "-c", "configs/jobs/demo-job.yaml"]]
    service.shutdown()


def test_run_harbor_scores_trial_when_result_appears(tmp_path, monkeypatch):
    import time

    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    config_path = repo / "configs" / "jobs" / "demo-job.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("job_name: demo-job\n", encoding="utf-8")

    scored: list[str] = []

    def _fake_run(command, *, cwd, env):
        del command, cwd, env
        trial = jobs_dir / "demo-job" / "trial-x"
        trial.mkdir(parents=True)
        (trial / "config.json").write_text("{}", encoding="utf-8")
        (trial / "result.json").write_text("{}", encoding="utf-8")
        # Let the watcher poll once before Harbor "exits".
        time.sleep(0.25)
        return 0

    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs",
        command_runner=_fake_run,
        harbor_command=("echo", "harbor", "run"),
        _host_score_poll_sec=0.05,
        _host_score_join_timeout_sec=5.0,
    )
    monkeypatch.setattr(
        service,
        "_score_finished_trial_on_host",
        lambda trial_dir: scored.append(trial_dir.name),
    )
    monkeypatch.setattr(service, "_maybe_run_host_verifier", lambda job_name: None)
    monkeypatch.setattr(service, "_maybe_generate_post_run_feedback", lambda job_name: None)
    monkeypatch.setattr(
        service, "_maybe_schedule_reporting", lambda job_name, job_dir: None
    )
    with service._guard:
        service._launches["demo-job"] = HarborLaunchRecord(
            job_name="demo-job",
            config_path="configs/jobs/demo-job.yaml",
        )

    service._run_harbor("demo-job", config_path)

    assert scored == ["trial-x"]
    service.shutdown()


def test_score_finished_trial_on_host_runs_verifier_then_feedback(tmp_path, monkeypatch):
    repo = tmp_path
    trial_dir = repo / "jobs" / "demo-job" / "trial-a"
    trial_dir.mkdir(parents=True)
    (trial_dir / "config.json").write_text("{}", encoding="utf-8")
    (trial_dir / "result.json").write_text("{}", encoding="utf-8")

    order: list[str] = []
    monkeypatch.setattr(
        "playground.host_verifier.maybe_run_host_verifier",
        lambda *, repo_root, trial_dir, timeout_sec=None: order.append("verify"),
    )
    monkeypatch.setattr(
        "playground.post_run_feedback.maybe_write_trial_user_feedback",
        lambda *, repo_root, trial_dir: order.append("feedback"),
    )
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        generated_configs_dir=repo / "configs" / "jobs",
    )

    service._score_finished_trial_on_host(trial_dir)

    assert order == ["verify", "feedback"]
    service.shutdown()


def test_trial_live_stage_from_artifacts(tmp_path):
    from backend.service.harbor_job_service import (
        _resolve_trial_stage,
        _stage_from_phase,
        _trial_live_stage,
    )

    trial_dir = tmp_path / "trial-a"
    assert _trial_live_stage(trial_dir) == "queued"

    trial_dir.mkdir()
    (trial_dir / "config.json").write_text("{}", encoding="utf-8")
    assert _trial_live_stage(trial_dir) == "starting_env"

    agent_dir = trial_dir / "agent"
    agent_dir.mkdir()
    (agent_dir / "setup").mkdir()
    assert _trial_live_stage(trial_dir) == "starting_env"

    (agent_dir / "trajectory.json").write_text("[]", encoding="utf-8")
    assert _trial_live_stage(trial_dir) == "agent_running"

    verifier_dir = trial_dir / "verifier"
    verifier_dir.mkdir()
    (verifier_dir / "reward.txt").write_text("1.0", encoding="utf-8")
    assert _trial_live_stage(trial_dir) == "verifying"

    (trial_dir / "result.json").write_text("{}", encoding="utf-8")
    assert _trial_live_stage(trial_dir) is None

    assert _stage_from_phase("persona_thinking") == "agent_running"
    assert _stage_from_phase("harbor_collecting_artifacts") == "verifying"
    assert _resolve_trial_stage(trial_dir, phase="persona_kickoff", completed=False) == "agent_running"


def test_get_job_status_incremental(tmp_path):
    jobs_dir = tmp_path / "jobs"
    job_dir = jobs_dir / "pg-batch"
    job_dir.mkdir(parents=True)
    for name in ("t0", "t1", "t2"):
        (job_dir / name).mkdir()

    service = HarborJobService(
        repo_root=tmp_path,
        jobs_dir=jobs_dir,
        generated_configs_dir=tmp_path / "generated",
    )

    first = service.get_job_status("pg-batch", since=0)
    assert first["full"] is True
    assert first["trialCount"] == 3
    assert first["statuses"] == [0, 0, 0]
    assert first["counts"] == {"pending": 3, "running": 0, "done": 0, "error": 0}

    # t0 finishes successfully -> incremental delta only.
    (job_dir / "t0" / "result.json").write_text("{}", encoding="utf-8")
    delta = service.get_job_status("pg-batch", since=first["version"])
    assert delta["full"] is False
    assert delta["changes"] == [[0, 2]]
    assert delta["counts"]["done"] == 1

    # t1 fails.
    (job_dir / "t1" / "result.json").write_text(
        json.dumps({"exception_info": {"exception_message": "boom"}}),
        encoding="utf-8",
    )
    delta2 = service.get_job_status("pg-batch", since=delta["version"])
    assert delta2["full"] is False
    assert delta2["changes"] == [[1, 3]]
    assert delta2["counts"] == {"pending": 1, "running": 0, "done": 1, "error": 1}

    # A stale/zero cursor always yields a fresh full snapshot.
    full = service.get_job_status("pg-batch", since=0)
    assert full["full"] is True
    assert full["statuses"] == [2, 3, 0]


def test_get_job_status_running_marker(tmp_path):
    jobs_dir = tmp_path / "jobs"
    job_dir = jobs_dir / "pg-batch"
    job_dir.mkdir(parents=True)
    (job_dir / "t0").mkdir()
    (job_dir / "t0" / "config.json").write_text("{}", encoding="utf-8")

    service = HarborJobService(
        repo_root=tmp_path,
        jobs_dir=jobs_dir,
        generated_configs_dir=tmp_path / "generated",
    )
    snapshot = service.get_job_status("pg-batch", since=0)
    assert snapshot["statuses"] == [1]
    assert snapshot["counts"]["running"] == 1


def test_list_jobs_skips_aggregation_rebuild_for_completed_reporting(tmp_path, monkeypatch):
    import json

    jobs_dir = tmp_path / "jobs"
    job_dir = jobs_dir / "done-job"
    job_dir.mkdir(parents=True)
    (job_dir / "result.json").write_text(
        json.dumps(
            {
                "finished_at": "2026-07-01T12:00:00Z",
                "n_total_trials": 1008,
                "stats": {"n_completed_trials": 1008, "n_errored_trials": 0},
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "aggregation.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "artifactType": "job_aggregation",
                "coverage": {
                    "trialCount": 1008,
                    "completedTrials": 1008,
                    "pendingTrials": 0,
                },
                "fields": [],
                "contexts": [],
                "reporting": {"status": "completed", "totalUnits": 0, "completedUnits": 0},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PLAYGROUND_REPORTING_ENABLE_LLM", "1")
    calls: list[str] = []

    def _boom(*_args, **_kwargs):
        calls.append("build")
        raise AssertionError("list_jobs must not rebuild aggregation for terminal reporting")

    monkeypatch.setattr(
        "backend.service.harbor_job_service.build_job_aggregation",
        _boom,
    )
    service = HarborJobService(
        repo_root=tmp_path,
        jobs_dir=jobs_dir,
        generated_configs_dir=tmp_path / "configs",
    )
    rows = service.list_jobs()
    assert len(rows) == 1
    assert rows[0]["jobName"] == "done-job"
    assert rows[0]["trialCount"] == 1008
    assert rows[0]["completedTrials"] == 1008
    assert rows[0]["status"] == "success"
    assert calls == []
    service.shutdown()


def test_list_jobs_reports_success_and_failed_status(tmp_path):
    import json

    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()

    success_job = jobs_dir / "job-success"
    success_job.mkdir()
    (success_job / "trial-a").mkdir()
    (success_job / "trial-a" / "result.json").write_text("{}", encoding="utf-8")
    (success_job / "result.json").write_text(
        json.dumps(
            {
                "finished_at": "2026-07-01T12:00:00Z",
                "n_total_trials": 1,
                "stats": {"n_completed_trials": 1, "n_errored_trials": 0},
            }
        ),
        encoding="utf-8",
    )

    failed_job = jobs_dir / "job-failed"
    failed_job.mkdir()
    (failed_job / "trial-a").mkdir()
    (failed_job / "trial-a" / "result.json").write_text("{}", encoding="utf-8")
    (failed_job / "result.json").write_text(
        json.dumps(
            {
                "finished_at": "2026-07-01T12:05:00Z",
                "stats": {"n_errored_trials": 1},
            }
        ),
        encoding="utf-8",
    )

    running_job = jobs_dir / "job-running"
    running_job.mkdir()
    (running_job / "trial-a").mkdir()

    # An orphaned job (trial dirs present but incomplete, and no in-memory launch
    # record because the backend was restarted) is terminal, not "running".
    orphaned_job = jobs_dir / "job-orphaned"
    orphaned_job.mkdir()
    (orphaned_job / "trial-a").mkdir()

    # A fully completed cohort without a job-level result.json still resolves to
    # a terminal status from disk instead of a stale "running".
    completed_job = jobs_dir / "job-completed"
    completed_job.mkdir()
    (completed_job / "trial-a").mkdir()
    (completed_job / "trial-a" / "result.json").write_text("{}", encoding="utf-8")

    service = HarborJobService(
        repo_root=tmp_path,
        jobs_dir=jobs_dir,
        generated_configs_dir=tmp_path / "configs",
    )
    # Only "job-running" is actively driven by this process.
    service._launches["job-running"] = HarborLaunchRecord(
        job_name="job-running",
        status="running",
    )
    rows = {row["jobName"]: row for row in service.list_jobs()}

    assert rows["job-success"]["status"] == "success"
    assert rows["job-success"]["failedTrials"] == 0
    assert rows["job-failed"]["status"] == "failed"
    assert rows["job-failed"]["failedTrials"] == 1
    assert rows["job-running"]["status"] == "running"
    assert rows["job-orphaned"]["status"] == "failed"
    assert rows["job-completed"]["status"] == "success"
    service.shutdown()


def test_list_jobs_reports_application_type_from_generated_config(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()

    survey_job = jobs_dir / "pg-survey-job"
    survey_job.mkdir()
    (survey_job / "trial-a").mkdir()

    task_dir = tmp_path / "application" / "tasks" / "example-survey"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text("metadata:\n  type: survey\n", encoding="utf-8")

    (configs_dir / "pg-survey-job.yaml").write_text(
        "# Generated by Playground POST /api/harbor/jobs\n"
        "# Task: application/tasks/example-survey\n"
        "job_name: pg-survey-job\n",
        encoding="utf-8",
    )

    service = HarborJobService(
        repo_root=tmp_path,
        jobs_dir=jobs_dir,
        generated_configs_dir=configs_dir,
    )
    rows = {row["jobName"]: row for row in service.list_jobs()}
    assert rows["pg-survey-job"]["applicationType"] == "survey"
    service.shutdown()


def test_launch_web_cli_stages_shared_web_cli_environment(tmp_path, monkeypatch):
    repo = tmp_path
    jobs_dir = repo / "jobs"
    jobs_dir.mkdir()
    task_dir = repo / "application" / "tasks" / "example-web-playwright_quote-choice"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        "\n".join(
            [
                "[metadata]",
                'type = "web"',
                "",
                "[environment]",
                'definition = "application/shared-web-playwright"',
            ]
        ),
        encoding="utf-8",
    )
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample").mkdir(parents=True)
    (repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("playground.harbor.playground._repo_root", lambda: repo)
    service = HarborJobService(
        repo_root=repo,
        jobs_dir=jobs_dir,
        generated_configs_dir=repo / "configs" / "jobs" / "application-task-job-recipe",
        command_runner=lambda *args, **kwargs: 0,
        harbor_command=("echo", "harbor"),
    )
    service._executor = _FakeExecutor()

    job_name = service.launch(
        task_path="application/tasks/example-web-playwright_quote-choice",
        persona_ids=["0001"],
        persona_pool="persona/datasets/matraix-persona-dev-sample",
        agent_name="persona-codex",
        persona_model="openai/gpt-4o-mini",
        job_name="web-cli-job",
        execution_mode="auto",
    )
    assert job_name == "web-cli-job"
    config_path = repo / "configs" / "jobs" / "application-task-job-recipe" / "web-cli-job.yaml"
    text = config_path.read_text(encoding="utf-8")
    assert "web_cli_staged_tasks/example-web-playwright_quote-choice" in text
    staged_root = repo / "data" / "cache" / "playground" / "web_cli_staged_tasks"
    staged_tomls = list(staged_root.rglob("task.toml"))
    assert staged_tomls
    assert 'application/shared-web-cli' in staged_tomls[0].read_text(encoding="utf-8")
    service.shutdown()
