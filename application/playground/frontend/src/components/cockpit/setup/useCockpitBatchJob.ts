import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { I18nContextValue } from "@/i18n/I18nProvider";
import type { PersonaPoolPersonaCard } from "@/lib/types";
import { PERSONA_CARD_PREVIEW_LIMIT } from "@/lib/types";
import { useHarborBatchLive } from "@/lib/useHarborBatchLive";
import type { HarborCockpitPhase } from "@/lib/useHarborCockpitRun";
import type { HarborCockpitTaskKind } from "@/lib/harborCockpitMappers";
import { useUrlState } from "@/lib/useUrlState";

import { useHarborBatchStatus } from "@/lib/useHarborBatchStatus";

import { buildBatchCellsFromStatus, buildBatchGridCells } from "./BatchTrialGrid";
import { readCockpitBatch, writeCockpitBatch } from "./cockpitBatchStorage";
import { BATCH_MOSAIC_THRESHOLD } from "./useBatchGridLayout";
import type { RunLaunchPhase } from "./RunLaunchBar";

function initialBatchState(taskKind?: HarborCockpitTaskKind) {
  if (!taskKind) {
    return {
      jobName: null as string | null,
      personaIds: [] as string[],
      selectedCount: 0,
      taskId: null as string | null,
      personaPool: null as string | null,
    };
  }
  const saved = readCockpitBatch(taskKind);
  return {
    jobName: saved?.jobName ?? null,
    personaIds: saved?.personaIds ?? [],
    selectedCount: saved?.selectedCount ?? saved?.personaIds.length ?? 0,
    taskId: saved?.taskId ?? null,
    personaPool: saved?.personaPool ?? null,
  };
}

