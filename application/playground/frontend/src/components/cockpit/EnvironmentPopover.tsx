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
type Translate = ReturnType<typeof useI18n>["t"];

interface AppEnvironment {
  selection: string;
  agent: string;
  resources: string;
}

/** Translate only static presentation defaults; backend-provided values pass through unchanged. */
function appEnvironment(t: Translate, applicationId: ApplicationId): AppEnvironment | null {
  switch (applicationId) {
    case "meal_planning_nutrition":
      return {
        selection: t("cockpit.environment.app.meal.selection"),
        agent: t("cockpit.environment.app.meal.agent"),
        resources: t("cockpit.environment.app.meal.resources"),
      };
    case "finance_openbb":
      return {
        selection: t("cockpit.environment.app.finance.selection"),
        agent: t("cockpit.environment.app.finance.agent"),
        resources: t("cockpit.environment.app.finance.resources"),
      };
    case "acme_support_api":
      return {
        selection: t("cockpit.environment.app.acmeApi.selection"),
        agent: t("cockpit.environment.app.acmeApi.agent"),
        resources: t("cockpit.environment.app.acmeApi.resources"),
      };
    case "acme_support_mcp":
      return {
        selection: t("cockpit.environment.app.acmeMcp.selection"),
        agent: t("cockpit.environment.app.acmeMcp.agent"),
        resources: t("cockpit.environment.app.acmeMcp.resources"),
      };
    default:
      return null;
  }
}

/** Friendly display labels for raw stack tokens; unknown backend values remain raw. */
function friendlyEnv(t: Translate, value: string): string {
  if (value === "recai_resources") return t("cockpit.environment.friendly.applicationResourceBundle");
  if (value === "self-report") return t("cockpit.environment.friendly.selfReport");
  return value;
}

type EnvironmentTooltip = "selection" | "agent" | "resources" | "scorer";

function environmentTooltip(t: Translate, tooltip: EnvironmentTooltip): string {
  switch (tooltip) {
    case "selection": return t("cockpit.environment.tooltip.selection");
    case "agent": return t("cockpit.environment.tooltip.agent");
    case "resources": return t("cockpit.environment.tooltip.resources");
    case "scorer": return t("cockpit.environment.tooltip.scorer");
  }
}

interface EnvironmentRow {
  id: string;
  label: string;
  value: string;
  tooltip?: EnvironmentTooltip;
}

export interface EnvironmentPanelProps {
  environment: ConfigEnvironment | null;
  /** Selected adapter: picks the per-app Selection / Agent / Resources facts. */
  applicationId: ApplicationId;
}

