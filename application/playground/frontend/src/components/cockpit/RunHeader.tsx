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

type Translate = ReturnType<typeof useI18n>["t"];

function subtitle(t: Translate, taskType: PlaygroundTaskType): string {
  switch (taskType) {
    case "chatbot": return t("runHeader.subtitle.chatbot");
    case "survey": return t("runHeader.subtitle.survey");
    case "web": return t("runHeader.subtitle.web");
    case "os-app": return t("runHeader.subtitle.osApp");
  }
}

/** Dense one-line header: title · subtitle inline · app-type switch right. */
export function RunHeader({ taskType, onTaskTypeChange }: RunHeaderProps) {
  const { t } = useI18n();
  const taskSubtitle = subtitle(t, taskType);
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <h1 className="shrink-0 font-display text-[18px] font-bold leading-tight tracking-tight text-text-main">
        {t("runHeader.title")}
      </h1>
      <p
        className="min-w-0 flex-1 basis-64 truncate text-[13.5px] leading-snug text-text-variant"
        title={taskSubtitle}
      >
        {taskSubtitle}
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