export function useCockpitBatchJob(
  selectedPersonaIds: string[],
  parallelTrials = 1,
  taskKind?: HarborCockpitTaskKind,
  selectedCount = 0,
  personaPool: string | null = null,
) {
  const { state: urlState, setState: setUrlState } = useUrlState();
  const [initial] = useState(() => initialBatchState(taskKind));
  const [batchJobName, setBatchJobNameInternal] = useState<string | null>(initial.jobName);
  const [restoredPersonaIds, setRestoredPersonaIds] = useState<string[]>(initial.personaIds);
  const [restoredSelectedCount, setRestoredSelectedCount] = useState(initial.selectedCount);
  const [restoredTaskId, setRestoredTaskId] = useState<string | null>(initial.taskId);
  const [restoredPersonaPool, setRestoredPersonaPool] = useState<string | null>(
    initial.personaPool,
  );
  /** Operator stopped the batch — keep attachment locked until Reset. */
  const [batchCancelled, setBatchCancelled] = useState(false);

  // Freeze the cohort to the batch launch snapshot until the user resets.
  const effectivePersonaIds = batchJobName
    ? restoredPersonaIds.length > 0
      ? restoredPersonaIds
      : selectedPersonaIds
    : selectedPersonaIds.length > 0
      ? selectedPersonaIds
      : restoredPersonaIds;

  // Large cohorts drop the heavy per-trial live feed for a lightweight,
  // incremental aggregate status feed that scales to tens of thousands.
  const aggregate = effectivePersonaIds.length > BATCH_MOSAIC_THRESHOLD;
  const batchLive = useHarborBatchLive(batchJobName, {
    enabled: !aggregate && !batchCancelled,
  });
  const statusFeed = useHarborBatchStatus(
    batchCancelled ? null : batchJobName,
    aggregate,
  );

  const setBatchJobName = useCallback(
    (jobName: string | null, meta?: { taskId?: string; personaPool?: string }) => {
      setBatchJobNameInternal(jobName);
      if (!taskKind) return;

      if (jobName) {
        setBatchCancelled(false);
        const personaIds = selectedPersonaIds.length > 0 ? selectedPersonaIds : restoredPersonaIds;
        const cohortSize = Math.max(
          selectedCount,
          personaIds.length,
          restoredSelectedCount,
        );
        const taskId = meta?.taskId ?? restoredTaskId ?? undefined;
        const launchPool =
          meta?.personaPool?.trim() || personaPool?.trim() || restoredPersonaPool || undefined;
        writeCockpitBatch(taskKind, {
          jobName,
          personaIds,
          selectedCount: cohortSize,
          taskId,
          personaPool: launchPool,
        });
        if (selectedPersonaIds.length > 0) {
          setRestoredPersonaIds(selectedPersonaIds);
        }
        setRestoredSelectedCount(cohortSize);
        if (taskId) {
          setRestoredTaskId(taskId);
        }
        setRestoredPersonaPool(launchPool ?? null);
        if (urlState.pgTask === taskKind) {
          setUrlState({
            cockpitBatch: jobName,
            cockpitJob: null,
            cockpitTrial: null,
            pgTask: taskKind,
          });
        }
      } else {
        setBatchCancelled(false);
        writeCockpitBatch(taskKind, null);
        setRestoredPersonaIds([]);
        setRestoredSelectedCount(0);
        setRestoredTaskId(null);
        setRestoredPersonaPool(null);
        if (urlState.pgTask === taskKind) {
          setUrlState({ cockpitBatch: null });
        }
      }
    },
    [
      personaPool,
      restoredPersonaIds,
      restoredPersonaPool,
      restoredSelectedCount,
      restoredTaskId,
      selectedCount,
      selectedPersonaIds,
      setUrlState,
      taskKind,
      urlState.pgTask,
    ],
  );

  const clearBatch = useCallback(() => setBatchJobName(null), [setBatchJobName]);
  const [cancelBusy, setCancelBusy] = useState(false);
  const [retryBusy, setRetryBusy] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  const cancelBatch = useCallback(async () => {
    if (!batchJobName || cancelBusy || batchCancelled) return;
    setCancelBusy(true);
    try {
      await api.deleteHarborJob(batchJobName);
      // Keep batchJobName so rails stay locked until Reset (same as done/failed).
      setBatchCancelled(true);
    } finally {
      setCancelBusy(false);
    }
  }, [batchCancelled, batchJobName, cancelBusy]);

  const retryFailed = useCallback(async () => {
    if (!batchJobName || retryBusy) return;
    setRetryBusy(true);
    setRetryError(null);
    try {
      await api.retryHarborJobFailed(batchJobName);
    } catch (exc) {
      setRetryError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setRetryBusy(false);
    }
  }, [batchJobName, retryBusy]);

  // Preview-only: launch uses the full ID list; the mosaic does not need every card.
  const previewPersonaIds = useMemo(
    () => effectivePersonaIds.slice(0, PERSONA_CARD_PREVIEW_LIMIT),
    [effectivePersonaIds],
  );

  // Launches that predate pool persistence: recover the resolved pool from the
  // job config's persona_path (…/cohorts/cohort-x/persona_y.yaml → cohort dir).
  const jobPoolQuery = useQuery({
    queryKey: ["batch-job-persona-pool", batchJobName],
    queryFn: () => api.getHarborJob(batchJobName as string),
    enabled: Boolean(batchJobName) && !restoredPersonaPool,
    staleTime: Infinity,
  });
  const derivedJobPool = useMemo(() => {
    const agents = (jobPoolQuery.data?.config as { agents?: unknown } | null | undefined)?.agents;
    if (!Array.isArray(agents)) return null;
    for (const agent of agents) {
      const path = (agent as { kwargs?: { persona_path?: unknown } } | null)?.kwargs
        ?.persona_path;
      if (typeof path === "string" && path.includes("/")) {
        return path.slice(0, path.lastIndexOf("/"));
      }
    }
    return null;
  }, [jobPoolQuery.data?.config]);

  const batchPersonaPool = restoredPersonaPool ?? derivedJobPool;

  // While a batch is locked, the launch-time pool wins: after a reload the
  // setup store may have reverted to the raw dataset (e.g. matraix-persona-1m),
  // which rejects id lookups — only the resolved cohort path serves cards.
  const cardsPool = (batchJobName ? batchPersonaPool ?? personaPool : personaPool) ?? undefined;

  const personaCardsQuery = useQuery({
    queryKey: ["batch-cohort-personas", cardsPool ?? "", previewPersonaIds.join(",")],
    queryFn: () =>
      api.getPersonaPoolCards({
        pool: cardsPool,
        personaIds: previewPersonaIds,
        limit: previewPersonaIds.length,
      }),
    enabled: previewPersonaIds.length > 0,
    staleTime: 300_000,
  });

  const personaById = useMemo(() => {
    const map: Record<string, PersonaPoolPersonaCard> = {};
    for (const card of personaCardsQuery.data?.personas ?? []) {
      map[card.personaId] = card;
    }
    return map;
  }, [personaCardsQuery.data?.personas]);

  const statusSnapshot = statusFeed.snapshot;
  const expectedTrialCount = Math.max(
    batchJobName ? restoredSelectedCount : selectedCount,
    effectivePersonaIds.length,
    statusSnapshot?.trialCount ?? 0,
    batchLive.live?.trialCount ?? 0,
    batchLive.live?.trials.length ?? 0,
  );

  const completedTrials =
    aggregate && statusSnapshot
      ? statusSnapshot.counts.done + statusSnapshot.counts.error
      : batchLive.live?.completedTrials ?? 0;

  const failedTrials =
    aggregate && statusSnapshot
      ? statusSnapshot.counts.error
      : (batchLive.live?.trials ?? []).filter(
          (trial) => trial.completed && trial.error != null,
        ).length;

  const isBatchActive =
    Boolean(batchJobName) && !batchCancelled
      ? aggregate
        ? statusSnapshot == null ||
          statusSnapshot.launchStatus === "running" ||
          statusSnapshot.launchStatus === "queued" ||
          completedTrials < expectedTrialCount
        : batchLive.isActive
      : false;

  const batchComplete =
    Boolean(batchJobName) &&
    !batchCancelled &&
    completedTrials >= expectedTrialCount &&
    expectedTrialCount > 0;

  const batchGridCells = useMemo(() => {
    if (aggregate && statusSnapshot) {
      return buildBatchCellsFromStatus(statusSnapshot, {
        expectedTotal: expectedTrialCount,
        personaIds: effectivePersonaIds,
        personaById,
      });
    }
    return buildBatchGridCells(effectivePersonaIds, batchLive.live?.trials, {
      jobStarted: Boolean(batchJobName),
      parallelTrials,
      personaById,
      expectedTotal: expectedTrialCount,
    });
  }, [
    aggregate,
    statusSnapshot,
    effectivePersonaIds,
    expectedTrialCount,
    batchLive.live?.trials,
    batchJobName,
    parallelTrials,
    personaById,
  ]);

  return {
    batchJobName,
    batchTaskId: restoredTaskId,
    batchPersonaIds: effectivePersonaIds,
    batchPersonaPool,
    setBatchJobName,
    batchLive,
    clearBatch,
    cancelBatch,
    cancelBusy,
    batchCancelled,
    retryFailed,
    retryBusy,
    retryError,
    failedTrials,
    isBatchActive,
    batchComplete,
    batchGridCells,
    completedTrials,
    expectedTrialCount,
    personaById,
    batchError: batchCancelled
      ? null
      : aggregate
        ? statusFeed.error
        : batchLive.error,
  };
}

