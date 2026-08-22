import { SOURCE_LOCALE, SOURCE_MESSAGES } from "./source";
import type { MessageCatalog, TextDirection } from "./types";

export interface LocaleDefinition<Code extends string = string> {
  code: Code;
  /** Native-script label shown in the locale popover. */
  nativeName: string;
  englishName: string;
  translationStatus?: "source" | "machine-assisted" | "human-reviewed";
  dir: TextDirection;
  fallback: Code | null;
  load: () => Promise<MessageCatalog>;
}

export const LOCALE_REGISTRY = [
  {
    code: SOURCE_LOCALE,
    nativeName: "English",
    englishName: "English",
    translationStatus: "source",
    dir: "ltr",
    fallback: null,
    load: async () => SOURCE_MESSAGES,
  },
  {
    code: "zh-Hans",
    nativeName: "简体中文",
    englishName: "Simplified Chinese",
    translationStatus: "machine-assisted",
    dir: "ltr",
    fallback: SOURCE_LOCALE,
    load: async () => (await import("./messages/zh-Hans.json")).default,
  },
  {
    code: "zh-Hant",
    nativeName: "繁體中文",
    englishName: "Traditional Chinese",
    translationStatus: "machine-assisted",
    dir: "ltr",
    fallback: SOURCE_LOCALE,
    load: async () => (await import("./messages/zh-Hant.json")).default,
  },
  {
    code: "ko",
    nativeName: "한국어",
    englishName: "Korean",
    translationStatus: "machine-assisted",
    dir: "ltr",
    fallback: SOURCE_LOCALE,
    load: async () => (await import("./messages/ko.json")).default,
  },
  {
    code: "ja",
    nativeName: "日本語",
    englishName: "Japanese",
    translationStatus: "machine-assisted",
    dir: "ltr",
    fallback: SOURCE_LOCALE,
    load: async () => (await import("./messages/ja.json")).default,
  },
  {
    code: "es",
    nativeName: "Español",
    englishName: "Spanish",
    translationStatus: "machine-assisted",
    dir: "ltr",
    fallback: SOURCE_LOCALE,
    load: async () => (await import("./messages/es.json")).default,
  },
] as const satisfies readonly LocaleDefinition[];

/** Adding a registry entry extends the UI-locale union automatically. */
export type UiLocale = (typeof LOCALE_REGISTRY)[number]["code"];

export function isUiLocale(value: unknown): value is UiLocale {
  return typeof value === "string" && LOCALE_REGISTRY.some((entry) => entry.code === value);
}

export function getLocaleDefinition(locale: UiLocale): LocaleDefinition<UiLocale> {
  const definition = LOCALE_REGISTRY.find((candidate) => candidate.code === locale);
  if (!definition) throw new Error(`Locale is not registered: ${locale}`);
  return definition;
}
