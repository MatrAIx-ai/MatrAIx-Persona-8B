"""Tests for Harbor web trace screenshot URL attachment."""

from __future__ import annotations

import json
from pathlib import Path

from backend.service.harbor_web_trace import (
    attach_harbor_trace_screenshot_urls,
    latest_trial_screenshot_bytes,
    read_harbor_web_trace,
    resolve_trial_screenshot_path,
    screenshot_file_from_step,
)


def test_screenshot_file_from_step_reads_cocoa_message_image() -> None:
    step = {
        "source": "agent",
        "message": [
            {"type": "text", "text": "Thought: browse"},
            {
                "type": "image",
                "source": {"media_type": "image/png", "path": "images/step_001.png"},
            },
        ],
    }
    assert screenshot_file_from_step(step) == "images/step_001.png"


def test_screenshot_file_from_step_reads_observation_webp() -> None:
    step = {
        "observation": {
            "results": [
                {
                    "content": [
                        {
                            "type": "image",
                            "source": {"path": "screenshot_ep0.webp"},
                        }
                    ]
                }
            ]
        }
    }
    assert screenshot_file_from_step(step) == "screenshot_ep0.webp"


def test_attach_harbor_trace_screenshot_urls(tmp_path: Path) -> None:
    trace = {
        "events": [
            {"step": 1, "screenshotFile": "images/step_001.png"},
            {"step": 2, "screenshotUrl": "https://example.com/existing.webp"},
        ],
        "raw": {},
    }
    view = attach_harbor_trace_screenshot_urls(
        trace,
        job_name="job-1",
        trial_name="trial-0",
    )
    assert view is not None
    assert view["events"][0]["screenshotUrl"].endswith(
        "/api/harbor/jobs/job-1/trials/trial-0/screenshots/images/step_001.png"
    )
    assert view["events"][1]["screenshotUrl"] == "https://example.com/existing.webp"


def test_read_harbor_web_trace_from_cocoa_trial(tmp_path: Path) -> None:
    logs_dir = tmp_path / "agent"
    images_dir = logs_dir / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "step_001.png").write_bytes(b"png")
    (logs_dir / "trajectory.json").write_text(
        json.dumps(
            {
                "steps": [
                    {"source": "user", "message": "instruction"},
                    {
                        "source": "agent",
                        "message": [
                            {"type": "text", "text": "browse"},
                            {
                                "type": "image",
                                "source": {
                                    "media_type": "image/png",
                                    "path": "images/step_001.png",
                                },
                            },
                        ],
                        "tool_calls": [
                            {
                                "function_name": "browser_navigate",
                                "arguments": {"url": "https://books.toscrape.com/"},
                            }
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    trace = read_harbor_web_trace(
        logs_dir,
        job_name="pg-job",
        trial_name="trial-a",
    )
    assert len(trace["events"]) == 2
    agent_event = trace["events"][1]
    assert agent_event["source"] == "agent"
    assert agent_event["screenshotFile"] == "images/step_001.png"
    assert agent_event["screenshotUrl"].endswith("images/step_001.png")
    path = resolve_trial_screenshot_path(logs_dir, "images/step_001.png")
    assert path.is_file()


def test_screenshot_file_from_step_normalizes_absolute_images_path() -> None:
    step = {
        "source": "agent",
        "message": [
            {
                "type": "image",
                "source": {"path": "/sandbox/logs/images/step_009.png"},
            }
        ],
    }
    assert screenshot_file_from_step(step) == "images/step_009.png"


def test_latest_trial_screenshot_bytes(tmp_path: Path) -> None:
    trial = tmp_path / "trial"
    images = trial / "agent" / "images"
    images.mkdir(parents=True)
    older = images / "step_001.png"
    newer = images / "step_002.png"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")
    older.touch()
    import time

    time.sleep(0.02)
    newer.write_bytes(b"new")
    assert latest_trial_screenshot_bytes(trial) == b"new"
