/**
 * Shared primitives + honest-data helpers for the Playground.
 *
 * The cockpit ports `tools/recbot-mockups/cockpit-stitch-v2.html` into React.
 * The mockup shows rich, structured persona fields (a descriptive title,
 * demographic chips, preference/dislike/constraint tags), but the real backend
 * only exposes, per curated persona, `{id, name, source, blurb}` over the list
 * endpoint and a humanized `context` *text block* (no structured fields) on a
 * persisted run. So the cockpit must derive what it shows from that text and
 * degrade gracefully when a field is genuinely absent, never invent data.
 *
 * This module collects:
 *   - `Sym`, a thin Material Symbols Outlined glyph (the cockpit's icon set),
 *     with the same `FILL`/size knobs the mockup uses, defaulting to
 *     `aria-hidden` so icon-only controls must supply their own `aria-label`.
 *   - persona-context parsing: a descriptive title (human framing for the bare
 *     codename) + demographic chips (age / gender / occupation / location),
 *     extracted best-effort from the rendered context block.
 *   - the red→amber→green evaluation score scale (the ONLY place a score colour
 *     is decided; the indigo accent is never used to express a score).
 */
import type { CSSProperties, ReactNode } from "react";

export type DisplayTranslate = (
  key: string,
  fallback?: string,
  values?: Record<string, string | number>,
) => string;

/**
 * The one tokenized focus-visible ring for every interactive element in the
 * cockpit: a 2px primary ring at a 2px offset (the Executive Precision focus
 * spec). Applied via `className` so the ring is consistent and obvious on
 * keyboard focus across buttons, tabs, knobs, links, and sliders.
 */
export const FOCUS_RING =
  "outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface-lowest";

// ---------------------------------------------------------------------------
// Material Symbols glyph
// ---------------------------------------------------------------------------

export interface SymProps {
  /** The Material Symbols ligature name, e.g. `"play_arrow"`. */
  name: string;
  /** Pixel size of the glyph (sets `font-size`). Defaults to 18. */
  size?: number;
  /** Filled (1) or outlined (0) optical axis. Defaults to outlined. */
  fill?: 0 | 1;
  className?: string;
  /**
   * Accessible label. When provided the glyph is exposed to AT with this label;
   * otherwise it is decorative (`aria-hidden`) and the *control* must label
   * itself. Icons are never the sole carrier of meaning paired with text.
   */
  label?: string;
  style?: CSSProperties;
}

