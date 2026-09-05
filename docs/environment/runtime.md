# Playground Runtime Runbook

Playground launches evaluations through **Matraix Playground batch jobs**. The Playground and
`POST /api/harbor/jobs` always use the same artifact layout under `jobs/`.

## Execution planes

| Plane | Meaning |
|-------|---------|
| `harbor` (default) | API machine or local dev runs the job locally |
| `remote` | API dispatches `taskType=harbor_job` to a **Remote Runner** HTTP worker |

Configure the default plane:

```bash
export MATRIX_EXECUTION_PLANE=harbor   # or remote
```

Optional per-request override: `"plane": "harbor"` or `"plane": "remote"` on
`POST /api/harbor/jobs`.

### Compute family

Set where trial compute runs (independent of `plane`):

```bash
export MATRIX_COMPUTE_FAMILY=local   # or modal or gcp
```

Optional per-request override: `"computeFamily": "local"`, `"modal"`, or `"gcp"`
on `POST /api/harbor/jobs`.

| family | Survey / chatbot | Web / Linux app | macOS / iOS app |
|--------|------------------|-----------------|-----------------|
| `local` | This machine | Docker on this machine | use.computer |
| `modal` | Modal | Modal (task images cached after the first build) | use.computer |
| `gcp` | GKE | GKE | use.computer |

Each run writes `jobs/<job_name>/compute.json` with `family` and `environment`.

**When to switch.** Start on `modal`. Move web / Linux to `gcp` first when
daily concurrency stays high. Survey / chat can stay packed on Modal until
concurrency or cost says otherwise, then set the same `computeFamily=gcp`.

Switch globally:

```bash
export MATRIX_COMPUTE_FAMILY=gcp     # was modal
```

Or per job: `"computeFamily": "gcp"`. `plane` stays `harbor`.
Artifacts still land in `jobs/<job_name>/`.

Survey/chat on Modal or GKE pack many I/O-bound host processes into one small
worker (`cpu=1`, `memory=4096` on Modal; 1 CPU / 4Gi request on GKE).
Playground Parallel / `nConcurrentTrials` is the Harbor cap as set — Modal
and GKE do not rewrite it.

Modal needs credentials on the API host (`MODAL_TOKEN_ID` /
`MODAL_TOKEN_SECRET` or `~/.modal.toml`) and one deployed app. From the
repository root:

```bash
uv pip install -e ".[modal]"
modal setup
modal secret create matraix-llm ANTHROPIC_API_KEY=... OPENAI_API_KEY=...
export MATRIX_REPO_ROOT="$PWD"
uv run --extra modal modal deploy application/playground/backend/service/modal_host_app.py
export MATRIX_COMPUTE_FAMILY=modal
export MATRIX_EXECUTION_PLANE=harbor
```

That one deploy covers survey, chat, web, and Linux. The first web/Linux job
builds the shared task image; later jobs reuse it.

Chat tasks need a sidecar URL reachable from Modal (`CHATBOT_API_URL` or the
task’s upstream env). Production uses a public (or VPC) endpoint.

Local sidecars on `127.0.0.1` are invisible from Modal/GKE. On launch,
Playground tries to open a **temporary public door** to that sidecar if
`cloudflared` (or `ngrok`) is on PATH — same idea as exposing a local website.
The door URL is stored in `MATRIX_CHATBOT_PUBLIC_URL` for this API process
only. Install with `brew install cloudflared`. Disable with
`MATRIX_CHATBOT_TUNNEL=0`. You can still set `MATRIX_CHATBOT_PUBLIC_URL`
yourself, or use `computeFamily=local` so everything stays on the laptop.

Artifacts land in the same `jobs/<job_name>/` tree as a local run
(`compute.json`, per-trial `agent/` / `verifier/` / `result.json`, `job.log`).

Survey/chat **Modal Jobs** keep two channels. Status (pending / running / done)
goes to a Modal Dict plus `live_status.json` about every
`MATRIX_MODAL_LIVE_PUSH_SEC` seconds (default `5`) — no volume commit. Full
trial trees flush every `MATRIX_MODAL_ARTIFACT_FLUSH_TRIALS` completions
(default `25`) or `MATRIX_MODAL_ARTIFACT_FLUSH_SEC` (default `30`), then
`volume.commit()`. The API overlays that status onto local `jobs/<job_name>/`
so the mosaic ticks without re-downloading logs.

