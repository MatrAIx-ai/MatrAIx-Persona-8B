import type { PersonaPoolCatalog } from "./types";

export function poolSlugLabel(poolPath: string): string {
  const slug = poolPath.split("/").filter(Boolean).pop() ?? poolPath;
  return slug.replace(/-/g, " ");
}

export interface PersonaPoolEmptyState {
  code: "persona_pool_empty";
  /** A dataset identifier to interpolate without translating it. */
  pool: string | null;
}

export function personaPoolEmptyState(
  catalog: PersonaPoolCatalog | null | undefined,
): PersonaPoolEmptyState {
  return {
    code: "persona_pool_empty",
    pool: catalog?.pool ? poolSlugLabel(catalog.pool) : null,
  };
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

export interface PersonaPoolSampleError {
  /** Known UI state; `rawMessage` remains unchanged for backend diagnostics. */
  code: "persona_pool_coverage" | null;
  rawMessage: string;
  /** Whether the rendering layer should add its localized recovery guidance. */
  showRecoveryHint: boolean;
}

/**
 * Classify a sampling failure without rewriting its backend / model text.
 * Components translate only the stable code and leave `rawMessage` intact.
 */
export function classifyPersonaPoolSampleError(
  message: string,
): PersonaPoolSampleError {
  const code = isPersonaPoolCoverageError(message)
    ? "persona_pool_coverage"
    : null;
  const alreadyHinted =
    message.includes("matraix-persona-1m") ||
    message.includes("Synthesize to fill") ||
    message.includes("does not synthesize");

  return {
    code,
    rawMessage: message,
    showRecoveryHint: code === "persona_pool_coverage" && !alreadyHinted,
  };
}