export function resolveRunLaunchPhase(
  batchJobName: string | null,
  batchComplete: boolean,
  batchError: string | null,
  phase: HarborCockpitPhase,
  batchCancelled = false,
): RunLaunchPhase {
  if (batchJobName) {
    if (batchCancelled) return "error";
    if (batchComplete) return "done";
    if (batchError) return "error";
    return "running";
  }
  if (phase === "launching") return "launching";
  if (phase === "running") return "running";
  if (phase === "done") return "done";
  if (phase === "error" || phase === "timeout") return "error";
  return "idle";
}

export function batchProgressPct(
  batchJobName: string | null,
  completedTrials: number | undefined,
  expectedTrialCount: number,
): number {
  if (!batchJobName || expectedTrialCount <= 0) return 0;
  return Math.round(((completedTrials ?? 0) / expectedTrialCount) * 100);
}

/** Batch footer progress — counts simulated people, not job re-runs. */
export function formatBatchProgressLabel(
  t: I18nContextValue["t"],
  completed: number,
  total: number,
): string {
  const done = Math.max(0, Math.min(completed, total));
  if (total <= 0) return t("eval.progress.batchRun");
  if (done >= total) {
    return t("eval.progress.batchAllFinished", { total });
  }
  return t("eval.progress.batchFinished", { done, total });
}
