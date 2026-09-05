"""Package entry point for ``python -m playground``."""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "playground no longer provides a standalone in-process CLI.\n"
        "Launch evaluations through Harbor instead:\n"
        "  uv run python application/scripts/generate_application_job.py --task <task> --execution-mode auto\n"
        "  uv run matraix run -c configs/jobs/application-task-job-recipe/<job>.yaml\n"
        "Or use the Playground (POST /api/harbor/jobs).",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
