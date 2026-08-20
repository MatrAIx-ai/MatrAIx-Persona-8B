"""Acme customer support REST API with per-session conversation state."""

from __future__ import annotations

import re
import threading
import uuid

from flask import Flask, jsonify, request

app = Flask(__name__)

_sessions_lock = threading.Lock()
# session_id → ordered chat turns for that trial / browser session
_sessions: dict[str, list[dict[str, str]]] = {}

_ORDER_ID = "4521"
_ORDER_STATUS = (
    "Order #4521 is still in transit. The latest carrier scan shows it left the "
    "regional hub yesterday. Delivery is expected within 1–2 business days."
)


def _bot_reply(customer_message: str) -> str:
    text = customer_message.lower()

    if re.search(r"\b4521\b", text):
        if any(
            word in text for word in ("refund", "replace", "replacement", "money back")
        ):
            return (
                f"I understand your frustration about order #{_ORDER_ID}. "
                f"{_ORDER_STATUS} I can't authorize a refund or replacement until "
                "we confirm a delivery exception with the carrier. If it hasn't "
                "arrived by Friday, reply here and we'll open a trace."
            )
        return (
            f"Thanks for confirming. {_ORDER_STATUS} If it hasn't arrived by "
            "Friday, let me know and we'll open a carrier trace. Is the shipping "
            "address on the order still correct?"
        )

    if any(word in text for word in ("refund", "replace", "replacement", "money back")):
        return (
            "I can't authorize a refund or replacement without verifying the order "
            "status first. Could you share your order number so I can look it up?"
        )

    if any(
        word in text
        for word in ("order", "package", "delivery", "arrive", "late", "shipped")
    ):
        return (
            "I'm sorry your delivery is delayed. Could you share your order number "
            "so I can check the latest tracking status?"
        )

    return (
        "Hi, thanks for contacting Acme Support. How can I help you today? If this "
        "is about an order, please share your order number."
    )


def _resolve_session_id(raw: object) -> str:
    text = str(raw or "").strip()
    return text or str(uuid.uuid4())


def _session_messages(session_id: str) -> list[dict[str, str]]:
    with _sessions_lock:
        bucket = _sessions.get(session_id)
        if bucket is None:
            bucket = []
            _sessions[session_id] = bucket
        return bucket


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

    session_id = _resolve_session_id(payload.get("sessionId"))
    messages = _session_messages(session_id)
    with _sessions_lock:
        messages.append({"role": "customer", "content": customer_message})
        reply = _bot_reply(customer_message)
        messages.append({"role": "support", "content": reply})
        snapshot = list(messages)

    turn = {
        "index": len(snapshot) // 2,
        "userMessage": customer_message,
        "assistantReply": reply,
    }
    return jsonify({"sessionId": session_id, "reply": reply, "turn": turn})


@app.get("/v1/conversation")
def get_conversation():
    session_id = str(request.args.get("sessionId") or "").strip()
    with _sessions_lock:
        if session_id:
            messages = list(_sessions.get(session_id, []))
            return jsonify({"sessionId": session_id, "messages": messages})

        if len(_sessions) > 1:
            return jsonify(
                {
                    "error": "sessionId is required when multiple conversations exist",
                    "sessionCount": len(_sessions),
                }
            ), 400

        if len(_sessions) == 1:
            only_id, only_messages = next(iter(_sessions.items()))
            return jsonify({"sessionId": only_id, "messages": list(only_messages)})

    return jsonify({"sessionId": "", "messages": []})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
