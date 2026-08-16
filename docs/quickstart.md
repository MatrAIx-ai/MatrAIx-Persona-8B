# Quickstart

A step-by-step path from zero to your first multi-persona survey run, then into
the **Playground** for interactive task play. No prior Matraix Playground experience
required. More docs: the [MatrAIx Handbook](README.md).

**What you are doing:** loading a synthetic user profile (persona), putting that
user in a product scenario (survey, chat, web, …), and inspecting what they
“said” — all inside a reproducible sandbox.

**Time:** ~30–60 minutes the first time (mostly Docker image build on web/CUA tasks).

---

## What you need

| Requirement | Why |
|-------------|-----|
| **[Docker](https://docs.docker.com/get-docker/)** | Web, CUA, and some smoke recipes use containers |
| **uv** | Python + `harbor` CLI — [install in step 2](#2-install-uv-clone-and-sync) |
| **Node.js 20+** | Playground frontend (optional but recommended) |
| **Anthropic API key** | Persona agents (step 6+). [Create one](https://console.anthropic.com/) if needed |
| **OpenAI API key** | Some chat tasks and alternate LLM backends |

Smoke pool: `persona/datasets/matraix-persona-dev-sample/` (200 profiles;
persona **`0042`**). **Recommended** for real cohorts: import **Persona 1M** —
[Handbook § Persona 1M](README.md#3-persona-1m-recommended) ·
[Persona setup](persona/README.md#setup-and-usage).

---

## 0. Windows users: set up WSL2 first

Everything below assumes a Linux/macOS shell. On Windows, use
[WSL2](https://learn.microsoft.com/windows/wsl/install) — it takes ~5 minutes
and then every command in this guide works exactly as written:

1. Open **PowerShell as Administrator** and run `wsl --install` (installs
   Ubuntu). Reboot if prompted, then create your Linux username/password.
2. Install [Docker Desktop](https://docs.docker.com/get-docker/) and enable
   **Settings → Resources → WSL integration** for your Ubuntu distro.
3. Do all remaining steps **inside the Ubuntu terminal** (search “Ubuntu” in
   the Start menu). Clone the repo into the WSL filesystem — e.g. `~/MatrAIx`,
   **not** `/mnt/c/…` — Windows-mounted paths are dramatically slower and can
   cause file-watching issues with the Playground dev server.

Native PowerShell/cmd is not supported: task verifiers and dev scripts
require `bash`.

---

## 1. Install Docker and confirm it works

1. Install [Docker Desktop](https://docs.docker.com/get-docker/) (or Docker Engine on Linux).
2. **Start Docker** and wait until it reports “running”.
3. In a terminal:

   ```bash
   docker run --rm hello-world
   ```

   You should see a “Hello from Docker!” message. If this fails, fix Docker before continuing.

---

## 2. Install uv, clone, and sync

**Install [uv](https://docs.astral.sh/uv/)**:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Open a **new terminal** (or run `source $HOME/.local/bin/env` if the installer says so). Check:

```bash
uv --version
```

On macOS you can also use Homebrew: `brew install uv`.

**Clone the repo and install dependencies:**

```bash
git clone https://github.com/matraix-ai/matraix.git   # or your fork
cd matraix
uv sync
```

Check the CLI:

```bash
uv run matraix --help
```

---

## 3. Smoke test (no API key)

Confirms Docker and Matraix Playground with the upstream **hello-world** task (reference
solution, no LLM call):

```bash
uv run matraix run -c configs/jobs/example-job-recipe/harbor-smoke-local.yaml
```

First run builds the Docker image (several minutes).

**Success:** the command finishes without error and writes output under
`jobs/harbor-smoke-local/`.

---

## 4. Set your API key

**Auto** survey / chat / most web agents read provider keys from your **shell**
(not committed to git). For Anthropic persona models:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # replace with your key
```

Also set `OPENAI_API_KEY` when the chat **sidecar** needs it, and
`LLM_API_KEY="$ANTHROPIC_API_KEY"` for Playwright (`persona-openhands-sdk`).
macOS/iOS computer-use also needs `USE_COMPUTER_API_KEY`.

To keep keys across terminal sessions, add the same lines to `~/.zshrc` or
`~/.bashrc`, then open a new terminal.

Full agent ↔ key matrix: [choosing-an-agent.md](environment/agents.md).

---

## 5. Look at a persona (optional but recommended)

A **persona** is a YAML profile — demographics, preferences, communication style,
etc. The agent reads it and tries to answer *as that person*.

```bash
head -40 persona/datasets/matraix-persona-dev-sample/persona_0042.yaml
```

You will pass this file path on the command line as `persona_path=...`. Swap
`persona_0042` for any `persona_XXXX.yaml` in the dataset to simulate a different
person.

---

## Matraix Playground vocabulary (Application runs)

| Term | In this guide |
|------|----------------|
| **Task** | The scenario — e.g. [example-survey_product-feedback](../application/tasks/example-survey_product-feedback/) (product brief + survey questions + verifier). Same task for every persona. |
| **Trial** | One full run: **one persona** + **one task** → agent acts → verifier scores. Step 6 is a single trial. |
| **Job** | A batch container: Matraix Playground runs **many trials** from one YAML (step 7). Output lands in `jobs/<job_name>/` with one subfolder per trial. |
| **Agent** | How the simulated user is driven — under **auto**: `persona-json-survey` / `persona-user-sim` (host), or web/os-app Docker agents. |
| **Model** | Which LLM plays the persona — e.g. `anthropic/claude-sonnet-4-6`. Independent of the agent harness. |
| **Persona** | Which synthetic user profile — `persona_path=persona/datasets/matraix-persona-dev-sample/persona_0042.yaml`. |
| **Execution mode** | Playground **Mode** / `generate_application_job.py --execution-mode`. Default **`auto`**. |

**Step 6 vs 7:** Step 6 = **one persona** (`--persona-ids`). Step 7 =
`generate_application_job.py` **samples N personas** (seed + pool) into a job
YAML, then you `matraix run -c` that file once.

**Terminal vs Playground:** Steps 6–9 use the terminal (good for CI and smoke).
[Section 10](#10-playground-play-tasks-visually) uses the Playground UI —
same Matraix Playground contracts, better for exploring trajectories and iterating on new tasks.

---

## 6. One persona — CLI with Mode **auto** (default)

**Prefer this path for all four application types.** It matches Playground
**Mode → auto**.

```bash
uv run python application/scripts/generate_application_job.py \
  --task <task_path> \
  --execution-mode auto \
  --persona-ids 0042 \
  --model-name anthropic/claude-sonnet-4-6
# Then run the printed export lines and:
# uv run matraix run -c configs/jobs/application-task-job-recipe/<generated>-auto-n1.yaml
```

| Type | Auto picks | Runs on | Example `--task` |
|------|------------|---------|------------------|
| **Survey** | `persona-json-survey` | **host** (no task image build) | `application/tasks/example-survey_product-feedback` |
| **Chat** | `persona-user-sim` | **host** (+ sidecar env the script prints) | `application/tasks/chat_meal-planning-nutrition` |
| **Web** | path heuristic (OpenHands / browser-use / Cocoa / computer-1) | **docker** | `…/example-web-playwright_quote-choice`, `…/example-web-browser-use_laptop-choice`, … |
| **OS-app** | `persona-computer-1` | Linux **docker**; macOS/iOS **use-computer** | `…/example-computer-use-linux_note-to-csv`, `…/example-computer-use-macos_calendar-reminder-handoff` |

Web agent under auto (same as Playground): `*browser-use*` → `persona-browser-use`;
`*cocoa*` → `persona-cocoa`; `*cua*` / `*os-app*` / `*computer-use*` →
`persona-computer-1`; else → `persona-openhands-sdk`.

### Survey (auto)

```bash
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-survey_product-feedback \
  --execution-mode auto \
  --persona-ids 0042 \
  --model-name openai/gpt-4o-mini

# The generator prints a provider-aware Preflight block (which credential, present/missing).
export OPENAI_API_KEY="sk-..."
uv run matraix run -c configs/jobs/application-task-job-recipe/example-survey-product-feedback-auto-n1.yaml
# Optional hard spend gate (Survey refuses further provider calls once spend meets the cap):
# uv run matraix run -c … --max-cost-usd 1.00
```

`matraix run` reads the `MATRIX_*` task exports from the generated job files —
you only export your model API key. Completed Survey and Chat trials persist
`n_input_tokens` / `n_output_tokens` / `cost_usd` (when pricing is known) on
the trial and job result. Web / OS-app agents already report the same fields
through their Docker / computer-use runtimes.

### Chat (auto)

```bash
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/chat_meal-planning-nutrition \
  --execution-mode auto \
  --persona-ids 0042

export ANTHROPIC_API_KEY="sk-ant-..."
uv run matraix run -c configs/jobs/application-task-job-recipe/<generated>-auto-n1.yaml
```

### Web / OS-app (auto still uses Docker or use.computer)

```bash
# Playwright web
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-web-playwright_quote-choice \
  --execution-mode auto \
  --persona-ids 0042

export LLM_API_KEY="$ANTHROPIC_API_KEY"
uv run matraix run -c configs/jobs/application-task-job-recipe/example-web-playwright-quote-choice-auto-n1.yaml

# Linux computer-use (macOS/iOS need USE_COMPUTER_API_KEY)
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-computer-use-linux_note-to-csv \
  --execution-mode auto \
  --persona-ids 0042
```

The generator always prints the exact `export` lines and recipe path.
Script reference: [Job Generation Scripts](application/README.md).
Agent / key details: [choosing-an-agent.md](environment/agents.md).

**What happens**

1. Survey/chat **auto**: host-native agent (no application image build).
2. Web/os-app **auto**: Matraix Playground builds the task Docker image the first time
   (or starts a use.computer sandbox for macOS/iOS).
3. The agent reads the persona + task materials and writes `/app/output/…`.
4. The verifier runs; Matraix Playground writes one trial under `jobs/`.

**Success:** command ends without error; you see a path under `jobs/`.

### Optional: checked-in Docker recipes (`force_docker`-style)

Hand-written YAMLs under `configs/jobs/example-job-recipe/appSim-*-local.yaml`
are **smoke / Docker harness** examples (often `persona-claude-code` for
survey/chat). They are **not** Mode auto. Prefer the generator above unless you
intentionally want the CLI harness in Docker:

```bash
uv run matraix run -c configs/jobs/example-job-recipe/appSim-example-survey-local.yaml
uv run matraix run -c configs/jobs/example-job-recipe/appSim-example-web-playwright-local.yaml
```

To force Docker CLI agents from the generator: `--execution-mode force_docker`.

---

## 7. Batch — sample many personas (job)

Same generator as step 6; swap `--persona-ids` for **`--sample-size N`**
(or keep strategy filters). Works for **survey, chat, web, and os-app** —
auto still picks host vs Docker the same way.

**`generate_application_job.py`** samples personas, pins **agent**, **model**,
and **seed**, and writes a **job YAML** under
`configs/jobs/application-task-job-recipe/` (gitignored except curated examples).

Batch ≠ parallel: N personas = N trials. Edit `n_concurrent_trials` in the YAML
to run trials in parallel (generator often writes `1`; Playground defaults higher).

### Generate your own batch

```bash
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-survey_product-feedback \
  --execution-mode auto \
  --sample-size 10 \
  --seed 42 \
  --dataset persona/datasets/matraix-persona-dev-sample
```

**Persona 1M pool** (after
[importing the public coreset](README.md#3-persona-1m-recommended)):

```bash
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-survey_product-feedback \
  --execution-mode auto \
  --dataset persona/datasets/matraix-persona-1m \
  --sample-size 10 \
  --seed 42
```

**Playground-parity retrieval** (sources / dimension filters / task strategy / cohorts):

```bash
# Uses <task>/persona_strategy.json by default (filters + stratify + sampleSize).
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-survey_product-feedback \
  --execution-mode auto

# Explicit filters (same semantics as Persona World Filters).
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-survey_product-feedback \
  --execution-mode auto \
  --sample-size 6 \
  --sources wiki amazon \
  --filter age_bracket=25-34,35-44 \
  --filter economic_motivation=Cost-sensitive \
  --no-strategy
```

**Stratify** when you need balanced representation across a persona field:

```bash
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-survey_product-feedback \
  --execution-mode auto \
  --sample-size 10 \
  --seed 42 \
  --stratify dimensions.age_bracket
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--sample-size` | strategy / `1` | How many personas (= how many trials in the job) |
| `--persona-ids` | (none) | Explicit IDs instead of retrieval sampling |
| `--seed` | strategy / `42` | Random seed — same seed + pool → same persona IDs |
| `--dataset` | strategy / `matraix-persona-dev-sample` | Persona pool (also supports `matraix-persona-1m`) |
| `--sources` | strategy | Restrict to source chips (`wiki`, `amazon`, …) |
| `--filter DIM=VAL` | strategy | Dimension filter; repeatable; `a,b` for multi-value |
| `--filters-json` | (none) | JSON object form of dimension filters |
| `--strategy` / `--no-strategy` | auto-load task file | Apply or skip `persona_strategy.json` |
| `--cohort-id` | strategy | Saved Playground cohort |
| `--execution-mode` | `auto` | Same as Playground; use `force_docker` to always run in Docker |
| `--stratify` | strategy | Balance across a field, e.g. `dimensions.age_bracket` |
| `--name` | (derived) | Job basename |

Run the generated job (paths are also in the YAML header):

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
uv run matraix run -c configs/jobs/application-task-job-recipe/example-survey-product-feedback-auto-n10.yaml
```

**What a job means here:** one **task**, **N trials** — each trial uses a
different `persona_path` from the YAML. All trials share the same agent and model.

Each trial is one Matraix Playground run. Edit `n_concurrent_trials` in the YAML to run trials
in parallel.

**Cost note:** 10 trials ≈ 10 LLM calls. Use `--sample-size 3` while testing.

---

## 8. Find your output on disk

After a job finishes:

```text
jobs/<job_name>/
├── result.json           # Job summary stats (tokens/cost when recorded)
├── job.log
└── <trial_name>/
    ├── result.json       # Trial reward / verifier outcome + agent usage
    ├── persona_meta.json # Which persona was used (if persona agent)
    └── artifacts/
        └── app/output/   # The agent's submission JSON
            # Survey: survey_result.json
```

Summarize a finished job from the CLI (no extra LLM call):

```bash
uv run matraix results jobs/<job_name>
uv run matraix results <job_name> --format json,csv -o /tmp/matraix-exports/
# Optional persona cuts when dimensions are present:
# uv run matraix results <job_name> --group-by life_stage --format json
```

Open the submission JSON to read what that simulated user chose.

Refresh batch reporting:

```bash
uv run python application/scripts/report_job.py jobs/<job_name>
```

For a **task PR**, also open the job in Playground **Runs** and download the
persona-task batch report with **Download PDF**. Attach that UI PDF to the PR —
not the server text `…/report.pdf` export. See
[tasks/README.md — PR batch evidence](../application/tasks/README.md#pr-batch-evidence-required).

---

## 9. Browse runs in the viewer

```bash
uv run harbor view jobs --build
```

Opens a local web UI listing jobs and trials — transcripts, artifacts, verifier
logs. Use this to compare personas side by side.

To explore without spending API credits, browse checked-in examples under `jobs/`
if present, or run the no-key smoke recipe from step 3.

Job recipe layout: [../docs/configuration.md](configuration.md#job-recipe-conventions).

---

## 10. Playground — play tasks visually

After smoke passes, use the **Playground** to pick tasks, sample personas, launch
Matraix Playground jobs, and inspect trajectories live — without hand-writing job YAML each
time.

### Start the UI

**Terminal A — API**

```bash
VENV=.venv bash application/playground/backend/run_dev.sh
```

**Terminal B — frontend (hot reload)**

```bash
cd application/playground/frontend && npm ci && npm run dev
```

Open **http://localhost:5173** (proxies `/api` → `:8765`).

Check the footer **Preflight** chip before blaming a task. Green = keys, Docker
(when needed), and catalogs look ready.

One-shot (API serves built frontend, no Vite):

```bash
cd application/playground/frontend && npm ci && npm run build
cd ../../.. && application/playground/run_demo.sh
# → http://127.0.0.1:8765
```

More detail: [docs/application/README.md § Playground App](application/README.md),
[rest-api.md](application/playground-api.md).

### In the Playground

1. Open the **Playground** tab.
2. Switch task kind: **Survey** · **Chat** · **Web** · **OS app**.
3. Pick a task card; read instruction/context in the right panel.
4. Sample personas — **Quick pick** (`0042` is the default smoke id), **Random**,
   or **Stratified**.
5. Leave **Mode → auto** (default) and click **Run eval**.
6. Watch live progress; open a trial debrief for trajectory, scorecard, and verifier output.
7. Use **Runs** in the top bar to reopen past jobs.

| Task kind | First-run notes |
|-----------|-----------------|
| Survey | Fast — host auto mode, no task image build |
| Chat | Host auto; toggle **Start sidecar** if the task card shows the sidecar down |
| Web | Docker image build on first run; pick the web agent driver that matches the task stack |
| OS app | Docker or use.computer depending on platform |

Playground launches the same Matraix Playground jobs as `generate_application_job.py --execution-mode auto`.
Chat env exports (`MATRIX_CHATBOT_*`) are applied automatically from the UI.

### Register a new task for Playground

New tasks must be indexed before they appear in the task picker. See
[task-guide.md § Playground registration](application/task-guide.md#playground-registration).

---

## 11. Create a new application task

### 1. Understand task structure

Read [task-guide.md](application/task-guide.md) — `task.toml`, `instruction.md`, `input/`,
shared runtimes under `environment/task-environments/application/`, `tests/`.

### 2. View other scenario types

Survey is only one **form**. Chat, web, and computer-use use different runtimes
and agents — under Mode **auto** the generator picks them
([choosing-an-agent.md](environment/agents.md)).

Browse the example table in [task-guide.md § Reference scenarios](application/task-guide.md#reference-scenarios),
run any example with the suggested agent, then inspect with Playground or
`harbor view`.

Web stack choice: [web-interaction.md](environment/web-interaction.md).

### 3. Scaffold a new task

Copy the closest **example** task, then put your copy at
**`application/tasks/<your-task-name>`**:

```bash
# survey
cp -R application/tasks/example-survey_product-feedback application/tasks/<your-task-name>

# chat (REST API sidecar) — persona talks HTTP /v1/messages
cp -R application/tasks/example-chat-api_support_chatbot application/tasks/<your-task-name>

# chat (MCP sidecar) — persona talks MCP chat tools directly
cp -R application/tasks/example-chat-mcp_support_chatbot application/tasks/<your-task-name>

# For real benchmark tasks, rename to survey_* / chat_<sut> (see tasks/README.md).
# HTTP adapter over an internal MCP data layer still uses chatbot-api-sidecar_*
# (example: chat_openbb-corporate-action-honesty → chatbot-api-sidecar_openbb).

# web — pick one example-web-* stack (see web-interaction.md)
cp -R application/tasks/example-web-playwright_quote-choice application/tasks/<your-task-name>

# computer-use (macOS / iOS / Linux — copy the matching example)
cp -R application/tasks/example-computer-use-macos_calendar-reminder-handoff application/tasks/<your-task-name>
```

### 4. Edit the task

1. **`task.toml`** — metadata (`type`, `domain`, `tags`), timeouts, `[environment].definition`.
2. **`instruction.md`** — scenario and required `/app/output/` format (**persona-facing only** — no agent names).
3. **`input/`** — context, schemas, questionnaire (survey), chatbot config (chat).
4. **`tests/`** — verifier; trajectory / submission fields for metrics.
5. **`reporting.json`** — batch reporting policy.

Runtime Dockerfiles live under `environment/task-environments/application/`
(prefer `shared-*` when the execution model matches).

### 5. Smoke with one persona (terminal)

```bash
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/<your-task-name> \
  --execution-mode auto \
  --persona-ids 0042
# Run the printed harbor command + exports
```

Use the agent from [choosing-an-agent.md](environment/agents.md) for your form.

### 6. Iterate in Playground

Register the task ([task-guide.md](application/task-guide.md)), restart the backend, then
play with Quick pick personas before scaling sample size.

### 7. Batch of personas

Same as [step 7](#7-batch--sample-many-personas-job) with your task path.

### 8. View outputs

Playground **Runs** tab, or:

```bash
uv run harbor view jobs/<job_name> --build
```

Full task checklist: [tasks/README.md](../application/tasks/README.md).

---

## Cheat sheet

| Goal | Tool | Output |
|------|------|--------|
| Explore / debug visually | Playground (Mode **auto**) | `jobs/` |
| Any of 4 types (terminal, single or batch) | `generate_application_job.py --execution-mode auto` + `matraix run -c` | `jobs/<job_name>/` |
| Validate Docker/Matraix Playground only | `harbor-smoke-local.yaml` | smoke task image |
| Docker CLI harness (survey/chat) | `--execution-mode force_docker` or `appSim-*-local.yaml` | Docker trials |
| Browse trajectories | `harbor view` or Playground **Runs** | local viewer |
| New scenario | copy `example-*` + register for Playground | `application/tasks/<name>/` |

---

## Related docs

| Doc | Purpose |
|-----|---------|
| [task-guide.md](application/task-guide.md) | Task folder structure and reference scenarios |
| [web-interaction.md](environment/web-interaction.md) | Playwright vs browser-use vs Cocoa vs CUA |
| [choosing-an-agent.md](environment/agents.md) | Agent ↔ form mapping and API keys |
| [tasks/README.md](../application/tasks/README.md) | Task-authoring checklist and reporting |
| [docs/application/README.md § Job Generation Scripts](application/README.md) | Job generator and reporting scripts |
| [unified-runtime.md](environment/runtime.md) | Matraix Playground vs remote execution plane |
