/**
 * PlaygroundCockpit: the Playground chatbot surface (ports the Playground
 * `app-redesign-v3.html` cockpit + liverun screens).
 *
 * Two flows off one shared state:
 *   - IDLE  (`data-view="cockpit"`) shows a centered "Configure a simulation" setup
 *     form: header + app-type switch, a compact Pipeline strip, then a 12-col
 *     grid (LEFT 8: application cards · run-configuration knobs · target persona;
 *     RIGHT 4: the read-only runtime panel · the glowing Run-eval CTA · a hint).
 *   - RUNNING/DONE (`data-view="liverun"`) shows the live-run layout: the stateful
 *     Pipeline strip, the Trajectory thread (persona/app bubbles with items +
 *     tool-plan fold), the right Inspector tabs (Evaluation / Persona / Prompts),
 *     and a bottom status bar.
 *
 * It owns all cross-component state (selected persona, run knobs, the run via
 * `usePlayground`, inspector tab, open tool-plan folds, focused turn) and the
 * keyboard shortcuts (R run · J/K move turns · 1/2/3 inspector tab · E expand
 * folds). Data is honest: real personas / config / run shape
 * (real per-turn latency; no tokens or cost, which aren't tracked).
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n/I18nProvider";

import { RunHeader } from "./RunHeader";
import { Trajectory } from "./Trajectory";
import { InspectorTabs, type InspectorTab } from "./InspectorTabs";
import { Scorecard } from "./Scorecard";
import { InstructionPanel } from "./InstructionPanel";
import { PersonaDrawer } from "./PersonaDrawer";
import { SurveyEvalCockpit } from "./SurveyEvalCockpit";
import { WebEvalCockpit } from "./WebEvalCockpit";
import { OsAppEvalCockpit } from "./OsAppEvalCockpit";
import { type PlaygroundTaskType } from "./TaskTypeSwitch";
import { CockpitSetupShell } from "./setup/CockpitSetupShell";
import { PersonaSamplingRail } from "./setup/PersonaSamplingRail";
import {
  buildPersonaLaunchFields,
  hasLaunchableCohort,
  resolveCohortSize,
} from "./setup/personaLaunchFields";
import { CockpitPipelineDiagram } from "./setup/CockpitPipelineDiagram";
import { TaskSelectionRail, type ChatTransport, type TaskCardModel } from "./setup/TaskSelectionRail";
import { BatchTrialGrid } from "./setup/BatchTrialGrid";
import { BatchTrialStage } from "./setup/BatchTrialStage";
import { CockpitLiveStage } from "./setup/CockpitLiveStage";
import { RunLaunchBar } from "./setup/RunLaunchBar";
import {
  batchProgressPct as computeBatchProgressPct,
  BATCH_RUN_COMPLETE_HINT,
  formatBatchProgressLabel,
  resolveRunLaunchPhase,
  useCockpitBatchJob,
} from "./setup/useCockpitBatchJob";
import { readCockpitBatch } from "./setup/cockpitBatchStorage";
import { useSetupPersonaSampling } from "./setup/useSetupPersonaSampling";
import { useCockpitRunCancel } from "./setup/useCockpitRunCancel";
import { useCockpitSetupLock } from "./setup/useCockpitSetupLock";
import { api, ApiError } from "@/lib/api";
import { useHarborCockpitRun, type HarborCockpitPhase } from "@/lib/useHarborCockpitRun";
import { PersonaLanguagePicker } from "@/components/i18n/PersonaLanguagePicker";
import { useUrlState } from "@/lib/useUrlState";
import { usePgTaskIdDeepLink } from "@/lib/usePgTaskIdDeepLink";
import { useCockpitInstruction } from "@/lib/useCockpitInstruction";
import { mapChatbotDebriefToJobView, mapChatbotLiveToJobView, isRewardOnlyTrialFailure } from "@/lib/harborCockpitMappers";
import { type PlaygroundRunPhase } from "@/lib/usePlayground";
import type {
  ApplicationId,
  ChatbotEvalTask,
  ConfigOptionsResponse,
  Domain,
  PlaygroundJobView,
} from "@/lib/types";
import { personaModelPipelineLabel } from "@/lib/personaAgentCatalog";
import { chatbotEvalTaskCards, sortByAvailability } from "./setup/cockpitTaskCards";
import { mergeChatbotTaskAvailability } from "@/lib/chatbotTaskAvailability";
import { resolveLaunchLanguage, readPersonaLanguageSetting } from "@/lib/personaLanguage";

/** Per-app display name + icon (presentational; the data layer is app-agnostic). */
const APP_NAME: Record<string, string> = {
  meal_planning_nutrition: "Meal Planning",
  finance_openbb: "OpenBB",
  acme_support_api: "ACME Support API",
  acme_support_mcp: "ACME Support MCP",
};

