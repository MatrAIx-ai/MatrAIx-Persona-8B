/**
 * Shared chat trial debrief: persona subjective scores, objective task metrics,
 * then the conversational transcript (batch monitor + RunDetail).
 */
import type { ReactNode } from "react";

import { PersonaBubble, RecBotBubble } from "./cockpit/TurnBubble";
import { humanizeToken } from "./cockpit/cockpitShared";
import { useI18n } from "@/i18n/I18nProvider";
import {
  localizedBooleanLabel,
  localizedDecisionLabel,
  localizedStructuredChoiceLabel,
  type Translate,
} from "@/lib/localizedDisplayValues";
import {
  StatTile,
  appName,
  type RunConfig,
  type RunDetailView,
  type RunPersona,
  type RunTranscriptTurn,
} from "./runsShared";
import type { TurnView } from "@/lib/types";
import type { PlaygroundQuestionnaire } from "@/lib/types";
import type {
  TrialEvaluationArtifact,
  TrialEvaluationContext,
} from "@/lib/types";
import type { SelfReportSchema, UserFeedbackArtifact } from "@/lib/types";
import { SchemaSelfReportPanel } from "./SchemaSelfReportPanel";

export type ChatTrialVerifier = NonNullable<RunDetailView["verifier"]>;

export interface ChatTrialDebriefBodyProps {
  config: RunConfig;
  transcript: RunTranscriptTurn[];
  persona?: RunPersona | null;
  questionnaire?: PlaygroundQuestionnaire | null;
  userFeedback?: UserFeedbackArtifact | null;
  selfReportSchema?: SelfReportSchema | null;
  metricScores?: RunDetailView["metricScores"];
  verifier?: ChatTrialVerifier | null;
  trialEvaluation?: TrialEvaluationArtifact | null;
  /** Task title — the SUT label when `config.applicationId` is unknown. */
  taskTitle?: string | null;
  /** When false, hide section headings (embedded in batch monitor). */
  showSectionHeadings?: boolean;
}

function DashedNote({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-md glass-tile glass-tile--dim px-4 py-8 text-center text-[15px] text-text-variant">
      {children}
    </div>
  );
}

function SectionHeading({ children }: { children: ReactNode }) {
  return <h2 className="hud text-[12px] text-primary">{children}</h2>;
}

function SubsectionHeading({ children }: { children: ReactNode }) {
  return (
    <h3 className="text-[14px] font-semibold text-text-main">{children}</h3>
  );
}

function previewText(value: string | null | undefined, limit = 180): string {
  const normalized = (value ?? "").trim().replace(/\s+/g, " ");
  if (!normalized) return "";
  if (normalized.length <= limit) return normalized;
  return `${normalized.slice(0, limit - 1).trimEnd()}…`;
}

function contextOfType(
  trialEvaluation: TrialEvaluationArtifact | null | undefined,
  contextType: string,
): TrialEvaluationContext | null {
  return (
    trialEvaluation?.contexts.find(
      (context) => context.contextType === contextType,
    ) ?? null
  );
}

function facetValue(
  context: TrialEvaluationContext | null,
  key: string,
): string | number | boolean | null {
  const facet = context?.facets.find((item) => item.key === key);
  return facet?.value ?? null;
}

function facetText(
  context: TrialEvaluationContext | null,
  key: string,
): string {
  const value = facetValue(context, key);
  return typeof value === "string" ? value : "";
}

function facetNumber(
  context: TrialEvaluationContext | null,
  key: string,
): number | null {
  const value = facetValue(context, key);
  return typeof value === "number" ? value : null;
}

function formatFacetToken(
  value: string | number | boolean | null | undefined,
  t: Translate,
): string {
  if (typeof value === "boolean") return localizedBooleanLabel(value, t);
  if (typeof value === "number") return String(value);
  if (!value) return "-";
  return localizedStructuredChoiceLabel(value, t) ?? humanizeToken(value);
}

function SummarySignalCard({
  title,
  value,
  eyebrow,
  detail,
}: {
  title: string;
  value: ReactNode;
  eyebrow?: string | null;
  detail?: string | null;
}) {
  return (
    <div className="rounded-md glass-panel p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="hud text-[11px] text-text-dim">{title}</span>
        {eyebrow ? (
          <span className="inline-flex items-center glass-tile rounded px-2 py-0.5 text-[12px] text-text-variant">
            {eyebrow}
          </span>
        ) : null}
      </div>
      <div className="mt-2 text-[20px] font-semibold leading-tight text-text-main">
        {value}
      </div>
      {detail ? (
        <p className="mt-2 text-[14px] leading-relaxed text-text-variant">
          {detail}
        </p>
      ) : null}
    </div>
  );
}