GKE host workers (`dispatch=gke_workers`) do the same overlay from
`/tmp/matraix-live.json` about every `MATRIX_GKE_LIVE_PUSH_SEC` seconds
(default `5`) while the pod is running.

Closing the laptop does **not** stop shards already spawned on Modal (or GKE
Jobs already created). Launch writes `jobs/<job>/_generated/cloud_run.json`
with FunctionCall / Job ids **after each spawn**, then waits. Restart the
Playground API on the same checkout/`jobs/` to reattach and pull artifacts.
Shards that were never spawned (killed during the brief spawn loop) will not
run until you retry. The live mosaic is gone while the API is down; it
catches up on resume. Survey, chat, web, and Linux all use this path when
`computeFamily` is `modal` or `gcp`.

macOS / iOS computer-use always stays on use.computer, even when
`MATRIX_COMPUTE_FAMILY` is `modal` or `gcp`. Set the family with
`MATRIX_COMPUTE_FAMILY`, `"computeFamily"` on the API, or
`--compute-family` on the generator or `matraix run --compute-family`.

### GCP / GKE (high-concurrency / always-on)

`computeFamily=gcp` runs survey, chat, web, and Linux on GKE. macOS / iOS
still use use.computer.

Install the extra on the API host, then point at the cluster:

```bash
uv pip install -e ".[gke]"
export MATRIX_GKE_CLUSTER=your-cluster
export MATRIX_GKE_REGION=us-central1
export MATRIX_GKE_REGISTRY=matraix          # Artifact Registry repository
export MATRIX_GKE_NAMESPACE=default         # optional
export GCP_PROJECT=your-project             # or MATRIX_GCP_PROJECT
gcloud container clusters get-credentials "$MATRIX_GKE_CLUSTER" --region "$MATRIX_GKE_REGION"
```

Harbor `type: gke` also accepts those cluster fields as `environment.kwargs`.

Survey/chat workers need an image that contains this checkout plus Harbor:

```bash
export MATRIX_GKE_HOST_IMAGE=REGION-docker.pkg.dev/PROJECT/REPO/matraix-host:latest
application/playground/backend/service/build_gke_host_image.sh "$MATRIX_GKE_HOST_IMAGE"
docker push "$MATRIX_GKE_HOST_IMAGE"
export MATRIX_COMPUTE_FAMILY=gcp
export MATRIX_EXECUTION_PLANE=harbor
```

The cluster must be able to pull that image. Optional `MATRIX_GKE_JOBS_PVC`
mounts a PVC at `/matraix/jobs` inside the worker; otherwise the Job uses
`emptyDir` and the API copies `jobs/<job_name>/` back when Harbor finishes.

Chat tasks need a sidecar URL reachable from the GKE pod (not localhost on the
API host). Same automatic tunnel as Modal: `cloudflared` on PATH, or
`MATRIX_CHATBOT_PUBLIC_URL`, or `computeFamily=local`.

Then flip the family (restart the Playground API so it picks up the env):

```bash
# burst / not yet saturated
export MATRIX_COMPUTE_FAMILY=modal

# daily saturation — especially Type 3/4 browsers
export MATRIX_COMPUTE_FAMILY=gcp
```

Per-request override still wins: a survey can stay `"computeFamily": "modal"`
while a web job uses `"gcp"`.

`MATRIX_SHARD_CONCURRENCY` (default 8) is the max Modal/GKE workers for one
job. `MATRIX_HOST_PACK_CONCURRENCY` (default 32) is the max survey/chat
processes packed onto one of those workers. Playground Parallel is the
global in-flight cap; the planner fills pack first, then adds workers.
Results still write to one `jobs/<job_name>/`. See
[large-scale-runs.md](large-scale-runs.md).

## Option A: Local Matraix Playground (default)

**Terminal A — API**

```bash
bash application/playground/backend/run_dev.sh
```

**Terminal B — frontend**

```bash
cd application/playground/frontend && npm run dev
```

Open http://localhost:5173 and launch with **Mode → auto**.

## Option B: Remote Runner worker

Use this when the API should not execute `harbor run` locally.

**Terminal A — Remote Runner**

```bash
PYTHONPATH=.:environment/runtime:packages/playground/src:application/playground:src \
  uvicorn playground.remote_runner.server:app \
  --host 127.0.0.1 --port 9100
```

**Terminal B — Playground API**

