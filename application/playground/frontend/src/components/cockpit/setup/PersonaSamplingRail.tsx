import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";
import { personaDimensionLabelKey } from "@/i18n/personaLabelKeys";
import {
  PERSONA_BENCH_POOL,
  PERSONA_CARD_PREVIEW_LIMIT,
  PERSONA_GENERATE_COUNT_DEFAULT,
  PERSONA_GENERATE_COUNT_MAX,
  PERSONA_PRODUCTION_1M_POOL,
  PERSONA_SAMPLE_SIZE_MAX_DEV,
  PERSONA_SAMPLE_SIZE_MAX_PRODUCTION,
  PERSONA_UI_ID_LIST_MAX,
  type PersonaPoolGenerateProgress,
  type PersonaPoolGenerateResult,
  type PersonaPoolPersonaCard,
  type TaskPersonaStrategy,
} from "@/lib/types";
import {
  formatPersonaSampleError,
  isPersonaPoolCoverageError,
  poolSlugLabel,
} from "@/lib/personaPoolCopy";
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
  emptyPersonaDimensionFilters,
  filtersForSampleApi,
  readStrategySampling,
  type PersonaDimensionFilters,
  type PersonaSamplingMode,
  type StratifiedAllocation,
  type StrategySamplingView,
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

const ALLOCATION_LABELS: Record<StratifiedAllocation, string> = {
  perCell: "Per-cell",
  proportional: "Proportional",
  equalTotal: "Equal-total",
};

const ALLOCATION_TITLES: Record<StratifiedAllocation, string> = {
  perCell: "Take N personas from every stratify combination",
  proportional: "Allocate sample size by cell population (Hamilton)",
  equalTotal: "Ensure coverage then clip to sample size",
};

const ALLOCATION_ORDER: StratifiedAllocation[] = ["perCell", "proportional", "equalTotal"];

/** Default showcase personas from matraix-persona-dev-sample (smoke + spread). */
const QUICK_PICK_PERSONA_IDS = ["0042", "0001", "0328", "0058", "0012", "0020", "0030", "0040"];

function clampSampleSize(value: number, max = PERSONA_SAMPLE_SIZE_MAX_DEV): number {
  if (!Number.isFinite(value)) return 4;
  return Math.min(max, Math.max(2, Math.round(value)));
}

function isProduction1mCohortPool(pool: string): boolean {
  return pool.includes("/matraix-persona-1m/cohorts/");
}

/** ``persona/datasets/<source>/cohorts/cohort-…`` — source dataset stays in the path. */
function parentDatasetFromCohortPool(pool: string): string | null {
  const match = pool.match(/^(persona\/datasets\/[^/]+)\/cohorts\/cohort-/);
  return match?.[1] ?? null;
}

function isSampleCohortPool(pool: string): boolean {
  const parent = parentDatasetFromCohortPool(pool);
  return Boolean(parent) && parent !== PERSONA_PRODUCTION_1M_POOL;
}

/** Pulled launch cache (1M or local dataset) — can be saved as a reusable dataset. */
function isMaterializedCohortPool(pool: string): boolean {
  return isProduction1mCohortPool(pool) || isSampleCohortPool(pool);
}

function isGeneratedDevPool(pool: string): boolean {
  return /(?:^|\/)generated-persona-dev-/.test(pool);
}

function clampGenerateCount(value: number): number {
  if (!Number.isFinite(value)) return PERSONA_GENERATE_COUNT_DEFAULT;
  return Math.min(PERSONA_GENERATE_COUNT_MAX, Math.max(1, Math.round(value)));
}

function PersonaFilterChips({
  filters,
  fields,
  showStratify,
}: {
  filters: PersonaDimensionFilters;
  fields: string[];
  showStratify: boolean;
}) {
  const filterCount = activeFilterCount(filters);
  if (filterCount === 0 && !(showStratify && fields.length > 0)) return null;
  return (
    <div className="flex flex-wrap gap-1 px-0.5">
      {filters.sources.map((source) => (
        <span
          key={`src:${source}`}
          className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] text-primary"
        >
          {source}
        </span>
      ))}
      {Object.entries(filters.dimensionFilters)
        .filter(([, values]) => values.length > 0)
        .map(([dim, values]) => (
          <span
            key={dim}
            className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] text-primary"
            title={values.join(", ")}
          >
            {humanizeToken(dim)}
            <span className="text-primary/70"> · {values.length}</span>
          </span>
        ))}
      {showStratify
        ? fields.map((field) => (
            <span
              key={`st:${field}`}
              className="rounded-full border border-secondary/35 bg-secondary/10 px-2 py-0.5 text-[11px] text-secondary"
            >
              stratify · {humanizeToken(field)}
            </span>
          ))
        : null}
    </div>
  );
}

/** Dataset dropdown source — cohorts are launch caches, not selectable sources. */
function datasetSourcePool(pool: string): string {
  if (pool === PERSONA_PRODUCTION_1M_POOL || isProduction1mCohortPool(pool)) {
    return PERSONA_PRODUCTION_1M_POOL;
  }
  const parent = parentDatasetFromCohortPool(pool);
  if (parent) return parent;
  if (isSampleCohortPool(pool)) {
    return PERSONA_BENCH_POOL;
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

function strategySampleTypeLabel(sampling: StrategySamplingView): string | null {
  if (sampling.mode === "all") return "Entire filtered pool";
  if (sampling.mode === "single") return "1 persona";
  if (sampling.mode === "stratified" && sampling.allocation === "perCell") {
    const n = sampling.perCell ?? 1;
    return `${n} persona${n === 1 ? "" : "s"} per cell`;
  }
  if (sampling.sampleSize != null) {
    return `Total sample · ${sampling.sampleSize} persona${sampling.sampleSize === 1 ? "" : "s"}`;
  }
  if (sampling.perCell != null) {
    return `${sampling.perCell} persona${sampling.perCell === 1 ? "" : "s"} per cell`;
  }
  return null;
}

const STRATEGY_CHIP =
  "rounded-full px-2 py-0.5 text-[11px] leading-5 transition-colors duration-150";
const STRATEGY_FILTER_CHIP = `${STRATEGY_CHIP} bg-primary/10 text-primary hover:bg-primary/15`;
const STRATEGY_STRATIFY_CHIP = `${STRATEGY_CHIP} border border-secondary/35 bg-secondary/10 text-secondary`;

function StrategySectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-text-dim">{children}</p>
  );
}

