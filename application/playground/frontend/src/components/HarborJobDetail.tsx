/**
 * Harbor batch job detail — trial index only; open a trial for evaluation + run content.
 */
import { useId, useMemo, useRef, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";
import type { MessageKey } from "@/i18n/types";
import { SOURCE_MESSAGES } from "@/i18n/source";
import {
  exportBatchReportPdf,
  humanizePathLeaf,
  plainTextFromMarkdown,
  type BatchReportPdfMeta,
  type BatchReportPdfPersona,
  type BatchReportPdfPersonaStrategy,
  type BatchReportPdfSnapshot,
} from "@/lib/exportBatchReportPdf";
import {
  formatCostUsd,
  formatTokenCount,
  hasUsage,
  usageCompactLine,
  usageFromJobResult,
  usageFromTrialResult,
  usageListPrimary,
} from "@/lib/llmUsage";
import { personaDisplayId, personaPrimaryName } from "@/lib/personaDisplay";
import {
  surveyQuestionTypeChipClass,
  surveyQuestionTypeLabel,
  type SurveyQuestionTypeCount,
} from "@/lib/surveyDisplay";
import type {
  HarborJobAggregation,
  HarborJobDetail,
  JobAggregationCrossFacetView,
  SurveyInstrument,
  TaskPersonaStrategy,
} from "@/lib/types";
import { Markdown } from "@/components/Markdown";
import { QuestionnairePreview } from "@/components/QuestionnairePreview";
import { PersonaAvatar } from "./cockpit/setup/PersonaAvatar";
import { readStrategySampling } from "./cockpit/setup/personaSamplingTypes";
import {
  buildTaskDocSections,
  type TaskDocTabId,
} from "./cockpit/setup/taskDetailSections";
import { FOCUS_RING, Sym } from "./cockpit/cockpitShared";
import { HarborJobLiveRoster } from "./cockpit/setup/HarborJobLiveRoster";
import {
  CockpitSelect,
  type CockpitSelectOption,
} from "./cockpit/setup/CockpitSelect";
import {
  StudioGlassPanel,
  StudioPageFrame,
  StudioPageHeader,
  StudioToolbarButton,
} from "./studio/StudioShell";
import {
  crossFacetReasonPhrase,
  facetKeyLeaf,
  humanizeAnalysisStatus,
  humanizeAnalysisTitle,
  humanizeFacetLabel,
  likertPointLabel,
  type HarborReportTranslate,
} from "./harborReportPresentation";

export interface HarborJobDetailProps {
  jobName: string;
  onBack: () => void;
  onOpenTrial?: (trialName: string) => void;
}

type HarborTrialRow = HarborJobDetail["trials"][number];
type AggregationField = HarborJobAggregation["fields"][number];
type AggregationContext = NonNullable<HarborJobAggregation["contexts"]>[number];
type AggregationSummary = NonNullable<AggregationContext["summaries"]>[number];
type AggregationJudge = NonNullable<AggregationContext["judges"]>[number];
type AggregationPersonaDistribution = NonNullable<
  AggregationContext["personaDistributions"]
>[number];
type AggregationCrossFacetView = JobAggregationCrossFacetView;
type ReportTranslate = HarborReportTranslate;
type AggregationContextType =
  | "question_response"
  | "decision"
  | "decision_process"
  | "experience"
  | "task_outcome"
  | "conversation_summary"
  | "user_feedback"
  | "feedback"
  | "policy_and_trust"
  | "coordination"
  | string;

const CONTEXT_TYPE_META: Record<
  string,
  { badge: string; description: string; order: number }
> = {
  question_response: {
    badge: "Question",
    description: "One survey question — how all personas answered.",
    order: 0,
  },
  trial_summary: {
    badge: "Trial summary",
    description: "Coverage per persona run (answers and activity).",
    order: 80,
  },
  decision: {
    badge: "Decision",
    description: "What the persona ultimately chose and why.",
    order: 0,
  },
  task_outcome: {
    badge: "Task outcome",
    description: "How the task ended for each persona — success, partial, blocked, or left open.",
    order: 0,
  },
  decision_process: {
    badge: "Decision process",
    description: "How the persona explored options before deciding.",
    order: 1,
  },
  conversation_summary: {
    badge: "Conversation summary",
    description: "How the exchange progressed, including turn counts and clarification behavior.",
    order: 1,
  },
  experience: {
    badge: "Experience",
    description: "Post-task ratings covering ease, trust, and friction.",
    order: 2,
  },
  user_feedback: {
    badge: "User feedback",
    description: "Persona self-report about usefulness, fit, trust, or effort.",
    order: 2,
  },
  feedback: {
    badge: "User feedback",
    description: "Persona self-report about usefulness, fit, trust, or effort.",
    order: 2,
  },
  policy_and_trust: {
    badge: "Policy and trust",
    description: "Checks for groundedness, policy compliance, and handoff quality.",
    order: 3,
  },
  coordination: {
    badge: "Coordination",
    description: "Who still needs to act and whether the next step was clear.",
    order: 4,
  },
  web_interaction: {
    badge: "Web interaction",
    description: "How the persona navigated the site before submitting.",
    order: 5,
  },
  web_artifact: {
    badge: "Web artifact",
    description: "Whether the saved submission artifact matched the task goal.",
    order: 5,
  },
  goal_component: {
    badge: "Goal component",
    description: "Per-step checks against individual task requirements.",
    order: 5,
  },
  persona_alignment: {
    badge: "Persona alignment",
    description: "How well the outcome matched persona preferences or constraints.",
    order: 1,
  },
  persona_constraint: {
    badge: "Persona constraint",
    description: "Whether persona-specific limits or preferences were respected.",
    order: 1,
  },
};

type ReportingCategory = "web" | "os-app" | "chatbot" | "survey" | "generic";

/** Category-level UX: context ordering / compaction / breakdown preference — not per-task facet keys. */
const CONTEXT_PRIORITY_BY_CATEGORY: Record<ReportingCategory, Record<string, number>> = {
  web: {
    decision: 0,
    question_response: 0,
    user_feedback: 1,
    feedback: 1,
    decision_process: 2,
    task_outcome: 3,
    experience: 4,
    web_artifact: 8,
    web_interaction: 9,
  },
  "os-app": {
    persona_alignment: 0,
    persona_constraint: 1,
    question_response: 0,
    user_feedback: 2,
    feedback: 2,
    decision: 3,
    task_outcome: 4,
    goal_component: 5,
    experience: 6,
  },
  chatbot: {
    // Shared chatbot contract only. Task-authored contextTypes are unlisted
    // and fall back to a late default order (Custom tab).
    task_outcome: 0,
    conversation_summary: 1,
    user_feedback: 2,
    feedback: 2,
    coordination: 13,
    policy_and_trust: 14,
    question_response: 0,
  },
  survey: {
    question_response: 0,
    user_feedback: 1,
    feedback: 1,
    experience: 2,
  },
  generic: {},
};

const HEADLINE_CONTEXT_TYPES: Record<ReportingCategory, Set<string>> = {
  web: new Set(["decision", "decision_process", "user_feedback", "feedback", "question_response"]),
  "os-app": new Set([
    "persona_alignment",
    "persona_constraint",
    "decision",
    "user_feedback",
    "feedback",
    "question_response",
  ]),
  // Chatbot General = shared basics + self-report only. Any other contextType
  // the task authors goes under Custom analysis (no per-task hardcoding).
  chatbot: new Set([
    "task_outcome",
    "conversation_summary",
    "user_feedback",
    "feedback",
  ]),
  survey: new Set(["question_response", "user_feedback", "feedback"]),
  generic: new Set(["decision", "user_feedback", "feedback", "question_response"]),
};

const EXECUTION_CONTEXT_TYPES_BY_CATEGORY: Record<ReportingCategory, Set<string>> = {
  web: new Set(["task_outcome", "web_artifact", "web_interaction", "decision_process"]),
  "os-app": new Set(["task_outcome", "goal_component", "side_effects", "execution_profile"]),
  chatbot: new Set(["task_outcome", "conversation_summary"]),
  survey: new Set(["task_outcome"]),
  generic: new Set([
    "task_outcome",
    "web_artifact",
    "web_interaction",
    "decision_process",
    "goal_component",
    "side_effects",
    "execution_profile",
    "conversation_summary",
  ]),
};

/** Chatbot contexts that belong on the General tab. Everything else with
 *  chartable facets is a task-authored angle → Custom task analysis. */
const CHATBOT_GENERAL_CONTEXT_TYPES = new Set([
  "task_outcome",
  "conversation_summary",
  "user_feedback",
  "feedback",
]);

function isChatbotGeneralContext(contextType: string | null | undefined): boolean {
  return CHATBOT_GENERAL_CONTEXT_TYPES.has(contextType ?? "")
}

const WEB_SIGNAL_CONTEXT_TYPES = new Set(["web_artifact", "web_interaction"]);
const OS_APP_SIGNAL_CONTEXT_TYPES = new Set(["goal_component", "persona_alignment", "persona_constraint"]);
/** Shared chatbot signals only — never task-private contextTypes. */
const CHAT_SIGNAL_CONTEXT_TYPES = new Set([
  "conversation_summary",
  "coordination",
  "policy_and_trust",
]);

function inferReportingCategory(
  contexts: AggregationContext[],
  applicationType?: string | null,
): ReportingCategory {
  // Prefer the job's declared application type over inferring from context keys,
  // so task-authored contextTypes cannot reclassify the report surface.
  const explicit = (applicationType ?? "").trim().toLowerCase()
  if (explicit && explicit !== "unknown" && ["web", "os-app", "chatbot", "survey"].includes(explicit)) {
    return explicit as ReportingCategory
  }

  const contextTypes = new Set(contexts.map((context) => context.contextType).filter(Boolean) as string[])
  if ([...contextTypes].some((type) => CHAT_SIGNAL_CONTEXT_TYPES.has(type))) return "chatbot"
  if ([...contextTypes].some((type) => WEB_SIGNAL_CONTEXT_TYPES.has(type))) return "web"
  if ([...contextTypes].some((type) => OS_APP_SIGNAL_CONTEXT_TYPES.has(type))) return "os-app"
  if (contextTypes.has("question_response")) return "survey"
  return "generic"
}

type InsightGroup = "outcome" | "process" | "feedback"

/** Shared context types → narrative lens. Unknown/task-authored types fall through. */
const CONTEXT_GROUP_BY_TYPE: Record<string, InsightGroup> = {
  task_outcome: "outcome",
  decision: "outcome",
  persona_alignment: "outcome",
  persona_constraint: "outcome",
  web_artifact: "outcome",
  goal_component: "outcome",
  decision_process: "process",
  conversation_summary: "process",
  coordination: "process",
  policy_and_trust: "process",
  web_interaction: "process",
  user_feedback: "feedback",
  feedback: "feedback",
  experience: "feedback",
}

/** Reading order across the whole report: what happened → how it went → how personas felt. */
const INSIGHT_GROUP_ORDER: InsightGroup[] = ["outcome", "process", "feedback"]

function insightGroupLabel(group: InsightGroup, t: ReportTranslate): string {
  switch (group) {
    case "outcome":
      return t("reports.insight.outcome");
    case "process":
      return t("reports.insight.process");
    case "feedback":
      return t("reports.insight.feedback");
  }
}

function insightGroupBlurb(group: InsightGroup, t: ReportTranslate): string {
  switch (group) {
    case "outcome":
      return t("reports.insight.outcomeBlurb");
    case "process":
      return t("reports.insight.processBlurb");
    case "feedback":
      return t("reports.insight.feedbackBlurb");
  }
}

function contextGroup(contextType: string | null | undefined): InsightGroup | null {
  return contextType ? CONTEXT_GROUP_BY_TYPE[contextType] ?? null : null
}

function insightGroupRank(contextType: string | null | undefined): number {
  const group = contextGroup(contextType)
  return group ? INSIGHT_GROUP_ORDER.indexOf(group) : INSIGHT_GROUP_ORDER.length
}

function contextPriority(context: AggregationContext, category: ReportingCategory): number {
  const mapped = CONTEXT_PRIORITY_BY_CATEGORY[category][context.contextType ?? ""]
  const base = mapped != null ? mapped : contextTypeMeta(context.contextType)?.order ?? 50
  // Surveys keep their own question-first ordering.
  if (category === "survey") return base
  // Group first (Outcome → Process → Feedback), then the tuned per-category order within a group.
  return insightGroupRank(context.contextType) * 100 + base
}

function trialStatus(trial: HarborTrialRow): "done" | "failed" | "running" | "pending" {
  if (trial.error || trial.succeeded === false) return "failed";
  if (trial.completed) return "done";
  if (trial.completed === false) return "running";
  return "pending";
}

function trialStatusLabel(status: ReturnType<typeof trialStatus>, t?: ReportTranslate): string {
  switch (status) {
    case "done":
      return t ? t("reports.status.done") : "Done";
    case "failed":
      return t ? t("reports.status.failed") : "Failed";
    case "running":
      return t ? t("reports.status.running") : "Running";
    default:
      return t ? t("reports.status.pending") : "Pending";
  }
}

const TRIAL_STATUS_STYLES: Record<
  ReturnType<typeof trialStatus>,
  { className: string; icon: string; fill?: 0 | 1 }
> = {
  running: { className: "bg-warn/10 text-warn", icon: "autorenew" },
  done: { className: "bg-secondary/10 text-secondary", icon: "check_circle", fill: 1 },
  failed: { className: "bg-danger/10 text-danger", icon: "error", fill: 1 },
  pending: { className: "glass-tile text-text-dim", icon: "hourglass_empty" },
};

function TrialStatusBadge({ trial }: { trial: HarborTrialRow }) {
  const { t } = useI18n();
  const status = trialStatus(trial);
  const style = TRIAL_STATUS_STYLES[status];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-mono text-[12px] uppercase tracking-wide ${style.className}`}
    >
      <Sym
        name={style.icon}
        size={12}
        fill={style.fill}
        className={status === "running" ? "shrink-0 animate-rb-spin" : "shrink-0"}
      />
      {trialStatusLabel(status, t)}
    </span>
  );
}

function TrialPersonaIdentity({ trial }: { trial: HarborTrialRow }) {
  const displayName = personaPrimaryName(trial.personaName, trial.personaId);
  const codename = trial.personaId ? personaDisplayId(trial.personaId) : trial.trialName;
  const personaKey = trial.personaId ?? trial.trialName;

  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <PersonaAvatar personaId={personaKey} size="sm" />
      <div className="min-w-0">
        <p className="truncate font-medium text-text-main">{displayName}</p>
        <p className="truncate font-mono text-[12px] text-text-dim">{codename}</p>
      </div>
    </div>
  );
}

function metricValue(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function reportingStatusLabel(status: string | null | undefined, t: ReportTranslate): string {
  const normalized = (status ?? "").trim().toLowerCase();
  switch (normalized) {
    case "queued":
      return t("reports.status.queued");
    case "running":
      return t("reports.status.summarizing");
    case "completed":
      return t("reports.status.ready");
    case "completed_with_errors":
      return t("reports.status.readyWithIssues");
    case "partial":
      return t("reports.status.partlyReady");
    case "partial_with_errors":
      return t("reports.status.partlyReadyWithIssues");
    case "failed":
      return t("reports.status.failed");
    case "ready":
    case "ready_for_llm":
      return t("reports.status.waitingToSummarize");
    case "not_applicable":
      return t("reports.status.notApplicable");
    default:
      return normalized ? normalized.split("_").join(" ") : t("reports.status.unknown");
  }
}

function reportingStatusClassName(status: string | null | undefined): string {
  const normalized = (status ?? "").trim().toLowerCase();
  if (normalized === "queued" || normalized === "running") {
    return "bg-warn/10 text-warn";
  }
  if (normalized === "completed") {
    return "bg-secondary/10 text-secondary";
  }
  if (normalized === "completed_with_errors" || normalized === "partial_with_errors" || normalized === "failed") {
    return "bg-danger/10 text-danger";
  }
  if (normalized === "ready" || normalized === "partial") {
    return "bg-primary/10 text-primary";
  }
  return "glass-tile text-text-dim";
}

function ratioWidth(count: number, total: number): string {
  const safeTotal = Math.max(total, 1)
  return `${Math.max(6, Math.round((count / safeTotal) * 100))}%`
}

function previewText(value: string | null | undefined, limit = 220): string {
  const normalized = (value ?? "").trim().replace(/\s+/g, " ")
  if (!normalized) return ""
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, limit - 1).trimEnd()}…`
}

/** Full prose for PDF / evidence quotes — do not collapse whitespace mid-sentence beyond a soft cap. */
function fullProseText(value: string | null | undefined, limit = 8000): string {
  const normalized = (value ?? "").trim().replace(/\s+/g, " ")
  if (!normalized) return ""
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, limit - 1).trimEnd()}…`
}

/** Long self-report prompts should stay sentence case — not CSS uppercase. */
function isProseFacetTitle(label: string): boolean {
  const text = label.trim()
  if (text.length > 42) return true
  if (/[—?]/.test(text)) return true
  return text.split(/\s+/).filter(Boolean).length > 6
}

function facetTitleClassName(label: string, size: "sm" | "md" = "md"): string {
  if (isProseFacetTitle(label)) {
    return size === "sm"
      ? "text-[11px] font-medium leading-snug text-text-dim normal-case tracking-normal"
      : "text-[13px] font-medium leading-snug text-text-dim normal-case tracking-normal"
  }
  return size === "sm"
    ? "text-[11px] font-medium uppercase tracking-wide text-text-dim"
    : "text-[13px] font-medium uppercase tracking-wide text-text-dim"
}

function primaryFacetForContext(context: AggregationContext): AggregationField | null {
  return context.facets.find((facet) => facet.role === "primary") ?? context.facets[0] ?? null
}

function explanationFacetForContext(context: AggregationContext): AggregationField | null {
  return (
    context.facets.find((facet) => facet.role === "explanation") ??
    context.facets.find((facet) => facet.kind === "textual") ??
    null
  )
}

/** Survey reasons only — never reuse the primary answer facet. */
function surveyReasonFacetForContext(context: AggregationContext): AggregationField | null {
  const primary = primaryFacetForContext(context)
  const byRole = context.facets.find((facet) => facet.role === "explanation")
  if (byRole && byRole.key !== primary?.key) return byRole
  return (
    context.facets.find(
      (facet) => facet.kind === "textual" && facet.key !== primary?.key && facet.role !== "primary",
    ) ?? null
  )
}

function humanizeContextTypeKey(contextType: string): string {
  return contextType
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (ch) => ch.toUpperCase())
}

function contextTypeMeta(contextType: AggregationContextType | null | undefined) {
  if (!contextType) return null
  const known = CONTEXT_TYPE_META[contextType]
  if (known) return known
  // Task-authored contextTypes: title-case the key, no bespoke copy.
  return {
    badge: humanizeContextTypeKey(contextType),
    description: null as string | null,
    order: 50,
  }
}

function contextTypeBadge(
  contextType: AggregationContextType | null | undefined,
  t?: ReportTranslate,
): string | null {
  if (!t) return contextTypeMeta(contextType)?.badge ?? null
  switch (contextType) {
    case "question_response":
      return t("reports.context.question")
    case "trial_summary":
      return t("reports.context.trialSummary")
    case "decision":
      return t("reports.context.decision")
    case "task_outcome":
      return t("reports.context.taskOutcome")
    case "decision_process":
      return t("reports.context.decisionProcess")
    case "conversation_summary":
      return t("reports.context.conversationSummary")
    case "experience":
      return t("reports.context.experience")
    case "user_feedback":
    case "feedback":
      return t("reports.context.userFeedback")
    case "policy_and_trust":
      return t("reports.context.policyAndTrust")
    case "coordination":
      return t("reports.context.coordination")
    case "web_interaction":
      return t("reports.context.webInteraction")
    case "web_artifact":
      return t("reports.context.webArtifact")
    case "goal_component":
      return t("reports.context.goalComponent")
    case "persona_alignment":
      return t("reports.context.personaAlignment")
    case "persona_constraint":
      return t("reports.context.personaConstraint")
    default:
      return contextTypeMeta(contextType)?.badge ?? null
  }
}

function contextTypeDescription(context: AggregationContext, t?: ReportTranslate): string | null {
  if (!t) return contextTypeMeta(context.contextType)?.description ?? null
  switch (context.contextType) {
    case "question_response":
      return t("reports.context.questionDescription")
    case "trial_summary":
      return t("reports.context.trialSummaryDescription")
    case "decision":
      return t("reports.context.decisionDescription")
    case "task_outcome":
      return t("reports.context.taskOutcomeDescription")
    case "decision_process":
      return t("reports.context.decisionProcessDescription")
    case "conversation_summary":
      return t("reports.context.conversationSummaryDescription")
    case "experience":
      return t("reports.context.experienceDescription")
    case "user_feedback":
    case "feedback":
      return t("reports.context.userFeedbackDescription")
    case "policy_and_trust":
      return t("reports.context.policyAndTrustDescription")
    case "coordination":
      return t("reports.context.coordinationDescription")
    case "web_interaction":
      return t("reports.context.webInteractionDescription")
    case "web_artifact":
      return t("reports.context.webArtifactDescription")
    case "goal_component":
      return t("reports.context.goalComponentDescription")
    case "persona_alignment":
      return t("reports.context.personaAlignmentDescription")
    case "persona_constraint":
      return t("reports.context.personaConstraintDescription")
    default:
      return contextTypeMeta(context.contextType)?.description ?? null
  }
}

function isHeuristicAggregationSummary(text: string): boolean {
  const normalized = text.trim()
  return (
    /^All \d+ available trials reported the same text:/i.test(normalized) ||
    /^Collected \d+ text responses across \d+ unique values/i.test(normalized) ||
    /^All \d+ answers (point to the same theme|converge on one theme|converge on one main topic):/i.test(
      normalized,
    ) ||
    /^Across \d+ answers/i.test(normalized)
  )
}

function isUnanimousField(field: AggregationField): boolean {
  if (field.kind !== "categorical") return false
  const counts = field.categorical?.counts ?? []
  return counts.length === 1 && counts[0].count === field.presentCount && field.presentCount > 0
}

function contextDivergenceScore(context: AggregationContext): number {
  let score = 0
  for (const facet of context.facets) {
    if (facet.kind === "categorical") {
      score += facet.categorical?.distinctCount ?? facet.categorical?.counts?.length ?? 0
    } else if (facet.kind === "textual") {
      score += facet.textual?.uniqueCount ?? 0
    }
  }
  return score
}

/** Contract enum → plain reporting language (never show snake_case to readers). */
const BUCKET_LABEL_KEYS: Record<string, MessageKey> = {
  // booleans / satisfaction
  "true": "reports.bucket.yes",
  "false": "reports.bucket.no",
  yes: "reports.bucket.yes",
  no: "reports.bucket.no",
  partially: "reports.bucket.partially",
  partial: "reports.bucket.partially",
  // outcome_status (chat + web/os-app)
  resolved: "reports.bucket.resolved",
  partially_resolved: "reports.bucket.partiallyResolved",
  unresolved: "reports.bucket.unresolved",
  escalated: "reports.bucket.escalated",
  abandoned: "reports.bucket.abandoned",
  blocked: "reports.bucket.blocked",
  passed: "reports.bucket.passed",
  failed: "reports.bucket.failed",
  infeasible_correct: "reports.bucket.infeasibleCorrect",
  infeasible_incorrect: "reports.bucket.infeasibleIncorrect",
  error: "reports.bucket.error",
  // conversation_path
  direct_resolution: "reports.bucket.directResolution",
  clarify_then_resolve: "reports.bucket.clarifyThenResolve",
  clarify_then_partial: "reports.bucket.clarifyThenPartial",
  handoff_or_followup: "reports.bucket.handoffOrFollowup",
  stalled: "reports.bucket.stalled",
  other: "reports.bucket.other",
  // resolution_basis
  tool_state: "reports.bucket.toolState",
  conversation_commitment: "reports.bucket.conversationCommitment",
  user_feedback: "reports.bucket.userFeedback",
  policy_guardrail: "reports.bucket.policyGuardrail",
  // next_step_owner
  none: "reports.bucket.none",
  agent: "reports.bucket.agent",
  user: "reports.bucket.user",
  external: "reports.bucket.external",
  shared: "reports.bucket.shared",
  // policy / groundedness / coordination
  pass: "reports.bucket.pass",
  warn: "reports.bucket.warn",
  fail: "reports.bucket.fail",
  not_evaluated: "reports.bucket.notEvaluated",
  verified: "reports.bucket.verified",
  mixed: "reports.bucket.mixed",
  unsupported: "reports.bucket.unsupported",
  agent_only: "reports.bucket.agentOnly",
  user_followup_required: "reports.bucket.userFollowupRequired",
  shared_world: "reports.bucket.sharedWorld",
  handoff: "reports.bucket.handoff",
  clear: "reports.bucket.clear",
  confusing: "reports.bucket.confusing",
  not_applicable: "reports.bucket.notApplicable",
  // goal / failure buckets
  near_complete: "reports.bucket.nearComplete",
  complete: "reports.bucket.complete",
  not_attempted: "reports.bucket.notAttempted",
  navigation: "reports.bucket.navigation",
  grounding: "reports.bucket.grounding",
  tool_use: "reports.bucket.toolUse",
  misread_instruction: "reports.bucket.misreadInstruction",
  missing_knowledge: "reports.bucket.missingKnowledge",
  validation_mismatch: "reports.bucket.validationMismatch",
  environment: "reports.bucket.environment",
  unsafe_action: "reports.bucket.unsafeAction",
  state_exact: "reports.bucket.stateExact",
  state_tolerant: "reports.bucket.stateTolerant",
  artifact_exact: "reports.bucket.artifactExact",
  artifact_semantic: "reports.bucket.artifactSemantic",
  hybrid: "reports.bucket.hybrid",
}

function formatBucketLabel(value: string, t?: ReportTranslate): string {
  const normalized = value.trim().toLowerCase().replace(/[\s-]+/g, "_")
  if (!normalized) return value
  if (normalized in BUCKET_LABEL_KEYS) {
    return t
      ? t(BUCKET_LABEL_KEYS[normalized])
      : SOURCE_MESSAGES[BUCKET_LABEL_KEYS[normalized]]
  }
  // Already human sentence-ish (contains spaces or punctuation) — keep as-is.
  if (/[\s,:]/.test(value.trim()) && !/_/.test(value)) return value.trim()
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function formatCategoricalDistribution(field: AggregationField | null, t?: ReportTranslate): string {
  const counts = field?.categorical?.counts ?? []
  if (counts.length === 0) return "—"
  const total = Math.max(
    field?.presentCount ?? 0,
    counts.reduce((sum, entry) => sum + entry.count, 0),
    1,
  )
  // Compact share form for small enums (Yes/No, yes/partially/no).
  if (counts.length <= 3) {
    return counts
      .map((entry) => `${formatBucketLabel(entry.value, t)} ${entry.count}/${total}`)
      .join(" · ")
  }
  return counts.map((entry) => `${formatBucketLabel(entry.value, t)} (${entry.count})`).join(" · ")
}

type InsightTone = "success" | "warn" | "danger" | "primary"

/** Per-value tone for a single categorical bucket (yes/partial/no style). */
function bucketTone(value: string): InsightTone {
  const v = value.trim().toLowerCase().replace(/[\s-]+/g, "_")
  if (
    ["no", "false", "failed", "unresolved", "blocked", "stalled", "unmet", "missed", "not_met", "abandoned"].includes(v)
  ) {
    return "danger"
  }
  if (v.includes("partial") || ["partially", "escalated"].includes(v)) return "warn"
  if (
    ["yes", "true", "passed", "complete", "resolved", "selected", "met", "satisfied", "aligned"].includes(v) ||
    (v.includes("resolve") && !v.includes("partial"))
  ) {
    return "success"
  }
  return "primary"
}

function segmentBarClass(tone: InsightTone): string {
  switch (tone) {
    case "success":
      return "bg-secondary"
    case "warn":
      return "bg-warn"
    case "danger":
      return "bg-danger"
    default:
      return "bg-primary/55"
  }
}

function ratingTone(avg: number | null | undefined): InsightTone {
  if (avg == null || Number.isNaN(avg)) return "warn"
  if (avg >= 7) return "success"
  if (avg >= 4) return "warn"
  return "danger"
}

function categoricalFacetTone(field: AggregationField | null): InsightTone {
  const values = (field?.categorical?.counts ?? []).map((entry) => entry.value.toLowerCase())
  if (values.length === 0) return "primary"
  if (
    values.some((value) =>
      ["no", "false", "failed", "unresolved", "blocked", "stalled", "unmet", "missed", "not_met"].includes(
        value,
      ),
    )
  ) {
    return "danger"
  }
  if (
    values.some(
      (value) =>
        ["partially", "partially_resolved", "partial", "partial_met"].includes(value) ||
        value.includes("partial") ||
        value.includes("clarify"),
    )
  ) {
    return "warn"
  }
  if (
    values.some(
      (value) =>
        ["yes", "true", "passed", "complete", "resolved", "selected", "met", "satisfied", "aligned"].includes(
          value,
        ) || (value.includes("resolve") && !value.includes("partial")),
    )
  ) {
    return "success"
  }
  return "primary"
}

function inferRatingScale(field: AggregationField): number | null {
  const max = field.numerical?.max
  if (max == null) return null
  if (max <= 5) return 5
  if (max <= 10) return 10
  if (max <= 100) return 100
  return null
}

/** True only for real rating/score facets — not raw counts like answer_count. */
function looksLikeRatingFacet(field: AggregationField): boolean {
  const haystack = `${field.facetKey} ${field.key} ${field.label}`.toLowerCase()
  if (
    haystack.includes("count") ||
    haystack.includes("answer_count") ||
    haystack.includes("trajectory") ||
    haystack.includes("event")
  ) {
    return false
  }
  if (!(haystack.includes("rating") || haystack.includes("score") || haystack.includes("likert"))) {
    return false
  }
  return inferRatingScale(field) != null
}

function facetUsesSemanticTone(field: AggregationField): boolean {
  if (field.kind === "numerical") return looksLikeRatingFacet(field)
  if (field.kind === "categorical") return categoricalFacetTone(field) !== "primary"
  return false
}

type InsightChipSegment = { label: string; count: number; tone: InsightTone }

type InsightChipProps = {
  label: string
  value: string
  tone?: InsightTone
  variant?: "neutral" | "semantic"
  meterPct?: number | null
  segments?: InsightChipSegment[]
  segmentTotal?: number
  group?: InsightGroup
}

function facetToInsightChip(field: AggregationField, t: ReportTranslate): InsightChipProps | null {
  const label = humanizeFacetLabel(field.label, field.key, t)
  if (field.kind === "numerical") {
    const avg = field.numerical?.avg ?? null
    const scale = inferRatingScale(field)
    const isRating = looksLikeRatingFacet(field)
    // Only append /5 or /10 for real ratings — never for counts (e.g. answer_count=9 → "9/10").
    const suffix = isRating ? (scale === 10 ? "/10" : scale === 5 ? "/5" : "") : ""
    return {
      label,
      value: `${formatNumericalSummary(field)}${suffix}`,
      variant: isRating ? "semantic" : "neutral",
      tone: isRating ? ratingTone(avg) : "primary",
      meterPct: isRating && scale != null && avg != null ? (avg / scale) * 100 : null,
    }
  }
  if (field.kind === "categorical") {
    const tone = categoricalFacetTone(field)
    const counts = field.categorical?.counts ?? []
    const total = Math.max(
      field.presentCount ?? 0,
      counts.reduce((sum, entry) => sum + entry.count, 0),
      1,
    )
    const segments: InsightChipSegment[] = counts.map((entry) => ({
      label: formatBucketLabel(entry.value, t),
      count: entry.count,
      tone: bucketTone(entry.value),
    }))
    return {
      label,
      value: formatCategoricalDistribution(field, t),
      variant: facetUsesSemanticTone(field) ? "semantic" : "neutral",
      tone,
      segments,
      segmentTotal: total,
    }
  }
  return null
}

function insightFacetsForContext(context: AggregationContext): AggregationField[] {
  const facets: AggregationField[] = []
  const push = (facet: AggregationField | null | undefined) => {
    if (!facet || facet.kind === "textual") return
    if (!facets.some((entry) => entry.key === facet.key)) facets.push(facet)
  }
  push(primaryFacetForContext(context))
  const isFeedback =
    context.contextType === "user_feedback" || context.contextType === "feedback"
  for (const facet of context.facets) {
    if (facet.role === "score" && looksLikeRatingFacet(facet)) push(facet)
    if (facet.kind === "categorical" && facetUsesSemanticTone(facet)) push(facet)
    // Self-report enums always belong in At a glance — including unanimous
    // "unsure" / single-bucket answers that fail the semantic-tone heuristic.
    if (isFeedback && facet.kind === "categorical" && facet.role === "evidence") {
      push(facet)
    }
  }
  return facets
}

function buildHeadlineInsightChips(
  contexts: AggregationContext[],
  coverage: HarborJobAggregation["coverage"],
  category: ReportingCategory,
  t: ReportTranslate,
  options?: { excludeFacetKeys?: ReadonlySet<string> },
): InsightChipProps[] {
  if (category === "survey") {
    return buildSurveyCoverageStats(contexts, coverage, t).map((stat) => ({
      label: stat.label,
      value: stat.value,
      variant: "neutral",
      tone: "primary",
    }))
  }
  // Coverage tiles already show trial completion — chips only carry signals not expanded below.
  const chips: InsightChipProps[] = []
  const exclude = options?.excludeFacetKeys ?? new Set<string>()
  const seen = new Set<string>()
  for (const context of orderedContexts(contexts, category)) {
    // Chatbot At a glance mirrors General: basics + self-report only.
    // Task-authored contextTypes stay in Custom.
    if (category === "chatbot" && !isChatbotGeneralContext(context.contextType)) continue
    if (shouldCompactContext(context, category)) continue
    const group = contextGroup(context.contextType) ?? undefined
    for (const facet of insightFacetsForContext(context)) {
      if (seen.has(facet.key) || exclude.has(facet.key)) continue
      const nonFeedbackCount = chips.filter((chip) => chip.group !== "feedback").length
      // Keep room for authored self-report enums; don't let outcome/process fill a hard cap.
      if (group !== "feedback" && nonFeedbackCount >= 6) continue
      seen.add(facet.key)
      const chip = facetToInsightChip(facet, t)
      if (chip) chips.push({ ...chip, group })
    }
  }
  return chips
}

/** Survey header extras — mirror single-trial debrief (types + agreement), never a global Likert mean. */
function buildSurveyCoverageStats(
  contexts: AggregationContext[],
  coverage: HarborJobAggregation["coverage"],
  t?: ReportTranslate,
): Array<{ label: string; value: string; hint?: string }> {
  const stats: Array<{ label: string; value: string; hint?: string }> = []
  const questionContexts = contexts.filter((context) => context.contextType === "question_response")
  const questionCount = questionContexts.length
  const summary = contexts.find((context) => context.contextType === "trial_summary")

  if (coverage.completedTrials !== coverage.trialCount) {
    stats.push({
      label: t ? t("reports.report.completed") : "Completed",
      value: `${coverage.completedTrials}/${coverage.trialCount}`,
      hint: t ? t("reports.report.stillRunningOrFailed") : "Still running or failed",
    })
  }

  const answerCount = summary?.facets.find(
    (facet) => facet.key === "answer_count" || facet.facetKey === "answer_count",
  )
  if (answerCount?.kind === "numerical" && answerCount.numerical?.avg != null) {
    const avg = answerCount.numerical.avg
    const expected = questionCount > 0 ? questionCount : (answerCount.numerical.max ?? null)
    // Only surface when personas skipped questions — full completion is implied by Questions.
    if (expected != null && Math.abs(avg - expected) > 0.05) {
      stats.push({
        label: t ? t("reports.report.answered") : "Answered",
        value: `${metricValue(avg)} / ${expected}`,
        hint: t
          ? t("reports.report.avgQuestionsAnswered")
          : "Avg questions answered per persona",
      })
    }
  }

  const agreement = buildSurveyAgreementStat(questionContexts, t)
  if (agreement) stats.push(agreement)

  return stats
}

/** Count instrument questions by type — same chip language as single-trial debrief. */
function buildSurveyQuestionTypeCounts(
  contexts: AggregationContext[],
  t?: ReportTranslate,
): SurveyQuestionTypeCount[] {
  const totals = new Map<string, number>()
  for (const context of contexts) {
    if (context.contextType !== "question_response") continue
    const type = resolveSurveyQuestionType(context, primaryFacetForContext(context))
    if (type === "unknown") continue
    totals.set(type, (totals.get(type) ?? 0) + 1)
  }
  return [...totals.entries()]
    .map(([type, count]) => ({
      type,
      label: surveyQuestionTypeLabel(type, t),
      count,
    }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
}

/** Per-question consensus — same labels as the question cards (Unanimous / Clear / Split). */
function surveyQuestionConsensus(context: AggregationContext): "unanimous" | "clear" | "split" | null {
  const primary = primaryFacetForContext(context)
  if (!primary || (primary.presentCount ?? 0) <= 0) return null
  const questionType = resolveSurveyQuestionType(context, primary)

  if (questionType === "likert" || primary.kind === "numerical") {
    const scale = likertScaleBounds(context, primary)
    const points = likertScalePoints(context, primary, scale)
    const filled = points.filter((point) => point.count > 0).length
    if (filled <= 1) return "unanimous"
    const avg = primary.numerical?.avg
    if (avg != null && (avg >= scale.max - 0.35 || avg <= scale.min + 0.35)) return "clear"
    return "split"
  }

  if (
    questionType === "single_choice" ||
    questionType === "multi_choice" ||
    primary.kind === "categorical"
  ) {
    const items = surveyAnswerItems(context, primary)
    const denom = Math.max(primary.presentCount ?? 0, 1)
    const ranked = [...items].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
    const leader = ranked.find((item) => item.count > 0)
    const chosen = ranked.filter((item) => item.count > 0).length
    if (chosen <= 1 && (leader?.count ?? 0) > 0) return "unanimous"
    const share = leader ? leader.count / denom : 0
    if (share >= 0.6) return "clear"
    return "split"
  }

  if (questionType === "free_text" || primary.kind === "textual") {
    const themes = freeTextThemes(primary)
    if (themes.length === 0) return null
    const present = Math.max(primary.presentCount ?? 0, 1)
    if (themes.length === 1) return "unanimous"
    if (themes[0].count / present >= 0.6) return "clear"
    return "split"
  }

  return null
}

function buildSurveyAgreementStat(
  questionContexts: AggregationContext[],
  t?: ReportTranslate,
): { label: string; value: string; hint?: string } | null {
  let unanimous = 0
  let clear = 0
  let split = 0
  for (const context of questionContexts) {
    const consensus = surveyQuestionConsensus(context)
    if (consensus === "unanimous") unanimous += 1
    else if (consensus === "clear") clear += 1
    else if (consensus === "split") split += 1
  }
  const scored = unanimous + clear + split
  if (scored === 0) return null

  if (unanimous === scored) {
    return {
      label: t ? t("reports.report.agreement") : "Agreement",
      value: t ? t("reports.report.unanimous") : "Unanimous",
      hint: t
        ? t("reports.report.allQuestions", { count: scored })
        : `All ${scored} question${scored === 1 ? "" : "s"}`,
    }
  }
  if (split === scored) {
    return {
      label: t ? t("reports.report.agreement") : "Agreement",
      value: t ? t("reports.report.split") : "Split",
      hint: t
        ? t("reports.report.allQuestionsDiverge", { count: scored })
        : `All ${scored} question${scored === 1 ? "" : "s"} diverge`,
    }
  }
  const aligned = unanimous + clear
  return {
    label: t ? t("reports.report.agreement") : "Agreement",
    value: `${aligned}/${scored}`,
    hint: [
      unanimous > 0
        ? t
          ? t("reports.report.unanimousCount", { count: unanimous })
          : `${unanimous} unanimous`
        : null,
      clear > 0
        ? t
          ? t("reports.report.clearCount", { count: clear })
          : `${clear} clear`
        : null,
      split > 0
        ? t
          ? t("reports.report.splitCount", { count: split })
          : `${split} split`
        : null,
    ]
      .filter(Boolean)
      .join(" · "),
  }
}

/** One categorical facet → labeled distribution bars (share %). */
function FacetCategoricalDistribution({ facet }: { facet: AggregationField }) {
  const { t } = useI18n()
  const counts = facet.categorical?.counts ?? []
  const total = counts.reduce((sum, entry) => sum + entry.count, 0)
  const label = humanizeFacetLabel(facet.label, facet.key, t)
  return (
    <div className="rounded-lg bg-surface/45 px-3 py-2.5">
      <div className="mb-2 text-[13px] font-medium text-text-main" title={facet.label}>
        {label}
      </div>
      <CountBars
        items={counts.map((entry) => ({ label: formatBucketLabel(entry.value, t), count: entry.count }))}
        total={total}
        compact
        showShare
      />
    </div>
  )
}

/**
 * Facets that describe *how* a trial was measured/judged rather than the result
 * itself. They are process metadata (often constant across the cohort) and add
 * noise to Common analysis, so we never chart them as distributions.
 */
const COMMON_METADATA_FACET_KEYS = new Set(["resolution_basis", "verifier_mode", "verifier_kind"])

/** Categorical facets worth charting in Common analysis (skip metadata + single-value). */
function isChartableCommonCategorical(facet: AggregationField): boolean {
  if (facet.kind !== "categorical") return false
  const leaf = facetKeyLeaf(facet.key).toLowerCase().replace(/-/g, "_")
  if (COMMON_METADATA_FACET_KEYS.has(leaf)) return false
  const counts = facet.categorical?.counts ?? []
  if (counts.length === 0) return false
  // A single-value "distribution" (everyone answered the same) is a 100% bar with
  // no comparison value — keep it only if it is the context's primary answer.
  if (counts.length === 1 && facet.role !== "primary") return false
  return true
}

function contextHasCommonContent(
  context: AggregationContext,
  crossViews: AggregationCrossFacetView[],
): boolean {
  const hasCategorical = context.facets.some(isChartableCommonCategorical)
  const hasNumerical = context.facets.some(
    (facet) => facet.kind === "numerical" && facet.numerical?.avg != null,
  )
  return hasCategorical || hasNumerical || crossViews.length > 0
}

/** True once the reporting LLM has produced real prose for this summary. */
function summaryHasLlmContent(summary: AggregationSummary): boolean {
  return (summary.status ?? "").toLowerCase() === "llm_completed"
}

/** Completed auto reason-summaries for a context (Common analysis). */
function autoReasonSummaries(context: AggregationContext): AggregationSummary[] {
  return (context.summaries ?? []).filter((summary) => summary.auto && summaryHasLlmContent(summary))
}

/** L2 Common analysis: one context, every facet charted by its data type. */
/** Prominent, consistent section header used across every Detailed tab so users
 *  can tell at a glance which part of the report they're looking at. */
function ContextSectionHeader({
  title,
  description,
}: {
  title: string
  description?: string | null
}) {
  return (
    <div className="flex items-center gap-2 border-b border-border/50 pb-2">
      <span className="h-4 w-[3px] shrink-0 rounded-full bg-primary/70" aria-hidden />
      <h4 className="shrink-0 text-[14px] font-semibold text-text-main">{title}</h4>
      {description ? (
        <span className="min-w-0 flex-1 truncate text-[12px] text-text-dim" title={description}>
          {description}
        </span>
      ) : null}
    </div>
  )
}

function CommonContextPanel({
  context,
  trialCount,
}: {
  context: AggregationContext
  trialCount: number
}) {
  const { t } = useI18n()
  const title = contextTypeBadge(context.contextType, t) ?? context.label
  const summaries = autoReasonSummaries(context)
  // When an auto LLM summary exists for a reason facet, it replaces the raw-quote
  // cross-facet view; otherwise (LLM off) the example quotes remain as fallback.
  const summarizedLeaves = new Set(
    summaries.map((summary) => facetKeyLeaf(summary.targetFacetKey).toLowerCase().replace(/-/g, "_")),
  )
  const crossViews = crossFacetViewsForContext(context).filter(
    (view) => !summarizedLeaves.has(facetKeyLeaf(view.textFacetKey).toLowerCase().replace(/-/g, "_")),
  )
  const facets = orderedFacets(context.facets)
  const categoricalFacets = facets.filter(isChartableCommonCategorical)
  const numericalFacets = facets.filter(
    (facet) => facet.kind === "numerical" && facet.numerical?.avg != null,
  )

  return (
    <div className="space-y-3 rounded-xl glass-tile p-3">
      <ContextSectionHeader title={title} description={contextTypeDescription(context, t)} />

      {categoricalFacets.length > 0 ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {categoricalFacets.map((facet) => (
            <FacetCategoricalDistribution key={facet.key} facet={facet} />
          ))}
        </div>
      ) : null}

      {numericalFacets.length > 0 ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {numericalFacets.map((facet) => (
            <NumericalDistributionCard key={facet.key} facet={facet} trialCount={trialCount} />
          ))}
        </div>
      ) : null}

      {summaries.map((summary) => (
        <SummaryDisclosure key={summary.id} summary={summary} />
      ))}

      {crossViews.map((view, index) => (
        <CrossFacetViewDisclosure
          key={`${context.key}-${view.type}-${index}`}
          crossFacetView={view}
        />
      ))}
    </div>
  )
}

/** Small bar chart for a numerical facet with a bounded discrete scale (e.g. 1–10 ratings). */
function NumericalDistributionCard({
  facet,
  trialCount,
}: {
  facet: AggregationField
  trialCount: number
}) {
  const { t } = useI18n()
  const num = facet.numerical
  const label = humanizeFacetLabel(facet.label, facet.key, t)
  const avg = num?.avg ?? null
  const min = num?.min ?? null
  const max = num?.max ?? null
  const std = num?.std ?? null
  const { lo, hi, hasDeclaredScale } = resolveNumericalDisplayScale(facet)
  const byValue = new Map((num?.counts ?? []).map((entry) => [String(entry.value), entry.count]))

  const points: Array<{ value: number; count: number }> = []
  if (lo != null && hi != null && hi > lo && hi - lo <= 30) {
    for (let value = lo; value <= hi; value += 1) {
      points.push({ value, count: byValue.get(String(value)) ?? 0 })
    }
  }
  const total = points.reduce((sum, point) => sum + point.count, 0)
  const peak = Math.max(...points.map((point) => point.count), 1)
  const span = lo != null && hi != null ? Math.max(hi - lo, 1) : 1
  const avgPct =
    avg != null && lo != null && Number.isFinite(avg)
      ? Math.max(0, Math.min(100, ((avg - lo) / span) * 100))
      : null

  return (
    <div className="rounded-lg glass-tile px-3 py-2.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-medium text-text-main" title={facet.label}>
          {label}
        </span>
        <span className="font-mono text-[13px] text-text-dim">
          {t("reports.report.avg")} {metricValue(avg)}
          {hasDeclaredScale && hi != null ? ` / ${hi}` : ""}
        </span>
      </div>

      {points.length > 0 && total > 0 ? (
        <div className="relative mt-3 px-1">
          {avgPct != null ? (
            <div
              className="pointer-events-none absolute -top-1 bottom-5 z-10 w-px -translate-x-1/2 bg-text-main/70"
              style={{ left: `calc(4px + (100% - 8px) * ${avgPct / 100})` }}
            />
          ) : null}
          <div className="flex h-16 items-end gap-1">
            {points.map((point, index) => {
              const heightPct = point.count > 0 ? Math.max(8, Math.round((point.count / peak) * 100)) : 3
              return (
                <div key={point.value} className="flex min-w-0 flex-1 flex-col items-center gap-1">
                  <div className="flex h-12 w-full items-end">
                    <div
                      className={`w-full rounded-t ${point.count > 0 ? likertSegmentClass(index, points.length) : "bg-outline/25"}`}
                      style={{ height: `${heightPct}%` }}
                      title={`${point.value}: ${point.count}`}
                    />
                  </div>
                  <div className="font-mono text-[11px] text-text-dim">{point.value}</div>
                </div>
              )
            })}
          </div>
        </div>
      ) : (
        <div className="mt-1.5 font-mono text-[20px] leading-none text-text-main">{metricValue(avg)}</div>
      )}

      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-0.5 text-[12px] text-text-dim">
        {min != null ? <span>{t("reports.report.min")} {metricValue(min)}</span> : null}
        {max != null ? <span>{t("reports.report.max")} {metricValue(max)}</span> : null}
        {avg != null ? <span>{t("reports.report.avg")} {metricValue(avg)}</span> : null}
        {std != null ? <span>± {metricValue(std)}</span> : null}
        <span>{t("reports.report.personasCount", { count: num?.count ?? trialCount })}</span>
      </div>
    </div>
  )
}

/** Declared scale (1–10) vs observed cohort min/max — never treat observed max as full score. */
function resolveNumericalDisplayScale(facet: AggregationField): {
  lo: number | null
  hi: number | null
  hasDeclaredScale: boolean
} {
  const leaf = facetKeyLeaf(facet.key).toLowerCase().replace(/-/g, "_")
  const haystack = `${leaf} ${facet.facetKey ?? ""} ${facet.label}`.toLowerCase()
  const isOverallExperience =
    leaf === "overall_experience_rating" || haystack.includes("overall experience")
  const isKnownTenPoint =
    isOverallExperience || leaf === "trust_level" || leaf === "effort_rating"

  if (typeof facet.scaleMin === "number" && typeof facet.scaleMax === "number") {
    return { lo: facet.scaleMin, hi: facet.scaleMax, hasDeclaredScale: true }
  }
  if (isKnownTenPoint) {
    return {
      lo: typeof facet.scaleMin === "number" ? facet.scaleMin : 1,
      hi: typeof facet.scaleMax === "number" ? facet.scaleMax : 10,
      hasDeclaredScale: true,
    }
  }
  if (typeof facet.scaleMax === "number") {
    return {
      lo: typeof facet.scaleMin === "number" ? facet.scaleMin : facet.numerical?.min != null ? Math.floor(facet.numerical.min) : 1,
      hi: facet.scaleMax,
      hasDeclaredScale: true,
    }
  }
  const inferred = inferRatingScale(facet)
  if (inferred != null) {
    return {
      lo: typeof facet.scaleMin === "number" ? facet.scaleMin : 1,
      hi: inferred,
      hasDeclaredScale: true,
    }
  }
  const min = facet.numerical?.min
  const max = facet.numerical?.max
  return {
    lo: min != null ? Math.floor(min) : null,
    hi: max != null ? Math.ceil(max) : null,
    hasDeclaredScale: false,
  }
}

function ratingBarClass(tone: "success" | "warn" | "danger"): string {
  if (tone === "success") return "bg-secondary"
  if (tone === "warn") return "bg-warn"
  return "bg-danger"
}

function shouldCompactContext(context: AggregationContext, category: ReportingCategory): boolean {
  if (HEADLINE_CONTEXT_TYPES[category].has(context.contextType ?? "")) return false
  if (!EXECUTION_CONTEXT_TYPES_BY_CATEGORY[category].has(context.contextType ?? "")) return false
  const primary = primaryFacetForContext(context)
  return primary != null && primary.kind === "categorical" && isUnanimousField(primary)
}

function splitContexts(contexts: AggregationContext[], category: ReportingCategory): {
  headline: AggregationContext[]
  compact: AggregationContext[]
} {
  const ordered = orderedContexts(contexts, category)
  const headline: AggregationContext[] = []
  const compact: AggregationContext[] = []
  for (const context of ordered) {
    if (shouldCompactContext(context, category)) compact.push(context)
    else headline.push(context)
  }
  return { headline, compact }
}

function orderedContexts(contexts: AggregationContext[], category: ReportingCategory): AggregationContext[] {
  return [...contexts].sort((a, b) => {
    const aPriority = contextPriority(a, category)
    const bPriority = contextPriority(b, category)
    if (aPriority !== bPriority) return aPriority - bPriority
    const aDivergence = contextDivergenceScore(a)
    const bDivergence = contextDivergenceScore(b)
    if (aDivergence !== bDivergence) return bDivergence - aDivergence
    const aOrder = contextTypeMeta(a.contextType)?.order ?? 99
    const bOrder = contextTypeMeta(b.contextType)?.order ?? 99
    if (aOrder !== bOrder) return aOrder - bOrder
    return a.label.localeCompare(b.label)
  })
}

/**
 * Text facets that are fixed labels / non-persona prose — grouping them by an
 * answer just repeats the same string in every bucket, so they are noise.
 * Mirrors the backend `skip_text_leaves` guard; also filtered here so stale
 * aggregation artifacts never surface the view.
 */
const CROSS_FACET_SKIP_TEXT_LEAVES = new Set(["task_goal_label"])

function isNoisyCrossFacetView(view: AggregationCrossFacetView): boolean {
  const leaf = facetKeyLeaf(view.textFacetKey).toLowerCase().replace(/-/g, "_")
  if (CROSS_FACET_SKIP_TEXT_LEAVES.has(leaf)) return true
  const samples = new Set<string>()
  let totalCount = 0
  for (const bucket of view.buckets ?? []) {
    totalCount += bucket.count ?? 0
    for (const sample of bucket.samples ?? []) samples.add(sample.trim())
  }
  // Low-diversity text (a couple of templated notes repeated across the cohort)
  // just echoes the same quote in every bucket — not a useful grouping.
  return samples.size <= 2 && totalCount > 2
}

function crossFacetViewsForContext(context: AggregationContext): AggregationCrossFacetView[] {
  const raw = context.crossFacetViews ?? context.relationships ?? []
  return raw.filter((view) => !isNoisyCrossFacetView(view))
}

function summaryBucketsForContext(context: AggregationContext, t?: ReportTranslate): CountBarItem[] {
  const summary = context.summaries?.find((item) => item.buckets.length > 0)
  if (summary) {
    return summary.buckets.map((bucket) => ({
      label: formatBucketLabel(bucket.bucket, t),
      count: bucket.count,
      detail: bucket.summary ?? null,
    }))
  }
  const categorical = context.facets.find((facet) => facet.kind === "categorical")
  if (categorical?.categorical?.counts?.length) {
    return categorical.categorical.counts.map((entry) => ({
      label: formatBucketLabel(entry.value, t),
      count: entry.count,
    }))
  }
  const crossFacetView = crossFacetViewsForContext(context).find(
    (item) => (item.buckets?.length ?? 0) > 0,
  )
  return (crossFacetView?.buckets ?? []).map((bucket) => ({
    label: bucket.category,
    count: bucket.count,
  }))
}

function contextLeadText(context: AggregationContext, t?: ReportTranslate): string {
  const summary = context.summaries?.find((item) => item.overall?.summary)?.overall?.summary
  // Collapsed cards keep a short tease; expand for the full quote.
  if (summary && !isHeuristicAggregationSummary(summary)) return previewText(summary, 220)

  const explanation = explanationFacetForContext(context)
  const explanationSample = explanation?.textual?.samples?.[0]
  if (explanationSample && !isHeuristicAggregationSummary(explanation?.textual?.summary ?? explanationSample)) {
    return previewText(explanationSample, 220)
  }
  if (explanation?.textual?.summary && !isHeuristicAggregationSummary(explanation.textual.summary)) {
    return previewText(explanation.textual.summary, 220)
  }

  const primary = primaryFacetForContext(context)
  if (primary?.kind === "categorical" && isUnanimousField(primary)) {
    const value = primary.categorical?.counts?.[0]?.value ?? "—"
    return t
      ? t("reports.report.allPersonasValue", {
          count: primary.presentCount,
          value: formatBucketLabel(value, t),
        })
      : `All ${primary.presentCount} personas: ${formatBucketLabel(value, t)}`
  }
  if (primary?.kind === "numerical") {
    return t
      ? `${humanizeFacetLabel(primary.label, primary.key, t)}: ${formatNumericalSummary(primary)}`
      : `${primary.label}: ${formatNumericalSummary(primary)}`
  }

  const buckets = summaryBucketsForContext(context, t)
  if (buckets.length > 0) {
    return `${buckets[0].label} (${buckets[0].count})`
  }

  return ""
}

function reportingSummary(
  reporting: HarborJobAggregation["reporting"] | null | undefined,
  t: ReportTranslate,
): { value: string; hint: string } | null {
  if (!reporting || reporting.status === "not_applicable") return null

  const total = reporting.totalUnits ?? 0
  const completed = reporting.completedUnits ?? 0
  const ready = reporting.readyUnits ?? 0
  const failed = reporting.failedUnits ?? 0
  const model = reporting.model ? ` · ${reporting.model}` : ""
  const status = reportingStatusLabel(reporting.status, t)

    if ((reporting.status === "ready" || reporting.status === "partial") && completed === 0) {
    return {
      value: status,
      hint: t("reports.status.toSummarize", { count: ready || total, model }),
    }
  }

  if (reporting.status === "queued" || reporting.status === "running") {
    return {
      value: `${completed}/${total}`,
      hint: `${status}${model}`,
    }
  }

  if (
    reporting.status === "completed" ||
    reporting.status === "completed_with_errors" ||
    reporting.status === "partial_with_errors" ||
    reporting.status === "failed"
  ) {
    return {
      value: status,
      hint: t("reports.status.completedWithFailures", { completed, total, failed, model }),
    }
  }

  return {
    value: status,
    hint: t ? t("reports.status.unitCount", { count: total, model }) : `${total} units${model}`,
  }
}

function orderedFacets(facets: AggregationField[]): AggregationField[] {
  return [...facets].sort((a, b) => {
    const aRank = a.role === "primary" ? 0 : a.role === "explanation" ? 2 : 1
    const bRank = b.role === "primary" ? 0 : b.role === "explanation" ? 2 : 1
    if (aRank !== bRank) return aRank - bRank
    return a.label.localeCompare(b.label)
  })
}

type CountBarItem = {
  label: string
  count: number
  detail?: string | null
}

function formatNumericalSummary(field: AggregationField | null, suffix = ""): string {
  if (!field) return "—"
  const avg = field.numerical?.avg
  if (avg == null) return "—"
  const min = field.numerical?.min
  const max = field.numerical?.max
  if (min != null && max != null && min !== max) {
    return `${metricValue(min)}–${metricValue(max)} avg ${metricValue(avg)}${suffix}`
  }
  return `${metricValue(avg)}${suffix}`
}

function InsightChip({
  label,
  value,
  tone = "primary",
  variant = "neutral",
  meterPct,
  segments,
  segmentTotal,
}: {
  label: string
  value: string
  tone?: "primary" | "success" | "warn" | "danger"
  /** semantic = always apply tone colors; neutral = grey summary chip */
  variant?: "neutral" | "semantic"
  meterPct?: number | null
  segments?: InsightChipSegment[]
  segmentTotal?: number
}) {
  const toneTextClass: Record<NonNullable<typeof tone>, string> = {
    success: "text-secondary",
    primary: "text-primary",
    warn: "text-warn",
    danger: "text-danger",
  }
  const toneBoxClass: Record<NonNullable<typeof tone>, string> = {
    success: "bg-secondary/10",
    primary: "bg-primary/15",
    warn: "bg-warn/10",
    danger: "bg-danger/10",
  }
  const swatchTextClass: Record<InsightTone, string> = {
    success: "text-secondary",
    primary: "text-primary",
    warn: "text-warn",
    danger: "text-danger",
  }
  const colored = variant === "semantic"
  const meterTone = tone === "primary" ? "warn" : tone

  const hasSegments = Array.isArray(segments) && segments.length > 0
  const total = Math.max(segmentTotal ?? 0, hasSegments ? segments.reduce((s, e) => s + e.count, 0) : 0, 1)

  return (
    <div
      className={`${hasSegments ? "min-w-[188px] flex-1" : "min-w-[108px]"} rounded-lg px-2.5 py-1.5 ${
        colored ? toneBoxClass[tone] : "glass-tile"
      }`}
    >
      <div className={facetTitleClassName(label, "sm")}>{label}</div>
      {hasSegments ? (
        <div className="mt-1.5 space-y-1.5">
          <div className="flex h-2 overflow-hidden rounded-full bg-surface-high/70">
            {segments.map((seg) =>
              seg.count > 0 ? (
                <div
                  key={seg.label}
                  className={segmentBarClass(seg.tone)}
                  style={{ width: `${(seg.count / total) * 100}%` }}
                  title={`${seg.label}: ${seg.count}/${total}`}
                />
              ) : null,
            )}
          </div>
          <div className="flex flex-wrap gap-x-2.5 gap-y-0.5">
            {segments.map((seg) => (
              <span key={seg.label} className="inline-flex items-center gap-1 text-[11px] text-text-variant">
                <span className={`h-2 w-2 shrink-0 rounded-sm ${segmentBarClass(seg.tone)}`} />
                <span className="text-text-dim">{seg.label}</span>
                <span className={`font-medium ${swatchTextClass[seg.tone]}`}>{seg.count}</span>
              </span>
            ))}
          </div>
        </div>
      ) : (
        <div className={`mt-0.5 text-[14px] font-medium ${colored ? toneTextClass[tone] : "text-text-main"}`}>
          {value}
        </div>
      )}
      {meterPct != null ? (
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-high/80">
          <div
            className={`h-full rounded-full ${ratingBarClass(meterTone)}`}
            style={{ width: `${Math.max(4, Math.min(100, meterPct))}%` }}
          />
        </div>
      ) : null}
    </div>
  )
}

type CohortAnalysisGroup = {
  contextKey: string
  contextLabel: string
  contextType: string | null
  summaries: AggregationSummary[]
  judges: AggregationJudge[]
  crossFacetViews: AggregationCrossFacetView[]
}

function collectCohortAnalysisGroups(
  contexts: AggregationContext[],
  t?: ReportTranslate,
): CohortAnalysisGroup[] {
  const groups: CohortAnalysisGroup[] = []
  for (const context of contexts) {
    // Auto reason-summaries live in Common analysis, not the reporting.json Custom section.
    const summaries = (context.summaries ?? []).filter((summary) => !summary.auto)
    const judges = context.judges ?? []
    const crossFacetViews = crossFacetViewsForContext(context)
    if (summaries.length + judges.length + crossFacetViews.length === 0) continue
    groups.push({
      contextKey: context.key,
      contextLabel: contextTypeBadge(context.contextType, t) ?? context.label,
      contextType: context.contextType ?? null,
      summaries,
      judges,
      crossFacetViews,
    })
  }
  return groups
}

type LensAnalysisGroup = {
  contextKey: string
  contextLabel: string
  summaries: AggregationSummary[]
  judges: AggregationJudge[]
}

/** Keep only the summaries/judges tagged for a given analysis lens ("task" or "persona"). */
function analysisGroupsForLens(
  groups: CohortAnalysisGroup[],
  lens: "task" | "persona",
): LensAnalysisGroup[] {
  return groups
    .map((group) => ({
      contextKey: group.contextKey,
      contextLabel: group.contextLabel,
      summaries: group.summaries.filter((summary) => (summary.lens ?? "task") === lens),
      judges: group.judges.filter((judge) => (judge.lens ?? "task") === lens),
    }))
    .filter((group) => group.summaries.length + group.judges.length > 0)
}

function AnalysisGroupList({ groups }: { groups: LensAnalysisGroup[] }) {
  return (
    <>
      {groups.map((group) => (
        <div key={group.contextKey} className="space-y-3 rounded-xl glass-tile p-3">
          <ContextSectionHeader title={group.contextLabel} />
          {group.summaries.map((summary) => (
            <SummaryDisclosure key={summary.id} summary={summary} />
          ))}
          {group.judges.map((judge) => (
            <JudgeDisclosure key={judge.id} judge={judge} />
          ))}
        </div>
      ))}
    </>
  )
}

type PersonaDistributionGroup = {
  contextKey: string
  contextLabel: string
  distributions: AggregationPersonaDistribution[]
  standaloneFacets: AggregationField[]
  choiceOptions?: Array<{ id: string; label: string }>
}

/** Default persona lens: optional standalone facets + signal × segment cards. */
function collectPersonaDistributionGroups(
  contexts: AggregationContext[],
  t?: ReportTranslate,
): PersonaDistributionGroup[] {
  const groups: PersonaDistributionGroup[] = []
  for (const context of contexts) {
    const distributions = context.personaDistributions ?? []
    const standaloneFacets = (context.personaStandaloneFacets ?? []).slice(0, 2)
    if (distributions.length === 0 && standaloneFacets.length === 0) continue
    const labeled = explorerContextLabel(context, t)
    groups.push({
      contextKey: context.key,
      contextLabel: labeled.meta
        ? `${labeled.meta} · ${labeled.label}`
        : labeled.label,
      distributions,
      standaloneFacets,
      choiceOptions: context.choiceOptions?.map((option) => ({
        id: option.id,
        label: option.label?.trim() || option.id,
      })),
    })
  }
  return groups
}

/** Column order for the heatmap: facet values (numeric ascending, or categories). */
function personaDistributionColumns(
  distribution: AggregationPersonaDistribution,
): string[] {
  const numeric = distribution.kind === "numerical"
  if (!numeric && distribution.categories && distribution.categories.length > 0) {
    return distribution.categories
  }
  const seen = new Set<string>()
  const values: string[] = []
  for (const bucket of distribution.buckets) {
    const counts = numeric ? bucket.numerical?.counts : bucket.categorical?.counts
    for (const row of counts ?? []) {
      if (seen.has(row.value)) continue
      seen.add(row.value)
      values.push(row.value)
    }
  }
  if (numeric) {
    values.sort((a, b) => {
      const na = Number(a)
      const nb = Number(b)
      if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb
      return a.localeCompare(b)
    })
  }
  return values
}

/**
 * Joint distribution of one signal facet × one persona dimension, as a heatmap
 * matrix: rows = persona segments, columns = facet values (numeric scale points
 * or categories), cell colour = share within that segment. Shows the actual
 * interaction shape (not a collapsed average), and unifies numeric + categorical.
 */
function stripSplitBySuffix(label: string): string {
  // Tasks sometimes bake "— split by X" into titles; the card already shows the
  // persona group-by, so drop the baked-in phrase to avoid "… by X by X".
  return (
    label
      .replace(/\s*[—–-]\s*split by\s+.+$/i, "")
      .replace(/\s+split by\s+.+$/i, "")
      .trim() || label
  )
}

function PersonaDistributionCard({
  distribution,
  choiceOptions,
}: {
  distribution: AggregationPersonaDistribution
  /** Questionnaire options — map opaque ids to readable column labels. */
  choiceOptions?: Array<{ id: string; label: string }>
}) {
  const { t } = useI18n()
  const numeric = distribution.kind === "numerical"
  const columns = personaDistributionColumns(distribution)
  const columnMeta = useMemo(
    () => buildDistributionColumnMeta(columns, { numeric, choiceOptions }, t),
    [columns, numeric, choiceOptions, t],
  )
  const signalBase = stripSplitBySuffix(
    humanizeFacetLabel(distribution.facetLabel, distribution.facetKey, t),
  )
  const segmentLabel = distribution.groupByLabel || t("reports.report.personaSegment")
  const showSegmentSuffix = Boolean(distribution.groupByPersonaDimension?.trim())
  const countFor = (
    bucket: AggregationPersonaDistribution["buckets"][number],
    value: string,
  ): number => {
    const counts = numeric ? bucket.numerical?.counts : bucket.categorical?.counts
    return counts?.find((row) => row.value === value)?.count ?? 0
  }
  return (
    <div className="space-y-2 rounded-lg border border-outline/35 bg-surface/50 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <div className="min-w-0 text-[13px] font-medium text-text-main">
          {signalBase}
          {showSegmentSuffix ? (
            <span className="font-normal text-text-dim">
              {" "}
              {t("reports.report.bySegmentOfPersona", { segment: segmentLabel })}
            </span>
          ) : null}
        </div>
        <span className="shrink-0 font-mono text-[11px] text-text-dim">
          {t("reports.report.countShort", { count: distribution.total })}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="text-left text-text-dim">
              <th className="py-1 pr-3 font-medium">{segmentLabel}</th>
              <th className="py-1 pr-3 text-right font-medium">{t("reports.report.n")}</th>
              {columns.map((value) => {
                const meta = columnMeta.get(value) ?? {
                  fullLabel: formatBucketLabel(value, t),
                  title: formatBucketLabel(value, t),
                  compact: false,
                }
                return (
                  <th
                    key={value}
                    className={`px-1 py-1 font-medium align-bottom ${
                      meta.compact ? "max-w-[3.25rem] text-center" : "text-center"
                    }`}
                    title={meta.title}
                  >
                    {meta.compact ? (
                      <span
                        className="mx-auto inline-block max-h-[9rem] whitespace-normal break-words text-[10px] leading-snug text-text-main"
                        style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
                      >
                        {meta.fullLabel}
                      </span>
                    ) : (
                      <span className="inline-block text-[12px] text-text-main">
                        {meta.fullLabel}
                      </span>
                    )}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {distribution.buckets.map((bucket) => (
              <tr key={bucket.bucket} className="border-t border-outline/25">
                <td className="py-1.5 pr-3 font-medium text-text-main">
                  {formatBucketLabel(bucket.bucket, t)}
                </td>
                <td className="py-1.5 pr-3 text-right font-mono text-text-variant">
                  {bucket.count}
                </td>
                {columns.map((value) => {
                  const count = countFor(bucket, value)
                  const share = bucket.count > 0 ? count / bucket.count : 0
                  const pct = Math.round(share * 100)
                  const intensity = count > 0 ? 0.1 + 0.55 * share : 0
                  const meta = columnMeta.get(value)
                  const answerLabel = meta?.title ?? formatBucketLabel(value, t)
                  return (
                    <td key={value} className="p-0.5 text-center align-middle">
                      <span
                        className="flex h-7 min-w-[2rem] items-center justify-center rounded font-mono text-[11px] text-text-main"
                        style={{
                          backgroundColor:
                            count > 0
                              ? `rgba(99, 102, 241, ${intensity.toFixed(3)})`
                              : "transparent",
                        }}
                        title={
                          count > 0
                            ? t("reports.report.distributionCell", {
                                bucket: formatBucketLabel(bucket.bucket, t),
                                answer: answerLabel,
                                count,
                                total: bucket.count,
                                percent: pct,
                              })
                            : "0"
                        }
                      >
                        {count > 0 ? count : <span className="text-text-dim/40">·</span>}
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-text-dim">
        {t("reports.report.distributionExplanation", {
          kind: numeric ? t("reports.report.value") : t("reports.report.answer"),
        })}
      </p>
    </div>
  )
}

function PersonaDistributionList({
  groups,
  trialCount,
}: {
  groups: PersonaDistributionGroup[]
  trialCount: number
}) {
  const { t } = useI18n()
  if (groups.length === 0) return null
  return (
    <>
      {groups.map((group) => (
        <div key={`dist-${group.contextKey}`} className="space-y-3 rounded-xl glass-tile p-3">
          <ContextSectionHeader title={group.contextLabel} />
          {group.standaloneFacets.length > 0 ? (
            <>
              <p className="text-[12px] text-text-dim">{t("reports.report.overallForCohort")}</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {group.standaloneFacets.map((facet) =>
                  facet.kind === "numerical" && facet.numerical?.avg != null ? (
                    <NumericalDistributionCard
                      key={`solo-${group.contextKey}-${facet.key}`}
                      facet={facet}
                      trialCount={trialCount}
                    />
                  ) : facet.kind === "categorical" ? (
                    <FacetCategoricalDistribution
                      key={`solo-${group.contextKey}-${facet.key}`}
                      facet={facet}
                    />
                  ) : null,
                )}
              </div>
            </>
          ) : null}
          {group.distributions.length > 0 ? (
            <>
              <p className="text-[12px] text-text-dim">
                {group.standaloneFacets.length > 0
                  ? t("reports.report.segmentDifferences")
                  : t("reports.report.resultSegmentDifferences")}
              </p>
              <div className="grid gap-3 md:grid-cols-2">
                {group.distributions.map((distribution) => (
                  <PersonaDistributionCard
                    key={distribution.id}
                    distribution={distribution}
                    choiceOptions={group.choiceOptions}
                  />
                ))}
              </div>
            </>
          ) : null}
        </div>
      ))}
    </>
  )
}

type PersonaExplorerEntry = {
  contextKey: string
  contextLabel: string
  distribution: AggregationPersonaDistribution
  choiceOptions?: Array<{ id: string; label: string }>
}

const LONG_COLUMN_LABEL_CHARS = 22

type DistributionColumnMeta = {
  fullLabel: string
  title: string
  /** Narrow vertical/wrapped header instead of a single horizontal line. */
  compact: boolean
}

/**
 * Column headers for persona heatmaps.
 * Short labels stay on one line; long labels wrap vertically (web-style).
 * Opaque choice ids (e.g. "c") map through questionnaire options when available.
 */
function buildDistributionColumnMeta(
  columns: string[],
  {
    numeric,
    choiceOptions,
  }: {
    numeric: boolean
    choiceOptions?: Array<{ id: string; label: string }>
  },
  t?: ReportTranslate,
): Map<string, DistributionColumnMeta> {
  const byId = new Map(
    (choiceOptions ?? []).map((option, index) => [
      option.id,
      { index: index + 1, label: option.label.trim() || option.id },
    ]),
  )
  const meta = new Map<string, DistributionColumnMeta>()
  columns.forEach((value) => {
    if (numeric) {
      meta.set(value, {
        fullLabel: value,
        title: t ? t("reports.report.scoreValue", { value }) : `Score ${value}`,
        compact: false,
      })
      return
    }
    const choice = byId.get(value)
    if (choice) {
      meta.set(value, {
        fullLabel: choice.label,
        title: t
          ? t("reports.report.optionValue", { index: choice.index, label: choice.label })
          : `Option ${choice.index}: ${choice.label}`,
        compact: choice.label.length > LONG_COLUMN_LABEL_CHARS,
      })
      return
    }
    const pretty = formatBucketLabel(value, t)
    meta.set(value, {
      fullLabel: pretty,
      title: pretty,
      compact: pretty.length > LONG_COLUMN_LABEL_CHARS,
    })
  })
  return meta
}

/** Prefer the real question prompt over the generic "Question" type badge. */
function explorerContextLabel(
  context: AggregationContext,
  t?: ReportTranslate,
): {
  label: string
  meta?: string
} {
  if (context.contextType === "question_response") {
    const prompt = (context.label || "").trim()
    const shortId = (context.key || "").replace(/^question\./i, "").trim()
    if (prompt) {
      return {
        label: prompt,
        meta: shortId
          ? t
            ? t("reports.context.questionId", { id: shortId })
            : `Question ${shortId}`
          : undefined,
      }
    }
    if (shortId) return { label: shortId }
  }
  return {
    label: contextTypeBadge(context.contextType, t) ?? context.label,
  }
}

/** Flatten every eligible facet × dimension pairing across contexts. */
function collectPersonaExplorerEntries(
  contexts: AggregationContext[],
  t?: ReportTranslate,
): PersonaExplorerEntry[] {
  const entries: PersonaExplorerEntry[] = []
  for (const context of contexts) {
    const options = context.personaDistributionOptions ?? []
    if (options.length === 0) continue
    const labeled = explorerContextLabel(context, t)
    const choiceOptions = context.choiceOptions?.map((option) => ({
      id: option.id,
      label: option.label?.trim() || option.id,
    }))
    for (const distribution of options) {
      entries.push({
        contextKey: context.key,
        contextLabel: labeled.meta
          ? `${labeled.meta} · ${labeled.label}`
          : labeled.label,
        distribution,
        choiceOptions,
      })
    }
  }
  return entries
}

const BREAK_DOWN_BY_HINTS = {
  study: "reports.report.breakDownByHint",
  withMore: "reports.report.breakDownByHintWithMore",
} as const

/**
 * Interactive persona explorer: pick a context and persona dimension to cross-tab.
 * Survey mode hides the result-field picker (answers are always the primary facet).
 */
function PersonaDistributionExplorer({
  entries,
  hideResultField = false,
}: {
  entries: PersonaExplorerEntry[]
  hideResultField?: boolean
}) {
  const { t } = useI18n()
  // Level 1 of the cascade: context (Decision, User feedback, …).
  const contextOptions = useMemo((): CockpitSelectOption[] => {
    const seen = new Map<string, CockpitSelectOption>()
    for (const entry of entries) {
      if (!seen.has(entry.contextKey)) {
        const shortId = entry.contextKey.replace(/^question\./i, "").trim()
        // Prefer full prompt as the primary label; keep id as meta for scanability.
        const sep = " · "
        const hasSep = entry.contextLabel.includes(sep)
        const meta = hasSep ? entry.contextLabel.split(sep)[0] : shortId || undefined
        const label = hasSep
          ? entry.contextLabel.slice(entry.contextLabel.indexOf(sep) + sep.length)
          : entry.contextLabel
        seen.set(entry.contextKey, {
          value: entry.contextKey,
          label,
          meta: meta && meta !== label ? meta : undefined,
        })
      }
    }
    return [...seen.values()]
  }, [entries])

  const [contextValue, setContextValue] = useState<string>(
    contextOptions[0]?.value ?? "",
  )
  const activeContext = contextOptions.some((option) => option.value === contextValue)
    ? contextValue
    : contextOptions[0]?.value ?? ""

  // Level 2 of the cascade: facets within the chosen context.
  const facetOptions = useMemo((): CockpitSelectOption[] => {
    const seen = new Map<string, CockpitSelectOption>()
    for (const entry of entries) {
      if (entry.contextKey !== activeContext) continue
      if (!seen.has(entry.distribution.facetKey)) {
        seen.set(entry.distribution.facetKey, {
          value: entry.distribution.facetKey,
          label: stripSplitBySuffix(
            humanizeFacetLabel(
              entry.distribution.facetLabel,
              entry.distribution.facetKey,
              t,
            ),
          ),
        })
      }
    }
    return [...seen.values()]
  }, [entries, activeContext, t])

  const [facetValue, setFacetValue] = useState<string>(facetOptions[0]?.value ?? "")
  const preferredFacet =
    hideResultField
      ? facetOptions.find((option) => option.value === "response")?.value ??
        facetOptions[0]?.value ??
        ""
      : facetOptions.some((option) => option.value === facetValue)
        ? facetValue
        : facetOptions[0]?.value ?? ""
  const activeFacet = preferredFacet

  const { dimOptions, hasMoreAxes } = useMemo((): {
    dimOptions: CockpitSelectOption[]
    hasMoreAxes: boolean
  } => {
    const pending: Array<{
      value: string
      label: string
      axisGroup: "study" | "more"
    }> = []
    const seen = new Set<string>()
    let hasMore = false
    for (const entry of entries) {
      if (entry.contextKey !== activeContext) continue
      if (entry.distribution.facetKey !== activeFacet) continue
      const dimension = entry.distribution.groupByPersonaDimension
      if (!dimension || seen.has(dimension)) continue
      seen.add(dimension)
      const axisGroup =
        entry.distribution.axisGroup === "more" ? "more" : "study"
      if (axisGroup === "more") hasMore = true
      pending.push({
        value: dimension,
        label: entry.distribution.groupByLabel,
        axisGroup,
      })
    }
    return {
      dimOptions: pending.map((item) => ({
        value: item.value,
        label: item.label,
        group: hasMore
          ? item.axisGroup === "more"
            ? t("reports.report.axisGroupMore")
            : t("reports.report.axisGroupStudy")
          : undefined,
      })),
      hasMoreAxes: hasMore,
    }
  }, [entries, activeContext, activeFacet, t])

  const [dimValue, setDimValue] = useState<string>(dimOptions[0]?.value ?? "")
  const activeDim = dimOptions.some((option) => option.value === dimValue)
    ? dimValue
    : dimOptions[0]?.value ?? ""

  const selectedEntry = useMemo(
    () =>
      entries.find(
        (entry) =>
          entry.contextKey === activeContext &&
          entry.distribution.facetKey === activeFacet &&
          entry.distribution.groupByPersonaDimension === activeDim,
      ) ?? null,
    [entries, activeContext, activeFacet, activeDim],
  )

  if (contextOptions.length === 0) return null

  const showResultFieldPicker = !hideResultField && facetOptions.length > 1
  const showDimPicker = dimOptions.length > 1

  return (
    <div className="space-y-3 rounded-xl glass-tile p-3">
      <div className="space-y-1">
        <ContextSectionHeader title={t("reports.report.exploreBySegment")} />
        <p className="text-[12px] text-text-dim">
          {hideResultField
            ? t("reports.report.pickQuestion")
            : showResultFieldPicker
              ? t("reports.report.pickContextResult")
              : t("reports.report.pickContext")}
        </p>
      </div>
      <div className="grid gap-3">
        <CockpitSelect
          label={hideResultField ? t("reports.report.question") : t("reports.report.context")}
          value={activeContext}
          options={contextOptions}
          onChange={setContextValue}
          wrapOptions
          wideMenu
        />
        {showResultFieldPicker || showDimPicker ? (
          <div
            className={`grid gap-2 ${
              showResultFieldPicker && showDimPicker ? "sm:grid-cols-2" : ""
            }`}
          >
            {showResultFieldPicker ? (
              <CockpitSelect
                label={t("reports.report.resultField")}
                value={activeFacet}
                options={facetOptions}
                onChange={setFacetValue}
                hint={t("reports.report.resultFieldHint")}
              />
            ) : null}
            {showDimPicker ? (
              <CockpitSelect
                label={t("reports.report.breakDownBy")}
                value={activeDim}
                options={dimOptions}
                onChange={setDimValue}
                hint={t(BREAK_DOWN_BY_HINTS[hasMoreAxes ? "withMore" : "study"])}
              />
            ) : (
              <p className="rounded-lg border border-outline/35 bg-surface/40 px-3 py-2 text-[12px] text-text-dim">
                {t("reports.report.rowsFixedTo", { label: dimOptions[0]?.label ?? "" })}
              </p>
            )}
          </div>
        ) : null}
      </div>
      {selectedEntry ? (
        <PersonaDistributionCard
          distribution={selectedEntry.distribution}
          choiceOptions={selectedEntry.choiceOptions}
        />
      ) : (
        <p className="rounded-lg border border-outline/35 bg-surface/50 p-3 text-[12px] text-text-dim">
          {t("reports.report.noSegmentBreakdown")}
        </p>
      )}
    </div>
  )
}

/** L1 at-a-glance: one headline chip per outcome dimension. */
function BasicEvaluationPanel({
  aggregation,
  category,
}: {
  aggregation: HarborJobAggregation
  category: ReportingCategory
}) {
  const { t } = useI18n()
  const contexts = aggregation.contexts ?? []
  if (category === "survey") return null
  if (contexts.length === 0 && aggregation.fields.length === 0) return null

  const chips = buildHeadlineInsightChips(contexts, aggregation.coverage, category, t)
  if (chips.length === 0) return null

  const groupedChips = INSIGHT_GROUP_ORDER.map((group) => ({
    group,
    chips: chips.filter((chip) => chip.group === group),
  })).filter((entry) => entry.chips.length > 0)
  const ungroupedChips = chips.filter((chip) => !chip.group)

  return (
    <div className="mt-2.5 space-y-2 rounded-xl bg-primary/10 p-2.5">
      <div>
        <div className="flex items-center gap-2 text-[13px] font-medium uppercase tracking-wide text-primary">
          <Sym name="insights" size={14} />
          {t("reports.report.atAGlance")}
        </div>
        <p className="mt-0.5 text-[13px] leading-relaxed text-text-variant">
          {t("reports.report.atAGlanceDescription")}
        </p>
      </div>

      {groupedChips.length > 0 ? (
        <div className="space-y-2">
          {groupedChips.map(({ group, chips: groupChips }) => (
            <div key={group} className="space-y-1">
              <div className="flex items-baseline gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-primary/80">
                {insightGroupLabel(group, t)}
                <span className="font-normal normal-case tracking-normal text-text-dim">
                  {insightGroupBlurb(group, t)}
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {groupChips.map((chip) => (
                  <InsightChip key={`${chip.label}-${chip.value}`} {...chip} />
                ))}
              </div>
            </div>
          ))}
          {ungroupedChips.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {ungroupedChips.map((chip) => (
                <InsightChip key={`${chip.label}-${chip.value}`} {...chip} />
              ))}
            </div>
          ) : null}
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {chips.map((chip) => (
            <InsightChip key={`${chip.label}-${chip.value}`} {...chip} />
          ))}
        </div>
      )}
    </div>
  )
}

/** Collapsed-by-default detail: distributions + reporting.json group/stratum analyses. */
function DetailedEvaluationPanel({
  aggregation,
  category,
  compactContexts,
  captureMode = false,
  /** Survey per-question cards rendered as the General tab (web-style two-tab layout). */
  surveyHeadlineContexts,
}: {
  aggregation: HarborJobAggregation
  category: ReportingCategory
  compactContexts: AggregationContext[]
  captureMode?: boolean
  surveyHeadlineContexts?: AggregationContext[]
}) {
  const { t } = useI18n()
  const isSurvey = category === "survey"
  const contexts = aggregation.contexts ?? []
  const trialCount = aggregation.coverage.trialCount
  const compactKeys = new Set(compactContexts.map((context) => context.key))

  const commonContexts = orderedContexts(contexts, category).filter(
    (context) =>
      context.contextType !== "trial_summary" &&
      !compactKeys.has(context.key) &&
      contextHasCommonContent(context, crossFacetViewsForContext(context)) &&
      // Chatbot General = basics + self-report only; task-specific angles → Custom.
      (category !== "chatbot" || isChatbotGeneralContext(context.contextType)),
  )
  // Task-specific context panels (e.g. product_behavior) for the Custom tab.
  const customContextPanels = orderedContexts(contexts, category).filter(
    (context) =>
      category === "chatbot" &&
      context.contextType !== "trial_summary" &&
      !compactKeys.has(context.key) &&
      !isChatbotGeneralContext(context.contextType) &&
      contextHasCommonContent(context, crossFacetViewsForContext(context)),
  )

  const analysisGroups = collectCohortAnalysisGroups(contexts, t)
  // Every LLM summary / signal scan renders in Custom analysis (task lens), even
  // when grouped by a persona dimension. Persona insights = distributions only.
  const taskGroups = analysisGroupsForLens(analysisGroups, "task")
  const personaDistGroups = collectPersonaDistributionGroups(contexts, t)
  const personaExplorerEntries = collectPersonaExplorerEntries(contexts, t)

  const surveyGeneralContexts = (surveyHeadlineContexts ?? []).filter(
    (context) => context.contextType !== "trial_summary",
  )
  const hasSurveyGeneral =
    isSurvey &&
    (surveyGeneralContexts.length > 0 || compactContexts.length > 0)
  const hasCommonGeneral =
    !isSurvey && (commonContexts.length > 0 || compactContexts.length > 0)
  const hasGeneral = hasSurveyGeneral || hasCommonGeneral
  const hasCustomTask =
    taskGroups.length > 0 || customContextPanels.length > 0

  const tabs = (
    [
      hasGeneral
        ? {
            id: "general" as const,
            label: isSurvey
              ? t("reports.report.perQuestion")
              : t("reports.report.general"),
          }
        : null,
      personaDistGroups.length > 0 ||
      personaExplorerEntries.length > 0
        ? {
            id: "persona" as const,
            label: t("reports.report.personaInsights"),
          }
        : null,
      hasCustomTask
        ? {
            id: "task" as const,
            label: t("reports.report.customTask"),
          }
        : null,
    ].filter(Boolean) as { id: "general" | "task" | "persona"; label: string }[]
  )

  const [activeTab, setActiveTab] = useState<"general" | "task" | "persona">("general")
  const currentTabId = tabs.some((tab) => tab.id === activeTab) ? activeTab : tabs[0]?.id

  if (tabs.length === 0) return null

  return (
    <StudioGlassPanel className="overflow-hidden bg-surface/95">
      <SectionHeader title={t("reports.report.detailedSection")} />
      <div className="space-y-5 p-4">
        {captureMode || tabs.length <= 1 ? null : (
          <div className="flex gap-1.5 rounded-xl bg-surface/40 p-1" role="tablist">
            {tabs.map((tab) => {
              const active = tab.id === currentTabId
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex-1 rounded-lg border px-3 py-1.5 text-center text-[13px] font-medium transition-colors ${FOCUS_RING} ${
                    active
                      ? "border-primary/30 bg-primary/15 text-primary shadow-sm"
                      : "border-outline/40 bg-surface/60 text-text-variant hover:border-primary/25 hover:bg-surface hover:text-text"
                  }`}
                >
                  {tab.label}
                </button>
              )
            })}
          </div>
        )}

        {tabs.map((tab) => {
          if (!captureMode && tab.id !== currentTabId) return null
          return (
            <div key={tab.id} className="space-y-3">
              {captureMode ? (
                <div className="text-[13px] font-semibold uppercase tracking-wide text-primary">
                  {tab.label}
                </div>
              ) : null}
              {tab.id === "general" ? (
                isSurvey ? (
                  <>
                    {compactContexts.length > 0 ? (
                      <CompactContextGroup contexts={compactContexts} />
                    ) : null}
                    {surveyGeneralContexts.map((context) =>
                      context.contextType === "question_response" ? (
                        <SurveyQuestionCard key={context.key} context={context} />
                      ) : context.contextType === "user_feedback" ||
                        context.contextType === "feedback" ? (
                        <UserFeedbackBatchCard key={context.key} context={context} />
                      ) : (
                        <ContextCard key={context.key} context={context} />
                      ),
                    )}
                  </>
                ) : (
                  <>
                    {compactContexts.length > 0 ? (
                      <CompactContextGroup contexts={compactContexts} />
                    ) : null}
                    {commonContexts.map((context) => (
                      <CommonContextPanel
                        key={`common-${context.key}`}
                        context={context}
                        trialCount={trialCount}
                      />
                    ))}
                  </>
                )
              ) : null}
              {tab.id === "task" ? (
                <>
                  {customContextPanels.map((context) => (
                    <CommonContextPanel
                      key={`custom-${context.key}`}
                      context={context}
                      trialCount={trialCount}
                    />
                  ))}
                  {taskGroups.length > 0 ? (
                    <AnalysisGroupList groups={taskGroups} />
                  ) : null}
                </>
              ) : null}
              {tab.id === "persona" ? (
                <>
                  <PersonaDistributionList
                    groups={personaDistGroups}
                    trialCount={trialCount}
                  />
                  {captureMode ? null : (
                    <PersonaDistributionExplorer
                      entries={personaExplorerEntries}
                      hideResultField={isSurvey}
                    />
                  )}
                </>
              ) : null}
            </div>
          )
        })}
      </div>
    </StudioGlassPanel>
  )
}

