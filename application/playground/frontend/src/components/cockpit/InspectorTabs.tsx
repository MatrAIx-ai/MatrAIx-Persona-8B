/**
 * InspectorTabs: the live-run right inspector, as a real ARIA tablist.
 *
 * InspectorTabs: evaluation plus optional task-doc panels.
 */
import { useRef } from "react";

import { useI18n } from "@/i18n/I18nProvider";
import { FOCUS_RING, Sym } from "./cockpitShared";

export type InspectorTab =
  | "evaluation"
  | "instruction"
  | "context"
  | "questionnaire"
  | "output-schema"
  | "self-report";

export interface InspectorTabsProps {
  active: InspectorTab;
  onChange: (tab: InspectorTab) => void;
  evaluation: React.ReactNode;
  instruction: React.ReactNode;
  context?: React.ReactNode;
  questionnaire?: React.ReactNode;
  outputSchema?: React.ReactNode;
  selfReport?: React.ReactNode;
}

export function InspectorTabs({
  active,
  onChange,
  evaluation,
  instruction,
  context,
  questionnaire,
  outputSchema,
  selfReport,
}: InspectorTabsProps) {
  const { t } = useI18n();
  const tabs: Array<{ id: InspectorTab; label: string; icon: string }> = [
    { id: "evaluation", label: t("cockpit.inspector.evaluation"), icon: "verified" },
    { id: "instruction", label: t("cockpit.inspector.instruction"), icon: "description" },
  ];
  if (context) tabs.push({ id: "context", label: t("cockpit.inspector.context"), icon: "menu_book" });
  if (questionnaire) tabs.push({ id: "questionnaire", label: t("cockpit.inspector.questionnaire"), icon: "list_alt" });
  if (outputSchema) tabs.push({ id: "output-schema", label: t("cockpit.inspector.outputSchema"), icon: "schema" });
  if (selfReport) tabs.push({ id: "self-report", label: t("cockpit.inspector.selfReport"), icon: "rate_review" });
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const activeLabel = tabs.find((t) => t.id === active)?.label ?? "";

  function focusTab(index: number) {
    const clamped = (index + tabs.length) % tabs.length;
    const tab = tabs[clamped];
    onChange(tab.id);
    tabRefs.current[clamped]?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      focusTab(index + 1);
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      focusTab(index - 1);
    } else if (e.key === "Home") {
      e.preventDefault();
      focusTab(0);
    } else if (e.key === "End") {
      e.preventDefault();
      focusTab(tabs.length - 1);
    }
  }

  return (
    <aside className="z-0 flex h-[340px] w-full flex-shrink-0 flex-col border-t border-outline bg-surface-lowest lg:h-full lg:w-[360px] lg:border-l lg:border-t-0">
      <div className="flex shrink-0 items-center justify-between border-b border-outline bg-surface px-4 py-3">
        <span className="hud text-[12px] text-primary">{t("cockpit.inspector.title")}</span>
        <span className="hud text-[11px] text-text-dim">{activeLabel}</span>
      </div>

      <div
        role="tablist"
        aria-label={t("cockpit.inspector.title")}
        aria-orientation="horizontal"
        className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-0 border-b border-outline px-3"
      >
        {tabs.map((tab, i) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              ref={(el) => (tabRefs.current[i] = el)}
              role="tab"
              id={`inspector-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`inspector-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => {
                onChange(tab.id);
              }}
              onKeyDown={(e) => onKeyDown(e, i)}
              className={`-mb-px flex min-w-0 select-none items-center gap-1.5 border-b-2 py-2.5 text-[13px] font-medium transition ease-out active:opacity-70 lg:text-[14px] ${FOCUS_RING} ${
                selected ? "border-primary text-primary" : "border-transparent text-text-variant hover:text-text-main"
              }`}
            >
              <Sym name={tab.icon} fill={selected ? 1 : 0} size={16} />
              <span className="whitespace-nowrap">{tab.label}</span>
            </button>
          );
        })}
      </div>

      <div className="custom-scrollbar flex-1 overflow-y-auto">
        <div role="tabpanel" id="inspector-panel-evaluation" aria-labelledby="inspector-tab-evaluation" hidden={active !== "evaluation"}>
          {active === "evaluation" && evaluation}
        </div>
        <div role="tabpanel" id="inspector-panel-instruction" aria-labelledby="inspector-tab-instruction" hidden={active !== "instruction"}>
          {active === "instruction" && instruction}
        </div>
        <div role="tabpanel" id="inspector-panel-context" aria-labelledby="inspector-tab-context" hidden={active !== "context"}>
          {active === "context" && context}
        </div>
        <div
          role="tabpanel"
          id="inspector-panel-questionnaire"
          aria-labelledby="inspector-tab-questionnaire"
          hidden={active !== "questionnaire"}
        >
          {active === "questionnaire" && questionnaire}
        </div>
        <div
          role="tabpanel"
          id="inspector-panel-output-schema"
          aria-labelledby="inspector-tab-output-schema"
          hidden={active !== "output-schema"}
        >
          {active === "output-schema" && outputSchema}
        </div>
        <div
          role="tabpanel"
          id="inspector-panel-self-report"
          aria-labelledby="inspector-tab-self-report"
          hidden={active !== "self-report"}
        >
          {active === "self-report" && selfReport}
        </div>
      </div>
    </aside>
  );
}

export default InspectorTabs;
