import type { ToneChipTone } from "./ToneChip";

export type TaskKind = "example" | "task";

type TaskKindMessageKey =
  | "cockpitSetup.taskKind.example"
  | "cockpitSetup.taskKind.task";

const TASK_KIND_MESSAGE_KEYS: Record<TaskKind, TaskKindMessageKey> = {
  example: "cockpitSetup.taskKind.example",
  task: "cockpitSetup.taskKind.task",
};

/** Example tasks live under ``application/tasks/example-*`` folders. */
export function inferTaskKindFromPath(taskPath?: string): TaskKind {
  const folder = taskPath?.split("/").filter(Boolean).pop() ?? "";
  return folder.startsWith("example-") ? "example" : "task";
}

export function resolveTaskKind(taskPath?: string, taskKind?: string): TaskKind {
  if (taskKind === "example" || taskKind === "task") {
    return taskKind;
  }
  return inferTaskKindFromPath(taskPath);
}

export type TaskCardTag =
  | { label: string; tone: ToneChipTone; taskKind?: undefined }
  | { label?: undefined; tone: ToneChipTone; taskKind: TaskKind };

export function taskCardTagLabel(
  tag: TaskCardTag,
  t: (key: TaskKindMessageKey) => string,
): string {
  return tag.taskKind
    ? t(TASK_KIND_MESSAGE_KEYS[tag.taskKind])
    : formatChipLabel(tag.label);
}

export function taskCardTagKey(tag: TaskCardTag): string {
  return tag.taskKind ? `task-kind:${tag.taskKind}` : `label:${tag.label}`;
}

export function taskCardTagSearchText(tag: TaskCardTag): string {
  return tag.taskKind ?? tag.label;
}

export interface TaskCardTagInput {
  taskPath?: string;
  taskKind?: string;
  metaType?: string;
  domain?: string;
  difficulty?: string;
  tags?: string[];
}

export function osChipLabel(os?: string | null): string {
  const key = (os ?? "").trim().toLowerCase();
  if (key === "macos") return "macOS";
  if (key === "ios") return "iOS";
  if (key === "linux") return "Linux";
  if (!key) return "";
  return formatChipLabel(key);
}

/** Sentence-case chip text — only the first letter capitalized unless already mixed case. */
export function formatChipLabel(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "";
  if (/[a-z]/.test(trimmed) && /[A-Z]/.test(trimmed)) {
    return trimmed;
  }
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1).toLowerCase();
}

/** Persona dimension chips use the same tone order as task metadata chips. */
const PERSONA_DIM_TONE: Record<string, ToneChipTone> = {
  age_bracket: "primary",
  region: "accent",
  domain: "secondary",
  intent: "warn",
  life_stage: "warn",
  source: "secondary",
};

const PERSONA_DIM_FALLBACK_TONES: ToneChipTone[] = ["primary", "accent", "secondary", "warn"];

export function personaDimChipTone(dimensionKey: string, index: number): ToneChipTone {
  return PERSONA_DIM_TONE[dimensionKey] ?? PERSONA_DIM_FALLBACK_TONES[index % PERSONA_DIM_FALLBACK_TONES.length];
}

/** Shared chip typography (task rail + persona cards). */
export const CHIP_TEXT_CLASS = "text-[11px]";

/** OS chips use a distinct tone so they do not collide with difficulty (secondary). */
export function osChipTone(os?: string | null): ToneChipTone {
  void os;
  return "warn";
}

/** Build visible chips from ``task.toml`` structural metadata (kind / type / domain / difficulty).
 * Free-form ``metadata.tags`` stay off the card — they remain searchable via ``searchTags``. */
export function taskCardTags({
  taskPath,
  taskKind,
  domain,
  difficulty,
}: TaskCardTagInput): TaskCardTag[] {
  const kind = resolveTaskKind(taskPath, taskKind);
  // One tone per chip category so they read at a glance:
  // kind → neutral, domain → accent, difficulty → secondary. The task type is
  // NOT repeated here — it already renders as its own chip / tab context.
  const chips: TaskCardTag[] = [{ taskKind: kind, tone: "neutral" }];

  const domainLabel = domain?.trim();
  if (domainLabel) {
    chips.push({ label: formatChipLabel(domainLabel), tone: "accent" });
  }

  const difficultyLabel = difficulty?.trim();
  if (difficultyLabel) {
    chips.push({ label: formatChipLabel(difficultyLabel), tone: "secondary" });
  }

  return chips;
}

/** Normalize free-form ``metadata.tags`` for search (not shown as chips). */
export function taskSearchTags(tags?: string[] | null): string[] {
  return (tags ?? [])
    .map((tag) => tag.trim())
    .filter(Boolean);
}