function CompactContextGroup({ contexts }: { contexts: AggregationContext[] }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  if (contexts.length === 0) return null

  return (
    <section className="overflow-hidden rounded-xl glass-panel">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={`flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-surface/25 ${FOCUS_RING}`}
      >
        <div>
          <div className="text-[15px] font-medium text-text-main">{t("reports.report.executionChecks")}</div>
          <p className="mt-1 text-[13px] text-text-dim">
            {t("reports.report.allPersonasAgreed", { count: contexts.length })}
          </p>
        </div>
        <span className="inline-flex items-center gap-1 text-[12px] uppercase tracking-wide text-text-dim">
          {open ? t("reports.report.hide") : t("reports.report.show")}
          <Sym name={open ? "expand_less" : "expand_more"} size={14} />
        </span>
      </button>
      <div className="divide-y divide-outline/30 border-t border-outline/35">
        {(open ? contexts : contexts.slice(0, 4)).map((context) => {
          const primary = primaryFacetForContext(context)
          const rawValue = primary?.categorical?.counts?.[0]?.value ?? "—"
          const value = rawValue === "—" ? rawValue : formatBucketLabel(rawValue, t)
          return (
            <div key={context.key} className="flex items-center gap-3 px-4 py-2.5">
              <Sym name="check_circle" size={16} className="shrink-0 text-secondary" fill={1} />
              <div className="min-w-0 flex-1">
                <div className="text-[14px] font-medium text-text-main">
                  {contextTypeBadge(context.contextType, t) ?? context.label}
                </div>
                {contextTypeDescription(context, t) ? (
                  <div className="truncate text-[12px] text-text-dim">
                    {contextTypeDescription(context, t)}
                  </div>
                ) : null}
              </div>
              <div className="shrink-0 text-right">
                <div className="text-[14px] font-medium text-text-main">{value}</div>
                <div className="font-mono text-[12px] text-text-dim">{primary?.presentCount ?? 0}/{primary?.presentCount ?? 0}</div>
              </div>
            </div>
          )
        })}
      </div>
      {!open && contexts.length > 4 ? (
        <div className="border-t border-outline/35 px-4 py-2 text-[13px] text-text-dim">
          {t("reports.report.moreChecks", { count: contexts.length - 4 })}
        </div>
      ) : null}
    </section>
  )
}


