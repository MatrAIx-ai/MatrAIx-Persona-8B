import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";
import { personaDimensionLabelKey } from "@/i18n/personaLabelKeys";
import {
  PERSONA_BENCH_POOL,
  PERSONA_CARD_PREVIEW_LIMIT,
  PERSONA_PRODUCTION_1M_POOL,
  PERSONA_SAMPLE_SIZE_MAX_DEV,
  PERSONA_SAMPLE_SIZE_MAX_PRODUCTION,
  type PersonaPoolPersonaCard,
  type TaskPersonaStrategy,
} from "@/lib/types";
import { formatPersonaSampleError, poolSlugLabel } from "@/lib/personaPoolCopy";
import { syntheticDisplayName } from "@/lib/personaDisplay";
import { FOCUS_RING, Sym, humanizeToken } from "../cockpitShared";
import { CockpitSelect, type CockpitSelectOption } from "./CockpitSelect";
import { CockpitToggle } from "./CockpitToggle";
import { BenchPersonaCard } from "./BenchPersonaCard";
import { BenchPersonaDetailPanel } from "./BenchPersonaDetailPanel";
import { CockpitRailHeader } from "./CockpitRailHeader";
import { PersonaFilterModal } from "./PersonaFilterModal";
import {
  activeFilterCount,
  filtersForSampleApi,
  type PersonaDimensionFilters,
  type PersonaSamplingMode,
} from "./personaSamplingTypes";
import type { PlaygroundTaskType } from "../TaskTypeSwitch";

