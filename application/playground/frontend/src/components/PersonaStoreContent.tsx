/**
 * PersonaStoreContent: persona grid (Persona World page + ⌘K drawer).
 * Supports bench pools (full browse) and MatrAIx Persona 1M (scroll-loaded
 * 10k preview; search/filters apply to that window). Headline count is the
 * dataset total.
 */
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";

import { BenchPersonaCard } from "./cockpit/setup/BenchPersonaCard";
import { BenchPersonaDetailPanel } from "./cockpit/setup/BenchPersonaDetailPanel";
import {
  CockpitSelect,
  type CockpitSelectOption,
} from "./cockpit/setup/CockpitSelect";
import { PersonaFilterModal } from "./cockpit/setup/PersonaFilterModal";
import {
  applyAllSuggestions,
  isSuggestionSelected,
  shouldMatchAttributes,
  suggestionKey,
  toggleSuggestionInFilters,
} from "./cockpit/setup/personaAttributeMatch";
import {
  activeFilterCount,
  emptyPersonaDimensionFilters,
  type PersonaDimensionFilters,
} from "./cockpit/setup/personaSamplingTypes";
import {
  catalogDimIdSet,
  findPersonaSearchHits,
  MIN_HIT_QUERY_LENGTH,
  personaHasDimensionValue,
  personaMatchesQuery,
  summarizeHitsAcrossPersonas,
} from "./cockpit/setup/personaSearchHits";
import { FOCUS_RING, Sym } from "./cockpit/cockpitShared";
import { StudioGlassPanel } from "./studio/StudioShell";
import { useI18n } from "@/i18n/I18nProvider";
import { api } from "@/lib/api";
import { personaPoolEmptyState, poolSlugLabel } from "@/lib/personaPoolCopy";
import type {
  PersonaMatchedAttribute,
  PersonaPoolCatalog,
  PersonaPoolPersonaCard,
} from "@/lib/types";
import { PERSONA_BENCH_POOL, PERSONA_PRODUCTION_1M_POOL } from "@/lib/types";

/** Page size when loading a full small pool (API max per request). */
const PERSONA_POOL_PAGE = 50;
/** 1M browse/search window — always filled in the background for filter/search. */
const PERSONA_1M_PREVIEW_CAP = 10_000;
/** Personas fetched per background page for the 10k preview (API max 500). */
const PERSONA_1M_PAGE = 500;
/** Idle / search grid: initial cards shown; scroll reveals more from the 10k window. */
const PERSONA_1M_VISIBLE_PAGE = 100;

function nearestScrollRoot(el: HTMLElement | null): Element | null {
  let node: HTMLElement | null = el?.parentElement ?? null;
  while (node && node !== document.body) {
    const { overflow, overflowY } = getComputedStyle(node);
    const y = overflowY || overflow;
    if (y === "auto" || y === "scroll" || y === "overlay") return node;
    node = node.parentElement;
  }
  return null;
}

/** Local-state search input so keystrokes don't re-render the persona grid. */
function PersonaSearchField({
  value,
  onDebouncedChange,
  inputRef,
  placeholder,
}: {
  value: string;
  onDebouncedChange: (value: string) => void;
  inputRef?: React.RefObject<HTMLInputElement>;
  placeholder: string;
}) {
  const { t } = useI18n();
  const [local, setLocal] = useState(value);
  useEffect(() => {
    setLocal(value);
  }, [value]);
  useEffect(() => {
    const id = window.setTimeout(() => {
      if (local !== value) onDebouncedChange(local);
    }, 320);
    return () => window.clearTimeout(id);
  }, [local, onDebouncedChange, value]);

  return (
    <div className="glass-tile flex h-9 min-w-0 flex-1 items-center rounded-lg transition-colors focus-within:bg-surface-high/50">
      <Sym name="search" size={15} className="ml-2.5 flex-none text-text-dim" />
      <input
        ref={inputRef}
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        placeholder={placeholder}
        aria-label={t("catalog.personaStore.search")}
        className="h-full w-full min-w-0 bg-transparent px-2.5 text-[13px] text-text-main outline-none placeholder:text-text-variant"
      />
      {local ? (
        <button
          type="button"
          onClick={() => {
            setLocal("");
            onDebouncedChange("");
          }}
          aria-label={t("catalog.personaStore.clearSearch")}
          className={`mr-1.5 flex-none rounded p-1 text-text-dim transition-colors hover:bg-surface-high hover:text-text-main ${FOCUS_RING}`}
        >
          <Sym name="close" size={15} />
        </button>
      ) : null}
    </div>
  );
}

