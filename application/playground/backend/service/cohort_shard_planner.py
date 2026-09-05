"""Split a large Harbor job into internal workers (same job_name).

Playground Parallel is the global in-flight cap. Env vars only cap packing
and cluster width. See docs/environment/large-scale-runs.md.
"""

from __future__ import annotations

import copy
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


DEFAULT_SHARD_SIZE = 100
DEFAULT_SHARD_CONCURRENCY = 8
DEFAULT_HOST_PACK_CONCURRENCY = 32
DEFAULT_WEB_PACK_CONCURRENCY = 1
SHARD_SIZE_ENV = "MATRIX_SHARD_SIZE"
SHARD_CONCURRENCY_ENV = "MATRIX_SHARD_CONCURRENCY"
HOST_PACK_CONCURRENCY_ENV = "MATRIX_HOST_PACK_CONCURRENCY"
WEB_PACK_CONCURRENCY_ENV = "MATRIX_WEB_PACK_CONCURRENCY"
MAX_CONCURRENT_TRIALS_ENV = "MATRIX_MAX_CONCURRENT_TRIALS"
_NATIVE_TRIAL_PROFILES = frozenset({"json_survey", "user_sim_chat"})


@dataclass(frozen=True)
class CohortShard:
    """One internal work slice under a run."""

    shard_index: int
    shard_count: int
    persona_ids: tuple[str, ...]
    offset: int
    limit: int

    @property
    def key(self) -> str:
        return "s{}".format(self.shard_index)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["key"] = self.key
        return payload


@dataclass(frozen=True)
class ShardLayout:
    """How N people and Parallel map onto workers.

    ``requested_parallel`` is what the operator set (report / parent YAML).
    ``effective_parallel`` is global in-flight after env caps: min(N, Parallel,
    pack * max_workers, MATRIX_MAX_CONCURRENT_TRIALS).
    """

    requested_parallel: int
    effective_parallel: int
    pack: int
    worker_count: int
    shard_size: int
    per_shard_concurrent: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "requestedParallel": self.requested_parallel,
            "effectiveParallel": self.effective_parallel,
            "pack": self.pack,
            "workerCount": self.worker_count,
            "shardSize": self.shard_size,
            "perShardConcurrent": list(self.per_shard_concurrent),
        }


@dataclass(frozen=True)
class JobShardPlan:
    layout: ShardLayout
    shards: list[tuple[CohortShard, dict[str, Any]]]


def _positive_int(raw: str, default: int) -> int:
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return default


def _ceil_div(num: int, den: int) -> int:
    den = max(1, int(den))
    return (max(0, int(num)) + den - 1) // den


def shard_size_from_env() -> int:
    return _positive_int((os.environ.get(SHARD_SIZE_ENV) or "").strip(), DEFAULT_SHARD_SIZE)


def shard_concurrency_from_env() -> int:
    return _positive_int(
        (os.environ.get(SHARD_CONCURRENCY_ENV) or "").strip(),
        DEFAULT_SHARD_CONCURRENCY,
    )


def host_pack_concurrency_from_env() -> int:
    return _positive_int(
        (os.environ.get(HOST_PACK_CONCURRENCY_ENV) or "").strip(),
        DEFAULT_HOST_PACK_CONCURRENCY,
    )


def web_pack_concurrency_from_env() -> int:
    return _positive_int(
        (os.environ.get(WEB_PACK_CONCURRENCY_ENV) or "").strip(),
        DEFAULT_WEB_PACK_CONCURRENCY,
    )


