/**
 * Scorecard: the cockpit's Evaluation inspector panel.
 *
 * Ports the mockup's evaluation card: a large overall rating beside the
 * persona's self-rating quote, per-criterion rows (constraint / preference
 * satisfaction) with threshold-coloured bars + rationale, the clarifying-
 * questions line, and a run-metrics strip.
 *
 * Honest scoring rules (acceptance criteria):
 *   - the overall number is rendered on the red→amber→green score scale, never
 *     the indigo accent, and the colour is ALWAYS paired with the number;
 *   - each criterion bar + score share the same band colour;
 *   - metrics show only what's tracked (turns / items); no tokens or cost.
 *
 * States: a skeleton while a run is in progress, and a plain teaching empty
 * state before any run / when a run finished without an evaluation.
 */
import type { ReactNode } from "react";

import { SCORE_BAND_CLASS, Sym, scoreBand } from "./cockpitShared";
import { useI18n } from "@/i18n/I18nProvider";
import type { PlaygroundMetricScores, PlaygroundQuestionnaire } from "@/lib/types";
import type { PlaygroundRunPhase } from "@/lib/usePlayground";

export interface ScorecardProps {
  questionnaire: PlaygroundQuestionnaire | null;
  metrics: PlaygroundMetricScores | null;
  phase: PlaygroundRunPhase;
}

/** Clamp a raw score into [0, max]. */
function clamp(value: number, max: number): number {
  if (Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(max, value));
}

export function Scorecard({ questionnaire, metrics, phase }: ScorecardProps) {
  const { rich, t } = useI18n();
  const running = phase === "building" || phase === "running";

  if (running && !questionnaire) return <ScorecardSkeleton />;

  if (!questionnaire || !metrics) {
    return (
      <div className="p-md">
        <div className="rise-in rounded-md border border-dashed border-outline-dim bg-surface-low px-4 py-10 text-center">
          <Sym name="fact_check" size={28} className="text-text-dim" />
          <p className="mt-2 text-[15px] leading-relaxed text-text-variant">
            {phase === "error" || phase === "timeout"
              ? t("scorecards.empty.failed")
              : t("scorecards.empty.ready")}
          </p>
        </div>
      </div>
    );
  }

  const overall = clamp(questionnaire.overallRating, 10);
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
    <div className="p-md">
      <div className="panel rise-in overflow-hidden rounded-md border border-outline bg-surface-lowest">
        {/* Card header */}
        <div className="flex items-center justify-between border-b border-outline bg-surface-low px-3 py-2.5">
          <div className="flex items-center gap-2">
            <Sym name="verified" fill={1} size={18} className="text-primary" />
            <h3 className="hud text-[13px] text-primary">{t("scorecards.header")}</h3>
          </div>
          <span className="flex items-center gap-1 hud text-[12px] text-text-dim">
            <span className="h-2 w-2 rounded-full bg-secondary" aria-hidden />
            {t("scorecards.scored")}
          </span>
        </div>

        <div className="p-3">
          {/* Overall score + quote */}
          <div className="mb-3 flex items-start gap-3">
            <div className="flex flex-shrink-0 flex-col items-center">
              <div className="flex items-baseline gap-0.5" aria-label={t("scorecards.aria.overallRating", { overall, max: 10 })}>
                <span className={`font-display text-[44px] font-bold leading-none tracking-tight tabular-nums ${overallColor.text}`}>
                  {overall}
                </span>
                <span className="text-[15px] text-text-dim">{t("scorecards.outOf", { max: 10 })}</span>
              </div>
              <span className="mt-1 text-center hud text-[12px] text-text-dim">
                {t("scorecards.rating.userRated")}
              </span>
            </div>
            {questionnaire.ratingReason && (
              <div className={`flex-1 border-l-2 pl-3 ${overallBorder}`}>
                <p className="text-[14px] italic leading-relaxed text-text-variant">
                  &ldquo;{questionnaire.ratingReason}&rdquo;
                </p>
              </div>
            )}
          </div>

          {/* Criterion rows — only fields that were actually authored */}
          <div className="mb-3 space-y-2.5">
            {(questionnaire.constraintSatisfaction ?? 0) > 0 ? (
              <CriterionRow
                label={t("scorecards.criteria.mustHaves")}
                score={questionnaire.constraintSatisfaction}
                max={5}
                rationale={questionnaire.constraintRationale}
              />
            ) : null}
            {(questionnaire.preferenceSatisfaction ?? 0) > 0 ? (
              <CriterionRow
                label={t("scorecards.criteria.tastes")}
                score={questionnaire.preferenceSatisfaction}
                max={5}
                rationale={questionnaire.preferenceRationale}
              />
            ) : null}
          </div>

          {/* Clarifying questions line */}
          {questionnaire.askedUsefulClarifyingQuestions || questionnaire.clarifyingNotes ? (
            <ClarifyingLine
              asked={questionnaire.askedUsefulClarifyingQuestions}
              notes={questionnaire.clarifyingNotes}
            />
          ) : null}
          {/* Metrics strip: real counts only (no tokens / cost). */}
          <div className="mt-3 grid grid-cols-1 gap-2">
            <MetricTile value={String(metrics.numTurns)} caption={t("scorecards.metrics.totalTurns")} />
          </div>

          {/* Scale hint: what the colours mean. */}
          <p className="mt-3 text-[12px] leading-relaxed text-text-dim">
            {rich("scorecards.scale.legend", {
              green: (chunks) => <span className="text-secondary">{chunks}</span>,
              amber: (chunks) => <span className="text-warn">{chunks}</span>,
              red: (chunks) => <span className="text-danger">{chunks}</span>,
            })}
          </p>
        </div>
      </div>
    </div>
  );
}

