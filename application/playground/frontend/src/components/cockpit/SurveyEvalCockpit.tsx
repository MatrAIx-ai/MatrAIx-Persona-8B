/**
 * SurveyEvalCockpit: the Survey Playground surface.
 *
 * Reproduces the approved redesign mockup's `data-view="cockpit"` setup form
 * (the same centered shell as the canonical chatbot cockpit: header +
 * application-type switch + pipeline strip + run-config card + target-persona
 * panel + Run-eval CTA), with the Survey-specific body (an instrument picker +
 * an "Instrument preview" panel and a driver/artifacts note instead of an
 * environment panel.
 * environment). Once a run starts, the left column flips to the live answering /
 * results view modelled on `data-view="surveylive"` (completion progress +
 * mean-Likert summary + per-question answer cards with likert / single / multi /
 * free-text rendering).
 *
 * Harbor-backed: `useHarborCockpitRun`, task detail lazy-load on selection,
 * query, the export logic, and every result/trajectory shape are wired exactly
 * as before. Only the structure and presentation are rebuilt.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useI18n } from "@/i18n/I18nProvider";
import { listSurveyHarborTasks, api } from "@/lib/api";
import { personaModelPipelineLabel } from "@/lib/personaAgentCatalog";
import type {
  ConfigOptionsResponse,
  SurveyAnswer,
  SurveyHarborTask,
  SurveyHarborTasksResponse,
  SurveyInstrument,
  SurveyEvalJobView,
  SurveyQuestion,
  SurveyResult,
  SurveyTrajectoryEvent,
} from "@/lib/types";
import { useHarborCockpitRun, type HarborCockpitPhase } from "@/lib/useHarborCockpitRun";
import { usePgTaskIdDeepLink } from "@/lib/usePgTaskIdDeepLink";
import { useUrlState } from "@/lib/useUrlState";
import { useCockpitInstruction } from "@/lib/useCockpitInstruction";
import { mapSurveyDebriefToJobView, mapSurveyLiveToJobView, isRewardOnlyTrialFailure, classifyCockpitRunError } from "@/lib/harborCockpitMappers";
import { localizeCockpitRunError } from "./cockpitRunErrorPresentation";
import {
  formatSurveyTrajectoryValue,
  groupSurveyTrajectory,
  surveyQuestionTypeChipClass,
  surveyQuestionTypeLabel,
  surveyTrajectoryPrompt,
  surveyTrajectoryQuestionIndex,
  surveyTrajectoryQuestionType,
} from "@/lib/surveyDisplay";
import { normalizeTaskInstructionMarkdown } from "@/lib/taskContent";
import { Markdown } from "@/components/Markdown";
import { QuestionnairePreview } from "@/components/QuestionnairePreview";
import { RunHeader } from "./RunHeader";
import { PersonaDrawer } from "./PersonaDrawer";
import { InspectorTabs, type InspectorTab } from "./InspectorTabs";
import { InstructionPanel } from "./InstructionPanel";
import { SurveyEvalScorecard } from "./TaskEvalScorecard";
import { CockpitSetupShell } from "./setup/CockpitSetupShell";
import { PersonaSamplingRail } from "./setup/PersonaSamplingRail";
import { resolveCohortSize } from "./setup/personaLaunchFields";
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
import { surveyHarborTaskCards } from "./setup/cockpitTaskCards";
import type { TaskCardModel } from "./setup/TaskSelectionRail";
import {
  FOCUS_RING,
  Sym,
  humanizeToken,
} from "./cockpitShared";
import type { PlaygroundTaskType } from "./TaskTypeSwitch";
import { HARBOR_TASK_PATHS } from "@/lib/types";

type Translate = ReturnType<typeof useI18n>["t"];
export interface SurveyEvalCockpitProps {
  options: ConfigOptionsResponse | null;
  taskType: PlaygroundTaskType;
  onTaskTypeChange: (value: PlaygroundTaskType) => void;
  /** Report the honest footer context up (the active questionnaire). */
  onFooterContextChange?: (context: string) => void;
  /** Open a launched Harbor job in the Runs sub-view. */
  onOpenHarborJob?: (jobName: string) => void;
  onOpenHarborTrial?: (jobName: string, trialName: string) => void;
  /** When false, the cockpit stays mounted but hidden — skip footer updates. */
  isActive?: boolean;
}



