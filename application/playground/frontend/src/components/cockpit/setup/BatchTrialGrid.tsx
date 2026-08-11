import { useVirtualizer } from "@tanstack/react-virtual";

import { useI18n } from "@/i18n/I18nProvider";
import { formatBatchCellStatusLabel } from "@/lib/trialStatus";
import { isMachinePersonaName, personaDisplayId, personaPrimaryName } from "@/lib/personaDisplay";
import type { PersonaPoolPersonaCard } from "@/lib/types";

import { BatchMosaicCanvas, MOSAIC_STATUS_COLORS } from "./BatchMosaicCanvas";
import { PersonaAvatar } from "./PersonaAvatar";
import { useBatchGridLayout, type BatchGridLayout } from "./useBatchGridLayout";

export type BatchTrialStatus = "pending" | "running" | "done" | "error";

export interface BatchTrialPersonaMeta {
  personaId: string;
  name?: string;
  source?: string;
  dimensions: Record<string, string>;
}

export interface BatchTrialCell {
  id: string;
  label: string;
  status: BatchTrialStatus;
  statusLabel?: string;
  persona?: BatchTrialPersonaMeta;
}

const STATUS_STYLES: Record<
  BatchTrialStatus,
  { ring: string; dot: string; glow?: string; wash: string }
> = {
  pending: {
    ring: "border-outline/30",
    dot: "bg-text-dim/55",
    wash: "from-surface-high/40 to-surface/20",
  },
  running: {
    ring: "border-[#e5c07b]/40",
    dot: "bg-[#e5c07b] animate-batch-heartbeat-dot",
    glow: "animate-batch-heartbeat-cell",
    wash: "from-[#e5c07b]/[0.08] to-surface/30",
  },
  done: {
    ring: "border-[#63c090]/30",
    dot: "bg-[#63c090]",
    wash: "from-[#63c090]/[0.08] to-surface/30",
  },
  error: {
    ring: "border-[#e08a92]/35",
    dot: "bg-[#e08a92]",
    glow: "shadow-[0_8px_24px_-12px_rgba(224,138,146,0.28)]",
    wash: "from-[#e08a92]/[0.08] to-surface/30",
  },
};

export interface BatchTrialGridProps {
  trials: BatchTrialCell[];
  jobLabel?: string;
  className?: string;
}

function statusBadgeLabel(
  trial: BatchTrialCell,
  translate: (key: string, fallback?: string) => string,
): string {
  return (
    trial.statusLabel ??
    translate(`setup.status.${trial.status}`, formatBatchCellStatusLabel(trial.status, null, null))
  );
}

function statusLineClass(status: BatchTrialStatus): string {
  if (status === "error") return "text-danger";
  if (status === "running") return "text-amber-600";
  if (status === "done") return "text-secondary";
  return "text-text-variant";
}

function BatchTrialCellView({
  trial,
  rowHeight,
}: {
  trial: BatchTrialCell;
  rowHeight: number;
}) {
  const { t } = useI18n();
  const style = STATUS_STYLES[trial.status];
  const dimensions = trial.persona?.dimensions ?? {};
  const rawPersonaId = (trial.persona?.personaId ?? trial.label.replace(/^persona[-_]?/i, "")).trim();
  const personaId = personaDisplayId(rawPersonaId || null);
  const statusLabel = statusBadgeLabel(trial, t);
  const displayName = personaPrimaryName(trial.persona?.name, rawPersonaId, dimensions) || trial.label || personaId;
  const avatarMuted = trial.status === "pending";
  const portrait = rowHeight >= 96;

  const avatarFrame = (
    <span className="relative inline-flex shrink-0">
      {trial.status === "running" ? (
        <span
          className="absolute inset-[-2px] rounded-full bg-amber-400/12 animate-batch-heartbeat-wash"
          aria-hidden
        />
      ) : null}
      <PersonaAvatar
        personaId={rawPersonaId || trial.id}
        dimensions={dimensions}
        size={portrait ? "lg" : "sm"}
        muted={avatarMuted}
        className={trial.status === "running" ? "relative z-[1] ring-1 ring-amber-400/35" : ""}
      />
    </span>
  );

  return (
    <article
      className={`group relative flex h-full min-h-0 overflow-hidden rounded-2xl border bg-gradient-to-b ${style.ring} ${style.wash} ${style.glow ?? "shadow-sm"} ${
        portrait
          ? "flex-col items-center justify-center gap-2.5 px-3 py-3"
          : "items-center gap-3 px-3 py-2.5"
      }`}
      title={`${displayName} · ${personaId} · ${statusLabel}`}
    >
      {trial.status === "running" ? (
        <span
          className="pointer-events-none absolute inset-0 bg-gradient-to-b from-amber-400/[0.08] via-transparent to-transparent animate-batch-heartbeat-wash"
          aria-hidden
        />
      ) : null}
      <span
        className={`absolute right-2.5 top-2.5 z-10 h-2 w-2 rounded-full ring-2 ring-surface/80 ${style.dot}`}
        aria-label={statusLabel}
      />

      {avatarFrame}

      <div
        className={`min-w-0 ${portrait ? "w-full space-y-1 text-center" : "flex-1 space-y-0.5 pr-4"}`}
      >
        <p
          className={`truncate font-display font-semibold leading-snug text-text-main ${
            portrait ? "text-[14px] px-1" : "text-[13px]"
          }`}
        >
          {displayName}
        </p>
        <p className="truncate font-mono text-[11px] tracking-wide text-text-dim">
          {personaId}
        </p>
        <p
          className={`truncate font-medium ${statusLineClass(trial.status)} ${
            portrait ? "text-[13px] px-1" : "text-[12px]"
          }`}
        >
          {statusLabel}
        </p>
      </div>
    </article>
  );
}

