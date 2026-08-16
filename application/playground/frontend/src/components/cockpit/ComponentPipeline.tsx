/**
 * ComponentPipeline: the Persona → Chatbot → Scorer flow strip.
 *
 * Two presentations off the same status state-machine:
 *   - `variant="setup"`: the cockpit's compact pipeline panel
 *     (`app-redesign-v3.html:116-141`), each stage as icon + name + a muted
 *     owner subtitle, chevrons between. Teaches the shape before a run.
 *   - `variant="live"`: the live-run strip row (`app-redesign-v3.html:457-480`),
 *     each stage as a state marker (done check / pulsing dot / hollow dot /
 *     error) + name + a status chip, driven by the run phase.
 *
 * The done/active/idle/error tone per stage comes from the unchanged status
 * functions; only the rendering differs by variant.
 */
import { Sym } from "./cockpitShared";
import { useI18n } from "@/i18n/I18nProvider";
import type { ConfigEnvironment } from "@/lib/types";
import type { PlaygroundRunPhase } from "@/lib/usePlayground";

export interface ComponentPipelineProps {
  variant: "setup" | "live";
  environment: ConfigEnvironment | null;
  engine: string;
  personaModel: string;
  phase: PlaygroundRunPhase;
  jobPhase: string | null | undefined;
  hasPersona: boolean;
  turnCount: number;
  hasQuestionnaire: boolean;
}

type Tone = "idle" | "active" | "done" | "error";

interface NodeState {
  key: string;
  label: string;
  icon: string;
  owner: string;
  statusKey: PipelineStatus;
  tone: Tone;
}

type PipelineStatus =
  | "choosePersona"
  | "stoppedEarly"
  | "complete"
  | "gettingReady"
  | "active"
  | "connected"
  | "ready"
  | "needsALook"
  | "warmingUp"
  | "replying"
  | "chatting"
  | "waiting"
  | "nothingToScore"
  | "notScored"
  | "scoring";

type Translate = ReturnType<typeof useI18n>["t"];

function normalizedPhase(value: string | null | undefined): string {
  return (value ?? "").toLowerCase();
}

function personaStatus(phase: PlaygroundRunPhase, jobPhase: string, hasPersona: boolean): Pick<NodeState, "statusKey" | "tone"> {
  if (!hasPersona) return { statusKey: "choosePersona", tone: "idle" };
  if (phase === "error" || phase === "timeout") return { statusKey: "stoppedEarly", tone: "error" };
  if (phase === "done") return { statusKey: "complete", tone: "done" };
  if (phase === "building") return { statusKey: "gettingReady", tone: "active" };
  if (phase === "running") {
    const active = jobPhase.includes("persona") || jobPhase.includes("user") || jobPhase.includes("simulat");
    return { statusKey: active ? "active" : "connected", tone: active ? "active" : "done" };
  }
  return { statusKey: "ready", tone: "idle" };
}

function chatbotStatus(phase: PlaygroundRunPhase, jobPhase: string, turnCount: number): Pick<NodeState, "statusKey" | "tone"> {
  if (phase === "error" || phase === "timeout") return { statusKey: "needsALook", tone: "error" };
  if (phase === "done") return { statusKey: "complete", tone: "done" };
  if (phase === "building") return { statusKey: "warmingUp", tone: "active" };
  if (phase === "running") {
    const active =
      jobPhase.includes("recommend") || jobPhase.includes("agent") || jobPhase.includes("turn");
    if (active) return { statusKey: "replying", tone: "active" };
    return turnCount > 0 ? { statusKey: "chatting", tone: "done" } : { statusKey: "waiting", tone: "idle" };
  }
  return { statusKey: "ready", tone: "idle" };
}

function scorerStatus(phase: PlaygroundRunPhase, jobPhase: string, hasQuestionnaire: boolean): Pick<NodeState, "statusKey" | "tone"> {
  if (phase === "error" || phase === "timeout") return { statusKey: "nothingToScore", tone: "error" };
  if (phase === "done") return hasQuestionnaire ? { statusKey: "complete", tone: "done" } : { statusKey: "notScored", tone: "idle" };
  if (phase === "running") {
    const active = jobPhase.includes("eval") || jobPhase.includes("scor") || jobPhase.includes("verifier");
    return active ? { statusKey: "scoring", tone: "active" } : { statusKey: "waiting", tone: "idle" };
  }
  return { statusKey: "waiting", tone: "idle" };
}