function surveyStatusLine(
  phase: HarborCockpitPhase,
  jobPhase: string | null | undefined,
  harborPhase: string | null | undefined,
  t: Translate,
): string | null {
  if (phase === "launching") return t("eval.survey.status.launching");
  if (phase !== "running") return null;
  const raw = (harborPhase ?? jobPhase ?? "").toLowerCase();
  if (raw.includes("harbor") || raw.includes("trial")) return t("eval.survey.status.trial");
  if (raw.includes("collect")) return t("eval.survey.status.collecting");
  if (raw.includes("survey")) return t("eval.survey.status.answering");
  return t("eval.survey.status.running");
}

/** Friendly chip word + tint + tooltip for a survey question type. Presentation only. */
function questionTypeMeta(type: string, t: Translate): { label: string; tone: string; tooltip: string } {
  const label = surveyQuestionTypeLabel(type, t);
  const tone = surveyQuestionTypeChipClass(type);
  switch (type) {
    case "likert":
      return { label, tone, tooltip: t("eval.survey.tooltip.likert") };
    case "single_choice":
      return { label, tone, tooltip: t("eval.survey.tooltip.singleChoice") };
    case "multi_choice":
      return { label, tone, tooltip: t("eval.survey.tooltip.multiChoice") };
    case "free_text":
      return { label, tone, tooltip: t("eval.survey.tooltip.freeText") };
    default:
      return { label, tone, tooltip: type || t("eval.survey.questionType") };
  }
}

/** Friendly actor name for a trajectory row. Presentation only. */
function trajectoryActor(actor: string, t: Translate): string {
  const value = actor.toLowerCase();
  if (value === "agent") return t("eval.survey.actor.agent");
  if (value === "system") return t("eval.survey.actor.system");
  if (value === "scorer") return t("eval.survey.actor.scorer");
  return actor;
}

function formatSurveyValue(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => String(item)).join(", ");
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function inferSurveyTaskIdFromJob(jobName: string, taskCards: TaskCardModel[]): string | null {
  const normalized = jobName.toLowerCase();
  for (const card of taskCards) {
    const folder = card.taskPath.split("/").pop() ?? "";
    const slug = folder.replace(/^example-survey_/, "").replace(/^survey_/, "").replace(/_/g, "-");
    if (slug && normalized.includes(slug)) {
      return card.id;
    }
  }
  return null;
}

