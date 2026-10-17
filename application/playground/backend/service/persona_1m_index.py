"""Inverted dim → row_id indexes for MatrAIx Persona 1M sampling.

Layout (next to the release or under ``persona/datasets/matraix-persona-1m/indexes``)::

    indexes/
      manifest.json
      postings.sqlite   # (field_id, value) → packed uint32 row_ids

Global ``row_id`` is contiguous across ``persona-1m-*.parquet`` in sorted order.
"""

from __future__ import annotations

import array
import json
import sqlite3
import struct
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from backend.service.persona_1m_pool import (
    PRODUCTION_1M_POOL,
    Persona1MPaths,
    load_codec,
    resolve_1m_paths,
)
from persona.post_process.unified_dataset.schema import (
    ATTRIBUTE_BYTES,
    ATTRIBUTE_COUNT,
)

INDEX_VERSION = 1
POSTINGS_DB = "postings.sqlite"
MANIFEST_NAME = "manifest.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_index_dir(
    repo_root: Path,
    paths: Persona1MPaths | None = None,
) -> Path | None:
    """Return an indexes directory that already has a manifest, if any."""
    candidates = [
        repo_root / PRODUCTION_1M_POOL / "indexes",
    ]
    if paths is not None:
        candidates.insert(0, paths.root / "indexes")
    for candidate in candidates:
        if (candidate / MANIFEST_NAME).is_file() and (candidate / POSTINGS_DB).is_file():
            return candidate
    return None


def default_index_dir(repo_root: Path) -> Path:
    return repo_root / PRODUCTION_1M_POOL / "indexes"


