import { describe, expect, it } from "vitest";

import enPack from "../messages/packs/en-US";
import koPack from "../messages/packs/ko-KR";
import zhPack from "../messages/packs/zh-CN";
import zhTwPack from "../messages/packs/zh-TW";
import jaPack from "../messages/packs/ja-JP";
import ptPack from "../messages/packs/pt-BR";
import esPack from "../messages/packs/es-ES";
import {
  personaDimensionLabelKey,
  personaSectionLabelKey,
} from "../personaLabelKeys";
import { LOCALE_REGISTRY, localePacks } from "../registry";
import { interpolate, resolveMessage } from "../resolve";
import { taskDisplayTitle } from "../../components/cockpit/setup/taskCardLabels";
import {
  persistPersonaLanguageSetting,
  readPersonaLanguageSetting,
  resolveLaunchLanguage,
  uiLocaleToLanguage,
} from "../../lib/personaLanguage";

const NEW_SOURCE_KEYS = [
  "reports.strategy.allocation",
  "reports.strategy.allocationTitle",
  "reports.strategy.perCell",
  "reports.strategy.perCellTitle",
  "setup.filters.axis",
  "setup.filters.axes",
  "setup.filters.filter",
  "setup.filters.filters",
  "setup.filters.stratifyAxes",
  "setup.filters.stratifyHint",
  "setup.persona.allocation",
  "setup.persona.allocationEqualTotal",
  "setup.persona.allocationPerCell",
  "setup.persona.allocationProportional",
] as const;

describe("resolveMessage — fallback chain (pack[key] ?? enPack[key] ?? fallback ?? key)", () => {
  it("returns the zh-CN value when the key exists in the active pack", () => {
    expect(resolveMessage(zhPack, enPack, "shell.home.title")).toBe("行星级");
    expect(resolveMessage(zhPack, enPack, "shell.home.title")).toBe(
      zhPack["shell.home.title"],
    );
  });

  it("falls back to the en-US pack when the key is missing from the active pack", () => {
    const zh: Record<string, string> = { "shared.key": "zh value" };
    const en: Record<string, string> = {
      "shared.key": "en value",
      "en.only": "en-only value",
    };
    expect(resolveMessage(zh, en, "shared.key")).toBe("zh value");
    expect(resolveMessage(zh, en, "en.only")).toBe("en-only value");
  });

  it("falls back to en-US when the active pack is empty (e.g. pre-load state)", () => {
    expect(resolveMessage({}, enPack, "shell.locale.picker")).toBe(
      enPack["shell.locale.picker"],
    );
  });

  it("uses the explicit fallback when both packs miss the key", () => {
    expect(resolveMessage({}, {}, "missing.key", "custom fallback")).toBe(
      "custom fallback",
    );
  });

  it("defaults the fallback to the key itself", () => {
    expect(resolveMessage({}, {}, "some.unknown.key")).toBe("some.unknown.key");
  });

  it("keeps an empty-string translation instead of falling back (?? semantics)", () => {
    const zh: Record<string, string> = { "empty.key": "" };
    const en: Record<string, string> = { "empty.key": "en value" };
    expect(resolveMessage(zh, en, "empty.key")).toBe("");
  });

  it("missing zh keys fall back to en-US (community packs may be incomplete)", () => {
    const zhMissing = Object.keys(enPack).filter((key) => !(key in zhPack));
    // Fallback chain must return the English copy for every key zh lacks.
    const enCopy = enPack as Record<string, string>;
    for (const key of zhMissing.slice(0, 50)) {
      expect(resolveMessage(zhPack, enPack, key)).toBe(enCopy[key]);
    }
    // Drift is allowed and documented, not enforced.
    console.log(
      `[drift] zh-CN missing ${zhMissing.length} of ${Object.keys(enPack).length} en keys`,
    );
  });
});

describe("interpolate", () => {
  it("replaces {name} placeholders with string values", () => {
    expect(interpolate("Hello {name}!", { name: "World" })).toBe("Hello World!");
  });

  it("replaces multiple distinct placeholders in one template", () => {
    expect(interpolate("{a} + {b} = {a}", { a: "x", b: "y" })).toBe("x + y = x");
  });

  it("leaves missing placeholders untouched", () => {
    expect(interpolate("Hello {name}!", {})).toBe("Hello {name}!");
    expect(interpolate("Hello {name}!", { other: "x" })).toBe("Hello {name}!");
  });

  it("stringifies numeric values", () => {
    expect(interpolate("{count} personas", { count: 42 })).toBe("42 personas");
    expect(interpolate("{count} ready", { count: 0 })).toBe("0 ready");
  });

  it("returns the template unchanged when no values are given", () => {
    expect(interpolate("{count} ready", undefined)).toBe("{count} ready");
  });

  it("ignores provided values when the template has no placeholders", () => {
    expect(interpolate("plain text", { anything: "value" })).toBe("plain text");
  });

  it("combines resolveMessage + interpolate exactly like I18nProvider.t", () => {
    const zh: Record<string, string> = {
      "catalog.personaCatalog.ready": "已准备 {count} 个数字人",
    };
    const en: Record<string, string> = {
      "catalog.personaCatalog.ready": "{count} personas ready",
    };
    const message = resolveMessage(zh, en, "catalog.personaCatalog.ready");
    expect(interpolate(message, { count: 3 })).toBe("已准备 3 个数字人");
  });
});