/** A single Material Symbols Outlined glyph, sized + filled like the mockup. */
export function Sym({ name, size = 18, fill = 0, className = "", label, style }: SymProps) {
  return (
    <span
      className={`material-symbols-outlined ${className}`}
      style={{ fontSize: size, fontVariationSettings: `'FILL' ${fill}`, ...style }}
      aria-hidden={label ? undefined : true}
      role={label ? "img" : undefined}
      aria-label={label}
    >
      {name}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Persona codename / descriptive title
// ---------------------------------------------------------------------------

/**
 * The bare codename half of a persona `name`. Curated names read
 * `"Nemotron · 01B0D4D4"` (source · id); OASIS names are a realname
 * (`"James Miller"`). We surface the codename (id) separately so the heading
 * can pair a human descriptive title with the machine id.
 */
export function personaCodename(name: string | null | undefined, id?: string | null): string {
  const trimmed = (name ?? "").trim();
  if (trimmed.includes("·")) {
    const parts = trimmed.split("·").map((s) => s.trim());
    return parts[parts.length - 1] || (id ?? trimmed);
  }
  return id ?? trimmed;
}

/** Title-case a snake_case / lowercase token (`financial_manager` → `Financial Manager`). */
export function humanizeToken(value: string | null | undefined): string {
  const text = (value ?? "").replace(/_/g, " ").trim();
  if (!text) return "";
  return text
    .split(/\s+/)
    .map((w) => (w[0] ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

/** A parsed demographic chip (`label` is the value text; `key` for React). */
export interface DemographicChip {
  key: string;
  /** Localized fixed label for this display field. */
  label: string;
  /** Short value text shown in the chip (e.g. `"Age 51"`, `"Fin. Manager"`). */
  text: string;
  /** Full value for the chip's `title`/tooltip (un-abbreviated). */
  full: string;
}

/** Pull the value for an indented `Label: value` line from a context block. */
function lineValue(context: string, label: RegExp): string | null {
  for (const raw of context.split("\n")) {
    const line = raw.trim();
    const m = line.match(label);
    if (m) {
      const value = line.slice(m[0].length).trim();
      if (value) return value;
    }
  }
  return null;
}

/** Abbreviate a long occupation for a compact chip, keeping the full form for the title. */
function abbreviateOccupation(occupation: string): string {
  const human = humanizeToken(occupation);
  if (human.length <= 16) return human;
  // Abbreviate the common "<adjective> Manager/Officer/Engineer/…" pattern.
  const words = human.split(" ");
  if (words.length >= 2) {
    const head = words[0];
    const tail = words[words.length - 1];
    const headAbbrev = head.length > 5 ? head.slice(0, 3) + "." : head;
    return `${headAbbrev} ${tail}`;
  }
  return human.slice(0, 14) + "…";
}

/**
 * Best-effort demographic chips parsed from a persona `context` block. Returns
 * only the fields that genuinely appear (age / gender / occupation / location),
 * so a persona without structured demographics shows no chips rather than
 * fabricated ones.
 */
export function parseDemographics(
  context: string | null | undefined,
  t?: DisplayTranslate,
): DemographicChip[] {
  if (!context) return [];
  const chips: DemographicChip[] = [];

  const age = lineValue(context, /^age:\s*/i);
  if (age && /^\d{1,3}$/.test(age)) {
    const label = t?.("cockpit.personaCard.age", "Age") ?? "Age";
    chips.push({ key: "age", label, text: `${label} ${age}`, full: `${label} ${age}` });
  }

  const gender = lineValue(context, /^gender:\s*/i);
  if (gender) {
    const short = /^f(emale)?$/i.test(gender) ? "F" : /^m(ale)?$/i.test(gender) ? "M" : humanizeToken(gender);
    const label = t?.("cockpit.personaCard.gender", "Gender") ?? "Gender";
    chips.push({ key: "gender", label, text: short, full: humanizeToken(gender) });
  }

  const occupation = lineValue(context, /^occupation:\s*/i);
  if (occupation) {
    const label = t?.("cockpit.personaCard.occupation", "Occupation") ?? "Occupation";
    chips.push({ key: "occupation", label, text: abbreviateOccupation(occupation), full: humanizeToken(occupation) });
  }

  // Location: prefer "City, State" if the block has them; else a single "Location:" value.
  const city = lineValue(context, /^city:\s*/i);
  const state = lineValue(context, /^state:\s*/i);
  if (city) {
    const full = state ? `${city}, ${state}` : city;
    const label = t?.("cockpit.personaCard.location", "Location") ?? "Location";
    chips.push({ key: "location", label, text: full.length > 18 ? city : full, full });
  }

  return chips;
}

/**
 * Best-effort demographic chips parsed from a *collapsed* persona `blurb` (the
 * list endpoint whitespace-collapses the context, so the line-based parser
 * above won't bite). Pulls the same age / gender / occupation fields via inline
 * regex; returns only what genuinely appears. Used by the catalog rows, which
 * only have the blurb, not the full context.
 */
export function parseDemographicsFromBlurb(
  blurb: string | null | undefined,
  t?: DisplayTranslate,
): DemographicChip[] {
  if (!blurb) return [];
  const chips: DemographicChip[] = [];

  // Age may be a number (Nemotron) or a range like "40 to 49" (PRIMEX).
  const age = blurb.match(/\bAge:\s*(\d{1,3}(?:\s*(?:to|-|-)\s*\d{1,3})?)/i);
  if (age) {
    const value = age[1].replace(/\s+/g, " ").trim();
    const label = t?.("cockpit.personaCard.age", "Age") ?? "Age";
    chips.push({ key: "age", label, text: `${label} ${value}`, full: `${label} ${value}` });
  }

  const gender = blurb.match(/\bGender:\s*([A-Za-z]+)/i);
  if (gender) {
    const g = gender[1];
    const short = /^f(emale)?$/i.test(g) ? "F" : /^m(ale)?$/i.test(g) ? "M" : humanizeToken(g);
    const label = t?.("cockpit.personaCard.gender", "Gender") ?? "Gender";
    chips.push({ key: "gender", label, text: short, full: humanizeToken(g) });
  }

  // Occupation runs until the next "Word:" label in the collapsed line.
  const occ = blurb.match(/\bOccupation:\s*([^:]+?)(?:\s+[A-Z][a-z]+:|$)/);
  if (occ) {
    const value = occ[1].trim();
    if (value) {
      const label = t?.("cockpit.personaCard.occupation", "Occupation") ?? "Occupation";
      chips.push({ key: "occupation", label, text: abbreviateOccupation(value), full: humanizeToken(value) });
    }
  }

  return chips;
}

/**
 * A descriptive, human title for a persona, the "human framing" the bare
 * codename heading needs. Derived from the persona's real text (context when
 * loaded, else the catalog blurb):
 *   1. a `Bio:` self-description (OASIS), else
 *   2. the occupation (`Occupation: financial_manager` → "Financial Manager"), else
 *   3. the first prose clause of a `Personas:`/`Persona:` block, else
 *   4. the persona `source`, else "Persona".
 * Never fabricated: it always reflects something present in the persona record,
 * and it never surfaces the raw "Demographics: …" preamble as a title.
 */
function truncateTitle(text: string): string {
  const t = text.trim();
  return t.length > 64 ? t.slice(0, 61).trimEnd() + "…" : t;
}

export function personaDescriptiveTitle(
  context: string | null | undefined,
  blurb: string | null | undefined,
  source: string | null | undefined,
): string {
  // The blurb whitespace-collapses the context, so match fields inline; the
  // line-based context (when present) is a superset, so searching the blurb-or-
  // context text covers both shapes.
  const text = (context && context.trim() ? context : blurb) ?? "";

  // 1. A "Persona Description:" sentence (PersonaHub), the cleanest self-desc.
  const desc = text.match(/\bPersona Description:\s*([^]+?)(?:\s+[A-Z][a-z]+:|$)/);
  if (desc?.[1]?.trim()) {
    const clause = desc[1].split(/[.\n]/)[0]?.trim();
    if (clause && clause.length > 4) return truncateTitle(clause);
  }

  // 2. Bio (a self-description, OASIS), bounded by the next "Word:" label.
  const bio = text.match(/\bBio:\s*([^]+?)(?:\s+[A-Z][a-z]+:|$)/);
  if (bio?.[1]?.trim()) return truncateTitle(bio[1]);

  // 3. Occupation → a clean role title (Nemotron).
  const occ = text.match(/\bOccupation:\s*([^:]+?)(?:\s+[A-Z][a-z]+:|$)/);
  if (occ?.[1]?.trim()) return humanizeToken(occ[1].trim());

  // 4. The first clause of a Personas/Persona prose block.
  const persona = text.match(/\bPersonas?:\s*([^]+?)(?:\s+[A-Z][a-z]+:|$)/);
  if (persona?.[1]?.trim()) {
    const clause = persona[1].split(/[.\n]/)[0]?.trim();
    if (clause && clause.length > 4) return truncateTitle(clause);
  }

  return source ? `${source} persona` : "Persona";
}

// ---------------------------------------------------------------------------
// Persona context → labelled sections (Persona inspector tab)
// ---------------------------------------------------------------------------

/** One parsed "Label: body" section of a persona context block. */
export interface PersonaSection {
  label: string;
  body: string;
}

/**
 * Split a rendered persona context into top-level `Label:` sections (e.g.
 * `Demographics`, `Personas`, `Background`). Nested indented lines are folded
 * into the parent section's body. This is presentation only, the raw context
 * is always available verbatim for the "Raw" view.
 */
export function parsePersonaSections(context: string | null | undefined): PersonaSection[] {
  if (!context) return [];
  const sections: PersonaSection[] = [];
  let current: PersonaSection | null = null;
  const bodyLines: string[] = [];

  const flush = () => {
    if (current) {
      current.body = bodyLines.join("\n").trim();
      sections.push(current);
    }
    bodyLines.length = 0;
  };

  for (const raw of context.split("\n")) {
    const isTopLevel = /^[A-Za-z][^:]{0,40}:\s*$/.test(raw) && !raw.startsWith(" ");
    if (isTopLevel) {
      flush();
      current = { label: humanizeToken(raw.replace(/:\s*$/, "")), body: "" };
    } else if (current) {
      bodyLines.push(raw.replace(/^ {2}/, ""));
    } else {
      // Leading content before any section header, start an untitled section.
      current = { label: "", body: "" };
      bodyLines.push(raw);
    }
  }
  flush();
  return sections.filter((s) => s.body || s.label);
}

// ---------------------------------------------------------------------------
// Evaluation score scale (red → amber → green), scores ONLY
// ---------------------------------------------------------------------------

/** The colour band an evaluation score falls into. */
export type ScoreBand = "high" | "mid" | "low" | "none";

/**
 * Band a normalized [0,1] score: high (≥0.7) green, mid (≥0.4) amber, low red.
 * `null`/NaN → the quiet "none" band. This is the single source of truth for
 * score colour across the cockpit; never use the indigo accent for a score.
 */
export function scoreBand(normalized: number | null | undefined): ScoreBand {
  if (normalized === null || normalized === undefined || Number.isNaN(normalized)) return "none";
  if (normalized >= 0.7) return "high";
  if (normalized >= 0.4) return "mid";
  return "low";
}

/**
 * Tokenized text + bar + soft-background classes per score band, drawn from the
 * Executive Precision semantic ramp (emerald success / amber warning / rose
 * error, never the indigo accent). Score *text* uses the darker
 * `on-*-container` tokens so it clears 4.5:1 on a light surface; bars use the
 * base semantic colour; soft backgrounds use the `*-container` token.
 */
export const SCORE_BAND_CLASS: Record<ScoreBand, { text: string; bar: string; soft: string }> = {
  high: { text: "text-score-high", bar: "bg-score-high", soft: "bg-score-high/15" },
  mid: { text: "text-score-mid", bar: "bg-score-mid", soft: "bg-score-mid/15" },
  low: { text: "text-score-low", bar: "bg-score-low", soft: "bg-score-low/15" },
  none: { text: "text-text-dim", bar: "bg-outline", soft: "bg-surface-high" },
};

// ---------------------------------------------------------------------------
// Small formatting helpers
// ---------------------------------------------------------------------------

/** Real per-turn latency, formatted (`1.9s`); `null`/NaN → null (render nothing). */
export function fmtLatency(seconds: number | null | undefined): string | null {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return null;
  if (seconds < 0) return null;
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

/** A reusable label for a node rendered only for screen readers. */
export function VisuallyHidden({ children }: { children: ReactNode }) {
  return <span className="sr-only">{children}</span>;
}
