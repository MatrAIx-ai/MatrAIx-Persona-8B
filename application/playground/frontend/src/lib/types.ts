export type Domain = "movie" | "beauty_product" | "game" | string;
export type ApplicationId =
  | "meal_planning_nutrition"
  | "finance_openbb"
  | "acme_support_api"
  | "acme_support_mcp"
  | string;
export type Engine = string;
export type PersonaModel = string;

export interface ConfigOptionValue {
  value: string;
  label: string;
  description?: string;
}

export interface ConfigKnob {
  key: string;
  label: string;
  description?: string;
  options: ConfigOptionValue[];
  rebuildsAgent?: boolean;
}

export interface ConfigEnvironment {
  runtime: string;
  personaAgent: string;
  personaModel: string;
  applicationApi: string;
  scorer: string;
  cache: string;
  ranker: string;
  resources: string;
  agent: string;
  promptOwnership?: Record<string, string>;
}

export interface ConfigOptionsResponse {
  knobs: ConfigKnob[];
  defaults: SessionConfig;
  environment: ConfigEnvironment;
}

export interface PreflightCheck {
  name: string;
  ok: boolean;
  detail: string;
  group?: string | null;
  optional?: boolean;
  applicationId?: string | null;
}

export interface PreflightResponse {
  ready: boolean;
  checks: PreflightCheck[];
}

export interface ChatbotSidecarStatus {
  applicationId: string;
  ok: boolean;
  healthUrl: string;
  canStart: boolean;
  detail: string;
}

export interface ChatbotSidecarsResponse {
  sidecars: ChatbotSidecarStatus[];
}

export interface StartChatbotSidecarResponse {
  sidecar: ChatbotSidecarStatus;
  started: boolean;
}

export interface PlanStep {
  tool: string;
  detail?: string | null;
  status?: string;
}

export interface TurnView {
  turnId?: string | null;
  conversationId?: string | null;
  backend?: string | null;
  userMessage: string;
  assistantMessage: string;
  plan?: PlanStep[];
  structuredExposure?: StructuredExposureField[];
  nativeRaw?: string | null;
  rawToolOutputs?: unknown;
  durationSeconds?: number | null;
}

export interface StructuredExposureField {
  key?: string | null;
  label?: string | null;
  format?: string | null;
  value?: unknown;
}

export interface SessionConfig {
  engine?: string;
  rankerMode?: string;
  resourceMode?: string;
  domain?: Domain;
  botType?: string;
  applicationId?: ApplicationId;
  applicationContext?: string;
  [key: string]: unknown;
}

export interface Session {
  id: string;
  title: string;
  config: SessionConfig;
  messages: { role: string; content: string }[];
  turns: TurnView[];
  createdAt: string;
}

export interface SessionSummary {
  id: string;
  title: string;
  config: SessionConfig;
  turnCount: number;
  messageCount: number;
  createdAt?: string;
}

export interface PlaygroundPersona {
  id: string;
  name: string;
  source: string;
  blurb?: string;
  context?: string;
}

export interface PlaygroundPersonasResponse {
  personas: PlaygroundPersona[];
  sutDescription?: string | null;
}

export interface PlaygroundPrompts {
  personaPrompt?: string;
  harborPrompt?: string;
  taskPrompt?: string;
  scorerPrompt?: string;
  [key: string]: string | undefined;
}

export interface PlaygroundQuestionnaire {
  overallRating: number;
  ratingReason: string;
  constraintSatisfaction: number;
  constraintRationale: string;
  preferenceSatisfaction: number;
  preferenceRationale: string;
  askedUsefulClarifyingQuestions: boolean;
  clarifyingNotes: string;
  goalAchieved?: boolean | null;
  satisfaction?: number | null;
  frustration?: number | null;
  trust?: number | null;
  easeOfUse?: number | null;
  comments?: string | null;
  [key: string]: string | number | boolean | null | undefined;
}