function isKnownChatApplicationId(
  value: string,
): value is "meal_planning_nutrition" | "finance_openbb" | "acme_support_api" | "acme_support_mcp" {
  return (
    value === "meal_planning_nutrition"
    || value === "finance_openbb"
    || value === "acme_support_api"
    || value === "acme_support_mcp"
  );
}

function transportForChatTask(
  task: Pick<ChatbotEvalTask, "transport" | "canStart">,
): ChatTransport {
  const transport = (task.transport || "").trim();
  if (transport === "mcp") {
    return task.canStart ? "mcp_sidecar" : "mcp_external";
  }
  if (transport === "external_http") return "api_external";
  // sidecar_http and any other HTTP local task setup
  return "api_sidecar";
}

/** Map the job's coarse phase into a single "what's happening now" line. */
function liveStatusLine(
  job: PlaygroundJobView | null,
  phase: HarborCockpitPhase,
  isRunning: boolean,
  harborPhase?: string | null,
  t?: (key: string, fallback?: string) => string,
): string | null {
  if (phase === "launching") return t ? t("eval.live.launching", "Launching batch…") : "Launching batch…";
  if (!isRunning) return null;
  const raw = (harborPhase ?? job?.phase ?? "").toLowerCase();
  if (raw.includes("harbor") || raw.includes("trial")) return t ? t("eval.live.runningTrial", "Running trial…") : "Running trial…";
  if (raw.includes("persona") || raw.includes("user") || raw.includes("simulat"))
    return t ? t("eval.live.typing", "The simulated user is typing…") : "The simulated user is typing…";
  if (raw.includes("chatbot") || raw.includes("application") || raw.includes("agent") || raw.includes("recai") || raw.includes("turn"))
    return t ? t("eval.live.thinking", "The app is thinking…") : "The app is thinking…";
  if (raw.includes("eval")) return t ? t("eval.live.scoring", "Scoring how it went…") : "Scoring how it went…";
  if (job?.phase) return `${job.phase.replace(/^harbor_/, "").replace(/_/g, " ")}…`;
  return t ? t("eval.live.runningPlayground", "Running the playground…") : "Running the playground…";
}

/** True when focus is in a text input / textarea / select / contenteditable. */
function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}

/**
 * A frozen copy of the persona + run controls captured the moment a run reaches
 * `done`. The export is built from this (never the live controls), so changing
 * a knob after a run finishes cannot mislabel the completed transcript.
 */
interface ExportSnapshot {
  persona: { id: string; name: string; source: string } | null;
  config: {
    applicationId: ApplicationId;
    applicationContext: string;
    domain?: Domain;
    engine: string;
    personaModel: string;
    maxTurns: number | null;
  };
}

export interface PlaygroundCockpitProps {
  /** Config metadata (knobs + defaults + environment) from the app. */
  options: ConfigOptionsResponse | null;
  /** Navigate to the Runs surface. */
  onOpenRuns: () => void;
  /** Open a Harbor batch job detail in the Runs sub-view. */
  onOpenHarborJob?: (jobName: string) => void;
  /** Open a Harbor trial debrief in the Runs sub-view. */
  onOpenHarborTrial?: (jobName: string, trialName: string) => void;
  /** Report the active run domain up (so the shared catalog drawer can match it). */
  onDomainChange?: (domain: Domain) => void;
  /** Report the honest footer context up (task type + active app/instrument/site). */
  onFooterContextChange?: (context: string) => void;
}

/** Keep inactive cockpits mounted (hidden) so setup + run state survives type switches. */
function CockpitPanel({ active, children }: { active: boolean; children: ReactNode }) {
  return (
    <div
      className={active ? "flex min-h-0 flex-1 flex-col overflow-hidden" : "hidden"}
      aria-hidden={!active}
    >
      {children}
    </div>
  );
}

const PLAYGROUND_TASK_TYPES: ReadonlyArray<PlaygroundTaskType> = ["survey", "chatbot", "web", "os-app"];

