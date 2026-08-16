import type {
  HarborDraftTurn,
  PlaygroundJobView,
  PlaygroundMetricScores,
  PlaygroundPrompts,
  PlaygroundQuestionnaire,
  PlaygroundResult,
  StructuredExposureField,
  SurveyEvalJobView,
  SurveyResult,
  TurnView,
  UserFeedbackArtifact,
  WebEvalJobView,
  WebResult,
  WebTrace,
  OsAppEvalJobView,
  OsAppResult,
  VerifierSummary,
} from "./types";

export interface HarborRunContext {
  jobName: string;
  trialName: string;
}

export interface HarborCockpitLiveState {
  turns: TurnView[];
  draftTurn: HarborDraftTurn | null;
  phase: string | null;
  prompts?: PlaygroundPrompts | null;
  instructionMarkdown?: string | null;
  contextMarkdown?: string | null;
  questionnaireMarkdown?: string | null;
  outputSchemaMarkdown?: string | null;
  surveyResult?: SurveyResult | null;
}

function asTurns(transcript: unknown): TurnView[] {
  if (!Array.isArray(transcript)) return [];
  return transcript.map((turn) => normalizeTurnDict(turn as Record<string, unknown>));
}

function asStructuredExposure(raw: unknown): StructuredExposureField[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((item): item is StructuredExposureField => Boolean(item) && typeof item === "object");
}

export function normalizeTurnDict(turn: Record<string, unknown>): TurnView {
  const assistant = turn.assistantMessage;
  const legacyAssistant = turn.assistantReply;
  const userMessage = turn.userMessage ?? turn.user_message;
  const durationSeconds = turn.durationSeconds ?? turn.duration_seconds;
  const rawTurnId = turn.turnId ?? turn.turnIndex ?? turn.index;
  return {
    turnId: rawTurnId != null ? String(rawTurnId) : "",
    userMessage: String(userMessage ?? ""),
    assistantMessage: String(assistant ?? legacyAssistant ?? ""),
    durationSeconds: (durationSeconds as number | null | undefined) ?? null,
    plan: Array.isArray(turn.plan) ? (turn.plan as TurnView["plan"]) : [],
    structuredExposure: asStructuredExposure(turn.structuredExposure),
    nativeRaw: typeof turn.nativeRaw === "string" ? turn.nativeRaw : null,
    rawToolOutputs: turn.rawToolOutputs ?? null,
  };
}

export function draftTurnToView(draft: HarborDraftTurn): TurnView {
  return {
    turnId: draft.turnIndex != null ? String(draft.turnIndex) : "draft",
    userMessage: draft.userMessage ?? "",
    assistantMessage: draft.assistantMessage ?? "",
    durationSeconds: draft.durationSeconds ?? null,
    structuredExposure: draft.structuredExposure ?? [],
    plan: [],
  };
}

export function harborTrialErrorFromResult(
  result?: Record<string, unknown> | null,
): string | null {
  if (!result) return null;
  const exc = result.exception_info as
    | { exception_message?: string; exception_type?: string }
    | undefined;
  if (!exc) return null;
  return exc.exception_message ?? exc.exception_type ?? "Trial failed.";
}

/** Trial failed only because verifier reward.txt was missing, but debrief artifacts exist. */
export function isRewardOnlyTrialFailure(
  trialError: string | null | undefined,
  debrief: {
    transcript?: unknown;
    questionnaire?: unknown;
    surveyResult?: { answers?: unknown[] } | null;
    webResult?: Record<string, unknown> | null;
    webTrace?: { events?: unknown[] } | null;
    trace?: { events?: unknown[] } | null;
    cuaResult?: Record<string, unknown> | null;
  },
): boolean {
  if (!trialError?.toLowerCase().includes("reward")) return false;
  if (asTurns(debrief.transcript).length > 0) return true;
  const questionnaire = debrief.questionnaire as Record<string, unknown> | null | undefined;
  if (questionnaire && Object.keys(questionnaire).length > 0) return true;
  const surveyResult = debrief.surveyResult as { answers?: unknown[] } | null | undefined;
  if (Array.isArray(surveyResult?.answers) && surveyResult.answers.length > 0) return true;
  const webResult = debrief.webResult as Record<string, unknown> | null | undefined;
  if (webResult && Object.keys(webResult).length > 0) return true;
  const webTrace = debrief.webTrace as { events?: unknown[] } | null | undefined;
  if (Array.isArray(webTrace?.events) && webTrace.events.length > 0) return true;
  const trace = debrief.trace as { events?: unknown[] } | null | undefined;
  if (Array.isArray(trace?.events) && trace.events.length > 0) return true;
  const debriefRecord = debrief as Record<string, unknown>;
  const osAppResult = debriefRecord.osAppResult as Record<string, unknown> | null | undefined;
  if (osAppResult && Object.keys(osAppResult).length > 0) return true;
  const cuaResult = debriefRecord.cuaResult as Record<string, unknown> | null | undefined;
  if (cuaResult && Object.keys(cuaResult).length > 0) return true;
  return false;
}

