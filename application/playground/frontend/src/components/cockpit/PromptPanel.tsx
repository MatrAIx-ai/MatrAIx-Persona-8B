import { Sym } from "./cockpitShared";
import { useI18n } from "@/i18n/I18nProvider";
import type { PlaygroundPrompts } from "@/lib/types";

export interface PromptPanelProps {
  prompts: PlaygroundPrompts | null | undefined;
}

export function PromptPanel({ prompts }: PromptPanelProps) {
  const { t } = useI18n();
  if (!prompts) {
    return (
      <div className="p-md">
        <div className="rise-in rounded-md border border-dashed border-outline-dim bg-surface-low px-4 py-10 text-center">
          <Sym name="terminal" size={28} className="text-text-dim" />
          <p className="mt-2 text-[15px] leading-relaxed text-text-variant">
            {t("promptPanel.empty")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 p-md">
      <PromptBlock
        label={t("promptPanel.personaPrompt")}
        sublabel={t("promptPanel.personaPromptSublabel")}
        value={prompts.personaPrompt ?? prompts.harborPrompt ?? ""}
        index={0}
        emptyLabel={t("promptPanel.emptyValue")}
      />
      <PromptBlock
        label={t("promptPanel.taskPrompt")}
        sublabel={t("promptPanel.taskPromptSublabel")}
        value={prompts.taskPrompt ?? ""}
        index={1}
        emptyLabel={t("promptPanel.emptyValue")}
      />
    </div>
  );
}

function PromptBlock({
  label,
  sublabel,
  value,
  emptyLabel,
  index = 0,
}: {
  label: string;
  sublabel: string;
  value: string;
  emptyLabel: string;
  index?: number;
}) {
  return (
    <section
      className="rise-in overflow-hidden rounded-md border border-outline bg-surface-lowest"
      style={{ animationDelay: `${Math.min(index, 6) * 30}ms` }}
    >
      <div className="flex items-center justify-between gap-3 border-b border-outline bg-surface-low px-3 py-2">
        <div className="min-w-0">
          <h3 className="font-semibold text-sm text-text-main">{label}</h3>
          <p className="hud break-words text-[11px] text-text-dim">{sublabel}</p>
        </div>
        <Sym name="data_object" size={16} className="flex-shrink-0 text-text-dim" />
      </div>
      <pre className="custom-scrollbar max-h-72 overflow-auto whitespace-pre-wrap break-words bg-field p-3 font-mono text-[13px] leading-relaxed text-text-variant">
        {value || emptyLabel}
      </pre>
    </section>
  );
}

export default PromptPanel;