function parsePlaygroundTask(value: string | null): PlaygroundTaskType {
  if (value === "cua") return "os-app";
  return value && (PLAYGROUND_TASK_TYPES as readonly string[]).includes(value)
    ? (value as PlaygroundTaskType)
    : "survey";
}

export function PlaygroundCockpit({
  options,
  onOpenRuns,
  onOpenHarborJob,
  onOpenHarborTrial,
  onDomainChange,
  onFooterContextChange,
}: PlaygroundCockpitProps) {
  const { state: urlState, setState: setUrlState } = useUrlState();
  const [taskType, setTaskTypeInternal] = useState<PlaygroundTaskType>(() => parsePlaygroundTask(urlState.pgTask));

  useEffect(() => {
    const next = parsePlaygroundTask(urlState.pgTask);
    setTaskTypeInternal((current) => (current === next ? current : next));
  }, [urlState.pgTask]);

  const setTaskType = useCallback(
    (next: PlaygroundTaskType) => {
      setTaskTypeInternal(next);
      const batch = readCockpitBatch(next);
      setUrlState({
        pgTask: next,
        cockpitJob: null,
        cockpitTrial: null,
        cockpitBatch: batch?.jobName ?? null,
      });
    },
    [setUrlState],
  );

    return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <CockpitPanel active={taskType === "chatbot"}>
        <ChatbotEvalCockpit
          options={options}
          onOpenRuns={onOpenRuns}
          onOpenHarborJob={onOpenHarborJob}
          onOpenHarborTrial={onOpenHarborTrial}
          onDomainChange={onDomainChange}
          onFooterContextChange={onFooterContextChange}
          taskType={taskType}
          onTaskTypeChange={setTaskType}
          isActive={taskType === "chatbot"}
        />
      </CockpitPanel>
      <CockpitPanel active={taskType === "survey"}>
      <SurveyEvalCockpit
        options={options}
        taskType={taskType}
        onTaskTypeChange={setTaskType}
        onFooterContextChange={onFooterContextChange}
        onOpenHarborJob={onOpenHarborJob}
        onOpenHarborTrial={onOpenHarborTrial}
          isActive={taskType === "survey"}
        />
      </CockpitPanel>
      <CockpitPanel active={taskType === "web"}>
      <WebEvalCockpit
        options={options}
        taskType={taskType}
        onTaskTypeChange={setTaskType}
        onFooterContextChange={onFooterContextChange}
        onOpenHarborJob={onOpenHarborJob}
        onOpenHarborTrial={onOpenHarborTrial}
          isActive={taskType === "web"}
        />
      </CockpitPanel>
      <CockpitPanel active={taskType === "os-app"}>
        <OsAppEvalCockpit
        options={options}
        taskType={taskType}
        onTaskTypeChange={setTaskType}
        onFooterContextChange={onFooterContextChange}
      onOpenHarborJob={onOpenHarborJob}
      onOpenHarborTrial={onOpenHarborTrial}
          isActive={taskType === "os-app"}
    />
      </CockpitPanel>
    </div>
  );
}

interface ChatbotEvalCockpitProps extends PlaygroundCockpitProps {
  taskType: PlaygroundTaskType;
  onTaskTypeChange: (value: PlaygroundTaskType) => void;
  isActive: boolean;
}

