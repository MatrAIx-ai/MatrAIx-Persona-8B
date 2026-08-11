import {
  hasMeaningfulTaskContext,
  normalizeOutputSchemaMarkdown,
  normalizeQuestionnaireMarkdown,
  normalizeSelfReportMarkdown,
  normalizeTaskInstructionMarkdown,
} from "@/lib/taskContent";
import type { DisplayTranslate } from "../cockpitShared";
import { taskDocumentLabel } from "./taskCardLabels";

export type TaskDocTabId =
  | "instruction"
  | "context"
  | "questionnaire"
  | "output-schema"
  | "self-report";

export type TaskDocSection = {
  id: TaskDocTabId;
  label: string;
  icon: string;
  markdown: string;
};

export type TaskDocSource = {
  instructionMarkdown?: string | null;
  contextMarkdown?: string | null;
  questionnaireMarkdown?: string | null;
  outputSchemaMarkdown?: string | null;
  /** Task-owned ``input/self_report_schema.yaml`` only (no platform default). */
  selfReportMarkdown?: string | null;
  /** When true, keep a Questionnaire tab even without markdown (structured preview). */
  hasStructuredQuestionnaire?: boolean;
};

/** Contributor-facing task docs for preview. */
export function buildTaskDocSections(source: TaskDocSource, t?: DisplayTranslate): TaskDocSection[] {
  const sections: TaskDocSection[] = [];

  const instruction = normalizeTaskInstructionMarkdown(source.instructionMarkdown);
  if (instruction) {
    sections.push({
      id: "instruction",
      label: taskDocumentLabel("instruction", t),
      icon: "description",
      markdown: instruction,
    });
  }

  const context = (source.contextMarkdown ?? "").trim();
  if (hasMeaningfulTaskContext(context)) {
    sections.push({
      id: "context",
      label: taskDocumentLabel("context", t),
      icon: "menu_book",
      markdown: context,
    });
  }

  const questionnaire = normalizeQuestionnaireMarkdown(source.questionnaireMarkdown);
  if (questionnaire || source.hasStructuredQuestionnaire) {
    sections.push({
      id: "questionnaire",
      label: taskDocumentLabel("questionnaire", t),
      icon: "list_alt",
      // Structured preview replaces this markdown in TaskDetailModal when instrument is present.
      markdown: questionnaire || "_Structured questionnaire_",
    });
  }

  const outputSchema = normalizeOutputSchemaMarkdown(source.outputSchemaMarkdown);
  if (outputSchema) {
    sections.push({
      id: "output-schema",
      label: taskDocumentLabel("output-schema", t),
      icon: "schema",
      markdown: outputSchema,
    });
  }

  const selfReport = normalizeSelfReportMarkdown(source.selfReportMarkdown);
  if (selfReport) {
    sections.push({
      id: "self-report",
      label: taskDocumentLabel("self-report", t),
      icon: "rate_review",
      markdown: selfReport,
    });
  }

  return sections;
}
