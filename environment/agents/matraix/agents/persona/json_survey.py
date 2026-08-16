"""Host-native survey agent for Harbor's survey host path."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.agent.name import AgentName

from playground.harbor.playground import resolve_repo_root
from playground.survey_task_content import (
    load_survey_task_content_for_questionnaire_id,
    load_survey_task_content_for_task_path,
)
from playground.harbor.trial_events import TrialEventWriter
from backend.service.survey_types import SurveyEvalConfig
from playground.inprocess.survey_eval import InprocessSurveyEvalRunner
from playground.persona_model import resolve_persona_model
from matraix.agents.persona.mixin import PersonaMixin
from playground.types import Persona as EvalPersona


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _eval_persona(persona: object) -> EvalPersona:
    """Map Harbor persona → EvalPersona metadata for survey results.

    Prompt text does **not** come from ``summary`` / ``context`` (unused on
    dimensions cohorts). Harbor always passes ``persona_yaml_path`` so the
    runner renders the YAML via ``render_persona_block``.
    """
    data = getattr(persona, "data", {}) or {}
    return EvalPersona(
        id=str(getattr(persona, "persona_id", None) or data.get("persona_id") or "persona"),
        name=str(getattr(persona, "display_name", None) or data.get("name") or "Persona"),
        source=str(data.get("source") or ""),
    )


def _load_survey_content(*, task_path: str | None, instrument_path: str | None):
    from backend.service.survey_types import SurveyInstrument

    if instrument_path:
        path = Path(instrument_path).expanduser()
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                instrument = SurveyInstrument.from_dict(payload)
                return instrument, None
    resolved_task_path = str(task_path or os.environ.get("MATRIX_SURVEY_TASK_PATH") or "").strip()
    if resolved_task_path:
        content = load_survey_task_content_for_task_path(
            resolved_task_path,
            repo_root=_repo_root(),
        )
        if content.instrument is None:
            raise FileNotFoundError(
                "survey task {} is missing input/questionnaire.yaml".format(resolved_task_path)
            )
        return content.instrument, content
    raise ValueError(
        "survey host runs require survey_task_path or MATRIX_SURVEY_TASK_PATH"
    )


def _survey_result_payload(result) -> dict[str, object]:
    payload: dict[str, object] = {
        "instrument": {
            "id": result.instrument.id,
            "title": result.instrument.title,
        },
        "answers": [answer.to_dict() for answer in result.answers],
        "trajectory": [event.to_dict() for event in result.trajectory],
    }
    if getattr(result, "usage", None):
        payload["usage"] = dict(result.usage)
    return payload


def _apply_usage_to_context(context: AgentContext, usage: dict | None) -> None:
    """Copy Survey LLM usage into Harbor ``AgentContext`` for trial/job rollup."""
    if not usage:
        return
    if usage.get("n_input_tokens") is not None:
        context.n_input_tokens = int(usage["n_input_tokens"])
    if usage.get("n_output_tokens") is not None:
        context.n_output_tokens = int(usage["n_output_tokens"])
    if usage.get("n_cache_tokens") is not None:
        context.n_cache_tokens = int(usage["n_cache_tokens"])
    if usage.get("cost_usd") is not None:
        context.cost_usd = float(usage["cost_usd"])
    meta = dict(context.metadata or {})
    for key in ("request_id", "model", "provider", "cost_source"):
        if usage.get(key) is not None:
            meta[key] = usage[key]
    if meta:
        context.metadata = meta


def _repo_root() -> Path:
    return resolve_repo_root(Path(__file__))


def _instruction_markdown_for_questionnaire(questionnaire) -> str:
    from backend.service.survey_instruction_builder import (
        render_survey_instruction_markdown,
    )

    content = load_survey_task_content_for_questionnaire_id(
        questionnaire.id,
        repo_root=_repo_root(),
        fallback_questionnaire=questionnaire,
    )
    if content is not None:
        full = content.combined_markdown().strip()
        if full:
            return full
    return render_survey_instruction_markdown(questionnaire)


class PersonaJsonSurvey(PersonaMixin, BaseAgent):
    """Complete a survey through the host-native structured output path."""

    SUPPORTS_WINDOWS = True

    @staticmethod
    def name() -> str:
        return AgentName.PERSONA_JSON_SURVEY.value

    def version(self) -> str:
        return "1.0.0"

    def __init__(
        self,
        logs_dir: Path,
        persona_path: str | None = None,
        persona_template_path: str | None = None,
        survey_task_path: str | None = None,
        survey_instrument_path: str | None = None,
        **kwargs,
    ) -> None:
        self._init_persona(
            persona_path,
            AgentName.PERSONA_JSON_SURVEY.value,
            persona_template_path=persona_template_path,
        )
        self._survey_task_path = survey_task_path
        self._survey_instrument_path = survey_instrument_path
        super().__init__(logs_dir=logs_dir, **kwargs)

    async def setup(self, environment: BaseEnvironment) -> None:
        return None

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        del instruction
        await self._prepare_persona_trial(environment)
        instrument, content = _load_survey_content(
            task_path=self._survey_task_path,
            instrument_path=self._survey_instrument_path,
        )
        persona = _eval_persona(self._persona)
        persona_yaml_path = str(self._persona.persona_path)
        created_at = _utc_now()
        trial_dir = self.logs_dir.parent
        job_dir = trial_dir.parent
        event_writer = TrialEventWriter.for_trial_dir(trial_dir)
        if content is None:
            content = load_survey_task_content_for_questionnaire_id(
                instrument.id,
                repo_root=_repo_root(),
                fallback_questionnaire=instrument,
            )
        instruction_md = (
            content.combined_markdown().strip()
            if content is not None and content.combined_markdown().strip()
            else _instruction_markdown_for_questionnaire(instrument)
        )
        (trial_dir / "instruction.md").write_text(instruction_md, encoding="utf-8")
        if content is not None:
            if content.instruction_markdown.strip():
                (trial_dir / "task_instruction.md").write_text(
                    content.instruction_markdown.strip(),
                    encoding="utf-8",
                )
            if content.context_markdown.strip():
                (trial_dir / "context.md").write_text(
                    content.context_markdown.strip(),
                    encoding="utf-8",
                )
            if content.questionnaire_markdown.strip():
                (trial_dir / "questionnaire.md").write_text(
                    content.questionnaire_markdown.strip(),
                    encoding="utf-8",
                )
            if content.output_schema_markdown.strip():
                (trial_dir / "output_schema.md").write_text(
                    content.output_schema_markdown.strip(),
                    encoding="utf-8",
                )
        event_writer.append({"type": "instruction", "markdown": instruction_md})

        def on_event(event: dict) -> None:
            event_writer.append(event)

        survey_config = SurveyEvalConfig(
            persona_model=resolve_persona_model(model_name=self.model_name),
        )
        result = InprocessSurveyEvalRunner()(
            persona,
            instrument,
            config=survey_config,
            created_at=created_at,
            on_event=on_event,
            persona_yaml_path=persona_yaml_path,
            job_dir=job_dir,
        )
        _apply_usage_to_context(context, result.usage)
        payload = _survey_result_payload(result)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            temp_path = Path(handle.name)
        try:
            await environment.upload_file(temp_path, "/app/output/survey_result.json")
        finally:
            temp_path.unlink(missing_ok=True)
