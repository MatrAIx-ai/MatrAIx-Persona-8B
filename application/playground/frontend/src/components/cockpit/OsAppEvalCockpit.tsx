/**
 * OsAppEvalCockpit: Harbor computer-use tasks (linux / macos / ios) from MatrAIx
 * example-computer-use-* — not AppWorld.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useI18n } from "@/i18n/I18nProvider";
import { listOsAppEvalTasks, api, ApiError, harborTrialLiveScreenshotUrl } from "@/lib/api";
import {
  cuaPersonaModelSelectOptions,
  DEFAULT_CUA_AGENT_MODEL,
  personaModelPipelineLabel,
  suggestedCuaBackend,
} from "@/lib/personaAgentCatalog";
import type {
  ConfigOptionsResponse,
  OsAppEvalJobView,
  OsAppEvalTask,
  OsAppEvalTasksResponse,
  OsAppResult,
  WebTrace,
} from "@/lib/types";
import { useHarborCockpitRun, type HarborCockpitPhase } from "@/lib/useHarborCockpitRun";
import { PersonaLanguagePicker } from "@/components/i18n/PersonaLanguagePicker";
import { usePgTaskIdDeepLink } from "@/lib/usePgTaskIdDeepLink";
import { useUrlState } from "@/lib/useUrlState";
import { useCockpitInstruction } from "@/lib/useCockpitInstruction";
import { mapOsAppDebriefToJobView, formatCockpitRunError, harborTrialRecordingUrl } from "@/lib/harborCockpitMappers";
import { RunHeader } from "./RunHeader";
import { HarborTraceReplay } from "./HarborTraceReplay";
import { PersonaDrawer } from "./PersonaDrawer";
import { InspectorTabs, type InspectorTab } from "./InspectorTabs";
import { InstructionPanel } from "./InstructionPanel";
import { OsAppEvalScorecard } from "./TaskEvalScorecard";
import { CockpitSetupShell } from "./setup/CockpitSetupShell";
import { PersonaSamplingRail } from "./setup/PersonaSamplingRail";
import {
  buildPersonaLaunchFields,
  hasLaunchableCohort,
  resolveCohortSize,
} from "./setup/personaLaunchFields";
import { CockpitPipelineDiagram } from "./setup/CockpitPipelineDiagram";
import { TaskSelectionRail } from "./setup/TaskSelectionRail";
import { CockpitRunCenter } from "./setup/CockpitRunCenter";
import { useSetupPersonaSampling } from "./setup/useSetupPersonaSampling";
import {
  batchProgressPct as computeBatchProgressPct,
  BATCH_RUN_COMPLETE_HINT,
  formatBatchProgressLabel,
  resolveRunLaunchPhase,
  useCockpitBatchJob,
} from "./setup/useCockpitBatchJob";
import { useCockpitRunCancel } from "./setup/useCockpitRunCancel";
import { useCockpitSetupLock } from "./setup/useCockpitSetupLock";
import { osAppTaskCards } from "./setup/cockpitTaskCards";
import { FOCUS_RING, Sym } from "./cockpitShared";
import type { PlaygroundTaskType } from "./TaskTypeSwitch";
import { PersonaLanguagePicker } from "@/components/i18n/PersonaLanguagePicker";
import { resolveLaunchLanguage, readPersonaLanguageSetting } from "@/lib/personaLanguage";

type Translate = ReturnType<typeof useI18n>["t"];

const DEFAULT_AGENT_MODEL = DEFAULT_CUA_AGENT_MODEL;

export interface OsAppEvalCockpitProps {
  options: ConfigOptionsResponse | null;
  taskType: PlaygroundTaskType;
  onTaskTypeChange: (value: PlaygroundTaskType) => void;
  onFooterContextChange?: (context: string) => void;
  onOpenHarborJob?: (jobName: string) => void;
  onOpenHarborTrial?: (jobName: string, trialName: string) => void;
  /** When false, the cockpit stays mounted but hidden — skip footer updates. */
  isActive?: boolean;
}


function cuaStatusLine(
  phase: HarborCockpitPhase,
  jobPhase: string | null | undefined,
  harborPhase?: string | null,
  t?: Translate,
): string | null {
  if (phase === "launching") return t?.("eval.os.status.launching", "Launching trial…") ?? "Launching trial…";
  if (phase !== "running") return null;
  const raw = (harborPhase ?? jobPhase ?? "").toLowerCase();
  if (raw.includes("harbor") || raw.includes("trial")) return t?.("eval.os.status.trial", "Running OS app trial…") ?? "Running OS app trial…";
  if (raw.includes("collect")) return t?.("eval.os.status.collecting", "Saving OS app artifacts and trajectory…") ?? "Saving OS app artifacts and trajectory…";
  return t?.("eval.os.status.desktop", "The persona agent is using the desktop…") ?? "The persona agent is using the desktop…";
}

