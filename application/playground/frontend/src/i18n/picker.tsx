import { useI18n } from "./I18nProvider";
import type { Locale } from "./types";

/**
 * Generic language picker driven by the locale registry (extensible; not a
 * binary toggle). Renders the self-name of each locale.
 */
export function LocalePicker({ compact = false }: { compact?: boolean }) {
  const { locale, setLocale, t, locales } = useI18n();
  return (
    <select
      value={locale}
      onChange={(event) => setLocale(event.target.value as Locale)}
      aria-label={t("shell.locale.picker", "Language")}
      className={
        compact
          ? "h-7 rounded border border-outline bg-surface px-1.5 text-[13px] text-text-main"
          : "h-8 rounded border border-outline bg-surface px-2 text-[14px] text-text-main"
      }
    >
      {locales.map((meta) => (
        <option key={meta.code} value={meta.code}>
          {meta.label}
        </option>
      ))}
    </select>
  );
}
