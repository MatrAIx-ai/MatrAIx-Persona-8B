"""Tests for Harbor trial → Playground debrief mapping."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from backend.service.harbor_trial_debrief import map_trial_debrief


def _write_chat_trial(repo: Path, job_name: str, trial_name: str) -> None:
    persona_path = repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0042.yaml"
    persona_path.parent.mkdir(parents=True, exist_ok=True)
    persona_path.write_text(
        "persona_id: '0042'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    trial_dir = repo / "jobs" / job_name / trial_name
    output = trial_dir / "artifacts" / "app" / "output"
    output.mkdir(parents=True)
    (output / "transcript.json").write_text(
        json.dumps(
            {
                "domain": "movie",
                "turns": [
                    {
                        "userMessage": "Hi",
                        "assistantMessage": "Hello",
                        "recommendedItems": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (output / "application_result.json").write_text(
        json.dumps({"recommendedItems": [], "turnsToResult": 1}),
        encoding="utf-8",
    )
    (output / "user_feedback.json").write_text(
        json.dumps({"overallExperienceRating": 7, "reason": "Okay."}),
        encoding="utf-8",
    )
    (trial_dir / "result.json").write_text(
        json.dumps(
            {
                "config": {
                    "agent": {
                        "kwargs": {
                            "persona_path": "persona/datasets/matraix-persona-dev-sample/persona_0042.yaml",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _write_example_survey_task(repo: Path) -> None:
    task_dir = repo / "application" / "tasks" / "example-survey_product-feedback"
    input_dir = task_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.toml").write_text('[metadata]\ntype = "survey"\n', encoding="utf-8")
    (input_dir / "questionnaire.yaml").write_text(
        "\n".join(
            [
                'schemaVersion: "1.0"',
                "id: product_feedback_v1",
                "title: Survey Product Feedback",
                "questions:",
                "  - id: q0",
                "    prompt: After trying the free version, your realistic plan is...",
                "    type: single_choice",
                "    construct: default_pay_intent",
                "    required: true",
                "    options:",
                "      - id: q0_pay_when_roi_clear",
                "        label: Upgrade when ROI is clear",
                "  - id: q1",
                "    prompt: Plus vs Pro...",
                "    type: single_choice",
                "    construct: tier_receptivity",
                "    required: true",
                "    options:",
                "      - id: q1_happy_plus_or_pro",
                "        label: Happy with Plus or Pro",
                "  - id: q2",
                "    prompt: Annual vs monthly billing...",
                "    type: single_choice",
                "    construct: prepay_willingness",
                "    required: true",
                "    options:",
                "      - id: q2_billing_no_preference",
                "        label: No billing preference",
                "  - id: q3",
                "    prompt: A limited $1 first-month Plus promo...",
                "    type: single_choice",
                "    construct: promo_reaction",
                "    required: true",
                "    options:",
                "      - id: q3_grab_dollar_promo",
                "        label: Grab the dollar promo",
                "  - id: q4",
                "    prompt: A friend uses a paid organizer app...",
                "    type: single_choice",
                "    construct: switch_behavior",
                "    required: true",
                "    options:",
                "      - id: q4_compare_pay_if_wins",
                "        label: Compare and pay if it wins",
                "  - id: q5",
                "    prompt: Ads on free vs paying to remove them...",
                "    type: single_choice",
                "    construct: ads_tradeoff",
                "    required: true",
                "    options:",
                "      - id: q5_ads_pay_if_plus_useful",
                "        label: Pay if Plus is useful",
                "  - id: q6",
                "    prompt: Overall, the product pricing feels...",
                "    type: single_choice",
                "    construct: price_stance",
                "    required: true",
                "    options:",
                "      - id: q6_fair_if_use_justifies",
                "        label: Fair if use justifies it",
                "  - id: overall_interest",
                "    prompt: Overall interest in this product.",
                "    type: likert",
                "    construct: overall_interest",
                "    required: true",
                "    minValue: 1",
                "    maxValue: 5",
                "  - id: would_try_beta",
                "    prompt: Would you try a beta version?",
                "    type: single_choice",
                "    construct: beta_intent",
                "    required: true",
                "    options:",
                '      - id: "true"',
                "        label: Yes",
                '      - id: "false"',
                "        label: No",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (task_dir / "instruction.md").write_text(
        "\n".join(
            [
                "# Survey Product Feedback",
                "",
                "Answer this product-concept survey.",
                "",
                "You are reacting to FocusLoop. Use the task context, then complete",
                "every required question in the questionnaire.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (input_dir / "context.md").write_text(
        "# FocusLoop\n\nFamily coordination app concept brief.\n",
        encoding="utf-8",
    )


def test_map_trial_debrief_chatbot_enriches_prompts_from_events(tmp_path: Path) -> None:
    repo = tmp_path
    task_dir = repo / "application" / "tasks" / "chat_meal-planning-nutrition"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text('[metadata]\ntype = "chat"\n', encoding="utf-8")
    (task_dir / "instruction.md").write_text("# Task instruction\nUse the chat API.\n", encoding="utf-8")
    _write_chat_trial(repo, "job-prompts", "trial-prompts")
    (
        repo
        / "persona"
        / "datasets"
        / "matraix-persona-dev-sample"
        / "persona_0042.yaml"
    ).write_text(
        "\n".join(
            [
                "persona_id: '0042'",
                "version: '1.0'",
                "display_name: Casey Brooks",
                "summary: A careful shopper with a detailed profile.",
                "system_prompt: Prefer practical choices and explain tradeoffs.",
                "dimensions: {}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    trial_dir = repo / "jobs" / "job-prompts" / "trial-prompts"
    (trial_dir / "config.json").write_text(
        json.dumps({"task": {"path": "application/tasks/chat_meal-planning-nutrition"}}),
        encoding="utf-8",
    )
    (trial_dir / "persona_meta.json").write_text(
        json.dumps({"effective_language": "zh", "language_source": "explicit"}),
        encoding="utf-8",
    )
    prompts = {
        "personaPrompt": "Actual runtime persona prompt from events.\nThis exact artifact must be preserved.",
        "harborPrompt": "You are Casey Brooks.\n\n## Who you are\n\nA detailed biography.\n\n## Task instruction\nJudge the chatbot honestly.\n\n## Task context\nThis chatbot helps people discover movies.",
        "taskPrompt": "## Task instruction\nJudge the chatbot honestly.\n\n## Application kickoff\nReveal needs gradually.",
    }
    (trial_dir / "events.jsonl").write_text(
        json.dumps({"type": "prompts", "prompts": prompts}) + "\n",
        encoding="utf-8",
    )
    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name="job-prompts",
        trial_name="trial-prompts",
    )
    assert debrief["prompts"]["personaPrompt"] == prompts["personaPrompt"]
    assert "Task context" in debrief["prompts"]["harborPrompt"]
    assert "Task instruction" in debrief["prompts"]["taskPrompt"]
    assert debrief["instructionMarkdown"].startswith("# Task instruction")


@pytest.mark.parametrize(
    ("language", "summary_heading", "guidance_heading"),
    [
        ("zh", "## 个人简介", "## 行为准则"),
        ("zh-Hant", "## 個人簡介", "## 行為準則"),
    ],
)
def test_map_trial_debrief_rebuilds_missing_persona_prompt_in_recorded_language(
    tmp_path: Path,
    language: str,
    summary_heading: str,
    guidance_heading: str,
) -> None:
    repo = tmp_path
    task_dir = repo / "application" / "tasks" / "chat_recai"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text('[metadata]\ntype = "chat"\n', encoding="utf-8")
    (task_dir / "instruction.md").write_text(
        "# Task instruction\nUse the chat API.\n", encoding="utf-8"
    )
    _write_chat_trial(repo, "job-zh-prompt", "trial-zh-prompt")
    (
        repo
        / "persona"
        / "datasets"
        / "matraix-persona-dev-sample"
        / "persona_0042.yaml"
    ).write_text(
        "\n".join(
            [
                "persona_id: '0042'",
                "version: '1.0'",
                "display_name: Casey Brooks",
                "summary: A careful shopper with a detailed profile.",
                "system_prompt: Prefer practical choices and explain tradeoffs.",
                "dimensions: {}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    trial_dir = repo / "jobs" / "job-zh-prompt" / "trial-zh-prompt"
    (trial_dir / "persona_meta.json").write_text(
        json.dumps({"effective_language": language, "language_source": "explicit"}),
        encoding="utf-8",
    )
    (trial_dir / "events.jsonl").write_text(
        json.dumps(
            {
                "type": "prompts",
                "prompts": {
                    "taskPrompt": "Original task prompt must remain unchanged.",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name="job-zh-prompt",
        trial_name="trial-zh-prompt",
    )

    persona_prompt = debrief["prompts"]["personaPrompt"]
    assert "你是 Casey Brooks。" in persona_prompt
    assert summary_heading in persona_prompt
    assert guidance_heading in persona_prompt
    assert (
        "Original task prompt must remain unchanged."
        in debrief["prompts"]["taskPrompt"]
    )


def test_map_trial_debrief_survey_from_events_without_output_dir(tmp_path: Path) -> None:
    repo = tmp_path
    task_dir = repo / "application" / "tasks" / "example-survey_product-feedback"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text('[metadata]\ntype = "survey"\n', encoding="utf-8")
    (task_dir / "input").mkdir()
    (task_dir / "input" / "questionnaire.yaml").write_text(
        "schemaVersion: '1.0'\nid: product_feedback_v1\ntitle: Survey\nquestions: []\n",
        encoding="utf-8",
    )
    trial_dir = repo / "jobs" / "job-survey-events" / "trial-a"
    trial_dir.mkdir(parents=True)
    (trial_dir / "config.json").write_text(
        json.dumps({"task": {"path": "application/tasks/example-survey_product-feedback"}}),
        encoding="utf-8",
    )
    (trial_dir / "result.json").write_text(
        json.dumps({"finished_at": "2026-07-02T08:00:00Z", "exception_info": None}),
        encoding="utf-8",
    )
    done_result = {
        "instrument": {"id": "product_feedback_v1", "title": "Survey Product Feedback"},
        "answers": [
            {"questionId": "q0", "value": "q0_pay_when_roi_clear", "rationale": "ok"},
        ],
        "metrics": {"numQuestions": 1, "numAnswered": 1},
    }
    (trial_dir / "events.jsonl").write_text(
        json.dumps({"type": "done", "result": done_result}) + "\n",
        encoding="utf-8",
    )
    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name="job-survey-events",
        trial_name="trial-a",
    )
    assert debrief["applicationType"] == "survey"
    assert debrief["surveyResult"]["answers"][0]["questionId"] == "q0"


def test_map_trial_debrief_chatbot(tmp_path: Path) -> None:
    repo = tmp_path
    _write_chat_trial(repo, "job-1", "trial-0")
    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name="job-1",
        trial_name="trial-0",
    )
    assert debrief["applicationType"] == "chatbot"
    assert debrief["transcript"][0]["assistantMessage"] == "Hello"
    assert debrief["harbor"]["trialName"] == "trial-0"


def test_map_trial_debrief_attaches_task_self_report_schema(tmp_path: Path) -> None:
    repo = tmp_path
    _write_chat_trial(repo, "job-schema", "trial-schema")
    task_dir = repo / "application" / "tasks" / "chat_meal-planning-nutrition"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.toml").write_text('[metadata]\ntype = "chat"\n', encoding="utf-8")
    input_dir = task_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "self_report_schema.yaml").write_text(
        "\n".join(
            [
                "artifactName: user_feedback.json",
                "instructions: Judge each ticker.",
                "fields:",
                "  - key: hcpDelistingHandled",
                "    prompt: Satisfied with HCP?",
                "    kind: enum",
                "    choices: [yes, partially, no]",
                "  - key: overallExperienceRating",
                "    prompt: Overall rating",
                "    kind: integer",
                "    minimum: 1",
                "    maximum: 10",
                "    explanation:",
                "      key: reason",
                "      prompt: Why?",
            ]
        ),
        encoding="utf-8",
    )
    trial_dir = repo / "jobs" / "job-schema" / "trial-schema"
    (trial_dir / "config.json").write_text(
        json.dumps({"task": {"path": "application/tasks/chat_meal-planning-nutrition"}}),
        encoding="utf-8",
    )
    (trial_dir / "artifacts" / "app" / "output" / "user_feedback.json").write_text(
        json.dumps(
            {
                "hcpDelistingHandled": "no",
                "overallExperienceRating": 3,
                "reason": "HCP failed.",
            }
        ),
        encoding="utf-8",
    )
    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name="job-schema",
        trial_name="trial-schema",
    )
    schema = debrief["selfReportSchema"]
    assert schema["fields"][0]["key"] == "hcpDelistingHandled"
    assert debrief["userFeedback"]["hcpDelistingHandled"] == "no"
    assert debrief["questionnaire"]["overallRating"] == 3
    assert debrief["questionnaire"]["preferenceSatisfaction"] == 0


def test_map_trial_debrief_includes_verifier(tmp_path: Path) -> None:
    repo = tmp_path
    _write_chat_trial(repo, "job-v", "trial-v")
    trial_dir = repo / "jobs" / "job-v" / "trial-v"
    (trial_dir / "reward.txt").write_text("1.0\n", encoding="utf-8")
    verifier_dir = trial_dir / "verifier"
    verifier_dir.mkdir()
    (verifier_dir / "test-stdout.txt").write_text("all checks passed\n", encoding="utf-8")
    (verifier_dir / "structured_output.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "artifactType": "matraix.trial_evaluation",
                "taskType": "chatbot",
                "contexts": [
                    {
                        "key": "task_outcome.primary",
                        "label": "Task outcome",
                        "contextType": "task_outcome",
                        "facets": [
                            {
                                "key": "outcome_status",
                                "label": "Outcome status",
                                "role": "primary",
                                "kind": "categorical",
                                "value": "resolved",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name="job-v",
        trial_name="trial-v",
    )
    assert debrief["verifier"]["passed"] is True
    assert debrief["verifier"]["reward"] == 1.0
    assert "checks passed" in debrief["verifier"]["detail"]
    assert debrief["trialEvaluation"]["contexts"][0]["contextType"] == "task_outcome"


def test_map_trial_debrief_survey_responses(tmp_path: Path) -> None:
    repo = tmp_path
    _write_example_survey_task(repo)
    trial_dir = repo / "jobs" / "job-2" / "trial-a"
    output = trial_dir / "artifacts" / "app" / "output"
    output.mkdir(parents=True)
    (trial_dir / "config.json").write_text(
        json.dumps({"task": {"path": "application/tasks/example-survey_product-feedback"}}),
        encoding="utf-8",
    )
    (output / "survey_responses.json").write_text(
        json.dumps(
            {
                "responses": [
                    {"question_id": "q0", "choice_id": "q0_pay_when_roi_clear"},
                    {"question_id": "overall_interest", "value": 4},
                ]
            }
        ),
        encoding="utf-8",
    )
    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name="job-2",
        trial_name="trial-a",
    )
    assert debrief["applicationType"] == "survey"
    assert debrief["instructionMarkdown"].startswith("# Survey Product Feedback")
    assert "/app/output/survey_result.json" not in debrief["instructionMarkdown"]
    assert "## Questionnaire" not in debrief["instructionMarkdown"]
    assert debrief["surveyResult"]["answers"][0]["questionId"] == "q0"
    assert debrief["surveyResult"]["completion"]["meanLikert"] == 4.0


def test_map_trial_debrief_survey_enriches_persona_dimensions(tmp_path: Path) -> None:
    repo = tmp_path
    persona_dir = repo / "persona" / "datasets" / "matraix-persona-dev-sample"
    persona_dir.mkdir(parents=True)
    (persona_dir / "persona_0174.yaml").write_text(
        "\n".join(
            [
                "persona_id: '0174'",
                "source: PRIMEX",
                "dimensions:",
                "  age_bracket: 65+",
                "  region: East Asia",
                "  gender_identity: Non-binary",
            ]
        ),
        encoding="utf-8",
    )
    _write_example_survey_task(repo)
    trial_dir = repo / "jobs" / "job-persona" / "trial-a"
    output = trial_dir / "artifacts" / "app" / "output"
    output.mkdir(parents=True)
    (trial_dir / "config.json").write_text(
        json.dumps(
            {
                "task": {"path": "application/tasks/example-survey_product-feedback"},
                "agent": {
                    "kwargs": {
                        "persona_path": "persona/datasets/matraix-persona-dev-sample/persona_0174.yaml",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (trial_dir / "events.jsonl").write_text(
        json.dumps(
            {
                "type": "prompts",
                "prompts": {
                    "harborPrompt": (
                        "You are a simulated user with predefined persona attributes.\n"
                        "Stay in character as this user throughout the task.\n\n"
                        "Persona:\npersona-0174"
                    ),
                    "personaPrompt": "Persona:\npersona-0174",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "survey_responses.json").write_text(
        json.dumps({"responses": [{"question_id": "overall_interest", "value": 3}]}),
        encoding="utf-8",
    )
    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name="job-persona",
        trial_name="trial-a",
    )
    persona_prompt = debrief["prompts"]["personaPrompt"]
    assert "## Who you are" in persona_prompt
    assert "Non-binary" in persona_prompt
    assert debrief["persona"]["dimensions"]["region"] == "East Asia"


def test_map_trial_debrief_survey_result_resolves_registered_instrument(tmp_path: Path) -> None:
    repo = tmp_path
    _write_example_survey_task(repo)
    trial_dir = repo / "jobs" / "job-survey" / "trial-0"
    output = trial_dir / "artifacts" / "app" / "output"
    output.mkdir(parents=True)
    (trial_dir / "config.json").write_text(
        json.dumps({"task": {"path": "application/tasks/example-survey_product-feedback"}}),
        encoding="utf-8",
    )
    (output / "survey_result.json").write_text(
        json.dumps(
            {
                "instrument": {"id": "product_feedback_v1", "title": "Survey Product Feedback"},
                "answers": [
                    {"questionId": "q0", "value": "q0_pay_when_roi_clear"},
                    {"questionId": "q1", "value": "q1_happy_plus_or_pro"},
                    {"questionId": "q2", "value": "q2_billing_no_preference"},
                    {"questionId": "q3", "value": "q3_grab_dollar_promo"},
                    {"questionId": "q4", "value": "q4_compare_pay_if_wins"},
                    {"questionId": "q5", "value": "q5_ads_pay_if_plus_useful"},
                    {"questionId": "q6", "value": "q6_fair_if_use_justifies"},
                    {"questionId": "overall_interest", "value": 3, "rationale": "Moderate interest."},
                    {"questionId": "would_try_beta", "value": "true"},
                ],
                "trajectory": [
                    {
                        "timestamp": "2026-07-02T08:00:00Z",
                        "actor": "system",
                        "action": "survey_started",
                        "context": {},
                        "outcome": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name="job-survey",
        trial_name="trial-0",
    )
    completion = debrief["surveyResult"]["completion"]
    assert completion["meanLikert"] == 3.0
    assert debrief["surveyResult"]["instrument"]["id"] == "product_feedback_v1"


def test_map_trial_debrief_failed_without_output(tmp_path: Path) -> None:
    repo = tmp_path
    task_dir = repo / "application" / "tasks" / "example-web-cua_bookshop-choice"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        '[metadata]\ntype = "os-app"\n',
        encoding="utf-8",
    )
    trial_dir = repo / "jobs" / "job-cua" / "trial-0"
    trial_dir.mkdir(parents=True)
    (trial_dir / "config.json").write_text(
        json.dumps({"task": {"path": "application/tasks/example-web-cua_bookshop-choice"}}),
        encoding="utf-8",
    )
    (trial_dir / "result.json").write_text(
        json.dumps(
            {
                "finished_at": "2026-07-01T12:00:00Z",
                "exception_info": {
                    "exception_type": "RuntimeError",
                    "exception_message": "Browser session closed unexpectedly",
                },
            }
        ),
        encoding="utf-8",
    )
    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name="job-cua",
        trial_name="trial-0",
    )
    assert debrief["status"] == "error"
    assert "Browser session closed" in debrief["error"]
    assert debrief["applicationType"] == "os-app"
    assert debrief["osAppResult"]["success"] is False


def test_map_trial_debrief_chatbot_from_events_when_artifacts_missing(tmp_path: Path) -> None:
    repo = tmp_path
    task_dir = repo / "application" / "tasks" / "chat_meal-planning-nutrition"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text('[metadata]\ntype = "chat"\n', encoding="utf-8")
    trial_dir = repo / "jobs" / "job-events" / "trial-0"
    output = trial_dir / "artifacts" / "app" / "output"
    output.mkdir(parents=True)
    (trial_dir / "config.json").write_text(
        json.dumps({"task": {"path": "application/tasks/chat_meal-planning-nutrition"}}),
        encoding="utf-8",
    )
    done_result = {
        "config": {
            "domain": "meal_planning",
            "applicationId": "meal_planning_nutrition",
        },
        "transcript": [
            {
                "turnIndex": 1,
                "userMessage": "Hi",
                "assistantMessage": "Hello",
                "recommendedItems": [],
            }
        ],
        "questionnaire": {
            "overallRating": 8,
            "ratingReason": "Good",
            "constraintSatisfaction": 4,
            "constraintRationale": "ok",
            "preferenceSatisfaction": 4,
            "preferenceRationale": "ok",
            "askedUsefulClarifyingQuestions": True,
            "clarifyingNotes": "",
        },
        "metricScores": {"numTurns": 1},
    }
    (trial_dir / "events.jsonl").write_text(
        json.dumps({"type": "done", "result": done_result}) + "\n",
        encoding="utf-8",
    )
    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name="job-events",
        trial_name="trial-0",
    )
    assert debrief["applicationType"] == "chatbot"
    assert debrief["transcript"][0]["assistantMessage"] == "Hello"
    assert debrief["questionnaire"]["overallRating"] == 8


def test_map_trial_debrief_ios_cua_tmp_artifacts(tmp_path: Path) -> None:
    repo = tmp_path
    task_dir = repo / "application" / "tasks" / "example-computer-use-ios_photo-access-review"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        '[metadata]\ntype = "os-app"\n',
        encoding="utf-8",
    )
    trial_dir = repo / "jobs" / "job-ios" / "trial-0"
    output = trial_dir / "artifacts" / "tmp" / "os-app-ios-photo-access-review"
    output.mkdir(parents=True)
    (output / "decision.json").write_text(
        json.dumps({"keep_notifications_on": True, "app_reviewed": "Calendar"}),
        encoding="utf-8",
    )
    (output / "user_feedback.json").write_text(
        json.dumps({"overallExperienceRating": 8, "reason": "The settings flow felt clear."}),
        encoding="utf-8",
    )
    verifier_dir = trial_dir / "verifier"
    verifier_dir.mkdir(parents=True)
    (verifier_dir / "reward.txt").write_text("1\n", encoding="utf-8")
    (trial_dir / "config.json").write_text(
        json.dumps({"task": {"path": "application/tasks/example-computer-use-ios_photo-access-review"}}),
        encoding="utf-8",
    )
    (trial_dir / "result.json").write_text(
        json.dumps(
            {
                "verifier_result": {"rewards": {"reward": 1.0}},
                "exception_info": None,
            }
        ),
        encoding="utf-8",
    )
    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name="job-ios",
        trial_name="trial-0",
    )
    assert debrief["applicationType"] == "os-app"
    assert debrief["osAppResult"]["success"] is True
    assert debrief["osAppResult"]["artifactName"] == "decision.json"
    assert debrief["userFeedback"]["overallExperienceRating"] == 8
    assert debrief.get("status") != "error"


def test_map_trial_debrief_os_app_runs_host_verifier_before_scoring(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path
    task_dir = repo / "application" / "tasks" / "os-app-ios_news-subscription-decision"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text('[metadata]\ntype = "os-app"\n', encoding="utf-8")
    (task_dir / "tests").mkdir()
    (task_dir / "tests" / "test.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    trial_dir = repo / "jobs" / "job-ios" / "trial-host"
    output = trial_dir / "artifacts" / "app" / "output"
    output.mkdir(parents=True)
    (output / "decision.json").write_text(
        json.dumps(
            {
                "app_reviewed": "News",
                "browsed_full_offer": True,
                "reviewed_features_and_pricing": True,
                "clicked_get_started": False,
                "price_seen": "$12.99/month",
                "highlights_noticed": ["WSJ"],
                "reason": "Too expensive for my student budget right now.",
            }
        ),
        encoding="utf-8",
    )
    (trial_dir / "config.json").write_text(
        json.dumps({"task": {"path": "application/tasks/os-app-ios_news-subscription-decision"}}),
        encoding="utf-8",
    )
    (trial_dir / "result.json").write_text("{}", encoding="utf-8")

    def _fake_host_verifier(*, repo_root: Path, trial_dir: Path, timeout_sec: float | None = None) -> bool:
        del repo_root, timeout_sec
        verifier_dir = trial_dir / "verifier"
        verifier_dir.mkdir(parents=True, exist_ok=True)
        (verifier_dir / "reward.txt").write_text("1\n", encoding="utf-8")
        return True

    monkeypatch.setattr(
        "playground.host_verifier.maybe_run_host_verifier",
        _fake_host_verifier,
    )

    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name="job-ios",
        trial_name="trial-host",
    )
    assert debrief["applicationType"] == "os-app"
    assert debrief["osAppResult"]["success"] is True
    assert debrief["osAppResult"]["score"] == 1.0
    assert debrief["verifier"]["passed"] is True


def test_map_trial_debrief_web_recovers_from_trajectory_when_artifact_missing(
    tmp_path: Path,
) -> None:
    repo = tmp_path
    persona_path = repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0020.yaml"
    persona_path.parent.mkdir(parents=True, exist_ok=True)
    persona_path.write_text(
        "persona_id: '0020'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    task_dir = repo / "application" / "tasks" / "example-web-playwright_quote-choice"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        'schema_version = "1.1"\n\n[metadata]\ntype = "web"\n',
        encoding="utf-8",
    )
    job_name = "job-web"
    trial_name = "trial-web"
    trial_dir = repo / "jobs" / job_name / trial_name
    output = trial_dir / "artifacts" / "app" / "output"
    output.mkdir(parents=True)
    (output / "user_feedback.json").write_text(
        json.dumps({"overallExperienceRating": 6, "trustLevel": 7, "reason": "The site worked but felt busy."}),
        encoding="utf-8",
    )
    agent_dir = trial_dir / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "trajectory.json").write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "source": "agent",
                        "message": (
                            "Done browsing.\n```json\n"
                            + json.dumps(
                                {
                                    "selected_product_id": "desk-002",
                                    "selected_product_name": "FocusDesk Pro",
                                    "need_satisfaction": 8,
                                    "ease_of_use": 7,
                                    "overall_experience_rating": 6,
                                    "reason": (
                                        "The FocusDesk Pro matched my workspace needs with "
                                        "drawer storage and cable routing for multiple devices."
                                    ),
                                }
                            )
                            + "\n```"
                        ),
                    }
                ]
            }
        ),
            encoding="utf-8",
        )
    (trial_dir / "config.json").write_text(
        json.dumps(
            {
                "task": {"path": "application/tasks/example-web-playwright_quote-choice"},
            }
        ),
        encoding="utf-8",
    )
    (trial_dir / "result.json").write_text(
        json.dumps(
            {
                "config": {
                    "task": {"path": "application/tasks/example-web-playwright_quote-choice"},
                    "agent": {
                        "kwargs": {
                            "persona_path": "persona/datasets/matraix-persona-dev-sample/persona_0020.yaml",
                        }
                    },
                },
                "exception_info": None,
            }
        ),
        encoding="utf-8",
    )

    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name=job_name,
        trial_name=trial_name,
    )

    assert debrief["applicationType"] == "web"
    assert debrief["webResult"]["selectedProductId"] == "desk-002"
    assert debrief["webTrace"]["events"]
    assert debrief["userFeedback"]["trustLevel"] == 7
    assert (output / "quote_choice.json").is_file()


def test_map_trial_debrief_web_maps_decision_submission_artifact(tmp_path: Path) -> None:
    repo = tmp_path
    persona_path = repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0001.yaml"
    persona_path.parent.mkdir(parents=True, exist_ok=True)
    persona_path.write_text(
        "persona_id: '0001'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    task_dir = repo / "application" / "tasks" / "example-web-cocoa_plan-choice"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        'schema_version = "1.1"\n\n[metadata]\ntype = "web"\n',
        encoding="utf-8",
    )
    job_name = "job-web-plan"
    trial_name = "trial-web-plan"
    trial_dir = repo / "jobs" / job_name / trial_name
    output = trial_dir / "artifacts" / "app" / "output"
    output.mkdir(parents=True)
    (output / "plan_choice.json").write_text(
        json.dumps(
            {
                "decision_subject_id": "developer",
                "decision_subject_label": "Developer",
                "decision_outcome": "selected",
                "basis_primary": "fit",
                "exploration_style": "compared_multiple",
                "reason": "The fixed monthly price and bounded feature set felt like the safest realistic fit for my needs.",
                "task_price_text": "$10/month",
            }
        ),
        encoding="utf-8",
    )
    (trial_dir / "config.json").write_text(
        json.dumps(
            {
                "task": {"path": "application/tasks/example-web-cocoa_plan-choice"},
                "agent": {
                    "kwargs": {
                        "persona_path": "persona/datasets/matraix-persona-dev-sample/persona_0001.yaml",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (trial_dir / "result.json").write_text(
        json.dumps({"exception_info": None}),
        encoding="utf-8",
    )

    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name=job_name,
        trial_name=trial_name,
    )

    assert debrief["applicationType"] == "web"
    assert debrief["webResult"]["selectedProductId"] == "developer"
    assert debrief["webResult"]["selectedProductName"] == "Developer"
    assert debrief["webResult"]["overallExperienceRating"] == 8
    assert debrief["webResult"]["easeOfUse"] == 8
    assert debrief["webResult"]["needSatisfaction"] == 8


def test_map_trial_debrief_web_restores_harbor_import_paths_when_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path
    persona_path = repo / "persona" / "datasets" / "matraix-persona-dev-sample" / "persona_0020.yaml"
    persona_path.parent.mkdir(parents=True, exist_ok=True)
    persona_path.write_text(
        "persona_id: '0020'\nversion: '1.0'\nsource: Nemotron\ndimensions: {}\n",
        encoding="utf-8",
    )
    task_dir = repo / "application" / "tasks" / "example-web-playwright_quote-choice"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        'schema_version = "1.1"\n\n[metadata]\ntype = "web"\n',
        encoding="utf-8",
    )
    job_name = "job-web-imports"
    trial_name = "trial-web-imports"
    trial_dir = repo / "jobs" / job_name / trial_name
    output = trial_dir / "artifacts" / "app" / "output"
    output.mkdir(parents=True)
    (output / "user_feedback.json").write_text(
        json.dumps(
            {
                "overallExperienceRating": 6,
                "trustLevel": 7,
                "reason": "The site worked but felt busy.",
            }
        ),
        encoding="utf-8",
    )
    agent_dir = trial_dir / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "trajectory.json").write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "source": "agent",
                        "message": (
                            "Done browsing.\n```json\n"
                            + json.dumps(
                                {
                                    "selected_product_id": "desk-002",
                                    "selected_product_name": "FocusDesk Pro",
                                    "need_satisfaction": 8,
                                    "ease_of_use": 7,
                                    "overall_experience_rating": 6,
                                    "reason": "The FocusDesk Pro matched my workspace needs.",
                                }
                            )
                            + "\n```"
                        ),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (trial_dir / "config.json").write_text(
        json.dumps(
            {
                "task": {"path": "application/tasks/example-web-playwright_quote-choice"},
                "agent": {
                    "kwargs": {
                        "persona_path": "persona/datasets/matraix-persona-dev-sample/persona_0020.yaml",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (trial_dir / "result.json").write_text(
        json.dumps({"exception_info": None}),
        encoding="utf-8",
    )

    source_repo_root = Path(__file__).resolve().parents[4]
    filtered_path = []
    for entry in sys.path:
        try:
            resolved = Path(entry or ".").resolve()
        except OSError:
            filtered_path.append(entry)
            continue
        if resolved == source_repo_root:
            continue
        filtered_path.append(entry)

    for name in list(sys.modules):
        if name == "environment" or name.startswith("environment."):
            sys.modules.pop(name, None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", filtered_path)

    debrief = map_trial_debrief(
        repo_root=repo,
        jobs_dir=repo / "jobs",
        job_name=job_name,
        trial_name=trial_name,
    )

    assert debrief["applicationType"] == "web"
    assert debrief["webResult"]["selectedProductId"] == "desk-002"
