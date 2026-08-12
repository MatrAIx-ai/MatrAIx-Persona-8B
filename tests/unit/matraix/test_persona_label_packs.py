"""Persona schema locale assets cover the complete schema and raw value keys."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_spanish_persona_schema_pack_is_complete():
    dimensions = json.loads(
        (REPO_ROOT / "persona/schema/dimensions.json").read_text(encoding="utf-8")
    )
    labels = json.loads(
        (REPO_ROOT / "persona/schema/labels_es.json").read_text(encoding="utf-8")
    )

    dimension_ids = {dimension["id"] for dimension in dimensions["dimensions"]}
    assert set(labels) == dimension_ids
    assert len(labels) == 1290
    assert labels["musg_hip_hop"]["label"] == "Música: Hip-hop"
    assert labels["musg_hip_hop"]["values"]["Love"] == "amor"


def test_spanish_persona_schema_pack_preserves_raw_value_keys():
    labels = json.loads(
        (REPO_ROOT / "persona/schema/labels_es.json").read_text(encoding="utf-8")
    )
    source = json.loads(
        (REPO_ROOT / "persona/schema/labels_zh.json").read_text(encoding="utf-8")
    )

    for dimension_id, source_item in source.items():
        assert set(labels[dimension_id]["values"]) == set(source_item.get("values", {}))
