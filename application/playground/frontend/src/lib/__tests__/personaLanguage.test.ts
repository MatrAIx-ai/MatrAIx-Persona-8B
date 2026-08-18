import { describe, expect, it } from "vitest";

import { LOCALE_REGISTRY } from "@/i18n/registry";
import { SOURCE_LOCALE } from "@/i18n/source";
import {
  resolveLaunchLanguage,
  uiLocaleToLanguage,
  withLaunchLanguage,
} from "../personaLanguage";

describe("persona/runtime language launch mapping", () => {
  it("derives the runtime language from each locale registry entry", () => {
    for (const entry of LOCALE_REGISTRY) {
      expect(uiLocaleToLanguage(entry.code)).toBe(entry.personaLanguage);
    }
  });

  it("falls back to the English registry entry for an unknown UI locale", () => {
    expect(uiLocaleToLanguage("future-locale")).toBe("en");
    expect(uiLocaleToLanguage("future-locale")).toBe(uiLocaleToLanguage(SOURCE_LOCALE));
  });

  it("records follow_ui provenance in the launch body", () => {
    expect(resolveLaunchLanguage(SOURCE_LOCALE)).toEqual({
      language: "en",
      languageSource: "follow_ui",
    });
  });

  it("adds language fields without changing the shared task payload", () => {
    const body = {
      taskPath: "application/tasks/example-survey_product-feedback",
      personaIds: ["0042"],
      nConcurrentTrials: 1,
    };

    expect(withLaunchLanguage(body, SOURCE_LOCALE)).toEqual({
      ...body,
      language: "en",
      languageSource: "follow_ui",
    });
    expect(body).toEqual({
      taskPath: "application/tasks/example-survey_product-feedback",
      personaIds: ["0042"],
      nConcurrentTrials: 1,
    });
  });

  it("overwrites stale language fields so UI-derived provenance wins at launch", () => {
    expect(
      withLaunchLanguage(
        { taskPath: "task", language: "stale", languageSource: "explicit" },
        SOURCE_LOCALE,
      ),
    ).toMatchObject({ language: "en", languageSource: "follow_ui" });
  });
});
