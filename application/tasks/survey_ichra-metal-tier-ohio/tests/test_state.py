from __future__ import annotations

import json
import os
import sys
from pathlib import Path

OUTPUT_DIR = Path(
    os.environ.get("HARBOR_OUTPUT_DIR")
    or os.environ.get("MATRIX_OUTPUT_DIR")
    or "/app/output"
)
RESULT_PATH = OUTPUT_DIR / "survey_result.json"
EVENT_KEYS = {"timestamp", "actor", "action", "context", "outcome"}


def _verifier_dir() -> Path:
    base = (
        os.environ.get("HARBOR_VERIFIER_DIR")
        or os.environ.get("HARBOR_VERIFIER_DIR")
        or "/logs/verifier"
    )
    path = Path(base)
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        path = Path(__file__).resolve().parent.parent / "verifier"
        path.mkdir(parents=True, exist_ok=True)
        return path


def _write_structured_output(payload: dict[str, object]) -> None:
    path = _verifier_dir() / "structured_output.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _question_types_from_trajectory(trajectory: list[object]) -> dict[str, str]:
    """Map questionId -> questionnaire type from ask_question trajectory events."""
    out: dict[str, str] = {}
    for event in trajectory:
        if not isinstance(event, dict):
            continue
        if str(event.get("action") or "") != "ask_question":
            continue
        context = event.get("context")
        if not isinstance(context, dict):
            continue
        question_id = str(context.get("questionId") or "").strip()
        question_type = str(context.get("questionType") or "").strip().lower()
        if question_id and question_type:
            out[question_id] = question_type
    return out


def _field_kind_for_question(question_type: str | None, value: object) -> str:
    """Kind follows questionnaire type — not string-shape heuristics."""
    qtype = (question_type or "").strip().lower()
    if qtype == "likert":
        return "numerical"
    if qtype in {"single_choice", "multi_choice"}:
        return "categorical"
    if qtype == "free_text":
        return "textual"
    if isinstance(value, bool):
        return "categorical"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "numerical"
    if isinstance(value, list):
        return "categorical"
    if isinstance(value, str):
        text = value.strip()
        if " " in text or "\n" in text or len(text) > 64:
            return "textual"
        return "categorical"
    return "textual"


def main() -> int:
    if not RESULT_PATH.is_file():
        return fail("missing /app/output/survey_result.json")
    try:
        payload = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return fail("survey_result.json is not valid JSON: {}".format(exc))
    if not isinstance(payload, dict):
        return fail("survey_result.json must contain an object")
    answers = payload.get("answers")
    if not isinstance(answers, list) or not answers:
        return fail("survey_result.answers must be a non-empty list")
    trajectory = payload.get("trajectory")
    if not isinstance(trajectory, list) or not trajectory:
        return fail("survey_result.trajectory must be a non-empty list")
    question_types = _question_types_from_trajectory(trajectory)
    fields: list[dict[str, object]] = []
    contexts: list[dict[str, object]] = []
    numeric_values: list[float] = []
    for index, answer in enumerate(answers):
        if not isinstance(answer, dict):
            return fail("answers[{}] must be an object".format(index))
        question_id = str(answer.get("questionId", "")).strip()
        if not question_id:
            return fail("answers[{}].questionId is required".format(index))
        if "value" not in answer:
            return fail("answers[{}].value is required".format(index))
        value = answer.get("value")
        question_type = question_types.get(question_id)
        kind = _field_kind_for_question(question_type, value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric_values.append(float(value))
        context_key = "question.{}".format(question_id)
        context_label = str(answer.get("prompt") or question_id)
        facets: list[dict[str, object]] = [
            {
                "key": "response",
                "label": "Selected response",
                "role": "primary",
                "kind": kind,
                "value": value,
            }
        ]
        fields.append(
            {
                "key": "{}.response".format(context_key),
                "label": "Selected response",
                "group": context_key,
                "role": "primary",
                "kind": kind,
                "value": value,
            }
        )
        rationale = str(answer.get("rationale") or "").strip()
        if rationale:
            facets.append(
                {
                    "key": "reason",
                    "label": "Reason",
                    "role": "explanation",
                    "kind": "textual",
                    "value": rationale,
                }
            )
            fields.append(
                {
                    "key": "{}.reason".format(context_key),
                    "label": "Reason",
                    "group": context_key,
                    "role": "explanation",
                    "kind": "textual",
                    "value": rationale,
                }
            )
        confidence = answer.get("confidence")
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            facets.append(
                {
                    "key": "confidence",
                    "label": "Confidence",
                    "role": "score",
                    "kind": "numerical",
                    "value": float(confidence),
                }
            )
            fields.append(
                {
                    "key": "{}.confidence".format(context_key),
                    "label": "Confidence",
                    "group": context_key,
                    "role": "score",
                    "kind": "numerical",
                    "value": float(confidence),
                }
            )
        context_payload: dict[str, object] = {
            "key": context_key,
            "label": context_label,
            "contextType": "question_response",
            "facets": facets,
        }
        if question_type:
            context_payload["questionType"] = question_type
        contexts.append(context_payload)
    for index, event in enumerate(trajectory):
        if not isinstance(event, dict):
            return fail("trajectory[{}] must be an object".format(index))
        missing = EVENT_KEYS - set(event)
        if missing:
            return fail(
                "trajectory[{}] missing keys: {}".format(index, ", ".join(sorted(missing)))
            )
        if not isinstance(event.get("context"), dict):
            return fail("trajectory[{}].context must be an object".format(index))
        if not isinstance(event.get("outcome"), dict):
            return fail("trajectory[{}].outcome must be an object".format(index))
    summary_facets: list[dict[str, object]] = [
        {
            "key": "answer_count",
            "label": "Answer count",
            "role": "score",
            "kind": "numerical",
            "value": len(answers),
        },
        {
            "key": "trajectory_event_count",
            "label": "Trajectory event count",
            "role": "score",
            "kind": "numerical",
            "value": len(trajectory),
        },
    ]
    fields.append(
        {
            "key": "survey.summary.answer_count",
            "label": "Answer count",
            "group": "survey.summary",
            "role": "score",
            "kind": "numerical",
            "value": len(answers),
        }
    )
    fields.append(
        {
            "key": "survey.summary.trajectory_event_count",
            "label": "Trajectory event count",
            "group": "survey.summary",
            "role": "score",
            "kind": "numerical",
            "value": len(trajectory),
        }
    )
    if numeric_values:
        summary_facets.append(
            {
                "key": "mean_numeric_answer",
                "label": "Mean numeric answer",
                "role": "score",
                "kind": "numerical",
                "value": round(sum(numeric_values) / len(numeric_values), 4),
            }
        )
        fields.append(
            {
                "key": "survey.summary.mean_numeric_answer",
                "label": "Mean numeric answer",
                "group": "survey.summary",
                "role": "score",
                "kind": "numerical",
                "value": round(sum(numeric_values) / len(numeric_values), 4),
            }
        )
    contexts.append(
        {
            "key": "survey.summary",
            "label": "Survey summary",
            "contextType": "trial_summary",
            "facets": summary_facets,
        }
    )
    _write_structured_output(
        {
            "schemaVersion": "1.0",
            "artifactType": "matraix.trial_evaluation",
            "taskType": "survey",
            "presenceCheck": {
                "passed": True,
                "requiredArtifacts": ["survey_result.json"],
                "missingArtifacts": [],
            },
            "sourceArtifacts": {
                "surveyResult": str(RESULT_PATH),
            },
            "contexts": contexts,
            "fields": fields,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
