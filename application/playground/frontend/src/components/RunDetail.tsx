/**
 * RunDetail: one persisted run, rebuilt as the mockup's "Run debrief".
 *
 * Shape mirrors `data-view="runs"` (app-redesign-v3.html:340-429): a back link +
 * "Run debrief" H1 with a run-type reflection on the right, a one-line run-meta
 * breadcrumb, a headline score band + metric tiles, then the body.
 *
 * Option-aware, honestly scoped (spec §05): the debrief renders the stored
 * application artifact shape: chatbot, survey, web, or OS app.
 */
import { useMemo, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  StatTile,
  AppTypeTag,
  appName,
  asRunDetail,
  fmtDomain,
  fmtRunDateFriendly,
  runApplicationType,
  runWebTrace,
  type RunApplicationType,
  type RunDetailView,
} from "./runsShared";
import { ChatTrialDebriefBody } from "./ChatTrialDebrief";
import { TrialDebriefRails } from "./TrialDebriefRails";
import { HarborTraceReplay } from "./cockpit/HarborTraceReplay";
import { OsAppEvalScorecard } from "./cockpit/TaskEvalScorecard";
import {
  StudioGlassPanel,
  StudioPageFrame,
  StudioPageHeader,
  StudioToolbarButton,
} from "./studio/StudioShell";
import {
  FOCUS_RING,
  SCORE_BAND_CLASS,
  Sym,
  humanizeToken,
  scoreBand,
} from "./cockpit/cockpitShared";
import { api, ApiError } from "@/lib/api";
import { useI18n, type I18nContextValue } from "@/i18n/I18nProvider";
import { localizedBooleanLabel } from "@/lib/localizedDisplayValues";
import {
  asLlmUsage,
  usageTableRows,
} from "@/lib/llmUsage";
import {
  countSurveyQuestionTypes,
  formatSurveyTrajectoryValue,
  groupSurveyTrajectory,
  surveyQuestionTypeChipClass,
  surveyQuestionTypeLabel,
  surveyTrajectoryPrompt,
  surveyTrajectoryQuestionIndex,
  surveyTrajectoryQuestionType,
} from "@/lib/surveyDisplay";
import type {
  PlaygroundResult,
  OsAppResult,
  SurveyAnswer,
  SurveyInstrument,
  SurveyQuestion,
  SurveyTrajectoryEvent,
  TrialEvaluationArtifact,
  UserFeedbackArtifact,
  WebTrace,
} from "@/lib/types";

export interface RunDetailProps {
  harborTrial: { jobName: string; trialName: string };
  onBack: () => void;
}

type Translate = I18nContextValue["t"];

function runDebriefMetaLine(
  run: RunDetailView,
  appType: RunApplicationType,
  t: Translate,
): string {
  const parts: string[] = [];
  if (appType === "survey" && run.surveyResult) {
    parts.push(
      run.surveyResult.instrument.title ||
        run.instrumentTitle ||
        run.surveyResult.instrument.id,
    );
  } else if (appType === "web" && run.webResult) {
    const task = run.taskTitle || run.siteName || t("runs.websiteTask");
    parts.push(
      run.siteName && run.taskTitle
        ? t("runs.taskOnSite", { task, site: run.siteName })
        : task,
    );
  } else if (appType === "os-app") {
    parts.push(run.taskTitle || t("runs.osAppTask"));
  } else {
    const applicationId = run.config?.applicationId?.trim() || null;
    const app = applicationId
      ? appName(applicationId, t)
      : run.taskTitle || appName(null, t);
    const domain = run.config?.domain
      ? t("runs.domainCatalog", { domain: fmtDomain(run.config.domain) })
      : "";
    parts.push(domain ? `${app} · ${domain}` : app);
  }
  if (run.persona?.name) {
    parts.push(run.persona.name);
  }
  const when = fmtRunDateFriendly(
    run.surveyResult?.createdAt ?? run.webResult?.createdAt ?? run.createdAt,
    t,
  );
  if (when) {
    parts.push(
      when === t("runs.relative.justNow") ||
        when === t("runs.relative.yesterday")
        ? when
        : t("runs.ranAt", { when }),
    );
  }
  return parts.join(" · ");
}

