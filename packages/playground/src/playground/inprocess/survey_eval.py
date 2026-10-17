from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from backend.service.survey_instruction_builder import (
    render_survey_context_markdown,
    render_survey_output_schema_markdown,
    render_survey_questionnaire_markdown,
    render_survey_task_instruction_markdown,
)
from backend.service.survey_types import (
    SurveyAnswer,
    SurveyEvalConfig,
    SurveyEvalResult,
    SurveyInstrument,
    SurveyMetrics,
    SurveyQuestion,
    SurveyTaskContent,
    TrajectoryEvent,
)
from playground.budget import assert_budget_allows_request, record_trial_cost
from playground.model_client import build_json_client
from playground.types import Persona
from playground.user_sim.prompt import render_persona_block


def persona_system_prompt(persona: Persona, *, persona_yaml_path: str) -> str:
    persona_body = render_persona_block(
        persona, persona_yaml_path=persona_yaml_path
    ).strip()
    if not persona_body:
        raise ValueError(f"empty persona render for yaml path: {persona_yaml_path}")
    return persona_body


def build_survey_task_prompt(*, instrument: SurveyInstrument) -> str:
    from playground.harbor.playground import _repo_root
    from playground.survey_task_content import (
        load_survey_task_content_for_questionnaire_id,
    )

    task_content = load_survey_task_content_for_questionnaire_id(
        instrument.id,
        repo_root=_repo_root(),
        fallback_questionnaire=instrument,
    )
    if task_content is None:
        task_content = SurveyTaskContent(
            title=instrument.title,
            instruction_markdown=render_survey_task_instruction_markdown(instrument).strip(),
            context_markdown=render_survey_context_markdown(instrument).strip(),
            questionnaire_markdown=render_survey_questionnaire_markdown(instrument).strip(),
            output_schema_markdown=render_survey_output_schema_markdown(instrument).strip(),
            instrument=instrument,
        )
    lines: list[str] = []
    if task_content.instruction_markdown.strip():
        lines.extend(["## Task instruction", "", task_content.instruction_markdown.strip(), ""])
    if task_content.context_markdown.strip():
        lines.extend(["## Context", "", task_content.context_markdown.strip(), ""])
    if task_content.questionnaire_markdown.strip():
        lines.extend(["## Questionnaire", "", task_content.questionnaire_markdown.strip(), ""])
    # Answer envelope is derived from questionnaire flags; keep a short derived
    # schema section so the model sees the JSON shape without a task-owned file.
    derived_schema = (
        task_content.output_schema_markdown.strip()
        or render_survey_output_schema_markdown(instrument).strip()
    )
    if derived_schema:
        lines.extend(["## Answer envelope", "", derived_schema, ""])
    return "\n".join(lines).strip()


class InprocessSurveyEvalRunner:
    """Run survey completion through the configured persona model."""

    def __call__(
        self,
        persona: Persona,
        instrument: SurveyInstrument,
        config: Optional[SurveyEvalConfig] = None,
        *,
        created_at: str,
        persona_yaml_path: str,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        job_dir: Optional[Any] = None,
        client: Any | None = None,
        client_factory: Optional[Callable[[str], Any]] = None,
    ) -> SurveyEvalResult:
        config = config or SurveyEvalConfig()

        def emit(event: Dict[str, Any]) -> None:
            if on_event is not None:
                on_event(event)

        task_prompt = build_survey_task_prompt(instrument=instrument)
        persona_prompt = persona_system_prompt(
            persona, persona_yaml_path=persona_yaml_path
        )
        prompts = {
            "personaPrompt": persona_prompt,
            "harborPrompt": persona_prompt,
            "taskPrompt": task_prompt,
        }
        emit({"type": "prompts", "prompts": prompts})
        emit({"type": "phase", "phase": "survey_answering"})

        assert_budget_allows_request(job_dir)
        if client is not None:
            pass
        elif client_factory is not None:
            client = client_factory(config.persona_model)
        else:
            client = build_json_client(config.persona_model)
        if hasattr(client, "complete_json_with_usage"):
            completion = client.complete_json_with_usage(
                prompts["personaPrompt"], task_prompt
            )
            raw = completion.data
            usage = completion.usage
        else:
            raw = client.complete_json(prompts["personaPrompt"], task_prompt)
            usage = None
        if usage is not None:
            record_trial_cost(job_dir, usage.cost_usd)
            emit({"type": "usage", "usage": usage.to_dict()})
        answers, filled_ids = _normalize_answers(raw.get("answers"), instrument)
        metrics = _metrics(answers, instrument)
        trajectory = _build_trajectory(
            instrument, answers, created_at, missing_required=filled_ids
        )
        result = SurveyEvalResult(
            config=config,
            persona=persona,
            instrument=instrument,
            answers=answers,
            trajectory=trajectory,
            metrics=metrics,
            created_at=created_at,
            prompts=prompts,
            usage=usage.to_dict() if usage is not None else None,
        )
        emit({"type": "done", "result": result.to_dict()})
        return result


def _event_timestamp(created_at: str, offset_seconds: int) -> str:
    try:
        base = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return created_at
    return (
        base.astimezone(timezone.utc) + timedelta(seconds=offset_seconds)
    ).isoformat().replace("+00:00", "Z")


