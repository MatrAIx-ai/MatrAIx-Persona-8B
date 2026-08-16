/** Normalize Harbor token/cost receipts for Playground UI and PDF meta. */

export type LlmUsageView = {
  nInputTokens?: number | null;
  nOutputTokens?: number | null;
  nCacheTokens?: number | null;
  costUsd?: number | null;
};

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function firstNumber(record: Record<string, unknown>, ...keys: string[]): number | null {
  for (const key of keys) {
    const value = asNumber(record[key]);
    if (value != null) return value;
  }
  return null;
}

function usagePayload(parts: {
  nInputTokens: number | null;
  nOutputTokens: number | null;
  nCacheTokens: number | null;
  costUsd: number | null;
}): LlmUsageView | null {
  const usage: LlmUsageView = {};
  if (parts.nInputTokens != null) usage.nInputTokens = parts.nInputTokens;
  if (parts.nOutputTokens != null) usage.nOutputTokens = parts.nOutputTokens;
  if (parts.nCacheTokens != null) usage.nCacheTokens = parts.nCacheTokens;
  if (parts.costUsd != null) usage.costUsd = parts.costUsd;
  return hasUsage(usage) ? usage : null;
}

export function hasUsage(usage: LlmUsageView | null | undefined): boolean {
  if (!usage) return false;
  return (
    usage.nInputTokens != null
    || usage.nOutputTokens != null
    || usage.nCacheTokens != null
    || usage.costUsd != null
  );
}

export function usageFromAgentContext(raw: unknown): LlmUsageView | null {
  if (!raw || typeof raw !== "object") return null;
  const ctx = raw as Record<string, unknown>;
  return usagePayload({
    nInputTokens: firstNumber(ctx, "n_input_tokens", "nInputTokens"),
    nOutputTokens: firstNumber(ctx, "n_output_tokens", "nOutputTokens"),
    nCacheTokens: firstNumber(ctx, "n_cache_tokens", "nCacheTokens"),
    costUsd: firstNumber(ctx, "cost_usd", "costUsd"),
  });
}

function sumNumbers(values: Array<number | null>): number | null {
  const present = values.filter((value): value is number => value != null);
  if (present.length === 0) return null;
  return present.reduce((acc, value) => acc + value, 0);
}

/** Aggregate usage from a Harbor trial ``result.json`` payload. */
export function usageFromTrialResult(raw: unknown): LlmUsageView | null {
  if (!raw || typeof raw !== "object") return null;
  const result = raw as Record<string, unknown>;
  const direct = usageFromAgentContext(result.agent_result);
  if (direct) return direct;

  const steps = Array.isArray(result.step_results) ? result.step_results : [];
  const contexts = steps
    .map((step) =>
      step && typeof step === "object"
        ? (step as Record<string, unknown>).agent_result
        : null,
    )
    .filter(Boolean);
  if (contexts.length === 0) return null;

  const parsed = contexts.map((ctx) => usageFromAgentContext(ctx));
  return usagePayload({
    nInputTokens: sumNumbers(parsed.map((u) => u?.nInputTokens ?? null)),
    nOutputTokens: sumNumbers(parsed.map((u) => u?.nOutputTokens ?? null)),
    nCacheTokens: sumNumbers(parsed.map((u) => u?.nCacheTokens ?? null)),
    costUsd: sumNumbers(parsed.map((u) => u?.costUsd ?? null)),
  });
}

/** Extract rolled-up usage from a Harbor job ``result.json`` payload. */
export function usageFromJobResult(raw: unknown): LlmUsageView | null {
  if (!raw || typeof raw !== "object") return null;
  const result = raw as Record<string, unknown>;
  const stats = result.stats;
  if (!stats || typeof stats !== "object") return null;
  return usageFromAgentContext(stats);
}

