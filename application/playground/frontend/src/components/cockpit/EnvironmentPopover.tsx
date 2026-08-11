/**
 * EnvironmentPopover: the read-only "Fixed environment" facts.
 *
 * The cockpit separates *editable knobs* (Model/Domain/Conversation style/Max
 * turns) from the *fixed* parts of the stack the operator cannot change. This
 * renders that read-only block: runtime, persona agent, application
 * adapter, scorer, persona model default, cache policy, adapter
 * resources, adapter agent, and the Playground/application prompt boundary, from the
 * backend `environment` block of `GET /api/config/options`, behind a button
 * that toggles a popover.
 *
 * The button is distinct from the knobs (a quiet "lock" affordance, not a
 * primary-bordered dropdown) so it reads as facts, not controls. The popover is
 * keyboard-dismissible (Escape) and closes on outside click.
 */
import { useEffect, useId, useRef, useState } from "react";

import { useI18n } from "@/i18n/I18nProvider";
import { FOCUS_RING, Sym } from "./cockpitShared";
import type { ApplicationId, ConfigEnvironment } from "@/lib/types";

export interface EnvironmentPopoverProps {
  environment: ConfigEnvironment | null;
}

/**
 * Per-app Selection / Agent / Resources: fixed infrastructure facts that differ
 * by adapter (the data layer exposes a single `ConfigEnvironment`, so these are
 * a presentational constant, in the same spirit as `DOMAIN_META`). Falls back to
 * the `environment` block when an app isn't mapped (never fabricated).
 */
const APP_ENVIRONMENT: Record<ApplicationId, { selection: string; agent: string; resources: string }> = {
  recai: { selection: "SASRec ranker", agent: "InteRecAgent", resources: "recai_resources" },
  finance_openbb: { selection: "Finance tool selection", agent: "OpenBB research agent", resources: "OpenBB data providers" },
  medical_assistant: { selection: "Clinical retrieval", agent: "Medical assistant agent", resources: "Medical knowledge base" },
};

/**
 * Friendly display labels for the few raw stack tokens the environment block can
 * carry (translate DISPLAY ONLY: the underlying token/value is never changed).
 * Unknown values pass through untouched, so already-friendly labels stay as-is.
 */
const FRIENDLY_ENV: Record<string, string> = {
  recai_resources: "RecAI resource bundle",
  "self-report": "Self-report scorer",
};
const friendlyEnv = (
  value: string,
  t: (key: string, fallback?: string) => string,
): string => {
  if (value === "recai_resources") return t("cockpit.environment.friendly.recaiResources", "RecAI resource bundle");
  if (value === "self-report") return t("cockpit.environment.friendly.selfReport", "Self-report scorer");
  return FRIENDLY_ENV[value] ?? value;
};

function appEnvironmentKey(applicationId: ApplicationId): "recai" | "finance" | "medical" {
  if (applicationId === "finance_openbb") return "finance";
  if (applicationId === "medical_assistant") return "medical";
  return "recai";
}

export interface EnvironmentPanelProps {
  environment: ConfigEnvironment | null;
  /** Selected adapter: picks the per-app Selection / Agent / Resources facts. */
  applicationId: ApplicationId;
}

/** One label/value row of the read-only environment panel. */
function EnvRow({ label, value, t }: { label: string; value: string; t: (key: string, fallback?: string) => string }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <span className="hud shrink-0 text-[11px] text-text-dim">{label}</span>
      <span className="min-w-0 break-words text-right font-mono text-[13px] text-text-variant">{friendlyEnv(value, t)}</span>
    </div>
  );
}

/**
 * EnvironmentPanel: the cockpit's read-only local runtime right-rail
 * panel (mockup `app-redesign-v3.html:250-264`). A persistent facts surface
 * (not the popover): Runtime / Chatbot API / Selection / Agent / Resources /
 * Scorer, plus the prompt-boundary footer. Per-app Selection/Agent/Resources
 * come from `APP_ENVIRONMENT`, falling back to the `environment` block.
 */