def _build_trajectory(
    instrument: SurveyInstrument,
    answers: List[SurveyAnswer],
    created_at: str,
    *,
    missing_required: Optional[List[str]] = None,
) -> List[TrajectoryEvent]:
    answer_by_id = {answer.question_id: answer for answer in answers}
    # Callers pass the required questions they back-filled with a neutral
    # default, since those are in ``answers`` but were never really answered.
    if missing_required is None:
        missing_required = [
            question.id
            for question in instrument.questions
            if question.required and question.id not in answer_by_id
        ]
    events = [
        TrajectoryEvent(
            timestamp=_event_timestamp(created_at, 0),
            actor="system",
            action="survey_started",
            context={
                "instrumentId": instrument.id,
                "instrumentTitle": instrument.title,
                "numQuestions": len(instrument.questions),
            },
            outcome={"status": "started"},
        )
    ]

    offset = 1
    for index, question in enumerate(instrument.questions, start=1):
        question_context = {
            "instrumentId": instrument.id,
            "questionId": question.id,
            "questionIndex": index,
            "questionType": question.type,
            "construct": question.construct,
        }
        events.append(
            TrajectoryEvent(
                timestamp=_event_timestamp(created_at, offset),
                actor="assistant",
                action="ask_question",
                context=question_context,
                outcome={
                    "prompt": question.prompt,
                    "options": list(question.options),
                },
            )
        )
        offset += 1

        answer = answer_by_id.get(question.id)
        if answer is None:
            continue
        events.append(
            TrajectoryEvent(
                timestamp=_event_timestamp(created_at, offset),
                actor="user",
                action="answer_question",
                context=question_context,
                outcome={
                    "questionId": answer.question_id,
                    "value": answer.value,
                    "rationale": answer.rationale,
                    "confidence": answer.confidence,
                },
            )
        )
        offset += 1

    events.append(
        TrajectoryEvent(
            timestamp=_event_timestamp(created_at, offset),
            actor="system",
            action="survey_completed",
            context={"instrumentId": instrument.id},
            outcome={
                "numAnswered": len(answers),
                "missingRequiredQuestionIds": missing_required,
                "valid": not missing_required,
            },
        )
    )
    return events


def _normalize_answers(
    raw_answers: Any, instrument: SurveyInstrument
) -> tuple[List[SurveyAnswer], List[str]]:
    """Return usable answers plus the ids of required questions that were back-filled."""
    by_id = {question.id: question for question in instrument.questions}
    answers: List[SurveyAnswer] = []
    if not isinstance(raw_answers, list):
        raw_answers = []
    seen = set()
    for raw in raw_answers:
        if not isinstance(raw, dict):
            continue
        answer = SurveyAnswer.from_dict(raw)
        question = by_id.get(answer.question_id)
        if question is None or answer.question_id in seen:
            continue
        value = _normalize_value(answer.value, question)
        if value is _NO_ANSWER:
            # Not a valid answer for this question: treat it as unanswered rather
            # than recording some other option under the persona's rationale.
            continue
        answer.value = value
        if not question.resolves_ask_rationale(instrument):
            answer.rationale = ""
        if not question.resolves_ask_confidence(instrument):
            answer.confidence = None
        answers.append(answer)
        seen.add(answer.question_id)
    filled: List[str] = []
    for question in instrument.questions:
        if question.required and question.id not in seen:
            filled.append(question.id)
            answers.append(
                SurveyAnswer(
                    question_id=question.id,
                    value=_default_value(question),
                    rationale=(
                        "No persona-specific answer was produced, so a neutral answer was used."
                        if question.resolves_ask_rationale(instrument)
                        else ""
                    ),
                    confidence=(
                        0.0 if question.resolves_ask_confidence(instrument) else None
                    ),
                )
            )
    return answers, filled


_NO_ANSWER = object()


def _likert_bounds(question: SurveyQuestion) -> tuple[int, int]:
    low = 1 if question.min_value is None else int(question.min_value)
    high = 5 if question.max_value is None else int(question.max_value)
    return low, high


def _match_option(value: Any, question: SurveyQuestion) -> Optional[str]:
    """Option id for ``value``: exact id, then id or label ignoring case/whitespace."""
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    if text in question.options:
        return text
    folded = text.casefold()
    for option_id in question.options:
        if option_id.casefold() == folded:
            return option_id
    for detail in question.option_details:
        if detail.label and detail.label.strip().casefold() == folded:
            return detail.id
    return None


def _normalize_value(value: Any, question: SurveyQuestion) -> Any:
    """Coerce a model answer to the question's type, or ``_NO_ANSWER`` if it can't be."""
    if question.type == "likert":
        if isinstance(value, bool):
            return _NO_ANSWER
        try:
            number = int(round(float(value)))
        except (TypeError, ValueError):
            return _NO_ANSWER
        low, high = _likert_bounds(question)
        return max(low, min(high, number))
    if question.type == "single_choice":
        matched = _match_option(value, question)
        return matched if matched is not None else _NO_ANSWER
    if question.type == "multi_choice":
        values = value if isinstance(value, list) else [value]
        selected: List[str] = []
        for item in values:
            matched = _match_option(item, question)
            if matched is not None and matched not in selected:
                selected.append(matched)
        return selected or _NO_ANSWER
    return str(value or "").strip()


def _default_value(question: SurveyQuestion) -> Any:
    if question.type == "likert":
        low, high = _likert_bounds(question)
        return int(round((low + high) / 2))
    if question.type == "single_choice":
        return question.options[0]
    if question.type == "multi_choice":
        return [question.options[0]]
    return ""


def _metrics(answers: List[SurveyAnswer], instrument: SurveyInstrument) -> SurveyMetrics:
    likert_values: List[float] = []
    question_types = {question.id: question.type for question in instrument.questions}
    for answer in answers:
        if question_types.get(answer.question_id) != "likert":
            continue
        try:
            likert_values.append(float(answer.value))
        except (TypeError, ValueError):
            continue
    mean = round(sum(likert_values) / len(likert_values), 2) if likert_values else None
    return SurveyMetrics(
        num_questions=len(instrument.questions),
        num_answered=len(answers),
        mean_likert=mean,
    )
