/**
 * Capture the on-screen Batch report into a branded, client-facing PDF.
 *
 * Structure:
 *   1(+). Front matter — task content + persona strategy + cohort (once; may span pages)
 *   N+. Batch results — branded header/footer + screenshot slices
 */
import { toPng } from "html-to-image";
import { jsPDF } from "jspdf";
import type { I18nContextValue } from "@/i18n/I18nProvider";

import { usageMetaLines, type LlmUsageView } from "./llmUsage";

const A4_WIDTH_MM = 210;
const A4_HEIGHT_MM = 297;
const SIDE_MM = 14;
const HEADER_MM = 16;
const FOOTER_MM = 14;
const BRAND = { r: 0, g: 118, b: 194 };
const INK = { r: 17, g: 23, b: 31 };
const MUTED = { r: 100, g: 116, b: 139 };
const RULE = { r: 226, g: 232, b: 240 };
const WASH = { r: 245, g: 249, b: 252 };
const CHIP_BG = { r: 232, g: 242, b: 250 };
const SOFT = { r: 248, g: 250, b: 252 };
const PAGE_BOTTOM = A4_HEIGHT_MM - 14;

type ReportTranslate = I18nContextValue["t"];

export type BatchReportPdfPersona = {
  id: string;
  name: string;
};

export type BatchReportPdfSnapshot = {
  label: string;
  value: string;
  hint?: string;
};

export type BatchReportPdfQuestion = {
  id: string;
  prompt: string;
  type?: string | null;
  scaleMin?: number | null;
  scaleMax?: number | null;
  options?: string[];
};

export type BatchReportPdfPersonaStrategy = {
  mode?: string | null;
  allocation?: string | null;
  perCell?: number | null;
  sampleSize?: number | null;
  seed?: number | null;
  fields?: string[];
  dimensionFilters?: Record<string, string[]>;
  sources?: string[];
};

export type BatchReportPdfMeta = {
  jobName: string;
  status?: string | null;
  configPath?: string | null;
  agentModel?: string | null;
  parallelism?: number | null;
  runWindow?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  generatedAt?: string | null;
  applicationType?: string | null;
  taskPath?: string | null;
  taskTitle?: string | null;
  taskDescription?: string | null;
  taskContext?: string | null;
  taskInstruction?: string | null;
  taskDomain?: string | null;
  taskDifficulty?: string | null;
  taskTags?: string[];
  taskName?: string | null;
  questionCount?: number | null;
  questions?: BatchReportPdfQuestion[];
  personaPool?: string | null;
  personaStrategy?: BatchReportPdfPersonaStrategy | null;
  personas?: BatchReportPdfPersona[];
  snapshot?: BatchReportPdfSnapshot[];
  usage?: LlmUsageView | null;
};

function waitFrames(count = 2): Promise<void> {
  return new Promise((resolve) => {
    const step = (left: number) => {
      if (left <= 0) {
        resolve();
        return;
      }
      requestAnimationFrame(() => step(left - 1));
    };
    step(count);
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function loadImage(
  src: string,
  t?: ReportTranslate,
): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () =>
      reject(
        new Error(
          t
            ? t("reports.pdf.decodeImage")
            : "Failed to decode captured report image.",
        ),
      );
    img.src = src;
  });
}

function cropPageSlice(
  source: HTMLImageElement,
  sourceY: number,
  sliceHeightPx: number,
  t?: ReportTranslate,
): string {
  const canvas = document.createElement("canvas");
  const width = source.width;
  const height = Math.max(1, Math.min(sliceHeightPx, source.height - sourceY));
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error(
      t
        ? t("reports.pdf.allocatePageSlice")
        : "Could not allocate canvas for PDF page slice.",
    );
  }
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(source, 0, sourceY, width, height, 0, 0, width, height);
  return canvas.toDataURL("image/jpeg", 0.92);
}

