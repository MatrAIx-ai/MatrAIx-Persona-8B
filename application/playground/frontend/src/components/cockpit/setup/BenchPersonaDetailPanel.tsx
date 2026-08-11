import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";
import {
  personaDimensionLabelKey,
  personaSectionLabelKey,
} from "@/i18n/personaLabelKeys";
import { personaDisplayId, personaPrimaryName } from "@/lib/personaDisplay";
import {
  PERSONA_BENCH_POOL,
  type PersonaDimensionGroup,
  type PersonaPoolPersonaCard,
} from "@/lib/types";
import { FOCUS_RING, Sym } from "../cockpitShared";
import { PersonaAvatar } from "./PersonaAvatar";
import { personaRosterLines } from "./simulatedPersonaVisual";
import { personaDimChipTone } from "./taskCardLabels";

const SPOTLIGHT: Array<{ key: string; label: string }> = [
  { key: "age_bracket", label: "Age" },
  { key: "life_stage", label: "Life stage" },
  { key: "domain", label: "Domain" },
  { key: "region", label: "Region" },
  { key: "intent", label: "Intent" },
];

export interface BenchPersonaDetailPanelProps {
  persona: PersonaPoolPersonaCard | null;
  /** Pool used to resolve the full YAML / Parquet record. */
  pool?: string | null;
  onClose: () => void;
  onUse?: (persona: PersonaPoolPersonaCard) => void;
  useLabel?: string;
  /** Fill the entire persona rail (hides Model / Dataset / tabs). */
  coverRail?: boolean;
  /** Inline inside the cockpit persona rail — no nested glass card chrome. */
  embedded?: boolean;
  className?: string;
}

