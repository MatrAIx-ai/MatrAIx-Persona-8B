import { useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import {
  persistPersonaLanguageSetting,
  readPersonaLanguageSetting,
  type PersonaLanguageSetting,
} from "@/lib/personaLanguage";

/**
 * Runtime / persona prompt language setting (upstream review #3):
 * Follow UI | English | 简体中文. Independent of the UI locale picker.
 */
export function PersonaLanguagePicker() {
  const { t } = useI18n();
  const [setting, setSetting] = useState<PersonaLanguageSetting>(() =>
    readPersonaLanguageSetting(),
  );

  const options: Array<{ value: PersonaLanguageSetting; label: string }> = [
    { value: "follow_ui", label: t("personaLanguage.followUi", "Follow UI") },
    { value: "en", label: t("personaLanguage.english", "English") },
    { value: "zh", label: t("personaLanguage.chinese", "简体中文") },
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