export function RunDetail({ harborTrial, onBack }: RunDetailProps) {
  const { t } = useI18n();
  const query = useQuery<PlaygroundResult>({
    queryKey: [
      "harbor-trial-debrief",
      harborTrial.jobName,
      harborTrial.trialName,
    ],
    queryFn: () =>
      api.getHarborTrialDebrief(harborTrial.jobName, harborTrial.trialName),
    staleTime: 60_000,
  });

  const run = useMemo(
    () => (query.data ? asRunDetail(query.data) : null),
    [query.data],
  );
  const appType: RunApplicationType = run ? runApplicationType(run) : "chatbot";
  const metaLine = run ? runDebriefMetaLine(run, appType, t) : null;
  const absoluteWhen = run
    ? (run.surveyResult?.createdAt ??
      run.webResult?.createdAt ??
      run.createdAt ??
      null)
    : null;
  const usage = run ? asLlmUsage(run.usage) : null;
  const usageRows = usageTableRows(usage, t);

  return (
    <StudioPageFrame>
      <StudioPageHeader
        compact
        eyebrow={t("runs.eyebrow")}
        title={metaLine || harborTrial.trialName}
        meta={run ? <AppTypeTag type={appType} /> : null}
        actions={
          <>
            <StudioToolbarButton icon="arrow_back" onClick={onBack}>
              {t("runs.backToJob")}
            </StudioToolbarButton>
            <StudioToolbarButton
              icon="refresh"
              onClick={() => query.refetch()}
              disabled={query.isFetching}
            >
              {t("runs.refresh")}
            </StudioToolbarButton>
            <StudioToolbarButton
              icon="picture_as_pdf"
              onClick={() =>
                api.downloadHarborTrialReportPdf(
                  harborTrial.jobName,
                  harborTrial.trialName,
                )
              }
            >
              {t("runs.downloadPdf")}
            </StudioToolbarButton>
          </>
        }
      />

      <p className="-mt-2 mb-2 break-all font-mono text-[12px] leading-relaxed text-text-dim">
        {harborTrial.trialName} · {harborTrial.jobName}
        {absoluteWhen ? ` · ${fmtRunDateFriendly(absoluteWhen, t)}` : ""}
      </p>
      {usageRows.length > 0 ? (
        <div
          className="mb-3.5 grid gap-px overflow-hidden rounded-lg border border-outline/40 bg-outline/25 text-[12px]"
          style={{ gridTemplateColumns: `repeat(${usageRows.length}, minmax(0, 1fr))` }}
        >
          {usageRows.map((row) => (
            <div key={row.label} className="flex items-baseline gap-1.5 bg-surface/80 px-2.5 py-1.5">
              <span className="font-medium uppercase tracking-wide text-text-dim">{row.label}</span>
              <span className="font-mono tabular-nums text-text-variant">{row.value}</span>
            </div>
          ))}
        </div>
      ) : null}

      {query.isLoading ? (
        <DetailLoading />
      ) : query.isError ? (
        <DetailError error={query.error} onRetry={() => query.refetch()} />
      ) : !run ? (
        <DetailNotFound />
      ) : (
        <>
          {appType === "survey" ? (
            <SurveyDebrief run={run} />
          ) : appType === "web" ? (
            <WebDebrief run={run} />
          ) : appType === "os-app" ? (
            <OsAppDebrief run={run} />
          ) : (
            <ChatbotDebrief run={run} />
          )}
        </>
      )}
    </StudioPageFrame>
  );
}

// ---------------------------------------------------------------------------
// Shared chrome
// ---------------------------------------------------------------------------

function DebriefPanel({
  title,
  icon,
  children,
  className = "",
  bodyClassName = "",
}: {
  title?: string;
  icon?: string;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <StudioGlassPanel
      className={`flex h-full flex-col overflow-hidden ${className}`}
    >
      {title ? (
        <div className="flex shrink-0 items-center gap-2 border-b border-outline/40 px-4 py-2.5 text-[12px] font-medium uppercase tracking-wide text-text-dim">
          {icon ? <Sym name={icon} size={14} className="text-primary" /> : null}
          {title}
        </div>
      ) : null}
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </StudioGlassPanel>
  );
}

function TrialDebriefChrome({
  prompts,
  persona,
  instructionMarkdown,
  contextMarkdown,
  questionnaire,
  questionnaireMarkdown,
  outputSchemaMarkdown,
  hideOutputSchema,
  children,
}: {
  prompts?: RunDetailView["prompts"];
  persona?: RunDetailView["persona"];
  instructionMarkdown?: RunDetailView["instructionMarkdown"];
  contextMarkdown?: RunDetailView["contextMarkdown"];
  questionnaire?: SurveyInstrument | null;
  questionnaireMarkdown?: RunDetailView["questionnaireMarkdown"];
  outputSchemaMarkdown?: RunDetailView["outputSchemaMarkdown"];
  hideOutputSchema?: boolean;
  children: ReactNode;
}) {
  const rails = (
    <TrialDebriefRails
      prompts={prompts}
      persona={persona ?? null}
      instructionMarkdown={instructionMarkdown ?? null}
      contextMarkdown={contextMarkdown ?? null}
      questionnaire={questionnaire ?? null}
      questionnaireMarkdown={questionnaireMarkdown ?? null}
      outputSchemaMarkdown={outputSchemaMarkdown ?? null}
      hideOutputSchema={hideOutputSchema}
    />
  );

  return (
    <div className="space-y-5">
      {rails ? (
        <StudioGlassPanel className="divide-y divide-outline/40 overflow-hidden">
          {rails}
        </StudioGlassPanel>
      ) : null}
      {children}
    </div>
  );
}

/** A quiet dashed "nothing here" note, reused by empty bodies. */
function DashedNote({ children }: { children: ReactNode }) {
  return (
    <div className="px-4 py-10 text-center text-[15px] text-text-variant">
      {children}
    </div>
  );
}

