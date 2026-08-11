"""Meridian Mobile billing-dispute REST API with in-memory conversation state.

A deterministic mock telco support bot whose *language* behaviour is deliberately
uneven, so that a persona population produces a distribution rather than a
constant. Every reply is a pure function of the customer message, so repeated
runs on the same input are byte-identical (no randomness, no clock, no network).

Language behaviour is data, not control flow: ``_REPLIES[intent]`` holds one
entry per language the bot has been localized for, and anything missing falls
back to English. That encodes three failure modes seen in real systems:

1. **Tiered localization.** Greetings are localized widely; the deeper the
   intent, the thinner the coverage. ``bill_breakdown`` and ``refund_policy``
   are English-only for *every* user, including full-support languages.
2. **Partial locales.** Spanish stops after ``dispute_open``; German stops after
   ``greeting``. Both silently degrade to English instead of erroring.
3. **Locale-fallback bug.** ``status_check`` detects the user's language and
   then answers in the wrong one, simulating a misconfigured fallback chain
   that leaks a non-English default locale.

The bot does **not** expose what it detected. Detection is an internal concern;
the observable surface is the reply text, which is what a verifier should
measure. See README.md for the full behaviour matrix.
"""

from __future__ import annotations

import threading

from flask import Flask, jsonify, request

app = Flask(__name__)

# Conversation state is scoped per session, not global.
#
# Playground reuses one sidecar process for a whole cohort when the service is
# registered as a shared sidecar (see chatbot_shared_sidecar.py), and that path
# never resets state between trials. A single module-level message list would
# therefore accumulate every persona's turns, and because the harness builds
# ``transcript.json`` from ``GET /v1/conversation`` rather than from the agent's
# own record, trial N would be scored against trials 1..N. Session scoping is a
# correctness requirement here, not an optimization.
#
# Session ids are minted from a counter rather than a UUID or timestamp so the
# service stays free of randomness and clock reads.
_sessions: dict[str, list[dict[str, str]]] = {}
_session_counter = 0
_state_lock = threading.Lock()

_INVOICE_ID = "INV-70431"
_DISPUTE_REF = "DSP-5512"

# Languages this bot has any localization for. Anything else resolves to English.
_SUPPORTED_LANGUAGES = ("en", "tr", "es", "de")
_DEFAULT_LANGUAGE = "en"

# Naive SUT-side detection: language-exclusive characters plus a function-word
# list. Intentionally simple — this is the system under test, not the measuring
# instrument.
#
# Only characters *exclusive* to one language count. Umlauts o and u appear in
# both Turkish and German, so scoring them would make the two languages tie and
# let iteration order pick the winner. Function words carry the real signal and
# are weighted above characters.
_LANGUAGE_CHARS: dict[str, str] = {
    "tr": "çğış",
    "es": "ñ¿¡",
    "de": "äß",
    "en": "",
}

_LANGUAGE_WORDS: dict[str, frozenset[str]] = {
    "tr": frozenset(
        {
            "alabilir", "bir", "değil", "durumu", "ederim", "fatura", "faturam",
            "faturamın", "görebilir", "günler", "hakkında", "hesabım", "hesap",
            "istiyorum", "itiraz", "itirazımın", "için", "lütfen", "merhaba",
            "miyim", "neden", "nedir", "oldu", "selam", "sorum", "teşekkür",
            "var", "yanlış", "çok"
        }
    ),
    "es": frozenset(
        {
            "buenos", "cobro", "cuenta", "cuál", "desglose", "días", "erróneo",
            "estado", "está", "factura", "gracias", "hay", "hola", "incorrecta",
            "la", "mi", "nombre", "novedades", "partidas", "política", "por",
            "puedo", "qué", "reclamación", "reembolso", "sobre", "ver"
        }
    ),
    "de": frozenset(
        {
            "aufschlüsselung", "bitte", "danke", "das", "dauert", "der", "die",
            "einzelposten", "falsch", "guten", "hallo", "hoch", "ich", "ihre",
            "ist", "kann", "konto", "lange", "mein", "meine", "nicht", "noch",
            "rechnung", "richtlinie", "rückerstattung", "sehen", "stand", "tag",
            "und", "warum", "wie", "zur"
        }
    ),
    "en": frozenset(
        {
            "account", "any", "bill", "breakdown", "can", "charge", "dispute",
            "good", "hello", "high", "invoice", "is", "items", "line", "mine",
            "morning", "my", "on", "please", "policy", "refund", "see",
            "status", "thanks", "the", "there", "too", "update", "what", "why",
            "wrong", "your"
        }
    ),
}

