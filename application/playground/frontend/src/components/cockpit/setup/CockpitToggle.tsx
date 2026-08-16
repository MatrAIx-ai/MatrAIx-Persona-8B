import { useI18n } from "@/i18n/I18nProvider";

import { FOCUS_RING } from "../cockpitShared";

export interface CockpitToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
  /** Show spinner + indeterminate bar while an async start is in flight. */
  busy?: boolean;
  busyLabel?: string;
}

export function CockpitToggle({
  checked,
  onChange,
  label,
  description,
  disabled,
  busy = false,
  busyLabel,
}: CockpitToggleProps) {
  const { t } = useI18n();
  const resolvedBusyLabel = busyLabel ?? t("cockpitSetup.status.starting");

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-[14px] font-semibold text-text-main">{label}</p>
            {busy && (
              <span
                className="inline-block h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-primary/25 border-t-primary"
                aria-hidden
              />
            )}
          </div>
          {(busy || description) && (
            <p className="mt-0.5 text-[12px] leading-snug text-text-dim">
              {busy ? resolvedBusyLabel : description}
            </p>
          )}
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          aria-busy={busy || undefined}
          disabled={disabled}
          onClick={() => onChange(!checked)}
          className={`relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING} ${
            checked || busy ? "bg-primary" : "bg-outline/55"
          }`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-[left] duration-200 ${
              checked || busy ? "left-[1.35rem]" : "left-0.5"
            }`}
          />
        </button>
      </div>
      {busy && (
        <div
          className="h-1 overflow-hidden rounded-full bg-outline/35"
          role="progressbar"
          aria-valuetext={resolvedBusyLabel}
        >
          <div className="h-full w-2/5 animate-cockpit-indeterminate rounded-full bg-primary" />
        </div>
      )}
    </div>
  );
}
