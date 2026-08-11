/**
 * RunsView: Harbor job history inside Playground.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { RunDetail } from "./RunDetail";
import { HarborJobDetail } from "./HarborJobDetail";
import { FOCUS_RING, Sym } from "./cockpit/cockpitShared";
import { AppTypeTag } from "./runsShared";
import {
  StudioGlassPanel,
  StudioMeshShell,
  StudioPageFrame,
  StudioPageHeader,
  StudioToolbarButton,
} from "./studio/StudioShell";
import { api, ApiError } from "@/lib/api";
import { jobDisplayIdentity } from "@/lib/jobDisplay";
import {
  deriveHarborJobListStatus,
  harborJobListStatusLabel,
} from "@/lib/trialStatus";
import type { HarborJobListStatus, HarborJobSummary } from "@/lib/types";
import { useI18n } from "../i18n/I18nProvider";

export interface RunsViewProps {
  harborJobId: string | null;
  harborTrialId: string | null;
  openHarborJob: (jobName: string) => void;
  openHarborTrial: (jobName: string, trialName: string) => void;
  backToList: () => void;
  backToHarborJob: () => void;
  onClose: () => void;
  backLabel?: string;
}

export function RunsView({
  harborJobId,
  harborTrialId,
  openHarborJob,
  openHarborTrial,
  backToList,
  backToHarborJob,
  onClose,
  backLabel = "Back",
}: RunsViewProps) {
  if (harborJobId && harborTrialId) {
    return (
      <StudioMeshShell>
        <RunDetail
          harborTrial={{ jobName: harborJobId, trialName: harborTrialId }}
          onBack={backToHarborJob}
        />
      </StudioMeshShell>
    );
  }
  if (harborJobId) {
    return (
      <StudioMeshShell>
        <HarborJobDetail
          jobName={harborJobId}
          onBack={backToList}
          onOpenTrial={(trialName) => openHarborTrial(harborJobId, trialName)}
        />
      </StudioMeshShell>
    );
  }
  return <HarborJobsList openHarborJob={openHarborJob} onClose={onClose} backLabel={backLabel} />;
}

interface HarborJobsListProps {
  openHarborJob: (jobName: string) => void;
  onClose: () => void;
  backLabel: string;
}

function sortHarborJobs(jobs: HarborJobSummary[]): HarborJobSummary[] {
  return [...jobs].sort((a, b) => {
    const ta = Date.parse(a.startedAt ?? a.updatedAt ?? "") || 0;
    const tb = Date.parse(b.startedAt ?? b.updatedAt ?? "") || 0;
    return tb - ta;
  });
}

function formatJobTimeFull(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const date = new Date(t);
  const y = date.getFullYear();
  const mo = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  const h = String(date.getHours()).padStart(2, "0");
  const mi = String(date.getMinutes()).padStart(2, "0");
  const s = String(date.getSeconds()).padStart(2, "0");
  return `${y}-${mo}-${d} ${h}:${mi}:${s}`;
}

function harborJobAppType(job: HarborJobSummary): string {
  const explicit = (job.applicationType ?? "").toString().toLowerCase();
  if (explicit && explicit !== "unknown") return explicit;
  const name = job.jobName.toLowerCase();
  if (name.includes("survey")) return "survey";
  if (name.includes("web") || name.includes("playwright") || name.includes("cocoa")) return "web";
  if (name.includes("computer-use") || name.includes("os-app") || name.includes("cua")) return "os-app";
  if (name.includes("appworld")) return "os-app";
  return "chatbot";
}

/** Shared column template for the Harbor jobs table (header + rows + skeleton). */
const HARBOR_JOBS_GRID =
  "grid grid-cols-[minmax(0,1fr)_5.75rem_9.75rem_4.25rem_minmax(5.5rem,6.25rem)_2.25rem] items-center gap-x-5";

type AppTypeFilter = "all" | "chatbot" | "survey" | "web" | "os-app";
type StatusFilter = "all" | HarborJobListStatus;