export function harborDebriefError(debrief: PlaygroundResult): string | null {
  const direct = debrief.error;
  if (typeof direct === "string" && direct.trim()) return direct;
  const harbor = debrief.harbor as { failed?: boolean } | undefined;
  if (harbor?.failed) return "Trial failed.";
  return null;
}

export type CockpitRunErrorCode =
  | "trial_failed"
  | "batch_run_failed"
  | "run_timeout"
  | "run_stopped_reset"
  | "empty_conversation"
  | "missing_trial"
  | "trial_output_artifacts_missing"
  | "trial_not_found"
  | "reward_file_missing";

export interface CockpitRunError {
  /** Stable UI classification; raw backend text is kept separately. */
  code: CockpitRunErrorCode | null;
  rawMessage: string;
}

/**
 * Recognize known Harbor failures without formatting or rewriting backend text.
 * The rendering layer owns localization for `code` and shows `rawMessage` as-is
 * for errors the client does not recognize.
 */
export function classifyCockpitRunError(
  message: string | null | undefined,
): CockpitRunError | null {
  if (!message?.trim()) return null;
  const normalized = message.trim();
  const clientFallbackCode: Record<string, CockpitRunErrorCode> = {
    "Trial failed.": "trial_failed",
    "Batch run failed.": "batch_run_failed",
    "This run is taking longer than expected.": "run_timeout",
    "Run stopped. Reset to change setup and launch again.": "run_stopped_reset",
    "Run finished with no conversation turns.": "empty_conversation",
    "Run finished without producing a trial.": "missing_trial",
  };
  const clientCode = clientFallbackCode[normalized];
  if (clientCode) return { code: clientCode, rawMessage: message };
  const lower = message.toLowerCase();
  if (lower.includes("trial output artifacts not found")) {
    return { code: "trial_output_artifacts_missing", rawMessage: message };
  }
  if (lower.includes("trial not found")) {
    return { code: "trial_not_found", rawMessage: message };
  }
  if (lower.includes("reward file") || lower.includes("rewardfilenotfound")) {
    return { code: "reward_file_missing", rawMessage: message };
  }
  return { code: null, rawMessage: message };
}

function asVerifier(raw: unknown): VerifierSummary | null {
  if (!raw || typeof raw !== "object") return null;
  const value = raw as Record<string, unknown>;
  if (typeof value.reward !== "number") return null;
  return {
    passed: Boolean(value.passed),
    reward: value.reward,
    detail: typeof value.detail === "string" ? value.detail : null,
  };
}

