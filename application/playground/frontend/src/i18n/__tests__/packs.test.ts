import { IntlMessageFormat } from "intl-messageformat";
import { describe, expect, it } from "vitest";

import { LOCALE_REGISTRY } from "../registry";
import { SOURCE_LOCALE, SOURCE_MESSAGES } from "../source";

const SOURCE_KEYS = Object.keys(SOURCE_MESSAGES).sort();
const EXPECTED_OPTIONAL = ["zh-Hans", "zh-Hant", "ko", "ja", "es", "pt-BR"];

describe("optional UI locale packs", () => {
  it("registers lazy-loaded optional locales in popover order", () => {
    const optional = LOCALE_REGISTRY.filter((entry) => entry.code !== SOURCE_LOCALE);
    expect(optional.map((entry) => entry.code)).toEqual(EXPECTED_OPTIONAL);
    for (const entry of optional) {
      expect(entry.fallback).toBe(SOURCE_LOCALE);
      expect(entry.dir).toBe("ltr");
      expect(entry.translationStatus).toBe("machine-assisted");
      expect(entry.nativeName.trim()).not.toBe("");
    }
  });

  it("loads each pack with exact English key parity and ICU-compilable messages", async () => {
    for (const entry of LOCALE_REGISTRY.filter((e) => e.code !== SOURCE_LOCALE)) {
      const pack = await entry.load();
      expect(Object.keys(pack).sort(), entry.code).toEqual(SOURCE_KEYS);
      for (const key of SOURCE_KEYS) {
        const message = pack[key as keyof typeof pack];
        expect(typeof message, `${entry.code} ${key}`).toBe("string");
        if (typeof message !== "string") continue;
        expect(message.trim(), `${entry.code} ${key}`).not.toBe("");
        expect(
          () => new IntlMessageFormat(message, entry.code),
          `${entry.code} ${key}`,
        ).not.toThrow();
      }
    }
  });
});
