/**
 * PersonaDrawer: the persona detail slide-over (mockup `data-view="drawer"`).
 *
 * A right-anchored, focus-trapped, Escape-dismissible dialog that restores focus
 * to its opener on close. It ports the mockup's sectioned layout: an avatar +
 * name + source + id header, then Demographics, Goal context, and a Raw record
 * panel (with Copy), closed by a "Use this persona" footer CTA.
 *
 * Honest data: the personas API returns only `{id, name, source, blurb}` plus a
 * humanized `context` *text block*. There are no structured demographic/trait
 * fields. So Demographics is parsed best-effort (render-if-present), Goal context
 * is the parsed prose sections, and Raw record is the verbatim context text. A
 * Traits panel is intentionally omitted because curated personas carry no
 * discrete trait list. We never fabricate one.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { useI18n } from "@/i18n/I18nProvider";
import {
  FOCUS_RING,
  Sym,
  humanizeToken,
  parseDemographics,
  parseDemographicsFromBlurb,
  parsePersonaSections,
  personaCodename,
  personaDescriptiveTitle,
} from "./cockpitShared";
import { usePlaygroundPersonaDetail } from "@/lib/usePlayground";
import type { PlaygroundPersona } from "@/lib/types";

/** Per-source provenance-chip tone; unknown sources fall to the neutral default. */
const SOURCE_TONE: Record<string, string> = {
  Nemotron: "text-secondary bg-secondary/10",
  OASIS: "text-primary bg-primary/10",
  PersonaHub: "text-warn bg-warn/10",
};
const NEUTRAL_TONE = "text-text-variant glass-tile";

export interface PersonaDrawerProps {
  open: boolean;
  onClose: () => void;
  persona: PlaygroundPersona | null;
  /** A run-loaded context, if richer than the catalog's; otherwise the drawer
   * fetches the persona's full record itself. */
  context: string | null;
  /** Optional: confirm this persona as the run target (footer CTA). */
  onUse?: (persona: PlaygroundPersona) => void;
}

