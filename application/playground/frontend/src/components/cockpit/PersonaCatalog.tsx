/**
 * PersonaCatalog: the cockpit's left navigator (persona catalog).
 *
 * Ports the mockup's left column: a header with the total persona count, a
 * search box, and source-filter chips ("All" + the curated datasets); then a
 * scrollable list of `PersonaCard` rows. The catalog is domain-free and
 * searchable, so it queries `GET /api/playground/personas?q=&limit=`
 * (debounced) and filters the result client-side by `source` for the chips.
 *
 * Every persona shipped is curated (the synthetic fixtures were removed), so
 * the "Curated" chip documents provenance; the remaining chips narrow to a
 * single curated dataset (Nemotron / OASIS / …) when the operator wants one.
 *
 * Owns its own search + filter UI state; selection is lifted to the parent.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useI18n } from "@/i18n/I18nProvider";
import { PersonaCard } from "./PersonaCard";
import { FOCUS_RING, Sym } from "./cockpitShared";
import { listPlaygroundPersonas } from "@/lib/api";
import type { PlaygroundPersona, PlaygroundPersonasResponse } from "@/lib/types";

/** How many personas to fetch per search (the full catalog is ~336). */
const PERSONA_LIMIT = 400;

/** Debounce a fast-changing value (the search box) by `delay` ms. */
function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

/** The synthetic "All / Curated" filter, plus one chip per curated source. */
type SourceFilter = "all" | "curated" | string;

export interface PersonaCatalogProps {
  selectedId: string | null;
  onSelect: (persona: PlaygroundPersona) => void;
}

export function PersonaCatalog({ selectedId, onSelect }: PersonaCatalogProps) {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<SourceFilter>("all");
  const debouncedQuery = useDebounced(query.trim(), 200);

  const personasQuery = useQuery<PlaygroundPersonasResponse>({
    queryKey: ["playground-personas", debouncedQuery],
    queryFn: () => listPlaygroundPersonas({ q: debouncedQuery, limit: PERSONA_LIMIT }),
    refetchOnWindowFocus: false,
    placeholderData: (prev) => prev,
    staleTime: 60 * 1000,
  });

  const all = useMemo(() => personasQuery.data?.personas ?? [], [personasQuery.data]);

  // Distinct curated sources, for the per-source filter chips.
  const sources = useMemo(() => {
    const set = new Set<string>();
    for (const p of all) if (p.source) set.add(p.source);
    return Array.from(set).sort();
  }, [all]);

  const personas = useMemo(() => {
    if (filter === "all" || filter === "curated") return all;
    return all.filter((p) => p.source === filter);
  }, [all, filter]);

  const totalLabel =
    personasQuery.isLoading && all.length === 0
      ? t("catalog.personaCatalog.loading")
      : t("catalog.personaCatalog.ready", { count: all.length });

  return (
    <aside className="relative z-0 flex h-[260px] w-full flex-shrink-0 flex-col border-b border-outline bg-surface-lowest lg:h-full lg:w-[300px] lg:border-b-0 lg:border-r">
      {/* Header: title, count, search, filter chips */}
      <div className="flex-shrink-0 border-b border-outline p-md pb-sm">
        <div className="mb-xs">
          <div className="hud mb-1.5 text-[12px] text-primary">{t("catalog.personaCatalog.eyebrow")}</div>
          <h2 className="font-display text-[15px] font-bold text-text-main">{t("catalog.personaCatalog.pick")}</h2>
        </div>
        <p className="hud mb-sm text-[11px] text-text-dim">{totalLabel}</p>

        <div className="relative mb-sm w-full">
          <Sym
            name="search"
            size={18}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-dim"
          />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("catalog.personaCatalog.searchPlaceholder")}
            aria-label={t("catalog.personaCatalog.search")}
            className={`w-full rounded-md border border-outline bg-field h-8 pl-10 pr-3 text-[15px] text-text-main outline-none transition-colors placeholder:text-text-variant hover:border-primary/40 focus:border-primary ${FOCUS_RING}`}
          />
        </div>

        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={t("catalog.personaCatalog.filterBySource")}>
          <FilterChip label={t("catalog.personaCatalog.allSources")} active={filter === "all"} onClick={() => setFilter("all")} />
          <FilterChip
            label={t("catalog.personaCatalog.curated")}
            title={t("catalog.personaCatalog.curatedTitle")}
            active={filter === "curated"}
            onClick={() => setFilter("curated")}
          />
          {sources.map((s) => (
            <FilterChip
              key={s}
              label={s}
              title={t("catalog.personaCatalog.sourceDataset", { source: s })}
              active={filter === s}
              onClick={() => setFilter(s)}
            />
          ))}
        </div>
      </div>

      {/* List */}
      <div className="custom-scrollbar flex-1 space-y-2 overflow-y-auto p-sm">
        {personasQuery.isLoading && all.length === 0 ? (
          <CatalogSkeleton />
        ) : personasQuery.isError ? (
          <CatalogError onRetry={() => personasQuery.refetch()} />
        ) : personas.length === 0 ? (
          <CatalogEmpty query={debouncedQuery} />
        ) : (
          personas.map((p, i) => (
            <div
              key={p.id}
              className="rise-in"
              style={{ animationDelay: `${Math.min(i, 6) * 30}ms` }}
            >
              <PersonaCard persona={p} selected={p.id === selectedId} onSelect={onSelect} />
            </div>
          ))
        )}
      </div>
    </aside>
  );
}