/** Coerce a debrief ``usage`` object (already camelCase) or raw agent context. */
export function asLlmUsage(raw: unknown): LlmUsageView | null {
  const fromCamel = usageFromAgentContext(raw);
  if (fromCamel) return fromCamel;
  if (!raw || typeof raw !== "object") return null;
  return usagePayload({
    nInputTokens: firstNumber(raw as Record<string, unknown>, "nInputTokens"),
    nOutputTokens: firstNumber(raw as Record<string, unknown>, "nOutputTokens"),
    nCacheTokens: firstNumber(raw as Record<string, unknown>, "nCacheTokens"),
    costUsd: firstNumber(raw as Record<string, unknown>, "costUsd"),
  });
}

export function formatCostUsd(value: number): string {
  if (Math.abs(value) >= 1) return `$${value.toFixed(2)}`;
  if (Math.abs(value) >= 0.01) return `$${value.toFixed(3)}`;
  return `$${value.toFixed(4)}`;
}

export function formatTokenCount(value: number): string {
  return Math.round(value).toLocaleString();
}

/** Compact one-line summary for tooltips / dense bylines. */
export function usageCompactLine(usage: LlmUsageView | null | undefined): string | null {
  if (!hasUsage(usage)) return null;
  const bits: string[] = [];
  if (usage?.costUsd != null) bits.push(formatCostUsd(usage.costUsd));
  const tokenBits: string[] = [];
  if (usage?.nInputTokens != null) tokenBits.push(`${formatTokenCount(usage.nInputTokens)} in`);
  if (usage?.nOutputTokens != null) tokenBits.push(`${formatTokenCount(usage.nOutputTokens)} out`);
  if (usage?.nCacheTokens != null && usage.nCacheTokens > 0) {
    tokenBits.push(`${formatTokenCount(usage.nCacheTokens)} cache`);
  }
  if (tokenBits.length) bits.push(tokenBits.join(" · "));
  return bits.length ? bits.join(" · ") : null;
}

/** Compact cost-first cell for dense trial lists (full detail stays in title). */
export function usageListPrimary(usage: LlmUsageView | null | undefined): string | null {
  if (!hasUsage(usage)) return null;
  if (usage?.costUsd != null) return formatCostUsd(usage.costUsd);
  if (usage?.nInputTokens != null) return `${formatTokenCount(usage.nInputTokens)} in`;
  if (usage?.nOutputTokens != null) return `${formatTokenCount(usage.nOutputTokens)} out`;
  return null;
}

/** Rows for a small usage table on trial debrief. */
export function usageTableRows(
  usage: LlmUsageView | null | undefined,
): Array<{ label: string; value: string }> {
  if (!hasUsage(usage)) return [];
  const rows: Array<{ label: string; value: string }> = [];
  if (usage?.costUsd != null) rows.push({ label: "Cost", value: formatCostUsd(usage.costUsd) });
  if (usage?.nInputTokens != null) {
    rows.push({ label: "Input", value: formatTokenCount(usage.nInputTokens) });
  }
  if (usage?.nOutputTokens != null) {
    rows.push({ label: "Output", value: formatTokenCount(usage.nOutputTokens) });
  }
  if (usage?.nCacheTokens != null && usage.nCacheTokens > 0) {
    rows.push({ label: "Cache", value: formatTokenCount(usage.nCacheTokens) });
  }
  return rows;
}

export function usageMetaLines(usage: LlmUsageView | null | undefined): string[] {
  if (!hasUsage(usage)) return [];
  const lines: string[] = [];
  if (usage?.costUsd != null) lines.push(`Cost: ${formatCostUsd(usage.costUsd)}`);
  const bits: string[] = [];
  if (usage?.nInputTokens != null) bits.push(`${formatTokenCount(usage.nInputTokens)} in`);
  if (usage?.nOutputTokens != null) bits.push(`${formatTokenCount(usage.nOutputTokens)} out`);
  if (usage?.nCacheTokens != null && usage.nCacheTokens > 0) {
    bits.push(`${formatTokenCount(usage.nCacheTokens)} cache`);
  }
  if (bits.length) lines.push(`Tokens: ${bits.join(" · ")}`);
  return lines;
}
