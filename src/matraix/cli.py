"""Product-facing ``matraix`` CLI.

``matraix run`` wraps ``harbor run`` with the complete launch environment so
commands printed by the job generator work from a clean documented setup.
Harbor remains available directly as the underlying runtime.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from matraix.launch_env import (
    find_repo_root,
    merge_pythonpath,
    required_pythonpath_entries,
)
from matraix.job_results import (
    collect_job_results,
    format_csv_report,
    format_json_report,
    format_text_report,
    parse_formats,
    resolve_job_dir,
)
from matraix.smoke import format_smoke_report, run_survey_smoke

# Matches the export lines the job generator writes into the YAML header,
# e.g. "#   export MATRIX_SURVEY_TASK_PATH=application/tasks/...".
_HEADER_EXPORT_RE = re.compile(r"^#\s*export\s+(MATRIX_[A-Z0-9_]+)=(\S+)\s*$")


def _task_env_from_sidecar(config_path: Path) -> dict[str, str]:
    """Derive ``MATRIX_*`` task exports from the generator's ``.meta.json``."""
    sidecar = config_path.with_suffix(".meta.json")
    if not sidecar.is_file():
        return {}
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(meta, dict):
        return {}
    task_path = meta.get("task")
    trial_profile = meta.get("trial_profile")
    if not task_path or not isinstance(task_path, str):
        return {}
    if trial_profile == "json_survey":
        return {"MATRIX_SURVEY_TASK_PATH": task_path}
    if trial_profile == "user_sim_chat":
        return {"MATRIX_CHATBOT_TASK_PATH": task_path}
    return {}


def _task_env_from_header(config_path: Path) -> dict[str, str]:
    """Fallback: parse ``export MATRIX_*`` comment lines from the YAML header."""
    env: dict[str, str] = {}
    try:
        with config_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.startswith("#"):
                    break
                match = _HEADER_EXPORT_RE.match(line.strip())
                if match:
                    env[match.group(1)] = match.group(2)
    except OSError:
        return {}
    return env


