#!/usr/bin/env python3
"""Run browser-use inside a Harbor task container."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

OUTPUT_DIR = Path("/app/output")
TASK_INPUT_DIR = Path("/app/input")

_IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _create_llm(model: str):
    provider, _, bare = model.partition("/")
    bare = bare or model

    if provider in ("anthropic", "") and (
        bare.startswith("claude") or provider == "anthropic"
    ):
        from browser_use import ChatAnthropic

        return ChatAnthropic(model=bare)

    from browser_use import ChatOpenAI

    if provider == "dashscope":
        api_key = (
            os.environ.get("DASHSCOPE_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or ""
        ).strip()
        base_url = (
            os.environ.get("DASHSCOPE_API_BASE")
            or os.environ.get("LLM_BASE_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).strip()
        return ChatOpenAI(model=bare, api_key=api_key, base_url=base_url)

    return ChatOpenAI(model=bare)


def available_task_input_paths(input_dir: Path = TASK_INPUT_DIR) -> list[str]:
    """Return mounted task inputs that browser-use may safely read.

    Harbor mounts task-owned inputs under ``/app/input`` while browser-use
    limits file reads to explicitly allowed paths outside its output sandbox.
    Include both the canonical mount path and the task-facing ``input/...``
    spelling used by task instructions.
    """
    if not input_dir.is_dir():
        return []

    available: list[str] = []
    for path in sorted(
        candidate for candidate in input_dir.rglob("*") if candidate.is_file()
    ):
        relative = path.relative_to(input_dir)
        available.extend(
            [
                (Path("input") / relative).as_posix(),
                path.as_posix(),
            ]
        )
    return available


def promote_browser_use_outputs(agent: Any) -> list[str]:
    """Copy browser-use sandbox files into Playground /app/output."""
    promoted: list[str] = []
    file_system = getattr(agent, "file_system", None)
    if file_system is None:
        return promoted

    data_dir = file_system.get_dir()
    if not data_dir.is_dir():
        return promoted

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for src in data_dir.iterdir():
        if not src.is_file():
            continue
        dest = OUTPUT_DIR / src.name
        shutil.copy2(src, dest)
        promoted.append(str(dest))

    return promoted


def _media_type_for_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return _IMAGE_MEDIA_TYPES.get(suffix, "image/png")


def _copy_screenshot(
    screenshot_path: str | None, images_dir: Path, step_number: int
) -> str | None:
    if not screenshot_path:
        return None
    src = Path(screenshot_path)
    if not src.is_file():
        return None

    images_dir.mkdir(parents=True, exist_ok=True)
    dest = images_dir / f"step_{step_number:03d}{src.suffix.lower() or '.png'}"
    shutil.copy2(src, dest)
    return f"images/{dest.name}"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically rewrite JSON so the host can poll a growing trajectory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def flush_browser_use_trajectory(
    history: Any,
    *,
    instruction: str,
    model_name: str,
    trajectory_path: Path,
    agent_version: str = "unknown",
    session_id: str | None = None,
    promoted_outputs: list[str] | None = None,
) -> dict[str, Any]:
    """Convert history → ATIF and persist under the bind-mounted agent logs dir."""
    trajectory = history_to_atif(
        history,
        instruction=instruction,
        model_name=model_name,
        trajectory_path=trajectory_path,
        agent_version=agent_version,
        session_id=session_id,
        promoted_outputs=promoted_outputs,
    )
    _atomic_write_json(trajectory_path, trajectory)
    return trajectory


def _action_name_and_args(action: Any) -> tuple[str, dict[str, Any]]:
    action_dump = action.model_dump(exclude_none=True, mode="json")
    if len(action_dump) == 1:
        name, args = next(iter(action_dump.items()))
        if isinstance(args, dict):
            return name, args
        return name, {"value": args}
    return "unknown", action_dump


def _step_timestamp(metadata: Any) -> str | None:
    if metadata is None:
        return None
    start = getattr(metadata, "step_start_time", None)
    if start is None:
        return None
    return datetime.fromtimestamp(float(start), tz=UTC).isoformat()


def _usage_value(usage: Any, *names: str) -> int | float | None:
    if usage is None:
        return None
    for name in names:
        value = getattr(usage, name, None)
        if value is not None:
            return value
    return None


def history_to_atif(
    history: Any,
    *,
    instruction: str,
    model_name: str,
    trajectory_path: Path,
    agent_version: str = "unknown",
    session_id: str | None = None,
    promoted_outputs: list[str] | None = None,
) -> dict[str, Any]:
    """Convert browser-use AgentHistoryList to ATIF-v1.6 for the Playground viewer."""
    images_dir = trajectory_path.parent / "images"
    steps: list[dict[str, Any]] = []
    step_id = 1

    steps.append(
        {
            "step_id": step_id,
            "timestamp": None,
            "source": "user",
            "message": instruction,
        }
    )
    step_id += 1

    history_items = getattr(history, "history", None) or []
    for hist_idx, item in enumerate(history_items):
        model_output = getattr(item, "model_output", None)
        results = getattr(item, "result", None) or []
        state = getattr(item, "state", None)
        metadata = getattr(item, "metadata", None)

        message_lines: list[str] = []
        reasoning: str | None = None
        tool_calls: list[dict[str, Any]] = []
        observation_results: list[dict[str, Any]] = []

        if model_output is not None:
            if model_output.evaluation_previous_goal:
                message_lines.append(f"Eval: {model_output.evaluation_previous_goal}")
            if model_output.memory:
                message_lines.append(f"Memory: {model_output.memory}")
            if model_output.next_goal:
                message_lines.append(f"Next goal: {model_output.next_goal}")
            reasoning = model_output.thinking

            screenshot_path = getattr(state, "screenshot_path", None) if state else None
            screenshot_rel = _copy_screenshot(screenshot_path, images_dir, hist_idx + 1)

            for action_idx, action in enumerate(model_output.action):
                func_name, arguments = _action_name_and_args(action)
                call_id = f"step{hist_idx + 1}_action{action_idx + 1}"
                tool_calls.append(
                    {
                        "tool_call_id": call_id,
                        "function_name": func_name,
                        "arguments": arguments,
                    }
                )

                if action_idx < len(results):
                    result = results[action_idx]
                    obs_parts: list[str] = []
                    extracted = getattr(result, "extracted_content", None)
                    if extracted:
                        obs_parts.append(str(extracted))
                    error = getattr(result, "error", None)
                    if error:
                        obs_parts.append(f"Error: {error}")
                    memory = getattr(result, "long_term_memory", None)
                    if memory:
                        obs_parts.append(str(memory))
                    content = (
                        "\n".join(obs_parts)
                        if obs_parts
                        else f"Action '{func_name}' executed"
                    )
                    observation_results.append(
                        {
                            "source_call_id": call_id,
                            "content": content,
                        }
                    )

            text_message = "\n".join(message_lines) if message_lines else "[agent step]"
            if screenshot_rel:
                message: str | list[dict[str, Any]] = [
                    {"type": "text", "text": text_message},
                    {
                        "type": "image",
                        "source": {
                            "media_type": _media_type_for_path(screenshot_rel),
                            "path": screenshot_rel,
                        },
                    },
                ]
            else:
                message = text_message
        else:
            message = "[agent step]"

        agent_step: dict[str, Any] = {
            "step_id": step_id,
            "timestamp": _step_timestamp(metadata),
            "source": "agent",
            "model_name": model_name,
            "message": message,
        }
        if reasoning:
            agent_step["reasoning_content"] = reasoning
        if tool_calls:
            agent_step["tool_calls"] = tool_calls
        if observation_results:
            agent_step["observation"] = {"results": observation_results}
        steps.append(agent_step)
        step_id += 1

    usage = getattr(history, "usage", None)
    final_metrics = {
        "total_prompt_tokens": _usage_value(
            usage, "total_prompt_tokens", "prompt_tokens"
        ),
        "total_completion_tokens": _usage_value(
            usage, "total_completion_tokens", "completion_tokens"
        ),
        "total_cached_tokens": _usage_value(
            usage, "total_cached_tokens", "cached_tokens"
        ),
        "total_cost_usd": _usage_value(usage, "total_cost", "cost_usd"),
        "total_steps": len(steps),
    }

    browser_use_summary = {
        "final_result": history.final_result() if history else None,
        "is_done": history.is_done() if history else False,
        "is_successful": history.is_successful() if history else False,
        "urls": history.urls() if history else [],
        "action_names": history.action_names() if history else [],
        "promoted_outputs": promoted_outputs or [],
    }

    return {
        "schema_version": "ATIF-v1.6",
        "session_id": session_id or str(uuid4()),
        "agent": {
            "name": "browser-use",
            "version": agent_version,
            "model_name": model_name,
        },
        "steps": steps,
        "final_metrics": final_metrics,
        "extra": {"browser_use": browser_use_summary},
    }


async def _run(args: argparse.Namespace) -> int:
    from browser_use import Agent, Browser

    extend = os.environ.get("PERSONA_SYSTEM", "").strip() or None
    max_steps = int(os.environ.get("MAX_STEPS", "50"))
    agent_version = os.environ.get("BROWSER_USE_VERSION", "unknown")

    llm = _create_llm(args.model)

    # Some sites' WAFs reject Chromium's default ``HeadlessChrome`` User-Agent
    # with 403 before any page JS runs. Presenting a normal Chrome UA is enough
    # to pass (the block is on the UA header, not the IP). Both the UA and
    # headless mode are overridable via env for debugging.
    headless = (os.environ.get("BROWSER_USE_HEADLESS", "1").strip().lower()
                not in ("0", "false", "no"))
    user_agent = os.environ.get("BROWSER_USE_USER_AGENT", "").strip() or (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    browser_kwargs: dict = {"headless": headless}
    if user_agent:
        browser_kwargs["user_agent"] = user_agent
    browser = Browser(**browser_kwargs)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    agent_kwargs: dict = {
        "task": args.instruction,
        "llm": llm,
        "browser": browser,
        "file_system_path": str(OUTPUT_DIR),
    }
    task_input_paths = available_task_input_paths()
    if task_input_paths:
        agent_kwargs["available_file_paths"] = task_input_paths
    if extend:
        agent_kwargs["extend_system_message"] = extend

    trajectory_path = Path(args.trajectory_path)
    trajectory_path.parent.mkdir(parents=True, exist_ok=True)
    session_id = str(uuid4())

    async def _on_step_end(agent_obj: Any) -> None:
        """Flush screenshots + trajectory after each browser-use step."""
        try:
            flush_browser_use_trajectory(
                getattr(agent_obj, "history", None),
                instruction=args.instruction,
                model_name=args.model,
                trajectory_path=trajectory_path,
                agent_version=agent_version,
                session_id=session_id,
            )
        except Exception as exc:  # noqa: BLE001 — live flush must not kill the run
            print(f"[browser-use] live trajectory flush failed: {exc}", flush=True)

    agent = Agent(**agent_kwargs)
    try:
        history = await agent.run(max_steps=max_steps, on_step_end=_on_step_end)
    except TypeError:
        # Older browser-use: flush via register_new_step_callback instead.
        agent_ref: dict[str, Any] = {}

        async def _legacy_new_step(_state: Any, _output: Any, _n: int) -> None:
            current = agent_ref.get("agent")
            if current is not None:
                await _on_step_end(current)

        agent_kwargs["register_new_step_callback"] = _legacy_new_step
        agent = Agent(**agent_kwargs)
        agent_ref["agent"] = agent
        history = await agent.run(max_steps=max_steps)

    promoted_outputs = promote_browser_use_outputs(agent)
    flush_browser_use_trajectory(
        history,
        instruction=args.instruction,
        model_name=args.model,
        trajectory_path=trajectory_path,
        agent_version=agent_version,
        session_id=session_id,
        promoted_outputs=promoted_outputs,
    )

    if history and not history.is_successful():
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--trajectory-path", required=True)
    args = parser.parse_args()

    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
