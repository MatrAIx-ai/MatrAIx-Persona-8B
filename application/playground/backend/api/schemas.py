"""Pydantic v2 request/response models for the Playground API.

These models mirror the wire contract one-to-one with the TypeScript types in
``web/src/lib/types.ts`` and the service-layer view objects
(:class:`~backend.service.trace_view.TraceView` output,
:class:`~backend.service.session.RecBotSession`, catalog items). The JSON wire
format is ``camelCase`` throughout, matching the rest of the contract and the
SPA.

Design notes:

* The service layer already produces plain ``dict`` views in exactly this shape
  (e.g. ``TurnView``, ``Session``, ``SessionSummary``). The response models are
  therefore deliberately permissive: they ``model_validate`` those dicts to
  validate / document the contract without forcing the service to construct
  pydantic objects. ``model_config = ConfigDict(extra="allow")`` lets
  forward-compatible extra fields (should the service add any) pass through
  rather than being silently dropped.
* Request models are strict where it matters (``message`` is required and
  trimmed-non-empty; ``config`` keys are validated downstream by
  :class:`~backend.service.config.ConfigManager`), but tolerant of partial
  configs so the PATCH/POST bodies stay ergonomic.
* No backend (RecAI / numpy) import happens here; this module is stdlib +
  pydantic only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.service.config import PERSONA_MODEL_OPTIONS
from matraix.launch_env import (
    PERSONA_LANGUAGE_TOKENS,
    canonicalize_persona_language,
    normalize_persona_language_source,
)

__all__ = [
    "HealthResponse",
    "PreflightCheck",
    "PreflightResponse",
    "ConfigOptionValue",
    "ConfigKnob",
    "ConfigEnvironment",
    "ConfigOptionsResponse",
    "ChatMessageModel",
    "PlanStep",
    "StructuredExposureField",
    "TurnView",
    "SessionConfig",
    "Session",
    "SessionSummary",
    "CreateSessionRequest",
    "PatchConfigRequest",
    "PatchConfigResponse",
    "SubmitTurnRequest",
    "SubmitTurnResponse",
    "JobView",
    "CatalogItem",
    "CatalogSearchResponse",
    "PersonaSummary",
    "PlaygroundPersonasResponse",
    "PlaygroundPersonaDetail",
    "PlaygroundJobView",
    "SurveyQuestion",
    "SurveyInstrument",
    "SurveyInstrumentsResponse",
    "SurveyHarborTask",
    "SurveyHarborTasksResponse",
    "SurveyEvalJobView",
    "ChatbotEvalTask",
    "ChatbotEvalTasksResponse",
    "WebEvalTask",
    "WebEvalTasksResponse",
    "WebEvalJobView",
    "OsAppEvalTask",
    "OsAppEvalTasksResponse",
    "CuaEvalTask",
    "CuaEvalTasksResponse",
]

#: Domains the playground (and the rest of the Studio) supports. Mirrors the
#: ``domain`` option enumerated by
#: :class:`~backend.service.config.ConfigManager` (movie / beauty_product /
#: game) so a bad domain is rejected here with a clean 422.
SUPPORTED_DOMAINS = ("movie", "beauty_product", "game")
SUPPORTED_APPLICATION_IDS = (
    "finance_openbb",
    "acme_support_api",
    "acme_support_mcp",
    "meal_planning_nutrition",
)
DEFAULT_APPLICATION_CONTEXTS = {
    "finance_openbb": "financial_research",
    "acme_support_api": "customer_support",
    "acme_support_mcp": "customer_support",
    "meal_planning_nutrition": "meal_planning",
}

SUPPORTED_PERSONA_MODELS = tuple(PERSONA_MODEL_OPTIONS)
SUPPORTED_PERSONA_LANGUAGES = PERSONA_LANGUAGE_TOKENS

def _resolved_chat_context(
    *,
    domain: Optional[str],
    application_context: Optional[str],
    default_context: Optional[str],
) -> str:
    return str(application_context or default_context or domain or "").strip()


# --------------------------------------------------------------------------- #
# Health / preflight
# --------------------------------------------------------------------------- #
class HealthResponse(BaseModel):
    """``GET /api/health`` payload."""

    status: str = "ok"


class PreflightCheck(BaseModel):
    """One environment/resource readiness probe."""

    name: str
    ok: bool
    detail: str
    #: Coarse area this check belongs to ("Core" / "Chatbot" / "Survey" / "Web")
    #: so the UI can group the overall-readiness checklist. Optional for back-compat.
    group: Optional[str] = None
    #: Optional adapters report status but do not gate overall readiness.
    #: Required checks (optional=false) block ``ready``; optional ones are
    #: task-specific (Docker, use.computer, chat sidecars, per-provider keys).
    optional: bool = False
    #: When set, maps this probe to a chatbot application card in the cockpit.
    applicationId: Optional[str] = None


class PreflightResponse(BaseModel):
    """``GET /api/preflight`` payload."""

    ready: bool
    checks: List[PreflightCheck]


class ChatbotSidecarStatus(BaseModel):
    """Reachability of one chatbot HTTP sidecar."""

    applicationId: str
    ok: bool
    healthUrl: str
    canStart: bool = True
    detail: str


class ChatbotSidecarsResponse(BaseModel):
    """``GET /api/chatbot-sidecars`` payload."""

    sidecars: List[ChatbotSidecarStatus]


class StartChatbotSidecarResponse(BaseModel):
    """``POST /api/chatbot-sidecars/{application_id}/start`` payload."""

    sidecar: ChatbotSidecarStatus
    started: bool = True


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
class ConfigOptionValue(BaseModel):
    """One selectable value for an editable config knob, with display metadata."""

    model_config = ConfigDict(extra="allow")

    value: str
    label: str
    description: str = ""


class ConfigKnob(BaseModel):
    """One user-editable config knob and its allowed values.

    ``rebuildsAgent`` is ``True`` when changing this knob cold-starts the cached
    agent (a slower next turn); the UI surfaces that so the operator is not
    surprised.
    """

    model_config = ConfigDict(extra="allow")

    key: str
    label: str
    description: str = ""
    options: List[ConfigOptionValue] = Field(default_factory=list)
    rebuildsAgent: bool = False


class ConfigEnvironment(BaseModel):
    """Read-only facts about the fixed parts of the stack.

    ``runtime`` / ``personaAgent`` / ``personaModel`` / ``applicationApi`` /
    ``scorer`` report the in-process Playground execution boundary. The ranker,
    resources, and agent are adapter-specific and not user-configurable.
    ``promptOwnership`` reports the prompt boundary for in-process Harbor runs.
    """

    model_config = ConfigDict(extra="allow")

    runtime: str
    personaAgent: str
    personaModel: str
    applicationApi: str
    scorer: str
    cache: str
    ranker: str
    resources: str
    agent: str
    promptOwnership: Dict[str, str]


class ConfigOptionsResponse(BaseModel):
    """``GET /api/config/options`` payload.

    ``knobs`` is the list of user-editable config knobs (each with per-value
    labels/descriptions and a ``rebuildsAgent`` flag); ``defaults`` is the full
    canonical default config (every key, including the fixed ranker/resource
    modes); ``environment`` reports the fixed parts of the stack. All come
    straight from :meth:`~backend.service.config.ConfigManager.options`.
    """

    model_config = ConfigDict(extra="allow")

    knobs: List[ConfigKnob] = Field(default_factory=list)
    defaults: Dict[str, str]
    environment: ConfigEnvironment


# --------------------------------------------------------------------------- #
# Chat / turn view (TraceView.build output)
# --------------------------------------------------------------------------- #
class ChatMessageModel(BaseModel):
    """A single chat message in a session transcript."""

    role: str
    content: str


class PlanStep(BaseModel):
    """A parsed step of the agent's tool plan (best-effort)."""

    model_config = ConfigDict(extra="allow")

    tool: str
    detail: Optional[str] = None
    status: str = "ok"

    @field_validator("tool", mode="before")
    @classmethod
    def _coerce_tool(cls, value: Any) -> str:
        # Legacy artifacts may carry a non-string / missing tool name; coerce so
        # an old persisted session still opens (see ``TurnView.turnId``).
        if value is None:
            return "step"
        return value if isinstance(value, str) else str(value)