const APP_TYPE_FILTER_OPTIONS: { value: Exclude<AppTypeFilter, "all">; label: string }[] = [
  { value: "chatbot", label: "Chatbot" },
  { value: "survey", label: "Survey" },
  { value: "web", label: "Web" },
  { value: "os-app", label: "OS app" },
];

const STATUS_FILTER_OPTIONS: { value: Exclude<StatusFilter, "all">; label: string }[] = [
  { value: "running", label: "Running" },
  { value: "success", label: "Success" },
  { value: "failed", label: "Failed" },
];

function harborJobSearchHaystack(job: HarborJobSummary): string {
  const status = deriveHarborJobListStatus(job);
  const timeIso = job.startedAt ?? job.updatedAt;
  const appType = harborJobAppType(job);
  const identity = jobDisplayIdentity(job.jobName, appType);
  return [
    job.jobName,
    job.taskTitle,
    job.taskName,
    job.domain,
    job.difficulty,
    ...(job.tags ?? []),
    identity.title,
    identity.shortId,
    appType,
    harborJobListStatusLabel(status),
    formatJobTimeFull(timeIso),
    `${job.completedTrials ?? job.trialCount}/${job.trialCount}`,
  ]
    .join(" ")
    .toLowerCase();
}

function filterHarborJobs(
  jobs: HarborJobSummary[],
  {
    searchQuery,
    appTypeFilter,
    statusFilter,
  }: {
    searchQuery: string;
    appTypeFilter: AppTypeFilter;
    statusFilter: StatusFilter;
  },
): HarborJobSummary[] {
  const q = searchQuery.trim().toLowerCase();
  return jobs.filter((job) => {
    if (appTypeFilter !== "all" && harborJobAppType(job) !== appTypeFilter) return false;
    if (statusFilter !== "all" && deriveHarborJobListStatus(job) !== statusFilter) return false;
    if (!q) return true;
    return harborJobSearchHaystack(job).includes(q);
  });
}

function runsFiltersActive(
  searchQuery: string,
  appTypeFilter: AppTypeFilter,
  statusFilter: StatusFilter,
): boolean {
  return searchQuery.trim() !== "" || appTypeFilter !== "all" || statusFilter !== "all";
}

const JOB_STATUS_STYLES: Record<
  HarborJobListStatus,
  { className: string; icon: string; fill?: 0 | 1 }
> = {
  running: {
    className: "bg-warn/10 text-warn",
    icon: "autorenew",
  },
  success: {
    className: "bg-secondary/10 text-secondary",
    icon: "check_circle",
    fill: 1,
  },
  failed: {
    className: "bg-danger/10 text-danger",
    icon: "error",
    fill: 1,
  },
};

const JOB_PROGRESS_STYLES: Record<
  HarborJobListStatus,
  { bar: string; track?: string }
> = {
  running: {
    bar: "bg-warn animate-pulse",
  },
  success: {
    bar: "bg-secondary",
  },
  failed: {
    bar: "bg-danger",
  },
};

function JobTrialProgress({
  job,
  status,
}: {
  job: HarborJobSummary;
  status: HarborJobListStatus;
}) {
  const { t } = useI18n();
  const completed = job.completedTrials ?? 0;
  const total = Math.max(job.trialCount ?? 0, 0);
  const ratio = total > 0 ? Math.min(1, completed / total) : 0;
  const style = JOB_PROGRESS_STYLES[status];
  const label =
    total === 0
      ? t("runs.noTrials", "No trials")
      : total === 1
        ? t("runs.trialsComplete", "{completed} of {total} {trialLabel} complete", {
            completed,
            total,
            trialLabel: t("runs.trial", "trial"),
          })
        : t("runs.trialsComplete", "{completed} of {total} {trialLabel} complete", {
            completed,
            total,
            trialLabel: t("runs.trials", "trials"),
          });

  return (
    <div
      className="mt-1.5 h-1.5 min-w-[5rem] overflow-hidden rounded-full bg-surface-high"
      role="progressbar"
      aria-valuenow={completed}
      aria-valuemin={0}
      aria-valuemax={total}
      aria-label={label}
    >
      <div
        className={`h-full rounded-full transition-[width] duration-300 ${style.bar}`}
        style={{ width: `${ratio * 100}%` }}
      />
    </div>
  );
}