def max_concurrent_trials_from_env() -> int | None:
    raw = (os.environ.get(MAX_CONCURRENT_TRIALS_ENV) or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


def pack_concurrency_for_profile(trial_profile: str | None) -> int:
    if (trial_profile or "").strip().lower() in _NATIVE_TRIAL_PROFILES:
        return host_pack_concurrency_from_env()
    return web_pack_concurrency_from_env()


def _allocate_concurrency(
    parallel: int, pack: int, shard_limits: Sequence[int]
) -> tuple[int, ...]:
    remaining = max(0, int(parallel))
    pack = max(1, int(pack))
    allocated: list[int] = []
    for limit in shard_limits:
        take = min(pack, max(0, int(limit)), remaining)
        allocated.append(take)
        remaining -= take
    return tuple(allocated)


def plan_shard_layout(
    *,
    n: int,
    parallel: int,
    pack: int,
    max_workers: int | None = None,
    max_parallel: int | None = None,
) -> ShardLayout:
    """Map cohort size and Parallel onto workers without rewriting Parallel.

    in_flight ≈ min(N, Parallel, pack * max_workers [, MATRIX_MAX_CONCURRENT_TRIALS])
    workers = ceil(in_flight / pack), then min with N and max_workers.
    """
    n = max(0, int(n))
    requested = max(1, int(parallel or 1))
    pack = max(1, int(pack))
    max_workers = max(1, int(max_workers if max_workers is not None else shard_concurrency_from_env()))
    cap = requested
    if max_parallel is not None:
        cap = min(cap, max(1, int(max_parallel)))
    if n <= 0:
        return ShardLayout(
            requested_parallel=requested,
            effective_parallel=0,
            pack=pack,
            worker_count=0,
            shard_size=1,
            per_shard_concurrent=(),
        )
    cluster = pack * max_workers
    effective = min(cap, n, cluster)
    workers = min(n, max_workers, _ceil_div(effective, pack))
    workers = max(1, workers)
    shard_size = _ceil_div(n, workers)
    limits: list[int] = []
    remaining_people = n
    for _ in range(workers):
        take = min(shard_size, remaining_people)
        if take <= 0:
            break
        limits.append(take)
        remaining_people -= take
    concurrent = _allocate_concurrency(effective, pack, limits)
    return ShardLayout(
        requested_parallel=requested,
        effective_parallel=int(sum(concurrent)),
        pack=pack,
        worker_count=len(limits),
        shard_size=shard_size,
        per_shard_concurrent=concurrent,
    )


def plan_cohort_shards(
    persona_ids: Sequence[str] | Iterable[str],
    *,
    shard_size: int = DEFAULT_SHARD_SIZE,
) -> list[CohortShard]:
    """Split persona IDs into contiguous internal shards of at most ``shard_size``.

    Empty input yields no shards. ``shard_size`` must be >= 1.
    Callers attach the result to the run’s control-plane plan; do not expose
    each shard as its own product-level run or job name.
    """
    ids = [str(pid).strip() for pid in persona_ids if str(pid).strip()]
    size = max(1, int(shard_size))
    if not ids:
        return []
    shard_count = (len(ids) + size - 1) // size
    shards: list[CohortShard] = []
    for index in range(shard_count):
        offset = index * size
        chunk = tuple(ids[offset : offset + size])
        shards.append(
            CohortShard(
                shard_index=index,
                shard_count=shard_count,
                persona_ids=chunk,
                offset=offset,
                limit=len(chunk),
            )
        )
    return shards


def plan_pool_shards_from_manifest(
    manifest_personas: Sequence[dict[str, Any]],
    *,
    shard_size: int = DEFAULT_SHARD_SIZE,
) -> list[CohortShard]:
    """Plan internal shards from a persona pool manifest ``personas`` list."""
    ids: list[str] = []
    for row in manifest_personas:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("persona_id") or row.get("personaId") or "").strip()
        if pid:
            ids.append(pid)
    return plan_cohort_shards(ids, shard_size=shard_size)


def _agent_persona_id(agent: dict[str, Any], index: int) -> str:
    kwargs = agent.get("kwargs") if isinstance(agent.get("kwargs"), dict) else {}
    path = str((kwargs or {}).get("persona_path") or "")
    stem = Path(path).stem
    if stem.startswith("persona_"):
        return stem[len("persona_") :]
    return stem or str(index)


