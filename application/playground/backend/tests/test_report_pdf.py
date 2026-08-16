"""PDF report builders for Harbor batch and trial downloads."""

from __future__ import annotations

import re
import zlib

from backend.service.report_pdf import (
    build_batch_report_pdf,
    build_trial_report_pdf,
    pdf_filename,
)


def _pdf_text(raw: bytes) -> str:
    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.S):
        data = match.group(1)
        try:
            data = zlib.decompress(data)
        except Exception:
            pass
        chunks.append(data.decode("latin-1", errors="ignore"))
    return "\n".join(chunks)


def test_pdf_filename_sanitizes_parts():
    assert pdf_filename("job/a", "trial:b") == "job-a-trial-b.pdf"
    assert pdf_filename("demo-job", "persona-task-batch-report") == (
        "demo-job-persona-task-batch-report.pdf"
    )


def test_build_batch_report_pdf_returns_pdf_bytes():
    payload = build_batch_report_pdf(
        job_name="demo-job",
        job={
            "applicationType": "survey",
            "taskPath": "application/tasks/example-survey_product-feedback",
            "taskTitle": "Product feedback survey",
            "personaStrategy": {
                "sampling": {"mode": "random", "sampleSize": 12},
                "seed": 42,
                "sources": ["Nemotron"],
            },
            "launch": {"status": "completed", "exitCode": 0, "configPath": "/tmp/cfg.yaml"},
            "result": {
                "started_at": "2026-07-12T00:00:00Z",
                "finished_at": "2026-07-12T00:01:00Z",
                "stats": {
                    "n_input_tokens": 4200,
                    "n_output_tokens": 880,
                    "cost_usd": 0.21,
                },
            },
            "config": {
                "tasks": [{"path": "application/tasks/example-survey_product-feedback"}],
                "_job_meta": {"persona_pool": "persona/datasets/matraix-persona-dev-sample"},
            },
            "trials": [
                {
                    "trialName": "trial-1",
                    "personaName": "Alex",
                    "completed": True,
                    "succeeded": True,
                }
            ],
        },
        aggregation={
            "generatedAt": "2026-07-12T00:00:00Z",
            "coverage": {
                "trialCount": 1,
                "completedTrials": 1,
                "pendingTrials": 0,
                "artifactReadyTrials": 1,
                "completedWithoutArtifactTrials": 0,
            },
            "reporting": {"status": "not_applicable", "model": "gpt-test"},
            "fields": [
                {
                    "key": "question.q1.response",
                    "label": "Selected response",
                    "kind": "categorical",
                    "presentCount": 1,
                    "missingCount": 0,
                    "categorical": {
                        "count": 1,
                        "distinctCount": 1,
                        "counts": [{"value": "incorrect_code_changes", "count": 1}],
                    },
                }
            ],
            "contexts": [
                {
                    "key": "question.q1",
                    "label": "What is your biggest concern?",
                    "contextType": "question_response",
                    "questionType": "single_choice",
                    "choiceOptions": [
                        {"id": "incorrect_code_changes", "label": "Incorrect code changes"},
                        {"id": "too_much_autonomy", "label": "Too much autonomy"},
                    ],
                    "facets": [
                        {
                            "key": "question.q1.response",
                            "label": "Selected response",
                            "kind": "categorical",
                            "role": "primary",
                            "presentCount": 1,
                            "missingCount": 0,
                            "categorical": {
                                "count": 1,
                                "distinctCount": 1,
                                "counts": [{"value": "incorrect_code_changes", "count": 1}],
                            },
                        }
                    ],
                }
            ],
        },
        task_detail={
            "title": "Product feedback survey",
            "description": "Collect product opinions from simulated users.",
            "instructionMarkdown": "# Answer in character\n\nBe honest.",
            "personaStrategy": {
                "sampling": {"mode": "random", "sampleSize": 12},
                "seed": 42,
            },
        },
    )
    assert payload.startswith(b"%PDF")
    assert len(payload) > 500

    text = _pdf_text(payload)
    assert "Persona-task batch report" in text
    assert "Per-question report" in text
    assert "Incorrect code changes" in text
    assert "What is your biggest concern?" in text
    assert "Task" in text
    assert "Persona strategy" in text
    assert "Cohort" in text
    assert "Cost: $0.210" in text or "Cost: $0.21" in text
    assert "4,200 in" in text
    # Flat field dump should not dominate when question contexts exist.
    assert text.count("Selected response") <= 2