const JOB_TRIAL_COUNT_STYLES: Record<HarborJobListStatus, string> = {
  running: "bg-warn/10",
  success: "bg-secondary/10",
  failed: "bg-danger/10",
};

function JobTrialCountCell({
  job,
  status,
  onOpen,
}: {
  job: HarborJobSummary;
  status: HarborJobListStatus;
  onOpen: () => void;
}) {
  const { t } = useI18n();
  const completed = job.completedTrials ?? 0;
  const total = Math.max(job.trialCount ?? 0, 0);
  const inProgress = status === "running" && completed < total;
  const countLabel = t(total === 1 ? "runs.trial" : "runs.trials", total === 1 ? "trial" : "trials");
  const detail =
    total === 0
      ? t("runs.noTrials", "No trials")
      : inProgress
        ? t("runs.trialsComplete", "{completed} of {total} {trialLabel} complete", {
            completed,
            total,
            trialLabel: countLabel,
          })
        : `${total} ${countLabel}`;

  return (
    <button
      type="button"
      onClick={onOpen}
      title={detail}
      className={`justify-self-center ${FOCUS_RING}`}
    >
      <div
        className={`inline-flex min-w-[3.5rem] flex-col items-center rounded-lg px-2.5 py-1.5 shadow-[inset_0_1px_0_rgb(255_255_255/0.06)] ${JOB_TRIAL_COUNT_STYLES[status]}`}
      >
        <span className="font-display text-[20px] font-bold leading-none tabular-nums text-text-main">
          {inProgress ? (
            <>
              {completed}
              <span className="text-[14px] font-semibold text-text-dim">/{total}</span>
            </>
          ) : (
            total
          )}
        </span>
        <span className="mt-0.5 font-mono text-[11px] uppercase tracking-wide text-text-dim">
          {countLabel}
        </span>
      </div>
    </button>
  );
}

function JobListIdentity({
  job,
  onOpen,
}: {
  job: HarborJobSummary;
  onOpen: () => void;
}) {
  const appType = harborJobAppType(job);
  const status = deriveHarborJobListStatus(job);
  const identity = jobDisplayIdentity(job.jobName, appType);
  // Prefer title derived from task.toml ``[task].name``.
  const title = (job.taskTitle ?? "").trim() || identity.title;
  const metaChips = [
    job.domain,
    job.difficulty,
  ]
    .map((value) => (value ?? "").trim())
    .filter(Boolean);

  return (
    <button
      type="button"
      onClick={onOpen}
      className={`min-w-0 text-left ${FOCUS_RING}`}
      title={job.taskName || job.jobName}
    >
      <p className="truncate font-display text-[15px] font-semibold leading-snug text-text-main group-hover:text-primary">
        {title}
      </p>
      {job.taskName ? (
        <p className="truncate font-mono text-[12px] tracking-wide text-text-dim">{job.taskName}</p>
      ) : identity.shortId && identity.shortId !== title ? (
        <p className="truncate font-mono text-[12px] tracking-wide text-text-dim">{identity.shortId}</p>
      ) : title !== job.jobName ? (
        <p className="truncate font-mono text-[12px] tracking-wide text-text-dim">{job.jobName}</p>
      ) : null}
      {metaChips.length > 0 ? (
        <div className="mt-1 flex flex-wrap gap-1">
          {metaChips.map((chip) => (
            <span
              key={chip}
              className="rounded glass-tile px-1.5 py-0.5 text-[11px] text-text-variant"
            >
              {chip}
            </span>
          ))}
        </div>
      ) : null}
      <JobTrialProgress job={job} status={status} />
    </button>
  );
}

