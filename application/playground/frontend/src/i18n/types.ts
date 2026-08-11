/**
 * Single source of truth for locale codes. Adding a language = add a code
 * here, a single-locale pack under messages/packs/<code>.ts, and a registry
 * entry (registry.ts). No dual-locale tables anywhere.
 */
export const LOCALE_CODES = ["en-US", "zh-CN"] as const;
export type Locale = (typeof LOCALE_CODES)[number];

export interface LocaleMeta {
  code: Locale;
  /** self-name shown in the picker, e.g. "English" / "简体中文" */
  label: string;
  /** English name, shown when the UI itself is English */
  englishName: string;
}

export type MessageValues = Record<string, string | number>;

/** Single-locale pack: flat key -> copy. English is the source-of-truth pack. */
export type MessagePack = Record<string, string>;

export type MessageBundle = Record<Locale, MessagePack>;