export function EnvironmentPanel({ environment, applicationId }: EnvironmentPanelProps) {
  const { t } = useI18n();
  const app = APP_ENVIRONMENT[applicationId];
  const appKey = appEnvironmentKey(applicationId);
  const promptOwnership = environment?.promptOwnership ?? {
    personaSystemPrompt: t("cockpit.environment.default.personaPrompt", "Persona prompt from Playground"),
    taskPrompt: t("cockpit.environment.default.taskPrompt", "Application provides the chatbot simulation prompt"),
  };
  const appSelection = t(`cockpit.environment.app.${appKey}.selection`, app?.selection ?? "application ranking");
  const appAgent = t(`cockpit.environment.app.${appKey}.agent`, app?.agent ?? "chatbot application adapter");
  const appResources = t(`cockpit.environment.app.${appKey}.resources`, app?.resources ?? "adapter resources");

  return (
    <div className="rounded-md border border-outline bg-surface-lowest p-5">
      <div className="mb-3.5 flex items-center justify-between">
        <h3 className="hud flex items-center gap-1.5 text-[12px] text-text-dim">
          <Sym name="dns" size={14} />
          {t("cockpit.environment.localRuntime", "Local runtime")}
        </h3>
        <span
          className="hud rounded border border-outline px-1.5 py-0.5 text-[11px] text-text-dim"
          title={t("cockpit.environment.fixedFactsTitle", "These runtime facts are fixed for this run.")}
        >
          {t("cockpit.environment.readOnly", "Read-only")}
        </span>
      </div>
      <div className="space-y-3 text-[14px]">
        <EnvRow t={t} label={t("cockpit.environment.runtime", "Runtime")} value={environment?.runtime ?? t("cockpit.environment.default.runtime", "In-process Matraix Playground runner")} />
        <EnvRow t={t} label={t("cockpit.environment.applicationApi", "Application API")} value={environment?.applicationApi ?? t("cockpit.environment.default.applicationApi", "direct application adapter")} />
        <EnvRow t={t} label={t("cockpit.environment.selection", "Selection")} value={app ? appSelection : environment?.ranker ?? "application ranking"} />
        <EnvRow t={t} label={t("cockpit.environment.agent", "Agent")} value={app ? appAgent : environment?.agent ?? t("cockpit.environment.default.agent", "chatbot application adapter")} />
        <EnvRow t={t} label={t("cockpit.environment.resources", "Resources")} value={app ? appResources : environment?.resources ?? t("cockpit.environment.default.resources", "adapter resources")} />
        <EnvRow t={t} label={t("cockpit.environment.scorer", "Scorer")} value={environment?.scorer ?? "self-report"} />
      </div>
      <div className="mt-4 border-t border-outline pt-3">
        <div className="hud mb-1.5 text-[11px] text-text-dim">{t("cockpit.environment.promptBoundary", "Prompt boundary")}</div>
        <p className="text-[13px] leading-relaxed text-text-variant">
          {promptOwnership.personaSystemPrompt} · {promptOwnership.taskPrompt}
        </p>
      </div>
    </div>
  );
}

/** Plain-language tooltips for the fixed-stack rows (teaching, not data). */
const ROW_TOOLTIPS: Record<string, string> = {
  Selection: "How the app picks candidate items.",
  Agent: "The agent that drives the app.",
  Resources: "The data the agent draws on.",
  Scorer: "Turns the user's self-report into scores.",
};

