import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { Markdown } from "@/components/Markdown";
import { QuestionnairePreview } from "@/components/QuestionnairePreview";
import { useI18n } from "@/i18n/I18nProvider";
import { api, ApiError } from "@/lib/api";
import type { SurveyInstrument } from "@/lib/types";
import { FOCUS_RING, Sym } from "../cockpitShared";
import { RailInsetModal } from "./RailInsetModal";
import type { TaskCardModel } from "./TaskSelectionRail";
import { ToneChip, transportChipTone } from "./ToneChip";
import {
  CHIP_TEXT_CLASS,
  formatChipLabel,
  taskDisplayTitle,
  taskDocumentLabel,
} from "./taskCardLabels";
import { buildTaskDocSections, type TaskDocSection, type TaskDocTabId } from "./taskDetailSections";

function transportLabel(
  transport: TaskCardModel["transport"] | undefined,
  translate: (key: string, fallback?: string) => string,
): string {
  if (transport === "api_sidecar") return translate("setup.tasks.apiSidecar", "API (sidecar)");
  if (transport === "api_external") return translate("setup.tasks.apiEndpoint", "API (endpoint)");
  if (transport === "mcp_sidecar") return translate("setup.tasks.mcpSidecar", "MCP (sidecar)");
  if (transport === "mcp_external") return translate("setup.tasks.mcpEndpoint", "MCP (endpoint)");
  return "—";
}

function TaskDocTabBar({
  sections,
  active,
  onChange,
}: {
  sections: TaskDocSection[];
  active: TaskDocTabId;
  onChange: (tab: TaskDocTabId) => void;
}) {
  const { t } = useI18n();
  if (sections.length <= 1) return null;

  return (
    <div
      role="tablist"
      aria-label={t("setup.tasks.documents", "Task documents")}
      className="flex flex-wrap items-center gap-x-1 gap-y-1 border-b border-outline/40"
    >
      {sections.map((section) => {
        const selected = section.id === active;
        return (
          <button
            key={section.id}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(section.id)}
            className={`-mb-px flex items-center gap-1 border-b-2 px-2 py-2 text-[12px] font-medium transition ${FOCUS_RING} ${
              selected
                ? "border-primary text-primary"
                : "border-transparent text-text-variant hover:text-text-main"
            }`}
          >
            <Sym name={section.icon} fill={selected ? 1 : 0} size={14} />
            {taskDocumentLabel(section.id, t)}
          </button>
        );
      })}
    </div>
  );
}

export interface TaskDetailModalProps {
  open: boolean;
  card: TaskCardModel | null;
  onClose: () => void;
  /** Optional primary CTA (e.g. Open in Playground from Task Gallery). */
  primaryAction?: { label: string; onClick: () => void };
}

