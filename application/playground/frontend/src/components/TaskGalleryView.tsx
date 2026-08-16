import { TaskGalleryContent } from "./TaskGalleryContent";
import type { PlaygroundTaskType } from "./cockpit/TaskTypeSwitch";
import {
  StudioMeshShell,
  StudioPageFrame,
  StudioPageHeader,
} from "./studio/StudioShell";
import { useI18n } from "@/i18n/I18nProvider";

export interface TaskGalleryViewProps {
  onOpenInPlayground: (taskType: PlaygroundTaskType, taskId: string) => void;
}

export function TaskGalleryView({ onOpenInPlayground }: TaskGalleryViewProps) {
  const { t } = useI18n();

  return (
    <StudioMeshShell>
      <StudioPageFrame>
        <StudioPageHeader
          eyebrow={t("catalog.taskGallery.eyebrow")}
          title={t("catalog.taskGallery.title")}
          subtitle={t("catalog.taskGallery.subtitle")}
        />
        <TaskGalleryContent
          onOpenInPlayground={onOpenInPlayground}
          autoFocusSearch
        />
      </StudioPageFrame>
    </StudioMeshShell>
  );
}

export default TaskGalleryView;