function HarborJobStatusBadge({ job }: { job: HarborJobSummary }) {
  const { t } = useI18n();
  const status = deriveHarborJobListStatus(job);
  const style = JOB_STATUS_STYLES[status];
  const label = t(`runs.status.${status}`, harborJobListStatusLabel(status));
  const detail =
    status === "failed" && (job.failedTrials ?? 0) > 0
      ? t("runs.failedTrials", "{statusLabel} · {count} trial{suffix} failed", {
          statusLabel: label,
          count: job.failedTrials ?? 0,
          suffix: job.failedTrials === 1 ? "" : "s",
        })
      : label;

  return (
    <span
      className={`inline-flex max-w-full items-center gap-1 truncate rounded-md px-2 py-0.5 font-mono text-[12px] uppercase tracking-wide ${style.className}`}
      title={detail}
    >
      <Sym
        name={style.icon}
        size={12}
        fill={style.fill}
        className={status === "running" ? "shrink-0 animate-rb-spin" : "shrink-0"}
      />
      <span className="truncate">{label}</span>
    </span>
  );
}

function HarborJobsList({ openHarborJob, onClose, backLabel }: HarborJobsListProps) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [appTypeFilter, setAppTypeFilter] = useState<AppTypeFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const harborQuery = useQuery({
    queryKey: ["harbor-jobs"],
    queryFn: api.listHarborJobs,
    refetchInterval: 5000,
  });
  const harborJobs = useMemo(
    () => sortHarborJobs(harborQuery.data?.jobs ?? []),
    [harborQuery.data],
  );
  const filteredJobs = useMemo(
    () =>
      filterHarborJobs(harborJobs, {
        searchQuery,
        appTypeFilter,
        statusFilter,
      }),
    [harborJobs, searchQuery, appTypeFilter, statusFilter],
  );
  const filtersActive = runsFiltersActive(searchQuery, appTypeFilter, statusFilter);

  const clearFilters = () => {
    setSearchQuery("");
    setAppTypeFilter("all");
    setStatusFilter("all");
  };

  const deleteMutation = useMutation({
    mutationFn: (jobName: string) => api.deleteHarborJob(jobName),
    onSuccess: () => {
      setDeleteError(null);
      void queryClient.invalidateQueries({ queryKey: ["harbor-jobs"] });
    },
    onError: (error) => {
      setDeleteError(error instanceof ApiError ? error.message : t("runs.couldNotDelete", "Could not delete job."));
    },
  });

  const handleDelete = (job: HarborJobSummary) => {
    const ok = window.confirm(
      t("runs.deleteConfirm", "Delete \"{jobName}\"?\n\nThis removes the job folder under jobs/ and cannot be undone.", {
        jobName: job.jobName,
      }),
    );
    if (!ok) return;
    deleteMutation.mutate(job.jobName);
  };

  return (
    <StudioMeshShell>
      <StudioPageFrame>
        <StudioPageHeader
          compact
          eyebrow={t("runs.eyebrow", "MatrAIx · Runs")}
          title={t("runs.title", "Runs")}
          subtitle={t("runs.subtitle", "Harbor jobs in {jobsPath} — launch from Playground, debrief trials here.", {
            jobsPath: "jobs/",
          })}
          meta={
            !harborQuery.isLoading && !harborQuery.isError ? (
              <span className="font-mono text-[13px] text-text-variant">
                {filtersActive
                  ? t("runs.filteredJobCount", "{filtered} of {total} jobs", {
                      filtered: filteredJobs.length,
                      total: harborJobs.length,
                    })
                  : t("runs.jobCount", "{count} job{suffix}", {
                      count: harborJobs.length,
                      suffix: harborJobs.length === 1 ? "" : "s",
                    })}
              </span>
            ) : null
          }
          actions={
            <>
              <StudioToolbarButton icon="arrow_back" onClick={onClose}>
                {backLabel === "Back" ? t("runs.back", "Back") : backLabel}
              </StudioToolbarButton>
              <StudioToolbarButton
                icon="refresh"
                onClick={() => harborQuery.refetch()}
                disabled={harborQuery.isFetching}
              >
                {harborQuery.isFetching
                  ? t("runs.refreshing", "Refreshing…")
                  : t("runs.refresh", "Refresh")}
              </StudioToolbarButton>
            </>
          }
        />
        {deleteError && (
          <p className="mb-4 text-[14px] text-danger" role="alert">
            {deleteError}
          </p>
        )}

        {harborQuery.isLoading ? (
          <ListLoading />
        ) : harborQuery.isError ? (
          <ListError error={harborQuery.error} onRetry={() => harborQuery.refetch()} />
        ) : harborJobs.length === 0 ? (
          <ListEmpty onClose={onClose} />
        ) : (
          <>
            <HarborJobsFilterBar
              searchQuery={searchQuery}
              onSearchQueryChange={setSearchQuery}
              appTypeFilter={appTypeFilter}
              onAppTypeFilterChange={setAppTypeFilter}
              statusFilter={statusFilter}
              onStatusFilterChange={setStatusFilter}
              onClearFilters={clearFilters}
              filtersActive={filtersActive}
            />
            {filteredJobs.length === 0 ? (
              <ListFilterEmpty onClearFilters={clearFilters} />
            ) : (
              <HarborJobsTable
                jobs={filteredJobs}
                onOpen={openHarborJob}
                onDelete={handleDelete}
                deletingJobName={deleteMutation.isPending ? deleteMutation.variables : null}
              />
            )}
          </>
        )}
      </StudioPageFrame>
    </StudioMeshShell>
  );
}

