/**
 * CatalogDrawer: the ⌘K persona catalog (mockup `data-view="catalog"`).
 *
 * Opened from the top-bar "Search catalog" button or ⌘K, this is the full
 * "Browse personas" surface: a header (eyebrow + title + loaded count), a
 * search box, source-filter chips, and a responsive grid of `PersonaCard`s.
 * Picking a card selects that persona (via `onSelect`, the same contract the
 * cockpit rail uses) and closes the overlay, so the cockpit's "Change persona"
 * flow runs through here.
 *
 * It debounces the search box and hits `GET /api/playground/personas` under
 * the *same* query key the rail uses (shared cache), then filters client-side by
 * `source` for the chips. Honest data only: every field shown comes from the
 * real persona record via the `cockpitShared` parsers. Mounts only when `open`.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { PersonaCard } from "./cockpit/PersonaCard";
import { PersonaDrawer } from "./cockpit/PersonaDrawer";
import { FOCUS_RING, Sym } from "./cockpit/cockpitShared";
import { useI18n } from "@/i18n/I18nProvider";
import { listPlaygroundPersonas } from "@/lib/api";
import type {
  Domain,
  PlaygroundPersona,
  PlaygroundPersonasResponse,
} from "@/lib/types";

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

export interface CatalogDrawerProps {
  open: boolean;
  onClose: () => void;
  /** Highlight the currently-selected persona in the grid. */
  selectedId?: string | null;
  /**
   * Pick a persona from the catalog. Matches `PersonaCatalog`'s `onSelect`
   * contract so the cockpit's "Change persona" flow runs through here.
   */
  onSelect?: (persona: PlaygroundPersona) => void;
  /**
   * @deprecated Back-compat with the old item-catalog call sites; the ⌘K palette
   * now browses personas, so this is ignored. The shell rewires the call sites
   * to pass `onSelect` / `selectedId`.
   */
  domain?: Domain;
}

export function CatalogDrawer({
  open,
  onClose,
  selectedId,
  onSelect,
}: CatalogDrawerProps) {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<SourceFilter>("all");
  // Clicking a card opens this persona's detail drawer (view), not select-and-close.
  const [viewing, setViewing] = useState<PlaygroundPersona | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debouncedQuery = useDebounced(query.trim(), 220);

  // Focus the search box and close on Escape while open.
  useEffect(() => {
    if (!open) return;
    const id = window.setTimeout(() => inputRef.current?.focus(), 40);
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(id);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  // Same query key the rail uses → React Query shares one cache entry.
  const personasQuery = useQuery<PlaygroundPersonasResponse>({
    queryKey: ["playground-personas", debouncedQuery],
    queryFn: () =>
      listPlaygroundPersonas({ q: debouncedQuery, limit: PERSONA_LIMIT }),
    enabled: open,
    refetchOnWindowFocus: false,
    placeholderData: (prev) => prev,
    staleTime: 60 * 1000,
  });

  const all = useMemo(
    () => personasQuery.data?.personas ?? [],
    [personasQuery.data],
  );

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

  const loadedLabel =
    personasQuery.isLoading && all.length === 0
      ? t("catalog.catalogDrawer.loading")
      : all.length.toLocaleString();

  if (!open) return null;

  function handleSelect(persona: PlaygroundPersona) {
    onSelect?.(persona);
    onClose();
  }

  return (
    <div
      className="fade-in fixed inset-0 z-50 flex flex-col bg-surface-dim"
      role="dialog"
      aria-modal="true"
      aria-label={t("catalog.personaWorld.title")}
    >
      {/* Header: title + loaded count + close, then search + source chips. */}
      <div className="flex-shrink-0 border-b border-outline bg-surface-lowest px-6 py-5">
        <div className="mx-auto w-full max-w-[1320px]">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <div className="hud mb-1.5 text-[12px] text-primary">
                {t("catalog.personaCatalog.eyebrow")}
              </div>
              <h1 className="font-display text-[24px] font-bold tracking-tight text-text-main">
                {t("catalog.personaWorld.title")}
              </h1>
            </div>
            <div className="flex items-center gap-3">
              <div className="rounded-md border border-outline bg-surface px-4 py-2 text-center">
                <div className="hud text-[11px] text-text-dim">
                  {t("catalog.catalogDrawer.loaded")}
                </div>
                <div className="font-mono text-[18px] font-bold text-primary">
                  {loadedLabel}
                </div>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label={t("catalog.catalogDrawer.close")}
                className={`flex h-9 w-9 flex-none items-center justify-center rounded-md border border-outline bg-surface-low text-text-variant transition-colors hover:border-primary hover:bg-surface hover:text-text-main active:bg-surface-high ${FOCUS_RING}`}
              >
                <Sym name="close" size={18} />
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="flex h-9 min-w-0 flex-1 items-center rounded-md border border-outline bg-field transition-colors hover:border-primary/40 focus-within:border-primary">
              <Sym
                name="search"
                size={16}
                className="ml-3.5 flex-none text-text-dim"
              />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t("catalog.catalogDrawer.searchPlaceholder")}
                aria-label={t("catalog.personaCatalog.search")}
                className="h-full w-full min-w-0 bg-transparent px-3 text-[15px] text-text-main outline-none placeholder:text-text-variant"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  aria-label={t("catalog.personaStore.clearSearch")}
                  className={`mr-2 flex-none rounded p-1 text-text-dim transition-colors hover:bg-surface-high hover:text-text-main active:bg-surface-low ${FOCUS_RING}`}
                >
                  <Sym name="close" size={16} />
                </button>
              )}
            </div>
            <div
              className="flex flex-wrap gap-2"
              role="group"
              aria-label={t("catalog.personaCatalog.filterBySource")}
            >
              <FilterChip
                label={t("catalog.personaCatalog.all")}
                active={filter === "all"}
                onClick={() => setFilter("all")}
              />
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
                  title={t("catalog.personaCatalog.sourceDataset", {
                    source: s,
                  })}
                  active={filter === s}
                  onClick={() => setFilter(s)}
                />
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Grid */}
      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto w-full max-w-[1320px]">
          {personasQuery.isLoading && all.length === 0 ? (
            <CatalogSkeleton />
          ) : personasQuery.isError ? (
            <CatalogError onRetry={() => personasQuery.refetch()} />
          ) : personas.length === 0 ? (
            <CatalogEmpty query={debouncedQuery} />
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {personas.map((p, i) => (
                <div
                  key={p.id}
                  className="rise-in"
                  style={{ animationDelay: `${Math.min(i, 6) * 30}ms` }}
                >
                  <PersonaCard
                    persona={p}
                    selected={p.id === (selectedId ?? null)}
                    onSelect={setViewing}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Persona detail, opened by clicking a card. "Use this persona" selects
          it (when a target context provided one) and closes the catalog. */}
      <PersonaDrawer
        open={viewing !== null}
        persona={viewing}
        context={null}
        onClose={() => setViewing(null)}
        onUse={onSelect ? handleSelect : undefined}
      />
    </div>
  );
}

/** A segmented source-filter chip (port of the mockup's `.seg` catalog chips). */
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
      className={`inline-flex h-9 items-center rounded-md border px-3.5 text-[14px] font-medium transition-colors ${FOCUS_RING} ${
        active
          ? "border-primary bg-primary text-on-primary active:bg-primary-dim"
          : "border-outline bg-surface text-text-variant hover:border-primary hover:bg-surface-low hover:text-text-main active:bg-surface-high"
      }`}
    >
      {label}
    </button>
  );
}

