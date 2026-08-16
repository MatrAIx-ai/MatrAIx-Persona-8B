"""Job-level spend tracking for ``MATRIX_MAX_COST_USD`` (issue #78 P1-A).

Survey trials share a job directory. Before each LLM call we refuse to spend
when the recorded job total already meets the budget; after each call we add
this trial's cost so later trials see the updated total.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Optional

_BUDGET_FILENAME = "_matraix_budget.json"
_LOCK = threading.Lock()


class BudgetExceededError(RuntimeError):
    """Raised when a job would exceed ``MATRIX_MAX_COST_USD``."""


def max_cost_usd_from_env() -> Optional[float]:
    raw = (os.environ.get("MATRIX_MAX_COST_USD") or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"MATRIX_MAX_COST_USD must be a number, got {raw!r}"
        ) from exc
    if value < 0:
        raise ValueError(f"MATRIX_MAX_COST_USD must be >= 0, got {value}")
    return value


def budget_state_path(job_dir: Path) -> Path:
    return Path(job_dir) / _BUDGET_FILENAME


def read_spent_usd(job_dir: Path) -> float:
    path = budget_state_path(job_dir)
    if not path.is_file():
        return 0.0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0.0
    if not isinstance(payload, dict):
        return 0.0
    try:
        return float(payload.get("spent_usd") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def assert_budget_allows_request(job_dir: Path | None) -> None:
    """Raise ``BudgetExceededError`` if spent already meets the configured max."""
    max_cost = max_cost_usd_from_env()
    if max_cost is None or job_dir is None:
        return
    spent = read_spent_usd(job_dir)
    if spent >= max_cost:
        raise BudgetExceededError(
            f"Job spend ${spent:.6f} already meets MATRIX_MAX_COST_USD=${max_cost:.6f}; "
            "refusing further provider requests."
        )


def record_trial_cost(job_dir: Path | None, cost_usd: float | None) -> float:
    """Add ``cost_usd`` to the job spend file; return the new total.

    When cost is unknown (``None``), the spend file is left unchanged and the
    current total is returned. Unknown costs cannot enforce a hard dollar gate.
    """
    if job_dir is None:
        return 0.0
    max_cost = max_cost_usd_from_env()
    with _LOCK:
        spent = read_spent_usd(job_dir)
        if cost_usd is not None and cost_usd > 0:
            spent += float(cost_usd)
            path = budget_state_path(job_dir)
            path.write_text(
                json.dumps(
                    {
                        "spent_usd": spent,
                        "max_cost_usd": max_cost,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        if max_cost is not None and cost_usd is not None and spent > max_cost:
            raise BudgetExceededError(
                f"Job spend ${spent:.6f} exceeded MATRIX_MAX_COST_USD=${max_cost:.6f} "
                f"after recording this trial's ${float(cost_usd):.6f}."
            )
        return spent
