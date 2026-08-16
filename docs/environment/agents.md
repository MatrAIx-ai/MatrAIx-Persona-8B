# Choosing a Persona Agent and Model

Every run specifies the agent, model, persona, and task — via Playground,
`generate_application_job.py`, or a hand-written Matraix Playground recipe.

## Execution mode (default: **auto**)

Playground **Mode** and `generate_application_job.py --execution-mode` share the
same three values. **Use `auto` unless you have a reason not to.**

| Mode | Survey / chat | Web / OS-app |
|------|---------------|--------------|
| **`auto`** (default) | Host: `persona-json-survey` / `persona-user-sim` | Docker (or use.computer for macOS/iOS CUA); agent from task path |
| **`force_docker`** | Docker CLI harness (default `persona-claude-code` unless `--agent-name`) | Docker |
| **`smoke`** | Smoke profile | — |

**Important:** `auto` does **not** mean “no Docker” for web/os-app — only
survey/chat skip the task image. CLI walkthrough for all four types:
[quickstart.md §6–7](../quickstart.md#6-one-persona--cli-with-mode-auto-default).

Web agent under auto (path heuristics):

- `*browser-use*` → `persona-browser-use`
- `*cocoa*` → `persona-cocoa`
- `*cua*` / `*os-app*` / `*computer-use*` → `persona-computer-1`
- else web → `persona-openhands-sdk`

## Parameters

| Flag | Meaning | Example |
|------|---------|---------|
| `-a` | Persona agent (manual `harbor run` only) | `persona-browser-use` |
| `-m` | Persona LLM (simulated user) | `anthropic/claude-sonnet-4-6` |
| `-p` | Task scenario | `application/tasks/example-survey_product-feedback` |
| `--ak persona_path` | Persona YAML (**which profile**) | `persona/datasets/matraix-persona-dev-sample/persona_0042.yaml` |
| `--model-name` | Same as `-m`, on `generate_application_job.py` | `openai/gpt-4o-mini` |
| `--execution-mode` | `auto` / `force_docker` / `smoke` | `auto` |

Default smoke persona: **`persona_0042`** in `persona/datasets/matraix-persona-dev-sample/`.

## Persona model (`-m` / `--model-name`)

The **persona LLM** is the model that plays the simulated user. It is separate
from chat **SUT** backends (`MATRIX_CHATBOT_ENGINE`, sidecar APIs, etc.).

All persona agents — including auto host-native survey/chat — resolve the model
the same way:

1. Matraix Playground job `agents[].model_name` or CLI `-m` / `--model-name` (**wins**)
2. `MATRIX_CHATBOT_PERSONA_MODEL` (chat auto only, when no YAML model)
3. `MATRIX_PERSONA_MODEL` or `MATRIX_HARBOR_PERSONA_MODEL`
4. Default: `anthropic/claude-haiku-4-5`

Web/CUA agents (`persona-browser-use`, `persona-computer-1`, …) and auto agents
(`persona-json-survey`, `persona-user-sim`) all honor the YAML `model_name`.
CLI wrapper agents (`persona-claude-code`, …) pass `-m` through to the same field.

Supported persona models in Playground include Anthropic (`anthropic/claude-*`),
OpenAI (`openai/gpt-4o*`), and DashScope OpenAI-compatible models
(`dashscope/qwen3.6-plus-2026-04-02`, `dashscope/qwen3.7-max`,
`dashscope/deepseek-v4-pro`, …). Set `DASHSCOPE_API_KEY` (and optional
`DASHSCOPE_API_BASE`) when using `dashscope/*` — the same `-m` value applies to
auto survey/chat and Docker web/CUA agents. OpenRouter models include
`openrouter/z-ai/glm-4.7` and `openrouter/anthropic/claude-haiku-4.5`. Set
`OPENROUTER_API_KEY` (and optional `OPENROUTER_API_BASE`) for `openrouter/*`.
`OPENROUTER_BASE_URL` remains a compatibility alias when
`OPENROUTER_API_BASE` is unset.
CLI harness agents
(`persona-claude-code`, `persona-gemini-cli`, `persona-codex`) stay
vendor-locked. Other LiteLLM-compatible ids may work if the matching API key is
set.

## Persona agents

| CLI name | Application | Typical use | Example task |
|----------|-------------|-------------|----------------|
| `persona-json-survey` | survey | **Auto mode (recommended):** one-shot JSON survey on the host; no Docker | [product-feedback](../../application/tasks/example-survey_product-feedback) |
| `persona-user-sim` | chat | **Auto mode (recommended):** multi-turn user simulator + task sidecar on the host | [meal-planning](../../application/tasks/chat_meal-planning-nutrition)<br>[openbb-honesty](../../application/tasks/chat_openbb-corporate-action-honesty)<br>[acme-support-api](../../application/tasks/example-chat-api_support_chatbot) |
| `persona-claude-code` | survey<br>chat | Docker CLI harness — use with `--execution-mode force_docker`, not Mode auto | [product-feedback](../../application/tasks/example-survey_product-feedback)<br>[acme-support-api](../../application/tasks/example-chat-api_support_chatbot)<br>[acme-support-mcp](../../application/tasks/example-chat-mcp_support_chatbot) |
| `persona-gemini-cli` | survey<br>chat | Same role as `persona-claude-code`; Google Gemini CLI | [product-feedback](../../application/tasks/example-survey_product-feedback) |
| `persona-codex` | survey<br>chat | Same role as `persona-claude-code`; OpenAI Codex CLI | [product-feedback](../../application/tasks/example-survey_product-feedback) |
| `persona-openhands-sdk` | web | Python Playwright in the terminal (DOM selectors); fast, CI-friendly | [quote-choice-playwright](../../application/tasks/example-web-playwright_quote-choice) |
| `persona-browser-use` | web | browser-use agent loop over Chromium | [laptop-choice-browser-use](../../application/tasks/example-web-browser-use_laptop-choice) |
| `persona-cocoa` | web | browser + shell + files in one container | [plan-choice-cocoa](../../application/tasks/example-web-cocoa_plan-choice) |
| `persona-computer-1` | web<br>computer-use | Screenshot CUA; auto-routes to use.computer (macOS/iOS) or Docker Linux | **computer-use:** [macos-calendar-reminder-handoff](../../application/tasks/example-computer-use-macos_calendar-reminder-handoff)<br>[ios-photo-access-review](../../application/tasks/example-computer-use-ios_photo-access-review)<br>[ios-news-subscription-decision](../../application/tasks/os-app-ios_news-subscription-decision)<br>[linux-note-to-csv](../../application/tasks/example-computer-use-linux_note-to-csv)<br>**web:** [bookshop-choice-cua](../../application/tasks/example-web-cua_bookshop-choice) |

`generate_application_job.py --execution-mode auto` picks `persona-json-survey` or
`persona-user-sim` from the task type. Use `--agent-name` to override, or
`--execution-mode force_docker` for the CLI agents above.

Live-web details: [web-interaction.md](web-interaction.md).

The Playground selects the web agent driver per task in the UI — that
metadata is for operators, not for `instruction.md`.

### Web modes at a glance

| Mode | Agent | How the agent sees the page | Strengths | Trade-offs |
|------|-------|----------------------------|-----------|------------|
| **Playwright** | `persona-openhands-sdk` | Terminal agent **writes & runs Python**; reads the page via Playwright **DOM API** (`locator`, `goto`, …). No built-in screenshot loop. | Cheapest Docker web mode; repeatable | Agent must write working scripts |
| **browser-use** | `persona-browser-use` | Dedicated browser loop: each step the model gets **page structure (DOM)** and picks click/type/scroll tools. Screenshots are **optional**, not every turn. | Purpose-built web agent | Slower than a good hand-written script |
| **Cocoa** | `persona-cocoa` | Same browser as above (**DOM tools first**), plus optional `browser_screenshot`, and **shell + files** in one container. | All-in-one digital agent in Docker | Heavier base image |
| **CUA** | `persona-computer-1` | **Screenshot every turn** of a real remote desktop, then mouse/keyboard — closest to “looking at the screen”. | Highest human fidelity | Slowest; higher LLM cost |

## Environment variables (host)

Persona agents read API keys from the **host** shell (or job `agents[].env`). Names
differ by agent:

| Agent | Required on host | Notes |
|-------|------------------|-------|
| `persona-json-survey` | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DASHSCOPE_API_KEY`, or `OPENROUTER_API_KEY` | Match `-m` / YAML `model_name`. Auto host-native survey. |
| `persona-user-sim` | Persona: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DASHSCOPE_API_KEY`, or `OPENROUTER_API_KEY`; often `OPENAI_API_KEY` for SUT | Persona model via `-m`; chat sidecar engine via `MATRIX_CHATBOT_ENGINE` (default `gpt-4o-mini`). |
| `persona-claude-code` | `ANTHROPIC_API_KEY` (or subscription — see below) | Anthropic models |
| `persona-gemini-cli` | `GEMINI_API_KEY` (or subscription — see below) | Google models, e.g. `google/gemini-2.5-pro` |
| `persona-codex` | `OPENAI_API_KEY` (or subscription — see below) | OpenAI models, e.g. `openai/gpt-4o` |
| `persona-openhands-sdk` | **`LLM_API_KEY`**, `DASHSCOPE_API_KEY`, or `OPENROUTER_API_KEY` (match `-m`) | Provider-specific DashScope and OpenRouter keys map automatically to `LLM_API_KEY`. For Anthropic/OpenAI, map explicitly, e.g. `export LLM_API_KEY="$ANTHROPIC_API_KEY"`. |
| `persona-browser-use` | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DASHSCOPE_API_KEY`, or `LLM_API_KEY` | DashScope: set `DASHSCOPE_API_KEY` (+ optional `DASHSCOPE_API_BASE`). |
| `persona-cocoa` | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DASHSCOPE_API_KEY`, or `LLM_API_KEY` | Task image must be AIO Sandbox-based. |
| `persona-computer-1` | `ANTHROPIC_API_KEY` or `DASHSCOPE_API_KEY` | Docker Linux web CUA and linux computer-use. **use.computer** (macOS/iOS) also needs `USE_COMPUTER_API_KEY`. Install extras: `uv sync --extra use-computer --extra computer-1`. |

Chat tasks may also need `OPENAI_API_KEY` and `MATRIX_CHATBOT_*` exports — the
job generator prints them. Optional global persona default:
`export MATRIX_PERSONA_MODEL=anthropic/claude-sonnet-4-6` (overridden when the job
YAML sets `model_name`).

Job YAML can pass keys per agent, e.g. `agents[].env.LLM_API_KEY: ${ANTHROPIC_API_KEY}`.

### Setting API keys

Export in your shell before running (e.g. in `~/.zshrc` or the current terminal):

```bash
export ANTHROPIC_API_KEY=sk-...
export GEMINI_API_KEY=...
export OPENAI_API_KEY=sk-...
export OPENROUTER_API_KEY=...

# persona-openhands-sdk (pick one to match -m)
export LLM_API_KEY="$ANTHROPIC_API_KEY"
# export LLM_API_KEY="$GEMINI_API_KEY"
# export LLM_API_KEY="$OPENAI_API_KEY"

export USE_COMPUTER_API_KEY=...  # persona-computer-1 on use.computer (macOS/iOS)
```

Variable names per agent: see the export blocks below.

### CLI subscription auth (optional)

For **`persona-claude-code`**, **`persona-codex`**, and **`persona-gemini-cli`**, the
default path is an **API key** on the Matraix Playground runner (the machine that launches Docker
trials). If you already use the vendor CLI through a **subscription**, you can opt in
instead — Matraix Playground uploads your local credential file into the trial container.

**Playground:** copy `application/playground/.env.local.example` to `.env.local`,
uncomment the matching block, restart the backend (`run_dev.sh` / `run_demo.sh`).

| Harness | Host setup (once) | Enable in `.env.local` or shell |
|---------|-------------------|----------------------------------|
| `persona-codex` | `codex login` → `~/.codex/auth.json` | `CODEX_FORCE_AUTH_JSON=1` |
| `persona-claude-code` | `claude setup-token` → paste token | `CLAUDE_FORCE_OAUTH=1` and `CLAUDE_CODE_OAUTH_TOKEN=...` |
| `persona-gemini-cli` | Gemini CLI login → `~/.gemini/oauth_creds.json` | `GEMINI_FORCE_OAUTH=1` |

Optional explicit paths: `CODEX_AUTH_JSON_PATH`, `GEMINI_OAUTH_CREDS_PATH`.

If both an API key and subscription flags are set, **API keys win** unless you set
`CLAUDE_FORCE_OAUTH=1` or `CODEX_FORCE_AUTH_JSON=1` (Claude/Codex drop the key and
use subscription). Match `-m` / Playground persona model to the harness vendor as
usual.

Web CLI runs (Playground **Web → CLI family**) use the same runner credentials; see
[web-interaction.md](web-interaction.md) § CLI harness on web tasks.

## Examples

Auto mode (matches Playground; preferred for all four types):

```bash
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-survey_product-feedback \
  --execution-mode auto \
  --model-name anthropic/claude-sonnet-4-6 \
  --persona-ids 0042
# Run the printed harbor command + exports
```

The generated YAML includes `agents[].model_name`; edit it or pass `--model-name`
on regenerate to swap the persona LLM.

Manual Docker web one-liner (when you already know the agent):

```bash
uv run harbor run \
  -a persona-browser-use \
  -m anthropic/claude-sonnet-4-6 \
  --ak persona_path=persona/datasets/matraix-persona-dev-sample/persona_0042.yaml \
  -p application/tasks/example-web-browser-use_laptop-choice
```

Force Docker CLI harness for survey/chat (optional; not Mode auto):

```bash
uv run harbor run \
  -a persona-claude-code \
  -m anthropic/claude-sonnet-4-6 \
  --ak persona_path=persona/datasets/matraix-persona-dev-sample/persona_0042.yaml \
  -p application/tasks/example-chat-mcp_support_chatbot
```

Batch runs: [quickstart.md §7](../quickstart.md#7-batch--sample-many-personas-job),
[../configuration.md](../configuration.md#batch-job-generation).

## For task authors

Add **Suggested setup (non-binding)** in `application/tasks/.../README.md`; do
not hard-require an agent in `task.toml` or `instruction.md`.

The Playground web agent selector and this doc are for **operators**. The simulated
user prompt in `instruction.md` should never mention which Matraix Playground agent runs the
task.

## Related

- [quickstart.md](../quickstart.md)
- [task-guide.md](../application/task-guide.md)
- [web-interaction.md](web-interaction.md)
- [../configuration.md](../configuration.md#job-recipe-conventions)
