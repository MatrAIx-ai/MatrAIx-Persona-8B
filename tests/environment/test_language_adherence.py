"""Unit tests for the multilingual telco support verifier's language detection.

The verifier lives inside a task folder and is executed by ``tests/test.sh`` in an
isolated ``uvx`` environment, so it is loaded here by path rather than imported as
a package. Fixtures are deliberately tiny synthetic transcripts — no captured job
output.
"""

from __future__ import annotations

import importlib.util
import sys
import types
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


# Customer turns long enough to attribute; short ones are undetermined by design.
CUSTOMER = {
    "en": "Hello, my invoice is wrong and the charge on it is too high, can you see why?",
    "tr": "Merhaba, faturam yanlış geldi ve tutar çok yüksek, bir itiraz açmak istiyorum.",
    "es": "Hola, mi factura es incorrecta y el cobro por los días es erróneo, ¿puedo ver el desglose?",
    "de": "Hallo, meine Rechnung ist falsch und der Betrag ist zu hoch, kann ich die Aufstellung sehen?",
}


@pytest.mark.parametrize("language", sorted(CUSTOMER))
def test_customer_language_detected(language: str) -> None:
    messages = _messages(("customer", CUSTOMER[language]), ("support", REPLIES[language]))
    assert verifier.detect_customer_language(messages) == language


def test_customer_language_resolved_by_majority() -> None:
    messages = _messages(
        ("customer", CUSTOMER["de"]),
        ("support", REPLIES["de"]),
        ("customer", CUSTOMER["de"]),
        ("support", REPLIES["de"]),
        ("customer", CUSTOMER["en"]),
    )
    assert verifier.detect_customer_language(messages) == "de"


def test_customer_language_tie_is_undetermined() -> None:
    """A tie must not be broken by whichever language sorts first."""
    messages = _messages(("customer", CUSTOMER["de"]), ("customer", CUSTOMER["es"]))
    assert verifier.detect_customer_language(messages) == verifier.UNDETERMINED


def test_no_attributable_customer_turn_is_undetermined() -> None:
    messages = _messages(("customer", "ok"), ("customer", "Tamam."))
    assert verifier.detect_customer_language(messages) == verifier.UNDETERMINED


def test_match_rate_counts_only_attributed_replies() -> None:
    messages = _messages(
        ("customer", CUSTOMER["tr"]),
        ("support", REPLIES["tr"]),
        ("customer", CUSTOMER["tr"]),
        ("support", REPLIES["en"]),
        ("customer", CUSTOMER["tr"]),
        ("support", "Tamam."),
    )
    result = verifier.analyze_language(messages, "tr")
    # Two attributed replies (tr, en); the third is too short to attribute.
    assert result["undetermined_reply_count"] == 1
    assert result["match_rate"] == 0.5
    assert result["first_reply_language"] == "tr"
    assert result["language_switch_count"] == 1


def test_full_adherence_and_no_switches() -> None:
    messages = _messages(
        ("customer", CUSTOMER["es"]),
        ("support", REPLIES["es"]),
        ("customer", CUSTOMER["es"]),
        ("support", REPLIES["es"]),
    )
    result = verifier.analyze_language(messages, "es")
    assert result["match_rate"] == 1.0
    assert result["language_switch_count"] == 0


def test_match_rate_omitted_when_customer_language_undetermined() -> None:
    messages = _messages(("customer", "ok"), ("support", REPLIES["en"]))
    result = verifier.analyze_language(messages, verifier.UNDETERMINED)
    assert result["match_rate"] is None
    # Reply-only signals stay available regardless.
    assert result["first_reply_language"] == "en"
    assert result["detection_confidence"] > 0


@pytest.mark.parametrize(
    ("customer", "expected", "persona_status", "want"),
    [
        ("de", "de", "measured", "yes"),
        ("en", "de", "measured", "no"),
        ("undetermined", "de", "measured", "customer_language_undetermined"),
        ("en", "unknown", "persona_language_unknown", "persona_language_unknown"),
        ("en", "Mandarin", "persona_language_unsupported", "persona_language_unsupported"),
    ],
)
def test_persona_adherence_resolution(
    customer: str, expected: str, persona_status: str, want: str
) -> None:
    assert verifier.resolve_persona_adherence(customer, expected, persona_status) == want


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


def test_rate_targets_the_customer_language_not_the_declared_one() -> None:
    """Regression for the first real cohort run.

    A persona declaring German conducted the conversation in English and the bot
    replied in English. Scoring against the declared language called that 0%
    adherence; the bot in fact did the right thing. The SUT never sees
    primary_language, so the rate must target what the customer wrote.
    """
    messages = _messages(
        ("customer", CUSTOMER["en"]),
        ("support", REPLIES["en"]),
        ("customer", CUSTOMER["en"]),
        ("support", REPLIES["en"]),
    )
    facets = _language_facets(_payload(messages, "German"))
    assert facets["customer_language"]["value"] == "en"
    assert facets["persona_expected_language"]["value"] == "de"
    assert facets["language_match_rate"]["value"] == 1.0
    # The trial is flagged as not having exercised the declared language.
    assert facets["persona_language_adherence"]["value"] == "no"
    assert "did not exercise" in facets["language_adherence_notes"]["value"]