function CohortStat({
  tone,
  label,
  pulse,
}: {
  tone: "dim" | "amber" | "secondary" | "danger";
  label: string;
  pulse?: boolean;
}) {
  const dot =
    tone === "amber"
      ? "bg-[#e5c07b]"
      : tone === "secondary"
        ? "bg-[#63c090]"
        : tone === "danger"
          ? "bg-[#e08a92]"
          : "bg-text-dim/50";
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-outline/35 bg-surface/80 px-2 py-0.5 text-[12px] text-text-variant">
      <span
        className={`h-1.5 w-1.5 rounded-full ${dot} ${pulse ? "animate-batch-heartbeat-dot" : ""}`}
      />
      {label}
    </span>
  );
}

function chipDotClass(status: BatchTrialStatus): string {
  return STATUS_STYLES[status].dot;
}

/** Compact fixed-height chip — used for mid-size cohorts (virtualized rows). */
function BatchTrialChipView({ trial }: { trial: BatchTrialCell }) {
  const { t } = useI18n();
  const style = STATUS_STYLES[trial.status];
  const dimensions = trial.persona?.dimensions ?? {};
  const rawPersonaId = (trial.persona?.personaId ?? trial.label.replace(/^persona[-_]?/i, "")).trim();
  const personaId = personaDisplayId(rawPersonaId || null);
  const statusLabel = statusBadgeLabel(trial, t);
  const displayName =
    personaPrimaryName(trial.persona?.name, rawPersonaId, dimensions) || trial.label || personaId;

  return (
    <article
      className={`relative flex h-full items-center gap-2 overflow-hidden rounded-xl border bg-gradient-to-b px-2 ${style.ring} ${style.wash}`}
      title={`${displayName} · ${personaId} · ${statusLabel}`}
    >
      <PersonaAvatar
        personaId={rawPersonaId || trial.id}
        dimensions={dimensions}
        size="sm"
        muted={trial.status === "pending"}
      />
      <div className="min-w-0 flex-1">
        <p className="truncate font-display text-[12px] font-semibold leading-tight text-text-main">
          {displayName}
        </p>
        <p className="truncate font-mono text-[10px] leading-tight text-text-dim">{personaId}</p>
      </div>
      <span
        className={`h-2 w-2 shrink-0 rounded-full ${chipDotClass(trial.status)} ${
          trial.status === "running" ? "animate-batch-heartbeat-dot" : ""
        }`}
        aria-label={statusLabel}
      />
    </article>
  );
}

type CohortCounts = { done: number; running: number; pending: number; failed: number };

/** Aggregate signal for large cohorts — the individual cell stops being readable. */
function CohortProgressBar({ counts, total }: { counts: CohortCounts; total: number }) {
  if (total <= 0) return null;
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <div
      className="flex h-1.5 w-full shrink-0 overflow-hidden rounded-full bg-surface-high/60"
      role="progressbar"
      aria-valuenow={counts.done}
      aria-valuemax={total}
    >
      <span className="h-full" style={{ width: pct(counts.done), backgroundColor: MOSAIC_STATUS_COLORS.done }} />
      <span
        className="h-full animate-batch-heartbeat-dot"
        style={{ width: pct(counts.running), backgroundColor: MOSAIC_STATUS_COLORS.running }}
      />
      <span className="h-full" style={{ width: pct(counts.failed), backgroundColor: MOSAIC_STATUS_COLORS.error }} />
    </div>
  );
}