/** Task-owned ``input/self_report_schema.yaml`` field (debrief / UI). */
export interface SelfReportSchemaField {
  key: string;
  prompt: string;
  kind: string;
  required?: boolean;
  minimum?: number | null;
  maximum?: number | null;
  choices?: string[];
  explains?: string | null;
}

export interface SelfReportSchema {
  artifactName?: string;
  instructions?: string;
  fields: SelfReportSchemaField[];
}

export interface UserFeedbackArtifact {
  [key: string]: string | number | boolean | null | undefined;
}

export interface PlaygroundMetricScores {
  numTurns: number;
  durationSeconds?: number | null;
  [key: string]: string | number | boolean | null | undefined;
}

export interface TrialEvaluationPresenceCheck {
  passed?: boolean;
  requiredArtifacts?: string[];
  missingArtifacts?: string[];
}

export interface TrialEvaluationFacet {
  key: string;
  label: string;
  role?: string | null;
  kind: "numerical" | "categorical" | "textual" | string;
  value?: string | number | boolean | null;
}

export interface TrialEvaluationContext {
  key: string;
  label: string;
  contextType?: string | null;
  facets: TrialEvaluationFacet[];
}

export interface TrialEvaluationArtifact {
  schemaVersion: string;
  artifactType: string;
  taskType?: string | null;
  presenceCheck?: TrialEvaluationPresenceCheck | null;
  sourceArtifacts?: Record<string, string | null> | null;
  contexts: TrialEvaluationContext[];
}

export interface HarborDraftTurn {
  turnIndex?: number;
  userMessage?: string;
  assistantMessage?: string;
  structuredExposure?: StructuredExposureField[];
  durationSeconds?: number | null;
}

export interface PlaygroundJobView {
  jobId: string;
  domain: string;
  applicationId?: string | null;
  applicationContext?: string | null;
  personaId: string;
  personaName: string;
  sutDescription: string;
  status: string;
  phase?: string | null;
  turns: TurnView[];
  draftTurn?: HarborDraftTurn | null;
  questionnaire?: PlaygroundQuestionnaire | null;
  metricScores?: PlaygroundMetricScores | null;
  prompts?: PlaygroundPrompts | null;
  error?: string | null;
}

export interface PlaygroundResult {
  id: string;
  createdAt?: string | null;
  config: Record<string, unknown>;
  persona: Record<string, unknown>;
  sutDescription?: string | null;
  transcript: TurnView[];
  questionnaire?: PlaygroundQuestionnaire | null;
  userFeedback?: UserFeedbackArtifact | null;
  metricScores?: PlaygroundMetricScores | null;
  prompts?: PlaygroundPrompts | null;
  applicationType?: string | null;
  [key: string]: unknown;
}

export interface SurveyQuestion {
  id: string;
  prompt: string;
  type: string;
  options: string[];
  optionDetails?: { id: string; label?: string; description?: string }[];
  minValue?: number | null;
  maxValue?: number | null;
  construct?: string | null;
  required?: boolean;
}

export interface SurveyInstrument {
  id: string;
  title: string;
  description?: string;
  questions: SurveyQuestion[];
}

export interface SurveyInstrumentsResponse {
  instruments: SurveyInstrument[];
}

export interface SurveyHarborTask {
  id: string;
  title: string;
  description: string;
  taskPath: string;
  instrumentId: string;
  questionCount?: number;
  profileMarkdown?: string;
  instructionMarkdown?: string;
  contextMarkdown?: string;
  questionnaireMarkdown?: string;
  outputSchemaMarkdown?: string;
  questionnaire?: SurveyInstrument | null;
  surveyKind?: "example" | "contributing";
  metaType?: string;
  domain?: string;
  difficulty?: string;
  taskKind?: "example" | "task";
  tags?: string[];
}

export interface SurveyHarborTasksResponse {
  tasks: SurveyHarborTask[];
}

export interface SurveyAnswer {
  questionId: string;
  value: string | number | boolean | string[] | null;
  rationale?: string | null;
  confidence?: number | null;
}

export interface SurveyTrajectoryEvent {
  timestamp?: string | null;
  actor: string;
  action: string;
  context?: Record<string, unknown>;
  outcome?: Record<string, unknown>;
}

