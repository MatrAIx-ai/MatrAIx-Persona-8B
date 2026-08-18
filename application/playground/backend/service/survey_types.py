"""Survey schema types used by Playground application helpers."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

try:
    from playground.types import DEFAULT_PERSONA_MODEL, Persona
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[4]
    core_src = repo_root / "packages" / "playground" / "src"
    if str(core_src) not in sys.path:
        sys.path.insert(0, str(core_src))
    from playground.types import DEFAULT_PERSONA_MODEL, Persona

from playground.persona_language import resolve_persona_language_with_source

QUESTION_TYPES = {"likert", "single_choice", "multi_choice", "free_text"}


@dataclass
class SurveyOption:
    """One structured option for a choice-based survey question."""

    id: str
    label: str = ""
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurveyOption":
        return cls(
            id=str(data["id"]),
            label=str(data.get("label", "")),
            description=str(data.get("description", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
        }


def _optional_bool(data: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key in data and data[key] is not None:
            return bool(data[key])
    return None


@dataclass
class SurveyQuestion:
    """One question in a task-backed survey questionnaire."""

    id: str
    prompt: str
    type: str = "likert"
    options: list[str] = field(default_factory=list)
    option_details: list[SurveyOption] = field(default_factory=list)
    min_value: int | None = None
    max_value: int | None = None
    construct: str = ""
    required: bool = True
    # None inherits SurveyInstrument.ask_rationale / ask_confidence.
    ask_rationale: bool | None = None
    ask_confidence: bool | None = None

    def __post_init__(self) -> None:
        if self.type not in QUESTION_TYPES:
            raise ValueError(
                "question type must be one of {}".format(sorted(QUESTION_TYPES))
            )
        if self.type == "likert":
            if self.min_value is None:
                self.min_value = 1
            else:
                self.min_value = int(self.min_value)
            if self.max_value is None:
                self.max_value = 5
            else:
                self.max_value = int(self.max_value)
            if self.min_value >= self.max_value:
                raise ValueError("likert min_value must be less than max_value")
        if self.type in {"single_choice", "multi_choice"} and not self.options:
            raise ValueError("{} questions require options".format(self.type))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurveyQuestion":
        raw_options = list(data.get("options", []))
        option_details = [
            SurveyOption.from_dict(option)
            for option in raw_options
            if isinstance(option, dict) and option.get("id")
        ]
        if not option_details:
            option_details = [
                SurveyOption.from_dict(option)
                for option in data.get("optionDetails", [])
                if isinstance(option, dict) and option.get("id")
            ]
        option_ids = [detail.id for detail in option_details] or [
            str(option) for option in raw_options
        ]
        return cls(
            id=str(data["id"]),
            prompt=str(data["prompt"]),
            type=str(data.get("type", "likert")),
            options=option_ids,
            option_details=option_details,
            min_value=data.get("minValue", data.get("min_value")),
            max_value=data.get("maxValue", data.get("max_value")),
            construct=str(data.get("construct", "")),
            required=bool(data.get("required", True)),
            ask_rationale=_optional_bool(data, "askRationale", "ask_rationale"),
            ask_confidence=_optional_bool(data, "askConfidence", "ask_confidence"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "prompt": self.prompt,
            "type": self.type,
            "options": list(self.options),
            "optionDetails": [option.to_dict() for option in self.option_details],
            "minValue": self.min_value,
            "maxValue": self.max_value,
            "construct": self.construct,
            "required": self.required,
        }
        if self.ask_rationale is not None:
            payload["askRationale"] = self.ask_rationale
        if self.ask_confidence is not None:
            payload["askConfidence"] = self.ask_confidence
        return payload

    def resolves_ask_rationale(self, instrument: "SurveyInstrument") -> bool:
        return instrument.ask_rationale if self.ask_rationale is None else self.ask_rationale

    def resolves_ask_confidence(self, instrument: "SurveyInstrument") -> bool:
        return instrument.ask_confidence if self.ask_confidence is None else self.ask_confidence


@dataclass
class SurveyInstrument:
    """A named set of survey questions."""

    id: str
    title: str
    description: str = ""
    questions: list[SurveyQuestion] = field(default_factory=list)
    # Defaults for answer metadata; questions may override per item.
    # Off by default — opt in via questionnaire.yaml when needed.
    ask_rationale: bool = False
    ask_confidence: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurveyInstrument":
        ask_rationale = _optional_bool(data, "askRationale", "ask_rationale")
        ask_confidence = _optional_bool(data, "askConfidence", "ask_confidence")
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            description=str(data.get("description", "")),
            questions=[SurveyQuestion.from_dict(q) for q in data.get("questions", [])],
            ask_rationale=False if ask_rationale is None else ask_rationale,
            ask_confidence=False if ask_confidence is None else ask_confidence,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "askRationale": self.ask_rationale,
            "askConfidence": self.ask_confidence,
            "questions": [question.to_dict() for question in self.questions],
        }


@dataclass
class SurveyTaskContent:
    """Canonical survey task docs loaded from a task environment."""

    title: str = ""
    task_path: str = ""
    instruction_markdown: str = ""
    context_markdown: str = ""
    questionnaire_markdown: str = ""
    output_schema_markdown: str = ""
    instrument: SurveyInstrument | None = None

    def combined_markdown(self) -> str:
        parts: list[str] = []
        title = self.title or (self.instrument.title if self.instrument else "")
        if title:
            parts.extend(["# {}".format(title), ""])
        if self.instruction_markdown.strip():
            parts.extend(["## Task instruction", "", self.instruction_markdown.strip(), ""])
        if self.context_markdown.strip():
            parts.extend(["## Context", "", self.context_markdown.strip(), ""])
        if self.questionnaire_markdown.strip():
            parts.extend(["## Questionnaire", "", self.questionnaire_markdown.strip(), ""])
        if self.output_schema_markdown.strip():
            parts.extend(["## Answer envelope", "", self.output_schema_markdown.strip(), ""])
        return "\n".join(parts).strip()


@dataclass
class SurveyEvalConfig:
    """Runtime config for in-process survey evaluation."""

    persona_model: str = DEFAULT_PERSONA_MODEL
    mode: str = "inprocess_persona_survey"
    # Deprecated: rationale/confidence now come from questionnaire.yaml.
    # Kept for API compatibility; ignored by the survey runner.
    require_rationale: bool = True
    persona_language: str = "en"
    persona_language_source: str = "default"

    def __post_init__(self) -> None:
        resolution = resolve_persona_language_with_source(
            self.persona_language,
            requested_source=self.persona_language_source,
            environ={},
        )
        self.persona_language = resolution.language
        self.persona_language_source = resolution.source

    def to_dict(self) -> dict[str, Any]:
        return {
            "personaModel": self.persona_model,
            "mode": self.mode,
            "requireRationale": self.require_rationale,
            "effectiveLanguage": self.persona_language,
            "languageSource": self.persona_language_source,
        }


@dataclass
class SurveyAnswer:
    """One simulated persona answer to a survey question."""

    question_id: str
    value: Any
    rationale: str = ""
    confidence: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurveyAnswer":
        question_id = str(data.get("questionId", data.get("question_id", ""))).strip()
        if not question_id:
            raise ValueError("answer.questionId is required")
        confidence = data.get("confidence")
        if confidence is not None:
            try:
                confidence = max(0.0, min(1.0, float(confidence)))
            except (TypeError, ValueError):
                confidence = None
        return cls(
            question_id=question_id,
            value=data.get("value"),
            rationale=str(data.get("rationale", "")),
            confidence=confidence,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "questionId": self.question_id,
            "value": self.value,
            "rationale": self.rationale,
            "confidence": self.confidence,
        }


@dataclass
class TrajectoryEvent:
    """One event in a survey/web evaluation trajectory."""

    timestamp: str
    actor: str
    action: str
    context: dict[str, Any] = field(default_factory=dict)
    outcome: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrajectoryEvent":
        missing = [
            key
            for key in ("timestamp", "actor", "action", "context", "outcome")
            if key not in data
        ]
        if missing:
            raise ValueError(
                "trajectory event missing required keys: {}".format(", ".join(missing))
            )
        context = data.get("context")
        outcome = data.get("outcome")
        if not isinstance(context, dict):
            raise ValueError("trajectory event context must be an object")
        if not isinstance(outcome, dict):
            raise ValueError("trajectory event outcome must be an object")
        timestamp = str(data.get("timestamp") or "").strip()
        actor = str(data.get("actor") or "").strip()
        action = str(data.get("action") or "").strip()
        if not timestamp or not actor or not action:
            raise ValueError("trajectory event timestamp, actor, and action are required")
        return cls(
            timestamp=timestamp,
            actor=actor,
            action=action,
            context=dict(context),
            outcome=dict(outcome),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action": self.action,
            "context": dict(self.context),
            "outcome": dict(self.outcome),
        }


@dataclass
class SurveyMetrics:
    """Aggregate survey completion metrics."""

    num_questions: int
    num_answered: int
    mean_likert: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "numQuestions": self.num_questions,
            "numAnswered": self.num_answered,
            "meanLikert": self.mean_likert,
        }


@dataclass
class SurveyEvalResult:
    """Full in-process survey evaluation result."""

    config: SurveyEvalConfig
    persona: Persona
    instrument: SurveyInstrument
    answers: list[SurveyAnswer]
    trajectory: list[TrajectoryEvent]
    metrics: SurveyMetrics
    created_at: str
    prompts: dict[str, str]
    usage: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "config": self.config.to_dict(),
            "effectiveLanguage": self.config.persona_language,
            "languageSource": self.config.persona_language_source,
            "persona": self.persona.to_dict(),
            "instrument": self.instrument.to_dict(),
            "trajectory": [event.to_dict() for event in self.trajectory],
            "answers": [answer.to_dict() for answer in self.answers],
            "metrics": self.metrics.to_dict(),
            "createdAt": self.created_at,
            "prompts": dict(self.prompts),
        }
        if self.usage:
            payload["usage"] = dict(self.usage)
        return payload


def _read_artifact_json(path: Path) -> dict[str, Any]:
    data = path.read_text(encoding="utf-8")
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError("{} must contain a JSON object".format(path.name))
    return payload


def _normalize_survey_artifact_answers(
    instrument: SurveyInstrument,
    raw_answers: Any,
) -> list[SurveyAnswer]:
    if not isinstance(raw_answers, list):
        raise ValueError("survey_result.answers must be a list")
    question_by_id = {question.id: question for question in instrument.questions}
    answers: list[SurveyAnswer] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_answers):
        if not isinstance(raw, dict):
            raise ValueError("survey_result.answers[{}] must be an object".format(index))
        answer = SurveyAnswer.from_dict(raw)
        question = question_by_id.get(answer.question_id)
        if question is None:
            raise ValueError("unknown answer questionId: {}".format(answer.question_id))
        if answer.question_id in seen:
            raise ValueError("duplicate answer questionId: {}".format(answer.question_id))
        seen.add(answer.question_id)
        if question.type == "likert":
            try:
                number = float(answer.value)
            except (TypeError, ValueError):
                raise ValueError(
                    "answer {} must be numeric for likert question".format(question.id)
                ) from None
            min_value = float(question.min_value or 1)
            max_value = float(question.max_value or 5)
            if number < min_value or number > max_value:
                raise ValueError(
                    "answer {} must be between {} and {}".format(
                        question.id,
                        question.min_value,
                        question.max_value,
                    )
                )
            answer.value = int(number) if number.is_integer() else number
        elif question.type == "single_choice":
            value = str(answer.value)
            if value not in question.options:
                raise ValueError(
                    "answer {} must be one of {}".format(
                        question.id, ", ".join(question.options)
                    )
                )
            answer.value = value
        elif question.type == "multi_choice":
            if not isinstance(answer.value, list):
                raise ValueError("answer {} must be a list".format(question.id))
            values = [str(value) for value in answer.value]
            invalid = [value for value in values if value not in question.options]
            if invalid:
                raise ValueError(
                    "answer {} includes invalid choices: {}".format(
                        question.id, ", ".join(invalid)
                    )
                )
            answer.value = values
        else:
            answer.value = str(answer.value or "")
            if question.required and not answer.value.strip():
                raise ValueError("answer {} must not be empty".format(question.id))
        answers.append(answer)
    missing = [
        question.id
        for question in instrument.questions
        if question.required and question.id not in seen
    ]
    if missing:
        raise ValueError(
            "survey_result.answers missing required question ids: {}".format(
                ", ".join(missing)
            )
        )
    return answers


def _normalize_survey_artifact_trajectory(raw_trajectory: Any) -> list[TrajectoryEvent]:
    if not isinstance(raw_trajectory, list) or not raw_trajectory:
        raise ValueError("survey_result.trajectory must be a non-empty list")
    events: list[TrajectoryEvent] = []
    for index, raw in enumerate(raw_trajectory):
        if not isinstance(raw, dict):
            raise ValueError(
                "survey_result.trajectory[{}] must be an object".format(index)
            )
        events.append(TrajectoryEvent.from_dict(raw))
    return events


def _normalize_survey_prompts(prompts: dict[str, Any] | None) -> dict[str, str]:
    data = prompts or {}
    return {
        str(key): str(value).strip()
        for key, value in data.items()
        if isinstance(key, str) and value is not None and str(value).strip()
    }


def _config_with_artifact_language(
    config: SurveyEvalConfig,
    payload: dict[str, Any],
) -> SurveyEvalConfig:
    """Recover the recorded runtime language without consulting the host env."""
    raw_config = payload.get("config")
    artifact_config = raw_config if isinstance(raw_config, dict) else {}
    language = artifact_config.get(
        "effectiveLanguage",
        artifact_config.get(
            "personaLanguage",
            artifact_config.get("persona_language", payload.get("effectiveLanguage")),
        ),
    )
    source = artifact_config.get(
        "languageSource",
        artifact_config.get(
            "personaLanguageSource",
            artifact_config.get("persona_language_source", payload.get("languageSource")),
        ),
    )
    if language is None and source is None:
        return config
    resolution = resolve_persona_language_with_source(
        language if language is not None else config.persona_language,
        requested_source=source if source is not None else config.persona_language_source,
        environ={},
    )
    return replace(
        config,
        persona_language=resolution.language,
        persona_language_source=resolution.source,
    )


def build_survey_eval_result_from_artifacts(
    *,
    output_dir: Path,
    config: SurveyEvalConfig,
    persona: Persona,
    instrument: SurveyInstrument,
    created_at: str,
    prompts: dict[str, Any] | None = None,
) -> SurveyEvalResult:
    payload = _read_artifact_json(output_dir / "survey_result.json")
    config = _config_with_artifact_language(config, payload)
    artifact_instrument = payload.get("instrument")
    if isinstance(artifact_instrument, dict):
        artifact_id = str(artifact_instrument.get("id", "")).strip()
        if artifact_id and artifact_id != instrument.id:
            raise ValueError(
                "survey_result.instrument.id mismatch: expected {}, got {}".format(
                    instrument.id, artifact_id
                )
            )
    answers = _normalize_survey_artifact_answers(instrument, payload.get("answers"))
    trajectory = _normalize_survey_artifact_trajectory(payload.get("trajectory"))
    likert_values: list[float] = []
    question_by_id = {question.id: question for question in instrument.questions}
    for answer in answers:
        question = question_by_id.get(answer.question_id)
        if question is None or question.type != "likert":
            continue
        try:
            likert_values.append(float(answer.value))
        except (TypeError, ValueError):
            continue
    mean = sum(likert_values) / len(likert_values) if likert_values else None
    artifact_prompts = prompts if prompts is not None else payload.get("prompts")
    if not isinstance(artifact_prompts, dict):
        artifact_prompts = None
    return SurveyEvalResult(
        config=config,
        persona=persona,
        instrument=instrument,
        answers=answers,
        trajectory=trajectory,
        metrics=SurveyMetrics(
            num_questions=len(instrument.questions),
            num_answered=len(answers),
            mean_likert=mean,
        ),
        created_at=created_at,
        prompts=_normalize_survey_prompts(artifact_prompts),
    )


def survey_result_view(result: SurveyEvalResult) -> dict[str, Any]:
    """Return the UI/API survey artifact view for Harbor trial debriefs."""
    answered_ids = {answer.question_id for answer in result.answers}
    missing = [
        question.id
        for question in result.instrument.questions
        if question.required and question.id not in answered_ids
    ]
    metrics = result.metrics.to_dict()
    return {
        "effectiveLanguage": result.config.persona_language,
        "languageSource": result.config.persona_language_source,
        "instrument": result.instrument.to_dict(),
        "answers": [answer.to_dict() for answer in result.answers],
        "trajectory": [event.to_dict() for event in result.trajectory],
        "completion": {
            "numQuestions": metrics["numQuestions"],
            "numAnswered": metrics["numAnswered"],
            "missingQuestionIds": missing,
            "valid": not missing,
            "meanLikert": metrics["meanLikert"],
        },
        "createdAt": result.created_at,
        "prompts": dict(result.prompts),
    }
