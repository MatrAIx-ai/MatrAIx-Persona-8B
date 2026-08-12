/** Locale codes are inferred from the registry so the type axis cannot drift. */
export type Locale = import("./registry").Locale;

export type RuntimePersonaLanguage =
  | "en"
  | "ko"
  | "zh"
  | "zh-Hant"
  | "ja"
  | "pt"
  | "es";

export interface LocaleMeta<Code extends string = string> {
  code: Code;
  /** self-name shown in the picker, e.g. "English" / "简体中文" */
  label: string;
  /** English name, shown when the UI itself is English */
  englishName: string;
  /** Canonical runtime/persona language used when this locale is followed. */
  personaLanguage: RuntimePersonaLanguage;
}

export type MessageValues = Record<string, string | number>;

/** Single-locale pack: flat key -> copy. English is the source-of-truth pack. */
export type MessagePack = Record<string, string>;

export type MessageBundle = Record<Locale, MessagePack>;