function readAgentModel(config: Record<string, unknown> | null): string | null {
  const agents = Array.isArray(config?.agents) ? config.agents : [];
  const firstAgent =
    agents.length > 0 && agents[0] && typeof agents[0] === "object"
      ? (agents[0] as Record<string, unknown>)
      : null;
  return typeof firstAgent?.model_name === "string" ? firstAgent.model_name : null;
}

function readTaskPathFromConfig(config: Record<string, unknown> | null): string | null {
  const tasks = Array.isArray(config?.tasks) ? config.tasks : [];
  const first =
    tasks.length > 0 && tasks[0] && typeof tasks[0] === "object"
      ? (tasks[0] as Record<string, unknown>)
      : null;
  return typeof first?.path === "string" && first.path.trim() ? first.path.trim() : null;
}

function personaPoolFromPath(personaPath: string | null | undefined): string | null {
  if (!personaPath) return null;
  const parts = personaPath.replace(/\\/g, "/").split("/").filter(Boolean);
  if (parts.length < 2) return null;
  const leaf = parts[parts.length - 1] ?? "";
  const parent = parts[parts.length - 2] ?? "";
  const isPersonaFile =
    /^persona_/i.test(leaf) || leaf.endsWith(".yaml") || leaf.endsWith(".yml");
  if (!isPersonaFile) {
    return parent || leaf || null;
  }
  // .../<dataset>/cohorts/cohort-<id>/persona_*.yaml → keep both dataset and cohort
  if (
    parent.startsWith("cohort-") &&
    parts.length >= 4 &&
    parts[parts.length - 3] === "cohorts"
  ) {
    const dataset = parts[parts.length - 4] ?? "";
    return dataset ? `${dataset} · ${parent}` : parent;
  }
  return parent || null;
}