export function PersonaDrawer({ open, onClose, persona, context, onUse }: PersonaDrawerProps) {
  const { t } = useI18n();
  const closeRef = useRef<HTMLButtonElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const [copied, setCopied] = useState(false);
  // Fetch the complete humanized profile (cached by id) so the drawer shows the
  // *full* persona, not the truncated list blurb. Prefer a run-loaded context.
  const detail = usePlaygroundPersonaDetail(persona?.id ?? null);

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previouslyFocused.current?.focus?.();
    };
  }, [open, onClose]);

  const fullContext = context && context.trim() ? context : detail.data?.context ?? null;

  // Demographics: parse the full context, falling back to the collapsed blurb.
  const demographics = useMemo(() => {
    if (fullContext) {
      const fromContext = parseDemographics(fullContext);
      if (fromContext.length > 0) return fromContext;
    }
    return parseDemographicsFromBlurb(persona?.blurb);
  }, [fullContext, persona?.blurb]);

  // Goal context: the parsed prose sections (excluding Demographics, already a
  // grid above). Only from the multi-line context, never the collapsed blurb.
  const sections = useMemo(() => {
    if (!fullContext) return [];
    return parsePersonaSections(fullContext)
      .filter((s) => !/^demographics$/i.test(s.label))
      .filter((s) => s.body)
      .slice(0, 4);
  }, [fullContext]);

  useEffect(() => {
    if (!copied) return;
    const id = window.setTimeout(() => setCopied(false), 1200);
    return () => window.clearTimeout(id);
  }, [copied]);

  if (!open || !persona) return null;

  // Human-readable heading (descriptive role) + machine codename.
  const title = personaDescriptiveTitle(fullContext, persona.blurb, persona.source);
  const codename = personaCodename(persona.name, persona.id);
  const tone = SOURCE_TONE[persona.source ?? ""] ?? NEUTRAL_TONE;
  const loading = detail.isLoading && !fullContext;
  const rawText = fullContext || persona.blurb || "";

  function handleCopy() {
    if (!rawText) return;
    void navigator.clipboard?.writeText(rawText);
    setCopied(true);
  }

  function handleUse() {
    if (persona) onUse?.(persona);
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50">
      {/* Scrim */}
      <div className="fade-in absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} aria-hidden />

      {/* Slide-over panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("catalog.personaDrawer.dialogLabel", { title })}
        className="slide-in-right absolute bottom-0 right-0 top-0 z-10 flex w-[420px] max-w-[92vw] flex-col border-l border-outline bg-surface-lowest shadow-2xl"
      >
        {/* Header */}
        <div className="flex-shrink-0 border-b border-outline p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-3.5">
              <div
                className="flex h-12 w-12 flex-none items-center justify-center rounded-md border border-outline bg-surface-high"
                aria-hidden
              >
                <Sym name="person" fill={1} size={24} className="text-primary" />
              </div>
              <div className="min-w-0">
                <div className="hud mb-1.5 text-[11px] text-text-dim">{t("catalog.personaDrawer.persona")}</div>
                <h2 title={title} className="truncate font-display text-[18px] font-bold leading-none tracking-tight text-text-main">
                  {title}
                </h2>
                <div className="mt-2 flex min-w-0 items-center gap-2">
                  {persona.source && (
                    <span className={`hud flex-none rounded px-1.5 py-0.5 text-[11px] ${tone}`}>
                      {persona.source}
                    </span>
                  )}
                  <span className="truncate font-mono text-[12px] text-text-variant" title={codename}>
                    {codename}
                  </span>
                </div>
              </div>
            </div>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label={t("catalog.personaDrawer.close")}
              className={`flex h-9 w-9 flex-none items-center justify-center rounded-md border border-outline text-text-variant transition-colors hover:border-primary hover:bg-surface-high hover:text-text-main active:bg-surface-low ${FOCUS_RING}`}
            >
              <Sym name="close" size={18} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="custom-scrollbar flex-1 space-y-5 overflow-y-auto p-5">
          {loading ? (
            <div className="space-y-2" aria-label={t("catalog.personaDrawer.loading")} aria-busy>
              {[5, 7, 6, 4, 7, 5].map((w, i) => (
                <div
                  key={i}
                  className="h-3 animate-rb-pulse rounded bg-surface-high"
                  style={{ width: `${w * 10}%` }}
                />
              ))}
            </div>
          ) : (
            <>
              {/* Demographics */}
              <div className="panel rise-in rounded-md border border-outline bg-surface p-4">
                <h3 className="hud mb-3 text-[12px] text-text-dim">{t("catalog.personaDrawer.demographics")}</h3>
                {demographics.length > 0 ? (
                  <div className="space-y-2.5 text-[14px]">
                    {demographics.map((d) => (
                      <div key={d.key} className="flex items-start justify-between gap-3">
                        <span className="hud flex-none text-[11px] text-text-dim">
                          {humanizeToken(d.key)}
                        </span>
                        <span className="min-w-0 break-words text-right font-mono text-text-variant" title={d.full}>
                          {d.full}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-[14px] italic leading-snug text-text-variant">
                    {t("catalog.personaDrawer.noDemographics")}
                  </p>
                )}
              </div>

              {/* Goal context */}
              {sections.length > 0 && (
                <div
                  className="rise-in rounded-md border border-outline bg-surface p-4"
                  style={{ animationDelay: "60ms" }}
                >
                  <h3 className="hud mb-3 text-[12px] text-text-dim">{t("catalog.personaDrawer.goalContext")}</h3>
                  <div className="space-y-3">
                    {sections.map((s) => (
                      <div key={s.label || "context"}>
                        {s.label && (
                          <div className="hud mb-1 text-[11px] text-text-dim">{s.label}</div>
                        )}
                        <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-text-variant">
                          {s.body}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Raw record */}
              {rawText ? (
                <div
                  className="rise-in rounded-md border border-outline bg-surface p-4"
                  style={{ animationDelay: "120ms" }}
                >
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <h3 className="hud text-[12px] text-text-dim">{t("catalog.personaDrawer.rawRecord")}</h3>
                    <button
                      type="button"
                      onClick={handleCopy}
                      aria-label={copied ? t("catalog.personaDrawer.copiedToClipboard") : t("catalog.personaDrawer.copyRawRecord")}
                      className={`flex flex-none items-center gap-1.5 rounded border px-2 py-1 transition-colors ${FOCUS_RING} ${
                        copied
                          ? "border-secondary/40 text-secondary"
                          : "border-outline text-text-variant hover:border-primary hover:bg-surface-high hover:text-text-main active:bg-surface-low"
                      }`}
                    >
                      <Sym name={copied ? "check" : "content_copy"} size={12} />
                      <span className="hud text-[11px]">{copied ? t("catalog.personaDrawer.copied") : t("catalog.personaDrawer.copy")}</span>
                    </button>
                  </div>
                  <div className="custom-scrollbar overflow-x-auto rounded border border-outline bg-field p-3">
                    <pre className="whitespace-pre-wrap break-words font-mono text-[10.5px] leading-relaxed text-primary">
                      {rawText}
                    </pre>
                  </div>
                </div>
              ) : (
                <p className="text-[14px] italic leading-relaxed text-text-variant">
                  {t("catalog.personaDrawer.noExtraProfile")}
                </p>
              )}
            </>
          )}
        </div>

        {/* Footer: only when a target context can actually adopt this persona
            (i.e. the cockpit's "Change persona"); pure browse/view omits it. */}
        {onUse && (
          <div className="flex-shrink-0 border-t border-outline p-4">
            <button
              type="button"
              onClick={handleUse}
              className={`glow flex w-full items-center justify-center gap-2 rounded-md bg-primary py-3.5 text-[15px] font-semibold text-on-primary transition-[background-color,transform] duration-150 ease-out hover:bg-primary-dim active:scale-[0.99] ${FOCUS_RING}`}
            >
              <Sym name="check" size={16} />
              {t("catalog.personaDrawer.use")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default PersonaDrawer;
