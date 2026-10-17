from __future__ import annotations

import pytest

from playground.user_sim.self_report_contract import (
    DEFAULT_CHATBOT_SELF_REPORT_SCHEMA,
    coerce_self_report_payload,
)


def _coerce(**raw):
    return coerce_self_report_payload(raw, DEFAULT_CHATBOT_SELF_REPORT_SCHEMA)


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("no", "no"),
        ("No.", "no"),
        ("No - it ignored my budget", "no"),
        ("Partially, it missed my budget", "partially"),
        ("  YES!  ", "yes"),
        (False, "no"),
        ("false", "no"),
        (True, "yes"),
    ],
)
def test_enum_answers_keep_their_meaning(answer, expected):
    assert _coerce(needConstraintSatisfaction=answer)["needConstraintSatisfaction"] == expected


def test_enum_prefix_needs_a_word_boundary():
    # "nothing" must not be read as "no", and "not really" isn't a listed choice.
    payload = _coerce(needConstraintSatisfaction="nothing worked")
    assert payload["needConstraintSatisfaction"] == "yes"  # unchanged fallback for unparseable


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (8, 8),
        ("8", 8),
        ("8/10", 8),
        ("8 / 10", 8),
        ("3 out of 10", 3),
        ("Rating: 7", 7),
        (12, 10),
    ],
)
def test_rating_answers_parse_scores(answer, expected):
    assert _coerce(overallExperienceRating=answer)["overallExperienceRating"] == expected


@pytest.mark.parametrize("answer", ["nan", "inf", "between 6 and 8"])
def test_unparseable_rating_keeps_existing_fallback(answer):
    assert _coerce(overallExperienceRating=answer)["overallExperienceRating"] == 1


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("Yes.", True), ("yes, they did", True), ("No.", False), ("true", True), (0, False)],
)
def test_boolean_answers_read_leading_word(answer, expected):
    payload = _coerce(askedUsefulClarificationQuestions=answer)
    assert payload["askedUsefulClarificationQuestions"] is expected