/** Pass/fail status — mint is reserved for this, not for question-type chips. */
function ValidityBadge({
  valid,
  validLabel,
  invalidLabel,
}: {
  valid: boolean;
  validLabel: string;
  invalidLabel: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[13px] font-semibold ${
        valid ? "bg-secondary/15 text-secondary" : "bg-danger/15 text-danger"
      }`}
    >
      <Sym name={valid ? "check_circle" : "error"} fill={1} size={14} />
      {valid ? validLabel : invalidLabel}
    </span>
  );
}

function humanizeFeedbackKey(key: string): string {
  const snake = key.replace(/([a-z0-9])([A-Z])/g, "$1_$2");
  return humanizeToken(snake);
}

function feedbackDisplayValue(value: unknown, t: Translate): string {
  if (typeof value === "boolean") return localizedBooleanLabel(value, t);
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  return "-";
}

function feedbackNumericValue(
  feedback: UserFeedbackArtifact | null | undefined,
  key: string,
): number | null {
  const value = feedback?.[key];
  return typeof value === "number" ? value : null;
}

function feedbackTextValue(
  feedback: UserFeedbackArtifact | null | undefined,
  key: string,
): string {
  const value = feedback?.[key];
  return typeof value === "string" ? value : "";
}

function feedbackBooleanValue(
  feedback: UserFeedbackArtifact | null | undefined,
  key: string,
): boolean | null {
  const value = feedback?.[key];
  return typeof value === "boolean" ? value : null;
}

function trialEvaluationFeedback(
  run: RunDetailView,
): UserFeedbackArtifact | null {
  const context =
    run.trialEvaluation?.contexts.find(
      (item) =>
        item.contextType === "user_feedback" || item.contextType === "feedback",
    ) ?? null;
  if (!context) return null;
  const payload: UserFeedbackArtifact = {};
  for (const facet of context.facets) {
    const value = facet.value;
    if (
      typeof value === "string" ||
      typeof value === "number" ||
      typeof value === "boolean" ||
      value === null
    ) {
      payload[facet.key] = value;
    }
  }
  return Object.keys(payload).length > 0 ? payload : null;
}

function resolveUserFeedback(run: RunDetailView): UserFeedbackArtifact | null {
  return run.userFeedback ?? trialEvaluationFeedback(run);
}

function UserFeedbackPanel({
  feedback,
}: {
  feedback: UserFeedbackArtifact | null | undefined;
}) {
  const { t, rich } = useI18n();
  const overall = feedbackNumericValue(feedback, "overallExperienceRating");
  const trust = feedbackNumericValue(feedback, "trustLevel");
  const effort = feedbackNumericValue(feedback, "effortRating");
  const clarity = feedbackNumericValue(feedback, "clarityOfNextStep");
  const feltUnderstood = feedbackBooleanValue(feedback, "feltUnderstood");
  const reason = feedbackTextValue(feedback, "reason");
  const extraEntries = Object.entries(feedback ?? {})
    .filter(
      ([, value]) => value !== null && value !== undefined && value !== "",
    )
    .filter(
      ([key]) =>
        ![
          "overallExperienceRating",
          "trustLevel",
          "effortRating",
          "clarityOfNextStep",
          "feltUnderstood",
          "reason",
        ].includes(key),
    );

  return (
    <DebriefPanel
      title={t("runs.personaSelfReport")}
      icon="rate_review"
      bodyClassName="p-4"
    >
      {!feedback || Object.keys(feedback).length === 0 ? (
        <DashedNote>
          {rich("runs.noPostRunSelfReport", {
            path: (parts) => (
              <span className="font-mono text-[13px]">{parts}</span>
            ),
          })}
        </DashedNote>
      ) : (
        <div className="space-y-4">
          <p className="text-[14px] leading-relaxed text-text-variant">
            {rich("runs.subjectiveReflection", {
              path: (parts) => <span className="font-mono">{parts}</span>,
            })}
          </p>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {overall != null ? (
              <StatTile
                lead
                caption={t("runs.overallExperience")}
                value={overall}
                unit="/10"
                band={scoreBand(overall / 10)}
              />
            ) : null}
            {trust != null ? (
              <StatTile caption={t("runs.trust")} value={trust} unit="/10" />
            ) : null}
            {effort != null ? (
              <StatTile caption={t("runs.effort")} value={effort} />
            ) : null}
            {clarity != null ? (
              <StatTile caption={t("runs.nextStepClarity")} value={clarity} />
            ) : null}
            {feltUnderstood != null ? (
              <div className="flex flex-col justify-center rounded-lg glass-tile p-4 backdrop-blur-sm">
                <span className="hud text-[11px] text-text-dim">
                  {t("runs.feltUnderstood")}
                </span>
                <div className="mt-1.5">
                  <ValidityBadge
                    valid={feltUnderstood}
                    validLabel={t("runs.yes")}
                    invalidLabel={t("runs.notReally")}
                  />
                </div>
              </div>
            ) : null}
          </div>

          {extraEntries.length > 0 ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {extraEntries.map(([key, value]) => (
                <div
                  key={key}
                  className="rounded-lg glass-tile p-3 backdrop-blur-sm"
                >
                  <div className="text-[12px] uppercase tracking-wide text-text-dim">
                    {humanizeFeedbackKey(key)}
                  </div>
                  <div className="mt-1.5 text-[15px] leading-relaxed text-text-main">
                    {feedbackDisplayValue(value, t)}
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          {reason ? (
            <div className="rounded-lg glass-tile p-4 backdrop-blur-sm">
              <div className="text-[12px] uppercase tracking-wide text-text-dim">
                {t("runs.reasoning")}
              </div>
              <div className="mt-1.5 text-[14px] leading-relaxed text-text-variant">
                {reason}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </DebriefPanel>
  );
}

// ===========================================================================
// Chatbot debrief
// ===========================================================================

function ChatbotDebrief({ run }: { run: RunDetailView }) {
  const persona = run.persona ?? {};
  const config = run.config ?? {};

  return (
    <TrialDebriefChrome
      prompts={run.prompts}
      persona={persona}
      instructionMarkdown={run.instructionMarkdown}
      contextMarkdown={run.contextMarkdown}
      questionnaireMarkdown={run.questionnaireMarkdown}
      outputSchemaMarkdown={run.outputSchemaMarkdown}
    >
      <ChatTrialDebriefBody
        config={config}
        transcript={run.transcript ?? []}
        persona={run.persona}
        questionnaire={run.questionnaire}
        userFeedback={run.userFeedback}
        selfReportSchema={run.selfReportSchema}
        metricScores={run.metricScores}
        verifier={run.verifier}
        trialEvaluation={run.trialEvaluation}
        taskTitle={run.taskTitle}
      />
    </TrialDebriefChrome>
  );
}

// ===========================================================================
// Survey debrief: reads `SurveyResult` (types.ts)
// ===========================================================================

function SurveyDebrief({ run }: { run: RunDetailView }) {
  const { t } = useI18n();
  const survey = run.surveyResult;
  const persona = run.persona ?? {};
  if (!survey) {
    return (
      <TrialDebriefChrome
        prompts={run.prompts}
        persona={persona}
        instructionMarkdown={run.instructionMarkdown}
        contextMarkdown={run.contextMarkdown}
        questionnaireMarkdown={run.questionnaireMarkdown}
        hideOutputSchema
      >
        <DashedNote>{t("runs.noSurveyResults")}</DashedNote>
      </TrialDebriefChrome>
    );
  }

  const c = survey.completion;
  const questionsById = new Map<string, SurveyQuestion>(
    survey.instrument.questions.map((qq) => [qq.id, qq]),
  );
  const typeCounts = countSurveyQuestionTypes(survey.instrument.questions, t);
  const trajectoryGroups = groupSurveyTrajectory(survey.trajectory);

  return (
    <TrialDebriefChrome
      prompts={run.prompts}
      persona={persona}
      instructionMarkdown={run.instructionMarkdown}
      contextMarkdown={run.contextMarkdown}
      questionnaire={survey.instrument}
      questionnaireMarkdown={run.questionnaireMarkdown}
      hideOutputSchema
    >
      <DebriefPanel bodyClassName="p-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatTile
            lead
            caption={t("runs.questionsAnswered")}
            value={`${c.numAnswered}/${c.numQuestions}`}
          />
          <div className="flex flex-col justify-center rounded-lg glass-tile p-4 backdrop-blur-sm">
            <span className="hud text-[11px] text-text-dim">
              {t("runs.answersLookValid")}
            </span>
            <div className="mt-1.5">
              <ValidityBadge
                valid={c.valid}
                validLabel={t("runs.valid")}
                invalidLabel={t("runs.needsReview")}
              />
            </div>
          </div>
          <div className="flex flex-col justify-center rounded-lg glass-tile p-4 backdrop-blur-sm">
            <span className="hud text-[11px] text-text-dim">
              {t("runs.questionTypes")}
            </span>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {typeCounts.length === 0 ? (
                <span className="text-[14px] text-text-dim">
                  {t("runs.notAvailable")}
                </span>
              ) : (
                typeCounts.map((entry) => (
                  <span
                    key={entry.type}
                    className={`hud inline-flex items-center gap-1 rounded border px-2 py-1 text-[11px] ${surveyQuestionTypeChipClass(entry.type)}`}
                  >
                    <span className="tabular-nums font-semibold">
                      {entry.count}
                    </span>
                    {entry.label}
                  </span>
                ))
              )}
            </div>
          </div>
        </div>
      </DebriefPanel>

      <div className="grid grid-cols-1 items-stretch gap-5 lg:grid-cols-12">
        <DebriefPanel
          title={t("runs.answers")}
          icon="fact_check"
          className="lg:col-span-7"
          bodyClassName="overflow-y-auto"
        >
          {survey.answers.length === 0 ? (
            <DashedNote>{t("runs.noSurveyAnswers")}</DashedNote>
          ) : (
            <ul className="divide-y divide-outline-dim">
              {survey.answers.map((a, i) => (
                <SurveyAnswerRow
                  key={a.questionId}
                  answer={a}
                  question={questionsById.get(a.questionId)}
                  index={i}
                />
              ))}
            </ul>
          )}
        </DebriefPanel>

        <DebriefPanel
          title={t("runs.trajectory")}
          icon="route"
          className="lg:col-span-5 lg:min-h-full"
          bodyClassName="flex flex-col"
        >
          {trajectoryGroups.length === 0 ? (
            <DashedNote>{t("runs.noTrajectory")}</DashedNote>
          ) : (
            <div className="custom-scrollbar flex min-h-0 flex-1 flex-col p-3">
              <div className="relative flex min-h-full flex-1 flex-col">
                <div
                  className="pointer-events-none absolute bottom-3 left-[15px] top-3 w-px bg-outline/60"
                  aria-hidden
                />
                <div className="flex flex-1 flex-col justify-between gap-1">
                  {trajectoryGroups.map((group, i) =>
                    group.kind === "qa" ? (
                      <SurveyTrajectoryQaCard
                        key={`${group.ask.timestamp}-${i}`}
                        ask={group.ask}
                        answer={group.answer}
                        question={
                          questionsById.get(
                            String(group.ask.context?.questionId ?? ""),
                          ) ??
                          questionsById.get(
                            String(group.answer.context?.questionId ?? ""),
                          )
                        }
                      />
                    ) : (
                      <SurveyTrajectoryMilestone
                        key={`${group.event.timestamp}-${i}`}
                        event={group.event}
                      />
                    ),
                  )}
                </div>
              </div>
            </div>
          )}
        </DebriefPanel>
      </div>
    </TrialDebriefChrome>
  );
}

/** One survey answer: visual likert / choice / free-text (not a text dump). */
function SurveyAnswerRow({
  answer,
  question,
  index,
}: {
  answer: SurveyAnswer;
  question: SurveyQuestion | undefined;
  index: number;
}) {
  const { t } = useI18n();
  const type = question?.type;
  const prompt = question?.prompt ?? answer.questionId;
  const conf = answer.confidence;
  const likert = type === "likert";
  const singleChoice = type === "single_choice";
  const typeLabel = surveyQuestionTypeLabel(type, t);
  const typeChipClass = surveyQuestionTypeChipClass(type);

  return (
    <li
      className="px-4 py-4 rise-in hover:bg-surface/30"
      style={{
        animationDelay: `${Math.min(index, 6) * 30}ms`,
        animationFillMode: "backwards",
      }}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <p className="min-w-0 flex-1 text-[15px] font-medium leading-snug text-text-main">
          <span className="text-text-dim">Q{index + 1}</span>
          <span className="text-text-dim"> · </span>
          {prompt}
        </p>
        {type ? (
          <span
            className={`shrink-0 hud rounded border px-1.5 py-0.5 text-[11px] ${typeChipClass}`}
          >
            {typeLabel}
          </span>
        ) : null}
      </div>

      <SurveyAnswerVisual answer={answer} question={question} />

      {answer.rationale ? (
        <p className="mt-3 glass-tile glass-tile--dim rounded-lg px-3 py-2 text-[14px] leading-relaxed text-text-variant">
          {singleChoice || likert ? t("runs.why") : ""}
          {answer.rationale}
          {conf != null && (
            <span className="text-text-dim">
              {" · "}
              {t("runs.howSure", { percent: (conf * 100).toFixed(0) })}
            </span>
          )}
        </p>
      ) : conf != null ? (
        <p className="mt-2 text-[13px] text-text-variant">
          {t("runs.howSure", { percent: (conf * 100).toFixed(0) })}
        </p>
      ) : null}
    </li>
  );
}

function SurveyAnswerVisual({
  answer,
  question,
}: {
  answer: SurveyAnswer;
  question: SurveyQuestion | undefined;
}) {
  const { t } = useI18n();
  const type = question?.type;

  if (type === "likert") {
    const chosen = Number(answer.value);
    const min = question?.minValue ?? 1;
    const max = question?.maxValue ?? 5;
    if (Number.isFinite(chosen) && max >= min && max - min <= 12) {
      const scale = Array.from({ length: max - min + 1 }, (_, i) => min + i);
      const band = scoreBand(chosen / (max || 5));
      const color = SCORE_BAND_CLASS[band];
      return (
        <div>
          <div className="flex flex-wrap items-center gap-2">
            {scale.map((n) => {
              const selected = n === chosen;
              return (
                <span
                  key={n}
                  className={`grid h-9 w-9 place-items-center rounded-full border font-mono text-[14px] ${
                    selected
                      ? `${color.bar} border-transparent font-bold text-on-primary`
                      : "border-outline/60 bg-surface/40 text-text-dim"
                  }`}
                >
                  {n}
                </span>
              );
            })}
            <span
              className={`ml-1 font-mono text-[15px] font-bold tabular-nums ${color.text}`}
            >
              {chosen}/{max}
            </span>
          </div>
        </div>
      );
    }
  }

  if ((type === "single_choice" || type === "multi_choice") && question) {
    const multi = type === "multi_choice";
    const selected = Array.isArray(answer.value)
      ? answer.value.map((v) => String(v))
      : answer.value != null
        ? [String(answer.value)]
        : [];
    const optionDetails =
      question.optionDetails && question.optionDetails.length > 0
        ? question.optionDetails
        : (question.options ?? []).map((option) => ({
            id: option,
            label: option,
          }));

    if (optionDetails.length > 0) {
      return (
        <div className="space-y-1.5">
          {multi ? (
            <p className="hud text-[11px] text-text-dim">
              {t("runs.selected", { count: selected.length })}
            </p>
          ) : null}
          {optionDetails.map((option) => {
            const isSelected = selected.includes(option.id);
            return (
              <div
                key={option.id}
                className={`flex items-start gap-2.5 rounded-lg border px-3 py-2 ${
                  isSelected
                    ? "border-primary/50 bg-primary/10"
                    : "border-outline/25 bg-surface/20 opacity-55"
                }`}
              >
                {multi ? (
                  <span
                    className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-sm border ${
                      isSelected
                        ? "border-primary bg-primary"
                        : "border-outline"
                    }`}
                  >
                    {isSelected ? (
                      <Sym name="check" size={12} className="text-on-primary" />
                    ) : null}
                  </span>
                ) : (
                  <span
                    className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border ${
                      isSelected ? "border-2 border-primary" : "border-outline"
                    }`}
                  >
                    {isSelected ? (
                      <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                    ) : null}
                  </span>
                )}
                <span
                  className={`min-w-0 text-[14px] leading-snug ${
                    isSelected ? "font-medium text-text-main" : "text-text-dim"
                  }`}
                >
                  {option.label || option.id}
                </span>
              </div>
            );
          })}
        </div>
      );
    }
  }

  const fallback = fmtAnswerValue(answer.value, question, t);
  return (
    <p className="glass-tile rounded-lg px-3 py-2 text-[14px] leading-relaxed text-text-main break-words">
      {fallback || t("runs.noAnswer")}
    </p>
  );
}

/** Milestone row for survey_started / survey_completed / unpaired events. */
function SurveyTrajectoryMilestone({
  event,
}: {
  event: SurveyTrajectoryEvent;
}) {
  const { t } = useI18n();
  const action = event.action;
  const outcome = event.outcome ?? {};
  const context = event.context ?? {};
  let title = humanizeToken(action);
  let detail = "";

  if (action === "survey_started") {
    title = t("runs.started");
    const n = context.numQuestions;
    detail =
      typeof n === "number"
        ? t("runs.questionCount", { count: n })
        : String(context.instrumentTitle ?? "");
  } else if (action === "survey_completed") {
    title = t("runs.completed");
    const answered = outcome.numAnswered;
    const valid = outcome.valid;
    const parts: string[] = [];
    if (typeof answered === "number")
      parts.push(t("runs.answered", { count: answered }));
    if (typeof valid === "boolean")
      parts.push(valid ? t("runs.valid") : t("runs.needsReview"));
    detail = parts.join(" · ");
  } else if (action === "ask_question") {
    const index = surveyTrajectoryQuestionIndex(event);
    title = index != null ? `Q${index}` : t("runs.asked");
    detail =
      surveyTrajectoryPrompt(event) ||
      surveyQuestionTypeLabel(surveyTrajectoryQuestionType(event), t);
  } else if (action === "answer_question") {
    const index = surveyTrajectoryQuestionIndex(event);
    title = index != null ? `Q${index}` : t("runs.answeredShort");
    detail = formatSurveyTrajectoryValue(outcome.value, t);
  }

  return (
    <div className="relative flex items-start gap-3 py-1.5 pl-1">
      <span className="relative z-[1] mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full border-2 border-primary bg-surface-lowest" />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[14px] font-semibold text-text-main">
            {title}
          </span>
          {event.timestamp ? (
            <span className="shrink-0 font-mono text-[11px] text-text-dim">
              {compactTimestamp(event.timestamp)}
            </span>
          ) : null}
        </div>
        {detail ? (
          <p className="mt-0.5 text-[14px] leading-snug text-text-variant">
            {detail}
          </p>
        ) : null}
      </div>
    </div>
  );
}

/** Compact timeline step: Qn + selected label (fills column via parent justify-between). */
function SurveyTrajectoryQaCard({
  ask,
  answer,
  question,
}: {
  ask: SurveyTrajectoryEvent;
  answer: SurveyTrajectoryEvent;
  question?: SurveyQuestion;
}) {
  const { t } = useI18n();
  const index =
    surveyTrajectoryQuestionIndex(ask) ?? surveyTrajectoryQuestionIndex(answer);
  const type =
    surveyTrajectoryQuestionType(ask) || surveyTrajectoryQuestionType(answer);
  const valueLabel = fmtAnswerLabel(answer.outcome?.value, question, t);

  return (
    <div className="relative flex items-start gap-3 py-1.5 pl-1">
      <span className="relative z-[1] mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-primary" />
      <div className="min-w-0 flex-1 glass-tile rounded-lg px-2.5 py-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-1.5">
            <span className="hud text-[11px] text-primary">
              {index != null ? `Q${index}` : "Q"}
            </span>
            {type ? (
              <span
                className={`hud rounded border px-1.5 py-0.5 text-[11px] ${surveyQuestionTypeChipClass(type)}`}
              >
                {surveyQuestionTypeLabel(type, t)}
              </span>
            ) : null}
          </div>
          {answer.timestamp ? (
            <span className="shrink-0 font-mono text-[11px] text-text-dim">
              {compactTimestamp(answer.timestamp)}
            </span>
          ) : null}
        </div>
        <p className="mt-1 text-[14px] font-medium leading-snug text-text-main line-clamp-3">
          {valueLabel || t("runs.noAnswer")}
        </p>
      </div>
    </div>
  );
}

function compactTimestamp(value: string): string {
  const match = value.match(/T(\d{2}:\d{2}:\d{2})/);
  return match ? match[1] : value;
}

function fmtAnswerLabel(
  value: unknown,
  question: SurveyQuestion | undefined,
  t: Translate,
): string {
  const optionLabel = (raw: unknown): string => {
    const id = String(raw);
    const detail = question?.optionDetails?.find((option) => option.id === id);
    if (detail?.label) return detail.label;
    return id;
  };
  if (question?.type === "likert") {
    const max = question.maxValue ?? 5;
    return `${value} / ${max}`;
  }
  if (question?.type === "single_choice") return optionLabel(value);
  if (question?.type === "multi_choice" && Array.isArray(value)) {
    return value.map(optionLabel).join(", ");
  }
  return formatSurveyTrajectoryValue(value, t);
}

function fmtAnswerValue(
  value: unknown,
  question: SurveyQuestion | undefined,
  t: Translate,
): string {
  return fmtAnswerLabel(value, question, t);
}

// ===========================================================================
// Web debrief: reads `WebResult` + `WebTrace` (types.ts)
// ===========================================================================

function WebDebrief({ run }: { run: RunDetailView }) {
  const { t } = useI18n();
  const result = run.webResult;
  const persona = run.persona ?? {};
  const trace = runWebTrace(run);
  const events = trace?.events ?? [];
  const feedback = resolveUserFeedback(run);

  if (!result) {
    return (
      <TrialDebriefChrome
        prompts={run.prompts}
        persona={persona}
        instructionMarkdown={run.instructionMarkdown}
        contextMarkdown={run.contextMarkdown}
        questionnaireMarkdown={run.questionnaireMarkdown}
        outputSchemaMarkdown={run.outputSchemaMarkdown}
      >
        <DebriefPanel>
          <DashedNote>{t("runs.noWebResult")}</DashedNote>
        </DebriefPanel>
      </TrialDebriefChrome>
    );
  }

  return (
    <TrialDebriefChrome
      prompts={run.prompts}
      persona={persona}
      instructionMarkdown={run.instructionMarkdown}
      contextMarkdown={run.contextMarkdown}
      questionnaireMarkdown={run.questionnaireMarkdown}
      outputSchemaMarkdown={run.outputSchemaMarkdown}
    >
      <DebriefPanel bodyClassName="p-4">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:col-span-5">
            <StatTile
              lead
              caption={t("runs.metPersonaNeed")}
              value={result.needSatisfaction}
              unit="/10"
              band={scoreBand(result.needSatisfaction / 10)}
            />
            <StatTile
              caption={t("runs.easeOfUse")}
              value={result.easeOfUse}
              unit="/10"
              band={scoreBand(result.easeOfUse / 10)}
            />
            <StatTile
              caption={t("runs.overallExperience")}
              value={result.overallExperienceRating}
              unit="/10"
              band={scoreBand(result.overallExperienceRating / 10)}
            />
          </div>

          <div className="flex items-center gap-4 rounded-lg glass-tile p-4 backdrop-blur-sm lg:col-span-7">
            <div
              className="grid h-12 w-12 shrink-0 place-items-center glass-tile rounded-lg"
              aria-hidden
            >
              <Sym name="inventory_2" size={22} className="text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[14px] font-semibold text-text-main">
                  {result.selectedProductName || t("runs.noProductChosen")}
                </span>
                <ValidityBadge
                  valid={result.valid}
                  validLabel={t("runs.validPick")}
                  invalidLabel={t("runs.invalidPick")}
                />
              </div>
              {result.selectedProductId && (
                <div className="mt-0.5 font-mono text-[12px] text-text-dim">
                  {result.selectedProductId}
                </div>
              )}
              {result.reason && (
                <p className="mt-1 text-[14px] leading-snug text-text-variant">
                  {t("runs.whyThisOne")}
                  {result.reason}
                </p>
              )}
            </div>
          </div>
        </div>
      </DebriefPanel>

      <UserFeedbackPanel feedback={feedback} />

      <DebriefPanel
        title={t("runs.browserTrace", { count: events.length })}
        icon="route"
      >
        {!trace || events.length === 0 ? (
          <DashedNote>{t("runs.noBrowserSteps")}</DashedNote>
        ) : (
          <div className="p-4">
            <HarborTraceReplay trace={trace} />
          </div>
        )}
      </DebriefPanel>
    </TrialDebriefChrome>
  );
}

// ===========================================================================
// OS app debrief
// ===========================================================================

function TrialDecisionPanel({
  trialEvaluation,
}: {
  trialEvaluation?: TrialEvaluationArtifact | null;
}) {
  const { t } = useI18n();
  if (!trialEvaluation) return null;

  const ignoredTypes = new Set([
    "task_outcome",
    "user_feedback",
    "feedback",
    "persona_alignment",
  ]);
  const contexts = trialEvaluation.contexts.filter(
    (c) => c.contextType && !ignoredTypes.has(c.contextType),
  );
  if (contexts.length === 0) return null;

  return (
    <DebriefPanel
      title={t("runs.taskOutput")}
      icon="analytics"
      bodyClassName="p-4"
    >
      <div className="space-y-4">
        {contexts.map((ctx) => (
          <div
            key={ctx.key}
            className="rounded-lg glass-tile p-3 backdrop-blur-sm"
          >
            <div className="flex items-center gap-2 text-[12px] font-medium uppercase tracking-wide text-text-dim">
              {ctx.label}
            </div>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {ctx.facets
                .filter((f) => f.value != null && f.value !== "")
                .map((f) => (
                  <div key={f.key}>
                    <div className="text-[11px] text-text-dim">{f.label}</div>
                    <div
                      className={`mt-0.5 text-[14px] leading-relaxed ${
                        f.role === "explanation"
                          ? "col-span-full text-text-variant"
                          : f.role === "primary"
                            ? "font-semibold text-text-main"
                            : "text-text-main"
                      }`}
                    >
                      {String(f.value)}
                    </div>
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>
    </DebriefPanel>
  );
}

function OsAppDebrief({ run }: { run: RunDetailView }) {
  const { t } = useI18n();
  const runRecord = run as Record<string, unknown>;
  const osAppResult =
    (runRecord.osAppResult as OsAppResult | null | undefined) ?? null;
  const trace = (runRecord.osAppTrace ??
    run.webTrace ??
    run.trace ??
    null) as WebTrace | null;
  const events = trace?.events ?? [];
  const feedback = resolveUserFeedback(run);

  return (
    <TrialDebriefChrome
      prompts={run.prompts}
      persona={run.persona}
      instructionMarkdown={run.instructionMarkdown}
      contextMarkdown={run.contextMarkdown}
      questionnaireMarkdown={run.questionnaireMarkdown}
      outputSchemaMarkdown={run.outputSchemaMarkdown}
    >
      <DebriefPanel
        title={t("runs.evaluation")}
        icon="verified"
        bodyClassName="p-4"
      >
        <OsAppEvalScorecard
          osAppResult={osAppResult}
          verifier={run.verifier ?? null}
          traceStepCount={events.length}
          phase="done"
        />
      </DebriefPanel>
      <TrialDecisionPanel trialEvaluation={run.trialEvaluation} />
      <UserFeedbackPanel feedback={feedback} />
      <DebriefPanel
        title={t("runs.desktopTrace", { count: events.length })}
        icon="route"
      >
        {events.length === 0 ? (
          <DashedNote>{t("runs.noDesktopSteps")}</DashedNote>
        ) : (
          <div className="p-4">
            <HarborTraceReplay trace={trace!} />
          </div>
        )}
      </DebriefPanel>
    </TrialDebriefChrome>
  );
}

// ===========================================================================
// States
// ===========================================================================

function DetailLoading() {
  return (
    <div className="space-y-5" aria-hidden>
      <div className="glass-panel h-14 animate-rb-pulse rounded-xl" />
      <div className="glass-panel h-28 animate-rb-pulse rounded-xl" />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="glass-panel h-80 animate-rb-pulse rounded-xl lg:col-span-7" />
        <div className="glass-panel h-80 animate-rb-pulse rounded-xl lg:col-span-5" />
      </div>
    </div>
  );
}

function DetailNotFound() {
  const { t } = useI18n();
  return (
    <StudioGlassPanel className="px-6 py-14 text-center rise-in">
      <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-md glass-tile">
        <Sym name="search_off" size={26} className="text-text-dim" />
      </div>
      <h2 className="font-display text-[15px] font-semibold text-text-main">
        {t("runs.notFoundTitle")}
      </h2>
      <p className="mx-auto mt-2 max-w-sm text-[15px] leading-relaxed text-text-variant">
        {t("runs.notFoundDescription")}
      </p>
    </StudioGlassPanel>
  );
}

function DetailError({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry: () => void;
}) {
  const { t } = useI18n();
  const notFound = error instanceof ApiError && error.status === 404;
  if (notFound) return <DetailNotFound />;
  const message =
    error instanceof ApiError
      ? error.message
      : t("runs.detailLoadErrorMessage");
  return (
    <StudioGlassPanel className="border-l-4 border-l-danger px-5 py-8 text-center rise-in">
      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-md bg-danger/10">
        <Sym name="error" fill={1} size={22} className="text-danger" />
      </div>
      <h2 className="font-display text-[15px] font-semibold text-text-main">
        {t("runs.detailLoadErrorTitle")}
      </h2>
      <p className="mx-auto mt-1.5 max-w-md break-words text-[15px] leading-relaxed text-text-variant">
        {message}
      </p>
      <button
        type="button"
        onClick={onRetry}
        className={`mt-4 inline-flex items-center gap-1.5 rounded-md bg-danger/10 px-4 py-2 text-[14px] text-danger transition ease-out hover:bg-danger/20 active:scale-[0.97] ${FOCUS_RING}`}
      >
        <Sym name="refresh" size={16} />
        {t("runs.tryAgain")}
      </button>
    </StudioGlassPanel>
  );
}

export default RunDetail;