/** Harbor test.sh verifier outcome from reward.txt (+ optional stdout). */
export interface VerifierSummary {
  passed: boolean;
  reward: number;
  detail?: string | null;
}

export interface SurveyResult {
  instrument: { id: string; title: string; questions: SurveyQuestion[] };
  answers: SurveyAnswer[];
  trajectory: SurveyTrajectoryEvent[];
  completion: {
    numAnswered: number;
    numQuestions: number;
    answered: number;
    total: number;
    valid: boolean;
    meanLikert?: number | null;
    freeTextCount?: number | null;
  };
  createdAt?: string | null;
  prompts?: PlaygroundPrompts | null;
}

export interface SurveyEvalJobView {
  jobId: string;
  applicationType: "survey";
  taskId: string;
  instrumentId: string;
  instrumentTitle: string;
  personaId: string;
  personaName: string;
  status: string;
  phase?: string | null;
  surveyResult?: SurveyResult | null;
  instructionMarkdown?: string | null;
  contextMarkdown?: string | null;
  questionnaireMarkdown?: string | null;
  outputSchemaMarkdown?: string | null;
  verifier?: VerifierSummary | null;
  prompts?: PlaygroundPrompts | null;
  error?: string | null;
}

export interface ChatbotEvalTask {
  id: string;
  title: string;
  description: string;
  taskPath: string;
  transport: string;
  applicationId: string;
  applicationContext: string;
  defaultDomain: string;
  metaType: string;
  domain: string;
  difficulty: string;
  taskKind?: "example" | "task";
  tags?: string[];
  available?: boolean | null;
  canStart?: boolean;
  healthUrl?: string;
  statusDetail?: string;
  capabilities?: Array<{
    id: string;
    label: string;
    description?: string;
    kind?: string;
    tool?: string;
  }>;
  profileMarkdown?: string;
  instructionMarkdown?: string;
  contextMarkdown?: string;
  outputSchemaMarkdown?: string;
}

export interface ChatbotEvalTasksResponse {
  tasks: ChatbotEvalTask[];
}

export interface WebEvalTask {
  id: string;
  title: string;
  siteName: string;
  siteUrl: string;
  description: string;
  taskPath?: string;
  metaType?: string;
  domain?: string;
  difficulty?: string;
  taskKind?: "example" | "task";
  tags?: string[];
  outputArtifact: string;
  submissionProfile: string;
  profileMarkdown?: string;
  instructionMarkdown?: string;
}

export interface WebEvalTasksResponse {
  tasks: WebEvalTask[];
}

export interface WebAction {
  name: string;
  arguments?: Record<string, unknown>;
}

export interface WebTraceEvent {
  step: number;
  source: string;
  message: string;
  actions: WebAction[];
  screenshotUrl?: string | null;
  screenshotFile?: string | null;
}

export interface WebTrace {
  events: WebTraceEvent[];
  raw?: Record<string, unknown>;
}

export interface WebResult {
  selectedProductId: string;
  selectedProductName: string;
  needSatisfaction: number;
  easeOfUse: number;
  informationQuality?: number | null;
  overallExperienceRating: number;
  overallQuality?: number | null;
  valid: boolean;
  reason: string;
  createdAt?: string | null;
}

export interface WebEvalJobView {
  jobId: string;
  applicationType: "web";
  taskId: string;
  taskTitle: string;
  siteName: string;
  siteUrl: string;
  personaId: string;
  personaName: string;
  status: string;
  phase?: string | null;
  webResult?: WebResult | null;
  trace?: WebTrace | null;
  verifier?: VerifierSummary | null;
  userFeedback?: UserFeedbackArtifact | null;
  prompts?: PlaygroundPrompts | null;
  error?: string | null;
}

export interface OsAppEvalTask {
  id: string;
  title: string;
  platform: string;
  os?: string;
  description?: string;
  taskPath: string;
  metaType?: string;
  domain?: string;
  difficulty?: string;
  taskKind?: "example" | "task";
  tags?: string[];
  outputArtifact?: string;
  osAppSubmissionProfile?: string | null;
  environmentLabel?: string;
  /** Harbor persona-computer-1 backend: docker | macos | ios (use.computer). */
  osAppBackend?: string;
  profileMarkdown?: string;
  instructionMarkdown?: string;
}