/** A grid of shimmering placeholder cards while the catalog resolves. */
function CatalogSkeleton() {
  return (
    <div
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
      aria-hidden
    >
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          className="rounded-md border border-outline bg-surface p-4"
        >
          <div className="mb-3 flex items-start justify-between">
            <div className="h-10 w-10 animate-rb-pulse rounded bg-surface-high" />
            <div className="h-3.5 w-14 animate-rb-pulse rounded bg-surface-high" />
          </div>
          <div className="h-3.5 w-2/3 animate-rb-pulse rounded bg-surface-high" />
          <div className="mt-2 h-2.5 w-1/2 animate-rb-pulse rounded bg-surface-high" />
          <div className="mt-3 h-2.5 w-3/4 animate-rb-pulse rounded bg-surface-high" />
        </div>
      ))}
    </div>
  );
}

/** Empty state: no personas match the current search. */
function CatalogEmpty({ query }: { query: string }) {
  const { t } = useI18n();

  return (
    <div className="rise-in flex flex-col items-center px-4 py-16 text-center">
      <div
        className="mb-3 flex h-14 w-14 items-center justify-center rounded-md border border-dashed border-outline bg-surface-high"
        aria-hidden
      >
        <Sym name="search_off" size={26} className="text-text-dim" />
      </div>
      <p className="font-display text-[15px] font-semibold text-text-main">
        {query
          ? t("catalog.personaCatalog.noMatches")
          : t("catalog.personaCatalog.noPersonasYet")}
      </p>
      <p className="mt-1 max-w-[320px] text-[14px] leading-snug text-text-variant">
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
    <div className="rise-in mx-auto max-w-md rounded-md border border-outline border-l-4 border-l-danger bg-surface px-4 py-6 text-center">
      <div
        className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-md border border-danger/30 bg-danger/10"
        aria-hidden
      >
        <Sym name="error" size={24} className="text-danger" />
      </div>
      <p className="font-display text-[15px] font-semibold text-text-main">
        {t("catalog.personaCatalog.couldNotLoad")}
      </p>
      <p className="mx-auto mt-1 max-w-[300px] text-[14px] leading-snug text-text-variant">
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

export default CatalogDrawer;
