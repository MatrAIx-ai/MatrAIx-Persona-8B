import type { ToneChipTone } from "./ToneChip";

export type DisplayTranslate = (
  key: string,
  fallback?: string,
  values?: Record<string, string | number>,
) => string;

type TaskDisplayIdentity = {
  id?: string;
  taskPath?: string;
};

/** Task titles are task-owned content and must not depend on the UI locale. */
export function taskDisplayTitle(
  title: string | undefined,
  _identity: TaskDisplayIdentity,
  _t?: DisplayTranslate,
): string {
  return title ?? "";
}

export function taskKindLabel(taskKind: "example" | "task", t?: DisplayTranslate): string {
  const key = taskKind === "example" ? "catalog.task.kind.example" : "catalog.task.kind.task";
  const fallback = taskKind === "example" ? "Example" : "Task";
  return t?.(key, fallback) ?? fallback;
}

/** Example tasks live under ``application/tasks/example-*`` folders. */
export function inferTaskKindFromPath(taskPath?: string): "example" | "task" {
  const folder = taskPath?.split("/").filter(Boolean).pop() ?? "";
  return folder.startsWith("example-") ? "example" : "task";
}

export function resolveTaskKind(taskPath?: string, taskKind?: string): "example" | "task" {
  if (taskKind === "example" || taskKind === "task") {
    return taskKind;
  }
  return inferTaskKindFromPath(taskPath);
}

export interface TaskCardTag {
  label: string;
  tone: ToneChipTone;
}

export interface TaskCardTagInput {
  taskPath?: string;
  taskKind?: string;
  metaType?: string;
  domain?: string;
  difficulty?: string;
  tags?: string[];
}

export function osChipLabel(os?: string | null, t?: DisplayTranslate): string {
  const key = (os ?? "").trim().toLowerCase();
  if (key === "macos") return t?.("taskDisplay.os.macos", "macOS") ?? "macOS";
  if (key === "ios") return t?.("taskDisplay.os.ios", "iOS") ?? "iOS";
  if (key === "linux") return t?.("taskDisplay.os.linux", "Linux") ?? "Linux";
  if (!key) return "";
  return formatChipLabel(key, t);
}

/** Sentence-case chip text — only the first letter capitalized unless already mixed case. */
export function formatChipLabel(text: string, t?: DisplayTranslate): string {
  const trimmed = text.trim();
  if (!trimmed) return "";
  const normalized = trimmed.toLowerCase().replace(/[\s_]+/g, "-");
  const knownLabels: Record<string, { key: string; fallback: string }> = {
    example: { key: "taskDisplay.kind.example", fallback: "Example" },
    task: { key: "taskDisplay.kind.task", fallback: "Task" },
    available: { key: "taskDisplay.status.available", fallback: "Available" },
    unavailable: { key: "taskDisplay.status.unavailable", fallback: "Unavailable" },
    survey: { key: "taskDisplay.type.survey", fallback: "Survey" },
    chatbot: { key: "taskDisplay.type.chatbot", fallback: "Chatbot" },
    web: { key: "taskDisplay.type.web", fallback: "Web" },
    "os-app": { key: "taskDisplay.type.osApp", fallback: "OS App" },
    software: { key: "taskDisplay.domain.software", fallback: "Software" },
    healthcare: { key: "taskDisplay.domain.healthcare", fallback: "Healthcare" },
    "finance-research": { key: "taskDisplay.domain.financeResearch", fallback: "Finance research" },
    "commerce-retail": { key: "taskDisplay.domain.commerceRetail", fallback: "Commerce-retail" },
    commerce: { key: "taskDisplay.domain.commerce", fallback: "Commerce" },
    "arts-culture": { key: "taskDisplay.domain.artsCulture", fallback: "Arts-culture" },
    education: { key: "taskDisplay.domain.education", fallback: "Education" },
    finance: { key: "taskDisplay.domain.finance", fallback: "Finance" },
    easy: { key: "taskDisplay.difficulty.easy", fallback: "Easy" },
    medium: { key: "taskDisplay.difficulty.medium", fallback: "Medium" },
    hard: { key: "taskDisplay.difficulty.hard", fallback: "Hard" },
    linux: { key: "taskDisplay.os.linux", fallback: "Linux" },
    macos: { key: "taskDisplay.os.macos", fallback: "macOS" },
    ios: { key: "taskDisplay.os.ios", fallback: "iOS" },
  };
  const known = knownLabels[normalized];
  if (known) return t?.(known.key, known.fallback) ?? known.fallback;
  if (/[a-z]/.test(trimmed) && /[A-Z]/.test(trimmed)) return trimmed;
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1).toLowerCase();
}

export function taskDocumentLabel(documentId: string, t?: DisplayTranslate): string {
  const labels: Record<string, { key: string; fallback: string }> = {
    instruction: { key: "taskDisplay.document.instruction", fallback: "Instruction" },
    context: { key: "taskDisplay.document.context", fallback: "Context" },
    questionnaire: { key: "taskDisplay.document.questionnaire", fallback: "Questionnaire" },
    "output-schema": { key: "taskDisplay.document.outputSchema", fallback: "Output schema" },
    "self-report": { key: "taskDisplay.document.selfReport", fallback: "Self-report" },
  };
  const label = labels[documentId];
  return label && t ? t(label.key, label.fallback) : label?.fallback ?? documentId;
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
}: TaskCardTagInput, t?: DisplayTranslate): TaskCardTag[] {
  const kind = resolveTaskKind(taskPath, taskKind);
  // One tone per chip category so they read at a glance:
  // kind → neutral, domain → accent, difficulty → secondary. The task type is
  // NOT repeated here — it already renders as its own chip / tab context.
  const chips: TaskCardTag[] = [{ label: taskKindLabel(kind, t), tone: "neutral" }];

  const domainLabel = domain?.trim();
  if (domainLabel) {
    chips.push({ label: formatChipLabel(domainLabel, t), tone: "accent" });
  }

  const difficultyLabel = difficulty?.trim();
  if (difficultyLabel) {
    chips.push({ label: formatChipLabel(difficultyLabel, t), tone: "secondary" });
  }

  return chips;
}

/** Normalize free-form ``metadata.tags`` for search (not shown as chips). */
export function taskSearchTags(tags?: string[] | null): string[] {
  return (tags ?? [])
    .map((tag) => tag.trim())
    .filter(Boolean);
}
