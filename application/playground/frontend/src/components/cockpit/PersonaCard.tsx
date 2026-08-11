/**
 * PersonaCard: one selectable persona, used both as a row in the cockpit's
 * left catalog rail and as a cell in the ⌘K catalog grid.
 *
 * Ports the mockup's catalog card (`app-redesign-v3.html:1297`): a top row with
 * a square avatar tile (left) and a source-tinted provenance chip (right), then
 * the persona's role/occupation as the display heading, an `Age · Sex · id` HUD
 * micro-line, and an optional one-line trait below. Every card carries the
 * Playground corner bracket (`.panel`); the selected card turns its border + glyph
 * cyan and sets `aria-pressed` (color is never the only selection cue).
 *
 * Honest data: the heading/meta are derived from the persona's real text via the
 * `cockpitShared` parsers, never fabricated. A field that does not parse is
 * simply not shown.
 *
 * Purely presentational: the parent owns selection + the persona data.
 */
import { memo } from "react";

import { useI18n } from "@/i18n/I18nProvider";
import {
  FOCUS_RING,
  Sym,
  parseDemographicsFromBlurb,
  personaCodename,
  personaDescriptiveTitle,
} from "./cockpitShared";
import type { PlaygroundPersona } from "@/lib/types";

/**
 * Per-source provenance-chip tone (port of the mockup's `srcColor`,
 * `app-redesign-v3.html:1294`). Unknown sources fall to the neutral default. We
 * never invent a tone for a source we don't recognise.
 */
const SOURCE_TONE: Record<string, string> = {
  Nemotron: "text-secondary bg-secondary/10",
  OASIS: "text-primary bg-primary/10",
  PersonaHub: "text-warn bg-warn/10",
};
const NEUTRAL_TONE = "text-text-variant glass-tile";

export interface PersonaCardProps {
  persona: PlaygroundPersona;
  selected: boolean;
  onSelect: (persona: PlaygroundPersona) => void;
}

function PersonaCardInner({ persona, selected, onSelect }: PersonaCardProps) {
  const { t } = useI18n();
  const codename = personaCodename(persona.name, persona.id);
  const heading = personaDescriptiveTitle(null, persona.blurb, persona.source);
  const demographics = parseDemographicsFromBlurb(persona.blurb);
  const age = demographics.find((c) => c.key === "age");
  const sex = demographics.find((c) => c.key === "gender");
  const occupation = demographics.find((c) => c.key === "occupation");
  // Age · Sex · id: render only the parts that genuinely parse (id is always present).
  const metaLabel = [age?.text, sex?.text, codename].filter(Boolean).join(" · ");
  // Surface the parsed occupation as a one-line trait only when it adds something
  // the heading does not (avoid repeating the heading).
  const traitLine = occupation && occupation.full !== heading ? occupation.full : null;
  const tone = SOURCE_TONE[persona.source ?? ""] ?? NEUTRAL_TONE;

  return (
    <button
      type="button"
      onClick={() => onSelect(persona)}
      aria-pressed={selected}
      aria-label={
        persona.source
          ? t("catalog.personaCard.ariaLabel", "{title}, {source}", {
              title: heading,
              source: persona.source,
            })
          : heading
      }
      className={`panel group relative w-full rounded-md border p-4 text-left transition-[color,background-color,border-color,transform] duration-200 ease-out active:scale-[0.98] ${FOCUS_RING} ${
        selected
          ? "border-primary bg-primary/[0.06]"
          : "border-outline bg-surface hover:border-primary hover:bg-surface-low"
      }`}
    >
      {/* Top row: avatar tile + source-tinted provenance chip. */}
      <div className="mb-3 flex items-start justify-between gap-2">
        <span
          className={`flex h-10 w-10 flex-none items-center justify-center rounded border transition-colors ${
            selected
              ? "border-primary/30 bg-primary/10 text-primary"
              : "border-outline bg-surface-high text-text-variant group-hover:border-primary/40 group-hover:text-primary"
          }`}
          aria-hidden
        >
          <Sym name="person" fill={1} size={20} />
        </span>
        {persona.source && (
          <span
            title={t("catalog.personaCard.sourceDataset", "Source dataset: {source}", {
              source: persona.source,
            })}
            className={`hud flex-none rounded px-1.5 py-0.5 text-[11px] ${tone}`}
          >
            {persona.source}
          </span>
        )}
      </div>

      {/* Role / occupation heading. */}
      <h3
        title={heading}
        className={`truncate font-display text-[14px] font-semibold ${
          selected ? "text-primary" : "text-text-main"
        }`}
      >
        {heading}
      </h3>

      {/* Age · Sex · id micro-label. */}
      {metaLabel && (
        <p
          title={t("catalog.personaCard.demographicsTitle", "Age · sex · persona id")}
          className="hud mt-1 truncate text-[11px] text-text-dim"
        >
          {metaLabel}
        </p>
      )}

      {/* Optional one-line trait. */}
      {traitLine && (
        <p className="mt-2 line-clamp-2 text-[13px] leading-snug text-text-variant">{traitLine}</p>
      )}
    </button>
  );
}

export const PersonaCard = memo(PersonaCardInner);

export default PersonaCard;
