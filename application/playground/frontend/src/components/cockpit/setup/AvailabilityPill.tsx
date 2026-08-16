import { useI18n } from "@/i18n/I18nProvider";

import { ToneChip } from "./ToneChip";

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
        {label ?? t("cockpitSetup.status.checking")}
      </ToneChip>
    );
  }

  if (available) {
    return (
      <ToneChip tone="secondary" showDot>
        {label ?? t("cockpitSetup.status.available")}
      </ToneChip>
    );
  }

  return (
    <ToneChip tone="danger" showDot>
      {label ?? t("cockpitSetup.status.unavailable")}
    </ToneChip>
  );
}
