/**
 * RatingChip: the scannable signature of the Runs surface.
 *
 * A compact mono chip that bands an overall 1-10 rating by colour on the
 * red→amber→green evaluation score scale (the same scale the cockpit scorecard
 * uses, never the indigo accent). The colour is ALWAYS paired with the number,
 * and the rest of the Runs list stays deliberately calm so the eye lands here.
 *
 *   rating >= 7  → high (green)
 *   4 .. 6       → mid  (amber)
 *   rating <= 3  → low  (red)
 *   null         → "-"  (muted, quiet)
 *
 * The value is mono with a faint "/10" suffix; `tabular-nums` keeps a column of
 * chips aligned.
 */
import { SCORE_BAND_CLASS, scoreBand } from "./cockpit/cockpitShared";
import { useI18n } from "../i18n/I18nProvider";

export interface RatingChipProps {
  rating: number | null | undefined;
  /** Slightly larger chip for detail/compare headers. */
  size?: "sm" | "md";
  className?: string;
}

export function RatingChip({ rating, size = "sm", className = "" }: RatingChipProps) {
  const { t } = useI18n();
  // Band on the normalized [0,1] scale so the chip shares the scorecard's bands.
  const band = scoreBand(
    rating === null || rating === undefined || Number.isNaN(rating) ? null : rating / 10,
  );
  const color = SCORE_BAND_CLASS[band];
  const pad = size === "md" ? "px-2.5 py-1 text-[15px]" : "px-2 py-0.5 text-[13px]";

  if (band === "none") {
    return (
      <span
        className={`inline-flex items-center whitespace-nowrap rounded-md border border-outline bg-surface-high font-mono tabular-nums text-text-dim ${pad} ${className}`}
        title={t("runs.notScored", "Not scored")}
        aria-label={t("runs.noRating", "No rating")}
      >
        -
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-baseline whitespace-nowrap rounded-md font-mono font-semibold tabular-nums ${color.text} ${color.soft} ${pad} ${className}`}
      aria-label={t("runs.ratingAria", "Rating {rating} out of 10", { rating: rating ?? 0 })}
    >
      {rating}
      <span className="ml-px text-[0.82em] font-medium opacity-70">/10</span>
    </span>
  );
}

export default RatingChip;
