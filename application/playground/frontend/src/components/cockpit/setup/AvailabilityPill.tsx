import { ToneChip } from "./ToneChip";
import { useI18n } from "@/i18n/I18nProvider";

export interface AvailabilityPillProps {
  available?: boolean;
  label?: string;
}

/** Availability badge — green when ready, red when not. */
export function AvailabilityPill({ available, label }: AvailabilityPillProps) {
  const { t } = useI18n();
  if (available === undefined) {
    return (
      <ToneChip tone="warn" showDot pulseDot>
      {label ?? t("setup.status.checking", "Checking…")}
      </ToneChip>
    );
  }

  if (available) {
    return (
      <ToneChip tone="secondary" showDot>
      {label ?? t("setup.status.available", "Available")}
      </ToneChip>
    );
  }

  return (
    <ToneChip tone="danger" showDot>
    {label ?? t("setup.status.unavailable", "Unavailable")}
    </ToneChip>
  );
}
