"""Single MCP tool call, executed inside the Harbor environment.

Uploaded into the environment and run against the ``mcp`` release pinned in
``chat_mcp_session.MCP_CLIENT_REQUIREMENT``. ``mcp`` is imported lazily because
this module must also import on hosts that do not have the SDK installed.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Dict


def payload_from_result(result: Any) -> Dict[str, Any]:
    """Flatten an MCP ``CallToolResult`` into the sidecar stdout contract."""
    chunks: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            chunks.append(str(text))
    # Result types other than CallToolResult carry no error flag.
    return {"text": "".join(chunks), "isError": bool(getattr(result, "is_error", False))}


async def call_tool(
    mcp_url: str,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(mcp_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return payload_from_result(result)


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: mcp_call_client.py MCP_URL TOOL_NAME JSON_ARGUMENTS", file=sys.stderr)
        return 2
    payload = asyncio.run(call_tool(argv[1], argv[2], json.loads(argv[3])))
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