export function applyHarborTrialEvents(
  events: Array<{
    type: string;
    phase?: string;
    turn?: TurnView | Record<string, unknown>;
    prompts?: PlaygroundPrompts;
    markdown?: string;
    result?: Record<string, unknown>;
    turnIndex?: number;
    message?: string;
    userMessage?: string;
    assistantMessage?: string;
    structuredExposure?: StructuredExposureField[];
    durationSeconds?: number | null;
  }>,
  prev: HarborCockpitLiveState,
): HarborCockpitLiveState {
  let turns = prev.turns;
  let draftTurn = prev.draftTurn;
  let phase = prev.phase;
  let prompts = prev.prompts ?? null;
  let instructionMarkdown = prev.instructionMarkdown ?? null;
  let contextMarkdown = prev.contextMarkdown ?? null;
  let questionnaireMarkdown = prev.questionnaireMarkdown ?? null;
  let outputSchemaMarkdown = prev.outputSchemaMarkdown ?? null;
  let surveyResult = prev.surveyResult ?? null;

  for (const event of events) {
    if (event.type === "user_message" && event.message) {
      draftTurn = {
        turnIndex: event.turnIndex,
        userMessage: event.message,
        assistantMessage: "",
        structuredExposure: [],
      };
      phase = "recommender_thinking";
    } else if (event.type === "assistant_message") {
      draftTurn = {
        turnIndex: event.turnIndex ?? draftTurn?.turnIndex,
        userMessage: event.userMessage ?? draftTurn?.userMessage ?? "",
        assistantMessage: event.assistantMessage ?? "",
        structuredExposure: asStructuredExposure(event.structuredExposure),
        durationSeconds: event.durationSeconds ?? null,
      };
      phase = "persona_thinking";
    } else if (event.type === "phase" && event.phase) {
      phase = event.phase;
      if (event.phase === "recommender_thinking" && event.userMessage && !draftTurn?.assistantMessage) {
        draftTurn = {
          turnIndex: draftTurn?.turnIndex,
          userMessage: event.userMessage,
          assistantMessage: draftTurn?.assistantMessage ?? "",
          structuredExposure: draftTurn?.structuredExposure ?? [],
        };
      }
    } else if (event.type === "turn" && event.turn) {
      const normalized = normalizeTurnDict(event.turn as Record<string, unknown>);
      const turnId = normalized.turnId ?? "";
      const duplicate = turns.some((turn) => (turn.turnId ?? "") === turnId);
      turns = duplicate ? turns : [...turns, normalized];
      draftTurn = null;
    } else if (event.type === "prompts" && event.prompts) {
      prompts = event.prompts;
    } else if (event.type === "instruction" && event.markdown) {
      instructionMarkdown = event.markdown;
    } else if (event.type === "done" && event.result) {
      const payload = event.result;
      const extracted = surveyResultFromDonePayload(payload);
      if (extracted) {
        surveyResult = extracted;
      }
      if (Array.isArray(payload.transcript)) {
        turns = asTurns(payload.transcript);
      }
      phase = "done";
      draftTurn = null;
    }
  }

  return {
    turns,
    draftTurn,
    phase,
    prompts,
    instructionMarkdown,
    contextMarkdown,
    questionnaireMarkdown,
    outputSchemaMarkdown,
    surveyResult,
  };
}

export function surveyResultFromDonePayload(payload: Record<string, unknown>): SurveyResult | null {
  const nested = payload.surveyResult;
  if (nested && typeof nested === "object") {
    const nestedRecord = nested as Record<string, unknown>;
    const answers = nestedRecord.answers;
    if (Array.isArray(answers)) {
      return nested as SurveyResult;
    }
  }
  if (!Array.isArray(payload.answers)) {
    return null;
  }
  const answers = payload.answers as SurveyResult["answers"];
  const instrumentPayload = payload.instrument as SurveyResult["instrument"] | undefined;
  const metrics = (payload.metrics ?? {}) as Record<string, unknown>;
  const questionCount =
    Number(metrics.numQuestions) ||
    instrumentPayload?.questions?.length ||
    answers.length;
  return {
    instrument: instrumentPayload ?? { id: "survey", title: "Survey", questions: [] },
    answers,
    trajectory: (payload.trajectory as SurveyResult["trajectory"]) ?? [],
    completion: {
      numAnswered: Number(metrics.numAnswered) || answers.length,
      numQuestions: questionCount,
      answered: Number(metrics.numAnswered) || answers.length,
      total: questionCount,
      valid: Boolean(metrics.valid ?? (answers.length > 0 && answers.length >= questionCount)),
      meanLikert: typeof metrics.meanLikert === "number" ? metrics.meanLikert : null,
    },
    createdAt: typeof payload.createdAt === "string" ? payload.createdAt : undefined,
    prompts: (payload.prompts as SurveyResult["prompts"]) ?? undefined,
  };
}

