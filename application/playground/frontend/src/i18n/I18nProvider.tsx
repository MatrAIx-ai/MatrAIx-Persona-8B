import {
  RawIntlProvider,
  createIntl,
  createIntlCache,
  type IntlShape,
} from "react-intl";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { createLatestRequestGuard, loadRegisteredLocale } from "./loader";
import { getLocaleDefinition, isUiLocale, type UiLocale } from "./registry";
import { SOURCE_LOCALE, SOURCE_MESSAGES, withEnglishFallback } from "./source";
import type { MessageCatalog, MessageKey, MessageValues } from "./types";

const STORAGE_KEY = "matraix.uiLocale";
const intlCache = createIntlCache();

export interface I18nContextValue {
  locale: UiLocale;
  loadingLocale: UiLocale | null;
  loadError: string | null;
  setLocale: (locale: UiLocale) => Promise<void>;
  t: (key: MessageKey, values?: MessageValues) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function readStoredLocale(): UiLocale {
  if (typeof window === "undefined") return SOURCE_LOCALE;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isUiLocale(stored) ? stored : SOURCE_LOCALE;
  } catch {
    return SOURCE_LOCALE;
  }
}

function persistLocale(locale: UiLocale): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // Storage may be disabled. The in-memory selection still works.
  }
}

export function syncDocumentLocale(locale: UiLocale): void {
  if (typeof document === "undefined") return;
  const definition = getLocaleDefinition(locale);
  document.documentElement.lang = definition.code;
  document.documentElement.dir = definition.dir;
}

function makeIntl(locale: UiLocale, messages: MessageCatalog): IntlShape {
  return createIntl(
    {
      locale,
      defaultLocale: SOURCE_LOCALE,
      messages: withEnglishFallback(messages),
      onError: (error) => {
        if (import.meta.env.DEV) console.error(error);
      },
    },
    intlCache,
  );
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setActiveLocale] = useState<UiLocale>(SOURCE_LOCALE);
  const [messages, setMessages] = useState<MessageCatalog>(SOURCE_MESSAGES);
  const [loadingLocale, setLoadingLocale] = useState<UiLocale | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const requestGuard = useRef(createLatestRequestGuard());

  const setLocale = useCallback(async (nextLocale: UiLocale) => {
    const requestId = requestGuard.current.begin();
    setLoadError(null);
    setLoadingLocale(nextLocale);
    try {
      const nextMessages = await loadRegisteredLocale(nextLocale);
      if (!requestGuard.current.isCurrent(requestId)) return;
      setMessages(nextMessages);
      setActiveLocale(nextLocale);
      persistLocale(nextLocale);
    } catch (error) {
      if (!requestGuard.current.isCurrent(requestId)) return;
      setLoadError(error instanceof Error ? error.message : String(error));
    } finally {
      if (requestGuard.current.isCurrent(requestId)) setLoadingLocale(null);
    }
  }, []);

  useEffect(() => {
    const storedLocale = readStoredLocale();
    if (storedLocale !== SOURCE_LOCALE) void setLocale(storedLocale);
  }, [setLocale]);

  useEffect(() => syncDocumentLocale(locale), [locale]);

  const intl = useMemo(() => makeIntl(locale, messages), [locale, messages]);
  const t = useCallback<I18nContextValue["t"]>(
    (key, values) =>
      intl.formatMessage(
        { id: key, defaultMessage: SOURCE_MESSAGES[key] },
        values,
      ) as string,
    [intl],
  );

  const value = useMemo<I18nContextValue>(
    () => ({ locale, loadingLocale, loadError, setLocale, t }),
    [loadError, loadingLocale, locale, setLocale, t],
  );

  return (
    <RawIntlProvider value={intl}>
      <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
    </RawIntlProvider>
  );
}

export function useI18n(): I18nContextValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}