/** Virtualized chip grid — bounded DOM regardless of cohort size. */
function BatchChipGrid({
  trials,
  layout,
  scrollRef,
}: {
  trials: BatchTrialCell[];
  layout: BatchGridLayout;
  scrollRef: HTMLDivElement | null;
}) {
  const cols = Math.max(1, layout.cols);
  const rowCount = Math.ceil(trials.length / cols);
  const rowSize = layout.rowHeight + layout.gap;

  const virtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => scrollRef,
    estimateSize: () => rowSize,
    overscan: 6,
  });

  return (
    <div style={{ height: virtualizer.getTotalSize(), position: "relative", width: "100%" }}>
      {virtualizer.getVirtualItems().map((virtualRow) => {
        const start = virtualRow.index * cols;
        const rowTrials = trials.slice(start, start + cols);
        return (
          <div
            key={virtualRow.key}
            className="absolute left-0 top-0 grid w-full"
            style={{
              transform: `translateY(${virtualRow.start}px)`,
              height: layout.rowHeight,
              gap: layout.gap,
              gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
            }}
          >
            {rowTrials.map((trial) => (
              <BatchTrialChipView key={trial.id} trial={trial} />
            ))}
          </div>
        );
      })}
    </div>
  );
}

/** Adaptive roster: full portraits → compact chips → aggregate pixel-wall as cohort grows. */
export function BatchTrialGrid({ trials, jobLabel, className = "" }: BatchTrialGridProps) {
  const { t } = useI18n();
  const counts: CohortCounts = {
    done: trials.filter((t) => t.status === "done").length,
    running: trials.filter((t) => t.status === "running").length,
    pending: trials.filter((t) => t.status === "pending").length,
    failed: trials.filter((t) => t.status === "error").length,
  };
  const { setContainer, container, layout } = useBatchGridLayout(trials.length);
  const isAggregate = layout.mode !== "cards";

  return (
    <div className={`flex h-full min-h-0 w-full flex-col overflow-hidden ${className}`}>
      <header className="mb-2 flex shrink-0 flex-wrap items-baseline gap-x-2.5 gap-y-1 border-b border-outline/25 pb-2">
        <p className="hud text-[11px] text-primary">{t("setup.batch.simulatedCohort", "Simulated cohort")}</p>
        <p className="font-display text-[15px] font-bold tracking-tight text-text-main">
          {trials.length.toLocaleString()} {t(
            trials.length === 1 ? "setup.batch.person" : "setup.batch.people",
            trials.length === 1 ? "person" : "people",
          )}
        </p>
        {jobLabel ? (
          <p className="min-w-0 flex-1 truncate font-mono text-[12px] text-text-dim" title={jobLabel}>
            {jobLabel}
          </p>
        ) : null}
        <div className="ml-auto flex flex-wrap justify-end gap-1">
          {counts.pending > 0 && <CohortStat tone="dim" label={`${counts.pending.toLocaleString()} ${t("setup.batch.waiting", "waiting")}`} />}
          {counts.running > 0 && (
            <CohortStat tone="amber" label={`${counts.running.toLocaleString()} ${t("setup.batch.active", "active")}`} pulse />
          )}
          {counts.done > 0 && <CohortStat tone="secondary" label={`${counts.done.toLocaleString()} ${t("setup.batch.finished", "finished")}`} />}
          {counts.failed > 0 && <CohortStat tone="danger" label={`${counts.failed.toLocaleString()} ${t("setup.batch.failed", "failed")}`} />}
        </div>
      </header>

      {isAggregate ? (
        <div className="mb-2 shrink-0">
          <CohortProgressBar counts={counts} total={trials.length} />
        </div>
      ) : null}

      {layout.mode === "mosaic" ? (
        <BatchMosaicCanvas trials={trials} />
      ) : (
        <div
          ref={setContainer}
          className={`min-h-0 flex-1 ${layout.scroll ? "overflow-y-auto overflow-x-hidden pr-0.5" : "overflow-hidden"}`}
        >
          {layout.mode === "chips" && layout.scroll ? (
            <BatchChipGrid trials={trials} layout={layout} scrollRef={container} />
          ) : (
            <div
              className="grid w-full"
              style={{
                height: layout.scroll ? undefined : "100%",
                gap: layout.gap,
                gridTemplateColumns: `repeat(${layout.cols}, minmax(0, 1fr))`,
                gridTemplateRows: layout.scroll
                  ? `repeat(${layout.rows}, ${layout.rowHeight}px)`
                  : `repeat(${layout.rows}, minmax(0, 1fr))`,
                alignContent: layout.scroll ? "start" : "stretch",
              }}
            >
              {trials.map((trial) =>
                layout.mode === "chips" ? (
                  <BatchTrialChipView key={trial.id} trial={trial} />
                ) : (
                  <BatchTrialCellView key={trial.id} trial={trial} rowHeight={layout.rowHeight} />
                ),
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

type HarborTrialRow = {
  trialName: string;
  personaId?: string | null;
  personaName?: string | null;
  completed?: boolean;
  succeeded?: boolean | null;
  error?: string | null;
  phase?: string | null;
  stage?: string | null;
};

type BatchGridSlot = {
  personaId: string;
  label: string;
  trial?: HarborTrialRow;
};

function personaMetaFromCard(card: PersonaPoolPersonaCard | undefined): BatchTrialPersonaMeta | undefined {
  if (!card) return undefined;
  return {
    personaId: card.personaId,
    name: card.name,
    source: card.source,
    dimensions: card.dimensions ?? {},
  };
}

// Status feeds carry bare ids ("wiki-ebc…") while cohort cards key the
// prefixed form ("persona-wiki-ebc…") — accept either.
function lookupPersonaCard(
  personaById: Record<string, PersonaPoolPersonaCard>,
  personaId: string | null | undefined,
): PersonaPoolPersonaCard | undefined {
  const raw = (personaId ?? "").trim();
  if (!raw) return undefined;
  return personaById[raw] ?? personaById[personaDisplayId(raw)] ?? personaById[raw.replace(/^persona[-_]/i, "")];
}

function resolveBatchGridSlots(
  personaIds: string[],
  harborTrials: HarborTrialRow[] | undefined,
  expectedTotal = 0,
): BatchGridSlot[] {
  const trials = harborTrials ?? [];
  if (personaIds.length > 0) {
    // Bind each persona to its trial by persona_id (from persona_meta.json), NOT
    // by array position. Harbor creates/orders trial dirs independently of the
    // cohort order and the live array grows over time, so index binding makes a
    // cell flip running -> queued -> done as the array shifts. A stable id match
    // keeps each cell's status monotonic.
    const byPersona = new Map<string, HarborTrialRow>();
    const unmatched: HarborTrialRow[] = [];
    for (const trial of trials) {
      const pid = trial.personaId ? personaDisplayId(trial.personaId) : null;
      if (pid && !byPersona.has(pid)) {
        byPersona.set(pid, trial);
      } else if (!trial.personaId) {
        // persona_meta.json not written yet — can't attribute to a persona.
        unmatched.push(trial);
      }
    }
    const previewKeys = new Set(personaIds.map((id) => personaDisplayId(id)));
    const leftovers = [...byPersona.entries()]
      .filter(([key]) => !previewKeys.has(key))
      .map(([, trial]) => trial);
    let nextUnmatched = 0;
    let nextLeftover = 0;
    const slotCount = Math.max(personaIds.length, expectedTotal, trials.length);
    return Array.from({ length: slotCount }, (_, index) => {
      const personaId = personaIds[index];
      let trial = personaId ? byPersona.get(personaDisplayId(personaId)) : undefined;
      if (!trial && nextLeftover < leftovers.length) {
        trial = leftovers[nextLeftover++];
      }
      if (!trial && nextUnmatched < unmatched.length) {
        // Temporarily show an unattributed live trial on a still-empty slot so
        // the running count stays accurate; it snaps to the right cell once
        // persona_meta lands.
        trial = unmatched[nextUnmatched++];
      }
      const id = personaId ?? trial?.personaId ?? trial?.trialName ?? `pending-${index}`;
      return {
        personaId: id,
        label: trial?.personaName ?? (personaId ? `persona-${personaId}` : `persona-${index + 1}`),
        trial,
      };
    });
  }
  return trials.map((trial) => ({
    personaId: trial.personaId ?? trial.trialName,
    label:
      trial.personaName ??
      (trial.personaId ? `persona-${trial.personaId}` : trial.trialName),
    trial,
  }));
}

/** One grid cell per persona — all slots visible from job start. */
export function buildBatchGridCells(
  personaIds: string[],
  harborTrials: HarborTrialRow[] | undefined,
  opts: {
    jobStarted?: boolean;
    parallelTrials?: number;
    personaById?: Record<string, PersonaPoolPersonaCard>;
    expectedTotal?: number;
  } = {},
): BatchTrialCell[] {
  const { personaById = {}, expectedTotal = 0 } = opts;
  const slots = resolveBatchGridSlots(personaIds, harborTrials, expectedTotal);
  if (slots.length === 0) return [];

  return slots.map((slot) => {
    const trial = slot.trial;
    // Status is driven by each cell's OWN matched trial, so it only ever moves
    // forward (queued -> running -> done/error) instead of flickering.
    let status: BatchTrialStatus = "pending";
    if (trial?.completed) {
      status = trial.succeeded === false || trial.error ? "error" : "done";
    } else if (trial) {
      status = "running";
    }

    const card = lookupPersonaCard(personaById, slot.personaId);
    const persona = personaMetaFromCard(card);

    return {
      id: trial?.trialName ?? `persona-${slot.personaId}`,
      label: persona?.name ?? card?.name ?? slot.label,
      status,
      persona,
      statusLabel: formatBatchCellStatusLabel(
        status,
        trial?.stage ?? (status === "running" ? "starting_env" : null),
        trial?.phase,
      ),
    };
  });
}

const STATUS_CODE_TO_STATUS: readonly BatchTrialStatus[] = [
  "pending",
  "running",
  "done",
  "error",
];

type BatchStatusSnapshotLike = {
  codes: number[];
  trialNames: string[];
  personaIds: (string | null)[];
  personaNames: (string | null)[];
};

/**
 * Build grid cells from the lightweight aggregate status feed (large cohorts).
 * Trials known to the backend map positionally; the remainder is padded with
 * pending cells up to the expected cohort size so the mosaic total is stable.
 */
export function buildBatchCellsFromStatus(
  snapshot: BatchStatusSnapshotLike,
  opts: {
    expectedTotal?: number;
    personaIds?: string[];
    personaById?: Record<string, PersonaPoolPersonaCard>;
  } = {},
): BatchTrialCell[] {
  const { expectedTotal = 0, personaIds = [], personaById = {} } = opts;
  const cells: BatchTrialCell[] = [];

  for (let i = 0; i < snapshot.codes.length; i += 1) {
    const status = STATUS_CODE_TO_STATUS[snapshot.codes[i]] ?? "pending";
    const personaId = snapshot.personaIds[i] ?? undefined;
    const card = lookupPersonaCard(personaById, personaId);
    // Feed names are machine ids ("persona-wiki-…") until real names land —
    // never surface those; prefer the cohort card's display name.
    const feedName = snapshot.personaNames[i] ?? undefined;
    const name = card?.name ?? (feedName && !isMachinePersonaName(feedName) ? feedName : undefined);
    cells.push({
      id: snapshot.trialNames[i] ?? `trial-${i}`,
      label: name ?? personaId ?? `#${i + 1}`,
      status,
      persona:
        personaId || card
          ? {
              personaId: card?.personaId ?? personaId ?? "",
              name,
              source: card?.source,
              dimensions: card?.dimensions ?? {},
            }
          : undefined,
    });
  }

  const total = Math.max(expectedTotal, cells.length);
  for (let i = cells.length; i < total; i += 1) {
    const personaId = personaIds[i];
    const card = lookupPersonaCard(personaById, personaId);
    cells.push({
      id: personaId ? `persona-${personaId}` : `pending-${i}`,
      label: card?.name ?? personaId ?? `#${i + 1}`,
      status: "pending",
      persona: personaId
        ? {
            personaId: card?.personaId ?? personaId,
            name: card?.name,
            source: card?.source,
            dimensions: card?.dimensions ?? {},
          }
        : undefined,
    });
  }

  return cells;
}

/** @deprecated Use buildBatchGridCells — keeps old call sites working. */
export function harborTrialsToGridCells(
  trials: HarborTrialRow[],
  personaIds?: string[],
  jobStarted = true,
): BatchTrialCell[] {
  const ids =
    personaIds && personaIds.length >= trials.length
      ? personaIds
      : trials.map((trial, index) => personaIds?.[index] ?? trial.trialName);
  return buildBatchGridCells(ids, trials, { jobStarted, parallelTrials: trials.length });
}
