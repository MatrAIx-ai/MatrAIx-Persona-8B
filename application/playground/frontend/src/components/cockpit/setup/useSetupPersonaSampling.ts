import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { takePersonaHandoff, peekPersonaHandoff } from "@/lib/personaHandoffStorage";
import { useUrlState } from "@/lib/useUrlState";
import type { HarborCockpitTaskKind } from "@/lib/harborCockpitMappers";
import type { ConfigOptionsResponse, PlaygroundPersona, TaskPersonaStrategy } from "@/lib/types";
import { PERSONA_BENCH_POOL } from "@/lib/types";

import {
  defaultPersonaSetup,
  hasStoredPersonaSetup,
  isTaskStrategyFillPool,
  readCockpitPersonaSetup,
  sanitizePersonaPool,
  scrubTaskStrategyFillForCustomMode,
  setupFromPersonaStrategy,
  writeCockpitPersonaSetup,
  type CockpitPersonaSetupRecord,
} from "./cockpitPersonaSetupStorage";
import {
  emptyPersonaDimensionFilters,
  readStrategySampling,
  type PersonaDimensionFilters,
  type PersonaSamplingMode,
  type StratifiedAllocation,
} from "./personaSamplingTypes";

function applyPersonaHandoffToSetup(
  handoff: { pool: string; personaIds: string[] },
  base: CockpitPersonaSetupRecord,
): CockpitPersonaSetupRecord {
  const ids = handoff.personaIds.filter(Boolean);
  return {
    ...base,
    selectedPersonaIds: ids,
    selectedCount: ids.length,
    useEntirePool: false,
    personaPool: sanitizePersonaPool(handoff.pool) || base.personaPool || PERSONA_BENCH_POOL,
    samplingMode: ids.length > 1 ? "random" : "single",
    useTaskDefaultStrategy: false,
    taskDefaultStrategyDismissed: true,
  };
}

const PERSONA_MODEL_PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic",
  dashscope: "DashScope",
  openai: "OpenAI",
  openrouter: "OpenRouter",
};

function personaModelProviderLabel(modelId: string): string | undefined {
  return PERSONA_MODEL_PROVIDER_LABELS[modelId.split("/", 1)[0]];
}

