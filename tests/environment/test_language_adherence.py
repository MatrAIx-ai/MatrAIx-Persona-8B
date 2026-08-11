"""Unit tests for the multilingual telco support verifier's language detection.

The verifier lives inside a task folder and is executed by ``tests/test.sh`` in an
isolated ``uvx`` environment, so it is loaded here by path rather than imported as
a package. Fixtures are deliberately tiny synthetic transcripts — no captured job
output.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER_PATH = (
    REPO_ROOT
    / "application"
    / "tasks"
    / "chat_multilingual-telco-support"
    / "tests"
    / "test_state.py"
)


def _load_verifier() -> Any:
    spec = importlib.util.spec_from_file_location(
        "telco_language_verifier", VERIFIER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_verifier()


# Short, synthetic replies in the style the SUT produces.
REPLIES = {
    "en": (
        "Here is the breakdown for your invoice and the charge you asked about. "
        "Our billing team will confirm that only once we have the carrier record."
    ),
    "tr": (
        "Bu fatura için üzgünüm, itiraz kaydettim ve fatura ekibimiz bunu üç iş "
        "günü içinde inceliyor. Size sonra tekrar bilgi vereceğiz."
    ),
    "es": (
        "Lamento el cargo en su factura. Su reclamación sigue en revisión por "
        "nuestro equipo, y le avisaremos hasta cuanto haya novedades."
    ),
    "de": (
        "Ihr Widerspruch wird noch geprüft und das Abrechnungsteam hat die "
        "Entscheidung nicht erfasst. Wir informieren Ihnen, sobald wir mehr wissen."
    ),
}


def _messages(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"role": role, "content": content} for role, content in pairs]


@pytest.mark.parametrize("language", sorted(REPLIES))
def test_detects_each_supported_language(language: str) -> None:
    detected, confidence = verifier.detect_language(REPLIES[language])
    assert detected == language
    assert 0.5 <= confidence <= 1.0


def test_detection_is_deterministic() -> None:
    for text in REPLIES.values():
        results = {verifier.detect_language(text) for _ in range(25)}
        assert len(results) == 1


@pytest.mark.parametrize("text", ["Tamam.", "Ok", "Sí", "", "   "])
def test_short_replies_are_undetermined(text: str) -> None:
    detected, confidence = verifier.detect_language(text)
    assert detected == verifier.UNDETERMINED
    assert confidence == 0.0


def test_language_neutral_filler_is_undetermined() -> None:
    """Invoice ids and amounts carry no language signal and must not be guessed."""
    detected, _ = verifier.detect_language("INV-70431 DSP-5512 412.50 89.90 249.00")
    assert detected == verifier.UNDETERMINED


def test_turkish_dotted_capital_i_is_normalized() -> None:
    """``"İ".lower()`` leaves a combining dot that would break every match."""
    assert "itiraz" in verifier.normalize("İtiraz kaydedildi")
    detected, _ = verifier.detect_language(
        "İtiraz için üzgünüm, ekibimiz bunu üç iş günü içinde inceliyor."
    )
    assert detected == "tr"


def test_persona_language_read_from_dimensions_block(tmp_path: Path) -> None:
    persona = tmp_path / "persona.yaml"
    persona.write_text(
        "persona_id: '0007'\n"
        "source: wiki\n"
        "dimensions:\n"
        "  role_function: Teaching\n"
        "  primary_language: German\n"
        "provenance:\n"
        "  parent_pool: somewhere\n",
        encoding="utf-8",
    )
    assert verifier.read_persona_language([persona]) == "German"


def test_persona_language_absent_returns_none(tmp_path: Path) -> None:
    persona = tmp_path / "persona.yaml"
    persona.write_text(
        "persona_id: '0042'\ndimensions:\n  role_function: Teaching\n",
        encoding="utf-8",
    )
    assert verifier.read_persona_language([persona]) is None


def test_persona_language_outside_dimensions_is_ignored(tmp_path: Path) -> None:
    """A same-named key under another top-level block must not be picked up."""
    persona = tmp_path / "persona.yaml"
    persona.write_text(
        "dimensions:\n"
        "  role_function: Teaching\n"
        "provenance:\n"
        "  primary_language: Klingon\n",
        encoding="utf-8",
    )
    assert verifier.read_persona_language([persona]) is None


def test_missing_persona_file_returns_none(tmp_path: Path) -> None:
    assert verifier.read_persona_language([tmp_path / "absent.yaml"]) is None


@pytest.mark.parametrize(
    ("raw", "expected_code", "status"),
    [
        ("German", "de", "measured"),
        ("turkish", "tr", "measured"),
        (None, "unknown", "persona_language_unknown"),
        ("", "unknown", "persona_language_unknown"),
        ("Mandarin", "Mandarin", "persona_language_unsupported"),
    ],
)
def test_expected_language_resolution(
    raw: str | None, expected_code: str, status: str
) -> None:
    assert verifier.resolve_expected_language(raw) == (expected_code, status)


def test_match_rate_counts_only_attributed_replies() -> None:
    messages = _messages(
        ("customer", "Faturam yanlış geldi."),
        ("support", REPLIES["tr"]),
        ("customer", "Kalem dökümü?"),
        ("support", REPLIES["en"]),
        ("customer", "Peki."),
        ("support", "Tamam."),
    )
    result = verifier.analyze_language(messages, "tr", "measured")
    # Two attributed replies (tr, en); the third is too short to attribute.
    assert result["undetermined_reply_count"] == 1
    assert result["match_rate"] == 0.5
    assert result["first_reply_language"] == "tr"
    assert result["language_switch_count"] == 1


def test_full_adherence_and_no_switches() -> None:
    messages = _messages(
        ("customer", "Hola"),
        ("support", REPLIES["es"]),
        ("customer", "Gracias"),
        ("support", REPLIES["es"]),
    )
    result = verifier.analyze_language(messages, "es", "measured")
    assert result["match_rate"] == 1.0
    assert result["language_switch_count"] == 0


def test_match_rate_omitted_when_persona_language_unknown() -> None:
    messages = _messages(
        ("customer", "My invoice is wrong."),
        ("support", REPLIES["en"]),
    )
    result = verifier.analyze_language(messages, "unknown", "persona_language_unknown")
    assert result["match_rate"] is None
    # Reply-only signals stay available without the persona's language.
    assert result["first_reply_language"] == "en"
    assert result["detection_confidence"] > 0


def _payload(messages: list[dict[str, str]], persona_language: str | None) -> Any:
    combined = " ".join(message["content"] for message in messages)
    return verifier.build_evaluation_payload(messages, combined, None, persona_language)


def _language_facets(payload: Any) -> dict[str, Any]:
    context = next(
        item
        for item in payload["contexts"]
        if item["contextType"] == "language_adherence"
    )
    return {facet["key"]: facet for facet in context["facets"]}


def test_payload_declares_unmeasurability_instead_of_omitting_silently() -> None:
    messages = _messages(
        ("customer", "My invoice is wrong."),
        ("support", REPLIES["en"]),
    )
    facets = _language_facets(_payload(messages, None))
    assert facets["measurement_status"]["value"] == "persona_language_unknown"
    assert "language_match_rate" not in facets
    # The explanation rebinds to the status so the grouped view still renders.
    assert facets["language_adherence_notes"]["explainsFacetKey"] == "measurement_status"


def test_payload_binds_notes_to_match_rate_when_measured() -> None:
    messages = _messages(
        ("customer", "Meine Rechnung ist falsch."),
        ("support", REPLIES["de"]),
    )
    facets = _language_facets(_payload(messages, "German"))
    assert facets["language_match_rate"]["value"] == 1.0
    assert facets["language_adherence_notes"]["explainsFacetKey"] == "language_match_rate"


def test_unsupported_persona_language_is_reported_not_approximated() -> None:
    messages = _messages(
        ("customer", "My invoice is wrong."),
        ("support", REPLIES["en"]),
    )
    facets = _language_facets(_payload(messages, "Mandarin"))
    assert facets["measurement_status"]["value"] == "persona_language_unsupported"
    assert facets["persona_expected_language"]["value"] == "Mandarin"
    assert "language_match_rate" not in facets


def test_every_facet_kind_is_accepted_by_aggregation() -> None:
    """Invalid kinds are dropped silently downstream, so assert them here."""
    messages = _messages(
        ("customer", "Faturam yanlış geldi."),
        ("support", REPLIES["tr"]),
    )
    payload = _payload(messages, "Turkish")
    allowed = {"numerical", "categorical", "textual"}
    for context in payload["contexts"]:
        for facet in context["facets"]:
            assert facet["kind"] in allowed, (context["contextType"], facet["key"])
            assert facet["role"] in {"primary", "score", "evidence", "explanation"}