function HarborJobsFilterBar({
  searchQuery,
  onSearchQueryChange,
  appTypeFilter,
  onAppTypeFilterChange,
  statusFilter,
  onStatusFilterChange,
  onClearFilters,
  filtersActive,
}: {
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  appTypeFilter: AppTypeFilter;
  onAppTypeFilterChange: (value: AppTypeFilter) => void;
  statusFilter: StatusFilter;
  onStatusFilterChange: (value: StatusFilter) => void;
  onClearFilters: () => void;
  filtersActive: boolean;
}) {
  const { t } = useI18n();
  return (
    <StudioGlassPanel className="mb-3 p-3">
      <div className="flex h-8 min-w-0 items-center rounded-lg glass-tile backdrop-blur transition-colors focus-within:border-primary/50">
        <Sym name="search" size={16} className="ml-3 flex-none text-text-dim" />
        <input
          type="search"
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
          placeholder={t("runs.searchPlaceholder", "Search by job name, app type, or status…")}
          aria-label={t("runs.searchRuns", "Search runs")}
          className="h-full w-full min-w-0 bg-transparent px-3 text-[15px] text-text-main outline-none placeholder:text-text-variant"
        />
        {searchQuery && (
          <button
            type="button"
            onClick={() => onSearchQueryChange("")}
            aria-label={t("runs.clearSearch", "Clear search")}
            className={`mr-2 flex-none rounded p-1 text-text-dim transition-colors hover:bg-surface-high hover:text-text-main ${FOCUS_RING}`}
          >
            <Sym name="close" size={16} />
          </button>
        )}
      </div>

      <div className="mt-2.5 flex flex-col gap-2 border-t border-outline/20 pt-2.5 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-3">
          <span className="cockpit-field-label shrink-0 text-[12px] text-text-dim">{t("runs.appType", "App type")}</span>
          <div className="flex flex-wrap gap-2" role="group" aria-label={t("runs.filterByAppType", "Filter by app type")}>
            <RunsFilterChip
              label={t("runs.all", "All")}
              active={appTypeFilter === "all"}
              onClick={() => onAppTypeFilterChange("all")}
            />
            {APP_TYPE_FILTER_OPTIONS.map((option) => (
              <RunsFilterChip
                key={option.value}
                label={t(`runs.appType.${option.value === "os-app" ? "osApp" : option.value}`, option.label)}
                active={appTypeFilter === option.value}
                onClick={() => onAppTypeFilterChange(option.value)}
              />
            ))}
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-3 lg:pl-4">
          <span className="hidden h-6 w-px bg-outline/30 sm:block" aria-hidden />
          <span className="cockpit-field-label shrink-0 text-[12px] text-text-dim">{t("runs.status", "Status")}</span>
          <div className="flex flex-wrap gap-2" role="group" aria-label={t("runs.filterByStatus", "Filter by status")}>
            <RunsFilterChip
              label={t("runs.all", "All")}
              active={statusFilter === "all"}
              onClick={() => onStatusFilterChange("all")}
            />
            {STATUS_FILTER_OPTIONS.map((option) => (
              <RunsFilterChip
                key={option.value}
                label={t(`runs.status.${option.value}`, option.label)}
                active={statusFilter === option.value}
                onClick={() => onStatusFilterChange(option.value)}
              />
            ))}
          </div>
        </div>
      </div>

      {filtersActive && (
        <div className="mt-3 flex justify-end border-t border-outline/20 pt-3">
          <button
            type="button"
            onClick={onClearFilters}
            className={`inline-flex h-8 items-center gap-1.5 rounded-md glass-tile glass-tile--hover px-3 text-[13px] font-medium text-text-variant transition-colors hover:text-text-main ${FOCUS_RING}`}
          >
            <Sym name="filter_alt_off" size={15} />
            {t("runs.clearFilters", "Clear filters")}
          </button>
        </div>
      )}
    </StudioGlassPanel>
  );
}

