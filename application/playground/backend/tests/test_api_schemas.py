import pytest
from pydantic import ValidationError

from backend.api.schemas import HarborJobLaunchRequest


def test_harbor_job_launch_request_prefers_chat_application_context():
    request = HarborJobLaunchRequest(
        taskPath="application/tasks/chat_meal-planning-nutrition",
        chatApplicationId="meal_planning_nutrition",
        chatApplicationContext="meal_planning",
    )

    assert request.chatApplicationContext == "meal_planning"
    assert request.chatDomain is None


def test_harbor_job_launch_request_defaults_chat_context():
    request = HarborJobLaunchRequest(
        taskPath="application/tasks/chat_openbb-corporate-action-honesty",
        chatApplicationId="finance_openbb",
    )

    assert request.chatApplicationContext == "financial_research"
    assert request.chatDomain is None


@pytest.mark.parametrize(
    ("language", "language_source", "expected_language", "expected_source"),
    [
        ("en", None, "en", "explicit"),
        ("zh-CN", "follow_ui", "zh-Hans", "follow_ui"),
        ("ZH-hant", "follow_ui", "zh-Hant", "follow_ui"),
        ("ja-JP", "explicit", "ja", "explicit"),
        ("pt", None, "pt-BR", "explicit"),
    ],
)
def test_harbor_job_launch_request_accepts_and_normalizes_language(
    language: str,
    language_source: str | None,
    expected_language: str,
    expected_source: str,
):
    request = HarborJobLaunchRequest(
        taskPath="application/tasks/chat_recai",
        language=language,
        languageSource=language_source,
    )

    assert request.language == expected_language
    assert request.languageSource == expected_source


@pytest.mark.parametrize("source", ["ui", "env", "default", "cli"])
def test_harbor_job_launch_request_rejects_non_client_sources(source: str):
    with pytest.raises(ValidationError, match="languageSource"):
        HarborJobLaunchRequest(
            taskPath="application/tasks/chat_recai",
            language="en",
            languageSource=source,
        )


def test_harbor_job_launch_request_rejects_source_without_language():
    with pytest.raises(ValidationError, match="languageSource"):
        HarborJobLaunchRequest(
            taskPath="application/tasks/chat_recai",
            languageSource="follow_ui",
        )


def test_harbor_job_launch_request_defaults_language_fields_to_null():
    request = HarborJobLaunchRequest(taskPath="application/tasks/chat_recai")

    assert request.language is None
    assert request.languageSource is None
