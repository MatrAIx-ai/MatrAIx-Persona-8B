import { SOURCE_LOCALE, SOURCE_MESSAGES } from "./source";
import type { MessageCatalog, TextDirection } from "./types";

export interface LocaleDefinition<Code extends string = string> {
  code: Code;
  /** Native-script label shown in the locale popover. */
  nativeName: string;
  englishName: string;
  dir: TextDirection;
  fallback: Code | null;
  load: () => Promise<MessageCatalog>;
}

export const LOCALE_REGISTRY = [
  {
    code: SOURCE_LOCALE,
    nativeName: "English",
    englishName: "English",
    dir: "ltr",
    fallback: null,
    load: async () => SOURCE_MESSAGES,
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
