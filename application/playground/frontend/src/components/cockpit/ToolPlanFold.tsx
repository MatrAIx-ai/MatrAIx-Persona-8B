/**
 * ToolPlanFold: the expandable "How the app decided" disclosure on an app turn.
 *
 * Ports the mockup's fold: a header button that expands to reveal (when the
 * data is present) the parsed tool-plan steps, the ranked items with their
 * scores, and the raw native action text. Each section renders only when it has
 * content, so a turn that carried no tool plan / no raw action shows just the
 * sections it actually has, never empty scaffolding.
 *
 * Controlled disclosure: the parent owns `open` (so the "expand/collapse all"
 * keyboard shortcut can drive every fold at once) and gets `onToggle`. The
 * header is a real `aria-expanded` button targeting the panel by id.
 */
import { useId } from "react";

import { useI18n } from "@/i18n/I18nProvider";
import type { ExposureItem } from "./StructuredExposurePanel";
import { Sym, FOCUS_RING } from "./cockpitShared";
import type { PlanStep } from "@/lib/types";

/** A plan-step tool → a representative Material Symbol. */
const TOOL_ICON: Record<string, string> = {
  bufferstore: "database",
  buffer: "database",
  hardfilter: "filter_alt",
  softfilter: "filter_alt",
  filter: "filter_alt",
  rank: "leaderboard",
  rankingtool: "leaderboard",
  ranking: "leaderboard",
  map: "map",
  lookup: "map",
};

function iconForTool(tool: string): string {
  return TOOL_ICON[tool.toLowerCase().replace(/[^a-z]/g, "")] ?? "bolt";
}

export interface ToolPlanFoldProps {
  plan: PlanStep[];
  /** Structured item-list entries (for optional score display). */
  items: ExposureItem[];
  /** Raw native action text (the model's own output), if any. */
  nativeRaw: string | null;
  open: boolean;
  onToggle: () => void;
}

export function ToolPlanFold({ plan, items, nativeRaw, open, onToggle }: ToolPlanFoldProps) {
  const { t } = useI18n();
  const panelId = useId();
  const scored = items.filter((i) => i.score !== null && i.score !== undefined);
  const hasPlan = plan.length > 0;
  const hasScores = scored.length > 0;
  const hasRaw = Boolean(nativeRaw && nativeRaw.trim());
  const hasBody = hasPlan || hasScores || hasRaw;
  if (!hasBody) return null;

  return (
    <div
      className={`overflow-hidden rounded-md border ${
        open ? "border-outline bg-surface-lowest" : "border-outline bg-surface-low"
      }`}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={panelId}
        className={`flex w-full items-center justify-between p-2 hud text-[12px] text-text-dim transition-colors hover:text-text-variant active:bg-surface-high ${
          open ? "border-b border-outline bg-surface-low" : "hover:bg-surface-high"
        } ${FOCUS_RING}`}
      >
        <span className="flex items-center gap-2">
          <Sym name="code" size={16} />
          {t("cockpit.toolPlan.toggle")}
        </span>
        <Sym name={open ? "expand_less" : "expand_more"} size={16} />
      </button>

      {open && (
        <div id={panelId} className="rise-in">
          {hasPlan && (
            <div className="border-b border-outline p-3">
              <p className="mb-2 hud text-[12px] text-text-dim">{t("cockpit.toolPlan.steps")}</p>
              <ol className="space-y-1.5">
                {plan.map((step, i) => (
                  <li key={i} className="flex items-start gap-2 font-mono text-[13px] text-text-variant">
                    <span className="w-4 shrink-0 font-mono text-[13px] text-text-dim">{i + 1}</span>
                    <Sym name={iconForTool(step.tool)} size={15} className="shrink-0 text-primary" />
                    <span className="shrink-0 font-medium">{step.tool}</span>
                    {step.detail && <span className="min-w-0 break-words text-text-variant">{step.detail}</span>}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {hasScores && (
            <div className="border-b border-outline p-3">
              <p className="mb-2 hud text-[12px] text-text-dim">
                {t("cockpit.toolPlan.candidates")}
              </p>
              <div className="space-y-1 font-mono text-[13px] text-text-variant">
                {scored.map((item) => (
                  <div key={`${item.itemId}-${item.rank}`} className="flex items-start justify-between gap-3">
                    <span className="min-w-0 break-words">
                      {item.itemId}
                      {item.title ? ` · ${item.title}` : ""}
                    </span>
                    <span className="flex-shrink-0 text-text-main">{item.score?.toFixed(3)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {hasRaw && (
            <pre className="overflow-x-auto whitespace-pre-wrap break-words bg-field p-3 font-mono text-[13px] text-text-variant">
              {nativeRaw}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export default ToolPlanFold;
