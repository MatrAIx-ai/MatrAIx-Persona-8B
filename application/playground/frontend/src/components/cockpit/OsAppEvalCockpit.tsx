/**
 * OsAppEvalCockpit: Harbor computer-use tasks (linux / macos / ios) from MatrAIx
 * example-computer-use-* — not AppWorld.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useI18n } from "@/i18n/I18nProvider";
import { listOsAppEvalTasks, api, harborTrialLiveScreenshotUrl } from "@/lib/api";
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
import { usePgTaskIdDeepLink } from "@/lib/usePgTaskIdDeepLink";
import { useUrlState } from "@/lib/useUrlState";
import { useCockpitInstruction } from "@/lib/useCockpitInstruction";
import { mapOsAppDebriefToJobView, classifyCockpitRunError, harborTrialRecordingUrl } from "@/lib/harborCockpitMappers";
import { RunHeader } from "./RunHeader";
import { HarborTraceReplay } from "./HarborTraceReplay";
import { PersonaDrawer } from "./PersonaDrawer";
import { InspectorTabs, type InspectorTab } from "./InspectorTabs";
import { InstructionPanel } from "./InstructionPanel";
import { OsAppEvalScorecard } from "./TaskEvalScorecard";
import { localizeCockpitRunError } from "./cockpitRunErrorPresentation";
import { CockpitSetupShell } from "./setup/CockpitSetupShell";
import { PersonaSamplingRail } from "./setup/PersonaSamplingRail";
import {
  resolveCohortSize,
} from "./setup/personaLaunchFields";
import { CockpitPipelineDiagram } from "./setup/CockpitPipelineDiagram";
import { TaskSelectionRail } from "./setup/TaskSelectionRail";
import { CockpitRunCenter } from "./setup/CockpitRunCenter";
import { useCockpitLaunch } from "./setup/useCockpitLaunch";
import {
  batchProgressPct as computeBatchProgressPct,
  formatBatchProgressLabel,
  resolveRunLaunchPhase,
} from "./setup/useCockpitBatchJob";
import { useCockpitRunCancel } from "./setup/useCockpitRunCancel";
import { useCockpitSetupLock } from "./setup/useCockpitSetupLock";
import { osAppTaskCards } from "./setup/cockpitTaskCards";
import { FOCUS_RING, Sym } from "./cockpitShared";
import type { PlaygroundTaskType } from "./TaskTypeSwitch";

const DEFAULT_AGENT_MODEL = DEFAULT_CUA_AGENT_MODEL;
type Translate = ReturnType<typeof useI18n>["t"];

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
  harborPhase: string | null | undefined,
  t: Translate,
): string | null {
  if (phase === "launching") return t("eval.os.status.launching");
  if (phase !== "running") return null;
  const raw = (harborPhase ?? jobPhase ?? "").toLowerCase();
  if (raw.includes("harbor") || raw.includes("trial")) return t("eval.os.status.trial");
  if (raw.includes("collect")) return t("eval.os.status.collecting");
  return t("eval.os.status.desktop");
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
  const { t } = useI18n();
  const { state: urlState } = useUrlState();
  const { run, job, phase, isRunning, error, timedOut, retry, reset, harborPhase, harborJobName, harborTrialName, vncUrl, sandboxId, cancelRun, cancelBusy: harborCancelBusy } =
    useHarborCockpitRun<OsAppEvalJobView>({ taskKind: "os-app" });
  const [taskId, setTaskId] = useState("");
  const [cuaRuntimeByTaskId, setCuaRuntimeByTaskId] = useState<Record<string, string>>({});
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [tab, setTab] = useState<InspectorTab>("evaluation");
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
    sampling: {
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
    },
    batch: {
      batchJobName,
      batchTaskId,
      batchPersonaIds,
      batchPersonaPool,
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
    },
    launchError,
    setLaunchError,
    clearLaunchError,
    canLaunchCohort,
    launchBatch,
    requestConfigAnotherRun,
    confirmConfigAnotherRun,
    cancelConfigAnotherRun,
    configAnotherOpen,
    batchLaunching,
  } = useCockpitLaunch(options, "os-app", setupTaskPath, isActive);


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
    onFooterContextChange?.(`os-app · ${task?.platform ?? "desktop"} · ${task?.title ?? "task"}`);
  }, [isActive, onFooterContextChange, task]);

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
  const displayError = localizeCockpitRunError(
    classifyCockpitRunError(error ?? job?.error ?? null),
    t,
  );
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
      mapDebrief: (debrief, ctx) =>
        mapOsAppDebriefToJobView(debrief, ctx, {
          personaId: persona.id,
          personaName: persona.name,
          taskId: task.id,
          taskTitle: task.title,
          platform: task.platform,
        }),
    });
  }, [persona, task, isRunning, run, personaModel, activeCuaRuntime]);

  const handleLaunch = useCallback(async () => {
    if (!canLaunchCohort || !task || isRunning) {
      return;
    }
    if (isBatchRun) {
      await launchBatch({
        taskPath: task.taskPath,
        taskId: task.id,
        overrides: {
          agentName: "persona-computer-1",
          osAppBackend: resolveCuaRuntime(task.id, task.platform),
          osAppSubmissionProfile: task.osAppSubmissionProfile ?? undefined,
        },
      });
      return;
    }
    handleRun();
  }, [canLaunchCohort, task, isRunning, isBatchRun, resolveCuaRuntime, launchBatch, handleRun]);

  const handleNewRun = useCallback(() => {
    reset();
    clearBatch();
    clearLaunchError();
  }, [reset, clearBatch, clearLaunchError]);

  const handleConfirmConfigAnotherRun = useCallback(() => {
    reset();
    confirmConfigAnotherRun();
    setTaskId("");
  }, [reset, confirmConfigAnotherRun]);

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
    batchLaunching,
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
      ? t("eval.progress.batchStopped")
      : formatBatchProgressLabel(
          t,
          batchCompletedTrials,
          expectedTrialCount,
        )
    : phase === "launching"
      ? t("eval.os.progress.launching")
      : phase === "running"
        ? stepCount > 0
          ? t("eval.os.progress.desktopAgent", { count: stepCount })
          : (status ?? t("eval.os.progress.desktop"))
        : phase === "done"
          ? t("eval.os.progress.complete", { count: stepCount })
          : failed
            ? error?.startsWith("Run stopped")
              ? t("eval.progress.runStopped")
              : t("eval.os.progress.failed")
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
      header={<RunHeader taskType={taskType} onTaskTypeChange={onTaskTypeChange} />}
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
              ? t("eval.progress.batchCompleteHint")
              : undefined
          }
          canRun={
            canLaunchCohort &&
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
            (batchCancelled ? t("eval.progress.batchStoppedReset") : batchError) ??
            retryError ??
            (failed && !batchJobName ? null : displayError)
          }
          onNewRun={showLiveCenter ? handleNewRun : undefined}
          onConfigAnotherRun={
            batchJobName
              ? batchComplete || batchCancelled
                ? handleConfirmConfigAnotherRun
                : requestConfigAnotherRun
              : undefined
          }
          configAnotherOpen={configAnotherOpen}
          onConfirmConfigAnother={handleConfirmConfigAnotherRun}
          onCancelConfigAnother={cancelConfigAnotherRun}
          onCancelRun={onCancelRun}
          cancelRunBusy={cancelRunBusy}
          onViewJob={
            batchJobName && onOpenHarborJob
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
                label={t("eval.os.contextLabel")}
                title={instructionView.title}
                markdown={instructionView.contextMarkdown}
                loading={instructionView.loading}
                error={instructionView.error}
                emptyMessage={t("eval.os.contextEmpty")}
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
                ? t("eval.os.tasksApiUnavailable")
                : t("eval.os.tasksEmpty")
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
  sandboxId: _sandboxId,
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
  const screenshotUrl =
    harborJobName && harborTrialName
      ? harborTrialLiveScreenshotUrl(harborJobName, harborTrialName)
      : null;
  const useScreenshot = Boolean(screenshotUrl) && !vncUrl;
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

  const hasLiveView = Boolean(vncUrl) || Boolean(screenshotUrl);

  const stepsPanel = (
    <div className="flex h-full min-h-0 flex-col rounded-md border border-outline bg-surface p-2">
      <div className="hud mb-1 shrink-0 text-[10px] font-semibold uppercase tracking-wider text-text-dim">
        {t("eval.os.stepsTitle")}
      </div>
      <div ref={stepsPanelRef} className="custom-scrollbar min-h-0 flex-1 overflow-y-auto">
        {liveSteps.length === 0 && (
          <p className="text-[12px] italic text-text-dim">{t("eval.os.stepsWaiting")}</p>
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
      aria-label={isFullscreen ? t("eval.os.fullscreen.exit") : t("eval.os.fullscreen.enter")}
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
    ? t("eval.os.collectingResults", { elapsed: collectingElapsed })
    : (status ?? t("eval.os.runningTrial"));

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
                  alt={t("eval.os.iosLiveViewAlt")}
                  className="absolute inset-0 m-auto max-h-full max-w-full object-contain"
                />
              ) : (
                <p className="absolute inset-0 flex items-center justify-center text-[12px] text-text-dim">{t("eval.os.connectingIos")}</p>
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
                      alt={t("eval.os.desktopLiveViewAlt")}
                      className="absolute inset-0 m-auto max-h-full max-w-full object-contain"
                    />
                  ) : (
                    <p className="absolute inset-0 flex items-center justify-center text-[12px] text-text-dim">{t("eval.os.connectingSandbox")}</p>
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
                    title={t("eval.os.liveSandboxTitle")}
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
        ? t("eval.os.errorHint")
        : "";
    return (
      <section className="rounded-md border border-danger/30 bg-danger/10 p-5">
        <div className="flex items-start gap-3">
          <Sym name="error" fill={1} size={20} className="mt-0.5 text-danger" />
          <div>
            <h2 className="font-semibold text-text-main">{t("eval.os.errorTitle")}</h2>
            <p className="mt-1 text-[15px] text-text-variant">
              {error ?? t("eval.os.errorBody")}
              {useComputerHint}
            </p>
            <button
              type="button"
              onClick={onRetry}
              className={`mt-3 inline-flex items-center gap-1.5 rounded-md border border-danger/40 px-3 py-1.5 text-[14px] font-medium text-danger hover:bg-danger/10 ${FOCUS_RING}`}
            >
              <Sym name="refresh" size={15} />
              {t("eval.common.tryAgain")}
            </button>
          </div>
        </div>
      </section>
    );
  }

  if (!osAppResult) {
    return (
      <section className="rounded-md border border-outline bg-surface-lowest p-5">
        <p className="text-[15px] text-text-variant">{t("eval.os.waitingArtifacts")}</p>
      </section>
    );
  }

  return (
    <div className="space-y-4">
      {recordingUrl && recordingAvailable && (
        <section className="rounded-md border border-outline bg-surface-lowest p-4">
          <div className="hud mb-2 flex items-center gap-2 text-[11px] text-primary">
            <Sym name="videocam" size={14} />
            {t("eval.os.recording")}
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
            {t("eval.os.output", { name: osAppResult.artifactName ?? task?.outputArtifact ?? t("eval.os.artifactFallback") })}
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
            {t("eval.os.desktopTrace", { count: trace.events.length })}
          </div>
          <HarborTraceReplay
            trace={trace}
            autoFollowLatest={running}
            emptyMessage={t("eval.os.traceEmpty")}
          />
        </section>
      )}
    </div>
  );
}

export default OsAppEvalCockpit;
