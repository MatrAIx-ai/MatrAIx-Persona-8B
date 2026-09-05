"""Tests for cohort shard planner."""

from __future__ import annotations

from backend.service.cohort_shard_planner import (
    plan_cohort_shards,
    plan_job_config_shards,
    plan_job_shards,
    plan_pool_shards_from_manifest,
    plan_shard_layout,
    should_fanout_cloud_shards,
    should_fanout_harbor_shards,
)


def test_plan_cohort_shards_splits_evenly():
    ids = [f"{i:04d}" for i in range(1, 11)]
    shards = plan_cohort_shards(ids, shard_size=4)
    assert len(shards) == 3
    assert shards[0].persona_ids == ("0001", "0002", "0003", "0004")
    assert shards[0].shard_count == 3
    assert shards[2].persona_ids == ("0009", "0010")
    assert shards[2].limit == 2
    # Shards are internal slices under one run’s plan.
    assert [s.shard_index for s in shards] == [0, 1, 2]


def test_plan_cohort_shards_empty():
    assert plan_cohort_shards([], shard_size=100) == []


def test_plan_pool_shards_from_manifest():
    rows = [{"persona_id": "a"}, {"personaId": "b"}, {"other": 1}]
    shards = plan_pool_shards_from_manifest(rows, shard_size=1)
    assert [s.persona_ids for s in shards] == [("a",), ("b",)]


def test_plan_job_config_shards_keeps_job_name():
    config = {
        "job_name": "batch-one",
        "jobs_dir": "jobs",
        "agents": [
            {"name": "persona-json-survey", "kwargs": {"persona_path": "persona/p/persona_0001.yaml"}},
            {"name": "persona-json-survey", "kwargs": {"persona_path": "persona/p/persona_0002.yaml"}},
            {"name": "persona-json-survey", "kwargs": {"persona_path": "persona/p/persona_0003.yaml"}},
        ],
    }
    planned = plan_job_config_shards(config, shard_size=2)
    assert len(planned) == 2
    assert planned[0][0].key == "s0"
    assert planned[0][1]["job_name"] == "batch-one"
    assert planned[1][1]["job_name"] == "batch-one"
    assert len(planned[0][1]["agents"]) == 2
    assert len(planned[1][1]["agents"]) == 1
    assert should_fanout_cloud_shards("modal_jobs", 2)
    assert not should_fanout_cloud_shards("modal_jobs", 1)
    assert not should_fanout_cloud_shards(None, 5)
    assert should_fanout_harbor_shards(
        family="modal", environment="modal", dispatch=None, shard_count=2
    )
    assert should_fanout_harbor_shards(
        family="gcp", environment="gke", dispatch=None, shard_count=3
    )
    assert not should_fanout_harbor_shards(
        family="modal", environment="host", dispatch="modal_jobs", shard_count=4
    )
    assert not should_fanout_harbor_shards(
        family="modal", environment="docker", dispatch="modal_jobs", shard_count=4
    )
    assert not should_fanout_harbor_shards(
        family="local", environment="docker", dispatch=None, shard_count=20
    )


def test_shard_size_default_is_100(monkeypatch) -> None:
    monkeypatch.delenv("MATRIX_SHARD_SIZE", raising=False)
    from backend.service.cohort_shard_planner import (
        DEFAULT_SHARD_SIZE,
        shard_size_from_env,
    )

    assert DEFAULT_SHARD_SIZE == 100
    assert shard_size_from_env() == 100


def test_layout_small_parallel_stays_on_one_worker() -> None:
    layout = plan_shard_layout(n=100, parallel=2, pack=32, max_workers=8)
    assert layout.worker_count == 1
    assert layout.effective_parallel == 2
    assert layout.per_shard_concurrent == (2,)


def test_layout_fills_pack_then_adds_workers() -> None:
    layout = plan_shard_layout(n=100, parallel=64, pack=32, max_workers=8)
    assert layout.requested_parallel == 64
    assert layout.worker_count == 2
    assert layout.per_shard_concurrent == (32, 32)
    assert layout.effective_parallel == 64


def test_layout_cluster_caps_parallel() -> None:
    layout = plan_shard_layout(n=10000, parallel=500, pack=32, max_workers=8)
    assert layout.worker_count == 8
    assert layout.effective_parallel == 256
    assert layout.per_shard_concurrent == (32,) * 8


def test_layout_web_pack_one() -> None:
    layout = plan_shard_layout(n=100, parallel=8, pack=1, max_workers=8)
    assert layout.worker_count == 8
    assert layout.effective_parallel == 8
    assert layout.per_shard_concurrent == (1,) * 8


def test_layout_remainder_goes_to_later_workers() -> None:
    layout = plan_shard_layout(n=100, parallel=50, pack=32, max_workers=8)
    assert layout.worker_count == 2
    assert layout.per_shard_concurrent == (32, 18)
    assert layout.effective_parallel == 50


def test_layout_max_parallel_env_cap() -> None:
    layout = plan_shard_layout(
        n=1000, parallel=500, pack=32, max_workers=8, max_parallel=64
    )
    assert layout.requested_parallel == 500
    assert layout.effective_parallel == 64
    assert layout.worker_count == 2
    assert layout.per_shard_concurrent == (32, 32)


def test_demand_shards_keep_parent_parallel() -> None:
    agents = [
        {"name": "persona-json-survey", "kwargs": {"persona_path": f"persona/p/persona_{i:04d}.yaml"}}
        for i in range(1, 5)
    ]
    config = {
        "job_name": "batch-one",
        "n_concurrent_trials": 2,
        "agents": agents,
    }
    planned = plan_job_shards(config, trial_profile="json_survey", pack=32, max_workers=8)
    assert planned.layout.worker_count == 1
    assert len(planned.shards) == 1
    assert planned.shards[0][1]["n_concurrent_trials"] == 2
    assert config["n_concurrent_trials"] == 2


def test_demand_shards_split_when_parallel_exceeds_pack() -> None:
    agents = [
        {"name": "persona-json-survey", "kwargs": {"persona_path": f"persona/p/persona_{i:04d}.yaml"}}
        for i in range(1, 101)
    ]
    config = {
        "job_name": "batch-one",
        "n_concurrent_trials": 64,
        "agents": agents,
    }
    planned = plan_job_shards(config, trial_profile="json_survey", pack=32, max_workers=8)
    assert len(planned.shards) == 2
    assert planned.shards[0][1]["n_concurrent_trials"] == 32
    assert planned.shards[1][1]["n_concurrent_trials"] == 32
    assert config["n_concurrent_trials"] == 64
    assert len(planned.shards[0][1]["agents"]) == 50
    assert len(planned.shards[1][1]["agents"]) == 50


def test_demand_shards_do_not_split_on_shard_size_env(monkeypatch) -> None:
    monkeypatch.setenv("MATRIX_SHARD_SIZE", "2")
    agents = [
        {"name": "persona-json-survey", "kwargs": {"persona_path": f"persona/p/persona_{i:04d}.yaml"}}
        for i in range(1, 5)
    ]
    config = {"job_name": "batch-one", "n_concurrent_trials": 2, "agents": agents}
    planned = plan_job_shards(config, trial_profile="json_survey", pack=32, max_workers=8)
    assert len(planned.shards) == 1
    assert planned.shards[0][1]["n_concurrent_trials"] == 2
