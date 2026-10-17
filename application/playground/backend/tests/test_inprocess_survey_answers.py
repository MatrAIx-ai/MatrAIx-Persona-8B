"""How the in-process survey runner turns model answers into recorded values."""

from __future__ import annotations

import pytest

from backend.service.survey_types import SurveyEvalConfig, SurveyInstrument, SurveyQuestion
from backend.tests.test_inprocess_eval_runners import FakeJSONClient, _persona, _persona_yaml
from playground.inprocess.survey_eval import InprocessSurveyEvalRunner


def _instrument(*, plan_required: bool = True) -> SurveyInstrument:
    return SurveyInstrument(
        id="nps_survey",
        title="Survey",
        description="Recommend and plan questions.",
        ask_rationale=True,
        questions=[
            SurveyQuestion(id="nps", prompt="How likely to recommend?", min_value=0, max_value=10),
            SurveyQuestion.from_dict(
                {
                    "id": "plan",
                    "prompt": "Your plan?",
                    "type": "single_choice",
                    "required": plan_required,
                    "options": [
                        {"id": "wont_pay", "label": "Keep using free"},
                        {"id": "pay_when_roi", "label": "Upgrade once it pays off"},
                    ],
                }
            ),
        ],
    )


def _run(tmp_path, monkeypatch, payload, *, instrument=None):
    monkeypatch.setattr(
        "playground.inprocess.survey_eval.build_json_client",
        lambda model: FakeJSONClient(payload),
    )
    result = InprocessSurveyEvalRunner()(
        _persona(),
        instrument or _instrument(),
        SurveyEvalConfig(persona_model="openai/gpt-4o-mini"),
        created_at="2026-06-26T00:00:00Z",
        persona_yaml_path=_persona_yaml(tmp_path),
    )
    answers = {answer.question_id: answer for answer in result.answers}
    return answers, result.trajectory[-1].outcome


@pytest.mark.parametrize("score", [0, 10])
def test_zero_based_likert_keeps_endpoints(tmp_path, monkeypatch, score):
    answers, done = _run(
        tmp_path,
        monkeypatch,
        {"answers": [{"questionId": "nps", "value": score}, {"questionId": "plan", "value": "wont_pay"}]},
    )
    assert answers["nps"].value == score
    assert done["valid"] is True


@pytest.mark.parametrize(
    "raw",
    ["pay_when_roi", "pay_when_roi\n", "  PAY_WHEN_ROI ", "Upgrade once it pays off", "upgrade once it pays off"],
)
def test_choice_answer_matches_id_or_label(tmp_path, monkeypatch, raw):
    answers, done = _run(
        tmp_path,
        monkeypatch,
        {"answers": [{"questionId": "nps", "value": 8}, {"questionId": "plan", "value": raw, "rationale": "Pays off."}]},
    )
    assert answers["plan"].value == "pay_when_roi"
    assert answers["plan"].rationale == "Pays off."
    assert done["missingRequiredQuestionIds"] == []


def test_unknown_choice_is_not_recorded_as_first_option(tmp_path, monkeypatch):
    answers, done = _run(
        tmp_path,
        monkeypatch,
        {
            "answers": [
                {"questionId": "nps", "value": 8},
                {"questionId": "plan", "value": "Pro annual", "rationale": "I'd go straight to Pro."},
            ]
        },
    )
    # Back-filled as unanswered: the persona's rationale is not attached to it.
    assert answers["plan"].rationale != "I'd go straight to Pro."
    assert done["missingRequiredQuestionIds"] == ["plan"]
    assert done["valid"] is False


def test_unparseable_likert_is_flagged_and_uses_scale_midpoint(tmp_path, monkeypatch):
    answers, done = _run(
        tmp_path,
        monkeypatch,
        {"answers": [{"questionId": "nps", "value": "very likely"}, {"questionId": "plan", "value": "wont_pay"}]},
    )
    assert answers["nps"].value == 5
    assert done["missingRequiredQuestionIds"] == ["nps"]
    assert done["valid"] is False


def test_empty_reply_is_not_a_valid_survey(tmp_path, monkeypatch):
    _answers, done = _run(tmp_path, monkeypatch, {})
    assert done["missingRequiredQuestionIds"] == ["nps", "plan"]
    assert done["valid"] is False


def test_unknown_optional_choice_is_dropped(tmp_path, monkeypatch):
    answers, done = _run(
        tmp_path,
        monkeypatch,
        {"answers": [{"questionId": "nps", "value": 7}, {"questionId": "plan", "value": "something else"}]},
        instrument=_instrument(plan_required=False),
    )
    assert "plan" not in answers
    assert done["valid"] is True
