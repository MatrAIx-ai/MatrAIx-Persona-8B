/**
 * Runtime / persona prompt language (upstream review #3).
 *
 * Separate from the UI locale: this controls the language the persona
 * narrative / system prompt is rendered in. Options:
 *   - follow_ui: resolve from the current UI locale at launch time
 *   - "en" | "zh": explicit override
 * The backend records the resolved language + its source on every run and
 * never trusts the browser locale itself — the frontend resolves follow-UI.
 */

export type PersonaLanguageSetting = "follow_ui" | "en" | "zh";

const STORAGE_KEY = "matraix.personaLanguage";
export const DEFAULT_PERSONA_LANGUAGE: PersonaLanguageSetting = "follow_ui";

export function readPersonaLanguageSetting(): PersonaLanguageSetting {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (value === "en" || value === "zh" || value === "follow_ui") {
      return value;
    }
  } catch {
    /* storage unavailable */
  }
  return DEFAULT_PERSONA_LANGUAGE;
}

export function persistPersonaLanguageSetting(setting: PersonaLanguageSetting): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, setting);
  } catch {
    /* storage unavailable */
  }
}

/** Map a UI locale code to the runtime persona language token. */
export function uiLocaleToLanguage(uiLocale: string): "en" | "zh" {
  return uiLocale === "zh-CN" ? "zh" : "en";
}

export interface LaunchLanguage {
  /** Request-body language: explicit en|zh (null = follow env/default). */
  language: "en" | "zh" | null;
  /** Where the language came from, for the run record. */
  languageSource: "follow_ui" | "explicit" | null;
}

export function resolveLaunchLanguage(
  setting: PersonaLanguageSetting,
  uiLocale: string,
): LaunchLanguage {
  if (setting === "en" || setting === "zh") {
    return { language: setting, languageSource: "explicit" };
  }
  return { language: uiLocaleToLanguage(uiLocale), languageSource: "follow_ui" };
}
