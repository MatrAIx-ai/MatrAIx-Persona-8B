"""Tests for persona pool catalog and sampling."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from backend.service.persona_pool_service import PersonaPoolService


def _write_pool(repo: Path) -> None:
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    (pool / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions:\n  economic_motivation: Price-sensitive\n",
        encoding="utf-8",
    )
    (pool / "persona_0002.yaml").write_text(
        "persona_id: '0002'\nversion: '1.0'\nsource: OASIS\ndimensions:\n  economic_motivation: Indifferent\n",
        encoding="utf-8",
    )
    (pool / "manifest.json").write_text(
        json.dumps(
            {
                "count": 2,
                "smoke_persona_id": "0001",
                "schema_version": "1.0",
                "source_counts": {"Nemotron": 1, "OASIS": 1},
                "dimension_categories": "persona/schema/dimension_categories.json",
                "personas": [
                    {
                        "persona_id": "0001",
                        "path": "persona/datasets/matraix-persona-dev-sample/persona_0001.yaml",
                        "source": "Nemotron",
                        "dimensions": {"economic_motivation": "Price-sensitive"},
                    },
                    {
                        "persona_id": "0002",
                        "path": "persona/datasets/matraix-persona-dev-sample/persona_0002.yaml",
                        "source": "OASIS",
                        "dimensions": {"economic_motivation": "Indifferent"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    schema = repo / "persona" / "schema"
    schema.mkdir(parents=True)
    (schema / "dimension_categories.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "personaSources": ["Nemotron", "OASIS"],
                "devProfile": {
                    "dimensionCount": 1,
                    "groups": [
                        {
                            "id": "values",
                            "label": "Values",
                            "dimensionIds": ["economic_motivation"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    dims = schema / "dimensions.json"
    dims.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "dimensions": [
                    {
                        "id": "economic_motivation",
                        "label": "Economic motivation",
                        "category": "Values & Motivation",
                        "values": ["Price-sensitive", "Indifferent"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_list_persona_ids_from_yaml_filenames(tmp_path):
    repo = tmp_path
    _write_pool(repo)
    service = PersonaPoolService(repo_root=repo)
    listed = service.list_persona_ids("persona/datasets/matraix-persona-dev-sample")
    assert listed["count"] == 2
    assert listed["personaIds"] == ["0001", "0002"]


def test_list_datasets_includes_default_and_extras(tmp_path):
    repo = tmp_path
    _write_pool(repo)
    extra = repo / "persona" / "datasets" / "bench-dev-extra"
    extra.mkdir(parents=True)
    (extra / "manifest.json").write_text(
        json.dumps({"count": 1, "personas": [{"persona_id": "0001"}]}),
        encoding="utf-8",
    )
    generated_dev = repo / "persona" / "datasets" / "generated-persona-dev-50"
    generated_dev.mkdir(parents=True)
    (generated_dev / "manifest.json").write_text(
        json.dumps({"count": 50, "personas": []}),
        encoding="utf-8",
    )
    generated_run = (
        repo / "persona" / "datasets" / "generated-persona-dev-stratified-20260823-192847"
    )
    generated_run.mkdir(parents=True)
    (generated_run / "manifest.json").write_text(
        json.dumps({"count": 32, "personas": []}),
        encoding="utf-8",
    )
    generated = repo / "persona" / "datasets" / "_generated" / "strategy-demo"
    generated.mkdir(parents=True)
    (generated / "manifest.json").write_text(
        json.dumps({"count": 3, "personas": []}),
        encoding="utf-8",
    )
    (repo / "persona" / "datasets" / "saved-cohorts" / "ignore-me").mkdir(parents=True)
    (
        repo / "persona" / "datasets" / "saved-cohorts" / "ignore-me" / "manifest.json"
    ).write_text(
        "{}",
        encoding="utf-8",
    )
    prod_cohort = (
        repo / "persona" / "datasets" / "matraix-persona-1m" / "cohorts" / "cohort-deadbeef"
    )
    prod_cohort.mkdir(parents=True)
    (prod_cohort / "manifest.json").write_text(
        json.dumps({"count": 4, "personas": []}),
        encoding="utf-8",
    )
    service = PersonaPoolService(repo_root=repo)

    listed = service.list_datasets()
    pools = [item["pool"] for item in listed]
    assert pools[0] == "persona/datasets/matraix-persona-dev-sample"
    assert listed[0]["default"] is True
    assert listed[0]["label"] == "matraix-persona-dev-sample"
    assert "persona/datasets/bench-dev-extra" in pools
    assert "persona/datasets/generated-persona-dev-50" in pools
    assert (
        "persona/datasets/generated-persona-dev-stratified-20260823-192847" in pools
    )
    # Nested leftover `_generated/` dirs stay omitted from Dataset.
    assert "persona/datasets/_generated/strategy-demo" not in pools
    assert "persona/datasets/saved-cohorts/ignore-me" not in pools
    # Production sample caches must not appear as Dataset sources.
    assert "persona/datasets/matraix-persona-1m/cohorts/cohort-deadbeef" not in pools
    by_pool = {item["pool"]: item for item in listed}
    assert by_pool["persona/datasets/bench-dev-extra"]["count"] == 1
    assert by_pool["persona/datasets/generated-persona-dev-50"]["count"] == 50
    assert by_pool["persona/datasets/generated-persona-dev-50"]["label"].startswith(
        "50 · "
    )
    assert (
        by_pool["persona/datasets/generated-persona-dev-stratified-20260823-192847"][
            "label"
        ]
        == "stratified · 2026-08-23 19:28:47"
    )
    assert "persona/datasets/matraix-persona-1m" in by_pool
    assert by_pool["persona/datasets/matraix-persona-1m"]["kind"] == "production"


def test_save_pool_as_dataset(tmp_path):
    repo = tmp_path
    _write_pool(repo)
    cohort = (
        repo
        / "persona"
        / "datasets"
        / "matraix-persona-1m"
        / "cohorts"
        / "cohort-abc123"
    )
    cohort.mkdir(parents=True)
    (cohort / "persona_p1.yaml").write_text(
        "persona_id: p1\nversion: '1.0'\nsource: Nemotron\ndimensions:\n  age_bracket: 25-34\n",
        encoding="utf-8",
    )
    (cohort / "persona_p2.yaml").write_text(
        "persona_id: p2\nversion: '1.0'\nsource: OASIS\ndimensions:\n  age_bracket: 35-44\n",
        encoding="utf-8",
    )
    (cohort / "manifest.json").write_text(
        json.dumps(
            {
                "kind": "matraix-persona-1m-cohort",
                "parent_pool": "persona/datasets/matraix-persona-1m",
                "count": 2,
                "seed": 7,
                "personas": [],
            }
        ),
        encoding="utf-8",
    )

    service = PersonaPoolService(repo_root=repo)
    saved = service.save_pool_as_dataset(
        source_pool="persona/datasets/matraix-persona-1m/cohorts/cohort-abc123",
        name="My Robinhood Cohort",
    )
    assert saved["pool"] == "persona/datasets/my-robinhood-cohort"
    assert saved["count"] == 2
    dest = repo / "persona/datasets/my-robinhood-cohort"
    assert (dest / "persona_p1.yaml").is_file()
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "saved-persona-dataset"
    assert manifest["count"] == 2
    assert manifest["personas"][0]["path"].startswith(
        "persona/datasets/my-robinhood-cohort/"
    )

    listed = {item["pool"]: item for item in service.list_datasets()}
    assert "persona/datasets/my-robinhood-cohort" in listed
    assert listed["persona/datasets/my-robinhood-cohort"]["kind"] == "saved"

    with pytest.raises(FileExistsError):
        service.save_pool_as_dataset(
            source_pool="persona/datasets/matraix-persona-1m/cohorts/cohort-abc123",
            name="My Robinhood Cohort",
        )

    again = service.save_pool_as_dataset(
        source_pool="persona/datasets/matraix-persona-1m/cohorts/cohort-abc123",
        name="My Robinhood Cohort",
        overwrite=True,
    )
    assert again["pool"] == "persona/datasets/my-robinhood-cohort"


def test_save_pool_as_dataset_from_sample_cohort(tmp_path, monkeypatch):
    repo = tmp_path
    _write_pool(repo)
    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    cohort = (
        repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "cohorts" / "cohort-dev110"
    )
    cohort.mkdir(parents=True)
    (cohort / "persona_0001.yaml").write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    (cohort / "persona_0002.yaml").write_text(
        "persona_id: '0002'\nversion: '1.0'\nsource: OASIS\ndimensions: {}\n",
        encoding="utf-8",
    )
    service = PersonaPoolService(repo_root=repo)
    saved = service.save_pool_as_dataset(
        source_pool="persona/datasets/matraix-persona-dev-sample/cohorts/cohort-dev110",
        name="Dev Feedback 110",
    )
    assert saved["pool"] == "persona/datasets/dev-feedback-110"
    assert saved["count"] == 2
    listed = {item["pool"] for item in service.list_datasets()}
    assert "persona/datasets/dev-feedback-110" in listed


def test_save_list_and_resolve_cohort(tmp_path, monkeypatch):
    repo = tmp_path
    _write_pool(repo)
    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = PersonaPoolService(repo_root=repo)

    saved = service.save_cohort(
        cohort_id="nemotron-price-sensitive",
        name="Nemotron price-sensitive",
        kind="recipe",
        seed=7,
        sample_size=1,
        sources=["Nemotron"],
        dimension_filters={"economic_motivation": "Price-sensitive"},
    )
    assert saved["cohortId"] == "nemotron-price-sensitive"
    assert (
        repo / "persona/datasets/saved-cohorts/nemotron-price-sensitive/cohort.json"
    ).is_file()

    listed = service.list_cohorts()
    assert len(listed) == 1
    assert listed[0]["cohortId"] == "nemotron-price-sensitive"

    frozen = service.save_cohort(
        cohort_id="frozen-pair",
        kind="frozen",
        seed=1,
        sample_size=1,
        dimension_filters={"economic_motivation": "Indifferent"},
    )
    assert frozen["personaIds"] == ["0002"]

    resolved = service.resolve_cohort_launch("frozen-pair")
    assert resolved["personaIds"] == ["0002"]


def test_get_persona_detail(tmp_path, monkeypatch):
    repo = tmp_path
    _write_pool(repo)
    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = PersonaPoolService(repo_root=repo)
    detail = service.get_persona_detail("0001")
    assert detail["personaId"] == "0001"
    assert detail["dimensions"]["economic_motivation"] == "Price-sensitive"
    assert "persona_id: '0001'" in detail["yaml"]
    assert detail["name"] and "persona-" not in detail["name"]
    assert not detail["profileMarkdown"].startswith("#")
    assert "## Dimensions" not in detail["profileMarkdown"]


def test_get_catalog_and_sample_with_filters(tmp_path, monkeypatch):
    repo = tmp_path
    _write_pool(repo)
    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = PersonaPoolService(repo_root=repo)
    catalog = service.get_catalog()
    assert catalog["count"] == 2
    assert catalog["smokePersonaId"] == "0001"
    assert catalog["dimensionCategories"]["devProfile"]["groups"]

    matched = service.filter_pool(sources=["Nemotron"])
    assert len(matched) == 1
    assert matched[0]["persona_id"] == "0001"

    sampled = service.sample_pool(
        sample_size=1,
        seed=7,
        dimension_filters={"economic_motivation": "Indifferent"},
    )
    assert sampled["matchedCount"] == 1
    assert sampled["personaIds"] == ["0002"]

    stratified = service.sample_pool(
        sample_size=2,
        seed=7,
        stratify_fields=["economic_motivation"],
        sample_size_per_value_group=1,
    )
    assert stratified["matchedCount"] == 2
    assert set(stratified["personaIds"]) == {"0001", "0002"}
    assert stratified["fields"] == ["economic_motivation"]

    with pytest.raises(ValueError, match="matraix-persona-1m") as excinfo:
        service.sample_pool(
            sample_size=99,
            seed=7,
            task_path="application/tasks/example-survey_product-feedback",
        )
    assert "exceeds matched pool size" in str(excinfo.value)


def test_sample_pool_per_value_group_not_truncated_by_sample_size(tmp_path, monkeypatch):
    """perCell is primary; sample_size must not clip N×cells."""
    repo = tmp_path
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    personas = [
        ("0001", "Nemotron", "Price-sensitive"),
        ("0002", "Nemotron", "Price-sensitive"),
        ("0003", "OASIS", "Indifferent"),
        ("0004", "OASIS", "Indifferent"),
    ]
    manifest_rows = []
    for pid, source, motivation in personas:
        (pool / f"persona_{pid}.yaml").write_text(
            f"persona_id: '{pid}'\nversion: '1.0'\nsource: {source}\n"
            f"dimensions:\n  economic_motivation: {motivation}\n",
            encoding="utf-8",
        )
        manifest_rows.append(
            {
                "persona_id": pid,
                "path": f"persona/datasets/matraix-persona-dev-sample/persona_{pid}.yaml",
                "source": source,
                "dimensions": {"economic_motivation": motivation},
            }
        )
    (pool / "manifest.json").write_text(
        json.dumps(
            {
                "count": 4,
                "smoke_persona_id": "0001",
                "schema_version": "1.0",
                "source_counts": {"Nemotron": 2, "OASIS": 2},
                "dimension_categories": "persona/schema/dimension_categories.json",
                "personas": manifest_rows,
            }
        ),
        encoding="utf-8",
    )
    schema = repo / "persona" / "schema"
    schema.mkdir(parents=True)
    (schema / "dimension_categories.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "personaSources": ["Nemotron", "OASIS"],
                "devProfile": {
                    "dimensionCount": 1,
                    "groups": [
                        {
                            "id": "values",
                            "label": "Values",
                            "dimensionIds": ["economic_motivation"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    (schema / "dimensions.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "dimensions": [
                    {
                        "id": "economic_motivation",
                        "label": "Economic motivation",
                        "values": ["Price-sensitive", "Indifferent"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = PersonaPoolService(repo_root=repo)

    # sample_size=2 would previously clip the 2×2=4 per-cell cohort down to 2.
    result = service.sample_pool(
        sample_size=2,
        seed=7,
        stratify_fields=["economic_motivation"],
        sample_size_per_value_group=2,
    )
    assert result["matchedCount"] == 4
    assert result["sampleSize"] == 4
    assert set(result["personaIds"]) == {"0001", "0002", "0003", "0004"}


def test_sample_pool_stratified_without_per_cell_caps_at_sample_size(tmp_path, monkeypatch):
    """sampleSize-only stratified: spread ceil(N/cells) then clip to sampleSize."""
    repo = tmp_path
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True)
    # 3 strata × 3 people so ceil(8/3)=3 per cell fits, then clip to 8.
    personas = [
        ("0001", "A", "18-24"),
        ("0002", "A", "18-24"),
        ("0003", "A", "18-24"),
        ("0004", "B", "25-34"),
        ("0005", "B", "25-34"),
        ("0006", "B", "25-34"),
        ("0007", "C", "35-44"),
        ("0008", "C", "35-44"),
        ("0009", "C", "35-44"),
    ]
    manifest_rows = []
    for pid, source, age in personas:
        (pool / f"persona_{pid}.yaml").write_text(
            f"persona_id: '{pid}'\nversion: '1.0'\nsource: {source}\n"
            f"dimensions:\n  age_bracket: {age}\n",
            encoding="utf-8",
        )
        manifest_rows.append(
            {
                "persona_id": pid,
                "path": f"persona/datasets/matraix-persona-dev-sample/persona_{pid}.yaml",
                "source": source,
                "dimensions": {"age_bracket": age},
            }
        )
    (pool / "manifest.json").write_text(
        json.dumps(
            {
                "count": 9,
                "smoke_persona_id": "0001",
                "schema_version": "1.0",
                "source_counts": {"A": 3, "B": 3, "C": 3},
                "dimension_categories": "persona/schema/dimension_categories.json",
                "personas": manifest_rows,
            }
        ),
        encoding="utf-8",
    )
    schema = repo / "persona" / "schema"
    schema.mkdir(parents=True)
    (schema / "dimension_categories.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "categories": [
                    {"id": "demo", "label": "Demo", "dimensionIds": ["age_bracket"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    (schema / "dimensions.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "dimensions": [
                    {
                        "id": "age_bracket",
                        "label": "Age",
                        "values": ["18-24", "25-34", "35-44"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = PersonaPoolService(repo_root=repo)

    result = service.sample_pool(
        sample_size=8,
        seed=7,
        dimension_filters={"age_bracket": ["18-24", "25-34", "35-44"]},
        stratify_fields=["age_bracket"],
        sample_size_per_value_group=None,
    )
    assert result["matchedCount"] == 9
    assert result["sampleSize"] == 8
    assert len(result["personaIds"]) == 8


def test_sample_pool_rejects_sample_size_below_cell_count(tmp_path, monkeypatch):
    repo = tmp_path
    _write_pool(repo)
    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = PersonaPoolService(repo_root=repo)
    try:
        service.sample_pool(
            sample_size=1,
            seed=7,
            dimension_filters={"economic_motivation": ["Price-sensitive", "Indifferent"]},
            stratify_fields=["economic_motivation"],
            sample_size_per_value_group=None,
        )
        raise AssertionError("expected sampleSize below cell count to fail")
    except ValueError as exc:
        assert "below the stratified cell count=2" in str(exc)


def test_sample_pool_fails_when_filter_coverage_is_thin(tmp_path, monkeypatch):
    """Thin fixture coverage fails with a 1M / widen / cohort hint — no synthetic top-up."""
    repo = tmp_path
    _write_pool(repo)
    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = PersonaPoolService(repo_root=repo)

    with pytest.raises(ValueError, match="matraix-persona-1m") as excinfo:
        service.sample_pool(
            sample_size=4,
            seed=7,
            dimension_filters={"economic_motivation": ["Price-sensitive"]},
            task_path="application/tasks/example-survey_product-feedback",
        )
    assert "poolEnsured" not in str(excinfo.value)


def test_sample_pool_fails_on_incomplete_stratify_cells(tmp_path, monkeypatch):
    """Missing stratify cells raise instead of synthesizing a local pool."""
    repo = tmp_path
    _write_pool(repo)
    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = PersonaPoolService(repo_root=repo)

    with pytest.raises(ValueError, match="Incomplete stratify coverage|matraix-persona-1m"):
        service.sample_pool(
            sample_size=4,
            seed=7,
            dimension_filters={"economic_motivation": ["Price-sensitive", "Indifferent"]},
            stratify_fields=["economic_motivation"],
            sample_size_per_value_group=2,
            task_path="application/tasks/example-survey_product-feedback",
        )


def test_list_persona_cards_all_personas(tmp_path, monkeypatch):
    repo = tmp_path
    _write_pool(repo)
    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = PersonaPoolService(repo_root=repo)

    shuffled = service.list_persona_cards(limit=2, seed=99)
    assert len(shuffled["personas"]) == 2

    all_cards = service.list_persona_cards(limit=2, all_personas=True)
    assert [card["personaId"] for card in all_cards["personas"]] == ["0001", "0002"]

    page_two = service.list_persona_cards(limit=1, offset=1, all_personas=True)
    assert [card["personaId"] for card in page_two["personas"]] == ["0002"]

    full_pool = service.list_persona_cards(limit=500, all_personas=True)
    assert [card["personaId"] for card in full_pool["personas"]] == ["0001", "0002"]


def _write_large_pool(repo: Path, count: int = 120) -> None:
    pool = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    pool.mkdir(parents=True, exist_ok=True)
    personas = []
    for i in range(1, count + 1):
        pid = f"{i:04d}"
        (pool / f"persona_{pid}.yaml").write_text(
            f"persona_id: '{pid}'\nversion: '1.0'\nsource: Nemotron\ndimensions:\n  economic_motivation: Price-sensitive\n",
            encoding="utf-8",
        )
        personas.append(
            {
                "persona_id": pid,
                "path": f"persona/datasets/matraix-persona-dev-sample/persona_{pid}.yaml",
                "source": "Nemotron",
                "dimensions": {"economic_motivation": "Price-sensitive"},
            }
        )
    (pool / "manifest.json").write_text(
        json.dumps(
            {
                "count": count,
                "smoke_persona_id": "0001",
                "schema_version": "1.0",
                "source_counts": {"Nemotron": count},
                "dimension_categories": "persona/schema/dimension_categories.json",
                "personas": personas,
            }
        ),
        encoding="utf-8",
    )
    schema = repo / "persona" / "schema"
    schema.mkdir(parents=True, exist_ok=True)
    (schema / "dimension_categories.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "personaSources": ["Nemotron"],
                "devProfile": {
                    "dimensionCount": 1,
                    "groups": [
                        {
                            "id": "values",
                            "label": "Values",
                            "dimensionIds": ["economic_motivation"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    (schema / "dimensions.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "dimensions": [
                    {
                        "id": "economic_motivation",
                        "label": "Economic motivation",
                        "category": "Values & Motivation",
                        "values": ["Price-sensitive"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_sample_pool_truncates_ids_and_materializes_large_cohort(tmp_path, monkeypatch):
    repo = tmp_path
    _write_large_pool(repo, count=120)
    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = PersonaPoolService(repo_root=repo)
    result = service.sample_pool(sample_size=120, seed=7)
    assert result["selectedCount"] == 120
    assert result["sampleSize"] == 120
    assert result["idsTruncated"] is True
    assert len(result["personaIds"]) <= 32
    assert len(result["personas"]) <= 32
    assert result["pool"].startswith("persona/datasets/matraix-persona-dev-sample/cohorts/")
    assert (repo / result["pool"]).is_dir()


def test_list_persona_ids_truncates_over_ui_max(tmp_path, monkeypatch):
    repo = tmp_path
    _write_large_pool(repo, count=120)
    monkeypatch.setattr(
        "playground.harbor.playground._repo_root",
        lambda: repo,
    )
    service = PersonaPoolService(repo_root=repo)
    listed = service.list_persona_ids("persona/datasets/matraix-persona-dev-sample")
    assert listed["count"] == 120
    assert listed["idsTruncated"] is True
    assert len(listed["personaIds"]) <= 32


def test_coverage_recovery_hint_mentions_synthesize_when_task_path():
    from backend.service.persona_pool_service import coverage_recovery_hint

    plain = coverage_recovery_hint()
    assert "Not enough matching personas" in plain
    assert "matraix-persona-1m" in plain
    assert "does not synthesize" not in plain
    tasked = coverage_recovery_hint(task_path="application/tasks/demo")
    assert "matraix-persona-1m" in tasked
    assert "Synthesize to fill this task" in tasked


def _fake_generated_persona(persona_id: str = "0001") -> dict:
    return {
        "persona_id": persona_id,
        "version": "1.0",
        "source": "synthetic",
        "dimensions": {"age_bracket": "25-34"},
    }


def test_generate_synthetic_pool_random_count(tmp_path, monkeypatch):
    _write_pool(tmp_path)
    service = PersonaPoolService(repo_root=tmp_path)

    def fake_generate(**kwargs):
        assert kwargs["count"] == 2
        assert kwargs["stratum_top_up"] is None
        return [_fake_generated_persona("0001"), _fake_generated_persona("0002")]

    monkeypatch.setattr(
        "matraix.persona_generator.generate_persona_pool",
        fake_generate,
    )
    result = service.generate_synthetic_pool(count=2, seed=7)
    assert re.fullmatch(
        r"persona/datasets/generated-persona-dev-2-\d{8}-\d{6}",
        result["pool"],
    )
    assert result["label"].startswith("2 · ")
    assert result["count"] == 2
    assert result["source"] == "synthetic"
    assert result["personaIds"] == ["0001", "0002"]
    dest = tmp_path / result["pool"]
    assert (dest / "persona_0001.yaml").is_file()
    assert (dest / "manifest.json").is_file()


def test_generate_synthetic_pool_random_applies_catalog_filters(tmp_path, monkeypatch):
    _write_pool(tmp_path)
    service = PersonaPoolService(repo_root=tmp_path)
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return [_fake_generated_persona("0001"), _fake_generated_persona("0002")]

    monkeypatch.setattr(
        "matraix.persona_generator.generate_persona_pool",
        fake_generate,
    )
    service.generate_synthetic_pool(
        count=2,
        seed=7,
        dimension_filters={"age_bracket": ["25-34"]},
        overlay_dimensions=[
            {"id": "overlay_1", "label": "品牌信任", "values": ["Low", "High"]},
        ],
    )
    assert captured["count"] == 2
    assert captured["extra_filters"] == {"age_bracket": ["25-34"]}
    assert captured["stratum_top_up"] is None


def test_generate_synthetic_pool_keeps_prior_run(tmp_path, monkeypatch):
    _write_pool(tmp_path)
    service = PersonaPoolService(repo_root=tmp_path)
    monkeypatch.setattr(
        "matraix.persona_generator.generate_persona_pool",
        lambda **kwargs: [_fake_generated_persona("0001"), _fake_generated_persona("0002")],
    )
    stamps = iter(["20260823-192847", "20260823-192847"])
    monkeypatch.setattr(
        "backend.service.persona_pool_service._generated_run_stamp",
        lambda: next(stamps),
    )
    first = service.generate_synthetic_pool(count=2, seed=1)
    second = service.generate_synthetic_pool(count=2, seed=2)
    assert first["pool"] == "persona/datasets/generated-persona-dev-2-20260823-192847"
    assert second["pool"] == "persona/datasets/generated-persona-dev-2-20260823-192847-2"
    assert (tmp_path / first["pool"] / "manifest.json").is_file()
    assert (tmp_path / second["pool"] / "manifest.json").is_file()


def test_generate_synthetic_pool_rejects_over_max(tmp_path):
    _write_pool(tmp_path)
    service = PersonaPoolService(repo_root=tmp_path)
    with pytest.raises(ValueError, match="count must be <="):
        service.generate_synthetic_pool(count=5001)


def test_generate_synthetic_pool_stratified(tmp_path, monkeypatch):
    _write_pool(tmp_path)
    service = PersonaPoolService(repo_root=tmp_path)
    monkeypatch.setattr(
        "matraix.persona_generator.strategy_pin_cells",
        lambda **kwargs: ([{"age_bracket": "25-34"}], []),
    )
    monkeypatch.setattr(
        "matraix.persona_generator.generate_persona_pool",
        lambda **kwargs: (
            [_fake_generated_persona("0001"), _fake_generated_persona("0002")]
            if kwargs["min_per_stratum"] == 2
            else []
        ),
    )
    result = service.generate_synthetic_pool(
        dimension_filters={"age_bracket": ["25-34"]},
        stratify_fields=["age_bracket"],
        allocation="perCell",
        per_cell=2,
        seed=1,
    )
    assert re.fullmatch(
        r"persona/datasets/generated-persona-dev-stratified-\d{8}-\d{6}",
        result["pool"],
    )
    assert result["label"].startswith("stratified · ")
    assert result["count"] == 2


def test_generate_synthetic_pool_from_task_strategy(tmp_path, monkeypatch):
    _write_pool(tmp_path)
    task_dir = tmp_path / "application" / "tasks" / "demo-task"
    task_dir.mkdir(parents=True)
    (task_dir / "persona_strategy.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "dimensionFilters": {"age_bracket": ["25-34"]},
                "sampling": {
                    "mode": "stratified",
                    "fields": ["age_bracket"],
                    "allocation": "perCell",
                    "perCell": 2,
                },
            }
        ),
        encoding="utf-8",
    )
    service = PersonaPoolService(repo_root=tmp_path)
    monkeypatch.setattr(
        "matraix.persona_generator.strategy_pin_cells",
        lambda **kwargs: ([{"age_bracket": "25-34"}], []),
    )
    monkeypatch.setattr(
        "matraix.persona_generator.generate_persona_pool",
        lambda **kwargs: [_fake_generated_persona("0001"), _fake_generated_persona("0002")],
    )
    result = service.generate_synthetic_pool(task_path="application/tasks/demo-task")
    assert re.fullmatch(
        r"persona/datasets/generated-persona-dev-strategy-demo-task-\d{8}-\d{6}",
        result["pool"],
    )
    assert result["count"] == 2


def test_get_dimension_labels_missing_pack_reports_unavailable(tmp_path):
    service = PersonaPoolService(repo_root=tmp_path)
    result = service.get_dimension_labels("ko")
    assert result == {
        "locale": "ko",
        "available": False,
        "reviewStatus": None,
        "dimensions": {},
        "taxonomy": {},
    }


def test_get_dimension_labels_reads_committed_pack(tmp_path):
    labels_dir = tmp_path / "persona" / "schema" / "labels"
    labels_dir.mkdir(parents=True)
    (labels_dir / "dimensions.labels.zh-Hans.json").write_text(
        json.dumps(
            {
                "formatVersion": "1.0",
                "locale": "zh-Hans",
                "reviewStatus": "machine-assisted",
                "dimensions": {
                    "primary_language": {
                        "label": "主要语言",
                        "values": {"Mandarin": "普通话"},
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = PersonaPoolService(repo_root=tmp_path)
    result = service.get_dimension_labels("zh-Hans")
    assert result["available"] is True
    assert result["reviewStatus"] == "machine-assisted"
    entry = result["dimensions"]["primary_language"]
    assert entry["label"] == "主要语言"
    assert entry["values"]["Mandarin"] == "普通话"


def test_get_dimension_labels_rejects_unsafe_locale_tokens(tmp_path):
    service = PersonaPoolService(repo_root=tmp_path)
    for bad in ("", "../secrets", "zh Hans", "a/b", "x" * 33):
        with pytest.raises(ValueError):
            service.get_dimension_labels(bad)


def test_generate_synthetic_pool_stamps_overlay(tmp_path, monkeypatch):
    _write_pool(tmp_path)
    service = PersonaPoolService(repo_root=tmp_path)
    monkeypatch.setattr(
        "matraix.persona_generator.generate_persona_pool",
        lambda **kwargs: [_fake_generated_persona("0001"), _fake_generated_persona("0002")],
    )
    overlay = [
        {"id": "study_trust", "label": "品牌信任", "values": ["Low", "High"]},
    ]
    result = service.generate_synthetic_pool(
        count=2,
        seed=7,
        overlay_dimensions=overlay,
    )
    dest = tmp_path / result["pool"]
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["overlay_dimensions"][0]["id"] == "study_trust"
    yaml_text = (dest / "persona_0001.yaml").read_text(encoding="utf-8")
    assert "study_trust:" in yaml_text
    catalog = service.get_catalog(result["pool"])
    groups = catalog["dimensionCategories"]["devProfile"]["groups"]
    assert groups[0]["id"] == "study-overlay"
    assert groups[0]["dimensions"][0]["label"] == "品牌信任"


def test_generate_synthetic_pool_overlay_only_per_cell(tmp_path, monkeypatch):
    _write_pool(tmp_path)
    service = PersonaPoolService(repo_root=tmp_path)
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return [_fake_generated_persona("0001"), _fake_generated_persona("0002")]

    monkeypatch.setattr(
        "matraix.persona_generator.generate_persona_pool",
        fake_generate,
    )
    overlay = [
        {"id": "study_trust", "label": "品牌信任", "values": ["Low", "High"]},
    ]
    result = service.generate_synthetic_pool(
        seed=3,
        overlay_dimensions=overlay,
        dimension_filters={"study_trust": ["Low", "High"]},
        stratify_fields=["study_trust"],
        allocation="perCell",
        per_cell=1,
    )
    assert captured["count"] == 2
    assert captured["stratum_top_up"] is None
    assert captured["include_smoke"] is False
    dest = tmp_path / result["pool"]
    values = {
        yaml.safe_load((dest / name).read_text(encoding="utf-8"))["dimensions"]["study_trust"]
        for name in ("persona_0001.yaml", "persona_0002.yaml")
    }
    assert values == {"Low", "High"}


def test_generate_synthetic_pool_overlay_with_catalog_per_cell(tmp_path, monkeypatch):
    _write_pool(tmp_path)
    service = PersonaPoolService(repo_root=tmp_path)
    monkeypatch.setattr(
        "matraix.persona_generator.strategy_pin_cells",
        lambda **kwargs: ([{"age_bracket": "25-34"}], []),
    )

    def fake_generate(**kwargs):
        assert kwargs["min_per_stratum"] == 2
        assert kwargs["count"] == 0
        return [_fake_generated_persona("0001"), _fake_generated_persona("0002")]

    monkeypatch.setattr(
        "matraix.persona_generator.generate_persona_pool",
        fake_generate,
    )
    result = service.generate_synthetic_pool(
        seed=4,
        overlay_dimensions=[
            {"id": "study_trust", "label": "品牌信任", "values": ["Low", "High"]},
        ],
        dimension_filters={
            "age_bracket": ["25-34"],
            "study_trust": ["Low", "High"],
        },
        stratify_fields=["age_bracket", "study_trust"],
        allocation="perCell",
        per_cell=1,
    )
    dest = tmp_path / result["pool"]
    values = set()
    for name in ("persona_0001.yaml", "persona_0002.yaml"):
        dims = yaml.safe_load((dest / name).read_text(encoding="utf-8"))["dimensions"]
        assert dims["age_bracket"] == "25-34"
        values.add(dims["study_trust"])
    assert values == {"Low", "High"}


def test_save_generated_pool_keeps_overlay_for_filter_and_catalog(tmp_path, monkeypatch):
    _write_pool(tmp_path)
    service = PersonaPoolService(repo_root=tmp_path)
    monkeypatch.setattr(
        "matraix.persona_generator.generate_persona_pool",
        lambda **kwargs: [_fake_generated_persona("0001"), _fake_generated_persona("0002")],
    )
    generated = service.generate_synthetic_pool(
        seed=7,
        overlay_dimensions=[
            {"id": "study_trust", "label": "品牌信任", "values": ["Low", "High"]},
        ],
        dimension_filters={"study_trust": ["Low", "High"]},
        stratify_fields=["study_trust"],
        allocation="perCell",
        per_cell=1,
    )
    saved = service.save_pool_as_dataset(
        source_pool=generated["pool"],
        name="Overlay Cohort",
    )
    catalog = service.get_catalog(saved["pool"])
    groups = catalog["dimensionCategories"]["devProfile"]["groups"]
    assert groups[0]["id"] == "study-overlay"
    assert groups[0]["dimensions"][0]["label"] == "品牌信任"
    matched = service.filter_pool(
        persona_pool=saved["pool"],
        dimension_filters={"study_trust": ["Low"]},
    )
    assert len(matched) == 1
    dims = yaml.safe_load((tmp_path / matched[0]["path"]).read_text(encoding="utf-8"))[
        "dimensions"
    ]
    assert dims["study_trust"] == "Low"


def test_generate_synthetic_pool_rejects_schema_collision(tmp_path):
    _write_pool(tmp_path)
    schema_dir = tmp_path / "persona" / "schema"
    schema_dir.mkdir(parents=True, exist_ok=True)
    (schema_dir / "dimensions.json").write_text(
        json.dumps(
            {
                "dimensions": [
                    {"id": "age_bracket", "label": "Age", "values": ["25-34"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    service = PersonaPoolService(repo_root=tmp_path)
    with pytest.raises(ValueError, match="collides"):
        service.generate_synthetic_pool(
            count=1,
            overlay_dimensions=[
                {"id": "age_bracket", "label": "Age", "values": ["25-34"]},
            ],
        )


def test_clone_contrast_pool_copies_and_flips_overlay(tmp_path):
    _write_pool(tmp_path)
    src = tmp_path / "persona" / "datasets" / "matraix-persona-dev-sample"
    for path in src.glob("persona_*.yaml"):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        payload["dimensions"]["study_trust"] = "High"
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    for row in manifest["personas"]:
        row["dimensions"]["study_trust"] = "High"
    manifest["overlay_dimensions"] = [
        {"id": "study_trust", "label": "品牌信任", "values": ["Low", "High"]},
    ]
    (src / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    service = PersonaPoolService(repo_root=tmp_path)
    result = service.clone_contrast_pool(
        persona_pool="persona/datasets/matraix-persona-dev-sample",
        overlay_id="study_trust",
        value="Low",
    )
    assert result["count"] == 2
    assert result["parentPool"] == "persona/datasets/matraix-persona-dev-sample"
    dest = tmp_path / result["pool"]
    first = yaml.safe_load((dest / "persona_0001-c-low.yaml").read_text(encoding="utf-8"))
    assert first["dimensions"]["study_trust"] == "Low"
    assert first["dimensions"]["economic_motivation"] == "Price-sensitive"
    assert first["pair_id"] == "0001"
    written = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert written["contrast"]["value"] == "Low"


def test_clone_contrast_pool_requires_overlay(tmp_path):
    _write_pool(tmp_path)
    service = PersonaPoolService(repo_root=tmp_path)
    with pytest.raises(ValueError, match="custom dimensions"):
        service.clone_contrast_pool(
            persona_pool="persona/datasets/matraix-persona-dev-sample",
            overlay_id="study_trust",
            value="Low",
        )


def test_generate_synthetic_pool_writes_contrast_clones(tmp_path, monkeypatch):
    _write_pool(tmp_path)
    service = PersonaPoolService(repo_root=tmp_path)
    monkeypatch.setattr(
        "matraix.persona_generator.generate_persona_pool",
        lambda **kwargs: [_fake_generated_persona("0001"), _fake_generated_persona("0002")],
    )
    overlay = [
        {"id": "study_trust", "label": "品牌信任", "values": ["Low", "High"]},
        {"id": "ad_arm", "label": "广告", "values": ["None", "Banner"]},
    ]
    result = service.generate_synthetic_pool(
        count=2,
        seed=7,
        overlay_dimensions=overlay,
        dimension_filters={
            "study_trust": ["Low", "High"],
            "ad_arm": ["None", "Banner"],
        },
        contrast=[
            {"overlayId": "study_trust", "baseValue": "High", "values": ["Low"]},
            {"overlayId": "ad_arm", "baseValue": "None", "values": ["Banner"]},
        ],
    )
    clones = result["contrastPools"]
    assert len(clones) == 1
    assert clones[0]["contrastStamps"] == {
        "study_trust": "Low",
        "ad_arm": "Banner",
    }
    # Parent is the base arm (values not in the contrast extras).
    assert result["contrastStamps"] == {
        "study_trust": "High",
        "ad_arm": "None",
    }
    assert result["label"].startswith("Contrast ·")
    assert "品牌信任=High" in result["label"]
    assert "广告=None" in result["label"]
    assert "contrast-" in Path(result["pool"]).name
    assert clones[0]["label"].startswith("Contrast ·")
    assert "品牌信任=Low" in clones[0]["label"]
    assert "广告=Banner" in clones[0]["label"]
    parent = yaml.safe_load(
        (tmp_path / result["pool"] / "persona_0001.yaml").read_text(encoding="utf-8")
    )
    assert parent["dimensions"]["study_trust"] == "High"
    assert parent["dimensions"]["ad_arm"] == "None"
    combo = yaml.safe_load(
        (tmp_path / clones[0]["pool"] / "persona_0001-c-low-banner.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert combo["dimensions"]["study_trust"] == "Low"
    assert combo["dimensions"]["ad_arm"] == "Banner"
    assert combo["pair_id"] == "0001"


def test_generate_synthetic_pool_contrast_drops_overlay_per_cell(tmp_path, monkeypatch):
    _write_pool(tmp_path)
    service = PersonaPoolService(repo_root=tmp_path)
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return [_fake_generated_persona("0001"), _fake_generated_persona("0002")]

    monkeypatch.setattr(
        "matraix.persona_generator.generate_persona_pool",
        fake_generate,
    )
    result = service.generate_synthetic_pool(
        seed=3,
        overlay_dimensions=[
            {"id": "study_trust", "label": "品牌信任", "values": ["Low", "High"]},
        ],
        dimension_filters={"study_trust": ["Low", "High"]},
        stratify_fields=["study_trust"],
        allocation="perCell",
        per_cell=2,
        contrast=[{"overlayId": "study_trust", "baseValue": "Low", "values": ["High"]}],
    )
    assert captured["count"] == 2
    assert captured["stratum_top_up"] is None
    dest = tmp_path / result["pool"]
    values = {
        yaml.safe_load((dest / name).read_text(encoding="utf-8"))["dimensions"]["study_trust"]
        for name in ("persona_0001.yaml", "persona_0002.yaml")
    }
    assert values <= {"Low", "High"}
    assert len(result["contrastPools"]) == 1
    clone = yaml.safe_load(
        (
            tmp_path
            / result["contrastPools"][0]["pool"]
            / "persona_0001-c-high.yaml"
        ).read_text(encoding="utf-8")
    )
    assert clone["dimensions"]["study_trust"] == "High"


def _write_outside_pool(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "persona_x1.yaml").write_text(
        "persona_id: x1\nversion: '1.0'\nsource: external\ndimensions: {}\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "pool",
    ["{outside}", "../outside", "persona/../../outside", "../repo-sibling"],
)
def test_pool_outside_repo_is_rejected(tmp_path, pool):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_pool(repo)
    _write_outside_pool(tmp_path / "outside")
    _write_outside_pool(tmp_path / "repo-sibling")
    service = PersonaPoolService(repo_root=repo)
    pool = pool.format(outside=tmp_path / "outside")
    with pytest.raises(ValueError, match="inside the repo"):
        service.list_persona_ids(pool)
    with pytest.raises(ValueError, match="inside the repo"):
        service.get_persona_detail("x1", persona_pool=pool)


def test_save_pool_as_dataset_rejects_source_outside_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_pool(repo)
    _write_outside_pool(tmp_path / "outside")
    service = PersonaPoolService(repo_root=repo)
    with pytest.raises(ValueError, match="inside the repo"):
        service.save_pool_as_dataset(
            source_pool=str(tmp_path / "outside"), name="poc"
        )
    assert not (repo / "persona" / "datasets" / "poc").exists()


def test_pool_inside_repo_still_resolves(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_pool(repo)
    service = PersonaPoolService(repo_root=repo)
    pool = "persona/datasets/matraix-persona-dev-sample"
    for variant in (pool, pool + "/", "persona/./datasets/../datasets/matraix-persona-dev-sample"):
        assert service.list_persona_ids(variant)["count"] == 2
    assert service.list_persona_ids(str(repo / pool))["count"] == 2
