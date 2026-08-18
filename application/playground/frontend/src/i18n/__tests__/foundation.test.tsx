// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createIntl, createIntlCache } from "react-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LocalePopover } from "@/components/LocalePopover";
import { I18nProvider, useI18n } from "../I18nProvider";
import {
  createLatestRequestGuard,
  createLocalePackLoader,
  loadLocaleWithFallback,
} from "../loader";
import type { LocaleDefinition } from "../registry";
import { SOURCE_LOCALE, SOURCE_MESSAGES, withEnglishFallback } from "../source";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  document.documentElement.lang = "";
  document.documentElement.dir = "";
});

describe("ICU MessageFormat", () => {
  it("supports plural rules and language-dependent word order", () => {
    const intl = createIntl(
      {
        locale: "en-US",
        messages: {
          count: "{count, plural, one {# persona} other {# personas}} selected",
          order: "{subject} completed {object}",
        },
      },
      createIntlCache(),
    );

    expect(intl.formatMessage({ id: "count" }, { count: 1 })).toBe("1 persona selected");
    expect(intl.formatMessage({ id: "count" }, { count: 3 })).toBe("3 personas selected");
    expect(intl.formatMessage({ id: "order" }, { subject: "Ada", object: "the run" })).toBe(
      "Ada completed the run",
    );
  });
});

describe("catalog fallback", () => {
  it("fills omitted optional keys from English", () => {
    expect(withEnglishFallback({ "locale.current": "Active locale" })["locale.english"]).toBe(
      "English",
    );
  });
});

describe("locale loading", () => {
  it("deduplicates concurrent loads and caches the result", async () => {
    const load = vi.fn(async () => ({ "locale.english": "English" }));
    const definitions: LocaleDefinition<"en-US">[] = [
      {
        code: "en-US",
        nativeName: "English",
        englishName: "English",
        personaLanguage: "en",
        dir: "ltr",
        fallback: null,
        load,
      },
    ];
    const loader = createLocalePackLoader(definitions);

    const [first, second] = await Promise.all([loader.load("en-US"), loader.load("en-US")]);
    expect(first).toBe(second);
    expect(load).toHaveBeenCalledTimes(1);
    await loader.load("en-US");
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("lets only the latest request commit", () => {
    const guard = createLatestRequestGuard();
    const slow = guard.begin();
    const fast = guard.begin();
    expect(guard.isCurrent(slow)).toBe(false);
    expect(guard.isCurrent(fast)).toBe(true);
  });

  it("applies the registry fallback chain before selected messages", async () => {
    type TestLocale = "en-US" | "fr" | "fr-CA";
    const packs = {
      "en-US": { "locale.current": "Current language", "locale.english": "English" },
      fr: { "locale.current": "Langue actuelle" },
      "fr-CA": { "locale.english": "Anglais canadien" },
    } as const;
    const definitions: LocaleDefinition<TestLocale>[] = [
      { code: "en-US", nativeName: "English", englishName: "English", personaLanguage: "en", dir: "ltr", fallback: null, load: async () => packs["en-US"] },
      { code: "fr", nativeName: "Français", englishName: "French", personaLanguage: "en", dir: "ltr", fallback: "en-US", load: async () => packs.fr },
      { code: "fr-CA", nativeName: "Français (Canada)", englishName: "Canadian French", personaLanguage: "en", dir: "ltr", fallback: "fr", load: async () => packs["fr-CA"] },
    ];
    const loader = createLocalePackLoader(definitions);

    await expect(loadLocaleWithFallback("fr-CA", definitions, loader)).resolves.toMatchObject({
      "locale.current": "Langue actuelle",
      "locale.english": "Anglais canadien",
    });
  });
});

describe("provider and locale popover", () => {
  it("renders a complete ICU sentence with styled message parts", () => {
    function ScoreLegend() {
      const { rich } = useI18n();
      return (
        <p>
          {rich("scorecards.scale.legend", {
            green: (parts) => <strong data-band="high">{parts}</strong>,
            amber: (parts) => <strong data-band="mid">{parts}</strong>,
            red: (parts) => <strong data-band="low">{parts}</strong>,
          })}
        </p>
      );
    }

    render(
      <I18nProvider>
        <ScoreLegend />
      </I18nProvider>,
    );
    expect(screen.getByText("green").getAttribute("data-band")).toBe("high");
    expect(screen.getByText("amber").getAttribute("data-band")).toBe("mid");
    expect(screen.getByText("red").getAttribute("data-band")).toBe("low");
    expect(screen.getByText(/Scores read/).textContent).toContain("when it missed.");
  });

  it("syncs html language and direction", async () => {
    render(
      <I18nProvider>
        <div>content</div>
      </I18nProvider>,
    );
    await waitFor(() => expect(document.documentElement.lang).toBe(SOURCE_LOCALE));
    expect(document.documentElement.dir).toBe("ltr");
  });

  it("opens an icon-triggered custom popover", async () => {
    render(
      <I18nProvider>
        <LocalePopover />
      </I18nProvider>,
    );
    const trigger = screen.getByRole("button", { name: SOURCE_MESSAGES["locale.buttonLabel"] });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("dialog", { name: SOURCE_MESSAGES["locale.popoverTitle"] })).toBeTruthy();
    const englishOption = screen.getByRole("button", { name: "English" });
    await waitFor(() => expect(document.activeElement).toBe(englishOption));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("reselects the active locale through the same guarded load path", async () => {
    render(
      <I18nProvider>
        <LocalePopover />
      </I18nProvider>,
    );
    const trigger = screen.getByRole("button", {
      name: SOURCE_MESSAGES["locale.buttonLabel"],
    });
    fireEvent.click(trigger);
    let popoverWasOpenWhenFocusReturned: boolean | null = null;
    const focus = trigger.focus.bind(trigger);
    vi.spyOn(trigger, "focus").mockImplementation(() => {
      popoverWasOpenWhenFocusReturned = screen.queryByRole("dialog") !== null;
      focus();
    });
    fireEvent.click(screen.getByRole("button", { name: "English" }));
    await waitFor(() => expect(window.localStorage.getItem("matraix.uiLocale")).toBe("en-US"));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(trigger));
    expect(popoverWasOpenWhenFocusReturned).toBe(false);
  });

  it("returns focus to the trigger after selecting a locale with the mouse", async () => {
    render(
      <I18nProvider>
        <LocalePopover />
      </I18nProvider>,
    );
    const trigger = screen.getByRole("button", { name: SOURCE_MESSAGES["locale.buttonLabel"] });
    fireEvent.click(trigger);
    const englishOption = screen.getByRole("button", { name: "English" });
    await waitFor(() => expect(document.activeElement).toBe(englishOption));
    fireEvent.click(englishOption);
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });
});