/** Keep live cockpit artifacts when debrief mapping is thin or stale. */
export function mergeHarborCockpitJob<TJob>(
  mapped: TJob,
  live: HarborCockpitLiveState,
  input: { mapLive?: (live: HarborCockpitLiveState, ctx: HarborRunContext) => TJob },
  ctx: HarborRunContext,
): TJob {
  if (!input.mapLive) {
    return mapped;
  }
  const liveJob = input.mapLive(live, ctx) as Record<string, unknown>;
  const mappedRecord = mapped as Record<string, unknown>;
  const next: Record<string, unknown> = { ...mappedRecord };

  const mappedSurvey = mappedRecord.surveyResult as SurveyResult | null | undefined;
  const liveSurvey = liveJob.surveyResult as SurveyResult | null | undefined;
  if ((!mappedSurvey?.answers?.length) && liveSurvey?.answers?.length) {
    next.surveyResult = liveSurvey;
  }

  const mappedTurns = mappedRecord.turns as TurnView[] | undefined;
  const liveTurns = liveJob.turns as TurnView[] | undefined;
  if ((!mappedTurns?.length) && liveTurns?.length) {
    next.turns = liveTurns;
    next.draftTurn = null;
  }

  if (!next.instructionMarkdown && liveJob.instructionMarkdown) {
    next.instructionMarkdown = liveJob.instructionMarkdown;
  }
  if (!next.prompts && liveJob.prompts) {
    next.prompts = liveJob.prompts;
  }

  const mappedWeb = mappedRecord.webResult as WebResult | null | undefined;
  const liveWeb = liveJob.webResult as WebResult | null | undefined;
  if (!mappedWeb && liveWeb) {
    next.webResult = liveWeb;
  }

  const mappedCua = mappedRecord.osAppResult as OsAppResult | null | undefined;
  const liveCua = liveJob.osAppResult as OsAppResult | null | undefined;
  if (!mappedCua && liveCua) {
    next.osAppResult = liveCua;
  }

  return next as TJob;
}

export type HarborCockpitTaskKind = "chatbot" | "survey" | "web" | "os-app";

function personaFallback(debrief: PlaygroundResult): { personaId: string; personaName: string } {
  const persona = (debrief.persona ?? {}) as { id?: string; name?: string };
  return {
    personaId: String(persona.id ?? ""),
    personaName: String(persona.name ?? "Persona"),
  };
}

export function createHarborCockpitRestoreMappers(taskKind: HarborCockpitTaskKind): {
  mapDebrief: (debrief: PlaygroundResult, ctx: HarborRunContext) => unknown;
  mapLive?: (live: HarborCockpitLiveState, ctx: HarborRunContext) => unknown;
} {
  return {
    mapDebrief: (debrief, ctx) => {
      const fallback = personaFallback(debrief);
      switch (taskKind) {
        case "chatbot":
          return mapChatbotDebriefToJobView(debrief, ctx, fallback);
        case "survey":
          return mapSurveyDebriefToJobView(debrief, ctx, fallback);
        case "web":
          return mapWebDebriefToJobView(debrief, ctx, fallback);
        case "os-app":
          return mapOsAppDebriefToJobView(debrief, ctx, fallback);
      }
    },
    mapLive:
      taskKind === "chatbot" || taskKind === "survey"
        ? (live, ctx) => {
            const fallback = { personaId: "", personaName: "Persona" };
            return taskKind === "chatbot"
              ? mapChatbotLiveToJobView(live, ctx, fallback)
              : mapSurveyLiveToJobView(live, ctx, fallback);
          }
        : undefined,
  };
}

export function mapChatbotLiveToJobView(
  live: HarborCockpitLiveState,
  ctx: HarborRunContext,
  fallback: {
    personaId: string;
    personaName: string;
    domain?: string;
    applicationId?: string;
    sutDescription?: string;
  },
): PlaygroundJobView {
  return {
    jobId: `${ctx.jobName}/${ctx.trialName}`,
    domain: fallback.domain ?? "movie",
    applicationId: fallback.applicationId ?? "meal_planning_nutrition",
    applicationContext: fallback.domain ?? null,
    personaId: fallback.personaId,
    personaName: fallback.personaName,
    sutDescription: fallback.sutDescription ?? "Chat application under test.",
    status: "running",
    phase: live.phase,
    turns: live.turns,
    draftTurn: live.draftTurn,
    questionnaire: null,
    metricScores: null,
    prompts: live.prompts ?? null,
    error: null,
  };
}

export function mapSurveyLiveToJobView(
  live: HarborCockpitLiveState,
  ctx: HarborRunContext,
  fallback: {
    personaId: string;
    personaName: string;
    instrumentId?: string;
    instrumentTitle?: string;
  },
): SurveyEvalJobView {
  return {
    jobId: `${ctx.jobName}/${ctx.trialName}`,
    applicationType: "survey",
    taskId: "harbor",
    instrumentId: fallback.instrumentId ?? "harbor_survey",
    instrumentTitle: fallback.instrumentTitle ?? "Survey",
    personaId: fallback.personaId,
    personaName: fallback.personaName,
    status: "running",
    phase: live.phase,
    surveyResult: live.surveyResult ?? null,
    instructionMarkdown: live.instructionMarkdown ?? null,
    contextMarkdown: live.contextMarkdown ?? null,
    questionnaireMarkdown: live.questionnaireMarkdown ?? null,
    outputSchemaMarkdown: live.outputSchemaMarkdown ?? null,
    prompts: live.prompts ?? null,
    error: null,
  };
}

