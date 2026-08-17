import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useI18n } from "@/i18n/I18nProvider";
import { LOCALE_REGISTRY } from "@/i18n/registry";
import { FOCUS_RING, Sym } from "./cockpit/cockpitShared";

export function LocalePopover() {
  const { locale, loadingLocale, loadError, setLocale, t } = useI18n();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const firstOptionRef = useRef<HTMLButtonElement>(null);
  const restoreFocusRef = useRef(false);
  const [position, setPosition] = useState({ left: 12, top: 56 });

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const width = 224;
    const panelHeight = panelRef.current?.getBoundingClientRect().height || 196;
    const margin = 12;
    const alignToLogicalEnd = document.documentElement.dir !== "rtl";
    const preferredLeft = alignToLogicalEnd ? rect.right - width : rect.left;
    const left = Math.min(window.innerWidth - width - margin, Math.max(margin, preferredLeft));
    const below = rect.bottom + 8;
    const top =
      below + panelHeight <= window.innerHeight - margin
        ? below
        : Math.max(margin, rect.top - panelHeight - 8);
    setPosition({ left, top });
  }, []);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !panelRef.current?.contains(target)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, updatePosition]);

  useEffect(() => {
    if (!open) return;
    updatePosition();
    firstOptionRef.current?.focus();
  }, [open, updatePosition]);

  useEffect(() => {
    if (open || !restoreFocusRef.current) return;
    restoreFocusRef.current = false;
    const raf = requestAnimationFrame(() => triggerRef.current?.focus());
    return () => cancelAnimationFrame(raf);
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label={t("locale.buttonLabel")}
        title={t("locale.buttonLabel")}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="locale-popover"
        aria-busy={loadingLocale !== null}
        className={`nasa-glass-pill grid h-9 w-9 flex-none place-items-center rounded-full text-text-variant transition hover:bg-surface-high/40 hover:text-text-main active:scale-95 ${FOCUS_RING}`}
      >
        <Sym
          name={loadingLocale ? "progress_activity" : "language"}
          size={18}
          className={loadingLocale ? "animate-spin" : ""}
        />
      </button>

      {open
        ? createPortal(
            <div
              id="locale-popover"
              ref={panelRef}
              role="dialog"
              aria-label={t("locale.popoverTitle")}
              style={{ left: position.left, top: position.top }}
              className="pop-in fixed z-50 max-h-[calc(100vh-1.5rem)] w-56 overflow-y-auto custom-scrollbar rounded-xl border border-outline bg-surface-lowest p-2 shadow-2xl"
            >
              <p className="px-3 pb-2 pt-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-text-variant">
                {t("locale.popoverTitle")}
              </p>
              <div className="space-y-1">
                {LOCALE_REGISTRY.map((definition) => {
                  const active = definition.code === locale;
                  const loading = definition.code === loadingLocale;
                  return (
                    <button
                      ref={definition.code === LOCALE_REGISTRY[0].code ? firstOptionRef : undefined}
                      key={definition.code}
                      type="button"
                      lang={definition.code}
                      dir={definition.dir}
                      disabled={loading}
                      aria-current={active ? "true" : undefined}
                      onClick={() => {
                        void setLocale(definition.code);
                        restoreFocusRef.current = true;
                        setOpen(false);
                      }}
                      className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-start text-sm transition ${FOCUS_RING} ${
                        active
                          ? "bg-primary/12 font-semibold text-primary"
                          : "text-text-main hover:bg-surface-high/70"
                      }`}
                    >
                      <span>{definition.nativeName}</span>
                      {active ? <Sym name="check" size={17} /> : null}
                      {loading ? (
                        <Sym name="progress_activity" size={17} className="animate-spin" />
                      ) : null}
                    </button>
                  );
                })}
              </div>
              {loadError ? (
                <p className="mt-2 rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">
                  {t("locale.loadError")}
                </p>
              ) : null}
            </div>,
            document.body,
          )
        : null}

      <p className="sr-only" aria-live="polite">
        {loadingLocale ? t("locale.loading") : ""}
        {loadError ? t("locale.loadError") : ""}
      </p>
    </div>
  );
}
