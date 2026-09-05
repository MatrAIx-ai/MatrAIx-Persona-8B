# Playground REST API

This document describes the Playground HTTP API exposed by
`backend.api.app:app`. All application endpoints are mounted under `/api`.

Interactive OpenAPI documentation is also available at `/docs` when the backend
is running.

## Conventions

- JSON uses camelCase field names.
- The API does not require authentication in local development.
- Long-running work is launched through `POST /api/harbor/jobs`. Clients poll
  `GET /api/harbor/jobs/{job_name}` until `launch.status` is `completed` or
  `failed`.
- Common Matraix Playground launch statuses are `queued`, `running`, `completed`, and
  `failed`.
- FastAPI may return `422` for malformed requests or failed validation.
- Application handlers return `404` for unknown jobs, trials, personas, cohorts,
  screenshots, recordings, or tasks where applicable.

## Runtime boundary

Playground launches evaluations through Matraix Playground batch jobs. The Playground and
`POST /api/harbor/jobs` share the same artifact layout under `jobs/`.

Execution can stay on the API host or dispatch to a Remote Runner worker:

```bash
MATRIX_EXECUTION_PLANE=harbor    # default — run the job locally
MATRIX_EXECUTION_PLANE=remote    # HTTP dispatch to Remote Runner
REMOTE_RUNNER_API_URL=http://127.0.0.1:9100
REMOTE_RUNNER_API_KEY=...        # optional bearer token for the worker API
```

Survey, chatbot, web, and os-app jobs share the same API regardless of plane.
See [unified-runtime.md](../environment/runtime.md) for worker setup and remote payload
fields.

Optional per-request override: `"plane": "harbor"` or `"plane": "remote"` on
`POST /api/harbor/jobs`.

## Endpoint index

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Backend liveness. |
| `GET` | `/api/preflight` | Environment and resource readiness checks. |
| `GET` | `/api/chatbot-sidecars` | List chat sidecar statuses. |
| `POST` | `/api/chatbot-sidecars/{application_id}/start` | Start one chat sidecar. |
| `GET` | `/api/config/options` | Editable config knobs, defaults, and runtime facts. |
| `GET` | `/api/playground/personas` | List persona profiles (searchable). |
| `GET` | `/api/playground/personas/{persona_id}` | Read one full persona profile. |
| `GET` | `/api/harbor/jobs` | List Matraix Playground batch jobs. |
| `POST` | `/api/harbor/jobs` | Launch a Matraix Playground batch job. |
| `GET` | `/api/harbor/jobs/{job_name}` | Read one job detail view. |
| `DELETE` | `/api/harbor/jobs/{job_name}` | Delete one job and its artifacts. |
| `GET` | `/api/harbor/jobs/{job_name}/aggregation` | Read refreshed job aggregation JSON. |
| `GET` | `/api/harbor/jobs/{job_name}/live` | Live job/trial progress for the Playground. |
| `GET` | `/api/harbor/jobs/{job_name}/trials/{trial_name}/events` | Incremental trial event stream. |
| `GET` | `/api/harbor/jobs/{job_name}/trials/{trial_name}/debrief` | Post-run debrief for one trial. |
| `GET` | `/api/harbor/jobs/{job_name}/trials/{trial_name}/instruction` | Persona-facing instruction for one trial. |
| `GET` | `/api/harbor/jobs/{job_name}/trials/{trial_name}/trace` | Web trace payload for one trial. |
| `GET` | `/api/harbor/jobs/{job_name}/trials/{trial_name}/screenshots/{filename}` | Fetch one web trace screenshot. |
| `GET` | `/api/harbor/jobs/{job_name}/trials/{trial_name}/recording` | Fetch one os-app screen recording. |
| `GET` | `/api/persona-pool/datasets` | List Dataset picker pools (`kind`: dataset / saved / production). |
| `POST` | `/api/persona-pool/datasets` | Save as dataset (promote pulled YAML cohort). |
| `GET` | `/api/persona-pool/catalog` | Persona pool dimension catalog. |
| `POST` | `/api/persona-pool/sample` | Sample / Pull personas from a pool. |
| `POST` | `/api/persona-pool/generate` | Write a synthetic `generated-persona-dev-*` pool. |
| `GET` | `/api/persona-pool/personas` | List persona cards from a pool. |
| `GET` | `/api/persona-pool/personas/{persona_id}` | Read one persona card/detail from a pool. |
| `GET` | `/api/persona-pool/cohorts` | List saved cohort recipes (`saved-cohorts/`). |
| `POST` | `/api/persona-pool/cohorts` | Save a cohort recipe / frozen ids. |
| `GET` | `/api/persona-pool/cohorts/{cohort_id}` | Read one saved cohort recipe. |
| `GET` | `/api/tasks/detail` | Task detail for Playground setup (`taskPath` query). |
| `GET` | `/api/survey-eval/instruments` | List task-backed survey questionnaires. |
| `GET` | `/api/survey-eval/harbor-tasks` | List survey Harbor tasks for the Playground. |
| `GET` | `/api/chatbot-eval/tasks` | List chatbot Harbor tasks for the Playground. |
| `GET` | `/api/web-eval/tasks` | List web Harbor tasks for the Playground. |
| `GET` | `/api/os-app-eval/tasks` | List os-app Harbor tasks for the Playground. |