export function mapChatbotDebriefToJobView(
  debrief: PlaygroundResult,
  ctx: HarborRunContext,
  fallback: { personaId: string; personaName: string; domain?: string; applicationId?: string },
): PlaygroundJobView {
  const config = (debrief.config ?? {}) as Record<string, unknown>;
  const persona = (debrief.persona ?? {}) as Record<string, unknown>;
  const error = harborDebriefError(debrief);
  const turns = asTurns(debrief.transcript);
  const emptyTranscriptError = !error && turns.length === 0 ? "Run finished with no conversation turns." : null;
  const failed = Boolean(error || emptyTranscriptError);
  return {
    jobId: `${ctx.jobName}/${ctx.trialName}`,
    domain: String(config.domain ?? fallback.domain ?? "movie"),
    applicationId: (config.applicationId as string | undefined) ?? fallback.applicationId ?? "meal_planning_nutrition",
    applicationContext: (config.applicationContext as string | undefined) ?? null,
    personaId: String(persona.id ?? fallback.personaId),
    personaName: String(persona.name ?? fallback.personaName),
    sutDescription: String(debrief.sutDescription ?? "Chat application under test."),
    status: failed ? "error" : "done",
    phase: null,
    turns,
    questionnaire: (debrief.questionnaire as PlaygroundQuestionnaire | undefined) ?? null,
    metricScores: (debrief.metricScores as PlaygroundMetricScores | undefined) ?? null,
    prompts: (debrief.prompts as PlaygroundPrompts | undefined) ?? null,
    error: error ?? emptyTranscriptError,
  };
}

export function mapSurveyDebriefToJobView(
  debrief: PlaygroundResult,
  ctx: HarborRunContext,
  fallback: { personaId: string; personaName: string; instrumentId?: string; instrumentTitle?: string },
): SurveyEvalJobView {
  const surveyResult = (debrief.surveyResult ?? null) as SurveyResult | null;
  const instrument = surveyResult?.instrument;
  const error = harborDebriefError(debrief);
  return {
    jobId: `${ctx.jobName}/${ctx.trialName}`,
    applicationType: "survey",
    taskId: "harbor",
    instrumentId: instrument?.id ?? fallback.instrumentId ?? "harbor_survey",
    instrumentTitle: instrument?.title ?? fallback.instrumentTitle ?? String(debrief.instrumentTitle ?? "Survey"),
    personaId: String((debrief.persona as { id?: string } | undefined)?.id ?? fallback.personaId),
    personaName: String((debrief.persona as { name?: string } | undefined)?.name ?? fallback.personaName),
    status: error ? "error" : "done",
    phase: null,
    surveyResult,
    verifier: asVerifier(debrief.verifier),
    instructionMarkdown:
      typeof debrief.instructionMarkdown === "string" ? debrief.instructionMarkdown : null,
    contextMarkdown:
      typeof (debrief as Record<string, unknown>).contextMarkdown === "string"
        ? ((debrief as Record<string, unknown>).contextMarkdown as string)
        : null,
    questionnaireMarkdown:
      typeof (debrief as Record<string, unknown>).questionnaireMarkdown === "string"
        ? ((debrief as Record<string, unknown>).questionnaireMarkdown as string)
        : null,
    outputSchemaMarkdown:
      typeof (debrief as Record<string, unknown>).outputSchemaMarkdown === "string"
        ? ((debrief as Record<string, unknown>).outputSchemaMarkdown as string)
        : null,
    prompts: (debrief.prompts as PlaygroundPrompts | undefined) ?? surveyResult?.prompts ?? null,
    error,
  };
}

export function attachHarborTraceScreenshotUrls(
  trace: WebTrace | null | undefined,
  jobName: string,
  trialName: string,
): WebTrace | null {
  if (!trace?.events?.length) return trace ?? null;
  return {
    ...trace,
    events: trace.events.map((event) => {
      if (event.screenshotUrl || !event.screenshotFile) return event;
      const rel = event.screenshotFile.replace(/^\/+/, "");
      return {
        ...event,
        screenshotUrl: `/api/harbor/jobs/${encodeURIComponent(jobName)}/trials/${encodeURIComponent(trialName)}/screenshots/${rel
          .split("/")
          .map(encodeURIComponent)
          .join("/")}`,
      };
    }),
  };
}