export interface OsAppEvalTasksResponse {
  tasks: OsAppEvalTask[];
}

export interface OsAppResult {
  success: boolean;
  score: number;
  artifactName?: string | null;
  artifact?: Record<string, unknown> | null;
  createdAt?: string | null;
}

export interface OsAppEvalJobView {
  jobId: string;
  applicationType: "os-app";
  taskId: string;
  taskTitle: string;
  platform: string;
  personaId: string;
  personaName: string;
  status: string;
  phase?: string | null;
  osAppResult?: OsAppResult | null;
  trace?: WebTrace | null;
  verifier?: VerifierSummary | null;
  userFeedback?: UserFeedbackArtifact | null;
  prompts?: PlaygroundPrompts | null;
  error?: string | null;
}

/** @deprecated Use OsAppEvalTask */
export type CuaEvalTask = OsAppEvalTask;
/** @deprecated Use OsAppEvalTasksResponse */
export type CuaEvalTasksResponse = OsAppEvalTasksResponse;
/** @deprecated Use OsAppResult */
export type CuaResult = OsAppResult;
/** @deprecated Use OsAppEvalJobView */
export type CuaEvalJobView = OsAppEvalJobView;

export type HarborJobListStatus = "running" | "success" | "failed";

export interface HarborJobSummary {
  jobName: string;
  applicationType?: string | null;
  /** Display title derived from ``task.toml`` ``[task].name``. */
  taskTitle?: string | null;
  /** Full Harbor task name, e.g. ``application/chat-meal-planning-nutrition``. */
  taskName?: string | null;
  domain?: string | null;
  difficulty?: string | null;
  tags?: string[];
  metaType?: string | null;
  trialCount: number;
  completedTrials?: number;
  startedAt?: string | null;
  updatedAt?: string | null;
  finishedAt?: string | null;
  jobResult?: Record<string, unknown> | null;
  status?: HarborJobListStatus;
  failedTrials?: number;
  launchStatus?: string | null;
}

export interface HarborJobsListResponse {
  jobs: HarborJobSummary[];
}

export interface HarborTrialView {
  trialName: string;
  personaId?: string | null;
  personaName?: string | null;
  completed?: boolean;
  succeeded?: boolean;
  error?: string | null;
  result?: Record<string, unknown> | null;
}

export interface HarborTrialEvent {
  type: string;
  phase?: string;
  turn?: TurnView;
  prompts?: PlaygroundPrompts;
  [key: string]: unknown;
}

export interface HarborTrialEventsResponse {
  events: HarborTrialEvent[];
  offset: number;
}

export interface HarborJobLiveTrial {
  trialName: string;
  personaId?: string | null;
  personaName?: string | null;
  completed?: boolean;
  succeeded?: boolean | null;
  error?: string | null;
  phase?: string | null;
  stage?: string | null;
  hasInstruction?: boolean;
}

export interface HarborJobLiveResponse {
  jobName: string;
  launchStatus?: string | null;
  trialCount: number;
  completedTrials: number;
  trials: HarborJobLiveTrial[];
}

/** Coarse trial status codes for the incremental cohort status feed. */
export type HarborStatusCode = 0 | 1 | 2 | 3; // pending | running | done | error

export interface HarborJobStatusResponse {
  jobName: string;
  launchStatus?: string | null;
  version: number;
  trialCount: number;
  counts: { pending: number; running: number; done: number; error: number };
  full: boolean;
  /** Present when `full` — the complete positional snapshot. */
  statuses?: HarborStatusCode[];
  trialNames?: string[];
  personaIds?: (string | null)[];
  personaNames?: (string | null)[];
  /** Present when `!full` — `[index, code]` deltas since the requested version. */
  changes?: [number, HarborStatusCode][];
}

