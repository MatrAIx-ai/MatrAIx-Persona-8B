"""CLI helpers for the playground package.

Headless end-to-end runs now launch through ``matraix run`` or
``POST /api/harbor/jobs``. This module keeps :func:`format_transcript` for
tests and tooling.
"""

from __future__ import annotations

from playground.types import PlaygroundResult

__all__ = ["format_transcript"]


def format_transcript(result: PlaygroundResult) -> str:
    """Render a :class:`PlaygroundResult` as a human-readable CLI transcript."""
    context_label = (
        result.config.application_context
        or result.config.domain
        or result.config.application_id
        or "chatbot"
    )
    lines = [
        "=== Playground run: {} ({}) ===".format(result.persona.name, context_label),
        "Persona goal: {}".format(result.persona.goal),
        "",
    ]
    for t in result.transcript:
        lines.append("USER:  {}".format(t.user_message))
        lines.append("AGENT: {}".format(t.assistant_message))
        for item in t.structured_exposure:
            label = item.get("label") or item.get("key") or "detail"
            value = item.get("value")
            if value not in (None, "", []):
                lines.append("       {}: {}".format(label, value))
        lines.append("")
    q = result.questionnaire
    lines += [
        "--- Evaluation ---",
        "Constraint satisfaction: {}/5 — {}".format(
            q.constraint_satisfaction, q.constraint_rationale
        ),
        "Preference satisfaction: {}/5 — {}".format(
            q.preference_satisfaction, q.preference_rationale
        ),
        "Overall: {}/10 — {}".format(q.overall_rating, q.rating_reason),
        "Useful clarifying questions: {} — {}".format(
            q.asked_useful_clarifying_questions, q.clarifying_notes
        ),
        "num turns: {}".format(result.metric_scores.num_turns),
    ]
    return "\n".join(lines)
