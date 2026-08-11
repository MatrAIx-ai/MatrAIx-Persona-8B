/**
 * Compact cockpit header — title + subtitle on the left, task-type switch on the right.
 * (No "Persona Cockpit" breadcrumb banner.)
 */
import { TaskTypeSwitch, type PlaygroundTaskType } from "./TaskTypeSwitch";
import { useI18n } from "@/i18n/I18nProvider";

export interface RunHeaderProps {
  taskType: PlaygroundTaskType;
  onTaskTypeChange: (value: PlaygroundTaskType) => void;
}

const SUBTITLE_FALLBACKS: Record<PlaygroundTaskType, string> = {
  chatbot:
    "Pick personas and a chat application, then launch. Watch the simulated user converse bubble-by-bubble.",
  survey:
    "Pick a persona and a questionnaire, then launch. A simulated user fills out the form and we score the responses.",
  web: "Pick personas and a web task, then launch. The simulated user completes the site in a real browser trace.",
  "os-app": "Pick personas and an OS app task, then launch. Native apps on Linux, macOS, or iOS.",
};

/** Dense one-line header: title · subtitle inline · app-type switch right. */
export function RunHeader({ taskType, onTaskTypeChange }: RunHeaderProps) {
  const { t } = useI18n();
  const subtitle = t(`runHeader.subtitle.${taskType}`, SUBTITLE_FALLBACKS[taskType]);
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <h1 className="shrink-0 font-display text-[18px] font-bold leading-tight tracking-tight text-text-main">
        {t("runHeader.title", "Configure a simulation")}
      </h1>
      <p
        className="min-w-0 flex-1 basis-64 truncate text-[13.5px] leading-snug text-text-variant"
        title={subtitle}
      >
        {subtitle}
      </p>
      <TaskTypeSwitch
        value={taskType}
        onChange={onTaskTypeChange}
        showLabel={false}
        className="ml-auto shrink-0"
      />
    </div>
  );
}

export default RunHeader;