class StructuredExposureField(BaseModel):
    """One task-configured structured field visible on a turn."""

    model_config = ConfigDict(extra="allow")

    key: Optional[str] = None
    label: Optional[str] = None
    format: Optional[str] = "text"
    value: Any = None


class TurnView(BaseModel):
    """The fully-built view of one conversational turn.

    Mirrors :meth:`backend.service.trace_view.TraceView.build`. Extra fields are
    allowed so the service can enrich the view without breaking the schema.
    """

    model_config = ConfigDict(extra="allow")

    turnId: Optional[str] = None
    conversationId: Optional[str] = None
    backend: Optional[str] = None
    userMessage: Optional[str] = None
    assistantMessage: Optional[str] = None
    plan: List[PlanStep] = Field(default_factory=list)
    structuredExposure: List[StructuredExposureField] = Field(default_factory=list)
    nativeRaw: Optional[str] = None
    rawToolOutputs: Any = None

    @field_validator("turnId", "conversationId", mode="before")
    @classmethod
    def _coerce_optional_str(cls, value: Any) -> Optional[str]:
        # Legacy persisted turns store ``turnId`` as an int (the native backend's
        # 0-based turn index); the wire/UI contract treats it as a string.
        # Coerce int -> str here so an old session opens instead of 500-ing on
        # response validation. ``None`` stays ``None``.
        if value is None or isinstance(value, str):
            return value
        return str(value)


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #
class SessionConfig(BaseModel):
    """Full session configuration (camelCase on the wire)."""

    model_config = ConfigDict(extra="allow")

    engine: str
    rankerMode: str
    resourceMode: str
    domain: str
    botType: str