function spotlightDotClass(tone: ReturnType<typeof personaDimChipTone>): string {
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

function TaxonomyTree({ groups }: { groups: PersonaDimensionGroup[] }) {
  const { t } = useI18n();
  const sectionLabel = (id: string, label: string): string => {
    const labelKey = personaSectionLabelKey(id, label);
    return labelKey ? t(labelKey, label) : label;
  };
  const dimensionLabel = (id: string, label: string): string => {
    const labelKey = personaDimensionLabelKey(id, label);
    return labelKey ? t(labelKey, label) : label;
  };
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    groups.forEach((group, index) => {
      // Open only the first group so the panel doesn't start as a dense wall.
      initial[group.id] = index === 0;
    });
    return initial;
  });
  const [openSubgroups, setOpenSubgroups] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const next: Record<string, boolean> = {};
    groups.forEach((group, index) => {
      next[group.id] = index === 0;
    });
    setOpenGroups(next);
    setOpenSubgroups({});
  }, [groups]);

  if (groups.length === 0) {
    return (
      <p className="mt-4 text-[13px] leading-relaxed text-text-dim">{t("setup.persona.noDimensionValues", "No dimension values available.")}</p>
    );
  }

  return (
    <div className="mt-4 space-y-3">
      {groups.map((group) => {
        const groupOpen = openGroups[group.id] ?? false;
        return (
          <section
            key={group.id}
            className="overflow-hidden rounded-xl border border-outline/20 bg-surface/30"
          >
            <button
              type="button"
              aria-expanded={groupOpen}
              onClick={() =>
                setOpenGroups((prev) => ({ ...prev, [group.id]: !groupOpen }))
              }
              className={`flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left transition hover:bg-primary/5 ${FOCUS_RING}`}
            >
              <span className="min-w-0">
                <span className="block font-display text-[14px] font-semibold text-text-main">
                  {sectionLabel(group.id, group.label)}
                </span>
                <span className="mt-1 block text-[12px] text-text-dim">
                  {t("setup.persona.subgroups", "{count} attributes · {subgroups} subgroups", {
                    count: group.count.toLocaleString(),
                    subgroups: group.subgroups.length,
                  })}
                </span>
              </span>
              <Sym
                name={groupOpen ? "expand_less" : "expand_more"}
                size={20}
                className="shrink-0 text-text-dim"
              />
            </button>
            {groupOpen ? (
              <div className="space-y-2 border-t border-outline/15 px-3 py-3">
                {group.subgroups.map((subgroup) => {
                  const subKey = `${group.id}/${subgroup.id}`;
                  const subOpen = openSubgroups[subKey] ?? false;
                  return (
                    <div key={subgroup.id} className="rounded-lg bg-field/35">
                      <button
                        type="button"
                        aria-expanded={subOpen}
                        onClick={() =>
                          setOpenSubgroups((prev) => ({
                            ...prev,
                            [subKey]: !subOpen,
                          }))
                        }
                        className={`flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left ${FOCUS_RING}`}
                      >
                        <span className="text-[13px] font-medium text-text-main">
                          {sectionLabel(subgroup.id, subgroup.label)}
                        </span>
                        <span className="flex items-center gap-1.5 text-[12px] text-text-dim">
                          {subgroup.count}
                          <Sym
                            name={subOpen ? "expand_less" : "expand_more"}
                            size={16}
                          />
                        </span>
                      </button>
                      {subOpen ? (
                        <ul className="divide-y divide-outline/10 border-t border-outline/15 px-3.5 py-1">
                          {subgroup.items.map((item) => (
                            <li
                              key={item.id}
                              className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] gap-3 py-2.5"
                            >
                              <span
                                className="truncate text-[12px] leading-snug text-text-dim"
                                title={dimensionLabel(item.id, item.label)}
                              >
                                {dimensionLabel(item.id, item.label)}
                              </span>
                              <span
                                className="truncate text-right text-[13px] leading-snug text-text-main"
                                title={item.value}
                              >
                                {item.value}
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}

export function BenchPersonaDetailPanel({
  persona,
  pool = PERSONA_BENCH_POOL,
  onClose,
  onUse,
  useLabel,
  coverRail = false,
  embedded = false,
  className = "",
}: BenchPersonaDetailPanelProps) {
  const { t } = useI18n();
  const personaId = persona?.personaId ?? null;
  const activePool = pool?.trim() || PERSONA_BENCH_POOL;
  const detailQuery = useQuery({
    queryKey: ["persona-pool-detail", activePool, personaId],
    queryFn: () => api.getPersonaPoolPersona(personaId!, activePool),
    enabled: Boolean(personaId),
    staleTime: 120_000,
    retry: 1,
  });

  const dims = detailQuery.data?.dimensions ?? persona?.dimensions ?? {};
  const groups = useMemo<PersonaDimensionGroup[]>(() => {
    const fromApi = detailQuery.data?.dimensionGroups;
    if (fromApi && fromApi.length > 0) return fromApi;
    const entries = Object.entries(dims);
    if (entries.length === 0) return [];
    return [
      {
        id: "all",
        label: t("setup.persona.attributes", "Attributes"),
        count: entries.length,
        subgroups: [
          {
            id: "flat",
            label: t("setup.persona.allDimensions", "All dimensions"),
            count: entries.length,
            items: entries.map(([id, value]) => ({
              id,
              label: (() => {
                const fallback = id.replace(/_/g, " ");
                const labelKey = personaDimensionLabelKey(id, fallback);
                return labelKey ? t(labelKey, fallback) : fallback;
              })(),
              value,
            })),
          },
        ],
      },
    ];
  }, [detailQuery.data?.dimensionGroups, dims, t]);

  const spotlight = useMemo(
    () => SPOTLIGHT.map((item) => ({ ...item, value: dims[item.key] })).filter((item) => item.value),
    [dims],
  );

  if (!persona) return null;

  const displayName = personaPrimaryName(persona.name, persona.personaId, dims);
  const codename = personaDisplayId(persona.personaId);
  const roster = personaRosterLines(dims);
  const blurb = roster
    ? roster.secondary
      ? `${roster.primary} · ${roster.secondary}`
      : roster.primary
    : null;
  const poolLabel =
    detailQuery.data?.pool?.trim() ||
    detailQuery.data?.path?.trim() ||
    activePool;
  const filledCount =
    detailQuery.data?.dimensionGroups?.reduce((sum, group) => sum + group.count, 0) ??
    Object.keys(dims).length;

  const shellClass = coverRail
    ? `flex h-full min-h-0 w-full flex-col overflow-hidden ${className}`
    : embedded
      ? `flex h-full min-h-0 w-full flex-col overflow-hidden ${className}`
      : `glass-panel flex h-full max-h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-xl ${className}`;

  return (
    <aside className={shellClass} aria-label={t("setup.persona.detailsFor", "Persona details for {name}", { name: displayName })}>
      <div className="shrink-0 border-b border-outline/20 px-1 pb-3 pt-0.5">
        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={onClose}
            className={`inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-[13px] font-medium text-text-dim transition hover:bg-surface-high hover:text-text-main ${FOCUS_RING}`}
          >
            <Sym name="arrow_back" size={16} />
            {t("setup.common.back", "Back")}
          </button>
          <p className="cockpit-field-label text-[11px] tracking-[0.08em] text-text-dim">
            {t("setup.persona.profile", "Persona profile")}
          </p>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("setup.persona.closeDetails", "Close persona details")}
            className={`shrink-0 rounded-md p-1.5 text-text-dim transition hover:bg-surface-high hover:text-text-main ${FOCUS_RING}`}
          >
            <Sym name="close" size={18} />
          </button>
        </div>
      </div>

      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain px-1 pt-5">
        <div className="flex items-start gap-4">
          <PersonaAvatar personaId={persona.personaId} dimensions={dims} size="lg" />
          <div className="min-w-0 flex-1 pt-0.5">
            <h2 className="font-display text-[20px] font-semibold leading-tight text-text-main">
              {displayName}
            </h2>
            <p className="mt-1 flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[12px] leading-snug text-text-dim">
              <span className="font-mono tracking-wide">{codename}</span>
              {persona.source ? (
                <>
                  <span className="text-outline/80" aria-hidden>
                    ·
                  </span>
                  <span>{persona.source}</span>
                </>
              ) : null}
              {filledCount > 0 ? (
                <>
                  <span className="text-outline/80" aria-hidden>
                    ·
                  </span>
                  <span>{filledCount.toLocaleString()} {t("setup.persona.dimensions", "dimensions")}</span>
                </>
              ) : null}
            </p>
          </div>
        </div>

        {blurb ? (
          <p className="mt-4 text-[14px] leading-relaxed text-text-variant">{blurb}</p>
        ) : null}

        {spotlight.length > 0 ? (
          <dl className="mt-5 space-y-3 border-y border-outline/20 py-4">
            {spotlight.map(({ key, label, value }, index) => {
              const labelKey = personaDimensionLabelKey(key, label);
              const displayLabel = labelKey ? t(labelKey, label) : label;
              return (
                <div key={key} className="grid grid-cols-[5.5rem_1fr] items-baseline gap-x-3">
                  <dt className="text-[12px] text-text-dim">
                    <span
                      className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle ${spotlightDotClass(personaDimChipTone(key, index))}`}
                      aria-hidden
                    />
                    {displayLabel}
                  </dt>
                  <dd className="min-w-0 text-[14px] leading-snug text-text-main" title={value}>
                    {value}
                  </dd>
                </div>
              );
            })}
          </dl>
        ) : null}

        <div className="mt-6">
          <div>
            <p className="font-display text-[15px] font-semibold text-text-main">{t("setup.persona.taxonomy", "Taxonomy")}</p>
            <p className="mt-1 text-[12px] leading-relaxed text-text-dim">
              {t("setup.persona.groupsBrowse", "{count} groups · expand a category to browse attributes", { count: groups.length })}
            </p>
          </div>
          {detailQuery.isPending ? (
            <p className="mt-4 text-[13px] text-text-dim">{t("setup.persona.loadingDimensions", "Loading full dimensions…")}</p>
          ) : null}
          {detailQuery.isError ? (
            <p className="mt-4 text-[13px] text-danger">
              {detailQuery.error instanceof ApiError
                ? detailQuery.error.message
                : t("setup.persona.loadRecordFailed", "Could not load persona record.")}
            </p>
          ) : null}
          {!detailQuery.isPending ? <TaxonomyTree groups={groups} /> : null}
        </div>

        <p className="mt-6 pb-4 font-mono text-[11px] leading-relaxed text-text-dim">{poolLabel}</p>
      </div>

      {onUse ? (
        <div className="shrink-0 border-t border-outline/25 px-1 py-3.5">
          <button
            type="button"
            onClick={() => onUse(persona)}
            className={`inline-flex h-10 w-full items-center justify-center rounded-md bg-primary text-[14px] font-medium text-on-primary transition hover:bg-primary/90 ${FOCUS_RING}`}
          >
            {useLabel ?? t("setup.persona.use", "Use persona")}
          </button>
        </div>
      ) : null}
    </aside>
  );
}
