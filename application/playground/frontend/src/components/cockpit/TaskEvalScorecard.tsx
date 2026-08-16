/**
 * TaskEvalScorecard: Evaluation inspector panels for Survey, Web, and CUA runs.
 *
 * Mirrors the chat Scorecard layout (overall score + quote + criterion rows +
 * Harbor verifier strip) using each task type's debrief payload.
 */
import type { ReactNode } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { SCORE_BAND_CLASS, Sym, scoreBand } from "./cockpitShared";
import { countSurveyQuestionTypes, surveyQuestionTypeChipClass } from "@/lib/surveyDisplay";
import type { HarborCockpitPhase } from "@/lib/useHarborCockpitRun";
import type { OsAppResult, SurveyResult, VerifierSummary, WebResult } from "@/lib/types";

export type TaskEvalPhase = HarborCockpitPhase;

function clamp(value: number, max: number): number {
  if (Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(max, value));
}

function runningPhase(phase: TaskEvalPhase): boolean {
  return phase === "launching" || phase === "running";
}

function failedPhase(phase: TaskEvalPhase): boolean {
  return phase === "error" || phase === "timeout";
}

function ScorecardShell({
  scored,
  children,
}: {
  scored: boolean;
  children: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <div className="p-md">
      <div className="panel rise-in overflow-hidden rounded-md border border-outline bg-surface-lowest">
        <div className="flex items-center justify-between border-b border-outline bg-surface-low px-3 py-2.5">
          <div className="flex items-center gap-2">
            <Sym name="verified" fill={1} size={18} className="text-primary" />
            <h3 className="hud text-[13px] text-primary">{t("taskScorecard.title")}</h3>
          </div>
          {scored ? (
            <span className="flex items-center gap-1 hud text-[12px] text-text-dim">
              <span className="h-2 w-2 rounded-full bg-secondary" aria-hidden />
              {t("taskScorecard.scored")}
            </span>
          ) : null}
        </div>
        <div className="p-3">{children}</div>
      </div>
    </div>
  );
}

function ScorecardSkeleton() {
  return (
    <div className="p-md" aria-hidden>
      <div className="rise-in overflow-hidden rounded-md border border-outline bg-surface-lowest">
        <div className="border-b border-outline bg-surface-low px-3 py-2.5">
          <div className="h-4 w-28 animate-rb-pulse rounded bg-surface-high" />
        </div>
        <div className="space-y-3 p-3">
          <div className="flex items-center gap-3">
            <div className="h-10 w-14 animate-rb-pulse rounded bg-surface-high" />
            <div className="h-10 flex-1 animate-rb-pulse rounded bg-surface-high" />
          </div>
          <div className="h-8 w-full animate-rb-pulse rounded bg-surface-high" />
          <div className="h-8 w-full animate-rb-pulse rounded bg-surface-high" />
        </div>
      </div>
    </div>
  );
}

function EmptyScorecard({ phase }: { phase: TaskEvalPhase }) {
  const { t } = useI18n();
  return (
    <div className="p-md">
      <div className="rise-in rounded-md border border-dashed border-outline-dim bg-surface-low px-4 py-10 text-center">
        <Sym name="fact_check" size={28} className="text-text-dim" />
        <p className="mt-2 text-[15px] leading-relaxed text-text-variant">
          {failedPhase(phase)
            ? t("taskScorecard.empty.failed")
            : t("taskScorecard.empty.ready")}
        </p>
      </div>
    </div>
  );
}