function RunsFilterChip({
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
      className={`inline-flex h-8 items-center rounded-full border px-2.5 text-[13px] font-medium transition-colors ${FOCUS_RING} ${
        active
          ? "border-primary bg-primary text-on-primary active:bg-primary-dim"
          : "glass-tile glass-tile--hover border-transparent text-text-variant hover:text-text-main"
      }`}
    >
      {label}
    </button>
  );
}

function HarborJobsTable({
  jobs,
  onOpen,
  onDelete,
  deletingJobName,
}: {
  jobs: HarborJobSummary[];
  onOpen: (jobName: string) => void;
  onDelete: (job: HarborJobSummary) => void;
  deletingJobName: string | null | undefined;
}) {
  const { t } = useI18n();
  return (
    <StudioGlassPanel className="rounded-xl">
      <div
        className={`${HARBOR_JOBS_GRID} border-b border-outline/40 px-4 py-2.5 text-[12px] uppercase tracking-wide text-text-dim`}
      >
        <span>{t("runs.job", "Job")}</span>
        <span>{t("runs.appType", "App type")}</span>
        <span>{t("runs.started", "Started")}</span>
        <span className="text-center">{t("runs.trialsHeader", "Trials")}</span>
        <span className="justify-self-end">{t("runs.status", "Status")}</span>
        <span className="sr-only">{t("runs.actions", "Actions")}</span>
      </div>
      <ul className="divide-y divide-outline-dim">
        {jobs.map((job) => {
          const timeIso = job.startedAt ?? job.updatedAt;
          const deleting = deletingJobName === job.jobName;
          return (
            <li key={job.jobName} className="group">
              <div className={`${HARBOR_JOBS_GRID} px-4 py-3.5`}>
                <JobListIdentity job={job} onOpen={() => onOpen(job.jobName)} />
                <div className="min-w-0">
                  <AppTypeTag type={harborJobAppType(job)} />
                </div>
                <button
                  type="button"
                  onClick={() => onOpen(job.jobName)}
                  title={timeIso ?? undefined}
                  className={`whitespace-nowrap text-left font-mono text-[13px] tabular-nums text-text-variant hover:text-text-main ${FOCUS_RING}`}
                >
                  {formatJobTimeFull(timeIso)}
                </button>
                <JobTrialCountCell
                  job={job}
                  status={deriveHarborJobListStatus(job)}
                  onOpen={() => onOpen(job.jobName)}
                />
                <div className="min-w-0 justify-self-end">
                  <HarborJobStatusBadge job={job} />
                </div>
                <button
                  type="button"
                  aria-label={t("runs.delete", "Delete {jobName}", { jobName: job.jobName })}
                  disabled={deleting}
                  onClick={() => onDelete(job)}
                  className={`grid h-8 w-8 place-items-center rounded-md text-text-dim opacity-0 transition hover:bg-danger/10 hover:text-danger group-hover:opacity-100 disabled:opacity-40 ${FOCUS_RING}`}
                >
                  <Sym
                    name={deleting ? "autorenew" : "delete"}
                    size={16}
                    className={deleting ? "animate-rb-spin" : ""}
                  />
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </StudioGlassPanel>
  );
}

function ListLoading() {
  return (
    <StudioGlassPanel className="rounded-xl" aria-hidden>
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className={`${HARBOR_JOBS_GRID} border-b border-outline-dim px-4 py-3.5 last:border-b-0`}
        >
          <div className="space-y-1.5">
            <div className="h-3.5 w-3/5 animate-rb-pulse rounded bg-surface-high" />
            <div className="h-2.5 w-16 animate-rb-pulse rounded bg-surface-high" />
            <div className="h-1 w-full animate-rb-pulse rounded-full bg-surface-high" />
          </div>
          <div className="h-3.5 w-14 animate-rb-pulse rounded bg-surface-high" />
          <div className="h-3.5 animate-rb-pulse rounded bg-surface-high" />
          <div className="mx-auto h-10 w-12 animate-rb-pulse rounded-lg bg-surface-high" />
          <div className="ml-auto h-3.5 w-16 animate-rb-pulse rounded bg-surface-high" />
        </div>
      ))}
    </StudioGlassPanel>
  );
}

function ListFilterEmpty({ onClearFilters }: { onClearFilters: () => void }) {
  const { t } = useI18n();
  return (
    <StudioGlassPanel className="px-6 py-12 text-center rise-in">
      <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-md glass-tile">
        <Sym name="search_off" size={24} className="text-text-dim" />
      </div>
      <h2 className="font-display text-[15px] font-semibold text-text-main">{t("runs.noMatchingRuns", "No matching runs")}</h2>
      <p className="mx-auto mt-2 max-w-md text-[15px] leading-relaxed text-text-variant">
        {t("runs.noMatchingRunsDetail", "Try a different search term or clear the app type and status filters.")}
      </p>
      <button
        type="button"
        onClick={onClearFilters}
        className={`mt-4 inline-flex items-center gap-1.5 rounded-md glass-tile glass-tile--hover px-4 py-2 text-[14px] text-text-variant transition hover:text-text-main ${FOCUS_RING}`}
      >
        <Sym name="filter_alt_off" size={16} />
        {t("runs.clearFilters", "Clear filters")}
      </button>
    </StudioGlassPanel>
  );
}

function ListEmpty({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  return (
    <StudioGlassPanel className="px-6 py-14 text-center rise-in">
      <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-md glass-tile">
        <Sym name="history" size={26} className="text-text-dim" />
      </div>
      <h2 className="font-display text-[15px] font-semibold text-text-main">{t("runs.noRunsYet", "No runs yet")}</h2>
      <p className="mx-auto mt-2 max-w-md text-[15px] leading-relaxed text-text-variant">
        {t("runs.noRunsYetDetail", "Launch a batch from Playground to run personas at scale. Results appear here under {jobsPath}.", {
          jobsPath: "jobs/",
        })}
      </p>
      <button
        type="button"
        onClick={onClose}
        className={`mt-4 inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-[14px] text-on-primary glow transition ease-out hover:bg-primary-dim active:scale-[0.97] ${FOCUS_RING}`}
      >
        <Sym name="play_arrow" fill={1} size={16} />
        {t("runs.backHome", "Back to home")}
      </button>
    </StudioGlassPanel>
  );
}

function ListError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const { t } = useI18n();
  const message =
    error instanceof ApiError
      ? error.message
      : t("runs.somethingWrongLoadingRuns", "Something went wrong loading runs.");
  return (
    <StudioGlassPanel className="border-l-4 border-l-danger px-5 py-8 text-center rise-in">
      <h2 className="font-display text-[15px] font-semibold text-text-main">{t("runs.couldntLoadJobs", "Couldn’t load jobs")}</h2>
      <p className="mx-auto mt-1.5 max-w-md break-words text-[15px] leading-relaxed text-text-variant">
        {message}
      </p>
      <button
        type="button"
        onClick={onRetry}
        className={`mt-4 inline-flex items-center gap-1.5 rounded-md bg-danger/10 px-4 py-2 text-[14px] text-danger ${FOCUS_RING}`}
      >
        <Sym name="refresh" size={16} />
        {t("runs.tryAgain", "Try again")}
      </button>
    </StudioGlassPanel>
  );
}

export default RunsView;