export function EnvironmentPopover({ environment }: EnvironmentPopoverProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  // Close on outside click + Escape.
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

  const runtime = environment?.runtime ?? t("cockpit.environment.default.runtime", "In-process Matraix Playground runner");
  const runtimeRows: Array<{ label: string; value: string }> = [
    { label: t("cockpit.environment.runtime", "Runtime"), value: runtime },
    { label: t("cockpit.environment.persona", "Persona"), value: environment?.personaAgent ?? t("cockpit.environment.default.persona", "Playground simulated user") },
    { label: t("cockpit.environment.personaDefault", "Persona default"), value: environment?.personaModel ?? t("cockpit.environment.default.personaModel", "anthropic/claude-haiku-4-5") },
    { label: t("cockpit.environment.applicationApi", "Application API"), value: environment?.applicationApi ?? t("cockpit.environment.default.applicationApi", "direct application adapter") },
    { label: t("cockpit.environment.scorer", "Scorer"), value: environment?.scorer ?? t("cockpit.environment.default.scorer", "Playground self-report scorer") },
    { label: t("cockpit.environment.cache", "Cache"), value: environment?.cache ?? t("cockpit.environment.default.cache", "local service and model caches") },
  ];
  const stackRows: Array<{ label: string; value: string }> = [
    { label: t("cockpit.environment.selection", "Selection"), value: environment?.ranker ?? t("cockpit.environment.default.selection", "application-specific ranking / tool selection") },
    { label: t("cockpit.environment.resources", "Resources"), value: environment?.resources ?? t("cockpit.environment.default.resources", "adapter-specific resources") },
    { label: t("cockpit.environment.agent", "Agent"), value: environment?.agent ?? t("cockpit.environment.default.agent", "chatbot application adapter") },
  ];
  const promptOwnership = environment?.promptOwnership ?? {
    personaSystemPrompt: t("cockpit.environment.default.personaPrompt", "Persona prompt from Playground"),
    taskPrompt: t("cockpit.environment.default.taskPrompt", "Application-provided chatbot simulation prompt"),
  };
  const promptRows: Array<{ label: string; value: string }> = [
    { label: t("cockpit.environment.systemPrompt", "System prompt"), value: promptOwnership.personaSystemPrompt },
    { label: t("cockpit.environment.taskPrompt", "Task prompt"), value: promptOwnership.taskPrompt },
  ];

  return (
    <div ref={rootRef} className="relative ml-auto flex flex-shrink-0 items-center gap-2 border-l border-outline-dim pl-6">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        className={`flex items-center gap-1.5 rounded border border-outline bg-surface-low px-3 py-1.5 text-[15px] font-medium text-text-variant transition ease-out hover:border-primary hover:text-text-main active:scale-[0.98] ${FOCUS_RING}`}
      >
        <Sym name="hub" size={16} className="shrink-0 text-text-dim" />
        <span className="min-w-0 truncate" title={runtime}>{runtime}</span>
        <Sym name={open ? "expand_less" : "expand_more"} size={16} className="shrink-0 text-text-dim" />
      </button>

      {open && (
        <div
          id={panelId}
          role="region"
          aria-label={t("cockpit.environment.fixedEnvironment", "Fixed environment")}
          className="pop-in absolute right-0 top-full z-30 mt-2 w-80 max-w-[calc(100vw-1.5rem)] max-h-[70vh] overflow-y-auto custom-scrollbar rounded-md border border-outline bg-surface-lowest p-3 shadow-2xl"
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="flex items-center gap-1 hud text-[12px] text-text-dim">
              <Sym name="lock" size={13} />
              {t("cockpit.environment.testEnvironment", "Test environment")}
            </p>
            <span
              className="hud rounded border border-outline px-1.5 py-0.5 text-[11px] text-text-dim"
              title={t("cockpit.environment.fixedFactsTitle", "These runtime facts are fixed for this run.")}
            >
              {t("cockpit.environment.readOnly", "Read-only")}
            </span>
          </div>
          <div className="space-y-2">
            {runtimeRows.map((r) => (
              <div key={r.label} className="flex items-start justify-between gap-3">
                <span className="hud shrink-0 text-[11px] text-text-dim" title={
                  t(
                    `cockpit.environment.tooltip.${r.label === "Selection" || r.label === "选择" ? "selection" : r.label === "Agent" || r.label === "智能体" ? "agent" : r.label === "Resources" || r.label === "资源" ? "resources" : "scorer"}`,
                    ROW_TOOLTIPS[r.label] ?? "",
                  )
                }>
                  {r.label}
                </span>
                <span className="min-w-0 break-words text-right font-mono text-[13px] text-text-variant">
                  {friendlyEnv(r.value, t)}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-3 border-t border-outline-dim pt-3">
            <p className="mb-2 flex items-center gap-1 hud text-[12px] text-text-dim">
              <Sym name="storage" size={13} />
              {t("cockpit.environment.whatsRunning", "What’s running inside the app")}
            </p>
            <div className="space-y-2">
              {stackRows.map((r) => (
                <div key={r.label} className="flex items-start justify-between gap-3">
                  <span className="hud shrink-0 text-[11px] text-text-dim" title={
                    t(
                      `cockpit.environment.tooltip.${r.label === "Selection" || r.label === "选择" ? "selection" : r.label === "Agent" || r.label === "智能体" ? "agent" : r.label === "Resources" || r.label === "资源" ? "resources" : "scorer"}`,
                      ROW_TOOLTIPS[r.label] ?? "",
                    )
                  }>
                    {r.label}
                  </span>
                  <span className="min-w-0 break-words text-right font-mono text-[13px] text-text-variant">
                    {friendlyEnv(r.value, t)}
                  </span>
                </div>
              ))}
            </div>
          </div>
          <div className="mt-3 border-t border-outline-dim pt-3">
            <p className="mb-2 flex items-center gap-1 hud text-[12px] text-text-dim">
              <Sym name="account_tree" size={13} />
              {t("cockpit.environment.whoWritesPrompt", "Who writes which prompt")}
            </p>
            <div className="space-y-2">
              {promptRows.map((r) => (
                <div key={r.label} className="flex items-start justify-between gap-3">
                  <span className="shrink-0 hud text-[11px] text-text-dim">{r.label}</span>
                  <span className="max-w-[12.5rem] text-right text-[13px] leading-relaxed text-text-variant">
                    {r.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default EnvironmentPopover;
