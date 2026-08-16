import type { MessageKey } from "@/i18n/types";
import type {
  CockpitRunError,
  CockpitRunErrorCode,
} from "@/lib/harborCockpitMappers";

type CockpitRunErrorMessageKey =
  | "eval.errors.trialFailed"
  | "eval.errors.batchRunFailed"
  | "eval.errors.runTimeout"
  | "eval.errors.runStoppedReset"
  | "eval.errors.emptyConversation"
  | "eval.errors.missingTrial"
  | "eval.errors.trialOutputArtifactsMissing"
  | "eval.errors.trialNotFound"
  | "eval.errors.rewardFileMissing";

const COCKPIT_RUN_ERROR_MESSAGE_KEYS: Record<
  CockpitRunErrorCode,
  CockpitRunErrorMessageKey
> = {
  trial_failed: "eval.errors.trialFailed",
  batch_run_failed: "eval.errors.batchRunFailed",
  run_timeout: "eval.errors.runTimeout",
  run_stopped_reset: "eval.errors.runStoppedReset",
  empty_conversation: "eval.errors.emptyConversation",
  missing_trial: "eval.errors.missingTrial",
  trial_output_artifacts_missing: "eval.errors.trialOutputArtifactsMissing",
  trial_not_found: "eval.errors.trialNotFound",
  reward_file_missing: "eval.errors.rewardFileMissing",
};

/** Render stable local error codes with the active UI locale; leave raw backend text unchanged. */
export function localizeCockpitRunError(
  error: CockpitRunError | null,
  t: (key: MessageKey) => string,
): string | null {
  if (!error) return null;
  return error.code
    ? t(COCKPIT_RUN_ERROR_MESSAGE_KEYS[error.code])
    : error.rawMessage;
}
