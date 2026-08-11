/**
 * PreflightChip: the live readiness status in the top bar.
 *
 * Polls `GET /api/preflight` and reports readiness in plain language. The chip
 * itself is calm; clicking it opens a popover that lists each readiness check by
 * its human name with a pass/fail marker and the (already user-facing) detail.
 * It never surfaces raw environment-variable names.
 *
 * States:
 *   - checking (amber)  → probe in flight
 *   - ready    (green)  → every required and optional check passed
 *   - setup    (amber)  → required gaps and/or optional adapters not ready
 *   - offline  (red)    → API unreachable
 */
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { FOCUS_RING, Sym } from "./cockpit/cockpitShared";
import { api } from "@/lib/api";
import type { PreflightResponse } from "@/lib/types";
import { useI18n } from "@/i18n/I18nProvider";

type Tone = "ready" | "setup" | "offline" | "checking";

type PreflightCheck = PreflightResponse["checks"][number];

/** Tokenized chip classes per tone (tinted fill + matching text, no stroke). */
const TONE_CLASS: Record<Tone, string> = {
  ready: "bg-secondary/12 text-secondary",
  setup: "bg-warn/12 text-warn",
  offline: "bg-danger/12 text-danger",
  checking: "bg-warn/12 text-warn",
};

const DOT_CLASS: Record<Tone, string> = {
  ready: "bg-secondary",
  setup: "bg-warn",
  offline: "bg-danger",
  checking: "bg-warn",
};

function groupChecks(checks: PreflightCheck[], defaultGroup: string) {
  return checks.reduce<{ group: string; items: PreflightCheck[] }[]>((acc, c) => {
    const g = c.group ?? defaultGroup;
    const bucket = acc.find((x) => x.group === g);
    if (bucket) bucket.items.push(c);
    else acc.push({ group: g, items: [c] });
    return acc;
  }, []);
}

export function PreflightChip() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const preflight = useQuery<PreflightResponse>({
    queryKey: ["preflight"],
    queryFn: api.getPreflight,
    // Re-probe occasionally so a resource that comes online is reflected.
    refetchInterval: 20_000,
  });

  // Close the popover on outside click + Escape.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Resolve the tone + compact chip label (details live in the popover).
  let tone: Tone;
  let label: string;
  const data = preflight.data;
  const requiredFailing = data?.checks.filter((c) => !c.ok && !c.optional) ?? [];
  const optionalFailing = data?.checks.filter((c) => !c.ok && c.optional) ?? [];
  const allGreen = data ? data.checks.every((c) => c.ok) : false;

  if (preflight.isLoading) {
    tone = "checking";
    label = t("shell.preflight.checking", "Checking…");
  } else if (preflight.isError || !data) {
    tone = "offline";
    label = t("shell.preflight.backendOffline", "Backend offline");
  } else if (!data.ready) {
    tone = "setup";
    label =
      requiredFailing.length === 1
        ? t("shell.preflight.issue.one", "{count} issue", { count: 1 })
        : t("shell.preflight.issue.many", "{count} issues", { count: requiredFailing.length });
  } else if (optionalFailing.length > 0) {
    tone = "setup";
    label = t("shell.preflight.almostReady", "Almost ready");
  } else {
    tone = "ready";
    label = t("shell.preflight.envReady", "Env ready");
  }

  const popoverChecks = data
    ? groupChecks([...requiredFailing, ...optionalFailing], t("shell.preflight.checks", "Checks"))
    : [];

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => data && setOpen((v) => !v)}
        aria-expanded={data ? open : undefined}
        aria-label={t("shell.preflight.readinessLabel", "Readiness: {label}", { label })}
        className={`flex h-9 items-center gap-2 whitespace-nowrap rounded-full px-3 text-xs font-medium transition ${TONE_CLASS[tone]} ${FOCUS_RING} ${
          data ? "cursor-pointer hover:opacity-90 active:scale-[0.98]" : "cursor-default"
        }`}
      >
        <span
          className={`h-2 w-2 rounded-full ${DOT_CLASS[tone]} ${tone === "checking" ? "animate-rb-pulse" : ""}`}
          aria-hidden
        />
        {label}
      </button>

      {open && data && (
        <div
          role="region"
          aria-label={t("shell.preflight.setupChecklist", "Setup checklist")}
          className="pop-in absolute right-0 top-full z-30 mt-2 w-80 max-w-[calc(100vw-1.5rem)] max-h-[70vh] overflow-y-auto custom-scrollbar rounded-xl border border-outline bg-surface-lowest p-3 shadow-2xl"
        >
          <p className="hud mb-2.5 text-[12px] text-text-dim">
            {t("shell.preflight.systemReadiness", "System readiness")}
          </p>
          {allGreen ? (
            <p className="text-[14px] text-secondary">
              {t("shell.preflight.allChecksPassed", "All checks passed.")}
            </p>
          ) : popoverChecks.length === 0 ? (
            <p className="text-[14px] text-secondary">
              {t("shell.preflight.allRequiredChecksPassed", "All required checks passed.")}
            </p>
          ) : (
            <div className="space-y-3.5">
              {data.ready && optionalFailing.length > 0 && (
                <p className="text-[13px] leading-relaxed text-text-variant">
                  {t(
                    "shell.preflight.optionalAdaptersNeedAttention",
                    "Required checks passed. Optional adapters below still need attention.",
                  )}
                </p>
              )}
              {popoverChecks.map((g) => (
                <div key={g.group}>
                  <div className="hud mb-1.5 text-[11px] text-primary">{g.group}</div>
                  <ul className="space-y-2">
                    {g.items.map((check) => {
                      const iconClass = check.optional ? "text-warn" : "text-danger";
                      return (
                        <li key={check.name} className="flex items-start gap-2">
                          <Sym name="error" fill={1} size={16} className={`mt-px flex-none ${iconClass}`} />
                          <div className="min-w-0">
                            <div className="text-[14px] font-medium text-text-main">
                              {check.name}
                              {check.optional && (
                                <span className="hud ml-1.5 text-[11px] text-text-dim">
                                  {t("shell.preflight.optional", "optional")}
                                </span>
                              )}
                            </div>
                            <div className="text-[13px] leading-relaxed text-text-variant">
                              {check.detail}
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