class Session(BaseModel):
    """Full session record. Mirrors
    :meth:`backend.service.session.RecBotSession.to_dict`."""

    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    config: Dict[str, Any]
    messages: List[ChatMessageModel] = Field(default_factory=list)
    turns: List[TurnView] = Field(default_factory=list)
    createdAt: str


class SessionSummary(BaseModel):
    """Lightweight session entry for the left rail. Mirrors
    :meth:`backend.service.session.RecBotSession.summary`."""

    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    config: Dict[str, Any]
    turnCount: int = 0
    messageCount: int = 0
    createdAt: Optional[str] = None


class CreateSessionRequest(BaseModel):
    """Body for ``POST /api/sessions``. Both fields optional."""

    title: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class PatchConfigRequest(BaseModel):
    """Body for ``PATCH /api/sessions/{id}/config``."""

    config: Dict[str, Any]


class PatchConfigResponse(BaseModel):
    """Response of ``PATCH /api/sessions/{id}/config``."""

    session: Session
    cacheInvalidated: bool


# --------------------------------------------------------------------------- #
# Turns & jobs (async)
# --------------------------------------------------------------------------- #
class SubmitTurnRequest(BaseModel):
    """Body for ``POST /api/sessions/{id}/turns``."""

    message: str


class SubmitTurnResponse(BaseModel):
    """Response of ``POST /api/sessions/{id}/turns``."""

    jobId: str


class JobView(BaseModel):
    """``GET /api/jobs/{jobId}`` payload.

    ``status`` is one of ``building | running | done | error``. ``turn`` is
    populated only on ``done``; ``error`` only on ``error``.
    """

    model_config = ConfigDict(extra="allow")

    jobId: str
    status: str
    turn: Optional[TurnView] = None
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
class CatalogItem(BaseModel):
    """A normalized catalog item (the subset the UI surfaces).

    Built from a raw ``items.jsonl`` line, which uses snake_case keys
    (``item_id`` / ``display_text``); :func:`~backend.api.routes` adapts those to
    the camelCase wire shape before validation, but ``extra="allow"`` keeps the
    adapter forgiving.
    """

    model_config = ConfigDict(extra="allow")

    itemId: str
    title: Optional[str] = None
    description: Optional[str] = None
    displayText: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CatalogSearchResponse(BaseModel):
    """``GET /api/catalog/search`` payload."""

    items: List[CatalogItem]
    total: int