export interface HarborLaunchView {
  status?: string;
  configPath?: string | null;
  error?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  exitCode?: number | null;
  executionPlane?: string | null;
  remoteRunId?: string | null;
}

export type StructuredFieldKind = "numerical" | "categorical" | "textual";

export interface JobAggregationCoverage {
  trialCount: number;
  completedTrials: number;
  pendingTrials: number;
  artifactReadyTrials: number;
  completedWithoutArtifactTrials: number;
}

export interface JobAggregationNumerical {
  count: number;
  min: number | null;
  max: number | null;
  avg: number | null;
  std: number | null;
  /** Value frequencies for discrete scales (e.g. likert 1–5). */
  counts?: JobAggregationCategoricalCount[] | null;
}

export interface JobAggregationCategoricalCount {
  value: string;
  count: number;
}

export interface JobAggregationCategorical {
  count: number;
  distinctCount: number;
  counts: JobAggregationCategoricalCount[];
}

export interface JobAggregationTextual {
  count: number;
  uniqueCount: number;
  samples: string[];
  /** Full value frequencies when available (preferred over unique-only samples). */
  counts?: Array<{ value: string; count: number; samples?: string[] | null }> | null;
  summary?: string | null;
  summaryType?: string | null;
}

export interface JobAggregationField {
  key: string;
  facetKey?: string | null;
  contextKey?: string | null;
  contextLabel?: string | null;
  label: string;
  kind: StructuredFieldKind;
  role?: string | null;
  group?: string | null;
  description?: string | null;
  unit?: string | null;
  higherIsBetter?: boolean | null;
  categories?: string[] | null;
  order?: number | null;
  /** Optional rating scale bounds (chat self-report / survey likert). */
  scaleMin?: number | null;
  scaleMax?: number | null;
  presentCount: number;
  missingCount: number;
  numerical?: JobAggregationNumerical | null;
  categorical?: JobAggregationCategorical | null;
  textual?: JobAggregationTextual | null;
}

export interface JobAggregationCrossFacetViewBucket {
  category: string;
  count: number;
  samples: string[];
}

export interface JobAggregationCrossFacetView {
  type: string;
  primaryFacetKey?: string | null;
  textFacetKey?: string | null;
  buckets?: JobAggregationCrossFacetViewBucket[];
}

export interface JobAggregationPersonaDistributionBucket {
  /** Persona segment value (e.g. a life_stage or age_bracket). */
  bucket: string;
  count: number;
  numerical?: JobAggregationNumerical | null;
  categorical?: JobAggregationCategorical | null;
}

export interface JobAggregationPersonaDistribution {
  id: string;
  facetKey: string;
  facetLabel: string;
  kind: "numerical" | "categorical" | string;
  groupByPersonaDimension: string;
  groupByLabel: string;
  lens?: string | null;
  total: number;
  /** Stable category column order (categorical only). */
  categories?: string[] | null;
  buckets: JobAggregationPersonaDistributionBucket[];
}

export interface JobAggregationSummaryBucket {
  bucket: string;
  count: number;
  samples?: string[] | null;
  summary?: string | null;
  summaryType?: string | null;
}

export interface JobAggregationSummary {
  id: string;
  title: string;
  targetFacetKey: string;
  groupByFacetKey?: string | null;
  groupByPersonaDimension?: string | null;
  groupByLabel?: string | null;
  groupByMode?: string | null;
  /** Which analysis tab: "general" (auto), "task" (SUT), or "persona" (customer insight). */
  lens?: string | null;
  summaryKind?: string | null;
  instruction?: string | null;
  /** True for auto-synthesized reason summaries (Common), false/absent for reporting.json ones (Custom). */
  auto?: boolean | null;
  status?: string | null;
  error?: string | null;
  overall?: JobAggregationTextual | null;
  buckets: JobAggregationSummaryBucket[];
}

export interface JobAggregationJudgeSignal {
  key: string;
  label: string;
  valueType?: string | null;
  description?: string | null;
}

