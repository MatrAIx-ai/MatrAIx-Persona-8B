from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _read_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_korean_schema_label_pack_covers_every_dimension_and_enum_value() -> None:
    schema = _read_json("persona/schema/dimensions.json")
    labels = _read_json("persona/schema/labels_ko.json")

    rows = [row for row in schema["dimensions"] if row.get("id")]
    assert set(labels) == {str(row["id"]) for row in rows}

    for row in rows:
        entry = labels[row["id"]]
        assert entry["label"]
        translated_values = entry["values"]
        for value in row.get("values", row.get("values_list", [])):
            assert value in translated_values
            assert translated_values[value]


def test_korean_schema_label_pack_is_decoded_as_utf8_and_has_hangul() -> None:
    labels = _read_json("persona/schema/labels_ko.json")
    assert len(labels) == 1290
    assert any("가" <= character <= "힣" for entry in labels.values() for character in entry["label"])