/** One label/value row of the read-only environment panel. */
function EnvRow({ label, value, tooltip, t }: EnvironmentRow & { t: Translate }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <span className="hud shrink-0 text-[11px] text-text-dim" title={tooltip ? environmentTooltip(t, tooltip) : undefined}>{label}</span>
      <span className="min-w-0 break-words text-right font-mono text-[13px] text-text-variant">{friendlyEnv(t, value)}</span>
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
  const app = appEnvironment(t, applicationId);
  const promptOwnership = environment?.promptOwnership ?? {
    personaSystemPrompt: t("cockpit.environment.default.personaPrompt"),
    taskPrompt: t("cockpit.environment.default.panelTaskPrompt"),
  };

  return (
    <div className="rounded-md border border-outline bg-surface-lowest p-5">
      <div className="mb-3.5 flex items-center justify-between">
        <h3 className="hud flex items-center gap-1.5 text-[12px] text-text-dim">
          <Sym name="dns" size={14} />
          {t("cockpit.environment.localRuntime")}
        </h3>
        <span
          className="hud rounded border border-outline px-1.5 py-0.5 text-[11px] text-text-dim"
          title={t("cockpit.environment.fixedFactsTitle")}
        >
          {t("cockpit.environment.readOnly")}
        </span>
      </div>
      <div className="space-y-3 text-[14px]">
        <EnvRow id="runtime" t={t} label={t("cockpit.environment.runtime")} value={environment?.runtime ?? t("cockpit.environment.default.runtime")} />
        <EnvRow id="applicationApi" t={t} label={t("cockpit.environment.applicationApi")} value={environment?.applicationApi ?? t("cockpit.environment.default.applicationApi")} />
        <EnvRow id="selection" t={t} label={t("cockpit.environment.selection")} value={app?.selection ?? environment?.ranker ?? t("cockpit.environment.default.panelSelection")} tooltip="selection" />
        <EnvRow id="agent" t={t} label={t("cockpit.environment.agent")} value={app?.agent ?? environment?.agent ?? t("cockpit.environment.default.agent")} tooltip="agent" />
        <EnvRow id="resources" t={t} label={t("cockpit.environment.resources")} value={app?.resources ?? environment?.resources ?? t("cockpit.environment.default.panelResources")} tooltip="resources" />
        <EnvRow id="scorer" t={t} label={t("cockpit.environment.scorer")} value={environment?.scorer ?? "self-report"} tooltip="scorer" />
      </div>
      <div className="mt-4 border-t border-outline pt-3">
        <div className="hud mb-1.5 text-[11px] text-text-dim">{t("cockpit.environment.promptBoundary")}</div>
        <p className="text-[13px] leading-relaxed text-text-variant">
          {t("cockpit.environment.promptBoundaryValue", {
            personaPrompt: promptOwnership.personaSystemPrompt,
            taskPrompt: promptOwnership.taskPrompt,
          })}
        </p>
      </div>
    </div>
  );
}

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

  const runtime = environment?.runtime ?? t("cockpit.environment.default.runtime");
  const runtimeRows: EnvironmentRow[] = [
    { id: "runtime", label: t("cockpit.environment.runtime"), value: runtime },
    { id: "persona", label: t("cockpit.environment.persona"), value: environment?.personaAgent ?? t("cockpit.environment.default.persona") },
    { id: "personaDefault", label: t("cockpit.environment.personaDefault"), value: environment?.personaModel ?? "anthropic/claude-haiku-4-5" },
    { id: "applicationApi", label: t("cockpit.environment.applicationApi"), value: environment?.applicationApi ?? t("cockpit.environment.default.applicationApi") },
    { id: "scorer", label: t("cockpit.environment.scorer"), value: environment?.scorer ?? t("cockpit.environment.default.scorer"), tooltip: "scorer" },
    { id: "cache", label: t("cockpit.environment.cache"), value: environment?.cache ?? t("cockpit.environment.default.cache") },
  ];
  const stackRows: EnvironmentRow[] = [
    { id: "selection", label: t("cockpit.environment.selection"), value: environment?.ranker ?? t("cockpit.environment.default.selection"), tooltip: "selection" },
    { id: "resources", label: t("cockpit.environment.resources"), value: environment?.resources ?? t("cockpit.environment.default.resources"), tooltip: "resources" },
    { id: "agent", label: t("cockpit.environment.agent"), value: environment?.agent ?? t("cockpit.environment.default.agent"), tooltip: "agent" },
  ];
  const promptOwnership = environment?.promptOwnership ?? {
    personaSystemPrompt: t("cockpit.environment.default.personaPrompt"),
    taskPrompt: t("cockpit.environment.default.taskPrompt"),
  };
  const promptRows: EnvironmentRow[] = [
    { id: "systemPrompt", label: t("cockpit.environment.systemPrompt"), value: promptOwnership.personaSystemPrompt },
    { id: "taskPrompt", label: t("cockpit.environment.taskPrompt"), value: promptOwnership.taskPrompt },
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
          aria-label={t("cockpit.environment.fixedEnvironment")}
          className="pop-in absolute right-0 top-full z-30 mt-2 w-80 max-w-[calc(100vw-1.5rem)] max-h-[70vh] overflow-y-auto custom-scrollbar rounded-md border border-outline bg-surface-lowest p-3 shadow-2xl"
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="flex items-center gap-1 hud text-[12px] text-text-dim">
              <Sym name="lock" size={13} />
              {t("cockpit.environment.testEnvironment")}
            </p>
            <span
              className="hud rounded border border-outline px-1.5 py-0.5 text-[11px] text-text-dim"
              title={t("cockpit.environment.fixedFactsTitle")}
            >
              {t("cockpit.environment.readOnly")}
            </span>
          </div>
          <div className="space-y-2">
            {runtimeRows.map((r) => (
              <div key={r.id} className="flex items-start justify-between gap-3">
                <span className="hud shrink-0 text-[11px] text-text-dim" title={r.tooltip ? environmentTooltip(t, r.tooltip) : undefined}>
                  {r.label}
                </span>
                <span className="min-w-0 break-words text-right font-mono text-[13px] text-text-variant">
                  {friendlyEnv(t, r.value)}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-3 border-t border-outline-dim pt-3">
            <p className="mb-2 flex items-center gap-1 hud text-[12px] text-text-dim">
              <Sym name="storage" size={13} />
              {t("cockpit.environment.whatsRunning")}
            </p>
            <div className="space-y-2">
              {stackRows.map((r) => (
                <div key={r.id} className="flex items-start justify-between gap-3">
                  <span className="hud shrink-0 text-[11px] text-text-dim" title={r.tooltip ? environmentTooltip(t, r.tooltip) : undefined}>
                    {r.label}
                  </span>
                  <span className="min-w-0 break-words text-right font-mono text-[13px] text-text-variant">
                    {friendlyEnv(t, r.value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
          <div className="mt-3 border-t border-outline-dim pt-3">
            <p className="mb-2 flex items-center gap-1 hud text-[12px] text-text-dim">
              <Sym name="account_tree" size={13} />
              {t("cockpit.environment.whoWritesPrompt")}
            </p>
            <div className="space-y-2">
              {promptRows.map((r) => (
                <div key={r.id} className="flex items-start justify-between gap-3">
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
