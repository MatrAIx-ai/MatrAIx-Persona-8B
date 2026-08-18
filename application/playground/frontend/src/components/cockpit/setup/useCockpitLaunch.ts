import { useCallback, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";
import type { HarborCockpitTaskKind } from "@/lib/harborCockpitMappers";
import { withLaunchLanguage } from "@/lib/personaLanguage";
import type { ConfigOptionsResponse } from "@/lib/types";

import { buildPersonaLaunchFields, hasLaunchableCohort } from "./personaLaunchFields";
import { useCockpitBatchJob } from "./useCockpitBatchJob";
import { useSetupPersonaSampling } from "./useSetupPersonaSampling";

type HarborLaunchBody = Parameters<typeof api.launchHarborJob>[0];

/**
 * Cockpit-specific launch extras. Everything a cockpit may add on top of the
 * shared launch assembly; typed straight off the API client so the two can
 * never drift.
 */
export type CockpitLaunchOverrides = Pick<
  HarborLaunchBody,
  | "mode"
  | "agentName"
  | "chatDomain"
  | "chatApplicationId"
  | "chatApplicationContext"
  | "chatMaxTurns"
  | "osAppSubmissionProfile"
  | "osAppBackend"
>;

/**
 * Shared launch assembly for the cockpits (#47).
 *
 * Owns everything every cockpit repeated by hand: the sampling + batch hook
 * pair, the launch-error state, the launchable-cohort guard, and the batch
 * launch call (persona fields, common body, batch record with the launch-time
 * persona pool). Cockpit-specific launch fields go through `overrides`;
 * debrief/live mappers and single-run wiring stay in the cockpits, which own
 * their result shapes.
 */
export function useCockpitLaunch(
  options: ConfigOptionsResponse | null,
  taskKind: HarborCockpitTaskKind,
  taskPath: string | null = null,
  isActive = true,
) {
  const { locale } = useI18n();
  const sampling = useSetupPersonaSampling(options, taskKind, taskPath, isActive);
  const batch = useCockpitBatchJob(
    sampling.selectedPersonaIds,
    sampling.parallelTrials,
    taskKind,
    sampling.selectedCount,
    sampling.personaPool,
  );
  const [launchError, setLaunchError] = useState<string | null>(null);

  const canLaunchCohort = hasLaunchableCohort({
    selectedPersonaIds: sampling.selectedPersonaIds,
    selectedCount: sampling.selectedCount,
    useEntirePool: sampling.useEntirePool,
  });

  const {
    personaPool,
    selectedPersonaIds,
    selectedCount,
    useEntirePool,
    parallelTrials,
    seed,
    personaModel,
  } = sampling;
  const { setBatchJobName } = batch;

  /**
   * Launch a batch job for `taskPath` and record it against `taskId`.
   * Resolves to true on success; on failure the message lands in
   * `launchError` and the call resolves to false.
   */
  const launchBatch = useCallback(
    async (input: {
      taskPath: string;
      taskId: string;
      overrides?: CockpitLaunchOverrides;
    }): Promise<boolean> => {
      setLaunchError(null);
      try {
        const personaFields = buildPersonaLaunchFields({
          personaPool,
          selectedPersonaIds,
          selectedCount,
          useEntirePool,
          parallelTrials,
        });
        const launched = await api.launchHarborJob(
          withLaunchLanguage(
            {
              taskPath: input.taskPath,
              seed,
              personaModel,
              ...personaFields,
              mode: "auto",
              ...input.overrides,
            },
            locale,
          ),
        );
        setBatchJobName(launched.jobName, { taskId: input.taskId, personaPool });
        return true;
      } catch (exc) {
        const message =
          exc instanceof ApiError ? exc.message : exc instanceof Error ? exc.message : String(exc);
        setLaunchError(message);
        return false;
      }
    },
    [
      personaPool,
      selectedPersonaIds,
      selectedCount,
      useEntirePool,
      parallelTrials,
      seed,
      personaModel,
      locale,
      setBatchJobName,
    ],
  );

  const clearLaunchError = useCallback(() => setLaunchError(null), []);

  return {
    sampling,
    batch,
    launchError,
    setLaunchError,
    clearLaunchError,
    canLaunchCohort,
    launchBatch,
  };
}
