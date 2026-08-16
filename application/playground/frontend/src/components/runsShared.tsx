/**
 * Shared helpers + precise types for the Runs monitoring surface.
 *
 * `src/lib/types.ts` declares the persisted-run shapes loosely (`transcript:
 * TurnView[]`) to stay tolerant of legacy artifacts. The live backend returns a
 * richer, more specific shape (verified against the running API), so the Runs
 * views narrow it here, at the read boundary, into the fields they actually
 * render, rather than threading `unknown` through the components.
 */
import type { ReactNode } from "react";

import { SCORE_BAND_CLASS, Sym, type ScoreBand } from "./cockpit/cockpitShared";
import type {
  Domain,
  PlaygroundResult,
  SurveyResult,
  TrialEvaluationArtifact,
  UserFeedbackArtifact,
  WebResult,
  WebTrace,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Narrowed run-detail shapes (what RunDetail / RunCompare actually read)
// ---------------------------------------------------------------------------

/** One recommended item as the transcript carries it (id + resolved title). */
export interface RunRecItem {
  id: string;
  title: string | null;
}

/** The persona's terminal stance on a turn. */
export type RunDecision = "continue" | "satisfied" | "give_up";

/** One turn of a persisted run's transcript (the verified backend shape). */
export interface RunTranscriptTurn {
  turnIndex: number;
  userMessage: string;
  assistantMessage: string;
  structuredExposure?: { key?: string | null; label?: string | null; format?: string | null; value?: unknown }[];
  decision: RunDecision | string;
  durationSeconds: number | null;
}

/** The run config block we surface (domain / engine / app selection, etc.). */
export interface RunConfig {
  domain?: Domain | string | null;
  engine?: string | null;
  rankerMode?: string | null;
  resourceMode?: string | null;
  maxTurns?: number | null;
  /** Which chatbot adapter was under test (`meal_planning_nutrition` / `finance_openbb` / …). */
  applicationId?: string | null;
}

/**
 * Which kind of app a run exercised. The debrief picks its shape from this.
 * Today the runs endpoints persist mixed application artifacts, so
 * `runApplicationType` resolves from the stored discriminator and the survey/web/AppWorld branches activate
 * only if the loaded artifact carries the matching result object (see below).
 */
export type RunApplicationType = "chatbot" | "survey" | "web" | "os-app";

/** The persona block we surface in headers. */
export interface RunPersona {
  id?: string | null;
  name?: string | null;
  source?: string | null;
  context?: string | null;
  dimensions?: Record<string, string> | null;
}

/**
 * The full persisted run, narrowed for the Runs views. We re-type the loosely
 * declared members of `PlaygroundResult` to the verified concrete shapes and add
 * the top-level fields the API injects at persist time.
 */
export type RunDetailView = Omit<
  PlaygroundResult,
  "config" | "persona" | "transcript" | "questionnaire" | "metricScores" | "prompts"
> & {
  createdAt?: string | null;
  config: RunConfig;
  persona: RunPersona;
  transcript: RunTranscriptTurn[];
  questionnaire?: PlaygroundResult["questionnaire"];
  metricScores?: PlaygroundResult["metricScores"];
  prompts?: PlaygroundResult["prompts"];
  // ---------------------------------------------------------------------------
  // Option-aware fields the data layer MAY hand over (render-what-we-get).
  // Harbor trial debrief payloads reuse the PlaygroundResult shape.
  // absent today and the debrief renders the chatbot shape. The survey/web/AppWorld
  // bodies read the result/trace shapes already
  // declared in `types.ts`; they light up unchanged once those run kinds persist.
  // ---------------------------------------------------------------------------
  /** Discriminator the artifact may carry; absent → resolved from the payload. */
  applicationType?: RunApplicationType | string | null;
  /** Survey artifact, present only on a persisted survey run. */
  surveyResult?: SurveyResult | null;
  /** Web result + browser trace, present only on a persisted web run. */
  webResult?: WebResult | null;
  webTrace?: WebTrace | null;
  trace?: WebTrace | null;
  /** Human labels a survey/web artifact may carry for the run-meta line. */
  instrumentTitle?: string | null;
  taskTitle?: string | null;
  siteName?: string | null;
  appName?: string | null;
  /** Harbor ``test_state`` / verifier outcome when the trial wrote ``reward.txt``. */
  verifier?: {
    passed: boolean;
    reward: number;
    detail?: string | null;
  } | null;
  /** Raw post-run self-reflection artifact from ``user_feedback.json`` when present. */
  userFeedback?: UserFeedbackArtifact | null;
  /** Task-owned self-report schema used to render personalized feedback fields. */
  selfReportSchema?: import("@/lib/types").SelfReportSchema | null;
  /** Raw trial-level structured evaluation from ``verifier/structured_output.json`` when present. */
  trialEvaluation?: TrialEvaluationArtifact | null;
  /** Harbor task ``instruction.md`` when the debrief API enriches it. */
  instructionMarkdown?: string | null;
  contextMarkdown?: string | null;
  questionnaireMarkdown?: string | null;
  outputSchemaMarkdown?: string | null;
  /** Per-trial agent token/cost receipt from Harbor ``result.json``. */
  usage?: import("@/lib/llmUsage").LlmUsageView | null;
};

/** Narrow a raw `PlaygroundResult` into the richer `RunDetailView` shape. */
export function asRunDetail(raw: PlaygroundResult): RunDetailView {
  return raw as unknown as RunDetailView;
}

/**
 * Resolve which debrief shape a loaded run should render. Prefers an explicit
 * `applicationType` discriminator, then falls back to sniffing which result
 * object the artifact carries. Defaults to `"chatbot"`.
 */
export function runApplicationType(run: RunDetailView): RunApplicationType {
  const explicit = (run.applicationType ?? "").toString().toLowerCase();
  if (
    explicit === "survey"
    || explicit === "web"
    || explicit === "os-app"
    || explicit === "chatbot"
  ) {
    return explicit as RunApplicationType;
  }
  const runRecord = run as Record<string, unknown>;
  if (runRecord.osAppResult) return "os-app";
  if (run.webResult || run.webTrace || run.trace) return "web";
  if (run.surveyResult) return "survey";
  return "chatbot";
}

/** The browser trace, wherever the artifact stashed it. */
export function runWebTrace(run: RunDetailView): WebTrace | null {
  return run.webTrace ?? run.trace ?? null;
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

/** The sentinel the backend uses for a failed/empty agent turn. */
export const AGENT_ERROR_TEXT = "Something went wrong, please retry.";

/** True when an assistant message reads as an error / empty hiccup. */
export function isAgentHiccup(message: string | null | undefined): boolean {
  if (message === null || message === undefined) return true;
  const trimmed = message.trim();
  return trimmed === "" || trimmed === AGENT_ERROR_TEXT;
}

/** A short absolute date like `Jun 21, 14:03` (locale-aware, no year clutter). */
function shortAbsolute(d: Date): string {
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/**
 * Relative age for run lists / meta lines.
 * Always includes "ago" so `22m` is not mistaken for a duration.
 */
export function fmtRunDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "-";
  const date = new Date(t);
  const diffMs = Date.now() - t;
  const sec = Math.round(diffMs / 1000);
  if (sec < 0) return shortAbsolute(date); // clock skew: just show the date
  if (sec < 45) return "just now";
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  if (day < 7) return `${day}d ago`;
  return shortAbsolute(date);
}

/** Spelled-out relative time for debrief headers (`22 minutes ago`). */
export function fmtRunDateFriendly(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const date = new Date(t);
  const diffMs = Date.now() - t;
  const sec = Math.round(diffMs / 1000);
  if (sec < 0) return shortAbsolute(date);
  if (sec < 45) return "just now";
  const min = Math.round(sec / 60);
  if (min === 1) return "1 minute ago";
  if (min < 60) return `${min} minutes ago`;
  const hr = Math.round(min / 60);
  if (hr === 1) return "1 hour ago";
  if (hr < 24) return `${hr} hours ago`;
  const day = Math.round(hr / 24);
  if (day === 1) return "yesterday";
  if (day < 7) return `${day} days ago`;
  return shortAbsolute(date);
}

/** Title-case a snake/lower domain token for a pill (`beauty_product` → `Beauty product`). */
export function fmtDomain(domain: string | null | undefined): string {
  if (!domain) return "-";
  const spaced = domain.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Render a persona `source`, falling back to "curated" when absent. */
export function fmtSource(source: string | null | undefined): string {
  if (source === null || source === undefined || source === "") return "curated";
  return source;
}

// ---------------------------------------------------------------------------
// Small shared presentational atoms
// ---------------------------------------------------------------------------

/** A quiet domain pill (reused across list / detail / compare headers). */
export function DomainPill({ domain }: { domain: string | null | undefined }) {
  return (
    <span className="glass-tile inline-flex items-center rounded px-2 py-0.5 text-[13px] font-medium text-text-variant">
      {fmtDomain(domain)}
    </span>
  );
}

/** A small muted source tag next to a persona name. */
export function SourceTag({ source }: { source: string | null | undefined }) {
  return (
    <span className="glass-tile inline-flex shrink-0 items-center rounded px-1.5 py-px font-mono text-[12px] text-text-variant">
      {fmtSource(source)}
    </span>
  );
}

/** A compact structured-data chip (mono id + title) for trajectories. */
export function RecChip({ item }: { item: RunRecItem }) {
  return (
    <span
      className="glass-tile inline-flex max-w-full items-center gap-1.5 rounded px-2 py-1 text-[13px]"
      title={item.title ?? undefined}
    >
      <span className="font-mono text-[12px] text-text-dim">{item.id}</span>
      {item.title && <span className="truncate text-text-variant">{item.title}</span>}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Option-aware helpers + tiles (chatbot / survey / web / AppWorld debrief shapes)
// ---------------------------------------------------------------------------

/** Friendly display name for the chatbot adapter that was under test. */
const APP_DISPLAY_NAMES: Record<string, string> = {
  meal_planning_nutrition: "Meal planning",
  finance_openbb: "OpenBB",
  acme_support_api: "ACME support API",
  acme_support_mcp: "ACME support MCP",
};

/** The app's real name for the transcript label + meta line. No hardcoded
 * product fallback — callers should prefer the trial's task title when the
 * applicationId is unknown. */
export function appName(applicationId: string | null | undefined): string {
  if (!applicationId) return "Chat app";
  return APP_DISPLAY_NAMES[applicationId] ?? fmtDomain(applicationId);
}

/** Per-kind glyph + label for the list "Kind" tag (Material Symbols, like the cockpit switch). */
const APP_TYPE_META: Record<string, { icon: string; label: string }> = {
  chatbot: { icon: "forum", label: "Chatbot" },
  survey: { icon: "fact_check", label: "Survey" },
  web: { icon: "language", label: "Web" },
  "os-app": { icon: "apps", label: "OS app" },
  unknown: { icon: "help_outline", label: "Unknown" },
};

/**
 * A small app-type tag for the runs list, so a (future) mixed list reads at a
 * glance. Renders from whatever type the summary carries; absent → chatbot.
 */
export function AppTypeTag({ type }: { type?: string | null }) {
  const key = (type ?? "chatbot").toString().toLowerCase();
  const meta = APP_TYPE_META[key] ?? APP_TYPE_META.chatbot;
  return (
    <span
      className="glass-tile inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[13px] text-text-variant"
      title="Application type for this run."
    >
      <Sym name={meta.icon} size={13} />
      {meta.label}
    </span>
  );
}

/** Read a run summary's app type defensively (the summary may not carry one). */
export function runSummaryAppType(summary: unknown): RunApplicationType {
  const t = ((summary as { applicationType?: string | null } | null)?.applicationType ?? "").toString().toLowerCase();
  if (t === "cua" || t === "appworld") return "os-app";
  if (t === "survey" || t === "web" || t === "os-app") return t as RunApplicationType;
  return "chatbot";
}

/** Map a score band to its left-rule accent class (mirrors the cockpit Scorecard). */
export function bandBorderL(band: ScoreBand): string {
  switch (band) {
    case "high":
      return "border-l-score-high";
    case "mid":
      return "border-l-score-mid";
    case "low":
      return "border-l-score-low";
    default:
      return "border-l-outline";
  }
}

/**
 * A debrief headline tile: HUD caption + a big `font-display` value (+ optional
 * unit). When `band` is supplied the value is score-coloured via
 * `SCORE_BAND_CLASS`; `lead` adds the mockup's `border-l-4` accent (band-tinted,
 * or mint when the tile carries no score).
 */
export function StatTile({
  caption,
  value,
  unit,
  band,
  lead = false,
}: {
  caption: string;
  value: ReactNode;
  unit?: string;
  band?: ScoreBand;
  lead?: boolean;
}) {
  const color = band ? SCORE_BAND_CLASS[band] : null;
  const leadBorder = lead ? `border-l-4 ${band ? bandBorderL(band) : "border-l-secondary"}` : "";
  const captionTone = lead ? (color ? color.text : "text-secondary") : "text-text-dim";
  return (
    <div className={`glass-tile flex flex-col justify-center rounded-lg p-4 backdrop-blur-sm ${leadBorder}`}>
      <span className={`hud text-[11px] ${captionTone}`}>{caption}</span>
      <div className="mt-1.5 flex items-baseline gap-1">
        <span
          className={`font-display text-[26px] font-bold leading-none tabular-nums ${color ? color.text : "text-text-main"}`}
        >
          {value}
        </span>
        {unit && <span className="font-sans text-[15px] text-text-dim">{unit}</span>}
      </div>
    </div>
  );
}
