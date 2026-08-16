import { useEffect, useMemo, useRef, useState } from "react";

import { useI18n } from "@/i18n/I18nProvider";
import { personaDisplayId, personaPrimaryName } from "@/lib/personaDisplay";
import { formatBatchCellStatusLabel } from "@/lib/trialStatus";

import type { BatchTrialCell } from "./BatchTrialGrid";

const PAD = 2;
const MIN_CELL = 4;

/**
 * Muted, equiluminant palette in the spirit of Nord / Tokyo Night: the three
 * signal colours share a similar lightness and moderate saturation so none
 * shouts over the others. Each status is a single flat colour — status is
 * categorical, so shade variation would wrongly imply a quantity.
 */
export const MOSAIC_STATUS_COLORS = {
  done: "#63c090", // soft jade
  running: "#e5c07b", // warm honey amber
  error: "#e08a92", // muted coral rose
  pending: "rgba(118,126,143,0.13)", // faint cool slate
} as const;

function cellColor(trial: BatchTrialCell): string {
  switch (trial.status) {
    case "done":
      return MOSAIC_STATUS_COLORS.done;
    case "running":
      return MOSAIC_STATUS_COLORS.running;
    case "error":
      return MOSAIC_STATUS_COLORS.error;
    default:
      return MOSAIC_STATUS_COLORS.pending;
  }
}

type Geometry = {
  cols: number;
  rows: number;
  cellW: number;
  cellH: number;
  gap: number;
  radius: number;
  contentH: number;
  scroll: boolean;
};

const EMPTY_GEOM: Geometry = {
  cols: 1,
  rows: 1,
  cellW: MIN_CELL,
  cellH: MIN_CELL,
  gap: 1,
  radius: 1,
  contentH: 0,
  scroll: false,
};

function gapFor(cell: number): number {
  return Math.max(1, Math.min(4, Math.round(cell * 0.22)));
}

/**
 * Pack `count` near-square cells so they fill the stage. Scans column counts for
 * the layout with the largest square cell, then stretches to fill both axes. If
 * cells would be sub-pixel (extreme cohorts) it clamps to a floor and scrolls.
 */
function computeGeometry(
  count: number,
  width: number,
  height: number,
): Geometry {
  if (count <= 0 || width <= 0 || height <= 0) return EMPTY_GEOM;

  const usableW = width - PAD * 2;
  const usableH = height - PAD * 2;
  const maxCols = Math.max(1, Math.min(count, Math.floor(usableW)));

  let best: { cols: number; rows: number; cell: number } | null = null;
  for (let cols = 1; cols <= maxCols; cols += 1) {
    const rows = Math.ceil(count / cols);
    const g = 2;
    const cellW = (usableW - (cols - 1) * g) / cols;
    const cellH = (usableH - (rows - 1) * g) / rows;
    const cell = Math.min(cellW, cellH);
    if (cell <= 0) continue;
    if (!best || cell > best.cell) best = { cols, rows, cell };
  }

  if (best && best.cell >= MIN_CELL) {
    const gap = gapFor(best.cell);
    const cellW = (usableW - (best.cols - 1) * gap) / best.cols;
    const cellH = (usableH - (best.rows - 1) * gap) / best.rows;
    return {
      cols: best.cols,
      rows: best.rows,
      cellW,
      cellH,
      gap,
      radius: Math.max(1, Math.min(cellW, cellH) * 0.24),
      contentH: height,
      scroll: false,
    };
  }

  // Extreme cohort — floor the cell size and let the stage scroll vertically.
  const cell = MIN_CELL;
  const gap = 1;
  const cols = Math.max(1, Math.floor((usableW + gap) / (cell + gap)));
  const rows = Math.ceil(count / cols);
  return {
    cols,
    rows,
    cellW: cell,
    cellH: cell,
    gap,
    radius: 1,
    contentH: rows * (cell + gap) - gap + PAD * 2,
    scroll: true,
  };
}

export interface BatchMosaicCanvasProps {
  trials: BatchTrialCell[];
}

/**
 * Aggregate cohort view for very large runs: one canvas cell per persona,
 * coloured GitHub-style by status. Handles tens of thousands of cells without
 * per-person DOM. Hover surfaces the individual persona under the cursor.
 */
