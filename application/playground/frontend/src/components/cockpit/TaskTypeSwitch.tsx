/**
 * TaskTypeSwitch: the application-type segmented control.
 *
 * Ports the mockup's "Application type" switch (`app-redesign-v3.html:106-112`):
 * a `.hud` micro-label above a compact `inline-flex` segmented control
 * (Chatbot / Survey / Website / AppWorld). It is a self-contained, header-embeddable block
 * (no full-width bar) so each cockpit can drop it into the top-right of its
 * "Configure a simulation" header.
 *
 * Shared primitive: Survey/Web cockpits render the same control. Props are
 * unchanged (`value` / `onChange` / `disabled`); `showLabel` + `className` are
 * optional presentation knobs.
 */
import { OS_APP_TAB_LABEL } from "@/lib/personaAgentCatalog";
import { useI18n } from "@/i18n/I18nProvider";
import { FOCUS_RING, Sym } from "./cockpitShared";

export type PlaygroundTaskType = "chatbot" | "survey" | "web" | "os-app";

export interface TaskTypeSwitchProps {
  value: PlaygroundTaskType;
  onChange: (value: PlaygroundTaskType) => void;
  disabled?: boolean;
  /** Show the "Application type" hud label above the control. Default true. */
  showLabel?: boolean;
  className?: string;
}

const OPTIONS: ReadonlyArray<{ value: PlaygroundTaskType; icon: string }> = [
  { value: "survey", icon: "fact_check" },
  { value: "chatbot", icon: "forum" },
  { value: "web", icon: "language" },
  { value: "os-app", icon: "apps" },
];

const OPTION_COPY: Record<PlaygroundTaskType, { labelKey: string; label: string; hintKey: string; hint: string }> = {
  survey: { labelKey: "cockpit.taskType.survey", label: "Survey", hintKey: "cockpit.taskType.surveyHint", hint: "A fixed questionnaire the user fills out." },
  chatbot: { labelKey: "cockpit.taskType.chatbot", label: "Chatbot", hintKey: "cockpit.taskType.chatbotHint", hint: "A back-and-forth conversation." },
  web: { labelKey: "cockpit.taskType.web", label: "Web", hintKey: "cockpit.taskType.webHint", hint: "A real browser task the user completes." },
  "os-app": { labelKey: "cockpit.taskType.osApp", label: OS_APP_TAB_LABEL, hintKey: "cockpit.taskType.osAppHint", hint: "Native apps on Linux, macOS, or iOS (computer-use simulation)." },
};

export function TaskTypeSwitch({ value, onChange, disabled, showLabel = true, className = "" }: TaskTypeSwitchProps) {
  const { t } = useI18n();
  return (
    <div className={className}>
      {showLabel && (
        <div className="hud mb-1.5 text-[11px] text-primary">
          {t("cockpit.taskType.label", "Application type")}
        </div>
      )}
      <div className="cockpit-segment inline-flex">
        {OPTIONS.map((option) => {
          const selected = option.value === value;
          const copy = OPTION_COPY[option.value];
          return (
            <button
              key={option.value}
              type="button"
              disabled={disabled}
              title={t(copy.hintKey, copy.hint)}
              aria-pressed={selected}
              onClick={() => onChange(option.value)}
              className={`cockpit-segment__btn flex items-center gap-1.5 px-3 py-1.5 text-[14px] transition ease-out active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-60 disabled:active:scale-100 ${FOCUS_RING} ${
                selected ? "cockpit-segment__btn--active" : ""
              }`}
            >
              <Sym name={option.icon} fill={selected ? 1 : 0} size={14} />
              {t(copy.labelKey, copy.label)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default TaskTypeSwitch;