# Intent keywords span all four languages: a Turkish customer asking for a line
# item breakdown must still reach ``bill_breakdown``, otherwise the deep-intent
# English fallback would only ever fire for English speakers and the task would
# measure nothing. Order matters — the first matching intent wins, so specific
# intents are listed before the broad ``dispute_open``.
_INTENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "bill_breakdown",
        (
            "breakdown",
            "line item",
            "line items",
            "itemize",
            "itemized",
            "detailed bill",
            "kalem",
            "döküm",
            "ayrıntılı",
            "detaylı fatura",
            "desglose",
            "partidas",
            "detallada",
            "aufschlüsselung",
            "einzelposten",
            "aufstellung",
        ),
    ),
    (
        "refund_policy",
        (
            "refund",
            "reimburse",
            "money back",
            "policy",
            "iade",
            "geri ödeme",
            "politika",
            "reembolso",
            "devolución",
            "política",
            "rückerstattung",
            "erstattung",
            "richtlinie",
        ),
    ),
    (
        "status_check",
        (
            "status",
            "any update",
            "progress",
            "how long",
            "durum",
            "ne oldu",
            "ne zaman",
            "ilerleme",
            "estado",
            "novedades",
            "tarda",
            "stand",
            "wie lange",
        ),
    ),
    (
        "dispute_open",
        (
            "dispute",
            "wrong",
            "incorrect",
            "too high",
            "overcharge",
            "invoice",
            "bill",
            "charge",
            "roaming",
            "itiraz",
            "yanlış",
            "hatalı",
            "yüksek",
            "fatura",
            "reclamación",
            "reclamo",
            "incorrecto",
            "erróneo",
            "factura",
            "cobro",
            "widerspruch",
            "falsch",
            "zu hoch",
            "rechnung",
        ),
    ),
    (
        "greeting",
        (
            "hello",
            "hi ",
            "good morning",
            "good afternoon",
            "merhaba",
            "selam",
            "iyi günler",
            "günaydın",
            "hola",
            "buenos días",
            "buenas tardes",
            "hallo",
            "guten tag",
            "guten morgen",
        ),
    ),
)

# One entry per language the intent has been localized for. A missing language
# is the whole mechanism for partial support — see module docstring.
_REPLIES: dict[str, dict[str, str]] = {
    # Fully localized: every supported language present.
    "greeting": {
        "en": (
            "Hello, welcome to Meridian Mobile support. How can I help you with "
            "your account today?"
        ),
        "tr": (
            "Merhaba, Meridian Mobile destek hattına hoş geldiniz. Hesabınızla "
            "ilgili size nasıl yardımcı olabilirim?"
        ),
        "es": (
            "Hola, bienvenido al soporte de Meridian Mobile. ¿Cómo puedo "
            "ayudarle con su cuenta hoy?"
        ),
        "de": (
            "Hallo, willkommen beim Meridian Mobile Support. Wie kann ich Ihnen "
            "heute mit Ihrem Konto helfen?"
        ),
    },
    # German missing on purpose: German degrades to English past the greeting.
    "dispute_open": {
        "en": (
            f"I'm sorry about the unexpected amount on invoice {_INVOICE_ID}. I "
            "have logged a billing dispute for the international data roaming "
            f"charge of 89.90. Your dispute reference is {_DISPUTE_REF} and our "
            "billing team reviews it within 3 business days."
        ),
        "tr": (
            f"{_INVOICE_ID} numaralı faturadaki beklenmedik tutar için üzgünüm. "
            "89,90 tutarındaki yurt dışı veri dolaşım ücreti için bir fatura "
            f"itirazı kaydettim. İtiraz referansınız {_DISPUTE_REF} ve fatura "
            "ekibimiz bunu 3 iş günü içinde inceliyor."
        ),
        "es": (
            f"Lamento el importe inesperado en la factura {_INVOICE_ID}. He "
            "registrado una reclamación por el cargo de datos en roaming "
            f"internacional de 89,90. Su referencia de reclamación es "
            f"{_DISPUTE_REF} y nuestro equipo de facturación la revisa en 3 "
            "días laborables."
        ),
    },
    # Spanish and German missing: only Turkish keeps parity with English here.
    "generic": {
        "en": (
            "I can help with billing questions on your Meridian Mobile account. "
            f"Could you tell me which charge on invoice {_INVOICE_ID} looks "
            "wrong to you?"
        ),
        "tr": (
            "Meridian Mobile hesabınızdaki fatura sorularında yardımcı "
            f"olabilirim. {_INVOICE_ID} numaralı faturadaki hangi ücretin "
            "yanlış göründüğünü söyleyebilir misiniz?"
        ),
    },
    # Deep intent: English only, for every user including full-support languages.
    "bill_breakdown": {
        "en": (
            f"Here is the breakdown for invoice {_INVOICE_ID}: monthly plan "
            "249.00, domestic calls beyond bundle 41.60, SMS packs 32.00, "
            "international data roaming 89.90. Total 412.50. The roaming block "
            "is the line you disputed."
        ),
    },
    # Deep intent: English only.
    "refund_policy": {
        "en": (
            "Our refund policy: a disputed charge is credited to your next "
            "invoice once the billing team confirms the error, normally within "
            "3 business days. Direct bank refunds are only issued when the "
            "account is closed. Credits cannot be applied to charges older "
            "than two billing periods."
        ),
    },
    # Locale-fallback bug: never answered in the user's language, never English.
    "status_check": {
        "es": (
            f"Su reclamación {_DISPUTE_REF} sigue en revisión. El equipo de "
            "facturación aún no ha registrado una decisión. Le avisaremos en "
            "cuanto haya novedades."
        ),
        "de": (
            f"Ihr Widerspruch {_DISPUTE_REF} wird noch geprüft. Das "
            "Abrechnungsteam hat noch keine Entscheidung erfasst. Wir "
            "informieren Sie, sobald es Neuigkeiten gibt."
        ),
    },
}