function ChatContractSummary({
  trialEvaluation,
}: {
  trialEvaluation: TrialEvaluationArtifact | null | undefined;
}) {
  const { t } = useI18n();
  const outcome = contextOfType(trialEvaluation, "task_outcome");
  const conversation = contextOfType(trialEvaluation, "conversation_summary");
  const feedback =
    contextOfType(trialEvaluation, "user_feedback") ??
    contextOfType(trialEvaluation, "feedback");

  if (!outcome && !conversation && !feedback) return null;

  const outcomeStatus = formatFacetToken(
    facetValue(outcome, "outcome_status"),
    t,
  );
  const resolutionBasis = facetText(outcome, "resolution_basis");
  const outcomeReason = previewText(facetText(outcome, "outcome_reason"), 140);

  const conversationPath = formatFacetToken(
    facetValue(conversation, "conversation_path"),
    t,
  );
  const turnCount = facetNumber(conversation, "message_count");
  const clarificationCount = facetNumber(
    conversation,
    "clarification_question_count",
  );
  const processNotes = previewText(
    facetText(conversation, "process_notes"),
    140,
  );

  const rating = facetNumber(feedback, "overall_experience_rating");
  const needSatisfaction = formatFacetToken(
    facetValue(feedback, "need_constraint_satisfaction"),
    t,
  );
  const feedbackReason = previewText(
    facetText(feedback, "feedback_reason"),
    140,
  );

  return (
    <div className="space-y-3 glass-tile rounded-md p-4">
      <div className="space-y-1">
        <SubsectionHeading>{t("runs.trialSummary")}</SubsectionHeading>
        <p className="text-[14px] leading-relaxed text-text-variant">
          {t("runs.trialSummaryDescription")}
        </p>
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {outcome ? (
          <SummarySignalCard
            title={t("runs.taskOutcome")}
            value={outcomeStatus}
            eyebrow={
              resolutionBasis ? formatFacetToken(resolutionBasis, t) : null
            }
            detail={outcomeReason || t("runs.noOutcomeExplanation")}
          />
        ) : null}
        {conversation ? (
          <SummarySignalCard
            title={t("runs.conversationPath")}
            value={conversationPath}
            eyebrow={
              turnCount != null || clarificationCount != null
                ? t("runs.messagesAndClarifications", {
                    messages: turnCount ?? "-",
                    clarifications: clarificationCount ?? "-",
                  })
                : null
            }
            detail={processNotes || t("runs.noProcessSummary")}
          />
        ) : null}
        {feedback ? (
          <SummarySignalCard
            title={t("runs.userFeedback")}
            value={rating != null ? `${rating}/10` : needSatisfaction}
            eyebrow={rating != null ? needSatisfaction : null}
            detail={feedbackReason || t("runs.noFeedbackExplanation")}
          />
        ) : null}
      </div>
    </div>
  );
}

const _DEFAULT_FEEDBACK_KEYS = new Set([
  "needConstraintSatisfaction",
  "personalPreferenceSatisfaction",
  "overallExperienceRating",
  "reason",
  "askedUsefulClarificationQuestions",
  "clarifyingNotes",
  "trustLevel",
  "feltUnderstood",
]);

function inferSchemaFromFeedback(
  feedback: UserFeedbackArtifact,
): SelfReportSchema {
  const fields: SelfReportSchema["fields"] = [];
  for (const [key, value] of Object.entries(feedback)) {
    if (value === null || value === undefined || value === "") continue;
    let kind = "string";
    let minimum: number | null = null;
    let maximum: number | null = null;
    if (typeof value === "boolean") kind = "boolean";
    else if (typeof value === "number") {
      kind = "integer";
      if (key === "overallExperienceRating" || /rating|score/i.test(key)) {
        minimum = 1;
        maximum = 10;
      }
    } else if (
      typeof value === "string" &&
      ["yes", "no", "partially", "unsure", "true", "false"].includes(
        value.trim().toLowerCase(),
      )
    ) {
      kind = "enum";
    }
    fields.push({
      key,
      prompt: humanizeToken(key),
      kind,
      minimum,
      maximum,
      explains:
        key === "reason"
          ? "overallExperienceRating"
          : key === "clarifyingNotes"
            ? "askedUsefulClarificationQuestions"
            : null,
    });
  }
  const rank = (key: string) => {
    if (key === "overallExperienceRating") return 0;
    if (key === "reason") return 1;
    if (_DEFAULT_FEEDBACK_KEYS.has(key)) return 2;
    return 3;
  };
  fields.sort(
    (a, b) => rank(a.key) - rank(b.key) || a.key.localeCompare(b.key),
  );
  return { fields };
}

