from __future__ import annotations

import json

from playground.scoring import (
    OriginalPromptFeedbackScorer,
    _config_from_dict,
    score_harbor_artifacts,
)
from playground.types import Persona, PlaygroundConfig


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def complete_json(self, system: str, user: str):
        self.calls.append({"system": system, "user": user})
        return {
            "needConstraintSatisfaction": "yes",
            "personalPreferenceSatisfaction": "yes",
            "overallExperienceRating": 8,
            "reason": "The conversation adapted after feedback.",
            "askedUsefulClarificationQuestions": True,
            "clarifyingNotes": "The application asked about tone.",
        }


def test_original_prompt_feedback_scorer_reuses_canonical_feedback_prompt():
    fake_client = FakeClient()
    scorer = OriginalPromptFeedbackScorer(client_factory=lambda _model: fake_client)

    questionnaire = scorer(
        persona=Persona(
            id="p1",
            name="Persona One",
            context="Name: Persona One\nHow you talk: concise and skeptical",
        ),
        sut_description="Movie recommender.",
        config=PlaygroundConfig(domain="movie", engine="gpt-4o-mini"),
        turn_views=[
            {
                "turnId": "0",
                "userMessage": "I want a quiet film.",
                "assistantMessage": "What tone do you prefer?",
                "recommendedItems": [],
            },
            {
                "turnId": "1",
                "userMessage": "Atmospheric and reflective.",
                "assistantMessage": "Try Movie A.",
                "recommendedItems": [{"itemId": "42", "title": "Movie A"}],
            },
        ],
    )

    assert questionnaire.to_dict()["overallRating"] == 8
    assert questionnaire.to_dict()["constraintSatisfaction"] == 5
    assert questionnaire.to_dict()["preferenceSatisfaction"] == 5
    assert len(fake_client.calls) == 1
    call = fake_client.calls[0]
    assert "Return one JSON object with these fields" in call["user"]
    assert "you: I want a quiet film." in call["user"]
    assert "RecAI: Try Movie A." in call["user"]
    assert "Recommended items" not in call["user"]
    assert "Name: Persona One" in call["system"]


def test_scoring_deserializes_and_uses_effective_persona_language():
    config = _config_from_dict(
        {
            "domain": "movie",
            "engine": "gpt-4o-mini",
            "effectiveLanguage": "zh-Hans",
            "languageSource": "follow_ui",
        }
    )
    assert config.persona_language == "zh-Hans"
    assert config.persona_language_source == "follow_ui"

    fake_client = FakeClient()
    OriginalPromptFeedbackScorer(
        client_factory=lambda _model: fake_client
    )(
        persona=Persona(id="p1", name="Persona One", context="A careful user."),
        sut_description="A movie recommender.",
        config=config,
        turn_views=[],
    )

    assert "Effective persona language: Simplified Chinese (zh-Hans)." in (
        fake_client.calls[0]["system"]
    )


def test_score_harbor_artifacts_writes_original_questionnaire(tmp_path):
    fake_client = FakeClient()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "transcript.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "domain": "movie",
                "turns": [
                    {
                        "turnId": "0",
                        "userMessage": "I want a quiet film.",
                        "assistantMessage": "What tone do you prefer?",
                        "recommendedItems": [],
                    },
                    {
                        "turnId": "1",
                        "userMessage": "Atmospheric and reflective.",
                        "assistantMessage": "Try Movie A.",
                        "recommendedItems": [{"itemId": "42", "title": "Movie A"}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "application_result.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "domain": "movie",
                "recommendedItems": [{"itemId": "42", "title": "Movie A"}],
                "turnsToResult": 2,
            }
        ),
        encoding="utf-8",
    )

    feedback = score_harbor_artifacts(
        transcript_path=output_dir / "transcript.json",
        application_path=output_dir / "application_result.json",
        output_path=output_dir / "user_feedback.json",
        persona=Persona(
            id="p1",
            name="Persona One",
            context="Name: Persona One\nHow you talk: concise and skeptical",
        ),
        sut_description="Movie recommender.",
        config=PlaygroundConfig(domain="movie", engine="gpt-4o-mini"),
        client_factory=lambda _model: fake_client,
    )

    written = json.loads(
        (output_dir / "user_feedback.json").read_text(encoding="utf-8")
    )
    assert written == feedback
    assert written["overallExperienceRating"] == 8
    assert written["needConstraintSatisfaction"] == "yes"
    assert written["personalPreferenceSatisfaction"] == "yes"
    assert "RecAI: Try Movie A." in fake_client.calls[0]["user"]
    assert "Recommended items" not in fake_client.calls[0]["user"]


def test_score_harbor_artifacts_accepts_application_result_path(tmp_path):
    fake_client = FakeClient()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "transcript.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "applicationId": "finance_openbb",
                "applicationContext": "financial_research",
                "domain": "financial_research",
                "turns": [
                    {
                        "turnId": "0",
                        "userMessage": "Compare conservative ETFs.",
                        "assistantMessage": "I used OpenBB data for VTI.",
                        "recommendedItems": [
                            {"itemId": "finance:ETF:VTI", "title": "VTI"}
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "application_result.json").write_text(
        json.dumps(
            {
                "sessionId": "ses_123",
                "applicationId": "finance_openbb",
                "applicationContext": "financial_research",
                "domain": "financial_research",
                "recommendedItems": [{"itemId": "finance:ETF:VTI", "title": "VTI"}],
                "turnsToResult": 1,
            }
        ),
        encoding="utf-8",
    )

    feedback = score_harbor_artifacts(
        transcript_path=output_dir / "transcript.json",
        application_path=output_dir / "application_result.json",
        output_path=output_dir / "user_feedback.json",
        persona=Persona(id="p1", name="Persona One", context="Careful investor."),
        sut_description="Financial research chatbot.",
        config=PlaygroundConfig(
            domain="financial_research",
            application_id="finance_openbb",
            application_context="financial_research",
            engine="gpt-4o-mini",
        ),
        client_factory=lambda _model: fake_client,
    )

    assert feedback["overallExperienceRating"] == 8
    assert "FinAI / OpenBB: I used OpenBB data for VTI." in fake_client.calls[0]["user"]
    assert "recommended items" not in fake_client.calls[0]["user"].lower()
