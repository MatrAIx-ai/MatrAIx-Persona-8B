/** Coarse Harbor trial lifecycle stages shown in batch grids. */
import type { I18nContextValue } from "@/i18n/I18nProvider";

type Translate = I18nContextValue["t"];

export type TrialLifecycleStage =
  "queued" | "starting_env" | "agent_running" | "verifying";

const STAGE_LABELS: Record<TrialLifecycleStage, string> = {
  queued: "Queued",
  starting_env: "Starting env",
  agent_running: "Agent running",
  verifying: "Verifying",
};

function stageLabel(stage: TrialLifecycleStage, t?: Translate): string {
  switch (stage) {
    case "queued":
      return t ? t("runs.status.queued") : STAGE_LABELS.queued;
    case "starting_env":
      return t ? t("runs.status.startingEnv") : STAGE_LABELS.starting_env;
    case "agent_running":
      return t ? t("runs.status.agentRunning") : STAGE_LABELS.agent_running;
    case "verifying":
      return t ? t("runs.status.verifying") : STAGE_LABELS.verifying;
  }
}

const PHASE_TO_STAGE: Record<string, TrialLifecycleStage> = {
  harbor_starting: "starting_env",
  harbor_running: "agent_running",
  trial_running: "agent_running",
  // Legacy event phase names (pre-Harbor unify). Per Xiaoming & Yuexing: no external
  // BenchFlow branding in user-facing copy — prefer neutral stages or MatrAIx/Harbor terms.
  benchflow_starting: "starting_env",
  persona_kickoff: "agent_running",
  recommender_thinking: "agent_running",
  persona_thinking: "agent_running",
  web_simulating: "agent_running",
  survey_answering: "agent_running",
  appworld_simulating: "agent_running",
  benchflow_running: "agent_running",
  harbor_collecting_artifacts: "verifying",
  benchflow_collecting: "verifying",
  persona_feedback: "verifying",
};

export function formatTrialStageLabel(
  stage?: string | null,
  phase?: string | null,
  t?: Translate,
): string | null {
  if (stage && stage in STAGE_LABELS) {
    return stageLabel(stage as TrialLifecycleStage, t);
  }
  const mapped = phase ? PHASE_TO_STAGE[phase] : undefined;
  if (mapped) return stageLabel(mapped, t);
  if (phase) return phase.replace(/^harbor_/, "").replace(/_/g, " ");
  return null;
}

export function formatBatchCellStatusLabel(
  status: "pending" | "running" | "done" | "error",
  stage?: string | null,
  phase?: string | null,
  t?: Translate,
): string {
  if (status === "pending") return t ? t("runs.status.queued") : "Queued";
  if (status === "done") return t ? t("runs.status.done") : "Done";
  if (status === "error") return t ? t("runs.status.failed") : "Failed";
  return (
    formatTrialStageLabel(stage, phase, t) ??
    (t ? t("runs.status.running") : "Running")
  );
}

/** Resolve a Harbor job list row status (API field with jobResult fallback). */
export function deriveHarborJobListStatus(job: {
  status?: string | null;
  trialCount?: number;
  completedTrials?: number;
  jobResult?: Record<string, unknown> | null;
}): "running" | "success" | "failed" {
  const explicit = (job.status ?? "").toLowerCase();
  if (
    explicit === "success" ||
    explicit === "failed" ||
    explicit === "running"
  ) {
    return explicit;
  }

  const result = job.jobResult;
  if (result && typeof result === "object" && result.finished_at) {
    const stats = result.stats as { n_errored_trials?: number } | undefined;
    const errors = Number(stats?.n_errored_trials ?? 0);
    return errors > 0 ? "failed" : "success";
  }

  const trialCount = job.trialCount ?? 0;
  const completed = job.completedTrials ?? 0;
  // Without an explicit backend status or a job-level result, treat a fully
  // completed cohort as success and anything else as terminal rather than
  // reporting a stale, never-ending "running".
  if (trialCount > 0 && completed >= trialCount) return "success";
  return "failed";
}

const HARBOR_JOB_STATUS_LABEL: Record<
  "running" | "success" | "failed",
  string
> = {
  running: "Running",
  success: "Success",
  failed: "Failed",
};

export function harborJobListStatusLabel(
  status: "running" | "success" | "failed",
  t?: Translate,
): string {
  switch (status) {
    case "running":
      return t ? t("runs.status.running") : HARBOR_JOB_STATUS_LABEL.running;
    case "success":
      return t ? t("runs.status.success") : HARBOR_JOB_STATUS_LABEL.success;
    case "failed":
      return t ? t("runs.status.failed") : HARBOR_JOB_STATUS_LABEL.failed;
  }
}
