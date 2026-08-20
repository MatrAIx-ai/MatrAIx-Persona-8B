"""Unit tests for web-agent mid-run trajectory flush helpers."""

from __future__ import annotations

import base64
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "environment" / "agents"))
sys.path.insert(0, str(REPO / "environment" / "runtime"))

from matraix.agents.installed import browser_use_runner as bu  # noqa: E402
from matraix.agents.installed import cocoa_runner as cocoa  # noqa: E402


def _install_openhands_stubs() -> None:
    """Allow importing openhands_sdk_runner without the real SDK installed."""
    if "openhands.sdk" in sys.modules and hasattr(sys.modules["openhands.sdk"], "Tool"):
        return

    def _mod(name: str) -> types.ModuleType:
        module = types.ModuleType(name)
        sys.modules[name] = module
        return module

    openhands = _mod("openhands")
    sdk = _mod("openhands.sdk")
    context = _mod("openhands.sdk.context")
    event = _mod("openhands.sdk.event")
    tools = _mod("openhands.tools")
    file_editor = _mod("openhands.tools.file_editor")
    task_tracker = _mod("openhands.tools.task_tracker")
    terminal = _mod("openhands.tools.terminal")

    class _Tool:
        def __init__(self, name: str):
            self.name = name

    class _Named:
        name = "stub"

    def get_logger(_name: str | None = None):
        return SimpleNamespace(debug=lambda *a, **k: None)

    sdk.LLM = object
    sdk.Agent = object
    sdk.AgentContext = object
    sdk.Conversation = object
    sdk.Tool = _Tool
    sdk.get_logger = get_logger
    context.Skill = object
    event.ActionEvent = type("ActionEvent", (), {})
    event.MessageEvent = type("MessageEvent", (), {})
    event.ObservationEvent = type("ObservationEvent", (), {})
    event.TokenEvent = type("TokenEvent", (), {})
    file_editor.FileEditorTool = _Named
    task_tracker.TaskTrackerTool = _Named
    terminal.TerminalTool = _Named

    openhands.sdk = sdk
    tools.file_editor = file_editor
    tools.task_tracker = task_tracker
    tools.terminal = terminal


_install_openhands_stubs()
from harbor.agents.installed import openhands_sdk_runner as oh  # noqa: E402


def test_browser_use_allow_lists_mounted_task_inputs(tmp_path):
    input_dir = tmp_path / "input"
    nested_dir = input_dir / "nested"
    nested_dir.mkdir(parents=True)
    (input_dir / "context.md").write_text("Task context", encoding="utf-8")
    (nested_dir / "options.json").write_text("{}", encoding="utf-8")

    assert bu.available_task_input_paths(input_dir) == [
        "input/context.md",
        (input_dir / "context.md").as_posix(),
        "input/nested/options.json",
        (nested_dir / "options.json").as_posix(),
    ]


def test_browser_use_flush_writes_atomic_trajectory(tmp_path):
    history = SimpleNamespace(
        history=[],
        usage=None,
        final_result=lambda: None,
        is_done=lambda: False,
        is_successful=lambda: False,
        urls=lambda: [],
        action_names=lambda: [],
    )
    trajectory_path = tmp_path / "trajectory.json"
    payload = bu.flush_browser_use_trajectory(
        history,
        instruction="pick a laptop",
        model_name="anthropic/claude-haiku",
        trajectory_path=trajectory_path,
        agent_version="test",
        session_id="sess-1",
    )
    assert trajectory_path.is_file()
    assert not trajectory_path.with_suffix(".json.tmp").exists()
    on_disk = json.loads(trajectory_path.read_text(encoding="utf-8"))
    assert on_disk["session_id"] == "sess-1"
    assert on_disk["steps"][0]["source"] == "user"
    assert payload["agent"]["name"] == "browser-use"


def test_cocoa_partial_flush_saves_screenshot(tmp_path):
    png = base64.b64encode(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
        )
    ).decode("ascii")
    trajectory_path = tmp_path / "trajectory.json"
    result = {
        "conversation": [
            {
                "role": "assistant",
                "content": "Thought: looking",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {"name": "browser_click", "arguments": "{}"},
                    }
                ],
            }
        ],
        "execution_trace": [
            {
                "action": {"action_type": "browser_click", "tool_call_id": "call-1"},
                "feedback": {"message": "clicked", "done": False},
            }
        ],
        "visualization_data": {
            "iterations": [
                {
                    "actions": [
                        {
                            "action": {"tool_call_id": "call-1"},
                            "screenshot": png,
                        }
                    ]
                }
            ]
        },
        "status": "running",
    }
    traj = cocoa.cocoa_to_atif(
        result,
        instruction="choose a plan",
        model_name="anthropic/claude",
        trajectory_path=trajectory_path,
        agent_version="test",
        session_id="cocoa-sess",
    )
    assert trajectory_path.is_file()
    assert (tmp_path / "images" / "step_001.png").is_file()
    agent_step = next(s for s in traj["steps"] if s["source"] == "agent")
    assert isinstance(agent_step["message"], list)
    assert any(
        part.get("type") == "image" and part["source"]["path"].startswith("images/")
        for part in agent_step["message"]
        if isinstance(part, dict)
    )


def test_openhands_build_trajectory_attaches_screenshot():
    events = [
        {"type": "user_message", "content": "go browse", "timestamp": "t0"},
        {
            "type": "assistant_message",
            "content": "",
            "timestamp": "t1",
            "tool_calls": [
                {
                    "id": "c1",
                    "name": "browser_navigate",
                    "arguments": {"url": "https://x"},
                }
            ],
        },
        {
            "type": "tool_result",
            "tool_call_id": "c1",
            "content": "ok",
            "timestamp": "t2",
            "screenshot_rel": "images/step_001.png",
        },
    ]
    traj = oh.build_trajectory(events, {"prompt_tokens": 1}, "test-model")
    agent_step = next(s for s in traj["steps"] if s.get("source") == "agent")
    assert isinstance(agent_step["message"], list)
    assert agent_step["observation"]["results"][0]["source_call_id"] == "c1"


def test_openhands_save_screenshot_b64(tmp_path):
    png = base64.b64encode(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
        )
    ).decode("ascii")
    rel = oh._save_screenshot_b64(png, tmp_path / "images", 2)
    assert rel == "images/step_002.png"
    assert (tmp_path / "images" / "step_002.png").is_file()