function CriterionRow({
  label,
  score,
  max,
  rationale,
}: {
  label: string;
  score: number;
  max: number;
  rationale?: string | null;
}) {
  const value = clamp(score, max);
  const band = scoreBand(value / max);
  const color = SCORE_BAND_CLASS[band];
  const pct = (value / max) * 100;
  const passing = band === "high";

  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-[14px] font-medium text-text-main">
          <Sym
            name={passing ? "check_circle" : band === "low" ? "cancel" : "remove_circle"}
            fill={1}
            size={16}
            className={color.text}
          />
          {label}
        </span>
        <span className={`font-mono text-[14px] font-bold tabular-nums ${color.text}`}>
          {value} / {max}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-field">
        <div className={`h-full rounded-full transition-[width] duration-200 ${color.bar}`} style={{ width: `${pct}%` }} />
      </div>
      {rationale ? <p className="mt-1 text-[13px] leading-snug text-text-variant">{rationale}</p> : null}
    </div>
  );
}

export function VerifierStrip({ verifier }: { verifier: VerifierSummary }) {
  const { t } = useI18n();
  const passed = verifier.passed;
  return (
    <div
      className={`mt-3 rounded-md px-3 py-2 ${
        passed ? "bg-secondary/10" : "bg-danger/10"
      }`}
    >
      <div className="flex items-center gap-2">
        <Sym name={passed ? "task_alt" : "error"} fill={1} size={18} className={passed ? "text-secondary" : "text-danger"} />
        <span className="text-[14px] font-semibold text-text-main">
          {t("taskScorecard.verifierStatus", {
            status: passed ? t("taskScorecard.passed") : t("taskScorecard.failed"),
          })}
        </span>
        <span className="ml-auto font-mono text-[13px] tabular-nums text-text-variant">
          {t("taskScorecard.reward", { reward: verifier.reward })}
        </span>
      </div>
      {verifier.detail ? (
        <pre className="custom-scrollbar mt-2 max-h-28 overflow-auto whitespace-pre-wrap font-mono text-[12px] leading-snug text-text-variant">
          {verifier.detail}
        </pre>
      ) : null}
    </div>
  );
}

function MetricTile({ value, caption }: { value: string; caption: string }) {
  return (
    <div className="glass-tile flex flex-col items-center justify-center rounded-md py-2.5">
      <span className="font-display text-[22px] font-bold tabular-nums text-text-main">{value}</span>
      <span className="mt-0.5 text-center hud text-[12px] leading-tight text-text-dim">{caption}</span>
    </div>
  );
}

export interface WebEvalScorecardProps {
  webResult: WebResult | null;
  verifier?: VerifierSummary | null;
  phase: TaskEvalPhase;
}

export function WebEvalScorecard({ webResult, verifier, phase }: WebEvalScorecardProps) {
  const { rich, t } = useI18n();
  if (runningPhase(phase) && !webResult) return <ScorecardSkeleton />;
  if (!webResult) return <EmptyScorecard phase={phase} />;

  const overall = clamp(webResult.overallExperienceRating, 10);
  const overallBand = scoreBand(overall / 10);
  const overallColor = SCORE_BAND_CLASS[overallBand];
  const overallBorder =
    overallBand === "high"
      ? "border-l-score-high"
      : overallBand === "mid"
        ? "border-l-score-mid"
        : overallBand === "low"
          ? "border-l-score-low"
          : "border-l-outline";

  return (
    <ScorecardShell scored>
      <div className="mb-3 flex items-start gap-3">
        <div className="flex flex-shrink-0 flex-col items-center">
          <div className="flex items-baseline gap-0.5" aria-label={t("taskScorecard.web.overallAria", { overall })}>
            <span className={`font-display text-[44px] font-bold leading-none tracking-tight tabular-nums ${overallColor.text}`}>
              {overall}
            </span>
            <span className="text-[15px] text-text-dim">/ 10</span>
          </div>
          <span className="mt-1 text-center hud text-[12px] text-text-dim">{t("taskScorecard.web.userRated")}</span>
        </div>
        {webResult.reason ? (
          <div className={`flex-1 border-l-2 pl-3 ${overallBorder}`}>
            <p className="text-[14px] italic leading-relaxed text-text-variant">&ldquo;{webResult.reason}&rdquo;</p>
          </div>
        ) : null}
      </div>

      <div className="mb-3 space-y-2.5">
        <CriterionRow
          label={t("taskScorecard.web.meetsNeed")}
          score={webResult.needSatisfaction}
          max={10}
          rationale={webResult.reason}
        />
        <CriterionRow label={t("taskScorecard.web.easyToUse")} score={webResult.easeOfUse} max={10} />
      </div>

      <div className="glass-tile flex items-start gap-3 rounded-md px-3 py-2.5">
        <div className="glass-tile grid h-10 w-10 shrink-0 place-items-center rounded">
          <Sym name="inventory_2" size={20} className="text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[15px] font-semibold text-text-main">{webResult.selectedProductName}</span>
            <span
              className={`hud rounded px-1.5 py-0.5 text-[11px] ${
                webResult.valid ? "bg-secondary/10 text-secondary" : "bg-danger/10 text-danger"
              }`}
            >
              {webResult.valid ? t("taskScorecard.complete") : t("taskScorecard.incomplete")}
            </span>
          </div>
          <div className="mt-0.5 truncate font-mono text-[12px] text-text-variant">{webResult.selectedProductId}</div>
        </div>
      </div>

      {verifier ? <VerifierStrip verifier={verifier} /> : null}

      <p className="mt-3 text-[12px] leading-relaxed text-text-dim">
        {rich("taskScorecard.web.scaleLegend", {
          green: (chunks) => <span className="text-secondary">{chunks}</span>,
          amber: (chunks) => <span className="text-warn">{chunks}</span>,
          red: (chunks) => <span className="text-danger">{chunks}</span>,
        })}
      </p>
    </ScorecardShell>
  );
}