def _rel_or_abs(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _pack_row_ids(row_ids: Iterable[int]) -> bytes:
    arr = array.array("I", (int(x) for x in row_ids))
    if arr.itemsize != 4:
        # Platform oddity — force little-endian uint32.
        return b"".join(struct.pack("<I", int(x)) for x in arr)
    if sys_byteorder_is_big():
        arr.byteswap()
    return arr.tobytes()


def sys_byteorder_is_big() -> bool:
    return struct.pack("@I", 1) != struct.pack("<I", 1)


def _unpack_row_ids(blob: bytes) -> np.ndarray:
    if not blob:
        return np.zeros(0, dtype=np.uint32)
    return np.frombuffer(blob, dtype="<u4").astype(np.uint32, copy=False)


def _unpack_codes(
    attributes: bytes | memoryview,
    null_bitmap: bytes | memoryview | None,
) -> tuple[np.ndarray, np.ndarray]:
    packed = np.frombuffer(memoryview(attributes), dtype=np.uint8)
    if packed.size < ATTRIBUTE_BYTES:
        raise ValueError(f"attributes width {packed.size} < expected {ATTRIBUTE_BYTES}")
    codes = np.empty(ATTRIBUTE_COUNT, dtype=np.uint8)
    codes[0::2] = packed[:ATTRIBUTE_BYTES] & 0x0F
    codes[1::2] = (packed[: (ATTRIBUTE_COUNT // 2)] >> 4) & 0x0F
    nulls = np.zeros(ATTRIBUTE_COUNT, dtype=np.uint8)
    if null_bitmap is not None:
        bits = np.frombuffer(memoryview(null_bitmap), dtype=np.uint8)
        unpacked = np.unpackbits(bits, bitorder="little")
        nulls[: min(ATTRIBUTE_COUNT, unpacked.size)] = unpacked[:ATTRIBUTE_COUNT]
    return codes, nulls


def build_indexes(
    *,
    repo_root: Path,
    output_dir: Path | None = None,
    progress_every: int = 20_000,
) -> dict[str, Any]:
    """Scan the local 1M release and write a full per-dimension inverted index."""
    import pyarrow.parquet as pq

    paths = resolve_1m_paths(repo_root)
    codec = load_codec(paths.schema_path)
    out_dir = output_dir or default_index_dir(repo_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / POSTINGS_DB
    if db_path.exists():
        db_path.unlink()

    # field_id -> value -> array('I')
    postings: dict[str, dict[str, array.array]] = defaultdict(
        lambda: defaultdict(lambda: array.array("I"))
    )
    reverse_labels: list[list[str | None]] = []
    for field_index in range(ATTRIBUTE_COUNT):
        max_code = max(codec.value_codes[field_index].values(), default=-1)
        labels: list[str | None] = [None] * (max_code + 1)
        for name, code in codec.value_codes[field_index].items():
            labels[code] = name
        reverse_labels.append(labels)

    shard_info: list[dict[str, Any]] = []
    global_row = 0
    t0 = time.time()
    for parquet_path in paths.parquet_files:
        parquet = pq.ParquetFile(parquet_path)
        shard_start = global_row
        for batch in parquet.iter_batches(
            batch_size=4_096,
            columns=["source", "attributes", "null_bitmap", "attribute_overrides"],
        ):
            sources = batch.column("source").to_pylist()
            attributes = batch.column("attributes").to_pylist()
            null_bitmaps = batch.column("null_bitmap").to_pylist()
            overrides_col = (
                batch.column("attribute_overrides").to_pylist()
                if "attribute_overrides" in batch.schema.names
                else [None] * len(attributes)
            )
            for source, attrs, null_bitmap, overrides in zip(
                sources, attributes, null_bitmaps, overrides_col
            ):
                source_label = str(source or "unknown").strip() or "unknown"
                postings["source"][source_label].append(global_row)
                if attrs is None:
                    global_row += 1
                    continue
                codes, nulls = _unpack_codes(attrs, null_bitmap)
                # Apply overrides as string labels keyed by field index.
                override_labels: dict[int, str] = {}
                for override in overrides or ():
                    try:
                        field_index = int(override["field_index"])
                        value = override.get("value")
                    except (KeyError, TypeError, ValueError):
                        continue
                    if value is None or not (0 <= field_index < ATTRIBUTE_COUNT):
                        continue
                    override_labels[field_index] = str(value)

                for field_index, field_id in enumerate(codec.field_ids):
                    if field_index in override_labels:
                        label = override_labels[field_index]
                    elif nulls[field_index]:
                        continue
                    else:
                        code = int(codes[field_index])
                        labels = reverse_labels[field_index]
                        if code >= len(labels) or labels[code] is None:
                            continue
                        label = labels[code]
                    postings[field_id][label].append(global_row)

                global_row += 1
                if progress_every and global_row % progress_every == 0:
                    elapsed = time.time() - t0
                    rate = global_row / max(elapsed, 1e-6)
                    print(
                        f"[persona-1m-index] rows={global_row:,} "
                        f"({rate:,.0f}/s) fields={len(postings)}",
                        flush=True,
                    )

        shard_info.append(
            {
                "path": _rel_or_abs(parquet_path, paths.root),
                "rowStart": shard_start,
                "rowCount": global_row - shard_start,
            }
        )

    print(f"[persona-1m-index] writing sqlite ({global_row:,} rows)…", flush=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute(
            """
            CREATE TABLE postings (
              field_id TEXT NOT NULL,
              value TEXT NOT NULL,
              row_ids BLOB NOT NULL,
              count INTEGER NOT NULL,
              PRIMARY KEY (field_id, value)
            )
            """
        )
        rows_out = []
        for field_id, by_value in postings.items():
            for value, ids in by_value.items():
                blob = _pack_row_ids(ids)
                rows_out.append((field_id, value, blob, len(ids)))
                if len(rows_out) >= 2_000:
                    conn.executemany(
                        "INSERT INTO postings(field_id, value, row_ids, count) VALUES (?,?,?,?)",
                        rows_out,
                    )
                    rows_out.clear()
        if rows_out:
            conn.executemany(
                "INSERT INTO postings(field_id, value, row_ids, count) VALUES (?,?,?,?)",
                rows_out,
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS postings_field ON postings(field_id)"
        )
        conn.commit()
    finally:
        conn.close()

    source_values = sorted(postings.get("source", {}).keys())
    manifest = {
        "format": "matraix_persona_1m_postings_v1",
        "version": INDEX_VERSION,
        "createdAt": _utc_now(),
        "rows": global_row,
        "fieldCount": len(postings),
        "postingKeys": sum(len(v) for v in postings.values()),
        "schemaPath": str(paths.schema_path),
        "releaseRoot": str(paths.root),
        "shards": shard_info,
        "db": POSTINGS_DB,
        "sourceIndexed": bool(source_values),
        "sourceValues": source_values,
    }
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"[persona-1m-index] done rows={global_row:,} "
        f"keys={manifest['postingKeys']:,} dir={out_dir} "
        f"in {time.time() - t0:.1f}s",
        flush=True,
    )
    return manifest


@dataclass
class Persona1MIndex:
    root: Path
    manifest: dict[str, Any]
    rows: int
    _conn: sqlite3.Connection

    @classmethod
    def open(cls, index_dir: Path) -> "Persona1MIndex":
        manifest = json.loads((index_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
        conn = sqlite3.connect(f"file:{(index_dir / POSTINGS_DB).resolve()}?mode=ro", uri=True)
        return cls(
            root=index_dir,
            manifest=manifest,
            rows=int(manifest.get("rows") or 0),
            _conn=conn,
        )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Persona1MIndex":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def values_for_field(self, field_id: str) -> list[str]:
        cur = self._conn.execute(
            "SELECT value FROM postings WHERE field_id = ? ORDER BY value",
            (field_id,),
        )
        return [str(row[0]) for row in cur.fetchall()]

    def has_field(self, field_id: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM postings WHERE field_id = ? LIMIT 1",
            (field_id,),
        )
        return cur.fetchone() is not None

    def row_ids_for(self, field_id: str, values: list[str] | None = None) -> np.ndarray:
        """Union of row_ids for ``field_id`` in ``values`` (all values if None)."""
        if values is None:
            cur = self._conn.execute(
                "SELECT row_ids FROM postings WHERE field_id = ?",
                (field_id,),
            )
        else:
            cleaned = [str(v) for v in values if str(v).strip()]
            if not cleaned:
                return np.zeros(0, dtype=np.uint32)
            placeholders = ",".join("?" for _ in cleaned)
            cur = self._conn.execute(
                f"SELECT row_ids FROM postings WHERE field_id = ? AND value IN ({placeholders})",
                (field_id, *cleaned),
            )
        chunks = [_unpack_row_ids(blob) for (blob,) in cur.fetchall() if blob]
        if not chunks:
            return np.zeros(0, dtype=np.uint32)
        if len(chunks) == 1:
            return np.unique(chunks[0])
        return np.unique(np.concatenate(chunks))


def intersect_sorted(arrays: list[np.ndarray]) -> np.ndarray:
    if not arrays:
        return np.zeros(0, dtype=np.uint32)
    arrays = [np.asarray(a, dtype=np.uint32) for a in arrays if a is not None and len(a)]
    if not arrays:
        return np.zeros(0, dtype=np.uint32)
    arrays.sort(key=len)
    out = np.unique(arrays[0])
    for other in arrays[1:]:
        out = np.intersect1d(out, np.unique(other), assume_unique=True)
        if out.size == 0:
            break
    return out.astype(np.uint32, copy=False)


def enrich_source_postings(
    *,
    repo_root: Path,
    index_dir: Path | None = None,
    progress_every: int = 100_000,
) -> dict[str, Any]:
    """Add/replace ``source`` postings without rebuilding all 1290 attribute indexes."""
    import pyarrow.parquet as pq

    paths = resolve_1m_paths(repo_root)
    out_dir = index_dir or resolve_index_dir(repo_root, paths) or default_index_dir(repo_root)
    db_path = out_dir / POSTINGS_DB
    if not db_path.is_file():
        raise FileNotFoundError(f"missing index db: {db_path}")

    postings: dict[str, array.array] = defaultdict(lambda: array.array("I"))
    global_row = 0
    t0 = time.time()
    for parquet_path in paths.parquet_files:
        parquet = pq.ParquetFile(parquet_path)
        for batch in parquet.iter_batches(batch_size=8_192, columns=["source"]):
            for source in batch.column("source").to_pylist():
                label = str(source or "unknown").strip() or "unknown"
                postings[label].append(global_row)
                global_row += 1
                if progress_every and global_row % progress_every == 0:
                    print(
                        f"[persona-1m-index] source rows={global_row:,} "
                        f"({global_row / max(time.time() - t0, 1e-6):,.0f}/s)",
                        flush=True,
                    )

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM postings WHERE field_id = ?", ("source",))
        rows_out = [
            ("source", value, _pack_row_ids(ids), len(ids))
            for value, ids in postings.items()
        ]
        conn.executemany(
            "INSERT INTO postings(field_id, value, row_ids, count) VALUES (?,?,?,?)",
            rows_out,
        )
        conn.commit()
        manifest_path = out_dir / MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["sourceIndexed"] = True
        manifest["sourceValues"] = sorted(postings.keys())
        manifest["updatedAt"] = _utc_now()
        # recount keys
        cur = conn.execute("SELECT COUNT(*) FROM postings")
        manifest["postingKeys"] = int(cur.fetchone()[0])
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    finally:
        conn.close()
    print(
        f"[persona-1m-index] source postings written values={len(postings)} "
        f"rows={global_row:,} in {time.time() - t0:.1f}s",
        flush=True,
    )
    return {"rows": global_row, "sourceValues": sorted(postings.keys()), "indexDir": str(out_dir)}


def candidate_row_ids_for_filters(
    index: Persona1MIndex,
    *,
    dimension_filters: dict[str, list[str]] | None,
) -> np.ndarray | None:
    """AND across dimensions; OR within a dimension's values. None = no dim filters."""
    if not dimension_filters:
        return None
    parts: list[np.ndarray] = []
    for field_id, values in dimension_filters.items():
        cleaned = [str(v).strip() for v in (values or []) if str(v).strip()]
        if not cleaned:
            continue
        ids = index.row_ids_for(field_id, cleaned)
        parts.append(ids)
    if not parts:
        return None
    return intersect_sorted(parts)


def even_quotas(sizes: list[int], total: int) -> list[int]:
    """Split ``total`` as evenly as possible over cells capped at ``sizes``.

    Remainders go to the earliest cells; a cell that runs out hands its share
    to the cells that still have room.
    """
    quotas = [0] * len(sizes)
    remaining = min(max(0, int(total)), sum(sizes))
    open_cells = [i for i, size in enumerate(sizes) if size > 0]
    while remaining > 0 and open_cells:
        share, extra = divmod(remaining, len(open_cells))
        still_open: list[int] = []
        for rank, i in enumerate(open_cells):
            take = min(share + (1 if rank < extra else 0), sizes[i] - quotas[i])
            quotas[i] += take
            remaining -= take
            if quotas[i] < sizes[i]:
                still_open.append(i)
        open_cells = still_open
    return quotas


def sample_row_ids_with_index(
    index: Persona1MIndex,
    *,
    sample_size: int,
    seed: int,
    sources: list[str] | None = None,
    dimension_filters: dict[str, list[str]] | None = None,
    stratify_fields: list[str] | None = None,
    sample_size_per_value_group: int | None = None,
) -> np.ndarray | None:
    """Return global row_ids using the inverted index, or None if unusable."""
    if sample_size < 1:
        return np.zeros(0, dtype=np.uint32)

    rng = np.random.default_rng(seed)
    bare = [
        str(field).removeprefix("dimensions.").strip()
        for field in (stratify_fields or [])
        if str(field).removeprefix("dimensions.").strip()
    ]
    per_cell = (
        sample_size_per_value_group
        if isinstance(sample_size_per_value_group, int) and sample_size_per_value_group >= 1
        else None
    )

    parts: list[np.ndarray] = []
    dim_base = candidate_row_ids_for_filters(index, dimension_filters=dimension_filters)
    if dim_base is not None:
        parts.append(dim_base)
    if sources:
        cleaned = [str(s).strip() for s in sources if str(s).strip()]
        if cleaned:
            if not index.has_field("source"):
                return None
            parts.append(index.row_ids_for("source", cleaned))
    base = intersect_sorted(parts) if parts else None

    if bare:
        # Stratified: fill cells from index, stop at sample_size.
        # Cell values: intersection of filter constraints with each field's values.
        field_values: list[list[str]] = []
        for field in bare:
            if dimension_filters and field in dimension_filters and dimension_filters[field]:
                field_values.append(
                    [str(v).strip() for v in dimension_filters[field] if str(v).strip()]
                )
            else:
                field_values.append(index.values_for_field(field))
            if not field_values[-1]:
                return np.zeros(0, dtype=np.uint32)

        chosen: list[int] = []
        # Iterate cells in deterministic order; sample within each cell.
        from itertools import product

        cells = list(product(*field_values))
        rng.shuffle(cells)
        if per_cell is None:
            # equalTotal: spread sample_size evenly over the non-empty cells.
            pools: list[np.ndarray] = []
            for cell in cells:
                if len(pools) >= sample_size:
                    break  # every later cell would get a zero quota
                parts = [base] if base is not None else []
                for field, value in zip(bare, cell):
                    parts.append(index.row_ids_for(field, [value]))
                cell_ids = intersect_sorted(parts)
                if cell_ids.size:
                    pools.append(cell_ids)
            quotas = even_quotas([int(pool.size) for pool in pools], sample_size)
            for pool, take in zip(pools, quotas):
                if take:
                    pick = rng.choice(pool, size=take, replace=False)
                    chosen.extend(int(x) for x in np.atleast_1d(pick))
            return np.asarray(chosen, dtype=np.uint32)
        # Explicit per-cell quota is primary: take N per cell across ALL cells;
        # sample_size is not a clip (mirrors PersonaPoolService contract).
        target = per_cell * len(cells) if per_cell is not None else sample_size
        for cell in cells:
            if len(chosen) >= target:
                break
            parts = []
            if base is not None:
                parts.append(base)
            for field, value in zip(bare, cell):
                parts.append(index.row_ids_for(field, [value]))
            cell_ids = intersect_sorted(parts)
            if cell_ids.size == 0:
                continue
            take = per_cell if per_cell is not None else 1
            take = min(take, int(cell_ids.size), target - len(chosen))
            if take <= 0:
                continue
            pick = rng.choice(cell_ids, size=take, replace=False)
            chosen.extend(int(x) for x in np.atleast_1d(pick))
        return np.asarray(chosen[:target], dtype=np.uint32)

    # Random (optionally filtered).
    pool = base if base is not None else np.arange(index.rows, dtype=np.uint32)
    if pool.size == 0:
        return np.zeros(0, dtype=np.uint32)
    take = min(sample_size, int(pool.size))
    return rng.choice(pool, size=take, replace=False).astype(np.uint32)