def test_build_batch_report_pdf_includes_detailed_analysis_content():
    """CLI/server PDF must carry Detailed-tab data (summaries, judges, crosses, personas)."""
    payload = build_batch_report_pdf(
        job_name="chat-job",
        job={
            "applicationType": "chatbot",
            "taskTitle": "Meal planning chat",
            "config": {"_job_meta": {"persona_pool": "persona/datasets/demo"}},
            "trials": [
                {"trialName": "t1", "personaName": "Sam", "completed": True, "succeeded": True},
                {"trialName": "t2", "personaName": "Jordan", "completed": True, "succeeded": True},
            ],
        },
        aggregation={
            "generatedAt": "2026-08-10T00:00:00Z",
            "coverage": {
                "trialCount": 2,
                "completedTrials": 2,
                "pendingTrials": 0,
                "artifactReadyTrials": 2,
                "completedWithoutArtifactTrials": 0,
            },
            "reporting": {"status": "ready", "model": "gpt-test"},
            "fields": [],
            "contexts": [
                {
                    "key": "conversation_summary",
                    "label": "Conversation summary",
                    "contextType": "conversation_summary",
                    "facets": [
                        {
                            "key": "conversation_path",
                            "label": "Conversation path",
                            "kind": "categorical",
                            "role": "primary",
                            "presentCount": 4,
                            "missingCount": 0,
                            "categorical": {
                                "count": 4,
                                "distinctCount": 2,
                                "counts": [
                                    {"value": "clarify_then_resolve", "count": 3},
                                    {"value": "clarify_then_partial", "count": 1},
                                ],
                            },
                        },
                        {
                            "key": "process_notes",
                            "label": "Process notes",
                            "kind": "textual",
                            "presentCount": 4,
                            "missingCount": 0,
                            "textual": {
                                "summary": "Asked about dietary needs before planning.",
                                "samples": [
                                    "Clarified allergies then offered a meal plan.",
                                ],
                            },
                        },
                    ],
                    "summaries": [
                        {
                            "id": "auto-process",
                            "title": "Process notes rollup",
                            "auto": True,
                            "lens": "general",
                            "overall": {
                                "summary": "All answers converge on clarifying dietary needs.",
                            },
                            "buckets": [
                                {
                                    "bucket": "clarify_then_resolve",
                                    "count": 3,
                                    "summary": "Resolved after clarifying questions.",
                                    "samples": ["Asked about vegan options."],
                                }
                            ],
                        },
                        {
                            "id": "custom-task",
                            "title": "Custom task theme",
                            "auto": False,
                            "lens": "task",
                            "overall": {"summary": "Meal plans stayed practical."},
                            "buckets": [],
                        },
                    ],
                    "judges": [
                        {
                            "id": "signal-scan",
                            "title": "Dietary signal scan",
                            "status": "ready",
                            "overallAssessment": "Dietary constraints were usually explicit.",
                            "signalStats": [
                                {
                                    "key": "allergy",
                                    "label": "Allergy mentioned",
                                    "present": 2,
                                    "total": 4,
                                    "examples": ["Nut allergy noted up front."],
                                }
                            ],
                            "buckets": [
                                {
                                    "bucket": "yes",
                                    "count": 2,
                                    "samples": ["Peanut allergy"],
                                    "assessment": "Clear allergy callout.",
                                }
                            ],
                        }
                    ],
                    "crossFacetViews": [
                        {
                            "type": "text_by_category",
                            "primaryFacetKey": "conversation_path",
                            "textFacetKey": "process_notes",
                            "buckets": [
                                {
                                    "category": "clarify_then_resolve",
                                    "count": 3,
                                    "samples": [
                                        "The assistant asked clarifying questions about dietary needs."
                                    ],
                                }
                            ],
                        }
                    ],
                    "personaDistributions": [
                        {
                            "id": "path-by-life-stage",
                            "facetKey": "conversation_path",
                            "facetLabel": "Path by life stage",
                            "kind": "categorical",
                            "groupByPersonaDimension": "life_stage",
                            "groupByLabel": "Life stage",
                            "total": 4,
                            "buckets": [
                                {
                                    "bucket": "early_career",
                                    "count": 2,
                                    "categorical": {
                                        "counts": [
                                            {"value": "clarify_then_resolve", "count": 2},
                                        ]
                                    },
                                }
                            ],
                        }
                    ],
                    "personaStandaloneFacets": [
                        {
                            "key": "overall_helpfulness",
                            "label": "Overall helpfulness",
                            "kind": "numerical",
                            "presentCount": 2,
                            "missingCount": 0,
                            "numerical": {"avg": 4.5, "min": 4, "max": 5, "count": 2},
                        }
                    ],
                }
            ],
        },
    )
    assert payload.startswith(b"%PDF")
    text = _pdf_text(payload)
    assert "Conversation summary" in text
    assert "Process notes" in text
    assert "Asked about dietary needs before planning." in text
    assert "All answers converge on clarifying dietary needs." in text
    assert "Custom task theme" in text
    assert "Dietary signal scan" in text
    assert "Allergy mentioned" in text
    assert "The assistant asked clarifying questions about dietary needs." in text
    assert "Persona insights" in text
    assert "Path by life stage" in text
    assert "early_career" in text
    assert "Overall helpfulness" in text
    assert "Sam" in text
    assert "Jordan" in text


def test_build_trial_report_pdf_survey_returns_pdf_bytes():
    payload = build_trial_report_pdf(
        job_name="demo-job",
        trial_name="trial-1",
        debrief={
            "applicationType": "survey",
            "createdAt": "2026-07-12T00:00:00Z",
            "persona": {"id": "p1", "name": "Alex", "source": "pool", "dimensions": {"age": "25-34"}},
            "config": {"taskPath": "application/tasks/example-survey_product-feedback"},
            "verifier": {"reward": 1.0, "passed": True, "details": "ok"},
            "usage": {
                "nInputTokens": 1500,
                "nOutputTokens": 220,
                "costUsd": 0.018,
            },
            "surveyResult": {
                "completed": True,
                "instrument": {"id": "inst-1", "title": "Product feedback"},
                "answers": [
                    {
                        "questionId": "q1",
                        "value": 5,
                        "rationale": "Clear and useful.",
                    }
                ],
            },
        },
    )
    assert payload.startswith(b"%PDF")
    assert len(payload) > 400
    text = _pdf_text(payload)
    assert "Usage" in text
    assert "Cost" in text
    assert "1,500" in text
    assert "220" in text
