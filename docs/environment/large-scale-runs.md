# Large-scale runs

Run a Playground evaluation over many personas. The result is still **one job**:
one name in Runs, one folder `jobs/<job_name>/`.

First single-persona walkthrough: [quickstart](../quickstart.md).

---

## Launch

Pick one surface. They all write the same `jobs/<job_name>/` tree.

| Surface | Use when |
|---------|----------|
| **Playground** | Interactive launch and inspection |
| **`POST /api/harbor/jobs`** | Automation |
| **`matraix run -c <job.yaml>`** | CLI that matches Playground (local, Modal, or GCP) |

A thousand-persona Modal (or GCP) batch:

```bash
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-survey_product-feedback \
  --sample-size 1000 \
  --n-concurrent-trials 32 \
  --compute-family modal

uv run matraix run -c configs/jobs/application-task-job-recipe/<generated>.yaml
```

`--compute-family modal|gcp` on the generator records the family in the sidecar.
`matraix run -c` then dispatches through HarborJobService (Modal Function /
Sandbox or GKE workers + shards), same as Playground. Override with
`matraix run -c <job.yaml> --compute-family local` to force this machine.

One launch covers the whole cohort. Do not start a separate job per persona.

### Compute family

`plane` is who starts the job. `computeFamily` is where trials run.

```bash
export MATRIX_COMPUTE_FAMILY=modal   # or gcp when daily concurrency saturates
```

Or pass `"computeFamily"` on `POST /api/harbor/jobs`.

| | Survey / chat | Web / Linux app | macOS / iOS app |
|--|---------------|-----------------|-----------------|
| `local` | This machine | Docker on this machine | use.computer |
| `modal` | Modal | Modal | use.computer |
| `gcp` | GKE | GKE | use.computer |

macOS / iOS always use use.computer, even when `computeFamily` is `modal` or
`gcp`. Set `MATRIX_COMPUTE_FAMILY` or pass `computeFamily` on launch.

**Modal** (`survey`, `chat`, `web`, Linux os-app): credentials on the API host
and one deploy. Survey/chat run as a Function; web/Linux as a Sandbox with
Docker. The first web/Linux job builds the task image; later jobs reuse it.
Chat needs a sidecar URL that Modal can reach. Setup:
[runtime.md](runtime.md).

Start on `modal`. Switch web/Linux to `gcp` first when daily concurrency stays
high. Flip with `MATRIX_COMPUTE_FAMILY=gcp` or `"computeFamily": "gcp"`.

`nConcurrentTrials` (Playground **Parallel**) is how many trials run at once.
Large Modal and GCP jobs split across workers automatically. Every trial still
lands in `jobs/<job_name>/`. Survey/chat pack up to
`MATRIX_HOST_PACK_CONCURRENCY` (default `32`) processes per worker; web/linux
pack `MATRIX_WEB_PACK_CONCURRENCY` (default `1`) browser per worker.
`MATRIX_SHARD_CONCURRENCY` (default `8`) is the max workers.
`MATRIX_MAX_CONCURRENT_TRIALS` optionally caps Parallel.
Survey/chat on Modal Functions and GKE host workers publish **status** every few
seconds so the mosaic ticks; artifacts flush in batches (Modal) or when the
pod packs the tree (GKE). Web/linux Modal Sandboxes publish the same overlay
while the sandbox is up. All shards are spawned up front so closing the
laptop does not cancel already-queued Modal / GKE work; restart the API to
reattach.

Chat on Modal/GKE needs a sidecar URL the worker can reach. Set a public
endpoint, or `MATRIX_CHATBOT_PUBLIC_URL`, or `MATRIX_CHATBOT_TUNNEL=auto` so
Playground can start cloudflared/ngrok, or use `computeFamily=local`.

Optional knobs: `MATRIX_HOST_PACK_CONCURRENCY`, `MATRIX_WEB_PACK_CONCURRENCY`,
`MATRIX_SHARD_CONCURRENCY`, `MATRIX_MAX_CONCURRENT_TRIALS`,
`MATRIX_MODAL_LIVE_PUSH_SEC`, `MATRIX_MODAL_LIVE_PULL_SEC`,
`MATRIX_MODAL_ARTIFACT_FLUSH_TRIALS`, `MATRIX_MODAL_ARTIFACT_FLUSH_SEC`
([runtime.md](runtime.md)).

---

## Personas

A **cohort** for launch is a directory of persona YAML files (or a pool path
plus `useEntirePool`).

| Batch size | How to pass them |
|------------|------------------|
| Small (about ≤100) | Optional `personaIds` |
| Large | `personaPool` = that directory, plus `useEntirePool` |

Sources:

1. **Task strategy** — most tasks ship `persona_strategy.json`. Sample in
   Playground, or run
   `generate_application_job.py --task application/tasks/<name>`.
   For a stratified sample, set ``sampling.allocation`` to ``perCell`` /
   ``proportional`` / ``equalTotal``. Per-cell uses ``sampling.perCell``;
   the other two use ``sampling.sampleSize`` as the total.
2. **Public Persona 1M** —
   [`MatrAIx2026/MatrAIx_Persona_1M_Public_Release`](https://huggingface.co/datasets/MatrAIx2026/MatrAIx_Persona_1M_Public_Release).
   Import it locally, then **Pull cohort** in Playground (writes a launch cache
   under `matraix-persona-1m/cohorts/`). See
   [Persona setup](../persona/README.md#setup-and-usage).
3. **Dev sample** — `persona/datasets/matraix-persona-dev-sample/` for small
   local batches.
4. **Saved dataset** — after a pull, **Save as dataset…** copies the YAML into
   `persona/datasets/<name>/` for reuse. Playground defaults sampling to **All**.

Path taxonomy (picker vs on-disk caches):  
[Playground pools & cohorts](../persona/README.md#playground-pools--cohorts).

Playground / API fields: `personaPool`, `useEntirePool`, `sampleSize`,
`nConcurrentTrials`. Reference: [playground-api.md](../application/playground-api.md).

Record the persona path (and the Hugging Face revision, if you used one) so the
batch is reproducible.

---

## Outputs

```text
jobs/<job_name>/
├── result.json
├── <task>__<trial>/
│   ├── agent/
│   ├── verifier/
│   └── result.json
└── job.log
```

Keep `jobs/<job_name>/` and any sampled cohort directory if you need to
reproduce the run. Pulled launch caches sit next to the source dataset, for
example:

- `persona/datasets/matraix-persona-1m/cohorts/cohort-<digest>/`
- `persona/datasets/matraix-persona-dev-sample/cohorts/cohort-<digest>/`

Those caches (and `generated-persona-dev-*`, `saved-cohorts/`) are gitignored.

---

## Related

- [Runtime](runtime.md)
- [Quickstart](../quickstart.md)
- [Persona 1M](../persona/README.md#public-coreset-matraix-persona-1m)
- [Playground API](../application/playground-api.md)