function matchesPersonaFilters(
  persona: PersonaPoolPersonaCard,
  filters: PersonaDimensionFilters,
): boolean {
  if (filters.sources.length > 0) {
    const source = persona.source ?? persona.dimensions.source ?? "";
    if (!filters.sources.includes(source)) return false;
  }
  for (const [dimId, values] of Object.entries(filters.dimensionFilters)) {
    if (values.length === 0) continue;
    if (
      !values.some((value) => personaHasDimensionValue(persona, dimId, value))
    ) {
      return false;
    }
  }
  return true;
}

function isProduction1mRoot(pool: string): boolean {
  return pool === PERSONA_PRODUCTION_1M_POOL;
}

export interface PersonaStoreContentProps {
  enabled?: boolean;
  autoFocusSearch?: boolean;
  onOpenInPlayground?: (input: { pool: string; personaIds: string[] }) => void;
}

export function PersonaStoreContent({
  enabled = true,
  autoFocusSearch = false,
  onOpenInPlayground,
}: PersonaStoreContentProps) {
  const { t } = useI18n();
  const [pool, setPool] = useState(PERSONA_BENCH_POOL);
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<PersonaDimensionFilters>(
    emptyPersonaDimensionFilters(),
  );
  const [filterModalOpen, setFilterModalOpen] = useState(false);
  const [viewing, setViewing] = useState<PersonaPoolPersonaCard | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [previewPersonas, setPreviewPersonas] = useState<
    PersonaPoolPersonaCard[]
  >([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState(false);
  const [previewReady, setPreviewReady] = useState(false);
  const [previewReloadKey, setPreviewReloadKey] = useState(0);
  /** Idle browse: how many of the (matched) preview cards to render. */
  const [visibleCount, setVisibleCount] = useState(PERSONA_1M_VISIBLE_PAGE);
  const inputRef = useRef<HTMLInputElement>(null);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const previewGenRef = useRef(0);
  const deferredQuery = useDeferredValue(query.trim());
  const matchEnabled = enabled && shouldMatchAttributes(query.trim());
  const is1m = isProduction1mRoot(pool);
  const hitQueryReady = deferredQuery.length >= MIN_HIT_QUERY_LENGTH;
  /** 1M uses a background-filled 10k preview; search/filters run on that full window. */
  const previewMode = is1m;

  useEffect(() => {
    if (!autoFocusSearch) return;
    const id = window.setTimeout(() => inputRef.current?.focus(), 40);
    return () => window.clearTimeout(id);
  }, [autoFocusSearch]);

  useEffect(() => {
    if (!viewing) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setViewing(null);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [viewing]);

  // Fill the entire 10k preview in the background (not gated on scroll).
  // Scroll only controls how many cards are rendered in the DOM.
  useEffect(() => {
    previewGenRef.current += 1;
    const gen = previewGenRef.current;
    setPreviewPersonas([]);
    setPreviewError(false);
    setPreviewReady(false);
    setVisibleCount(PERSONA_1M_VISIBLE_PAGE);
    if (!enabled || !previewMode) {
      setPreviewLoading(false);
      return;
    }

    let cancelled = false;
    setPreviewLoading(true);
    void (async () => {
      const accumulated: PersonaPoolPersonaCard[] = [];
      try {
        for (
          let offset = 0;
          offset < PERSONA_1M_PREVIEW_CAP;
          offset += PERSONA_1M_PAGE
        ) {
          if (cancelled || gen !== previewGenRef.current) return;
          const pageLimit = Math.min(
            PERSONA_1M_PAGE,
            PERSONA_1M_PREVIEW_CAP - offset,
          );
          const page = await api.getPersonaPoolCards({
            pool,
            limit: pageLimit,
            offset,
            seed: 42,
          });
          if (cancelled || gen !== previewGenRef.current) return;
          accumulated.push(...page.personas);
          setPreviewPersonas(accumulated.slice());
          if (page.personas.length < pageLimit) break;
        }
        if (!cancelled && gen === previewGenRef.current) {
          setPreviewReady(true);
        }
      } catch {
        if (!cancelled && gen === previewGenRef.current) setPreviewError(true);
      } finally {
        if (!cancelled && gen === previewGenRef.current)
          setPreviewLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [enabled, pool, previewMode, previewReloadKey]);

  const datasetsQuery = useQuery({
    queryKey: ["persona-pool-datasets"],
    queryFn: () => api.listPersonaDatasets(),
    enabled,
    refetchOnWindowFocus: false,
    staleTime: 5 * 60 * 1000,
  });

  const catalogQuery = useQuery<PersonaPoolCatalog>({
    queryKey: ["persona-pool-catalog", pool],
    queryFn: () => api.getPersonaPoolCatalog(pool),
    enabled,
    refetchOnWindowFocus: false,
    staleTime: 5 * 60 * 1000,
  });

  const matchQuery = useQuery({
    queryKey: ["persona-pool-match-attributes", query.trim()],
    queryFn: () => api.matchPersonaAttributes(query.trim()),
    enabled: matchEnabled,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  const suggestions: PersonaMatchedAttribute[] =
    matchQuery.data?.attributes ?? [];

  const browseQuery = useQuery({
    queryKey: [
      "persona-pool-store",
      pool,
      is1m ? "preview-skip" : "all",
      PERSONA_POOL_PAGE,
    ],
    queryFn: async () => {
      if (is1m) {
        return {
          pool,
          personas: [] as PersonaPoolPersonaCard[],
          matchedCount: null as number | null,
          mode: "preview" as const,
        };
      }
      const all = await api.listAllPersonaPoolCards(PERSONA_POOL_PAGE, pool);
      return {
        pool: all.pool,
        personas: all.personas,
        matchedCount: null as number | null,
        mode: "all" as const,
      };
    },
    enabled: enabled && !previewMode,
    refetchOnWindowFocus: false,
    staleTime: 60_000,
  });

  const datasetOptions = useMemo<CockpitSelectOption[]>(() => {
    const listed = datasetsQuery.data?.datasets ?? [];
    const options: CockpitSelectOption[] = listed.map((item) => {
      const unavailable =
        item.kind === "production" && item.available === false;
      return {
        value: item.pool,
        label: item.label,
        meta: unavailable
          ? "download HF release / set MATRIX_PERSONA_1M_DIR"
          : item.count > 0
            ? t("catalog.personaStore.datasetPersonas", { count: item.count })
            : undefined,
      };
    });
    if (!options.some((opt) => opt.value === pool)) {
      options.unshift({
        value: pool,
        label: poolSlugLabel(pool),
      });
    }
    if (options.length === 0) {
      return [
        { value: PERSONA_BENCH_POOL, label: "matraix-persona-dev-sample" },
      ];
    }
    return options;
  }, [datasetsQuery.data?.datasets, pool, t]);

  const loaded = useMemo(
    () => (previewMode ? previewPersonas : (browseQuery.data?.personas ?? [])),
    [browseQuery.data?.personas, previewMode, previewPersonas],
  );
  const browseMode = previewMode
    ? "preview"
    : (browseQuery.data?.mode ?? "all");
  const personaSources = useMemo(() => {
    const fromCatalog =
      catalogQuery.data?.dimensionCategories?.personaSources ?? [];
    if (fromCatalog.length > 0) return fromCatalog;
    return [
      ...new Set(
        loaded
          .map((persona) => persona.source)
          .filter((s): s is string => Boolean(s)),
      ),
    ];
  }, [loaded, catalogQuery.data]);
  const poolCount = catalogQuery.data?.count ?? loaded.length;
  const emptyPoolState = personaPoolEmptyState(catalogQuery.data);
  const filterCount = activeFilterCount(filters);
  const searchingPreview = previewMode && hitQueryReady;
  const filteringPreview = previewMode && filterCount > 0;
  const queryingPreview = searchingPreview || filteringPreview;
  /** Search/filter wait for the full 10k window — not the currently rendered slice. */
  const previewQueryPending = queryingPreview && !previewReady && !previewError;

  const matchedPersonas = useMemo(() => {
    if (previewQueryPending) return [];
    const q = deferredQuery.toLowerCase();
    // Ignore 1–2 char queries — they match almost everything and thrash the UI.
    const activeQ = q.length >= MIN_HIT_QUERY_LENGTH ? q : "";
    return loaded.filter((persona) => {
      if (!matchesPersonaFilters(persona, filters)) return false;
      if (!activeQ) return true;
      if (suggestions.length > 0) {
        const matchesSuggestion = suggestions.some((attr) =>
          personaHasDimensionValue(persona, attr.dimensionId, attr.value),
        );
        if (matchesSuggestion) return true;
      }
      return personaMatchesQuery(persona, activeQ);
    });
  }, [deferredQuery, filters, loaded, previewQueryPending, suggestions]);

  // Idle / search: reveal cards on scroll from the in-memory 10k (DOM only).
  const personas = useMemo(() => {
    if (previewMode) return matchedPersonas.slice(0, visibleCount);
    return matchedPersonas;
  }, [matchedPersonas, previewMode, visibleCount]);

  // Reset visible window when the query/filter set changes.
  useEffect(() => {
    setVisibleCount(PERSONA_1M_VISIBLE_PAGE);
  }, [deferredQuery, filters, pool]);

  // Scroll reveals more cards (>100) from already-matched / already-fetched rows.
  useEffect(() => {
    if (!enabled || !previewMode) return;
    const sentinel = loadMoreRef.current;
    if (!sentinel) return;

    const root = nearestScrollRoot(sentinel);
    const matchCap = matchedPersonas.length;
    const maybeReveal = () => {
      setVisibleCount((prev) => {
        const cap = matchCap || PERSONA_1M_VISIBLE_PAGE;
        if (prev >= cap) return prev;
        return Math.min(cap, prev + PERSONA_1M_VISIBLE_PAGE);
      });
    };

    const onScroll = () => {
      const margin = 480;
      const rootBottom = root
        ? root.getBoundingClientRect().bottom
        : window.innerHeight;
      if (sentinel.getBoundingClientRect().top <= rootBottom + margin)
        maybeReveal();
    };

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) maybeReveal();
      },
      { root, rootMargin: "480px 0px", threshold: 0 },
    );
    observer.observe(sentinel);
    root?.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    return () => {
      observer.disconnect();
      root?.removeEventListener("scroll", onScroll);
    };
  }, [enabled, matchedPersonas.length, previewMode, visibleCount]);

  const dimIds = useMemo(
    () => catalogDimIdSet(catalogQuery.data),
    [catalogQuery.data],
  );

  const hitSummary = useMemo(() => {
    if (previewQueryPending) return [];
    if (!hitQueryReady && suggestions.length === 0) return [];
    // Chip counts must reflect the full 10k preview matches, not the DOM slice.
    return summarizeHitsAcrossPersonas(
      matchedPersonas,
      hitQueryReady ? deferredQuery : "",
      catalogQuery.data,
      suggestions,
    ).slice(0, 8);
  }, [
    catalogQuery.data,
    deferredQuery,
    hitQueryReady,
    matchedPersonas,
    previewQueryPending,
    suggestions,
  ]);

  const hitsByPersona = useMemo(() => {
    const map = new Map<string, ReturnType<typeof findPersonaSearchHits>>();
    if (!hitQueryReady && suggestions.length === 0) return map;
    for (const persona of personas) {
      map.set(
        persona.personaId,
        findPersonaSearchHits(
          persona,
          hitQueryReady ? deferredQuery : "",
          catalogQuery.data,
          suggestions,
          dimIds,
        ),
      );
    }
    return map;
  }, [
    catalogQuery.data,
    deferredQuery,
    dimIds,
    hitQueryReady,
    personas,
    suggestions,
  ]);

  function setSourceFilter(source: string | null) {
    setFilters((prev) => ({
      ...prev,
      sources: source ? [source] : [],
    }));
  }

  function handleDatasetChange(nextPool: string) {
    if (nextPool === pool) return;
    setPool(nextPool);
    setFilters(emptyPersonaDimensionFilters());
    setViewing(null);
    setQuery("");
    setSelectedIds([]);
  }

  function toggleSelected(personaId: string) {
    setSelectedIds((prev) =>
      prev.includes(personaId)
        ? prev.filter((id) => id !== personaId)
        : [...prev, personaId],
    );
  }

  function selectPersonaGroup(personaIds: string[]) {
    const unique = [...new Set(personaIds.filter(Boolean))];
    setSelectedIds(unique);
  }

  function handleOpenInPlayground() {
    if (!onOpenInPlayground || selectedIds.length === 0) return;
    onOpenInPlayground({ pool, personaIds: selectedIds });
  }

  const activeSource =
    filters.sources.length === 1
      ? filters.sources[0]
      : filters.sources.length === 0
        ? "all"
        : null;

  const previewLoadedCount = previewPersonas.length;
  const dimensionFilterCount = Object.values(filters.dimensionFilters).filter(
    (values) => values.length > 0,
  ).length;

  // Headline: dataset total when idle; match count over the full 10k once ready.
  const countingMatches = hitQueryReady || filterCount > 0;
  const countMain = previewQueryPending
    ? t("catalog.personaStore.loading")
    : countingMatches
      ? matchedPersonas.length.toLocaleString()
      : poolCount > 0
        ? poolCount.toLocaleString()
        : personas.length.toLocaleString();
  const countSuffix = previewQueryPending
    ? t("catalog.personaStore.loadingPreviewStatus")
    : countingMatches
      ? t("catalog.personaStore.matched")
      : t("catalog.personaStore.total");
  const browseBusy =
    (previewMode &&
      previewLoadedCount === 0 &&
      previewLoading &&
      !previewError) ||
    (!previewMode && browseQuery.isLoading && loaded.length === 0);
  const browseFailed = previewMode
    ? previewError && previewLoadedCount === 0
    : browseQuery.isError;
  const canRevealMore = previewMode && visibleCount < matchedPersonas.length;

  const loadMoreFooter =
    previewMode && !browseBusy && !browseFailed ? (
      <div
        ref={loadMoreRef}
        className="flex min-h-10 items-center justify-center py-4"
      >
        {previewQueryPending ? (
          <p className="text-[12px] text-text-dim">
            {t("catalog.personaStore.loadingPreview")}
          </p>
        ) : canRevealMore ? (
          <p className="text-[12px] text-text-dim">
            {t("catalog.personaStore.scrollMore")}
          </p>
        ) : null}
      </div>
    ) : null;

  return (
    <>
      <StudioGlassPanel className="relative z-20 mb-3 overflow-visible p-0">
        <div className="space-y-2.5 px-3 py-2.5 sm:px-3.5">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="w-full shrink-0 sm:min-w-[16rem] sm:max-w-[20rem] sm:flex-1 lg:max-w-[22rem]">
              <CockpitSelect
                label={t("catalog.personaStore.dataset")}
                inlineLabel
                labelClassName="w-[3.6rem] text-[11px]"
                value={pool}
                options={datasetOptions}
                showSelectedMeta={false}
                wideMenu
                wrapOptions
                onChange={handleDatasetChange}
              />
            </div>
            <PersonaSearchField
              value={query}
              onDebouncedChange={setQuery}
              inputRef={inputRef}
              placeholder={t("catalog.personaStore.searchPlaceholder")}
            />
            <button
              type="button"
              onClick={() => setFilterModalOpen(true)}
              className={`inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium transition-colors ${FOCUS_RING} ${
                dimensionFilterCount > 0
                  ? "bg-primary text-on-primary"
                  : "border border-outline/40 bg-surface/50 text-text-main hover:bg-surface-high"
              }`}
            >
              <Sym name="tune" size={15} />
              {t("catalog.personaStore.filters")}
              {dimensionFilterCount > 0 ? (
                <span className="rounded-full bg-on-primary/20 px-1.5 py-0.5 text-[10px] font-bold">
                  {dimensionFilterCount}
                </span>
              ) : null}
            </button>
            <div className="flex shrink-0 items-center gap-1.5 sm:pl-0.5">
              <span className="font-mono text-[15px] font-bold tabular-nums text-text-main">
                {countMain}
              </span>
              <span className="text-[12px] text-text-dim">{countSuffix}</span>
              {countingMatches &&
              matchedPersonas.length > 0 &&
              !previewQueryPending ? (
                <button
                  type="button"
                  onClick={() =>
                    selectPersonaGroup(
                      matchedPersonas.map((persona) => persona.personaId),
                    )
                  }
                  className={`ml-1 text-[12px] font-medium text-primary hover:underline ${FOCUS_RING}`}
                >
                  {t("catalog.personaStore.selectAllCount", {
                    count: matchedPersonas.length,
                  })}
                </button>
              ) : null}
            </div>
          </div>

          <div
            className="flex flex-wrap items-center gap-1.5"
            role="group"
            aria-label={t("catalog.personaStore.filterByDataSource")}
          >
            <span className="mr-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-text-dim">
              {t("catalog.personaStore.source")}
            </span>
            <SourceChip
              label={t("catalog.personaStore.all")}
              active={activeSource === "all"}
              onClick={() => setSourceFilter(null)}
            />
            {personaSources.map((source) => (
              <SourceChip
                key={source}
                label={source}
                active={activeSource === source}
                onClick={() => setSourceFilter(source)}
              />
            ))}
          </div>

          {suggestions.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-[0.06em] text-secondary">
                {t("catalog.personaStore.suggested")}
              </span>
              {suggestions.map((attr) => {
                const active = isSuggestionSelected(filters, attr);
                const label = (attr.label || attr.dimensionId).replace(
                  /_/g,
                  " ",
                );
                return (
                  <button
                    key={suggestionKey(attr)}
                    type="button"
                    title={
                      attr.evidence
                        ? t("catalog.personaStore.evidence", {
                            evidence: attr.evidence,
                          })
                        : undefined
                    }
                    onClick={() =>
                      setFilters((prev) =>
                        toggleSuggestionInFilters(prev, attr),
                      )
                    }
                    className={`inline-flex max-w-full items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium transition ${FOCUS_RING} ${
                      active
                        ? "bg-secondary/25 text-secondary ring-1 ring-secondary/50"
                        : "border border-secondary/35 bg-secondary/10 text-secondary hover:bg-secondary/15"
                    }`}
                  >
                    <span className="opacity-70">{label}</span>
                    <span className="opacity-40">·</span>
                    <span className="truncate">{attr.value}</span>
                  </button>
                );
              })}
              <button
                type="button"
                onClick={() =>
                  setFilters((prev) => applyAllSuggestions(prev, suggestions))
                }
                className={`text-[11px] font-medium text-primary hover:underline ${FOCUS_RING}`}
              >
                {t("catalog.personaStore.selectAll")}
              </button>
            </div>
          ) : null}

          {hitSummary.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-[0.06em] text-primary">
                {t("catalog.personaStore.matches")}
              </span>
              {hitSummary.map((hit) => {
                const active = (
                  filters.dimensionFilters[hit.dimensionId] ?? []
                ).includes(hit.value);
                return (
                  <button
                    key={`${hit.dimensionId}:${hit.value}`}
                    type="button"
                    title={
                      active
                        ? t("catalog.personaStore.clearFilter", {
                            label: hit.label,
                            value: hit.value,
                          })
                        : t("catalog.personaStore.selectAllWith", {
                            count: hit.personaCount,
                            label: hit.label,
                            value: hit.value,
                          })
                    }
                    onClick={() => {
                      const turningOn = !active;
                      setFilters((prev) =>
                        toggleSuggestionInFilters(prev, {
                          dimensionId: hit.dimensionId,
                          label: hit.label,
                          value: hit.value,
                        }),
                      );
                      if (turningOn) {
                        // Auto-select the whole attribute group for Playground handoff.
                        selectPersonaGroup(
                          matchedPersonas
                            .filter((persona) =>
                              personaHasDimensionValue(
                                persona,
                                hit.dimensionId,
                                hit.value,
                              ),
                            )
                            .map((persona) => persona.personaId),
                        );
                      }
                    }}
                    className={`inline-flex max-w-full items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium transition ${FOCUS_RING} ${
                      active
                        ? "bg-primary text-on-primary"
                        : "border border-primary/30 bg-primary/10 text-primary hover:bg-primary/15"
                    }`}
                  >
                    <span className="opacity-70">{hit.label}</span>
                    <span className="opacity-40">·</span>
                    <span className="max-w-[8rem] truncate">{hit.value}</span>
                    <span
                      className={`rounded-full px-1 py-0.5 font-mono text-[10px] font-bold ${
                        active ? "bg-on-primary/20" : "bg-primary/15"
                      }`}
                    >
                      {hit.personaCount}
                    </span>
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>
      </StudioGlassPanel>

      {browseBusy ? (
        <CatalogSkeleton />
      ) : browseFailed ? (
        <CatalogError
          onRetry={() => {
            if (previewMode) {
              setPreviewError(false);
              setPreviewReloadKey((key) => key + 1);
              void catalogQuery.refetch();
            } else {
              void browseQuery.refetch();
              void catalogQuery.refetch();
            }
          }}
        />
      ) : matchedPersonas.length === 0 ? (
        <>
          <CatalogEmpty
            query={query.trim()}
            hasFilters={filterCount > 0}
            emptyPoolMessage={
              previewQueryPending
                ? t("catalog.personaStore.loadingPreviewCount", {
                    total: PERSONA_1M_PREVIEW_CAP,
                    loaded: previewLoadedCount,
                  })
                : is1m &&
                    browseMode === "preview" &&
                    (query.trim() || filterCount > 0)
                  ? t("catalog.personaStore.noPreviewHits")
                  : t("catalog.personaStore.emptyPool", {
                      pool:
                        emptyPoolState.pool ??
                        t("catalog.personaStore.unnamedPool"),
                    })
            }
          />
          {loadMoreFooter}
        </>
      ) : (
        <>
          <div className="grid grid-cols-1 items-stretch gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {personas.map((persona, i) => (
              <div
                key={persona.personaId}
                className="rise-in h-full"
                style={{ animationDelay: `${Math.min(i, 6) * 30}ms` }}
              >
                <BenchPersonaCard
                  persona={persona}
                  hits={hitsByPersona.get(persona.personaId) ?? []}
                  selected={selectedIds.includes(persona.personaId)}
                  onToggle={() => toggleSelected(persona.personaId)}
                  onOpenDetail={() => setViewing(persona)}
                />
              </div>
            ))}
          </div>
          {loadMoreFooter}
        </>
      )}

      {queryingPreview &&
      !previewQueryPending &&
      matchedPersonas.length > personas.length ? (
        <p className="mt-3 text-center text-[12px] text-text-dim">
          {t("catalog.personaStore.showing", {
            shown: personas.length,
            total: matchedPersonas.length,
          })}
        </p>
      ) : null}

      {viewing
        ? createPortal(
            <div className="fixed inset-0 z-[70] flex items-center justify-center p-4 sm:p-6">
              <button
                type="button"
                className="absolute inset-0 bg-surface-dim/75 backdrop-blur-sm"
                aria-label={t("catalog.personaStore.closeDetails")}
                onClick={() => setViewing(null)}
              />
              <div className="relative z-10 flex h-[min(88vh,760px)] w-full max-w-lg min-h-0">
                <BenchPersonaDetailPanel
                  persona={viewing}
                  pool={browseQuery.data?.pool ?? pool}
                  onClose={() => setViewing(null)}
                  onUse={(persona) => {
                    setSelectedIds((prev) =>
                      prev.includes(persona.personaId)
                        ? prev
                        : [...prev, persona.personaId],
                    );
                    setViewing(null);
                  }}
                  useLabel={t("catalog.personaStore.addToSelection")}
                  className="glass-panel-strong h-full min-h-0 w-full p-4 shadow-2xl sm:p-5"
                />
              </div>
            </div>,
            document.body,
          )
        : null}

      <PersonaFilterModal
        open={filterModalOpen}
        catalog={catalogQuery.data ?? null}
        filters={filters}
        onClose={() => setFilterModalOpen(false)}
        onConfirm={(next) => {
          setFilters(next);
          setFilterModalOpen(false);
        }}
      />

      {selectedIds.length > 0
        ? createPortal(
            <div className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex justify-center p-4 pb-5">
              <div className="pointer-events-auto glass-panel-strong flex w-full max-w-xl flex-wrap items-center justify-between gap-3 rounded-xl border border-primary/30 px-4 py-3 shadow-2xl">
                <div className="min-w-0">
                  <p className="text-[13px] font-semibold text-text-main">
                    {t("catalog.personaStore.selected", {
                      count: selectedIds.length,
                    })}
                  </p>
                  <p className="text-[12px] text-text-dim">
                    {t("catalog.personaStore.openHint")}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setSelectedIds([])}
                    className={`rounded-lg px-3 py-1.5 text-[13px] font-medium text-text-variant hover:bg-surface-high hover:text-text-main ${FOCUS_RING}`}
                  >
                    {t("catalog.personaStore.clearSelection")}
                  </button>
                  <button
                    type="button"
                    onClick={handleOpenInPlayground}
                    disabled={!onOpenInPlayground}
                    className={`inline-flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-1.5 text-[13px] font-semibold text-on-primary disabled:opacity-50 ${FOCUS_RING}`}
                  >
                    <Sym name="play_arrow" size={16} />
                    {t("catalog.taskGallery.openPlayground")}
                  </button>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}
      {selectedIds.length > 0 ? <div className="h-20" aria-hidden /> : null}
    </>
  );
}

function SourceChip({
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
      className={`inline-flex h-7 items-center rounded-full px-2.5 text-[11px] font-medium transition-colors ${FOCUS_RING} ${
        active
          ? "bg-text-main text-surface-lowest"
          : "border border-outline/35 bg-surface/40 text-text-variant hover:border-outline/60 hover:text-text-main"
      }`}
    >
      {label}
    </button>
  );
}

function CatalogSkeleton() {
  return (
    <div
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
      aria-hidden
    >
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="glass-panel rounded-xl p-4">
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

function CatalogEmpty({
  query,
  hasFilters,
  emptyPoolMessage,
}: {
  query: string;
  hasFilters: boolean;
  emptyPoolMessage: string;
}) {
  const { t } = useI18n();

  return (
    <div className="glass-panel rise-in flex flex-col items-center rounded-xl px-4 py-16 text-center">
      <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-lg border border-dashed border-outline/50 bg-surface/50">
        <Sym name="search_off" size={26} className="text-text-dim" />
      </div>
      <p className="font-display text-[15px] font-semibold text-text-main">
        {query || hasFilters
          ? t("catalog.personaStore.noMatches")
          : t("catalog.personaStore.noPersonasYet")}
      </p>
      <p className="mt-1 max-w-[360px] text-[14px] leading-snug text-text-variant">
        {query
          ? t("catalog.personaStore.nothingMatches", { query })
          : hasFilters
            ? t("catalog.personaStore.noFilterMatches")
            : emptyPoolMessage}
      </p>
    </div>
  );
}

function CatalogError({ onRetry }: { onRetry: () => void }) {
  const { t } = useI18n();

  return (
    <div className="glass-panel rise-in flex flex-col items-center rounded-xl px-4 py-16 text-center">
      <p className="font-display text-[15px] font-semibold text-text-main">
        {t("catalog.personaStore.couldNotLoad")}
      </p>
      <button
        type="button"
        onClick={onRetry}
        className={`mt-3 rounded-md bg-primary px-3 py-1.5 text-[13px] font-medium text-on-primary ${FOCUS_RING}`}
      >
        {t("catalog.personaStore.retry")}
      </button>
    </div>
  );
}
