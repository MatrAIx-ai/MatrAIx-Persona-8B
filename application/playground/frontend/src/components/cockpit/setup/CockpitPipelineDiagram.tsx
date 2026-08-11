import { useEffect, useRef, useState, type ReactNode } from "react";

import type { PlaygroundTaskType } from "../TaskTypeSwitch";
import { useI18n } from "@/i18n/I18nProvider";
import {
  CHAT_ACCESS_PIPELINE_PATHS,
  OS_PLATFORM_PIPELINE_PATHS,
  WEB_ACCESS_PIPELINE_PATHS,
  type PipelinePathOption,
  type WebAgentFamily,
} from "@/lib/personaAgentCatalog";
import { Sym } from "../cockpitShared";
import type { ChatTransport } from "./TaskSelectionRail";

export interface CockpitPipelineDiagramProps {
  taskType: PlaygroundTaskType;
  chatTransport?: ChatTransport;
  /** Selected chatbot app name (pipeline display). */
  chatbotLabel?: string;
  /** Web capability tier id (light / standard / extended / full). */
  webCapabilityTierId?: string;
  /** When CLI family is selected, show harness label instead of tier fork. */
  webHarnessLabel?: string;
  webAgentFamily?: WebAgentFamily;
  /** OS app task platform (linux / macos / ios). */
  cuaPlatform?: string;
  /** Short label for the selected persona base model (pipeline display). */
  personaModelLabel?: string;
  hasPersona: boolean;
  hasTask: boolean;
  className?: string;
}

interface NodeProps {
  label: string;
  icon: string;
  detail?: string;
  active?: boolean;
  visible?: boolean;
}

function PipelineNode({ label, icon, detail, active = false, visible = true }: NodeProps) {
  return (
    <div
      className={`rise-in flex w-[118px] shrink-0 flex-col items-center rounded-2xl border px-3 py-4 text-center transition-all duration-500 sm:w-[132px] ${
        visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-3"
      } ${active ? "glass-tile glass-tile--active" : "glass-tile"}`}
    >
      <div
        className={`mb-2.5 grid h-12 w-12 place-items-center rounded-full sm:h-[52px] sm:w-[52px] ${
          active ? "bg-primary/15" : "bg-surface-high/60"
        }`}
      >
        <Sym name={icon} size={24} className={active ? "text-primary" : "text-text-variant"} />
      </div>
      <p className="text-[15px] font-semibold leading-tight text-text-main sm:text-[14px]">{label}</p>
      {detail && (
        <p className="mt-1.5 line-clamp-2 text-[12px] leading-snug text-text-dim">{detail}</p>
      )}
    </div>
  );
}

function Arrow({ visible = true }: { visible?: boolean }) {
  return (
    <Sym
      name="arrow_forward"
      size={22}
      className={`mx-1.5 shrink-0 text-text-dim sm:mx-2.5 ${visible ? "opacity-75" : "opacity-0"}`}
    />
  );
}

/* All path options share the same neutral glass look when inactive. */
function pathOptionInactiveClass(): string {
  return "glass-tile glass-tile--dim";
}

type ForkSize = "narrow" | "default" | "dense";

function forkChipClass(size: ForkSize): string {
  switch (size) {
    case "narrow":
      return "w-[128px] px-2 py-1.5 sm:w-[140px]";
    case "dense":
      return "w-[124px] px-2 py-1.5 sm:w-[130px]";
    default:
      return "w-[132px] px-2.5 py-2 sm:w-[140px] sm:px-3 sm:py-2.5";
  }
}

function forkRowGap(size: ForkSize): string {
  switch (size) {
    case "dense":
      return "gap-2.5 sm:gap-3.5";
    default:
      return "gap-3 sm:gap-4";
  }
}

function forkColumnClass(size: ForkSize): string {
  const margin = size === "dense" ? "mr-3 sm:mr-5" : "mr-5 sm:mr-8";
  const rowGap = size === "dense" ? "gap-1" : "gap-2";
  return `${margin} ${rowGap}`;
}