export function BatchMosaicCanvas({ trials }: BatchMosaicCanvasProps) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [hover, setHover] = useState<{
    index: number;
    left: number;
    top: number;
  } | null>(null);

  const count = trials.length;
  const geom = useMemo(
    () => computeGeometry(count, box.w, box.h),
    [count, box.w, box.h],
  );
  const canvasH = geom.scroll ? geom.contentH : box.h;

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      setBox({ w: rect.width, h: rect.height });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || box.w <= 0 || canvasH <= 0) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(box.w * dpr);
    canvas.height = Math.round(canvasH * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, box.w, canvasH);

    const { cols, cellW, cellH, gap, radius } = geom;
    const rounded = typeof ctx.roundRect === "function";
    for (let i = 0; i < count; i += 1) {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const x = PAD + col * (cellW + gap);
      const y = PAD + row * (cellH + gap);
      ctx.fillStyle = cellColor(trials[i]);
      if (rounded) {
        ctx.beginPath();
        ctx.roundRect(x, y, cellW, cellH, radius);
        ctx.fill();
      } else {
        ctx.fillRect(x, y, cellW, cellH);
      }
    }
  }, [trials, count, geom, box.w, canvasH]);

  const hoverCell = useMemo(() => {
    if (!hover) return null;
    const { cols, cellW, cellH, gap } = geom;
    const col = hover.index % cols;
    const row = Math.floor(hover.index / cols);
    return {
      left: PAD + col * (cellW + gap),
      top: PAD + row * (cellH + gap),
      w: cellW,
      h: cellH,
    };
  }, [hover, geom]);

  const hoverTrial = hover ? trials[hover.index] : null;

  function handleMove(event: React.MouseEvent<HTMLCanvasElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left - PAD;
    const y = event.clientY - rect.top - PAD;
    const { cols, cellW, cellH, gap } = geom;
    const col = Math.floor(x / (cellW + gap));
    const row = Math.floor(y / (cellH + gap));
    if (col < 0 || col >= cols || row < 0) {
      setHover(null);
      return;
    }
    const index = row * cols + col;
    if (index < 0 || index >= count) {
      setHover(null);
      return;
    }
    setHover({
      index,
      left: event.clientX - rect.left,
      top: event.clientY - rect.top,
    });
  }

  return (
    <div
      ref={wrapRef}
      className="relative min-h-0 flex-1 overflow-y-auto overflow-x-hidden"
    >
      <canvas
        ref={canvasRef}
        className="block"
        style={{ width: box.w, height: canvasH }}
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
      />
      {hoverCell ? (
        <span
          className="pointer-events-none absolute z-10 rounded-[3px] ring-1 ring-text-main/90"
          style={{
            left: hoverCell.left - 1,
            top: hoverCell.top - 1,
            width: hoverCell.w + 2,
            height: hoverCell.h + 2,
          }}
          aria-hidden
        />
      ) : null}
      {hover && hoverTrial ? (
        <MosaicTooltip
          trial={hoverTrial}
          left={hover.left}
          top={hover.top}
          boxW={box.w}
        />
      ) : null}
    </div>
  );
}

function MosaicTooltip({
  trial,
  left,
  top,
  boxW,
}: {
  trial: BatchTrialCell;
  left: number;
  top: number;
  boxW: number;
}) {
  const { t } = useI18n();
  const rawId = (
    trial.persona?.personaId ?? trial.label.replace(/^persona[-_]?/i, "")
  ).trim();
  const personaId = personaDisplayId(rawId || null);
  const name =
    personaPrimaryName(
      trial.persona?.name,
      rawId,
      trial.persona?.dimensions ?? {},
    ) ||
    trial.label ||
    personaId;
  const statusLabel = formatBatchCellStatusLabel(
    trial.status,
    trial.statusStage,
    trial.statusPhase,
    t,
  );
  const flip = left > boxW - 180;
  return (
    <div
      className="pointer-events-none absolute z-20 max-w-[200px] rounded-lg border border-outline/50 bg-surface-lowest/95 px-2.5 py-1.5 shadow-lg backdrop-blur-sm"
      style={{
        left: flip ? undefined : left + 12,
        right: flip ? boxW - left + 12 : undefined,
        top: top + 12,
      }}
    >
      <p className="truncate font-display text-[12px] font-semibold text-text-main">
        {name}
      </p>
      <p className="truncate font-mono text-[11px] text-text-dim">
        {personaId}
      </p>
      <p className="truncate text-[11px] text-text-variant">{statusLabel}</p>
    </div>
  );
}