## Health

### `GET /api/health`

Returns a process liveness response.

```json
{
  "status": "ok"
}
```

### `GET /api/preflight`

Returns user-facing readiness checks for credentials, optional sidecars, and
eval surfaces aligned to shipped `application/tasks`.

```json
{
  "ready": true,
  "checks": [
    {
      "group": "Core",
      "name": "Model credentials",
      "ok": true,
      "detail": "Configured: OpenAI, Anthropic.",
      "optional": false
    }
  ]
}
```

`ready` ignores checks marked `optional`.

**Required (blocks `ready`):** Model credentials (any of OpenAI / Anthropic /
DashScope / OpenRouter), plus always-available Survey / Web surface markers.

**Optional (task-specific):** per-provider keys, Docker (survey / web / chat /
Linux OS-app), use.computer (macOS / iOS), and chat sidecars (OpenBB, meal
planning, Acme API, Acme MCP). RecAI and medical are not probed.

### `GET /api/chatbot-sidecars`

Returns sidecar container status for supported chat applications.

### `POST /api/chatbot-sidecars/{application_id}/start`

Starts the sidecar for one supported `application_id` when it is not already
running. Returns `404` for unknown application ids.

## Config

### `GET /api/config/options`

Returns the available config knobs, canonical defaults, and fixed runtime
environment metadata used by the Playground.

## Personas

### `GET /api/playground/personas`

Query parameters:

- `q` — optional substring search
- `limit` — optional result cap
- `domain` — accepted for backwards compatibility; no domain-specific blurb is
  returned

### `GET /api/playground/personas/{persona_id}`

Returns the full persona record (`id`, `name`, `source`, `context`).

## Matraix Playground batch jobs

Matraix Playground jobs are the canonical launch path. Artifacts are written under
`jobs/{job_name}/`.

### `GET /api/harbor/jobs`

Returns a list of job summaries (`jobName`, trial counts, status, timestamps).

### `POST /api/harbor/jobs`

Launch a multi-trial Matraix Playground job from one application task.

Request body:

```json
{
  "taskPath": "application/tasks/example-survey_product-feedback",
  "sampleSize": 3,
  "seed": 42,
  "personaPool": "persona/datasets/matraix-persona-dev-sample",
  "personaIds": ["0042"],
  "mode": "auto",
  "plane": "harbor",
  "personaModel": "anthropic/claude-haiku-4-5",
  "nConcurrentTrials": 2
}
```

`computeFamily` is optional (`local`, `modal`, or `gcp`; default
`MATRIX_COMPUTE_FAMILY` or `local`). The CLI equivalent is
`generate_application_job.py --compute-family …` then `matraix run -c`. Each job writes
`jobs/<job_name>/compute.json`. macOS/iOS CUA stays `use-computer`
(`cuaPinned`) even when the family is `modal`/`gcp`. See
[large-scale-runs.md](../environment/large-scale-runs.md) and
[runtime.md](../environment/runtime.md).

Common optional fields:

| Field | Purpose |
|---|---|
| `agentName` | Override resolved Matraix Playground agent |
| `jobName` | Explicit job basename; if omitted, defaults to `pg-{task_slug}-{8 hex chars}` |
| `cohortId` | Launch from a saved persona cohort |
| `useEntirePool` | Launch every persona in `personaPool` without listing IDs |
| `personaSources` / `personaFilters` | Pool sampling filters |
| `chatDomain`, `chatApplicationId`, `chatApplicationContext`, `chatMaxTurns` | Chatbot / user-sim tasks |
| `osAppSubmissionProfile`, `osAppBackend` | os-app / CUA tasks |

`mode` must be one of `auto`, `force_docker`, or `smoke`.
`plane` must be `harbor` or `remote`.
`computeFamily` must be `local`, `modal`, or `gcp`.
Large cohorts should set `useEntirePool` and point `personaPool` at the
cohort directory. See [large-scale-runs.md](../environment/large-scale-runs.md).

Response:

```json
{
  "jobName": "pg-example-survey-product-feedback-abc123",
  "configPath": "configs/jobs/application-task-job-recipe/pg-example-survey-product-feedback-abc123.yaml",
  "jobsDir": "jobs",
  "agentName": "persona-json-survey",
  "taskType": "survey",
  "trialProfile": "json_survey",
  "mode": "auto",
  "plane": "harbor"
}
```

Poll `GET /api/harbor/jobs/{job_name}` until `launch.status` is terminal.

