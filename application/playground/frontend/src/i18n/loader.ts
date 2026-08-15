import { LOCALE_REGISTRY, type LocaleDefinition, type UiLocale } from "./registry";
import { SOURCE_LOCALE, SOURCE_MESSAGES } from "./source";
import type { MessageCatalog } from "./types";

export interface LocalePackLoader<Code extends string> {
  load: (locale: Code) => Promise<MessageCatalog>;
  hasCached: (locale: Code) => boolean;
}

/**
 * Cache completed packs and deduplicate concurrent requests per locale.
 * Rejections are not cached, so a later selection can retry.
 */
export function createLocalePackLoader<Code extends string>(
  definitions: readonly LocaleDefinition<Code>[],
  preload: ReadonlyMap<Code, MessageCatalog> = new Map(),
): LocalePackLoader<Code> {
  const cache = new Map(preload);
  const inflight = new Map<Code, Promise<MessageCatalog>>();

  return {
    hasCached: (locale) => cache.has(locale),
    load: async (locale) => {
      const cached = cache.get(locale);
      if (cached) return cached;

      const pending = inflight.get(locale);
      if (pending) return pending;

      const definition = definitions.find((candidate) => candidate.code === locale);
      if (!definition) throw new Error(`Locale is not registered: ${locale}`);

      const request = definition
        .load()
        .then((messages) => {
          cache.set(locale, messages);
          return messages;
        })
        .finally(() => inflight.delete(locale));
      inflight.set(locale, request);
      return request;
    },
  };
}

/** Resolve the registry-declared fallback chain, then let the selected pack win. */
export async function loadLocaleWithFallback<Code extends string>(
  locale: Code,
  definitions: readonly LocaleDefinition<Code>[],
  loader: LocalePackLoader<Code>,
  seen: ReadonlySet<Code> = new Set(),
): Promise<MessageCatalog> {
  if (seen.has(locale)) throw new Error(`Locale fallback cycle includes: ${locale}`);
  const definition = definitions.find((candidate) => candidate.code === locale);
  if (!definition) throw new Error(`Locale is not registered: ${locale}`);

  const nextSeen = new Set(seen).add(locale);
  const fallbackMessages = definition.fallback
    ? await loadLocaleWithFallback(definition.fallback, definitions, loader, nextSeen)
    : {};
  const selectedMessages = await loader.load(locale);
  return { ...fallbackMessages, ...selectedMessages };
}

export interface LatestRequestGuard {
  begin: () => number;
  isCurrent: (requestId: number) => boolean;
}

/** Prevent a slower, stale locale request from replacing a newer selection. */
export function createLatestRequestGuard(): LatestRequestGuard {
  let currentRequestId = 0;
  return {
    begin: () => ++currentRequestId,
    isCurrent: (requestId) => requestId === currentRequestId,
  };
}

export const localePackLoader = createLocalePackLoader<UiLocale>(
  LOCALE_REGISTRY,
  new Map([[SOURCE_LOCALE, SOURCE_MESSAGES]]),
);

export function loadRegisteredLocale(locale: UiLocale): Promise<MessageCatalog> {
  return loadLocaleWithFallback(locale, LOCALE_REGISTRY, localePackLoader);
}
