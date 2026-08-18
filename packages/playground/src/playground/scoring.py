from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from playground.self_report_task_config import (
    load_self_report_schema_for_task_path,
)
from playground.task_content_bundle import (
    load_task_content_bundle_for_task_path,
)
from playground.self_report_runtime import write_self_report_artifact
from playground.user_sim.chatbot_labels import chatbot_display_name
from playground.openai_client import OpenAIChatClient, coerce_json
from playground.types import Persona, PlaygroundConfig, PlaygroundTurn, Questionnaire
from playground.user_sim.prompt import assemble_report_system_prompt
from playground.user_sim.self_report import final_self_report


def _turn_from_view(index: int, turn: Dict[str, Any]) -> PlaygroundTurn:
    return PlaygroundTurn(
        turn_index=index,
        user_message=str(turn.get("userMessage") or ""),
        assistant_message=str(turn.get("assistantMessage") or ""),
        structured_exposure=[
            dict(item)
            for item in (turn.get("structuredExposure") or [])
            if isinstance(item, dict)
        ],
        decision=str(turn.get("decision") or "continue"),
        duration_seconds=turn.get("durationSeconds"),
    )


def _read_json_object(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError("{} must contain a JSON object".format(path))
    return value


def _turn_views_from_transcript(transcript: Dict[str, Any]) -> List[Dict[str, Any]]:
    turns = transcript.get("turns")
    if isinstance(turns, list) and all(isinstance(turn, dict) for turn in turns):
        return [dict(turn) for turn in turns]

    messages = transcript.get("messages") or []
    if not isinstance(messages, list):
        return []
    views: List[Dict[str, Any]] = []
    pending_user: Optional[str] = None
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = str(message.get("content") or "")
        if role == "user":
            pending_user = content
        elif role == "assistant" and pending_user is not None:
            views.append(
                {
                    "turnId": str(len(views)),
                    "userMessage": pending_user,
                    "assistantMessage": content,
                }
            )
            pending_user = None
    return views


def _config_from_dict(value: Dict[str, Any]) -> PlaygroundConfig:
    raw_max_turns = value.get("maxTurns", value.get("max_turns"))
    return PlaygroundConfig(
        domain=str(value.get("domain") or "movie"),
        application_id=str(
            value.get(
                "applicationId",
                value.get("application_id", "meal_planning_nutrition"),
            )
        ),
        application_context=str(
            value.get(
                "applicationContext",
                value.get("application_context", value.get("domain") or "movie"),
            )
        ),
        engine=str(value.get("engine") or "gpt-4o-mini"),
        persona_model=str(
            value.get(
                "personaModel", value.get("persona_model", "anthropic/claude-haiku-4-5")
            )
        ),
        ranker_mode=str(value.get("rankerMode", value.get("ranker_mode", "native"))),
        resource_mode=str(
            value.get("resourceMode", value.get("resource_mode", "recai_resources"))
        ),
        max_turns=int(raw_max_turns) if raw_max_turns not in (None, "") else None,
        persona_language=str(
            value.get(
                "effectiveLanguage",
                value.get(
                    "effective_language",
                    value.get("personaLanguage", value.get("persona_language", "en")),
                ),
            )
            or "en"
        ),
        persona_language_source=str(
            value.get(
                "languageSource",
                value.get(
                    "language_source",
                    value.get(
                        "personaLanguageSource",
                        value.get("persona_language_source", "default"),
                    ),
                ),
            )
            or "default"
        ),
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


class StdlibOpenAIChatClient:
    """Small OpenAI JSON-mode client for Harbor verifier containers."""

    def __init__(
        self,
        model: str,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        timeout_seconds: float = 90.0,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (
            base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        ).rstrip("/")
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds

    def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for application scoring")
        body = json.dumps(
            {
                "model": self.model,
                "temperature": self.temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "{}/chat/completions".format(self.base_url),
            data=body,
            headers={
                "Authorization": "Bearer {}".format(self.api_key),
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                "OpenAI scoring request failed: {}".format(detail[:500])
            ) from exc
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("OpenAI scoring response did not include choices")
        message = choices[0].get("message") or {}
        return coerce_json(str(message.get("content") or ""))


class OriginalPromptFeedbackScorer:
    """Score Harbor recommender runs with the original playground prompt."""

    def __init__(
        self,
        *,
        client_factory: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self.client_factory = client_factory or (
            lambda model: OpenAIChatClient(model=model)
        )

    def __call__(
        self,
        *,
        persona: Persona,
        sut_description: str,
        config: PlaygroundConfig,
        turn_views: List[Dict[str, Any]],
        task_path: str | None = None,
    ) -> Questionnaire:
        del sut_description
        repo_root = _repo_root()
        task_bundle = (
            load_task_content_bundle_for_task_path(task_path, repo_root=repo_root)
            if task_path
            else None
        )
        schema = (
            load_self_report_schema_for_task_path(task_path, repo_root=repo_root)
            if task_path
            else None
        )
        system_prompt = assemble_report_system_prompt(
            persona,
            task_bundle=task_bundle,
            persona_language=config.effective_language,
        )
        transcript = [
            _turn_from_view(index, turn) for index, turn in enumerate(turn_views)
        ]
        return final_self_report(
            self.client_factory(config.engine),
            system_prompt=system_prompt,
            persona=persona,
            transcript=transcript,
            schema=schema,
            chatbot_label=chatbot_display_name(config.application_id),
        )


def score_harbor_artifacts(
    *,
    transcript_path: Path,
    application_path: Path,
    output_path: Path,
    persona: Persona,
    sut_description: str,
    config: PlaygroundConfig,
    client_factory: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Score Harbor chatbot artifacts and write the questionnaire artifact."""
    _ = application_path  # legacy path kept for Harbor verifier layout
    transcript = _read_json_object(Path(transcript_path))
    turn_views = _turn_views_from_transcript(transcript)
    scorer = OriginalPromptFeedbackScorer(
        client_factory=client_factory
        or (lambda model: StdlibOpenAIChatClient(model=model))
    )
    questionnaire = scorer(
        persona=persona,
        sut_description=sut_description,
        config=config,
        turn_views=turn_views,
        task_path=os.environ.get("MATRIX_CHATBOT_TASK_PATH"),
    )
    output = Path(output_path)
    artifact = questionnaire.artifact_dict()
    write_self_report_artifact(artifact, output_path=output)
    return artifact


def score_harbor_artifacts_from_env(
    *,
    transcript_path: Path,
    application_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    client_factory: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Environment-driven entry point used by the Harbor verifier."""
    persona_payload = os.environ.get("MATRIX_SCORER_PERSONA_JSON")
    config_payload = os.environ.get("MATRIX_SCORER_CONFIG_JSON")
    if not persona_payload:
        raise ValueError("MATRIX_SCORER_PERSONA_JSON is required")
    if not config_payload:
        raise ValueError("MATRIX_SCORER_CONFIG_JSON is required")
    persona = Persona.from_dict(json.loads(persona_payload))
    config = _config_from_dict(json.loads(config_payload))
    sut_description = os.environ.get("MATRIX_SCORER_SUT_DESCRIPTION", "")
    target = Path(
        os.environ.get("MATRIX_SCORER_OUTPUT_PATH")
        or str(output_path or Path(transcript_path).with_name("user_feedback.json"))
    )
    return score_harbor_artifacts(
        transcript_path=Path(transcript_path),
        application_path=Path(application_path)
        if application_path is not None
        else Path(transcript_path).with_name("application_result.json"),
        output_path=target,
        persona=persona,
        sut_description=sut_description,
        config=config,
        client_factory=client_factory,
    )
