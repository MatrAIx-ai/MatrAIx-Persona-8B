import { createIntl, createIntlCache } from "react-intl";
import { describe, expect, it } from "vitest";

import { SOURCE_MESSAGES } from "@/i18n/source";
import type { MessageKey } from "@/i18n/types";
import { classifyCockpitRunError } from "@/lib/harborCockpitMappers";
import { localizeCockpitRunError } from "../cockpitRunErrorPresentation";

const intl = createIntl(
  { locale: "en-US", messages: SOURCE_MESSAGES },
  createIntlCache(),
);
const t = (key: MessageKey) => intl.formatMessage({ id: key });

describe("cockpit run-error presentation", () => {
  it("uses the English catalog for a known Harbor artifact error", () => {
    const error = classifyCockpitRunError(
      "Trial output artifacts not found after the worker exited.",
    );

    expect(error).toEqual({
      code: "trial_output_artifacts_missing",
      rawMessage: "Trial output artifacts not found after the worker exited.",
    });
    expect(localizeCockpitRunError(error, t)).toBe(
      "The trial finished but no output was saved. The agent may have crashed before submitting results.",
    );
  });

  it("leaves an unrecognized backend error byte-for-byte intact", () => {
    const raw = "ProviderError: model reply failed\nrequest_id=req-42";
    const error = classifyCockpitRunError(raw);

    expect(error).toEqual({ code: null, rawMessage: raw });
    expect(localizeCockpitRunError(error, t)).toBe(raw);
  });

  it.each([
    ["Trial failed.", "eval.errors.trialFailed"],
    ["Batch run failed.", "eval.errors.batchRunFailed"],
    ["This run is taking longer than expected.", "eval.errors.runTimeout"],
    [
      "Run stopped. Reset to change setup and launch again.",
      "eval.errors.runStoppedReset",
    ],
    [
      "Run finished with no conversation turns.",
      "eval.errors.emptyConversation",
    ],
    [
      "Run finished without producing a trial.",
      "eval.errors.missingTrial",
    ],
  ])("localizes the client fallback %s", (raw, messageKey) => {
    const error = classifyCockpitRunError(raw);
    expect(error?.code).not.toBeNull();
    expect(localizeCockpitRunError(error, ((key) => key) as typeof t)).toBe(
      messageKey,
    );
  });
});
