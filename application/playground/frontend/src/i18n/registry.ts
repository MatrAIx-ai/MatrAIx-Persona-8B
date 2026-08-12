import type { LocaleMeta, MessagePack } from "./types";

/**
 * Locale registry — adding a language means:
 *   1. add a single-locale pack file under messages/packs/<code>.ts
 *   2. register it here (meta + loader)
 * No dual-locale tables anywhere; English stays the source-of-truth pack.
 */
export const LOCALE_REGISTRY = [
  { code: "en-US", label: "English", englishName: "English" },
  { code: "ko-KR", label: "한국어", englishName: "Korean" },
  { code: "zh-CN", label: "简体中文", englishName: "Simplified Chinese" },
  { code: "zh-TW", label: "繁體中文", englishName: "Traditional Chinese" },
  { code: "ja-JP", label: "日本語", englishName: "Japanese" },
  { code: "pt-BR", label: "Português (Brasil)", englishName: "Brazilian Portuguese" },
  { code: "es-ES", label: "Español", englishName: "Spanish" },
] as const satisfies readonly LocaleMeta[];

export type Locale = (typeof LOCALE_REGISTRY)[number]["code"];

/**
 * Lazy per-locale loaders. en-US is loaded eagerly by I18nProvider (default +
 * fallback base); every other locale is fetched on first switch and cached.
 */
export const localePacks = {
  "en-US": () => import("./messages/packs/en-US").then((m) => m.default),
  "ko-KR": () => import("./messages/packs/ko-KR").then((m) => m.default),
  "zh-CN": () => import("./messages/packs/zh-CN").then((m) => m.default),
  "zh-TW": () => import("./messages/packs/zh-TW").then((m) => m.default),
  "ja-JP": () => import("./messages/packs/ja-JP").then((m) => m.default),
  "pt-BR": () => import("./messages/packs/pt-BR").then((m) => m.default),
  "es-ES": () => import("./messages/packs/es-ES").then((m) => m.default),
} satisfies { [Code in Locale]: () => Promise<MessagePack> };
