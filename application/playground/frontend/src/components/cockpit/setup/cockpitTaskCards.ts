import type { ChatbotEvalTask, OsAppEvalTask, SurveyHarborTask, WebEvalTask } from "@/lib/types";
import { suggestedWebPersonaAgent, webPersonaAgentLabel } from "@/lib/personaAgentCatalog";
import type { ChatTransport, TaskCardModel } from "./TaskSelectionRail";
import {
  resolveTaskKind,
  taskCardTags,
  taskSearchTags,
  osChipLabel,
  osChipTone,
  type DisplayTranslate,
  type TaskCardTag,
} from "./taskCardLabels";

function transportForChatTask(
  task: Pick<ChatbotEvalTask, "transport" | "canStart">,
): ChatTransport {
  const transport = (task.transport || "").trim();
  if (transport === "mcp") {
    return task.canStart ? "mcp_sidecar" : "mcp_external";
  }
  if (transport === "external_http") return "api_external";
  return "api_sidecar";
}

/** Map chatbot catalog rows into shared TaskCardModel cards (gallery + cockpit). */
export function chatbotEvalTaskCards(
  tasks: ChatbotEvalTask[],
  opts?: { runningTaskIds?: ReadonlySet<string> },
  t?: DisplayTranslate,
): TaskCardModel[] {
  const runningTaskIds = opts?.runningTaskIds;
  return tasks.map((task) => {
    const transport = transportForChatTask(task);
    const runningNow = Boolean(runningTaskIds?.has(task.id));
    const available =
      runningNow ? true : task.available === null || task.available === undefined ? null : task.available;
    const statusTone: "secondary" | "danger" = available ? "secondary" : "danger";
    const statusTags =
      available === null
        ? []
        : [
            {
              label: available
                ? t?.("eval.taskCards.available", "Available") ?? "Available"
                : t?.("eval.taskCards.unavailable", "Unavailable") ?? "Unavailable",
              tone: statusTone,
            },
          ];
    return {
      id: task.id,
      title: task.title,
      subtitle: task.description,
      taskType: "chatbot" as const,
      taskPath: task.taskPath,
      transport,
      available,
      canStart: task.canStart ?? false,
      statusLabel: available === null ? undefined : available ? t ? t("eval.taskCards.available", "Available") : "Available" : t ? t("eval.taskCards.unavailable", "Unavailable") : "Unavailable",
      statusDetail: runningNow
        ? t
          ? t("eval.taskCards.sidecarStarted", "Sidecar started for this run.")
          : "Sidecar started for this run."
        : task.statusDetail ?? undefined,
      capabilities: (task.capabilities ?? []).map((cap) => ({
        id: cap.id,
        label: cap.label,
        kind: cap.kind,
      })),
      domain: task.domain,
      difficulty: task.difficulty,
      taskKind: task.taskKind,
      profileMarkdown: task.profileMarkdown,
      instructionMarkdown: task.instructionMarkdown,
      tags: [
        ...taskCardTags({
          taskPath: task.taskPath,
          taskKind: task.taskKind,
          metaType: task.metaType,
          domain: task.domain,
          difficulty: task.difficulty,
        }, t),
        ...statusTags,
      ],
      searchTags: taskSearchTags(task.tags),
    };
  });
}

function availabilityRank(available?: boolean | null): number {
  if (available === true) return 0;
  if (available === false) return 2;
  return 1;
}

/** Available tasks first, then unknown status, then unavailable; stable title order within each group. */
export function sortByAvailability<T extends { available?: boolean | null; title?: string; id?: string }>(
  tasks: T[],
): T[] {
  return [...tasks].sort((a, b) => {
    const byAvailability = availabilityRank(a.available) - availabilityRank(b.available);
    if (byAvailability !== 0) return byAvailability;
    return (a.title ?? a.id ?? "").localeCompare(b.title ?? b.id ?? "");
  });
}

function withExtraTags(tags: TaskCardTag[], ...extra: TaskCardTag[]): TaskCardTag[] {
  return [...tags, ...extra];
}

function harborTaskTags(
  item: {
    taskPath?: string;
    taskKind?: string;
    metaType?: string;
    domain?: string;
    difficulty?: string;
  },
): TaskCardTag[] {
  return taskCardTags({
    taskPath: item.taskPath,
    taskKind: item.taskKind,
    metaType: item.metaType,
    domain: item.domain,
    difficulty: item.difficulty,
  });
}

export function surveyHarborTaskCards(tasks: SurveyHarborTask[]): TaskCardModel[] {
  return tasks.map((item) => {
    const taskKind = resolveTaskKind(item.taskPath, item.taskKind);
    return {
      id: item.id,
      title: item.title,
      subtitle: item.description,
      taskType: "survey",
      taskPath: item.taskPath,
      available: true,
      metaType: item.metaType ?? "survey",
      domain: item.domain,
      difficulty: item.difficulty,
      taskKind,
      tags: harborTaskTags(item),
      searchTags: taskSearchTags(item.tags),
    };
  });
}

export function webEvalTaskCards(tasks: WebEvalTask[]): TaskCardModel[] {
  return tasks.map((item) => {
    const taskKind = resolveTaskKind(item.taskPath, item.taskKind);
    return {
      id: item.id,
      title: item.title,
      subtitle: item.description ?? item.siteName,
      taskType: "web",
      taskPath: item.taskPath ?? "",
      available: true,
      metaType: item.metaType ?? "web",
      domain: item.domain,
      difficulty: item.difficulty,
      taskKind,
      tags: withExtraTags(harborTaskTags(item), {
        label: webPersonaAgentLabel(suggestedWebPersonaAgent(item.id)),
        tone: "warn",
      }),
      searchTags: taskSearchTags(item.tags),
    };
  });
}

export function osAppTaskCards(tasks: OsAppEvalTask[]): TaskCardModel[] {
  return tasks.map((item) => {
    const taskKind = resolveTaskKind(item.taskPath, item.taskKind);
    const os = item.os ?? item.platform;
    const metaType = item.metaType?.trim() || "os-app";
    const enriched = {
      ...item,
      metaType,
      domain: item.domain,
      difficulty: item.difficulty,
      taskKind,
    };
    const osLabel = osChipLabel(os);
    return {
      id: item.id,
      title: item.title,
      subtitle: item.description ?? item.environmentLabel,
      taskType: "os-app",
      taskPath: item.taskPath,
      platform: item.platform,
      os,
      available: true,
      metaType,
      domain: item.domain,
      difficulty: item.difficulty,
      taskKind,
      tags: osLabel
        ? withExtraTags(harborTaskTags(enriched), { label: osLabel, tone: osChipTone(os) })
        : harborTaskTags(enriched),
      searchTags: taskSearchTags(item.tags),
    };
  });
}
