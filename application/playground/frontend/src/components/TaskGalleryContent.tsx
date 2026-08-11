/**
 * TaskGalleryContent: cross-type task catalog grid (Task Gallery page).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useI18n } from "@/i18n/I18nProvider";
import {
  chatbotEvalTaskCards,
  osAppTaskCards,
  surveyHarborTaskCards,
  webEvalTaskCards,
} from "./cockpit/setup/cockpitTaskCards";
import { TaskDetailModal } from "./cockpit/setup/TaskDetailModal";
import type { TaskCardModel } from "./cockpit/setup/TaskSelectionRail";
import { taskCardIcon } from "./cockpit/setup/taskCardIcons";
import {
  CHIP_TEXT_CLASS,
  formatChipLabel,
  taskDisplayTitle,
  type DisplayTranslate,
} from "./cockpit/setup/taskCardLabels";
import { ToneChip, transportChipTone, type ToneChipTone } from "./cockpit/setup/ToneChip";
import type { PlaygroundTaskType } from "./cockpit/TaskTypeSwitch";
import { FOCUS_RING, Sym } from "./cockpit/cockpitShared";
import { StudioGlassPanel } from "./studio/StudioShell";
import {
  listChatbotEvalTasks,
  listOsAppEvalTasks,
  listSurveyHarborTasks,
  listWebEvalTasks,
} from "@/lib/api";
import {
  FALLBACK_OS_APP_TASKS,
  FALLBACK_SURVEY_HARBOR_TASKS,
  FALLBACK_WEB_TASKS,
} from "@/lib/fallbackTasks";
import { mergeTaskCatalog } from "@/lib/mergeTaskCatalog";
import type { ChatbotEvalTask, OsAppEvalTask, WebEvalTask } from "@/lib/types";

type TypeFilter = "all" | PlaygroundTaskType;

const TYPE_FILTERS: ReadonlyArray<TypeFilter> = ["all", "survey", "chatbot", "web", "os-app"];

function typeFilterLabel(value: TypeFilter, t: DisplayTranslate): string {
  const labels: Record<TypeFilter, { key: string; fallback: string }> = {
    all: { key: "catalog.taskGallery.filter.all", fallback: "All" },
    survey: { key: "catalog.taskGallery.filter.survey", fallback: "Survey" },
    chatbot: { key: "catalog.taskGallery.filter.chatbot", fallback: "Chatbot" },
    web: { key: "catalog.taskGallery.filter.web", fallback: "Web" },
    "os-app": { key: "catalog.taskGallery.filter.osApp", fallback: "OS App" },
  };
  const label = labels[value];
  return t(label.key, label.fallback);
}

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

function transportLabel(transport: TaskCardModel["transport"] | undefined, t: DisplayTranslate): string {
  if (transport === "api_sidecar") return t("taskDisplay.transport.apiSidecar", "API (sidecar)");
  if (transport === "api_external") return t("taskDisplay.transport.apiEndpoint", "API (endpoint)");
  if (transport === "mcp_sidecar") return t("taskDisplay.transport.mcpSidecar", "MCP (sidecar)");
  if (transport === "mcp_external") return t("taskDisplay.transport.mcpEndpoint", "MCP (endpoint)");
  return "—";
}

function taskSearchHaystack(card: TaskCardModel): string {
  return [
    card.id,
    card.title,
    card.subtitle ?? "",
    card.taskPath,
    card.domain ?? "",
    card.difficulty ?? "",
    card.metaType ?? "",
    card.platform ?? "",
    card.os ?? "",
    ...(card.searchTags ?? []),
    ...(card.tags?.map((tag) => tag.label) ?? []),
  ]
    .join(" ")
    .toLowerCase();
}

function mergeWebTasks(apiTasks: WebEvalTask[] | undefined): WebEvalTask[] {
  return mergeTaskCatalog(FALLBACK_WEB_TASKS, apiTasks, (row, api, base) => ({
    ...row,
    taskPath: api?.taskPath || base?.taskPath || row.taskPath || "",
  }));
}

function mergeOsAppTasks(apiTasks: OsAppEvalTask[] | undefined): OsAppEvalTask[] {
  return mergeTaskCatalog(FALLBACK_OS_APP_TASKS, apiTasks);
}

export interface TaskGalleryContentProps {
  onOpenInPlayground: (taskType: PlaygroundTaskType, taskId: string) => void;
  autoFocusSearch?: boolean;
}

export function TaskGalleryContent({
  onOpenInPlayground,
  autoFocusSearch = false,
}: TaskGalleryContentProps) {
  const { t, formatNumber } = useI18n();
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [detailCard, setDetailCard] = useState<TaskCardModel | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debouncedQuery = useDebounced(query.trim(), 220);

  useEffect(() => {
    if (!autoFocusSearch) return;
    const id = window.setTimeout(() => inputRef.current?.focus(), 40);
    return () => window.clearTimeout(id);
  }, [autoFocusSearch]);

  const surveyQuery = useQuery({
    queryKey: ["survey-eval-harbor-tasks"],
    queryFn: listSurveyHarborTasks,
    staleTime: 10 * 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
  const chatbotQuery = useQuery({
    queryKey: ["chatbot-eval-tasks"],
    queryFn: listChatbotEvalTasks,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
  const webQuery = useQuery({
    queryKey: ["web-eval-tasks"],
    queryFn: listWebEvalTasks,
    staleTime: 10 * 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
  const osAppQuery = useQuery({
    queryKey: ["os-app-eval-tasks"],
    queryFn: listOsAppEvalTasks,
    staleTime: 10 * 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  const allCards = useMemo(() => {
    const surveyTasks =
      (surveyQuery.data?.tasks?.length ?? 0) > 0
        ? surveyQuery.data!.tasks
        : surveyQuery.isError
          ? FALLBACK_SURVEY_HARBOR_TASKS
          : [];
    const chatbotTasks: ChatbotEvalTask[] = chatbotQuery.data?.tasks ?? [];
    const webTasks = mergeWebTasks(webQuery.data?.tasks);
    const osAppTasks = mergeOsAppTasks(osAppQuery.data?.tasks);

    return [
      ...surveyHarborTaskCards(surveyTasks),
      ...chatbotEvalTaskCards(chatbotTasks, undefined, t),
      ...webEvalTaskCards(webTasks),
      ...osAppTaskCards(osAppTasks),
    ];
  }, [
    chatbotQuery.data?.tasks,
    osAppQuery.data?.tasks,
    surveyQuery.data,
    surveyQuery.isError,
    webQuery.data?.tasks,
  ]);

  const filtered = useMemo(() => {
    const q = debouncedQuery.toLowerCase();
    return allCards.filter((card) => {
      if (typeFilter !== "all" && card.taskType !== typeFilter) return false;
      if (!q) return true;
      return taskSearchHaystack(card).includes(q);
    });
  }, [allCards, debouncedQuery, typeFilter]);

  const loading =
    (surveyQuery.isLoading || chatbotQuery.isLoading || webQuery.isLoading || osAppQuery.isLoading) &&
    allCards.length === 0;
  const allFailed =
    surveyQuery.isError && chatbotQuery.isError && webQuery.isError && osAppQuery.isError && allCards.length === 0;

  function handleOpen(card: TaskCardModel) {
    onOpenInPlayground(card.taskType, card.id);
  }

  return (
    <>
      <StudioGlassPanel className="mb-4 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="glass-tile flex h-9 min-w-0 flex-1 basis-56 items-center rounded-lg transition-colors focus-within:bg-surface-high/50">
            <Sym name="search" size={16} className="ml-3 flex-none text-text-dim" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("catalog.taskGallery.searchPlaceholder", "Search title, domain, path, or tags…")}
              aria-label={t("catalog.taskGallery.searchTasks", "Search tasks")}
              className="h-full w-full min-w-0 bg-transparent px-3 text-[14px] text-text-main outline-none placeholder:text-text-variant"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                aria-label={t("catalog.taskGallery.clearSearch", "Clear search")}
                className={`mr-2 flex-none rounded p-1 text-text-dim transition-colors hover:bg-surface-high hover:text-text-main ${FOCUS_RING}`}
              >
                <Sym name="close" size={16} />
              </button>
            )}
          </div>

          <div
            className="flex flex-wrap items-center gap-1.5"
            role="group"
            aria-label={t("catalog.taskGallery.filterByTaskType", "Filter by task type")}
          >
            {TYPE_FILTERS.map((value) => (
              <FilterChip
                key={value}
                label={typeFilterLabel(value, t)}
                active={typeFilter === value}
                onClick={() => setTypeFilter(value)}
              />
            ))}
          </div>

          <div className="flex shrink-0 items-baseline gap-1.5 pl-1">
            <span className="hud text-[11px] text-text-dim">{t("catalog.taskGallery.tasks", "Tasks")}</span>
            <span className="font-mono text-[15px] font-bold text-primary">
              {loading ? "…" : formatNumber(allCards.length)}
            </span>
          </div>
        </div>

        {(typeFilter !== "all" || debouncedQuery) && (
          <p className="mt-2 text-[13px] text-text-variant">
            {t("catalog.taskGallery.showing", "Showing {shown} of {total} tasks", {
              shown: formatNumber(filtered.length),
              total: formatNumber(allCards.length),
            })}
          </p>
        )}
      </StudioGlassPanel>

      {loading ? (
        <CatalogSkeleton />
      ) : allFailed ? (
        <CatalogError
          onRetry={() => {
            void surveyQuery.refetch();
            void chatbotQuery.refetch();
            void webQuery.refetch();
            void osAppQuery.refetch();
          }}
        />
      ) : filtered.length === 0 ? (
        <CatalogEmpty query={debouncedQuery} hasTypeFilter={typeFilter !== "all"} />
      ) : (
        <div className="grid grid-cols-1 items-stretch gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((card, i) => (
            <div
              key={`${card.taskType}:${card.id}`}
              className="rise-in h-full"
              style={{ animationDelay: `${Math.min(i, 8) * 25}ms` }}
            >
              <GalleryTaskCard
                card={card}
                onOpenDetail={() => setDetailCard(card)}
                onOpenInPlayground={() => handleOpen(card)}
              />
            </div>
          ))}
        </div>
      )}

      <TaskDetailModal
        open={Boolean(detailCard)}
        card={detailCard}
        onClose={() => setDetailCard(null)}
        primaryAction={
          detailCard
            ? {
                label: t("catalog.taskGallery.openPlayground", "Open in Playground"),
                onClick: () => handleOpen(detailCard),
              }
            : undefined
        }
      />
    </>
  );
}

function GalleryTaskCard({
  card,
  onOpenDetail,
  onOpenInPlayground,
}: {
  card: TaskCardModel;
  onOpenDetail: () => void;
  onOpenInPlayground: () => void;
}) {
  const { t } = useI18n();
  const unavailable = card.available === false;
  const displayTitle = taskDisplayTitle(card.title, card, t);
  return (
    <div
      className={`flex h-full flex-col rounded-xl border transition ${
        unavailable
          ? "border-outline/35 bg-surface/20 opacity-80"
          : "border-outline/40 bg-surface/30 hover:border-primary/30"
      }`}
    >
      <button
        type="button"
        onClick={onOpenDetail}
        className={`flex min-h-0 flex-1 items-start gap-3 p-4 text-left ${FOCUS_RING}`}
      >
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-outline/40 bg-surface-high/60">
          <Sym name={taskCardIcon(card.taskType, card)} size={20} className="text-text-variant" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-display text-[14px] font-semibold leading-tight text-text-main">{displayTitle}</p>
          {card.subtitle && (
            <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-text-dim">{card.subtitle}</p>
          )}
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <ToneChip tone="primary" className={CHIP_TEXT_CLASS}>
              {formatChipLabel(card.taskType, t)}
            </ToneChip>
            {card.transport && (
              <ToneChip tone={transportChipTone(card.transport)} className={CHIP_TEXT_CLASS}>
                {transportLabel(card.transport, t)}
              </ToneChip>
            )}
            {(
              card.tags ??
              (card.tagLabels?.map((label) => ({ label, tone: "neutral" as ToneChipTone })) ?? [])
            )
              .slice(0, 4)
              .map((tag) => (
                <ToneChip
                  key={tag.label}
                  tone={tag.tone}
                  showDot={tag.label === "Available" || tag.label === "Unavailable"}
                  className={CHIP_TEXT_CLASS}
                >
                  {formatChipLabel(tag.label, t)}
                </ToneChip>
              ))}
          </div>
        </div>
      </button>
      <div className="flex items-center gap-2 border-t border-outline/25 px-3 py-2.5">
        <button
          type="button"
          onClick={onOpenDetail}
          className={`inline-flex h-8 items-center gap-1 rounded-md px-2 text-[12px] font-medium text-text-variant hover:bg-surface-high hover:text-text-main ${FOCUS_RING}`}
        >
          <Sym name="info" size={14} />
          {t("catalog.taskGallery.details", "Details")}
        </button>
        <button
          type="button"
          onClick={onOpenInPlayground}
          className={`glass-tile glass-tile--hover ml-auto inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-[12px] font-semibold text-primary ${FOCUS_RING}`}
        >
          <Sym name="play_arrow" size={15} />
          {t("catalog.taskGallery.openPlayground", "Open in Playground")}
        </button>
      </div>
    </div>
  );
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex h-8 items-center rounded-md px-3 text-[13px] font-medium transition-colors ${FOCUS_RING} ${
        active
          ? "bg-primary text-on-primary"
          : "glass-tile glass-tile--hover text-text-variant hover:text-text-main"
      }`}
    >
      {label}
    </button>
  );
}

function CatalogSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" aria-hidden>
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="glass-panel rounded-xl p-4">
          <div className="mb-3 flex items-start justify-between">
            <div className="h-10 w-10 animate-rb-pulse rounded bg-surface-high" />
            <div className="h-3.5 w-14 animate-rb-pulse rounded bg-surface-high" />
          </div>
          <div className="h-3.5 w-2/3 animate-rb-pulse rounded bg-surface-high" />
          <div className="mt-2 h-2.5 w-1/2 animate-rb-pulse rounded bg-surface-high" />
        </div>
      ))}
    </div>
  );
}

function CatalogEmpty({ query, hasTypeFilter }: { query: string; hasTypeFilter: boolean }) {
  const { t } = useI18n();
  return (
    <div className="glass-panel rise-in flex flex-col items-center rounded-xl px-4 py-16 text-center">
      <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-lg border border-dashed border-outline/50 bg-surface/50">
        <Sym name="search_off" size={26} className="text-text-dim" />
      </div>
      <p className="font-display text-[15px] font-semibold text-text-main">
        {query || hasTypeFilter
          ? t("catalog.taskGallery.noMatches", "No matches")
          : t("catalog.taskGallery.noTasksYet", "No tasks yet")}
      </p>
      <p className="mt-1 max-w-[320px] text-[14px] leading-snug text-text-variant">
        {query
          ? t("catalog.taskGallery.nothingMatches", "Nothing matches \"{query}\". Try another title, domain, or tag.", {
              query,
            })
          : hasTypeFilter
            ? t("catalog.taskGallery.noTasksInType", "No tasks in this type. Try All or another filter.")
            : t(
                "catalog.taskGallery.emptyDescription",
                "Task catalogs are empty. Check the backend and application/tasks.",
              )}
      </p>
    </div>
  );
}

function CatalogError({ onRetry }: { onRetry: () => void }) {
  const { t } = useI18n();
  return (
    <div className="glass-panel rise-in mx-auto max-w-md rounded-xl border-l-4 border-l-danger px-4 py-6 text-center">
      <Sym name="error" size={24} className="mx-auto mb-2 text-danger" />
      <p className="font-display text-[15px] font-semibold text-text-main">
        {t("catalog.taskGallery.loadFailed", "Couldn't load tasks")}
      </p>
      <p className="mx-auto mt-1 max-w-[300px] text-[14px] leading-snug text-text-variant">
        {t("catalog.taskGallery.loadFailedDescription", "Check the backend is running, then retry.")}
      </p>
      <button
        type="button"
        onClick={onRetry}
        className={`mt-3 inline-flex items-center gap-1.5 rounded-md border border-danger/40 bg-danger/10 px-3 py-1.5 text-[13px] font-medium text-danger ${FOCUS_RING}`}
      >
        <Sym name="refresh" size={15} />
        {t("catalog.taskGallery.tryAgain", "Try again")}
      </button>
    </div>
  );
}
