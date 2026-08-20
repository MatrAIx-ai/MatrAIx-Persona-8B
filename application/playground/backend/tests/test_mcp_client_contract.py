"""Contract test for the pinned ``mcp`` SDK used by the chat MCP sidecar client.

The rest of the suite exercises ``mcp_call_client`` against stand-in objects, so
it cannot catch the SDK moving a symbol or renaming a field. This one resolves
``MCP_CLIENT_REQUIREMENT`` the same way the environment does and runs the client
helper against a real ``CallToolResult``, which is what makes a version bump
fail loudly instead of at trial time. It needs ``uvx`` and network access, and
skips when ``uvx`` is unavailable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from playground.harbor import mcp_call_client
from playground.harbor.chat_mcp_session import MCP_CLIENT_REQUIREMENT

pytestmark = pytest.mark.skipif(
    shutil.which("uvx") is None,
    reason="uvx is required to resolve the pinned mcp SDK",
)

_PROBE = """
import importlib.metadata
import importlib.util
import json
import sys

import mcp.types as types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

spec = importlib.util.spec_from_file_location("mcp_call_client", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

result = types.CallToolResult(
    content=[types.TextContent(type="text", text="hi")],
    is_error=True,
)
print(
    json.dumps(
        {
            "version": importlib.metadata.version("mcp"),
            "session": ClientSession.__name__,
            "transport": streamable_http_client.__name__,
            "payload": module.payload_from_result(result),
        }
    )
)
"""


def test_pinned_mcp_sdk_satisfies_the_sidecar_client_contract() -> None:
    client_path = Path(mcp_call_client.__file__)
    completed = subprocess.run(
        [
            "uvx",
            "--with",
            MCP_CLIENT_REQUIREMENT,
            "python3",
            "-c",
            _PROBE,
            str(client_path),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )

    assert completed.returncode == 0, completed.stderr
    probe = json.loads(completed.stdout.strip().splitlines()[-1])
    assert probe["version"] == MCP_CLIENT_REQUIREMENT.split("==", 1)[1]
    assert probe["session"] == "ClientSession"
    assert probe["transport"] == "streamable_http_client"
    assert probe["payload"] == {"text": "hi", "isError": True}
