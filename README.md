<div align="center">
  <h1>MatrAIx</h1>
  <p><strong>Simulate before reality.</strong></p>
  <p>
    Population-scale, persona-driven infrastructure for evaluating AI systems
    and interactive products with heterogeneous simulated users.
  </p>
  <p>
    <strong>English</strong> |
    <a href="docs/i18n/README.ko.md">한국어</a> |
    <a href="docs/i18n/README.zh-CN.md">简体中文</a> |
    <a href="docs/i18n/README.zh-TW.md">繁體中文</a> |
    <a href="docs/i18n/README.ja.md">日本語</a> |
    <a href="docs/i18n/README.pt-BR.md">Português</a> |
    <a href="docs/i18n/README.es.md">Español</a>
  </p>
  <p>
    <a href="https://matraix.ai/"><img alt="Website" src="https://img.shields.io/badge/Website-matraix.ai-4f7cff?style=for-the-badge"></a>
    <a href="https://discord.gg/knVyQQnRFa"><img alt="Discord" src="https://img.shields.io/badge/Discord-join%20MatrAIx-5865F2?style=for-the-badge&logo=discord&logoColor=white"></a>
    <a href="https://x.com/MatrAIx2026"><img alt="X" src="https://img.shields.io/badge/X-%40MatrAIx2026-000000?style=for-the-badge&logo=x&logoColor=white"></a>
    <a href="https://www.linkedin.com/company/matraix"><img alt="LinkedIn" src="https://img.shields.io/badge/LinkedIn-MatrAIx-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white"></a>
    <a href="https://forms.gle/hwEHng5HGWRqcJue9"><img alt="Google Form" src="https://img.shields.io/badge/Google%20Form-join%20MatrAIx-4285F4?style=for-the-badge&logo=googleforms&logoColor=white"></a>
    <a href="docs/README.md"><img alt="Docs" src="https://img.shields.io/badge/Docs-Handbook-5b5b5b?style=for-the-badge"></a>
    <a href="https://huggingface.co/datasets/MatrAIx2026/MatrAIx_Persona_1M_Public_Release"><img alt="Hugging Face" src="https://img.shields.io/badge/Hugging%20Face-Persona%201M-ffcc4d?style=for-the-badge"></a>
    <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/License-MIT-c33b32?style=for-the-badge"></a>
    <a href="docs/quickstart.md#10-playground--play-tasks-visually"><img alt="Playground" src="https://img.shields.io/badge/Playground-Visual%20Runner-56b879?style=for-the-badge"></a>
  </p>
</div>

<div align="center">
  <a href="https://www.youtube.com/watch?v=cNFkz9Wo1y4&t=15s">
    <img src="https://img.youtube.com/vi/cNFkz9Wo1y4/maxresdefault.jpg" alt="Watch the MatrAIx demo on YouTube" width="900">
  </a>
  <p>
    <a href="https://www.youtube.com/watch?v=cNFkz9Wo1y4&t=15s"><img alt="Watch the MatrAIx demo on YouTube" src="https://img.shields.io/badge/%E2%96%B6%20Watch%20the%20demo-on%20YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white"></a>
  </p>
</div>

---

**MatrAIx** is a population-scale, persona-driven infrastructure for evaluating
AI systems and interactive products with heterogeneous simulated users. Instead
of testing against a generic or interchangeable user, MatrAIx instantiates
sampled persona records as LLM agents and runs them through reproducible tasks
across four environments — **Survey**, **AI Chatbot**, **Web**, and **App**
(native desktop and mobile, including macOS and iOS).

