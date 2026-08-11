/**
 * Persona group builder for Harbor batch launch — filters, cohorts, sample preview.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import type { PersonaCohortDetail, PersonaPoolCatalog } from "@/lib/types";
import { useI18n } from "@/i18n/I18nProvider";
import { FOCUS_RING } from "./cockpitShared";

export interface PersonaGroupFilters {
  sources: string[];
  dimensionFilters: Record<string, string>;
}

export interface PersonaGroupBuilderProps {
  sampleSize: number;
  seed?: number;
  filters: PersonaGroupFilters;
  selectedCohortId?: string | null;
  onFiltersChange: (next: PersonaGroupFilters) => void;
  onSeedChange?: (seed: number) => void;
  onSampleSizeChange?: (sampleSize: number) => void;
  onCohortChange?: (cohortId: string | null) => void;
}

export function emptyPersonaGroupFilters(): PersonaGroupFilters {
  return { sources: [], dimensionFilters: {} };
}

function filtersFromCohort(cohort: PersonaCohortDetail): PersonaGroupFilters {
  return {
    sources: [...(cohort.sources ?? [])],
    dimensionFilters: { ...(cohort.dimensionFilters ?? {}) },
  };
}

export function PersonaGroupBuilder({
  sampleSize,
  seed = 42,
  filters,
  selectedCohortId = null,
  onFiltersChange,
  onSeedChange,
  onSampleSizeChange,
  onCohortChange,
}: PersonaGroupBuilderProps) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [matchedCount, setMatchedCount] = useState<number | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveId, setSaveId] = useState("");
  const [saveName, setSaveName] = useState("");
  const [saveKind, setSaveKind] = useState<"recipe" | "frozen">("recipe");
  const [saveError, setSaveError] = useState<string | null>(null);

  const catalogQuery = useQuery({
    queryKey: ["persona-pool-catalog"],
    queryFn: () => api.getPersonaPoolCatalog(),
    staleTime: 60_000,
  });

  const cohortsQuery = useQuery({
    queryKey: ["persona-pool-cohorts"],
    queryFn: () => api.listPersonaCohorts(),
    staleTime: 30_000,
  });

  const catalog = catalogQuery.data as PersonaPoolCatalog | undefined;
  const cohorts = cohortsQuery.data?.cohorts ?? [];
  const sources = catalog?.dimensionCategories?.personaSources ?? [];
  const groups = catalog?.dimensionCategories?.devProfile?.groups ?? [];

  const activeFilterCount =
    filters.sources.length +
    Object.values(filters.dimensionFilters).filter((value) => value.trim()).length;

  const previewSample = useCallback(async () => {
    const dimensionFilters = Object.fromEntries(
      Object.entries(filters.dimensionFilters).filter(([, value]) => value.trim()),
    );
    try {
      const result = await api.samplePersonaPool({
        sampleSize: Math.min(sampleSize, 1),
        seed,
        sources: filters.sources.length ? filters.sources : undefined,
        dimensionFilters: Object.keys(dimensionFilters).length ? dimensionFilters : undefined,
      });
      setMatchedCount(result.matchedCount);
      setPreviewError(null);
    } catch (err) {
      setMatchedCount(null);
      setPreviewError(err instanceof ApiError ? err.message : t("personaGroups.previewError", "Could not preview sample."));
    }
  }, [filters.dimensionFilters, filters.sources, sampleSize, seed]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void previewSample();
    }, 300);
    return () => window.clearTimeout(handle);
  }, [previewSample]);

  const saveMutation = useMutation({
    mutationFn: () => {
      const dimensionFilters = Object.fromEntries(
        Object.entries(filters.dimensionFilters).filter(([, value]) => value.trim()),
      );
      return api.savePersonaCohort({
        cohortId: saveId.trim(),
        name: saveName.trim() || saveId.trim(),
        kind: saveKind,
        seed,
        sampleSize,
        sources: filters.sources.length ? filters.sources : undefined,
        dimensionFilters: Object.keys(dimensionFilters).length ? dimensionFilters : undefined,
      });
    },
    onSuccess: (cohort) => {
      setSaveError(null);
      setSaveOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["persona-pool-cohorts"] });
      onCohortChange?.(cohort.cohortId);
    },
    onError: (err: unknown) => {
      setSaveError(err instanceof ApiError ? err.message : t("personaGroups.saveError", "Could not save cohort."));
    },
  });

  const loadCohort = useCallback(
    async (cohortId: string) => {
      if (!cohortId) {
        onCohortChange?.(null);
        return;
      }
      try {
        const cohort = await api.getPersonaCohort(cohortId);
        onFiltersChange(filtersFromCohort(cohort));
        onSeedChange?.(cohort.seed);
        onSampleSizeChange?.(cohort.sampleSize);
        onCohortChange?.(cohort.cohortId);
      } catch (err) {
        setPreviewError(err instanceof ApiError ? err.message : t("personaGroups.loadError", "Could not load cohort."));
      }
    },
    [onCohortChange, onFiltersChange, onSampleSizeChange, onSeedChange],
  );

  const toggleSource = (source: string) => {
    onCohortChange?.(null);
    const next = filters.sources.includes(source)
      ? filters.sources.filter((item) => item !== source)
      : [...filters.sources, source];
    onFiltersChange({ ...filters, sources: next });
  };

  const setDimensionFilter = (dimensionId: string, value: string) => {
    onCohortChange?.(null);
    const next = { ...filters.dimensionFilters };
    if (!value.trim()) delete next[dimensionId];
    else next[dimensionId] = value;
    onFiltersChange({ ...filters, dimensionFilters: next });
  };

  const poolSummary = useMemo(() => {
    if (!catalog) return null;
    return `${catalog.count} ${t("personaGroups.personas", "personas")} · ${t("personaGroups.smoke", "smoke")} ${catalog.smokePersonaId ?? "—"}`;
  }, [catalog, t]);

  return (
    <div className="mt-3 rounded-md border border-outline/70 bg-surface px-3 py-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[14px] font-medium text-text-main">{t("personaGroups.title", "Persona group")}</p>
        {poolSummary && <p className="font-mono text-[13px] text-text-dim">{poolSummary}</p>}
      </div>

      <div className="mb-3 flex flex-wrap items-end gap-2">
        <label className="flex min-w-[12rem] flex-1 flex-col gap-1 text-[13px] text-text-variant">
          {t("personaGroups.savedCohort", "Saved cohort")}
          <select
            value={selectedCohortId ?? ""}
            onChange={(e) => void loadCohort(e.target.value)}
            className="h-8 rounded border border-outline bg-surface px-2 text-[14px] text-text-main"
          >
            <option value="">{t("personaGroups.noneAdHoc", "(none — ad hoc filters)")}</option>
            {cohorts.map((cohort) => (
              <option key={cohort.cohortId} value={cohort.cohortId}>
                {cohort.name} · {cohort.kind} · n={cohort.sampleSize}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => {
            setSaveOpen((open) => !open);
            setSaveError(null);
          }}
          className={`h-8 rounded-md border border-outline px-3 text-[13px] text-text-main hover:bg-surface-low ${FOCUS_RING}`}
        >
          {saveOpen ? t("personaGroups.cancelSave", "Cancel save") : t("personaGroups.saveCohort", "Save cohort…")}
        </button>
      </div>

      {saveOpen && (
        <div className="mb-3 grid gap-2 rounded border border-outline/60 p-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-[13px] text-text-variant">
            {t("personaGroups.cohortId", "Cohort ID")}
            <input
              value={saveId}
              onChange={(e) => setSaveId(e.target.value)}
              placeholder="price-sensitive-nemotron"
              className="h-8 rounded border border-outline bg-surface px-2 font-mono text-[14px]"
            />
          </label>
          <label className="flex flex-col gap-1 text-[13px] text-text-variant">
            {t("personaGroups.displayName", "Display name")}
            <input
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder={t("misc.optionalLabel", "Optional label")}
              className="h-8 rounded border border-outline bg-surface px-2 text-[14px]"
            />
          </label>
          <label className="flex flex-col gap-1 text-[13px] text-text-variant">
            {t("personaGroups.kind", "Kind")}
            <select
              value={saveKind}
              onChange={(e) => setSaveKind(e.target.value as "recipe" | "frozen")}
              className="h-8 rounded border border-outline bg-surface px-2 text-[14px]"
            >
              <option value="recipe">recipe ({t("personaGroups.recipeDescription", "re-sample on launch")})</option>
              <option value="frozen">frozen ({t("personaGroups.frozenDescription", "fixed persona list")})</option>
            </select>
          </label>
          <div className="flex items-end">
            <button
              type="button"
              disabled={!saveId.trim() || saveMutation.isPending}
              onClick={() => saveMutation.mutate()}
              className={`h-8 rounded-md bg-primary px-3 text-[13px] text-on-primary disabled:opacity-55 ${FOCUS_RING}`}
            >
              {saveMutation.isPending
                ? t("personaGroups.saving", "Saving…")
                : t("personaGroups.saveToPath", "Save to persona/datasets/saved-cohorts/")}
            </button>
          </div>
          {saveError && <p className="text-[13px] text-danger sm:col-span-2">{saveError}</p>}
        </div>
      )}

      {catalogQuery.isLoading && (
        <p className="text-[13px] text-text-variant">{t("personaGroups.loadingCatalog", "Loading dev persona catalog…")}</p>
      )}
      {catalogQuery.isError && (
        <p className="text-[13px] text-danger">{t("personaGroups.catalogError", "Could not load persona pool catalog.")}</p>
      )}

      {catalog && (
        <>
          <div className="mb-3">
            <p className="mb-1.5 text-[13px] text-text-variant">{t("personaGroups.provenance", "Provenance")}</p>
            <div className="flex flex-wrap gap-1.5">
              {sources.map((source) => {
                const active = filters.sources.includes(source);
                const count = catalog.sourceCounts?.[source];
                return (
                  <button
                    key={source}
                    type="button"
                    onClick={() => toggleSource(source)}
                    className={`rounded-full border px-2.5 py-1 text-[13px] ${FOCUS_RING} ${
                      active
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-outline bg-surface-low text-text-variant hover:border-primary/40"
                    }`}
                  >
                    {source}
                    {typeof count === "number" ? ` (${count})` : ""}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-[13px] text-text-variant">{t("personaGroups.dimensionFilters", "Dimension filters (dev profile)")}</p>
            {groups.map((group) => {
              const open = expandedGroup === group.id;
              const groupActive = group.dimensions.some(
                (dim) => filters.dimensionFilters[dim.id]?.trim(),
              );
              return (
                <div key={group.id} className="rounded border border-outline/60">
                  <button
                    type="button"
                    onClick={() => setExpandedGroup(open ? null : group.id)}
                    className={`flex w-full items-center justify-between px-2.5 py-2 text-left text-[14px] ${FOCUS_RING}`}
                  >
                    <span className={groupActive ? "text-primary" : "text-text-main"}>
                      {group.label}
                    </span>
                    <span className="text-text-dim">{open ? "−" : "+"}</span>
                  </button>
                  {open && (
                    <div className="grid gap-2 border-t border-outline/50 px-2.5 py-2 sm:grid-cols-2">
                      {group.dimensions.map((dim) => (
                        <label
                          key={dim.id}
                          className="flex flex-col gap-1 text-[13px] text-text-variant"
                        >
                          <span className="font-mono text-[12px] text-text-dim">{dim.id}</span>
                          <select
                            value={filters.dimensionFilters[dim.id] ?? ""}
                            onChange={(e) => setDimensionFilter(dim.id, e.target.value)}
                            className="h-8 rounded border border-outline bg-surface px-2 text-[14px] text-text-main"
                          >
                            <option value="">{t("personaGroups.any", "Any")}</option>
                            {dim.values.map((value) => (
                              <option key={value} value={value}>
                                {value}
                              </option>
                            ))}
                          </select>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <p className="mt-3 text-[13px] text-text-variant">
            {selectedCohortId ? (
              <>
                {t("personaGroups.usingCohort", "Using cohort")} <span className="font-mono text-text-main">{selectedCohortId}</span>
              </>
            ) : activeFilterCount > 0 ? (
              <>
                {matchedCount !== null ? (
                  <>
                    <span className="font-mono text-text-main">{matchedCount}</span> {t("personaGroups.personasMatch", "personas match filters")}
                  </>
                ) : (
                  t("personaGroups.checkingMatchCount", "Checking match count…")
                )}
              </>
            ) : (
              <>{t("personaGroups.noFilters", "No filters — random sample from full pool.")}</>
            )}
            {previewError && <span className="ml-2 text-danger">{previewError}</span>}
          </p>
        </>
      )}
    </div>
  );
}

export default PersonaGroupBuilder;