export function TaskDetailModal({ open, card, onClose, primaryAction }: TaskDetailModalProps) {
  const { t } = useI18n();
  const taskPath = card?.taskPath?.trim() ?? "";

  const detailQuery = useQuery({
    queryKey: ["task-detail", taskPath],
    queryFn: () => api.getTaskDetail(taskPath),
    enabled: open && Boolean(taskPath),
    staleTime: 300_000,
    retry: 1,
  });

  const sections = useMemo(
    () =>
      buildTaskDocSections({
        instructionMarkdown: detailQuery.data?.instructionMarkdown ?? card?.instructionMarkdown,
        contextMarkdown: detailQuery.data?.contextMarkdown,
        questionnaireMarkdown: detailQuery.data?.questionnaireMarkdown,
        // Surveys: never surface platform-derived output schema in the task modal.
        outputSchemaMarkdown:
          detailQuery.data?.metaType === "survey" ? null : detailQuery.data?.outputSchemaMarkdown,
        selfReportMarkdown: detailQuery.data?.selfReportMarkdown,
        hasStructuredQuestionnaire: Boolean(detailQuery.data?.questionnaire?.questions?.length),
      }),
    [card?.instructionMarkdown, detailQuery.data],
  );

  const structuredQuestionnaire: SurveyInstrument | null =
    detailQuery.data?.questionnaire?.questions?.length
      ? detailQuery.data.questionnaire
      : null;

  const [activeTab, setActiveTab] = useState<TaskDocTabId>("instruction");

  useEffect(() => {
    if (!open || sections.length === 0) return;
    setActiveTab((current) =>
      sections.some((section) => section.id === current) ? current : sections[0].id,
    );
  }, [open, card?.id, sections]);

  const activeSection = sections.find((section) => section.id === activeTab) ?? sections[0] ?? null;
  const loading = Boolean(taskPath) && detailQuery.isLoading && sections.length === 0;
  const failed = Boolean(taskPath) && detailQuery.isError && sections.length === 0;
  const displayTitle = taskDisplayTitle(detailQuery.data?.title ?? card?.title, card ?? {}, t);

  return (
    <RailInsetModal
      open={open && Boolean(card)}
      title={displayTitle || t("setup.tasks.title", "Task")}
      subtitle={card?.taskType
        ? t("setup.tasks.typeDocuments", "{type} task documents", {
            type: formatChipLabel(card.taskType, t),
          })
        : t("setup.tasks.documents", "Task documents")}
      onClose={onClose}
    >
      {card && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-1.5">
            {card.transport && (
              <ToneChip tone={transportChipTone(card.transport)} className={CHIP_TEXT_CLASS}>
                {transportLabel(card.transport, t)}
              </ToneChip>
            )}
            {(card.tags ??
              (card.tagLabels?.map((label) => ({ label, tone: "neutral" as const })) ??
                [])).map((tag) => (
              <ToneChip
                key={tag.label}
                tone={tag.tone}
                showDot={tag.label === "Available" || tag.label === "Unavailable"}
                className={CHIP_TEXT_CLASS}
              >
                {formatChipLabel(tag.label, t)}
              </ToneChip>
            ))}
          </div>

          {!taskPath && (
            <p className="text-[14px] text-danger">{t("setup.tasks.noTaskPath", "This task has no task path — no instruction document to show.")}</p>
          )}
          {loading && <p className="text-[14px] text-text-dim">{t("setup.tasks.loadingDocuments", "Loading task documents…")}</p>}
          {failed && (
            <p className="text-[14px] text-danger">
              {detailQuery.error instanceof ApiError
                ? detailQuery.error.message
                : t("setup.tasks.loadDocumentsFailed", "Could not load task documents.")}
            </p>
          )}

          {sections.length > 0 ? (
            <>
              <TaskDocTabBar sections={sections} active={activeTab} onChange={setActiveTab} />
              {activeSection ? (
                <div role="tabpanel" className="pt-1">
                  {activeSection.id === "questionnaire" && structuredQuestionnaire ? (
                    <QuestionnairePreview instrument={structuredQuestionnaire} />
                  ) : (
                    <Markdown className="text-[14px] leading-relaxed text-text-variant">
                      {activeSection.markdown}
                    </Markdown>
                  )}
                </div>
              ) : null}
            </>
          ) : null}

          {!loading && !failed && taskPath && sections.length === 0 ? (
            <p className="text-[14px] text-text-dim">{t("setup.tasks.noDocuments", "No task documents are available for this task.")}</p>
          ) : null}

          {primaryAction ? (
            <div className="border-t border-outline/30 pt-3">
              <button
                type="button"
                onClick={primaryAction.onClick}
                className={`inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-md bg-primary/12 px-3 text-[13px] font-semibold text-primary hover:bg-primary/18 ${FOCUS_RING}`}
              >
                <Sym name="play_arrow" size={16} />
                {primaryAction.label}
              </button>
            </div>
          ) : null}
        </div>
      )}
    </RailInsetModal>
  );
}
