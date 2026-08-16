import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";

import { useI18n } from "@/i18n/I18nProvider";
import { api } from "@/lib/api";
import type {
  PersonaMatchedAttribute,
  PersonaPoolCatalog,
  PersonaPoolDimensionGroup,
  PersonaPoolDimensionOption,
  PersonaPoolDimensionSubgroup,
} from "@/lib/types";
import { FOCUS_RING, Sym } from "../cockpitShared";
import {
  applyAllSuggestions,
  isSuggestionSelected,
  shouldMatchAttributes,
  suggestionKey,
  toggleSuggestionInFilters,
} from "./personaAttributeMatch";
import {
  activeFilterCount,
  type PersonaDimensionFilters,
} from "./personaSamplingTypes";

export interface PersonaFilterModalProps {
  open: boolean;
  catalog: PersonaPoolCatalog | null;
  filters: PersonaDimensionFilters;
  stratifyMode?: boolean;
  fields?: string[];
  onFieldsChange?: (fields: string[]) => void;
  onClose: () => void;
  onConfirm: (filters: PersonaDimensionFilters) => void;
}

function poolLabel(pool: string | undefined): string {
  if (!pool) return "";
  return pool.split("/").filter(Boolean).pop() || pool;
}

function dimLabel(dim: PersonaPoolDimensionOption): string {
  return (dim.label || dim.id.replace(/_/g, " ")).trim();
}

function findDimensionLabel(
  catalog: PersonaPoolCatalog | null,
  dimId: string,
): string {
  const groups = catalog?.dimensionCategories?.devProfile?.groups ?? [];
  for (const group of groups) {
    for (const dim of group.dimensions ?? []) {
      if (dim.id === dimId) return dimLabel(dim);
    }
    for (const sub of group.subgroups ?? []) {
      for (const dim of sub.dimensions ?? []) {
        if (dim.id === dimId) return dimLabel(dim);
      }
    }
  }
  return dimId.replace(/_/g, " ");
}

function matchesQuery(text: string, query: string): boolean {
  if (!query) return true;
  return text.toLowerCase().includes(query);
}

function dimensionMatchesQuery(
  dim: PersonaPoolDimensionOption,
  query: string,
): boolean {
  if (!query) return true;
  if (matchesQuery(`${dimLabel(dim)} ${dim.id}`, query)) return true;
  return (dim.values ?? []).some((value) => matchesQuery(value, query));
}

function filterDimensionValues(
  dim: PersonaPoolDimensionOption,
  query: string,
): string[] {
  const values = dim.values ?? [];
  if (!query) return values;
  if (matchesQuery(`${dimLabel(dim)} ${dim.id}`, query)) return values;
  return values.filter((value) => matchesQuery(value, query));
}

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