# --------------------------------------------------------------------------- #
# Playground persona catalog + Harbor debrief views
# --------------------------------------------------------------------------- #
class PersonaSummary(BaseModel):
    """A persona as surfaced by ``GET /api/playground/personas``.

    Domain-free: the lightweight subset the PersonaPicker needs, built from
    :class:`playground.types.Persona`. ``source`` is the curated dataset the
    persona came from (e.g. ``Nemotron``); ``blurb`` is a short preview of the
    persona context.
    """

    id: str
    name: str
    source: str
    blurb: str


class PlaygroundPersonasResponse(BaseModel):
    """``GET /api/playground/personas`` payload.

    The full (un-filtered) persona catalog, honoring optional ``q``/``limit``
    search.
    """

    model_config = ConfigDict(extra="allow")

    personas: List[PersonaSummary]


class PlaygroundPersonaDetail(BaseModel):
    """``GET /api/playground/personas/{id}`` payload — one full persona.

    Carries the complete, humanized ``context`` block (multi-line, far richer
    than the list ``blurb``) so the catalog's "full persona" view can show
    everything without waiting for a run.
    """

    id: str
    name: str
    source: str
    context: str


class PlaygroundJobView(BaseModel):
    """Harbor chatbot debrief/live view shape used by the Cockpit."""

    model_config = ConfigDict(extra="allow")

    jobId: str
    domain: str
    applicationId: Optional[str] = None
    applicationContext: Optional[str] = None
    personaId: str
    personaName: str
    sutDescription: str
    status: str
    phase: Optional[str] = None
    turns: List[TurnView] = Field(default_factory=list)
    questionnaire: Optional[Dict[str, Any]] = None
    metricScores: Optional[Dict[str, Any]] = None
    prompts: Optional[Dict[str, str]] = None
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
# Survey eval
# --------------------------------------------------------------------------- #
class SurveyQuestion(BaseModel):
    """One survey question in a task-owned questionnaire."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    prompt: str
    type: str
    options: List[str] = Field(default_factory=list)
    optionDetails: List[Dict[str, str]] = Field(default_factory=list)
    minValue: Optional[int] = None
    maxValue: Optional[int] = None
    construct_: str = Field(default="", alias="construct")
    required: bool = True


class SurveyInstrument(BaseModel):
    """A task-backed survey questionnaire available for persona-agent completion."""

    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    description: str = ""
    questions: List[SurveyQuestion] = Field(default_factory=list)


class SurveyInstrumentsResponse(BaseModel):
    """``GET /api/survey-eval/instruments`` payload."""

    instruments: List[SurveyInstrument]


class SurveyHarborTask(BaseModel):
    """Summary row for ``GET /api/survey-eval/harbor-tasks``.

    Full markdown and questionnaire bodies live on ``GET /api/tasks/detail``.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    description: str = ""
    taskPath: str
    instrumentId: str = ""
    questionCount: Optional[int] = None
    profileMarkdown: str = ""
    instructionMarkdown: str = ""
    contextMarkdown: str = ""
    questionnaireMarkdown: str = ""
    outputSchemaMarkdown: str = ""
    questionnaire: Optional[SurveyInstrument] = None
    surveyKind: Literal["example", "contributing"] = "contributing"
    metaType: str = "survey"
    domain: str = ""
    difficulty: str = "easy"
    taskKind: Literal["example", "task"] = "task"


class SurveyHarborTasksResponse(BaseModel):
    """``GET /api/survey-eval/harbor-tasks`` payload."""

    tasks: List[SurveyHarborTask]


