import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import enPackModule from "./messages/packs/en-US";
import { localePacks } from "./registry";
import { interpolate, resolveMessage } from "./resolve";
import type { Locale, LocaleMeta, MessagePack, MessageValues } from "./types";

const enPack: MessagePack = enPackModule;

const STORAGE_KEY = "matraix.locale";
const DEFAULT_LOCALE: Locale = "en-US"; // English-first: en is the shipped default

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  /** Locale registry (extensible, drives the picker). */
  locales: readonly LocaleMeta[];
  t: (key: string, fallback?: string, values?: MessageValues) => string;
  formatNumber: (value: number) => string;
  formatDate: (value: Date | number | string, options?: Intl.DateTimeFormatOptions) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function readStoredLocale(): Locale {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    // Validated against the registry, not a hardcoded pair — adding a
    // language only requires a registry entry + pack, not a provider edit.
    return LOCALES.some((l) => l.code === value)
      ? (value as Locale)
      : DEFAULT_LOCALE;
  } catch {
    return DEFAULT_LOCALE;
  }
}

/** Per-locale in-flight loads, so switching locale never reuses another
 * locale's pending request. Cleared when each load settles. */
const inflight = new Map<Locale, Promise<MessagePack>>();

const packCache = new Map<Locale, MessagePack>([["en-US", enPack]]);

function persistLocale(locale: Locale): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    /* storage unavailable */
  }
}

function resetToEnglishFallback(
  requestedRef: { current: Locale },
  setLocaleState: (locale: Locale) => void,
  setPack: (pack: MessagePack) => void,
): void {
  requestedRef.current = DEFAULT_LOCALE;
  setLocaleState(DEFAULT_LOCALE);
  setPack(enPack);
  persistLocale(DEFAULT_LOCALE);
}

/** Load a locale pack through the shared per-locale in-flight map and cache.
 * Both setLocale and the startup restore path go through here, so a locale is
 * never requested twice while its first load is still pending. */
function loadPack(locale: Locale): Promise<MessagePack> {
  const cached = packCache.get(locale);
  if (cached !== undefined) return Promise.resolve(cached);
  const pending = inflight.get(locale);
  if (pending) return pending;
  const request = localePacks[locale]()
    .then((p) => {
      packCache.set(locale, p);
      return p;
    })
    .finally(() => {
      inflight.delete(locale);
    });
  inflight.set(locale, request);
  return request;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale);
  const [pack, setPack] = useState<MessagePack>(enPack);
  // Tracks the *requested* locale across async loads so a stale load result
  // can never overwrite the pack for a newer locale selection.
  const requestedRef = useRef<Locale>(locale);

  // Startup: if the stored locale is not English, load its pack so the UI
  // actually matches the picker instead of silently staying on en-US.
  useEffect(() => {
    const stored = readStoredLocale();
    if (stored === "en-US") return;
    let cancelled = false;
    loadPack(stored)
      .then((p) => {
        if (!cancelled && requestedRef.current === stored) {
          setPack(p);
        }
      })
      .catch(() => {
        // A failed optional pack must not leave the picker claiming a locale
        // whose UI is actually rendered from English.
        if (!cancelled && requestedRef.current === stored) {
          resetToEnglishFallback(requestedRef, setLocaleState, setPack);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const setLocale = useCallback((next: Locale) => {
    if (next === locale && packCache.has(next)) {
      return;
    }
    requestedRef.current = next;
    setLocaleState(next);
    // Keep the UI consistent instantly: fall back to the always-present en-US
    // pack while the target locale loads.
    setPack(enPack);
    const load = loadPack(next);
    load
      .then((p) => {
        // Only apply if this locale is still the one the user asked for
        // (guards against rapid en -> zh -> en switching).
        if (requestedRef.current === next) {
          setPack(p);
        }
      })
      .catch(() => {
        // Keep the selected locale and the rendered pack truthful on failure.
        if (requestedRef.current === next) {
          resetToEnglishFallback(requestedRef, setLocaleState, setPack);
        }
      });
    persistLocale(next);
  }, [locale]);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      locales: LOCALES,
      t: (key, fallback, values) =>
        interpolate(resolveMessage(pack, enPack, key, fallback), values),
      formatNumber: (number) => new Intl.NumberFormat(locale).format(number),
      formatDate: (date, options) => new Intl.DateTimeFormat(locale, options).format(new Date(date)),
    }),
    [locale, setLocale, pack],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used inside I18nProvider");
  }
  return context;
}

// Imported lazily to avoid a cycle with registry.ts.
import { LOCALE_REGISTRY as LOCALES } from "./registry";
