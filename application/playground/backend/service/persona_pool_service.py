"""Persona pool catalog and sampling for Harbor job launch."""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import yaml
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from matraix.persona_dimension_catalog import values_for_dimension
from matraix.persona_generator import (
    GENERATE_COUNT_MAX,
    MAX_FILTER_STRATA,
    clone_contrast_personas,
    overlay_dimensions_from_manifest,
    resolve_contrast_overlay,
    validate_contrast_stamps_against_dag,
)
from matraix.persona_job import (
    _stratify_bucket_key,
    load_manifest,
    sample_personas,
    sample_personas_stratified,
)

from backend.service.persona_sampling_alloc import (
    sample_by_portions_from_buckets,
    sample_proportional_from_buckets,
)

PERSONA_CARD_DIMENSIONS = (
    "age_bracket",
    "region",
    "domain",
    "intent",
    "life_stage",
    "source",
)

DEFAULT_PERSONA_POOL = "persona/datasets/matraix-persona-dev-sample"
DATASETS_DIR = "persona/datasets"
COHORTS_DIR = "persona/datasets/saved-cohorts"
# Top-level dirs under persona/datasets that are not selectable pools.
_DATASETS_SKIP_TOP_LEVEL = frozenset(
    {
        "_generated",
        "_sampled",
        "cohorts",  # legacy Save-cohort root; superseded by saved-cohorts
        "saved-cohorts",
        "matraix-persona-1m",
    }
)
# Names that cannot be used when saving a pool as a named dataset.
_RESERVED_DATASET_SLUGS = frozenset(
    {
        "_generated",
        "_sampled",
        "cohorts",
        "saved-cohorts",
        "matraix-persona-1m",
        "matraix-persona-dev-sample",
    }
)
DIMENSION_CATEGORIES_PATH = "persona/schema/dimension_categories.json"
DIMENSION_LABELS_DIR = "persona/schema/labels"
_LABEL_LOCALE_RE = re.compile(r"^[A-Za-z0-9-]{1,32}$")
# UI keeps a full personaId list only at or below this size; larger cohorts are ref-based.
PERSONA_UI_ID_LIST_MAX = 100
PERSONA_CARD_PREVIEW_DEFAULT = 32
GENERATED_POOL_PREFIX = "generated-persona-dev"
_GENERATED_RUN_TS = re.compile(r"^(.*)-(\d{8})-(\d{6})(?:-\d+)?$")
CohortKind = Literal["recipe", "frozen"]


def coverage_recovery_hint(*, task_path: str | None = None) -> str:
    """Hint when a dataset cannot satisfy the current (task) filters."""
    synthesize = (
        " With Task default persona strategy on, you can also Synthesize to fill this task."
        if task_path
        else ""
    )
    return (
        "Not enough matching personas in this dataset for the current filters. "
        "Consider switching Dataset to matraix-persona-1m for fuller coverage."
        + synthesize
        + " Or widen filters / sources, or use a saved cohort that already has enough matches."
    )


def with_coverage_hint(message: str, *, task_path: str | None = None) -> str:
    text = (message or "").strip()
    if not text:
        return text
    if "matraix-persona-1m" in text:
        return text
    return f"{text}\n\n{coverage_recovery_hint(task_path=task_path)}"


def _normalize_allocation(
    allocation: str | None,
    *,
    sample_size_per_value_group: int | None,
) -> str | None:
    """Return perCell | proportional | equalTotal | None (non-stratified)."""
    text = str(allocation or "").strip()
    if text in {"per_cell", "per-cell"}:
        text = "perCell"
    if text in {"equal_total", "equal-total"}:
        text = "equalTotal"
    if text in {"perCell", "proportional", "equalTotal"}:
        return text
    if isinstance(sample_size_per_value_group, int) and sample_size_per_value_group >= 1:
        return "perCell"
    return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cohort_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("cohort id must not be empty")
    return slug


def _overlay_from_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in overlay_dimensions_from_manifest(manifest):
        dim_id = str(row.get("id") or "").strip()
        values = [str(value) for value in (row.get("values") or []) if str(value).strip()]
        if not dim_id or not values:
            continue
        out.append(
            {
                "id": dim_id,
                "label": str(row.get("label") or dim_id).strip(),
                "values": values,
            }
        )
    return out


def _generated_run_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def _generated_pool_folder(kind_slug: str, datasets_root: Path) -> str:
    """``generated-persona-dev-<kind>-YYYYMMDD-HHMMSS`` so runs do not overwrite."""
    stamp = _generated_run_stamp()
    base = f"{GENERATED_POOL_PREFIX}-{kind_slug}-{stamp}"
    folder = base
    n = 2
    while (datasets_root / folder).exists():
        folder = f"{base}-{n}"
        n += 1
    return folder


def _generated_pool_label(folder: str, path: Path | None = None) -> str:
    """``Contrast shared · 2026-08-23 19:28:47`` — from the folder name, else mtime."""
    prefix = f"{GENERATED_POOL_PREFIX}-"
    if not folder.startswith(prefix):
        return folder
    rest = folder[len(prefix):]
    match = _GENERATED_RUN_TS.match(rest)
    if match:
        kind, day, tod = match.group(1), match.group(2), match.group(3)
        stamp = f"{day[:4]}-{day[4:6]}-{day[6:]} {tod[:2]}:{tod[2:4]}:{tod[4:]}"
        return f"{_humanize_generated_kind(kind)} · {stamp}"
    when = None
    if path is not None:
        try:
            when = (
                datetime.fromtimestamp(path.stat().st_mtime)
                .astimezone()
                .strftime("%Y-%m-%d %H:%M")
            )
        except OSError:
            when = None
    if when:
        return f"{_humanize_generated_kind(rest)} · {when}"
    return folder


def _humanize_generated_kind(kind: str) -> str:
    text = str(kind or "").strip()
    if not text:
        return text
    if text.startswith("contrast-"):
        return f"Contrast · {text[len('contrast-'):]}"
    return text


def _contrast_clone_label(folder: str, resolved: list[dict[str, Any]]) -> str:
    """Dropdown label: ``Contrast · Brand=Low · 2026-08-24 03:23:25``."""
    bits = [
        f"{row.get('label') or row.get('id')}={row.get('value')}"
        for row in resolved
        if row.get("value")
    ]
    stamp = None
    prefix = f"{GENERATED_POOL_PREFIX}-"
    if folder.startswith(prefix):
        match = _GENERATED_RUN_TS.match(folder[len(prefix):])
        if match:
            day, tod = match.group(2), match.group(3)
            stamp = f"{day[:4]}-{day[4:6]}-{day[6:]} {tod[:2]}:{tod[2:4]}:{tod[4:]}"
    head = f"Contrast · {', '.join(bits)}" if bits else "Contrast"
    return f"{head} · {stamp}" if stamp else head


def _sampled_cohort_pool(parent_pool: str, digest: str) -> str:
    """``<source-dataset>/cohorts/cohort-<digest>`` so the parent pool is visible."""
    pool = (parent_pool or DEFAULT_PERSONA_POOL).strip().rstrip("/")
    marker = "/cohorts/cohort-"
    if marker in pool:
        pool = pool.split(marker, 1)[0]
    return f"{pool}/cohorts/cohort-{digest}"


def _repo_root() -> Path:
    from playground.harbor.playground import _repo_root as harbor_root

    return harbor_root()



def _resolve_persona_yaml_path(
    repo_root: Path,
    entry: dict[str, Any],
    persona_id: str,
    pool_dir: Path,
) -> Path:
    candidates: list[Path] = []
    rel_path = str(entry.get("path") or "").strip()
    if rel_path:
        path = Path(rel_path)
        candidates.append(path if path.is_absolute() else repo_root / rel_path)
    pid = persona_id.strip()
    candidates.append(pool_dir / "persona_{}.yaml".format(pid))
    if pid.isdigit():
        candidates.append(pool_dir / "persona_{}.yaml".format(pid.zfill(4)))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0] if candidates else pool_dir / "persona_{}.yaml".format(pid)


def _persona_profile_markdown(
    *,
    persona_id: str,
    source: str,
    path: str,
    yaml_text: str,
) -> str:
    lines = ["**Persona ID:** `{}`".format(persona_id)]
    if source:
        lines.append("**Source:** {}".format(source))
    if path:
        lines.append("**Path:** `{}`".format(path))
    if yaml_text.strip():
        lines.extend(["", "```yaml", yaml_text.rstrip(), "```"])
    return "\n".join(lines)


# Lazy-cached Treiver for NL → attribute matching (regex stage; offline).
_treiver_singleton: Any = None


def _get_treiver() -> Any:
    global _treiver_singleton
    if _treiver_singleton is None:
        from persona.extraction import Treiver

        _treiver_singleton = Treiver()
    return _treiver_singleton