export function mapWebDebriefToJobView(
  debrief: PlaygroundResult,
  ctx: HarborRunContext,
  fallback: { personaId: string; personaName: string; taskId?: string; taskTitle?: string },
): WebEvalJobView {
  const error = harborDebriefError(debrief);
  const rawTrace =
    (debrief.webTrace as WebTrace | undefined) ?? (debrief.trace as WebTrace | undefined) ?? null;
  const trace = attachHarborTraceScreenshotUrls(rawTrace, ctx.jobName, ctx.trialName);
  return {
    jobId: `${ctx.jobName}/${ctx.trialName}`,
    applicationType: "web",
    taskId: fallback.taskId ?? "harbor_web",
    taskTitle: String(debrief.taskTitle ?? fallback.taskTitle ?? "Website task"),
    siteName: String(debrief.siteName ?? "Website"),
    siteUrl: "https://example.com",
    personaId: String((debrief.persona as { id?: string } | undefined)?.id ?? fallback.personaId),
    personaName: String((debrief.persona as { name?: string } | undefined)?.name ?? fallback.personaName),
    status: error ? "error" : "done",
    phase: null,
    webResult: (debrief.webResult as WebResult | undefined) ?? null,
    trace,
    verifier: asVerifier(debrief.verifier),
    userFeedback: (debrief.userFeedback as UserFeedbackArtifact | undefined) ?? null,
    prompts: (debrief.prompts as PlaygroundPrompts | undefined) ?? null,
    error,
  };
}

/** Prefer agent steps with screenshots; skip the initial persona prompt wall. */
export function osAppReplayTrace(trace: WebTrace | null | undefined): WebTrace | null {
  if (!trace?.events?.length) return trace ?? null;
  const withScreenshots = trace.events.filter((event) => event.screenshotUrl || event.screenshotFile);
  if (withScreenshots.length > 0) {
    return { ...trace, events: withScreenshots };
  }
  const agentSteps = trace.events.filter(
    (event) => event.source === "agent" || event.actions.length > 0,
  );
  if (agentSteps.length > 0) {
    return { ...trace, events: agentSteps };
  }
  return trace;
}

export function harborTrialRecordingUrl(jobName: string, trialName: string): string {
  return `/api/harbor/jobs/${encodeURIComponent(jobName)}/trials/${encodeURIComponent(trialName)}/recording`;
}

export function mapOsAppDebriefToJobView(
  debrief: PlaygroundResult,
  ctx: HarborRunContext,
  fallback: { personaId: string; personaName: string; taskId?: string; taskTitle?: string; platform?: string },
): OsAppEvalJobView {
  const error = harborDebriefError(debrief);
  const debriefRecord = debrief as Record<string, unknown>;
  const rawTrace =
    (debriefRecord.osAppTrace as WebTrace | undefined)
    ?? (debriefRecord.cuaTrace as WebTrace | undefined)
    ?? (debrief.trace as WebTrace | undefined)
    ?? null;
  const trace = osAppReplayTrace(attachHarborTraceScreenshotUrls(rawTrace, ctx.jobName, ctx.trialName));
  const osAppResult =
    (debriefRecord.osAppResult as OsAppResult | undefined)
    ?? (debriefRecord.cuaResult as OsAppResult | undefined)
    ?? null;
  return {
    jobId: `${ctx.jobName}/${ctx.trialName}`,
    applicationType: "os-app",
    taskId: fallback.taskId ?? "harbor_os_app",
    taskTitle: String(debrief.taskTitle ?? fallback.taskTitle ?? "OS app task"),
    platform: String(debrief.platform ?? fallback.platform ?? "linux"),
    personaId: String((debrief.persona as { id?: string } | undefined)?.id ?? fallback.personaId),
    personaName: String((debrief.persona as { name?: string } | undefined)?.name ?? fallback.personaName),
    status: error ? "error" : "done",
    phase: null,
    osAppResult,
    trace,
    verifier: asVerifier(debrief.verifier),
    userFeedback: (debrief.userFeedback as UserFeedbackArtifact | undefined) ?? null,
    prompts: (debrief.prompts as PlaygroundPrompts | undefined) ?? null,
    error,
  };
}

/** @deprecated Use mapOsAppDebriefToJobView */
export const mapCuaDebriefToJobView = mapOsAppDebriefToJobView;

/** @deprecated Use osAppReplayTrace */
export const cuaReplayTrace = osAppReplayTrace;