export interface SurveyEvalScorecardProps {
  surveyResult: SurveyResult | null;
  verifier?: VerifierSummary | null;
  phase: TaskEvalPhase;
}

export function SurveyEvalScorecard({ surveyResult, verifier, phase }: SurveyEvalScorecardProps) {
  const { t } = useI18n();
  if (runningPhase(phase) && !surveyResult) return <ScorecardSkeleton />;
  if (!surveyResult?.completion) return <EmptyScorecard phase={phase} />;

  const { completion } = surveyResult;
  const total = completion.numQuestions || completion.total || 0;
  const answered = completion.numAnswered || completion.answered || surveyResult.answers.length;
  const pct = total > 0 ? Math.round((answered / total) * 100) : 0;
  const mainBand = scoreBand(pct / 100);
  const mainColor = SCORE_BAND_CLASS[mainBand];
  const typeCounts = countSurveyQuestionTypes(surveyResult.instrument?.questions, t);

  return (
    <ScorecardShell scored={phase === "done"}>
      <div className="mb-3 flex items-start gap-3">
        <div className="flex flex-shrink-0 flex-col items-center">
          <div className="flex items-baseline gap-0.5">
            <span className={`font-display text-[44px] font-bold leading-none tracking-tight tabular-nums ${mainColor.text}`}>
              {pct}
            </span>
            <span className="text-[15px] text-text-dim">/ 100</span>
          </div>
          <span className="mt-1 text-center hud text-[12px] text-text-dim">{t("taskScorecard.survey.completion")}</span>
        </div>
        <div className="flex-1 border-l-2 border-l-outline pl-3">
          <p className="text-[14px] leading-relaxed text-text-variant">
            {completion.valid
              ? t("taskScorecard.survey.completionValid", { answered, total })
              : t("taskScorecard.survey.completionInvalid", { answered, total })}
          </p>
        </div>
      </div>

      <div className="mb-3 space-y-2.5">
        <CriterionRow
          label={t("taskScorecard.survey.finishedQuestionnaire")}
          score={total > 0 ? (answered / total) * 5 : 0}
          max={5}
        />
        <CriterionRow
          label={t("taskScorecard.survey.answersValid")}
          score={completion.valid ? 5 : 1}
          max={5}
        />
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2">
        <MetricTile value={`${answered}/${total}`} caption={t("taskScorecard.survey.answered")} />
        <MetricTile
          value={completion.valid ? t("taskScorecard.yes") : t("taskScorecard.no")}
          caption={t("taskScorecard.survey.valid")}
        />
      </div>

      {typeCounts.length > 0 ? (
        <div className="mb-3 rounded border border-outline bg-surface-low px-3 py-2.5">
          <div className="hud mb-1.5 text-[11px] text-text-dim">{t("taskScorecard.survey.questionTypes")}</div>
          <div className="flex flex-wrap gap-1.5">
            {typeCounts.map((entry) => (
              <span
                key={entry.type}
                className={`hud inline-flex items-center gap-1 rounded border px-2 py-1 text-[11px] ${surveyQuestionTypeChipClass(entry.type)}`}
              >
                <span className="tabular-nums font-semibold">{entry.count}</span>
                {entry.label}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {verifier ? <VerifierStrip verifier={verifier} /> : null}
    </ScorecardShell>
  );
}

export interface OsAppEvalScorecardProps {
  osAppResult: OsAppResult | null;
  verifier?: VerifierSummary | null;
  traceStepCount?: number;
  phase: TaskEvalPhase;
}

export function OsAppEvalScorecard({ osAppResult, verifier, traceStepCount = 0, phase }: OsAppEvalScorecardProps) {
  const { t } = useI18n();
  if (runningPhase(phase) && !osAppResult) return <ScorecardSkeleton />;
  if (!osAppResult) return <EmptyScorecard phase={phase} />;

  const passed = osAppResult.success;
  const rawScore = osAppResult.score;
  const reward =
    (rawScore != null && rawScore > 0)
      ? rawScore
      : (verifier?.reward != null && verifier.reward > 0)
        ? verifier.reward
        : (passed ? 1 : 0);
  const band = passed ? "high" : "low";
  const color = SCORE_BAND_CLASS[band];
  const displayReward = reward >= 0 && reward <= 1 ? `${Math.round(reward * 100)}%` : String(reward);

  return (
    <ScorecardShell scored>
      <div className="mb-3 flex items-start gap-3">
        <div className="flex flex-shrink-0 flex-col items-center">
          <div className="flex items-baseline gap-0.5">
            <span className={`font-display text-[44px] font-bold leading-none tracking-tight tabular-nums ${color.text}`}>
              {displayReward}
            </span>
          </div>
          <span className="mt-1 text-center hud text-[12px] text-text-dim">{t("taskScorecard.os.verifierReward")}</span>
        </div>
        <div className={`flex-1 border-l-2 pl-3 ${passed ? "border-l-score-high" : "border-l-score-low"}`}>
          <p className="text-[14px] leading-relaxed text-text-variant">
            {passed
              ? t("taskScorecard.os.accepted")
              : t("taskScorecard.os.notAccepted")}
          </p>
        </div>
      </div>

      <div className="mb-3 space-y-2.5">
        <CriterionRow label={t("taskScorecard.os.taskSucceeded")} score={passed ? 5 : 0} max={5} />
        <CriterionRow
          label={t("taskScorecard.os.rewardScore")}
          score={reward <= 1 ? reward * 5 : clamp(reward, 5)}
          max={5}
        />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <MetricTile
          value={passed ? t("taskScorecard.pass") : t("taskScorecard.fail")}
          caption={t("taskScorecard.os.verifier")}
        />
        <MetricTile value={String(traceStepCount)} caption={t("taskScorecard.os.traceSteps")} />
      </div>

      {osAppResult.artifactName ? (
        <div className="mt-3 flex items-center gap-2 rounded-md border border-outline bg-surface px-3 py-2 text-[13px] text-text-variant">
          <Sym name="description" size={16} className="text-primary" />
          {t("taskScorecard.os.outputArtifact")} ·{" "}
          <span className="font-mono text-text-main">{osAppResult.artifactName}</span>
        </div>
      ) : null}

      {verifier?.detail ? <VerifierStrip verifier={verifier} /> : null}
    </ScorecardShell>
  );
}