/** Persona simulator self-report after the chat (from ``user_feedback.json``). */
export function ChatSelfReport({
  questionnaire,
  userFeedback,
  selfReportSchema,
}: {
  questionnaire: PlaygroundQuestionnaire | null | undefined;
  userFeedback?: UserFeedbackArtifact | null;
  selfReportSchema?: SelfReportSchema | null;
}) {
  const { rich } = useI18n();
  const feedback: UserFeedbackArtifact | null =
    userFeedback && Object.keys(userFeedback).length > 0
      ? userFeedback
      : questionnaire
        ? ({
            overallExperienceRating: questionnaire.overallRating,
            reason: questionnaire.ratingReason,
            needConstraintSatisfaction:
              (questionnaire.constraintSatisfaction ?? 0) > 0
                ? questionnaire.constraintSatisfaction >= 4
                  ? "yes"
                  : questionnaire.constraintSatisfaction >= 3
                    ? "partially"
                    : "no"
                : undefined,
            personalPreferenceSatisfaction:
              (questionnaire.preferenceSatisfaction ?? 0) > 0
                ? questionnaire.preferenceSatisfaction >= 4
                  ? "yes"
                  : questionnaire.preferenceSatisfaction >= 3
                    ? "partially"
                    : "no"
                : undefined,
            askedUsefulClarificationQuestions:
              questionnaire.askedUsefulClarifyingQuestions,
            clarifyingNotes: questionnaire.clarifyingNotes,
            ...Object.fromEntries(
              Object.entries(questionnaire).filter(
                ([key]) =>
                  ![
                    "overallRating",
                    "ratingReason",
                    "constraintSatisfaction",
                    "constraintRationale",
                    "preferenceSatisfaction",
                    "preferenceRationale",
                    "askedUsefulClarifyingQuestions",
                    "clarifyingNotes",
                  ].includes(key),
              ),
            ),
          } as UserFeedbackArtifact)
        : null;

  const schema = selfReportSchema?.fields?.length
    ? selfReportSchema
    : feedback
      ? inferSchemaFromFeedback(feedback)
      : null;

  if (schema?.fields?.length && feedback) {
    return <SchemaSelfReportPanel schema={schema} feedback={feedback} />;
  }

  return (
    <DashedNote>
      {rich("runs.noPersonaSelfReport", {
        path: (parts) => (
          <span className="font-mono text-[13px]">{parts}</span>
        ),
      })}
    </DashedNote>
  );
}

/** Run completeness strip — shown first so pass/fail is visible before quality insights. */
export function ChatObjectiveEvaluation({
  metrics,
  verifier,
}: {
  metrics: RunDetailView["metricScores"];
  verifier?: ChatTrialVerifier | null;
}) {
  const { t } = useI18n();
  const artifactMissing =
    verifier &&
    !verifier.passed &&
    (verifier.detail?.includes("transcript.json is missing") ||
      verifier.detail?.includes("artifacts/app/output"));

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatTile caption={t("runs.turns")} value={metrics?.numTurns ?? "-"} />
        {verifier ? (
          <div
            className={`flex flex-col justify-center rounded-lg px-3 py-2.5 ${
              verifier.passed ? "bg-secondary/10" : "bg-danger/10"
            }`}
          >
            <span className="hud text-[11px] text-text-dim">
              {t("runs.runComplete")}
            </span>
            <div className="mt-1 flex items-center gap-2">
              <span className="text-[15px] font-semibold text-text-main">
                {verifier.passed
                  ? t("runs.passedChecks")
                  : t("runs.failedChecks")}
              </span>
              <span className="font-mono text-[13px] text-text-variant">
                {t("runs.reward", { reward: verifier.reward })}
              </span>
            </div>
          </div>
        ) : (
          <div className="flex flex-col justify-center rounded-lg glass-tile glass-tile--dim px-3 py-2.5">
            <span className="hud text-[11px] text-text-dim">
              {t("runs.runComplete")}
            </span>
            <span className="mt-1 text-[15px] text-text-variant">
              {t("runs.checksPending")}
            </span>
          </div>
        )}
      </div>
      {artifactMissing ? (
        <p className="text-[14px] leading-relaxed text-text-variant">
          {t("runs.artifactMissingDescription")}
        </p>
      ) : null}
      {verifier?.detail && !verifier.passed ? (
        <pre className="custom-scrollbar max-h-24 overflow-auto whitespace-pre-wrap rounded-md glass-tile px-3 py-2 font-mono text-[12px] leading-snug text-text-variant">
          {verifier.detail}
        </pre>
      ) : null}
    </div>
  );
}