function readPersonaPool(config: Record<string, unknown> | null): string | null {
  const agents = Array.isArray(config?.agents) ? config.agents : [];
  for (const agent of agents) {
    if (!agent || typeof agent !== "object") continue;
    const kwargs = (agent as Record<string, unknown>).kwargs;
    if (!kwargs || typeof kwargs !== "object") continue;
    const personaPath = (kwargs as Record<string, unknown>).persona_path;
    if (typeof personaPath === "string" && personaPath.trim()) {
      return personaPoolFromPath(personaPath.trim());
    }
  }
  return null;
}

function buildPersonaRoster(trials: HarborJobDetail["trials"] | undefined): BatchReportPdfPersona[] {
  const seen = new Set<string>();
  const personas: BatchReportPdfPersona[] = [];
  for (const trial of trials ?? []) {
    const idRaw = (trial.personaId ?? "").trim();
    const id = idRaw ? personaDisplayId(idRaw) : "";
    const name = personaPrimaryName(trial.personaName, trial.personaId);
    const key = idRaw || name || trial.trialName;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    personas.push({
      id: id || key,
      name: name || key,
    });
  }
  return personas.sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
}

function buildCoverageSnapshot(
  aggregation: HarborJobAggregation | null | undefined,
  t: ReportTranslate,
): BatchReportPdfSnapshot[] {
  if (!aggregation) return [];
  const coverage = aggregation.coverage;
  const snap: BatchReportPdfSnapshot[] = [
    {
      label: t("reports.report.trials"),
      value: String(coverage.completedTrials),
      hint: coverage.trialCount !== coverage.completedTrials ? `/ ${coverage.trialCount}` : undefined,
    },
  ];
  if (coverage.pendingTrials > 0) {
    snap.push({ label: t("reports.report.pending"), value: String(coverage.pendingTrials) });
  }
  if (coverage.completedWithoutArtifactTrials > 0) {
    snap.push({
      label: t("reports.report.noArtifact"),
      value: String(coverage.completedWithoutArtifactTrials),
    });
  }
  const reportingStatus = aggregation.reporting?.status;
  if (reportingStatus && reportingStatus !== "not_applicable") {
    snap.push({
      label: t("reports.report.reporting"),
      value: reportingStatusLabel(reportingStatus, t),
    });
  }
  return snap.slice(0, 4);
}

function normalizePersonaStrategy(
  strategy: TaskPersonaStrategy | null | undefined,
): BatchReportPdfPersonaStrategy | null {
  if (!strategy) return null;
  const sampling = readStrategySampling(strategy);
  return {
    mode: sampling.mode,
    allocation: sampling.mode === "stratified" ? sampling.allocation : null,
    perCell:
      sampling.allocation === "perCell" ? sampling.perCell : null,
    sampleSize: sampling.sampleSize,
    seed: strategy.seed ?? null,
    fields: sampling.fields.length ? sampling.fields : undefined,
    dimensionFilters: strategy.dimensionFilters ?? undefined,
    sources: strategy.sources ?? undefined,
  };
}

async function enrichBatchReportPdfMeta(meta: BatchReportPdfMeta): Promise<BatchReportPdfMeta> {
  if (!meta.taskPath) return meta;
  try {
    const detail = await api.getTaskDetail(meta.taskPath);
    const instrumentTitle = detail.questionnaire?.title?.trim() || null;
    const instructionPlain = plainTextFromMarkdown(detail.instructionMarkdown);
    const contextPlain = plainTextFromMarkdown(detail.contextMarkdown);
    const description =
      (detail.description || "").trim() ||
      instructionPlain
        .split(/\n\n+/)
        .map((p) => p.trim())
        .find((p) => p.length > 40 && !/^how to answer/i.test(p)) ||
      null;
    return {
      ...meta,
      taskTitle: instrumentTitle || detail.title?.trim() || meta.taskTitle,
      taskDescription: description || meta.taskDescription || null,
      taskContext: contextPlain || meta.taskContext || null,
      taskInstruction: instructionPlain || meta.taskInstruction || null,
      taskDomain: detail.domain?.trim() || meta.taskDomain || null,
      taskDifficulty: detail.difficulty?.trim() || meta.taskDifficulty || null,
      taskTags: Array.isArray(detail.tags) && detail.tags.length ? detail.tags.map(String) : meta.taskTags,
      taskName: detail.taskName?.trim() || meta.taskName || null,
      applicationType: meta.applicationType || detail.metaType || null,
      personaStrategy: normalizePersonaStrategy(detail.personaStrategy) ?? meta.personaStrategy,
    };
  } catch {
    return meta;
  }
}

function buildBatchReportPdfMeta(
  jobName: string,
  job: HarborJobDetail | undefined,
  aggregation: HarborJobAggregation | null | undefined,
  t: ReportTranslate,
): BatchReportPdfMeta {
  const launch = job?.launch ?? null;
  const result = (job?.result ?? null) as Record<string, unknown> | null;
  const config = (job?.config ?? null) as Record<string, unknown> | null;

  let status = launch?.status ?? null;
  if (!status) {
    if (result?.finished_at) status = "completed";
    else if (result?.started_at) status = "running";
  }

  const started = typeof result?.started_at === "string" ? result.started_at : null;
  const finished = typeof result?.finished_at === "string" ? result.finished_at : null;
  const runWindow = started || finished ? `${started || "-"} -> ${finished || "-"}` : null;
  const generatedAt =
    typeof aggregation?.generatedAt === "string" && aggregation.generatedAt
      ? aggregation.generatedAt
      : null;
  const parallelismRaw = config?.n_concurrent_trials;
  const parallelism =
    typeof parallelismRaw === "number" && Number.isFinite(parallelismRaw)
      ? Math.max(1, Math.floor(parallelismRaw))
      : typeof parallelismRaw === "string" && parallelismRaw.trim() !== "" && Number.isFinite(Number(parallelismRaw))
        ? Math.max(1, Math.floor(Number(parallelismRaw)))
        : null;

  const taskPath = (job?.taskPath ?? readTaskPathFromConfig(config) ?? "").trim() || null;
  const taskTitle =
    (job?.taskTitle ?? "").trim() ||
    humanizePathLeaf(taskPath) ||
    null;
  const applicationType =
    (job?.applicationType ?? job?.metaType ?? "").trim() ||
    (taskPath && /\/survey[_-]/i.test(taskPath) ? "survey" : null);
  const personas = buildPersonaRoster(job?.trials);
  const usage = usageFromJobResult(result);

  return {
    jobName,
    status,
    configPath: launch?.configPath ?? null,
    agentModel: readAgentModel(config),
    parallelism,
    runWindow,
    startedAt: started,
    finishedAt: finished,
    generatedAt,
    applicationType,
    taskPath,
    taskTitle,
    taskDescription: (job?.description ?? "").trim() || null,
    taskDomain: (job?.domain ?? "").trim() || null,
    taskDifficulty: (job?.difficulty ?? "").trim() || null,
    taskTags: Array.isArray(job?.tags) ? job.tags.map(String) : undefined,
    taskName: (job?.taskName ?? "").trim() || null,
    personaPool: readPersonaPool(config),
    personaStrategy: normalizePersonaStrategy(job?.personaStrategy),
    personas,
    snapshot: buildCoverageSnapshot(job?.aggregation, t),
    usage,
  };
}

function shortModelLabel(model: string): string {
  return model.split("/").pop()?.trim() || model;
}

function formatRunDuration(startedAt: string | null | undefined, finishedAt: string | null | undefined): string | null {
  if (!startedAt || !finishedAt) return null;
  const start = Date.parse(startedAt);
  const end = Date.parse(finishedAt);
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return null;
  const sec = Math.round((end - start) / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  if (min < 60) return rem ? `${min}m ${rem}s` : `${min}m`;
  const hr = Math.floor(min / 60);
  const minRem = min % 60;
  return minRem ? `${hr}h ${minRem}m` : `${hr}h`;
}

/** Compact absolute timestamp for report chrome (`Jul 13, 00:38:25`). */
function formatTimestamp(iso: string | null | undefined, withSeconds = false): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return new Date(t).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    ...(withSeconds ? { second: "2-digit" as const } : {}),
    hour12: false,
  });
}

function BatchReportMetaFact({
  label,
  value,
  title,
}: {
  label: string;
  value: string;
  title?: string;
}) {
  return (
    <div className="min-w-0 bg-surface/80 px-3 py-2.5" title={title}>
      <div className="text-[11px] font-medium uppercase tracking-wide text-text-dim">{label}</div>
      <div className="mt-1 text-[14px] leading-snug text-text-main">{value}</div>
    </div>
  );
}

