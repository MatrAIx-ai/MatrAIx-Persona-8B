import { FOCUS_RING, Sym } from "../cockpitShared";
import { useI18n } from "@/i18n/I18nProvider";
import { CockpitInlineCount } from "./CockpitCountField";

export type RunLaunchPhase = "idle" | "launching" | "running" | "done" | "error";

export interface RunLaunchBarProps {
  canRun: boolean;
  isBatch: boolean;
  personaCount: number;
  parallelTrials: number;
  onParallelTrialsChange: (value: number) => void;
  isRunning: boolean;
  onRun: () => void;
  error?: string | null;
  /** When set, replaces the run button with a progress bar. */
  runPhase?: RunLaunchPhase;
  progressPct?: number;
  progressLabel?: string;
  progressSublabel?: string;
  onNewRun?: () => void;
  onViewJob?: () => void;
  onCancelRun?: () => void;
  cancelRunBusy?: boolean;
  onDownload?: () => void;
  canDownload?: boolean;
  /** Re-run only the failed trials in-place (batch only). */
  onRetryFailed?: () => void;
  failedCount?: number;
  retryBusy?: boolean;
  /** When the live panel already shows a failure card, keep the bar to actions only. */
  compactOnFailure?: boolean;
}

export function RunLaunchBar({
  canRun,
  isBatch,
  personaCount,
  parallelTrials,
  onParallelTrialsChange,
  isRunning,
  onRun,
  error,
  runPhase = "idle",
  progressPct = 0,
  progressLabel,
  progressSublabel,
  onNewRun,
  onViewJob,
  onCancelRun,
  cancelRunBusy = false,
  onDownload,
  canDownload = false,
  onRetryFailed,
  failedCount = 0,
  retryBusy = false,
}: RunLaunchBarProps) {
  const { t } = useI18n();
  const active = runPhase !== "idle";
  const failed = runPhase === "error";
  const done = runPhase === "done";
  const pct = Math.max(0, Math.min(100, progressPct));
  const parallelMax = Math.max(1, personaCount);

  return (
    <div className="glass-panel-strong w-full shrink-0 rounded-xl px-4 py-3 sm:px-5">
      {error && (
        <p className="mb-2 w-full rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-[13px] text-danger">
          {error}
        </p>
      )}

      {active ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5">
            <div className="flex min-w-0 flex-1 items-center gap-2.5">
              {failed ? (
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-danger/12">
                  <Sym name="error" fill={1} size={18} className="text-danger" />
                </span>
              ) : done ? (
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary/12">
                  <Sym name="check_circle" fill={1} size={18} className="text-secondary" />
                </span>
              ) : (
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
                  <Sym name="autorenew" size={18} className="animate-rb-spin text-primary" />
                </span>
              )}
              <div className="min-w-0">
                <p className="truncate font-display text-[15px] font-semibold leading-tight text-text-main">
                  {progressLabel ?? (isBatch
                    ? t("setup.run.batch", "Batch run")
                    : t("setup.run.running", "Running simulation"))}
                </p>
                {progressSublabel && (
                  <p className="mt-0.5 truncate text-[12px] text-text-dim">{progressSublabel}</p>
                )}
              </div>
            </div>

            <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
              {onCancelRun && !done && !failed && (
                <button
                  type="button"
                  onClick={onCancelRun}
                  disabled={cancelRunBusy}
                  className={`inline-flex items-center gap-1.5 rounded-lg border border-danger/35 bg-danger/8 px-3.5 py-2 text-[14px] font-medium text-danger transition hover:border-danger/50 hover:bg-danger/14 active:scale-[0.98] disabled:opacity-50 ${FOCUS_RING}`}
                >
                  <Sym name="stop_circle" size={16} />
                  {cancelRunBusy
                    ? t("setup.run.stopping", "Stopping…")
                    : isBatch
                      ? t("setup.run.stopBatch", "Stop batch")
                      : t("setup.run.stopRun", "Stop run")}
                </button>
              )}
              {onRetryFailed && isBatch && (done || failed) && failedCount > 0 && (
                <button
                  type="button"
                  onClick={onRetryFailed}
                  disabled={retryBusy}
                  className={`inline-flex items-center gap-1.5 rounded-lg border border-[#e5c07b]/45 bg-[#e5c07b]/10 px-3.5 py-2 text-[14px] font-medium text-[#e5c07b] transition hover:border-[#e5c07b]/60 hover:bg-[#e5c07b]/16 active:scale-[0.98] disabled:opacity-50 ${FOCUS_RING}`}
                >
                  <Sym
                    name="replay"
                    size={16}
                    className={retryBusy ? "animate-rb-spin" : undefined}
                  />
                  {retryBusy
                    ? t("setup.run.retrying", "Retrying…")
                    : t("setup.run.retryFailed", "Retry failed ({count})", { count: failedCount })}
                </button>
              )}
              {onDownload && (done || failed) && !onViewJob && (
                <button
                  type="button"
                  onClick={onDownload}
                  disabled={!canDownload}
                  className={`inline-flex items-center gap-1.5 rounded-lg border border-outline/60 bg-surface/40 px-3.5 py-2 text-[14px] font-medium text-text-variant backdrop-blur-sm transition hover:border-outline hover:bg-surface-high hover:text-text-main active:scale-[0.98] disabled:opacity-50 ${FOCUS_RING}`}
                >
                  <Sym name="download" size={16} />
                  {t("setup.run.download", "Download")}
                </button>
              )}
              {onViewJob && done && (
                <button
                  type="button"
                  onClick={onViewJob}
                  className={`inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 font-display text-[14px] font-semibold text-on-primary shadow-[0_2px_10px_-4px_rgb(0_0_0/0.45)] transition hover:bg-primary-dim active:scale-[0.98] ${FOCUS_RING}`}
                >
                  <Sym name="open_in_new" size={16} />
                  {isBatch
                    ? t("setup.run.viewJob", "View job")
                    : t("setup.run.viewTrial", "View trial")}
                </button>
              )}
              {onNewRun && (done || failed) && (
                <button
                  type="button"
                  onClick={onNewRun}
                  className={`inline-flex items-center gap-1.5 rounded-lg border border-outline/55 bg-transparent px-3.5 py-2 text-[14px] font-medium text-text-dim transition hover:border-outline hover:bg-surface-low hover:text-text-variant active:scale-[0.98] ${FOCUS_RING}`}
                >
                  <Sym name="restart_alt" size={16} />
                  {t("setup.run.reset", "Reset")}
                </button>
              )}
            </div>
          </div>
          <div className="h-1 w-full overflow-hidden rounded-full bg-field/80">
            <div
              className={`h-full rounded-full transition-[width] duration-500 ${
                failed ? "bg-danger" : done ? "bg-secondary" : "bg-primary"
              } ${runPhase === "launching" ? "animate-pulse" : ""}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      ) : (
        <>
          <div className="flex w-full flex-col items-center gap-3 sm:flex-row sm:justify-center">
            <button
              type="button"
              disabled={!canRun || isRunning}
              onClick={onRun}
              className={`glow inline-flex w-full min-w-[200px] items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3.5 font-display text-[16px] font-bold text-on-primary transition hover:bg-primary-dim disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto ${FOCUS_RING}`}
            >
              <Sym name={isBatch ? "rocket_launch" : "play_arrow"} fill={1} size={22} />
              {isRunning
                ? t("setup.run.launching", "Launching…")
                : isBatch
                  ? t("setup.run.runBatch", "Run Batch ({count})", { count: personaCount })
                  : t("setup.run.runLive", "Run Live")}
            </button>
            {isBatch && personaCount > 1 && (
              <CockpitInlineCount
                label={t("setup.run.parallel", "Parallel")}
                value={Math.min(parallelTrials, parallelMax)}
                onChange={onParallelTrialsChange}
                min={1}
                max={parallelMax}
                disabled={isRunning}
                hint={t("setup.run.atMost", "≤ {count}", { count: parallelMax })}
              />
            )}
          </div>
          <p className="mt-2 text-center text-[12px] text-text-dim">
            {isBatch
              ? t("setup.run.batchHint", "Trials appear in the center — status lights update as each finishes.")
              : t("setup.run.liveHint", "Live updates appear in the center frame.")}
          </p>
        </>
      )}
    </div>
  );
}
