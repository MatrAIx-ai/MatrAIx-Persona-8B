import { FOCUS_RING, Sym } from "../cockpitShared";
import { useI18n } from "@/i18n/I18nProvider";
import { personaDimensionLabelKey } from "@/i18n/personaLabelKeys";
import { personaDisplayId, personaPrimaryName } from "@/lib/personaDisplay";
import type { PersonaPoolPersonaCard } from "@/lib/types";
import { PersonaAvatar } from "./PersonaAvatar";
import type { PersonaSearchHit } from "./personaSearchHits";
import { CHIP_TEXT_CLASS, personaDimChipTone } from "./taskCardLabels";
import { ToneChip } from "./ToneChip";

const DIM_LABELS: Record<string, string> = {
  age_bracket: "Age",
  region: "Region",
  domain: "Domain",
  intent: "Intent",
  life_stage: "Life stage",
  source: "Source",
};

export interface BenchPersonaCardProps {
  persona: PersonaPoolPersonaCard;
  selected?: boolean;
  disabled?: boolean;
  onToggle?: () => void;
  onOpenDetail?: () => void;
  /** Attribute hits explaining why this card matched the current query. */
  hits?: PersonaSearchHit[];
}

export function BenchPersonaCard({
  persona,
  selected = false,
  disabled = false,
  onToggle,
  onOpenDetail,
  hits = [],
}: BenchPersonaCardProps) {
  const { t } = useI18n();
  const dims = Object.entries(persona.dimensions ?? {}).slice(0, 4);
  const displayName = personaPrimaryName(persona.name, persona.personaId, persona.dimensions ?? {});
  const codename = personaDisplayId(persona.personaId);
  const visibleHits = hits.slice(0, 2);

  return (
    <div
      role={onToggle ? "button" : undefined}
      tabIndex={onToggle && !disabled ? 0 : undefined}
      onClick={onToggle && !disabled ? onToggle : undefined}
      onKeyDown={
        onToggle && !disabled
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onToggle();
              }
            }
          : undefined
      }
      className={`relative flex h-full w-full flex-col overflow-hidden rounded-xl border border-transparent p-4 transition-all duration-200 ${
        onToggle && !disabled ? "cursor-pointer" : ""
      } ${
        selected
          ? "persona-card--selected"
          : disabled
            ? "glass-tile glass-tile--dim opacity-80"
            : "glass-tile glass-tile--hover border-outline/20"
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="relative shrink-0">
          <PersonaAvatar personaId={persona.personaId} dimensions={persona.dimensions} size="md" />
          {onToggle ? (
          <span
              className={`absolute -left-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border shadow-sm ${
              selected
                  ? "border-primary/40 bg-primary/15 text-primary"
                  : "border-outline/50 bg-surface-lowest/90 text-transparent"
            }`}
            aria-hidden
          >
            <Sym name="check" size={14} />
          </span>
          ) : null}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1 text-left">
              <div className="min-w-0">
                <p className="truncate font-display text-[15px] font-semibold leading-tight text-text-main">
                  {displayName}
                </p>
                <p className="mt-1 font-mono text-[11px] tracking-wide text-text-dim">{codename}</p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {persona.source ? (
                <ToneChip tone="neutral" muted className={CHIP_TEXT_CLASS}>
                  {persona.source}
                </ToneChip>
              ) : null}
              {onOpenDetail && (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onOpenDetail();
                  }}
                  aria-label={t("setup.persona.viewDetails", "View details for {name}", { name: displayName })}
                  className={`rounded-md p-1.5 text-text-dim transition hover:bg-surface-high hover:text-primary ${FOCUS_RING}`}
                >
                  <Sym name="info" size={16} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {visibleHits.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {visibleHits.map((hit) => (
            <span
              key={`${hit.dimensionId}:${hit.value}`}
              title={`${hit.label}: ${hit.value}`}
              className="inline-flex max-w-full items-center gap-1 rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary"
            >
              <span className="opacity-70">{t("setup.persona.match", "Match")}</span>
              <span className="opacity-40">·</span>
              <span className="truncate">{hit.value}</span>
            </span>
          ))}
          {hits.length > visibleHits.length ? (
            <span className="self-center text-[11px] text-text-dim">+{hits.length - visibleHits.length}</span>
          ) : null}
        </div>
      ) : null}

      {dims.length > 0 ? (
        <button
          type="button"
          disabled={disabled}
          onClick={onToggle}
          className={`mt-auto w-full border-t border-outline/20 pt-3 text-left disabled:cursor-default disabled:opacity-80 ${visibleHits.length ? "mt-3" : "mt-4"} ${FOCUS_RING}`}
        >
          <dl className="space-y-2">
            {dims.map(([key, value], index) => {
              const fallback = DIM_LABELS[key] ?? key.replace(/_/g, " ");
              const labelKey = personaDimensionLabelKey(key, fallback);
              const label = labelKey ? t(labelKey, fallback) : fallback;
              return (
                <div key={key} className="grid min-w-0 grid-cols-[4.75rem_1fr] items-baseline gap-x-2">
                  <dt className="truncate text-[11px] text-text-dim" title={label}>
                    <span
                      className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle ${dotClass(personaDimChipTone(key, index))}`}
                      aria-hidden
                    />
                    {label}
                  </dt>
                  <dd className="min-w-0 truncate text-[13px] leading-snug text-text-main" title={value}>
                    {value}
                  </dd>
                </div>
              );
            })}
          </dl>
        </button>
      ) : null}
    </div>
  );
}

function dotClass(tone: ReturnType<typeof personaDimChipTone>): string {
  switch (tone) {
    case "primary":
      return "bg-primary/70";
    case "accent":
      return "bg-accent/70";
    case "secondary":
      return "bg-secondary/70";
    case "warn":
      return "bg-warn/70";
    case "danger":
      return "bg-danger/70";
    default:
      return "bg-outline";
  }
}