function StepRow({ step: s }: { step: { step: number; action: string; detail: string } }) {
  return (
    <div className="mb-1.5 rounded bg-surface-lowest px-2 py-1.5">
      <div className="flex items-center gap-1.5">
        <span className="inline-flex h-4 min-w-[16px] items-center justify-center rounded bg-primary/15 px-1 text-[10px] font-bold text-primary">
          {s.step}
        </span>
        <span className="text-[12px] font-medium text-text-main">{s.action}</span>
      </div>
      {s.detail && (
        <p className="mt-0.5 break-all whitespace-pre-wrap pl-[22px] text-[11px] text-text-variant">
          {s.detail}
        </p>
      )}
    </div>
  );
}

export function OsAppEvalCockpit({
  options,
  taskType,
  onTaskTypeChange,
  onFooterContextChange,
  onOpenHarborJob,
  onOpenHarborTrial,
  isActive = true,
}: OsAppEvalCockpitProps) {
  const { t, locale } = useI18n();
  const { state: urlState } = useUrlState();
  const { run, job, phase, isRunning, error, timedOut, retry, reset, harborPhase, harborJobName, harborTrialName, vncUrl, sandboxId, cancelRun, cancelBusy: harborCancelBusy } =
    useHarborCockpitRun<OsAppEvalJobView>({ taskKind: "os-app" });
  const [taskId, setTaskId] = useState("");
  const [cuaRuntimeByTaskId, setCuaRuntimeByTaskId] = useState<Record<string, string>>({});
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [tab, setTab] = useState<InspectorTab>("evaluation");
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [exportSnapshot, setExportSnapshot] = useState<{
    persona: { id: string; name: string; source: string } | null;
    taskId: string;
    personaModel: string;
  } | null>(null);

  const tasksQuery = useQuery<OsAppEvalTasksResponse>({
    queryKey: ["os-app-eval-tasks"],
    queryFn: listOsAppEvalTasks,
    enabled: isActive,
    staleTime: 10 * 60_000,
    retry: 1,
  });
  const tasks = useMemo(
    () => tasksQuery.data?.tasks ?? [],
    [tasksQuery.data?.tasks],
  );
  const setupTaskPath =
    tasks.find((item) => item.id === taskId)?.taskPath ?? null;
  const {
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
    useTaskDefaultStrategy,
    setUseTaskDefaultStrategy,
  } = useSetupPersonaSampling(options, "os-app", setupTaskPath, isActive);
  const {
    batchJobName,
    batchTaskId,
    batchPersonaIds,
    batchPersonaPool,
    setBatchJobName,
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
    expectedTrialCount,
    completedTrials: batchCompletedTrials,
    batchError,
  } = useCockpitBatchJob(selectedPersonaIds, parallelTrials, "os-app", selectedCount, personaPool);


  const { setupLocked, visiblePersonaIds } = useCockpitSetupLock(
    phase,
    batchJobName,
    batchPersonaIds,
    selectedPersonaIds,
  );
  const visiblePersonaPool = batchJobName ? batchPersonaPool ?? personaPool : personaPool;
  const activeTaskId = batchJobName && batchTaskId ? batchTaskId : taskId;
  const task = tasks.find((item) => item.id === activeTaskId) ?? null;

  const cuaPersonaModelOptions = useMemo(
    () => cuaPersonaModelSelectOptions(task?.platform, personaModelOptions),
    [task?.platform, personaModelOptions],
  );

  const pipelinePersonaModelLabel = useMemo(
    () => personaModelPipelineLabel(personaModel, cuaPersonaModelOptions),
    [personaModel, cuaPersonaModelOptions],
  );

  useEffect(() => {
    if (cuaPersonaModelOptions.length === 0) return;
    if (!cuaPersonaModelOptions.some((opt) => opt.value === personaModel)) {
      setPersonaModel(cuaPersonaModelOptions[0]?.value ?? DEFAULT_AGENT_MODEL);
    }
  }, [cuaPersonaModelOptions, personaModel, setPersonaModel]);

  const osAppTaskIds = useMemo(() => tasks.map((item) => item.id), [tasks]);
  usePgTaskIdDeepLink("os-app", osAppTaskIds, setTaskId, isActive);

  useEffect(() => {
    if (urlState.pgTaskId) return;
    if (batchTaskId) {
      setTaskId(batchTaskId);
    }
  }, [batchTaskId, urlState.pgTaskId]);

  const resolveCuaRuntime = useCallback(
    (id: string, platform?: string) => {
      const row = tasks.find((item) => item.id === id);
      const base = row?.osAppBackend ?? suggestedCuaBackend(platform ?? "linux");
      return cuaRuntimeByTaskId[id] ?? base;
    },
    [cuaRuntimeByTaskId, tasks],
  );
  const activeCuaRuntime = task ? resolveCuaRuntime(task.id, task.platform) : "docker";

  useEffect(() => {
    if (!isActive) return;
    onFooterContextChange?.(t("eval.os.footerContext", "os-app · {platform} · {task}", {
      platform: task?.platform ?? t("eval.os.platformFallback", "desktop"),
      task: task?.title ?? t("eval.os.taskFallback", "task"),
    }));
  }, [isActive, onFooterContextChange, task, t]);

  const osAppResult = job?.osAppResult ?? null;
  const verifier = job?.verifier ?? null;
  const trace = job?.trace ?? null;
  const instructionView = useCockpitInstruction({
    taskPath: task?.taskPath ?? null,
    fallbackTitle: task?.title ?? null,
    harborJobName,
    harborTrialName,
    enabled: phase !== "idle",
  });
  const failed = phase === "error" || phase === "timeout" || job?.status === "error";
  const displayError = formatCockpitRunError(error ?? job?.error ?? null);
  const status = cuaStatusLine(phase, job?.phase, harborPhase, t);

  useEffect(() => {
    if (phase === "done") {
      setExportSnapshot(
        (prev) =>
          prev ?? {
            persona: persona ? { id: persona.id, name: persona.name, source: persona.source } : null,
            taskId,
            personaModel,
          },
      );
    }
  }, [phase, persona, taskId, personaModel]);

  const taskCards = useMemo(() => osAppTaskCards(tasks), [tasks]);

  const harborLaunchBody = useCallback(
    (targetTask: OsAppEvalTask) => {
      const personaFields = buildPersonaLaunchFields({
        personaPool,
        selectedPersonaIds,
        selectedCount,
        useEntirePool,
        parallelTrials,
      });
      return {
        taskPath: targetTask.taskPath,
        seed,
        personaModel,
        agentName: "persona-computer-1",
        osAppBackend: resolveCuaRuntime(targetTask.id, targetTask.platform),
        ...personaFields,
        mode: "auto" as const,
        osAppSubmissionProfile: targetTask.osAppSubmissionProfile ?? undefined,
        ...resolveLaunchLanguage(readPersonaLanguageSetting(), locale),
      };
    },
    [
      selectedPersonaIds,
      selectedCount,
      useEntirePool,
      seed,
      personaModel,
      resolveCuaRuntime,
      parallelTrials,
      personaPool,
      locale,
    ],
  );

  const handleRun = useCallback(() => {
    if (!persona || !task || isRunning) return;
    setExportSnapshot(null);
    void run({
      taskPath: task.taskPath,
      personaId: persona.id,
      personaModel,
      agentName: "persona-computer-1",
      osAppBackend: activeCuaRuntime,
      mode: "auto",
      osAppSubmissionProfile: task.osAppSubmissionProfile ?? undefined,
      ...resolveLaunchLanguage(readPersonaLanguageSetting(), locale),
      mapDebrief: (debrief, ctx) =>
        mapOsAppDebriefToJobView(debrief, ctx, {
          personaId: persona.id,
          personaName: persona.name,
          taskId: task.id,
          taskTitle: task.title,
          platform: task.platform,
        }),
    });
  }, [persona, task, isRunning, run, personaModel, activeCuaRuntime, locale]);

  const handleLaunch = useCallback(async () => {
    if (
      !hasLaunchableCohort({ selectedPersonaIds, selectedCount, useEntirePool }) ||
      !task ||
      isRunning
    ) {
      return;
    }
    if (isBatchRun) {
      setLaunchError(null);
      try {
        const launched = await api.launchHarborJob(harborLaunchBody(task));
        setBatchJobName(launched.jobName, { taskId: task.id, personaPool });
      } catch (exc) {
        const message = exc instanceof ApiError ? exc.message : exc instanceof Error ? exc.message : String(exc);
        setLaunchError(message);
      }
      return;
    }
    handleRun();
  }, [
    selectedPersonaIds,
    selectedCount,
    useEntirePool,
    task,
    isRunning,
    isBatchRun,
    harborLaunchBody,
    handleRun,
    personaPool,
    locale,
    setBatchJobName,
  ]);

  const handleNewRun = useCallback(() => {
    reset();
    clearBatch();
    setLaunchError(null);
  }, [reset, clearBatch]);

  const { onCancelRun, cancelRunBusy } = useCockpitRunCancel({
    batchJobName,
    batchComplete,
    cancelBatch,
    batchCancelBusy: cancelBusy,
    harborJobName,
    isRunning,
    cancelRun,
    harborCancelBusy,
    setError: setLaunchError,
  });

  const handleRetry = useCallback(() => {
    if (timedOut || phase === "error") retry();
    else handleRun();
  }, [timedOut, phase, retry, handleRun]);

  const handleExport = useCallback(() => {
    if (!exportSnapshot || !osAppResult) return;
    const payload = {
      applicationType: "os-app",
      config: exportSnapshot,
      osAppResult,
      trace,
      exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `os-app-eval-${exportSnapshot.persona?.id ?? "run"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [exportSnapshot, osAppResult, trace]);

  const runBusy = isRunning || isBatchActive;
  const showLiveCenter = phase !== "idle" || Boolean(batchJobName);
  const showInspector = phase !== "idle" && !batchJobName;

  useEffect(() => {
    if (!showInspector) return;
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "1") {
        e.preventDefault();
        setTab("evaluation");
      } else if (e.key === "2") {
        e.preventDefault();
        setTab("instruction");
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [showInspector]);
  const stepCount = trace?.events.length ?? 0;
  const runLaunchPhase = resolveRunLaunchPhase(
    batchJobName,
    batchComplete,
    batchError,
    phase,
    batchCancelled,
  );
  const runProgressPct = batchJobName
    ? computeBatchProgressPct(batchJobName, batchCompletedTrials, expectedTrialCount)
    : phase === "done" || phase === "error" || phase === "timeout"
      ? 100
      : phase === "launching"
        ? 12
        : stepCount > 0
          ? Math.min(95, stepCount * 12)
          : phase === "running"
            ? 20
            : 0;
  const runProgressLabel = batchJobName
    ? batchCancelled
      ? t("eval.progress.batchStopped", "Batch stopped")
      : formatBatchProgressLabel(
          batchCompletedTrials,
          expectedTrialCount,
          t,
        )
    : phase === "launching"
      ? t("eval.os.progress.launching", "Launching OS app trial…")
      : phase === "running"
        ? stepCount > 0
          ? t("eval.os.progress.trace", "Desktop agent · {count} {unit}", {
              count: stepCount,
              unit: t(stepCount === 1 ? "eval.common.step.one" : "eval.common.step.many", stepCount === 1 ? "step" : "steps"),
            })
          : (status ?? t("eval.os.progress.desktop", "Persona agent is using the desktop…"))
        : phase === "done"
          ? t("eval.os.progress.complete", "OS app complete · {count} {unit}", {
              count: stepCount,
              unit: t(stepCount === 1 ? "eval.common.step.one" : "eval.common.step.many", stepCount === 1 ? "step" : "steps"),
            })
          : failed
            ? error?.startsWith("Run stopped")
              ? t("eval.progress.runStopped", "Run stopped")
              : t("eval.os.progress.failed", "OS app trial failed")
            : undefined;
  const canExport = exportSnapshot !== null && osAppResult !== null;

  const osAppLiveContent = (
    <>
      <OsAppResults
        task={task}
        osAppResult={osAppResult}
        trace={trace}
        phase={phase}
        status={status}
        error={displayError}
        onRetry={handleRetry}
        harborJobName={harborJobName}
        harborTrialName={harborTrialName}
        vncUrl={vncUrl}
        sandboxId={sandboxId}
      />
    </>
  );

  const cockpitView = (
    <CockpitSetupShell
      header={
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <RunHeader taskType={taskType} onTaskTypeChange={onTaskTypeChange} />
          </div>
          <PersonaLanguagePicker />
        </div>
      }
      left={
        <PersonaSamplingRail
          taskType="os-app"
          taskPath={task?.taskPath ?? null}
          personaModel={personaModel}
          onPersonaModelChange={setPersonaModel}
          personaModelOptions={cuaPersonaModelOptions}
          mode={samplingMode}
          onModeChange={setSamplingMode}
          selectedPersonaIds={visiblePersonaIds}
          onSelectedPersonaIdsChange={setSelectedPersonaIds}
          selectedCount={selectedCount}
          onSelectedCountChange={setSelectedCount}
          useEntirePool={useEntirePool}
          onUseEntirePoolChange={setUseEntirePool}
          sampleSize={sampleSize}
          onSampleSizeChange={setSampleSize}
          perCell={perCell}
          onSampleSizePerValueGroupChange={setPerCell}
          stratifiedAllocation={stratifiedAllocation}
          onStratifiedAllocationChange={setStratifiedAllocation}
          seed={seed}
          filters={groupFilters}
          onFiltersChange={setGroupFilters}
          fields={fields}
          onFieldsChange={setFields}
          hasTaskStrategy={hasTaskStrategy}
          taskPersonaStrategy={taskPersonaStrategy}
          useTaskDefaultStrategy={useTaskDefaultStrategy}
          onUseTaskDefaultStrategyChange={setUseTaskDefaultStrategy}
          onPersonaPoolChange={setPersonaPool}
          personaPool={visiblePersonaPool}
          disabled={setupLocked}
        />
      }
      center={
        <>
          <div className="flex items-center justify-end gap-3 pb-2">
            <PersonaLanguagePicker />
          </div>
          <CockpitRunCenter
          showLive={showLiveCenter}
          pipeline={
            <CockpitPipelineDiagram
              className="h-full"
              taskType="os-app"
              cuaPlatform={task?.platform}
              personaModelLabel={pipelinePersonaModelLabel}
              hasPersona={visiblePersonaIds.length > 0}
              hasTask={Boolean(task)}
            />
          }
          liveContent={osAppLiveContent}
          fillLiveContent={isRunning}
          batchJobName={batchJobName}
          batchCells={batchGridCells}
          runLaunchPhase={runLaunchPhase}
          progressPct={runProgressPct}
          progressLabel={runProgressLabel}
          progressSublabel={
            batchJobName && batchComplete
              ? t("eval.common.batchCompleteHint", BATCH_RUN_COMPLETE_HINT)
              : undefined
          }
          canRun={
            hasLaunchableCohort({ selectedPersonaIds, selectedCount, useEntirePool }) &&
            Boolean(task) &&
            !runBusy
          }
          isBatch={isBatchRun}
          personaCount={Math.max(
            resolveCohortSize({ selectedPersonaIds, selectedCount }),
            visiblePersonaIds.length,
          )}
          parallelTrials={parallelTrials}
          onParallelTrialsChange={setParallelTrials}
          runBusy={runBusy}
          onRun={() => void handleLaunch()}
          error={
            launchError ??
            batchError ??
            retryError ??
            (failed && !batchJobName ? null : displayError)
          }
          onNewRun={showLiveCenter ? handleNewRun : undefined}
          onCancelRun={onCancelRun}
          cancelRunBusy={cancelRunBusy}
          onViewJob={
            batchJobName && batchComplete && onOpenHarborJob
              ? () => onOpenHarborJob(batchJobName)
              : !batchJobName && harborJobName && harborTrialName && onOpenHarborTrial
                ? () => onOpenHarborTrial(harborJobName, harborTrialName)
              : undefined
          }
          onDownload={!batchJobName ? handleExport : undefined}
          canDownload={canExport}
          onRetryFailed={
            batchJobName && !batchCancelled ? () => void retryFailed() : undefined
          }
          failedCount={failedTrials}
          retryBusy={retryBusy}
        />
        </>
      }
      right={
        showInspector ? (
          <InspectorTabs
            active={tab}
            onChange={setTab}
            evaluation={
              <OsAppEvalScorecard
                osAppResult={osAppResult}
                verifier={verifier}
                traceStepCount={trace?.events?.length ?? 0}
                phase={phase}
              />
            }
            instruction={
              <InstructionPanel
                title={instructionView.title}
                markdown={instructionView.instructionMarkdown ?? instructionView.markdown}
                loading={instructionView.loading}
                error={instructionView.error}
              />
            }
            context={
              <InstructionPanel
                label={t("eval.os.contextLabel", "Task context")}
                title={instructionView.title}
                markdown={instructionView.contextMarkdown}
                loading={instructionView.loading}
                error={instructionView.error}
                emptyMessage={t("eval.os.contextEmpty", "No separate context document is available for this task.")}
                icon="menu_book"
              />
            }
          />
        ) : (
        <TaskSelectionRail
          taskType="os-app"
          chatTasks={[]}
          surveyTasks={[]}
          webTasks={[]}
          cuaTasks={taskCards}
          selectedTaskId={activeTaskId}
          onSelectTask={(card) => setTaskId(card.id)}
          engine=""
          onEngineChange={() => undefined}
          engineOptions={[]}
          maxTurns={8}
          onMaxTurnsChange={() => undefined}
          resolveCuaRuntime={resolveCuaRuntime}
          onCuaRuntimeChange={(id, runtime) =>
            setCuaRuntimeByTaskId((prev) => ({ ...prev, [id]: runtime }))
          }
          tasksLoading={tasksQuery.isLoading}
          tasksError={
            tasks.length === 0
              ? tasksQuery.isError
                ? t("eval.os.tasksApiUnavailable", "OS app task API unavailable — restart the Playground backend (uvicorn backend.api.app:app on :8765).")
                : t("eval.os.tasksEmpty", "No OS app tasks available.")
              : null
          }
          disabled={setupLocked}
        />
        )
      }
    />
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {cockpitView}
      <PersonaDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} persona={persona} context={null} />
    </div>
  );
}


function OsAppResults({
  task,
  osAppResult,
  trace,
  phase,
  status,
  error,
  onRetry,
  harborJobName,
  harborTrialName,
  vncUrl,
  sandboxId,
}: {
  task: OsAppEvalTask | null;
  osAppResult: OsAppResult | null;
  trace: WebTrace | null;
  phase: HarborCockpitPhase;
  status: string | null;
  error: string | null;
  onRetry: () => void;
  harborJobName: string | null;
  harborTrialName: string | null;
  vncUrl: string | null;
  sandboxId: string | null;
}) {
const { t } = useI18n();
  const running = phase === "launching" || phase === "running";
  const failed = phase === "error" || phase === "timeout";
  const recordingUrl =
    harborJobName && harborTrialName
      ? harborTrialRecordingUrl(harborJobName, harborTrialName)
      : null;
  const [recordingAvailable, setRecordingAvailable] = useState(Boolean(recordingUrl));

  useEffect(() => {
    setRecordingAvailable(Boolean(recordingUrl));
  }, [recordingUrl]);

  const isIos = task?.platform === "ios";
  const useScreenshot = Boolean(sandboxId && harborJobName && harborTrialName);
  const screenshotUrl =
    useScreenshot && harborJobName && harborTrialName
      ? harborTrialLiveScreenshotUrl(harborJobName, harborTrialName)
      : null;
  const [screenshotSrc, setScreenshotSrc] = useState<string | null>(null);
  const screenshotTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!running || !screenshotUrl) {
      setScreenshotSrc(null);
      return;
    }
    let cancelled = false;
    const refresh = async () => {
      try {
        const resp = await fetch(`${screenshotUrl}?t=${Date.now()}`);
        if (cancelled || !resp.ok) return;
        const blob = await resp.blob();
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        setScreenshotSrc((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return url;
        });
      } catch { /* sandbox may not be ready yet */ }
    };
    void refresh();
    screenshotTimerRef.current = window.setInterval(() => void refresh(), 1500);
    return () => {
      cancelled = true;
      if (screenshotTimerRef.current !== null) window.clearInterval(screenshotTimerRef.current);
      setScreenshotSrc((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
    };
  }, [running, screenshotUrl]);

  const [liveSteps, setLiveSteps] = useState<{ step: number; action: string; detail: string }[]>([]);
  const liveViewRef = useRef<HTMLElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const toggleFullscreen = useCallback(() => {
    if (!liveViewRef.current) return;
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else {
      void liveViewRef.current.requestFullscreen();
    }
  }, []);

  useEffect(() => {
    const onChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  useEffect(() => {
    if (!running || !harborJobName || !harborTrialName) { setLiveSteps([]); return; }
    let cancelled = false;
    const poll = async () => {
      try {
        const resp = await api.getHarborTrialTrace(harborJobName, harborTrialName);
        if (cancelled) return;
        const events = resp?.trace?.events;
        if (Array.isArray(events)) {
          setLiveSteps(events.map((ev) => {
            const actions: { name?: string; arguments?: Record<string, unknown> }[] = ev.actions ?? [];
            const first = actions[0];
            const rawName = first?.name ?? "";
            const args = first?.arguments ?? {};
            const name = rawName || String(args.action ?? "") || "prompt";
            const coord = Array.isArray(args.coordinate) ? args.coordinate as number[] : null;
            let detail = "";
            if (/^(left_click|right_click|double_click|middle_click)$/.test(name)) {
              detail = coord ? `(${Math.round(coord[0])}, ${Math.round(coord[1])})` : "";
            } else if (name === "tap" || name === "click") {
              detail = coord
                ? `(${Math.round(coord[0])}, ${Math.round(coord[1])})`
                : `(${Math.round(Number(args.x ?? 0))}, ${Math.round(Number(args.y ?? 0))})`;
            } else if (name === "key") {
              detail = String(args.text ?? "");
            } else if (name === "type" || name === "fill") {
              detail = String(args.text ?? args.value ?? "").slice(0, 40);
            } else if (name === "scroll") {
              const dir = String(args.direction ?? "");
              detail = coord ? `${dir} (${Math.round(coord[0])}, ${Math.round(coord[1])})` : dir;
            } else if (name === "swipe" || name === "drag") {
              detail = `↕ ${Math.round(Number(args.from_y ?? 0))}→${Math.round(Number(args.to_y ?? 0))}`;
            } else if (name === "screenshot" || name === "cursor_position") {
              detail = "";
            } else if (name === "wait") {
              detail = `${args.duration ?? "?"}s`;
            } else if (name === "open_app" || name === "launch") {
              detail = String(args.bundle_id ?? args.app ?? "");
            } else if (Object.keys(args).length > 0) {
              detail = JSON.stringify(args).slice(0, 60);
            }
            return { step: Number(ev.step ?? 0), action: name, detail };
          }));
        }
      } catch { /* trace not ready yet */ }
    };
    void poll();
    const id = window.setInterval(() => void poll(), 2000);
    return () => { cancelled = true; window.clearInterval(id); };
  }, [running, harborJobName, harborTrialName]);

  const stepsPanelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = stepsPanelRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [liveSteps.length]);

  const hasLiveView = useScreenshot ? Boolean(screenshotUrl) : Boolean(vncUrl);

  const stepsPanel = (
    <div className="flex h-full min-h-0 flex-col rounded-md border border-outline bg-surface p-2">
      <div className="hud mb-1 shrink-0 text-[10px] font-semibold uppercase tracking-wider text-text-dim">
        {t("eval.os.stepsTitle", "Agent steps")}
      </div>
      <div ref={stepsPanelRef} className="custom-scrollbar min-h-0 flex-1 overflow-y-auto">
        {liveSteps.length === 0 && (
          <p className="text-[12px] italic text-text-dim">{t("eval.os.stepsWaiting", "Waiting for first action…")}</p>
        )}
        {liveSteps.filter((s) => s.action).map((s) => (
          <StepRow key={s.step} step={s} />
        ))}
      </div>
    </div>
  );

  const fullscreenBtn = (
    <button
      type="button"
      onClick={toggleFullscreen}
      aria-label={isFullscreen ? t("eval.os.fullscreen.exit", "Exit fullscreen") : t("eval.os.fullscreen.enter", "Enter fullscreen")}
      className={`absolute right-2 top-2 z-10 flex h-7 w-7 items-center justify-center rounded-md bg-black/60 text-white/80 backdrop-blur transition hover:bg-black/80 hover:text-white ${FOCUS_RING}`}
    >
      <Sym name={isFullscreen ? "fullscreen_exit" : "fullscreen"} size={16} />
    </button>
  );

  const [statusExpanded, setStatusExpanded] = useState(false);

  const agentDone = liveSteps.length > 0 && liveSteps[liveSteps.length - 1]?.action === "done";
  const [collectingElapsed, setCollectingElapsed] = useState(0);

  useEffect(() => {
    if (!agentDone || !running) { setCollectingElapsed(0); return; }
    const start = Date.now();
    const id = window.setInterval(() => setCollectingElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, [agentDone, running]);

  const displayStatus = agentDone
    ? t("eval.os.collecting", "Collecting results{elapsed}…", {
        elapsed: collectingElapsed > 0 ? ` (${collectingElapsed}s)` : "",
      })
    : (status ?? t("eval.os.runningTrial", "Running computer-use trial…"));

  if (running && !osAppResult) {
    if (isIos) {
      return (
        <div className="flex h-full min-h-0 flex-1 flex-col gap-1.5">
          <button
            type="button"
            onClick={() => setStatusExpanded((v) => !v)}
            className={`flex shrink-0 items-center gap-2 rounded-md border border-outline bg-surface-lowest px-3 py-1 text-left transition hover:bg-surface ${FOCUS_RING}`}
          >
            <Sym name="cast" size={14} className="shrink-0 text-primary" />
            <p className="truncate text-[12px] font-semibold text-text-main">{displayStatus}</p>
            <Sym name={statusExpanded ? "expand_less" : "expand_more"} size={14} className="ml-auto shrink-0 text-text-dim" />
          </button>
          {statusExpanded && task && (
            <div className="shrink-0 rounded-md border border-outline/60 bg-surface-lowest px-3 py-1.5">
              <p className="text-[12px] text-text-variant">{task.description}</p>
            </div>
          )}
          <div
            ref={liveViewRef as React.RefObject<HTMLDivElement>}
            className={isFullscreen ? "flex min-h-0 flex-1 gap-3 bg-black p-2" : "flex min-h-0 flex-1 gap-3"}
          >
            <div className="relative min-h-0 flex-1 overflow-hidden rounded-md border border-outline bg-black">
              {fullscreenBtn}
              {screenshotSrc ? (
                <img
                  src={screenshotSrc}
                  alt={t("eval.os.iosLiveViewAlt", "iOS simulator live view")}
                  className="absolute inset-0 m-auto max-h-full max-w-full object-contain"
                />
              ) : (
                <p className="absolute inset-0 flex items-center justify-center text-[12px] text-text-dim">{t("eval.os.connectingIos", "Connecting to iOS simulator…")}</p>
              )}
            </div>
            <div className={isFullscreen ? "w-72 shrink-0" : "w-48 shrink-0"}>{stepsPanel}</div>
          </div>
        </div>
      );
    }

    return (
      <div className="flex h-full min-h-0 flex-1 flex-col gap-1.5">
        <button
          type="button"
          onClick={() => setStatusExpanded((v) => !v)}
          className={`flex shrink-0 items-center gap-2 rounded-md border border-outline bg-surface-lowest px-3 py-1 text-left transition hover:bg-surface ${FOCUS_RING}`}
        >
          <Sym name="cast" size={14} className="shrink-0 text-primary" />
          <p className="truncate text-[12px] font-semibold text-text-main">{displayStatus}</p>
          <Sym name={statusExpanded ? "expand_less" : "expand_more"} size={14} className="ml-auto shrink-0 text-text-dim" />
        </button>
        {statusExpanded && task && (
          <div className="shrink-0 rounded-md border border-outline/60 bg-surface-lowest px-3 py-1.5">
            <p className="text-[12px] text-text-variant">{task.description}</p>
          </div>
        )}
        {hasLiveView ? (
          <section
            ref={liveViewRef}
            className={
              isFullscreen
                ? "flex min-h-0 flex-1 flex-col bg-black p-4"
                : "flex min-h-0 flex-1 flex-col"
            }
          >
            {useScreenshot ? (
              <div className="flex min-h-0 flex-1 flex-col gap-2">
                <div className="relative min-h-0 flex-[2] overflow-hidden rounded-md border border-outline bg-black">
                  {fullscreenBtn}
                  {screenshotSrc ? (
                    <img
                      src={screenshotSrc}
                  alt={t("eval.os.desktopLiveViewAlt", "Desktop live view")}
                      className="absolute inset-0 m-auto max-h-full max-w-full object-contain"
                    />
                  ) : (
                    <p className="absolute inset-0 flex items-center justify-center text-[12px] text-text-dim">{t("eval.os.connectingSandbox", "Connecting to sandbox…")}</p>
                  )}
                </div>
                <div className="min-h-0 flex-1">{stepsPanel}</div>
              </div>
            ) : (
              <div className="flex min-h-0 flex-1 gap-3">
                <div className="relative min-h-0 flex-1">
                  {fullscreenBtn}
                  <iframe
                    src={vncUrl!}
                    title={t("eval.os.liveSandboxTitle", "Live sandbox view")}
                    className="h-full w-full rounded-md border border-outline bg-black"
                    sandbox="allow-scripts allow-same-origin"
                    allow="clipboard-read; clipboard-write"
                  />
                </div>
                <div className={isFullscreen ? "w-72 shrink-0" : "w-48 shrink-0"}>{stepsPanel}</div>
              </div>
            )}
          </section>
        ) : (
          // Docker Linux has no published VNC / use.computer screenshot — still
          // show the polled trajectory steps so single-trial runs are not a blank pane.
          <div className="min-h-0 flex-1">{stepsPanel}</div>
        )}
      </div>
    );
  }

  if (failed) {
    const useComputerHint =
      (task?.platform === "macos" || task?.platform === "ios") &&
      (error?.includes("exit code") || error?.includes("environment definition"))
        ? ` ${t("eval.os.errorHint", "macOS and iOS tasks run on use.computer — set USE_COMPUTER_API_KEY (and ANTHROPIC_API_KEY) on the backend.")}`
        : "";
    return (
      <section className="rounded-md border border-danger/30 bg-danger/10 p-5">
        <div className="flex items-start gap-3">
          <Sym name="error" fill={1} size={20} className="mt-0.5 text-danger" />
          <div>
            <h2 className="font-semibold text-text-main">{t("eval.os.errorTitle", "OS app trial failed")}</h2>
            <p className="mt-1 text-[15px] text-text-variant">
              {error ?? t("eval.os.errorBody", "The trial did not finish.")}
              {useComputerHint}
            </p>
            <button
              type="button"
              onClick={onRetry}
              className={`mt-3 inline-flex items-center gap-1.5 rounded-md border border-danger/40 px-3 py-1.5 text-[14px] font-medium text-danger hover:bg-danger/10 ${FOCUS_RING}`}
            >
              <Sym name="refresh" size={15} />
              {t("eval.common.tryAgain", "Try again")}
            </button>
          </div>
        </div>
      </section>
    );
  }

  if (!osAppResult) {
    return (
      <section className="rounded-md border border-outline bg-surface-lowest p-5">
        <p className="text-[15px] text-text-variant">{t("eval.os.waitingArtifacts", "Waiting for OS app artifacts…")}</p>
      </section>
    );
  }

  return (
    <div className="space-y-4">
      {recordingUrl && recordingAvailable && (
        <section className="rounded-md border border-outline bg-surface-lowest p-4">
          <div className="hud mb-2 flex items-center gap-2 text-[11px] text-primary">
            <Sym name="videocam" size={14} />
            {t("eval.os.recording", "Session recording")}
          </div>
          <video
            src={recordingUrl}
            controls
            playsInline
            preload="metadata"
            className="max-h-[360px] w-full rounded-md border border-outline bg-black object-contain"
            onError={() => setRecordingAvailable(false)}
          />
        </section>
      )}
      {osAppResult.artifact && (
        <section className="rounded-md border border-outline bg-surface-lowest p-4">
          <div className="hud mb-2 text-[11px] text-text-dim">
            {t("eval.os.output", "Output · {name}", {
              name: osAppResult.artifactName ?? task?.outputArtifact ?? t("eval.os.taskFallback", "artifact"),
            })}
          </div>
          <pre className="custom-scrollbar max-h-80 overflow-auto rounded-md bg-surface p-3 font-mono text-[13px] text-text-main">
            {JSON.stringify(osAppResult.artifact, null, 2)}
          </pre>
        </section>
      )}
      {trace && trace.events.length > 0 && (
        <section className="rounded-md border border-outline bg-surface-lowest p-4">
          <div className="hud mb-3 flex items-center gap-2 text-[12px] text-primary">
            <Sym name="route" size={14} />
            {t("eval.os.trace", "Desktop trace · {count} {unit}", {
              count: trace.events.length,
              unit: t(trace.events.length === 1 ? "eval.common.step.one" : "eval.common.step.many", trace.events.length === 1 ? "step" : "steps"),
            })}
          </div>
          <HarborTraceReplay
            trace={trace}
            autoFollowLatest={running}
            emptyMessage={t("eval.os.traceEmpty", "This run finished without step screenshots.")}
          />
        </section>
      )}
    </div>
  );
}

export default OsAppEvalCockpit;