class SurveyEvalJobView(BaseModel):
    """Harbor survey debrief/live view shape used by the Cockpit."""

    model_config = ConfigDict(extra="allow")

    jobId: str
    applicationType: str = "survey"
    taskId: str = "survey_form"
    instrumentId: str
    instrumentTitle: str
    personaId: str
    personaName: str
    status: str
    phase: Optional[str] = None
    surveyResult: Optional[Dict[str, Any]] = None
    prompts: Optional[Dict[str, str]] = None
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
# Chatbot eval
# --------------------------------------------------------------------------- #
class ChatbotEvalTask(BaseModel):
    """Summary row for ``GET /api/chatbot-eval/tasks``.

    Live sidecar availability is merged client-side from ``GET /api/chatbot-sidecars``.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    description: str = ""
    taskPath: str
    transport: str = "http"
    applicationId: str = ""
    applicationContext: str = ""
    defaultDomain: str = ""
    metaType: str = "chatbot"
    domain: str = ""
    difficulty: str = "easy"
    taskKind: Literal["example", "task"] = "task"
    canStart: bool = False
    healthUrl: str = ""
    available: Optional[bool] = None
    statusDetail: str = ""


class ChatbotEvalTasksResponse(BaseModel):
    """``GET /api/chatbot-eval/tasks`` payload."""

    tasks: List[ChatbotEvalTask]


# --------------------------------------------------------------------------- #
# Web eval
# --------------------------------------------------------------------------- #
class WebEvalTask(BaseModel):
    """Summary row for ``GET /api/web-eval/tasks``.

    Full markdown lives on ``GET /api/tasks/detail``.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    siteName: str
    siteUrl: str
    description: str = ""
    taskPath: str = ""
    metaType: str = "web"
    domain: str = ""
    difficulty: str = "easy"
    taskKind: Literal["example", "task"] = "task"
    outputArtifact: str = "web_result.json"
    submissionProfile: str = "web_result"


class WebEvalTasksResponse(BaseModel):
    """``GET /api/web-eval/tasks`` payload."""

    tasks: List[WebEvalTask]


