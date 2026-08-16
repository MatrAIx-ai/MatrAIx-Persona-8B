import { describe, expect, it } from "vitest";

import type { I18nContextValue } from "@/i18n/I18nProvider";
import {
  localizedBooleanLabel,
  localizedDecisionLabel,
  localizedStructuredChoiceLabel,
} from "../localizedDisplayValues";
import { formatSurveyTrajectoryValue } from "../surveyDisplay";

const t = ((key: string) => `translated:${key}`) as I18nContextValue["t"];

describe("localized display values", () => {
  it("formats a structured boolean through the active translator", () => {
    expect(localizedBooleanLabel(true, t)).toBe("translated:runs.yes");
    expect(localizedBooleanLabel(false, t)).toBe("translated:runs.no");
  });

  it("translates only recognized self-report choice tokens", () => {
    expect(localizedStructuredChoiceLabel("yes", t)).toBe(
      "translated:runs.yes",
    );
    expect(localizedStructuredChoiceLabel("false", t)).toBe(
      "translated:runs.no",
    );
    expect(localizedStructuredChoiceLabel("Partially", t)).toBe(
      "translated:runs.partially",
    );
    expect(localizedStructuredChoiceLabel("unsure", t)).toBe(
      "translated:runs.unsure",
    );
    expect(localizedStructuredChoiceLabel("The answer is yes", t)).toBeNull();
  });

  it("translates known chat outcome decisions without rewriting unknown data", () => {
    expect(localizedDecisionLabel("satisfied", t)).toBe(
      "translated:runs.gotWhatTheyNeeded",
    );
    expect(localizedDecisionLabel("give_up", t)).toBe(
      "translated:runs.gaveUp",
    );
    expect(localizedDecisionLabel("escalated", t)).toBeNull();
  });

  it("translates only a structured survey boolean and preserves raw answers", () => {
    expect(formatSurveyTrajectoryValue(true, t)).toBe("translated:runs.yes");
    expect(formatSurveyTrajectoryValue("Yes", t)).toBe("Yes");
    expect(formatSurveyTrajectoryValue(["Yes", false], t)).toBe(
      "Yes, false",
    );
  });
});