/** One criterion: name + score + threshold-coloured bar + rationale. */
function CriterionRow({
  label,
  score,
  max,
  rationale,
}: {
  label: string;
  score: number;
  max: number;
  rationale: string;
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
      {rationale && <p className="mt-1 text-[13px] leading-snug text-text-variant">{rationale}</p>}
    </div>
  );
}

/** The clarifying-questions callout (mint when useful, neutral when not). */
function ClarifyingLine({ asked, notes }: { asked: boolean; notes: string }) {
  const { rich } = useI18n();
  const values = {
    label: (chunks: ReactNode) => <span className="font-semibold">{chunks}</span>,
    notes,
  };
  const message = asked
    ? notes
      ? rich("scorecards.followUp.askedWithNotes", values)
      : rich("scorecards.followUp.asked", values)
    : notes
      ? rich("scorecards.followUp.notAskedWithNotes", values)
      : rich("scorecards.followUp.notAsked", values);

  return (
    <div
      className={`flex items-start gap-2 rounded-md px-3 py-2 ${
        asked ? "bg-secondary/10" : "glass-tile glass-tile--dim text-text-dim"
      }`}
    >
      <Sym
        name={asked ? "help" : "help_outline"}
        fill={asked ? 1 : 0}
        size={18}
        className={`mt-0.5 ${asked ? "text-secondary" : "text-text-dim"}`}
      />
      <span className="text-[14px] text-text-main">
        {message}
      </span>
    </div>
  );
}

/** A compact metric tile (big value + caption). */
function MetricTile({ value, caption }: { value: string; caption: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-md border border-outline bg-surface py-2.5">
      <span className="font-display text-[22px] font-bold tabular-nums text-text-main">{value}</span>
      <span className="mt-0.5 text-center hud text-[12px] leading-tight text-text-dim">
        {caption}
      </span>
    </div>
  );
}

/** A skeleton scorecard shown while a run is in progress. */
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
          <div className="grid grid-cols-3 gap-2">
            <div className="h-14 animate-rb-pulse rounded-md bg-surface-high" />
            <div className="h-14 animate-rb-pulse rounded-md bg-surface-high" />
            <div className="h-14 animate-rb-pulse rounded-md bg-surface-high" />
          </div>
        </div>
      </div>
    </div>
  );
}

export default Scorecard;
