import { useState, type ReactNode } from "react";

import { FOCUS_RING, Sym } from "./cockpit/cockpitShared";
import Markdown from "./Markdown";
import { QuestionnairePreview } from "./QuestionnairePreview";
import { useI18n, type I18nContextValue } from "@/i18n/I18nProvider";
import {
  isMeaningfulPromptBody,
  resolvePromptSections,
} from "@/lib/promptSections";
import {
  hasMeaningfulTaskContext,
  normalizeOutputSchemaMarkdown,
  normalizeTaskInstructionMarkdown,
} from "@/lib/taskContent";
import type { PlaygroundPrompts, SurveyInstrument } from "@/lib/types";
import type { RunPersona } from "./runsShared";

type Translate = I18nContextValue["t"];

export interface TrialDebriefRailsProps {
  prompts?: PlaygroundPrompts | null;
  persona?: RunPersona | null;
  instructionMarkdown?: string | null;
  contextMarkdown?: string | null;
  /** Structured questionnaire.yaml instrument — preferred over markdown dump. */
  questionnaire?: SurveyInstrument | null;
  questionnaireMarkdown?: string | null;
  /** Surveys should not show this; kept for non-survey debriefs. */
  outputSchemaMarkdown?: string | null;
  /** When true, never render Output schema even if markdown is present. */
  hideOutputSchema?: boolean;
}

function formatPersonaDimensionFallback(
  persona: RunPersona | null | undefined,
  t: Translate,
): string {
  const dims = persona?.dimensions;
  if (!dims || Object.keys(dims).length === 0) return "";
  const lines = [t("runs.profileDimensions")];
  for (const [key, value] of Object.entries(dims).sort(([a], [b]) =>
    a.localeCompare(b),
  )) {
    if (!value?.trim()) continue;
    const label = key
      .replace(/_/g, " ")
      .replace(/\b\w/g, (ch) => ch.toUpperCase());
    lines.push(`- ${label}: ${value}`);
  }
  return lines.join("\n");
}

function DebriefRail({
  label,
  icon,
  subtitle,
  badge,
  body,
  children,
}: {
  label: string;
  icon: string;
  subtitle?: string | null;
  badge?: string | null;
  body?: string;
  children?: ReactNode;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const hasBody = Boolean((body ?? "").trim()) || Boolean(children);
  const expandable = hasBody;

  return (
    <section>
      <button
        type="button"
        onClick={() => expandable && setOpen((value) => !value)}
        aria-expanded={expandable ? open : undefined}
        disabled={!expandable}
        className={`flex w-full items-center justify-between gap-2 px-4 py-3 text-left transition-colors ${
          expandable ? "hover:bg-surface/40" : "cursor-default"
        } ${FOCUS_RING}`}
      >
        <span className="flex min-w-0 items-center gap-2.5">
          <Sym
            name={icon}
            fill={1}
            size={18}
            className="flex-none text-primary/80"
          />
          <span className="hud text-[11px] text-text-dim">{label}</span>
          {subtitle ? (
            <span className="truncate font-display text-[15px] font-semibold text-text-main">
              {subtitle}
            </span>
          ) : null}
          {badge ? (
            <span className="hud flex-none rounded glass-tile px-1.5 py-0.5 text-[11px] text-text-dim">
              {badge}
            </span>
          ) : null}
        </span>
        {expandable ? (
          <span className="flex flex-none items-center gap-2">
            <span className="hud text-[11px] text-text-dim">
              {open ? t("runs.hide") : t("runs.view")}
            </span>
            <Sym
              name={open ? "expand_more" : "chevron_right"}
              size={18}
              className="text-text-dim"
            />
          </span>
        ) : null}
      </button>
      {open && hasBody ? (
        <div className="border-t border-outline/40 bg-surface/20 px-4 py-3">
          <div className="custom-scrollbar max-h-96 overflow-auto">
            {children ? (
              children
            ) : (
              <Markdown className="max-w-none text-[14px] leading-relaxed text-text-variant">
                {body ?? ""}
              </Markdown>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}

/** Collapsible persona profile + task instruction rails for every trial debrief. */
export function TrialDebriefRails({
  prompts,
  persona,
  instructionMarkdown,
  contextMarkdown,
  questionnaire,
  questionnaireMarkdown,
  outputSchemaMarkdown,
  hideOutputSchema = false,
}: TrialDebriefRailsProps) {
  const { t } = useI18n();
  const sections = prompts
    ? resolvePromptSections(prompts)
    : { persona: "", task: "" };
  const personaCandidate = sections.persona || (persona?.context ?? "").trim();
  const dimensionFallback = formatPersonaDimensionFallback(persona, t);
  const personaBody = isMeaningfulPromptBody(personaCandidate)
    ? personaCandidate
    : isMeaningfulPromptBody(dimensionFallback)
      ? dimensionFallback
      : "";
  const normalizedInstruction =
    normalizeTaskInstructionMarkdown(instructionMarkdown);
  const taskCandidate = normalizedInstruction || sections.task;
  const taskBody = taskCandidate.trim();
  const contextBody = hasMeaningfulTaskContext(contextMarkdown)
    ? (contextMarkdown ?? "").trim()
    : "";
  const outputSchemaBody = hideOutputSchema
    ? ""
    : normalizeOutputSchemaMarkdown(outputSchemaMarkdown);
  const hasStructuredQuestionnaire = Boolean(questionnaire?.questions?.length);

  const rails: ReactNode[] = [];

  if (personaBody || persona?.name || persona?.id || persona?.source) {
    rails.push(
      <DebriefRail
        key="persona"
        label={t("runs.personaProfile")}
        icon="person"
        body={personaBody}
      />,
    );
  }
  if (taskBody) {
    rails.push(
      <DebriefRail
        key="instruction"
        label={t("runs.taskInstruction")}
        icon="assignment"
        body={taskBody}
      />,
    );
  }
  if (contextBody) {
    rails.push(
      <DebriefRail
        key="context"
        label={t("runs.taskContext")}
        icon="menu_book"
        body={contextBody}
      />,
    );
  }
  if (hasStructuredQuestionnaire && questionnaire) {
    rails.push(
      <DebriefRail
        key="questionnaire"
        label={t("runs.questionnaire")}
        icon="list_alt"
      >
        <QuestionnairePreview instrument={questionnaire} />
      </DebriefRail>,
    );
  } else if ((questionnaireMarkdown ?? "").trim()) {
    // Legacy fallback only — prefer structured instrument above.
    rails.push(
      <DebriefRail
        key="questionnaire"
        label={t("runs.questionnaire")}
        icon="list_alt"
        body={(questionnaireMarkdown ?? "").trim()}
      />,
    );
  }
  if (outputSchemaBody) {
    rails.push(
      <DebriefRail
        key="output-schema"
        label={t("runs.outputSchema")}
        icon="schema"
        body={outputSchemaBody}
      />,
    );
  }

  if (rails.length === 0) return null;

  return <div className="space-y-2">{rails}</div>;
}

export default TrialDebriefRails;
