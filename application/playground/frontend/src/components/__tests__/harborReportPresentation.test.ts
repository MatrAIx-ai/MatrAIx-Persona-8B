import { describe, expect, it } from "vitest";

import type { I18nContextValue } from "@/i18n/I18nProvider";
import {
  crossFacetReasonPhrase,
  humanizeAnalysisStatus,
  humanizeAnalysisTitle,
  humanizeFacetLabel,
  likertPointLabel,
} from "../harborReportPresentation";

const t = ((key, values) => {
  const serializedValues = values
    ? Object.entries(values)
        .map(([name, value]) => `${name}=${String(value)}`)
        .join(",")
    : "";
  return `[${key}${serializedValues ? `:${serializedValues}` : ""}]`;
}) as I18nContextValue["t"];

describe("Harbor report presentation", () => {
  it("localizes generated report labels while preserving task-owned text", () => {
    expect(humanizeFacetLabel(null, null, t)).toBe("[reports.facet.explanation]");
    expect(humanizeFacetLabel(null, "task_outcome.primary.outcome_status", t)).toBe(
      "[reports.context.taskOutcome]",
    );
    expect(crossFacetReasonPhrase("outcome_reason", t)).toBe(
      "[reports.analysis.reasonsForResult]",
    );
    expect(humanizeAnalysisTitle("Outcome reason by outcome status", t)).toBe(
      "[reports.analysis.whyResultBy:group=[reports.context.taskOutcome]]",
    );
    expect(humanizeAnalysisStatus("queued", t)).toBe("[reports.status.queued]");
    expect(humanizeAnalysisStatus("completed", t)).toBe("[reports.status.ready]");
    expect(likertPointLabel(1, undefined, { min: 1, max: 7 }, t)).toBe(
      "[reports.likert.low]",
    );
    expect(likertPointLabel(7, undefined, { min: 1, max: 7 }, t)).toBe(
      "[reports.likert.high]",
    );
    expect(humanizeFacetLabel("Would you use this task again?", "task_prompt", t)).toBe(
      "Would you use this task again?",
    );
  });
});
