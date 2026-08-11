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
    ("language", "language_source"),
    [
        ("en", "explicit"),
        ("en", "follow_ui"),
        ("zh", "explicit"),
        ("zh", "follow_ui"),
    ],
)
def test_harbor_job_launch_request_accepts_language_source_pairs(
    language: str, language_source: str
):
    request = HarborJobLaunchRequest(
        taskPath="application/tasks/chat_recai",
        language=language,
        languageSource=language_source,
    )

    assert request.language == language
    assert request.languageSource == language_source


@pytest.mark.parametrize(
    "payload",
    [
        {"language": "en"},
        {"languageSource": "explicit"},
    ],
)
def test_harbor_job_launch_request_requires_language_fields_as_a_pair(payload):
    with pytest.raises(ValidationError, match="languageSource|language must be null"):
        HarborJobLaunchRequest(
            taskPath="application/tasks/chat_recai",
            **payload,
        )


def test_harbor_job_launch_request_rejects_client_language_source_env():
    with pytest.raises(ValidationError, match="languageSource must be follow_ui, explicit, or null"):
        HarborJobLaunchRequest(
            taskPath="application/tasks/chat_recai",
            language="en",
            languageSource="env",
        )


def test_harbor_job_launch_request_defaults_language_fields_to_null():
    request = HarborJobLaunchRequest(taskPath="application/tasks/chat_recai")

    assert request.language is None
    assert request.languageSource is None


def test_harbor_job_launch_request_accepts_explicit_null_language_fields():
    request = HarborJobLaunchRequest(
        taskPath="application/tasks/chat_recai",
        language=None,
        languageSource=None,
    )

    assert request.language is None
    assert request.languageSource is None
