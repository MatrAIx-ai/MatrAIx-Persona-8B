/**
 * AppFooter: the slim, honest status footer (mockup `app-redesign-v3.html:1279`).
 *
 * Left: the product name + the active surface context (e.g. "chatbot · RecAI ·
 * movie"). Only real values already in scope. Right: a dot + the live backend
 * connection status, read from the SHARED preflight query cache (same key as
 * `PreflightChip`); no new request and no extra polling here.
 *
 * Mounted once in each shell branch of `App.tsx` so it spans every surface.
 */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { PreflightResponse } from "@/lib/types";
import { useI18n } from "@/i18n/I18nProvider";

export interface AppFooterProps {
  /** The active surface context, e.g. "chatbot · RecAI · movie" (real values). */
  context: string;
  /** "glass" floats over the Home stage as a NASA-panel frosted bar. */
  variant?: "solid" | "glass";
}

export function AppFooter({ context, variant = "solid" }: AppFooterProps) {
  const { t } = useI18n();

  // Read-only: shares PreflightChip's cache. No refetchInterval -> no extra poll.
  const preflight = useQuery<PreflightResponse>({
    queryKey: ["preflight"],
    queryFn: api.getPreflight,
  });

  let dot = "bg-warn";
  let label = t("shell.footer.checking", "Checking…");
  let pulse = false;
  if (preflight.isLoading) {
    dot = "bg-warn";
    label = t("shell.footer.checking", "Checking…");
    pulse = true;
  } else if (preflight.isError || !preflight.data) {
    dot = "bg-danger";
    label = t("shell.footer.backendOffline", "Backend offline");
  } else if (preflight.data.ready) {
    dot = "bg-secondary";
    label = t("shell.footer.connected", "Connected");
  } else {
    dot = "bg-warn";
    label = t("shell.footer.finishingSetup", "Finishing setup");
  }

  return (
    <footer
      className={`nasa-glass-bar flex-shrink-0 ${
        variant === "glass" ? "absolute inset-x-0 bottom-0 z-20" : ""
      }`}
    >
      <div className="flex items-center justify-between gap-4 px-5 py-2 text-text-dim">
        <div className="hud flex min-w-0 items-center gap-3 text-[11px]">
          <span className="flex-none text-text-variant">
            Matr<span className="text-primary">AI</span>x
          </span>
          <span className="flex-none text-outline">·</span>
          <span className="min-w-0 truncate text-primary/75" title={context}>
            {context}
          </span>
        </div>
        <div
          className="hud flex flex-shrink-0 items-center gap-2 text-[11px] text-text-variant"
          aria-label={t("shell.footer.backendConnectionStatus", "Backend connection status")}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full transition-colors ${dot} ${pulse ? "animate-rb-pulse" : ""}`}
            aria-hidden
          />
          {label}
        </div>
      </div>
    </footer>
  );
}

export default AppFooter;
