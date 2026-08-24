import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useI18n } from "@/i18n/I18nProvider";
import { FOCUS_RING, Sym } from "../cockpitShared";

export interface CockpitSelectOption {
  value: string;
  label: string;
  /** Secondary line in the menu, e.g. "light · Playwright + DOM". */
  meta?: string;
  /** Shown below the field when this option is selected (normal case). */
  summary?: string;
  /** Optional section header in grouped menus. */
  group?: string;
}

export interface CockpitSelectProps {
  label: string;
  value: string;
  options: CockpitSelectOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  /** Fallback hint when the selected option has no summary. */
  hint?: string;
  /** Render the label to the left of the field instead of above (denser). */
  inlineLabel?: boolean;
  /** Extra classes for the label (e.g. fixed width so stacked inline selects align). */
  labelClassName?: string;
  /** Allow long option labels to wrap instead of truncating (survey prompts). */
  wrapOptions?: boolean;
  /** Make the open menu wider than the trigger for long option text. */
  wideMenu?: boolean;
  /**
   * When false, option ``meta`` only appears in the open menu — not on the
   * closed trigger (useful for Dataset counts that clutter the compact field).
   */
  showSelectedMeta?: boolean;
}

type MenuCoords = {
  top?: number;
  bottom?: number;
  left: number;
  width: number;
  maxHeight: number;
};

function menuCoordsFor(trigger: HTMLElement, wideMenu: boolean): MenuCoords {
  const rect = trigger.getBoundingClientRect();
  const gap = 4;
  const viewportPad = 8;
  const spaceBelow = window.innerHeight - rect.bottom - gap - viewportPad;
  const spaceAbove = rect.top - gap - viewportPad;
  const preferBelow = spaceBelow >= 160 || spaceBelow >= spaceAbove;
  const maxHeight = Math.max(120, Math.min(320, preferBelow ? spaceBelow : spaceAbove));
  // Never size the portaled menu solely from a squeezed inline trigger — Model
  // selects share a row with long option summaries and can shrink near-zero.
  const minWidth = wideMenu ? 288 : 240;
  const maxWidth = Math.min(window.innerWidth - viewportPad * 2, wideMenu ? 448 : 360);
  const width = Math.min(Math.max(rect.width, minWidth), maxWidth);
  let left = rect.left;
  if (left + width > window.innerWidth - viewportPad) {
    left = Math.max(viewportPad, window.innerWidth - viewportPad - width);
  }
  if (preferBelow) {
    return {
      top: rect.bottom + gap,
      left,
      width,
      maxHeight,
    };
  }
  return {
    bottom: window.innerHeight - rect.top + gap,
    left,
    width,
    maxHeight,
  };
}

