import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
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
    return { jobName: null as string | null, personaIds: [] as string[], taskId: null as string | null };
  }
  const saved = readCockpitBatch(taskKind);
  return {
    jobName: saved?.jobName ?? null,
    personaIds: saved?.personaIds ?? [],
    taskId: saved?.taskId ?? null,
  };
}

export function useCockpitBatchJob(
  selectedPersonaIds: string[],
  parallelTrials = 1,
  taskKind?: HarborCockpitTaskKind,
) {
  const { state: urlState, setState: setUrlState } = useUrlState();
  const [initial] = useState(() => initialBatchState(taskKind));
  const [batchJobName, setBatchJobNameInternal] = useState<string | null>(initial.jobName);
  const [restoredPersonaIds, setRestoredPersonaIds] = useState<string[]>(initial.personaIds);
  const [restoredTaskId, setRestoredTaskId] = useState<string | null>(initial.taskId);

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
  const batchLive = useHarborBatchLive(batchJobName, { enabled: !aggregate });
  const statusFeed = useHarborBatchStatus(batchJobName, aggregate);

  const setBatchJobName = useCallback(
    (jobName: string | null, meta?: { taskId?: string }) => {
      setBatchJobNameInternal(jobName);
      if (!taskKind) return;

      if (jobName) {
        const personaIds = selectedPersonaIds.length > 0 ? selectedPersonaIds : restoredPersonaIds;
        const taskId = meta?.taskId ?? restoredTaskId ?? undefined;
        writeCockpitBatch(taskKind, { jobName, personaIds, taskId });
        if (selectedPersonaIds.length > 0) {
          setRestoredPersonaIds(selectedPersonaIds);
        }
        if (taskId) {
          setRestoredTaskId(taskId);
        }
        if (urlState.pgTask === taskKind) {
          setUrlState({
            cockpitBatch: jobName,
            cockpitJob: null,
            cockpitTrial: null,
            pgTask: taskKind,
          });
        }
      } else {
        writeCockpitBatch(taskKind, null);
        setRestoredPersonaIds([]);
        setRestoredTaskId(null);
        if (urlState.pgTask === taskKind) {
          setUrlState({ cockpitBatch: null });
        }
      }
    },
    [restoredPersonaIds, restoredTaskId, selectedPersonaIds, setUrlState, taskKind, urlState.pgTask],
  );

  const clearBatch = useCallback(() => setBatchJobName(null), [setBatchJobName]);
  const [cancelBusy, setCancelBusy] = useState(false);
  const [retryBusy, setRetryBusy] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  const cancelBatch = useCallback(async () => {
    if (!batchJobName || cancelBusy) return;
    setCancelBusy(true);
    try {
      await api.deleteHarborJob(batchJobName);
      clearBatch();
    } finally {
      setCancelBusy(false);
    }
  }, [batchJobName, cancelBusy, clearBatch]);

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

  const personaCardsQuery = useQuery({
    queryKey: ["batch-cohort-personas", previewPersonaIds.join(",")],
    queryFn: () =>
      api.getPersonaPoolCards({
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
  const expectedTrialCount =
    effectivePersonaIds.length ||
    statusSnapshot?.trialCount ||
    batchLive.live?.trialCount ||
    batchLive.live?.trials.length ||
    0;

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

  const isBatchActive = Boolean(batchJobName)
    ? aggregate
      ? statusSnapshot == null ||
        statusSnapshot.launchStatus === "running" ||
        statusSnapshot.launchStatus === "queued" ||
        completedTrials < expectedTrialCount
      : batchLive.isActive
    : false;

  const batchComplete =
    Boolean(batchJobName) &&
    completedTrials >= expectedTrialCount &&
    expectedTrialCount > 0;

  const batchGridCells = useMemo(() => {
    if (aggregate && statusSnapshot) {
      return buildBatchCellsFromStatus(statusSnapshot, {
        expectedTotal: effectivePersonaIds.length,
        personaIds: effectivePersonaIds,
        personaById,
      });
    }
    return buildBatchGridCells(effectivePersonaIds, batchLive.live?.trials, {
      jobStarted: Boolean(batchJobName),
      parallelTrials,
      personaById,
    });
  }, [
    aggregate,
    statusSnapshot,
    effectivePersonaIds,
    batchLive.live?.trials,
    batchJobName,
    parallelTrials,
    personaById,
  ]);

  return {
    batchJobName,
    batchTaskId: restoredTaskId,
    batchPersonaIds: effectivePersonaIds,
    setBatchJobName,
    batchLive,
    clearBatch,
    cancelBatch,
    cancelBusy,
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
    batchError: aggregate ? statusFeed.error : batchLive.error,
  };
}

export function resolveRunLaunchPhase(
  batchJobName: string | null,
  batchComplete: boolean,
  batchError: string | null,
  phase: HarborCockpitPhase,
): RunLaunchPhase {
  if (batchJobName) {
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
  completed: number,
  total: number,
  t?: (key: string, fallback?: string, values?: Record<string, string>) => string,
): string {
  const done = Math.max(0, Math.min(completed, total));
  const noun =
    total === 1
      ? t
        ? t("eval.progress.person", "person")
        : "person"
      : t
        ? t("eval.progress.people", "people")
        : "people";
  if (total <= 0) return t ? t("eval.progress.batchRun", "Batch run") : "Batch run";
  if (done >= total)
    return t
      ? t("eval.progress.allFinished", `All ${total} ${noun} finished`, {
          total: String(total),
          noun,
        })
      : `All ${total} ${noun} finished`;
  return t
    ? t("eval.progress.partialFinished", `${done} of ${total} ${noun} finished`, {
        done: String(done),
        total: String(total),
        noun,
      })
    : `${done} of ${total} ${noun} finished`;
}

export const BATCH_RUN_COMPLETE_HINT =
  "Everyone finished — open Runs for debrief.";
