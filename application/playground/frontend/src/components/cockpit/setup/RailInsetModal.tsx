import type { ReactNode } from "react";

import { useI18n } from "@/i18n/I18nProvider";
import { FOCUS_RING, Sym } from "../cockpitShared";

export interface RailInsetModalProps {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
}

/** Opaque in-rail detail panel — fills the parent sidebar content area; X-only dismiss. */
export function RailInsetModal({ open, title, subtitle, onClose, children }: RailInsetModalProps) {
  const { t } = useI18n();
  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="absolute inset-0 z-30 flex flex-col overflow-hidden border border-outline/30 bg-surface-lowest shadow-[0_18px_48px_-24px_rgb(0_0_0/0.5)]"
    >
      <div className="flex shrink-0 items-start justify-between gap-3 border-b border-outline bg-surface-low px-4 py-3">
        <div className="min-w-0 flex-1">
          {subtitle && <p className="hud mb-1 text-[11px] uppercase tracking-wide text-primary">{subtitle}</p>}
          <h2 className="font-display text-[15px] font-semibold leading-snug text-text-main">{title}</h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label={t("setup.common.closeDetails", "Close details")}
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-outline bg-surface-high text-text-variant transition hover:border-primary hover:text-text-main ${FOCUS_RING}`}
        >
          <Sym name="close" size={18} />
        </button>
      </div>
      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto bg-surface-lowest px-4 py-4">
        {children}
      </div>
    </div>
  );
}