function BatchReportMetaByline({ meta }: { meta: BatchReportPdfMeta }) {
  const { t } = useI18n();
  const model = meta.agentModel ? shortModelLabel(meta.agentModel) : null;
  const duration = formatRunDuration(meta.startedAt, meta.finishedAt);
  const runStart = formatTimestamp(meta.startedAt, true);
  const runEnd = formatTimestamp(meta.finishedAt, true);
  const personasRun = meta.personas?.length ?? 0;

  let runValue: string | null = null;
  if (runStart && runEnd) {
    runValue = duration ? `${runStart} → ${runEnd} · ${duration}` : `${runStart} → ${runEnd}`;
  } else if (runStart || runEnd) {
    runValue = duration ? `${runStart ?? runEnd} · ${duration}` : (runStart ?? runEnd);
  } else if (duration) {
    runValue = t("reports.task.duration", { duration });
  }

  const facts: Array<{ label: string; value: string; title?: string }> = [];
  if (meta.taskTitle || meta.taskPath) {
    facts.push({
      label: t("reports.task.title"),
      value: meta.taskTitle || humanizePathLeaf(meta.taskPath) || meta.taskPath || "",
      title: meta.taskPath ?? undefined,
    });
  }
  // This run's actual persona cohort sits with the execution facts; the
  // default persona strategy is shown separately above.
  if (meta.personaPool) {
    facts.push({
      label: t("reports.task.dataset"),
      value: meta.personaPool,
      title: t("reports.task.sourceDatasetTitle"),
    });
  }
  if (personasRun > 0) {
    facts.push({
      label: t("reports.task.personasRun"),
      value: String(personasRun),
      title: t("reports.task.personasRunTitle"),
    });
  }
  if (model) {
    facts.push({
      label: t("reports.task.agentModel"),
      value: model,
      title: meta.agentModel ?? undefined,
    });
  }
  if (meta.parallelism != null) {
    facts.push({
      label: t("reports.task.parallelism"),
      value: String(meta.parallelism),
      title: t("reports.task.concurrentTrials", { count: meta.parallelism }),
    });
  }
  if (runValue) {
    facts.push({
      label: t("reports.task.run"),
      value: runValue,
      title: meta.runWindow ?? undefined,
    });
  }
  if (hasUsage(meta.usage)) {
    if (meta.usage?.costUsd != null) {
      facts.push({
        label: t("reports.usage.cost"),
        value: formatCostUsd(meta.usage.costUsd),
        title: t("reports.usage.costTitle"),
      });
    }
    const tokenBits: string[] = [];
    if (meta.usage?.nInputTokens != null) {
      tokenBits.push(t("reports.usage.tokenIn", { count: formatTokenCount(meta.usage.nInputTokens) }));
    }
    if (meta.usage?.nOutputTokens != null) {
      tokenBits.push(t("reports.usage.tokenOut", { count: formatTokenCount(meta.usage.nOutputTokens) }));
    }
    if (meta.usage?.nCacheTokens != null && meta.usage.nCacheTokens > 0) {
      tokenBits.push(t("reports.usage.tokenCache", { count: formatTokenCount(meta.usage.nCacheTokens) }));
    }
    if (tokenBits.length) {
      facts.push({
        label: t("reports.usage.tokens"),
        value: tokenBits.join(" · "),
        title: t("reports.usage.tokensTitle"),
      });
    }
    if (meta.usage?.costUsd != null && personasRun > 0) {
      facts.push({
        label: t("reports.usage.avgPerTrial"),
        value: formatCostUsd(meta.usage.costUsd / personasRun),
        title: t("reports.usage.avgPerTrialTitle", { count: personasRun }),
      });
    }
  }
  // "Report" generated time is shown globally in the panel header, not here.

  if (facts.length === 0) return null;

  const colClass =
    facts.length >= 5
      ? "grid-cols-1 sm:grid-cols-2 xl:grid-cols-3"
      : facts.length === 4
        ? "grid-cols-1 sm:grid-cols-2 xl:grid-cols-4"
        : facts.length === 3
          ? "grid-cols-1 sm:grid-cols-3"
          : facts.length === 2
            ? "grid-cols-1 sm:grid-cols-2"
            : "grid-cols-1";

  return (
    <div className={`mt-2.5 grid gap-px overflow-hidden rounded-lg bg-outline/25 ${colClass}`}>
      {facts.map((fact) => (
        <BatchReportMetaFact key={fact.label} label={fact.label} value={fact.value} title={fact.title} />
      ))}
    </div>
  );
}

/** snake_case / kebab-case → Title Case (mirrors the PDF's key humanizer). */
function humanizeStrategyKey(raw: string): string {
  return raw.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function humanizeAllocationLabel(raw: string | null | undefined, t: ReportTranslate): string {
  if (raw === "perCell") return t("personaSetup.allocation.perCell");
  if (raw === "proportional") return t("personaSetup.allocation.proportional");
  if (raw === "equalTotal") return t("personaSetup.allocation.equalTotal");
  return raw ? humanizeStrategyKey(raw) : "";
}

function BatchReportPersonaFactGrid({
  facts,
}: {
  facts: Array<{ label: string; value: string; title?: string }>;
}) {
  if (facts.length === 0) return null;
  const colClass =
    facts.length >= 3 ? "grid-cols-2 sm:grid-cols-3" : facts.length === 2 ? "grid-cols-2" : "grid-cols-1";
  return (
    <div className={`mt-2 grid gap-px overflow-hidden rounded-md bg-outline/20 ${colClass}`}>
      {facts.map((fact) => (
        <BatchReportMetaFact key={fact.label} label={fact.label} value={fact.value} title={fact.title} />
      ))}
    </div>
  );
}

function BatchReportPersonaCardHeader({ icon, label, tag }: { icon: string; label: string; tag: string }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-text-dim">
      <Sym name={icon} size={13} className="text-primary" />
      {label}
      <span className="rounded glass-tile px-1.5 py-0.5 text-[10px] normal-case tracking-normal text-text-dim">
        {tag}
      </span>
    </div>
  );
}

function taskDocumentLabel(id: TaskDocTabId, t: ReportTranslate): string {
  switch (id) {
    case "instruction":
      return t("reports.task.documentInstruction");
    case "context":
      return t("reports.task.documentContext");
    case "questionnaire":
      return t("reports.task.documentQuestionnaire");
    case "output-schema":
      return t("reports.task.documentOutputSchema");
    case "self-report":
      return t("reports.task.documentSelfReport");
  }
}

/** The task's background documents (instruction / context / questionnaire), the
 *  same ones surfaced in the task gallery. Rendered on-screen above the persona
 *  strategy so reviewers get the scenario before the sampling design. Marked
 *  data-pdf-ignore because the PDF already emits its own native Task section. */
