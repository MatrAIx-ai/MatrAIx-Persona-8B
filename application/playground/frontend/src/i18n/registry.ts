import type { Locale, LocaleMeta, MessagePack } from "./types";

/**
 * Locale registry — adding a language means:
 *   1. add a single-locale pack file under messages/packs/<code>.ts
 *   2. register it here (meta + loader)
 * No dual-locale tables anywhere; English stays the source-of-truth pack.
 */
export const LOCALE_REGISTRY: LocaleMeta[] = [
  { code: "en-US", label: "English", englishName: "English" },
  { code: "zh-CN", label: "简体中文", englishName: "Simplified Chinese" },
];

/**
 * Lazy per-locale loaders. en-US is loaded eagerly by I18nProvider (default +
 * fallback base); every other locale is fetched on first switch and cached.
 */
export const localePacks: Record<Locale, () => Promise<MessagePack>> = {
  "en-US": () => import("./messages/packs/en-US").then((m) => m.default),
  "zh-CN": () => import("./messages/packs/zh-CN").then((m) => m.default),
};