function PathForkRow({
  option,
  active,
  visible,
  forkSize = "default",
}: {
  option: PipelinePathOption;
  active: boolean;
  visible: boolean;
  forkSize?: ForkSize;
}) {
  const { t } = useI18n();
  const dense = forkSize === "dense";
  const narrow = forkSize === "narrow";

  return (
    <div
      className={`flex items-center transition-all duration-500 ${forkRowGap(forkSize)} ${
        visible ? "opacity-100 translate-x-0" : "opacity-0 -translate-x-2"
      }`}
    >
      <div
        className={`flex shrink-0 items-start gap-1.5 rounded-xl border text-left transition-colors sm:gap-2 ${forkChipClass(
          forkSize,
        )} ${
          active
            ? "glass-tile glass-tile--active"
            : `${pathOptionInactiveClass()} opacity-60`
        }`}
      >
        <Sym
          name={option.icon}
          size={narrow ? 16 : dense ? 15 : 17}
          className={`mt-0.5 shrink-0 ${active ? "text-primary" : "text-text-dim"}`}
        />
        <div className="min-w-0">
          <p
            className={`font-semibold leading-tight ${
              dense ? "text-[12px] sm:text-[13px]" : "text-[13px] sm:text-[14px]"
            } ${active ? "text-text-main" : "text-text-variant"}`}
          >
            {t(`setup.pipeline.option.${option.id}.label`, option.label)}
          </p>
          {option.hint && (
            <p
              className={`mt-0.5 leading-[1.2] text-text-dim line-clamp-2 ${
                dense ? "text-[10px] sm:text-[11px]" : "text-[11px] leading-snug sm:text-[11px]"
              }`}
            >
              {t(`setup.pipeline.option.${option.id}.hint`, option.hint)}
            </p>
          )}
        </div>
      </div>
      <Sym
        name="arrow_forward"
        size={narrow ? 18 : dense ? 16 : 19}
        className={`shrink-0 transition-opacity ${active ? "text-primary opacity-90" : "text-text-dim opacity-20"}`}
      />
    </div>
  );
}

function PipelinePathFork({
  options,
  selected,
  visible,
  caption,
  forkSize = "default",
}: {
  options: PipelinePathOption[];
  selected: string;
  visible: boolean;
  caption?: string;
  forkSize?: ForkSize;
}) {
  return (
    <div
      className={`rise-in flex shrink-0 flex-col items-stretch justify-center py-1 transition-all duration-500 ${forkColumnClass(
        forkSize,
      )} ${visible ? "opacity-100" : "opacity-0"}`}
    >
      {caption && (
        <p className="hud mb-1 text-center text-[11px] tracking-wide text-text-dim sm:text-[12px]">{caption}</p>
      )}
      {options.map((option) => (
        <PathForkRow
          key={option.id}
          option={option}
          active={option.id === selected}
          visible={visible}
          forkSize={forkSize}
        />
      ))}
    </div>
  );
}

/** Shrink wide pipeline rows so they stay inside the center column. */
function PipelineScaleFit({ children, deps }: { children: ReactNode; deps: unknown[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const container = containerRef.current;
    const content = contentRef.current;
    if (!container || !content) return;

    const update = () => {
      const available = container.clientWidth;
      const needed = content.scrollWidth;
      if (needed <= available || available <= 0) {
        setScale(1);
        return;
      }
      setScale(Math.max(0.78, available / needed));
    };

    update();
    const observer = new ResizeObserver(update);
    observer.observe(container);
    observer.observe(content);
    return () => observer.disconnect();
  }, deps);

  return (
    <div ref={containerRef} className="flex w-full min-w-0 items-center justify-center">
      <div
        ref={contentRef}
        className="transition-transform duration-300"
        style={scale < 1 ? { transform: `scale(${scale})`, transformOrigin: "center center" } : undefined}
      >
        {children}
      </div>
    </div>
  );
}

