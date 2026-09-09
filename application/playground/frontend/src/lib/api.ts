import type {
  ConfigOptionsResponse,
  PlaygroundPersonasResponse,
  PlaygroundResult,
  HarborJobAggregation,
  HarborJobDetail,
  HarborJobLaunchResponse,
  HarborJobsListResponse,
  HarborJobLiveResponse,
  HarborJobStatusResponse,
  HarborTrialEventsResponse,
  PersonaDatasetListResponse,
  PersonaDimensionLabels,
  PersonaMatchAttributesResponse,
  PersonaPoolCatalog,
  OverlayDimension,
  PersonaPoolCardsResponse,
  PersonaPoolIdsResponse,
  PersonaPoolPersonaDetail,
  PersonaPoolGenerateResult,
  PersonaPoolGenerateProgress,
  PersonaPoolSampleResult,
  TaskDetail,
  TaskPersonaStrategy,
  PersonaCohortDetail,
  PersonaCohortSummary,
  PreflightResponse,
  ChatbotSidecarsResponse,
  StartChatbotSidecarResponse,
  SurveyInstrumentsResponse,
  SurveyHarborTasksResponse,
  ChatbotEvalTasksResponse,
  WebEvalTasksResponse,
  WebTrace,
  OsAppEvalTasksResponse,
} from "./types";
import { PERSONA_BENCH_POOL, PERSONA_CARD_PREVIEW_LIMIT } from "./types";
import { normalizePersonaPoolName } from "./personaDisplay";

/** Backend `/persona-pool/personas` rejects limit > 500. */
const PERSONA_POOL_CARDS_LIMIT_MAX = 500;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? data.detail : data;
    const message = typeof detail === "string" ? detail : response.statusText;
    throw new ApiError(response.status, message || "Request failed", detail);
  }
  return data as T;
}