function BatchReportTaskBrief({ meta }: { meta: BatchReportPdfMeta }) {
  const { t } = useI18n();
  const taskPath = (meta.taskPath ?? "").trim();

  const detailQuery = useQuery({
    queryKey: ["task-detail", taskPath],
    queryFn: () => api.getTaskDetail(taskPath),
    enabled: Boolean(taskPath),
    staleTime: 300_000,
    retry: 1,
  });
  const detail = detailQuery.data;

  const sections = useMemo(
    () =>
      buildTaskDocSections({
        instructionMarkdown: detail?.instructionMarkdown,
        contextMarkdown: detail?.contextMarkdown,
        questionnaireMarkdown: detail?.questionnaireMarkdown,
        // Surveys never surface a platform-derived output schema in the brief.
        outputSchemaMarkdown:
          detail?.metaType === "survey" ? null : detail?.outputSchemaMarkdown,
        selfReportMarkdown: detail?.selfReportMarkdown,
        hasStructuredQuestionnaire: Boolean(detail?.questionnaire?.questions?.length),
      }),
    [detail],
  );

  const structuredQuestionnaire: SurveyInstrument | null =
    detail?.questionnaire?.questions?.length ? detail.questionnaire : null;

  const [open, setOpen] = useState(false);
  const [activeId, setActiveId] = useState<TaskDocTabId | null>(null);
  const activeSection =
    sections.find((section) => section.id === activeId) ?? sections[0] ?? null;

  const chips: Array<{ label: string; value: string }> = [];
  const applicationType = (meta.applicationType || detail?.metaType || "").trim();
  if (applicationType) chips.push({ label: t("reports.task.type"), value: applicationType });
  const domain = (detail?.domain || meta.taskDomain || "").trim();
  if (domain) chips.push({ label: t("reports.task.domain"), value: domain });
  const difficulty = (detail?.difficulty || meta.taskDifficulty || "").trim();
  if (difficulty) chips.push({ label: t("reports.task.difficulty"), value: difficulty });

  const tags =
    (Array.isArray(detail?.tags) && detail.tags.length
      ? detail.tags
      : meta.taskTags) ?? [];

  const summaryText = (meta.taskDescription ?? detail?.description ?? "").trim();
  const summary =
    summaryText.length > 0
      ? summaryText
      : sections.length > 0
        ? sections.map((section) => taskDocumentLabel(section.id, t)).join(" · ")
        : "";

  const loading = Boolean(taskPath) && detailQuery.isLoading;
  const failed = Boolean(taskPath) && detailQuery.isError && sections.length === 0;

  // Nothing to show at all — no task path, no docs, no blurb.
  if (!taskPath && sections.length === 0 && !summaryText) return null;

  return (
    <div
      data-pdf-ignore
      className="mt-2.5 rounded-lg border border-outline/25 bg-surface/60 px-3 py-2"
    >
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className={`flex w-full items-center justify-between gap-3 text-left ${FOCUS_RING}`}
      >
        <span className="flex min-w-0 items-center gap-2">
          <BatchReportPersonaCardHeader
            icon="description"
            label={t("reports.task.brief")}
            tag={t("reports.task.instructionContext")}
          />
          {!open && summary ? (
            <span className="truncate text-[12px] normal-case tracking-normal text-text-dim">
              {summary}
            </span>
          ) : null}
        </span>
        <Sym
          name={open ? "expand_less" : "expand_more"}
          size={16}
          className="shrink-0 text-text-dim"
        />
      </button>
      {open ? (
        <div className="mt-2.5 space-y-3">
          {chips.length > 0 || tags.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              {chips.map((chip) => (
                <span
                  key={chip.label}
                  className="inline-flex items-center gap-1 rounded-full glass-tile px-2 py-0.5 text-[12px] text-text-variant"
                >
                  <span className="text-text-dim">{humanizeStrategyKey(chip.label)}</span>
                  {humanizeStrategyKey(chip.value)}
                </span>
              ))}
              {tags.map((tag) => (
                <span
                  key={`tag-${tag}`}
                  className="inline-flex items-center rounded-full glass-tile px-2 py-0.5 text-[12px] text-text-variant"
                >
                  {tag}
                </span>
              ))}
            </div>
          ) : null}

          {loading ? (
            <p className="text-[13px] text-text-dim">{t("reports.task.loadingDocuments")}</p>
          ) : null}
          {failed ? (
            <p className="text-[13px] text-danger">
              {detailQuery.error instanceof ApiError
                ? detailQuery.error.message
                : t("reports.task.loadDocumentsFailed")}
            </p>
          ) : null}

          {sections.length > 1 ? (
            <div
              role="tablist"
              aria-label={t("reports.task.documents")}
              className="flex flex-wrap items-center gap-x-1 gap-y-1 border-b border-outline/40"
            >
              {sections.map((section) => {
                const selected = section.id === (activeSection?.id ?? null);
                return (
                  <button
                    key={section.id}
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    onClick={() => setActiveId(section.id)}
                    className={`-mb-px flex items-center gap-1 border-b-2 px-2 py-1.5 text-[12px] font-medium transition ${FOCUS_RING} ${
                      selected
                        ? "border-primary text-primary"
                        : "border-transparent text-text-variant hover:text-text-main"
                    }`}
                  >
                    <Sym name={section.icon} fill={selected ? 1 : 0} size={14} />
                    {taskDocumentLabel(section.id, t)}
                  </button>
                );
              })}
            </div>
          ) : null}

          {activeSection ? (
            <div
              role="tabpanel"
              className="custom-scrollbar max-h-96 overflow-y-auto pr-1"
            >
              {activeSection.id === "questionnaire" && structuredQuestionnaire ? (
                <QuestionnairePreview instrument={structuredQuestionnaire} />
              ) : (
                <Markdown className="text-[13px] leading-relaxed text-text-variant">
                  {activeSection.markdown}
                </Markdown>
              )}
            </div>
          ) : !loading && !failed && taskPath ? (
            <p className="text-[13px] text-text-dim">
              {t("reports.task.noDocuments")}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** The task's default persona sampling strategy (persona_strategy.json).
 *  This run's *actual* cohort lives with the execution facts (byline), since a
 *  run may override the default. Marked data-pdf-ignore so the PDF keeps its own
 *  native section (no duplication). */
function BatchReportPersonaStrategy({ meta }: { meta: BatchReportPdfMeta }) {
  const { t } = useI18n();
  const strategy = meta.personaStrategy;
  const filters = Object.entries(strategy?.dimensionFilters ?? {}).filter(
    ([, values]) => Array.isArray(values) && values.length > 0,
  );
  const stratify = strategy?.fields ?? [];

  const strategyFacts: Array<{ label: string; value: string; title?: string }> = [];
  if (strategy?.mode) {
    strategyFacts.push({
      label: t("reports.strategy.mode"),
      value: humanizeStrategyKey(String(strategy.mode)),
    });
  }
  if (strategy?.allocation) {
    strategyFacts.push({
      label: t("reports.strategy.allocation"),
      value: humanizeAllocationLabel(strategy.allocation, t),
      title: t("reports.strategy.allocationTitle"),
    });
  }
  if (
    (strategy?.allocation === "perCell" || !strategy?.allocation) &&
    strategy?.perCell != null
  ) {
    strategyFacts.push({
      label: t("reports.strategy.perCell"),
      value: String(strategy.perCell),
      title: t("reports.strategy.perCellTitle"),
    });
  } else if (strategy?.sampleSize != null) {
    strategyFacts.push({
      label: t("reports.strategy.sampleSize"),
      value: String(strategy.sampleSize),
      title: t("reports.strategy.sampleSizeTitle"),
    });
  }
  if (stratify.length > 0) {
    strategyFacts.push({
      label: t("reports.strategy.stratify"),
      value: stratify.map(humanizeStrategyKey).join(", "),
    });
  }
  const hasStrategy = strategyFacts.length > 0 || filters.length > 0;

  if (!hasStrategy) return null;

  return <BatchReportPersonaStrategyBody strategyFacts={strategyFacts} filters={filters} />;
}

function BatchReportPersonaStrategyBody({
  strategyFacts,
  filters,
}: {
  strategyFacts: Array<{ label: string; value: string; title?: string }>;
  filters: Array<[string, unknown[]]>;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const summary = [
    strategyFacts.find((fact) => fact.label === t("reports.strategy.mode"))?.value,
    filters.length > 0
      ? t("reports.strategy.audienceFiltersCount", { count: filters.length })
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div data-pdf-ignore className="mt-2.5 rounded-lg border border-outline/25 bg-surface/60 px-3 py-2">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className={`flex w-full items-center justify-between gap-3 text-left ${FOCUS_RING}`}
      >
        <span className="flex min-w-0 items-center gap-2">
          <BatchReportPersonaCardHeader
            icon="tune"
            label={t("reports.strategy.title")}
            tag={t("reports.strategy.tag")}
          />
          {!open && summary ? (
            <span className="truncate text-[12px] normal-case tracking-normal text-text-dim">
              {summary}
            </span>
          ) : null}
        </span>
        <Sym name={open ? "expand_less" : "expand_more"} size={16} className="shrink-0 text-text-dim" />
      </button>
      {open ? (
        <>
          <BatchReportPersonaFactGrid facts={strategyFacts} />
          {filters.length > 0 ? (
            <div className="mt-2.5 space-y-1.5">
              <div className="text-[11px] font-medium uppercase tracking-wide text-text-dim">
                {t("reports.strategy.audienceFilters")}
              </div>
              {filters.map(([dim, values]) => (
                <div key={dim} className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[12px] font-medium text-text-variant">
                    {humanizeStrategyKey(dim)}
                  </span>
                  {(values as string[]).map((value) => (
                    <span
                      key={`${dim}-${value}`}
                      className="inline-flex items-center rounded-full glass-tile px-2 py-0.5 text-[12px] text-text-variant"
                    >
                      {value}
                    </span>
                  ))}
                </div>
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function AggregationDashboard({
  aggregation,
  applicationType,
  pdfMeta,
}: {
  aggregation: HarborJobAggregation;
  applicationType?: string | null;
  pdfMeta: BatchReportPdfMeta;
}) {
  const { t } = useI18n();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [captureMode, setCaptureMode] = useState(false);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const allContexts = useMemo(() => aggregation.contexts ?? [], [aggregation.contexts]);
  const category = useMemo(
    () => inferReportingCategory(allContexts, applicationType),
    [allContexts, applicationType],
  );
  const { headline: headlineContexts, compact: compactContexts } = useMemo(
    () => splitContexts(allContexts, category),
    [allContexts, category],
  );
  const contexts = allContexts;
  const numerical = aggregation.fields.filter((field) => field.kind === "numerical");
  const categorical = aggregation.fields.filter((field) => field.kind === "categorical");
  const textual = aggregation.fields.filter((field) => field.kind === "textual");
  const coverage = aggregation.coverage;
  const reporting = aggregation.reporting ?? null;
  const reportingChip = reportingSummary(reporting, t);
  const hasDetails = contexts.length > 0 || numerical.length > 0 || categorical.length > 0 || textual.length > 0;
  const isSurvey = category === "survey";
  const questionCount = allContexts.filter((context) => context.contextType === "question_response").length;
  const detailCount = isSurvey
    ? questionCount || contexts.length
    : contexts.length > 0
      ? contexts.length
      : numerical.length + categorical.length + textual.length;
  const detailLabel = isSurvey
    ? t("reports.report.questions")
    : contexts.length > 0
      ? t("reports.report.contexts")
      : t("reports.report.fields");
  const trialHint =
    coverage.pendingTrials > 0
      ? t("reports.status.completedOf", {
          done: coverage.completedTrials,
          total: coverage.trialCount,
        })
      : coverage.completedTrials === coverage.trialCount
        ? t("reports.status.allCompleted")
        : t("reports.status.completedCount", { count: coverage.completedTrials });
  const showArtifactsChip =
    coverage.completedWithoutArtifactTrials > 0 || coverage.artifactReadyTrials !== coverage.trialCount;
  const showPendingChip = coverage.pendingTrials > 0;
  const surveyStats = useMemo(
    () => (isSurvey ? buildSurveyCoverageStats(contexts, coverage, t) : []),
    [contexts, coverage, isSurvey, t],
  );
  const surveyTypeCounts = useMemo(
    () => (isSurvey ? buildSurveyQuestionTypeCounts(contexts, t) : []),
    [contexts, isSurvey, t],
  );
  // The "Areas" count is the number of evaluation contexts; those contexts are
  // organized under up to three narrative lenses (outcome / process / feedback).
  // Surface the lenses actually present so the count and the hint line up.
  const areaLenses = useMemo(() => {
    if (isSurvey) return [] as string[];
    const present = new Set<InsightGroup>();
    for (const context of contexts) {
      const group = contextGroup(context.contextType);
      if (group) present.add(group);
    }
    return INSIGHT_GROUP_ORDER.filter((group) => present.has(group)).map((group) =>
      insightGroupLabel(group, t),
    );
  }, [contexts, isSurvey, t]);
  const showReportingBadge =
    reporting != null && (reporting.status ?? "").trim().toLowerCase() !== "not_applicable";

  const downloadPdf = async () => {
    if (downloadBusy) return;
    setDownloadBusy(true);
    setCaptureError(null);
    try {
      flushSync(() => {
        if (hasDetails) setOpen(true);
        setCaptureMode(true);
      });
      await new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      });
      const root = rootRef.current;
      if (root) {
        // Expand collapsed reason / evidence panels so PDF captures full quotes.
        root
          .querySelectorAll<HTMLButtonElement>('button[aria-expanded="false"]')
          .forEach((button) => {
            if (button.closest("[data-pdf-ignore]")) return;
            button.click();
          });
        await new Promise<void>((resolve) => {
          requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
        });
      }
      await new Promise((resolve) => window.setTimeout(resolve, 150));
      const captureRoot = rootRef.current;
      if (!captureRoot) {
        throw new Error(t("reports.report.notReady"));
      }
      const enriched = await enrichBatchReportPdfMeta({
        ...pdfMeta,
        applicationType: pdfMeta.applicationType ?? applicationType ?? null,
        snapshot:
          pdfMeta.snapshot && pdfMeta.snapshot.length > 0
            ? pdfMeta.snapshot
            : buildCoverageSnapshot(aggregation, t),
      });
      await exportBatchReportPdf(captureRoot, enriched, t);
    } catch (err) {
      const message = err instanceof Error ? err.message : t("reports.report.downloadFailed");
      setCaptureError(message);
    } finally {
      setCaptureMode(false);
      setDownloadBusy(false);
    }
  };

  return (
    <div ref={rootRef} className="mb-4 space-y-3" data-batch-report-root>
      <StudioGlassPanel className="bg-surface/95 px-4 py-2.5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[14px] font-medium text-text-main">
            <span className="flex items-center gap-2">
              <Sym name="analytics" size={16} className="shrink-0 text-primary" />
              {t("reports.report.title")}
            </span>
            {formatTimestamp(pdfMeta.generatedAt, true) ? (
              <span
                className="text-[12px] font-normal text-text-dim"
                title={pdfMeta.generatedAt ?? undefined}
              >
                · {t("reports.report.reportAt", {
                  date: formatTimestamp(pdfMeta.generatedAt, true) ?? "",
                })}
              </span>
            ) : null}
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              data-pdf-ignore
              onClick={() => {
                void downloadPdf();
              }}
              disabled={downloadBusy}
              className={`glass-tile glass-tile--hover inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[12px] font-medium text-text-variant transition hover:text-text-main disabled:opacity-55 ${FOCUS_RING}`}
            >
              <Sym name="download" size={14} />
              {downloadBusy ? t("reports.report.preparing") : t("reports.report.download")}
            </button>
            {showReportingBadge ? (
              <span
                className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-mono text-[12px] uppercase tracking-wide ${reportingStatusClassName(
                  reporting.status,
                )}`}
              >
                <Sym
                  name={reporting.status === "queued" || reporting.status === "running" ? "autorenew" : "analytics"}
                  size={12}
                  className={reporting.status === "queued" || reporting.status === "running" ? "animate-rb-spin" : ""}
                />
                {t("reports.report.detailedAnalysis")} · {reportingStatusLabel(reporting.status, t)}
              </span>
            ) : null}
          </div>
        </div>

        <BatchReportTaskBrief meta={pdfMeta} />

        <BatchReportPersonaStrategy meta={pdfMeta} />

        <BatchReportMetaByline meta={pdfMeta} />

        {captureError ? (
          <p className="mt-2 text-[13px] text-danger" data-pdf-ignore>
            {captureError}
          </p>
        ) : null}

        <div className="mt-2.5 flex flex-wrap gap-2">
          <CoverageTile
            label={isSurvey ? t("reports.report.personas") : t("reports.report.trials")}
            value={coverage.trialCount}
            hint={trialHint}
          />
          <CoverageTile
            label={isSurvey ? t("reports.report.questions") : t("reports.report.areas")}
            value={isSurvey ? questionCount || contexts.length : contexts.length}
            hint={
              isSurvey
                ? t("reports.report.inSurvey")
                : contexts.length > 0
                  ? areaLenses.length > 0
                    ? t("reports.report.across", { areas: areaLenses.join(" · ") })
                    : t("reports.report.evaluationAreas")
                  : t("reports.report.individualAnswers")
            }
          />
          {isSurvey && surveyTypeCounts.length > 0 ? (
            <SurveyQuestionTypesTile counts={surveyTypeCounts} />
          ) : null}
          {isSurvey
            ? surveyStats.map((stat) => (
                <CoverageTile key={`${stat.label}-${stat.value}`} label={stat.label} value={stat.value} hint={stat.hint} />
              ))
            : null}
          {showArtifactsChip ? (
            <CoverageTile
              label={t("reports.report.artifacts")}
              value={coverage.artifactReadyTrials}
              hint={
                coverage.completedWithoutArtifactTrials > 0
                  ? t("reports.report.missing", { count: coverage.completedWithoutArtifactTrials })
                  : t("reports.report.ready")
              }
            />
          ) : null}
          {showPendingChip ? (
            <CoverageTile
              label={t("reports.report.pending")}
              value={coverage.pendingTrials}
              hint={t("reports.report.stillRunning")}
            />
          ) : null}
          {!isSurvey && reportingChip ? (
            <CoverageTile
              label={t("reports.report.detailedAnalysis")}
              value={reportingChip.value}
              hint={reportingChip.hint}
            />
          ) : null}
        </div>
        {reporting?.error ? (
          <p className="mt-3 text-[14px] leading-relaxed text-danger">{reporting.error}</p>
        ) : null}
        {!isSurvey && contexts.length > 0 ? (
          <BasicEvaluationPanel aggregation={aggregation} category={category} />
        ) : null}
        {hasDetails ? (
          <div
            data-pdf-ignore
            className={`space-y-2 ${contexts.length > 0 ? "mt-2.5 border-t border-outline/35 pt-2.5" : "mt-2.5"}`}
          >
            <button
              type="button"
              onClick={() => setOpen((value) => !value)}
              aria-expanded={open}
              className={`flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-[15px] font-semibold text-white shadow-sm transition-colors hover:bg-primary/90 ${FOCUS_RING}`}
            >
              <Sym name={open ? "expand_less" : "expand_more"} size={20} className="shrink-0" />
              {open ? t("reports.report.hideDetailed") : t("reports.report.showDetailed")}
              {isSurvey && !open ? (
                <span className="ml-1 text-[13px] font-normal text-white/80">
                  {t("reports.report.detailCount", { count: detailCount, label: detailLabel })}
                </span>
              ) : null}
            </button>
          </div>
        ) : null}
      </StudioGlassPanel>

      {open ? (
        contexts.length > 0 ? (
          <DetailedEvaluationPanel
            aggregation={aggregation}
            category={category}
            compactContexts={compactContexts}
            captureMode={captureMode}
            surveyHeadlineContexts={isSurvey ? headlineContexts : undefined}
          />
        ) : (
          <FlatAggregationFallback
            numerical={numerical}
            categorical={categorical}
            textual={textual}
          />
        )
      ) : null}
    </div>
  );
}

function scoreFacetsForContext(context: AggregationContext): AggregationField[] {
  return context.facets.filter(
    (facet) =>
      facet.role === "score" ||
      /confidence|score|rating/i.test(facet.key) ||
      /confidence|score|rating/i.test(facet.label),
  )
}

function resolveSurveyQuestionType(
  context: AggregationContext,
  primary: AggregationField | null,
): "likert" | "single_choice" | "multi_choice" | "free_text" | "unknown" {
  const raw = String(context.questionType ?? "").trim().toLowerCase()
  if (raw === "likert" || raw === "single_choice" || raw === "multi_choice" || raw === "free_text") {
    return raw
  }
  // Legacy artifacts without questionType — infer from facet kind.
  if (primary?.kind === "numerical") return "likert"
  if (primary?.kind === "categorical") return "single_choice"
  if (primary?.kind === "textual") return "free_text"
  return "unknown"
}

function surveyAnswerItems(
  context: AggregationContext,
  primary: AggregationField | null,
  t?: ReportTranslate,
): Array<CountBarItem & { id?: string }> {
  if (!primary || primary.kind !== "categorical") return []
  const counts = primary.categorical?.counts ?? []
  const byId = new Map(counts.map((entry) => [entry.value, entry.count]))
  const options = context.choiceOptions ?? []
  if (options.length > 0) {
    const known = new Set(options.map((option) => option.id))
    const rows = options.map((option) => ({
      id: option.id,
      label: option.label?.trim() || formatBucketLabel(option.id, t),
      count: byId.get(option.id) ?? 0,
    }))
    // Keep unexpected values that aren't in the questionnaire inventory.
    for (const entry of counts) {
      if (!known.has(entry.value)) {
        rows.push({
          id: entry.value,
          label: formatBucketLabel(entry.value, t),
          count: entry.count,
        })
      }
    }
    return rows
  }
  return counts.map((entry) => ({
    id: entry.value,
    label: formatBucketLabel(entry.value, t),
    count: entry.count,
  }))
}

function ChoiceCompositionChart({
  items,
  respondentCount,
  multi = false,
}: {
  items: Array<CountBarItem & { id?: string }>
  respondentCount: number
  multi?: boolean
}) {
  const { t } = useI18n()
  const ranked = [...items].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
  const denom = Math.max(respondentCount, 1)
  const peak = Math.max(...ranked.map((item) => item.count), 1)
  const leader = ranked.find((item) => item.count > 0) ?? ranked[0]
  const leaderShare = leader ? Math.round((leader.count / denom) * 100) : 0
  const chosen = ranked.filter((item) => item.count > 0).length
  const consensus =
    chosen <= 1 && (leader?.count ?? 0) > 0
      ? t("reports.report.unanimous")
      : leaderShare >= 60
        ? t("reports.report.clearLeader")
        : t("reports.report.splitOpinions")

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0 text-[14px] text-text-main">
          {leader && leader.count > 0 ? (
            <>
              {t("reports.report.topPick")} <span className="font-medium">{leader.label}</span>
              <span className="font-mono text-text-dim">
                {" "}
                · {leader.count}/{denom} · {leaderShare}%
              </span>
            </>
          ) : (
            t("reports.report.noChoices")
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {multi ? (
            <span className="text-[12px] text-text-dim">{t("reports.report.multiSelect")}</span>
          ) : null}
          <span className="rounded-md glass-tile px-2 py-1 text-[13px] text-text-variant">
            {consensus}
          </span>
        </div>
      </div>

      <div className="rounded-lg glass-tile px-3 py-3">
        <div className="space-y-2.5">
          {ranked.map((item, index) => {
            const share = Math.round((item.count / denom) * 100)
            const widthPct = item.count > 0 ? Math.max(6, Math.round((item.count / peak) * 100)) : 0
            const tone =
              item.count <= 0
                ? "bg-outline/25"
                : index === 0
                  ? "bg-secondary/80"
                  : index === 1
                    ? "bg-primary/65"
                    : index === 2
                      ? "bg-warn/55"
                      : "bg-primary/40"
            return (
              <div key={`${item.id ?? item.label}-${item.count}`} className="space-y-1">
                <div className="flex items-start justify-between gap-3 text-[14px]">
                  <span className={`min-w-0 leading-snug ${item.count > 0 ? "text-text-main" : "text-text-dim"}`}>
                    {item.label}
                  </span>
                  <span className="shrink-0 font-mono text-text-dim">
                    {item.count}
                    {item.count > 0 ? <span className="text-text-variant"> · {share}%</span> : null}
                  </span>
                </div>
                <div className="h-2.5 rounded-full bg-surface-high/90">
                  <div
                    className={`h-2.5 rounded-full ${tone}`}
                    style={{ width: `${widthPct}%` }}
                    title={`${item.label}: ${item.count}`}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

type FreeTextTheme = { label: string; count: number; samples: string[] }

/** Long "themes" that are just the full quote — treat as evidence, not a topic tag. */
function isQuoteLikeTheme(theme: FreeTextTheme): boolean {
  const label = theme.label.trim()
  if (label.length >= 120) return true
  const sample = theme.samples[0]?.trim() ?? ""
  return sample.length > 0 && (label === sample || sample.startsWith(label.slice(0, 40)))
}

function freeTextThemes(primary: AggregationField | null): FreeTextTheme[] {
  const counts = primary?.textual?.counts ?? []
  // Trust backend TF-IDF clustering — do not re-cluster with client heuristics.
  if (counts.length === 0) return []
  return counts
    .filter((entry) => entry.value.trim().length > 0 && entry.count > 0)
    .slice(0, 8)
    .map((entry) => {
      const label = entry.value.trim()
      const samples = (entry.samples ?? [label]).map((sample) => sample.trim()).filter(Boolean)
      return {
        label,
        count: entry.count,
        samples: samples.length > 0 ? samples.slice(0, 3) : [label],
      }
    })
}

function freeTextSignalTags(judges: AggregationJudge[]): FreeTextTheme[] {
  const totals = new Map<string, { label: string; count: number; samples: string[] }>()
  for (const judge of judges) {
    const defs = new Map((judge.signals ?? []).map((signal) => [signal.key, signal.label || signal.key]))
    for (const bucket of judge.buckets ?? []) {
      for (const signal of bucket.signals ?? []) {
        if (!signal.present) continue
        const label = defs.get(signal.key) ?? signal.key
        const current = totals.get(signal.key)
        const quoteSamples = (bucket.samples ?? []).map((sample) => sample.trim()).filter(Boolean)
        if (current) {
          current.count += bucket.count || 1
          for (const sample of quoteSamples) {
            if (!current.samples.includes(sample)) current.samples.push(sample)
          }
        } else {
          totals.set(signal.key, {
            label,
            count: bucket.count || 1,
            samples: quoteSamples.slice(0, 3),
          })
        }
      }
    }
  }
  return [...totals.values()]
    .map((theme) => ({
      ...theme,
      samples: theme.samples.length > 0 ? theme.samples.slice(0, 3) : [theme.label],
    }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
}

function freeTextThemeSummary(
  present: number,
  themes: FreeTextTheme[],
  uniqueHint: number,
  t: ReportTranslate,
): string | null {
  if (present <= 0) return null
  const topicThemes = themes.filter((theme) => !isQuoteLikeTheme(theme))
  if (topicThemes.length === 0) {
    return uniqueHint > 0
      ? t("reports.theme.writtenWithTopics", { present, unique: uniqueHint })
      : t("reports.theme.writtenOnly", { present })
  }
  if (topicThemes.length === 1) {
    return t("reports.theme.allConverge", { present, label: topicThemes[0].label })
  }

  const primary = topicThemes[0]
  const secondary = topicThemes[1]
  const smaller = topicThemes.slice(2)
  const smallerAnswers = smaller.reduce((sum, theme) => sum + theme.count, 0)

  if (primary.count + secondary.count >= Math.max(2, Math.round(present * 0.65))) {
    if (smallerAnswers > 0) {
      return t("reports.theme.dominantTwoWithSmaller", {
        present,
        primary: primary.label,
        primaryCount: primary.count,
        secondary: secondary.label,
        secondaryCount: secondary.count,
        smallerAnswers,
        smallerTopics: smaller.length,
      })
    }
    return t("reports.theme.dominantTwo", {
      present,
      primary: primary.label,
      primaryCount: primary.count,
      secondary: secondary.label,
      secondaryCount: secondary.count,
    })
  }

  let summary = t("reports.theme.manyTopics", {
    present,
    topicCount: topicThemes.length,
    primary: primary.label,
    primaryCount: primary.count,
    secondary: secondary.label,
    secondaryCount: secondary.count,
  })
  if (smallerAnswers > 0) {
    summary += t("reports.theme.manyTopicsRemaining", {
      smallerAnswers,
      smallerTopics: smaller.length,
    })
  }
  return summary
}

function freeTextCoverage(primary: AggregationField | null, t: ReportTranslate): {
  present: number
  unique: number
  summary: string | null
  themes: FreeTextTheme[]
} {
  const present = primary?.presentCount ?? 0
  const themes = freeTextThemes(primary)
  const unique = themes.length || primary?.textual?.uniqueCount || 0
  const rawSummary = primary?.textual?.summary?.trim() || null
  // Prefer LLM/reporting summaries; otherwise roll up from clustered themes.
  const summary =
    rawSummary && !isHeuristicAggregationSummary(rawSummary)
      ? rawSummary
      : freeTextThemeSummary(present, themes, unique, t)
  return { present, unique, summary, themes }
}

function FreeTextThemeTags({ themes, label }: { themes: FreeTextTheme[]; label: string }) {
  if (themes.length === 0) return null
  return (
    <div className="space-y-1.5">
      <div className="text-[12px] font-medium uppercase tracking-wide text-text-dim">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {themes.map((theme) => (
          <span
            key={`${theme.label}-${theme.count}`}
            className="inline-flex max-w-full items-start gap-1.5 rounded-lg glass-tile px-2.5 py-1.5 text-[13px] leading-snug text-text-main"
          >
            <span className="min-w-0 whitespace-normal break-words">{theme.label}</span>
            <span className="shrink-0 font-mono text-text-dim">{theme.count}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

/**
 * Fallback for free-text questions whose only clusters are "quote-like" (the
 * theme label is the answer text itself). Renders the actual written answers so
 * the question shows real content instead of just a count summary.
 */
function FreeTextAnswerList({ themes }: { themes: FreeTextTheme[] }) {
  const { t } = useI18n()
  if (themes.length === 0) return null
  return (
    <div className="space-y-1.5">
      <div className="text-[12px] font-medium uppercase tracking-wide text-text-dim">
        {t("reports.report.writtenAnswers")}
      </div>
      <div className="space-y-1.5">
        {themes.map((theme) => (
          <div
            key={`${theme.label}-${theme.count}`}
            className="flex items-start justify-between gap-3 rounded-md glass-tile px-3 py-2"
          >
            <div className="min-w-0 whitespace-normal break-words text-[14px] leading-relaxed text-text-variant">
              {theme.label}
            </div>
            {theme.count > 1 ? (
              <span className="shrink-0 font-mono text-[13px] text-text-dim">×{theme.count}</span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}

function FreeTextThemeExamples({ themes }: { themes: FreeTextTheme[] }) {
  if (themes.length === 0) return null
  return (
    <div className="space-y-3">
      {themes.map((theme) => (
        <div key={`${theme.label}-${theme.count}`} className="space-y-1.5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 text-[14px] font-medium leading-snug text-text-main">{theme.label}</div>
            <span className="shrink-0 font-mono text-[13px] text-text-dim">{theme.count}</span>
          </div>
          <div className="space-y-1.5">
            {theme.samples.slice(0, 2).map((sample) => (
              <div
                key={`${theme.label}-${sample.slice(0, 40)}`}
                className="rounded-md glass-tile px-3 py-2 text-[14px] leading-relaxed text-text-variant"
              >
                {sample}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function likertScaleBounds(
  context: AggregationContext,
  primary: AggregationField,
): { min: number; max: number } {
  const fromContextMin = Number(context.scaleMin)
  const fromContextMax = Number(context.scaleMax)
  if (Number.isFinite(fromContextMin) && Number.isFinite(fromContextMax) && fromContextMax > fromContextMin) {
    return { min: fromContextMin, max: fromContextMax }
  }
  const observedMin = primary.numerical?.min
  const observedMax = primary.numerical?.max
  // Unanimous high scores still need the questionnaire scale (typically 1–5).
  if (
    observedMin != null &&
    observedMax != null &&
    observedMin === observedMax &&
    observedMax >= 1 &&
    observedMax <= 5
  ) {
    return { min: 1, max: 5 }
  }
  if (observedMin != null && observedMax != null && observedMax > observedMin) {
    return { min: Math.min(1, observedMin), max: observedMax <= 5 ? 5 : observedMax <= 10 ? 10 : observedMax }
  }
  const inferred = inferRatingScale(primary)
  return { min: 1, max: inferred ?? 5 }
}

function likertScalePoints(
  context: AggregationContext,
  primary: AggregationField,
  scale: { min: number; max: number },
  t?: ReportTranslate,
): Array<{ value: number; label: string; count: number }> {
  const counts = primary.numerical?.counts ?? []
  const byValue = new Map(counts.map((entry) => [String(entry.value), entry.count]))
  const points: Array<{ value: number; label: string; count: number }> = []
  for (let value = scale.min; value <= scale.max; value += 1) {
    const labelText = t ? likertPointLabel(value, context.scaleLabels, scale, t) : null
    points.push({
      value,
      label: labelText ? `${value} · ${labelText}` : String(value),
      count: byValue.get(String(value)) ?? 0,
    })
  }
  return points
}

function likertSegmentClass(index: number, total: number): string {
  if (total <= 1) return "bg-secondary/75"
  const t = index / Math.max(total - 1, 1)
  if (t <= 0.2) return "bg-danger/55"
  if (t <= 0.4) return "bg-warn/55"
  if (t <= 0.6) return "bg-outline/70"
  if (t <= 0.8) return "bg-secondary/55"
  return "bg-secondary/85"
}

function LikertSpectrumChart({
  points,
  total,
  avg,
  scale,
}: {
  points: Array<{ value: number; label: string; count: number }>
  total: number
  avg: number | null | undefined
  scale: { min: number; max: number }
}) {
  const { t } = useI18n()
  const safeTotal = Math.max(total, 1)
  const peak = Math.max(...points.map((point) => point.count), 1)
  const span = Math.max(scale.max - scale.min, 1)
  const avgPct =
    avg != null && Number.isFinite(avg) ? ((avg - scale.min) / span) * 100 : null

  return (
    <div className="space-y-3">
      <div className="relative rounded-lg glass-tile px-3 pb-2 pt-4">
        {avgPct != null ? (
          <div
            className="pointer-events-none absolute bottom-8 top-3 z-10 w-px -translate-x-1/2 bg-text-main/70"
            style={{ left: `calc(12px + (100% - 24px) * ${Math.max(0, Math.min(100, avgPct)) / 100})` }}
          >
            <span className="absolute -top-1 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-text-main px-1.5 py-0.5 font-mono text-[12px] text-surface">
              {t("reports.report.avg")} {metricValue(avg)}
            </span>
          </div>
        ) : null}
        <div className="flex h-24 items-end gap-1.5">
          {points.map((point, index) => {
            const heightPct = point.count > 0 ? Math.max(10, Math.round((point.count / peak) * 100)) : 3
            return (
              <div key={point.value} className="flex min-w-0 flex-1 flex-col items-center gap-1">
                <div className="flex h-16 w-full items-end">
                  <div
                    className={`w-full rounded-t-md ${point.count > 0 ? likertSegmentClass(index, points.length) : "bg-outline/25"}`}
                    style={{ height: `${heightPct}%` }}
                    title={`${point.label}: ${point.count}`}
                  />
                </div>
                <div className="font-mono text-[12px] text-text-dim">{point.value}</div>
              </div>
            )
          })}
        </div>
      </div>
      <div className="grid gap-1.5">
        {points.map((point, index) => {
          const share = Math.round((point.count / safeTotal) * 100)
          return (
            <div key={point.value} className="flex items-center gap-2 text-[13px]">
              <span className={`h-2.5 w-2.5 shrink-0 rounded-sm ${likertSegmentClass(index, points.length)}`} />
              <span className={`min-w-0 flex-1 ${point.count > 0 ? "text-text-main" : "text-text-dim"}`}>
                {point.label}
              </span>
              <span className="shrink-0 font-mono text-text-dim">
                {point.count}
                {point.count > 0 ? ` · ${share}%` : ""}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function LikertQuestionBody({
  context,
  primary,
}: {
  context: AggregationContext
  primary: AggregationField
}) {
  const { t } = useI18n()
  const scale = likertScaleBounds(context, primary)
  const avg = primary.numerical?.avg
  const avgLabel = avg != null ? likertPointLabel(Math.round(avg), context.scaleLabels, scale, t) : null
  const points = likertScalePoints(context, primary, scale, t)
  const total = Math.max(
    primary.presentCount ?? 0,
    points.reduce((sum, point) => sum + point.count, 0),
    1,
  )
  const lowLabel = likertPointLabel(scale.min, context.scaleLabels, scale, t)
  const highLabel = likertPointLabel(scale.max, context.scaleLabels, scale, t)
  const filled = points.filter((point) => point.count > 0).length
  const consensus =
    filled <= 1 && total > 0
      ? t("reports.report.unanimous")
      : avg != null && avg >= scale.max - 0.35
        ? t("reports.report.stronglyFavorable")
        : avg != null && avg <= scale.min + 0.35
          ? t("reports.report.stronglyUnfavorable")
          : t("reports.report.mixed")

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
          <div>
            <div className="text-[12px] uppercase tracking-wide text-text-dim">
              {t("reports.report.average")}
            </div>
            <div className="flex items-baseline gap-1.5">
              <span className="font-mono text-[22px] text-text-main">{metricValue(avg)}</span>
              <span className="font-mono text-[15px] text-text-dim">/{scale.max}</span>
            </div>
          </div>
          {avgLabel ? <div className="pb-1 text-[15px] text-text-main">{avgLabel}</div> : null}
        </div>
        <div className="rounded-md glass-tile px-2 py-1 text-[13px] text-text-variant">
          {consensus}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-text-dim">
        <span>
          {scale.min}
          {lowLabel ? ` · ${lowLabel}` : ""}
        </span>
        <span aria-hidden="true">→</span>
        <span>
          {scale.max}
          {highLabel ? ` · ${highLabel}` : ""}
        </span>
      </div>
      <LikertSpectrumChart points={points} total={total} avg={avg} scale={scale} />
    </div>
  )
}

function SurveyQuestionCard({ context }: { context: AggregationContext }) {
  const { t } = useI18n()
  const [reasonsOpen, setReasonsOpen] = useState(false)
  const [quotesOpen, setQuotesOpen] = useState(false)
  const [scoresOpen, setScoresOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const reasonsPanelId = useId()
  const quotesPanelId = useId()
  const scoresPanelId = useId()
  const morePanelId = useId()
  const primaryFacet = primaryFacetForContext(context)
  const questionType = resolveSurveyQuestionType(context, primaryFacet)
  const isFreeText = questionType === "free_text"
  const isLikert = questionType === "likert" || primaryFacet?.kind === "numerical"
  const explanationFacet = surveyReasonFacetForContext(context)
  const scoreFacets = scoreFacetsForContext(context).filter(
    (facet) => facet.key !== primaryFacet?.key && facet.key !== explanationFacet?.key,
  )
  const claimedKeys = new Set(
    [primaryFacet?.key, explanationFacet?.key, ...scoreFacets.map((facet) => facet.key)].filter(Boolean),
  )
  const leftoverFacets = orderedFacets(context.facets).filter((facet) => !claimedKeys.has(facet.key))
  const answerItems = surveyAnswerItems(context, primaryFacet, t)
  const answerTotal = Math.max(
    primaryFacet?.presentCount ?? 0,
    answerItems.reduce((sum, item) => sum + item.count, 0),
    1,
  )
  const judges = context.judges ?? []
  const freeText = isFreeText ? freeTextCoverage(primaryFacet, t) : null
  const freeTextSignalThemes = isFreeText ? freeTextSignalTags(judges) : []
  const freeTextDisplayThemes = (
    freeTextSignalThemes.length > 0 ? freeTextSignalThemes : (freeText?.themes ?? [])
  ).filter((theme) => !isQuoteLikeTheme(theme))
  // When every clustered theme is "quote-like" (its label is the answer text
  // itself), the topic-tag / examples views suppress it entirely. Surface the
  // raw written answers instead so the question is never left content-less.
  const freeTextQuoteThemes = (freeText?.themes ?? []).filter((theme) => isQuoteLikeTheme(theme))
  const freeTextRawAnswers =
    freeTextDisplayThemes.length === 0 ? freeTextQuoteThemes : []

  const reasonSamples = (explanationFacet?.textual?.samples ?? []).filter((sample) => sample.trim().length > 0)
  const reasonSummary =
    explanationFacet?.textual?.summary && !isHeuristicAggregationSummary(explanationFacet.textual.summary)
      ? explanationFacet.textual.summary
      : null
  const hasReasons = reasonSamples.length > 0 || Boolean(reasonSummary)
  const reasonTitle = humanizeFacetLabel(
    explanationFacet?.label ?? t("reports.report.reasons"),
    explanationFacet?.key ?? "explanation",
    t,
  )
  const quoteCount = reasonSamples.length
  const summaries = context.summaries ?? []
  const crossFacetViews = crossFacetViewsForContext(context)
  const hasGroupedAnalysis = summaries.length > 0 || judges.length > 0 || crossFacetViews.length > 0
  const scoreNeedsDetail = scoreFacets.some(
    (facet) =>
      (facet.kind === "numerical" &&
        facet.numerical?.min != null &&
        facet.numerical?.max != null &&
        facet.numerical.min !== facet.numerical.max) ||
      (facet.kind === "categorical" && (facet.categorical?.counts?.length ?? 0) > 1) ||
      (facet.kind === "textual" && (facet.textual?.samples?.length ?? 0) > 0),
  )
  const typeChip =
    questionType === "likert"
      ? t("reports.report.likert")
      : questionType === "single_choice"
        ? t("reports.report.singleChoice")
        : questionType === "multi_choice"
          ? t("reports.report.multiChoice")
          : questionType === "free_text"
            ? t("reports.report.freeText")
            : null

  return (
    <section className="overflow-hidden rounded-xl glass-panel">
      <div className="px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <FieldTitle field={context.label} />
            {typeChip ? <InlineBadge>{typeChip}</InlineBadge> : null}
            {primaryFacet?.presentCount != null ? (
              <span className="font-mono text-[13px] text-text-dim">
                {t("reports.report.answeredCount", { count: primaryFacet.presentCount })}
                {primaryFacet.missingCount > 0
                  ? ` · ${t("reports.report.missingCount", { count: primaryFacet.missingCount })}`
                  : ""}
              </span>
            ) : null}
          </div>
        </div>

        <div className="mt-3">
          {isFreeText && freeText ? (
            <div className="space-y-3">
              {(() => {
                const reportingSummary =
                  summaries.find((item) => item.overall?.summary)?.overall?.summary ??
                  judges.find((item) => item.overallAssessment)?.overallAssessment ??
                  null
                return (
                  <>
                    <p className="text-[15px] leading-relaxed text-text-main">
                      {reportingSummary || freeText.summary || t("reports.report.noWrittenAnswers")}
                    </p>
                    <FreeTextThemeTags
                      themes={freeTextDisplayThemes}
                      label={
                        freeTextSignalThemes.length > 0
                          ? t("reports.feedback.themes")
                          : t("reports.feedback.mainTopics")
                      }
                    />
                    {freeTextRawAnswers.length > 0 ? (
                      <FreeTextAnswerList themes={freeTextRawAnswers} />
                    ) : null}
                  </>
                )
              })()}
            </div>
          ) : isLikert && primaryFacet?.kind === "numerical" ? (
            <LikertQuestionBody context={context} primary={primaryFacet} />
          ) : answerItems.length > 0 ? (
            <ChoiceCompositionChart
              items={answerItems}
              respondentCount={primaryFacet?.presentCount ?? answerTotal}
              multi={questionType === "multi_choice"}
            />
          ) : (
            <p className="text-[14px] text-text-variant">{t("reports.report.noResponseMix")}</p>
          )}
        </div>

        {scoreFacets.length > 0 && !scoreNeedsDetail ? (
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[14px] text-text-main">
            {scoreFacets.map((facet) => (
              <span key={facet.key} className="inline-flex items-baseline gap-1.5">
                <span className="text-text-dim">{facet.label}</span>
                <span className="font-mono">
                  {facet.kind === "numerical"
                    ? formatNumericalSummary(facet)
                    : facet.kind === "categorical"
                      ? formatCategoricalDistribution(facet, t)
                      : previewText(facet.textual?.summary ?? facet.textual?.samples?.[0] ?? "—", 48)}
                </span>
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {isFreeText && freeTextDisplayThemes.length > 0 ? (
        <div className="border-t border-outline/40">
          <button
            type="button"
            onClick={() => setQuotesOpen((value) => !value)}
            aria-expanded={quotesOpen}
            aria-controls={quotesPanelId}
            className={`flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-2.5 text-left transition-colors duration-200 hover:bg-surface/40 ${FOCUS_RING}`}
          >
            <div className="min-w-0">
              <div className="text-[14px] font-medium text-text-main">
                {t("reports.feedback.examplesByTopic")}
              </div>
              <div className="mt-0.5 text-[13px] text-text-dim">
                {t("reports.feedback.topicQuotes", { count: freeTextDisplayThemes.length })}
              </div>
            </div>
            <Sym name={quotesOpen ? "expand_less" : "expand_more"} size={18} className="shrink-0 text-text-dim" />
          </button>
          {quotesOpen ? (
            <div id={quotesPanelId} className="border-t border-outline/35 bg-surface/20 px-4 py-3">
              <FreeTextThemeExamples themes={freeTextDisplayThemes} />
            </div>
          ) : null}
        </div>
      ) : null}

      {scoreFacets.length > 0 && scoreNeedsDetail ? (
        <div className="border-t border-outline/40">
          <button
            type="button"
            onClick={() => setScoresOpen((value) => !value)}
            aria-expanded={scoresOpen}
            aria-controls={scoresPanelId}
            className={`flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-2.5 text-left transition-colors duration-200 hover:bg-surface/40 ${FOCUS_RING}`}
          >
            <div className="min-w-0">
              <div className="text-[14px] font-medium text-text-main">
                {scoreFacets.length === 1 ? scoreFacets[0].label : t("reports.report.scores")}
              </div>
              <div className="mt-0.5 text-[13px] text-text-dim">
                {scoreFacets
                  .map((facet) =>
                    facet.kind === "numerical"
                      ? `${facet.label} ${formatNumericalSummary(facet)}`
                      : facet.label,
                  )
                  .join(" · ")}
              </div>
            </div>
            <Sym name={scoresOpen ? "expand_less" : "expand_more"} size={18} className="shrink-0 text-text-dim" />
          </button>
          {scoresOpen ? (
            <div id={scoresPanelId} className="space-y-3 border-t border-outline/35 bg-surface/20 px-4 py-3">
              {scoreFacets.map((facet) => (
                <div key={facet.key} className="space-y-2">
                  {scoreFacets.length > 1 ? (
                    <div className="text-[14px] font-medium text-text-main">{facet.label}</div>
                  ) : null}
                  <FacetVisual field={facet} />
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {hasReasons ||
      (!isFreeText && hasGroupedAnalysis) ||
      (isFreeText && crossFacetViews.length > 0) ||
      leftoverFacets.length > 0 ? (
        <div className="border-t border-outline/40">
          {hasReasons ? (
            <>
              <button
                type="button"
                onClick={() => setReasonsOpen((value) => !value)}
                aria-expanded={reasonsOpen}
                aria-controls={reasonsPanelId}
                className={`flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-2.5 text-left transition-colors duration-200 hover:bg-surface/40 ${FOCUS_RING}`}
              >
                <div className="min-w-0">
                  <div className="text-[14px] font-medium text-text-main">{reasonTitle}</div>
                  <div className="mt-0.5 text-[13px] text-text-dim">
                    {quoteCount > 0
                      ? t("reports.feedback.personaQuotes", { count: quoteCount })
                      : t("reports.feedback.personaExplanations")}
                  </div>
                </div>
                <Sym
                  name={reasonsOpen ? "expand_less" : "expand_more"}
                  size={18}
                  className="shrink-0 text-text-dim"
                />
              </button>
              {reasonsOpen ? (
                <div id={reasonsPanelId} className="space-y-3 border-t border-outline/35 bg-surface/20 px-4 py-3">
                  {reasonSummary ? (
                    <p className="text-[14px] leading-relaxed text-text-main">{reasonSummary}</p>
                  ) : null}
                  {reasonSamples.length > 0 ? (
                    <SampleList samples={reasonSamples} defaultExpanded />
                  ) : null}
                </div>
              ) : null}
            </>
          ) : null}

          {hasGroupedAnalysis && !isFreeText ? (
            <div
              className={`space-y-2 px-4 py-3 ${
                hasReasons || (scoreFacets.length > 0 && scoreNeedsDetail)
                  ? "border-t border-outline/35"
                  : ""
              }`}
            >
              <div className="text-[13px] font-medium uppercase tracking-wide text-text-dim">
                {t("reports.analysis.groupedAnalysis")}
              </div>
              {summaries.map((summary) => (
                <SummaryDisclosure key={summary.id} summary={summary} />
              ))}
              {judges.map((judge) => (
                <JudgeDisclosure key={judge.id} judge={judge} />
              ))}
              {crossFacetViews.map((crossFacetView, index) => (
                <CrossFacetViewDisclosure
                  key={`${context.key}-${crossFacetView.type}-${index}`}
                  crossFacetView={crossFacetView}
                />
              ))}
            </div>
          ) : null}
          {isFreeText && crossFacetViews.length > 0 ? (
            <div
              className={`space-y-2 px-4 py-3 ${
                hasReasons || (scoreFacets.length > 0 && scoreNeedsDetail) ? "border-t border-outline/35" : ""
              }`}
            >
              {crossFacetViews.map((crossFacetView, index) => (
                <CrossFacetViewDisclosure
                  key={`${context.key}-${crossFacetView.type}-${index}`}
                  crossFacetView={crossFacetView}
                />
              ))}
            </div>
          ) : null}

          {leftoverFacets.length > 0 ? (
            <div className={hasReasons || (!isFreeText && hasGroupedAnalysis) || (isFreeText && crossFacetViews.length > 0) ? "border-t border-outline/35" : ""}>
              <button
                type="button"
                onClick={() => setMoreOpen((value) => !value)}
                aria-expanded={moreOpen}
                aria-controls={morePanelId}
                className={`flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-2.5 text-left transition-colors duration-200 hover:bg-surface/40 ${FOCUS_RING}`}
              >
                <div className="min-w-0">
                  <div className="text-[14px] font-medium text-text-main">
                    {t("reports.analysis.moreSignals")}
                  </div>
                  <div className="mt-0.5 text-[13px] text-text-dim">
                    {t("reports.analysis.additionalFields", { count: leftoverFacets.length })}
                  </div>
                </div>
                <Sym name={moreOpen ? "expand_less" : "expand_more"} size={18} className="shrink-0 text-text-dim" />
              </button>
              {moreOpen ? (
                <div id={morePanelId} className="space-y-3 border-t border-outline/35 bg-surface/20 px-4 py-3">
                  {leftoverFacets.map((facet) => (
                    <FacetCard key={facet.key} field={facet} />
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}


function feedbackFacetKey(field: AggregationField): string {
  return String(field.facetKey ?? field.key.split(".").pop() ?? field.key).trim().toLowerCase()
}

function defaultFeedbackCategories(field: AggregationField): string[] {
  const key = feedbackFacetKey(field)
  if (
    key.includes("need_constraint") ||
    key.includes("personal_preference") ||
    key.includes("clarity_of_next")
  ) {
    return ["yes", "partially", "no"]
  }
  const observed = (field.categorical?.counts ?? []).map((entry) => entry.value.toLowerCase())
  if (
    observed.every((value) => value === "true" || value === "false") ||
    key.includes("felt_understood") ||
    key.includes("clarification")
  ) {
    return ["true", "false"]
  }
  return field.categories?.map((item) => String(item)) ?? []
}

function feedbackChoiceItems(field: AggregationField, t?: ReportTranslate): Array<CountBarItem & { id?: string }> {
  if (field.kind !== "categorical") return []
  const counts = field.categorical?.counts ?? []
  const byId = new Map(counts.map((entry) => [entry.value, entry.count]))
  const inventory = (field.categories?.length ? field.categories : defaultFeedbackCategories(field)).map(String)
  if (inventory.length === 0) {
    return counts.map((entry) => ({
      id: entry.value,
      label: formatBucketLabel(entry.value, t),
      count: entry.count,
    }))
  }
  const known = new Set(inventory)
  const rows = inventory.map((id) => ({
    id,
    label: formatBucketLabel(id, t),
    count: byId.get(id) ?? byId.get(id.toLowerCase()) ?? 0,
  }))
  for (const entry of counts) {
    if (!known.has(entry.value) && !known.has(entry.value.toLowerCase())) {
      rows.push({
        id: entry.value,
        label: formatBucketLabel(entry.value, t),
        count: entry.count,
      })
    }
  }
  return rows
}

function feedbackRatingContext(field: AggregationField): AggregationContext {
  const scaleMin =
    typeof field.scaleMin === "number"
      ? field.scaleMin
      : field.numerical?.min != null && field.numerical.min <= 1
        ? 1
        : 1
  const scaleMax =
    typeof field.scaleMax === "number"
      ? field.scaleMax
      : inferRatingScale(field) ?? (field.numerical?.max != null && field.numerical.max <= 10 ? 10 : 5)
  return {
    key: field.key,
    label: field.label,
    contextType: "user_feedback",
    scaleMin,
    scaleMax,
    facets: [field],
  }
}

function UserFeedbackBatchCard({ context }: { context: AggregationContext }) {
  const { t } = useI18n()
  const ratingFacets = context.facets.filter((facet) => facet.kind === "numerical")
  const choiceFacets = context.facets.filter((facet) => facet.kind === "categorical")
  const textFacets = context.facets.filter((facet) => facet.kind === "textual")
  const primaryRating =
    ratingFacets.find((facet) => facet.role === "primary") ??
    ratingFacets.find((facet) => feedbackFacetKey(facet).includes("overall_experience")) ??
    ratingFacets[0] ??
    null
  const otherRatings = ratingFacets.filter((facet) => facet.key !== primaryRating?.key)
  const judges = context.judges ?? []
  const explanation = explanationFacetForContext(context)
  const explanationLead =
    explanation?.textual?.summary && !isHeuristicAggregationSummary(explanation.textual.summary)
      ? fullProseText(explanation.textual.summary)
      : explanation?.textual?.samples?.[0]
        ? fullProseText(explanation.textual.samples[0])
        : null
  const ratingLead =
    primaryRating?.kind === "numerical"
      ? `${primaryRating.label}: ${t("reports.report.avg")} ${formatNumericalSummary(primaryRating)}${
          typeof primaryRating.scaleMax === "number"
            ? `/${primaryRating.scaleMax}`
            : inferRatingScale(primaryRating)
              ? `/${inferRatingScale(primaryRating)}`
              : ""
        }`
      : null
  const leadText = explanationLead || ratingLead
  const typeDescription = contextTypeDescription(context, t)
  const respondentCount = Math.max(
    ...context.facets.map((facet) => facet.presentCount ?? 0),
    context.facets[0]?.presentCount ?? 0,
    1,
  )

  return (
    <section className="overflow-hidden rounded-xl glass-panel">
      <div className="space-y-4 px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <FieldTitle field={context.label} />
            <InlineBadge>{t("reports.feedback.selfReport")}</InlineBadge>
            <span className="font-mono text-[13px] text-text-dim">
              {t("reports.report.personasCount", { count: respondentCount })}
            </span>
          </div>
          {typeDescription ? (
            <p className="mt-1 text-[14px] leading-relaxed text-text-dim">{typeDescription}</p>
          ) : null}
          {leadText ? (
            <p className="mt-1.5 max-w-4xl text-[14px] leading-relaxed text-text-main">{leadText}</p>
          ) : null}
        </div>

        {primaryRating ? (
          <div className="rounded-xl glass-tile p-3">
            <div className={`mb-2 ${facetTitleClassName(humanizeFacetLabel(primaryRating.label, primaryRating.key, t))}`}>
              {humanizeFacetLabel(primaryRating.label, primaryRating.key, t)}
            </div>
            <LikertQuestionBody context={feedbackRatingContext(primaryRating)} primary={primaryRating} />
          </div>
        ) : null}

        {choiceFacets.length > 0 ? (
          <div className="space-y-3">
            {choiceFacets.map((facet) => {
              const items = feedbackChoiceItems(facet, t)
              const total = Math.max(
                facet.presentCount,
                items.reduce((sum, item) => sum + item.count, 0),
                1,
              )
              return (
                <div key={facet.key} className="rounded-xl glass-tile p-3">
                  <div className={`mb-2 ${facetTitleClassName(humanizeFacetLabel(facet.label, facet.key, t))}`}>
                    {humanizeFacetLabel(facet.label, facet.key, t)}
                  </div>
                  <ChoiceCompositionChart items={items} respondentCount={total} />
                </div>
              )
            })}
          </div>
        ) : null}

        {otherRatings.length > 0 ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {otherRatings.map((facet) => (
              <div key={facet.key} className="rounded-xl glass-tile p-3">
                <div className={`mb-2 ${facetTitleClassName(humanizeFacetLabel(facet.label, facet.key, t))}`}>
                  {humanizeFacetLabel(facet.label, facet.key, t)}
                </div>
                <LikertQuestionBody context={feedbackRatingContext(facet)} primary={facet} />
              </div>
            ))}
          </div>
        ) : null}

        {textFacets.map((facet) => {
          const coverage = freeTextCoverage(facet, t)
          const signalThemes = freeTextSignalTags(
            judges.filter((judge) => judge.targetFacetKey === facet.facetKey || judge.targetFacetKey === facet.key),
          )
          const themes = (signalThemes.length > 0 ? signalThemes : coverage.themes).filter(
            (theme) => !isQuoteLikeTheme(theme),
          )
          const facetTitle = humanizeFacetLabel(facet.label, facet.key, t)
          const showSummary =
            coverage.summary &&
            !isHeuristicAggregationSummary(coverage.summary) &&
            // Avoid repeating the same long quote under both summary and examples.
            !(
              (facet.textual?.samples?.length ?? 0) === 1 &&
              coverage.summary.trim() === (facet.textual?.samples?.[0] ?? "").trim()
            )
          return (
            <div key={facet.key} className="space-y-2 rounded-xl glass-tile p-3">
              <div>
                <div className={facetTitleClassName(facetTitle)}>{facetTitle}</div>
                {facet.role === "explanation" ? (
                  <p className="mt-0.5 text-[12px] leading-relaxed text-text-dim">
                    {t("reports.feedback.personaOwnWords")}
                  </p>
                ) : null}
              </div>
              {showSummary ? (
                <p className="text-[14px] leading-relaxed text-text-main">{coverage.summary}</p>
              ) : null}
              {themes.length > 0 ? (
                <FreeTextThemeTags themes={themes} label={t("reports.feedback.mainTopics")} />
              ) : null}
              {(facet.textual?.samples?.length ?? 0) > 0 ? (
                <DisclosurePanel
                  title={t("reports.feedback.personaQuotesTitle", {
                    count: facet.textual?.samples?.length ?? 0,
                  })}
                  defaultOpen
                >
                  <SampleList samples={facet.textual?.samples ?? []} defaultExpanded />
                </DisclosurePanel>
              ) : null}
            </div>
          )
        })}
      </div>
    </section>
  )
}

function ContextCard({ context }: { context: AggregationContext }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const primaryFacet = primaryFacetForContext(context)
  const distributionItems = summaryBucketsForContext(context, t)
  const leadText = contextLeadText(context, t)
  const typeDescription = contextTypeDescription(context, t)
  const unanimousPrimary =
    primaryFacet?.kind === "categorical" && primaryFacet != null && isUnanimousField(primaryFacet)
  const showDistribution =
    !unanimousPrimary && primaryFacet?.kind !== "categorical" && distributionItems.length > 0
  const showPrimaryPreview = primaryFacet?.kind === "numerical" || (!showDistribution && !unanimousPrimary)
  const primaryValue = primaryFacet?.categorical?.counts?.[0]?.value ?? null

  return (
    <section className="overflow-hidden rounded-xl glass-panel">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={panelId}
        className={`w-full px-4 py-3 text-left transition-colors hover:bg-surface/30 ${FOCUS_RING}`}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <FieldTitle field={context.label} />
              {unanimousPrimary && primaryValue ? (
                <span className="inline-flex items-center gap-1 rounded-md bg-secondary/10 px-2 py-0.5 text-[13px] font-medium text-secondary">
                  <Sym name="check_circle" size={12} fill={1} />
                  {formatBucketLabel(primaryValue, t)}
                </span>
              ) : null}
            </div>
            {typeDescription ? (
              <p className="mt-1 text-[14px] leading-relaxed text-text-dim">{typeDescription}</p>
            ) : null}
            {leadText ? (
              <p className="mt-1.5 max-w-4xl text-[14px] leading-relaxed text-text-main">{leadText}</p>
            ) : null}
          </div>
          <span
            className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12px] uppercase tracking-wide ${
              open ? "glass-tile glass-tile--active text-primary" : "glass-tile text-text-dim"
            }`}
          >
            {open ? t("reports.analysis.collapse") : t("reports.analysis.expand")}
            <Sym name={open ? "expand_less" : "expand_more"} size={14} />
          </span>
        </div>

        {!unanimousPrimary ? (
          <div className={`mt-3 grid gap-2 ${showPrimaryPreview && showDistribution ? "lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]" : ""}`}>
            {primaryFacet && showPrimaryPreview ? (
              <div className="rounded-xl glass-tile p-2.5">
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <div className="text-[13px] font-medium uppercase tracking-wide text-text-dim">
                    {humanizeFacetLabel(primaryFacet.label, primaryFacet.key, t)}
                  </div>
                  {humanizeFacetRole(primaryFacet.role) ? (
                    <InlineBadge>{humanizeFacetRole(primaryFacet.role)}</InlineBadge>
                  ) : null}
                </div>
                <FacetVisual field={primaryFacet} compact />
              </div>
            ) : null}

            {showDistribution ? (
              <div className="rounded-xl glass-tile p-2.5">
                <div className="mb-1.5 text-[13px] font-medium uppercase tracking-wide text-text-dim">
                  {t("reports.facet.answerMix")}
                </div>
                <CountBars
                  items={distributionItems.slice(0, 3)}
                  total={distributionItems.reduce((sum, item) => sum + item.count, 0)}
                  compact
                  showDetails={false}
                />
              </div>
            ) : null}

            {primaryFacet?.kind === "categorical" && !showPrimaryPreview && !showDistribution ? (
              <div className="rounded-xl glass-tile p-2.5">
                <div className="mb-1.5 text-[13px] font-medium uppercase tracking-wide text-text-dim">
                  {t("reports.facet.distribution")}
                </div>
                <FacetVisual field={primaryFacet} compact />
              </div>
            ) : null}
          </div>
        ) : null}
      </button>

      {open ? (
        <div id={panelId} className="space-y-4 border-t border-outline/40 bg-surface/20 p-4">
          {context.facets.length > 0 ? (
            <div className="space-y-3">
              <SubsectionTitle
                title={t("reports.facet.details")}
                subtitle={t("reports.facet.detailsSubtitle")}
              />
              <div className="grid gap-3 lg:grid-cols-2">
                {orderedFacets(context.facets).map((facet) => (
                  <FacetCard key={facet.key} field={facet} />
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

function humanizeFacetKind(kind: string | null | undefined): string {
  const normalized = (kind ?? "").trim().toLowerCase()
  if (normalized === "categorical") return "categories"
  if (normalized === "numerical") return "scores"
  if (normalized === "textual") return "written answers"
  return kind ?? ""
}

function humanizeFacetRole(role: string | null | undefined): string | null {
  const normalized = (role ?? "").trim().toLowerCase()
  if (!normalized) return null
  if (normalized === "primary") return "main result"
  if (normalized === "explanation") return "persona explanation"
  if (normalized === "evidence") return "supporting detail"
  if (normalized === "score") return "score"
  return normalized.replace(/_/g, " ")
}

function FacetCard({ field }: { field: AggregationField }) {
  const { t } = useI18n()
  const textSummary = field.textual?.summary ?? null
  const textSamples = field.textual?.samples ?? []
  const title = humanizeFacetLabel(field.label, field.key, t)
  const roleLabel = humanizeFacetRole(field.role)

  return (
    <div className="rounded-xl glass-tile p-3">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[15px] font-medium text-text-main">{title}</div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] uppercase tracking-wide text-text-dim">
            <span>{humanizeFacetKind(field.kind)}</span>
            {roleLabel ? <InlineBadge>{roleLabel}</InlineBadge> : null}
            <span>{t("reports.report.presentCount", { count: field.presentCount })}</span>
            {field.missingCount > 0 ? (
              <span>{t("reports.report.missingCount", { count: field.missingCount })}</span>
            ) : null}
          </div>
        </div>
      </div>

      <FacetVisual field={field} />

      {field.kind === "textual" && (textSummary || textSamples.length > 0) ? (
        <div className="mt-3 space-y-2">
          {textSummary ? (
            <p className="text-[14px] leading-relaxed text-text-main">{textSummary}</p>
          ) : null}
          {textSamples.length > 0 ? (
            <DisclosurePanel
              title={t("reports.analysis.evidenceSamplesTitle")}
              subtitle={t("reports.analysis.capturedCount", { count: textSamples.length })}
              badge={t("reports.analysis.quotes")}
            >
              <SampleList samples={textSamples} />
            </DisclosurePanel>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function SummaryDisclosure({ summary }: { summary: AggregationSummary }) {
  const { t } = useI18n()
  const total = summary.buckets.reduce((sum, bucket) => sum + bucket.count, 0)
  const groupLower = summary.groupByFacetKey
    ? (() => {
        const label = humanizeFacetLabel(null, summary.groupByFacetKey, t)
        return `${label.charAt(0).toLowerCase()}${label.slice(1)}`
      })()
    : null
  // Auto reason-summaries self-describe from their facets; reporting.json ones keep their title.
  const title = summary.auto
    ? groupLower
      ? t("reports.analysis.titleBy", {
          title: crossFacetReasonPhrase(summary.targetFacetKey, t),
          group: groupLower,
        })
      : crossFacetReasonPhrase(summary.targetFacetKey, t)
    : humanizeAnalysisTitle(summary.title, t)
  const isPersonaGrouped = summary.groupByMode === "persona_attribute"
  const personaGroupLabel = (summary.groupByLabel || summary.groupByPersonaDimension || "")
    .toString()
    .toLowerCase()
  const subtitle = summary.auto
    ? t("reports.analysis.aiSummary")
    : isPersonaGrouped
      ? t("reports.analysis.customerInsight", {
          group: personaGroupLabel || t("reports.analysis.segment"),
        })
      : t("reports.analysis.personaByAnswer")

  return (
    <DisclosurePanel title={title} subtitle={subtitle} badge={humanizeAnalysisStatus(summary.status, t)}>
      {summary.error ? <p className="text-[14px] leading-relaxed text-danger">{summary.error}</p> : null}
      {summary.overall?.summary ? (
        <p className="text-[14px] leading-relaxed text-text-main">{fullProseText(summary.overall.summary)}</p>
      ) : null}
      {summary.buckets.length > 0 ? (
        <div className="mt-3 space-y-3">
          <CountBars
            items={summary.buckets.map((bucket) => ({
              label: formatBucketLabel(bucket.bucket, t),
              count: bucket.count,
            }))}
            total={total}
            showDetails={false}
          />
          <div className="space-y-2">
            {summary.buckets.map((bucket) => (
              <div key={`${summary.id}-${bucket.bucket}`} className="rounded-lg glass-tile p-3">
                <div className="flex items-center justify-between gap-3 text-[14px]">
                  <span className="font-medium text-text-main">{formatBucketLabel(bucket.bucket, t)}</span>
                  <span className="font-mono text-text-variant">{bucket.count}</span>
                </div>
                {bucket.summary ? (
                  <p className="mt-2 text-[14px] leading-relaxed text-text-variant">{fullProseText(bucket.summary)}</p>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </DisclosurePanel>
  )
}

/**
 * Theme × group presence matrix for an LLM signal judge.
 * Rows = signals (themes), columns = groups (buckets). A filled cell means the
 * LLM detected that theme in the group's explanations — this is topic *presence*,
 * not a quality score, so cells use a neutral fill (never green/red).
 */
/** Primary signal-scan view: how prevalent each signal is across all scored samples. */
function SignalPrevalence({ judge }: { judge: AggregationJudge }) {
  const [openKey, setOpenKey] = useState<string | null>(null)
  const stats = (judge.signalStats ?? [])
    .filter((stat) => (stat.total ?? 0) > 0)
    .slice()
    .sort((a, b) => b.present - a.present || (a.label || "").localeCompare(b.label || ""))
  if (stats.length === 0) return null

  return (
    <div className="space-y-2">
      {stats.map((stat) => {
        const total = Math.max(stat.total, 1)
        const pct = Math.round((stat.present / total) * 100)
        const examples = stat.examples ?? []
        const canExpand = examples.length > 0
        const expanded = openKey === stat.key
        return (
          <div key={stat.key} className="rounded-lg glass-tile p-2.5">
            <button
              type="button"
              disabled={!canExpand}
              onClick={() => canExpand && setOpenKey(expanded ? null : stat.key)}
              className={`flex w-full items-center gap-3 text-left ${canExpand ? FOCUS_RING : "cursor-default"}`}
            >
              <span className="min-w-0 flex-1 text-[14px] leading-snug text-text-variant">{stat.label}</span>
              <span className="shrink-0 font-mono text-[12px] text-text-dim">
                {stat.present}/{stat.total}
              </span>
              {canExpand ? (
                <Sym name={expanded ? "expand_less" : "expand_more"} size={16} className="shrink-0 text-text-dim" />
              ) : null}
            </button>
            <div className="mt-1.5 flex items-center gap-2">
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-high/40">
                <div className="h-full rounded-full bg-primary/70" style={{ width: `${pct}%` }} />
              </div>
              <span className="w-9 shrink-0 text-right text-[11px] text-text-dim">{pct}%</span>
            </div>
            {expanded && examples.length > 0 ? (
              <div className="mt-2">
                <SampleList samples={examples} defaultExpanded />
              </div>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

/** Optional secondary drill-down: signal prevalence split by persona segment.
 *
 * Only shown for the persona (customer-insight) lens. Cross-tabbing signals
 * against a feedback/outcome facet is redundant with the prevalence view and
 * fragments into tiny, misleading groups, so we don't render it there. */
function SignalGroupBreakdown({ judge }: { judge: AggregationJudge }) {
  const { t } = useI18n()
  if (String(judge.groupByMode ?? "") !== "persona_attribute") return null
  const signals = judge.signals ?? []
  const buckets = (judge.buckets ?? []).filter((bucket) => (bucket.signalStats ?? []).length > 0)
  if (signals.length === 0 || buckets.length < 2) return null
  const groupLabel = humanizeFacetLabel(judge.groupByLabel ?? null, judge.groupByFacetKey, t)
  const presentFor = (bucket: AggregationJudge["buckets"][number], key: string) =>
    (bucket.signalStats ?? []).find((stat) => stat.key === key) ?? null

  return (
    <DisclosurePanel
      title={t("reports.analysis.breakdownBy", { group: groupLabel })}
      subtitle={t("reports.analysis.groupThemeShare")}
    >
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr>
              <th className="p-1.5 text-left font-medium text-text-dim">
                {t("reports.analysis.signal")}
              </th>
              {buckets.map((bucket) => (
                <th key={bucket.bucket} className="whitespace-nowrap p-1.5 text-right font-medium text-text-dim">
                  {formatBucketLabel(bucket.bucket, t)}{" "}
                  <span className="font-normal text-text-dim/70">
                    {t("reports.report.countShort", { count: bucket.count })}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {signals.map((signal) => (
              <tr key={signal.key} className="border-t border-border/40">
                <td className="p-1.5 text-text-variant">{signal.label}</td>
                {buckets.map((bucket) => {
                  const stat = presentFor(bucket, signal.key)
                  const present = stat?.present ?? 0
                  const groupTotal = stat?.total ?? bucket.count
                  return (
                    <td key={bucket.bucket} className="p-1.5 text-right font-mono text-text-dim">
                      {present}/{groupTotal}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </DisclosurePanel>
  )
}

function JudgeDisclosure({ judge }: { judge: AggregationJudge }) {
  const { t } = useI18n()
  const rubricText = typeof judge.rubric === "string" && judge.rubric.trim() ? judge.rubric.trim() : null
  const total = judge.total ?? 0
  const hasStats = (judge.signalStats ?? []).some((stat) => (stat.total ?? 0) > 0)

  return (
    <DisclosurePanel
      title={humanizeAnalysisTitle(judge.title, t)}
      subtitle={t("reports.analysis.signalFrequency", {
        count: total || t("reports.analysis.the"),
        sampleLabel: total === 1 ? t("reports.analysis.sample") : t("reports.analysis.samples"),
      })}
      badge={humanizeAnalysisStatus(judge.status, t)}
    >
      <p className="mb-3 text-[12px] leading-relaxed text-text-dim">
        {t("reports.analysis.signalMethod")}
        {rubricText ? ` ${rubricText}` : ""}
      </p>
      {judge.overallAssessment ? (
        <p className="mb-3 text-[14px] leading-relaxed text-text-main">{judge.overallAssessment}</p>
      ) : null}
      {judge.error ? <p className="mb-3 text-[14px] leading-relaxed text-danger">{judge.error}</p> : null}
      {hasStats ? (
        <div className="space-y-3">
          <SignalPrevalence judge={judge} />
          <SignalGroupBreakdown judge={judge} />
        </div>
      ) : (
        <p className="text-[13px] text-text-dim">{t("reports.analysis.noSignals")}</p>
      )}
    </DisclosurePanel>
  )
}

function CrossFacetViewDisclosure({
  crossFacetView,
}: {
  crossFacetView: AggregationCrossFacetView
}) {
  const { t } = useI18n()
  const buckets = crossFacetView.buckets ?? []
  const total = buckets.reduce((sum, bucket) => sum + bucket.count, 0)
  const primaryLabel = crossFacetView.primaryFacetKey
    ? humanizeFacetLabel(null, crossFacetView.primaryFacetKey, t)
    : null
  const textLabel = crossFacetView.textFacetKey
    ? humanizeFacetLabel(null, crossFacetView.textFacetKey, t)
    : null
  const primaryLower = primaryLabel
    ? `${primaryLabel.charAt(0).toLowerCase()}${primaryLabel.slice(1)}`
    : null
  const title =
    primaryLower && textLabel
      ? t("reports.analysis.groupedBy", {
          reason: crossFacetReasonPhrase(crossFacetView.textFacetKey, t),
          answer: primaryLower,
        })
      : crossFacetView.type === "text_by_primary_category"
        ? t("reports.analysis.quotesByAnswer")
        : formatBucketLabel(crossFacetView.type, t)
  const subtitle = t("reports.analysis.expandGroupQuotes", {
    answer: primaryLower ?? t("reports.analysis.answer"),
  })

  return (
    <DisclosurePanel
      title={title}
      subtitle={subtitle}
      badge={t("reports.analysis.groupsCount", { count: buckets.length })}
    >
      <CountBars
        items={buckets.map((bucket) => ({
          label: formatBucketLabel(bucket.category, t),
          count: bucket.count,
        }))}
        total={total}
      />
      <div className="mt-3 space-y-2">
        {buckets.map((bucket) => (
          <div key={`${crossFacetView.type}-${bucket.category}`} className="rounded-lg glass-tile p-3">
            <div className="flex items-center justify-between gap-3 text-[14px]">
              <span className="font-medium text-text-main">{formatBucketLabel(bucket.category, t)}</span>
              <span className="font-mono text-text-variant">{bucket.count}</span>
            </div>
            {bucket.samples.length > 0 ? (
              <div className="mt-2">
                <DisclosurePanel
                  title={t("reports.analysis.examplesCount", { count: bucket.samples.length })}
                  subtitle={t("reports.analysis.shortPersonaQuotes")}
                >
                  <SampleList samples={bucket.samples} defaultExpanded />
                </DisclosurePanel>
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </DisclosurePanel>
  )
}

function FlatAggregationFallback({
  numerical,
  categorical,
  textual,
}: {
  numerical: AggregationField[]
  categorical: AggregationField[]
  textual: AggregationField[]
}) {
  const { t } = useI18n()
  return (
    <StudioGlassPanel className="overflow-hidden">
      <SectionHeader
        title={t("reports.report.responseSummaries")}
        subtitle={t("reports.analysis.noGroupedAnalysis")}
      />
      <div className="space-y-5 p-4">
        {numerical.length > 0 ? (
          <div className="space-y-3">
            <SubsectionTitle title={t("reports.report.numerical")} />
            <div className="grid gap-3 lg:grid-cols-2">
              {numerical.map((field) => (
                <FacetCard key={field.key} field={field} />
              ))}
            </div>
          </div>
        ) : null}
        {categorical.length > 0 ? (
          <div className="space-y-3">
            <SubsectionTitle title={t("reports.report.categorical")} />
            <div className="grid gap-3 lg:grid-cols-2">
              {categorical.map((field) => (
                <FacetCard key={field.key} field={field} />
              ))}
            </div>
          </div>
        ) : null}
        {textual.length > 0 ? (
          <div className="space-y-3">
            <SubsectionTitle title={t("reports.report.textual")} />
            <div className="grid gap-3 lg:grid-cols-2">
              {textual.map((field) => (
                <FacetCard key={field.key} field={field} />
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </StudioGlassPanel>
  )
}

function FacetVisual({ field, compact = false }: { field: AggregationField; compact?: boolean }) {
  const { t } = useI18n()
  if (field.kind === "numerical") {
    const min = field.numerical?.min
    const max = field.numerical?.max
    const avg = field.numerical?.avg
    const hasRange = min != null && max != null && avg != null && max > min
    const avgPct =
      hasRange && min != null && max != null && avg != null
        ? Math.max(0, Math.min(100, ((avg - min) / (max - min)) * 100))
        : null

    return (
      <div className="space-y-3">
        <div className={`flex flex-wrap items-end justify-between gap-3 ${compact ? "sm:flex-nowrap" : ""}`}>
          <div>
            <div className="text-[12px] uppercase tracking-wide text-text-dim">
              {t("reports.report.average")}
            </div>
            <div className={`${compact ? "text-[22px]" : "text-[30px]"} font-mono text-text-main`}>
              {metricValue(avg)}
            </div>
          </div>
          {compact ? (
            <div className="flex flex-wrap items-center gap-2 text-[13px] text-text-variant">
              <span>{t("reports.report.std")} {metricValue(field.numerical?.std)}</span>
              <span>{t("reports.report.present")} {field.presentCount}</span>
              {field.missingCount > 0 ? (
                <span>{t("reports.report.missingCount", { count: field.missingCount })}</span>
              ) : null}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2 text-[14px] text-text-variant sm:min-w-[220px]">
              <MetricLine label={t("reports.report.std")} value={metricValue(field.numerical?.std)} />
              <MetricLine label={t("reports.report.range")} value={`${metricValue(min)} - ${metricValue(max)}`} />
              <MetricLine label={t("reports.report.present")} value={String(field.presentCount)} />
              <MetricLine label={t("reports.report.missingLabel")} value={String(field.missingCount)} />
            </div>
          )}
        </div>
        {avgPct != null ? (
          <div className="space-y-1">
            <div className="relative h-2 rounded-full bg-surface-high">
              <div
                className="absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/60 bg-primary shadow-sm"
                style={{ left: `${avgPct}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-[13px] text-text-dim">
              <span>{metricValue(min)}</span>
              <span>{metricValue(max)}</span>
            </div>
          </div>
        ) : null}
      </div>
    )
  }

  if (field.kind === "categorical") {
    return (
      <CountBars
        items={(field.categorical?.counts ?? []).slice(0, compact ? 4 : 6).map((entry) => ({
          label: formatBucketLabel(entry.value, t),
          count: entry.count,
        }))}
        total={Math.max(field.presentCount, 1)}
        compact={compact}
        showDetails={!compact}
      />
    )
  }

  return (
    <div className="space-y-2">
      {field.textual?.summary ? (
        <p className="text-[14px] leading-relaxed text-text-main">
          {compact ? previewText(field.textual.summary, 180) : fullProseText(field.textual.summary)}
        </p>
      ) : (
        <p className="text-[14px] text-text-variant">{t("reports.analysis.noTextSummary")}</p>
      )}
      {!compact && (field.textual?.samples?.length ?? 0) > 0 ? (
        <div className="text-[13px] text-text-dim">
          {t("reports.analysis.evidenceSamples", { count: field.textual?.samples.length ?? 0 })}
        </div>
      ) : null}
    </div>
  )
}

function CountBars({
  items,
  total,
  compact = false,
  showDetails = true,
  showShare = false,
}: {
  items: CountBarItem[]
  total: number
  compact?: boolean
  showDetails?: boolean
  showShare?: boolean
}) {
  const { t } = useI18n()
  if (items.length === 0) {
    return <p className="text-[14px] text-text-variant">{t("reports.analysis.noDistribution")}</p>
  }

  return (
    <div className={compact ? "space-y-1.5" : "space-y-2"}>
      {items.map((item) => {
        const share = Math.round((item.count / Math.max(total, 1)) * 100)
        return (
          <div key={`${item.label}-${item.count}`} className="space-y-1">
            <div className={`flex items-center justify-between gap-3 ${compact ? "text-[13px]" : "text-[14px]"}`}>
              <span className="truncate text-text-main">{item.label}</span>
              <span className="shrink-0 font-mono text-text-variant">
                {item.count}
                {showShare ? ` · ${share}%` : ""}
              </span>
            </div>
            <div className="h-2 rounded-full bg-surface-high">
              <div className="h-2 rounded-full bg-primary/75" style={{ width: ratioWidth(item.count, total) }} />
            </div>
            {showDetails && item.detail ? (
              <p className="text-[14px] leading-relaxed text-text-dim">{fullProseText(item.detail)}</p>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

function SampleList({
  samples,
  defaultExpanded = false,
}: {
  samples: string[]
  defaultExpanded?: boolean
}) {
  const { t } = useI18n()
  const [expanded, setExpanded] = useState(defaultExpanded)
  const shown = expanded ? samples : samples.slice(0, 2)

  return (
    <div className="space-y-2">
      {shown.map((sample, index) => (
        <div
          key={`${index}-${sample.slice(0, 24)}`}
          className="rounded-md glass-tile px-3 py-2 text-[14px] leading-relaxed text-text-variant"
        >
          {fullProseText(sample)}
        </div>
      ))}
      {samples.length > 2 ? (
        <button
          type="button"
          data-pdf-ignore
          onClick={() => setExpanded((value) => !value)}
          className={`inline-flex items-center gap-1 rounded glass-tile glass-tile--hover px-2 py-1 text-[13px] text-text-dim ${FOCUS_RING}`}
        >
          <Sym name={expanded ? "expand_less" : "expand_more"} size={14} />
          {expanded
            ? t("reports.analysis.showFewerQuotes")
            : t("reports.analysis.showMoreQuotes", { count: samples.length - shown.length })}
        </button>
      ) : null}
    </div>
  )
}

function DisclosurePanel({
  title,
  subtitle,
  badge,
  children,
  defaultOpen = false,
}: {
  title: string
  subtitle?: string | null
  badge?: string | null
  children: ReactNode
  defaultOpen?: boolean
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(defaultOpen)
  const panelId = useId()

  return (
    <div className="overflow-hidden rounded-xl glass-tile">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={panelId}
        className={`flex w-full items-center justify-between gap-3 px-3 py-3 text-left hover:bg-surface/40 ${FOCUS_RING}`}
      >
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-[14px] font-medium text-text-main">{title}</div>
            {badge ? <InlineBadge>{badge}</InlineBadge> : null}
          </div>
          {subtitle ? <p className="mt-1 text-[14px] leading-relaxed text-text-dim">{subtitle}</p> : null}
        </div>
        <span className="inline-flex items-center gap-1 text-[12px] uppercase tracking-wide text-text-dim">
          {open ? t("reports.report.hide") : t("reports.report.view")}
          <Sym name={open ? "expand_less" : "expand_more"} size={14} />
        </span>
      </button>
      {open ? (
        <div id={panelId} className="space-y-3 border-t border-outline/40 bg-surface/20 p-3">
          {children}
        </div>
      ) : null}
    </div>
  )
}

function SectionHeader({
  title,
  subtitle,
}: {
  title: string
  subtitle?: string | null
}) {
  return (
    <div className="border-b border-outline/40 px-4 py-3">
      <div className="text-[12px] font-medium uppercase tracking-wide text-text-dim">{title}</div>
      {subtitle ? <p className="mt-1 text-[14px] leading-relaxed text-text-variant">{subtitle}</p> : null}
    </div>
  )
}

function SubsectionTitle({ title, subtitle }: { title: string; subtitle?: string | null }) {
  return (
    <div>
      <div className="text-[13px] font-medium uppercase tracking-wide text-text-dim">{title}</div>
      {subtitle ? <p className="mt-1 text-[14px] leading-relaxed text-text-variant">{subtitle}</p> : null}
    </div>
  )
}

/** Quiet inline metadata label — plain text so it never reads as a lit toggle. */
function InlineBadge({ children }: { children: ReactNode }) {
  return (
    <span className="text-[11px] uppercase tracking-wider text-text-dim">
      {children}
    </span>
  )
}

function ViewSwitchTab({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: string
  label: string
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-4 py-1.5 text-[14px] font-semibold transition-colors ${FOCUS_RING} ${
        active
          ? "border-primary bg-primary text-white shadow-sm"
          : "border-outline/50 bg-surface/70 text-text-variant hover:border-primary/40 hover:bg-surface hover:text-text"
      }`}
    >
      <Sym name={icon} size={16} />
      {label}
    </button>
  )
}

function CoverageTile({
  label,
  value,
  hint,
}: {
  label: string
  value: string | number
  hint?: string | null
}) {
  return (
    <div className="flex min-w-[120px] items-baseline gap-2 whitespace-nowrap rounded-lg glass-tile px-3 py-2">
      <span className="text-[11px] uppercase tracking-wide text-text-dim">{label}</span>
      <span className="font-mono text-[18px] leading-none text-text-main">{value}</span>
      {hint ? <span className="text-[12px] leading-snug text-text-variant">{hint}</span> : null}
    </div>
  )
}

/** Same question-type chip language as single-trial survey debrief / scorecard. */
function SurveyQuestionTypesTile({ counts }: { counts: SurveyQuestionTypeCount[] }) {
  const { t } = useI18n()
  return (
    <div className="min-w-[140px] rounded-lg glass-tile px-2.5 py-2">
      <div className="text-[11px] uppercase tracking-wide text-text-dim">
        {t("reports.report.questionTypes")}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {counts.map((entry) => (
          <span
            key={entry.type}
            className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-[12px] ${surveyQuestionTypeChipClass(entry.type)}`}
          >
            <span className="font-mono font-semibold tabular-nums">{entry.count}</span>
            {entry.label}
          </span>
        ))}
      </div>
    </div>
  )
}

function FieldTitle({ field }: { field: string }) {
  return <div className="text-[14px] font-medium text-text-main">{field}</div>
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-md bg-surface/50 px-2 py-1.5">
      <span>{label}</span>
      <span className="font-mono text-text-main">{value}</span>
    </div>
  )
}

export function HarborJobDetail({ jobName, onBack, onOpenTrial }: HarborJobDetailProps) {
  const { t } = useI18n()
  const queryClient = useQueryClient();
  const query = useQuery<HarborJobDetail>({
    queryKey: ["harbor-job", jobName],
    queryFn: () => api.getHarborJob(jobName),
    refetchInterval: (ctx) => {
      const launch = ctx.state.data?.launch;
      const trials = ctx.state.data?.trials ?? [];
      const pending = trials.some((trial) => !trial.completed);
      if (launch?.status === "running" || launch?.status === "queued" || pending) {
        return 3000;
      }
      return false;
    },
  });

  const job = query.data;
  const launch = job?.launch;
  const trials = job?.trials ?? [];
  const jobFinished = Boolean(
    job?.result &&
      typeof job.result === "object" &&
      (job.result as { finished_at?: unknown }).finished_at,
  );
  const liveLaunch =
    launch?.status === "running" || launch?.status === "queued";
  const jobInFlight =
    liveLaunch || (!jobFinished && trials.some((trial) => !trial.completed));

  const aggregationQuery = useQuery({
    queryKey: ["harbor-job-aggregation", jobName],
    queryFn: () => api.getHarborJobAggregation(jobName),
    enabled: query.isSuccess && trials.length > 0,
    refetchInterval: (ctx) => {
      const reporting = ctx.state.data?.reporting;
      const coverage = ctx.state.data?.coverage;
      const pending = trials.some((trial) => !trial.completed);
      // Modal/GKE merge artifacts a few seconds after Harbor marks trials
      // complete. Stop only once coverage has artifacts, or the launch has
      // been finished for two minutes (failed trials never grow artifacts).
      const artifactsPending =
        coverage != null &&
        (coverage.pendingTrials > 0 ||
          coverage.completedWithoutArtifactTrials > 0 ||
          coverage.artifactReadyTrials !== coverage.trialCount);
      const finishedAt = Date.parse(String(launch?.finishedAt ?? ""));
      const launchRecentlyFinished =
        launch?.status === "running" ||
        launch?.status === "queued" ||
        (Number.isFinite(finishedAt) && Date.now() - finishedAt < 120_000);
      if (
        launch?.status === "running" ||
        launch?.status === "queued" ||
        pending ||
        (artifactsPending && launchRecentlyFinished) ||
        reporting?.status === "queued" ||
        reporting?.status === "running"
      ) {
        return 3000;
      }
      return false;
    },
  });

  const aggregation = aggregationQuery.data ?? null;
  const aggregationLoading =
    aggregationQuery.isEnabled &&
    !aggregation &&
    (aggregationQuery.isPending || aggregationQuery.isFetching) &&
    !aggregationQuery.isError;
  const pdfMeta = useMemo(
    () => buildBatchReportPdfMeta(jobName, job, aggregation, t),
    [jobName, job, aggregation, t],
  );

  type JobDetailView = "status" | "report" | "runs";
  const [view, setView] = useState<JobDetailView | null>(null);
  const hasReport = Boolean(aggregation) || aggregationLoading;
  const defaultView: JobDetailView = jobInFlight || !hasReport ? "status" : "report";
  const activeView: JobDetailView = view ?? defaultView;

  const refreshAll = () => {
    void query.refetch();
    if (aggregationQuery.isEnabled) {
      void aggregationQuery.refetch();
    }
  };
  const prefetchTrialDebrief = (trialName: string) => {
    if (!onOpenTrial) return;
    void queryClient.prefetchQuery({
      queryKey: ["harbor-trial-debrief", jobName, trialName],
      queryFn: () => api.getHarborTrialDebrief(jobName, trialName),
      staleTime: 60_000,
    });
  };

  return (
    <StudioPageFrame>
      <StudioPageHeader
        eyebrow={`MatrAIx · ${t("reports.page.runsTab")}`}
        title={jobName}
        subtitle={
          launch?.configPath
            ? undefined
            : t("reports.page.openRunHint")
        }
        meta={
          launch?.status ? (
            <span className="rounded-lg glass-tile px-2.5 py-1 font-mono text-[13px] text-text-variant backdrop-blur">
              {launch.status}
              {launch.exitCode != null
                ? ` · ${t("reports.page.exit")} ${launch.exitCode}`
                : ""}
            </span>
          ) : null
        }
        actions={
          <>
            <StudioToolbarButton icon="arrow_back" onClick={onBack}>
              {t("reports.page.allJobs")}
            </StudioToolbarButton>
            <StudioToolbarButton
              icon="refresh"
              onClick={refreshAll}
              disabled={query.isFetching || aggregationQuery.isFetching}
            >
              {t("reports.page.refresh")}
            </StudioToolbarButton>
          </>
        }
      />
      {launch?.configPath ? (
        <p className="-mt-3 mb-5 break-all font-mono text-[13px] leading-snug text-text-variant">
          {t("reports.page.config")}: {launch.configPath}
        </p>
      ) : null}

      {query.isLoading ? (
        <p className="text-[15px] text-text-variant">{t("reports.page.loadingJob")}</p>
      ) : query.isError ? (
        <p className="text-[15px] text-danger">
          {query.error instanceof ApiError ? query.error.message : t("reports.page.loadFailed")}
        </p>
      ) : (
        <>
          {launch?.error && (
            <div className="mb-4 rounded-lg bg-danger/10 px-4 py-3 text-[15px] text-danger">
              {launch.error}
            </div>
          )}

          <div className="mb-4 flex items-center gap-2.5">
            <span className="text-[12px] font-medium uppercase tracking-wide text-text-dim">
              {t("reports.page.view")}
            </span>
            <div
              className="inline-flex gap-1 rounded-xl border border-outline/50 bg-surface/40 p-1 shadow-sm"
              role="tablist"
            >
              <ViewSwitchTab
                active={activeView === "status"}
                onClick={() => setView("status")}
                icon="grid_view"
                label={t("reports.page.runStatusTab")}
              />
              <ViewSwitchTab
                active={activeView === "report"}
                onClick={() => setView("report")}
                icon="analytics"
                label={t("reports.page.reportTab")}
              />
              <ViewSwitchTab
                active={activeView === "runs"}
                onClick={() => setView("runs")}
                icon="groups"
                label={t("reports.page.individualRuns", { count: trials.length })}
              />
            </div>
          </div>

          {activeView === "status" ? (
            <StudioGlassPanel className="mb-5 flex h-[min(48rem,calc(100vh-18rem))] min-h-[20rem] flex-col overflow-hidden p-3">
              <HarborJobLiveRoster
                jobName={jobName}
                config={job?.config}
                onOpenTrial={onOpenTrial}
              />
            </StudioGlassPanel>
          ) : null}

          {activeView === "report" && aggregationLoading ? (
            <StudioGlassPanel className="mb-4 flex items-center gap-2 px-4 py-8 text-[15px] text-text-variant">
              <Sym name="autorenew" size={18} className="animate-rb-spin text-primary" />
              {t("reports.page.loadingBatch")}
            </StudioGlassPanel>
          ) : null}

          {activeView === "report" && aggregation ? (
            <AggregationDashboard
              aggregation={aggregation}
              applicationType={job?.applicationType}
              pdfMeta={pdfMeta}
            />
          ) : null}

          {activeView === "report" && !aggregation && !aggregationLoading ? (
            <StudioGlassPanel className="mb-4 px-4 py-8 text-center text-[15px] text-text-variant">
              {aggregationQuery.isError
                ? aggregationQuery.error instanceof ApiError
                  ? aggregationQuery.error.message
                  : t("reports.page.reportFailed")
                : jobInFlight
                  ? t("reports.page.reportPending")
                  : t("reports.page.reportUnavailable")}
            </StudioGlassPanel>
          ) : null}

          {activeView === "runs" ? (
          <StudioGlassPanel className="overflow-hidden rounded-xl">
            <div className="flex items-center gap-2 border-b border-outline/40 px-4 py-3">
              <Sym name="groups" size={16} className="text-primary" />
              <span className="text-[15px] font-semibold text-text-main">
                {t("reports.page.individualRunsTitle")}
              </span>
              <span className="rounded-full glass-tile px-2 py-0.5 font-mono text-[12px] text-text-variant">
                {trials.length}
              </span>
              <span className="hidden text-[13px] text-text-dim sm:inline">
                · {t("reports.page.oneConversation")}
              </span>
            </div>
            <div className="grid grid-cols-[minmax(0,1.4fr)_minmax(0,1.2fr)_5.5rem_5.5rem_2rem] gap-3 border-b border-outline/40 px-4 py-2.5 text-[12px] uppercase tracking-wide text-text-dim">
              <span>{t("reports.page.persona")}</span>
              <span>{t("reports.page.run")}</span>
              <span>{t("reports.page.cost")}</span>
              <span>{t("reports.page.status")}</span>
              <span className="sr-only">{t("reports.page.open")}</span>
            </div>
            <ul className="divide-y divide-outline-dim">
              {trials.length === 0 ? (
                <li className="px-4 py-8 text-center text-[15px] text-text-variant">
                  {launch?.status === "running" || launch?.status === "queued"
                    ? t("reports.page.trialsStarting")
                    : t("reports.page.noTrials")}
                </li>
              ) : (
                trials.map((trial) => {
                  const clickable = Boolean(onOpenTrial);
                  const trialUsage = usageFromTrialResult(trial.result);
                  const costLabel = usageListPrimary(trialUsage, t);
                  const usageTitle = usageCompactLine(trialUsage, t);
                  return (
                    <li key={trial.trialName}>
                      <button
                        type="button"
                        disabled={!clickable}
                        onPointerEnter={() => prefetchTrialDebrief(trial.trialName)}
                        onFocus={() => prefetchTrialDebrief(trial.trialName)}
                        onClick={() => {
                          prefetchTrialDebrief(trial.trialName);
                          onOpenTrial?.(trial.trialName);
                        }}
                        className={`grid w-full grid-cols-[minmax(0,1.4fr)_minmax(0,1.2fr)_5.5rem_5.5rem_2rem] items-center gap-3 px-4 py-3 text-left text-[15px] ${
                          clickable ? "hover:bg-surface/40" : ""
                        } ${FOCUS_RING}`}
                      >
                        <TrialPersonaIdentity trial={trial} />
                        <span className="truncate font-mono text-[13px] text-text-variant">
                          {trial.trialName}
                        </span>
                        <span
                          className="truncate font-mono text-[12px] tabular-nums text-text-dim"
                          title={usageTitle ?? undefined}
                        >
                          {costLabel ?? "—"}
                        </span>
                        <TrialStatusBadge trial={trial} />
                        <Sym
                          name="chevron_right"
                          size={18}
                          className={clickable ? "text-text-dim" : "text-text-dim/40"}
                        />
                      </button>
                    </li>
                  );
                })
              )}
            </ul>
          </StudioGlassPanel>
          ) : null}
        </>
      )}
    </StudioPageFrame>
  );
}

export default HarborJobDetail;