/** Terminal pipeline step — collect metrics, traces, and verifier sign-off. */
const PIPELINE_EVALUATION = {
  label: "Evaluation",
  icon: "verified",
  detail: "Metric collection",
} as const;

const PIPELINE_ROW_CLASS =
  "flex w-max min-w-full items-center justify-center gap-2 px-2 sm:gap-3.5 sm:px-4";

function pipelineStepCount(taskType: PlaygroundTaskType): number {
  return taskType === "survey" ? 3 : 4;
}

export function CockpitPipelineDiagram({
  taskType,
  chatTransport = "api_sidecar",
  chatbotLabel,
  webCapabilityTierId,
  webHarnessLabel,
  webAgentFamily = "browser",
  cuaPlatform,
  personaModelLabel = "Base model",
  hasPersona,
  hasTask,
  className,
}: CockpitPipelineDiagramProps) {
  const { t } = useI18n();
  const [revealed, setRevealed] = useState(0);
  const stepCount = pipelineStepCount(taskType);

  useEffect(() => {
    setRevealed(0);
    const timers = Array.from({ length: stepCount }, (_, index) =>
      window.setTimeout(() => setRevealed(index + 1), 100 + index * 120),
    );
    return () => timers.forEach((id) => window.clearTimeout(id));
  }, [taskType, chatTransport, chatbotLabel, webCapabilityTierId, webHarnessLabel, webAgentFamily, cuaPlatform, personaModelLabel, stepCount]);

  const ready = hasPersona && hasTask;
  const v = (step: number) => revealed >= step;
  const cuaPath = (cuaPlatform ?? "linux").toLowerCase();
  const webPath = (webCapabilityTierId ?? "light").toLowerCase();

  const pipelineBody = (
    <>
      {taskType === "survey" && (
        <div className={PIPELINE_ROW_CLASS}>
          <PipelineNode
            label={t("setup.pipeline.persona", "Persona")}
            icon="face"
            detail={personaModelLabel}
            active={hasPersona}
            visible={v(1)}
          />
          <Arrow visible={v(2)} />
          <PipelineNode label={t("setup.pipeline.survey", "Survey")} icon="quiz" detail={t("setup.pipeline.instrument", "instrument")} active={hasTask} visible={v(2)} />
          <Arrow visible={v(3)} />
          <PipelineNode
            label={t("setup.pipeline.evaluation", PIPELINE_EVALUATION.label)}
            icon={PIPELINE_EVALUATION.icon}
            detail={t("setup.pipeline.metricCollection", PIPELINE_EVALUATION.detail)}
            active={ready}
            visible={v(3)}
          />
        </div>
      )}

      {taskType === "chatbot" && (
        <PipelineScaleFit deps={[taskType, chatTransport, chatbotLabel, personaModelLabel, hasPersona, hasTask, revealed]}>
          <div className={PIPELINE_ROW_CLASS}>
            <PipelineNode
              label={t("setup.pipeline.persona", "Persona")}
              icon="face"
              detail={personaModelLabel}
              active={hasPersona}
              visible={v(1)}
            />
            <Arrow visible={v(2)} />
            <PipelinePathFork
              forkSize="narrow"
              caption={t("setup.pipeline.connection", "Connection")}
              options={CHAT_ACCESS_PIPELINE_PATHS}
              selected={chatTransport}
              visible={v(2)}
            />
            <PipelineNode
              label={t("setup.pipeline.chatbot", "Chatbot")}
              icon="forum"
              detail={chatbotLabel ?? "SUT"}
              active={hasTask}
              visible={v(3)}
            />
            <Arrow visible={v(4)} />
            <PipelineNode
              label={t("setup.pipeline.evaluation", PIPELINE_EVALUATION.label)}
              icon={PIPELINE_EVALUATION.icon}
              detail={t("setup.pipeline.metricCollection", PIPELINE_EVALUATION.detail)}
              active={ready}
              visible={v(4)}
            />
          </div>
        </PipelineScaleFit>
      )}

      {taskType === "web" && (
        <PipelineScaleFit deps={[taskType, webPath, webHarnessLabel, webAgentFamily, personaModelLabel, hasPersona, hasTask, revealed]}>
          <div className={PIPELINE_ROW_CLASS}>
            <PipelineNode
                label={t("setup.pipeline.persona", "Persona")}
              icon="face"
              detail={personaModelLabel}
              active={hasPersona}
              visible={v(1)}
            />
            <Arrow visible={v(2)} />
            {webAgentFamily === "cli" ? (
              <PipelineNode
                label={t("setup.pipeline.harness", "Harness")}
                icon="terminal"
                detail={webHarnessLabel ?? t("setup.pipeline.cliAgent", "CLI agent")}
                active={hasTask}
                visible={v(2)}
              />
            ) : (
              <PipelinePathFork
                forkSize="dense"
                caption={t("setup.pipeline.access", "Access")}
                options={WEB_ACCESS_PIPELINE_PATHS}
                selected={webPath}
                visible={v(2)}
              />
            )}
            <PipelineNode label={t("setup.pipeline.website", "Website")} icon="public" detail="SUT" active={hasTask} visible={v(3)} />
            <Arrow visible={v(4)} />
            <PipelineNode
              label={t("setup.pipeline.evaluation", PIPELINE_EVALUATION.label)}
              icon={PIPELINE_EVALUATION.icon}
              detail={t("setup.pipeline.metricCollection", PIPELINE_EVALUATION.detail)}
              active={ready}
              visible={v(4)}
            />
          </div>
        </PipelineScaleFit>
      )}

      {taskType === "os-app" && (
        <PipelineScaleFit deps={[taskType, cuaPath, personaModelLabel, hasPersona, hasTask, revealed]}>
          <div className={PIPELINE_ROW_CLASS}>
            <PipelineNode
                label={t("setup.pipeline.persona", "Persona")}
              icon="face"
              detail={personaModelLabel}
              active={hasPersona}
              visible={v(1)}
            />
            <Arrow visible={v(2)} />
            <PipelinePathFork
              caption={t("setup.pipeline.osPlatform", "OS platform")}
              options={OS_PLATFORM_PIPELINE_PATHS}
              selected={cuaPath}
              visible={v(2)}
            />
            <PipelineNode label={t("setup.pipeline.osApp", "OS app")} icon="apps" detail={t("setup.pipeline.nativeSut", "native SUT")} active={hasTask} visible={v(3)} />
            <Arrow visible={v(4)} />
            <PipelineNode
              label={t("setup.pipeline.evaluation", PIPELINE_EVALUATION.label)}
              icon={PIPELINE_EVALUATION.icon}
              detail={t("setup.pipeline.metricCollection", PIPELINE_EVALUATION.detail)}
              active={ready}
              visible={v(4)}
            />
          </div>
        </PipelineScaleFit>
      )}
    </>
  );

  return (
    <div
      className={`glass-panel flex w-full flex-1 min-h-0 flex-col rounded-xl px-4 py-4 sm:px-6 sm:py-5 ${className ?? ""}`}
    >
      <p className="shrink-0 text-center font-display text-[16px] font-semibold tracking-wide text-text-main sm:text-[18px]">
        {t("setup.pipeline.title", "Simulation pipeline")}
      </p>

      <div className="custom-scrollbar flex min-h-0 min-w-0 flex-1 items-center justify-center overflow-x-auto py-4 sm:py-6">
        {pipelineBody}
      </div>

      <p className="shrink-0 text-center text-[15px] font-medium leading-snug sm:text-[14px]">
        {ready ? (
          <span className="font-semibold text-secondary">{t("setup.pipeline.ready", "Ready to launch — pipeline locked.")}</span>
        ) : (
          <span className="text-text-variant">{t("setup.pipeline.selectPrompt", "Select personas and a task, then run below.")}</span>
        )}
      </p>
    </div>
  );
}