class WebEvalJobView(BaseModel):
    """Harbor web debrief/live view shape used by the Cockpit."""

    model_config = ConfigDict(extra="allow")

    jobId: str
    applicationType: str = "web"
    taskId: str
    taskTitle: str
    siteName: str
    siteUrl: str
    personaId: str
    personaName: str
    status: str
    phase: Optional[str] = None
    webResult: Optional[Dict[str, Any]] = None
    trace: Optional[Dict[str, Any]] = None
    prompts: Optional[Dict[str, str]] = None
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
# OS app (computer-use) eval
# --------------------------------------------------------------------------- #
class OsAppEvalTask(BaseModel):
    """Summary row for ``GET /api/os-app-eval/tasks``.

    Full markdown lives on ``GET /api/tasks/detail``.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    platform: str
    description: str = ""
    taskPath: str
    metaType: str = ""
    os: str = ""
    domain: str = ""
    difficulty: str = "easy"
    taskKind: Literal["example", "task"] = "task"
    outputArtifact: str = "decision.json"
    osAppSubmissionProfile: Optional[str] = None
    environmentLabel: str = "persona-computer-1"
    osAppBackend: str = "docker"


class OsAppEvalTasksResponse(BaseModel):
    """``GET /api/os-app-eval/tasks`` payload."""

    tasks: List[OsAppEvalTask]


# Deprecated aliases (older clients).
CuaEvalTask = OsAppEvalTask
CuaEvalTasksResponse = OsAppEvalTasksResponse


# --------------------------------------------------------------------------- #
# Harbor batch jobs (jobs_dir — canonical artifact root)
# --------------------------------------------------------------------------- #
class HarborJobLaunchRequest(BaseModel):
    """Body for ``POST /api/harbor/jobs``."""

    taskPath: str
    sampleSize: int = 1
    seed: int = 42
    personaPool: str = "persona/datasets/matraix-persona-dev-sample"
    personaIds: Optional[List[str]] = None
    personaSources: Optional[List[str]] = None
    personaFilters: Optional[Dict[str, str]] = None
    cohortId: Optional[str] = None
    useEntirePool: bool = False
    agentName: Optional[str] = None
    personaModel: Optional[str] = None
    nConcurrentTrials: int = 2
    mode: str = "auto"
    plane: Optional[str] = None
    jobName: Optional[str] = None
    osAppSubmissionProfile: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("osAppSubmissionProfile", "cuaSubmissionProfile"),
    )
    osAppBackend: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("osAppBackend", "cuaBackend"),
    )
    chatDomain: Optional[str] = None
    chatApplicationId: Optional[str] = None
    chatApplicationContext: Optional[str] = None
    chatMaxTurns: Optional[int] = None
    # Runtime/persona language. A language without a source is an explicit
    # API/CLI override; follow_ui is the only UI-derived source. env/default
    # provenance is resolved internally by the backend and never accepted
    # from a caller.
    language: Optional[str] = None
    languageSource: Optional[str] = None

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        canonical = canonicalize_persona_language(value)
        if canonical is None:
            raise ValueError(
                "language must be one of {} or a supported locale".format(
                    ", ".join(SUPPORTED_PERSONA_LANGUAGES)
                )
            )
        return canonical

    @field_validator("languageSource")
    @classmethod
    def _validate_language_source(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            return normalize_persona_language_source(value)
        except ValueError as exc:
            raise ValueError(
                "languageSource must be follow_ui, explicit, or null "
                "(env/default provenance is derived server-side): {}".format(exc)
            ) from exc

    @model_validator(mode="after")
    def _validate_language_source_pair(self) -> "HarborJobLaunchRequest":
        if self.language is None and self.languageSource is not None:
            raise ValueError("languageSource requires language")
        if self.language is not None and self.languageSource is None:
            self.languageSource = "explicit"
        return self

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"auto", "force_docker", "smoke"}:
            raise ValueError("mode must be one of auto, force_docker, smoke")
        return normalized

    @field_validator("plane")
    @classmethod
    def _validate_plane(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in {"harbor", "remote"}:
            raise ValueError("plane must be one of harbor, remote")
        return normalized

    @field_validator("personaModel")
    @classmethod
    def _validate_persona_model(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if value not in SUPPORTED_PERSONA_MODELS:
            raise ValueError(
                "personaModel must be one of {}".format(list(SUPPORTED_PERSONA_MODELS))
            )
        return value

    @field_validator("chatApplicationId")
    @classmethod
    def _validate_chat_application_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if value not in SUPPORTED_APPLICATION_IDS:
            raise ValueError(
                "chatApplicationId must be one of {}".format(
                    list(SUPPORTED_APPLICATION_IDS)
                )
            )
        return value

    @model_validator(mode="after")
    def _normalize_chat_application_context(self) -> "HarborJobLaunchRequest":
        if not self.chatApplicationId:
            return self
        default_context = DEFAULT_APPLICATION_CONTEXTS.get(self.chatApplicationId)
        resolved_context = _resolved_chat_context(
            domain=self.chatDomain,
            application_context=self.chatApplicationContext,
            default_context=default_context,
        )
        self.chatApplicationContext = resolved_context
        if not self.chatApplicationContext:
            raise ValueError("chatApplicationContext is required")
        return self


class HarborJobLaunchResponse(BaseModel):
    jobName: str
    configPath: Optional[str] = None
    jobsDir: Optional[str] = None
    agentName: Optional[str] = None
    taskType: Optional[str] = None
    trialProfile: Optional[str] = None
    mode: Optional[str] = None
    plane: Optional[str] = None
    effectiveLanguage: Optional[str] = None
    languageSource: Optional[str] = None


class HarborJobsListResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    jobs: List[Dict[str, Any]]


class HarborJobDetailView(BaseModel):
    model_config = ConfigDict(extra="allow")

    jobName: str
    jobsDir: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    trials: List[Dict[str, Any]] = Field(default_factory=list)
    launch: Optional[Dict[str, Any]] = None


class PersonaPoolCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    pool: str
    count: int
    smokePersonaId: Optional[str] = None
    sourceCounts: Dict[str, int] = Field(default_factory=dict)
    schemaVersion: Optional[str] = None
    dimensionCategoriesPath: Optional[str] = None
    dimensionCategories: Dict[str, Any] = Field(default_factory=dict)


class PersonaMatchAttributesRequest(BaseModel):
    """Free-text / NL prompt → catalog attribute suggestions (Treiver)."""

    prompt: str = ""
    useLlm: bool = False


class PersonaMatchedAttribute(BaseModel):
    model_config = ConfigDict(extra="allow")

    dimensionId: str
    label: str = ""
    value: str
    evidence: Optional[str] = None
    method: str = "regex"
    confidence: float = 0.0


class PersonaMatchAttributesResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt: str = ""
    attributes: List[PersonaMatchedAttribute] = Field(default_factory=list)
    usedLlm: bool = False


class PersonaDatasetOption(BaseModel):
    model_config = ConfigDict(extra="allow")

    pool: str
    label: str
    kind: str = "dataset"
    count: int = 0
    default: bool = False


class PersonaDatasetListResponse(BaseModel):
    datasets: List[PersonaDatasetOption] = Field(default_factory=list)
    defaultPool: str = "persona/datasets/matraix-persona-dev-sample"


class PersonaDatasetSaveRequest(BaseModel):
    """Promote a materialized pool (e.g. 1M cohort) to a named Dataset."""

    sourcePool: str
    name: str
    description: Optional[str] = None
    overwrite: bool = False


class PersonaDatasetSaveResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    pool: str
    label: str
    name: str
    count: int
    sourcePool: str
    kind: str = "dataset"


class PersonaPoolIdsResponse(BaseModel):
    pool: str
    personaIds: List[str] = Field(default_factory=list)
    count: int = 0
    idsTruncated: bool = False


class PersonaPoolSampleRequest(BaseModel):
    pool: str = "persona/datasets/matraix-persona-dev-sample"
    sampleSize: int = 4
    seed: int = 42
    sources: Optional[List[str]] = None
    dimensionFilters: Optional[Dict[str, Any]] = None
    fields: Optional[List[str]] = None
    """Stratify axes (same as ``sampling.fields``)."""
    perCell: Optional[int] = None
    """Personas per cell when ``allocation="perCell"``."""
    allocation: Optional[str] = None
    """Stratified allocation: perCell | proportional | equalTotal."""
    taskPath: Optional[str] = None
    """Optional task path — included in coverage error hints."""
    previewLimit: int = 32
    includePersonaIds: Optional[bool] = None


class PersonaPoolGenerateRequest(BaseModel):
    """Write a Full-DAG synthetic pool under ``persona/datasets/generated-persona-dev-*``."""

    count: Optional[int] = None
    seed: int = 42
    dimensionFilters: Optional[Dict[str, Any]] = None
    fields: Optional[List[str]] = None
    perCell: Optional[int] = None
    allocation: Optional[str] = None
    sampleSize: Optional[int] = None
    taskPath: Optional[str] = None
    """When set, fill that task's ``persona_strategy.json`` (one-time synthesize)."""
    name: Optional[str] = None


class PersonaPoolGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    pool: str
    label: str
    count: int
    dimensionCount: int = 0
    source: str = "synthetic"
    kind: str = "dataset"
    personaIds: List[str] = Field(default_factory=list)
    seed: int = 42


class TaskPersonaSampling(BaseModel):
    """Unified ``sampling`` block inside ``persona_strategy.json``."""

    model_config = ConfigDict(extra="allow")

    mode: str
    personaId: Optional[str] = None
    sampleSize: Optional[int] = None
    fields: Optional[List[str]] = None
    allocation: Optional[str] = None
    perCell: Optional[int] = None


class TaskPersonaStrategy(BaseModel):
    """Optional per-task Playground sampling defaults (``persona_strategy.json``)."""

    model_config = ConfigDict(extra="allow")

    schemaVersion: str = "1.0"
    pool: Optional[str] = None
    sources: List[str] = Field(default_factory=list)
    dimensionFilters: Dict[str, List[str]] = Field(default_factory=dict)
    seed: Optional[int] = None
    cohortId: Optional[str] = None
    sampling: Optional[TaskPersonaSampling] = None


class PersonaPoolPersonaCard(BaseModel):
    model_config = ConfigDict(extra="allow")

    personaId: str
    name: Optional[str] = None
    source: Optional[str] = None
    path: Optional[str] = None
    dimensions: Dict[str, str] = Field(default_factory=dict)


class PersonaPoolCardsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    pool: str
    personas: List[PersonaPoolPersonaCard] = Field(default_factory=list)


class PersonaDimensionItem(BaseModel):
    id: str
    label: str
    value: str
    category: str = ""


class PersonaDimensionSubgroup(BaseModel):
    id: str
    label: str
    count: int = 0
    items: List[PersonaDimensionItem] = Field(default_factory=list)


class PersonaDimensionGroup(BaseModel):
    id: str
    label: str
    count: int = 0
    subgroups: List[PersonaDimensionSubgroup] = Field(default_factory=list)


class PersonaPoolPersonaDetailResponse(PersonaPoolPersonaCard):
    model_config = ConfigDict(extra="allow")

    pool: str
    path: Optional[str] = None
    yaml: str = ""
    profileMarkdown: str = ""
    dimensionGroups: List[PersonaDimensionGroup] = Field(default_factory=list)


class TaskPersonaStrategyResponse(BaseModel):
    """``GET /api/tasks/persona-strategy`` payload."""

    personaStrategy: Optional[TaskPersonaStrategy] = None


class TaskDetailResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    taskPath: str
    title: str = ""
    description: str = ""
    metaType: str = ""
    taskName: str = ""
    instructionMarkdown: str = ""
    contextMarkdown: str = ""
    questionnaireMarkdown: str = ""
    outputSchemaMarkdown: str = ""
    selfReportMarkdown: str = ""
    questionnaire: Optional[SurveyInstrument] = None
    personaStrategy: Optional[TaskPersonaStrategy] = None
    profileMarkdown: str = ""


class PersonaPoolSampleResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    pool: str
    matchedCount: int
    sampleSize: int
    seed: int
    personaIds: List[str] = Field(default_factory=list)
    personas: List[Dict[str, Any]] = Field(default_factory=list)
    selectedCount: Optional[int] = None
    idsTruncated: bool = False


class PersonaCohortSaveRequest(BaseModel):
    cohortId: str
    name: Optional[str] = None
    description: Optional[str] = None
    pool: str = "persona/datasets/matraix-persona-dev-sample"
    kind: str = "recipe"
    seed: int = 42
    sampleSize: int = 4
    sources: Optional[List[str]] = None
    dimensionFilters: Optional[Dict[str, str]] = None
    personaIds: Optional[List[str]] = None

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"recipe", "frozen"}:
            raise ValueError("kind must be recipe or frozen")
        return normalized


class PersonaCohortSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    cohortId: str
    name: str
    kind: str
    pool: str
    sampleSize: int
    matchedCount: int
    personaCount: int
    createdAt: Optional[str] = None


class PersonaCohortListResponse(BaseModel):
    cohorts: List[PersonaCohortSummary] = Field(default_factory=list)


class PersonaCohortDetailResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    cohortId: str
    name: str
    description: str = ""
    createdAt: Optional[str] = None
    pool: str
    kind: str
    seed: int
    sampleSize: int
    sources: List[str] = Field(default_factory=list)
    dimensionFilters: Dict[str, str] = Field(default_factory=dict)
    matchedCount: int
    personaIds: List[str] = Field(default_factory=list)
    personas: List[Dict[str, Any]] = Field(default_factory=list)
