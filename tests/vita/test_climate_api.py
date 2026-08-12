from __future__ import annotations

from fastapi.testclient import TestClient

from matraix.vita.api import create_app


def test_temperature_command_changes_only_its_session() -> None:
    # Given
    client = TestClient(create_app())

    # When
    first = client.post(
        "/v1/messages",
        json={"message": "Vita, đặt điều hòa 24 độ", "scenarioId": "climate"},
    )
    second = client.post(
        "/v1/messages",
        json={"message": "Vita, đặt điều hòa 21 độ", "scenarioId": "climate"},
    )

    # Then
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["decision"] == "executed"
    assert first.json()["vehicleState"]["cabinTemperatureC"] == 24
    assert second.json()["vehicleState"]["cabinTemperatureC"] == 21
    assert first.json()["sessionId"] != second.json()["sessionId"]
    assert first.json()["featureId"] == "climate_control"
    assert first.json()["capabilityIds"] == [
        "one_shot_interaction",
        "action_orchestration",
        "execution_status",
    ]
    assert first.json()["responseType"] == "status"
    assert first.json()["outcome"] == "success"
    assert first.json()["lifecycle"] == [
        "listening",
        "user_speaking",
        "thinking",
        "answering",
        "idle",
    ]
    assert first.json()["toolResult"]["tool"] == "set_cabin_temperature"
    assert first.json()["toolResult"]["status"] == "succeeded"


def test_ambiguous_temperature_command_requests_clarification() -> None:
    # Given
    client = TestClient(create_app())

    # When
    response = client.post(
        "/v1/messages",
        json={"message": "Vita ơi, trong xe lạnh quá", "scenarioId": "climate"},
    )

    # Then
    assert response.status_code == 200
    assert response.json()["decision"] == "clarification_required"
    assert response.json()["action"] is None
    assert response.json()["vehicleState"]["cabinTemperatureC"] == 22
    assert response.json()["responseType"] == "verify"
    assert response.json()["capabilityIds"] == [
        "clarification_disambiguation",
    ]
    assert response.json()["toolResult"] is None


def test_runtime_context_is_preserved_and_offline_climate_runs_on_device() -> None:
    client = TestClient(create_app())

    turn = client.post(
        "/v1/messages",
        json={
            "message": "Vita, đặt điều hòa 24 độ",
            "scenarioId": "offline-driving",
            "runtimeContext": {
                "vehicleMotion": "driving",
                "assistantMode": "normal",
                "network": "offline",
                "language": "vi",
                "audioState": "media",
                "inputModality": "voice",
            },
        },
    ).json()

    assert turn["decision"] == "executed"
    assert turn["runtimeContext"]["network"] == "offline"
    assert turn["runtimeContext"]["vehicleMotion"] == "driving"
    assert len(turn["reply"]) <= 120

    conversation = client.get(
        "/v1/conversation", params={"sessionId": turn["sessionId"]}
    ).json()
    assert conversation["turnEvidence"][-1]["context"]["network"] == "offline"
    assert conversation["turnEvidence"][-1]["stateBefore"]["cabinTemperatureC"] == 22
    assert conversation["turnEvidence"][-1]["stateAfter"]["cabinTemperatureC"] == 24


def test_conversation_exposes_state_transition_evidence() -> None:
    # Given
    client = TestClient(create_app())
    turn = client.post(
        "/v1/messages",
        json={"message": "Set cabin temperature to 23 C", "scenarioId": "climate"},
    ).json()

    # When
    response = client.get(
        "/v1/conversation",
        params={"sessionId": turn["sessionId"]},
    )

    # Then
    assert response.status_code == 200
    payload = response.json()
    assert payload["vehicleState"]["cabinTemperatureC"] == 23
    assert payload["events"][-1]["action"] == "set_cabin_temperature"
    assert payload["events"][-1]["status"] == "executed"
    assert len(payload["messages"]) == 2


def test_client_supplied_session_id_can_be_read_back() -> None:
    # Given
    client = TestClient(create_app())

    # When
    turn = client.post(
        "/v1/messages",
        json={
            "message": "Vita, đặt điều hòa 24 độ",
            "sessionId": "task-owned-session",
            "scenarioId": "climate",
        },
    )
    conversation = client.get(
        "/v1/conversation",
        params={"sessionId": "task-owned-session"},
    )

    # Then
    assert turn.json()["sessionId"] == "task-owned-session"
    assert conversation.status_code == 200
    assert conversation.json()["vehicleState"]["cabinTemperatureC"] == 24


def test_ready_reports_machine_consumable_capabilities() -> None:
    # Given
    client = TestClient(create_app())

    # When
    response = client.get("/ready")

    # Then
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert "climate_control" in response.json()["capabilities"]