export interface JobAggregationJudgeSignalStat {
  key: string;
  label: string;
  /** How many scanned samples exhibit this signal. */
  present: number;
  /** Total scanned samples in scope (overall, or the group for a bucket). */
  total: number;
  examples?: string[] | null;
}

export interface JobAggregationJudgeBucket {
  bucket: string;
  count: number;
  samples: string[];
  assessment?: string | null;
  signals?: JobAggregationJudgeSignalResult[] | null;
  signalStats?: JobAggregationJudgeSignalStat[] | null;
}

export interface JobAggregationJudgeSignalResult {
  key: string;
  present: boolean;
  evidence?: string | null;
}

export interface JobAggregationJudge {
  id: string;
  title: string;
  targetFacetKey: string;
  groupByFacetKey?: string | null;
  groupByPersonaDimension?: string | null;
  groupByLabel?: string | null;
  groupByMode?: string | null;
  /** Which analysis tab: "task" (SUT) or "persona" (customer insight). */
  lens?: string | null;
  judgeKind?: string | null;
  prompt?: string | null;
  rubric?: unknown;
  signals: JobAggregationJudgeSignal[];
  /** Per-signal prevalence across all scanned samples (primary view). */
  signalStats?: JobAggregationJudgeSignalStat[] | null;
  /** Total scanned samples backing signalStats. */
  total?: number | null;
  status?: string | null;
  error?: string | null;
  overall?: {
    count: number;
    samples: string[];
  } | null;
  overallAssessment?: string | null;
  buckets: JobAggregationJudgeBucket[];
}

export interface JobAggregationReporting {
  status: string;
  llmEnabled?: boolean;
  model?: string | null;
  totalUnits: number;
  summaryUnits?: number;
  judgeUnits?: number;
  readyUnits?: number;
  completedUnits?: number;
  failedUnits?: number;
  updatedAt?: string | null;
  liveStatus?: string | null;
  queuedAt?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  error?: string | null;
}

export interface HarborJobAggregationContext {
  key: string;
  label: string;
  contextType?: string | null;
  /** Survey questionnaire type when contextType is question_response. */
  questionType?: "likert" | "single_choice" | "multi_choice" | "free_text" | string | null;
  /** Likert scale bounds from questionnaire when available. */
  scaleMin?: number | null;
  scaleMax?: number | null;
  /** Optional per-point labels keyed by scale value ("1", "5", …). */
  scaleLabels?: Record<string, string> | null;
  /** Full choice inventory from questionnaire (includes zero-count options). */
  choiceOptions?: Array<{ id: string; label: string }> | null;
  facets: JobAggregationField[];
  summaries?: JobAggregationSummary[];
  judges?: JobAggregationJudge[];
  /** Default persona-insight lens: signals cross-tabbed by persona segment. */
  personaDistributions?: JobAggregationPersonaDistribution[];
  /**
   * Cohort-level single facets for Persona insights (no persona cross).
   * Authors declare these with ``groupByPersonaDimensions: []`` / ``standalone: true``
   * (capped at 2 per context).
   */
  personaStandaloneFacets?: JobAggregationField[];
  /** Every eligible facet × persona-dimension pairing, for the interactive explorer. */
  personaDistributionOptions?: JobAggregationPersonaDistribution[];
  crossFacetViews?: JobAggregationCrossFacetView[];
  /** @deprecated Renamed to `crossFacetViews`. Kept for older aggregation artifacts. */
  relationships?: JobAggregationCrossFacetView[];
}

export interface HarborJobAggregation {
  schemaVersion: string;
  artifactType: string;
  generatedAt: string;
  coverage: JobAggregationCoverage;
  reporting?: JobAggregationReporting | null;
  fields: JobAggregationField[];
  contexts?: HarborJobAggregationContext[];
}

export interface HarborJobDetail {
  jobName: string;
  jobsDir?: string | null;
  applicationType?: string | null;
  taskPath?: string | null;
  taskTitle?: string | null;
  taskName?: string | null;
  domain?: string | null;
  difficulty?: string | null;
  tags?: string[];
  metaType?: string | null;
  description?: string | null;
  personaStrategy?: TaskPersonaStrategy | null;
  config?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
  trials: HarborTrialView[];
  launch?: HarborLaunchView | null;
  /** @deprecated Prefer GET …/aggregation; job detail no longer embeds the full report. */
  aggregation?: HarborJobAggregation | null;
}