async function downloadFile(path: string, fallbackFilename: string): Promise<void> {
  const response = await fetch(path);
  if (!response.ok) {
    let message = response.statusText || "Download failed";
    try {
      const data = await response.json();
      if (data && typeof data === "object" && "detail" in data && typeof data.detail === "string") {
        message = data.detail;
      }
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, message);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  const filename = match?.[1]?.trim() || fallbackFilename;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function qs(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

function normalizePersonaPoolCardsResponse(
  response: PersonaPoolCardsResponse,
): PersonaPoolCardsResponse {
  return {
    ...response,
    personas: response.personas.map((persona) => normalizePersonaPoolName(persona)),
  };
}

function normalizePersonaPoolDetail(
  response: PersonaPoolPersonaDetail,
): PersonaPoolPersonaDetail {
  return normalizePersonaPoolName(response);
}

export const api = {
  getPreflight: () => request<PreflightResponse>("/api/preflight"),
  getChatbotSidecars: () => request<ChatbotSidecarsResponse>("/api/chatbot-sidecars"),
  startChatbotSidecar: (applicationId: string) =>
    request<StartChatbotSidecarResponse>(
      `/api/chatbot-sidecars/${encodeURIComponent(applicationId)}/start`,
      { method: "POST" },
    ),
  getConfigOptions: () => request<ConfigOptionsResponse>("/api/config/options"),
  listChatbotEvalTasks: () => request<ChatbotEvalTasksResponse>("/api/chatbot-eval/tasks"),

  listHarborJobs: () => request<HarborJobsListResponse>("/api/harbor/jobs"),
  deleteHarborJob: (jobName: string) =>
    request<{ deleted: boolean; jobName: string }>(
      `/api/harbor/jobs/${encodeURIComponent(jobName)}`,
      { method: "DELETE" },
    ),
  getHarborJob: (jobName: string) =>
    request<HarborJobDetail>(`/api/harbor/jobs/${encodeURIComponent(jobName)}`),
  retryHarborJobFailed: (jobName: string) =>
    request<{ jobName: string; retried: number }>(
      `/api/harbor/jobs/${encodeURIComponent(jobName)}/retry-failed`,
      { method: "POST" },
    ),
  getHarborJobAggregation: (jobName: string) =>
    request<HarborJobAggregation>(
      `/api/harbor/jobs/${encodeURIComponent(jobName)}/aggregation`,
    ),
  downloadHarborJobReportPdf: (jobName: string) =>
    downloadFile(
      `/api/harbor/jobs/${encodeURIComponent(jobName)}/report.pdf`,
      `${jobName}-persona-task-batch-report.pdf`,
    ),
  getHarborJobLive: (jobName: string) =>
    request<HarborJobLiveResponse>(`/api/harbor/jobs/${encodeURIComponent(jobName)}/live`),
  getHarborJobStatus: (jobName: string, since = 0) =>
    request<HarborJobStatusResponse>(
      `/api/harbor/jobs/${encodeURIComponent(jobName)}/status${qs({ since })}`,
    ),
  getHarborTrialDebrief: (jobName: string, trialName: string) =>
    request<PlaygroundResult>(
      `/api/harbor/jobs/${encodeURIComponent(jobName)}/trials/${encodeURIComponent(trialName)}/debrief`,
    ),
  downloadHarborTrialReportPdf: (jobName: string, trialName: string) =>
    downloadFile(
      `/api/harbor/jobs/${encodeURIComponent(jobName)}/trials/${encodeURIComponent(trialName)}/report.pdf`,
      `${jobName}-${trialName}-trial-report.pdf`,
    ),
  getHarborTrialTrace: (jobName: string, trialName: string) =>
    request<{ trace: WebTrace }>(
      `/api/harbor/jobs/${encodeURIComponent(jobName)}/trials/${encodeURIComponent(trialName)}/trace`,
    ),
  getHarborTrialEvents: (jobName: string, trialName: string, after = 0) =>
    request<HarborTrialEventsResponse>(
      `/api/harbor/jobs/${encodeURIComponent(jobName)}/trials/${encodeURIComponent(trialName)}/events${qs({ after })}`,
    ),
  getHarborTrialInstruction: (jobName: string, trialName: string) =>
    request<{
      title?: string | null;
      markdown: string;
      instructionMarkdown?: string | null;
      contextMarkdown?: string | null;
      questionnaireMarkdown?: string | null;
      outputSchemaMarkdown?: string | null;
      selfReportMarkdown?: string | null;
    }>(
      `/api/harbor/jobs/${encodeURIComponent(jobName)}/trials/${encodeURIComponent(trialName)}/instruction`,
    ),
  launchHarborJob: (body: {
    taskPath: string;
    sampleSize?: number;
    seed?: number;
    personaPool?: string;
    personaIds?: string[];
    agentName?: string | null;
    personaModel?: string | null;
    nConcurrentTrials?: number;
    mode?: "auto" | "force_docker" | "smoke";
    plane?: "harbor" | "remote";
    computeFamily?: "local" | "modal" | "gcp";
    jobName?: string | null;
    chatDomain?: string | null;
    chatApplicationId?: string | null;
    chatApplicationContext?: string | null;
    chatMaxTurns?: number | null;
    personaSources?: string[] | null;
    personaFilters?: Record<string, string> | null;
    cohortId?: string | null;
    useEntirePool?: boolean;
    osAppSubmissionProfile?: string | null;
    osAppBackend?: string | null;
  }) =>
    request<HarborJobLaunchResponse>("/api/harbor/jobs", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listPersonaDatasets: () =>
    request<PersonaDatasetListResponse>("/api/persona-pool/datasets"),
  savePersonaDataset: (body: {
    sourcePool: string;
    name: string;
    description?: string;
    overwrite?: boolean;
  }) =>
    request<{
      pool: string;
      label: string;
      name: string;
      count: number;
      sourcePool: string;
      kind: string;
    }>("/api/persona-pool/datasets", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listPersonaPoolIds: (pool = PERSONA_BENCH_POOL) =>
    request<PersonaPoolIdsResponse>(
      `/api/persona-pool/ids?${new URLSearchParams({ pool }).toString()}`,
    ),
  getPersonaPoolCatalog: (pool = PERSONA_BENCH_POOL) =>
    request<PersonaPoolCatalog>(
      `/api/persona-pool/catalog?${new URLSearchParams({ pool }).toString()}`,
    ),
  getPersonaDimensionLabels: (locale: string) =>
    request<PersonaDimensionLabels>(
      `/api/persona-pool/dimension-labels?${new URLSearchParams({ locale }).toString()}`,
    ),
  matchPersonaAttributes: (
    prompt: string,
    options?: {
      searchMode?: "keyword" | "keyword_and_embed" | "keyword_and_embed_and_llm";
      locale?: string;
      personaModel?: string;
    },
  ) =>
    request<PersonaMatchAttributesResponse>("/api/persona-pool/match-attributes", {
      method: "POST",
      body: JSON.stringify({
        prompt,
        searchMode: options?.searchMode ?? "keyword",
        ...(options?.locale ? { locale: options.locale } : {}),
        ...(options?.personaModel ? { personaModel: options.personaModel } : {}),
      }),
    }),
  getPersonaPoolCards: async (input?: {
    pool?: string;
    limit?: number;
    offset?: number;
    seed?: number;
    personaIds?: string[];
    all?: boolean;
  }) => {
    const personaIds = input?.personaIds?.slice(0, PERSONA_CARD_PREVIEW_LIMIT);
    const requestedLimit = input?.limit ?? personaIds?.length ?? 10;
    // Only cap to the selection-preview limit when resolving specific ids.
    // Browse/paging uses the backend max (500) so 1M preview can stream in pages.
    const limitCap = personaIds?.length
      ? Math.min(PERSONA_CARD_PREVIEW_LIMIT, PERSONA_POOL_CARDS_LIMIT_MAX)
      : PERSONA_POOL_CARDS_LIMIT_MAX;
    const limit = Math.min(Math.max(1, requestedLimit), limitCap);
    return normalizePersonaPoolCardsResponse(
      await request<PersonaPoolCardsResponse>(
        `/api/persona-pool/personas${qs({
          pool: input?.pool?.trim() || PERSONA_BENCH_POOL,
          limit,
          offset: input?.offset,
          seed: input?.seed,
          personaIds: personaIds?.join(","),
          all: input?.all ? "true" : undefined,
        })}`,
      ),
    );
  },
  listAllPersonaPoolCards: async (pageSize = 50, poolPath = PERSONA_BENCH_POOL) => {
    const personas: PersonaPoolCardsResponse["personas"] = [];
    let pool = poolPath.trim() || PERSONA_BENCH_POOL;
    let offset = 0;
    for (;;) {
      const page = await request<PersonaPoolCardsResponse>(
        `/api/persona-pool/personas${qs({
          pool,
          all: "true",
          limit: pageSize,
          offset,
        })}`,
      );
      pool = page.pool;
      if (
        offset > 0 &&
        page.personas.length > 0 &&
        personas.some((item) => item.personaId === page.personas[0]?.personaId)
      ) {
        break;
      }
      personas.push(...page.personas);
      if (page.personas.length < pageSize) break;
      offset += pageSize;
      if (offset > 10_000) break;
    }
    return normalizePersonaPoolCardsResponse({ pool, personas });
  },
  getPersonaPoolPersona: async (personaId: string, pool = PERSONA_BENCH_POOL) => {
    try {
      const byQuery = normalizePersonaPoolDetail(
        await request<PersonaPoolPersonaDetail>(
          `/api/persona-pool/personas${qs({
            pool,
            personaIds: personaId,
            detail: "true",
          })}`,
        ),
      );
      if (byQuery.profileMarkdown?.trim() || byQuery.personaId) return byQuery;
    } catch {
      // Fall through to path-style endpoint on older backends.
    }
    return normalizePersonaPoolDetail(
      await request<PersonaPoolPersonaDetail>(
        `/api/persona-pool/personas/${encodeURIComponent(personaId)}?${new URLSearchParams({ pool }).toString()}`,
      ),
    );
  },
  getTaskDetail: (taskPath: string) =>
    request<TaskDetail>(`/api/tasks/detail${qs({ taskPath })}`),
  getTaskPersonaStrategy: (taskPath: string) =>
    request<{ personaStrategy: TaskPersonaStrategy | null }>(
      `/api/tasks/persona-strategy${qs({ taskPath })}`,
    ),
  samplePersonaPool: (body: {
    pool?: string;
    sampleSize?: number;
    seed?: number;
    sources?: string[];
    dimensionFilters?: Record<string, string | string[]>;
    fields?: string[];
    perCell?: number;
    /** Stratified allocation: perCell | proportional | equalTotal. */
    allocation?: string;
    /** Declared target shares `{ dim: { value: weight } }` for a proportional mix. */
    portions?: Record<string, Record<string, number>>;
    taskPath?: string;
    /** Extra dimensions to carry per persona beyond the card whitelist. */
    includeDimensions?: string[];
  }) =>
    request<PersonaPoolSampleResult>("/api/persona-pool/sample", {
      method: "POST",
      body: JSON.stringify({
        pool: PERSONA_BENCH_POOL,
        ...body,
      }),
    }),
  generatePersonaPool: async (
    body: {
      count?: number;
      seed?: number;
      dimensionFilters?: Record<string, string | string[]>;
      fields?: string[];
      perCell?: number;
      allocation?: string;
      sampleSize?: number;
      marginals?: Record<string, Record<string, number>>;
      overlayDimensions?: OverlayDimension[];
      taskPath?: string;
      name?: string;
    },
    options?: { onProgress?: (event: PersonaPoolGenerateProgress) => void },
  ): Promise<PersonaPoolGenerateResult> => {
    if (!options?.onProgress) {
      return request<PersonaPoolGenerateResult>("/api/persona-pool/generate", {
        method: "POST",
        body: JSON.stringify(body),
      });
    }

    const response = await fetch("/api/persona-pool/generate?stream=1", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
      body: JSON.stringify(body),
    });
    if (!response.ok || !response.body) {
      let message = response.statusText || "Generate failed";
      try {
        const data = await response.json();
        if (data && typeof data === "object" && "detail" in data) {
          message = typeof data.detail === "string" ? data.detail : message;
        }
      } catch {
        /* ignore */
      }
      throw new ApiError(response.status, message);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result: PersonaPoolGenerateResult | null = null;

    const handleLine = (line: string) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      const event = JSON.parse(trimmed) as
        | PersonaPoolGenerateProgress
        | (PersonaPoolGenerateResult & { type: "result" })
        | { type: "error"; detail?: string; status?: number };
      if (event.type === "progress") {
        options.onProgress?.(event);
        return;
      }
      if (event.type === "error") {
        throw new ApiError(
          typeof event.status === "number" ? event.status : 500,
          event.detail || "Generate failed",
        );
      }
      if (event.type === "result") {
        const { type: _type, ...payload } = event;
        result = payload as PersonaPoolGenerateResult;
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) handleLine(line);
    }
    if (buffer.trim()) handleLine(buffer);
    if (!result) {
      throw new ApiError(500, "Generate stream ended without a result");
    }
    return result;
  },

  listPersonaCohorts: () =>
    request<{ cohorts: PersonaCohortSummary[] }>("/api/persona-pool/cohorts"),
  getPersonaCohort: (cohortId: string) =>
    request<PersonaCohortDetail>(`/api/persona-pool/cohorts/${encodeURIComponent(cohortId)}`),
  savePersonaCohort: (body: {
    cohortId: string;
    name?: string;
    description?: string;
    pool?: string;
    kind?: "recipe" | "frozen";
    seed?: number;
    sampleSize?: number;
    sources?: string[];
    dimensionFilters?: Record<string, string>;
    personaIds?: string[];
  }) =>
    request<PersonaCohortDetail>("/api/persona-pool/cohorts", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export function listPlaygroundPersonas(input?: {
  q?: string;
  limit?: number;
  domain?: string | null;
}): Promise<PlaygroundPersonasResponse> {
  return request<PlaygroundPersonasResponse>(
    `/api/playground/personas${qs({
      q: input?.q,
      limit: input?.limit,
      domain: input?.domain,
    })}`,
  );
}

export function getPlaygroundPersona(id: string): Promise<PlaygroundPersonasResponse["personas"][number]> {
  return request<PlaygroundPersonasResponse["personas"][number]>(
    `/api/playground/personas/${encodeURIComponent(id)}`,
  );
}

export function listSurveyInstruments(): Promise<SurveyInstrumentsResponse> {
  return request<SurveyInstrumentsResponse>("/api/survey-eval/instruments");
}

export function listSurveyHarborTasks(): Promise<SurveyHarborTasksResponse> {
  return request<SurveyHarborTasksResponse>("/api/survey-eval/harbor-tasks");
}

export function listChatbotEvalTasks(): Promise<ChatbotEvalTasksResponse> {
  return request<ChatbotEvalTasksResponse>("/api/chatbot-eval/tasks");
}

export function listWebEvalTasks(): Promise<WebEvalTasksResponse> {
  return request<WebEvalTasksResponse>("/api/web-eval/tasks");
}

export function listOsAppEvalTasks(): Promise<OsAppEvalTasksResponse> {
  return request<OsAppEvalTasksResponse>("/api/os-app-eval/tasks");
}

export function harborTrialLiveScreenshotUrl(jobName: string, trialName: string): string {
  return `/api/harbor/jobs/${encodeURIComponent(jobName)}/trials/${encodeURIComponent(trialName)}/live-screenshot`;
}