function formatTs(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return new Date(t).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function humanizePathLeaf(
  path: string | null | undefined,
): string | null {
  if (!path) return null;
  const leaf = path.split("/").filter(Boolean).pop() || path;
  return leaf.replace(/[-_]+/g, " ");
}

export function plainTextFromMarkdown(md: string | null | undefined): string {
  if (!md) return "";
  return md
    .replace(/\r\n/g, "\n")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "• ")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function shortenPath(path: string, maxChars = 72): string {
  const normalized = path.replace(/\\/g, "/");
  if (normalized.length <= maxChars) return normalized;
  const leaf = normalized.split("/").filter(Boolean).pop() || normalized;
  return `.../${leaf}`;
}

function humanizeKey(raw: string): string {
  return raw.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function humanizeAllocation(raw: string | null | undefined): string {
  if (raw === "perCell") return "Per-cell";
  if (raw === "proportional") return "Proportional";
  if (raw === "equalTotal") return "Equal-total";
  return raw ? humanizeKey(raw) : "";
}

function normText(s: string): string {
  return s.toLowerCase().replace(/\s+/g, " ").trim();
}

function paragraphs(text: string): string[] {
  return text
    .split(/\n\n+/)
    .map((p) => p.trim())
    .filter(Boolean);
}

function drawWordmark(pdf: jsPDF, x: number, y: number, size: number): void {
  pdf.setFont("helvetica", "bold");
  pdf.setFontSize(size);
  pdf.setTextColor(INK.r, INK.g, INK.b);
  pdf.text("Matr", x, y);
  const w1 = pdf.getTextWidth("Matr");
  pdf.setTextColor(BRAND.r, BRAND.g, BRAND.b);
  pdf.text("AI", x + w1, y);
  const w2 = pdf.getTextWidth("AI");
  pdf.setTextColor(INK.r, INK.g, INK.b);
  pdf.text("x", x + w1 + w2, y);
}

function drawWatermark(pdf: jsPDF): void {
  pdf.saveGraphicsState();
  try {
    pdf.setGState(pdf.GState({ opacity: 0.035 }));
  } catch {
    /* ignore */
  }
  pdf.setFont("helvetica", "bold");
  pdf.setFontSize(48);
  pdf.setTextColor(BRAND.r, BRAND.g, BRAND.b);
  pdf.text("MatrAIx", A4_WIDTH_MM / 2, A4_HEIGHT_MM / 2 + 8, {
    align: "center",
    angle: 32,
  });
  pdf.restoreGraphicsState();
}

function wrapLines(
  pdf: jsPDF,
  text: string,
  width: number,
  maxLines?: number,
): string[] {
  const lines = pdf.splitTextToSize(text, width) as string[];
  if (maxLines == null || lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  const last = kept[maxLines - 1] ?? "";
  kept[maxLines - 1] =
    last.length > 3
      ? `${last.slice(0, Math.max(0, last.length - 1))}...`
      : `${last}...`;
  return kept;
}

function drawPill(
  pdf: jsPDF,
  x: number,
  y: number,
  label: string,
  opts?: {
    fill?: { r: number; g: number; b: number };
    text?: { r: number; g: number; b: number };
    bold?: boolean;
    size?: number;
  },
): number {
  const fill = opts?.fill ?? CHIP_BG;
  const text = opts?.text ?? BRAND;
  const size = opts?.size ?? 7.5;
  pdf.setFont("helvetica", opts?.bold ? "bold" : "");
  pdf.setFontSize(size);
  const padX = 2.2;
  const w = pdf.getTextWidth(label) + padX * 2;
  const h = 5.2;
  pdf.setFillColor(fill.r, fill.g, fill.b);
  pdf.roundedRect(x, y - 3.7, w, h, 1.1, 1.1, "F");
  pdf.setTextColor(text.r, text.g, text.b);
  pdf.text(label, x + padX, y);
  return w;
}

function drawPillFlow(
  pdf: jsPDF,
  x: number,
  y: number,
  maxX: number,
  labels: string[],
  opts?: {
    fill?: { r: number; g: number; b: number };
    text?: { r: number; g: number; b: number };
    size?: number;
  },
): number {
  let cx = x;
  let cy = y;
  const gap = 1.6;
  const rowH = 6.4;
  for (const label of labels) {
    pdf.setFont("helvetica", "");
    pdf.setFontSize(opts?.size ?? 7.5);
    const w = pdf.getTextWidth(label) + 4.4;
    if (cx + w > maxX && cx > x) {
      cx = x;
      cy += rowH;
    }
    drawPill(pdf, cx, cy, label, opts);
    cx += w + gap;
  }
  return cy + 1.5;
}

/** Labeled key/value cells — visually distinct from tag pills. */
function drawLabeledFactGrid(
  pdf: jsPDF,
  x: number,
  y: number,
  contentW: number,
  facts: Array<{ label: string; value: string }>,
  cols = 4,
): number {
  if (!facts.length) return y;
  const gap = 2.5;
  const n = Math.min(cols, facts.length);
  const cellW = (contentW - gap * (n - 1)) / n;
  const cellH = 12;
  facts.forEach((fact, idx) => {
    const col = idx % n;
    const row = Math.floor(idx / n);
    const cx = x + col * (cellW + gap);
    const cy = y + row * (cellH + 2);
    pdf.setFillColor(SOFT.r, SOFT.g, SOFT.b);
    pdf.setDrawColor(RULE.r, RULE.g, RULE.b);
    pdf.setLineWidth(0.25);
    pdf.roundedRect(cx, cy, cellW, cellH, 1.2, 1.2, "FD");
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(6.5);
    pdf.setTextColor(MUTED.r, MUTED.g, MUTED.b);
    pdf.text(fact.label.toUpperCase(), cx + 2.5, cy + 4.2);
    pdf.setFont("helvetica", "");
    pdf.setFontSize(9);
    pdf.setTextColor(INK.r, INK.g, INK.b);
    const lines = wrapLines(pdf, fact.value, cellW - 5, 2);
    pdf.text(lines, cx + 2.5, cy + 8.8);
  });
  const rows = Math.ceil(facts.length / n);
  return y + rows * (cellH + 2) + 1;
}

function drawSectionRule(
  pdf: jsPDF,
  x: number,
  y: number,
  w: number,
  title: string,
): number {
  pdf.setFont("helvetica", "bold");
  pdf.setFontSize(8);
  pdf.setTextColor(BRAND.r, BRAND.g, BRAND.b);
  pdf.text(title.toUpperCase(), x, y + 3.5);
  pdf.setDrawColor(RULE.r, RULE.g, RULE.b);
  pdf.setLineWidth(0.3);
  pdf.line(x, y + 5.5, x + w, y + 5.5);
  return 8;
}

function drawContentHeader(
  pdf: jsPDF,
  meta: BatchReportPdfMeta,
  subtitle: string,
): void {
  drawWordmark(pdf, SIDE_MM, 10, 11);
  pdf.setFont("helvetica", "");
  pdf.setFontSize(8.5);
  pdf.setTextColor(MUTED.r, MUTED.g, MUTED.b);
  pdf.text(subtitle, A4_WIDTH_MM - SIDE_MM, 10, { align: "right" });
  pdf.setDrawColor(BRAND.r, BRAND.g, BRAND.b);
  pdf.setLineWidth(0.55);
  pdf.line(SIDE_MM, 12.5, A4_WIDTH_MM - SIDE_MM, 12.5);
  pdf.setFontSize(7.5);
  const job =
    meta.jobName.length > 72 ? `${meta.jobName.slice(0, 71)}...` : meta.jobName;
  pdf.text(job, SIDE_MM, 16);
}

function drawContentFooter(
  pdf: jsPDF,
  meta: BatchReportPdfMeta,
  page: number,
  total: number,
  t?: ReportTranslate,
): void {
  const y = A4_HEIGHT_MM - 8;
  pdf.setDrawColor(RULE.r, RULE.g, RULE.b);
  pdf.setLineWidth(0.3);
  pdf.line(SIDE_MM, y - 4, A4_WIDTH_MM - SIDE_MM, y - 4);
  pdf.setFont("helvetica", "");
  pdf.setFontSize(8);
  pdf.setTextColor(MUTED.r, MUTED.g, MUTED.b);
  pdf.text(
    t
      ? t("reports.pdf.confidentialReport")
      : "MatrAIx  |  Confidential evaluation report",
    SIDE_MM,
    y,
  );
  pdf.text(
    t ? t("reports.pdf.pageOf", { page, total }) : `Page ${page} of ${total}`,
    A4_WIDTH_MM - SIDE_MM,
    y,
    { align: "right" },
  );
  const stamp = formatTs(meta.generatedAt);
  if (stamp) {
    pdf.setFontSize(7);
    pdf.text(stamp, A4_WIDTH_MM / 2, y, { align: "center" });
  }
}

/**
 * Task content as whole documents — Instruction and Context stay intact.
 * Blocks are separate; content inside each block is not split.
 */
function buildTaskNarrative(
  meta: BatchReportPdfMeta,
  t?: ReportTranslate,
): Array<{ heading: string; body: string }> {
  const title = (meta.taskTitle || "").trim();
  const instruction = (meta.taskInstruction || "").trim();
  const contextRaw = (meta.taskContext || "").trim();
  const description = (meta.taskDescription || "").trim();
  const sections: Array<{ heading: string; body: string }> = [];

  const stripLeadingTitle = (text: string): string => {
    const paras = paragraphs(text);
    if (!paras.length) return "";
    // Drop a leading heading that only repeats the survey title
    if (title && normText(paras[0]) === normText(title)) {
      return paras.slice(1).join("\n\n").trim();
    }
    // Drop a markdown-style first line that matches title after stripping
    if (
      paras[0].length < 120 &&
      title &&
      normText(paras[0]).includes(normText(title))
    ) {
      const rest = paras.slice(1).join("\n\n").trim();
      if (rest) return rest;
    }
    return text;
  };

  // Prefer full instruction.md as one block
  if (instruction) {
    const body = stripLeadingTitle(instruction);
    if (body)
      sections.push({
        heading: t ? t("reports.pdf.instruction") : "Instruction",
        body,
      });
  } else if (description) {
    sections.push({
      heading: t ? t("reports.pdf.instruction") : "Instruction",
      body: description,
    });
  }

  // Full context.md as one block
  if (contextRaw) {
    const body = stripLeadingTitle(contextRaw);
    if (body)
      sections.push({
        heading: t ? t("reports.pdf.context") : "Context",
        body,
      });
  }

  return sections;
}

type FrontCursor = { page: number; y: number };

function ensureSpace(
  pdf: jsPDF,
  meta: BatchReportPdfMeta,
  cursor: FrontCursor,
  need: number,
  t?: ReportTranslate,
): void {
  if (cursor.y + need <= PAGE_BOTTOM) return;
  pdf.addPage();
  cursor.page += 1;
  drawWatermark(pdf);
  drawContentHeader(
    pdf,
    meta,
    t ? t("reports.pdf.simulationSetup") : "Simulation setup",
  );
  cursor.y = HEADER_MM + 6;
}

/**
 * Draw front matter once. Returns number of front-matter pages.
 */
function drawFrontMatter(
  pdf: jsPDF,
  meta: BatchReportPdfMeta,
  t?: ReportTranslate,
): number {
  const contentW = A4_WIDTH_MM - SIDE_MM * 2;
  const cursor: FrontCursor = { page: 1, y: 0 };

  // ---- Cover header ----
  pdf.setFillColor(WASH.r, WASH.g, WASH.b);
  pdf.rect(0, 0, A4_WIDTH_MM, 36, "F");
  pdf.setFillColor(BRAND.r, BRAND.g, BRAND.b);
  pdf.rect(0, 0, A4_WIDTH_MM, 2.8, "F");
  drawWatermark(pdf);
  drawWordmark(pdf, SIDE_MM, 12, 12);
  pdf.setFont("helvetica", "");
  pdf.setFontSize(8);
  pdf.setTextColor(MUTED.r, MUTED.g, MUTED.b);
  pdf.text(
    t ? t("reports.pdf.playground") : "Playground",
    A4_WIDTH_MM - SIDE_MM,
    11,
    {
      align: "right",
    },
  );
  pdf.setFontSize(8);
  pdf.setTextColor(BRAND.r, BRAND.g, BRAND.b);
  pdf.text(
    t ? t("reports.pdf.evaluationReport") : "EVALUATION REPORT",
    SIDE_MM,
    21,
  );
  pdf.setFont("helvetica", "bold");
  pdf.setFontSize(16);
  pdf.setTextColor(INK.r, INK.g, INK.b);
  pdf.text(
    t ? t("reports.pdf.batchReportTitle") : "Persona-Task Batch Report",
    SIDE_MM,
    29,
  );
  pdf.setFont("helvetica", "");
  pdf.setFontSize(8);
  pdf.setTextColor(MUTED.r, MUTED.g, MUTED.b);
  pdf.text(meta.jobName, SIDE_MM, 34.5);
  cursor.y = 40;

  // ---- Task (run meta lives in the captured batch report below) ----
  ensureSpace(pdf, meta, cursor, 28, t);
  cursor.y += drawSectionRule(
    pdf,
    SIDE_MM,
    cursor.y,
    contentW,
    t ? t("reports.pdf.task") : "Task",
  );

  const title =
    meta.taskTitle ||
    humanizePathLeaf(meta.taskPath) ||
    (t ? t("reports.pdf.task") : "Task");
  pdf.setFont("helvetica", "bold");
  pdf.setFontSize(13);
  pdf.setTextColor(INK.r, INK.g, INK.b);
  const titleLines = wrapLines(pdf, title, contentW, 2);
  ensureSpace(pdf, meta, cursor, titleLines.length * 5 + 10, t);
  pdf.text(titleLines, SIDE_MM, cursor.y + 4);
  cursor.y += titleLines.length * 5 + 2;

  // Task.toml fields as labeled facts (not mixed with tags)
  const taskFacts: Array<{ label: string; value: string }> = [];
  if (meta.applicationType)
    taskFacts.push({
      label: t ? t("reports.pdf.type") : "Type",
      value: meta.applicationType,
    });
  if (meta.taskDomain)
    taskFacts.push({
      label: t ? t("reports.pdf.domain") : "Domain",
      value: meta.taskDomain,
    });
  if (meta.taskDifficulty)
    taskFacts.push({
      label: t ? t("reports.pdf.difficulty") : "Difficulty",
      value: meta.taskDifficulty,
    });
  if (meta.taskPath)
    taskFacts.push({
      label: t ? t("reports.pdf.path") : "Path",
      value: shortenPath(meta.taskPath, 42),
    });
  if (taskFacts.length) {
    ensureSpace(pdf, meta, cursor, 16, t);
    cursor.y =
      drawLabeledFactGrid(pdf, SIDE_MM, cursor.y, contentW, taskFacts, 4) + 2;
  }

  // Actual tags only here
  if (meta.taskTags?.length) {
    ensureSpace(pdf, meta, cursor, 10, t);
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(7.5);
    pdf.setTextColor(MUTED.r, MUTED.g, MUTED.b);
    const tagsLabel = t ? t("reports.pdf.tags") : "Tags";
    pdf.text(tagsLabel, SIDE_MM, cursor.y + 3);
    const tagX = SIDE_MM + pdf.getTextWidth(tagsLabel) + 3;
    cursor.y =
      drawPillFlow(pdf, tagX, cursor.y + 3, SIDE_MM + contentW, meta.taskTags, {
        fill: CHIP_BG,
        text: BRAND,
        size: 7.5,
      }) + 3;
  }

  const narrative = buildTaskNarrative(meta, t);
  for (const section of narrative) {
    ensureSpace(pdf, meta, cursor, 16, t);
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(8);
    pdf.setTextColor(BRAND.r, BRAND.g, BRAND.b);
    pdf.text(section.heading.toUpperCase(), SIDE_MM, cursor.y + 4);
    cursor.y += 6;

    pdf.setFont("helvetica", "");
    pdf.setFontSize(9.5);
    pdf.setTextColor(INK.r, INK.g, INK.b);
    // Preserve paragraph breaks from the source document
    const paras = paragraphs(section.body);
    for (const para of paras.length ? paras : [section.body]) {
      const bodyLines = wrapLines(pdf, para, contentW);
      for (const line of bodyLines) {
        ensureSpace(pdf, meta, cursor, 5, t);
        pdf.text(line, SIDE_MM, cursor.y + 3.5);
        cursor.y += 4.3;
      }
      cursor.y += 2.5;
    }
    cursor.y += 1;
  }

  if (narrative.length === 0) {
    ensureSpace(pdf, meta, cursor, 10, t);
    pdf.setFont("helvetica", "");
    pdf.setFontSize(9);
    pdf.setTextColor(MUTED.r, MUTED.g, MUTED.b);
    pdf.text(
      t
        ? t("reports.pdf.noTaskNarrative")
        : "No task instruction or context was available for this job.",
      SIDE_MM,
      cursor.y + 4,
    );
    cursor.y += 10;
  }

  // ---- Persona strategy (once) ----
  const strategy = meta.personaStrategy;
  const filters = Object.entries(strategy?.dimensionFilters ?? {}).filter(
    ([, v]) => v?.length,
  );
  const stratify = strategy?.fields ?? [];
  ensureSpace(pdf, meta, cursor, 24, t);
  cursor.y += 1;
  cursor.y += drawSectionRule(
    pdf,
    SIDE_MM,
    cursor.y,
    contentW,
    t ? t("reports.pdf.personaSamplingStrategy") : "Persona sampling strategy",
  );

  const strategyFacts: Array<{ label: string; value: string }> = [];
  if (strategy?.mode) {
    strategyFacts.push({
      label: t ? t("reports.pdf.mode") : "Mode",
      value: humanizeKey(String(strategy.mode)),
    });
  }
  if (strategy?.allocation) {
    strategyFacts.push({
      label: t ? t("reports.pdf.allocation") : "Allocation",
      value: humanizeAllocation(strategy.allocation),
    });
  }
  if (strategy?.allocation === "perCell" && strategy.perCell != null) {
    strategyFacts.push({
      label: t ? t("reports.pdf.perCell") : "Per cell",
      value: String(strategy.perCell),
    });
  } else if (strategy?.perCell != null && !strategy?.allocation) {
    strategyFacts.push({
      label: t ? t("reports.pdf.perCell") : "Per cell",
      value: String(strategy.perCell),
    });
  } else if (strategy?.sampleSize != null) {
    strategyFacts.push({
      label: t ? t("reports.pdf.sampleSize") : "Sample size",
      value: String(strategy.sampleSize),
    });
  }
  if (stratify.length) {
    strategyFacts.push({
      label: t ? t("reports.pdf.stratify") : "Stratify",
      value: stratify.map(humanizeKey).join(", "),
    });
  }
  if (meta.personaPool) {
    strategyFacts.push({
      label: t ? t("reports.pdf.pool") : "Pool",
      value: meta.personaPool,
    });
  }
  if (strategyFacts.length) {
    ensureSpace(pdf, meta, cursor, 16, t);
    cursor.y =
      drawLabeledFactGrid(pdf, SIDE_MM, cursor.y, contentW, strategyFacts, 2) +
      2;
  }

  if (filters.length) {
    ensureSpace(pdf, meta, cursor, 8, t);
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(7.5);
    pdf.setTextColor(MUTED.r, MUTED.g, MUTED.b);
    pdf.text(
      t ? t("reports.pdf.audienceFilters") : "Audience filters",
      SIDE_MM,
      cursor.y + 3,
    );
    cursor.y += 5;

    for (const [dim, values] of filters) {
      ensureSpace(pdf, meta, cursor, 8, t);
      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(8);
      pdf.setTextColor(INK.r, INK.g, INK.b);
      const label = humanizeKey(dim);
      pdf.text(label, SIDE_MM, cursor.y + 3);
      const lw = pdf.getTextWidth(label) + 2;
      cursor.y =
        drawPillFlow(
          pdf,
          SIDE_MM + lw,
          cursor.y + 3,
          SIDE_MM + contentW,
          values,
          { fill: SOFT, text: INK, size: 7.5 },
        ) + 2.5;
    }
  }

  // Persona cohort roster and coverage stats are NOT drawn here:
  //  - coverage stats already appear as tiles in the captured on-screen report;
  //  - the full persona roster is appended at the very end (drawPersonaRoster).
  return cursor.page;
}

/**
 * Append the full persona roster as the last section of the report, on its own
 * page(s). Kept out of the front matter so the setup stays compact and the
 * detailed per-persona list lands at the end.
 */
function drawPersonaRoster(
  pdf: jsPDF,
  meta: BatchReportPdfMeta,
  t?: ReportTranslate,
): number {
  const personas = meta.personas ?? [];
  const contentW = A4_WIDTH_MM - SIDE_MM * 2;

  pdf.addPage();
  drawWatermark(pdf);
  drawContentHeader(
    pdf,
    meta,
    t ? t("reports.pdf.personaCohort") : "Persona cohort",
  );
  let y = HEADER_MM + 6;

  y += drawSectionRule(
    pdf,
    SIDE_MM,
    y,
    contentW,
    t
      ? t("reports.pdf.personaCohortCount", { count: personas.length })
      : `Persona cohort  (${personas.length})`,
  );

  const newPage = () => {
    pdf.addPage();
    drawWatermark(pdf);
    drawContentHeader(
      pdf,
      meta,
      t ? t("reports.pdf.personaCohort") : "Persona cohort",
    );
    y = HEADER_MM + 6;
  };

  if (!personas.length) {
    pdf.setFont("helvetica", "");
    pdf.setFontSize(9);
    pdf.setTextColor(MUTED.r, MUTED.g, MUTED.b);
    pdf.text(
      t
        ? t("reports.pdf.rosterUnavailable")
        : "Roster unavailable for this job.",
      SIDE_MM,
      y + 4,
    );
    return 1;
  }

  let pages = 1;
  const colW = (contentW - 4) / 2;
  const rowH = 4.6;
  const mid = Math.ceil(personas.length / 2);
  const left = personas.slice(0, mid);
  const right = personas.slice(mid);
  for (let i = 0; i < left.length; i += 1) {
    if (y + rowH > PAGE_BOTTOM) {
      newPage();
      pages += 1;
    }
    pdf.setFont("helvetica", "");
    pdf.setFontSize(8.5);
    pdf.setTextColor(INK.r, INK.g, INK.b);
    const l = left[i];
    pdf.text(
      wrapLines(pdf, `${l.id}  ${l.name}`, colW - 2, 1)[0],
      SIDE_MM,
      y + 3,
    );
    const r = right[i];
    if (r) {
      pdf.text(
        wrapLines(pdf, `${r.id}  ${r.name}`, colW - 2, 1)[0],
        SIDE_MM + colW + 4,
        y + 3,
      );
    }
    y += rowH;
  }
  return pages;
}

export async function exportBatchReportPdf(
  root: HTMLElement,
  meta: BatchReportPdfMeta,
  t?: ReportTranslate,
): Promise<void> {
  const filename = `${meta.jobName}-persona-task-batch-report.pdf`;
  root.classList.add("batch-report-pdf-capture");
  root.setAttribute("data-pdf-capturing", "true");

  try {
    await waitFrames(2);
    await sleep(120);

    const pixelRatio = Math.min(2, window.devicePixelRatio || 1);
    const dataUrl = await toPng(root, {
      cacheBust: true,
      pixelRatio,
      backgroundColor: "#ffffff",
      filter: (node) => {
        if (!(node instanceof HTMLElement)) return true;
        return !node.hasAttribute("data-pdf-ignore");
      },
    });

    const img = await loadImage(dataUrl, t);
    const contentWidthMm = A4_WIDTH_MM - SIDE_MM * 2;
    const contentTopMm = HEADER_MM + 4;
    const contentBottomMm = A4_HEIGHT_MM - FOOTER_MM;
    const contentHeightMm = contentBottomMm - contentTopMm;
    const pxPerMm = img.width / contentWidthMm;
    const pageHeightPx = Math.floor(contentHeightMm * pxPerMm);

    const slices: Array<{ dataUrl: string; heightMm: number }> = [];
    let sourceY = 0;
    while (sourceY < img.height - 0.5) {
      const remaining = img.height - sourceY;
      const slicePx = Math.min(pageHeightPx, remaining);
      slices.push({
        dataUrl: cropPageSlice(img, sourceY, slicePx, t),
        heightMm: slicePx / pxPerMm,
      });
      sourceY += slicePx;
      if (slices.length > 80) {
        throw new Error(
          t
            ? t("reports.pdf.tooLong")
            : "Batch report is too long to export as a PDF.",
        );
      }
    }

    const pdf = new jsPDF({
      orientation: "portrait",
      unit: "mm",
      format: "a4",
      compress: true,
    });

    drawFrontMatter(pdf, meta, t);

    if (slices.length === 0) {
      pdf.addPage();
      drawWatermark(pdf);
      drawContentHeader(
        pdf,
        meta,
        t ? t("reports.pdf.batchResults") : "Batch results",
      );
      pdf.setFont("helvetica", "");
      pdf.setFontSize(11);
      pdf.setTextColor(MUTED.r, MUTED.g, MUTED.b);
      pdf.text(
        t
          ? t("reports.pdf.noReportContent")
          : "No report content was available to capture.",
        SIDE_MM,
        contentTopMm + 10,
      );
    } else {
      slices.forEach((slice) => {
        pdf.addPage();
        drawWatermark(pdf);
        drawContentHeader(
          pdf,
          meta,
          t ? t("reports.pdf.batchResults") : "Batch results",
        );
        pdf.addImage(
          slice.dataUrl,
          "JPEG",
          SIDE_MM,
          contentTopMm,
          contentWidthMm,
          slice.heightMm,
          undefined,
          "FAST",
        );
      });
    }

    // Full persona roster as the closing section.
    drawPersonaRoster(pdf, meta, t);

    // Footers last, once total page count is known.
    const totalPages = pdf.getNumberOfPages();
    for (let p = 1; p <= totalPages; p += 1) {
      pdf.setPage(p);
      drawContentFooter(pdf, meta, p, totalPages, t);
    }

    pdf.setProperties({
      title: t
        ? t("reports.pdf.documentTitle", { jobName: meta.jobName })
        : `MatrAIx Persona-Task Batch Report - ${meta.jobName}`,
      subject: t ? t("reports.pdf.documentSubject") : "Playground batch report",
      author: "MatrAIx",
      creator: "MatrAIx Playground",
      keywords: [
        "MatrAIx",
        "persona",
        "task",
        "batch report",
        meta.applicationType || "eval",
      ]
        .filter(Boolean)
        .join(", "),
    });

    pdf.save(filename);
  } finally {
    root.classList.remove("batch-report-pdf-capture");
    root.removeAttribute("data-pdf-capturing");
  }
}

export function formatBatchReportMetaLines(
  meta: BatchReportPdfMeta,
  t?: ReportTranslate,
): string[] {
  const lines: string[] = [];
  lines.push(
    t
      ? t("reports.pdf.jobLine", { value: meta.jobName })
      : `Job: ${meta.jobName}`,
  );
  if (meta.taskTitle || meta.taskPath) {
    lines.push(
      t
        ? t("reports.pdf.taskLine", {
            value: meta.taskTitle || meta.taskPath || "",
          })
        : `Task: ${meta.taskTitle || meta.taskPath}`,
    );
  }
  if (meta.personaPool) {
    lines.push(
      t
        ? t("reports.pdf.datasetLine", { value: meta.personaPool })
        : `Dataset: ${meta.personaPool}`,
    );
  }
  if (meta.agentModel) {
    lines.push(
      t
        ? t("reports.pdf.agentModelLine", { value: meta.agentModel })
        : `Agent model: ${meta.agentModel}`,
    );
  }
  if (meta.parallelism != null) {
    lines.push(
      t
        ? t("reports.pdf.parallelismLine", { value: meta.parallelism })
        : `Parallelism: ${meta.parallelism}`,
    );
  }
  if (meta.personas?.length) {
    lines.push(
      t
        ? t("reports.pdf.personasLine", { value: meta.personas.length })
        : `Personas: ${meta.personas.length}`,
    );
  }
  if (meta.personaStrategy?.mode) {
    lines.push(
      t
        ? t("reports.pdf.personaModeLine", { value: meta.personaStrategy.mode })
        : `Persona mode: ${meta.personaStrategy.mode}`,
    );
  }
  if (meta.runWindow)
    lines.push(
      t
        ? t("reports.pdf.runLine", { value: meta.runWindow })
        : `Run: ${meta.runWindow}`,
    );
  if (meta.generatedAt) {
    lines.push(
      t
        ? t("reports.pdf.reportLine", { value: meta.generatedAt })
        : `Report: ${meta.generatedAt}`,
    );
  }
  lines.push(...usageMetaLines(meta.usage, t));
  return lines;
}