export interface HarborJobLaunchResponse {
  jobName: string;
  configPath?: string | null;
  jobsDir?: string | null;
  agentName?: string | null;
  taskType?: string | null;
  trialProfile?: string | null;
  mode?: string | null;
  plane?: string | null;
}

export interface PersonaPoolDimensionOption {
  id: string;
  label?: string;
  values: string[];
}

export interface PersonaPoolDimensionSubgroup {
  id: string;
  label: string;
  dimensionIds: string[];
  dimensions: PersonaPoolDimensionOption[];
}

export interface PersonaPoolDimensionGroup {
  id: string;
  label: string;
  dimensionIds: string[];
  dimensions: PersonaPoolDimensionOption[];
  /** Present for production 1M catalog (3-layer taxonomy). */
  subgroups?: PersonaPoolDimensionSubgroup[];
}

export interface PersonaPoolCatalog {
  pool: string;
  count: number;
  smokePersonaId?: string | null;
  sourceCounts?: Record<string, number>;
  schemaVersion?: string | null;
  dimensionCategoriesPath?: string | null;
  dimensionCategories: {
    schemaVersion?: string | null;
    personaSources?: string[];
    devProfile?: {
      dimensionCount?: number | null;
      groups?: PersonaPoolDimensionGroup[];
    };
  };
}

export interface PersonaMatchedAttribute {
  dimensionId: string;
  label: string;
  value: string;
  evidence?: string | null;
  method?: string;
  confidence?: number;
}

export interface PersonaMatchAttributesResponse {
  prompt: string;
  attributes: PersonaMatchedAttribute[];
  usedLlm: boolean;
}

export interface PersonaDatasetOption {
  pool: string;
  label: string;
  kind: "dataset" | "saved" | "generated" | "production" | "production-cohort" | string;
  count: number;
  default?: boolean;
  available?: boolean;
}

export interface PersonaDatasetListResponse {
  datasets: PersonaDatasetOption[];
  defaultPool: string;
}

export interface PersonaPoolIdsResponse {
  pool: string;
  personaIds: string[];
  count: number;
  idsTruncated?: boolean;
}

export interface PersonaPoolGenerateResult {
  pool: string;
  label: string;
  count: number;
  dimensionCount: number;
  source: string;
  kind: string;
  personaIds: string[];
  seed: number;
}

/** NDJSON progress line from ``POST /api/persona-pool/generate?stream=1``. */
export interface PersonaPoolGenerateProgress {
  type: "progress";
  stage: "prepare" | "sample" | "write" | "manifest" | "done" | string;
  ratio: number;
  label: string;
  done?: number;
  total?: number;
}

export interface PersonaPoolSampleResult {
  pool: string;
  matchedCount: number;
  sampleSize: number;
  seed: number;
  personaIds: string[];
  personas: Array<{
    personaId: string;
    source?: string;
    path?: string;
    name?: string;
    dimensions?: Record<string, string>;
  }>;
  fields?: string[];
  /** Full cohort size (may exceed personaIds when idsTruncated). */
  selectedCount?: number;
  idsTruncated?: boolean;
}

export interface PersonaPoolPersonaCard {
  personaId: string;
  name?: string;
  source?: string;
  path?: string | null;
  dimensions: Record<string, string>;
  /** Lowercased haystack of id/name/source + all YAML attribute keys/values. */
  searchText?: string;
}

export interface PersonaPoolCardsResponse {
  pool: string;
  personas: PersonaPoolPersonaCard[];
}

export interface PersonaDimensionItem {
  id: string;
  label: string;
  value: string;
  category?: string;
}

export interface PersonaDimensionSubgroup {
  id: string;
  label: string;
  count: number;
  items: PersonaDimensionItem[];
}