export function CockpitSelect({
  label,
  value,
  options,
  onChange,
  disabled,
  hint,
  inlineLabel = false,
  labelClassName,
  wrapOptions = false,
  wideMenu = false,
  showSelectedMeta = true,
}: CockpitSelectProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [coords, setCoords] = useState<MenuCoords | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLUListElement | null>(null);
  const menuId = useId();

  const selected = options.find((o) => o.value === value) ?? null;

  const syncCoords = () => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    setCoords(menuCoordsFor(trigger, wideMenu));
  };

  useLayoutEffect(() => {
    if (!open) {
      setCoords(null);
      return;
    }
    syncCoords();
  }, [open, wideMenu, options.length]);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      const target = e.target as Node;
      if (rootRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    }
    function onReposition() {
      syncCoords();
    }
    document.addEventListener("mousedown", onDown);
    window.addEventListener("resize", onReposition);
    // Capture scroll from nested scroll parents (Persona World page frame, etc.).
    window.addEventListener("scroll", onReposition, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("resize", onReposition);
      window.removeEventListener("scroll", onReposition, true);
    };
  }, [open, wideMenu]);

  useEffect(() => {
    if (open) {
      const idx = options.findIndex((o) => o.value === value);
      setActiveIndex(idx >= 0 ? idx : 0);
    }
  }, [open, options, value]);

  function commit(idx: number) {
    const opt = options[idx];
    if (opt) onChange(opt.value);
    setOpen(false);
  }

  function onButtonKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setOpen(true);
    }
  }

  function onMenuKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(options.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      commit(activeIndex);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    }
  }

  const footer = selected?.summary ?? hint;

  const groupedOptions = useMemo(() => {
    const hasGroups = options.some((opt) => opt.group);
    if (!hasGroups) {
      return [{ group: null as string | null, items: options.map((opt, idx) => ({ opt, idx })) }];
    }
    const sections: Array<{ group: string | null; items: Array<{ opt: CockpitSelectOption; idx: number }> }> =
      [];
    for (let idx = 0; idx < options.length; idx += 1) {
      const opt = options[idx];
      const group = opt.group ?? null;
      const last = sections[sections.length - 1];
      if (last && last.group === group) {
        last.items.push({ opt, idx });
      } else {
        sections.push({ group, items: [{ opt, idx }] });
      }
    }
    return sections;
  }, [options]);

  const menu =
    open && coords
      ? createPortal(
          <ul
            id={menuId}
            ref={(el) => {
              menuRef.current = el;
              el?.focus();
            }}
            role="listbox"
            aria-label={label}
            tabIndex={-1}
            onKeyDown={onMenuKey}
            style={{
              position: "fixed",
              top: coords.top,
              bottom: coords.bottom,
              left: coords.left,
              width: coords.width,
              maxHeight: coords.maxHeight,
              // Opaque fill — avoids glass-panel backdrop-filter compositing bugs.
              backgroundColor: "rgb(var(--surface-lowest))",
              zIndex: 80,
            }}
            className="pop-in custom-scrollbar overflow-auto rounded-lg border border-outline/60 p-1 shadow-2xl outline-none"
          >
            {groupedOptions.map((section) => (
              <li key={section.group ?? "default"} role="presentation" className="list-none">
                {section.group ? (
                  <p className="px-2.5 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-text-dim">
                    {section.group}
                  </p>
                ) : null}
                <ul role="group" aria-label={section.group ?? undefined} className="list-none">
                  {section.items.map(({ opt, idx }) => {
                    const isSelected = opt.value === value;
                    const isActive = idx === activeIndex;
                    return (
                      <li
                        key={opt.value}
                        role="option"
                        aria-selected={isSelected}
                        onMouseEnter={() => setActiveIndex(idx)}
                        onClick={() => commit(idx)}
                        className={`cursor-pointer rounded-md px-2.5 py-2 transition-colors ${
                          isActive ? "bg-surface-high" : ""
                        } ${isSelected ? "bg-primary/8" : ""}`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <span
                              className={`block text-[15px] font-medium ${
                                wrapOptions
                                  ? "whitespace-normal break-words leading-snug"
                                  : "truncate"
                              } ${isSelected ? "text-primary" : "text-text-main"}`}
                            >
                              {opt.label}
                            </span>
                            {opt.meta ? (
                              <span
                                className={`mt-0.5 block text-[12px] leading-snug text-text-dim ${
                                  wrapOptions ? "whitespace-normal break-words" : ""
                                }`}
                              >
                                {opt.meta}
                              </span>
                            ) : null}
                          </div>
                          {isSelected ? (
                            <Sym name="check" size={16} className="mt-0.5 shrink-0 text-primary" />
                          ) : null}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))}
          </ul>,
          document.body,
        )
      : null;

  return (
    <div ref={rootRef} className="flex flex-col gap-1.5">
      <div className={inlineLabel ? "flex min-w-0 items-center gap-2" : "contents"}>
        {label ? (
          <span
            className={`text-[13px] font-medium text-text-dim normal-case tracking-normal ${
              inlineLabel ? "shrink-0" : ""
            } ${labelClassName ?? ""}`}
          >
            {label}
          </span>
        ) : null}
        <div className={inlineLabel ? "relative min-w-0 flex-1" : "relative"}>
          <button
            ref={triggerRef}
            type="button"
            disabled={disabled}
            onClick={() => !disabled && setOpen((v) => !v)}
            onKeyDown={onButtonKey}
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-controls={open ? menuId : undefined}
            aria-label={t("cockpit.knob.selectedValue", { label, value: selected?.label ?? value })}
            className={`glass-tile glass-tile--hover flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left backdrop-blur transition ease-out active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-55 disabled:active:scale-100 ${FOCUS_RING}`}
          >
            <span className="min-w-0 flex-1">
              <span
                className={`block text-[15px] font-medium text-text-main ${
                  wrapOptions ? "whitespace-normal break-words leading-snug" : "truncate"
                }`}
              >
                {selected?.label ?? value}
              </span>
              {showSelectedMeta && selected?.meta ? (
                <span
                  className={`block text-[12px] text-text-dim ${
                    wrapOptions ? "whitespace-normal break-words leading-snug" : "truncate"
                  }`}
                >
                  {selected.meta}
                </span>
              ) : null}
            </span>
            <Sym
              name="expand_more"
              size={18}
              className={`shrink-0 text-text-dim transition-transform duration-150 ${open ? "rotate-180" : ""}`}
            />
          </button>
          {menu}
        </div>
      </div>
      {footer ? (
        <p className="text-[12px] leading-relaxed text-text-dim normal-case">{footer}</p>
      ) : null}
    </div>
  );
}
