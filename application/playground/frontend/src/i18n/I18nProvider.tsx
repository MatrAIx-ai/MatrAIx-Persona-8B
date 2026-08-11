import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
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
  locales: LocaleMeta[];
  t: (key: string, fallback?: string, values?: MessageValues) => string;
  formatNumber: (value: number) => string;
  formatDate: (value: Date | number | string, options?: Intl.DateTimeFormatOptions) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function readStoredLocale(): Locale {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "en-US" || value === "zh-CN" ? value : DEFAULT_LOCALE;
  } catch {
    return DEFAULT_LOCALE;
  }
}

/** Cache for lazily-loaded packs (en-US is always present). */
const packCache = new Map<Locale, MessagePack>([["en-US", enPack]]);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale);
  const [pack, setPack] = useState<MessagePack>(enPack);
  const inflight = useRef<Promise<MessagePack> | null>(null);

  const setLocale = useCallback((next: Locale) => {
    if (next === locale && packCache.has(next)) {
      return;
    }
    setLocaleState(next);
    // Keep the UI consistent instantly: fall back to the always-present en-US
    // pack while the target locale loads.
    setPack(enPack);
    const cached = packCache.get(next);
    const load =
      cached !== undefined
        ? Promise.resolve(cached)
        : (inflight.current =
            inflight.current ??
            localePacks[next]().then((p) => {
              packCache.set(next, p);
              return p;
            }));
    inflight.current = load;
    load
      .then((p) => {
        if (localePacks[next]) {
          setPack(p);
        }
      })
      .catch(() => {
        // Load failure: stay on English fallback.
        setPack(enPack);
      });
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage unavailable */
    }
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
