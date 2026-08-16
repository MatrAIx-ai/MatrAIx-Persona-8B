/**
 * InstructionPanel: task instruction document for the Inspector (not LLM prompts).
 */
import { Markdown } from "@/components/Markdown";
import { useI18n } from "@/i18n/I18nProvider";
import { Sym } from "./cockpitShared";

export interface InstructionPanelProps {
  label?: string;
  title?: string | null;
  markdown: string | null;
  loading?: boolean;
  error?: string | null;
  emptyMessage?: string;
  icon?: string;
}

export function InstructionPanel({
  label,
  title,
  markdown,
  loading,
  error,
  emptyMessage,
  icon = "description",
}: InstructionPanelProps) {
  const { t } = useI18n();
  const displayLabel = label ?? t("cockpit.instruction.label");
  const displayEmptyMessage = emptyMessage ?? t("cockpit.instruction.empty");
  if (loading) {
    return (
      <div className="p-md" aria-hidden>
        <div className="space-y-2">
          <div className="h-4 w-40 animate-rb-pulse rounded bg-surface-high" />
          <div className="h-24 w-full animate-rb-pulse rounded bg-surface-high" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-md">
        <div className="rounded-md border border-danger/30 bg-danger/10 px-4 py-3 text-[14px] text-danger">
          {error}
        </div>
      </div>
    );
  }

  if (!markdown?.trim()) {
    return (
      <div className="p-md">
        <div className="rounded-md border border-dashed border-outline-dim bg-surface-low px-4 py-10 text-center">
          <Sym name={icon} size={28} className="text-text-dim" />
          <p className="mt-2 text-[15px] leading-relaxed text-text-variant">
            {displayEmptyMessage}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-md">
      <div className="panel rise-in overflow-hidden rounded-md border border-outline bg-surface-lowest">
        <div className="border-b border-outline bg-surface-low px-3 py-2.5">
          <div className="flex items-center gap-2">
            <Sym name={icon} fill={1} size={18} className="text-primary" />
            <h3 className="hud text-[13px] text-primary">{displayLabel}</h3>
          </div>
          {title ? <p className="mt-1 text-[14px] font-medium text-text-main">{title}</p> : null}
        </div>
        <div className="custom-scrollbar max-h-[min(70vh,520px)] overflow-y-auto p-3">
          <Markdown className="text-[14px] leading-relaxed text-text-variant">{markdown}</Markdown>
        </div>
      </div>
    </div>
  );
}

export default InstructionPanel;