/** A pill-shaped source filter chip. */
function FilterChip({
  label,
  active,
  onClick,
  title,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-pressed={active}
      className={`inline-flex h-8 items-center rounded-full border px-2.5 text-[13px] font-medium transition-colors ${FOCUS_RING} ${
        active
          ? "border-primary bg-primary text-on-primary active:bg-primary-dim"
          : "border-outline bg-surface text-text-variant hover:border-primary hover:bg-surface-low hover:text-text-main active:bg-surface-high"
      }`}
    >
      {label}
    </button>
  );
}

/** A handful of shimmering placeholder cards while the catalog loads. */
function CatalogSkeleton() {
  return (
    <div aria-hidden className="space-y-2">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="rounded-md border border-outline bg-surface p-4">
          <div className="mb-3 flex items-start justify-between">
            <div className="h-10 w-10 animate-rb-pulse rounded bg-surface-high" />
            <div className="h-3.5 w-14 animate-rb-pulse rounded bg-surface-high" />
          </div>
          <div className="h-3.5 w-2/3 animate-rb-pulse rounded bg-surface-high" />
          <div className="mt-2 h-2.5 w-1/2 animate-rb-pulse rounded bg-surface-high" />
        </div>
      ))}
    </div>
  );
}

/** Empty state: no personas match the current search. */
function CatalogEmpty({ query }: { query: string }) {
  const { t } = useI18n();
  return (
    <div className="rise-in flex flex-col items-center px-3 py-8 text-center">
      <div
        className="mb-3 flex h-12 w-12 items-center justify-center rounded-md border border-dashed border-outline bg-surface-high"
        aria-hidden
      >
        <Sym name="search_off" size={24} className="text-text-dim" />
      </div>
      <p className="font-display text-[15px] font-semibold text-text-main">
        {query ? t("catalog.personaCatalog.noMatches") : t("catalog.personaCatalog.noPersonasYet")}
      </p>
      <p className="mt-1 max-w-[260px] text-[14px] leading-snug text-text-variant">
        {query
          ? t("catalog.personaCatalog.nothingMatches", { query })
          : t("catalog.personaCatalog.emptyDescription")}
      </p>
    </div>
  );
}

/** Error state: the catalog failed to load, with a retry. */
function CatalogError({ onRetry }: { onRetry: () => void }) {
  const { t } = useI18n();
  return (
    <div className="rise-in rounded-md border border-outline border-l-4 border-l-danger bg-surface px-4 py-6 text-center">
      <div
        className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-md border border-danger/30 bg-danger/10"
        aria-hidden
      >
        <Sym name="error" size={24} className="text-danger" />
      </div>
      <p className="font-display text-[15px] font-semibold text-text-main">{t("catalog.personaCatalog.couldNotLoad")}</p>
      <p className="mx-auto mt-1 max-w-[260px] text-[14px] leading-snug text-text-variant">
        {t("catalog.personaCatalog.loadDescription")}
      </p>
      <button
        type="button"
        onClick={onRetry}
        className={`mt-3 inline-flex items-center gap-1.5 rounded-md border border-danger/40 bg-danger/10 px-3 py-1.5 text-[13px] font-medium text-danger transition-colors hover:bg-danger/20 active:bg-danger/30 ${FOCUS_RING}`}
      >
        <Sym name="refresh" size={15} />
        {t("catalog.personaCatalog.tryAgain")}
      </button>
    </div>
  );
}

export default PersonaCatalog;
