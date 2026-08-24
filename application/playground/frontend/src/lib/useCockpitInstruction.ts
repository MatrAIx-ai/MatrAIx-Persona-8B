import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { useI18n } from "@/i18n/I18nProvider";
import { api, ApiError } from "./api";
import {
  hasMeaningfulTaskContext,
  normalizeOutputSchemaMarkdown,
  normalizeQuestionnaireMarkdown,
  normalizeTaskInstructionMarkdown,
} from "./taskContent";

export interface UseCockpitInstructionInput {
  taskPath?: string | null;
  /** Built-in fallback (e.g. survey instrument markdown) when no Harbor task doc exists. */
  fallbackMarkdown?: string | null;
  fallbackTitle?: string | null;
  harborJobName?: string | null;
  harborTrialName?: string | null;
  enabled?: boolean;
}

export function useCockpitInstruction({
  taskPath,
  fallbackMarkdown,
  fallbackTitle,
  harborJobName,
  harborTrialName,
  enabled = true,
}: UseCockpitInstructionInput) {
  const { t } = useI18n();
  const normalizedPath = taskPath?.trim() ?? "";
  const hasTrial = Boolean(harborJobName && harborTrialName);

  const trialQuery = useQuery({
    queryKey: ["harbor-trial-instruction", harborJobName, harborTrialName],
    queryFn: () => api.getHarborTrialInstruction(harborJobName!, harborTrialName!),
    enabled: enabled && hasTrial,
    staleTime: 300_000,
    retry: 1,
  });

  const taskQuery = useQuery({
    queryKey: ["task-detail", normalizedPath],
    queryFn: () => api.getTaskDetail(normalizedPath),
    enabled: enabled && Boolean(normalizedPath) && !trialQuery.data?.markdown,
    staleTime: 300_000,
    retry: 1,
  });

  const markdown = useMemo(() => {
    const trialMd = trialQuery.data?.instructionMarkdown?.trim() || trialQuery.data?.markdown?.trim();
    if (trialMd) return normalizeTaskInstructionMarkdown(trialMd);
    const taskMd = taskQuery.data?.instructionMarkdown?.trim();
    if (taskMd) return normalizeTaskInstructionMarkdown(taskMd);
    return normalizeTaskInstructionMarkdown(fallbackMarkdown ?? "");
  }, [
    trialQuery.data?.instructionMarkdown,
    trialQuery.data?.markdown,
    taskQuery.data?.instructionMarkdown,
    fallbackMarkdown,
  ]);

  const instructionMarkdown = useMemo(() => {
    const trialMd = trialQuery.data?.instructionMarkdown?.trim();
    if (trialMd) return normalizeTaskInstructionMarkdown(trialMd);
    const taskMd = taskQuery.data?.instructionMarkdown?.trim();
    if (taskMd) return normalizeTaskInstructionMarkdown(taskMd);
    return null;
  }, [trialQuery.data?.instructionMarkdown, taskQuery.data?.instructionMarkdown]);

  const contextMarkdown = useMemo(() => {
    const trialMd = trialQuery.data?.contextMarkdown?.trim() ?? "";
    if (hasMeaningfulTaskContext(trialMd)) return trialMd;
    const taskMd = taskQuery.data?.contextMarkdown?.trim() ?? "";
    if (hasMeaningfulTaskContext(taskMd)) return taskMd;
    return null;
  }, [trialQuery.data?.contextMarkdown, taskQuery.data?.contextMarkdown]);

  const questionnaireMarkdown = useMemo(() => {
    const trialMd = trialQuery.data?.questionnaireMarkdown?.trim();
    if (trialMd) return normalizeQuestionnaireMarkdown(trialMd);
    const taskMd = taskQuery.data?.questionnaireMarkdown?.trim();
    if (taskMd) return normalizeQuestionnaireMarkdown(taskMd);
    return null;
  }, [trialQuery.data?.questionnaireMarkdown, taskQuery.data?.questionnaireMarkdown]);

  const outputSchemaMarkdown = useMemo(() => {
    const trialMd = trialQuery.data?.outputSchemaMarkdown?.trim();
    if (trialMd) return normalizeOutputSchemaMarkdown(trialMd);
    const taskMd = taskQuery.data?.outputSchemaMarkdown?.trim();
    if (taskMd) return normalizeOutputSchemaMarkdown(taskMd);
    return null;
  }, [trialQuery.data?.outputSchemaMarkdown, taskQuery.data?.outputSchemaMarkdown]);

  const selfReportMarkdown = useMemo(() => {
    const trialMd = trialQuery.data?.selfReportMarkdown?.trim();
    if (trialMd) return normalizeOutputSchemaMarkdown(trialMd);
    const taskMd = taskQuery.data?.selfReportMarkdown?.trim();
    if (taskMd) return normalizeOutputSchemaMarkdown(taskMd);
    return null;
  }, [trialQuery.data?.selfReportMarkdown, taskQuery.data?.selfReportMarkdown]);

  const questionnaire = taskQuery.data?.questionnaire ?? null;

  const title =
    trialQuery.data?.title ??
    taskQuery.data?.title ??
    fallbackTitle ??
    null;

  const loading =
    (hasTrial && trialQuery.isLoading) ||
    (Boolean(normalizedPath) && !trialQuery.data?.markdown && taskQuery.isLoading);

  const error = useMemo(() => {
    if (markdown) return null;
    if (trialQuery.isError) {
      return trialQuery.error instanceof ApiError
        ? trialQuery.error.message
        : t("cockpit.instruction.trialLoadFailed");
    }
    if (taskQuery.isError) {
      return taskQuery.error instanceof ApiError
        ? taskQuery.error.message
        : t("cockpit.instruction.taskLoadFailed");
    }
    return null;
  }, [markdown, trialQuery.isError, trialQuery.error, taskQuery.isError, taskQuery.error, t]);

  return {
    markdown: markdown || null,
    title,
    loading,
    error,
    instructionMarkdown,
    contextMarkdown,
    questionnaireMarkdown,
    outputSchemaMarkdown,
    selfReportMarkdown,
    questionnaire,
  };
}