def _slice_job_config(
    job_config: dict[str, Any],
    agents: list[dict[str, Any]],
    ids: list[str],
    *,
    shard_size: int,
    per_shard_concurrent: Sequence[int] | None = None,
) -> list[tuple[CohortShard, dict[str, Any]]]:
    planned = plan_cohort_shards(ids, shard_size=shard_size)
    shards: list[tuple[CohortShard, dict[str, Any]]] = []
    for index, shard in enumerate(planned):
        config = copy.deepcopy(job_config)
        config["agents"] = [
            copy.deepcopy(agent)
            for agent in agents[shard.offset : shard.offset + shard.limit]
        ]
        if per_shard_concurrent is not None and index < len(per_shard_concurrent):
            concurrent = max(0, int(per_shard_concurrent[index]))
            if concurrent:
                config["n_concurrent_trials"] = concurrent
        shards.append((shard, config))
    return shards


def plan_job_config_shards(
    job_config: dict[str, Any],
    *,
    shard_size: int | None = None,
    trial_profile: str | None = None,
    pack: int | None = None,
    max_workers: int | None = None,
    max_parallel: int | None = None,
) -> list[tuple[CohortShard, dict[str, Any]]]:
    """Slice ``agents`` into shard configs that keep the same ``job_name``.

    Pass ``shard_size`` alone for a fixed-size split (tests). Otherwise workers
    and per-shard ``n_concurrent_trials`` follow Parallel and pack caps.
    """
    return plan_job_shards(
        job_config,
        shard_size=shard_size,
        trial_profile=trial_profile,
        pack=pack,
        max_workers=max_workers,
        max_parallel=max_parallel,
    ).shards


def plan_job_shards(
    job_config: dict[str, Any],
    *,
    shard_size: int | None = None,
    trial_profile: str | None = None,
    pack: int | None = None,
    max_workers: int | None = None,
    max_parallel: int | None = None,
) -> JobShardPlan:
    """Demand-driven shard plan. Parent ``n_concurrent_trials`` stays requested."""
    agents = [row for row in (job_config.get("agents") or []) if isinstance(row, dict)]
    ids = [_agent_persona_id(agent, index) for index, agent in enumerate(agents)]
    requested = max(1, int(job_config.get("n_concurrent_trials") or 1))
    legacy = shard_size is not None and pack is None and trial_profile is None
    if not agents:
        layout = plan_shard_layout(
            n=0,
            parallel=requested,
            pack=max(1, int(pack or pack_concurrency_for_profile(trial_profile))),
            max_workers=max_workers,
            max_parallel=max_parallel if max_parallel is not None else max_concurrent_trials_from_env(),
        )
        return JobShardPlan(layout=layout, shards=[])
    if legacy:
        size = max(1, int(shard_size))
        shards = _slice_job_config(job_config, agents, ids, shard_size=size)
        layout = ShardLayout(
            requested_parallel=requested,
            effective_parallel=requested,
            pack=size,
            worker_count=len(shards),
            shard_size=size,
            per_shard_concurrent=tuple(
                max(1, int((row[1].get("n_concurrent_trials") or requested)))
                for row in shards
            ),
        )
        return JobShardPlan(layout=layout, shards=shards)
    resolved_pack = max(1, int(pack if pack is not None else pack_concurrency_for_profile(trial_profile)))
    resolved_max_parallel = (
        max_parallel if max_parallel is not None else max_concurrent_trials_from_env()
    )
    layout = plan_shard_layout(
        n=len(agents),
        parallel=requested,
        pack=resolved_pack,
        max_workers=max_workers,
        max_parallel=resolved_max_parallel,
    )
    shards = _slice_job_config(
        job_config,
        agents,
        ids,
        shard_size=layout.shard_size,
        per_shard_concurrent=layout.per_shard_concurrent,
    )
    return JobShardPlan(layout=layout, shards=shards)


def should_fanout_cloud_shards(dispatch: str | None, shard_count: int) -> bool:
    return dispatch in {"modal_jobs", "gke_workers"} and shard_count > 1


def should_fanout_harbor_shards(
    *,
    family: str | None,
    environment: str | None,
    dispatch: str | None,
    shard_count: int,
) -> bool:
    """Split web/linux Harbor processes on Modal/GKE when Parallel needs more workers."""
    if shard_count <= 1 or dispatch:
        return False
    if (family or "").strip().lower() not in {"modal", "gcp"}:
        return False
    return (environment or "").strip().lower() in {"modal", "gke"}