def _normalize(text: str) -> str:
    """Lowercase for matching, without the Turkish dotted-capital-I trap.

    ``"İ".lower()`` is ``"i"`` followed by COMBINING DOT ABOVE (U+0307), so a
    plain ``lower()`` makes ``"iade" in "İade".lower()`` false and silently
    breaks keyword matching on Turkish sentences that begin with the letter.
    Dropping the combining dot maps it back onto a bare ``i``. The escape is
    written out rather than pasted literally, because the character is invisible
    in source and reads as an editing accident.

    Known limitation: this strips U+0307 in *every* language, not just Turkish.
    In Lithuanian the combining dot above is a meaningful part of a letter, so
    normalizing it away is lossy there. Acceptable for a four-language mock, and
    worth naming rather than hiding — a task that measures language fidelity
    should not quietly mangle a language it does not handle.
    """
    return text.lower().replace("\u0307", "")


def _detect_language(text: str) -> str:
    """Best-effort language guess for the customer message.

    Deterministic and offline. Ties resolve to English, which is also what an
    unrecognizable or very short message gets.
    """
    lowered = _normalize(text)
    tokens = {token.strip(".,!?¿¡:;()\"'") for token in lowered.split()}

    best_language = _DEFAULT_LANGUAGE
    best_score = 0
    for language in _SUPPORTED_LANGUAGES:
        chars = _LANGUAGE_CHARS[language]
        word_hits = len(tokens & _LANGUAGE_WORDS[language])
        char_hits = sum(1 for character in lowered if character in chars)
        score = 2 * word_hits + char_hits
        if score > best_score:
            best_language = language
            best_score = score
    return best_language


def _classify_intent(text: str) -> str:
    """First matching intent wins; specific intents precede broad ones."""
    lowered = _normalize(text)
    for intent, keywords in _INTENT_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return intent
    return "generic"


def _reply_language(intent: str, detected: str) -> str:
    """Which language the bot will actually answer in.

    ``status_check`` is the seeded defect: it resolves to a locale that is
    neither the customer's nor English, so a mismatch is guaranteed for every
    supported language. Every other intent takes the localized entry when one
    exists and silently degrades to English when it does not.
    """
    if intent == "status_check":
        return "de" if detected == "es" else "es"
    if detected in _REPLIES[intent]:
        return detected
    return _DEFAULT_LANGUAGE


def _bot_reply(customer_message: str) -> str:
    intent = _classify_intent(customer_message)
    detected = _detect_language(customer_message)
    return _REPLIES[intent][_reply_language(intent, detected)]


@app.get("/health")
@app.get("/v1/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/ready")
@app.get("/v1/ready")
def ready():
    # Exercise the reply path so Service up means the bot can answer.
    sample = _bot_reply("hello")
    if not str(sample).strip():
        return jsonify({"status": "error", "detail": "empty bot reply"}), 503
    return jsonify(
        {
            "status": "ready",
            "capabilities": ["text_chat", "conversation"],
        }
    )


@app.post("/v1/messages")
def post_message():
    payload = request.get_json(silent=True) or {}
    customer_message = str(payload.get("message", "")).strip()
    if not customer_message:
        return jsonify({"error": "message must not be empty"}), 400

    # The harness omits sessionId on the first turn and then echoes back whatever
    # this response returns, so minting one here starts the session.
    session_id = str(payload.get("sessionId") or "").strip()
    reply = _bot_reply(customer_message)
    with _state_lock:
        if not session_id:
            global _session_counter
            _session_counter += 1
            session_id = "telco-{}".format(_session_counter)
        messages = _sessions.setdefault(session_id, [])
        messages.append({"role": "customer", "content": customer_message})
        messages.append({"role": "support", "content": reply})
    return jsonify({"reply": reply, "sessionId": session_id})


@app.get("/v1/conversation")
def get_conversation():
    session_id = str(request.args.get("sessionId") or "").strip()
    with _state_lock:
        if not session_id:
            # Convenience for manual curl against a single-session instance.
            # Merging every session would reintroduce exactly the cross-trial
            # bleed this scoping exists to prevent, so refuse instead.
            if len(_sessions) > 1:
                return (
                    jsonify(
                        {
                            "error": "sessionId is required when more than one "
                            "conversation exists",
                            "sessionCount": len(_sessions),
                        }
                    ),
                    400,
                )
            session_id = next(iter(_sessions), "")
        # An unknown id yields an empty conversation rather than a merged or
        # invented one; the verifier then fails artifact validation, which is the
        # signal we want.
        messages = list(_sessions.get(session_id, []))
    return jsonify({"sessionId": session_id, "messages": messages})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