At its foundation is a shared schema of **1,290 categorical dimensions** covering
background, psychology, capability, and behavior. Personas combine
dependency-aware synthetic generation with evidence-aware human grounding; a
deterministic, quality-filtered coreset of **one million personas** is released
for research on
[Hugging Face](https://huggingface.co/datasets/MatrAIx2026/MatrAIx_Persona_1M_Public_Release).
Shared telemetry, task-owned verification, and reporting connect individual
responses and trajectories to subgroup- and population-level findings.

The name nods to *The Matrix*: a simulated world useful for exploration, stress
testing, and hypothesis generation, **not a replacement for evidence from real
people**.

## News

- **[2026-08-11]** Academic commentary: [*Can we simulate the world?*](https://aiscientist.substack.com/p/can-we-simulate-the-world) by Mayank Kejriwal ([*AI Scientist*](https://aiscientist.substack.com/)).
- **[2026-08-10]** Featured as an [X Trending Story](https://x.com/i/trending/2086626337561911419): *Harvard and MIT Unveil MatrAIx with 8.3 Billion Virtual Personas*. Also covered across tech media, including [36Kr](https://eu.36kr.com/en/p/3932853833759876), [Numerama](https://www.numerama.com/tech/2308727-ces-chercheurs-ont-cree-83-milliards-dhumains-virtuels-pour-tester-des-produits-a-notre-place.html), [Infobae](https://www.infobae.com/tecno/2026/08/10/asi-prueba-la-ia-un-mundo-con-8300-millones-de-personas-digitales-matraix-es-el-metaverso/), [AI타임스](https://www.aitimes.com/news/articleView.html?idxno=213824), [CryptoBriefing](https://cryptobriefing.com/matraix-simulation-harvard-mit-ai-personas/), and [Startup Fortune](https://startupfortune.com/harvard-and-mit-built-an-ai-model-of-83-billion-people-to-test-products-on/), among others. Also discussed by Cisco VP & CTO [Gianpaolo Barozzi](https://lnkd.in/p/gE9cV2nw).
- **[2026-08-04]** Technical report on arXiv: [MatrAIx: Simulating the World with 8.3 Billion Persona Agents](https://arxiv.org/abs/2608.04205) (`2608.04205`). Also featured on [Hugging Face Daily Papers](https://huggingface.co/papers/date/2026-08-10) ([paper page](https://huggingface.co/papers/2608.04205)).
- **[2026-08-01]** Released [Persona 1M](https://huggingface.co/datasets/MatrAIx2026/MatrAIx_Persona_1M_Public_Release) on Hugging Face (~1M quality-filtered personas).
- **[2026-07-31]** Open-sourced the Playground and task library: [MatrAIx-Persona-8B](https://github.com/MatrAIx-ai/MatrAIx-Persona-8B).
- **[2026-07-29]** Position note: [From Personas to Simulated Users](https://matraix.ai/research/survey-from-personas-to-simulated-users.html).

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- [uv](https://docs.astral.sh/uv/) and Python 3.12
- Node.js 20+ (Playground / viewer frontends only)
- Model API keys for persona-agent examples — see [agents.md](docs/environment/agents.md)

> **Windows users**: run everything inside
> [WSL2](https://learn.microsoft.com/windows/wsl/install) — open PowerShell,
> run `wsl --install` (installs Ubuntu), then clone this repo **inside the WSL
> filesystem** (e.g. `~/MatrAIx`, not `/mnt/c/…`, which is much slower) and
> enable *WSL integration* in Docker Desktop → Settings → Resources. Every
> command in this README then works exactly as written. Native
> PowerShell/cmd is not supported (the task verifiers require `bash`).

## Installation

```bash
git clone <repo-url> && cd MatrAIx
uv venv --python 3.12
uv pip install -e .
uv pip install pytest pytest-asyncio httpx
uv pip install -e packages/playground
uv pip install -e packages/harbor-langsmith
uv pip install -e packages/rewardkit
```

Run jobs and tasks with **`uv run matraix run …`** — it sets up the full
launch environment and delegates to the Harbor runtime. Check a Survey task
with **`uv run matraix smoke <task>`** (host / `json_survey`, no Docker, no API
key). Summarize a finished job with **`uv run matraix results <job>`** (text /
JSON / CSV, no extra LLM call). Runtime utilities (e.g. `harbor view`,
`harbor upload`) stay under `uv run harbor …`.

Set the model API key matching your provider before GUI or CLI task runs
(smokes above do not need one):

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # anthropic/claude-* models
# export OPENAI_API_KEY="sk-..."        # openai/gpt-* models
```

See [agents.md](docs/environment/agents.md) for the full key matrix.
Playground can also load keys from `application/playground/.env.local`.

### Import Persona 1M (recommended)

The in-repo `matraix-persona-dev-sample` (~200) is for smoke only. For real
cohorts and Playground sampling, import the public 1M coreset:

```bash
huggingface-cli download MatrAIx2026/MatrAIx_Persona_1M_Public_Release \
  --repo-type dataset \
  --local-dir persona/datasets/matraix-persona-1m/release
```

Playground: Dataset → **`matraix-persona-1m`**. CLI: `--dataset persona/datasets/matraix-persona-1m`.
Details: [Handbook § Persona 1M](docs/README.md#3-persona-1m-recommended).

## Quick start

### Smoke test

No API key required. **Requires Docker** (the smoke job uses
`environment.type: docker`):

```bash
uv run matraix run -c configs/jobs/example-job-recipe/harbor-smoke-local.yaml
```

### GUI task runs

Playground picks tasks, samples personas, and launches the same Matraix Playground jobs as CLI auto mode.
Start API + frontend (two terminals):

```bash
# Terminal A — API
VENV=.venv bash application/playground/backend/run_dev.sh

# Terminal B — frontend
cd application/playground/frontend && npm ci && npm run dev
```

Open **http://localhost:5173** → Playground → pick a persona cohort →
pick Survey / Chat / Web / OS app tasks → **Lock pipeline** → **Run eval**.
Details: [Playground §10](docs/quickstart.md#10-playground--play-tasks-visually).

### CLI task develop / runs

**Develop** — copy a reference task under `application/tasks/`, edit
`task.toml` / `instruction.md` / `input/` / verifier, then register it for Playground
([task-guide.md](docs/application/task-guide.md)):

```bash
cp -R application/tasks/example-survey_product-feedback \
  application/tasks/<your-task-name>
```

| Type | Reference task |
|------|----------------|
| Survey | `application/tasks/example-survey_product-feedback` |
| Chat | `application/tasks/example-chat-api_support_chatbot` |
| Web | `application/tasks/example-web-playwright_quote-choice` |
| OS-app | `application/tasks/example-computer-use-linux_note-to-csv` |

**Run** — generate a Matraix Playground job (pins agent + model), then execute it:

```bash
uv run python application/scripts/generate_application_job.py \
  --task application/tasks/example-survey_product-feedback \
  --execution-mode auto \
  --persona-ids 0042 \
  --model-name anthropic/claude-sonnet-4-6

# Use the export lines + recipe path the script prints, e.g.:
uv run matraix run -c configs/jobs/application-task-job-recipe/example-survey-product-feedback-auto-n1.yaml
```

Batch (`--sample-size N`), filters, and chat / web / os-app examples:
[docs/quickstart.md](docs/quickstart.md).

## Docs

**[MatrAIx Handbook](docs/README.md)** — guides, persona / application / environment docs.

<p align="center">
  <img src="docs/assets/matraix-architecture.png" alt="MatrAIx architecture" width="900">
</p>

## Repository layout

```text
MatrAIx/
├── persona/                 Schema, datasets, synthesis/curation/validation pipelines
│   ├── schema/              1,290-dimension persona schema
│   ├── datasets/            Dev sample pool and persona YAMLs
│   ├── validation/          Grounding / quality validation suites
│   └── scripts/             Persona job & pipeline helpers
├── application/
│   ├── tasks/               Survey · chat · web · os-app task specs
│   ├── task-spec/           Shared task contracts
│   ├── playground/          Visual runner (backend API + frontend)
│   └── scripts/             generate_application_job.py and task tooling
├── environment/
│   ├── runtime/             Matraix Playground runtime
│   ├── agents/              Persona-conditioned agents
│   ├── task-environments/   Docker images / sidecars
│   └── adapters/            External adapters (e.g. SimpleQA)
├── packages/                playground · rewardkit · harbor-langsmith
├── apps/viewer/             Frontend paired with `harbor view`
├── configs/jobs/            Curated & generated Matraix Playground job recipes
├── docs/                    Handbook — persona/ · application/ · environment/
├── examples/                Minimal example tasks
├── src/matraix/             Python package entrypoints
├── scripts/                 Repo-level helpers
├── tests/                   Unit / environment tests
└── jobs/                    Local Matraix Playground run outputs (gitignored)
```

Large generated datasets stay outside git (see the Hugging Face release above).

## Join the Community

[![Discord](https://img.shields.io/badge/Discord-join%20MatrAIx-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/knVyQQnRFa)
[![X](https://img.shields.io/badge/X-follow%20%40MatrAIx2026-000000?style=for-the-badge&logo=x&logoColor=white)](https://x.com/MatrAIx2026)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-follow%20MatrAIx-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/company/matraix)
[![Google Form](https://img.shields.io/badge/Google%20Form-join%20MatrAIx-4285F4?style=for-the-badge&logo=googleforms&logoColor=white)](https://forms.gle/hwEHng5HGWRqcJue9)

1. Join Discord — nickname **`Full Name - Affiliation`**. Fill the Google Form
   (background, interests, paper authorship / acknowledgements).
2. Say hi to us! We like to connect you for the shared interest or experience!
3. Participating MatrAIx research community for collaboration or contribution!

## Citation

If you use MatrAIx, the Persona 1M dataset, or results from this repository,
please cite:

```bibtex
@article{li2026matraix,
  title         = {MatrAIx: Simulating the World with 8.3 Billion Persona Agents},
  author        = {Li, Xiaomin and Hao, Yuexing and Hou, Jianheng and Huang, Jintao
                   and Wen, Qianfeng and Huang, Shirley and Liu, Yifan and Liu, Xiaoyi
                   and Fan, Yilan and Wang, Yijun and others},
  year          = {2026},
  eprint        = {2608.04205},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2608.04205}
}
```

Paper: [arXiv:2608.04205](https://arxiv.org/abs/2608.04205) ·
Full authors: GitHub **Cite this repository** (`CITATION.cff`) ·
Dataset: [Persona 1M on Hugging Face](https://huggingface.co/datasets/MatrAIx2026/MatrAIx_Persona_1M_Public_Release).

## Star History

<a href="https://www.star-history.com/?repos=MatrAIx-ai%2FMatrAIx-Persona-8B&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=MatrAIx-ai/MatrAIx-Persona-8B&type=date&theme=dark&legend=top-left&sealed_token=Yg8UrFwz3ELwyx6wW2CobWIwzUg_VZv53wOwlLji13fApPKuro445vOLW1W5Vy_NfU4NUON-ARepltF9i1-YiNiuSzMK4BVrFHURZLQMoAkeeh4uaxqysfKvTrPQ1cW6zXotcAwoUlKv5Ana5kuWGQj0e-wZoNDaJ6QVL7c8adFut281xX5Quo0c07Y7" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=MatrAIx-ai/MatrAIx-Persona-8B&type=date&legend=top-left&sealed_token=Yg8UrFwz3ELwyx6wW2CobWIwzUg_VZv53wOwlLji13fApPKuro445vOLW1W5Vy_NfU4NUON-ARepltF9i1-YiNiuSzMK4BVrFHURZLQMoAkeeh4uaxqysfKvTrPQ1cW6zXotcAwoUlKv5Ana5kuWGQj0e-wZoNDaJ6QVL7c8adFut281xX5Quo0c07Y7" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=MatrAIx-ai/MatrAIx-Persona-8B&type=date&legend=top-left&sealed_token=Yg8UrFwz3ELwyx6wW2CobWIwzUg_VZv53wOwlLji13fApPKuro445vOLW1W5Vy_NfU4NUON-ARepltF9i1-YiNiuSzMK4BVrFHURZLQMoAkeeh4uaxqysfKvTrPQ1cW6zXotcAwoUlKv5Ana5kuWGQj0e-wZoNDaJ6QVL7c8adFut281xX5Quo0c07Y7" />
 </picture>
</a>

## License

MIT — see [LICENSE](LICENSE).