def resolve_run_invocation(
    config_path: Path | None,
    repo_root: Path,
    passthrough: list[str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Return ``harbor`` argv and the env updates for a ``matraix run`` call.

    Environment variables already exported by the user always win over
    values derived from the generated job files.
    """
    env_updates: dict[str, str] = {}
    config_args: list[str] = []
    if config_path is not None:
        task_env = _task_env_from_header(config_path)
        task_env.update(_task_env_from_sidecar(config_path))
        env_updates = {
            name: value for name, value in task_env.items() if name not in os.environ
        }
        try:
            config_arg = str(config_path.relative_to(repo_root))
        except ValueError:
            config_arg = str(config_path)
        config_args = ["-c", config_arg]
    env_updates["PYTHONPATH"] = merge_pythonpath(
        os.environ.get("PYTHONPATH"), repo_root
    )
    argv = ["run", *config_args, *(passthrough or [])]
    return argv, env_updates


def _pop_positional_config(passthrough: list[str]) -> tuple[str | None, list[str]]:
    """Allow ``matraix run <job.yaml>`` by sniffing a YAML path from the args."""
    for index, extra in enumerate(passthrough):
        if not extra.startswith("-") and extra.endswith((".yaml", ".yml")):
            return extra, passthrough[:index] + passthrough[index + 1 :]
    return None, passthrough


def _cmd_run(args: argparse.Namespace, passthrough: list[str]) -> None:
    raw_config = args.config_opt
    if raw_config is None:
        raw_config, passthrough = _pop_positional_config(passthrough)

    config_path: Path | None = None
    if raw_config is not None:
        config_path = Path(raw_config).expanduser()
        if not config_path.is_absolute():
            config_path = Path.cwd() / config_path
        config_path = config_path.resolve()
        if not config_path.is_file():
            sys.exit(f"matraix run: job config not found: {config_path}")

    repo_root = (
        Path(args.repo_root).resolve()
        if args.repo_root
        else find_repo_root(config_path.parent if config_path else None)
    )
    argv, env_updates = resolve_run_invocation(config_path, repo_root, passthrough)
    if args.max_cost_usd is not None:
        if args.max_cost_usd < 0:
            sys.exit("matraix run: --max-cost-usd must be >= 0")
        env_updates["MATRIX_MAX_COST_USD"] = f"{args.max_cost_usd:g}"
    os.environ.update(env_updates)
    for name, value in env_updates.items():
        if name == "PYTHONPATH":
            continue
        if name == "MATRIX_MAX_COST_USD":
            print(f"matraix run: budget gate MATRIX_MAX_COST_USD={value}", file=sys.stderr)
        else:
            print(f"matraix run: {name}={value} (from generated job)", file=sys.stderr)
    # Make the injected paths visible to this process too, since Harbor loads
    # agent modules in-process before spawning trial workers.
    for entry in reversed(required_pythonpath_entries(repo_root)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    os.chdir(repo_root)
    print(f"matraix run: harbor {' '.join(argv)} (cwd {repo_root})", file=sys.stderr)

    from harbor.cli.main import app as harbor_app

    harbor_app(args=argv, prog_name="harbor")


def _cmd_results(args: argparse.Namespace) -> None:
    repo_root = (
        Path(args.repo_root).resolve()
        if args.repo_root
        else find_repo_root(Path.cwd())
    )
    try:
        job_dir = resolve_job_dir(args.job, repo_root=repo_root)
        formats = parse_formats(args.format)
    except (FileNotFoundError, ValueError) as exc:
        sys.exit(f"matraix results: {exc}")

    group_by = [part.strip() for part in (args.group_by or "").split(",") if part.strip()]
    report = collect_job_results(job_dir, group_by=group_by or None)

    writers = {
        "text": format_text_report,
        "json": format_json_report,
        "csv": format_csv_report,
    }

    if args.output == "-":
        for index, fmt in enumerate(formats):
            if len(formats) > 1:
                print(f"===== {fmt} =====")
            sys.stdout.write(writers[fmt](report))
        return

    if args.output:
        output_path = Path(args.output).expanduser()
        if not output_path.is_absolute():
            output_path = (Path.cwd() / output_path).resolve()
        else:
            output_path = output_path.resolve()
        single_file = len(formats) == 1 and (
            output_path.suffix.lower() in {".txt", ".md", ".json", ".csv"}
            or not output_path.exists()
        )
        if single_file and not output_path.is_dir():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(writers[formats[0]](report), encoding="utf-8")
            print(f"matraix results: wrote {output_path}", file=sys.stderr)
            return
        output_path.mkdir(parents=True, exist_ok=True)
        for fmt in formats:
            suffix = {"text": "txt", "json": "json", "csv": "csv"}[fmt]
            target = output_path / f"{report.job_name}.results.{suffix}"
            target.write_text(writers[fmt](report), encoding="utf-8")
            print(f"matraix results: wrote {target}", file=sys.stderr)
        return

    for index, fmt in enumerate(formats):
        if len(formats) > 1:
            print(f"===== {fmt} =====")
        sys.stdout.write(writers[fmt](report))


def _cmd_smoke(args: argparse.Namespace) -> None:
    repo_root = (
        Path(args.repo_root).resolve()
        if args.repo_root
        else find_repo_root(Path.cwd())
    )
    for entry in reversed(required_pythonpath_entries(repo_root)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    os.environ["PYTHONPATH"] = merge_pythonpath(
        os.environ.get("PYTHONPATH"), repo_root
    )
    report = run_survey_smoke(
        args.task,
        repo_root=repo_root,
        personas=max(1, int(args.personas)),
        persona=args.persona,
        keep_artifacts=bool(args.keep_artifacts),
    )
    sys.stdout.write(format_smoke_report(report))
    if not report.ok:
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="matraix",
        description="MatrAIx product CLI. Harbor stays available as the underlying runtime.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Run a job with the complete MatrAIx launch environment.",
        description=(
            "Runs `harbor run` with the same PYTHONPATH and MATRIX_* task exports "
            "the Playground injects. All other arguments (e.g. -p/-a for ad-hoc "
            "task runs) are passed through to harbor run."
        ),
    )
    run_parser.add_argument(
        "-c",
        "--config",
        dest="config_opt",
        default=None,
        help="Path to a generated job YAML (may also be passed positionally)",
    )
    run_parser.add_argument(
        "--repo-root",
        default=None,
        help="MatrAIx repository root (default: discovered from the config path)",
    )
    run_parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=None,
        help=(
            "Hard job spend gate for Survey/Chat paths that honor "
            "MATRIX_MAX_COST_USD. Further provider requests are refused once "
            "recorded spend meets this limit. Web/OS agents already report "
            "tokens/cost via their runtimes; this gate applies to host-native "
            "Survey/Chat today."
        ),
    )

    results_parser = subparsers.add_parser(
        "results",
        help="Summarize and export a finished job without another LLM call.",
        description=(
            "Deterministic job ledger + type-aware outcome lens for Survey, "
            "Chat, Web, and OS-app jobs. Reads jobs/<job>/ result.json, "
            "verifier/structured_output.json, and known artifacts. Default "
            "path never calls another model. Use --format json,csv for export."
        ),
    )
    results_parser.add_argument(
        "job",
        help="Job name under jobs/ or a path to a job directory",
    )
    results_parser.add_argument(
        "--format",
        default="text",
        help="Comma-separated formats: text,json,csv (default: text)",
    )
    results_parser.add_argument(
        "--group-by",
        default=None,
        help=(
            "Comma-separated persona fields for cuts "
            "(e.g. life_stage). Reads persona_meta / persona YAML dimensions."
        ),
    )
    results_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=(
            "Write export(s) to a file (single format) or directory "
            "(multiple formats). Use - for stdout."
        ),
    )
    results_parser.add_argument(
        "--repo-root",
        default=None,
        help="MatrAIx repository root (default: discovered from cwd)",
    )

    smoke_parser = subparsers.add_parser(
        "smoke",
        help="Zero-cost host Survey check (no Docker, no API key).",
        description=(
            "Host-lane onboarding smoke for Survey / json_survey. Loads the "
            "questionnaire, renders a persona, runs the real survey runner with "
            "a deterministic fake client, and checks the answer envelope. "
            "Does not call a provider and does not require Docker. "
            "For Docker/Harbor stack smoke use: "
            "matraix run -c configs/jobs/example-job-recipe/harbor-smoke-local.yaml"
        ),
    )
    smoke_parser.add_argument(
        "task",
        help="Survey task directory (e.g. application/tasks/example-survey_product-feedback)",
    )
    smoke_parser.add_argument(
        "--personas",
        type=int,
        default=1,
        help="Number of personas from the dev sample (default: 1 = persona_0042)",
    )
    smoke_parser.add_argument(
        "--persona",
        default=None,
        help="Optional persona YAML path (overrides --personas sampling)",
    )
    smoke_parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Keep temp survey_result.json artifacts after a successful smoke",
    )
    smoke_parser.add_argument(
        "--repo-root",
        default=None,
        help="MatrAIx repository root (default: discovered from cwd)",
    )

    args, passthrough = parser.parse_known_args(argv)
    if args.command == "run":
        _cmd_run(args, passthrough)
    elif args.command == "results":
        if passthrough:
            sys.exit(f"matraix results: unrecognized arguments: {' '.join(passthrough)}")
        _cmd_results(args)
    elif args.command == "smoke":
        if passthrough:
            sys.exit(f"matraix smoke: unrecognized arguments: {' '.join(passthrough)}")
        _cmd_smoke(args)


if __name__ == "__main__":
    main()
