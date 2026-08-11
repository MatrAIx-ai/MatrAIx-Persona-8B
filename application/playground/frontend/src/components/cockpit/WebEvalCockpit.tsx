/**
 * WebEvalCockpit: the Website-task Playground surface.
 *
 * Reproduces the approved redesign mockup's `data-view="cockpit"` setup shell
 * (the same centered form as the canonical chatbot cockpit: header +
 * application-type switch + pipeline strip + run-config card + target-persona
 * panel + Run-eval CTA) with the Web-specific body (a website-task picker + a
 * "Website task" card and a driver/artifacts note instead of an environment
 * panel.
 * environment). Once a run starts, the left column flips to the debrief view
 * modelled on the mockup's `data-view="runs"` web body: need-fit / ease /
 * overall-UX score tiles, the selected product, and a browser trace rendered as
 * screenshot tiles with per-step actions.
 *
 * Harbor-backed: `useHarborCockpitRun`, the `listWebEvalTasks` query, the
 * export logic, and every result/trace shape are wired exactly as before. Only
 * the structure and presentation are rebuilt.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useI18n } from "@/i18n/I18nProvider";
import { listWebEvalTasks, api, ApiError } from "@/lib/api";
import { FALLBACK_WEB_TASKS } from "@/lib/fallbackTasks";
import { mergeTaskCatalog } from "@/lib/mergeTaskCatalog";
import {
  findPersonaAgent,
  personaModelPipelineLabel,
  suggestedWebPersonaAgent,
  webAgentFamily,
  webHarnessPipelineLabel,
  webPersonaModelSelectOptions,
  WEB_PERSONA_AGENTS,
} from "@/lib/personaAgentCatalog";
import type {
  ConfigOptionsResponse,
  PlaygroundPersona,
  WebEvalJobView,
  WebEvalTask,
  WebEvalTasksResponse,
  WebResult,
  WebTrace,
} from "@/lib/types";
import { useHarborCockpitRun, type HarborCockpitPhase } from "@/lib/useHarborCockpitRun";
import { usePgTaskIdDeepLink } from "@/lib/usePgTaskIdDeepLink";
import { useUrlState } from "@/lib/useUrlState";
import { useCockpitInstruction } from "@/lib/useCockpitInstruction";
import { mapWebDebriefToJobView, attachHarborTraceScreenshotUrls, formatCockpitRunError } from "@/lib/harborCockpitMappers";
import { RunHeader } from "./RunHeader";
import { PersonaDrawer } from "./PersonaDrawer";
import { InspectorTabs, type InspectorTab } from "./InspectorTabs";
import { InstructionPanel } from "./InstructionPanel";
import { WebEvalScorecard } from "./TaskEvalScorecard";
import { CockpitSetupShell } from "./setup/CockpitSetupShell";
import { PersonaSamplingRail } from "./setup/PersonaSamplingRail";
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
import { webEvalTaskCards } from "./setup/cockpitTaskCards";
import { HarborTraceReplay } from "./HarborTraceReplay";
import {
  FOCUS_RING,
  Sym,
  personaDescriptiveTitle,
} from "./cockpitShared";
import type { PlaygroundTaskType } from "./TaskTypeSwitch";

type Translate = ReturnType<typeof useI18n>["t"];

function mergeWebTasks(apiTasks: WebEvalTask[] | undefined): WebEvalTask[] {
  return mergeTaskCatalog(FALLBACK_WEB_TASKS, apiTasks, (row, api, base) => ({
    ...row,
    taskPath: api?.taskPath || base?.taskPath || row.taskPath || "",
  }));
}

export interface WebEvalCockpitProps {
  options: ConfigOptionsResponse | null;
  taskType: PlaygroundTaskType;
  onTaskTypeChange: (value: PlaygroundTaskType) => void;
  /** Report the honest footer context up (the active website). */
  onFooterContextChange?: (context: string) => void;
  onOpenHarborJob?: (jobName: string) => void;
  onOpenHarborTrial?: (jobName: string, trialName: string) => void;
  /** When false, the cockpit stays mounted but hidden — skip footer updates. */
  isActive?: boolean;
}