export function ChatTrialTranscript({
  transcript,
  appLabel,
  domain = "movie",
  persona,
}: {
  transcript: RunTranscriptTurn[];
  appLabel: string;
  domain?: string;
  persona?: RunPersona | null;
}) {
  const { t } = useI18n();
  if (transcript.length === 0) {
    return <DashedNote>{t("runs.noConversationTurns")}</DashedNote>;
  }
  return (
    <div className="space-y-7 rounded-md glass-panel p-5">
      {transcript.map((turn, i) => (
        <TranscriptTurn
          key={turn.turnIndex ?? i}
          turn={turn}
          index={i}
          appLabel={appLabel}
          domain={domain}
          persona={persona}
        />
      ))}
    </div>
  );
}

/** Run checks first, then evaluation (chat summary + persona report), transcript below. */
export function ChatTrialDebriefBody({
  config,
  transcript,
  persona,
  questionnaire,
  userFeedback,
  selfReportSchema,
  metricScores,
  verifier,
  trialEvaluation,
  taskTitle,
  showSectionHeadings = true,
}: ChatTrialDebriefBodyProps) {
  const { t } = useI18n();
  const applicationId = config.applicationId?.trim() || null;
  const app = applicationId
    ? appName(applicationId, t)
    : taskTitle?.trim() || appName(null, t);

  return (
    <div className="space-y-6">
      <section className="space-y-4">
        {showSectionHeadings && (
          <SectionHeading>{t("runs.evaluation")}</SectionHeading>
        )}
        <div className="space-y-2 glass-tile rounded-md p-3">
          <p className="text-[14px] leading-relaxed text-text-variant">
            {t("runs.evaluationDescription")}
          </p>
          <ChatObjectiveEvaluation metrics={metricScores} verifier={verifier} />
        </div>
        <ChatContractSummary trialEvaluation={trialEvaluation} />
        <div className="space-y-3 glass-tile rounded-md p-4">
          {showSectionHeadings && (
            <SubsectionHeading>{t("runs.personaSelfReport")}</SubsectionHeading>
          )}
          <p className="text-[14px] leading-relaxed text-text-variant">
            {t("runs.personaSelfReportDescription")}
          </p>
          <ChatSelfReport
            questionnaire={questionnaire}
            userFeedback={userFeedback}
            selfReportSchema={selfReportSchema}
          />
        </div>
      </section>

      <section className="space-y-3">
        {showSectionHeadings && (
          <SectionHeading>{t("runs.conversation")}</SectionHeading>
        )}
        <ChatTrialTranscript
          transcript={transcript}
          appLabel={app}
          domain={String(config.domain ?? "movie")}
          persona={persona}
        />
      </section>
    </div>
  );
}

function TranscriptTurn({
  turn,
  index,
  appLabel,
  domain,
  persona,
}: {
  turn: RunTranscriptTurn;
  index: number;
  appLabel: string;
  domain: string;
  persona?: RunPersona | null;
}) {
  const { t } = useI18n();
  const turnView: TurnView = {
    userMessage: turn.userMessage,
    assistantMessage: turn.assistantMessage ?? "",
    structuredExposure: turn.structuredExposure ?? [],
    durationSeconds: turn.durationSeconds,
    plan: [],
  };

  return (
    <div
      className="space-y-7 rise-in"
      style={{
        animationDelay: `${Math.min(index, 6) * 30}ms`,
        animationFillMode: "backwards",
      }}
    >
      <div className="flex items-center justify-center">
        <span className="hud text-[11px] text-text-dim">
          {t("runs.turn", { count: index + 1 })}
        </span>
      </div>
      <PersonaBubble
        message={turn.userMessage}
        personaId={persona?.id}
        personaName={persona?.name}
        personaDimensions={persona?.dimensions ?? undefined}
      />
      {turn.decision && turn.decision !== "continue" ? (
        <div className="flex items-start gap-2.5 pr-10">
          <div className="h-8 w-8 shrink-0" aria-hidden />
          <DecisionTag decision={turn.decision} />
        </div>
      ) : null}
      <RecBotBubble
        turn={turnView}
        domain={domain}
        appName={appLabel}
        foldOpen={false}
        onToggleFold={() => undefined}
      />
    </div>
  );
}

function DecisionTag({ decision }: { decision: string }) {
  const { t } = useI18n();
  const satisfied = decision === "satisfied";
  const cls = satisfied
    ? "text-secondary bg-secondary/10"
    : "text-warn bg-warn/10";
  const label = localizedDecisionLabel(decision, t) ?? humanizeToken(decision);
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-px hud text-[11px] ${cls}`}
    >
      {label}
    </span>
  );
}

export default ChatTrialDebriefBody;
