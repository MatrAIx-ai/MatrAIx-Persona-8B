export type Locale = "en-US" | "zh-CN"; // extensible: add a pack + registry entry

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
