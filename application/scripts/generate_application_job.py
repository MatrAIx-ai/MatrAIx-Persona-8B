#!/usr/bin/env python3
"""Sample personas and write a multi-trial Harbor job YAML for application tasks.

Retrieval matches Playground Persona World:
  sources, dimension filters, task persona_strategy.json, cohorts,
  and matraix-persona-1m sampling via PersonaPoolService.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from matraix.application_job import (
    build_application_job_config,
    collect_run_env_exports,
)
from matraix.persona_job import DEFAULT_DATASET, parse_stratify_field_args
from matraix.provider_credentials import (
    export_hint_lines,
    format_credential_preflight,
)

from _repo_imports import REPO_ROOT, ensure_application_script_imports

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from persona_retrieval import (  # noqa: E402
    build_retrieval_plan,
    parse_filter_args,
    parse_filters_json,
    retrieve_personas,
)

DEFAULT_JOBS_DIR = REPO_ROOT / "configs" / "jobs" / "application-task-job-recipe"
_EXECUTION_MODES = frozenset({"auto", "force_docker", "smoke"})


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "application-job"


def _default_job_name(
    *,
    task: str,
    stratify_fields: list[str],
    sample_size: int,
    execution_mode: str,
) -> str:
    task_slug = _slug(Path(task).name)
    mode_suffix = "" if execution_mode == "auto" else f"-{execution_mode}"
    if stratify_fields:
        dim_slug = "-".join(_slug(field.split(".")[-1]) for field in stratify_fields)
        return f"{task_slug}{mode_suffix}-{dim_slug}-n{sample_size}"
    return f"{task_slug}{mode_suffix}-n{sample_size}"


def _format_run_env_comment(
    exports: list[tuple[str, str]],
    *,
    model_name: str,
    sample_size: int,
) -> str:
    primary_exports = export_hint_lines(model_name)
    needs_openai_sut = any(name == "MATRIX_CHATBOT_TASK_PATH" for name, _ in exports)
    openai_already = any("OPENAI_API_KEY" in line for line in primary_exports)
    lines = ["# Run (after exporting API keys):"]
    lines.extend(f"#   {hint}" for hint in primary_exports)
    if needs_openai_sut and not openai_already:
        lines.append("#   export OPENAI_API_KEY=...   # user-sim chatbot/SUT default")
    for name, value in exports:
        lines.append(f"#   export {name}={value}")
    lines.append("#   uv run matraix run -c <this-file>")
    lines.append("#")
    for line in format_credential_preflight(
        model_name,
        extra_env_hints=(
            [("OPENAI_API_KEY", "user-sim chatbot/SUT default")]
            if needs_openai_sut and not openai_already
            else None
        ),
    ):
        lines.append(f"# {line}")
    lines.append(f"# Expected logical completions: {sample_size} (1 per persona)")
    lines.append("#")
    return "\n".join(lines) + "\n"


def _resolve_auto_launch(
    *,
    task_path: str,
    execution_mode: str,
    agent_name: str | None,
    repo_root: Path,
) -> tuple[str, str]:
    ensure_application_script_imports()
    from backend.service.harbor_job_service import resolve_agent_name, resolve_trial_profile

    trial_profile = resolve_trial_profile(
        task_path,
        mode=execution_mode,
        repo_root=repo_root,
    )
    agent = resolve_agent_name(
        task_path,
        repo_root=repo_root,
        explicit=agent_name,
        mode=execution_mode,
        trial_profile=trial_profile,
    )
    return trial_profile, agent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task",
        required=True,
        help="Application task path (e.g. application/tasks/example-survey_product-feedback)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Number of personas / trials (default: strategy sampleSize, else 1)",
    )
    parser.add_argument(
        "--sample-size-per-value-group",
        type=int,
        default=None,
        help="Stratified per-cell quota (sampling.allocation=perCell / sampling.perCell)",
    )
    parser.add_argument(
        "--stratified-allocation",
        choices=["perCell", "proportional", "equalTotal"],
        default=None,
        help="Stratified allocation strategy (default: from persona_strategy.json)",
    )
    parser.add_argument(
        "--persona-ids",
        nargs="*",
        default=[],
        metavar="ID",
        help="Explicit persona ids. Skips pool retrieval / strategy sampling.",
    )
    parser.add_argument(
        "--stratify",
        action="append",
        default=[],
        metavar="FIELD",
        help=(
            "Stratify sampling by persona field(s). Repeat or comma-separate. "
            "When omitted, task persona_strategy.json sampling.fields apply if present."
        ),
    )
    parser.add_argument(
        "--no-stratify",
        action="store_true",
        help="Ignore strategy sampling.fields (random sample within filters).",
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help=f"Persona dataset / pool (default: strategy pool, else {DEFAULT_DATASET})",
    )
    parser.add_argument(
        "--sources",
        nargs="*",
        default=None,
        metavar="SOURCE",
        help="Restrict to persona sources (e.g. wiki amazon). Default: strategy sources.",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        dest="filters",
        metavar="DIM=VALUE",
        help=(
            "Dimension filter, e.g. --filter age_bracket=25-34 "
            "or --filter life_stage=Mid-life,Early career. Repeatable."
        ),
    )
    parser.add_argument(
        "--filters-json",
        default=None,
        help='JSON object of dimension filters, e.g. \'{"age_bracket":["25-34"]}\'',
    )
    parser.add_argument(
        "--strategy",
        default=None,
        metavar="PATH",
        help="Optional persona_strategy.json path (default: <task>/persona_strategy.json)",
    )
    parser.add_argument(
        "--no-strategy",
        action="store_true",
        help="Do not load task persona_strategy.json defaults.",
    )
    parser.add_argument(
        "--cohort-id",
        default=None,
        help="Launch from a saved Playground cohort id (frozen or recipe).",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed (default: strategy seed, else 42)")
    parser.add_argument(
        "--execution-mode",
        choices=sorted(_EXECUTION_MODES),
        default="auto",
        help=(
            "Harbor execution mode. 'auto' picks native host survey/chat profiles when "
            "applicable (default: auto)."
        ),
    )
    parser.add_argument(
        "--cua-backend",
        default=None,
        help="CUA backend override (e.g. macos, ios, docker) when execution-mode is auto.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Job basename for output YAML (default: derived from task + stratify fields)",
    )
    parser.add_argument(
        "--job-name",
        default=None,
        help="Harbor job_name / jobs/<job_name>/ directory (default: same as --name)",
    )
    parser.add_argument(
        "--agent-name",
        default=None,
        help="Override Harbor agent (default: derived from task + execution mode)",
    )
    parser.add_argument("--model-name", default="anthropic/claude-sonnet-4-6")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output job YAML (default: configs/jobs/application-task-job-recipe/<name>.yaml)",
    )
    args = parser.parse_args()

    ensure_application_script_imports()

    try:
        cli_filters = parse_filter_args(args.filters)
        cli_filters.update(parse_filters_json(args.filters_json))
    except (ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    explicit_stratify = parse_stratify_field_args(args.stratify)
    if args.no_stratify:
        explicit_stratify = []

    persona_ids = [value.strip() for value in args.persona_ids if value.strip()]
    if persona_ids and (explicit_stratify or args.filters or args.filters_json or args.sources):
        parser.error("--persona-ids cannot be combined with --stratify / --filter / --sources")
    if persona_ids and args.cohort_id:
        parser.error("--persona-ids cannot be combined with --cohort-id")
    if args.no_strategy and args.strategy:
        parser.error("use either --strategy or --no-strategy, not both")

    try:
        plan = build_retrieval_plan(
            task_path=args.task,
            repo_root=REPO_ROOT,
            default_pool=DEFAULT_DATASET,
            persona_ids=persona_ids,
            sample_size=args.sample_size,
            seed=args.seed,
            dataset=args.dataset,
            sources=args.sources,
            filters=cli_filters,
            stratify_fields=(
                []
                if args.no_stratify
                else (explicit_stratify if explicit_stratify else None)
            ),
            sample_size_per_value_group=args.sample_size_per_value_group,
            allocation=args.stratified_allocation,
            cohort_id=args.cohort_id,
            use_strategy=not args.no_strategy,
            strategy_path=args.strategy,
        )
        retrieved = retrieve_personas(plan, repo_root=REPO_ROOT, task_path=args.task)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    execution_mode = args.execution_mode
    trial_profile, resolved_agent = _resolve_auto_launch(
        task_path=args.task,
        execution_mode=execution_mode,
        agent_name=args.agent_name,
        repo_root=REPO_ROOT,
    )
    agent_name = args.agent_name or resolved_agent

    job_slug = args.name or _default_job_name(
        task=args.task,
        stratify_fields=retrieved.stratify_fields,
        sample_size=retrieved.sample_size,
        execution_mode=execution_mode,
    )
    job_name = args.job_name or job_slug

    spec: dict[str, object] = {
        "name": job_slug,
        "stratify_fields": [],  # already resolved to concrete ids
        "seed": retrieved.seed,
        "persona_pool": retrieved.persona_pool,
        "persona_ids": retrieved.persona_ids,
        "task": args.task,
        "execution_mode": execution_mode,
        "trial_profile": trial_profile,
        "agent": {
            "name": agent_name,
            "model_name": args.model_name,
        },
        "job": {
            "job_name": job_name,
            "jobs_dir": "jobs",
            "n_attempts": 1,
            "n_concurrent_trials": 1,
            "timeout_multiplier": 1.0,
        },
    }
    if args.cua_backend:
        spec["cua_backend"] = args.cua_backend

    if execution_mode == "force_docker" and not args.cua_backend:
        spec["job"]["environment"] = {"type": "docker", "delete": True}

    job_config = build_application_job_config(spec, repo_root=REPO_ROOT)
    meta = job_config.pop("_job_meta")
    meta.update(
        {
            "retrieval": {
                "pool": retrieved.persona_pool,
                "matchedCount": retrieved.matched_count,
                "sources": retrieved.sources,
                "dimensionFilters": retrieved.dimension_filters,
                "fields": retrieved.stratify_fields,
                "cohortId": retrieved.cohort_id,
                "strategyPath": retrieved.strategy_path,
            }
        }
    )

    if args.cua_backend:
        from matraix.application_job import resolve_job_environment

        job_config["environment"] = resolve_job_environment(
            execution_mode=execution_mode,
            trial_profile=trial_profile,
            cua_backend=args.cua_backend,
        )

    out_path = args.out
    if out_path is None:
        DEFAULT_JOBS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEFAULT_JOBS_DIR / f"{job_slug}.yaml"
    elif not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    run_env_exports = collect_run_env_exports(
        trial_profile=trial_profile,
        task_path=args.task,
        repo_root=REPO_ROOT,
    )
    stratify_line = (
        ", ".join(retrieved.stratify_fields)
        if retrieved.stratify_fields
        else "none (filtered / random sample)"
    )
    filter_bits = []
    if retrieved.sources:
        filter_bits.append("sources=" + ",".join(retrieved.sources))
    if retrieved.dimension_filters:
        filter_bits.append(
            "filters="
            + ";".join(
                f"{key}:{'|'.join(vals)}"
                for key, vals in sorted(retrieved.dimension_filters.items())
            )
        )
    if retrieved.cohort_id:
        filter_bits.append(f"cohort={retrieved.cohort_id}")
    if retrieved.strategy_path:
        filter_bits.append(f"strategy={retrieved.strategy_path}")
    retrieval_line = (" | ".join(filter_bits)) if filter_bits else "none"
    header = (
        f"# Generated by application/scripts/generate_application_job.py\n"
        f"# Task: {args.task}\n"
        f"# Execution mode: {execution_mode} | trial profile: {trial_profile}\n"
        f"# Agent: {agent_name} | harbor task: {job_config['tasks'][0]['path']}\n"
        f"# Stratify: {stratify_line} | "
        f"sample={meta['sample_size']} matched={retrieved.matched_count} "
        f"pool={retrieved.persona_pool} | seed={meta['seed']}\n"
        f"# Retrieval: {retrieval_line}\n"
        f"# Personas: {', '.join(meta['selected_persona_ids'])}\n"
        f"#\n"
        f"{_format_run_env_comment(run_env_exports, model_name=args.model_name, sample_size=meta['sample_size'])}"
    )
    out_path.write_text(
        header + yaml.safe_dump(job_config, sort_keys=False),
        encoding="utf-8",
    )

    sidecar = out_path.with_suffix(".meta.json")
    sidecar.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(
        f"Matched {retrieved.matched_count} personas; selected {meta['sample_size']}"
    )
    print(f"Pool: {retrieved.persona_pool}")
    if retrieved.strategy_path:
        print(f"Strategy: {retrieved.strategy_path}")
    print(f"Execution mode: {execution_mode} | trial profile: {trial_profile}")
    print(f"Agent: {agent_name} | harbor task: {job_config['tasks'][0]['path']}")
    print(f"Job: {out_path}")
    print(f"Meta: {sidecar}")
    print("Run:")
    primary_exports = export_hint_lines(args.model_name)
    needs_openai_sut = any(name == "MATRIX_CHATBOT_TASK_PATH" for name, _ in run_env_exports)
    openai_already = any("OPENAI_API_KEY" in line for line in primary_exports)
    for hint in primary_exports:
        print(f"  {hint}")
    if needs_openai_sut and not openai_already:
        print("  export OPENAI_API_KEY=...   # user-sim chatbot/SUT default")
    for name, value in run_env_exports:
        print(f"  export {name}={value}")
    print(f"  uv run matraix run -c {_display_path(out_path)}")
    print("Preflight:")
    for line in format_credential_preflight(
        args.model_name,
        extra_env_hints=(
            [("OPENAI_API_KEY", "user-sim chatbot/SUT default")]
            if needs_openai_sut and not openai_already
            else None
        ),
    ):
        print(f"  {line}")
    print(f"  Expected logical completions: {meta['sample_size']} (1 per persona)")


if __name__ == "__main__":
    main()