export function useSetupPersonaSampling(
  options: ConfigOptionsResponse | null,
  taskKind: HarborCockpitTaskKind,
  taskPath: string | null = null,
  isActive = true,
) {
  const fallbackPersonaModel =
    options?.environment.personaModel ?? "anthropic/claude-haiku-4-5";
  const normalizedPath = taskPath?.trim() || null;
  const [initial] = useState(() =>
    readCockpitPersonaSetup(taskKind, fallbackPersonaModel, normalizedPath),
  );

  const [personaModel, setPersonaModel] = useState<string>(
    initial.personaModel === "anthropic/claude-sonnet-4-6" ? fallbackPersonaModel : initial.personaModel,
  );
  const [samplingMode, setSamplingMode] = useState<PersonaSamplingMode>(initial.samplingMode);
  const [selectedPersonaIds, setSelectedPersonaIds] = useState<string[]>(initial.selectedPersonaIds);
  const [selectedCount, setSelectedCount] = useState(initial.selectedCount);
  const [useEntirePool, setUseEntirePool] = useState(initial.useEntirePool);
  const [groupFilters, setGroupFilters] = useState<PersonaDimensionFilters>(initial.groupFilters);
  const [fields, setFields] = useState<string[]>(initial.fields);
  const [stratifiedAllocation, setStratifiedAllocationState] = useState<StratifiedAllocation>(
    initial.stratifiedAllocation,
  );
  const [sampleSize, setSampleSize] = useState(initial.sampleSize);
  const [perCell, setPerCell] = useState(
    initial.perCell,
  );
  const [seed] = useState(42);
  const [parallelTrials, setParallelTrials] = useState(initial.parallelTrials);
  const [personaPool, setPersonaPool] = useState(
    sanitizePersonaPool(initial.personaPool) || PERSONA_BENCH_POOL,
  );
  const [persona, setPersona] = useState<PlaygroundPersona | null>(null);
  const [taskPersonaStrategy, setTaskPersonaStrategy] = useState<TaskPersonaStrategy | null>(null);
  const [useTaskDefaultStrategy, setUseTaskDefaultStrategyState] = useState(
    initial.useTaskDefaultStrategy,
  );
  const [taskDefaultStrategyDismissed, setTaskDefaultStrategyDismissed] = useState(
    initial.taskDefaultStrategyDismissed === true,
  );
  const hydratedPathRef = useRef<string | null>(null);
  const skipNextPersistRef = useRef(false);
  const handoffAppliedRef = useRef(false);
  const { state: urlState, setState: setUrlState } = useUrlState();

  const strategyQuery = useQuery({
    queryKey: ["task-persona-strategy", normalizedPath],
    queryFn: async () => {
      if (!normalizedPath) return null;
      const response = await api.getTaskPersonaStrategy(normalizedPath);
      return response.personaStrategy ?? null;
    },
    enabled: Boolean(normalizedPath),
    staleTime: 60_000,
  });

  const applySetupRecord = useCallback((record: CockpitPersonaSetupRecord) => {
    skipNextPersistRef.current = true;
    setSamplingMode(record.samplingMode);
    setSelectedPersonaIds(record.selectedPersonaIds);
    setSelectedCount(record.selectedCount);
    setUseEntirePool(record.useEntirePool);
    setGroupFilters(record.groupFilters);
    setFields(record.fields);
    setStratifiedAllocationState(record.stratifiedAllocation);
    setSampleSize(record.sampleSize);
    setPerCell(record.perCell);
    setPersonaModel(record.personaModel);
    setParallelTrials(record.parallelTrials);
    setPersonaPool(sanitizePersonaPool(record.personaPool));
    setUseTaskDefaultStrategyState(record.useTaskDefaultStrategy);
    setTaskDefaultStrategyDismissed(record.taskDefaultStrategyDismissed === true);
  }, []);

  const setStratifiedAllocation = useCallback((next: StratifiedAllocation) => {
    setStratifiedAllocationState(next);
    if (next === "perCell") {
      setPerCell((prev) => (prev == null ? 1 : prev));
    } else {
      setPerCell(null);
    }
  }, []);

  const resetToTaskStrategy = useCallback(() => {
    const strategy = strategyQuery.data ?? taskPersonaStrategy;
    const applied = setupFromPersonaStrategy(strategy, fallbackPersonaModel, {
      ...defaultPersonaSetup(fallbackPersonaModel),
      personaModel,
      parallelTrials,
    });
    applySetupRecord(applied);
    setTaskPersonaStrategy(strategy);
  }, [
    applySetupRecord,
    fallbackPersonaModel,
    parallelTrials,
    personaModel,
    strategyQuery.data,
    taskPersonaStrategy,
  ]);

  const setUseTaskDefaultStrategy = useCallback(
    (next: boolean) => {
      if (next) {
        resetToTaskStrategy();
        return;
      }
      // Explicit opt-out: leave the task-fill / strategy cohort and return to
      // the stock Quick-pick sandbox (dev-sample + empty selection).
      const defaults = defaultPersonaSetup(fallbackPersonaModel);
      setTaskDefaultStrategyDismissed(true);
      setUseTaskDefaultStrategyState(false);
      setPersonaPool(PERSONA_BENCH_POOL);
      setSelectedPersonaIds([]);
      setSelectedCount(0);
      setUseEntirePool(false);
      setSamplingMode(defaults.samplingMode);
      setGroupFilters(emptyPersonaDimensionFilters());
      setFields(defaults.fields);
      setStratifiedAllocationState(defaults.stratifiedAllocation);
      setSampleSize(defaults.sampleSize);
      setPerCell(defaults.perCell);
    },
    [fallbackPersonaModel, resetToTaskStrategy],
  );

  useEffect(() => {
    setTaskPersonaStrategy(strategyQuery.data ?? null);
  }, [strategyQuery.data]);

  const appliedKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (!useTaskDefaultStrategy) {
      appliedKeyRef.current = null;
      return;
    }
    const strategy = strategyQuery.data;
    if (!strategy) return;
    const sampling = readStrategySampling(strategy);
    const key = `${normalizedPath ?? ""}:${sampling.mode}:${sampling.allocation}:${sampling.sampleSize ?? ""}:${sampling.perCell ?? ""}:${sampling.fields.join(",")}`;
    if (appliedKeyRef.current === key) return;
    appliedKeyRef.current = key;
    setSamplingMode(sampling.mode);
    if (sampling.fields.length > 0) {
      setFields(sampling.fields);
    }
    setStratifiedAllocationState(sampling.allocation);
    if (sampling.allocation === "perCell") {
      setPerCell(Math.min(50, Math.max(1, sampling.perCell ?? 1)));
    } else {
      setPerCell(null);
      if (sampling.sampleSize != null) {
        setSampleSize(Math.min(500, Math.max(2, sampling.sampleSize)));
      }
    }
    setGroupFilters({
      sources: Array.isArray(strategy.sources)
        ? strategy.sources.filter(
            (value): value is string => typeof value === "string" && Boolean(value.trim()),
          )
        : [],
      dimensionFilters:
        strategy.dimensionFilters && typeof strategy.dimensionFilters === "object"
          ? Object.fromEntries(
              Object.entries(strategy.dimensionFilters)
                .map(([key, values]) => [
                  key,
                  Array.isArray(values)
                    ? values.filter(
                        (value): value is string =>
                          typeof value === "string" && Boolean(value.trim()),
                      )
                    : [],
                ])
                .filter(([, values]) => (values as string[]).length > 0),
            )
          : {},
    });
  }, [normalizedPath, strategyQuery.data, useTaskDefaultStrategy]);

  useEffect(() => {
    const path = normalizedPath;
    if (!path) {
      hydratedPathRef.current = null;
      return;
    }
    if (hydratedPathRef.current === path) return;

    // Wait for strategy fetch so default-on can re-apply persona_strategy.json.
    if (strategyQuery.isFetching || strategyQuery.isLoading) return;

    const stored = readCockpitPersonaSetup(taskKind, fallbackPersonaModel, path);
    const strategy = strategyQuery.data;
    const dismissed = stored.taskDefaultStrategyDismissed === true;

    const hasTaskSpecificStore = hasStoredPersonaSetup(path);
    const effectiveModel = hasTaskSpecificStore ? stored.personaModel : fallbackPersonaModel;

    let applied: CockpitPersonaSetupRecord;
    if (strategy && !dismissed) {
      applied = setupFromPersonaStrategy(strategy, fallbackPersonaModel, {
        ...defaultPersonaSetup(fallbackPersonaModel),
        personaModel: effectiveModel,
        parallelTrials: stored.parallelTrials,
      });
      // Keep last cohort selection across remount/navigation. Strategy apply
      // clears preview ids intentionally for explicit "Task default" toggles,
      // but hydrate must not wipe a selection the operator already made.
      if (stored.selectedPersonaIds.length > 0 || stored.selectedCount > 0) {
        applied.selectedPersonaIds = stored.selectedPersonaIds;
        applied.selectedCount = stored.selectedCount || stored.selectedPersonaIds.length;
        applied.useEntirePool = stored.useEntirePool;
      }
      // Task-fill pools belong to Task default ON — restore them with the cohort.
      if (isTaskStrategyFillPool(stored.personaPool)) {
        applied.personaPool = sanitizePersonaPool(stored.personaPool);
      }
    } else if (hasTaskSpecificStore) {
      // Custom / dismissed: restore draft, but never sticky-restore a task-fill pool.
      applied = scrubTaskStrategyFillForCustomMode(
        {
          ...stored,
          useTaskDefaultStrategy: Boolean(strategy) && stored.useTaskDefaultStrategy,
          taskDefaultStrategyDismissed: dismissed,
        },
        fallbackPersonaModel,
      );
    } else {
      applied = setupFromPersonaStrategy(strategy, fallbackPersonaModel, {
        ...defaultPersonaSetup(fallbackPersonaModel),
        personaModel: effectiveModel,
        parallelTrials: stored.parallelTrials,
      });
      if (stored.selectedPersonaIds.length > 0 || stored.selectedCount > 0) {
        applied.selectedPersonaIds = stored.selectedPersonaIds;
        applied.selectedCount = stored.selectedCount || stored.selectedPersonaIds.length;
        applied.useEntirePool = stored.useEntirePool;
      }
    }

    const handoff = isActive ? peekPersonaHandoff() : null;
    if (handoff && handoff.personaIds.length > 0) {
      applied = applyPersonaHandoffToSetup(handoff, applied);
      takePersonaHandoff();
      handoffAppliedRef.current = true;
      if (urlState.pgPersonaHandoff) {
        setUrlState({ pgPersonaHandoff: null });
      }
    }

    applySetupRecord(applied);
    hydratedPathRef.current = path;
  }, [
    applySetupRecord,
    fallbackPersonaModel,
    isActive,
    normalizedPath,
    setUrlState,
    strategyQuery.data,
    strategyQuery.isFetching,
    strategyQuery.isLoading,
    taskKind,
    urlState.pgPersonaHandoff,
  ]);

  // Handoff while already on a hydrated task (Persona World → Playground).
  useEffect(() => {
    if (urlState.pgPersonaHandoff === "1") {
      handoffAppliedRef.current = false;
    }
  }, [urlState.pgPersonaHandoff]);

  useEffect(() => {
    if (!isActive) return;
    if (handoffAppliedRef.current) return;
    if (!normalizedPath || hydratedPathRef.current !== normalizedPath) return;
    if (urlState.pgPersonaHandoff !== "1" && !peekPersonaHandoff()) return;

    const handoff = takePersonaHandoff();
    if (!handoff?.personaIds.length) {
      if (urlState.pgPersonaHandoff) setUrlState({ pgPersonaHandoff: null });
      return;
    }
    handoffAppliedRef.current = true;
    const base = readCockpitPersonaSetup(taskKind, fallbackPersonaModel, normalizedPath);
    applySetupRecord(applyPersonaHandoffToSetup(handoff, base));
    setUrlState({ pgPersonaHandoff: null });
  }, [
    applySetupRecord,
    fallbackPersonaModel,
    isActive,
    normalizedPath,
    setUrlState,
    taskKind,
    urlState.pgPersonaHandoff,
  ]);

  useEffect(() => {
    // Do not persist the pre-hydrate default (useTaskDefaultStrategy=false) —
    // that used to lock Task default strategy Off in localStorage forever.
    if (!normalizedPath || hydratedPathRef.current !== normalizedPath) {
      return;
    }
    if (skipNextPersistRef.current) {
      skipNextPersistRef.current = false;
      return;
    }
    const draft: CockpitPersonaSetupRecord = {
      selectedPersonaIds,
      selectedCount,
      useEntirePool,
      samplingMode,
      groupFilters,
      fields,
      stratifiedAllocation,
      sampleSize,
      perCell,
      parallelTrials,
      personaModel,
      personaPool,
      useTaskDefaultStrategy,
      taskDefaultStrategyDismissed,
    };
    // Task-fill pools are valid only while Task default is on.
    writeCockpitPersonaSetup(
      taskKind,
      useTaskDefaultStrategy
        ? draft
        : scrubTaskStrategyFillForCustomMode(draft, fallbackPersonaModel),
      normalizedPath,
    );
  }, [
    taskKind,
    normalizedPath,
    selectedPersonaIds,
    selectedCount,
    useEntirePool,
    samplingMode,
    groupFilters,
    fields,
    stratifiedAllocation,
    sampleSize,
    perCell,
    parallelTrials,
    personaModel,
    personaPool,
    useTaskDefaultStrategy,
    taskDefaultStrategyDismissed,
    fallbackPersonaModel,
  ]);

  useEffect(() => {
    const id = selectedPersonaIds[0];
    if (!id) {
      setPersona(null);
      return;
    }
    setPersona({
      id,
      name: `persona-${id}`,
      source: "matraix-persona-dev-sample",
    });
  }, [selectedPersonaIds]);

  const isBatchRun =
    samplingMode !== "single" || selectedCount > 1 || selectedPersonaIds.length > 1;

  const personaModelKnob = options?.knobs.find((k) => k.key === "personaModel");
  // Provider meta only in the open menu (closed trigger stays label-only).
  // Omit summary — long descriptions clutter the compact Persona rail.
  const personaModelOptions =
    personaModelKnob?.options.map((o) => ({
      value: o.value,
      label: o.label,
      meta: personaModelProviderLabel(o.value),
    })) ?? [{ value: personaModel, label: personaModel }];

  const togglePersona = useCallback(
    (personaId: string) => {
      if (useEntirePool) {
        // Ref-based cohorts are not individually toggled; keep preview selection cosmetic.
        return;
      }
      if (samplingMode === "single") {
        setSelectedPersonaIds((prev) => {
          const next = prev.includes(personaId) ? [] : [personaId];
          setSelectedCount(next.length);
          return next;
        });
        return;
      }
      setSelectedPersonaIds((prev) => {
        const next = prev.includes(personaId)
          ? prev.filter((id) => id !== personaId)
          : [...prev, personaId];
        setSelectedCount(next.length);
        return next;
      });
    },
    [samplingMode, useEntirePool],
  );

  const hasTaskStrategy = Boolean(taskPersonaStrategy);

  return {
    persona,
    personaModel,
    setPersonaModel,
    personaModelOptions,
    samplingMode,
    setSamplingMode,
    selectedPersonaIds,
    setSelectedPersonaIds,
    selectedCount,
    setSelectedCount,
    useEntirePool,
    setUseEntirePool,
    togglePersona,
    groupFilters,
    setGroupFilters,
    fields,
    setFields,
    stratifiedAllocation,
    setStratifiedAllocation,
    sampleSize,
    setSampleSize,
    perCell,
    setPerCell,
    seed,
    parallelTrials,
    setParallelTrials,
    personaPool,
    setPersonaPool,
    isBatchRun,
    hasTaskStrategy,
    taskPersonaStrategy,
    useTaskDefaultStrategy: hasTaskStrategy && useTaskDefaultStrategy,
    setUseTaskDefaultStrategy,
  };
}
