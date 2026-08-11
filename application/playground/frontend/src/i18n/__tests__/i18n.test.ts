import { describe, expect, it } from "vitest";

import enPack from "../messages/packs/en-US";
import zhPack from "../messages/packs/zh-CN";
import {
  personaDimensionLabelKey,
  personaSectionLabelKey,
} from "../personaLabelKeys";
import { LOCALE_REGISTRY, localePacks } from "../registry";
import { interpolate, resolveMessage } from "../resolve";

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

  it("has no duplicate keys within each pack", () => {
    expect(new Set(enKeys).size).toBe(enKeys.length);
    expect(new Set(zhKeys).size).toBe(zhKeys.length);
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
      expect(resolveMessage(zhPack, enPack, key)).toBe(zhPack[key] ?? enPack[key]);
    }
  });

  it("records the keys present in zh-CN but not in en-US (documented drift)", () => {
    const enMissingZhKeys = zhKeys.filter((key) => !(key in enPack)).sort();
    expect(enMissingZhKeys).toEqual([
      "shell.home.subtitle",
      "shell.preflight.optionalAdaptersNeedAttention",
      "taskDisplay.title.harborPriceSensitivityHasbroGamingCandyLand",
    ]);
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

  it("lazily loads a non-empty en-US pack via dynamic import", async () => {
    const pack = await localePacks["en-US"]();
    expect(pack).toBeTruthy();
    expect(Object.keys(pack).length).toBeGreaterThan(0);
  });

  it("lazily loads a non-empty zh-CN pack via dynamic import", async () => {
    const pack = await localePacks["zh-CN"]();
    expect(pack).toBeTruthy();
    expect(Object.keys(pack).length).toBeGreaterThan(0);
  });

  it("the dynamically loaded zh-CN pack has identical keys to the static one", async () => {
    const pack = await localePacks["zh-CN"]();
    expect(Object.keys(pack).sort()).toEqual(Object.keys(zhPack).sort());
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