function ChatbotEvalCockpit({
  options,
  onOpenHarborJob,
  onOpenHarborTrial,
  onDomainChange,
  onFooterContextChange,
  taskType,
  onTaskTypeChange,
  isActive,
}: ChatbotEvalCockpitProps) {
  const { t, locale } = useI18n();
  const { state: urlState } = useUrlState();
  const { run, job, phase, isRunning, error, timedOut, retry, reset, harborPhase, harborJobName, harborTrialName, cancelRun, cancelBusy: harborCancelBusy } =
    useHarborCockpitRun<PlaygroundJobView>({ taskKind: "chatbot" });

  // --- Selection + run knobs ---------------------------------------------
  const [selectedTaskId, setSelectedTaskId] = useState<string>("");
  const [engine, setEngine] = useState<string>(options?.defaults.engine ?? "gpt-4o-mini");
  const [maxTurns, setMaxTurns] = useState<number | null>(null);
  const [sidecarStartingId, setSidecarStartingId] = useState<string | null>(null);
  const [sidecarActionError, setSidecarActionError] = useState<string | null>(null);
  const tasksQuery = useQuery({
    queryKey: ["chatbot-eval-tasks"],
    queryFn: api.listChatbotEvalTasks,
    enabled: isActive,
    staleTime: 60_000,
  });
  const sidecarsQuery = useQuery({
    queryKey: ["chatbot-sidecars"],
    queryFn: api.getChatbotSidecars,
    enabled: isActive,
    staleTime: 10_000,
    refetchInterval: isActive && sidecarStartingId ? 3_000 : isActive ? 15_000 : false,
  });
  const chatbotTasks = useMemo(() => {
    const sidecars = sidecarsQuery.data?.sidecars ?? [];
    const merged = (tasksQuery.data?.tasks ?? []).map((task) =>
      mergeChatbotTaskAvailability(task, sidecars),
    );
    return sortByAvailability(merged);
  }, [tasksQuery.data?.tasks, sidecarsQuery.data?.sidecars]);
  const setupTaskPath =
    chatbotTasks.find((task) => task.id === selectedTaskId)?.taskPath ?? null;
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
  } = useSetupPersonaSampling(options, "chatbot", setupTaskPath, isActive);
  const pipelinePersonaModelLabel = useMemo(
    () => personaModelPipelineLabel(personaModel, personaModelOptions),
    [personaModel, personaModelOptions],
  );
  const [launchError, setLaunchError] = useState<string | null>(null);
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
    completedTrials: batchCompletedTrials,
    expectedTrialCount,
    personaById,
    batchError,
  } = useCockpitBatchJob(selectedPersonaIds, parallelTrials, "chatbot", selectedCount, personaPool);
  const [exportSnapshot, setExportSnapshot] = useState<ExportSnapshot | null>(null);

  // After navigating away/back, single-trial restore brings back the transcript
  // but strategy hydrate used to wipe the left-rail selection. Re-adopt the
  // persona id from the restored job when the rail is empty.
  useEffect(() => {
    const id = typeof job?.personaId === "string" ? job.personaId.trim() : "";
    if (!id || phase === "idle" || selectedPersonaIds.length > 0) return;
    setSelectedPersonaIds([id]);
  }, [job?.personaId, phase, selectedPersonaIds.length, setSelectedPersonaIds]);

  useEffect(() => {
    if (!batchTaskId) return;
    setSelectedTaskId(batchTaskId);
  }, [batchTaskId]);

  const chatbotTaskIds = useMemo(() => chatbotTasks.map((task) => task.id), [chatbotTasks]);
  usePgTaskIdDeepLink("chatbot", chatbotTaskIds, setSelectedTaskId, isActive);

  // No auto-selection: the pipeline stays unlit until the operator explicitly
  // picks a task (deep links and batch adoption still apply).
  useEffect(() => {
    if (urlState.pgTaskId) return;
    if (!chatbotTasks.length) return;
    setSelectedTaskId((current) =>
      current && chatbotTasks.some((task) => task.id === current) ? current : "",
    );
  }, [chatbotTasks, urlState.pgTaskId]);

  // Adopt engine default once config metadata arrives. Sidecar context/domain
  // come only from chatbot.yaml and are passed through as opaque runtime defaults.
  const adoptedDefaults = useRef(false);
  useEffect(() => {
    if (adoptedDefaults.current || !options) return;
    adoptedDefaults.current = true;
    setEngine(options.defaults.engine ?? "gpt-4o-mini");
  }, [options]);

  const selectedTask = useMemo(
    () => chatbotTasks.find((task) => task.id === selectedTaskId) ?? null,
    [chatbotTasks, selectedTaskId],
  );
  const applicationId = (selectedTask?.applicationId ||
    (options?.defaults.applicationId as ApplicationId | undefined) ||
    "chatbot") as ApplicationId;
  // Opaque passthrough from task chatbot.yaml — Playground does not interpret "domain".
  const applicationContext =
    selectedTask?.applicationContext?.trim() ||
    selectedTask?.defaultDomain?.trim() ||
    contextForApplication(applicationId, "movie");
  const requestDomain = selectedTask?.defaultDomain?.trim() || undefined;

  useEffect(() => {
    if (requestDomain) onDomainChange?.(requestDomain as Domain);
  }, [requestDomain, onDomainChange]);

  const handleStartSidecar = useCallback(
    async (taskId: string) => {
      const task = chatbotTasks.find((entry) => entry.id === taskId);
      const appId = task?.applicationId?.trim() ?? "";
      if (!task?.canStart || !appId) return;
      setSidecarActionError(null);
      setSidecarStartingId(taskId);
      try {
        await api.startChatbotSidecar(appId);
        await sidecarsQuery.refetch();
      } catch (e) {
        setSidecarActionError(
        e instanceof Error ? e.message : t("eval.common.startSidecarFailed", "Failed to start sidecar"),
      );
      } finally {
        setSidecarStartingId(null);
      }
    },
    [chatbotTasks, sidecarsQuery],
  );

  // Live persona + controls, mirrored to a ref so the "run finished" effect can
  // freeze them without re-running when a control changes.
  const liveControls = useMemo<ExportSnapshot>(
    () => ({
      persona: persona ? { id: persona.id, name: persona.name, source: persona.source } : null,
      config: {
        applicationId,
        applicationContext,
        domain: requestDomain,
        engine,
        personaModel,
        maxTurns,
      },
    }),
    [persona, applicationId, applicationContext, requestDomain, engine, personaModel, maxTurns],
  );
  const liveControlsRef = useRef(liveControls);
  liveControlsRef.current = liveControls;

  useEffect(() => {
    if (phase === "done") {
      setExportSnapshot((prev) => prev ?? liveControlsRef.current);
    }
  }, [phase]);

  // --- Inspector + folds + focus -----------------------------------------
  const [tab, setTab] = useState<InspectorTab>("evaluation");
  const [expandedTurns, setExpandedTurns] = useState<Set<number>>(new Set());
  const [focusedTurnIndex, setFocusedTurnIndex] = useState<number | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const turnRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  // --- Elapsed clock (live status bar) -----------------------------------
  const runStartedAtRef = useRef<number | null>(null);
  const [, setNowTick] = useState(0);
  useEffect(() => {
    if (!isRunning) return;
    const id = window.setInterval(() => setNowTick(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [isRunning]);

  const turns = useMemo(() => job?.turns ?? [], [job]);
  const draftTurn = job?.draftTurn ?? null;
  const sutDescription = job?.sutDescription ?? null;
  const status = liveStatusLine(job, phase, isRunning, harborPhase, t);
  const questionnaire = job?.questionnaire ?? null;
  const metrics = job?.metricScores ?? null;
  const chatTaskPath = selectedTask?.taskPath?.trim() ?? "";
  const chatTaskLabel = selectedTask?.title ?? APP_NAME[applicationId] ?? "Chatbot task";
  const knownLaunchApplicationId = isKnownChatApplicationId(applicationId) ? applicationId : null;
  // Prefer task-declared context; otherwise fall back by applicationId when known.
  const launchChatApplicationContext =
    selectedTask?.applicationContext?.trim() ||
    (knownLaunchApplicationId
      ? contextForApplication(knownLaunchApplicationId, (requestDomain || "movie") as Domain)
      : undefined);
  const runContext = chatTaskLabel;

  // Report the honest footer context up (task type + selected chatbot).
  useEffect(() => {
    if (!isActive) return;
    onFooterContextChange?.(`chatbot · ${runContext}`);
  }, [isActive, runContext, onFooterContextChange]);

  // --- Actions ------------------------------------------------------------
  const handleRun = useCallback(() => {
    if (!persona || isRunning || !chatTaskPath) return;
    if (phase === "error" || phase === "done" || phase === "timeout") {
      reset();
    }
    setExpandedTurns(new Set());
    setFocusedTurnIndex(null);
    setExportSnapshot(null);
    setLaunchError(null);
    runStartedAtRef.current = Date.now();
    void run({
      taskPath: chatTaskPath,
      personaId: persona.id,
      personaModel,
      mode: "auto",
      chatDomain: requestDomain,
      chatApplicationId: knownLaunchApplicationId ?? undefined,
      chatApplicationContext: launchChatApplicationContext,
      chatMaxTurns: maxTurns,
      ...resolveLaunchLanguage(readPersonaLanguageSetting(), locale),
      mapDebrief: (debrief, ctx) =>
        mapChatbotDebriefToJobView(debrief, ctx, {
          personaId: persona.id,
          personaName: persona.name,
          domain: requestDomain,
          applicationId,
        }),
      mapLive: (live, ctx) =>
        mapChatbotLiveToJobView(live, ctx, {
          personaId: persona.id,
          personaName: persona.name,
          domain: requestDomain,
          applicationId,
        }),
    });
  }, [
    persona,
    isRunning,
    chatTaskPath,
    run,
    applicationId,
    personaModel,
    requestDomain,
    knownLaunchApplicationId,
    launchChatApplicationContext,
    maxTurns,
    phase,
    reset,
    locale,
  ]);

  const handleLaunch = useCallback(async () => {
    if (
      !hasLaunchableCohort({ selectedPersonaIds, selectedCount, useEntirePool }) ||
      isRunning ||
      !chatTaskPath ||
      !selectedTask
    ) {
      return;
    }
    if (isBatchRun) {
      setLaunchError(null);
      try {
        const personaFields = buildPersonaLaunchFields({
          personaPool,
          selectedPersonaIds,
          selectedCount,
          useEntirePool,
          parallelTrials,
        });
        const launched = await api.launchHarborJob({
          taskPath: chatTaskPath,
          seed,
          personaModel,
          ...personaFields,
          mode: "auto",
          chatDomain: requestDomain,
          chatApplicationId: knownLaunchApplicationId ?? undefined,
          chatApplicationContext: launchChatApplicationContext,
          chatMaxTurns: maxTurns,
          ...resolveLaunchLanguage(readPersonaLanguageSetting(), locale),
        });
        setBatchJobName(launched.jobName, { taskId: selectedTask.id, personaPool });
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
    isRunning,
    isBatchRun,
    applicationId,
    seed,
    personaModel,
    parallelTrials,
    personaPool,
    requestDomain,
    knownLaunchApplicationId,
    launchChatApplicationContext,
    maxTurns,
    chatTaskPath,
    selectedTask,
    handleRun,
    setBatchJobName,
    locale,
  ]);

  const handleRetry = useCallback(() => {
    if (timedOut || phase === "error") retry();
    else handleRun();
  }, [timedOut, phase, retry, handleRun]);

  const handleNewRun = useCallback(() => {
    reset();
    clearBatch();
    setLaunchError(null);
    setFocusedTurnIndex(null);
    setExpandedTurns(new Set());
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

  const registerTurnRef = useCallback((index: number, el: HTMLDivElement | null) => {
    if (el) turnRefs.current.set(index, el);
    else turnRefs.current.delete(index);
  }, []);

  const toggleTurnFold = useCallback((index: number) => {
    setExpandedTurns((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }, []);

  const toggleExpandAll = useCallback(() => {
    setExpandedTurns((prev) => (prev.size >= turns.length && turns.length > 0 ? new Set() : new Set(turns.map((_, i) => i))));
  }, [turns]);

  const moveFocus = useCallback(
    (delta: number) => {
      if (turns.length === 0) return;
      setFocusedTurnIndex((prev) => {
        const start = prev ?? (delta > 0 ? -1 : turns.length);
        const next = Math.max(0, Math.min(turns.length - 1, start + delta));
        const el = turnRefs.current.get(next);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
        return next;
      });
    },
    [turns.length],
  );

  // --- Export (client-side JSON of the completed run) ---------------------
  const handleExport = useCallback(() => {
    if (!exportSnapshot || turns.length === 0) return;
    const payload = {
      persona: exportSnapshot.persona,
      config: exportSnapshot.config,
      transcript: turns,
      questionnaire,
      metricScores: metrics,
      exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `playground-${exportSnapshot.persona?.id ?? "run"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [exportSnapshot, turns, questionnaire, metrics]);

  const canExport = exportSnapshot !== null && turns.length > 0;

  // --- Keyboard shortcuts -------------------------------------------------
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isTypingTarget(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      switch (e.key) {
        case "r":
        case "R":
          e.preventDefault();
          void handleLaunch();
          break;
        case "j":
        case "J":
          e.preventDefault();
          moveFocus(1);
          break;
        case "k":
        case "K":
          e.preventDefault();
          moveFocus(-1);
          break;
        case "1":
          e.preventDefault();
          setTab("evaluation");
          break;
        case "2":
          e.preventDefault();
          setTab("instruction");
          break;
        case "3":
          e.preventDefault();
          setTab("context");
          break;
        case "e":
        case "E":
          e.preventDefault();
          toggleExpandAll();
          break;
        default:
          break;
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [handleLaunch, moveFocus, toggleExpandAll]);

  const knobs = options?.knobs ?? [];
  const engineKnob = knobs.find((k) => k.key === "engine");
  const engineOptions = engineKnob?.options ?? [];
  const chatTransport = selectedTask ? transportForChatTask(selectedTask) : "api_sidecar";
  const runningChatTaskIds = useMemo(() => {
    const ids = new Set<string>();
    if (isRunning && selectedTaskId) ids.add(selectedTaskId);
    if (isBatchActive && batchTaskId) ids.add(batchTaskId);
    return ids;
  }, [isRunning, selectedTaskId, isBatchActive, batchTaskId]);
  const chatTaskCards = useMemo<TaskCardModel[]>(
    () => chatbotEvalTaskCards(chatbotTasks, { runningTaskIds: runningChatTaskIds }, t),
    [chatbotTasks, runningChatTaskIds],
  );
  const verifierOnlyFailure = isRewardOnlyTrialFailure(error ?? job?.error ?? null, {
    transcript: turns,
    questionnaire: questionnaire ?? undefined,
  });
  const pipelinePhase = (
    !verifierOnlyFailure && (job?.status === "error" || phase === "error")
      ? "error"
      : phase === "launching"
        ? "building"
        : phase
  ) as PlaygroundRunPhase;
  const elapsedSeconds =
    isRunning && runStartedAtRef.current ? Math.max(0, Math.floor((Date.now() - runStartedAtRef.current) / 1000)) : 0;
  const showLiveCenter = phase !== "idle" || Boolean(batchJobName);
  const showInspector = phase !== "idle" && !batchJobName;
  const runBusy = isRunning || isBatchActive;
  const { setupLocked, visiblePersonaIds } = useCockpitSetupLock(
    phase,
    batchJobName,
    batchPersonaIds,
    selectedPersonaIds,
  );
  const visiblePersonaPool = batchJobName ? batchPersonaPool ?? personaPool : personaPool;
  const instructionView = useCockpitInstruction({
    taskPath: chatTaskPath,
    fallbackTitle: chatTaskLabel,
    harborJobName,
    harborTrialName,
    enabled: phase !== "idle" && Boolean(chatTaskPath),
  });

  const runLaunchPhase = resolveRunLaunchPhase(
    batchJobName,
    batchComplete,
    batchError,
    phase,
    batchCancelled,
  );

  const runProgressPct = batchJobName
    ? batchCancelled
      ? Math.max(
          0,
          computeBatchProgressPct(
            batchJobName,
            batchCompletedTrials,
            expectedTrialCount,
          ),
        )
      : computeBatchProgressPct(
          batchJobName,
          batchCompletedTrials,
          expectedTrialCount,
        )
    : pipelinePhase === "done"
      ? 100
      : pipelinePhase === "building"
        ? 12
        : pipelinePhase === "running"
          ? maxTurns !== null
            ? Math.min(100, Math.round((turns.length / Math.max(1, maxTurns)) * 100))
            : Math.min(92, 18 + turns.length * 14)
          : pipelinePhase === "error" || pipelinePhase === "timeout"
            ? 100
            : 0;

  const runProgressLabel = batchJobName
    ? batchCancelled
      ? t("eval.progress.batchStopped", "Batch stopped")
      : formatBatchProgressLabel(
          batchCompletedTrials,
          expectedTrialCount,
          t,
        )
    : pipelinePhase === "building"
      ? t("eval.progress.starting", "Starting the app…")
      : pipelinePhase === "running"
        ? maxTurns !== null
          ? t("eval.progress.turnOf", `Turn ${turns.length} of ${maxTurns} · ${elapsedSeconds}s`, {
              current: String(turns.length),
              total: String(maxTurns),
              seconds: String(elapsedSeconds),
            })
          : t("eval.progress.turn", `Turn ${turns.length} · ${elapsedSeconds}s`, {
              current: String(turns.length),
              seconds: String(elapsedSeconds),
            })
        : pipelinePhase === "done"
          ? t("eval.progress.complete", `Run complete · ${turns.length} turn${turns.length === 1 ? "" : "s"}`, {
              count: String(turns.length),
            })
          : pipelinePhase === "error" || pipelinePhase === "timeout"
            ? error?.startsWith("Run stopped")
              ? t("eval.progress.runStopped", "Run stopped")
              : error ?? t("eval.progress.stopped", "The run stopped before completing.")
            : undefined;

  const cockpitView = (
    <CockpitSetupShell
      header={<RunHeader taskType={taskType} onTaskTypeChange={onTaskTypeChange} />}
      left={
        <PersonaSamplingRail
          taskType="chatbot"
          taskPath={chatTaskPath || null}
          personaModel={personaModel}
          onPersonaModelChange={setPersonaModel}
          personaModelOptions={personaModelOptions}
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
        <div className="flex h-full min-h-0 w-full flex-col gap-2 overflow-hidden">
          {showLiveCenter ? (
            batchJobName ? (
              <BatchTrialStage>
                <BatchTrialGrid trials={batchGridCells} jobLabel={batchJobName} />
              </BatchTrialStage>
            ) : (
              <CockpitLiveStage className="h-0 min-h-0 flex-1">
                <Trajectory
          turns={turns}
                  draftTurn={draftTurn}
                  livePhase={job?.phase ?? harborPhase}
          domain={(requestDomain || applicationContext || "movie") as Domain}
          appName={chatTaskLabel}
          personaId={persona?.id}
          personaName={persona?.name}
          personaDimensions={
            persona?.id ? personaById[persona.id]?.dimensions ?? {} : {}
          }
          sutDescription={sutDescription}
          phase={pipelinePhase}
          liveStatus={status}
          error={verifierOnlyFailure ? null : error}
          expandedTurns={expandedTurns}
          onToggleTurn={toggleTurnFold}
          focusedTurnIndex={focusedTurnIndex}
          registerTurnRef={registerTurnRef}
          onRetry={handleRetry}
                />
              </CockpitLiveStage>
            )
          ) : (
            <div className="flex min-h-0 flex-1 flex-col">
              <CockpitPipelineDiagram
                className="h-full"
                taskType={taskType}
                chatTransport={chatTransport}
                chatbotLabel={chatTaskLabel}
                personaModelLabel={pipelinePersonaModelLabel}
                hasPersona={visiblePersonaIds.length > 0}
                hasTask={Boolean(chatTaskPath)}
              />
            </div>
          )}
          <div className="flex items-center justify-end gap-3 pb-2">
            <PersonaLanguagePicker />
          </div>
          <RunLaunchBar
            canRun={
              hasLaunchableCohort({ selectedPersonaIds, selectedCount, useEntirePool }) &&
              Boolean(chatTaskPath) &&
              !runBusy
            }
            isBatch={isBatchRun}
            personaCount={Math.max(
              resolveCohortSize({ selectedPersonaIds, selectedCount }),
              visiblePersonaIds.length,
            )}
            parallelTrials={parallelTrials}
            onParallelTrialsChange={setParallelTrials}
            isRunning={runBusy}
            onRun={() => void handleLaunch()}
            error={launchError ?? (verifierOnlyFailure ? null : error) ?? batchError ?? retryError}
            runPhase={runLaunchPhase}
            progressPct={runProgressPct}
            progressLabel={runProgressLabel}
            progressSublabel={
              batchJobName && batchComplete
                ? t("eval.common.batchCompleteHint", BATCH_RUN_COMPLETE_HINT)
                : undefined
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
        </div>
      }
      right={
        showInspector ? (
        <InspectorTabs
          active={tab}
          onChange={setTab}
          evaluation={<Scorecard questionnaire={questionnaire} metrics={metrics} phase={pipelinePhase} />}
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
                label={t("eval.common.taskContextLabel", "Task context")}
                title={instructionView.title}
                markdown={instructionView.contextMarkdown}
                loading={instructionView.loading}
                error={instructionView.error}
                emptyMessage={t("eval.common.noSeparateContext", "No separate context document is available for this task.")}
                icon="menu_book"
              />
            }
          />
        ) : (
          <TaskSelectionRail
            taskType={taskType}
            chatTasks={chatTaskCards}
            surveyTasks={[]}
            webTasks={[]}
            cuaTasks={[]}
            selectedTaskId={selectedTask?.id ?? selectedTaskId}
            onSelectTask={(task) => {
              setSelectedTaskId(task.id);
              setSidecarActionError(null);
            }}
            engine={engine}
            onEngineChange={setEngine}
            engineOptions={engineOptions}
            maxTurns={maxTurns}
            onMaxTurnsChange={setMaxTurns}
            onStartSidecar={handleStartSidecar}
            sidecarStartingId={sidecarStartingId}
            sidecarActionError={sidecarActionError}
            tasksLoading={tasksQuery.isLoading}
            tasksError={tasksQuery.error instanceof Error ? tasksQuery.error.message : null}
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
function contextForApplication(applicationId: ApplicationId, domain: Domain): string {
  if (applicationId === "finance_openbb") return "financial_research";
  if (applicationId === "meal_planning_nutrition") return "meal_planning";
  if (applicationId === "acme_support_api" || applicationId === "acme_support_mcp") return "customer_support";
  return domain;
}

export default PlaygroundCockpit;
