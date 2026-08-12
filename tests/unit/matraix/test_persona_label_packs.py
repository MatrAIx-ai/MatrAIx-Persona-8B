"""Persona schema locale assets cover the complete schema and raw value keys."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("locale", "filename"),
    [
        ("zh", "labels_zh.json"),
        ("zh-Hant", "labels_zh-TW.json"),
        ("ko", "labels_ko.json"),
        ("ja", "labels_ja.json"),
        ("pt", "labels_pt.json"),
        ("es", "labels_es.json"),
    ],
)
def test_persona_schema_locale_pack_is_complete(locale: str, filename: str):
    dimensions = json.loads(
        (REPO_ROOT / "persona/schema/dimensions.json").read_text(encoding="utf-8")
    )
    labels = json.loads(
        (REPO_ROOT / f"persona/schema/{filename}").read_text(encoding="utf-8")
    )

    dimension_ids = {dimension["id"] for dimension in dimensions["dimensions"]}
    assert set(labels) == dimension_ids, locale
    assert len(labels) == 1290, locale


@pytest.mark.parametrize(
    ("locale", "filename"),
    [
        ("zh", "labels_zh.json"),
        ("zh-Hant", "labels_zh-TW.json"),
        ("ko", "labels_ko.json"),
        ("ja", "labels_ja.json"),
        ("pt", "labels_pt.json"),
        ("es", "labels_es.json"),
    ],
)
def test_persona_schema_locale_pack_preserves_raw_value_keys(locale: str, filename: str):
    labels = json.loads(
        (REPO_ROOT / f"persona/schema/{filename}").read_text(encoding="utf-8")
    )
    source = json.loads(
        (REPO_ROOT / "persona/schema/labels_zh.json").read_text(encoding="utf-8")
    )

    for dimension_id, source_item in source.items():
        assert set(labels[dimension_id]["values"]) == set(source_item.get("values", {})), (
            locale,
            dimension_id,
        )


def test_spanish_persona_schema_pack_translates_representative_values():
    labels = json.loads(
        (REPO_ROOT / "persona/schema/labels_es.json").read_text(encoding="utf-8")
    )
    assert labels["musg_hip_hop"]["label"] == "Música: Hip-hop"
    assert labels["musg_hip_hop"]["values"]["Love"] == "amor"
