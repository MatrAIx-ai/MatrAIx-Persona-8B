"""Canonical metadata for Playground application tasks (+ persona bench).

``APPLICATION_TASK_METADATA`` keys must match ``application/tasks/<dirname>/``
folders that ship in this public tree (one entry per task directory).

Domain / vertical labels mirror each task's ``task.toml`` ``[metadata].domain``.

Tags are **task topic** labels (what the scenario is about). Use short
human-readable phrases (spaces allowed). Do not repeat ``type`` / ``domain``.

Harbor also supports ``[task].keywords`` for registry package search; Playground
example tasks omit it and use ``metadata.tags`` only.

Harbor ``[task].name`` (exactly one ``/``):

- Application tasks: ``matraix/application-{slug}``
- Persona bench (1 dim): ``personabench/persona-bench-dim-{NNN}-{slug}`` when ``bench_dim_index`` is set in catalog
- Persona bench (no dim): ``personabench/persona-bench-{slug}``
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, cast

DOMAIN_SOFTWARE = "software"
DOMAIN_FINANCE = "finance"
DOMAIN_FINANCE_RESEARCH = "finance-research"
DOMAIN_HEALTHCARE = "healthcare"
DOMAIN_COMMERCE = "commerce"
DOMAIN_COMMERCE_RETAIL = "commerce-retail"
DOMAIN_ARTS_CULTURE = "arts-culture"
DOMAIN_EDUCATION = "education"

APPLICATION_TASK_METADATA: dict[str, dict[str, object]] = {
    "chat_meal-planning-nutrition": {
        "type": "chatbot",
        "domain": DOMAIN_HEALTHCARE,
        "tags": [
            "nutrition",
            "meal planning",
            "dietary adherence",
            "health coaching",
            "multi turn chat",
            "personalized recommendations",
        ],
    },
    "chat_multilingual-telco-support": {
        "type": "chatbot",
        "domain": DOMAIN_COMMERCE,
        "tags": [
            "billing dispute",
            "invoice charge",
            "telecom operator",
            "language adherence",
            "reply language",
            "locale fallback",
        ],
    },
    "chat_openbb-corporate-action-honesty": {
        "type": "chatbot",
        "domain": DOMAIN_FINANCE_RESEARCH,
        "tags": [
            "corporate-action honesty",
            "ticker failure modes",
            "HCP ANSS CMG LAZR",
            "wouldStillContinueUse",
            "openbb",
            "multi turn chat",
        ],
    },
    "example-chat-api_support_chatbot": {
        "type": "chatbot",
        "domain": DOMAIN_COMMERCE_RETAIL,
        "tags": [
            "acme support",
            "missing delivery",
            "order 4521",
            "multi turn support",
            "delivery investigation",
        ],
    },
    "example-chat-mcp_support_chatbot": {
        "type": "chatbot",
        "domain": DOMAIN_COMMERCE_RETAIL,
        "tags": [
            "acme support",
            "missing delivery",
            "order 4521",
            "multi turn support",
            "delivery investigation",
        ],
    },
    "example-computer-use-ios_photo-access-review": {
        "type": "os-app",
        "domain": DOMAIN_SOFTWARE,
        "tags": [
            "photo permissions",
            "privacy settings",
            "app access review",
            "system settings",
        ],
    },
    "example-computer-use-linux_note-to-csv": {
        "type": "os-app",
        "domain": DOMAIN_SOFTWARE,
        "tags": [
            "file transform",
            "csv creation",
            "desktop editor",
            "structured output",
        ],
    },
    "example-computer-use-macos_calendar-reminder-handoff": {
        "type": "os-app",
        "domain": DOMAIN_SOFTWARE,
        "tags": [
            "calendar planning",
            "reminders handoff",
            "cross app workflow",
            "desktop productivity",
        ],
    },
    "example-survey_product-feedback": {
        "type": "survey",
        "domain": DOMAIN_SOFTWARE,
        "tags": [
            "FocusLoop",
            "product concept",
            "family calendar",
            "household coordination",
            "subscription pricing",
        ],
    },
    "example-web-browser-use_laptop-choice": {
        "type": "web",
        "domain": DOMAIN_COMMERCE_RETAIL,
        "tags": [
            "laptop shortlist",
            "product comparison",
            "budget tradeoff",
            "browser-use browsing",
        ],
    },
    "example-web-cocoa_plan-choice": {
        "type": "web",
        "domain": DOMAIN_SOFTWARE,
        "tags": [
            "pricing page",
            "plan selection",
            "budget sensitivity",
            "cocoa browser workflow",
        ],
    },
    "example-web-cua_bookshop-choice": {
        "type": "web",
        "domain": DOMAIN_ARTS_CULTURE,
        "tags": [
            "books toscrape",
            "bookshop browsing",
            "reading taste",
            "desktop browser choice",
        ],
    },
    "example-web-playwright_quote-choice": {
        "type": "web",
        "domain": DOMAIN_ARTS_CULTURE,
        "tags": [
            "quotes toscrape",
            "quote shortlist",
            "values preference",
            "playwright dom browsing",
        ],
    },
    "os-app-ios_news-subscription-decision": {
        "type": "os-app",
        "domain": DOMAIN_SOFTWARE,
        "tags": [
            "apple news",
            "News+",
            "subscription conversion",
            "Get Started",
            "features and pricing",
            "offer page browse",
        ],
    },
    "os-app-macos_stocks-mu-sentiment": {
        "type": "os-app",
        "domain": DOMAIN_FINANCE,
        "tags": [
            "stocks",
            "investment sentiment",
            "chart analysis",
            "news reading",
            "buy sell hold",
        ],
    },
    "survey_annual-checkup-habits": {
        "type": "survey",
        "domain": DOMAIN_HEALTHCARE,
        "tags": [
            "annual",
            "checkup",
            "habits",
        ],
    },
    "survey_price-sensitivity-hasbro-gaming-candy-land": {
        "type": "survey",
        "domain": DOMAIN_COMMERCE,
        "tags": [
            "price sensitivity",
            "toys and games",
            "retail",
            "product perturbation",
        ],
    },
    "web_mit-ocw-course-choice": {
        "type": "web",
        "domain": DOMAIN_EDUCATION,
        "tags": [
            "mit opencourseware",
            "course choice",
            "self-directed learning",
            "persona-sensitive comparison",
            "playwright dom browsing",
        ],
    },
    "web_notion-plan-comparison": {
        "type": "web",
        "domain": DOMAIN_SOFTWARE,
        "tags": [
            "notion",
            "workspace software",
            "pricing plan comparison",
            "personal and organization context",
            "budget sensitivity",
            "persona-sensitive comparison",
            "playwright dom browsing",
        ],
    },
}

PERSONA_BENCH_TASK_METADATA: dict[str, dict[str, object]] = {
    "example-survey_product-feedback": {
        "type": "survey",
        "domain": DOMAIN_SOFTWARE,
        "bench_dim_index": 47,
        "bench_dim_id": "economic_motivation",
        "tags": [
            "ClearQueue",
            "product concept",
            "subscription pricing",
            "tier selection",
            "spending posture",
        ],
    },
}

# Backward-compatible alias used by persona bench tests and grounding helpers.
EXAMPLE_TASK_METADATA = PERSONA_BENCH_TASK_METADATA


def _bench_dim_index(spec: dict[str, object]) -> int | None:
    raw = spec.get("bench_dim_index")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _example_slug(dirname: str) -> str:
    slug = dirname.replace("_", "-")
    if slug.startswith("example-"):
        slug = slug[len("example-") :]
    return slug


def application_harbor_name(dirname: str) -> str:
    """Harbor registry name for an application/tasks/<dirname> folder."""
    return f"matraix/application-{_example_slug(dirname)}"


def persona_bench_harbor_name(
    dirname: str, *, bench_dim_index: int | None = None
) -> str:
    """Harbor registry name for a legacy persona benchmark task folder."""
    slug = _example_slug(dirname)
    if bench_dim_index is not None:
        return f"personabench/persona-bench-dim-{bench_dim_index:03d}-{slug}"
    return f"personabench/persona-bench-{slug}"


def build_application_task_toml_dict(dirname: str, *, difficulty: str = "easy") -> dict:
    """Build task.toml content from ``task_catalog`` for an application task."""
    if dirname not in APPLICATION_TASK_METADATA:
        raise KeyError(
            f"No catalog entry for {dirname!r}; add it to APPLICATION_TASK_METADATA first"
        )
    data: dict = {
        "version": "1.0",
        "artifacts": ["/app/output"],
        "task": {"name": application_harbor_name(dirname)},
        "metadata": {"difficulty": difficulty},
        "verifier": {"timeout_sec": 120.0},
        "agent": {"timeout_sec": 600.0},
        "environment": {
            "build_timeout_sec": 600.0,
            "cpus": 1,
            "memory_mb": 2048,
            "storage_mb": 10240,
            "gpus": 0,
        },
    }
    apply_task_metadata(data, dirname, APPLICATION_TASK_METADATA)
    return data


def build_persona_task_toml_dict(dirname: str, *, difficulty: str = "easy") -> dict:
    """Build task.toml content from ``task_catalog`` for *dirname*."""
    if dirname not in PERSONA_BENCH_TASK_METADATA:
        raise KeyError(
            f"No catalog entry for {dirname!r}; add it to PERSONA_BENCH_TASK_METADATA first"
        )
    spec = PERSONA_BENCH_TASK_METADATA[dirname]
    bench_dim_index = _bench_dim_index(spec)
    data: dict = {
        "version": "1.0",
        "artifacts": ["/app/output"],
        "task": {
            "name": persona_bench_harbor_name(dirname, bench_dim_index=bench_dim_index)
        },
        "metadata": {"difficulty": difficulty},
        "verifier": {"timeout_sec": 120.0},
        "agent": {"timeout_sec": 600.0},
        "environment": {
            "build_timeout_sec": 600.0,
            "cpus": 1,
            "memory_mb": 2048,
            "storage_mb": 10240,
            "gpus": 0,
        },
    }
    apply_task_metadata(data, dirname, PERSONA_BENCH_TASK_METADATA)
    return data


def apply_task_metadata(
    data: dict,
    dirname: str,
    catalog: dict[str, dict[str, object]],
) -> None:
    """Merge catalog metadata into a parsed task.toml dict."""
    spec = catalog.get(dirname)
    if spec is None:
        return
    task = data.setdefault("task", {})
    task.pop("keywords", None)

    meta = data.setdefault("metadata", {})
    meta.pop("category", None)
    extra = {
        k: v
        for k, v in meta.items()
        if k not in {"difficulty", "type", "domain", "tags", "bench_dim_index"}
    }
    ordered: dict[str, object] = {
        "difficulty": meta.get("difficulty", "easy"),
        "type": spec["type"],
        "domain": spec["domain"],
        "tags": _as_str_list(spec.get("tags")),
    }
    ordered.update(extra)
    data["metadata"] = ordered


def task_dirname_from_harbor_path(task_path: str) -> str:
    """Return the example task directory name from a Harbor task path."""
    name = task_path.rstrip("/").split("/")[-1]
    if not name.startswith("example-"):
        raise ValueError(f"Expected an example task path, got {task_path!r}")
    return name


def get_task_catalog_entry(task_path: str) -> dict[str, object] | None:
    dirname = task_dirname_from_harbor_path(task_path)
    spec = PERSONA_BENCH_TASK_METADATA.get(dirname)
    return dict(spec) if spec is not None else None


def resolve_task_dir(task_path: str, *, repo_root: Path | None = None) -> Path:
    """Resolve a Harbor task path to an on-disk task directory."""
    path = Path(task_path)
    if path.is_dir():
        return path
    root = repo_root if repo_root is not None else Path.cwd()
    return root / task_path


def grounding_toml_path(task_path: str, *, repo_root: Path | None = None) -> Path:
    return resolve_task_dir(task_path, repo_root=repo_root) / "grounding.toml"


def load_grounding_toml(
    task_path: str, *, repo_root: Path | None = None
) -> dict[str, object] | None:
    """Load ``grounding.toml`` from a persona bench task directory, if present."""
    path = grounding_toml_path(task_path, repo_root=repo_root)
    if not path.is_file():
        return None
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a TOML table at root")
    probe = raw.get("probe_dimension")
    if not probe:
        raise ValueError(f"{path}: missing probe_dimension")
    confounders = raw.get("confounders")
    if confounders is not None and not isinstance(confounders, dict):
        raise ValueError(f"{path}: confounders must be a table")
    return {
        "probe_dimension": str(probe),
        "confounders": dict(confounders) if isinstance(confounders, dict) else {},
    }


def get_task_grounding_spec(
    task_path: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, object] | None:
    """Return grounding config from ``<task>/grounding.toml``, else catalog fallback."""
    from_task = load_grounding_toml(task_path, repo_root=repo_root)
    if from_task is not None:
        return from_task
    entry = get_task_catalog_entry(task_path)
    if entry is None:
        return None
    grounding = entry.get("grounding")
    if not isinstance(grounding, dict):
        return None
    return {str(key): value for key, value in grounding.items()}


def confounder_values_from_grounding(
    grounding: dict[str, object],
) -> dict[str, str]:
    """Extract dimension_id → fixed value from catalog confounder entries."""
    raw = grounding.get("confounders")
    if not isinstance(raw, dict):
        return {}
    values: dict[str, str] = {}
    for dim_id, entry in raw.items():
        if isinstance(entry, str):
            values[str(dim_id)] = entry
            continue
        if isinstance(entry, dict):
            entry_dict = cast(dict[str, Any], entry)
            value = entry_dict.get("value")
            if value is not None:
                values[str(dim_id)] = str(value)
    return values


def probe_dimension_from_grounding(grounding: dict[str, object]) -> str | None:
    probe = grounding.get("probe_dimension")
    return str(probe) if probe else None
