/**
 * Runtime / persona prompt language (upstream review #3).
 *
 * Separate from the UI locale: this controls the language the persona
 * narrative / system prompt is rendered in. Options:
 *   - follow_ui: resolve from the current UI locale at launch time
 *   - "en" | "ko" | "zh" | "zh-Hant" | "ja" | "pt" | "es": explicit override
 * The backend records the resolved language + its source on every run and
 * never trusts the browser locale itself — the frontend resolves follow-UI.
 */

export type PersonaLanguageCode =
  | "en"
  | "ko"
  | "zh"
  | "zh-Hant"
  | "ja"
  | "pt"
  | "es";
export type PersonaLanguageSetting = "follow_ui" | PersonaLanguageCode;

const STORAGE_KEY = "matraix.personaLanguage";
export const DEFAULT_PERSONA_LANGUAGE: PersonaLanguageSetting = "follow_ui";
const PERSONA_LANGUAGE_CODES = new Set<PersonaLanguageCode>([
  "en",
  "ko",
  "zh",
  "zh-Hant",
  "ja",
  "pt",
  "es",
]);
const UI_LOCALE_LANGUAGE: Record<string, PersonaLanguageCode> = {
  "en-US": "en",
  "ko-KR": "ko",
  "zh-CN": "zh",
  "zh-TW": "zh-Hant",
  "ja-JP": "ja",
  "pt-BR": "pt",
  "es-ES": "es",
};

export function readPersonaLanguageSetting(): PersonaLanguageSetting {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (value === "follow_ui" || PERSONA_LANGUAGE_CODES.has(value as PersonaLanguageCode)) {
      return value as PersonaLanguageSetting;
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
export function uiLocaleToLanguage(uiLocale: string): PersonaLanguageCode {
  return UI_LOCALE_LANGUAGE[uiLocale] ?? "en";
}

export interface LaunchLanguage {
  /** Request-body language: canonical runtime token (null = follow env/default). */
  language: PersonaLanguageCode | null;
  /** Where the language came from, for the run record. */
  languageSource: "follow_ui" | "explicit" | null;
}

export function resolveLaunchLanguage(
  setting: PersonaLanguageSetting,
  uiLocale: string,
): LaunchLanguage {
  if (setting !== "follow_ui") {
    return { language: setting, languageSource: "explicit" };
  }
  return { language: uiLocaleToLanguage(uiLocale), languageSource: "follow_ui" };
}
