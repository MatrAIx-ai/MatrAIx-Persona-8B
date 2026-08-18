/**
 * Resolve the persona/runtime language at the moment a Playground run starts.
 *
 * This is deliberately separate from task content and UI copy. The UI locale
 * is the only input available to the Playground launch path; API/CLI callers
 * may provide their own explicit runtime-language override elsewhere.
 */

import { LOCALE_REGISTRY } from "@/i18n/registry";
import { SOURCE_LOCALE } from "@/i18n/source";
import type { PersonaLanguageCode } from "@/i18n/types";

export type { PersonaLanguageCode } from "@/i18n/types";
export type LaunchLanguageSource = "follow_ui";

export interface LaunchLanguageFields {
  /** Canonical runtime/persona language for the run request. */
  language: PersonaLanguageCode;
  /** Provenance persisted with the run by the backend. */
  languageSource: LaunchLanguageSource;
}

const SOURCE_PERSONA_LANGUAGE =
  LOCALE_REGISTRY.find((entry) => entry.code === SOURCE_LOCALE)?.personaLanguage ?? "en";

/** Map a registered UI locale to its registry-owned runtime language token. */
export function uiLocaleToLanguage(uiLocale: string): PersonaLanguageCode {
  return (
    LOCALE_REGISTRY.find((entry) => entry.code === uiLocale)?.personaLanguage ??
    SOURCE_PERSONA_LANGUAGE
  );
}

/** Resolve the UI-derived language fields captured on every Playground launch. */
export function resolveLaunchLanguage(uiLocale: string): LaunchLanguageFields {
  return {
    language: uiLocaleToLanguage(uiLocale),
    languageSource: "follow_ui",
  };
}

/** Add launch-time language provenance to any shared Harbor request body. */
export function withLaunchLanguage<T extends object>(
  body: T,
  uiLocale: string,
): T & LaunchLanguageFields {
  return {
    ...body,
    ...resolveLaunchLanguage(uiLocale),
  };
}