describe("pack integrity and optional locale fallback", () => {
  const enKeys = Object.keys(enPack);
  const zhKeys = Object.keys(zhPack);
  const enMessages: Readonly<Partial<Record<string, string>>> = enPack;
  const zhMessages: Readonly<Partial<Record<string, string>>> = zhPack;
  const zhTwMessages: Readonly<Partial<Record<string, string>>> = zhTwPack;
  const localizedPacks: ReadonlyArray<{
    code: string;
    pack: Readonly<Record<string, string>>;
    extraKeys: readonly string[];
  }> = [
    { code: "ko-KR", pack: koPack, extraKeys: [] },
    {
      code: "zh-TW",
      pack: zhTwPack,
      extraKeys: [
        "shell.home.subtitle",
        "shell.preflight.optionalAdaptersNeedAttention",
        "personaLanguage.traditionalChinese",
      ],
    },
    { code: "ja-JP", pack: jaPack, extraKeys: [] },
    {
      code: "pt-BR",
      pack: ptPack,
      extraKeys: [
        "shell.locale.portuguese",
        "shell.locale.switchToPortuguese",
        "personaLanguage.portuguese",
      ],
    },
    { code: "es-ES", pack: esPack, extraKeys: [] },
  ];

  it("has no duplicate keys within every supported non-English pack", () => {
    expect(new Set(enKeys).size).toBe(enKeys.length);
    for (const { pack } of localizedPacks) {
      const keys = Object.keys(pack);
      expect(new Set(keys).size).toBe(keys.length);
    }
  });

  it("keeps every non-English pack at English source-key parity, with only documented extras", () => {
    for (const { code, pack, extraKeys } of localizedPacks) {
      const keys = Object.keys(pack);
      const expectedKeys = [...enKeys, ...extraKeys].sort();
      expect(keys.sort(), code).toEqual(expectedKeys);
      for (const key of enKeys) {
        expect(pack[key], `${code}:${key}`).toBeTruthy();
        expect(resolveMessage(pack, enPack, key), `${code}:${key}`).toBe(pack[key]);
      }
    }
  });

  it("preserves placeholders for every newly translated source key", () => {
    const placeholders = (message: string) =>
      [...message.matchAll(/\{[^{}]+\}/g)].map((match) => match[0]).sort();
    for (const { code, pack } of localizedPacks) {
      for (const key of NEW_SOURCE_KEYS) {
        expect(placeholders(pack[key] ?? ""), `${code}:${key}`).toEqual(
          placeholders(enMessages[key] ?? ""),
        );
      }
    }
  });

  it("contains representative Korean UI copy and preserves raw platform labels", () => {
    expect(koPack["shell.locale.picker"]).toBe("언어");
    expect(koPack["catalog.catalogDrawer.loaded"]).toBe("로드됨");
    expect(koPack["personaLanguage.followUi"]).toBe("UI 따르기");
    expect(koPack["taskDisplay.os.ios"]).toBe("iOS");
    expect(koPack["cockpit.environment.default.personaModel"]).toBe(
      "anthropic/claude-haiku-4-5",
    );
  });

  it("allows an incomplete optional locale to fall back to en-US", () => {
    const incompleteZh: Record<string, string> = {
      "shell.home.title": "行星级",
    };
    expect(resolveMessage(incompleteZh, enPack, "shell.locale.picker")).toBe(
      enPack["shell.locale.picker"],
    );
  });

  it("resolves every en-US key through the active zh-CN pack or English fallback", () => {
    for (const key of enKeys) {
      expect(resolveMessage(zhPack, enPack, key)).toBe(zhMessages[key] ?? enMessages[key]);
    }
  });

  it("resolves every current en-US key through the zh-TW pack or English fallback", () => {
    for (const key of enKeys) {
      expect(resolveMessage(zhTwPack, enPack, key)).toBe(
        zhTwMessages[key] ?? enMessages[key],
      );
    }
  });

  it("resolves every current en-US key through every registered non-English pack", () => {
    for (const { code, pack } of localizedPacks) {
      for (const key of enKeys) {
        expect(resolveMessage(pack, enPack, key), `${code}:${key}`).toBe(pack[key]);
      }
    }
  });

  it("keeps task title messages identical to English source text", () => {
    for (const key of enKeys.filter((candidate) => candidate.startsWith("taskDisplay.title."))) {
      expect(zhTwMessages[key]).toBe(enMessages[key]);
    }
  });

  it("records the keys present in zh-CN but not in en-US (documented drift)", () => {
    const enMissingZhKeys = zhKeys.filter((key) => !(key in enPack)).sort();
    expect(enMissingZhKeys).toEqual([
      "shell.home.subtitle",
      "shell.preflight.optionalAdaptersNeedAttention",
    ]);
  });
});

