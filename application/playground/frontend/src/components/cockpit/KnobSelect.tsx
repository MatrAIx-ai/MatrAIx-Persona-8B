/**
 * KnobSelect: one editable config knob (a description-rich dropdown).
 *
 * Two presentations, same description-carrying listbox:
 *   - inline (default): a compact "label + value + chevron" used by the Chat
 *     workbench config bars (unchanged contract);
 *   - `block`: the mockup's full-width field, a `.hud` label above a
 *     field-styled trigger (`bg-field border rounded`) with the value on the
 *     left and a chevron on the right, used inside the cockpit's "Run
 *     configuration" grid (`app-redesign-v3.html:173-180`).
 *
 * Implemented as a button + a positioned listbox (not a native `<select>`) so
 * the per-option `description` from the config metadata can be shown, a feature
 * a native select can't offer. The menu is keyboard-operable (Up/Down move,
 * Enter/Space select, Escape closes) via roving focus.
 */
import { useEffect, useId, useRef, useState } from "react";

import { useI18n } from "@/i18n/I18nProvider";
import { FOCUS_RING, Sym } from "./cockpitShared";

/** One selectable option (mirrors the backend `ConfigOptionValue`). */
export interface KnobOption {
  value: string;
  label: string;
  description?: string;
}

export interface KnobSelectProps {
  /** Uppercase knob label ("Model", "Domain", …). */
  label: string;
  /** Currently selected value. */
  value: string;
  options: KnobOption[];
  onChange: (value: string) => void;
  /** Render with the primary border (the highlighted knob in the mockup). */
  accent?: boolean;
  disabled?: boolean;
  /** Full-width field layout (label above), for the cockpit "Run options" grid. */
  block?: boolean;
  /** A normal-case accent suffix appended to the label (e.g. "· RecAI"). */
  labelAccent?: string;
}

export function KnobSelect({
  label,
  value,
  options,
  onChange,
  accent,
  disabled,
  block,
  labelAccent,
}: KnobSelectProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  const selected = options.find((o) => o.value === value) ?? null;
  const currentLabel = selected?.label ?? value;

  // Close on outside click + Escape.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  // When opening, focus the selected option.
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
    } else if (e.key === "Home") {
      e.preventDefault();
      setActiveIndex(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActiveIndex(options.length - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      commit(activeIndex);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    }
  }

  // --- Block (full-width field) layout: the cockpit "Run options" grid. -----
  if (block) {
    return (
      <div ref={rootRef} className="block">
        <span className="hud mb-1.5 block text-[11px] text-text-dim">
          {label}
          {labelAccent && <span className="ml-1 normal-case tracking-normal text-primary">{labelAccent}</span>}
        </span>
        <div className="relative">
          <button
            type="button"
            disabled={disabled}
            onClick={() => !disabled && setOpen((v) => !v)}
            onKeyDown={onButtonKey}
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-label={t("cockpit.knob.selectedValue", { label, value: currentLabel })}
            className={`flex w-full items-center justify-between gap-2 rounded border px-3 py-2.5 text-left text-[15px] transition ease-out active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-55 disabled:active:scale-100 ${FOCUS_RING} ${
              accent
                ? "border-primary bg-primary/10 text-primary hover:bg-primary/15"
                : "border-outline bg-field text-text-main hover:border-primary"
            }`}
          >
            <span className="min-w-0 truncate" title={currentLabel}>{currentLabel}</span>
            <Sym
              name="expand_more"
              size={16}
              className={`shrink-0 transition-transform duration-150 ease-out ${open ? "rotate-180" : ""} ${accent ? "" : "text-text-dim"}`}
            />
          </button>
          {open && (
            <Listbox
              menuId={menuId}
              label={label}
              options={options}
              value={value}
              activeIndex={activeIndex}
              setActiveIndex={setActiveIndex}
              onMenuKey={onMenuKey}
              commit={commit}
              widthClass="w-full"
            />
          )}
        </div>
      </div>
    );
  }

  // --- Inline (compact) layout: Chat workbench config bars. ------------------
  return (
    <div ref={rootRef} className="flex flex-shrink-0 items-center gap-2">
      <span className="hud text-[12px] text-text-dim">{label}</span>
      <div className="relative">
        <button
          type="button"
          disabled={disabled}
          onClick={() => !disabled && setOpen((v) => !v)}
          onKeyDown={onButtonKey}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label={t("cockpit.knob.selectedValue", { label, value: currentLabel })}
          className={`flex items-center gap-2 rounded border px-3 py-1.5 text-[15px] font-medium transition ease-out active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-55 disabled:active:scale-100 ${FOCUS_RING} ${
            accent
              ? "border-primary bg-primary/10 text-primary hover:bg-primary/15"
              : "border-outline bg-field text-text-main hover:border-primary"
          }`}
        >
          {currentLabel}
          <Sym
            name="expand_more"
            size={16}
            className={`shrink-0 transition-transform duration-150 ease-out ${open ? "rotate-180" : ""} ${accent ? "" : "text-text-dim"}`}
          />
        </button>
        {open && (
          <Listbox
            menuId={menuId}
            label={label}
            options={options}
            value={value}
            activeIndex={activeIndex}
            setActiveIndex={setActiveIndex}
            onMenuKey={onMenuKey}
            commit={commit}
            widthClass="w-64"
          />
        )}
      </div>
    </div>
  );
}

/** The shared description-carrying listbox (used by both layouts). */
function Listbox({
  menuId,
  label,
  options,
  value,
  activeIndex,
  setActiveIndex,
  onMenuKey,
  commit,
  widthClass,
}: {
  menuId: string;
  label: string;
  options: KnobOption[];
  value: string;
  activeIndex: number;
  setActiveIndex: (i: number) => void;
  onMenuKey: (e: React.KeyboardEvent) => void;
  commit: (i: number) => void;
  widthClass: string;
}) {
  return (
    <ul
      id={menuId}
      role="listbox"
      aria-label={label}
      tabIndex={-1}
      onKeyDown={onMenuKey}
      ref={(el) => el?.focus()}
      className={`pop-in custom-scrollbar absolute left-0 top-full z-30 mt-1 max-h-72 max-w-[calc(100vw-2rem)] overflow-auto rounded-md border border-outline bg-surface-lowest p-1 shadow-2xl outline-none ${widthClass}`}
    >
      {options.map((opt, idx) => {
        const isSelected = opt.value === value;
        const isActive = idx === activeIndex;
        return (
          <li
            key={opt.value}
            role="option"
            aria-selected={isSelected}
            onMouseEnter={() => setActiveIndex(idx)}
            onClick={() => commit(idx)}
            className={`cursor-pointer rounded-md px-2.5 py-2 transition-colors ${isActive ? "bg-surface-high" : ""}`}
          >
            <div className="flex items-center justify-between gap-2">
              <span
                title={opt.label}
                className={`min-w-0 truncate text-[15px] font-medium ${isSelected ? "text-primary" : "text-text-main"}`}
              >
                {opt.label}
              </span>
              {isSelected && <Sym name="check" size={16} className="shrink-0 text-primary" />}
            </div>
            {opt.description && (
              <p className="mt-0.5 text-[13px] leading-relaxed text-text-variant">{opt.description}</p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export default KnobSelect;