function slugifyDatasetName(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

const TAB_LABELS: Record<PersonaSamplingMode, string> = {
  single: "Quick",
  random: "Random",
  stratified: "Stratified",
  all: "All",
};

const TAB_TITLES: Record<PersonaSamplingMode, string> = {
  single: "Quick pick",
  random: "Random sample",
  stratified: "Stratified",
  all: "Use every persona in the selected dataset",
};

const TAB_ORDER: PersonaSamplingMode[] = ["single", "random", "stratified", "all"];

/** Default showcase personas from matraix-persona-dev-sample (smoke + spread). */
const QUICK_PICK_PERSONA_IDS = ["0042", "0001", "0328", "0058", "0012", "0020", "0030", "0040"];

function clampSampleSize(value: number, max = PERSONA_SAMPLE_SIZE_MAX_DEV): number {
  if (!Number.isFinite(value)) return 4;
  return Math.min(max, Math.max(2, Math.round(value)));
}

function isProduction1mCohortPool(pool: string): boolean {
  return pool.includes("/matraix-persona-1m/cohorts/");
}

/** Dataset dropdown source — cohorts are launch caches, not selectable sources. */
function datasetSourcePool(pool: string): string {
  if (pool === PERSONA_PRODUCTION_1M_POOL || isProduction1mCohortPool(pool)) {
    return PERSONA_PRODUCTION_1M_POOL;
  }
  return pool;
}

function clampPerCell(value: number): number {
  if (!Number.isFinite(value)) return 1;
  return Math.min(50, Math.max(1, Math.round(value)));
}

function strategyModeLabel(mode: string | null | undefined): string {
  if (mode === "stratified") return "Stratified";
  if (mode === "random") return "Random sample";
  if (mode === "single") return "Quick pick";
  if (mode === "all") return "All";
  return "Custom";
}

function strategyHeadline(
  strategy: TaskPersonaStrategy,
  translate: (key: string, fallback?: string, values?: Record<string, string | number>) => string,
): string {
  const stratify = (strategy.stratifyFields ?? []).filter((value) => value.trim());
  const sample =
    typeof strategy.sampleSize === "number" && strategy.sampleSize > 0
      ? strategy.sampleSize
      : null;
  const perCell =
    typeof strategy.sampleSizePerValueGroup === "number" && strategy.sampleSizePerValueGroup >= 1
      ? strategy.sampleSizePerValueGroup
      : null;
  const isStratified = strategy.defaultMode === "stratified" || stratify.length > 0;
  const mode = translate(
    strategy.defaultMode === "stratified"
      ? "setup.persona.stratified"
      : strategy.defaultMode === "random"
        ? "setup.persona.randomSample"
        : strategy.defaultMode === "single"
          ? "setup.persona.quickPick"
          : strategy.defaultMode === "all"
            ? "setup.persona.all"
            : "setup.persona.custom",
    strategyModeLabel(strategy.defaultMode),
  );
  if (isStratified && perCell != null) {
    return translate("setup.persona.perCombination", `${mode} · ${perCell} per combination`, {
      mode,
      count: perCell,
    });
  }
  if (sample != null) {
    return translate("setup.persona.sample", `${mode} · sample ${sample}`, { mode, count: sample });
  }
  return mode;
}

function TaskStrategySummary({ strategy }: { strategy: TaskPersonaStrategy }) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const dimEntries = Object.entries(strategy.dimensionFilters ?? {}).filter(
    ([, values]) => Array.isArray(values) && values.length > 0,
  );
  const sources = (strategy.sources ?? []).filter((value) => value.trim());
  const stratify = (strategy.stratifyFields ?? []).filter((value) => value.trim());
  const filterBits = dimEntries.length + (sources.length > 0 ? 1 : 0);
  const hasDetails = sources.length > 0 || dimEntries.length > 0 || stratify.length > 0;
  const displayField = (field: string): string => {
    const fallback = humanizeToken(field);
    const labelKey = personaDimensionLabelKey(field, fallback);
    return labelKey ? t(labelKey, fallback) : fallback;
  };

  return (
    <div className="border-t border-outline/35 pt-1.5">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((open) => !open)}
        className={`flex w-full items-start gap-1.5 rounded-md py-0.5 text-left transition hover:bg-primary/5 ${FOCUS_RING}`}
      >
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-medium leading-snug text-text-main">
            {strategyHeadline(strategy, t)}
          </p>
          {!expanded && hasDetails ? (
            <p className="mt-0.5 truncate text-[11px] leading-snug text-text-dim">
              {stratify.length > 0
                ? t("personaDisplay.strategy.stratify", "Stratify {fields}", {
                    fields: stratify.map(displayField).join(" × "),
                  })
                : null}
              {stratify.length > 0 && filterBits > 0 ? " · " : null}
              {filterBits > 0
                ? t(
                    filterBits === 1
                      ? "personaDisplay.strategy.filterOne"
                      : "personaDisplay.strategy.filterMany",
                    filterBits === 1 ? "{count} filter" : "{count} filters",
                    { count: filterBits },
                  )
                : null}
            </p>
          ) : null}
        </div>
        {hasDetails ? (
          <Sym
            name={expanded ? "expand_less" : "expand_more"}
            size={16}
            className="mt-0.5 shrink-0 text-text-dim"
          />
        ) : null}
      </button>
      {expanded ? (
        <div className="mt-1.5 max-h-28 space-y-1 overflow-y-auto custom-scrollbar pr-0.5">
          {sources.length > 0 ? (
            <p className="text-[12px] leading-snug text-text-variant">
              <span className="text-text-dim">{t("setup.persona.sources", "Sources")} · </span>
              {sources.join(", ")}
            </p>
          ) : null}
          {dimEntries.map(([dim, values]) => (
            <p key={dim} className="text-[12px] leading-snug text-text-variant">
              <span className="text-text-dim">{displayField(dim)} · </span>
              {values.join(", ")}
            </p>
          ))}
          {stratify.length > 0 ? (
            <p className="text-[12px] leading-snug text-text-variant">
              <span className="text-text-dim">{t("setup.filters.stratify", "Stratify")} · </span>
              {stratify.map(displayField).join(", ")}
            </p>
          ) : null}
          {!hasDetails ? (
            <p className="text-[12px] text-text-dim">{t("setup.persona.noFilters", "No filters — full pool.")}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function fallbackQuickPickCards(): PersonaPoolPersonaCard[] {
  return QUICK_PICK_PERSONA_IDS.map((personaId) => ({
    personaId,
    name: syntheticDisplayName(personaId),
    source: "matraix-persona-dev-sample",
    dimensions: {},
  }));
}

export interface PersonaSamplingRailProps {
  personaModel: string;
  onPersonaModelChange: (model: string) => void;
  personaModelOptions: CockpitSelectOption[];
  mode: PersonaSamplingMode;
  onModeChange: (mode: PersonaSamplingMode) => void;
  selectedPersonaIds: string[];
  onSelectedPersonaIdsChange: (ids: string[]) => void;
  sampleSize: number;
  onSampleSizeChange: (size: number) => void;
  /** Personas per stratify combination; null = cap at sampleSize (no explicit per-cell). */
  sampleSizePerValueGroup: number | null;
  onSampleSizePerValueGroupChange: (size: number) => void;
  seed: number;
  filters: PersonaDimensionFilters;
  onFiltersChange: (filters: PersonaDimensionFilters) => void;
  stratifyFields: string[];
  onStratifyFieldsChange: (fields: string[]) => void;
  taskType?: PlaygroundTaskType;
  /** Active task path — used for strategy pool coverage recovery hints. */
  taskPath?: string | null;
  hasTaskStrategy?: boolean;
  taskPersonaStrategy?: TaskPersonaStrategy | null;
  useTaskDefaultStrategy?: boolean;
  onUseTaskDefaultStrategyChange?: (useDefault: boolean) => void;
  /** Called when sampling resolves to a (possibly auto-generated) pool path. */
  onPersonaPoolChange?: (pool: string) => void;
  /** Active pool path for the footer label (defaults to matraix-persona-dev-sample). */
  personaPool?: string | null;
  disabled?: boolean;
}

export function PersonaSamplingRail({
  personaModel,
  onPersonaModelChange,
  personaModelOptions,
  mode,
  onModeChange,
  selectedPersonaIds,
  onSelectedPersonaIdsChange,
  sampleSize,
  onSampleSizeChange,
  sampleSizePerValueGroup,
  onSampleSizePerValueGroupChange,
  seed,
  filters,
  onFiltersChange,
  stratifyFields,
  onStratifyFieldsChange,
  taskType,
  taskPath = null,
  hasTaskStrategy = false,
  taskPersonaStrategy = null,
  useTaskDefaultStrategy = false,
  onUseTaskDefaultStrategyChange,
  onPersonaPoolChange,
  personaPool = null,
  disabled,
}: PersonaSamplingRailProps) {
  const { t } = useI18n();
  const [filterOpen, setFilterOpen] = useState(false);
  const [detailPersona, setDetailPersona] = useState<PersonaPoolPersonaCard | null>(null);
  const [generatedCards, setGeneratedCards] = useState<PersonaPoolPersonaCard[]>([]);
  const [generateError, setGenerateError] = useState<string | null>(null);
    const [generating, setGenerating] = useState(false);
  /** Local draft so users can clear/retype without clamp fighting every keystroke. */
  const [sampleSizeDraft, setSampleSizeDraft] = useState<string | null>(null);
  const [perCellDraft, setPerCellDraft] = useState<string | null>(null);
  const [saveNameDraft, setSaveNameDraft] = useState("");
  const [saveOpen, setSaveOpen] = useState(false);
  const [savingDataset, setSavingDataset] = useState(false);
  const [saveDatasetError, setSaveDatasetError] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const activePool = personaPool?.trim() || PERSONA_BENCH_POOL;
  const sourcePool = datasetSourcePool(activePool);
  const isBenchPool = sourcePool === PERSONA_BENCH_POOL;
  const isProduction1m = sourcePool === PERSONA_PRODUCTION_1M_POOL;
  const canSaveAsDataset =
    isProduction1mCohortPool(activePool) && selectedPersonaIds.length > 0;
  const sampleSizeMax = isProduction1m
    ? PERSONA_SAMPLE_SIZE_MAX_PRODUCTION
    : PERSONA_SAMPLE_SIZE_MAX_DEV;

  const datasetsQuery = useQuery({
    queryKey: ["persona-pool-datasets"],
    queryFn: () => api.listPersonaDatasets(),
    staleTime: 60_000,
  });

  const catalogQuery = useQuery({
    queryKey: ["persona-pool-catalog", sourcePool],
    queryFn: () => api.getPersonaPoolCatalog(sourcePool),
    staleTime: 60_000,
  });

  const defaultCardsQuery = useQuery({
    queryKey: [
      "persona-pool-default-cards",
      sourcePool,
      isBenchPool ? QUICK_PICK_PERSONA_IDS.join(",") : "preview",
    ],
    queryFn: async () => {
      try {
        return await api.getPersonaPoolCards({
          pool: sourcePool,
          limit: QUICK_PICK_PERSONA_IDS.length,
          personaIds: isBenchPool ? QUICK_PICK_PERSONA_IDS : undefined,
        });
      } catch {
        return {
          pool: sourcePool,
          personas: isBenchPool ? fallbackQuickPickCards() : [],
        };
      }
    },
    staleTime: 60_000,
  });

  const previewPersonaIds = useMemo(
    () => selectedPersonaIds.slice(0, PERSONA_CARD_PREVIEW_LIMIT),
    [selectedPersonaIds],
  );

  const lockedCohortQuery = useQuery({
    queryKey: [
      "persona-pool-locked-cohort",
      personaPool ?? PERSONA_BENCH_POOL,
      previewPersonaIds.join(","),
    ],
    queryFn: () =>
      api.getPersonaPoolCards({
        pool: personaPool ?? undefined,
        personaIds: previewPersonaIds,
        limit: previewPersonaIds.length,
      }),
    enabled: Boolean(disabled) && mode !== "single" && previewPersonaIds.length > 0,
    staleTime: 300_000,
  });

  const quickPickCards = useMemo(() => {
    const fromApi = defaultCardsQuery.data?.personas ?? [];
    if (fromApi.length > 0) return fromApi;
    if (defaultCardsQuery.isError) return fallbackQuickPickCards();
    return [];
  }, [defaultCardsQuery.data?.personas, defaultCardsQuery.isError]);

  const displayCards = useMemo(() => {
    if (mode === "single") return quickPickCards;
    if (disabled && selectedPersonaIds.length > 0) {
      const locked = lockedCohortQuery.data?.personas ?? [];
      if (locked.length > 0) return locked;
      return selectedPersonaIds.map((personaId) => ({
        personaId,
        name: syntheticDisplayName(personaId),
        source: "matraix-persona-dev-sample",
        dimensions: {},
      }));
    }
    return generatedCards;
  }, [
    quickPickCards,
    generatedCards,
    mode,
    disabled,
    selectedPersonaIds,
    lockedCohortQuery.data?.personas,
  ]);

  useEffect(() => {
    if (mode === "single") setGeneratedCards([]);
  }, [mode]);

  const togglePersona = useCallback(
    (personaId: string) => {
      if (mode === "single") {
        onSelectedPersonaIdsChange(
          selectedPersonaIds.includes(personaId) ? [] : [personaId],
        );
        return;
      }
      onSelectedPersonaIdsChange(
        selectedPersonaIds.includes(personaId)
          ? selectedPersonaIds.filter((id) => id !== personaId)
          : [...selectedPersonaIds, personaId],
      );
    },
    [mode, onSelectedPersonaIdsChange, selectedPersonaIds],
  );

  const handleSelectAll = useCallback(async () => {
    setGenerating(true);
    setGenerateError(null);
    try {
      const pool = activePool;
      const idsResult = await api.listPersonaPoolIds(pool);
      const personaIds = idsResult.personaIds;
      if (personaIds.length === 0) {
        throw new ApiError(404, "This dataset has no persona YAML files.");
      }
      const preview = await api.getPersonaPoolCards({
        pool,
        limit: Math.min(PERSONA_CARD_PREVIEW_LIMIT, personaIds.length),
        personaIds: personaIds.slice(0, PERSONA_CARD_PREVIEW_LIMIT),
      });
      setGeneratedCards(preview.personas);
      onSelectedPersonaIdsChange(personaIds);
      onPersonaPoolChange?.(pool);
    } catch (err) {
      const raw =
        err instanceof ApiError ? err.message : "Could not load the full dataset cohort.";
      setGenerateError(raw);
      } finally {
      setGenerating(false);
    }
  }, [activePool, onPersonaPoolChange, onSelectedPersonaIdsChange]);

  const handleGenerate = useCallback(async () => {
    if (mode === "all") {
      await handleSelectAll();
      return;
    }
    setGenerating(true);
    setGenerateError(null);
    try {
      const dimensionFilters = filtersForSampleApi(filters);
      // Only send per-cell when explicitly set. Omitting it makes the backend
      // take ~1/cell then truncate to sampleSize (task strategies often set
      // sampleSize alone without sampleSizePerValueGroup).
      const perCell =
        mode === "stratified" && sampleSizePerValueGroup != null
          ? clampPerCell(sampleSizePerValueGroup)
          : undefined;
      const result = await api.samplePersonaPool({
        pool: sourcePool,
        sampleSize,
        seed,
        sources: filters.sources.length ? filters.sources : undefined,
        dimensionFilters,
        stratifyFields: mode === "stratified" ? stratifyFields : undefined,
        sampleSizePerValueGroup: perCell,
        taskPath: taskPath?.trim() || undefined,
      });
      // Select the full cohort immediately; only keep a small card preview for the rail.
      const cards = result.personas.slice(0, PERSONA_CARD_PREVIEW_LIMIT).map((row) => ({
        personaId: row.personaId,
        name: row.name ?? `persona-${row.personaId}`,
        source: row.source,
        path: row.path,
        dimensions: row.dimensions ?? {},
      }));
      setGeneratedCards(cards);
      onSelectedPersonaIdsChange(result.personaIds);
      if (result.pool) {
        // Launch needs the materialized YAML dir; Dataset UI still shows sourcePool.
        onPersonaPoolChange?.(result.pool);
      }
    } catch (err) {
      const raw = err instanceof ApiError ? err.message : "Could not generate sample.";
      const formatted = formatPersonaSampleError(raw, taskPath);
      setGenerateError(formatted);
    } finally {
      setGenerating(false);
    }
  }, [
    filters,
    handleSelectAll,
    mode,
    onPersonaPoolChange,
    onSelectedPersonaIdsChange,
    sampleSize,
    sampleSizePerValueGroup,
    seed,
    sourcePool,
    stratifyFields,
    taskPath,
  ]);

  const datasetOptions = useMemo<CockpitSelectOption[]>(() => {
    const listed = datasetsQuery.data?.datasets ?? [];
    const options: CockpitSelectOption[] = listed.map((item) => {
      const unavailable = item.kind === "production" && item.available === false;
      return {
        value: item.pool,
        label: item.label,
        meta: unavailable
          ? t("setup.persona.downloadHint", "download HF release / set MATRIX_PERSONA_1M_DIR")
          : item.count > 0
            ? t("setup.persona.datasetPersonas", "{count} personas", {
                count: item.count.toLocaleString(),
              })
            : undefined,
      };
    });
    if (!options.some((opt) => opt.value === sourcePool)) {
      const slug = sourcePool.split("/").filter(Boolean).pop() || "matraix-persona-dev-sample";
      options.unshift({
        value: sourcePool,
        label: slug,
      });
    }
    if (options.length === 0) {
      return [{ value: PERSONA_BENCH_POOL, label: "matraix-persona-dev-sample" }];
    }
    return options;
  }, [datasetsQuery.data?.datasets, sourcePool, t]);

  const handleDatasetChange = useCallback(
    (pool: string) => {
      if (pool === sourcePool) return;
      onPersonaPoolChange?.(pool);
      onSelectedPersonaIdsChange([]);
      setGeneratedCards([]);
      setGenerateError(null);
        setDetailPersona(null);
      setSaveOpen(false);
      setSaveDatasetError(null);
      if (pool === PERSONA_PRODUCTION_1M_POOL && mode === "all") {
        onModeChange("random");
      }
    },
    [mode, onModeChange, onPersonaPoolChange, onSelectedPersonaIdsChange, sourcePool],
  );

  const handleSaveAsDataset = useCallback(async () => {
    const name = saveNameDraft.trim() || `cohort-${selectedPersonaIds.length}`;
    const slug = slugifyDatasetName(name);
    if (!slug) {
      setSaveDatasetError(t("setup.persona.invalidDatasetName", "Enter a name with letters or numbers."));
      return;
    }
    setSavingDataset(true);
    setSaveDatasetError(null);
    try {
      const saved = await api.savePersonaDataset({
        sourcePool: activePool,
        name,
      });
      await queryClient.invalidateQueries({ queryKey: ["persona-pool-datasets"] });
      onPersonaPoolChange?.(saved.pool);
      setSaveOpen(false);
      setSaveNameDraft("");
    } catch (err) {
      setSaveDatasetError(
        err instanceof ApiError ? err.message : t("setup.persona.saveFailed", "Could not save dataset."),
      );
    } finally {
      setSavingDataset(false);
    }
  }, [
    activePool,
    onPersonaPoolChange,
    queryClient,
    saveNameDraft,
    selectedPersonaIds.length,
    t,
  ]);

  const filterCount = activeFilterCount(filters);
  const poolCount = catalogQuery.data?.count;
  const showModelSelector =
    taskType === "survey" || taskType === "chatbot" || taskType === "web" || taskType === "os-app";
  const strategyLocked = hasTaskStrategy && useTaskDefaultStrategy;
  const customSamplingUnlocked = !strategyLocked;
  const poolFooterLabel = isProduction1mCohortPool(activePool)
    ? `${poolSlugLabel(sourcePool)} · ${t("setup.persona.sampleReady", "sample ready")}`
    : poolSlugLabel(sourcePool);

  return (
    <aside className="glass-panel glass-panel-rail relative flex h-full min-h-0 flex-col rounded-xl p-4">
      {detailPersona ? (
        <BenchPersonaDetailPanel
          coverRail
          embedded
          persona={detailPersona}
          pool={sourcePool}
          onClose={() => setDetailPersona(null)}
          className="min-h-0 flex-1"
        />
      ) : (
      <>
      <div className="shrink-0">
        <CockpitRailHeader label={t("setup.persona.title", "Persona")} />

        <div className="mb-2 space-y-1.5">
          {showModelSelector && (
            <CockpitSelect
              label={t("setup.persona.model", "Model")}
              inlineLabel
              labelClassName="w-[4.25rem]"
              value={personaModel}
              options={personaModelOptions}
              disabled={disabled}
              onChange={onPersonaModelChange}
            />
          )}
          <CockpitSelect
            label={t("setup.persona.dataset", "Dataset")}
            inlineLabel
            labelClassName="w-[4.25rem]"
            value={sourcePool}
            options={datasetOptions}
            disabled={disabled}
            showSelectedMeta={false}
            onChange={handleDatasetChange}
          />
        </div>

        {hasTaskStrategy && taskPersonaStrategy ? (
          <div
            className="glass-tile mb-2 rounded-lg px-2.5 py-1.5"
            title={
              useTaskDefaultStrategy
              ? t("setup.persona.followStrategy", "Filters follow persona_strategy.json")
                : t("setup.persona.editFilters", "Edit filters yourself")
            }
          >
            <CockpitToggle
              label={t("setup.persona.taskDefaultStrategy", "Task default persona strategy")}
              checked={useTaskDefaultStrategy}
              disabled={disabled}
              onChange={(checked) => onUseTaskDefaultStrategyChange?.(checked)}
            />
            {useTaskDefaultStrategy ? (
              <TaskStrategySummary strategy={taskPersonaStrategy} />
            ) : null}
          </div>
        ) : null}

        <div className="cockpit-segment cockpit-segment--grid mb-2 grid-cols-4">
          {TAB_ORDER.map((tab) => {
            const allBlocked = tab === "all" && isProduction1m;
            return (
              <button
                key={tab}
                type="button"
                title={t(
                  allBlocked
                    ? "setup.persona.allDisabled"
                    : tab === "single"
                      ? "setup.persona.quickPick"
                      : tab === "random"
                        ? "setup.persona.randomSample"
                        : tab === "stratified"
                          ? "setup.persona.stratified"
                          : "setup.persona.allDataset",
                  allBlocked
                    ? "All is disabled on the 1M production pool — sample up to 10,000 instead"
                    : TAB_TITLES[tab],
                )}
                disabled={disabled || strategyLocked || allBlocked}
                onClick={() => onModeChange(tab)}
                className={`cockpit-segment__btn cockpit-segment__btn--compact w-full ${FOCUS_RING} ${
                  mode === tab ? "cockpit-segment__btn--active" : ""
                }`}
              >
                {t(`setup.persona.${tab === "single" ? "quick" : tab}`, TAB_LABELS[tab])}
              </button>
            );
          })}
        </div>

        {disabled && selectedPersonaIds.length > 0 ? (
          <p className="glass-tile mb-2 rounded-lg px-2.5 py-1.5 text-[12px] leading-snug text-text-variant">
            {t("setup.persona.cohortLocked", "Cohort locked for this run — use Reset to change personas or sample settings.")}
          </p>
        ) : null}

        {mode === "all" && (
          <div className="mb-2 space-y-1.5">
            <p className="glass-tile rounded-lg px-2.5 py-1.5 text-[12px] leading-snug text-text-variant">
              {t("setup.persona.fullDataset", "Run the full selected dataset cohort")}
              {typeof poolCount === "number" ? (
                <>
                  {" "}
                  · <span className="font-mono text-text-main">{poolCount}</span> {t("setup.persona.personas", "personas")}
                </>
              ) : null}
              .
            </p>
            <button
              type="button"
              disabled={disabled || generating}
              onClick={() => void handleSelectAll()}
              className={`flex h-9 w-full items-center justify-center gap-1.5 rounded-lg bg-surface-high/90 text-[13px] font-medium text-text-main hover:bg-surface-high disabled:opacity-50 ${FOCUS_RING}`}
            >
              <Sym
                name={generating ? "autorenew" : "done_all"}
                size={15}
                className={generating ? "animate-rb-spin text-primary" : "text-primary"}
              />
              {generating
                ? t("setup.persona.loadingCohort", "Loading cohort…")
                : typeof poolCount === "number"
                  ? t("setup.persona.selectAll", "Select all · {count}", { count: poolCount })
                  : t("setup.persona.selectAllPlain", "Select all")}
            </button>
            {generateError ? (
              <div className="space-y-1.5 rounded-lg border border-danger/30 bg-danger/5 px-2.5 py-2">
                <p className="text-[12px] leading-snug text-danger">{generateError}</p>
              </div>
            ) : null}
          </div>
        )}

        {mode !== "single" && mode !== "all" && (
          <div className="mb-2 space-y-1.5">
            {customSamplingUnlocked ? (
              <button
                type="button"
                disabled={disabled}
                onClick={() => setFilterOpen(true)}
                className={`glass-tile glass-tile--hover flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition ${FOCUS_RING}`}
              >
                <Sym name="tune" size={16} className="shrink-0 text-primary" />
                <span className="min-w-0 flex-1 text-[13px] font-medium text-text-main">
                  {t("setup.persona.filters", "Persona filters")}
                </span>
                {filterCount > 0 ? (
                  <span className="rounded-full bg-primary/15 px-1.5 font-mono text-[11px] text-primary">
                    {filterCount}
                  </span>
                ) : null}
                <Sym name="chevron_right" size={16} className="shrink-0 text-text-dim" />
              </button>
            ) : null}

            <div className="flex items-end gap-2">
              {customSamplingUnlocked ? (
                <>
                  {mode === "stratified" && sampleSizePerValueGroup != null ? (
                    <label className="flex w-[4.25rem] shrink-0 flex-col gap-0.5">
                      <span className="text-[12px] text-text-dim">{t("setup.persona.perCell", "Per cell")}</span>
                      <input
                        type="number"
                        inputMode="numeric"
                        min={1}
                        max={50}
                        step={1}
                        value={perCellDraft ?? sampleSizePerValueGroup}
                        disabled={disabled}
                        onFocus={() => setPerCellDraft(String(sampleSizePerValueGroup))}
                        onChange={(e) => {
                          const raw = e.target.value;
                          if (raw === "" || /^\d+$/.test(raw)) {
                            setPerCellDraft(raw);
                          }
                        }}
                        onBlur={() => {
                          const raw = perCellDraft;
                          setPerCellDraft(null);
                          onSampleSizePerValueGroupChange(
                            clampPerCell(
                              raw === "" || raw == null
                                ? sampleSizePerValueGroup
                                : Number(raw),
                            ),
                          );
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            (e.target as HTMLInputElement).blur();
                          }
                        }}
                        className={`h-9 w-full rounded-lg border border-outline/50 bg-surface/60 px-1.5 text-center font-mono text-[15px] text-text-main disabled:opacity-50 ${FOCUS_RING}`}
                      />
                    </label>
                  ) : (
                    <label className="flex w-[4.25rem] shrink-0 flex-col gap-0.5">
                      <span className="text-[12px] text-text-dim">{t("setup.persona.sampleLabel", "Sample")}</span>
                      <input
                        type="number"
                        inputMode="numeric"
                        min={2}
                        max={sampleSizeMax}
                        step={1}
                        value={sampleSizeDraft ?? sampleSize}
                        disabled={disabled}
                        onFocus={() => setSampleSizeDraft(String(sampleSize))}
                        onChange={(e) => {
                          const raw = e.target.value;
                          if (raw === "" || /^\d+$/.test(raw)) {
                            setSampleSizeDraft(raw);
                          }
                        }}
                        onBlur={() => {
                          const raw = sampleSizeDraft;
                          setSampleSizeDraft(null);
                          onSampleSizeChange(
                            clampSampleSize(
                              raw === "" || raw == null ? sampleSize : Number(raw),
                              sampleSizeMax,
                            ),
                          );
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            (e.target as HTMLInputElement).blur();
                          }
                        }}
                        className={`h-9 w-full rounded-lg border border-outline/50 bg-surface/60 px-1.5 text-center font-mono text-[15px] text-text-main disabled:opacity-50 ${FOCUS_RING}`}
                      />
                    </label>
                  )}
                </>
              ) : null}
              <button
                type="button"
                disabled={disabled || generating}
                onClick={() => void handleGenerate()}
                className={`flex h-9 min-w-0 flex-1 items-center justify-center gap-1.5 rounded-lg bg-surface-high/90 text-[13px] font-medium text-text-main hover:bg-surface-high disabled:opacity-50 ${FOCUS_RING}`}
              >
                <Sym
                  name={generating ? "autorenew" : "auto_awesome"}
                  size={15}
                  className={generating ? "animate-rb-spin text-primary" : "text-primary"}
                />
                {generating
                  ? t("setup.persona.generating", "Generating…")
                  : t("setup.persona.generatePreview", "Generate preview")}
              </button>
            </div>
            {generateError ? (
              <div className="space-y-1.5 rounded-lg border border-danger/30 bg-danger/5 px-2.5 py-2">
                <p className="whitespace-pre-wrap text-[12px] leading-snug text-danger">{generateError}</p>
              </div>
            ) : null}
            {canSaveAsDataset && !disabled ? (
              <div className="rounded-lg border border-outline/40 bg-surface/40 px-2.5 py-2">
                {!saveOpen ? (
                  <button
                    type="button"
                    disabled={savingDataset}
                    onClick={() => {
                      setSaveOpen(true);
                      setSaveDatasetError(null);
                      if (!saveNameDraft.trim()) {
                        const stamp = new Date().toISOString().slice(0, 10);
                        setSaveNameDraft(`sample-${selectedPersonaIds.length}-${stamp}`);
                      }
                    }}
                    className={`flex w-full items-center justify-center gap-1.5 rounded-md py-1.5 text-[12px] font-medium text-primary hover:bg-primary/5 disabled:opacity-50 ${FOCUS_RING}`}
                  >
                    <Sym name="save" size={14} />
                    {t("setup.persona.saveAsDataset", "Save as dataset…")}
                  </button>
                ) : (
                  <div className="space-y-1.5">
                    <label className="block space-y-1">
                      <span className="text-[11px] font-medium uppercase tracking-wide text-text-dim">
                        {t("setup.persona.datasetName", "Dataset name")}
                      </span>
                      <input
                        type="text"
                        value={saveNameDraft}
                        disabled={savingDataset}
                        placeholder="my-robinhood-cohort"
                        onChange={(e) => setSaveNameDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            void handleSaveAsDataset();
                          }
                          if (e.key === "Escape") {
                            setSaveOpen(false);
                            setSaveDatasetError(null);
                          }
                        }}
                        className={`h-8 w-full rounded-md border border-outline/50 bg-field px-2 font-mono text-[12px] text-text-main disabled:opacity-50 ${FOCUS_RING}`}
                      />
                    </label>
                    {saveNameDraft.trim() ? (
                      <p className="truncate font-mono text-[10px] text-text-dim">
                        persona/datasets/{slugifyDatasetName(saveNameDraft) || "…"}
                      </p>
                    ) : null}
                    {saveDatasetError ? (
                      <p className="text-[11px] leading-snug text-danger">{saveDatasetError}</p>
                    ) : (
                      <p className="text-[11px] leading-snug text-text-dim">
                        {t("setup.persona.datasetReuse", "Copies this sample into Dataset for reuse across tasks.")}
                      </p>
                    )}
                    <div className="flex gap-1.5">
                      <button
                        type="button"
                        disabled={savingDataset}
                        onClick={() => {
                          setSaveOpen(false);
                          setSaveDatasetError(null);
                        }}
                        className={`h-8 flex-1 rounded-md border border-outline/50 text-[12px] text-text-variant hover:bg-surface-high/60 disabled:opacity-50 ${FOCUS_RING}`}
                      >
                        {t("setup.persona.cancel", "Cancel")}
                      </button>
                      <button
                        type="button"
                        disabled={savingDataset || !saveNameDraft.trim()}
                        onClick={() => void handleSaveAsDataset()}
                        className={`h-8 flex-1 rounded-md bg-primary/90 text-[12px] font-medium text-white hover:bg-primary disabled:opacity-50 ${FOCUS_RING}`}
                      >
                        {savingDataset ? t("setup.persona.saving", "Saving…") : t("setup.persona.save", "Save")}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        )}
      </div>

      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto pr-0.5">
          <div className="space-y-2">
            {mode === "single" && defaultCardsQuery.isLoading && quickPickCards.length === 0 && (
              <p className="text-[13px] text-text-variant">
                {t("setup.persona.loadingDataset", "Loading {dataset}…", {
                  dataset: activePool.split("/").filter(Boolean).pop() || "dataset",
                })}
              </p>
            )}
            {mode === "single" && defaultCardsQuery.isError && quickPickCards.length > 0 && (
              <p className="text-[12px] text-warn">
                {t("setup.persona.offlineList", "Using offline persona list — restart backend for full dimensions.")}
              </p>
            )}
            {displayCards.map((persona) => (
              <BenchPersonaCard
                key={persona.personaId}
                persona={persona}
                selected={selectedPersonaIds.includes(persona.personaId)}
                disabled={disabled}
                onToggle={() => togglePersona(persona.personaId)}
                onOpenDetail={() => setDetailPersona(persona)}
              />
            ))}
            {mode !== "single" &&
              selectedPersonaIds.length > displayCards.length &&
              displayCards.length > 0 && (
                <p className="rounded-lg border border-dashed border-outline/40 px-3 py-2 text-center text-[12px] text-text-dim">
                  {t("setup.persona.previewing", "Previewing {shown} of {selected} selected — full cohort is ready to launch.", {
                    shown: displayCards.length,
                    selected: selectedPersonaIds.length,
                  })}
                </p>
              )}
            {mode === "single" && !defaultCardsQuery.isLoading && displayCards.length === 0 && (
              <p className="rounded-lg border border-dashed border-outline/40 p-4 text-center text-[13px] text-text-dim">
                {t("setup.persona.noneLoaded", "No personas loaded. Check that the backend is running.")}
              </p>
            )}
            {mode !== "single" && displayCards.length === 0 && !disabled && (
              <p className="rounded-lg border border-dashed border-outline/40 p-4 text-center text-[13px] text-text-dim">
                {strategyLocked
                  ? t("setup.persona.emptyStrategy", "Generate a preview cohort from the task default strategy.")
                  : mode === "all"
                    ? t("setup.persona.emptyAll", "Select all to load every persona from the chosen dataset.")
                    : t("setup.persona.emptyCustom", "Set filters and generate a preview cohort.")}
              </p>
            )}
            {mode !== "single" &&
              displayCards.length === 0 &&
              disabled &&
              lockedCohortQuery.isLoading && (
                <p className="text-[13px] text-text-variant">{t("setup.persona.loading", "Loading cohort personas…")}</p>
              )}
          </div>
      </div>

      <p className="mt-2 shrink-0 truncate text-center font-mono text-[12px] tracking-wide text-text-dim">
        <span className="font-semibold text-primary">{selectedPersonaIds.length}</span> {t("setup.persona.selected", "selected")} ·{" "}
        {poolFooterLabel}
      </p>
      </>
      )}

      <PersonaFilterModal
        open={filterOpen}
        catalog={catalogQuery.data ?? null}
        filters={filters}
        stratifyMode={mode === "stratified"}
        stratifyFields={stratifyFields}
        onStratifyFieldsChange={onStratifyFieldsChange}
        onClose={() => setFilterOpen(false)}
        onConfirm={onFiltersChange}
      />

    </aside>
  );
}
