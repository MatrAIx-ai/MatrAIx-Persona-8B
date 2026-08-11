"""Verifier for the multilingual telco support chat task.

Measures whether the support bot answered in the persona's own language. The
question is *what the bot did*, not whether it did well, so:

- ``reward.txt`` stays 1/0 on artifact presence and schema validity alone. A bot
  that answered every single turn in the wrong language still scores 1.
- Language behaviour is reported as facets under the ``language_adherence``
  context in ``structured_output.json``, where batch reporting can slice it by
  persona segment.

``user_feedback`` is deliberately **not** emitted here. The platform synthesizes
that context from ``user_feedback.json`` plus ``input/self_report_schema.yaml``,
deriving each facet's kind and enum choices from the schema; a verifier-emitted
context short-circuits that path (``job_aggregation.py``) and would mean writing
facet code by hand for every self-report field, with the usual drift between
schema and code. The feedback artifact is still *read* below, as evidence for
``task_outcome``.

What the rate compares against
------------------------------
``language_match_rate`` scores the bot's replies against the language the
**customer actually wrote in**, not against the persona's declared
``primary_language``.

The sidecar receives only the incoming message; it cannot see a persona field, so
scoring it against one would not measure the bot. This is not hypothetical: in the
first real cohort run a persona declaring ``primary_language: German`` conducted
the whole conversation in English. Nothing forces a persona agent to write in its
declared language — the prompt is English, ``instruction.md`` is English, and the
task deliberately does not instruct a language, because instructing one would
measure compliance with our instruction instead of natural behaviour.

The declared language is still reported, in two facets that make the distinction
explicit:

- ``customer_language`` — what the customer actually used, the rate's target
- ``persona_expected_language`` — what the record declares
- ``persona_language_adherence`` — whether those two agree, which is the validity
  check on the trial. A German-declared persona writing English tested
  English-to-English, whatever the cohort filter selected for.

Language detection
------------------
Detection is deterministic and offline: language-exclusive characters plus
function-word lists, scored per reply. A probabilistic library such as
``langdetect`` was rejected on purpose — it can return different answers for the
same input and would make CI flake.

That choice has real limits, and they are reported rather than hidden:

- **Short replies carry little signal.** Below ``_MIN_TOKENS`` tokens a reply is
  ``undetermined`` rather than guessed at.
- **Language-neutral filler dilutes the score.** Invoice ids, reference codes,
  amounts, and proper nouns match nothing, so a reply that is mostly numbers
  scores low even when a human would read it instantly.
- **Related languages can collide.** Only characters *exclusive* to one language
  are scored — shared umlauts would let Turkish and German tie and hand the
  decision to iteration order — but overlapping function words still blur the
  boundary, so a reply must beat the runner-up by ``_MIN_HITS`` to be called.
- **Only four languages are modelled**, matching what the SUT can speak. A
  persona whose language falls outside them is reported as
  ``persona_language_unsupported``, never forced into the nearest match.

Nothing is silently assigned. Every reply is either attributed with a confidence
or marked ``undetermined``, and the per-trial ``measurement_status`` facet states
whether an adherence rate could be computed at all.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

OUTPUT_DIR = Path(
    os.environ.get("HARBOR_OUTPUT_DIR")
    or os.environ.get("MATRIX_OUTPUT_DIR")
    or "/app/output"
)
TRANSCRIPT_PATH = OUTPUT_DIR / "transcript.json"
FEEDBACK_PATH = OUTPUT_DIR / "user_feedback.json"

UNDETERMINED = "undetermined"

# Detector coverage. Kept to what the SUT can actually speak; anything else is
# reported as unsupported rather than approximated.
SUPPORTED_LANGUAGES = ("en", "tr", "es", "de")

# Persona schema values -> detector codes. "Turkish" is present in the persona
# datasets even though persona/schema/dimensions.json does not list it under
# primary_language; that mismatch is a known open question, and excluding the
# value here would silently drop exactly the personas this task exists to study.
PERSONA_LANGUAGE_CODES = {
    "english": "en",
    "turkish": "tr",
    "spanish": "es",
    "german": "de",
}

# Only characters exclusive to one language. Umlauts o and u appear in both
# Turkish and German, so scoring them would let the two tie.
LANGUAGE_CHARS = {
    "tr": "çğış",
    "es": "ñ¿¡",
    "de": "äß",
    "en": "",
}

# Function words, chosen to be unambiguous across the four languages: tokens that
# occur in more than one of them (for example Spanish/German "es", English/German
# "in") are left out entirely rather than scored for both.
LANGUAGE_WORDS = {
    "tr": frozenset(
        {
            "ancak", "bir", "bu", "cok", "daha", "degil", "ekibimiz", "faturadaki",
            "gun", "icin", "icinde", "ile", "kadar", "numarali", "olarak", "size",
            "sizin", "sonra", "tutarindaki", "uzgunum", "var", "yok",
        }
    ),
    "es": frozenset(
        {
            "cargo", "con", "cuanto", "dias", "equipo", "esta", "factura", "hasta",
            "las", "los", "para", "por", "reclamacion", "sigue", "su", "sus",
            "una", "revision",
        }
    ),
    "de": frozenset(
        {
            "dem", "den", "der", "die", "eine", "fuer", "geprueft", "ihnen", "ihr",
            "ihre", "ist", "sobald", "und", "wie", "wir", "wird",
        }
    ),
    "en": frozenset(
        {
            "and", "are", "been", "billing", "can", "charge", "confirms", "have",
            "invoice", "only", "our", "team", "that", "the", "until", "was", "we",
            "will", "you", "your",
        }
    ),
}

# Gates. Both are absolute rather than tuned: a reply must carry some minimum
# amount of evidence, and the winner must be clearly ahead of the runner-up.
_MIN_TOKENS = 4
_MIN_HITS = 2


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def _verifier_dir() -> Path:
    explicit = os.environ.get("HARBOR_VERIFIER_DIR")
    if explicit:
        path = Path(explicit)
        path.mkdir(parents=True, exist_ok=True)
        return path

    container_default = Path("/logs/verifier")
    try:
        container_default.mkdir(parents=True, exist_ok=True)
        return container_default
    except OSError:
        pass

    raise RuntimeError(
        "HARBOR_VERIFIER_DIR is required when running outside a Harbor trial "
        "container. Point it at jobs/<job>/<trial>/verifier for local harness runs."
    )


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        fail(f"{path} is missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{path} is not valid JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{path} must contain a JSON object")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{label} must be a non-empty string")
    return value


def normalize(text: str) -> str:
    """Casefold for matching, without the Turkish dotted-capital-I trap.

    ``"İ".lower()`` yields ``"i"`` followed by COMBINING DOT ABOVE (U+0307), so a
    plain ``lower()`` makes ``"itiraz" in "İtiraz".lower()`` false and silently
    breaks every Turkish match. Diacritics are then folded away so the word lists
    above can stay ASCII and readable; character evidence is scored separately,
    before folding.

    Known limitation: U+0307 is dropped for every language, though in Lithuanian
    the combining dot above is a meaningful part of a letter. Acceptable for a
    four-language detector, and named rather than hidden — a task measuring
    language fidelity should not quietly mangle a language it does not model.
    """
    lowered = text.lower().replace("̇", "")
    folded = (
        lowered.replace("ç", "c")
        .replace("ğ", "g")
        .replace("ı", "i")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ü", "u")
        .replace("ä", "a")
        .replace("ß", "ss")
        .replace("ñ", "n")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    return folded


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[^0-9a-z]+", normalize(text)) if token]


def detect_language(text: str) -> tuple[str, float]:
    """Return ``(language_code_or_undetermined, confidence)``.

    Confidence is the winner's share of the evidence, so it lives in ``[0.5, 1.0]``
    for an attributed reply and is ``0.0`` when the reply is undetermined.
    """
    lowered = text.lower().replace("̇", "")
    tokens = _tokens(text)
    if len(tokens) < _MIN_TOKENS:
        return UNDETERMINED, 0.0

    token_set = set(tokens)
    scores: dict[str, int] = {}
    for language in SUPPORTED_LANGUAGES:
        word_hits = len(token_set & LANGUAGE_WORDS[language])
        char_hits = sum(1 for char in lowered if char in LANGUAGE_CHARS[language])
        scores[language] = 2 * word_hits + char_hits

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    best_language, best_score = ranked[0]
    runner_up_score = ranked[1][1] if len(ranked) > 1 else 0

    if best_score < _MIN_HITS or best_score - runner_up_score < _MIN_HITS:
        return UNDETERMINED, 0.0

    confidence = round(best_score / (best_score + runner_up_score), 3)
    return best_language, confidence


def _persona_yaml_candidates() -> list[Path]:
    """Where the persona record can be found at verify time.

    ``PersonaMixin._prepare_persona_trial`` uploads the persona YAML to
    ``/app/input/persona.yaml`` for in-container verifiers. Under the host
    execution plane that path is remapped beside the collected output directory,
    and there is no ``HARBOR_INPUT_DIR`` to ask, so both are tried.
    """
    return [
        Path("/app/input/persona.yaml"),
        OUTPUT_DIR.parent / "input" / "persona.yaml",
    ]


def read_persona_language(candidates: list[Path] | None = None) -> str | None:
    """Return the persona's raw ``primary_language`` value, or ``None``.

    Verifiers in this repo run under an isolated ``uvx`` environment with only
    pytest available, so PyYAML cannot be imported. Rather than add a dependency
    for one scalar, this scans the ``dimensions:`` block for a single key. It is
    not a YAML parser: it assumes the flat ``key: value`` mapping that the persona
    generator emits, and would need revisiting if persona records ever gain
    nested or multi-line values under ``dimensions``.
    """
    for path in candidates if candidates is not None else _persona_yaml_candidates():
        if not path.is_file():
            continue
        in_dimensions = False
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if not raw_line[:1].isspace():
                # A new top-level key ends the dimensions block.
                in_dimensions = stripped.rstrip(":") == "dimensions"
                continue
            if not in_dimensions:
                continue
            match = re.match(r"primary_language\s*:\s*(.+)$", stripped)
            if match:
                value = match.group(1).strip().strip("'\"").strip()
                return value or None
    return None


def resolve_expected_language(raw_value: str | None) -> tuple[str, str]:
    """Map a persona language onto a detector code plus a measurement status."""
    if not raw_value:
        return "unknown", "persona_language_unknown"
    code = PERSONA_LANGUAGE_CODES.get(raw_value.strip().lower())
    if code is None:
        return raw_value.strip(), "persona_language_unsupported"
    return code, "measured"


def validate_transcript(data: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        fail("transcript.messages must be a non-empty list")
    for entry in messages:
        if entry.get("role") not in {"customer", "support"}:
            fail("invalid transcript message role")
        require_string(entry.get("content"), "message content")
    combined = " ".join(str(entry["content"]) for entry in messages)
    return messages, combined


def validate_feedback(feedback: dict[str, Any]) -> None:
    for key in ("needConstraintSatisfaction", "personalPreferenceSatisfaction"):
        if feedback.get(key) in (None, ""):
            fail(f"user_feedback.{key} must be present")
    require_string(feedback.get("reason"), "user_feedback.reason")
    rating = feedback.get("overallExperienceRating")
    if not isinstance(rating, int) or rating < 1 or rating > 10:
        fail("user_feedback.overallExperienceRating must be an integer 1-10")
    asked = feedback.get("askedUsefulClarificationQuestions")
    if not isinstance(asked, bool):
        fail("user_feedback.askedUsefulClarificationQuestions must be boolean")


def _support_messages(messages: list[dict[str, Any]]) -> list[str]:
    return [
        entry["content"].strip()
        for entry in messages
        if entry.get("role") == "support"
        and isinstance(entry.get("content"), str)
        and entry["content"].strip()
    ]


def _count_support_questions(messages: list[dict[str, Any]]) -> int:
    return sum(
        1
        for entry in messages
        if entry.get("role") == "support"
        and isinstance(entry.get("content"), str)
        and "?" in entry["content"]
    )


def _customer_messages(messages: list[dict[str, Any]]) -> list[str]:
    return [
        entry["content"].strip()
        for entry in messages
        if entry.get("role") == "customer"
        and isinstance(entry.get("content"), str)
        and entry["content"].strip()
    ]


def detect_customer_language(messages: list[dict[str, Any]]) -> str:
    """The language the customer actually wrote in, or ``undetermined``.

    Detected per message and resolved by majority so a single long turn cannot
    outvote the rest, with ties falling to ``undetermined`` rather than to
    whichever language happened to sort first.
    """
    attributed = [
        language
        for language, _ in (detect_language(text) for text in _customer_messages(messages))
        if language != UNDETERMINED
    ]
    if not attributed:
        return UNDETERMINED
    counts: dict[str, int] = {}
    for language in attributed:
        counts[language] = counts.get(language, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: -item[1])
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return UNDETERMINED
    return ranked[0][0]


def analyze_language(
    messages: list[dict[str, Any]],
    customer_language: str,
) -> dict[str, Any]:
    """Per-reply language attribution plus the trial-level rollup.

    The match rate compares the bot's replies against the language the customer
    **actually wrote in**, not against the persona's declared ``primary_language``.
    The sidecar only ever sees the incoming message; scoring it against a persona
    field it cannot observe would not be a measurement of the bot. The declared
    language is still reported, as a validity check on the trial rather than as
    the target.
    """
    replies = _support_messages(messages)
    detections = [detect_language(reply) for reply in replies]
    languages = [language for language, _ in detections]
    confidences = [confidence for _, confidence in detections]

    attributed = [language for language in languages if language != UNDETERMINED]
    switches = sum(
        1
        for previous, current in zip(attributed, attributed[1:])
        if previous != current
    )

    result: dict[str, Any] = {
        "reply_languages": languages,
        "first_reply_language": languages[0] if languages else UNDETERMINED,
        "language_switch_count": switches,
        "detection_confidence": (
            round(sum(confidences) / len(confidences), 3) if confidences else 0.0
        ),
        "undetermined_reply_count": languages.count(UNDETERMINED),
        "match_rate": None,
    }
    if customer_language != UNDETERMINED and attributed:
        matches = sum(1 for language in attributed if language == customer_language)
        result["match_rate"] = round(matches / len(attributed), 3)
    return result


def resolve_persona_adherence(customer_language: str, expected_code: str, persona_status: str) -> str:
    """Did the persona write in the language its record declares?

    This is the validity check that tells an analyst whether a trial exercised
    cross-language behaviour at all. A German-declared persona that writes English
    tested English-to-English, whatever the cohort filter said.
    """
    if persona_status != "measured":
        return persona_status
    if customer_language == UNDETERMINED:
        return "customer_language_undetermined"
    return "yes" if customer_language == expected_code else "no"


def _language_notes(
    language: dict[str, Any],
    customer_language: str,
    expected_code: str,
    adherence: str,
) -> str:
    observed = ", ".join(language["reply_languages"]) or "none"
    if customer_language == UNDETERMINED:
        return (
            "No customer message carried enough signal to attribute a language, so "
            "no adherence rate was computed. Reply languages observed: {}.".format(
                observed
            )
        )
    if language["match_rate"] is None:
        return (
            "No support reply carried enough signal to attribute a language, so "
            "no adherence rate was computed. The customer wrote in {}.".format(
                customer_language
            )
        )
    note = (
        "{} of the attributed support replies were in the language the customer "
        "wrote in ({}). First reply was {}; the reply language changed {} time(s); "
        "{} reply(ies) were left undetermined.".format(
            "{:.0%}".format(language["match_rate"]),
            customer_language,
            language["first_reply_language"],
            language["language_switch_count"],
            language["undetermined_reply_count"],
        )
    )
    if adherence == "no":
        note += (
            " Note: the persona record declares {}, so this trial did not exercise "
            "that language and says nothing about how the bot handles it.".format(
                expected_code
            )
        )
    return note


def _derive_outcome(
    combined_lower: str,
    support_count: int,
    feedback: dict[str, Any] | None,
) -> dict[str, str]:
    dispute_logged = "dsp-5512" in combined_lower
    if feedback is not None:
        need = str(feedback.get("needConstraintSatisfaction", "")).strip().lower()
        preference = str(
            feedback.get("personalPreferenceSatisfaction", "")
        ).strip().lower()
        if need == "yes" and preference == "yes":
            status = "resolved"
        elif need == "no":
            status = "unresolved"
        else:
            status = "partially_resolved"
        basis = "user_feedback"
        reason = require_string(feedback.get("reason"), "user_feedback.reason")
    else:
        status = (
            "partially_resolved"
            if dispute_logged and support_count >= 2
            else "unresolved"
        )
        basis = "conversation_commitment"
        reason = (
            "Support logged the billing dispute and gave a review window, but the "
            "disputed charge was not settled within this chat."
            if dispute_logged
            else "The chat did not produce a logged dispute, so the disputed "
            "charge remained unresolved."
        )

    followup_markers = ("business days", "review", "let us know", "get back")
    owner = (
        "user"
        if status != "resolved" or any(m in combined_lower for m in followup_markers)
        else "none"
    )
    return {
        "outcome_status": status,
        "resolution_basis": basis,
        "outcome_reason": reason,
        "next_step_owner": owner,
    }


def _derive_conversation_path(
    clarification_question_count: int,
    dispute_logged: bool,
    outcome_status: str,
) -> str:
    if outcome_status == "resolved" and clarification_question_count > 0:
        return "clarify_then_resolve"
    if clarification_question_count > 0 or dispute_logged:
        return "clarify_then_partial"
    return "stalled"


def build_evaluation_payload(
    messages: list[dict[str, Any]],
    combined: str,
    feedback: dict[str, Any] | None,
    persona_language: str | None,
) -> dict[str, Any]:
    combined_lower = normalize(combined)
    customer_count = sum(1 for message in messages if message["role"] == "customer")
    support_count = sum(1 for message in messages if message["role"] == "support")
    clarification_question_count = _count_support_questions(messages)
    dispute_logged = "dsp-5512" in combined_lower

    if feedback is not None:
        validate_feedback(feedback)

    expected_code, persona_status = resolve_expected_language(persona_language)
    customer_language = detect_customer_language(messages)
    language = analyze_language(messages, customer_language)
    adherence = resolve_persona_adherence(customer_language, expected_code, persona_status)
    status = (
        "measured" if customer_language != UNDETERMINED else "customer_language_undetermined"
    )
    outcome = _derive_outcome(combined_lower, support_count, feedback)
    conversation_path = _derive_conversation_path(
        clarification_question_count,
        dispute_logged,
        outcome["outcome_status"],
    )

    language_facets: list[dict[str, Any]] = []
    if language["match_rate"] is not None:
        language_facets.append(
            {
                "key": "language_match_rate",
                "label": "Share of replies in the customer's language",
                "role": "score",
                "kind": "numerical",
                "value": language["match_rate"],
            }
        )
    language_facets.extend(
        [
            {
                # Primary because it is the one facet always present, and it says
                # whether the rest of the context means anything.
                "key": "measurement_status",
                "label": "Language measurement status",
                "role": "primary",
                "kind": "categorical",
                "value": status,
            },
            {
                "key": "customer_language",
                "label": "Language the customer wrote in",
                "role": "evidence",
                "kind": "categorical",
                "value": customer_language,
            },
            {
                "key": "persona_language_adherence",
                "label": "Persona wrote in its declared language",
                "role": "evidence",
                "kind": "categorical",
                "value": adherence,
            },
            {
                "key": "first_reply_language",
                "label": "Language of the first reply",
                "role": "evidence",
                "kind": "categorical",
                "value": language["first_reply_language"],
            },
            {
                "key": "persona_expected_language",
                "label": "Persona's declared language",
                "role": "evidence",
                "kind": "categorical",
                "value": expected_code,
            },
            {
                "key": "language_switch_count",
                "label": "Reply language changes",
                "role": "score",
                "kind": "numerical",
                "value": language["language_switch_count"],
            },
            {
                "key": "detection_confidence",
                "label": "Mean detection confidence",
                "role": "score",
                "kind": "numerical",
                "value": language["detection_confidence"],
            },
            {
                "key": "undetermined_reply_count",
                "label": "Replies with no attributable language",
                "role": "score",
                "kind": "numerical",
                "value": language["undetermined_reply_count"],
            },
            {
                "key": "language_adherence_notes",
                "label": "Language adherence notes",
                "role": "explanation",
                "kind": "textual",
                # Bind to the match rate when there is one; otherwise the status
                # is the field this text explains, so the grouped view still works.
                "explainsFacetKey": (
                    "language_match_rate"
                    if language["match_rate"] is not None
                    else "measurement_status"
                ),
                "value": _language_notes(
                    language, customer_language, expected_code, adherence
                ),
            },
        ]
    )

    payload: dict[str, Any] = {
        "schemaVersion": "1.0",
        "artifactType": "matraix.trial_evaluation",
        "taskType": "chatbot",
        "presenceCheck": {
            "passed": True,
            "requiredArtifacts": ["transcript.json"],
            "missingArtifacts": [],
        },
        "sourceArtifacts": {
            "transcript": "/app/output/transcript.json",
            "userFeedback": (
                "/app/output/user_feedback.json" if feedback is not None else None
            ),
            "persona": next(
                (str(path) for path in _persona_yaml_candidates() if path.is_file()),
                None,
            ),
        },
        "contexts": [
            {
                "key": "language_adherence.primary",
                "label": "Language adherence",
                "contextType": "language_adherence",
                "facets": language_facets,
            },
            {
                "key": "task_outcome.primary",
                "label": "Task outcome",
                "contextType": "task_outcome",
                "facets": [
                    {
                        "key": "outcome_status",
                        "label": "Outcome status",
                        "role": "primary",
                        "kind": "categorical",
                        "value": outcome["outcome_status"],
                    },
                    {
                        "key": "resolution_basis",
                        "label": "Resolution basis",
                        "role": "primary",
                        "kind": "categorical",
                        "value": outcome["resolution_basis"],
                    },
                    {
                        "key": "outcome_reason",
                        "label": "Outcome reason",
                        "role": "explanation",
                        "kind": "textual",
                        "explainsFacetKey": "outcome_status",
                        "value": outcome["outcome_reason"],
                    },
                    {
                        "key": "next_step_owner",
                        "label": "Next step owner",
                        "role": "evidence",
                        "kind": "categorical",
                        "value": outcome["next_step_owner"],
                    },
                    {
                        "key": "task_goal_label",
                        "label": "Task goal",
                        "role": "evidence",
                        "kind": "textual",
                        "value": "Resolve an unexpected charge on a mobile invoice",
                    },
                ],
            },
            {
                "key": "conversation_summary.primary",
                "label": "Conversation summary",
                "contextType": "conversation_summary",
                "facets": [
                    {
                        "key": "conversation_path",
                        "label": "Conversation path",
                        "role": "primary",
                        "kind": "categorical",
                        "value": conversation_path,
                    },
                    {
                        "key": "process_notes",
                        "label": "Process notes",
                        "role": "explanation",
                        "kind": "textual",
                        "explainsFacetKey": "conversation_path",
                        "value": (
                            "The exchange moved from the disputed charge to a "
                            "logged dispute with a review window."
                            if dispute_logged
                            else "The exchange stayed short and never reached a "
                            "logged dispute."
                        ),
                    },
                    {
                        "key": "user_turn_count",
                        "label": "User turn count",
                        "role": "score",
                        "kind": "numerical",
                        "value": customer_count,
                    },
                    {
                        "key": "assistant_turn_count",
                        "label": "Assistant turn count",
                        "role": "score",
                        "kind": "numerical",
                        "value": support_count,
                    },
                    {
                        "key": "message_count",
                        "label": "Message count",
                        "role": "score",
                        "kind": "numerical",
                        "value": len(messages),
                    },
                    {
                        "key": "clarification_question_count",
                        "label": "Clarification question count",
                        "role": "score",
                        "kind": "numerical",
                        "value": clarification_question_count,
                    },
                ],
            },
        ],
    }
    return payload


def main() -> int:
    transcript = load_json(TRANSCRIPT_PATH)
    messages, combined = validate_transcript(transcript)
    feedback = load_json(FEEDBACK_PATH) if FEEDBACK_PATH.is_file() else None
    payload = build_evaluation_payload(
        messages, combined, feedback, read_persona_language()
    )
    (_verifier_dir() / "structured_output.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("PASS: multilingual telco support chat artifacts are valid")
    return 0


def test_transcript_exists() -> None:
    assert TRANSCRIPT_PATH.is_file(), f"Missing {TRANSCRIPT_PATH}"


def test_transcript_schema() -> None:
    transcript = load_json(TRANSCRIPT_PATH)
    messages, combined = validate_transcript(transcript)
    feedback = load_json(FEEDBACK_PATH) if FEEDBACK_PATH.is_file() else None
    payload = build_evaluation_payload(
        messages, combined, feedback, read_persona_language()
    )
    assert payload["contexts"], "evaluation contexts must not be empty"
    context_types = {context.get("contextType") for context in payload["contexts"]}
    assert "task_outcome" in context_types
    assert "language_adherence" in context_types


def test_language_context_declares_measurement_status() -> None:
    transcript = load_json(TRANSCRIPT_PATH)
    messages, combined = validate_transcript(transcript)
    feedback = load_json(FEEDBACK_PATH) if FEEDBACK_PATH.is_file() else None
    payload = build_evaluation_payload(
        messages, combined, feedback, read_persona_language()
    )
    language = next(
        context
        for context in payload["contexts"]
        if context["contextType"] == "language_adherence"
    )
    facets = {facet["key"]: facet for facet in language["facets"]}
    # Unmeasurability is declared, never silent: the status facet is always
    # present, and the match rate is absent exactly when it could not be computed.
    assert "measurement_status" in facets
    if facets["measurement_status"]["value"] != "measured":
        assert "language_match_rate" not in facets


if __name__ == "__main__":
    raise SystemExit(main())
