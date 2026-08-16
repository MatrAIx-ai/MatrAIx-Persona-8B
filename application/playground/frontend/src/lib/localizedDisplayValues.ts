import type { I18nContextValue } from "@/i18n/I18nProvider";

export type Translate = I18nContextValue["t"];

/** Formats a structural boolean at the view boundary. */
export function localizedBooleanLabel(value: boolean, t: Translate): string {
  if (value) return t("runs.yes");
  return t("runs.no");
}

/**
 * Translates stable response enum tokens while leaving arbitrary user/model text
 * to the caller for verbatim display.
 */
export function localizedStructuredChoiceLabel(
  value: string | boolean,
  t: Translate,
): string | null {
  if (typeof value === "boolean") return localizedBooleanLabel(value, t);

  switch (value.trim().toLowerCase()) {
    case "yes":
    case "true":
      return t("runs.yes");
    case "no":
    case "false":
      return t("runs.no");
    case "partially":
      return t("runs.partially");
    case "unsure":
      return t("runs.unsure");
    default:
      return null;
  }
}

/** Translates the stable chat decision enum and leaves unknown decisions alone. */
export function localizedDecisionLabel(
  decision: string,
  t: Translate,
): string | null {
  switch (decision) {
    case "satisfied":
      return t("runs.gotWhatTheyNeeded");
    case "give_up":
      return t("runs.gaveUp");
    default:
      return null;
  }
}