function webStatusLine(
  phase: HarborCockpitPhase,
  jobPhase: string | null | undefined,
  harborPhase?: string | null,
  t?: Translate,
): string | null {
  if (phase === "launching") return t?.("eval.web.status.launching", "Launching batch…") ?? "Launching batch…";
  if (phase !== "running") return null;
  const raw = (harborPhase ?? jobPhase ?? "").toLowerCase();
  if (raw.includes("harbor") || raw.includes("trial")) return t?.("eval.web.status.trial", "Running web trial…") ?? "Running web trial…";
  if (raw.includes("collect")) return t?.("eval.web.status.collecting", "Saving the results and step screenshots…") ?? "Saving the results and step screenshots…";
  if (raw.includes("web")) return t?.("eval.web.status.browsing", "The simulated visitor is using the site…") ?? "The simulated visitor is using the site…";
  return t?.("eval.web.status.running", "Running the website test…") ?? "Running the website test…";
}

function formatDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function WebEvalCockpit({
  options,
  taskType,
  onTaskTypeChange,
  onFooterContextChange,
  onOpenHarborJob,
  onOpenHarborTrial,
  isActive = true,
}: WebEvalCockpitProps) {
  const { t } = useI18n();
  const { state: urlState } = useUrlState();
  const { run, job, phase, isRunning, error, timedOut, retry, reset, harborPhase, harborJobName, harborTrialName, cancelRun, cancelBusy: harborCancelBusy } =
    useHarborCockpitRun<WebEvalJobView>({ taskKind: "web" });
  const [liveTrace, setLiveTrace] = useState<WebTrace | null>(null);
  const [taskId, setTaskId] = useState<string>("");
  const [webAgentByTaskId, setWebAgentByTaskId] = useState<Record<string, string>>({});
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [tab, setTab] = useState<InspectorTab>("evaluation");
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [exportSnapshot, setExportSnapshot] = useState<{
    persona: { id: string; name: string; source: string } | null;
    taskId: string;
    personaModel: string;
  } | null>(null);

  const tasksQuery = useQuery<WebEvalTasksResponse>({
    queryKey: ["web-eval-tasks"],
    queryFn: listWebEvalTasks,
    enabled: isActive,
    staleTime: 10 * 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
  const tasks = useMemo(
    () => mergeWebTasks(tasksQuery.data?.tasks),
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
    groupFilters,
    setGroupFilters,
    stratifyFields,
    setStratifyFields,
    sampleSize,
    setSampleSize,
    sampleSizePerValueGroup,
    setSampleSizePerValueGroup,
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
  } = useSetupPersonaSampling(options, "web", setupTaskPath, isActive);
  const {
    batchJobName,
    batchTaskId,
    batchPersonaIds,
    setBatchJobName,
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
    expectedTrialCount,
    completedTrials: batchCompletedTrials,
    batchError,
  } = useCockpitBatchJob(selectedPersonaIds, parallelTrials, "web");


  const { setupLocked, visiblePersonaIds } = useCockpitSetupLock(
    phase,
    batchJobName,
    batchPersonaIds,
    selectedPersonaIds,
  );
  const activeTaskId = batchJobName && batchTaskId ? batchTaskId : taskId;
  const task = tasks.find((item) => item.id === activeTaskId) ?? null;

  const webTaskIds = useMemo(() => tasks.map((item) => item.id), [tasks]);
  usePgTaskIdDeepLink("web", webTaskIds, setTaskId, isActive);

  useEffect(() => {
    if (urlState.pgTaskId) return;
    if (batchTaskId) {
      setTaskId(batchTaskId);
    }
  }, [batchTaskId, urlState.pgTaskId]);

  const resolveWebAgent = useCallback(
    (id: string) => webAgentByTaskId[id] ?? suggestedWebPersonaAgent(id),
    [webAgentByTaskId],
  );
  const activeWebAgent = task ? resolveWebAgent(task.id) : WEB_PERSONA_AGENTS[0].value;
  const activeWebAgentFamily = webAgentFamily(activeWebAgent);

  const webPersonaModelOptions = useMemo(
    () => webPersonaModelSelectOptions(activeWebAgent, personaModelOptions),
    [activeWebAgent, personaModelOptions],
  );

  const pipelinePersonaModelLabel = useMemo(
    () => personaModelPipelineLabel(personaModel, webPersonaModelOptions),
    [personaModel, webPersonaModelOptions],
  );

  useEffect(() => {
    if (webPersonaModelOptions.length === 0) return;
    if (!webPersonaModelOptions.some((opt) => opt.value === personaModel)) {
      setPersonaModel(webPersonaModelOptions[0]?.value ?? personaModel);
    }
  }, [webPersonaModelOptions, personaModel, setPersonaModel]);
  useEffect(() => {
    if (!isActive) return;
    onFooterContextChange?.(t("eval.web.footerContext", "web · {site}", {
      site: task?.siteName ?? t("eval.web.siteFallback", "Website"),
    }));
  }, [isActive, task, onFooterContextChange, t]);

  const webResult = job?.webResult ?? null;
  const verifier = job?.verifier ?? null;
  const trace = job?.trace ?? liveTrace;
  const instructionView = useCockpitInstruction({
    taskPath: task?.taskPath ?? null,
    fallbackTitle: task?.title ?? null,
    harborJobName,
    harborTrialName,
    enabled: phase !== "idle",
  });
  useEffect(() => {
    if (phase === "idle") {
      setLiveTrace(null);
      return;
    }
    if (!harborJobName || !harborTrialName || phase !== "running") return;

    let cancelled = false;
    const poll = async () => {
      try {
        const payload = await api.getHarborTrialTrace(harborJobName, harborTrialName);
        if (!cancelled && payload.trace?.events?.length) {
          setLiveTrace(
            attachHarborTraceScreenshotUrls(payload.trace, harborJobName, harborTrialName),
          );
        }
      } catch {
        // trajectory.json is flushed mid-run for computer-1 / browser-use / Cocoa /
        // OpenHands; keep polling until the first checkpoint appears.
      }
    };

    void poll();
    const id = window.setInterval(() => void poll(), 800);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [phase, harborJobName, harborTrialName]);

  const failed = phase === "error" || phase === "timeout" || job?.status === "error";
  const displayError = formatCockpitRunError(error ?? job?.error ?? null);
  const status = webStatusLine(phase, job?.phase, harborPhase, t);

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

  const taskCards = useMemo(() => webEvalTaskCards(tasks), [tasks]);

  const handleRun = useCallback(() => {
    if (!persona || !task?.taskPath || isRunning) return;
    setExportSnapshot(null);
    void run({
      taskPath: task.taskPath,
      personaId: persona.id,
      personaModel,
      agentName: activeWebAgent,
      mode: "auto",
      mapDebrief: (debrief, ctx) =>
        mapWebDebriefToJobView(debrief, ctx, {
          personaId: persona.id,
          personaName: persona.name,
      taskId: task.id,
          taskTitle: task.title,
        }),
    });
  }, [persona, task, isRunning, run, personaModel, activeWebAgent]);
  const handleLaunch = useCallback(async () => {
    if (selectedPersonaIds.length === 0 || !task?.taskPath || isRunning) return;
    if (isBatchRun) {
      setLaunchError(null);
      try {
        const launched = await api.launchHarborJob({
          taskPath: task.taskPath,
          sampleSize: selectedPersonaIds.length,
          seed,
          personaModel,
          agentName: activeWebAgent,
          personaPool,
          personaIds: selectedPersonaIds,
          nConcurrentTrials: Math.min(parallelTrials, selectedPersonaIds.length),
          mode: "auto",
        });
        setBatchJobName(launched.jobName, { taskId: task.id });
      } catch (exc) {
        const message = exc instanceof ApiError ? exc.message : exc instanceof Error ? exc.message : String(exc);
        setLaunchError(message);
      }
      return;
    }
    handleRun();
  }, [
    selectedPersonaIds,
    task,
    isRunning,
    isBatchRun,
    seed,
    personaModel,
    activeWebAgent,
    parallelTrials,
    personaPool,
    handleRun,
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
    if (!exportSnapshot || !webResult) return;
    const payload = {
      applicationType: "web",
      config: exportSnapshot,
      webResult,
      trace,
      exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `web-eval-${exportSnapshot.persona?.id ?? "run"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [exportSnapshot, webResult, trace]);

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
  );
  const runProgressPct = batchJobName
    ? computeBatchProgressPct(batchJobName, batchCompletedTrials, expectedTrialCount)
    : phase === "done"
      ? 100
      : phase === "launching"
        ? 12
        : stepCount > 0
          ? Math.min(95, Math.round((stepCount / Math.max(stepCount + 1, 8)) * 100))
          : phase === "running"
            ? 20
            : 0;
  const runProgressLabel = batchJobName
    ? formatBatchProgressLabel(
        batchCompletedTrials,
        expectedTrialCount,
        t,
      )
    : phase === "launching"
      ? t("eval.web.progress.launching", "Launching web trial…")
      : phase === "running"
        ? stepCount > 0
          ? t("eval.web.progress.trace", "Browser trace · {count} {unit}", {
              count: stepCount,
              unit: t(stepCount === 1 ? "eval.common.step.one" : "eval.common.step.many", stepCount === 1 ? "step" : "steps"),
            })
          : (status ?? t("eval.web.progress.browsing", "Simulated visitor is browsing…"))
        : phase === "done"
          ? t("eval.web.progress.complete", "Web run complete · {count} {unit}", {
              count: stepCount,
              unit: t(stepCount === 1 ? "eval.common.step.one" : "eval.common.step.many", stepCount === 1 ? "step" : "steps"),
            })
          : failed
            ? displayError ?? t("eval.web.progress.error", "The website test didn't finish.")
            : undefined;
  const canExport = exportSnapshot !== null && webResult !== null;

  const webLiveContent = (
    <>
              <WebResults
                task={task}
                webResult={webResult}
                trace={trace}
                phase={phase}
                status={status}
                error={displayError}
                persona={persona}
                onRetry={handleRetry}
              />
    </>
  );

  const cockpitView = (
    <CockpitSetupShell
      header={<RunHeader taskType={taskType} onTaskTypeChange={onTaskTypeChange} />}
      left={
        <PersonaSamplingRail
          taskType="web"
          taskPath={task?.taskPath ?? null}
          personaModel={personaModel}
          onPersonaModelChange={setPersonaModel}
          personaModelOptions={webPersonaModelOptions}
          mode={samplingMode}
          onModeChange={setSamplingMode}
          selectedPersonaIds={visiblePersonaIds}
          onSelectedPersonaIdsChange={setSelectedPersonaIds}
          sampleSize={sampleSize}
          onSampleSizeChange={setSampleSize}
          sampleSizePerValueGroup={sampleSizePerValueGroup}
          onSampleSizePerValueGroupChange={setSampleSizePerValueGroup}
          seed={seed}
          filters={groupFilters}
          onFiltersChange={setGroupFilters}
          stratifyFields={stratifyFields}
          onStratifyFieldsChange={setStratifyFields}
          hasTaskStrategy={hasTaskStrategy}
          taskPersonaStrategy={taskPersonaStrategy}
          useTaskDefaultStrategy={useTaskDefaultStrategy}
          onUseTaskDefaultStrategyChange={setUseTaskDefaultStrategy}
          onPersonaPoolChange={setPersonaPool}
          personaPool={personaPool}
          disabled={setupLocked}
        />
      }
      center={
        <CockpitRunCenter
          showLive={showLiveCenter}
          pipeline={
            <CockpitPipelineDiagram
              className="h-full"
              taskType="web"
              personaModelLabel={pipelinePersonaModelLabel}
              webCapabilityTierId={
                activeWebAgentFamily === "browser"
                  ? findPersonaAgent(activeWebAgent)?.tier
                  : undefined
              }
              webHarnessLabel={
                activeWebAgentFamily === "cli" ? webHarnessPipelineLabel(activeWebAgent) : undefined
              }
              webAgentFamily={activeWebAgentFamily}
              hasPersona={visiblePersonaIds.length > 0}
              hasTask={Boolean(task?.taskPath)}
            />
          }
          liveContent={webLiveContent}
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
          canRun={visiblePersonaIds.length > 0 && Boolean(task?.taskPath) && !runBusy}
          isBatch={isBatchRun}
          personaCount={visiblePersonaIds.length}
          parallelTrials={parallelTrials}
          onParallelTrialsChange={setParallelTrials}
          runBusy={runBusy}
          onRun={() => void handleLaunch()}
          error={formatCockpitRunError(launchError ?? error ?? batchError ?? retryError)}
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
          onRetryFailed={batchJobName ? () => void retryFailed() : undefined}
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
              <WebEvalScorecard webResult={webResult} verifier={verifier} phase={phase} />
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
                label={t("eval.web.contextLabel", "Task context")}
                title={instructionView.title}
                markdown={instructionView.contextMarkdown}
                loading={instructionView.loading}
                error={instructionView.error}
                emptyMessage={t("eval.web.contextEmpty", "No separate context document is available for this task.")}
                icon="menu_book"
              />
            }
          />
        ) : (
        <TaskSelectionRail
          taskType="web"
          chatTasks={[]}
          surveyTasks={[]}
          webTasks={taskCards}
          cuaTasks={[]}
          selectedTaskId={activeTaskId}
          onSelectTask={(card) => setTaskId(card.id)}
          engine=""
          onEngineChange={() => undefined}
          engineOptions={[]}
          maxTurns={8}
          onMaxTurnsChange={() => undefined}
          resolveWebPersonaAgent={resolveWebAgent}
          onWebPersonaAgentChange={(id, agent) =>
            setWebAgentByTaskId((prev) => ({ ...prev, [id]: agent }))
          }
          tasksLoading={tasksQuery.isLoading}
          tasksError={
            tasks.length === 0
              ? tasksQuery.isError
                ? t("eval.web.tasksApiUnavailable", "Web task API unavailable — restart the Playground backend on :8765.")
                : t("eval.web.tasksEmpty", "No web tasks available.")
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

/** Status-aware Persona → Website → Trace → Evaluation pipeline strip. */
function WebResults({
  task,
  webResult,
  trace,
  phase,
  status,
  error,
  persona,
  onRetry,
}: {
  task: WebEvalTask | null;
  webResult: WebResult | null;
  trace: WebTrace | null;
  phase: HarborCockpitPhase;
  status: string | null;
  error: string | null;
  persona: PlaygroundPersona | null;
  onRetry: () => void;
}) {
  const { t } = useI18n();
  const running = phase === "launching" || phase === "running";
  const failed = phase === "error" || phase === "timeout";
  const personaTitle = persona ? personaDescriptiveTitle(null, persona.blurb, persona.source) : t("eval.web.personaFallback", "Persona");
  const runDate = formatDate(webResult?.createdAt);
  const headerBits = [
    t("eval.web.siteFallback", "Web"),
    task?.title ?? t("eval.web.taskFallback", "website task"),
    personaTitle,
    ...(runDate ? [runDate] : []),
  ];

  return (
    <section className="space-y-5">
      {/* Run identity line */}
      <div className="hud flex items-start gap-2 text-[11px] text-text-variant">
        <Sym name="language" size={16} className="shrink-0 text-primary" />
        <span className="min-w-0 break-words">{t("eval.web.results.run", "Run · {details}", { details: headerBits.join(" · ") })}</span>
      </div>

      {/* Live "browsing" banner */}
      {running && !webResult && (
        <div className="rise-in rounded-md border border-outline bg-surface-lowest px-4 py-4">
          <div className="flex items-center gap-2">
            <Sym name="autorenew" size={16} className="animate-rb-spin text-primary" />
            <span className="hud text-[12px] text-primary">{t("eval.web.results.running", "Running")}</span>
          </div>
          <p className="mt-2 text-[15px] text-text-main">{t("eval.web.results.browsing", "Simulated visitor is browsing…")}</p>
          {status && <p className="mt-0.5 text-[14px] text-text-variant">{status}</p>}
          {trace && trace.events.length > 0 && (
            <p className="mt-2 font-mono text-[13px] text-text-variant">
              {t("eval.web.results.recorded", "Recorded {count} {unit} so far", {
                count: trace.events.length,
                unit: t(trace.events.length === 1 ? "eval.common.step.one" : "eval.common.step.many", trace.events.length === 1 ? "step" : "steps"),
              })}
            </p>
          )}
        </div>
      )}

      {/* Error */}
      {failed && (
        <ErrorCard
          title={t("eval.web.results.errorTitle", "The website test didn’t finish")}
          body={error ?? t("eval.web.results.errorBody", "Something interrupted the test. Your setup is still here. Press Try again.")}
          onRetry={onRetry}
          retryLabel={t("eval.web.results.retry", "Try again")}
        />
      )}

      {/* Browser trace — show as soon as partial trajectory exists */}
      {trace && trace.events.length > 0 && (
        <div className="space-y-3">
          <h3 className="hud flex items-center gap-2 text-[12px] text-primary">
            <Sym name="route" size={14} />
            {t("eval.web.results.trace", "Browser trace · {count} {unit}", {
              count: trace.events.length,
              unit: t(trace.events.length === 1 ? "eval.common.step.one" : "eval.common.step.many", trace.events.length === 1 ? "step" : "steps"),
            })}
          </h3>
          <HarborTraceReplay trace={trace} autoFollowLatest={running} />
        </div>
      )}

      {/* Loading skeleton before any result/trace lands */}
      {running && !webResult && !trace && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4" aria-hidden>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-32 animate-rb-pulse rounded-md bg-surface-high" />
          ))}
        </div>
      )}
    </section>
  );
}

function ErrorCard({
  title,
  body,
  onRetry,
  retryLabel,
}: {
  title: string;
  body: string;
  onRetry: () => void;
  retryLabel?: string;
}) {
  const { t } = useI18n();
  const resolvedRetryLabel = retryLabel ?? t("eval.common.tryAgain", "Try again");
  return (
    <section className="rounded-md border border-danger/30 bg-danger/10 p-5">
      <div className="flex items-start gap-3">
        <Sym name="error" fill={1} size={20} className="mt-0.5 text-danger" />
        <div>
          <h2 className="font-semibold text-text-main">{title}</h2>
          <p className="mt-1 text-[15px] text-text-variant">{body}</p>
          <button
            type="button"
            onClick={onRetry}
            className={`mt-3 inline-flex items-center gap-1.5 rounded-md border border-danger/40 px-3 py-1.5 text-[14px] font-medium text-danger hover:bg-danger/10 ${FOCUS_RING}`}
          >
            <Sym name="refresh" size={15} />
            {resolvedRetryLabel}
          </button>
        </div>
      </div>
    </section>
  );
}

