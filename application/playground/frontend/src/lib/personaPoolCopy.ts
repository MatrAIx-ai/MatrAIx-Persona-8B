import type { PersonaPoolCatalog } from "./types";

export type PersonaPoolTranslate = (
  key: string,
  fallback?: string,
  values?: Record<string, string | number>,
) => string;

export function poolSlugLabel(poolPath: string): string {
  const slug = poolPath.split("/").filter(Boolean).pop() ?? poolPath;
  return slug.replace(/-/g, " ");
}

export function personaPoolEmptyMessage(
  catalog: PersonaPoolCatalog | null | undefined,
  t?: PersonaPoolTranslate,
): string {
  const pool = catalog?.pool
    ? poolSlugLabel(catalog.pool)
    : t?.("catalog.personaStore.poolDefault", "persona pool") ?? "persona pool";
  return t?.(
    "catalog.personaStore.poolEmpty",
    "{pool} is empty or could not be loaded.",
    { pool },
  ) ?? `${pool} is empty or could not be loaded.`;
}

/** Backend / sampling errors that mean the fixture pool is too thin for filters. */
export function isPersonaPoolCoverageError(message: string | null | undefined): boolean {
  const text = message ?? "";
  return (
    text.includes("exceeds matched pool size") ||
    text.includes("No personas with stratify fields") ||
    text.includes("sample_size_per_value_group=") ||
    text.includes("Incomplete stratify coverage") ||
    text.includes("matraix-persona-1m") ||
    text.includes("matraix-persona-dev-sample")
  );
}

export function personaPoolCoverageHint(
  _taskPath?: string | null,
  t?: PersonaPoolTranslate,
): string {
  const fallback =
    "Not enough matching personas in this dataset for the current filters. " +
    "Widen filters / sources, switch dataset (dev sample vs matraix-persona-1m), " +
    "or use a saved cohort that already has enough matches. " +
    "Playground does not synthesize missing personas.";
  return t?.("catalog.personaStore.poolCoverageHint", fallback) ?? fallback;
}

/** Prefer the API message; fall back to a production-pool recovery hint. */
export function formatPersonaSampleError(
  message: string,
  taskPath?: string | null,
  t?: PersonaPoolTranslate,
): string {
  const trimmed = message.trim();
  if (isPersonaPoolCoverageError(trimmed)) {
    const first = trimmed.split("\n").find((line) => line.trim()) || trimmed;
    const alreadyHinted =
      trimmed.includes("matraix-persona-1m") ||
      trimmed.includes("Synthesize to fill") ||
      trimmed.includes("does not synthesize");
    return alreadyHinted ? trimmed : `${first}\n\n${personaPoolCoverageHint(taskPath, t)}`;
  }
  return trimmed;
}
