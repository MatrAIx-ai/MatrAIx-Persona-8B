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

type Translate = ReturnType<typeof useI18n>["t"];

function optionCopy(t: Translate, type: PlaygroundTaskType): { label: string; hint: string } {
  switch (type) {
    case "survey":
      return { label: t("cockpit.taskType.survey"), hint: t("cockpit.taskType.surveyHint") };
    case "chatbot":
      return { label: t("cockpit.taskType.chatbot"), hint: t("cockpit.taskType.chatbotHint") };
    case "web":
      return { label: t("cockpit.taskType.web"), hint: t("cockpit.taskType.webHint") };
    case "os-app":
      return { label: t("cockpit.taskType.osApp"), hint: t("cockpit.taskType.osAppHint") };
  }
}

export function TaskTypeSwitch({ value, onChange, disabled, showLabel = true, className = "" }: TaskTypeSwitchProps) {
  const { t } = useI18n();
  return (
    <div className={className}>
      {showLabel && <div className="hud mb-1.5 text-[11px] text-primary">{t("cockpit.taskType.label")}</div>}
      <div className="cockpit-segment inline-flex">
        {OPTIONS.map((option) => {
          const selected = option.value === value;
          const copy = optionCopy(t, option.value);
          return (
            <button
              key={option.value}
              type="button"
              disabled={disabled}
              title={copy.hint}
              aria-pressed={selected}
              onClick={() => onChange(option.value)}
              className={`cockpit-segment__btn flex items-center gap-1.5 px-3 py-1.5 text-[14px] transition ease-out active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-60 disabled:active:scale-100 ${FOCUS_RING} ${
                selected ? "cockpit-segment__btn--active" : ""
              }`}
            >
              <Sym name={option.icon} fill={selected ? 1 : 0} size={14} />
              {copy.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default TaskTypeSwitch;