export interface PersonaDimensionGroup {
  id: string;
  label: string;
  count: number;
  subgroups: PersonaDimensionSubgroup[];
}

export interface PersonaPoolPersonaDetail extends PersonaPoolPersonaCard {
  pool: string;
  path?: string | null;
  yaml?: string;
  profileMarkdown?: string;
  dimensions: Record<string, string>;
  dimensionGroups?: PersonaDimensionGroup[];
}

/** Unified sampling block inside ``persona_strategy.json``. */
export interface TaskPersonaSampling {
  mode: "single" | "random" | "stratified" | "all" | string;
  personaId?: string;
  sampleSize?: number | null;
  fields?: string[];
  allocation?: "perCell" | "proportional" | "equalTotal" | string | null;
  perCell?: number | null;
}

export interface TaskPersonaStrategy {
  schemaVersion?: string;
  pool?: string | null;
  sources?: string[];
  dimensionFilters?: Record<string, string[]>;
  seed?: number | null;
  cohortId?: string | null;
  sampling?: TaskPersonaSampling | null;
}

export interface TaskDetail {
  taskPath: string;
  title?: string;
  description?: string;
  metaType?: string;
  taskName?: string;
  domain?: string | null;
  difficulty?: string | null;
  tags?: string[];
  instructionMarkdown?: string;
  contextMarkdown?: string;
  questionnaireMarkdown?: string;
  outputSchemaMarkdown?: string;
  selfReportMarkdown?: string;
  questionnaire?: SurveyInstrument | null;
  personaStrategy?: TaskPersonaStrategy | null;
  profileMarkdown?: string;
}

/** Unified persona pool for all Playground sampling. */
export const PERSONA_BENCH_POOL = "persona/datasets/matraix-persona-dev-sample";
/** Production 1M coreset (HF MatrAIx_Persona_1M_Public_Release). */
export const PERSONA_PRODUCTION_1M_POOL = "persona/datasets/matraix-persona-1m";
export const PERSONA_SAMPLE_SIZE_MAX_DEV = 500;
export const PERSONA_GENERATE_COUNT_DEFAULT = 2000;
export const PERSONA_GENERATE_COUNT_MAX = 5000;
export const PERSONA_SAMPLE_SIZE_MAX_PRODUCTION = 10_000;

/**
 * Large cohorts keep a pool ref for launch; only this many cards hydrate in the UI.
 * At or below PERSONA_UI_ID_LIST_MAX the full ID list may still be held for toggles.
 */
export const PERSONA_CARD_PREVIEW_LIMIT = 32;
/** Max persona IDs kept in browser state; larger cohorts launch by pool ref. */
export const PERSONA_UI_ID_LIST_MAX = 100;

export interface PersonaCohortSummary {
  cohortId: string;
  name: string;
  kind: "recipe" | "frozen" | string;
  pool: string;
  sampleSize: number;
  matchedCount: number;
  personaCount: number;
  createdAt?: string | null;
}

export interface PersonaCohortDetail extends PersonaCohortSummary {
  description?: string;
  seed: number;
  sources: string[];
  dimensionFilters: Record<string, string>;
  personaIds: string[];
  personas: Array<{ personaId: string; source?: string; path?: string }>;
}

/** Default Harbor task paths for cockpit launch (one trial per persona). */
export const HARBOR_TASK_PATHS = {
  chatbot: "application/tasks/chat_meal-planning-nutrition",
  survey: "application/tasks/example-survey_product-feedback",
  web: "application/tasks/example-web-playwright_quote-choice",
  cuaLinux: "application/tasks/example-computer-use-linux_note-to-csv",
  cuaWeb: "application/tasks/example-web-cua_bookshop-choice",
} as const;

export const HARBOR_CHAT_TASKS: Record<string, string> = {
  meal_planning_nutrition: HARBOR_TASK_PATHS.chatbot,
  finance_openbb: "application/tasks/chat_openbb-corporate-action-honesty",
  acme_support_api: "application/tasks/example-chat-api_support_chatbot",
  acme_support_mcp: "application/tasks/example-chat-mcp_support_chatbot",
};