export function SurveyEvalCockpit({
  options,
  taskType,
  onTaskTypeChange,
  onFooterContextChange,
  onOpenHarborJob,
  onOpenHarborTrial,
  isActive = true,
}: SurveyEvalCockpitProps) {
  const { t } = useI18n();
  const { state: urlState } = useUrlState();
  const { run, job, phase, isRunning, error, timedOut, retry, reset, harborPhase, harborJobName, harborTrialName, cancelRun, cancelBusy: harborCancelBusy } =
    useHarborCockpitRun<SurveyEvalJobView>({ taskKind: "survey" });
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [tab, setTab] = useState<InspectorTab>("evaluation");
  const [exportSnapshot, setExportSnapshot] = useState<{
    persona: { id: string; name: string; source: string } | null;
    taskId: string;
    personaModel: string;
  } | null>(null);

  const harborTasksQuery = useQuery<SurveyHarborTasksResponse>({
    queryKey: ["survey-eval-harbor-tasks"],
    queryFn: listSurveyHarborTasks,
    enabled: isActive,
    staleTime: 10 * 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
  const harborTasks = useMemo(
    () => harborTasksQuery.data?.tasks ?? [],
    [harborTasksQuery.data?.tasks],
  );

  const taskCards = useMemo(() => surveyHarborTaskCards(harborTasks), [harborTasks]);
  const setupTaskPath =
    taskCards.find((item) => item.id === selectedTaskId)?.taskPath ?? null;
  const selectedTaskDetailQuery = useQuery({
    queryKey: ["task-detail", setupTaskPath],
    queryFn: () => api.getTaskDetail(setupTaskPath!),
    enabled: isActive && Boolean(setupTaskPath),
    staleTime: 300_000,
    retry: 1,
  });
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
  } = useCockpitLaunch(options, "survey", setupTaskPath, isActive);
  const setupLocked = phase !== "idle" || Boolean(batchJobName);
  const visiblePersonaIds = setupLocked && batchPersonaIds.length > 0 ? batchPersonaIds : selectedPersonaIds;
  // Locked batches must read cards from the launch-time pool (cohort path);
  // the live setup pool may have reverted to the raw dataset on reload.
  const visiblePersonaPool = batchJobName ? batchPersonaPool ?? personaPool : personaPool;
  const activeTaskId = batchJobName && batchTaskId ? batchTaskId : selectedTaskId;
  const selectedCard =
    taskCards.find((item) => item.id === activeTaskId) ?? null;
  const harborTask: SurveyHarborTask | null =
    harborTasks.find((item) => item.id === selectedCard?.id) ?? null;
  const activeQuestionnaire: SurveyInstrument | null = useMemo(() => {
    const fromDetail = selectedTaskDetailQuery.data?.questionnaire;
    if (fromDetail?.questions?.length) return fromDetail;
    return null;
  }, [selectedTaskDetailQuery.data?.questionnaire]);

  const pipelinePersonaModelLabel = useMemo(
    () => personaModelPipelineLabel(personaModel, personaModelOptions),
    [personaModel, personaModelOptions],
  );

  const surveyTaskIds = useMemo(() => taskCards.map((card) => card.id), [taskCards]);
  usePgTaskIdDeepLink("survey", surveyTaskIds, setSelectedTaskId, isActive);

  useEffect(() => {
    if (urlState.pgTaskId) return;
    if (batchTaskId) {
      setSelectedTaskId(batchTaskId);
      return;
    }
    if (batchJobName && taskCards.length > 0) {
      const inferred = inferSurveyTaskIdFromJob(batchJobName, taskCards);
      if (inferred) {
        setSelectedTaskId(inferred);
        return;
      }
    }
  }, [batchTaskId, batchJobName, taskCards, urlState.pgTaskId]);

  // Report the honest footer context up (the active questionnaire).
  useEffect(() => {
    if (!isActive) return;
    onFooterContextChange?.(
      `survey · ${harborTask?.title ?? activeQuestionnaire?.title ?? t("eval.survey.titleFallback")}`,
    );
  }, [isActive, harborTask, activeQuestionnaire, onFooterContextChange, t]);

  const surveyResult = job?.surveyResult ?? null;
  const verifier = job?.verifier ?? null;
  const verifierOnlyFailure = isRewardOnlyTrialFailure(error ?? job?.error ?? null, {
    surveyResult: surveyResult ?? undefined,
  });
  const displayError = localizeCockpitRunError(
    classifyCockpitRunError(error ?? job?.error ?? null),
    t,
  );
  const failed =
    !verifierOnlyFailure &&
    (phase === "error" || phase === "timeout" || job?.status === "error");
  const status = surveyStatusLine(phase, job?.phase, harborPhase, t);
  const setupInstructionMarkdown = useMemo(() => {
    const instruction = selectedTaskDetailQuery.data?.instructionMarkdown?.trim();
    if (instruction) return instruction;
    if (harborTask) return `# ${harborTask.title}\n\n${harborTask.description}`;
    return "";
  }, [selectedTaskDetailQuery.data?.instructionMarkdown, harborTask]);
  const liveInstructionMarkdown = normalizeTaskInstructionMarkdown(job?.instructionMarkdown ?? null);
  const centerInstructionMarkdown = liveInstructionMarkdown || setupInstructionMarkdown;

  const activeTaskPath = selectedCard?.taskPath || HARBOR_TASK_PATHS.survey;
  const instructionView = useCockpitInstruction({
    taskPath: activeTaskPath,
    fallbackMarkdown: setupInstructionMarkdown,
    fallbackTitle: harborTask?.title ?? activeQuestionnaire?.title ?? selectedCard?.title ?? null,
    harborJobName,
    harborTrialName,
    enabled: phase !== "idle",
  });

  useEffect(() => {
    if (phase === "done") {
      setExportSnapshot(
        (prev) =>
          prev ?? {
            persona: persona ? { id: persona.id, name: persona.name, source: persona.source } : null,
            taskId: selectedTaskId,
            personaModel,
          },
      );
    }
  }, [phase, persona, selectedTaskId, personaModel]);

  const launchSurveyRun = useCallback(
    (card: TaskCardModel) => {
      if (!persona || isRunning) return;
      setExportSnapshot(null);
      const task = harborTasks.find((item) => item.id === card.id) ?? null;
      const instrumentId = task?.instrumentId ?? "";
      const taskPath = card.taskPath || HARBOR_TASK_PATHS.survey;
      const instrumentTitle = task?.title ?? card.title;
      void run({
        taskPath,
        personaId: persona.id,
        personaModel,
        mode: "auto",
        mapDebrief: (debrief, ctx) =>
          mapSurveyDebriefToJobView(debrief, ctx, {
            personaId: persona.id,
            personaName: persona.name,
            instrumentId,
            instrumentTitle,
          }),
        mapLive: (live, ctx) =>
          mapSurveyLiveToJobView(live, ctx, {
            personaId: persona.id,
            personaName: persona.name,
            instrumentId,
            instrumentTitle,
          }),
      });
    },
    [persona, isRunning, run, personaModel, harborTasks],
  );

  const handleRun = useCallback(() => {
    if (!selectedCard) return;
    launchSurveyRun(selectedCard);
  }, [selectedCard, launchSurveyRun]);

  const handleLaunch = useCallback(async () => {
    if (!canLaunchCohort || !selectedCard || isRunning) {
      return;
    }
    if (isBatchRun) {
      await launchBatch({
        taskPath: selectedCard.taskPath || HARBOR_TASK_PATHS.survey,
        taskId: selectedCard.id,
      });
      return;
    }
    handleRun();
  }, [canLaunchCohort, selectedCard, isRunning, isBatchRun, launchBatch, handleRun]);

  const handleNewRun = useCallback(() => {
    reset();
    clearBatch();
    clearLaunchError();
  }, [reset, clearBatch, clearLaunchError]);

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
    if (!exportSnapshot || !surveyResult) return;
    const payload = {
      applicationType: "survey",
      config: exportSnapshot,
      surveyResult,
      exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `survey-eval-${exportSnapshot.persona?.id ?? "run"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [exportSnapshot, surveyResult]);

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
      } else if (e.key === "3") {
        e.preventDefault();
        setTab("context");
      } else if (e.key === "4") {
        e.preventDefault();
        setTab("questionnaire");
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [showInspector]);
  const activeInstrument = surveyResult?.instrument ?? activeQuestionnaire;
  const questionTotal =
    surveyResult?.completion?.numQuestions ?? activeInstrument?.questions.length ?? 0;
  const questionAnswered =
    surveyResult?.completion?.numAnswered ?? surveyResult?.answers.length ?? 0;
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
        : questionTotal > 0
          ? Math.round((questionAnswered / questionTotal) * 100)
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
      ? t("eval.survey.progress.launching")
      : phase === "running"
        ? questionTotal > 0
          ? t("eval.survey.progress.answering", { answered: questionAnswered, total: questionTotal })
          : (status ?? t("eval.survey.progress.persona"))
        : phase === "done"
          ? t("eval.survey.progress.complete", { count: questionAnswered })
          : failed
            ? error?.startsWith("Run stopped")
              ? t("eval.progress.runStopped")
              : displayError ?? t("eval.survey.progress.error")
            : undefined;
  const canExport = exportSnapshot !== null && surveyResult !== null;

  const surveyLiveContent =
    phase === "done" && !surveyResult && !runBusy ? (
      <div className="rounded-md border border-outline bg-surface-lowest p-5 text-[15px] text-text-variant">
        <p className="font-medium text-text-main">{t("eval.survey.finishedNoAnswers")}</p>
        <p className="mt-2">
          {displayError ?? t("eval.survey.finishedNoAnswersBody")}
        </p>
      </div>
    ) : phase !== "idle" || surveyResult ? (
      <SurveyLive
        instrument={activeQuestionnaire}
        result={surveyResult}
        phase={failed ? "error" : phase}
        error={displayError}
        instructionMarkdown={centerInstructionMarkdown}
        onRetry={handleRetry}
      />
    ) : null;

  const cockpitView = (
    <CockpitSetupShell
      header={<RunHeader taskType={taskType} onTaskTypeChange={onTaskTypeChange} />}
      left={
        <PersonaSamplingRail
          taskType="survey"
          taskPath={activeTaskPath || null}
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
        <CockpitRunCenter
          showLive={showLiveCenter}
          pipeline={
            <CockpitPipelineDiagram
              className="h-full"
              taskType="survey"
              personaModelLabel={pipelinePersonaModelLabel}
              hasPersona={visiblePersonaIds.length > 0}
              hasTask={Boolean(selectedCard)}
            />
          }
          liveContent={surveyLiveContent}
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
            Boolean(selectedCard) &&
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
            displayError ??
            (batchCancelled ? t("eval.progress.batchStoppedReset") : batchError) ??
            retryError
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
      }
      right={
        showInspector ? (
          <InspectorTabs
            active={tab}
            onChange={setTab}
            evaluation={
              <SurveyEvalScorecard surveyResult={surveyResult} verifier={verifier} phase={phase} />
            }
            instruction={
              <InstructionPanel
                label={t("eval.survey.instructionLabel")}
                title={instructionView.title}
                markdown={instructionView.instructionMarkdown ?? instructionView.markdown}
                loading={instructionView.loading}
                error={instructionView.error}
              />
            }
            context={
              <InstructionPanel
                label={t("eval.survey.contextLabel")}
                title={instructionView.title}
                markdown={instructionView.contextMarkdown}
                loading={instructionView.loading}
                error={instructionView.error}
                emptyMessage={t("eval.survey.contextEmpty")}
                icon="menu_book"
              />
            }
            questionnaire={
              (instructionView.questionnaire ?? activeQuestionnaire) ? (
                <div className="custom-scrollbar max-h-full overflow-y-auto p-4">
                  <QuestionnairePreview
                    instrument={(instructionView.questionnaire ?? activeQuestionnaire)!}
                  />
                </div>
              ) : (
                <InstructionPanel
                  label={t("eval.survey.questionnaireLabel")}
                  title={instructionView.title}
                  markdown={null}
                  loading={instructionView.loading}
                  error={instructionView.error}
                  emptyMessage={t("eval.survey.questionnaireEmpty")}
                  icon="list_alt"
                />
              )
            }
          />
        ) : (
        <TaskSelectionRail
          taskType="survey"
          chatTasks={[]}
          surveyTasks={taskCards}
          webTasks={[]}
          cuaTasks={[]}
          selectedTaskId={activeTaskId}
          onSelectTask={(card) => setSelectedTaskId(card.id)}
          engine=""
          onEngineChange={() => undefined}
          engineOptions={[]}
          maxTurns={8}
          onMaxTurnsChange={() => undefined}
          tasksLoading={harborTasksQuery.isLoading}
          tasksError={
            harborTasksQuery.isError && taskCards.length === 0
              ? t("eval.survey.tasksLoadFailed")
              : harborTasksQuery.isError
                ? t("eval.survey.tasksCatalogFallback")
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


/** The Survey live / results column (modelled on `data-view="surveylive"`). */
function SurveyLive({
  instrument,
  result,
  phase,
  error,
  instructionMarkdown,
  onRetry,
}: {
  instrument: SurveyInstrument | null;
  result: SurveyResult | null;
  phase: HarborCockpitPhase;
  error: string | null;
  instructionMarkdown?: string;
  onRetry: () => void;
}) {
  const { t } = useI18n();
  const running = phase === "launching" || phase === "running";
  const failed = phase === "error" || phase === "timeout";
  const activeInstrument = result?.instrument ?? instrument;
  const completion = result?.completion ?? null;
  const total = completion?.numQuestions ?? activeInstrument?.questions.length ?? 0;
  const answered = completion?.numAnswered ?? result?.answers.length ?? 0;

  return (
    <section className="space-y-4">
      {/* Header */}
      <div className="min-w-0">
        <div className="hud mb-2 break-words text-[12px] text-primary">
          {t("eval.survey.header", {
            name: humanizeToken(activeInstrument?.id ?? activeInstrument?.title ?? "questionnaire"),
          })}
        </div>
        <h2 className="font-display text-[22px] font-bold tracking-tight text-text-main">
          {running
            ? t("eval.survey.answering")
            : failed
              ? t("eval.survey.failed")
              : t("eval.survey.completed")}
        </h2>
      </div>

      {/* Answer cards */}
      {failed && (
        <ErrorCard
          title={t("eval.survey.failed")}
          body={error ?? t("eval.survey.errorBody")}
          onRetry={onRetry}
          retryLabel={t("eval.common.tryAgain")}
        />
      )}

      {/* Answer cards */}
      {result && activeInstrument ? (
        <div className="space-y-4">
          {result.answers.map((answer, index) => (
            <SurveyAnswerCard
              key={answer.questionId}
              index={index}
              answer={answer}
              question={activeInstrument.questions.find((q) => q.id === answer.questionId) ?? null}
            />
          ))}
        </div>
      ) : running ? (
        instructionMarkdown?.trim() ? (
          <div className="custom-scrollbar max-h-[480px] overflow-y-auto rounded-md border border-outline bg-surface-lowest p-4 text-[15px] text-text-main">
            <Markdown>{instructionMarkdown}</Markdown>
          </div>
        ) : (
        <div className="space-y-4" aria-hidden>
          <div className="h-36 animate-rb-pulse rounded-md bg-surface-high" />
          <div className="h-36 animate-rb-pulse rounded-md bg-surface-high" />
        </div>
        )
      ) : null}

      {/* Footer + trajectory */}
      {result && (
        <>
          <div className="flex items-center justify-center gap-2 pt-1">
            <span className="hud text-[11px] text-text-dim">{t("eval.survey.answered", { answered, total })}</span>
            {total - answered > 0 && (
              <>
                <span className="text-outline-dim">·</span>
                <span className="hud text-[11px] text-text-dim">{t("eval.survey.remaining", { count: total - answered })}</span>
              </>
            )}
          </div>
          {result.trajectory.length > 0 && <TrajectoryFold events={result.trajectory} />}
        </>
      )}
    </section>
  );
}

/** One answered question, rendered by type (likert / single / multi / free-text). */
function SurveyAnswerCard({
  index,
  answer,
  question,
}: {
  index: number;
  answer: SurveyAnswer;
  question: SurveyQuestion | null;
}) {
  const { t } = useI18n();
  const meta = questionTypeMeta(question?.type ?? "", t);
  const confidence = answer.confidence;
  return (
    <div
      className="rise-in rounded-md border border-outline bg-surface p-5"
      style={{ animationDelay: `${Math.min(index, 6) * 30}ms` }}
    >
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="hud text-[12px] text-text-dim">{t("eval.survey.questionNumber", { number: index + 1 })}</span>
          <span title={meta.tooltip} className={`hud rounded border px-1.5 py-0.5 text-[11px] ${meta.tone}`}>
            {meta.label}
          </span>
        </div>
        <Sym name="check_circle" fill={1} size={16} className="text-secondary" />
      </div>
      <p className="mb-4 text-[15px] leading-relaxed text-text-main">{question?.prompt ?? answer.questionId}</p>

      <AnswerValue answer={answer} question={question} />

      {(answer.rationale || confidence != null) && (
        <div className="mt-5 border-t border-outline pt-3.5">
          <p className="font-mono text-[13px] leading-relaxed text-text-variant">
            {answer.rationale
              ? t("eval.survey.rationale", { rationale: answer.rationale })
              : t("eval.survey.answeredByPersona")}{" "}
            {confidence != null && (
              <span className="text-text-variant">{t("eval.survey.confidence", { value: confidence.toFixed(2) })}</span>
            )}
          </p>
        </div>
      )}
    </div>
  );
}

function AnswerValue({ answer, question }: { answer: SurveyAnswer; question: SurveyQuestion | null }) {
  const { t } = useI18n();
  const type = question?.type;

  if (type === "likert") {
    const chosen = Number(answer.value);
    const min = question?.minValue ?? 1;
    const max = question?.maxValue ?? 5;
    if (Number.isFinite(chosen) && max >= min && max - min <= 12) {
      const scale = Array.from({ length: max - min + 1 }, (_, i) => min + i);
      const lowLabel = question?.options?.[0];
      const highLabel = question?.options && question.options.length > 1 ? question.options[question.options.length - 1] : undefined;
      return (
        <div>
          <div className="flex items-center justify-between gap-2">
            {scale.map((n) => (
              <span
                key={n}
                className={`grid h-11 w-11 shrink-0 place-items-center rounded-full border font-mono text-[15px] ${
                  n === chosen
                    ? "border-primary bg-primary font-bold text-on-primary"
                    : "border-outline text-text-variant"
                }`}
              >
                {n}
              </span>
            ))}
          </div>
          {(lowLabel || highLabel) && (
            <div className="mt-2.5 flex items-center justify-between">
              <span className="hud text-[11px] text-text-dim">{lowLabel}</span>
              <span className="hud text-[11px] text-text-dim">{highLabel}</span>
            </div>
          )}
        </div>
      );
    }
  }

  if ((type === "single_choice" || type === "multi_choice") && question && question.options.length > 0) {
    const multi = type === "multi_choice";
    const selected = Array.isArray(answer.value)
      ? answer.value.map((v) => String(v))
      : [String(answer.value)];
    const optionDetails =
      question.optionDetails && question.optionDetails.length > 0
        ? question.optionDetails
        : question.options.map((option) => ({ id: option, label: option, description: "" }));
    return (
      <div className="space-y-2">
        {multi && (
          <p className="hud text-[11px] text-text-dim">{t("eval.survey.multiChoiceSelected", { count: selected.length })}</p>
        )}
        {optionDetails.map((option) => {
          const isSelected = selected.includes(option.id);
          return (
            <div
              key={option.id}
              className={`flex items-center gap-3 rounded border px-3.5 py-2.5 ${
                isSelected ? "border-primary bg-primary/10" : "border-outline bg-surface-low"
              }`}
            >
              {multi ? (
                <span
                  className={`grid h-4 w-4 shrink-0 place-items-center rounded-sm border ${
                    isSelected ? "border-primary bg-primary" : "border-outline"
                  }`}
                >
                  {isSelected && <Sym name="check" size={12} className="text-on-primary" />}
                </span>
              ) : (
                <span
                  className={`grid h-4 w-4 shrink-0 place-items-center rounded-full border ${
                    isSelected ? "border-2 border-primary" : "border-outline"
                  }`}
                >
                  {isSelected && <span className="h-1.5 w-1.5 rounded-full bg-primary" />}
                </span>
              )}
              <div className="min-w-0">
                <span className={`block text-[14px] ${isSelected ? "font-medium text-text-main" : "text-text-variant"}`}>
                  {option.label || option.id}
                </span>
                {option.label && option.label !== option.id ? (
                  <span className="mt-0.5 block font-mono text-[12px] text-text-dim">{option.id}</span>
                ) : null}
                {option.description ? (
                  <span className="mt-0.5 block text-[12px] leading-relaxed text-text-dim">
                    {option.description}
                  </span>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  if (type === "free_text") {
    return (
      <div className="rounded border border-outline bg-field p-4">
        <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-text-variant">
          {formatSurveyValue(answer.value) || t("eval.survey.noResponse")}
        </p>
      </div>
    );
  }

  // Fallback for unknown types / missing question metadata.
  return (
    <div className="rounded border border-outline bg-field px-3 py-2.5">
      <p className="font-mono text-[14px] text-text-main">{formatSurveyValue(answer.value) || t("eval.survey.noAnswer")}</p>
    </div>
  );
}

/** Collapsible Q&A trajectory timeline. */
function TrajectoryFold({ events }: { events: SurveyTrajectoryEvent[] }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const groups = groupSurveyTrajectory(events);
  return (
    <section className="panel overflow-hidden rounded-md border border-outline bg-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={`flex w-full items-center justify-between gap-2 border-b border-outline px-4 py-3 text-left transition-colors hover:bg-surface-low active:bg-surface-high ${FOCUS_RING}`}
      >
        <span className="hud text-[12px] text-text-dim">{t("eval.survey.trajectory")}</span>
        <span className="flex items-center gap-2">
          <span className="hud text-[11px] text-text-dim">{t("eval.survey.steps", { count: groups.length })}</span>
          <Sym name={open ? "expand_more" : "chevron_right"} size={18} className="text-text-dim" />
        </span>
      </button>
      {open && (
        <div className="rise-in custom-scrollbar max-h-96 space-y-2.5 overflow-auto p-3">
          {groups.map((group, index) => {
            if (group.kind === "qa") {
              const qIndex =
                surveyTrajectoryQuestionIndex(group.ask) ??
                surveyTrajectoryQuestionIndex(group.answer);
              const type =
                surveyTrajectoryQuestionType(group.ask) ||
                surveyTrajectoryQuestionType(group.answer);
              const prompt = surveyTrajectoryPrompt(group.ask);
              const value = formatSurveyTrajectoryValue(
                group.answer.outcome?.value,
                t,
              );
              return (
                <div
                  key={`${group.ask.timestamp}-${index}`}
                  className="rounded-md border border-outline bg-surface-lowest px-3 py-2.5"
                >
                  <div className="mb-1 flex items-center gap-2">
                    <span className="hud text-[11px] text-primary">
                      {qIndex != null
                        ? t("eval.survey.questionNumber", { number: qIndex })
                        : t("eval.survey.questionShort")}
                    </span>
                    {type ? (
                      <span className={`hud rounded border px-1.5 py-0.5 text-[11px] ${surveyQuestionTypeChipClass(type)}`}>
                        {surveyQuestionTypeLabel(type, t)}
                      </span>
                    ) : null}
                  </div>
                  {prompt ? (
                    <p className="text-[14px] leading-snug text-text-variant">{prompt}</p>
                  ) : null}
                  <p className="mt-1.5 rounded border border-outline bg-field px-2.5 py-1.5 font-mono text-[13px] text-text-main break-words">
                    {value || t("eval.survey.noAnswer")}
                  </p>
                </div>
              );
            }

            const event = group.event;
            const action = event.action;
            let title = t("eval.survey.trajectoryAction", {
              actor: trajectoryActor(event.actor, t),
              action: event.action,
            });
            let detail = "";
            if (action === "survey_started") {
              title = t("eval.survey.started");
              const n = event.context?.numQuestions;
              detail = typeof n === "number" ? t("eval.survey.questions", { count: n }) : "";
            } else if (action === "survey_completed") {
              title = t("eval.survey.completed");
              const answered = event.outcome?.numAnswered;
              detail = typeof answered === "number" ? t("eval.survey.answers", { count: answered }) : "";
            }
            return (
              <div
                key={`${event.timestamp}-${index}`}
                className="rounded-md border border-outline/70 bg-surface-low px-3 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[14px] font-medium text-text-main">{title}</span>
                  <span className="shrink-0 font-mono text-[12px] text-text-dim">{event.timestamp}</span>
                </div>
                {detail ? <p className="mt-0.5 text-[13px] text-text-variant">{detail}</p> : null}
              </div>
            );
          })}
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
            {retryLabel ?? t("eval.common.tryAgain")}
          </button>
        </div>
      </div>
    </section>
  );
}