describe("task-owned display content", () => {
  it("keeps task titles from the task regardless of the active UI translator", () => {
    const translate = () => "翻译后的任务标题";

    expect(
      taskDisplayTitle(
        "Product Feedback",
        { id: "harbor-product-feedback" },
        translate,
      ),
    ).toBe("Product Feedback");
  });
});

describe("runtime persona language", () => {
  const localeLanguagePairs = [
    ["en-US", "en"],
    ["ko-KR", "ko"],
    ["zh-CN", "zh"],
    ["zh-TW", "zh-Hant"],
    ["ja-JP", "ja"],
    ["pt-BR", "pt"],
    ["es-ES", "es"],
  ] as const;

  it.each(localeLanguagePairs)("maps %s to canonical runtime language %s", (locale, language) => {
    expect(uiLocaleToLanguage(locale)).toBe(language);
    expect(resolveLaunchLanguage("follow_ui", locale)).toEqual({
      language,
      languageSource: "follow_ui",
    });
  });

  it("keeps explicit runtime overrides independent from the UI locale", () => {
    expect(resolveLaunchLanguage("zh-Hant", "en-US")).toEqual({
      language: "zh-Hant",
      languageSource: "explicit",
    });
    expect(resolveLaunchLanguage("zh", "zh-TW")).toEqual({
      language: "zh",
      languageSource: "explicit",
    });
  });

  it("persists the selected runtime language setting", () => {
    const previous = Object.getOwnPropertyDescriptor(globalThis, "window");
    const values = new Map<string, string>();
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: {
        localStorage: {
          getItem: (key: string) => values.get(key) ?? null,
          setItem: (key: string, value: string) => values.set(key, value),
        },
      },
    });
    try {
      persistPersonaLanguageSetting("zh-Hant");
      expect(readPersonaLanguageSetting()).toBe("zh-Hant");
    } finally {
      if (previous) {
        Object.defineProperty(globalThis, "window", previous);
      } else {
        delete (globalThis as { window?: unknown }).window;
      }
    }
  });
});

describe("registry", () => {
  it("every LOCALE_REGISTRY entry has a loader in localePacks", () => {
    for (const meta of LOCALE_REGISTRY) {
      expect(typeof localePacks[meta.code]).toBe("function");
    }
  });

  it("every registry code is present among the localePacks loaders", () => {
    const loaderCodes = Object.keys(localePacks);
    for (const meta of LOCALE_REGISTRY) {
      expect(loaderCodes).toContain(meta.code);
    }
  });

  it("English is the first registered locale (English-first)", () => {
    expect(LOCALE_REGISTRY[0].code).toBe("en-US");
    expect(LOCALE_REGISTRY[0].label).toBe("English");
  });

  it("lazily loads every registered non-empty locale pack with stable keys", async () => {
    for (const meta of LOCALE_REGISTRY) {
      const pack = await localePacks[meta.code]();
      expect(pack, meta.code).toBeTruthy();
      expect(Object.keys(pack).length, meta.code).toBeGreaterThan(0);
    }
  });
});

describe("personaLabelKeys", () => {
  it("maps known dimension ids to personaDisplay keys", () => {
    expect(personaDimensionLabelKey("age")).toBe("personaDisplay.dimension.age");
    expect(personaDimensionLabelKey("age_bracket")).toBe("personaDisplay.dimension.age");
    expect(personaDimensionLabelKey("age bracket")).toBe("personaDisplay.dimension.age");
    expect(personaDimensionLabelKey("life_stage")).toBe("personaDisplay.dimension.lifeStage");
    expect(personaDimensionLabelKey("life stage")).toBe("personaDisplay.dimension.lifeStage");
    expect(personaDimensionLabelKey("region")).toBe("personaDisplay.dimension.region");
    expect(personaDimensionLabelKey("gender")).toBe("personaDisplay.dimension.gender");
    expect(personaDimensionLabelKey("intent")).toBe("personaDisplay.dimension.intent");
  });

  it("maps known section ids to personaDisplay keys", () => {
    expect(personaSectionLabelKey("demographics")).toBe("personaDisplay.section.demographics");
    expect(personaSectionLabelKey("psychology")).toBe("personaDisplay.section.psychology");
    // '&' is normalized to "and" before lookup.
    expect(personaSectionLabelKey("behavior & interaction")).toBe(
      "personaDisplay.section.behaviorInteraction",
    );
  });

  it("matches by label when the id is unknown", () => {
    expect(personaSectionLabelKey(undefined, "Lifestyle & Health")).toBe(
      "personaDisplay.section.lifestyleHealth",
    );
    expect(personaDimensionLabelKey(undefined, "Age")).toBe("personaDisplay.dimension.age");
  });

  it("returns undefined for unknown ids", () => {
    expect(personaDimensionLabelKey("does_not_exist")).toBeUndefined();
    expect(personaSectionLabelKey("does_not_exist")).toBeUndefined();
    expect(personaDimensionLabelKey(undefined, undefined)).toBeUndefined();
  });
});
