import { useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import {
  persistPersonaLanguageSetting,
  readPersonaLanguageSetting,
  uiLocaleToLanguage,
  type PersonaLanguageSetting,
} from "@/lib/personaLanguage";

/**
 * Runtime / persona prompt language setting (upstream review #3):
 * Follow UI plus every canonical runtime language exposed by the UI locale registry.
 * Independent of the UI locale picker.
 */
export function PersonaLanguagePicker() {
  const { t, locales } = useI18n();
  const [setting, setSetting] = useState<PersonaLanguageSetting>(() =>
    readPersonaLanguageSetting(),
  );

  const options: Array<{ value: PersonaLanguageSetting; label: string }> = [
    { value: "follow_ui", label: t("personaLanguage.followUi", "Follow UI") },
    ...locales.map((meta) => ({
      value: uiLocaleToLanguage(meta.code),
      label: meta.label,
    })),
  ];

  return (
    <label className="inline-flex items-center gap-1.5 text-[13px] text-text-variant">
      <span className="whitespace-nowrap">
        {t("personaLanguage.label", "Persona language")}
      </span>
      <select
        value={setting}
        onChange={(event) => {
          const next = event.target.value as PersonaLanguageSetting;
          setSetting(next);
          persistPersonaLanguageSetting(next);
        }}
        className="rounded-md glass-tile border border-white/10 bg-transparent px-2 py-1 text-[13px] text-text-main outline-none transition-colors hover:border-white/20 focus:border-accent/50"
        aria-label={t("personaLanguage.label", "Persona language")}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