```bash
export REMOTE_RUNNER_API_URL=http://127.0.0.1:9100
export MATRIX_EXECUTION_PLANE=remote
bash application/playground/backend/run_dev.sh
```

The worker must have access to the same repository checkout (tasks, personas,
`jobs/` output directory). Production deployments typically mount a shared
`jobs/` path or sync artifacts after each run.

### Remote Runner API

- `GET /health`
- `POST /v1/runs` with `{"taskType": "harbor_job", "payload": {...}}`
- `GET /v1/runs/{id}`
- `GET /v1/runs/{id}/artifacts/{name}`

Primary payload fields for `harbor_job`:

- `jobName`
- `configYaml` — generated Matraix Playground job recipe
- `repoRoot`
- `jobsDir`
- `env` — optional `PYTHONPATH` plus `MATRIX_*` task exports only (no API keys)

API keys and other secrets must be configured on the **worker** process, not
sent from the Playground API host.

Optional dev-only `taskType=web` returns a deterministic mock when
`REMOTE_RUNNER_WEB_COMMAND` is not set.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `MATRIX_EXECUTION_PLANE` | Default `harbor` or `remote` |
| `MATRIX_COMPUTE_FAMILY` | Default `local`, `modal`, or `gcp` |
| `MATRIX_SHARD_CONCURRENCY` | Max workers for one job (default `8`) |
| `MATRIX_HOST_PACK_CONCURRENCY` | Max survey/chat processes per Modal / GKE host worker (default `32`; does not override Playground Parallel) |
| `MATRIX_WEB_PACK_CONCURRENCY` | Max browsers per Modal / GKE web worker (default `1`) |
| `MATRIX_MAX_CONCURRENT_TRIALS` | Optional cap on Playground Parallel |
| `MATRIX_MODAL_LIVE_PUSH_SEC` | Modal survey/chat status tick (Dict / `live_status.json`, default `5`) |
| `MATRIX_MODAL_LIVE_PULL_SEC` | How often the API reads that status into local `jobs/<job>/` (default `5`) |
| `MATRIX_MODAL_ARTIFACT_FLUSH_TRIALS` | Copy full trial trees to the jobs volume after this many new dones (default `25`) |
| `MATRIX_MODAL_ARTIFACT_FLUSH_SEC` | Or after this many seconds with new dones (default `30`) |
| `MATRIX_GKE_CLUSTER` | GKE cluster name (`computeFamily=gcp`) |
| `MATRIX_GKE_REGION` | GKE region |
| `MATRIX_GKE_NAMESPACE` | Kubernetes namespace (default `default`) |
| `MATRIX_GKE_REGISTRY` | Artifact Registry repository name (Harbor `type: gke`) |
| `MATRIX_GKE_REGISTRY_LOCATION` | Artifact Registry location (defaults to `MATRIX_GKE_REGION`) |
| `MATRIX_GKE_HOST_IMAGE` | Image for survey/chat GKE host workers |
| `MATRIX_GKE_JOBS_PVC` | Optional PVC name mounted at `/matraix/jobs` |
| `MATRIX_GKE_LIVE_PUSH_SEC` | GKE survey/chat status tick (`/tmp/matraix-live.json`, default `5`) |
| `MATRIX_CHATBOT_PUBLIC_URL` | Public/tunnel chatbot URL for Modal/GKE workers (replaces localhost) |
| `MATRIX_CHATBOT_TUNNEL` | `auto` (default): start cloudflared/ngrok for local sidecars. `0` disables |
| `GCP_PROJECT` / `MATRIX_GCP_PROJECT` | GCP project id |
| `REMOTE_RUNNER_API_URL` | Remote runner base URL (required for `remote`) |
| `REMOTE_RUNNER_API_KEY` | Optional bearer token |
| `REMOTE_RUNNER_INLINE` | Run jobs inline in the API process (tests) |
| `REMOTE_RUNNER_HARBOR_COMMAND` | Override `harbor` CLI command on the worker |

## Task types

Matraix Playground resolves execution per task `metadata.type`:

- `survey` / `chatbot` → host-native agents in `auto` mode (Modal Jobs or GKE host workers when `computeFamily` is `modal` / `gcp`)
- `web` / `os-app` → docker, Harbor `modal` / `gke`, or `use-computer` backends

See [large-scale-runs.md](large-scale-runs.md) and
[quickstart.md](../quickstart.md) for terminal `matraix run` examples.
