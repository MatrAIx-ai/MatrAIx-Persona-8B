from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS_ROOT = REPO_ROOT / "application" / "tasks"
VITA_TASKS = (
    "chat_vita-climate-temperature",
    "chat_vita-climate-clarification",
    "chat_vita-passenger-window-50",
    "chat_vita-trunk-driving-guardrail",
    "chat_vita-trunk-confirmation",
    "chat_vita-climate-tool-recovery",
    "chat_vita-climate-conflict-repair",
    "chat_vita-window-progressive-disclosure",
    "chat_vita-trunk-cancellation",
    "chat_vita-confirmation-context-switch",
)
VITA_PERSONAS_ROOT = REPO_ROOT / "persona" / "datasets" / "vita-driving-personas"
VITA_VN_DRIVER_ROOT = REPO_ROOT / "persona" / "datasets" / "vita-vn-driver-v1"


def test_vita_catalog_contains_distinct_logic_cases() -> None:
    # Given
    logic_case_ids: set[str] = set()

    # When
    for folder in VITA_TASKS:
        task_dir = TASKS_ROOT / folder
        task = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
        oracle = json.loads(
            (task_dir / "input" / "oracle.json").read_text(encoding="utf-8")
        )
        config = yaml.safe_load(
            (task_dir / "input" / "chatbot.yaml").read_text(encoding="utf-8")
        )
        logic_case_ids.add(oracle["logicCaseId"])

        # Then
        assert task["metadata"]["type"] == "agent"
        assert "uxagent" in task["metadata"]["tags"]
        assert task["environment"]["definition"] == "application/shared-chat-persona"
        assert config["runtimeDefaults"]["applicationId"] == "vita_climate"
        assert (
            config["protocol"]["sendMessage"]["staticBody"]["scenarioId"]
            == oracle["scenarioId"]
        )
        assert oracle["applicableEvaluators"]
        assert oracle["evaluatorWeights"]
        assert 0 < oracle["passThreshold"] <= 1
        assert oracle["requirementId"]
        assert oracle["policyReference"]
        assert oracle["toolContractVersion"]

    assert len(logic_case_ids) == len(VITA_TASKS)


def test_vita_oracles_do_not_weight_non_applicable_evaluators() -> None:
    # Given
    for folder in VITA_TASKS:
        oracle = json.loads(
            (TASKS_ROOT / folder / "input" / "oracle.json").read_text(encoding="utf-8")
        )

        # When
        applicable = set(oracle["applicableEvaluators"])
        weighted = set(oracle["evaluatorWeights"])

        # Then
        assert weighted <= applicable
        assert abs(sum(oracle["evaluatorWeights"].values()) - 1.0) < 0.0001


def test_vita_driving_personas_and_tasks_use_vietnamese_locale() -> None:
    # Given
    persona_paths = sorted(VITA_PERSONAS_ROOT.glob("persona_vita-driving-*.yaml"))

    # When
    persona_dimensions = [
        yaml.safe_load(path.read_text(encoding="utf-8"))["dimensions"]
        for path in persona_paths
    ]
    runtime_contexts = [
        yaml.safe_load(
            (TASKS_ROOT / folder / "input" / "chatbot.yaml").read_text(encoding="utf-8")
        )["protocol"]["sendMessage"]["staticBody"]["runtimeContext"]
        for folder in VITA_TASKS
    ]
    dimension_catalog = json.loads(
        (REPO_ROOT / "persona" / "schema" / "dimensions.json").read_text(
            encoding="utf-8"
        )
    )
    primary_language = next(
        item
        for item in dimension_catalog["dimensions"]
        if item["id"] == "primary_language"
    )

    # Then
    assert len(persona_dimensions) == 18
    assert "Vietnamese" in primary_language["values"]
    assert all(item["primary_language"] == "Vietnamese" for item in persona_dimensions)
    assert all(item["lang_vietnamese"] == "Native" for item in persona_dimensions)
    assert all(item["language"] == "vi" for item in runtime_contexts)


def test_vita_persona_interaction_strategies_are_mece() -> None:
    # Given
    expected = {
        "direct_command",
        "progressive_disclosure",
        "verify_then_accept",
        "challenge_and_repair",
        "safety_first",
        "accessibility_led",
    }

    # When
    personas = [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(VITA_PERSONAS_ROOT.glob("persona_vita-driving-*.yaml"))
    ]
    strategies = [persona["dimensions"]["interaction_strategy"] for persona in personas]
    behavioral_prompts = [persona["system_prompt"] for persona in personas]

    # Then
    assert set(strategies) == expected
    assert all(strategies.count(strategy) == 3 for strategy in expected)
    assert len(set(behavioral_prompts)) == 18