function StrategyKvRow({
  label,
  children,
  title,
}: {
  label: string;
  children: ReactNode;
  title?: string;
}) {
  return (
    <div className="grid grid-cols-[4.75rem_minmax(0,1fr)] items-start gap-x-2 gap-y-0.5">
      <dt className="pt-0.5 text-[11px] text-text-dim">{label}</dt>
      <dd className="min-w-0 text-[12px] leading-snug text-text-main" title={title}>
        {children}
      </dd>
    </div>
  );
}

/** Compact dim chip — click to peek selected values. */
function StrategyFilterValueChip({
  label,
  values,
  open,
  onToggle,
}: {
  label: string;
  values: string[];
  open: boolean;
  onToggle: () => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) onToggle();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onToggle();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onToggle]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={onToggle}
        className={`${STRATEGY_FILTER_CHIP} cursor-pointer ${FOCUS_RING} ${
          open ? "ring-1 ring-primary/40" : ""
        }`}
        title={values.join(", ")}
      >
        {label}
        <span className="text-primary/70"> · {values.length}</span>
      </button>
      {open ? (
        <div
          role="dialog"
          aria-label={`${label} selected values`}
          className="absolute left-0 top-[calc(100%+0.35rem)] z-20 w-[min(16.5rem,calc(100vw-2rem))] rounded-lg border border-outline/50 bg-surface-low p-2.5 shadow-[0_12px_28px_-16px_rgb(0_0_0/0.55)]"
        >
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <p className="min-w-0 truncate text-[11px] font-medium text-text-main">{label}</p>
            <p className="shrink-0 text-[10px] text-text-dim">
              {values.length} selected
            </p>
          </div>
          <div className="flex max-h-40 flex-wrap gap-1 overflow-y-auto">
            {values.map((value) => (
              <span
                key={value}
                className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] leading-5 text-primary"
              >
                {value}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function strategyCollapsedHeadline(sampling: StrategySamplingView): string {
  const mode = strategyModeLabel(sampling.mode);
  const sample = strategySampleTypeLabel(sampling);
  if (sampling.mode === "stratified" || sampling.fields.length > 0) {
    const alloc = ALLOCATION_LABELS[sampling.allocation] ?? sampling.allocation;
    return sample ? `${mode} · ${alloc} · ${sample}` : `${mode} · ${alloc}`;
  }
  return sample ? `${mode} · ${sample}` : mode;
}

function TaskStrategySummary({
  strategy,
  expanded,
  onExpandedChange,
}: {
  strategy: TaskPersonaStrategy;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
}) {
  const { t } = useI18n();
  const sampling = readStrategySampling(strategy);
  const dimEntries = Object.entries(strategy.dimensionFilters ?? {}).filter(
    ([, values]) => Array.isArray(values) && values.length > 0,
  );
  const sources = (strategy.sources ?? []).filter((value) => value.trim());
  const stratify = sampling.fields;
  const filterBits = dimEntries.length + (sources.length > 0 ? 1 : 0);
  const showAllocation = sampling.mode === "stratified" || stratify.length > 0;
  const sampleType = strategySampleTypeLabel(sampling);
  const allocLabel = t(
    sampling.allocation === "perCell"
      ? "setup.persona.allocationPerCell"
      : sampling.allocation === "proportional"
        ? "setup.persona.allocationProportional"
        : "setup.persona.allocationEqualTotal",
    ALLOCATION_LABELS[sampling.allocation] ?? sampling.allocation,
  );
  const [openFilterKey, setOpenFilterKey] = useState<string | null>(null);
  const displayField = (field: string): string => {
    const fallback = humanizeToken(field);
    const labelKey = personaDimensionLabelKey(field, fallback);
    return labelKey ? t(labelKey, fallback) : fallback;
  };

  useEffect(() => {
    if (!expanded) setOpenFilterKey(null);
  }, [expanded]);

  return (
    <div className="mt-2 border-t border-outline/35 pt-1.5">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => onExpandedChange(!expanded)}
        className={`flex w-full items-start gap-1.5 rounded-md py-0.5 text-left transition-colors duration-150 hover:bg-primary/5 ${FOCUS_RING}`}
      >
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-medium leading-snug text-text-main">
            {strategyCollapsedHeadline(sampling)}
          </p>
          {!expanded ? (
            <p className="mt-0.5 truncate text-[11px] leading-snug text-text-dim">
              {filterBits > 0
                ? t(
                    filterBits === 1
                      ? "personaDisplay.strategy.filterOne"
                      : "personaDisplay.strategy.filterMany",
                    filterBits === 1 ? "{count} filter" : "{count} filters",
                    { count: filterBits },
                  )
                : t("personaDisplay.strategy.noFilters", "No filters")}
              {stratify.length > 0
                ? ` · ${t("personaDisplay.strategy.stratify", "Stratify {fields}", {
                    fields: stratify.map(displayField).join(" × "),
                  })}`
                : ""}
            </p>
          ) : null}
        </div>
        <Sym
          name={expanded ? "expand_less" : "expand_more"}
          size={16}
          className="mt-0.5 shrink-0 text-text-dim"
        />
      </button>

      {expanded ? (
        <div className="mt-1 divide-y divide-outline/30">
          <section className="space-y-1.5 py-2.5">
            <StrategySectionLabel>{t("setup.persona.mode", "Mode")}</StrategySectionLabel>
            <p className="text-[13px] font-medium leading-snug text-text-main">
              {t(`setup.persona.${sampling.mode ?? "custom"}`, strategyModeLabel(sampling.mode))}
            </p>
          </section>

          <section className="space-y-1.5 py-2.5">
            <StrategySectionLabel>
              {t("setup.filters.filters", "Filters")}{filterBits > 0 ? ` · ${filterBits}` : ""}
            </StrategySectionLabel>
            {filterBits > 0 ? (
              <div className="flex flex-wrap gap-1">
                {sources.length > 0 ? (
                  <StrategyFilterValueChip
                    label={t("setup.filters.sources", "Sources")}
                    values={sources}
                    open={openFilterKey === "sources"}
                    onToggle={() =>
                      setOpenFilterKey((key) => (key === "sources" ? null : "sources"))
                    }
                  />
                ) : null}
                {dimEntries.map(([dim, values]) => (
                  <StrategyFilterValueChip
                    key={dim}
                    label={displayField(dim)}
                    values={values}
                    open={openFilterKey === dim}
                    onToggle={() => setOpenFilterKey((key) => (key === dim ? null : dim))}
                  />
                ))}
              </div>
            ) : (
              <p className="text-[12px] leading-snug text-text-dim">
                {t("setup.persona.noFilters", "No filters — full pool.")}
              </p>
            )}
          </section>

          <section className="space-y-2 py-2.5">
            <StrategySectionLabel>{t("setup.persona.sampling", "Sampling")}</StrategySectionLabel>
            <dl className="space-y-1.5">
              {showAllocation ? (
                <StrategyKvRow
                  label={t("setup.persona.allocation", "Allocation")}
                  title={t(
                    sampling.allocation === "perCell"
                      ? "setup.persona.allocationPerCellTitle"
                      : sampling.allocation === "proportional"
                        ? "setup.persona.allocationProportionalTitle"
                        : "setup.persona.allocationEqualTotalTitle",
                    ALLOCATION_TITLES[sampling.allocation],
                  )}
                >
                  <span className="font-medium">{allocLabel}</span>
                  <span className="mt-0.5 block text-[11px] leading-snug text-text-dim">
                    {ALLOCATION_TITLES[sampling.allocation]}
                  </span>
                </StrategyKvRow>
              ) : null}
              {sampleType ? (
                <StrategyKvRow label={t("setup.persona.sampleLabel", "Sample")}>
                  <span className="font-medium">{sampleType}</span>
                </StrategyKvRow>
              ) : null}
              {stratify.length > 0 || sampling.mode === "stratified" ? (
                <StrategyKvRow label={t("setup.filters.stratify", "Stratify")}>
                  {stratify.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {stratify.map((field) => (
                        <span key={field} className={STRATEGY_STRATIFY_CHIP}>
                          {displayField(field)}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="text-text-dim">
                      {t("setup.persona.noStratifyAxes", "No stratify axes")}
                    </span>
                  )}
                </StrategyKvRow>
              ) : null}
            </dl>
          </section>
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

function GenerateProgressBar({
  progress,
}: {
  progress: Pick<PersonaPoolGenerateProgress, "ratio" | "label" | "stage">;
}) {
  const pct = Math.max(0, Math.min(100, Math.round(progress.ratio * 100)));
  return (
    <div className="space-y-1" aria-live="polite">
      <div className="flex items-center justify-between gap-2 text-[11px] leading-snug">
        <span className="min-w-0 truncate text-text-variant">{progress.label}</span>
        <span className="shrink-0 font-mono text-text-dim">{pct}%</span>
      </div>
      <div
        className="h-1.5 overflow-hidden rounded-full bg-outline/35"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label={progress.label}
      >
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-200 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export interface PersonaSamplingRailProps {
  personaModel: string;
  onPersonaModelChange: (model: string) => void;
  personaModelOptions: CockpitSelectOption[];
  mode: PersonaSamplingMode;
  onModeChange: (mode: PersonaSamplingMode) => void;
  selectedPersonaIds: string[];
  onSelectedPersonaIdsChange: (ids: string[]) => void;
  selectedCount?: number;
  onSelectedCountChange?: (count: number) => void;
  useEntirePool?: boolean;
  onUseEntirePoolChange?: (value: boolean) => void;
  sampleSize: number;
  onSampleSizeChange: (size: number) => void;
  /** Personas per stratify combination; null when allocation is proportional / equalTotal. */
  perCell: number | null;
  onSampleSizePerValueGroupChange: (size: number) => void;
  /** Stratified allocation mode (only meaningful when mode === "stratified"). */
  stratifiedAllocation: StratifiedAllocation;
  onStratifiedAllocationChange: (allocation: StratifiedAllocation) => void;
  seed: number;
  filters: PersonaDimensionFilters;
  onFiltersChange: (filters: PersonaDimensionFilters) => void;
  fields: string[];
  onFieldsChange: (fields: string[]) => void;
  taskType?: PlaygroundTaskType;
  /** Active task path — used for strategy pool coverage recovery hints. */
  taskPath?: string | null;
  hasTaskStrategy?: boolean;
  taskPersonaStrategy?: TaskPersonaStrategy | null;
  useTaskDefaultStrategy?: boolean;
  onUseTaskDefaultStrategyChange?: (useDefault: boolean) => void;
  /** Called when sampling resolves to a (possibly materialized) pool path. */
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
  selectedCount = 0,
  onSelectedCountChange,
  useEntirePool = false,
  onUseEntirePoolChange,
  sampleSize,
  onSampleSizeChange,
  perCell,
  onSampleSizePerValueGroupChange,
  stratifiedAllocation,
  onStratifiedAllocationChange,
  seed,
  filters,
  onFiltersChange,
  fields,
  onFieldsChange,
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
  const [filterTarget, setFilterTarget] = useState<"dataset" | "generation">("dataset");
  const [railSegment, setRailSegment] = useState<"generation" | "dataset">("dataset");
  const [detailPersona, setDetailPersona] = useState<PersonaPoolPersonaCard | null>(null);
  const [previewCards, setPreviewCards] = useState<PersonaPoolPersonaCard[]>([]);
  const [pullError, setPullError] = useState<string | null>(null);
    const [pulling, setPulling] = useState(false);
  /** Local draft so users can clear/retype without clamp fighting every keystroke. */
  const [sampleSizeDraft, setSampleSizeDraft] = useState<string | null>(null);
  const [perCellDraft, setPerCellDraft] = useState<string | null>(null);
  const [saveNameDraft, setSaveNameDraft] = useState("");
  const [saveOpen, setSaveOpen] = useState(false);
  const [savingDataset, setSavingDataset] = useState(false);
  const [saveDatasetError, setSaveDatasetError] = useState<string | null>(null);
  const [genMode, setGenMode] = useState<"random" | "stratified">("random");
  const [genCount, setGenCount] = useState(PERSONA_GENERATE_COUNT_DEFAULT);
  const [genCountDraft, setGenCountDraft] = useState<string | null>(null);
  const [genSeed, setGenSeed] = useState(42);
  const [genAllocation, setGenAllocation] = useState<StratifiedAllocation>("perCell");
  const [genPerCell, setGenPerCell] = useState(2);
  const [genSampleSize, setGenSampleSize] = useState(32);
  const [genFilters, setGenFilters] = useState<PersonaDimensionFilters>(emptyPersonaDimensionFilters);
  const [genFields, setGenFields] = useState<string[]>([]);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [generateProgress, setGenerateProgress] = useState<PersonaPoolGenerateProgress | null>(
    null,
  );
  /** Task-default strategy detail — collapses after a successful pull / synthesize. */
  const [strategySummaryOpen, setStrategySummaryOpen] = useState(true);

  const queryClient = useQueryClient();
  const activePool = personaPool?.trim() || PERSONA_BENCH_POOL;
  const sourcePool = datasetSourcePool(activePool);
  const isBenchPool = sourcePool === PERSONA_BENCH_POOL;
  const isProduction1m = sourcePool === PERSONA_PRODUCTION_1M_POOL;
  const canSaveAsDataset =
    (isMaterializedCohortPool(activePool) || isGeneratedDevPool(activePool)) &&
    (selectedCount > 0 || selectedPersonaIds.length > 0);
  const cohortSize = Math.max(selectedCount, selectedPersonaIds.length);
  const sampleSizeMax = isProduction1m
    ? PERSONA_SAMPLE_SIZE_MAX_PRODUCTION
    : PERSONA_SAMPLE_SIZE_MAX_DEV;
  const strategyLocked = hasTaskStrategy && useTaskDefaultStrategy;
  const customSamplingUnlocked = !strategyLocked;
  const strategyView = taskPersonaStrategy ? readStrategySampling(taskPersonaStrategy) : null;
  const panelMode = strategyLocked && strategyView ? strategyView.mode : mode;
  const panelAllocation =
    strategyLocked && strategyView ? strategyView.allocation : stratifiedAllocation;
  const panelFields = strategyLocked && strategyView ? strategyView.fields : fields;

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
    if (panelMode === "single") return quickPickCards;
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
    return previewCards;
  }, [
    quickPickCards,
    previewCards,
    panelMode,
    disabled,
    selectedPersonaIds,
    lockedCohortQuery.data?.personas,
  ]);

  useEffect(() => {
    if (mode === "single") setPreviewCards([]);
  }, [mode]);

  // New task / re-enable Task default → show strategy detail again.
  useEffect(() => {
    if (useTaskDefaultStrategy) setStrategySummaryOpen(true);
  }, [taskPath, useTaskDefaultStrategy]);

  // Turning Task default off resets pool/selection in the parent — drop local preview too.
  useEffect(() => {
    if (!useTaskDefaultStrategy) {
      setPreviewCards([]);
      setPullError(null);
      setGenerateError(null);
    }
  }, [useTaskDefaultStrategy]);

  const togglePersona = useCallback(
    (personaId: string) => {
      if (useEntirePool) {
        // Cohort-ref selection is not per-card editable.
        return;
      }
      if (mode === "single") {
        onSelectedPersonaIdsChange(
          selectedPersonaIds.includes(personaId) ? [] : [personaId],
        );
        onSelectedCountChange?.(
          selectedPersonaIds.includes(personaId) ? 0 : 1,
        );
        return;
      }
      const next = selectedPersonaIds.includes(personaId)
        ? selectedPersonaIds.filter((id) => id !== personaId)
        : [...selectedPersonaIds, personaId];
      onSelectedPersonaIdsChange(next);
      onSelectedCountChange?.(next.length);
    },
    [
      mode,
      onSelectedCountChange,
      onSelectedPersonaIdsChange,
      selectedPersonaIds,
      useEntirePool,
    ],
  );

  const handleSelectAll = useCallback(async () => {
    setPulling(true);
    setPullError(null);
    try {
      const pool = activePool;
      const idsResult = await api.listPersonaPoolIds(pool);
      const count = idsResult.count || idsResult.personaIds.length;
      if (count === 0) {
        throw new ApiError(404, "This dataset has no persona YAML files.");
      }
      const previewIds = idsResult.personaIds.slice(0, PERSONA_CARD_PREVIEW_LIMIT);
      const preview = await api.getPersonaPoolCards({
        pool,
        limit: Math.min(PERSONA_CARD_PREVIEW_LIMIT, count),
        personaIds: previewIds.length ? previewIds : undefined,
      });
      setPreviewCards(preview.personas);
      const truncated = Boolean(idsResult.idsTruncated) || count > PERSONA_UI_ID_LIST_MAX;
      onSelectedCountChange?.(count);
      onUseEntirePoolChange?.(truncated);
      onSelectedPersonaIdsChange(truncated ? preview.personas.map((p) => p.personaId) : idsResult.personaIds);
      onPersonaPoolChange?.(pool);
    } catch (err) {
      const raw =
        err instanceof ApiError ? err.message : "Could not load the full dataset cohort.";
      setPullError(raw);
      } finally {
      setPulling(false);
    }
  }, [
    activePool,
    onPersonaPoolChange,
    onSelectedCountChange,
    onSelectedPersonaIdsChange,
    onUseEntirePoolChange,
  ]);

  const handlePull = useCallback(async () => {
    if (panelMode === "all") {
      await handleSelectAll();
      if (strategyLocked) setStrategySummaryOpen(false);
      return;
    }
    if (panelMode === "stratified" && panelFields.length === 0) {
      setPullError("Pick at least one stratify axis in Persona filters before pulling.");
      return;
    }
    setPulling(true);
    setPullError(null);
    try {
      const dimensionFilters = filtersForSampleApi(filters);
      const isPerCell = panelMode === "stratified" && panelAllocation === "perCell";
      const perCellQuota = isPerCell
        ? clampPerCell(perCell ?? 1)
        : undefined;
      const result = await api.samplePersonaPool({
        pool: sourcePool,
        sampleSize,
        seed,
        sources: filters.sources.length ? filters.sources : undefined,
        dimensionFilters,
        fields: panelMode === "stratified" ? panelFields : undefined,
        perCell: perCellQuota,
        allocation: panelMode === "stratified" ? panelAllocation : undefined,
        taskPath: taskPath?.trim() || undefined,
      });
      const cards = result.personas.slice(0, PERSONA_CARD_PREVIEW_LIMIT).map((row) => ({
        personaId: row.personaId,
        name: row.name ?? `persona-${row.personaId}`,
        source: row.source,
        path: row.path,
        dimensions: row.dimensions ?? {},
      }));
      setPreviewCards(cards);
      const count = result.selectedCount ?? result.sampleSize ?? result.personaIds.length;
      const truncated = Boolean(result.idsTruncated) || count > PERSONA_UI_ID_LIST_MAX;
      onSelectedCountChange?.(count);
      onUseEntirePoolChange?.(truncated);
      onSelectedPersonaIdsChange(result.personaIds);
      if (result.pool) {
        // Launch needs the materialized YAML dir; Dataset UI still shows sourcePool.
        onPersonaPoolChange?.(result.pool);
      }
      if (strategyLocked) setStrategySummaryOpen(false);
    } catch (err) {
      const raw = err instanceof ApiError ? err.message : "Could not pull cohort from this dataset.";
      const formatted = formatPersonaSampleError(raw, taskPath, t);
      setPullError(formatted);
    } finally {
      setPulling(false);
    }
  }, [
    filters,
    handleSelectAll,
    onPersonaPoolChange,
    onSelectedCountChange,
    onSelectedPersonaIdsChange,
    onUseEntirePoolChange,
    panelAllocation,
    panelFields,
    panelMode,
    sampleSize,
    perCell,
    seed,
    sourcePool,
    strategyLocked,
    taskPath,
    t,
  ]);

  const applyGeneratedPool = useCallback(
    async (
      result: PersonaPoolGenerateResult,
      options?: {
        /**
         * Task-default Synthesize replaces a failed Pull — select the fill cohort.
         * Custom Generation only materializes a Dataset; operator still Pulls.
         */
        selectCohort?: boolean;
      },
    ) => {
      await queryClient.invalidateQueries({ queryKey: ["persona-pool-datasets"] });
      const count = result.count;
      const ids = result.personaIds ?? [];
      const selectCohort = options?.selectCohort === true;
      const truncated = selectCohort && count > PERSONA_UI_ID_LIST_MAX;
      const previewIds = ids.slice(0, PERSONA_CARD_PREVIEW_LIMIT);
      onPersonaPoolChange?.(result.pool);
      if (selectCohort) {
        onSelectedCountChange?.(count);
        onUseEntirePoolChange?.(truncated);
        onSelectedPersonaIdsChange(truncated ? previewIds : ids);
      } else {
        // Pool is ready as Dataset — do not treat the whole draw as the launch cohort.
        onSelectedCountChange?.(0);
        onUseEntirePoolChange?.(false);
        onSelectedPersonaIdsChange([]);
        onModeChange("random");
      }
      try {
        const preview = await api.getPersonaPoolCards({
          pool: result.pool,
          limit: Math.min(
            PERSONA_CARD_PREVIEW_LIMIT,
            Math.max(selectCohort ? previewIds.length : 8, 1),
          ),
          personaIds: selectCohort && previewIds.length ? previewIds : undefined,
        });
        setPreviewCards(preview.personas);
      } catch {
        setPreviewCards(
          (selectCohort ? previewIds : ids.slice(0, 8)).map((personaId) => ({
            personaId,
            name: syntheticDisplayName(personaId),
            source: "synthetic",
            dimensions: {},
          })),
        );
      }
      setPullError(null);
      setGenerateError(null);
      setRailSegment("dataset");
      if (useTaskDefaultStrategy) setStrategySummaryOpen(false);
    },
    [
      onModeChange,
      onPersonaPoolChange,
      onSelectedCountChange,
      onSelectedPersonaIdsChange,
      onUseEntirePoolChange,
      queryClient,
      useTaskDefaultStrategy,
    ],
  );

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    setGenerateError(null);
    setGenerateProgress({
      type: "progress",
      stage: "prepare",
      ratio: 0.02,
      label: "Starting generation…",
    });
    try {
      const isStratified = genMode === "stratified";
      if (isStratified && genFields.length === 0) {
        throw new ApiError(422, "Pick at least one stratify field before generating.");
      }
      const dimensionFilters = isStratified ? filtersForSampleApi(genFilters) : undefined;
      const result = await api.generatePersonaPool(
        {
          count: isStratified ? undefined : genCount,
          seed: genSeed,
          dimensionFilters,
          fields: isStratified ? genFields : undefined,
          perCell:
            isStratified && genAllocation === "perCell"
              ? clampPerCell(genPerCell)
              : undefined,
          allocation: isStratified ? genAllocation : undefined,
          sampleSize:
            isStratified && genAllocation !== "perCell" ? genSampleSize : undefined,
        },
        { onProgress: setGenerateProgress },
      );
      await applyGeneratedPool(result, { selectCohort: false });
    } catch (err) {
      setGenerateError(
        err instanceof ApiError ? err.message : "Could not generate a synthetic pool.",
      );
    } finally {
      setGenerating(false);
      setGenerateProgress(null);
    }
  }, [
    applyGeneratedPool,
    genAllocation,
    genCount,
    genFields,
    genFilters,
    genMode,
    genPerCell,
    genSampleSize,
    genSeed,
  ]);

  const handleSynthesizeTask = useCallback(async () => {
    const path = taskPath?.trim();
    if (!path) {
      setPullError("Select a task before synthesizing.");
      return;
    }
    setGenerating(true);
    setPullError(null);
    setGenerateProgress({
      type: "progress",
      stage: "prepare",
      ratio: 0.02,
      label: "Starting synthesize…",
    });
    try {
      const result = await api.generatePersonaPool(
        { taskPath: path },
        { onProgress: setGenerateProgress },
      );
      // Synthesize stands in for Pull when coverage fails under Task default.
      await applyGeneratedPool(result, { selectCohort: true });
    } catch (err) {
      setPullError(
        err instanceof ApiError
          ? err.message
          : "Could not synthesize a pool for this task.",
      );
    } finally {
      setGenerating(false);
      setGenerateProgress(null);
    }
  }, [applyGeneratedPool, taskPath]);

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
      onSelectedCountChange?.(0);
      onUseEntirePoolChange?.(false);
      setPreviewCards([]);
      setPullError(null);
      setDetailPersona(null);
      setSaveOpen(false);
      setSaveDatasetError(null);
      const option = datasetsQuery.data?.datasets?.find((item) => item.pool === pool);
      // Saved cohorts are already curated — default to All (inverse of 1M).
      if (option?.kind === "saved") {
        onModeChange("all");
      } else if (pool === PERSONA_PRODUCTION_1M_POOL && mode === "all") {
        onModeChange("random");
      }
    },
    [
      datasetsQuery.data?.datasets,
      mode,
      onModeChange,
      onPersonaPoolChange,
      onSelectedCountChange,
      onSelectedPersonaIdsChange,
      onUseEntirePoolChange,
      sourcePool,
    ],
  );

  const handleSaveAsDataset = useCallback(async () => {
    const name = saveNameDraft.trim() || `cohort-${cohortSize}`;
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
      onModeChange("all");
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
    cohortSize,
    onModeChange,
    onPersonaPoolChange,
    queryClient,
    saveNameDraft,
    t,
  ]);

  const filterCount = activeFilterCount(filters);
  const poolCount = catalogQuery.data?.count;
  const showModelSelector =
    taskType === "survey" || taskType === "chatbot" || taskType === "web" || taskType === "os-app";
  const poolFooterLabel = isMaterializedCohortPool(activePool)
    ? `${poolSlugLabel(sourcePool)} · ${t("setup.persona.sampleReady", "cohort ready")}`
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
              wideMenu
              showSelectedMeta={false}
              onChange={onPersonaModelChange}
            />
          )}
        </div>

        <div className="cockpit-segment cockpit-segment--grid mb-2 grid-cols-2">
          {(["generation", "dataset"] as const).map((segment) => (
            <button
              key={segment}
              type="button"
              disabled={disabled}
              onClick={() => setRailSegment(segment)}
              className={`cockpit-segment__btn cockpit-segment__btn--compact w-full ${FOCUS_RING} ${
                railSegment === segment ? "cockpit-segment__btn--active" : ""
              }`}
            >
              {t(
                segment === "generation" ? "setup.persona.generation" : "setup.persona.dataset",
                segment === "generation" ? "Generation" : "Dataset",
              )}
            </button>
          ))}
        </div>

        {railSegment === "generation" ? (
          <div className="mb-2 space-y-1.5">
            <div className="cockpit-segment cockpit-segment--grid grid-cols-2">
              {(["random", "stratified"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  disabled={disabled || generating}
                  onClick={() => setGenMode(tab)}
                  className={`cockpit-segment__btn cockpit-segment__btn--compact w-full ${FOCUS_RING} ${
                    genMode === tab ? "cockpit-segment__btn--active" : ""
                  }`}
                >
                  {t(
                    tab === "random" ? "setup.persona.random" : "setup.persona.stratified",
                    tab === "random" ? "Random" : "Stratified",
                  )}
                </button>
              ))}
            </div>
            {genMode === "stratified" ? (
              <div className="cockpit-segment cockpit-segment--grid grid-cols-3">
                {ALLOCATION_ORDER.map((alloc) => (
                  <button
                    key={alloc}
                    type="button"
                    title={t(
                      alloc === "perCell"
                        ? "setup.persona.allocationPerCellTitle"
                        : alloc === "proportional"
                          ? "setup.persona.allocationProportionalTitle"
                          : "setup.persona.allocationEqualTotalTitle",
                      ALLOCATION_TITLES[alloc],
                    )}
                    disabled={disabled || generating}
                    onClick={() => setGenAllocation(alloc)}
                    className={`cockpit-segment__btn cockpit-segment__btn--compact w-full ${FOCUS_RING} ${
                      genAllocation === alloc ? "cockpit-segment__btn--active" : ""
                    }`}
                  >
                    {t(
                      alloc === "perCell"
                        ? "setup.persona.allocationPerCell"
                        : alloc === "proportional"
                          ? "setup.persona.allocationProportional"
                          : "setup.persona.allocationEqualTotal",
                      ALLOCATION_LABELS[alloc],
                    )}
                  </button>
                ))}
              </div>
            ) : null}
            {genMode === "stratified" ? (
              <div className="space-y-1.5">
                <button
                  type="button"
                  disabled={disabled || generating}
                  onClick={() => {
                    setFilterTarget("generation");
                    setFilterOpen(true);
                  }}
                  className={`glass-tile glass-tile--hover flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition ${FOCUS_RING}`}
                >
                  <Sym name="tune" size={16} className="shrink-0 text-primary" />
                  <span className="min-w-0 flex-1 text-[13px] font-medium text-text-main">
                    {t("setup.persona.filters", "Persona filters")}
                  </span>
                  {activeFilterCount(genFilters) > 0 ? (
                    <span className="rounded-full bg-primary/15 px-1.5 font-mono text-[11px] text-primary">
                      {activeFilterCount(genFilters)}
                    </span>
                  ) : null}
                  {genFields.length > 0 ? (
                    <span className="rounded-full bg-secondary/15 px-1.5 font-mono text-[11px] text-secondary">
                      {genFields.length}×
                    </span>
                  ) : null}
                  <Sym name="chevron_right" size={16} className="shrink-0 text-text-dim" />
                </button>
                <PersonaFilterChips
                  filters={genFilters}
                  fields={genFields}
                  showStratify
                />
              </div>
            ) : null}
            <div className="flex items-end gap-2">
              {genMode === "random" ? (
                <>
                  <label className="flex w-[4.25rem] shrink-0 flex-col gap-0.5">
                    <span className="text-[12px] text-text-dim">{t("setup.persona.count", "Count")}</span>
                    <input
                      type="number"
                      inputMode="numeric"
                      min={1}
                      max={PERSONA_GENERATE_COUNT_MAX}
                      step={1}
                      value={genCountDraft ?? genCount}
                      disabled={disabled || generating}
                      onFocus={() => setGenCountDraft(String(genCount))}
                      onChange={(e) => {
                        const raw = e.target.value;
                        if (raw === "" || /^\d+$/.test(raw)) setGenCountDraft(raw);
                      }}
                      onBlur={() => {
                        const raw = genCountDraft;
                        setGenCountDraft(null);
                        setGenCount(
                          clampGenerateCount(
                            raw === "" || raw == null ? genCount : Number(raw),
                          ),
                        );
                      }}
                      className={`h-9 w-full rounded-lg border border-outline/50 bg-surface/60 px-1.5 text-center font-mono text-[15px] text-text-main disabled:opacity-50 ${FOCUS_RING}`}
                    />
                  </label>
                  <label className="flex w-[4.25rem] shrink-0 flex-col gap-0.5">
                    <span className="text-[12px] text-text-dim">{t("setup.persona.seed", "Seed")}</span>
                    <input
                      type="number"
                      inputMode="numeric"
                      step={1}
                      value={genSeed}
                      disabled={disabled || generating}
                      onChange={(e) => setGenSeed(Number(e.target.value) || 0)}
                      className={`h-9 w-full rounded-lg border border-outline/50 bg-surface/60 px-1.5 text-center font-mono text-[15px] text-text-main disabled:opacity-50 ${FOCUS_RING}`}
                    />
                  </label>
                </>
              ) : genAllocation === "perCell" ? (
                <label className="flex w-[4.25rem] shrink-0 flex-col gap-0.5">
                  <span className="text-[12px] text-text-dim">{t("setup.persona.perCell", "Per cell")}</span>
                  <input
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={50}
                    step={1}
                    value={genPerCell}
                    disabled={disabled || generating}
                    onChange={(e) => setGenPerCell(clampPerCell(Number(e.target.value)))}
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
                    max={PERSONA_GENERATE_COUNT_MAX}
                    step={1}
                    value={genSampleSize}
                    disabled={disabled || generating}
                    onChange={(e) =>
                      setGenSampleSize(clampGenerateCount(Number(e.target.value)))
                    }
                    className={`h-9 w-full rounded-lg border border-outline/50 bg-surface/60 px-1.5 text-center font-mono text-[15px] text-text-main disabled:opacity-50 ${FOCUS_RING}`}
                  />
                </label>
              )}
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
                  : t("setup.persona.generate", "Generate")}
              </button>
            </div>
            {generating && generateProgress ? (
              <GenerateProgressBar progress={generateProgress} />
            ) : (
              <p className="text-[11px] leading-snug text-text-dim">
                {t(
                  "setup.persona.generateDescription",
                  "Writes a synthetic Full-DAG pool (no quality filter, dedup, or calibrate).",
                )}
              </p>
            )}
            {generateError ? (
              <div className="rounded-lg border border-danger/30 bg-danger/5 px-2.5 py-2">
                <p className="whitespace-pre-wrap text-[12px] leading-snug text-danger">
                  {generateError}
                </p>
              </div>
            ) : null}
          </div>
        ) : (
        <>
        <div className="mb-2">
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
            className="glass-tile mb-2 rounded-lg px-2.5 py-2"
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
              <TaskStrategySummary
                strategy={taskPersonaStrategy}
                expanded={strategySummaryOpen}
                onExpandedChange={setStrategySummaryOpen}
              />
            ) : null}
          </div>
        ) : null}

        {strategyLocked ? (
          <div className="mb-2 space-y-1.5">
            <button
              type="button"
              disabled={disabled || pulling}
              onClick={() => void handlePull()}
              className={`flex h-9 w-full items-center justify-center gap-1.5 rounded-lg bg-surface-high/90 text-[13px] font-medium text-text-main hover:bg-surface-high disabled:opacity-50 ${FOCUS_RING}`}
            >
              <Sym
                name={pulling ? "autorenew" : "download"}
                size={15}
                className={pulling ? "animate-rb-spin text-primary" : "text-primary"}
              />
              {pulling
                ? t("setup.persona.pulling", "Pulling…")
                : t("setup.persona.pull", "Pull cohort")}
            </button>
            {pullError ? (
              <div className="space-y-1.5 rounded-lg border border-danger/30 bg-danger/5 px-2.5 py-2">
                <p className="whitespace-pre-wrap text-[12px] leading-snug text-danger">{pullError}</p>
                {isPersonaPoolCoverageError(pullError) && Boolean(taskPath?.trim()) ? (
                  <div className="space-y-1.5">
                    <button
                      type="button"
                      disabled={disabled || generating}
                      onClick={() => void handleSynthesizeTask()}
                      className={`flex h-8 w-full items-center justify-center gap-1.5 rounded-md bg-primary/90 text-[12px] font-medium text-white hover:bg-primary disabled:opacity-50 ${FOCUS_RING}`}
                    >
                      <Sym
                        name={generating ? "autorenew" : "auto_awesome"}
                        size={14}
                        className={generating ? "animate-rb-spin" : ""}
                      />
                      {generating
                        ? t("setup.persona.synthesizing", "Synthesizing…")
                        : t("setup.persona.synthesize", "Synthesize to fill this task")}
                    </button>
                    {generating && generateProgress ? (
                      <GenerateProgressBar progress={generateProgress} />
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        {!strategyLocked ? (
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
                  panelMode === tab ? "cockpit-segment__btn--active" : ""
                }`}
              >
                {t(`setup.persona.${tab === "single" ? "quick" : tab}`, TAB_LABELS[tab])}
              </button>
            );
          })}
        </div>
        ) : null}

        {!strategyLocked && panelMode === "stratified" ? (
          <div className="cockpit-segment cockpit-segment--grid mb-2 grid-cols-3">
            {ALLOCATION_ORDER.map((alloc) => (
              <button
                key={alloc}
                type="button"
                title={t(
                  alloc === "perCell"
                    ? "setup.persona.allocationPerCellTitle"
                    : alloc === "proportional"
                      ? "setup.persona.allocationProportionalTitle"
                      : "setup.persona.allocationEqualTotalTitle",
                  ALLOCATION_TITLES[alloc],
                )}
                disabled={disabled || strategyLocked}
                onClick={() => onStratifiedAllocationChange(alloc)}
                className={`cockpit-segment__btn cockpit-segment__btn--compact w-full ${FOCUS_RING} ${
                  panelAllocation === alloc ? "cockpit-segment__btn--active" : ""
                }`}
              >
                {t(
                  alloc === "perCell"
                    ? "setup.persona.allocationPerCell"
                    : alloc === "proportional"
                      ? "setup.persona.allocationProportional"
                      : "setup.persona.allocationEqualTotal",
                  ALLOCATION_LABELS[alloc],
                )}
              </button>
            ))}
          </div>
        ) : null}

        {disabled && selectedPersonaIds.length > 0 ? (
          <p className="glass-tile mb-2 rounded-lg px-2.5 py-1.5 text-[12px] leading-snug text-text-variant">
            {t("setup.persona.cohortLocked", "Cohort locked for this run — use Reset to change personas or sample settings.")}
          </p>
        ) : null}

        {!strategyLocked && panelMode === "all" && (
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
              disabled={disabled || pulling}
              onClick={() => void handleSelectAll()}
              className={`flex h-9 w-full items-center justify-center gap-1.5 rounded-lg bg-surface-high/90 text-[13px] font-medium text-text-main hover:bg-surface-high disabled:opacity-50 ${FOCUS_RING}`}
            >
              <Sym
                name={pulling ? "autorenew" : "done_all"}
                size={15}
                className={pulling ? "animate-rb-spin text-primary" : "text-primary"}
              />
              {pulling
                ? t("setup.persona.loadingCohort", "Loading cohort…")
                : typeof poolCount === "number"
                  ? t("setup.persona.selectAll", "Select all · {count}", { count: poolCount })
                  : t("setup.persona.selectAllPlain", "Select all")}
            </button>
            {pullError ? (
              <div className="space-y-1.5 rounded-lg border border-danger/30 bg-danger/5 px-2.5 py-2">
                <p className="text-[12px] leading-snug text-danger">{pullError}</p>
              </div>
            ) : null}
          </div>
        )}

        {!strategyLocked && panelMode !== "single" && panelMode !== "all" ? (
          <div className="mb-2 space-y-1.5">
            <div className="space-y-1.5">
              {customSamplingUnlocked ? (
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    setFilterTarget("dataset");
                    setFilterOpen(true);
                  }}
                  className={`glass-tile glass-tile--hover flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition ${FOCUS_RING}`}
                >
                  <Sym name="tune" size={16} className="shrink-0 text-primary" />
                  <span className="min-w-0 flex-1 text-[13px] font-medium text-text-main">
                    {t("setup.persona.filters", "Persona filters")}
                  </span>
                  {filterCount > 0 ? (
                    <span
                      className="rounded-full bg-primary/15 px-1.5 font-mono text-[11px] text-primary"
                      title={`${filterCount} filter group${filterCount === 1 ? "" : "s"}`}
                    >
                      {filterCount}
                    </span>
                  ) : null}
                  {panelMode === "stratified" && panelFields.length > 0 ? (
                    <span
                      className="rounded-full bg-secondary/15 px-1.5 font-mono text-[11px] text-secondary"
                      title={`${panelFields.length} stratify axis${panelFields.length === 1 ? "" : "es"}`}
                    >
                      {panelFields.length}×
                    </span>
                  ) : null}
                  <Sym name="chevron_right" size={16} className="shrink-0 text-text-dim" />
                </button>
              ) : null}
              {customSamplingUnlocked ? (
              <PersonaFilterChips
                filters={filters}
                fields={panelFields}
                showStratify={panelMode === "stratified"}
              />
              ) : null}
            </div>

            <div className="flex items-end gap-2">
              {panelMode === "stratified" && panelAllocation === "perCell" ? (
                    <label className="flex w-[4.25rem] shrink-0 flex-col gap-0.5">
                      <span className="text-[12px] text-text-dim">{t("setup.persona.perCell", "Per cell")}</span>
                      <input
                        type="number"
                        inputMode="numeric"
                        min={1}
                        max={50}
                        step={1}
                        value={perCellDraft ?? (perCell ?? 1)}
                        disabled={disabled || strategyLocked}
                        onFocus={() => setPerCellDraft(String(perCell ?? 1))}
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
                                ? (perCell ?? 1)
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
                        disabled={disabled || strategyLocked}
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
              <button
                type="button"
                disabled={disabled || pulling}
                onClick={() => void handlePull()}
                className={`flex h-9 min-w-0 flex-1 items-center justify-center gap-1.5 rounded-lg bg-surface-high/90 text-[13px] font-medium text-text-main hover:bg-surface-high disabled:opacity-50 ${FOCUS_RING}`}
              >
                <Sym
                  name={pulling ? "autorenew" : "download"}
                  size={15}
                  className={pulling ? "animate-rb-spin text-primary" : "text-primary"}
                />
                {pulling
                  ? t("setup.persona.generating", "Pulling…")
                  : t("setup.persona.generatePreview", "Pull cohort")}
              </button>
            </div>
            {pullError ? (
              <div className="space-y-1.5 rounded-lg border border-danger/30 bg-danger/5 px-2.5 py-2">
                <p className="whitespace-pre-wrap text-[12px] leading-snug text-danger">{pullError}</p>
                {useTaskDefaultStrategy &&
                isPersonaPoolCoverageError(pullError) &&
                Boolean(taskPath?.trim()) ? (
                  <div className="space-y-1.5">
                    <button
                      type="button"
                      disabled={disabled || generating}
                      onClick={() => void handleSynthesizeTask()}
                      className={`flex h-8 w-full items-center justify-center gap-1.5 rounded-md bg-primary/90 text-[12px] font-medium text-white hover:bg-primary disabled:opacity-50 ${FOCUS_RING}`}
                    >
                      <Sym
                        name={generating ? "autorenew" : "auto_awesome"}
                        size={14}
                        className={generating ? "animate-rb-spin" : ""}
                      />
                      {generating
                        ? t("setup.persona.synthesizing", "Synthesizing…")
                        : t("setup.persona.synthesize", "Synthesize to fill this task")}
                    </button>
                    {generating && generateProgress ? (
                      <GenerateProgressBar progress={generateProgress} />
                    ) : null}
                  </div>
                ) : null}
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
                        setSaveNameDraft(`sample-${cohortSize}-${stamp}`);
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
        ) : null}
        </>
        )}
      </div>

      {railSegment === "generation" ? (
        <div className="flex min-h-0 flex-1 items-center justify-center px-2">
          <p className="rounded-lg border border-dashed border-outline/40 p-4 text-center text-[13px] leading-snug text-text-dim">
            {t(
              "setup.persona.generationEmpty",
              "Generate writes a new pool. Dataset then switches to it so you can Pull or Save.",
            )}
          </p>
        </div>
      ) : (
      <>
      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto pr-0.5">
          <div className="space-y-2">
            {panelMode === "single" && defaultCardsQuery.isLoading && quickPickCards.length === 0 && (
              <p className="text-[13px] text-text-variant">
                {t("setup.persona.loadingDataset", "Loading {dataset}…", {
                  dataset: activePool.split("/").filter(Boolean).pop() || "dataset",
                })}
              </p>
            )}
            {panelMode === "single" && defaultCardsQuery.isError && quickPickCards.length > 0 && (
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
            {panelMode !== "single" &&
              cohortSize > displayCards.length &&
              displayCards.length > 0 && (
                <p className="rounded-lg border border-dashed border-outline/40 px-3 py-2 text-center text-[12px] text-text-dim">
                  {t("setup.persona.previewing", "Previewing {shown} of {selected} selected", {
                    shown: displayCards.length,
                    selected: cohortSize.toLocaleString(),
                  })}
                  {useEntirePool ? " — launching by cohort ref" : " — full cohort is ready to launch"}.
                </p>
              )}
            {panelMode === "single" && !defaultCardsQuery.isLoading && displayCards.length === 0 && (
              <p className="rounded-lg border border-dashed border-outline/40 p-4 text-center text-[13px] text-text-dim">
                {t("setup.persona.noneLoaded", "No personas loaded. Check that the backend is running.")}
              </p>
            )}
            {panelMode !== "single" && displayCards.length === 0 && !disabled && (
              <p className="rounded-lg border border-dashed border-outline/40 p-4 text-center text-[13px] text-text-dim">
                {strategyLocked
                  ? t("setup.persona.emptyStrategy", "Pull the cohort this task recommends.")
                  : panelMode === "all"
                    ? t("setup.persona.emptyAll", "Select all to use everyone in this dataset.")
                    : t("setup.persona.emptyCustom", "Choose a sample size and Pull a cohort from this dataset.")}
              </p>
            )}
            {panelMode !== "single" &&
              displayCards.length === 0 &&
              disabled &&
              lockedCohortQuery.isLoading && (
                <p className="text-[13px] text-text-variant">{t("setup.persona.loading", "Loading cohort personas…")}</p>
              )}
          </div>
      </div>

      <p className="mt-2 shrink-0 truncate text-center font-mono text-[12px] tracking-wide text-text-dim">
        <span className="font-semibold text-primary">{cohortSize.toLocaleString()}</span> {t("setup.persona.selected", "selected")} ·{" "}
        {poolFooterLabel}
      </p>
      </>
      )}
      </>
      )}

      <PersonaFilterModal
        open={filterOpen}
        catalog={catalogQuery.data ?? null}
        filters={filterTarget === "generation" ? genFilters : filters}
        stratifyMode={
          filterTarget === "generation" ? genMode === "stratified" : panelMode === "stratified"
        }
        fields={filterTarget === "generation" ? genFields : fields}
        onFieldsChange={filterTarget === "generation" ? setGenFields : onFieldsChange}
        onClose={() => setFilterOpen(false)}
        onConfirm={(next) => {
          if (filterTarget === "generation") {
            setGenFilters(next);
            return;
          }
          onFiltersChange(next);
        }}
      />

    </aside>
  );
}