### `GET /api/harbor/jobs/{job_name}`

Returns the job detail view: launch metadata, generated config path, trial list,
and per-trial result summaries when available.

### `DELETE /api/harbor/jobs/{job_name}`

Deletes the job directory and generated config when present.

### `GET /api/harbor/jobs/{job_name}/aggregation`

Returns `jobs/{job_name}/aggregation.json`, refreshing it when needed.

### `GET /api/harbor/jobs/{job_name}/live`

Returns live progress for the Playground: launch status, trial phases, and basic
persona labels. Survey/chat Modal Functions overlay **status** on a few-second tick
(full trial dirs arrive in artifact flushes). Web/linux Modal Sandboxes publish
the same overlay while the sandbox is up. If the API host sleeps, already
spawned Modal/GKE work keeps running; reopen the API on the same `jobs/` to
reattach. GKE host workers otherwise update when a pod finishes.

### Trial inspection routes

| Route | Purpose |
|---|---|
| `GET .../trials/{trial_name}/events?after=0` | Incremental event stream |
| `GET .../trials/{trial_name}/debrief` | Structured post-run debrief |
| `GET .../trials/{trial_name}/instruction` | Persona-facing instruction text |
| `GET .../trials/{trial_name}/trace` | Web trajectory / trace JSON |
| `GET .../trials/{trial_name}/screenshots/{filename}` | Binary screenshot |
| `GET .../trials/{trial_name}/recording` | Binary screen recording (mp4) |

## Persona pool

Used by the Playground setup rails for sampling and cohort management.
User-facing path taxonomy:
[Playground pools & cohorts](../persona/README.md#playground-pools--cohorts).

### `GET /api/persona-pool/datasets`

Lists selectable Dataset pools. Entries include `kind`:

| `kind` | Meaning |
|--------|---------|
| `dataset` | Local YAML pool (fixture, generated, etc.) |
| `saved` | Promoted via **Save as dataset…** (`saved-persona-dataset` manifest) |
| `production` | `matraix-persona-1m` root |

Launch caches (`*/cohorts/`) and `saved-cohorts/` are omitted.

### `POST /api/persona-pool/datasets`

**Save as dataset…** — copy a pulled cohort’s YAML into
`persona/datasets/<slug>/` so it appears in the Dataset picker.

### `GET /api/persona-pool/catalog?pool=...`

Returns dimension metadata for one persona pool.

### `POST /api/persona-pool/sample`

Samples personas from a pool with optional filters and stratification.
Optional `previewLimit` (default 32) and `includePersonaIds`. Cohorts larger
than 100 IDs return a truncated `personaIds` list plus `selectedCount` /
`idsTruncated`, and may materialize a launch cache under
`<source>/cohorts/cohort-<digest>/`.

### `POST /api/persona-pool/generate`

Writes Full-DAG synthetic pool(s) under `persona/datasets/generated-persona-dev-*`
(gitignored). Supports Independent / Contrast the same way as Playground
Generation. Optional `?stream=1` returns NDJSON progress (one logical track per
dataset: `datasetIndex` / `datasetLabel` / `ratio`). Details:
[Playground Generation](../persona/README.md#playground-generation-independent--contrast).

### `GET /api/persona-pool/personas`

Lists persona cards. Supports `limit`, `offset`, `seed`, `personaIds`, `detail`,
and `all`.

### `GET /api/persona-pool/personas/{persona_id}?pool=...`

Returns one persona card or detail record from the requested pool.

### `GET /api/persona-pool/cohorts`

Lists **saved cohort recipes** under `persona/datasets/saved-cohorts/`
(`cohort.json` — not Dataset YAML pools).

### `POST /api/persona-pool/cohorts`

Saves a recipe or frozen id list to `persona/datasets/saved-cohorts/<id>/`.

### `GET /api/persona-pool/cohorts/{cohort_id}`

Returns one saved cohort definition.

## Task catalogs

Read-only catalogs for Playground task pickers. Each route returns a `tasks` array
with task metadata plus optional profile markdown when available.

| Route | Surface |
|---|---|
| `GET /api/tasks/detail?taskPath=...` | One task detail record (includes `personaStrategy` from `persona_strategy.json`) |
| `GET /api/survey-eval/instruments` | Survey questionnaires |
| `GET /api/survey-eval/harbor-tasks` | Survey Matraix Playground tasks |
| `GET /api/chatbot-eval/tasks` | Chatbot Matraix Playground tasks |
| `GET /api/web-eval/tasks` | Web Matraix Playground tasks |
| `GET /api/os-app-eval/tasks` | os-app Matraix Playground tasks |

## Related docs

- [unified-runtime.md](../environment/runtime.md) — Matraix Playground vs remote execution planes
- [quickstart.md](../quickstart.md) — terminal smoke and Playground setup
- OpenAPI `/docs` — generated from FastAPI models in `backend/api/schemas.py`