def test_vita_tasks_collect_mece_persona_verdicts() -> None:
    # Given
    expected_verdicts = {"endorse", "conditional", "reject", "inconclusive"}

    # When
    schemas = [
        yaml.safe_load(
            (TASKS_ROOT / folder / "input" / "self_report_schema.yaml").read_text(
                encoding="utf-8"
            )
        )
        for folder in VITA_TASKS
    ]

    # Then
    for schema in schemas:
        fields = {field["key"]: field for field in schema["fields"]}
        assert set(fields["personaVerdict"]["choices"]) == expected_verdicts
        explanation = fields["personaVerdict"]["explanation"]
        assert explanation["key"] == "verdictReason"
        assert explanation["explains"] == "personaVerdict"
        assert set(fields["trustDelta"]["choices"]) == {
            "increased",
            "unchanged",
            "decreased",
        }


def test_vita_vn_driver_v1_is_a_balanced_72_persona_benchmark() -> None:
    persona_paths = sorted(VITA_VN_DRIVER_ROOT.glob("persona_vita-vn-*.yaml"))
    personas = [
        yaml.safe_load(path.read_text(encoding="utf-8")) for path in persona_paths
    ]

    assert len(personas) == 72
    assert len({persona["persona_id"] for persona in personas}) == 72

    missions = {persona["dimensions"]["operating_mission"] for persona in personas}
    assert len(missions) == 12
    for mission in missions:
        mission_personas = [
            persona
            for persona in personas
            if persona["dimensions"]["operating_mission"] == mission
        ]
        assert len(mission_personas) == 6
        assert {
            persona["dimensions"]["speech_region_group"]
            for persona in mission_personas
        } == {"north", "central", "south"}
        assert {
            persona["dimensions"]["behavior_variant"]
            for persona in mission_personas
        } == {"baseline", "challenge"}
        assert len({persona["display_name"] for persona in mission_personas}) == 1
        assert len({persona["avatar_url"] for persona in mission_personas}) == 1
        assert len({persona["dimensions"]["gender_identity"] for persona in mission_personas}) == 1

    assert len({persona["display_name"] for persona in personas}) == 12
    assert len({persona["avatar_url"] for persona in personas}) == 12
    assert all(persona["avatar_url"].startswith("/persona-avatars/vita-vn-") for persona in personas)

    forbidden_prompt_terms = {"endorse", "conditional", "reject", "inconclusive"}
    assert all(
        not forbidden_prompt_terms.intersection(persona["system_prompt"].lower().split())
        for persona in personas
    )
    assert all(persona["dimensions"]["primary_language"] == "Vietnamese" for persona in personas)
    assert all(persona["provenance"]["taxonomy_version"] == "vita-vn-driver-v1" for persona in personas)


def test_vita_tasks_default_to_one_persona_per_vietnamese_driver_mission() -> None:
    expected_missions = {
        "A1_SOLO_ROUTINE_COMMUTE",
        "A2_FAMILY_CARE_LOGISTICS",
        "A3_INTERCITY_RANGE_TRAVEL",
        "A4_MOBILE_WORK_LOCAL_OPERATIONS",
        "B1_REGULAR_CO_DRIVER",
        "B2_OCCASIONAL_HOUSEHOLD_DRIVER",
        "C1_URBAN_ON_DEMAND_SERVICE",
        "C2_SCHEDULED_INTERCITY_SERVICE",
        "D1_EXECUTIVE_CORPORATE_CHAUFFEUR",
        "D2_FIELD_SERVICE_LOGISTICS_FLEET",
        "E1_BORROWED_RENTAL_TEST_DRIVE",
        "E2_VALET_SERVICE_DEALER",
    }

    for folder in VITA_TASKS:
        strategy = json.loads(
            (TASKS_ROOT / folder / "persona_strategy.json").read_text(encoding="utf-8")
        )
        assert strategy["pool"] == "persona/datasets/vita-vn-driver-v1"
        assert strategy["sources"] == ["synthetic_vita_vn_driver_v1"]
        assert strategy["defaultMode"] == "stratified"
        assert strategy["sampleSize"] == 12
        assert "sampleSizePerValueGroup" not in strategy
        assert strategy["stratifyFields"] == ["operating_mission"]
        assert set(strategy["dimensionFilters"]["operating_mission"]) == expected_missions