function statusLabel(t: Translate, status: PipelineStatus): string {
  switch (status) {
    case "choosePersona": return t("cockpit.pipeline.status.choosePersona");
    case "stoppedEarly": return t("cockpit.pipeline.status.stoppedEarly");
    case "complete": return t("cockpit.pipeline.status.complete");
    case "gettingReady": return t("cockpit.pipeline.status.gettingReady");
    case "active": return t("cockpit.pipeline.status.active");
    case "connected": return t("cockpit.pipeline.status.connected");
    case "ready": return t("cockpit.pipeline.status.ready");
    case "needsALook": return t("cockpit.pipeline.status.needsALook");
    case "warmingUp": return t("cockpit.pipeline.status.warmingUp");
    case "replying": return t("cockpit.pipeline.status.replying");
    case "chatting": return t("cockpit.pipeline.status.chatting");
    case "waiting": return t("cockpit.pipeline.status.waiting");
    case "nothingToScore": return t("cockpit.pipeline.status.nothingToScore");
    case "notScored": return t("cockpit.pipeline.status.notScored");
    case "scoring": return t("cockpit.pipeline.status.scoring");
  }
}

const CHIP_TONE: Record<Tone, string> = {
  active: "bg-primary/10 text-primary",
  done: "bg-secondary/10 text-secondary",
  error: "bg-danger/10 text-danger",
  idle: "glass-tile text-text-variant",
};

/** A live-run stage marker (done check / pulsing dot / error / hollow dot). */
function StateMarker({ tone }: { tone: Tone }) {
  if (tone === "done") return <Sym name="check_circle" fill={1} size={16} className="text-secondary" />;
  if (tone === "error") return <Sym name="error" fill={1} size={16} className="text-danger" />;
  if (tone === "active") return <span className="h-2 w-2 rounded-full bg-primary animate-pulse" aria-hidden />;
  return <span className="h-2 w-2 rounded-full border border-outline" aria-hidden />;
}

export function ComponentPipeline({
  variant,
  environment,
  phase,
  jobPhase,
  hasPersona,
  turnCount,
  hasQuestionnaire,
}: ComponentPipelineProps) {
  const { t } = useI18n();
  const raw = normalizedPhase(jobPhase);
  const nodes: NodeState[] = [
    {
      key: "persona",
      label: t("cockpit.pipeline.persona"),
      icon: "face",
      owner: environment?.personaAgent ?? t("cockpit.pipeline.owner.simulatedUser"),
      ...personaStatus(phase, raw, hasPersona),
    },
    {
      key: "chatbot",
      label: t("cockpit.pipeline.chatbot"),
      icon: "forum",
      owner: environment?.applicationApi ?? t("cockpit.pipeline.owner.applicationAdapter"),
      ...chatbotStatus(phase, raw, turnCount),
    },
    { key: "scorer", label: t("cockpit.pipeline.scorer"), icon: "fact_check", owner: t("cockpit.pipeline.owner.selfReport"), ...scorerStatus(phase, raw, hasQuestionnaire) },
  ];

  if (variant === "live") {
    return (
      <div className="flex min-w-0 items-center gap-3">
        <span className="hud shrink-0 text-[11px] text-text-dim">{t("cockpit.pipeline.title")}</span>
        <span className="h-3.5 w-px shrink-0 bg-outline" aria-hidden />
        <div className="custom-scrollbar flex items-center gap-2.5 overflow-x-auto text-[14px]">
          {nodes.map((node, i) => (
            <div key={node.key} className="flex shrink-0 items-center gap-2.5">
              <span className="flex items-center gap-1.5">
                <StateMarker tone={node.tone} />
                <span className={node.tone === "idle" ? "text-text-variant" : "text-text-main"}>{node.label}</span>
                <span className={`hud rounded px-1.5 py-0.5 text-[11px] ${CHIP_TONE[node.tone]}`}>{statusLabel(t, node.statusKey)}</span>
              </span>
              {i < nodes.length - 1 && <Sym name="chevron_right" size={14} className="text-text-dim" />}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // setup variant: the bordered "Pipeline" panel.
  return (
    <div className="rounded-md border border-outline bg-surface-lowest px-4 py-3">
      <div className="hud mb-2.5 text-[11px] text-text-dim">{t("cockpit.pipeline.title")}</div>
      <div className="custom-scrollbar flex items-center gap-2 overflow-x-auto text-[13px]">
        {nodes.map((node, i) => (
          <div key={node.key} className="flex shrink-0 items-center gap-2">
            <span className="flex items-center gap-1.5 text-text-main">
              <Sym name={node.icon} size={14} className="text-primary" />
              {node.label}
              <span className="text-text-variant">· {node.owner}</span>
            </span>
            {i < nodes.length - 1 && <Sym name="chevron_right" size={14} className="text-text-dim" />}
          </div>
        ))}
      </div>
    </div>
  );
}

export default ComponentPipeline;