export function PersonaFilterModal({
  open,
  catalog,
  filters,
  stratifyMode = false,
  fields = [],
  onFieldsChange,
  onClose,
  onConfirm,
}: PersonaFilterModalProps) {
  const { t } = useI18n();
  const [draft, setDraft] = useState(filters);
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const [expandedSubgroup, setExpandedSubgroup] = useState<string | null>(null);
  const [expandedDim, setExpandedDim] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounced(query.trim(), 280);
  const matchEnabled = open && shouldMatchAttributes(debouncedQuery);

  const matchQuery = useQuery({
    queryKey: ["persona-pool-match-attributes", debouncedQuery],
    queryFn: () => api.matchPersonaAttributes(debouncedQuery),
    enabled: matchEnabled,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  const suggestions: PersonaMatchedAttribute[] =
    matchQuery.data?.attributes ?? [];

  useEffect(() => {
    if (open) {
      setDraft(filters);
      setQuery("");
      setExpandedGroup(null);
      setExpandedSubgroup(null);
      setExpandedDim(null);
    }
  }, [open, filters]);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const sources = useMemo(() => {
    const fromCategories = catalog?.dimensionCategories?.personaSources ?? [];
    if (fromCategories.length > 0) return fromCategories;
    return Object.keys(catalog?.sourceCounts ?? {});
  }, [catalog]);

  const groups = catalog?.dimensionCategories?.devProfile?.groups ?? [];
  const dimensionCount =
    catalog?.dimensionCategories?.devProfile?.dimensionCount;
  const normalizedQuery = query.trim().toLowerCase();

  const visibleGroups = useMemo(() => {
    if (!normalizedQuery) return groups;
    const next: PersonaPoolDimensionGroup[] = [];
    for (const group of groups) {
      const subgroups = group.subgroups ?? [];
      if (subgroups.length > 0) {
        const matchedSubs: PersonaPoolDimensionSubgroup[] = [];
        for (const sub of subgroups) {
          const dims = (sub.dimensions ?? []).filter((dim) =>
            dimensionMatchesQuery(dim, normalizedQuery),
          );
          if (dims.length === 0) continue;
          matchedSubs.push({
            ...sub,
            dimensions: dims,
            dimensionIds: dims.map((d) => d.id),
          });
        }
        if (matchedSubs.length === 0) continue;
        next.push({
          ...group,
          subgroups: matchedSubs,
          dimensions: matchedSubs.flatMap((s) => s.dimensions),
          dimensionIds: matchedSubs.flatMap((s) => s.dimensionIds),
        });
        continue;
      }
      const dims = (group.dimensions ?? []).filter((dim) =>
        dimensionMatchesQuery(dim, normalizedQuery),
      );
      if (dims.length === 0) continue;
      next.push({
        ...group,
        dimensions: dims,
        dimensionIds: dims.map((d) => d.id),
      });
    }
    return next;
  }, [groups, normalizedQuery]);

  const selectedChips = useMemo(() => {
    const chips: Array<{
      key: string;
      dimId: string;
      label: string;
      value: string;
    }> = [];
    for (const source of draft.sources) {
      chips.push({
        key: `source:${source}`,
        dimId: "source",
        label: t("personaSetup.filters.source"),
        value: source,
      });
    }
    for (const [dimId, values] of Object.entries(draft.dimensionFilters)) {
      const label = findDimensionLabel(catalog, dimId);
      for (const value of values) {
        chips.push({ key: `${dimId}:${value}`, dimId, label, value });
      }
    }
    return chips;
  }, [catalog, draft, t]);

  if (!open) return null;

  const toggleSource = (source: string) => {
    setDraft((prev) => ({
      ...prev,
      sources: prev.sources.includes(source)
        ? prev.sources.filter((item) => item !== source)
        : [...prev.sources, source],
    }));
  };

  const toggleDimensionValue = (dimId: string, value: string) => {
    setDraft((prev) => {
      const current = prev.dimensionFilters[dimId] ?? [];
      const nextValues = current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value];
      const nextFilters = { ...prev.dimensionFilters };
      if (nextValues.length === 0) delete nextFilters[dimId];
      else nextFilters[dimId] = nextValues;
      return { ...prev, dimensionFilters: nextFilters };
    });
  };

  const removeChip = (chip: {
    key: string;
    dimId: string;
    label: string;
    value: string;
  }) => {
    if (chip.dimId === "source") {
      setDraft((prev) => ({
        ...prev,
        sources: prev.sources.filter((item) => item !== chip.value),
      }));
      return;
    }
    setDraft((prev) => {
      const current = prev.dimensionFilters[chip.dimId] ?? [];
      const nextValues = current.filter((item) => item !== chip.value);
      const nextFilters = { ...prev.dimensionFilters };
      if (nextValues.length === 0) delete nextFilters[chip.dimId];
      else nextFilters[chip.dimId] = nextValues;
      return { ...prev, dimensionFilters: nextFilters };
    });
  };

  const toggleStratifyField = (dimId: string) => {
    if (!onFieldsChange) return;
    const next = fields.includes(dimId)
      ? fields.filter((item) => item !== dimId)
      : [...fields, dimId];
    onFieldsChange(next);
  };

  const renderDimension = (dim: PersonaPoolDimensionOption) => {
    const visibleValues = filterDimensionValues(dim, normalizedQuery);
    const dimOpen =
      expandedDim === dim.id ||
      (Boolean(normalizedQuery) && visibleValues.length > 0);
    const selected = draft.dimensionFilters[dim.id] ?? [];
    const stratified = fields.includes(dim.id);
    return (
      <div
        key={dim.id}
        className="rounded-md border border-outline/30 bg-surface/20"
      >
        <button
          type="button"
          onClick={() =>
            setExpandedDim(dimOpen && !normalizedQuery ? null : dim.id)
          }
          className={`flex w-full items-center justify-between gap-2 px-2.5 py-2 text-left text-[13px] ${FOCUS_RING}`}
        >
          <span className={selected.length ? "text-primary" : "text-text-main"}>
            {dimLabel(dim)}
            {selected.length > 0 ? ` · ${selected.length}` : ""}
          </span>
          <div className="flex items-center gap-2">
            {stratifyMode && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleStratifyField(dim.id);
                }}
                className={`rounded-full border px-2 py-0.5 text-[11px] ${
                  stratified
                    ? "border-secondary/40 bg-secondary/10 text-secondary"
                    : "border-outline/40 text-text-dim"
                }`}
              >
                {t("personaSetup.filters.stratify")}
              </button>
            )}
            <Sym
              name={dimOpen ? "expand_less" : "expand_more"}
              size={16}
              className="text-text-dim"
            />
          </div>
        </button>
        {dimOpen && (
          <div className="flex flex-wrap gap-1.5 border-t border-outline/20 px-2.5 py-2">
            {visibleValues.map((value) => {
              const active = selected.includes(value);
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => toggleDimensionValue(dim.id, value)}
                  className={`rounded-full px-2.5 py-1 text-[12px] ${FOCUS_RING} ${
                    active
                      ? "glass-tile glass-tile--active text-primary"
                      : "glass-tile glass-tile--hover text-text-variant"
                  }`}
                >
                  {value}
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  const showEmptyTree =
    Boolean(normalizedQuery) &&
    visibleGroups.length === 0 &&
    suggestions.length === 0 &&
    !matchQuery.isFetching;

  return createPortal(
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4 sm:p-6">
      <button
        type="button"
        className="absolute inset-0 bg-surface-dim/75 backdrop-blur-sm"
        aria-label={t("personaSetup.filters.close")}
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="persona-filter-modal-title"
        className="glass-panel-strong relative z-10 flex max-h-[min(88vh,760px)] w-full max-w-4xl flex-col overflow-hidden rounded-xl shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-outline/40 px-5 py-4">
          <div>
            <p className="hud text-[11px] text-primary">
              {poolLabel(catalog?.pool) ||
                t("personaSetup.filters.defaultPool")}
            </p>
            <h2
              id="persona-filter-modal-title"
              className="font-display text-[18px] font-semibold text-text-main"
            >
              {t("personaSetup.filters.title")}
            </h2>
            {typeof dimensionCount === "number" && dimensionCount > 0 ? (
              <p className="mt-0.5 text-[12px] text-text-dim">
                {t("personaSetup.filters.dimensionCount", {
                  count: dimensionCount,
                })}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("personaSetup.filters.close")}
            className={`rounded-md p-2 text-text-variant hover:bg-surface-high ${FOCUS_RING}`}
          >
            <Sym name="close" size={20} />
          </button>
        </div>

        <div className="custom-scrollbar flex-1 overflow-y-auto px-5 py-4">
          <p className="mb-2 text-[13px] text-text-variant">
            {t("personaSetup.filters.provenance")}
          </p>
          <div className="mb-5 flex flex-wrap gap-2">
            {sources.map((source) => {
              const active = draft.sources.includes(source);
              const count = catalog?.sourceCounts?.[source];
              return (
                <button
                  key={source}
                  type="button"
                  onClick={() => toggleSource(source)}
                  className={`rounded-full px-3 py-1.5 text-[13px] transition ${FOCUS_RING} ${
                    active
                      ? "glass-tile glass-tile--active text-primary"
                      : "glass-tile glass-tile--hover text-text-variant"
                  }`}
                >
                  {source}
                  {typeof count === "number"
                    ? ` · ${count.toLocaleString()}`
                    : ""}
                </button>
              );
            })}
          </div>

          <div className="mb-2 flex items-center justify-between gap-3">
            <p className="text-[13px] text-text-variant">
              {t("personaSetup.filters.profileDimensions")}
            </p>
            <label className="relative min-w-0 flex-1 max-w-md">
              <Sym
                name="search"
                size={16}
                className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-text-dim"
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t("personaSetup.filters.searchPlaceholder")}
                className={`h-8 w-full rounded-md border border-outline/50 bg-field pl-8 pr-2 text-[13px] text-text-main placeholder:text-text-dim ${FOCUS_RING}`}
              />
            </label>
          </div>

          {suggestions.length > 0 ? (
            <div className="mb-4 rounded-lg border border-outline/30 bg-surface/30 px-3 py-2.5">
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="text-[12px] text-text-variant">
                  {t("personaSetup.filters.suggestedAttributes", {
                    count: suggestions.length,
                  })}
                </p>
                <button
                  type="button"
                  onClick={() =>
                    setDraft((prev) => applyAllSuggestions(prev, suggestions))
                  }
                  className={`rounded-md px-2 py-1 text-[11px] text-primary hover:bg-primary/10 ${FOCUS_RING}`}
                >
                  {t("personaSetup.filters.selectAll")}
                </button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {suggestions.map((attr) => {
                  const active = isSuggestionSelected(draft, attr);
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
                          ? t("personaSetup.filters.evidence", {
                              value: attr.evidence,
                            })
                          : undefined
                      }
                      onClick={() =>
                        setDraft((prev) =>
                          toggleSuggestionInFilters(prev, attr),
                        )
                      }
                      className={`rounded-full px-2.5 py-1 text-[12px] ${FOCUS_RING} ${
                        active
                          ? "glass-tile glass-tile--active text-primary"
                          : "glass-tile glass-tile--hover text-text-variant"
                      }`}
                    >
                      <span className="text-text-dim">{label}</span>
                      <span className="mx-1 text-text-dim">·</span>
                      {attr.value}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}

          <div className="space-y-2">
            {showEmptyTree ? (
              <p className="rounded-lg border border-dashed border-outline/40 px-3 py-4 text-center text-[13px] text-text-dim">
                {t("personaSetup.filters.noAttributes", {
                  query: query.trim(),
                })}
              </p>
            ) : null}
            {visibleGroups.map((group) => {
              const groupOpen =
                expandedGroup === group.id || Boolean(normalizedQuery);
              const subgroups = group.subgroups ?? [];
              return (
                <div
                  key={group.id}
                  className="rounded-lg border border-outline/30"
                >
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedGroup(
                        groupOpen && !normalizedQuery ? null : group.id,
                      )
                    }
                    className={`flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-[13px] font-medium ${FOCUS_RING}`}
                  >
                    <span>{group.label}</span>
                    <Sym
                      name={groupOpen ? "expand_less" : "expand_more"}
                      size={18}
                      className="text-text-dim"
                    />
                  </button>
                  {groupOpen ? (
                    <div className="space-y-2 border-t border-outline/20 px-2.5 py-2">
                      {subgroups.length > 0
                        ? subgroups.map((sub) => {
                            const subOpen =
                              expandedSubgroup === sub.id ||
                              Boolean(normalizedQuery);
                            return (
                              <div
                                key={sub.id}
                                className="rounded-md border border-outline/20"
                              >
                                <button
                                  type="button"
                                  onClick={() =>
                                    setExpandedSubgroup(
                                      subOpen && !normalizedQuery
                                        ? null
                                        : sub.id,
                                    )
                                  }
                                  className={`flex w-full items-center justify-between gap-2 px-2.5 py-2 text-left text-[12px] text-text-variant ${FOCUS_RING}`}
                                >
                                  <span>{sub.label}</span>
                                  <Sym
                                    name={
                                      subOpen ? "expand_less" : "expand_more"
                                    }
                                    size={16}
                                    className="text-text-dim"
                                  />
                                </button>
                                {subOpen ? (
                                  <div className="space-y-1.5 border-t border-outline/15 px-2 py-2">
                                    {(sub.dimensions ?? []).map(
                                      renderDimension,
                                    )}
                                  </div>
                                ) : null}
                              </div>
                            );
                          })
                        : (group.dimensions ?? []).map(renderDimension)}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>

        <div className="border-t border-outline/40 bg-surface/40 px-5 py-4">
          <div className="mb-3 space-y-2.5">
            {selectedChips.length > 0 ? (
              <div>
                <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-text-dim">
                  {t("personaSetup.filters.activeCount", {
                    count: activeFilterCount(draft),
                  })}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {selectedChips.map((chip) => (
                    <button
                      key={chip.key}
                      type="button"
                      onClick={() => removeChip(chip)}
                      className="glass-tile glass-tile--active inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[12px] text-primary"
                    >
                      <span className="text-text-dim">{chip.label}:</span>{" "}
                      {chip.value}
                      <Sym name="close" size={12} />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-[13px] text-text-dim">
                {t("personaSetup.filters.noFilters")}
              </p>
            )}

            {stratifyMode ? (
              <div>
                <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-text-dim">
                  {t("personaSetup.filters.stratifyAxes", {
                    count: fields.length,
                  })}
                </p>
                {fields.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {fields.map((field) => {
                      const label = findDimensionLabel(catalog, field);
                      return (
                        <button
                          key={field}
                          type="button"
                          onClick={() => toggleStratifyField(field)}
                          className="inline-flex items-center gap-1 rounded-full border border-secondary/40 bg-secondary/10 px-2.5 py-1 text-[12px] text-secondary"
                        >
                          <span className="text-[10px] uppercase tracking-wide text-secondary/80">
                            {t("personaSetup.filters.stratify")}
                          </span>
                          {label}
                          <Sym name="close" size={12} />
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-[13px] text-text-dim">
                    {t("personaSetup.filters.stratifyHint")}
                  </p>
                )}
              </div>
            ) : null}
          </div>

          <div className="flex items-center justify-between gap-3">
            <p className="text-[13px] text-text-variant">
              {t("personaSetup.filters.filterCount", {
                count: activeFilterCount(draft),
              })}
              {stratifyMode ? (
                <>
                  {" "}
                  ·{" "}
                  {t("personaSetup.filters.stratifyAxisCount", {
                    count: fields.length,
                  })}
                </>
              ) : null}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onClose}
                className={`rounded-md border border-outline px-3 py-2 text-[14px] text-text-variant ${FOCUS_RING}`}
              >
                {t("personaSetup.common.cancel")}
              </button>
              <button
                type="button"
                onClick={() => {
                  onConfirm(draft);
                  onClose();
                }}
                className={`rounded-md bg-primary px-4 py-2 text-[14px] font-medium text-on-primary ${FOCUS_RING}`}
              >
                {t("personaSetup.filters.apply")}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
