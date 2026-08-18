from playground.types import (
    Persona,
    PlaygroundConfig,
    PlaygroundTurn,
    Questionnaire,
    MetricScores,
    PlaygroundResult,
    SimulatorTurn,
)


def test_persona_roundtrip():
    p = Persona(
        id="p1",
        name="Sam",
        summary="lapsed co-op gamer",
        preferences=["co-op"],
        dislikes=["grind"],
        constraints=["PC", "limited time"],
        goal="find a co-op game",
        communication_style="casual, brief",
    )
    assert Persona.from_dict(p.to_dict()) == p


def test_simulator_turn_validates_decision():
    t = SimulatorTurn(message="hi", decision="continue", note="opening")
    assert t.decision == "continue"
    import pytest

    with pytest.raises(ValueError):
        SimulatorTurn(message="hi", decision="bogus", note="")


def test_questionnaire_clamps_and_serializes():
    q = Questionnaire(
        constraint_satisfaction=5,
        constraint_rationale="met",
        preference_satisfaction=4,
        preference_rationale="ok",
        overall_rating=8,
        rating_reason="good",
        asked_useful_clarifying_questions=True,
        clarifying_notes="asked genre",
    )
    d = q.to_dict()
    assert d["overallRating"] == 8 and d["askedUsefulClarifyingQuestions"] is True


def test_result_to_dict_has_camelcase_sections():
    cfg = PlaygroundConfig(
        domain="game",
        engine="gpt-4o-mini",
        ranker_mode="native",
        resource_mode="recai_resources",
        max_turns=8,
    )
    turn = PlaygroundTurn(
        turn_index=1,
        user_message="u",
        assistant_message="a",
        structured_exposure=[
            {"key": "items", "label": "Items", "format": "item_list", "value": [{"itemId": "6574", "title": "X"}]}
        ],
        decision="satisfied",
        duration_seconds=1.2,
    )
    res = PlaygroundResult(
        config=cfg,
        persona=Persona(
            id="p1",
            name="S",
            summary="s",
            preferences=[],
            dislikes=[],
            constraints=[],
            goal="g",
            communication_style="c",
        ),
        sut_description="desc",
        transcript=[turn],
        questionnaire=Questionnaire(3, "", 3, "", 6, "", False, ""),
        metric_scores=MetricScores(num_turns=1),
        created_at="2026-06-21T00:00:00Z",
    )
    d = res.to_dict()
    assert d["config"]["domain"] == "game"
    assert d["config"]["personaModel"] == "anthropic/claude-haiku-4-5"
    assert d["transcript"][0]["structuredExposure"][0]["value"][0]["title"] == "X"
    assert d["metricScores"]["numTurns"] == 1


def test_config_to_dict_mirrors_application_context_when_domain_missing():
    cfg = PlaygroundConfig(
        application_id="meal_planning_nutrition",
        application_context="meal_planning",
    )

    assert cfg.to_dict()["applicationContext"] == "meal_planning"
    assert cfg.to_dict()["domain"] == "meal_planning"


def test_config_persists_effective_persona_language_and_source():
    default = PlaygroundConfig()
    assert default.persona_language == "en"
    assert default.persona_language_source == "default"
    assert default.effective_language == "en"
    assert default.language_source == "default"
    assert default.to_dict()["effectiveLanguage"] == "en"
    assert default.to_dict()["languageSource"] == "default"

    cfg = PlaygroundConfig(
        persona_language="zh-Hant",
        persona_language_source="follow_ui",
    )
    assert cfg.to_dict()["effectiveLanguage"] == "zh-Hant"
    assert cfg.to_dict()["languageSource"] == "follow_ui"
    assert cfg.effective_language == "zh-Hant"
    assert cfg.language_source == "follow_ui"

    cfg.effective_language = "ja"
    cfg.language_source = "explicit"
    assert cfg.persona_language == "ja"
    assert cfg.persona_language_source == "explicit"