def test_declared_language_honoured_is_recorded_as_adherent() -> None:
    messages = _messages(("customer", CUSTOMER["de"]), ("support", REPLIES["de"]))
    facets = _language_facets(_payload(messages, "German"))
    assert facets["persona_language_adherence"]["value"] == "yes"
    assert facets["language_match_rate"]["value"] == 1.0


def test_payload_declares_unmeasurability_instead_of_omitting_silently() -> None:
    messages = _messages(("customer", "ok"), ("support", REPLIES["en"]))
    facets = _language_facets(_payload(messages, "German"))
    assert facets["measurement_status"]["value"] == "customer_language_undetermined"
    assert "language_match_rate" not in facets
    # The explanation rebinds to the status so the grouped view still renders.
    assert facets["language_adherence_notes"]["explainsFacetKey"] == "measurement_status"


def test_payload_binds_notes_to_match_rate_when_measured() -> None:
    messages = _messages(("customer", CUSTOMER["de"]), ("support", REPLIES["de"]))
    facets = _language_facets(_payload(messages, "German"))
    assert facets["language_match_rate"]["value"] == 1.0
    assert facets["language_adherence_notes"]["explainsFacetKey"] == "language_match_rate"


def test_unsupported_persona_language_still_measures_the_bot() -> None:
    """An unmodellable declared language no longer blocks the measurement."""
    messages = _messages(("customer", CUSTOMER["en"]), ("support", REPLIES["en"]))
    facets = _language_facets(_payload(messages, "Mandarin"))
    assert facets["persona_expected_language"]["value"] == "Mandarin"
    assert facets["persona_language_adherence"]["value"] == "persona_language_unsupported"
    assert facets["language_match_rate"]["value"] == 1.0


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


# --------------------------------------------------------------------------- #
# SUT intent routing
#
# The mock sidecar is the fixture this task measures, and two of its routing bugs
# only surfaced in a real cohort run. Both are locked in here.
# --------------------------------------------------------------------------- #
SIDECAR_PATH = (
    REPO_ROOT
    / "environment"
    / "task-environments"
    / "application"
    / "chatbot-api-sidecar_multilingual-telco-support"
    / "telco-support-api"
    / "server.py"
)


def _load_sidecar() -> Any:
    """Import the Flask app module without requiring Flask to be installed."""
    stub = types.ModuleType("flask")

    class _App:
        def __init__(self, name: str) -> None:
            self.name = name

        def _decorator(self, *_a: Any, **_k: Any):
            def wrap(fn):
                return fn

            return wrap

        get = _decorator
        post = _decorator

    stub.Flask = _App  # type: ignore[attr-defined]
    stub.jsonify = lambda *a, **k: None  # type: ignore[attr-defined]
    stub.request = None  # type: ignore[attr-defined]
    saved = sys.modules.get("flask")
    sys.modules["flask"] = stub
    try:
        spec = importlib.util.spec_from_file_location("telco_sidecar", SIDECAR_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if saved is not None:
            sys.modules["flask"] = saved
        else:
            sys.modules.pop("flask", None)


sidecar = _load_sidecar()


@pytest.mark.parametrize(
    "text",
    [
        "I believe there might be a misunderstanding",
        "my outstanding balance",
        "the standard plan",
    ],
)
def test_keywords_do_not_match_inside_longer_words(text: str) -> None:
    """``stand`` used to fire on "understanding" and route to status_check."""
    assert sidecar._classify_intent(text) != "status_check"


def test_standalone_status_word_still_routes() -> None:
    assert sidecar._classify_intent("Wie ist der Stand?") == "status_check"


@pytest.mark.parametrize(
    "text",
    [
        "I am calling about invoice INV-70431 and the roaming charge on it.",
        "Could you tell me more about the data roaming line on my bill?",
    ],
)
def test_scenario_nouns_alone_do_not_open_a_dispute(text: str) -> None:
    """Every turn in a billing scenario names the invoice.

    Keying dispute_open on those nouns made it absorb the whole conversation: a
    cohort run classified 30 of 30 customer turns as dispute_open and never
    reached another intent.
    """
    assert sidecar._classify_intent(text) != "dispute_open"


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("This charge is wrong and the amount is too high.", "dispute_open"),
        ("Faturam yanlış geldi, itiraz etmek istiyorum.", "dispute_open"),
        ("Can I see the line items breakdown?", "bill_breakdown"),
        ("What is your refund policy?", "refund_policy"),
        ("Any update on the status?", "status_check"),
        ("Hello, good morning", "greeting"),
        ("Thanks, that is all for now.", "generic"),
    ],
)
def test_intent_routing(text: str, intent: str) -> None:
    assert sidecar._classify_intent(text) == intent
