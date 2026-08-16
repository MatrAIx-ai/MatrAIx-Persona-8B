import { useCallback, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

import { useI18n } from "@/i18n/I18nProvider";
import type { ConfigOptionValue } from "@/lib/types";
import {
  isPinnedTask,
  recordRecentTaskSelection,
  togglePinnedTask,
} from "@/lib/cockpitTaskRailStorage";
import {
  domainOptionsForTaskCards,
  orderTaskCards,
} from "@/lib/taskRailOrdering";
import { FOCUS_RING, Sym } from "../cockpitShared";
import {
  USE_COMPUTER_URL,
  cuaRuntimeSelectOptions,
} from "@/lib/personaAgentCatalog";
import { CockpitSelect } from "./CockpitSelect";
import { WebAgentSettings } from "./WebAgentSettings";
import type { PlaygroundTaskType } from "../TaskTypeSwitch";
import { CockpitRailHeader } from "./CockpitRailHeader";
import { CockpitToggle } from "./CockpitToggle";
import { TaskDetailModal } from "./TaskDetailModal";
import { ToneChip, transportChipTone, type ToneChipTone } from "./ToneChip";
import {
  taskAvailabilityPresentation,
  type TaskAvailabilityStatus,
} from "./taskAvailability";
import {
  CHIP_TEXT_CLASS,
  taskCardTagKey,
  taskCardTagLabel,
} from "./taskCardLabels";
import type { TaskCardTag } from "./taskCardLabels";
import { taskCardIcon } from "./taskCardIcons";
import {
  taskRuntimeStatusLabel,
  taskTransportLabel,
  type TaskRuntimeStatus,
} from "./taskCardPresentation";

export type ChatTransport =
  "api_sidecar" | "api_external" | "mcp_sidecar" | "mcp_external";

export interface TaskCardModel {
  id: string;
  title: string;
  subtitle?: string;
  taskType: PlaygroundTaskType;
  taskPath: string;
  transport?: ChatTransport;
  available?: boolean | null;
  /** Availability status intended for display; its label is localized by the renderer. */
  availabilityStatus?: TaskAvailabilityStatus;
  canStart?: boolean;
  /** Runtime state intended for display; its label is localized by the renderer. */
  runtimeStatus?: TaskRuntimeStatus;
  statusDetail?: string;
  /** Product capabilities from chatbot.yaml for UserSim / persona agent. */
  capabilities?: Array<{ id: string; label: string; kind?: string }>;
  /** CUA runtime platform (linux / macos / ios / web). */
  platform?: string;
  /** Harbor metadata.type from task.toml — display tag only. */
  metaType?: string;
  /** CUA metadata.os (linux / macos / ios). */
  os?: string;
  domain?: string;
  difficulty?: string;
  taskKind?: "example" | "task";
  tags?: TaskCardTag[];
  /** Free-form ``task.toml`` tags — searchable, not shown as chips. */
  searchTags?: string[];
  /** @deprecated prefer tags */
  tagLabels?: string[];
  profileMarkdown?: string;
  instructionMarkdown?: string;
}

export { taskCardIcon, taskMetaTypeIcon } from "./taskCardIcons";

export interface TaskSelectionRailProps {
  taskType: PlaygroundTaskType;
  chatTasks: TaskCardModel[];
  surveyTasks: TaskCardModel[];
  webTasks: TaskCardModel[];
  cuaTasks: TaskCardModel[];
  selectedTaskId: string;
  onSelectTask: (task: TaskCardModel) => void;
  engine: string;
  onEngineChange: (engine: string) => void;
  engineOptions: ConfigOptionValue[];
  maxTurns: number | null;
  onMaxTurnsChange: (turns: number | null) => void;
  onStartSidecar?: (taskId: string) => void;
  sidecarStartingId?: string | null;
  sidecarActionError?: string | null;
  resolveWebPersonaAgent?: (taskId: string) => string;
  onWebPersonaAgentChange?: (taskId: string, agent: string) => void;
  resolveCuaRuntime?: (taskId: string, platform?: string) => string;
  onCuaRuntimeChange?: (taskId: string, runtime: string) => void;
  tasksLoading?: boolean;
  tasksError?: string | null;
  disabled?: boolean;
}

const VIRTUALIZE_THRESHOLD = 30;
const ESTIMATED_CARD_HEIGHT = 132;

/** Sentinel for the "no domain filter" dropdown entry. */
const ALL_DOMAINS = "__all__";

function formatDomainLabel(domain: string): string {
  return domain
    .split(/[-_/]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function TaskSelectionRail({
  taskType,
  chatTasks,
  surveyTasks,
  webTasks,
  cuaTasks,
  selectedTaskId,
  onSelectTask,
  engine,
  onEngineChange,
  engineOptions,
  maxTurns,
  onMaxTurnsChange,
  onStartSidecar,
  sidecarStartingId,
  sidecarActionError,
  resolveWebPersonaAgent,
  onWebPersonaAgentChange,
  resolveCuaRuntime,
  onCuaRuntimeChange,
  tasksLoading,
  tasksError,
  disabled,
}: TaskSelectionRailProps) {
  const { t } = useI18n();
  const [settingsOpen, setSettingsOpen] = useState<string | null>(null);
  const [detailCard, setDetailCard] = useState<TaskCardModel | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [domainFilter, setDomainFilter] = useState<string | null>(null);
  const [pinRevision, setPinRevision] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const cards =
    taskType === "chatbot"
      ? chatTasks
      : taskType === "survey"
        ? surveyTasks
        : taskType === "web"
          ? webTasks
          : taskType === "os-app"
            ? cuaTasks
            : [];

  const domainOptions = useMemo(
    () => domainOptionsForTaskCards(cards),
    [cards],
  );

  // Domains can grow without bound, so they live in a dropdown, not a chip row.
  const domainSelectOptions = useMemo(() => {
    const counts = new Map<string, number>();
    for (const card of cards) {
      const domain = (card.domain ?? "").trim().toLowerCase();
      if (domain) counts.set(domain, (counts.get(domain) ?? 0) + 1);
    }
    return [
      {
        value: ALL_DOMAINS,
        label: t("taskSetup.domain.all", { count: cards.length }),
      },
      ...domainOptions.map((domain) => ({
        value: domain,
        label: `${formatDomainLabel(domain)} · ${counts.get(domain) ?? 0}`,
      })),
    ];
  }, [cards, domainOptions, t]);

  const searchFilteredCards = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return cards;
    return cards.filter((card) => {
      const haystack = [
        card.id,
        card.title,
        card.subtitle ?? "",
        card.domain ?? "",
        ...(card.tags?.map((tag) => taskCardTagLabel(tag, t)) ?? []),
        ...(card.searchTags ?? []),
        taskAvailabilityPresentation(card.availabilityStatus, t)?.label ?? "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [cards, searchQuery, t]);

  const filteredCards = useMemo(
    () => orderTaskCards(searchFilteredCards, taskType, domainFilter),
    [searchFilteredCards, taskType, domainFilter, pinRevision],
  );

  const useVirtualList =
    filteredCards.length > VIRTUALIZE_THRESHOLD && settingsOpen === null;
  const virtualizer = useVirtualizer({
    count: useVirtualList ? filteredCards.length : 0,
    getScrollElement: () => listRef.current,
    estimateSize: () => ESTIMATED_CARD_HEIGHT,
    overscan: 8,
  });

  const handleSelectTask = useCallback(
    (card: TaskCardModel) => {
      recordRecentTaskSelection(taskType, card.id);
      onSelectTask(card);
    },
    [onSelectTask, taskType],
  );

  const handleTogglePin = useCallback(
    (taskId: string) => {
      togglePinnedTask(taskType, taskId);
      setPinRevision((value) => value + 1);
    },
    [taskType],
  );

  const renderTaskCard = (card: TaskCardModel) => {
    const selected = selectedTaskId === card.id;
    const settingsId = settingsOpen === card.id;
    const unavailable = card.available === false;
    const pinned = isPinnedTask(taskType, card.id);
    const availability = taskAvailabilityPresentation(card.availabilityStatus, t);
    const tags: TaskCardTag[] =
      card.tags ??
      card.tagLabels?.map((label) => ({
        label,
        tone: "neutral" as ToneChipTone,
      })) ??
      [];
    return (
      <div
        key={card.id}
        className={`rounded-lg border border-transparent transition ${
          selected
            ? "persona-card--selected"
            : unavailable
              ? "glass-tile glass-tile--dim opacity-75"
              : "glass-tile glass-tile--hover"
        }`}
      >
        <div className="flex items-start gap-3 p-3">
          <button
            type="button"
            disabled={disabled}
            onClick={() => handleSelectTask(card)}
            className={`flex min-w-0 flex-1 items-start gap-3 text-left ${FOCUS_RING}`}
          >
            <div
              className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg ${
                selected ? "bg-primary/15" : "bg-surface-high/60"
              }`}
            >
              <Sym
                name={taskCardIcon(taskType, card)}
                size={20}
                className={selected ? "text-primary" : "text-text-variant"}
              />
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-display text-[14px] font-semibold leading-tight text-text-main">
                {card.title}
              </p>
              {card.subtitle && (
                <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-text-dim">
                  {card.subtitle}
                </p>
              )}
              <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                {card.transport && (
                  <ToneChip
                    tone={transportChipTone(card.transport)}
                    className={CHIP_TEXT_CLASS}
                  >
                    {taskTransportLabel(card.transport, t)}
                  </ToneChip>
                )}
                {tags.map((tag) => (
                  <ToneChip
                    key={taskCardTagKey(tag)}
                    tone={tag.tone}
                    className={CHIP_TEXT_CLASS}
                  >
                    {taskCardTagLabel(tag, t)}
                  </ToneChip>
                ))}
                {availability && (
                  <ToneChip
                    key={`availability:${card.availabilityStatus}`}
                    tone={availability.tone}
                    showDot
                    className={CHIP_TEXT_CLASS}
                  >
                    {availability.label}
                  </ToneChip>
                )}
              </div>
            </div>
          </button>
          <button
            type="button"
            onClick={() => handleTogglePin(card.id)}
            className={`shrink-0 rounded-md p-1.5 ${pinned ? "text-primary" : "text-text-dim hover:bg-surface-high hover:text-primary"} ${FOCUS_RING}`}
            aria-label={
              pinned
                ? t("taskSetup.actions.unpin", { title: card.title })
                : t("taskSetup.actions.pin", { title: card.title })
            }
          >
            <Sym name={pinned ? "keep" : "keep_off"} size={16} />
          </button>
          <button
            type="button"
            onClick={() => setDetailCard(card)}
            className={`shrink-0 rounded-md p-1.5 text-text-dim hover:bg-surface-high hover:text-primary ${FOCUS_RING}`}
            aria-label={t("taskSetup.actions.viewDetails", {
              title: card.title,
            })}
          >
            <Sym name="info" size={16} />
          </button>
          {taskType === "chatbot" && (
            <button
              type="button"
              onClick={() => setSettingsOpen(settingsId ? null : card.id)}
              className={`shrink-0 rounded-md p-1.5 text-text-dim hover:bg-surface-high hover:text-primary ${FOCUS_RING}`}
              aria-label={t("taskSetup.actions.chatbotSettings")}
            >
              <Sym name="settings" size={16} />
            </button>
          )}
          {(taskType === "web" || taskType === "os-app") && (
            <button
              type="button"
              onClick={() => setSettingsOpen(settingsId ? null : card.id)}
              className={`shrink-0 rounded-md p-1.5 text-text-dim hover:bg-surface-high hover:text-primary ${FOCUS_RING}`}
              aria-label={t("taskSetup.actions.taskSettings")}
            >
              <Sym name="settings" size={16} />
            </button>
          )}
        </div>
        {settingsId &&
          taskType === "web" &&
          resolveWebPersonaAgent &&
          onWebPersonaAgentChange && (
            <div className="border-t border-outline/30 px-3 py-3">
              <WebAgentSettings
                taskId={card.id}
                agentId={resolveWebPersonaAgent(card.id)}
                disabled={disabled}
                onAgentChange={onWebPersonaAgentChange}
              />
            </div>
          )}
        {settingsId &&
          taskType === "os-app" &&
          resolveCuaRuntime &&
          onCuaRuntimeChange && (
            <div className="space-y-2 border-t border-outline/30 px-3 py-3">
              <CockpitSelect
                label={t("taskSetup.settings.osRuntime")}
                value={resolveCuaRuntime(card.id, card.platform)}
                options={cuaRuntimeSelectOptions(card.platform ?? "linux")}
                disabled={disabled}
                onChange={(backend) => onCuaRuntimeChange(card.id, backend)}
              />
              {(card.platform === "macos" || card.platform === "ios") && (
                <a
                  href={USE_COMPUTER_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="text-[12px] font-medium text-primary hover:underline"
                >
                  {t("taskSetup.settings.useComputerSetup")}
                </a>
              )}
            </div>
          )}
        {settingsId &&
          taskType === "chatbot" &&
          (() => {
            const serviceUp = card.available ?? false;
            const canStart = card.canStart ?? false;
            const starting = sidecarStartingId === card.id;
            const runtimeStatusDetail = taskRuntimeStatusLabel(
              card.runtimeStatus,
              t,
            );
            const showServiceToggle =
              card.available !== null && card.available !== undefined;
            return (
              <div className="space-y-3 border-t border-outline/30 px-3 py-3">
                {showServiceToggle ? (
                  <CockpitToggle
                    checked={serviceUp}
                    busy={starting}
                    busyLabel={t("taskSetup.status.starting")}
                    onChange={(on) => {
                      if (on && !serviceUp && canStart)
                        onStartSidecar?.(card.id);
                    }}
                    disabled={disabled || starting || serviceUp || !canStart}
                    label={t("taskSetup.status.serviceUp")}
                    description={
                      serviceUp
                        ? (runtimeStatusDetail ??
                          card.statusDetail ??
                          (card.transport === "mcp_sidecar" ||
                          card.transport === "mcp_external"
                            ? t("taskSetup.status.mcpReady")
                            : t("taskSetup.status.chatApiReady")))
                        : canStart
                          ? card.transport === "mcp_sidecar" ||
                            card.transport === "mcp_external"
                            ? t("taskSetup.status.startMcp")
                            : t("taskSetup.status.startChatApi")
                          : card.transport === "mcp_sidecar" ||
                              card.transport === "mcp_external"
                            ? t("taskSetup.status.configureMcp")
                            : t("taskSetup.status.configureApi")
                    }
                  />
                ) : (
                  <div className="glass-tile glass-tile--dim rounded-md px-3 py-2">
                    <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-text-dim">
                      {t("taskSetup.settings.connection")}
                    </p>
                    <p className="mt-1 text-[13px] leading-relaxed text-text-variant">
                      {runtimeStatusDetail ??
                        card.statusDetail ??
                        (card.transport === "mcp_sidecar" ||
                        card.transport === "mcp_external"
                          ? t("taskSetup.status.mcpNoToggle")
                          : t("taskSetup.status.noReadinessCheck"))}
                    </p>
                  </div>
                )}
                {sidecarActionError && settingsOpen === card.id && (
                  <p className="text-[12px] text-danger">
                    {sidecarActionError}
                  </p>
                )}
                {(card.capabilities?.length ?? 0) > 0 && (
                  <div>
                    <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-text-dim">
                      {t("taskSetup.settings.productCapabilities")}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {card.capabilities!.map((cap) => (
                        <span
                          key={cap.id}
                          className="glass-tile rounded px-2 py-0.5 text-[12px] text-text-variant"
                          title={
                            cap.kind === "exposure"
                              ? t("taskSetup.capabilities.visibleInReplies")
                              : t("taskSetup.capabilities.userSimTool")
                          }
                        >
                          {cap.label}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                <label className="cockpit-field-label flex flex-col gap-1.5">
                  {t("taskSetup.settings.applicationModel")}
                  <select
                    value={engine}
                    disabled={disabled}
                    onChange={(e) => onEngineChange(e.target.value)}
                    className="glass-tile h-8 rounded-md px-2 text-[14px] font-medium text-text-main"
                  >
                    {engineOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </label>
                <CockpitToggle
                  checked={maxTurns !== null}
                  onChange={(enabled) =>
                    onMaxTurnsChange(enabled ? (maxTurns ?? 8) : null)
                  }
                  disabled={disabled}
                  label={t("taskSetup.settings.turnLimit")}
                  description={
                    maxTurns === null
                      ? t("taskSetup.settings.unlimitedTurns")
                      : t("taskSetup.settings.stopAfterTurns")
                  }
                />
                {maxTurns !== null && (
                  <label className="cockpit-field-label flex flex-col gap-1.5">
                    {t("taskSetup.settings.maxTurns")}
                    <input
                      type="number"
                      min={1}
                      step={1}
                      value={maxTurns}
                      disabled={disabled}
                      onChange={(e) => {
                        const next = e.currentTarget.valueAsNumber;
                        if (Number.isFinite(next) && next >= 1)
                          onMaxTurnsChange(next);
                      }}
                      className="glass-tile h-8 rounded-md px-2 text-[14px] font-medium text-text-main"
                    />
                  </label>
                )}
              </div>
            );
          })()}
      </div>
    );
  };

  return (
    <aside className="glass-panel glass-panel-rail relative flex h-full min-h-0 flex-col rounded-xl p-4">
      <CockpitRailHeader label={t("taskSetup.title")} />

      <label className="mb-2.5 flex flex-col gap-1">
        <span className="sr-only">{t("taskSetup.search")}</span>
        <div className="relative">
          <Sym
            name="search"
            size={16}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-text-dim"
          />
          <input
            type="search"
            value={searchQuery}
            disabled={disabled}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t("taskSetup.searchPlaceholder")}
            className="glass-tile h-9 w-full rounded-lg pl-9 pr-2.5 text-[14px] text-text-main placeholder:text-text-dim"
          />
        </div>
      </label>

      {domainOptions.length > 1 && (
        <div className="mb-2.5">
          <CockpitSelect
            label={t("taskSetup.domain.label")}
            inlineLabel
            value={domainFilter ?? ALL_DOMAINS}
            options={domainSelectOptions}
            disabled={disabled}
            onChange={(next) =>
              setDomainFilter(next === ALL_DOMAINS ? null : next)
            }
          />
        </div>
      )}

      {tasksLoading && (
        <p className="mb-2 text-[13px] text-text-dim">
          {t("taskSetup.loading")}
        </p>
      )}
      {tasksError && (
        <p className="mb-2 text-[13px] text-danger">{tasksError}</p>
      )}

      <div
        ref={listRef}
        className="custom-scrollbar min-h-0 flex-1 overflow-y-auto pr-0.5"
      >
        {filteredCards.length === 0 && !tasksLoading && (
          <p className="glass-tile glass-tile--dim rounded-lg px-3 py-4 text-center text-[13px] text-text-dim">
            {searchQuery.trim() || domainFilter
              ? t("taskSetup.empty.noMatch")
              : t("taskSetup.empty.none")}
          </p>
        )}
        {useVirtualList ? (
          <div
            className="relative w-full"
            style={{ height: `${virtualizer.getTotalSize()}px` }}
          >
            {virtualizer.getVirtualItems().map((virtualRow) => {
              const card = filteredCards[virtualRow.index];
              if (!card) return null;
              return (
                <div
                  key={card.id}
                  className="absolute left-0 top-0 w-full pb-2.5"
                  style={{ transform: `translateY(${virtualRow.start}px)` }}
                >
                  {renderTaskCard(card)}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="space-y-2.5">
            {filteredCards.map((card) => renderTaskCard(card))}
          </div>
        )}
      </div>

      <TaskDetailModal
        open={detailCard !== null}
        card={detailCard}
        onClose={() => setDetailCard(null)}
      />
    </aside>
  );
}