@dataclass
class PersonaPoolService:
    repo_root: Path

    @classmethod
    def from_repo(cls, *, repo_root: Path | None = None) -> "PersonaPoolService":
        return cls(repo_root=Path(repo_root) if repo_root is not None else _repo_root())

    def _pool_dir(self, persona_pool: str) -> Path:
        root = Path(os.path.normpath(self.repo_root))
        pool_dir = Path(os.path.normpath(root / persona_pool))
        try:
            pool_dir.relative_to(root)
        except ValueError:
            raise ValueError(
                "persona pool must be inside the repo: {}".format(persona_pool)
            ) from None
        return pool_dir

    def match_attributes(
        self,
        prompt: str,
        *,
        search_mode: str = "keyword",
        locale: str | None = None,
        persona_model: str | None = None,
    ) -> dict[str, Any]:
        """Map free-text / NL phrase to selectable catalog attributes (Treiver).

        ``search_mode``:
        * ``keyword`` — regex only (default, offline)
        * ``keyword_and_embed`` — regex ∪ local embedding value picks
        * ``keyword_and_embed_and_llm`` — keyword ∪ embed candidates + LLM judge (``persona_model``)
        """
        from backend.service.config import persona_model as default_persona_model

        text = (prompt or "").strip()
        mode = (search_mode or "keyword").strip().lower()
        if mode not in {"keyword", "keyword_and_embed", "keyword_and_embed_and_llm"}:
            mode = "keyword"

        empty = {
            "prompt": text if text else "",
            "attributes": [],
            "usedLlm": False,
            "searchMode": mode,
            "judgeModel": None,
            "candidateCount": 0,
            "suggestedDimensionIds": [],
            "embedFallback": False,
        }
        if not text:
            return empty

        value_aliases, topic_aliases, label_overlays = self._label_pack_match_assets(
            locale
        )
        treiver = _get_treiver()
        resolved_model = (persona_model or "").strip() or default_persona_model()
        use_embed = mode in {"keyword_and_embed", "keyword_and_embed_and_llm"}
        use_judge = mode == "keyword_and_embed_and_llm"
        result = treiver.match(
            text,
            use_llm=use_judge,
            use_embed=use_embed,
            value_aliases=value_aliases or None,
            topic_aliases=topic_aliases or None,
            label_overlays=label_overlays or None,
            locale_cache_key=(locale or "").strip() or None,
            persona_model=resolved_model if use_judge else None,
        )
        embed_fallback = False
        if use_embed:
            try:
                embedder = treiver._embed_retriever(
                    label_overlays=label_overlays or None,
                    cache_key=(locale or "").strip() or None,
                )
                embedder._ensure_matrix()
                embed_fallback = bool(embedder._fallback)
            except Exception:  # noqa: BLE001
                embed_fallback = True
        attributes: list[dict[str, Any]] = []
        for attr in result.attributes:
            dim = treiver.schema.get(attr.dimension_id)
            label = dim.label if dim and dim.label else attr.dimension_id
            pack_label = self._label_pack_dim_label(locale, attr.dimension_id)
            pack_value = self._label_pack_value_label(
                locale, attr.dimension_id, attr.value
            )
            attributes.append(
                {
                    "dimensionId": attr.dimension_id,
                    "label": pack_label or label,
                    "value": attr.value,
                    "valueLabel": pack_value or attr.value,
                    "evidence": attr.evidence,
                    "method": attr.method,
                    "confidence": float(attr.confidence),
                }
            )
        return {
            "prompt": text,
            "attributes": attributes,
            "usedLlm": bool(result.used_llm),
            "searchMode": mode,
            "judgeModel": resolved_model if use_judge else None,
            "candidateCount": len(result.candidate_dimension_ids),
            "suggestedDimensionIds": list(result.candidate_dimension_ids),
            "embedFallback": embed_fallback,
        }

    def _label_pack_path(self, locale: str | None) -> Path | None:
        token = (locale or "").strip()
        if not token or not _LABEL_LOCALE_RE.match(token):
            return None
        path = self.repo_root / DIMENSION_LABELS_DIR / f"dimensions.labels.{token}.json"
        return path if path.is_file() else None

    def _label_pack_dim_label(self, locale: str | None, dim_id: str) -> str | None:
        path = self._label_pack_path(locale)
        if path is None:
            return None
        try:
            payload = self._read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        entry = (payload.get("dimensions") or {}).get(dim_id)
        if not isinstance(entry, dict):
            return None
        label = entry.get("label")
        return label.strip() if isinstance(label, str) and label.strip() else None

    def _label_pack_value_label(
        self, locale: str | None, dim_id: str, value: str
    ) -> str | None:
        path = self._label_pack_path(locale)
        if path is None:
            return None
        try:
            payload = self._read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        entry = (payload.get("dimensions") or {}).get(dim_id)
        if not isinstance(entry, dict):
            return None
        values = entry.get("values")
        if not isinstance(values, dict):
            return None
        translated = values.get(value)
        return (
            translated.strip()
            if isinstance(translated, str) and translated.strip()
            else None
        )

    def _label_pack_match_assets(
        self, locale: str | None
    ) -> tuple[
        dict[tuple[str, str], tuple[str, ...]],
        dict[str, tuple[str, ...]],
        dict[str, dict],
    ]:
        """Build Treiver regex + embed assets from a locale dimension label pack."""
        path = self._label_pack_path(locale)
        if path is None:
            return {}, {}, {}
        try:
            payload = self._read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return {}, {}, {}
        dimensions = payload.get("dimensions")
        if not isinstance(dimensions, dict):
            return {}, {}, {}

        value_aliases: dict[tuple[str, str], list[str]] = {}
        topic_aliases: dict[str, list[str]] = {}
        label_overlays: dict[str, dict] = {}
        for dim_id, entry in dimensions.items():
            if not isinstance(dim_id, str) or not isinstance(entry, dict):
                continue
            overlay_entry: dict[str, Any] = {}
            label = entry.get("label")
            if isinstance(label, str) and label.strip():
                overlay_entry["label"] = label.strip()
                topics = topic_aliases.setdefault(dim_id, [])
                text = label.strip()
                topics.append(text)
                # ``Familiarity: ML`` / ``精通：机器学习`` → topic after last separator.
                for sep in (":", "："):
                    if sep in text:
                        topic = text.rsplit(sep, 1)[-1].strip()
                        if topic and topic not in topics:
                            topics.append(topic)
                        break
            values = entry.get("values")
            if isinstance(values, dict):
                clean_values: dict[str, str] = {}
                for en_value, translated in values.items():
                    if not isinstance(en_value, str) or not isinstance(translated, str):
                        continue
                    form = translated.strip()
                    if not form:
                        continue
                    clean_values[en_value] = form
                    if form == en_value:
                        continue
                    bucket = value_aliases.setdefault((dim_id, en_value), [])
                    if form not in bucket:
                        bucket.append(form)
                if clean_values:
                    overlay_entry["values"] = clean_values
            if overlay_entry:
                label_overlays[dim_id] = overlay_entry

        return (
            {key: tuple(forms) for key, forms in value_aliases.items()},
            {key: tuple(forms) for key, forms in topic_aliases.items()},
            label_overlays,
        )

    def _label_pack_regex_aliases(
        self, locale: str | None
    ) -> tuple[
        dict[tuple[str, str], tuple[str, ...]],
        dict[str, tuple[str, ...]],
    ]:
        value_aliases, topic_aliases, _overlays = self._label_pack_match_assets(locale)
        return value_aliases, topic_aliases

    def _read_json(self, path: Path) -> dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("{} must contain a JSON object".format(path.name))
        return payload

    def load_manifest_summary(self, persona_pool: str = DEFAULT_PERSONA_POOL) -> dict[str, Any]:
        pool_dir = self._pool_dir(persona_pool)
        manifest_path = pool_dir / "manifest.json"
        if not manifest_path.is_file():
            entries = load_manifest(pool_dir, repo_root=self.repo_root)
            return {
                "pool": persona_pool,
                "count": len(entries),
                "smokePersonaId": None,
                "sourceCounts": {},
                "schemaVersion": None,
                "dimensionCategoriesPath": DIMENSION_CATEGORIES_PATH,
                "overlayDimensions": [],
            }
        manifest = self._read_json(manifest_path)
        return {
            "pool": persona_pool,
            "count": int(manifest.get("count") or len(manifest.get("personas") or [])),
            "smokePersonaId": manifest.get("smoke_persona_id"),
            "sourceCounts": dict(manifest.get("source_counts") or {}),
            "schemaVersion": manifest.get("schema_version"),
            "dimensionCategoriesPath": str(
                manifest.get("dimension_categories") or DIMENSION_CATEGORIES_PATH
            ),
            "overlayDimensions": _overlay_from_manifest(manifest),
        }

    def load_dimension_categories(
        self, *, path: str | None = None
    ) -> dict[str, Any]:
        rel = path or DIMENSION_CATEGORIES_PATH
        categories_path = Path(rel)
        if not categories_path.is_absolute():
            categories_path = self.repo_root / rel
        if not categories_path.is_file():
            return {
                "schemaVersion": "1.0",
                "personaSources": [],
                "devProfile": {"dimensionCount": None, "groups": []},
            }
        payload = self._read_json(categories_path)
        dev_profile = payload.get("devProfile")
        groups: list[dict[str, Any]] = []
        if isinstance(dev_profile, dict) and isinstance(dev_profile.get("groups"), list):
            for group in dev_profile["groups"]:
                if not isinstance(group, dict):
                    continue
                dimension_ids = list(group.get("dimensionIds") or [])
                dimensions = []
                for dim_id in dimension_ids:
                    dimensions.append(
                        {
                            "id": dim_id,
                            "values": values_for_dimension(str(dim_id)),
                        }
                    )
                groups.append(
                    {
                        "id": str(group.get("id") or ""),
                        "label": str(group.get("label") or ""),
                        "dimensionIds": dimension_ids,
                        "dimensions": dimensions,
                    }
                )
        return {
            "schemaVersion": payload.get("schemaVersion"),
            "personaSources": list(payload.get("personaSources") or []),
            "devProfile": {
                "dimensionCount": (
                    int(dev_profile.get("dimensionCount"))
                    if isinstance(dev_profile, dict) and dev_profile.get("dimensionCount")
                    else None
                ),
                "groups": groups,
            },
        }

    def get_catalog(self, persona_pool: str = DEFAULT_PERSONA_POOL) -> dict[str, Any]:
        from backend.service.persona_1m_pool import (
            PRODUCTION_1M_COUNT,
            PRODUCTION_1M_POOL,
            is_production_1m_root,
            production_1m_available,
        )
        from backend.service.persona_taxonomy import (
            build_production_filter_categories,
            prepend_overlay_group,
        )

        if is_production_1m_root(persona_pool):
            source_counts = {
                "wiki": 323438,
                "amazon": 97915,
                "stackoverflow": 113120,
                "prism": 1487,
                "gss": 63532,
                "real_human_survey": 508,
                "synthetic": 400000,
            }
            categories = build_production_filter_categories(
                repo_root=self.repo_root,
                persona_sources=list(source_counts.keys()),
            )
            return {
                "pool": PRODUCTION_1M_POOL,
                "count": PRODUCTION_1M_COUNT if production_1m_available(self.repo_root) else 0,
                "smokePersonaId": None,
                "sourceCounts": source_counts,
                "schemaVersion": "1.0",
                "dimensionCategoriesPath": "persona/schema/dimensions.json",
                "dimensionCategories": categories,
                "kind": "production",
            }

        summary = self.load_manifest_summary(persona_pool)
        source_counts = dict(summary.get("sourceCounts") or {})
        persona_sources = list(source_counts.keys())
        if not persona_sources:
            # Fall back to legacy category sources when the pool has no counts.
            legacy = self.load_dimension_categories(path=DIMENSION_CATEGORIES_PATH)
            persona_sources = list(legacy.get("personaSources") or [])
        # Prefer the checked-in dimensions catalog so local YAML pools do not
        # require the 1M release mirror to be present.
        dimensions_schema = self.repo_root / "persona/schema/dimensions.json"
        categories = build_production_filter_categories(
            repo_root=self.repo_root,
            schema_path=dimensions_schema if dimensions_schema.is_file() else None,
            persona_sources=persona_sources,
        )
        overlay = list(summary.get("overlayDimensions") or [])
        if overlay:
            categories = prepend_overlay_group(categories, overlay)
        return {
            **summary,
            "dimensionCategoriesPath": "persona/schema/dimensions.json",
            "dimensionCategories": categories,
        }

    def get_dimension_labels(self, locale: str) -> dict[str, Any]:
        """Display-label overlay for one locale (English fallback when absent).

        Packs live in ``persona/schema/labels/dimensions.labels.<locale>.json``
        and only carry translated labels/values keyed by canonical English
        ids — they never replace the catalog served by :meth:`get_catalog`.
        """
        token = (locale or "").strip()
        if not _LABEL_LOCALE_RE.match(token):
            raise ValueError(f"invalid locale token: {locale!r}")
        path = self.repo_root / DIMENSION_LABELS_DIR / f"dimensions.labels.{token}.json"
        if not path.is_file():
            return {
                "locale": token,
                "available": False,
                "reviewStatus": None,
                "dimensions": {},
                "taxonomy": {},
            }
        payload = self._read_json(path)
        dimensions = payload.get("dimensions")
        taxonomy = payload.get("taxonomy")
        return {
            "locale": token,
            "available": True,
            "reviewStatus": payload.get("reviewStatus"),
            "dimensions": dimensions if isinstance(dimensions, dict) else {},
            "taxonomy": taxonomy if isinstance(taxonomy, dict) else {},
        }

    def _is_persona_dataset_dir(self, path: Path) -> bool:
        if not path.is_dir():
            return False
        if (path / "manifest.json").is_file():
            return True
        return next(path.glob("persona_*.yaml"), None) is not None

    def _dataset_count_hint(self, path: Path) -> int:
        """Read pool size without loading multi‑MB manifests into memory."""
        manifest_path = path / "manifest.json"
        if manifest_path.is_file():
            try:
                size = manifest_path.stat().st_size
            except OSError:
                size = 0
            if 0 < size <= 2_000_000:
                try:
                    payload = self._read_json(manifest_path)
                    return int(
                        payload.get("count") or len(payload.get("personas") or [])
                    )
                except (OSError, ValueError, json.JSONDecodeError, TypeError):
                    pass
            else:
                # Large strategy pools put ``"count": N`` near the top.
                try:
                    with manifest_path.open("r", encoding="utf-8") as handle:
                        head = handle.read(8192)
                    match = re.search(r'"count"\s*:\s*(\d+)', head)
                    if match:
                        return int(match.group(1))
                except (OSError, ValueError):
                    pass
        try:
            return sum(1 for _ in path.glob("persona_*.yaml"))
        except OSError:
            return 0

    def _manifest_dataset_kind(self, path: Path) -> str | None:
        manifest_path = path / "manifest.json"
        if not manifest_path.is_file():
            return None
        try:
            raw = self._read_json(manifest_path)
        except Exception:  # noqa: BLE001
            return None
        kind = str(raw.get("kind") or "").strip()
        return kind or None

    def _dataset_entry(self, *, pool: str, label: str, kind: str, path: Path) -> dict[str, Any]:
        return {
            "pool": pool,
            "label": label,
            "kind": kind,
            "count": self._dataset_count_hint(path),
            "default": pool == DEFAULT_PERSONA_POOL,
        }

    def list_datasets(self) -> list[dict[str, Any]]:
        """Discover selectable persona pools under ``persona/datasets/``.

        Surfaces checked-in local pools, plus the production MatrAIx 1M pool.
        Launch caches (``<dataset>/cohorts/``) and leftover ``_generated`` dirs
        are omitted.
        """
        from backend.service.persona_1m_pool import (
            production_1m_available,
            production_dataset_entry,
        )

        datasets_root = self.repo_root / DATASETS_DIR
        by_pool: dict[str, dict[str, Any]] = {}

        if datasets_root.is_dir():
            for child in sorted(datasets_root.iterdir(), key=lambda p: p.name.lower()):
                if not child.is_dir() or child.name in _DATASETS_SKIP_TOP_LEVEL:
                    continue
                if not self._is_persona_dataset_dir(child):
                    continue
                pool = f"{DATASETS_DIR}/{child.name}"
                manifest_kind = self._manifest_dataset_kind(child)
                # Promote Save-as-dataset pools so the UI can default sampling to All.
                kind = (
                    "saved"
                    if manifest_kind == "saved-persona-dataset"
                    else "dataset"
                )
                label = (
                    _generated_pool_label(child.name, child)
                    if child.name.startswith(f"{GENERATED_POOL_PREFIX}-")
                    else child.name
                )
                by_pool[pool] = self._dataset_entry(
                    pool=pool, label=label, kind=kind, path=child
                )

            # Intentionally omit matraix-persona-1m/cohorts/* from Dataset.
            # Those dirs are launch caches from sampling the production release,
            # not user-facing sources (listing them next to the 1M root is confusing).

        if DEFAULT_PERSONA_POOL not in by_pool:
            by_pool[DEFAULT_PERSONA_POOL] = self._dataset_entry(
                pool=DEFAULT_PERSONA_POOL,
                label="matraix-persona-dev-sample",
                kind="dataset",
                path=self.repo_root / DEFAULT_PERSONA_POOL,
            )

        production = production_dataset_entry(
            available=production_1m_available(self.repo_root)
        )
        by_pool[production["pool"]] = production

        ordered = sorted(
            by_pool.values(),
            key=lambda item: (
                0 if item["default"] else
                1 if item.get("kind") == "production" else
                2 if item.get("kind") == "saved" else
                3 if item.get("kind") == "dataset" else
                4,
                str(item["label"]).lower(),
            ),
        )
        return ordered

    def save_pool_as_dataset(
        self,
        *,
        source_pool: str,
        name: str,
        description: str | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Promote a materialized pool (e.g. 1M cohort) to ``persona/datasets/<slug>/``.

        Copies ``persona_*.yaml`` (+ rewritten ``manifest.json``) so the pool
        appears in the Dataset dropdown and can be reused across tasks.
        """
        slug = _cohort_slug(name)
        if slug in _RESERVED_DATASET_SLUGS or slug.startswith("_"):
            raise ValueError(
                f"dataset name '{slug}' is reserved; choose a different name"
            )

        src_rel = (source_pool or "").strip().rstrip("/")
        if not src_rel:
            raise ValueError("source_pool is required")
        from backend.service.persona_1m_pool import is_production_1m_root

        if is_production_1m_root(src_rel) or src_rel.rstrip("/") == DEFAULT_PERSONA_POOL:
            raise ValueError(
                "Cannot save a full source dataset as a new dataset. "
                "Pull a cohort first, then save that cohort."
            )

        src_dir = self._pool_dir(src_rel)
        if not src_dir.is_dir():
            raise FileNotFoundError(f"source pool not found: {src_rel}")

        yaml_files = sorted(src_dir.glob("persona_*.yaml"))
        if not yaml_files:
            raise ValueError(f"source pool has no persona YAML files: {src_rel}")

        dest_rel = f"{DATASETS_DIR}/{slug}"
        dest_dir = self.repo_root / dest_rel
        if dest_dir.exists():
            if not overwrite:
                raise FileExistsError(
                    f"dataset already exists: {dest_rel} (pass overwrite=true to replace)"
                )
            if dest_dir.resolve() == src_dir.resolve():
                raise ValueError("source and destination are the same path")
            shutil.rmtree(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        source_counts: dict[str, int] = {}
        manifest_personas: list[dict[str, Any]] = []
        for yaml_path in yaml_files:
            dest_yaml = dest_dir / yaml_path.name
            shutil.copy2(yaml_path, dest_yaml)
            persona_id = yaml_path.stem.removeprefix("persona_")
            source = "unknown"
            card_dims: dict[str, str] = {}
            try:
                raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                raw = None
            if isinstance(raw, dict):
                persona_id = str(raw.get("persona_id") or persona_id)
                source = str(raw.get("source") or "unknown").strip() or "unknown"
                dims = raw.get("dimensions")
                if isinstance(dims, dict):
                    card_dims = {
                        key: str(dims[key])
                        for key in PERSONA_CARD_DIMENSIONS
                        if key != "source" and dims.get(key) is not None
                    }
            source_counts[source] = source_counts.get(source, 0) + 1
            manifest_personas.append(
                {
                    "persona_id": persona_id,
                    "path": f"{dest_rel}/{yaml_path.name}",
                    "source": source,
                    "dimensions": card_dims,
                }
            )

        parent_manifest: dict[str, Any] = {}
        src_manifest_path = src_dir / "manifest.json"
        if src_manifest_path.is_file():
            try:
                parent_manifest = self._read_json(src_manifest_path)
            except Exception:  # noqa: BLE001
                parent_manifest = {}

        manifest = {
            "kind": "saved-persona-dataset",
            "name": (name or slug).strip(),
            "description": (description or "").strip(),
            "count": len(manifest_personas),
            "seed": parent_manifest.get("seed"),
            "schema_version": str(parent_manifest.get("schema_version") or "1.0"),
            "smoke_persona_id": (
                manifest_personas[0]["persona_id"] if manifest_personas else None
            ),
            "source_counts": source_counts,
            "dimension_categories": str(
                parent_manifest.get("dimension_categories")
                or DIMENSION_CATEGORIES_PATH
            ),
            "created_at": _utc_now(),
            "source_pool": src_rel,
            "parent_pool": parent_manifest.get("parent_pool"),
            "hf_repo": parent_manifest.get("hf_repo"),
            "personas": manifest_personas,
        }
        overlay = _overlay_from_manifest(parent_manifest)
        if overlay:
            manifest["overlay_dimensions"] = overlay
        (dest_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return {
            "pool": dest_rel,
            "label": slug,
            "name": manifest["name"],
            "count": manifest["count"],
            "sourcePool": src_rel,
            "kind": "dataset",
        }

    def generate_synthetic_pool(
        self,
        *,
        count: int | None = None,
        seed: int = 42,
        dimension_filters: dict[str, str | list[str]] | None = None,
        stratify_fields: list[str] | None = None,
        allocation: str | None = None,
        per_cell: int | None = None,
        sample_size: int | None = None,
        marginals: dict[str, dict[str, float]] | None = None,
        overlay_dimensions: list[dict[str, Any]] | None = None,
        contrast: list[dict[str, Any]] | None = None,
        task_path: str | None = None,
        name: str | None = None,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Write a Full-DAG synthetic pool under ``persona/datasets/generated-persona-dev-*``.

        ``task_path`` loads that task's ``persona_strategy.json`` (one-time fill).
        Otherwise this is a custom Generation draw (plain ``count`` or stratified).
        ``overlay_dimensions`` are study attrs stamped after the Full-DAG sample.
        ``contrast`` writes extra stamped datasets from the first pool.

        ``on_progress`` receives NDJSON-friendly events::
            ``{"type":"progress","stage":...,"ratio":0..1,"label":...}``.
        """
        from matraix.persona_consistency import load_dev_dimension_ids
        from matraix.persona_generator import (
            apply_dimension_stamps,
            contrast_base_stamps,
            contrast_stamp_combinations,
            generate_synthetic_personas,
            normalize_generate_contrast,
            normalize_overlay_dimensions,
            write_persona_dataset,
        )

        def emit(
            stage: str,
            *,
            ratio: float,
            label: str,
            done: int | None = None,
            total: int | None = None,
            dataset_index: int | None = None,
            dataset_total: int | None = None,
            dataset_label: str | None = None,
        ) -> None:
            if on_progress is None:
                return
            payload: dict[str, Any] = {
                "type": "progress",
                "stage": stage,
                "ratio": max(0.0, min(1.0, float(ratio))),
                "label": label,
            }
            if done is not None:
                payload["done"] = int(done)
            if total is not None:
                payload["total"] = int(total)
            if dataset_index is not None:
                payload["datasetIndex"] = int(dataset_index)
            if dataset_total is not None:
                payload["datasetTotal"] = int(dataset_total)
            if dataset_label is not None:
                payload["datasetLabel"] = str(dataset_label)
            on_progress(payload)

        filters = self._filters_as_lists(self._normalize_dimension_filters(dimension_filters))
        fields = [
            str(field).removeprefix("dimensions.").strip()
            for field in (stratify_fields or [])
            if str(field).strip()
        ]
        alloc = str(allocation or "").strip() or None
        per_cell_n = per_cell if isinstance(per_cell, int) and per_cell >= 1 else None
        sample_n = sample_size if isinstance(sample_size, int) and sample_size >= 1 else None
        kind_slug = _cohort_slug(name) if name and str(name).strip() else None

        if task_path and str(task_path).strip():
            from backend.service.task_persona_strategy_service import (
                get_task_persona_strategy,
            )

            strategy = get_task_persona_strategy(task_path, repo_root=self.repo_root)
            if not strategy:
                raise ValueError(f"{task_path}: no persona_strategy.json")
            filters = {
                str(key): list(values)
                for key, values in (strategy.get("dimensionFilters") or {}).items()
                if isinstance(values, list) and values
            }
            if not filters:
                raise ValueError(f"{task_path}: persona_strategy.json has no dimensionFilters")
            sampling = strategy.get("sampling") if isinstance(strategy.get("sampling"), dict) else {}
            fields = [
                str(field).removeprefix("dimensions.").strip()
                for field in (sampling.get("fields") or [])
                if str(field).strip()
            ]
            alloc = str(sampling.get("allocation") or "").strip() or None
            per_cell_n = (
                sampling.get("perCell")
                if isinstance(sampling.get("perCell"), int)
                else None
            )
            # Request sampleSize is an explicit operator override; strategy is fallback.
            sample_n = (
                sample_n
                if sample_n is not None
                else (
                    sampling.get("sampleSize")
                    if isinstance(sampling.get("sampleSize"), int)
                    else None
                )
            )
            if marginals is None:
                strategy_portions = strategy.get("portions")
                if not isinstance(strategy_portions, dict) or not strategy_portions:
                    strategy_portions = (
                        sampling.get("portions")
                        if isinstance(sampling.get("portions"), dict)
                        else None
                    )
                if isinstance(strategy_portions, dict) and strategy_portions:
                    marginals = strategy_portions
            if isinstance(strategy.get("seed"), int):
                seed = int(strategy["seed"])
            task_slug = _cohort_slug(Path(str(task_path).strip()).name)
            kind_slug = kind_slug or f"strategy-{task_slug}"

            # Non-schema strategy filters are study attributes — auto-stamp overlays.
            # Skip when the schema catalog is absent (unit tests / ad-hoc roots)
            # so real schema dims are not treated as overlays.
            catalog = self.repo_root / "persona/schema/dimensions.json"
            if catalog.is_file():
                schema_ids = set(load_dev_dimension_ids(catalog_path=str(catalog)))
                overlay_in = list(overlay_dimensions or [])
                have_overlay = {str(row.get("id") or "").strip() for row in overlay_in}
                for dim_id, vals in filters.items():
                    if dim_id in schema_ids or dim_id in have_overlay or dim_id in fields:
                        continue
                    overlay_in.append({"id": dim_id, "label": dim_id, "values": list(vals)})
                    have_overlay.add(dim_id)
                if len(overlay_in) != len(overlay_dimensions or []):
                    overlay_dimensions = overlay_in
                    fields = [f for f in fields if f not in have_overlay]

        overlay_norm = normalize_overlay_dimensions(overlay_dimensions)
        contrast_plan: list[dict[str, Any]] = []
        filling_task = bool(task_path and str(task_path).strip())
        if contrast and not filling_task:
            catalog = self.repo_root / "persona/schema/dimensions.json"
            schema_ids = (
                set(load_dev_dimension_ids(catalog_path=str(catalog)))
                if catalog.is_file()
                else None
            )
            contrast_plan = normalize_generate_contrast(
                overlay_norm,
                contrast,
                schema_ids=schema_ids,
            )
            if contrast_plan:
                overlay_ids = {str(row["id"]) for row in overlay_norm}
                contrast_ids = {str(arm["id"]) for arm in contrast_plan}
                overlay_contrast_ids = contrast_ids & overlay_ids
                fields = [field for field in fields if field not in overlay_contrast_ids]
                if not fields:
                    remaining_catalog = [
                        key for key in filters if key not in overlay_ids
                    ]
                    if not remaining_catalog:
                        if not (isinstance(count, int) and count >= 1):
                            if per_cell_n:
                                count = per_cell_n
                            elif sample_n:
                                count = sample_n
                        per_cell_n = None
                        sample_n = None
                        alloc = None

        # Declared target shares generate to that mix (exact marginals), not
        # uniform per-cell ceil that overshoots and ignores the mix.
        if marginals and alloc == "proportional":
            alloc = "independentMarginal"

        combos = contrast_stamp_combinations(contrast_plan)
        dataset_total = 1 + len(combos)
        emit(
            "prepare",
            ratio=0.02,
            label="Sampling Full DAG…",
            dataset_index=0,
            dataset_total=dataset_total,
            dataset_label="Sampling…",
        )
        generated = generate_synthetic_personas(
            count=count,
            seed=seed,
            dimension_filters=filters,
            stratify_fields=fields,
            allocation=alloc,
            per_cell=per_cell_n,
            sample_size=sample_n,
            marginals=marginals,
            overlay_dimensions=overlay_norm or overlay_dimensions,
            catalog_path=self.repo_root / "persona/schema/dimensions.json",
            force_pin=filling_task,
        )
        personas = generated.personas
        overlay = generated.overlay
        pool_count = generated.folder_count

        base_stamps = contrast_base_stamps(contrast_plan)
        base_resolved: list[dict[str, Any]] = []
        if base_stamps:
            catalog = self.repo_root / "persona/schema/dimensions.json"
            schema_ids = (
                set(load_dev_dimension_ids(catalog_path=str(catalog)))
                if catalog.is_file()
                else None
            )
            for dim_id, text in base_stamps.items():
                dim = resolve_contrast_overlay(
                    overlay,
                    dim_id,
                    text,
                    schema_ids=schema_ids,
                )
                base_resolved.append(
                    {
                        "id": str(dim["id"]),
                        "label": dim.get("label") or dim_id,
                        "value": str(text).strip(),
                    }
                )
            stamp_map = {row["id"]: row["value"] for row in base_resolved}
            validate_contrast_stamps_against_dag(
                personas,
                stamp_map,
                schema_ids=schema_ids,
            )
            apply_dimension_stamps(personas, stamp_map)

        if not kind_slug:
            if base_resolved:
                slug_parts = [
                    f"{_cohort_slug(row['id'])}-{_cohort_slug(row['value'])}"
                    for row in base_resolved
                ]
                kind_slug = f"contrast-{'-'.join(slug_parts)}"
            else:
                kind_slug = str(pool_count if pool_count > 0 else "stratified")
        folder = _generated_pool_folder(kind_slug, self.repo_root / DATASETS_DIR)
        rel_pool = f"{DATASETS_DIR}/{folder}"
        out_dir = self.repo_root / rel_pool
        if out_dir.exists():
            for stale in out_dir.glob("persona_*.yaml"):
                stale.unlink()

        combos = contrast_stamp_combinations(contrast_plan)
        parent_label = (
            _contrast_clone_label(folder, base_resolved)
            if base_resolved
            else _generated_pool_label(folder)
        )
        parent_progress_label = (
            "Contrast · "
            + ", ".join(f"{row['label']}={row['value']}" for row in base_resolved)
            if base_resolved
            else parent_label.split(" · ")[0]
        )

        def _emit_dataset(
            stage: str,
            *,
            dataset_index: int,
            dataset_label: str,
            ratio: float,
            label: str,
            done: int | None = None,
            total: int | None = None,
        ) -> None:
            emit(
                stage,
                ratio=ratio,
                label=label,
                done=done,
                total=total,
                dataset_index=dataset_index,
                dataset_total=dataset_total,
                dataset_label=dataset_label,
            )

        _emit_dataset(
            "sample",
            dataset_index=0,
            dataset_label=parent_progress_label,
            ratio=0.12,
            label=f"Sampled {len(personas)} personas",
            done=len(personas),
            total=len(personas),
        )

        def _write_progress_for(
            dataset_index: int,
            dataset_label: str,
        ) -> Callable[[str, dict[str, Any]], None]:
            def _write_progress(stage: str, payload: dict[str, Any]) -> None:
                if stage == "write":
                    done = int(payload.get("done") or 0)
                    total = max(1, int(payload.get("total") or 1))
                    ratio = 0.15 + 0.75 * (done / total)
                    _emit_dataset(
                        "write",
                        dataset_index=dataset_index,
                        dataset_label=dataset_label,
                        ratio=ratio,
                        label=str(payload.get("label") or "Writing personas…"),
                        done=done,
                        total=total,
                    )
                    return
                if stage == "manifest":
                    _emit_dataset(
                        "manifest",
                        dataset_index=dataset_index,
                        dataset_label=dataset_label,
                        ratio=0.95,
                        label=str(payload.get("label") or "Writing manifest…"),
                    )

            return _write_progress

        _emit_dataset(
            "write",
            dataset_index=0,
            dataset_label=parent_progress_label,
            ratio=0.15,
            label="Writing personas…",
        )
        manifest = write_persona_dataset(
            out_dir=out_dir,
            personas=personas,
            repo_root=self.repo_root,
            kind=folder,
            seed=seed,
            smoke_persona_id="0042",
            overlay_dimensions=overlay or None,
            on_progress=(
                _write_progress_for(0, parent_progress_label)
                if on_progress is not None
                else None
            ),
        )
        _emit_dataset(
            "done",
            dataset_index=0,
            dataset_label=parent_progress_label,
            ratio=1.0,
            label=f"Wrote {int(manifest['count'])} personas",
        )

        contrast_pools: list[dict[str, Any]] = []
        for combo_index, stamps in enumerate(combos):
            dataset_index = 1 + combo_index
            resolved_preview = [
                {
                    "id": key,
                    "label": next(
                        (
                            str(row.get("label") or key)
                            for row in overlay
                            if str(row.get("id")) == key
                        ),
                        key,
                    ),
                    "value": value,
                }
                for key, value in stamps.items()
            ]
            dataset_label = "Contrast · " + ", ".join(
                f"{row['label']}={row['value']}" for row in resolved_preview
            )
            _emit_dataset(
                "contrast",
                dataset_index=dataset_index,
                dataset_label=dataset_label,
                ratio=0.05,
                label=f"Stamping {dataset_label}…",
                done=combo_index + 1,
                total=len(combos),
            )
            contrast_pools.append(
                self._write_contrast_clone(
                    personas=personas,
                    overlay=overlay,
                    stamps=stamps,
                    parent_pool=rel_pool,
                    on_progress=(
                        _write_progress_for(dataset_index, dataset_label)
                        if on_progress is not None
                        else None
                    ),
                )
            )
            _emit_dataset(
                "done",
                dataset_index=dataset_index,
                dataset_label=dataset_label,
                ratio=1.0,
                label=f"Wrote contrast {combo_index + 1}/{len(combos)}",
            )
        persona_ids = [str(entry["persona_id"]) for entry in personas]
        return {
            "pool": rel_pool,
            "label": parent_label,
            "count": int(manifest["count"]),
            "dimensionCount": int(manifest.get("dimension_count") or 0),
            "source": "synthetic",
            "kind": "dataset",
            "personaIds": persona_ids,
            "seed": seed,
            "contrastStamps": (
                {row["id"]: row["value"] for row in base_resolved}
                if base_resolved
                else None
            ),
            "contrastPools": contrast_pools,
        }

    def clone_contrast_pool(
        self,
        *,
        persona_pool: str,
        overlay_id: str,
        value: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Clone a YAML dataset and change one custom dimension only."""
        from backend.service.persona_1m_pool import is_production_1m_root

        src_rel = str(persona_pool or "").strip() or DEFAULT_PERSONA_POOL
        if is_production_1m_root(src_rel):
            raise ValueError(
                "Cannot build a contrast from the 1M pool. "
                "Generate or save a dataset first."
            )

        summary = self.load_manifest_summary(src_rel)
        overlay = list(summary.get("overlayDimensions") or [])
        if not overlay:
            raise ValueError(
                "This dataset has no custom dimensions. "
                "Generate a pool with a custom dimension first."
            )
        personas = self._load_pool_personas(src_rel)
        if not personas:
            raise ValueError(f"{src_rel} has no persona YAML files")
        if len(personas) > GENERATE_COUNT_MAX:
            raise ValueError(
                f"Contrast copies at most {GENERATE_COUNT_MAX} personas "
                f"({src_rel} has {len(personas)})"
            )
        return self._write_contrast_clone(
            personas=personas,
            overlay=overlay,
            overlay_id=overlay_id,
            value=value,
            parent_pool=src_rel,
            name=name,
        )

    def _write_contrast_clone(
        self,
        *,
        personas: list[dict[str, Any]],
        overlay: list[dict[str, Any]],
        overlay_id: str | None = None,
        value: str | None = None,
        stamps: dict[str, str] | None = None,
        parent_pool: str,
        name: str | None = None,
        on_progress: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        from matraix.persona_consistency import load_dev_dimension_ids
        from matraix.persona_generator import write_persona_dataset

        catalog = self.repo_root / "persona/schema/dimensions.json"
        schema_ids = (
            set(load_dev_dimension_ids(catalog_path=str(catalog)))
            if catalog.is_file()
            else None
        )
        mapping: dict[str, str] = dict(stamps or {})
        if overlay_id and value:
            mapping[str(overlay_id)] = str(value)
        if not mapping:
            raise ValueError("contrast dimension and value are required")
        resolved: list[dict[str, Any]] = []
        for dim_id, text in mapping.items():
            dim = resolve_contrast_overlay(
                overlay,
                dim_id,
                text,
                schema_ids=schema_ids,
            )
            resolved.append({"id": str(dim["id"]), "label": dim.get("label") or dim_id, "value": str(text).strip()})
        stamp_map = {row["id"]: row["value"] for row in resolved}
        validate_contrast_stamps_against_dag(
            personas,
            stamp_map,
            schema_ids=schema_ids,
        )
        cloned = clone_contrast_personas(personas, stamps=stamp_map)
        slug_parts = [
            f"{_cohort_slug(row['id'])}-{_cohort_slug(row['value'])}" for row in resolved
        ]
        kind_slug = (
            _cohort_slug(name)
            if name and str(name).strip()
            else f"contrast-{'-'.join(slug_parts)}"
        )
        folder = _generated_pool_folder(kind_slug, self.repo_root / DATASETS_DIR)
        rel_pool = f"{DATASETS_DIR}/{folder}"
        out_dir = self.repo_root / rel_pool
        first = resolved[0]
        manifest = write_persona_dataset(
            out_dir=out_dir,
            personas=cloned,
            repo_root=self.repo_root,
            kind=folder,
            seed=0,
            smoke_persona_id=str(cloned[0]["persona_id"]),
            overlay_dimensions=overlay,
            on_progress=on_progress,
            extra_manifest={
                "parent_pool": parent_pool,
                "contrast": {
                    "dimension": first["id"],
                    "label": first["label"],
                    "value": first["value"],
                    "stamps": {row["id"]: row["value"] for row in resolved},
                    "source_pool": parent_pool,
                },
            },
        )
        return {
            "pool": rel_pool,
            "label": _contrast_clone_label(folder, resolved),
            "count": int(manifest["count"]),
            "dimensionCount": int(manifest.get("dimension_count") or 0),
            "source": "synthetic",
            "kind": "dataset",
            "personaIds": [str(entry["persona_id"]) for entry in cloned],
            "seed": 0,
            "parentPool": parent_pool,
            "contrastStamps": {row["id"]: row["value"] for row in resolved},
        }

    def _load_pool_personas(self, persona_pool: str) -> list[dict[str, Any]]:
        pool_dir = self._pool_dir(persona_pool)
        entries = load_manifest(pool_dir, repo_root=self.repo_root)
        personas: list[dict[str, Any]] = []
        for entry in entries:
            rel = entry.get("path")
            raw: dict[str, Any] | None = None
            if rel:
                path = self.repo_root / str(rel)
                if path.is_file():
                    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        raw = loaded
            if raw is None and isinstance(entry.get("dimensions"), dict):
                raw = {
                    "persona_id": entry.get("persona_id"),
                    "version": entry.get("version", "1.0"),
                    "source": entry.get("source"),
                    "dimensions": dict(entry["dimensions"]),
                    **(
                        {"pair_id": entry["pair_id"]}
                        if entry.get("pair_id")
                        else {}
                    ),
                }
            if raw is not None:
                personas.append(raw)
        return personas

    def _normalize_dimension_filters(
        self, dimension_filters: dict[str, str | list[str]] | None
    ) -> dict[str, str | list[str]]:
        if not dimension_filters:
            return {}
        normalized: dict[str, str | list[str]] = {}
        for key, value in dimension_filters.items():
            if isinstance(value, list):
                cleaned = [str(item).strip() for item in value if str(item).strip()]
                if cleaned:
                    normalized[str(key)] = cleaned
            elif str(value).strip():
                normalized[str(key)] = str(value).strip()
        return normalized

    def _entry_dimensions(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        dims = self._yaml_dimensions(entry)
        return dims or None

    def _entry_matches_dimension_filters(
        self,
        entry: dict[str, Any],
        dimension_filters: dict[str, str | list[str]],
    ) -> bool:
        if not dimension_filters:
            return True
        dims = self._entry_dimensions(entry)
        if not dims:
            return False
        for key, value in dimension_filters.items():
            actual = dims.get(key)
            if isinstance(value, list):
                if actual not in value:
                    return False
            elif actual != value:
                return False
        return True

    def filter_pool(
        self,
        *,
        persona_pool: str = DEFAULT_PERSONA_POOL,
        sources: list[str] | None = None,
        dimension_filters: dict[str, str | list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        pool_dir = self._pool_dir(persona_pool)
        entries = load_manifest(pool_dir, repo_root=self.repo_root)
        matched = list(entries)
        if sources:
            allowed = {source.strip() for source in sources if source.strip()}
            matched = [
                entry
                for entry in matched
                if str(entry.get("source") or "").strip() in allowed
            ]
        filters = self._normalize_dimension_filters(dimension_filters)
        if filters:
            matched = [
                entry
                for entry in matched
                if self._entry_matches_dimension_filters(entry, filters)
            ]
        return matched

    def _yaml_dimensions(self, entry: dict[str, Any]) -> dict[str, str]:
        """Load full dimensions from persona YAML when present.

        Manifest entries often store only a small card subset (or none for sparse
        1M-sourced rows). Detail / cards should prefer the YAML file.
        """
        rel_path = str(entry.get("path") or "").strip()
        candidates: list[Path] = []
        if rel_path:
            path = Path(rel_path)
            candidates.append(path if path.is_absolute() else self.repo_root / path)
        persona_id = str(entry.get("persona_id") or "").strip()
        if persona_id:
            # Common layouts when path is missing / stale.
            candidates.append(
                self.repo_root
                / DEFAULT_PERSONA_POOL
                / f"persona_{persona_id}.yaml"
            )
        for yaml_path in candidates:
            if not yaml_path.is_file():
                continue
            try:
                raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(raw, dict):
                continue
            dims = raw.get("dimensions")
            if not isinstance(dims, dict):
                continue
            return {
                str(key): str(value)
                for key, value in dims.items()
                if value is not None and str(value).strip()
            }
        dims = entry.get("dimensions")
        if isinstance(dims, dict):
            return {
                str(key): str(value)
                for key, value in dims.items()
                if value is not None and str(value).strip()
            }
        return {}

    @staticmethod
    def _resolve_extra_card_dimensions(
        *,
        stratify_fields: list[str] | None,
        include_dimensions: list[str] | None,
    ) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for raw in [*(stratify_fields or []), *(include_dimensions or [])]:
            dim_id = str(raw or "").removeprefix("dimensions.").strip()
            if dim_id and dim_id != "source" and dim_id not in seen:
                seen.add(dim_id)
                out.append(dim_id)
        return out

    def _persona_card(self, entry: dict[str, Any]) -> dict[str, Any]:
        dims = self._yaml_dimensions(entry)
        display = {
            key: str(dims[key])
            for key in PERSONA_CARD_DIMENSIONS
            if key != "source" and dims.get(key)
        }
        # Sparse 1M-sourced rows may lack the usual card dims — show a few
        # populated attributes so the card is not blank.
        if not display and dims:
            for key, value in list(dims.items())[:4]:
                display[key] = value
        persona_id = str(entry.get("persona_id") or "")
        display_name = str(entry.get("display_name") or "").strip()
        if not display_name:
            rel_path = str(entry.get("path") or "").strip()
            if rel_path:
                yaml_path = self.repo_root / rel_path
                if yaml_path.is_file():
                    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        display_name = str(raw.get("display_name") or "").strip()
        if not display_name:
            from matraix.persona_display_name import synthetic_display_name

            display_name = synthetic_display_name(persona_id, dims)
        source = str(entry.get("source") or "")
        # Full attribute haystack for Persona World / text search (card dims alone are sparse).
        search_parts = [persona_id, display_name, source]
        for key, value in dims.items():
            search_parts.append(str(key))
            search_parts.append(str(value))
        return {
            "personaId": persona_id,
            "name": display_name,
            "source": source,
            "path": str(entry.get("path") or ""),
            "dimensions": display,
            "searchText": " ".join(search_parts),
        }

    def list_persona_ids(
        self, persona_pool: str = DEFAULT_PERSONA_POOL
    ) -> dict[str, Any]:
        """Return every persona id in a pool (for ``All`` cohort selection).

        Prefers a moderate-size ``manifest.json`` persona list (canonical HF
        cohorts). Falls back to ``persona_*.yaml`` filenames when the manifest
        is missing, incomplete, or too large to load cheaply.
        """
        from backend.service.persona_1m_pool import is_production_1m_root

        if is_production_1m_root(persona_pool):
            raise ValueError(
                "All is not supported on matraix-persona-1m (1,000,000 rows). "
                "Use Random/Stratified to sample a cohort (up to 10,000)."
            )

        pool_dir = self._pool_dir(persona_pool)
        if not pool_dir.is_dir():
            raise FileNotFoundError("persona pool not found: {}".format(persona_pool))

        ids: list[str] = []
        manifest_path = pool_dir / "manifest.json"
        if manifest_path.is_file():
            try:
                size = manifest_path.stat().st_size
            except OSError:
                size = 0
            if 0 < size <= 8_000_000:
                try:
                    payload = self._read_json(manifest_path)
                    for item in payload.get("personas") or []:
                        if isinstance(item, dict):
                            pid = str(item.get("persona_id") or "").strip()
                        elif isinstance(item, str):
                            stem = Path(item).stem
                            pid = (
                                stem[len("persona_") :]
                                if stem.startswith("persona_")
                                else stem
                            )
                        else:
                            pid = ""
                        if pid:
                            ids.append(pid)
                except (OSError, ValueError, json.JSONDecodeError, TypeError):
                    ids = []

        if not ids:
            for path in sorted(pool_dir.glob("persona_*.yaml")):
                stem = path.stem
                if stem.startswith("persona_"):
                    pid = stem[len("persona_") :]
                    if pid:
                        ids.append(pid)

        count = len(ids)
        truncated = count > PERSONA_UI_ID_LIST_MAX
        return {
            "pool": persona_pool,
            "personaIds": ids[:PERSONA_CARD_PREVIEW_DEFAULT] if truncated else ids,
            "count": count,
            "idsTruncated": truncated,
        }

    def list_persona_cards(
        self,
        *,
        persona_pool: str = DEFAULT_PERSONA_POOL,
        limit: int = 10,
        offset: int = 0,
        persona_ids: list[str] | None = None,
        seed: int = 42,
        all_personas: bool = False,
    ) -> dict[str, Any]:
        from backend.service.persona_1m_pool import (
            is_production_1m_root,
            preview_production_1m,
        )

        if is_production_1m_root(persona_pool):
            if persona_ids:
                raise ValueError(
                    "Preview specific persona ids from matraix-persona-1m after sampling "
                    "a cohort (Random/Stratified)."
                )
            start = max(0, int(offset))
            page_size = max(1, int(limit))
            preview = preview_production_1m(
                repo_root=self.repo_root,
                limit=page_size,
                offset=start,
                seed=seed,
            )
            return {
                "pool": persona_pool,
                "personas": preview["personas"],
                "offset": start,
                "limit": page_size,
                "previewCount": preview.get("previewCount"),
            }

        pool_dir = self._pool_dir(persona_pool)
        entries = load_manifest(pool_dir, repo_root=self.repo_root)
        if persona_ids:
            wanted = {pid.strip() for pid in persona_ids if pid.strip()}
            chosen = [
                entry
                for entry in entries
                if str(entry.get("persona_id") or "") in wanted
            ]
        elif all_personas:
            sorted_entries = sorted(
                entries,
                key=lambda entry: str(entry.get("persona_id") or ""),
            )
            start = max(0, offset)
            end = start + max(1, limit)
            chosen = sorted_entries[start:end]
        else:
            summary = self.load_manifest_summary(persona_pool)
            smoke_id = str(summary.get("smokePersonaId") or "").strip()
            smoke_entry = next(
                (entry for entry in entries if str(entry.get("persona_id") or "") == smoke_id),
                None,
            )
            rest = [
                entry
                for entry in entries
                if str(entry.get("persona_id") or "") != smoke_id
            ]
            rng = random.Random(seed)
            rng.shuffle(rest)
            chosen = ([smoke_entry] if smoke_entry else []) + rest[: max(0, limit - 1)]
        cards = [self._persona_card(entry) for entry in chosen]
        if not all_personas:
            cards = cards[:limit]
        return {
            "pool": persona_pool,
            "personas": cards,
            "offset": max(0, offset) if all_personas else 0,
            "limit": limit,
        }

    def get_persona_detail(
        self,
        persona_id: str,
        *,
        persona_pool: str = DEFAULT_PERSONA_POOL,
    ) -> dict[str, Any]:
        from backend.service.persona_1m_pool import (
            get_production_1m_persona_detail,
            is_production_1m_pool,
            is_production_1m_root,
        )

        # Production 1M root (and orphan ids): resolve from cohort YAML or Parquet.
        if is_production_1m_root(persona_pool):
            return get_production_1m_persona_detail(
                repo_root=self.repo_root,
                persona_id=persona_id,
                persona_pool=persona_pool,
            )

        pool_dir = self._pool_dir(persona_pool)
        entries = load_manifest(pool_dir, repo_root=self.repo_root)
        entry = next(
            (item for item in entries if str(item.get("persona_id") or "") == persona_id.strip()),
            None,
        )
        if entry is None and persona_id.strip().isdigit():
            padded = persona_id.strip().zfill(4)
            entry = next(
                (item for item in entries if str(item.get("persona_id") or "") == padded),
                None,
            )
        # Cohort path miss → fall back to production lookup (same persona id space).
        if entry is None and is_production_1m_pool(persona_pool):
            return get_production_1m_persona_detail(
                repo_root=self.repo_root,
                persona_id=persona_id,
                persona_pool=persona_pool,
            )
        if entry is None:
            raise FileNotFoundError("persona not found: {}".format(persona_id))
        card = self._persona_card(entry)
        full_dimensions = self._yaml_dimensions(entry)
        yaml_path = _resolve_persona_yaml_path(
            self.repo_root, entry, persona_id, pool_dir
        )
        yaml_text = yaml_path.read_text(encoding="utf-8") if yaml_path.is_file() else ""
        rel_path = str(entry.get("path") or card.get("path") or "")
        if not rel_path and yaml_path.is_file():
            try:
                rel_path = str(yaml_path.relative_to(self.repo_root))
            except ValueError:
                rel_path = str(yaml_path)
        profile_markdown = _persona_profile_markdown(
            persona_id=str(card.get("personaId") or persona_id),
            source=str(card.get("source") or ""),
            path=rel_path,
            yaml_text=yaml_text,
        )
        from backend.service.persona_taxonomy import build_dimension_groups

        return {
            **card,
            "pool": persona_pool,
            "path": rel_path,
            "dimensions": full_dimensions,
            "dimensionGroups": build_dimension_groups(
                full_dimensions, repo_root=self.repo_root
            ),
            "yaml": yaml_text,
            "profileMarkdown": profile_markdown,
        }

    @staticmethod
    def _filters_as_lists(
        dimension_filters: dict[str, str | list[str]] | None,
    ) -> dict[str, list[str]]:
        if not dimension_filters:
            return {}
        out: dict[str, list[str]] = {}
        for key, value in dimension_filters.items():
            dim = str(key).removeprefix("dimensions.").strip()
            if not dim:
                continue
            if isinstance(value, list):
                cleaned = [str(item).strip() for item in value if str(item).strip()]
            else:
                text = str(value).strip()
                cleaned = [text] if text else []
            if cleaned:
                out[dim] = cleaned
        return out

    def _expected_stratify_strata(
        self,
        dimension_filters: dict[str, str | list[str]] | None,
        stratify_fields: list[str] | None,
    ) -> list[dict[str, str]] | None:
        """Feasible stratify cells implied by filters, or None when unknown.

        Requires every stratify field to appear in dimensionFilters so the
        cartesian product of allowed values is well-defined.
        """
        if not stratify_fields:
            return None
        list_filters = self._filters_as_lists(self._normalize_dimension_filters(dimension_filters))
        stratify_filters: dict[str, list[str]] = {}
        for raw_field in stratify_fields:
            field = str(raw_field).removeprefix("dimensions.").strip()
            if not field:
                continue
            values = list_filters.get(field)
            if not values:
                return None
            stratify_filters[field] = values
        if len(stratify_filters) != len(
            [f for f in stratify_fields if str(f).removeprefix("dimensions.").strip()]
        ):
            return None
        from matraix.persona_generator import build_filter_strata, filter_feasible_strata

        try:
            strata = build_filter_strata(stratify_filters, max_strata=MAX_FILTER_STRATA)
        except ValueError:
            return None
        feasible, _dropped = filter_feasible_strata(strata)
        return feasible

    def _stratify_coverage_gap_message(
        self,
        matched: list[dict[str, Any]],
        *,
        stratify_fields: list[str],
        sample_size_per_value_group: int,
        expected_strata: list[dict[str, str]],
    ) -> str | None:
        """Return an error when any expected stratify cell has fewer than N personas."""
        bare_fields = [
            str(field).removeprefix("dimensions.").strip() for field in stratify_fields
        ]
        bare_fields = [field for field in bare_fields if field]
        buckets: dict[str, int] = {}
        for entry in matched:
            key = _stratify_bucket_key(entry, bare_fields, repo_root=self.repo_root)
            if key is None:
                continue
            buckets[key] = buckets.get(key, 0) + 1

        short: list[str] = []
        for stratum in expected_strata:
            key = "\x1f".join(str(stratum[field]) for field in bare_fields)
            have = buckets.get(key, 0)
            if have < sample_size_per_value_group:
                label = ", ".join(f"{field}={stratum[field]}" for field in bare_fields)
                short.append(
                    f"{label!r} has {have}, need sample_size_per_value_group="
                    f"{sample_size_per_value_group}"
                )
        if not short:
            return None
        preview = "; ".join(short[:6])
        more = f" (+{len(short) - 6} more)" if len(short) > 6 else ""
        return f"Incomplete stratify coverage: {preview}{more}"

    def _shape_sample_response(
        self,
        result: dict[str, Any],
        *,
        preview_limit: int = PERSONA_CARD_PREVIEW_DEFAULT,
        include_persona_ids: bool | None = None,
    ) -> dict[str, Any]:
        """Truncate cards/IDs for UI; keep selectedCount as the full cohort size."""
        ids = [str(pid) for pid in (result.get("personaIds") or []) if str(pid).strip()]
        personas = [row for row in (result.get("personas") or []) if isinstance(row, dict)]
        sample_size = int(result.get("sampleSize") or len(ids) or len(personas) or 0)
        if include_persona_ids is None:
            include_persona_ids = sample_size <= PERSONA_UI_ID_LIST_MAX
        if sample_size <= PERSONA_UI_ID_LIST_MAX:
            card_limit = min(sample_size, max(int(preview_limit), sample_size), 100)
        else:
            card_limit = min(sample_size, max(1, int(preview_limit)))
        preview_cards = personas[:card_limit]
        if not preview_cards and ids:
            preview_cards = [
                {
                    "personaId": pid,
                    "name": f"persona-{pid}",
                    "dimensions": {},
                }
                for pid in ids[:card_limit]
            ]
        preview_ids = [
            str(row.get("personaId") or "").strip()
            for row in preview_cards
            if str(row.get("personaId") or "").strip()
        ]
        shaped = dict(result)
        shaped["sampleSize"] = sample_size
        shaped["selectedCount"] = sample_size
        shaped["personas"] = preview_cards
        shaped["personaIds"] = ids if include_persona_ids else preview_ids
        shaped["idsTruncated"] = (not include_persona_ids) and sample_size > len(shaped["personaIds"])
        return shaped

    def _materialize_sample_cohort(
        self,
        chosen: list[dict[str, Any]],
        *,
        parent_pool: str,
        seed: int,
    ) -> dict[str, Any]:
        """Copy chosen YAML personas into a stable cohort dir for ref-based launch."""
        import hashlib

        persona_ids = [
            str(entry.get("persona_id") or entry.get("id") or "").strip()
            for entry in chosen
        ]
        persona_ids = [pid for pid in persona_ids if pid]
        digest = hashlib.sha1(
            json.dumps(
                {"pool": parent_pool, "seed": seed, "ids": persona_ids},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:12]
        rel_pool = _sampled_cohort_pool(parent_pool, digest)
        out_dir = self.repo_root / rel_pool
        out_dir.mkdir(parents=True, exist_ok=True)

        manifest_personas: list[dict[str, Any]] = []
        cards: list[dict[str, Any]] = []
        for entry in chosen:
            persona_id = str(entry.get("persona_id") or entry.get("id") or "").strip()
            if not persona_id:
                continue
            source_path = _resolve_persona_yaml_path(
                self.repo_root, entry, persona_id, self._pool_dir(parent_pool)
            )
            rel_yaml = f"{rel_pool}/persona_{persona_id}.yaml"
            dest = self.repo_root / rel_yaml
            if source_path.is_file():
                shutil.copy2(source_path, dest)
            else:
                payload = {
                    "persona_id": persona_id,
                    "version": "1.0",
                    "source": str(entry.get("source") or "unknown"),
                    "dimensions": dict(entry.get("dimensions") or {}),
                }
                dest.write_text(
                    yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
                    encoding="utf-8",
                )
            card = self._persona_card({**entry, "path": rel_yaml, "persona_id": persona_id})
            cards.append(card)
            manifest_personas.append(
                {
                    "persona_id": persona_id,
                    "path": rel_yaml,
                    "source": card.get("source"),
                    "dimensions": dict(card.get("dimensions") or {}),
                }
            )

        manifest = {
            "kind": "matraix-sample-cohort",
            "parent_pool": parent_pool,
            "count": len(manifest_personas),
            "seed": seed,
            "schema_version": "1.0",
            "created_at": _utc_now(),
            "personas": manifest_personas,
        }
        (out_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return {
            "pool": rel_pool,
            "personaIds": [item["persona_id"] for item in manifest_personas],
            "personas": cards,
            "count": len(manifest_personas),
        }

    def sample_pool(
        self,
        *,
        persona_pool: str = DEFAULT_PERSONA_POOL,
        sample_size: int,
        seed: int = 42,
        sources: list[str] | None = None,
        dimension_filters: dict[str, str | list[str]] | None = None,
        stratify_fields: list[str] | None = None,
        sample_size_per_value_group: int | None = None,
        allocation: str | None = None,
        portions: dict[str, dict[str, float]] | None = None,
        task_path: str | None = None,
        preview_limit: int = PERSONA_CARD_PREVIEW_DEFAULT,
        include_persona_ids: bool | None = None,
        include_dimensions: list[str] | None = None,
    ) -> dict[str, Any]:
        from backend.service.persona_1m_pool import (
            is_production_1m_root,
            sample_production_1m,
        )

        list_filters = self._filters_as_lists(self._normalize_dimension_filters(dimension_filters))
        allocation_norm = _normalize_allocation(
            allocation,
            sample_size_per_value_group=sample_size_per_value_group,
        )

        # Production 1M: sample + materialize a YAML cohort. Never synthesize.
        if is_production_1m_root(persona_pool):
            result = sample_production_1m(
                repo_root=self.repo_root,
                sample_size=sample_size,
                seed=seed,
                sources=sources,
                dimension_filters=list_filters or None,
                stratify_fields=stratify_fields,
                sample_size_per_value_group=sample_size_per_value_group,
                allocation=allocation_norm,
                portions=portions,
            )
            return self._shape_sample_response(
                result,
                preview_limit=preview_limit,
                include_persona_ids=include_persona_ids,
            )

        # Stratified quotas:
        # - perCell → N per cell (primary); sampleSize is not a clip.
        # - equalTotal / only sampleSize → ensure ≥1/cell, then clip to sampleSize.
        # - proportional → Hamilton allocation by cell population, total = sampleSize.
        explicit_per_cell = allocation_norm == "perCell" or (
            isinstance(sample_size_per_value_group, int) and sample_size_per_value_group >= 1
        )
        expected = (
            self._expected_stratify_strata(dimension_filters, stratify_fields)
            if stratify_fields
            else None
        )
        if (
            stratify_fields
            and not explicit_per_cell
            and allocation_norm != "proportional"
            and expected is not None
            and sample_size < len(expected)
        ):
            raise ValueError(
                with_coverage_hint(
                    "sampleSize={} is below the stratified cell count={} "
                    "(need ≥1 persona per combination). Raise sampleSize, set "
                    "perCell allocation, or sample from matraix-persona-1m.".format(
                        sample_size, len(expected)
                    ),
                    task_path=task_path,
                )
            )

        if stratify_fields and expected is not None and allocation_norm != "proportional":
            per_cell = (
                int(sample_size_per_value_group)
                if explicit_per_cell
                else max(1, (sample_size + len(expected) - 1) // len(expected))
            )
            matched = self.filter_pool(
                persona_pool=persona_pool,
                sources=sources,
                dimension_filters=dimension_filters,
            )
            gap = self._stratify_coverage_gap_message(
                matched,
                stratify_fields=list(stratify_fields),
                sample_size_per_value_group=per_cell,
                expected_strata=expected,
            )
            if gap:
                raise ValueError(with_coverage_hint(gap, task_path=task_path))

        try:
            result = self._sample_pool_inner(
                persona_pool=persona_pool,
                sample_size=sample_size,
                seed=seed,
                sources=sources,
                dimension_filters=dimension_filters,
                stratify_fields=stratify_fields,
                sample_size_per_value_group=sample_size_per_value_group,
                allocation=allocation_norm,
                portions=portions,
                include_dimensions=include_dimensions,
            )
        except ValueError as exc:
            raise ValueError(with_coverage_hint(str(exc), task_path=task_path)) from exc
        return self._shape_sample_response(
            result,
            preview_limit=preview_limit,
            include_persona_ids=include_persona_ids,
        )

    def _sample_pool_inner(
        self,
        *,
        persona_pool: str = DEFAULT_PERSONA_POOL,
        sample_size: int,
        seed: int = 42,
        sources: list[str] | None = None,
        dimension_filters: dict[str, str | list[str]] | None = None,
        stratify_fields: list[str] | None = None,
        sample_size_per_value_group: int | None = None,
        allocation: str | None = None,
        portions: dict[str, dict[str, float]] | None = None,
        include_dimensions: list[str] | None = None,
    ) -> dict[str, Any]:
        matched = self.filter_pool(
            persona_pool=persona_pool,
            sources=sources,
            dimension_filters=dimension_filters,
        )
        if sample_size < 1:
            raise ValueError("sample_size must be >= 1")
        allocation_norm = _normalize_allocation(
            allocation,
            sample_size_per_value_group=sample_size_per_value_group,
        )
        if stratify_fields:
            bare_fields = [
                str(field).removeprefix("dimensions.").strip() for field in stratify_fields
            ]
            bare_fields = [field for field in bare_fields if field]
            buckets: dict[str, list[dict[str, Any]]] = {}
            for entry in matched:
                key = _stratify_bucket_key(entry, bare_fields, repo_root=self.repo_root)
                if key is None:
                    continue
                buckets.setdefault(key, []).append(entry)
            n_buckets = len(buckets)
            if n_buckets < 1:
                label = ", ".join(bare_fields)
                raise ValueError(f"No personas with stratify fields ({label})")

            if allocation_norm == "proportional":
                if portions:
                    if len(bare_fields) != 1:
                        raise ValueError(
                            "portions currently supports a single stratify field "
                            f"(got {', '.join(bare_fields)})"
                        )
                    field = bare_fields[0]
                    weights = portions.get(field)
                    if not isinstance(weights, dict) or not weights:
                        raise ValueError(
                            f"portions has no target weights for stratify field {field!r}"
                        )
                    chosen = sample_by_portions_from_buckets(
                        buckets,
                        weights=weights,
                        sample_size=sample_size,
                        seed=seed,
                    )
                else:
                    chosen = sample_proportional_from_buckets(
                        buckets, sample_size=sample_size, seed=seed
                    )
            elif allocation_norm == "perCell" or sample_size_per_value_group is not None:
                per_group = (
                    int(sample_size_per_value_group)
                    if isinstance(sample_size_per_value_group, int)
                    and sample_size_per_value_group >= 1
                    else 1
                )
                chosen = sample_personas_stratified(
                    matched,
                    stratify_fields=list(stratify_fields),
                    sample_size_per_value_group=per_group,
                    seed=seed,
                    repo_root=self.repo_root,
                )
            else:
                # equalTotal: ceil(N / cells) then clip to sampleSize.
                if sample_size < n_buckets:
                    raise ValueError(
                        "sampleSize={} is below the stratified cell count={} "
                        "(need ≥1 persona per combination)".format(sample_size, n_buckets)
                    )
                per_group = max(1, (sample_size + n_buckets - 1) // n_buckets)
                chosen = sample_personas_stratified(
                    matched,
                    stratify_fields=list(stratify_fields),
                    sample_size_per_value_group=per_group,
                    seed=seed,
                    repo_root=self.repo_root,
                )
                if len(chosen) > sample_size:
                    chosen = chosen[:sample_size]
        else:
            if sample_size > len(matched):
                raise ValueError(
                    "sample_size={} exceeds matched pool size={}".format(sample_size, len(matched))
                )
            chosen = sample_personas(matched, sample_size=sample_size, seed=seed)
        personas = [self._persona_card(entry) for entry in chosen]
        extra_dims = self._resolve_extra_card_dimensions(
            stratify_fields=stratify_fields,
            include_dimensions=include_dimensions,
        )
        if extra_dims:
            for card, entry in zip(personas, chosen):
                full = self._yaml_dimensions(entry)
                dims_out = card.setdefault("dimensions", {})
                for dim_id in extra_dims:
                    value = full.get(dim_id)
                    if value is not None and str(value).strip():
                        dims_out[dim_id] = str(value)
        persona_ids = [row["personaId"] for row in personas if row["personaId"]]
        pool_out = persona_pool
        if len(persona_ids) > PERSONA_UI_ID_LIST_MAX:
            materialized = self._materialize_sample_cohort(
                chosen,
                parent_pool=persona_pool,
                seed=seed,
            )
            pool_out = str(materialized["pool"])
            persona_ids = list(materialized["personaIds"])
            personas = list(materialized["personas"])
        return {
            "pool": pool_out,
            "matchedCount": len(matched),
            "sampleSize": len(persona_ids),
            "seed": seed,
            "personaIds": persona_ids,
            "personas": personas,
            "fields": list(stratify_fields or []),
        }

    def _cohorts_root(self) -> Path:
        return self.repo_root / COHORTS_DIR

    def _cohort_path(self, cohort_id: str) -> Path:
        return self._cohorts_root() / _cohort_slug(cohort_id) / "cohort.json"

    def list_cohorts(self) -> list[dict[str, Any]]:
        root = self._cohorts_root()
        if not root.is_dir():
            return []
        summaries: list[dict[str, Any]] = []
        for path in sorted(root.glob("*/cohort.json")):
            try:
                payload = self._read_json(path)
            except Exception:  # noqa: BLE001
                continue
            summaries.append(self._cohort_summary(payload, path.parent.name))
        return summaries

    def get_cohort(self, cohort_id: str) -> dict[str, Any]:
        path = self._cohort_path(cohort_id)
        if not path.is_file():
            raise FileNotFoundError("cohort not found: {}".format(cohort_id))
        payload = self._read_json(path)
        return self._cohort_view(payload)

    def save_cohort(
        self,
        *,
        cohort_id: str,
        name: str | None = None,
        description: str | None = None,
        pool: str = DEFAULT_PERSONA_POOL,
        kind: CohortKind = "recipe",
        seed: int = 42,
        sample_size: int = 1,
        sources: list[str] | None = None,
        dimension_filters: dict[str, str] | None = None,
        persona_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        slug = _cohort_slug(cohort_id)
        matched = self.filter_pool(
            persona_pool=pool,
            sources=sources,
            dimension_filters=dimension_filters,
        )
        resolved_kind: CohortKind = kind
        resolved_persona_ids = list(persona_ids or [])
        personas: list[dict[str, str]] = []

        if resolved_kind == "frozen":
            if not resolved_persona_ids:
                if sample_size < 1:
                    raise ValueError("sample_size must be >= 1 for frozen cohort")
                if sample_size > len(matched):
                    raise ValueError(
                        "sample_size={} exceeds matched pool size={}".format(
                            sample_size, len(matched)
                        )
                    )
                chosen = sample_personas(matched, sample_size=sample_size, seed=seed)
                resolved_persona_ids = [
                    str(entry.get("persona_id") or "") for entry in chosen
                ]
            by_id = {str(entry.get("persona_id") or ""): entry for entry in matched}
            for pid in resolved_persona_ids:
                entry = by_id.get(pid)
                if entry is None:
                    raise ValueError("persona {} not in matched pool".format(pid))
                personas.append(
                    {
                        "personaId": pid,
                        "source": str(entry.get("source") or ""),
                        "path": str(entry.get("path") or ""),
                    }
                )
        else:
            resolved_persona_ids = []
            personas = []

        payload = {
            "cohortId": slug,
            "name": (name or slug).strip(),
            "description": (description or "").strip(),
            "createdAt": _utc_now(),
            "pool": pool,
            "kind": resolved_kind,
            "seed": int(seed),
            "sampleSize": int(sample_size),
            "sources": list(sources or []),
            "dimensionFilters": dict(dimension_filters or {}),
            "matchedCount": len(matched),
            "personaIds": resolved_persona_ids,
            "personas": personas,
        }
        cohort_dir = self._cohorts_root() / slug
        cohort_dir.mkdir(parents=True, exist_ok=True)
        path = cohort_dir / "cohort.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self._cohort_view(payload)

    def resolve_cohort_launch(
        self,
        cohort_id: str,
        *,
        sample_size_override: int | None = None,
    ) -> dict[str, Any]:
        cohort = self.get_cohort(cohort_id)
        pool = str(cohort.get("pool") or DEFAULT_PERSONA_POOL)
        if cohort.get("kind") == "frozen":
            persona_ids = list(cohort.get("personaIds") or [])
            if not persona_ids:
                raise ValueError("frozen cohort has no personaIds")
            return {
                "pool": pool,
                "personaIds": persona_ids,
                "seed": cohort.get("seed"),
                "sources": cohort.get("sources") or [],
                "dimensionFilters": cohort.get("dimensionFilters") or {},
                "cohortId": cohort.get("cohortId"),
            }
        sample_size = int(
            sample_size_override if sample_size_override is not None else cohort.get("sampleSize") or 1
        )
        sampled = self.sample_pool(
            persona_pool=pool,
            sample_size=sample_size,
            seed=int(cohort.get("seed") or 42),
            sources=list(cohort.get("sources") or []) or None,
            dimension_filters=dict(cohort.get("dimensionFilters") or {}) or None,
        )
        return {
            "pool": pool,
            "personaIds": list(sampled["personaIds"]),
            "seed": cohort.get("seed"),
            "sources": cohort.get("sources") or [],
            "dimensionFilters": cohort.get("dimensionFilters") or {},
            "cohortId": cohort.get("cohortId"),
        }

    def _cohort_summary(self, payload: dict[str, Any], fallback_id: str) -> dict[str, Any]:
        return {
            "cohortId": str(payload.get("cohortId") or fallback_id),
            "name": str(payload.get("name") or fallback_id),
            "kind": str(payload.get("kind") or "recipe"),
            "pool": str(payload.get("pool") or DEFAULT_PERSONA_POOL),
            "sampleSize": int(payload.get("sampleSize") or 0),
            "matchedCount": int(payload.get("matchedCount") or 0),
            "personaCount": len(payload.get("personaIds") or []),
            "createdAt": payload.get("createdAt"),
        }

    def _cohort_view(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "cohortId": str(payload.get("cohortId") or ""),
            "name": str(payload.get("name") or ""),
            "description": str(payload.get("description") or ""),
            "createdAt": payload.get("createdAt"),
            "pool": str(payload.get("pool") or DEFAULT_PERSONA_POOL),
            "kind": str(payload.get("kind") or "recipe"),
            "seed": int(payload.get("seed") or 42),
            "sampleSize": int(payload.get("sampleSize") or 1),
            "sources": list(payload.get("sources") or []),
            "dimensionFilters": dict(payload.get("dimensionFilters") or {}),
            "matchedCount": int(payload.get("matchedCount") or 0),
            "personaIds": list(payload.get("personaIds") or []),
            "personas": list(payload.get("personas") or []),
        }
