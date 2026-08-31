from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


EXPECTED_TOOLS = {
    "tracecite_retrieve",
    "tracecite_materialize",
    "tracecite_replay",
    "tracecite_aggregate",
    "tracecite_traverse",
    "tracecite_verify",
}


def test_stdio_protocol_round_trip_uses_real_mcp_client(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")

    async def run() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tracecite_mcp.server"],
            cwd=str(tmp_path),
            env={
                "TRACECITE_MCP_ALLOWED_ROOTS": str(tmp_path),
                "TRACECITE_MCP_STATE_DIR": str(tmp_path / "state"),
            },
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                listed = await session.list_tools()
                assert {tool.name for tool in listed.tools} == EXPECTED_TOOLS

                arguments = {
                    "session_id": "stdio-smoke",
                    "target": {
                        "kind": "query",
                        "source": str(source),
                        "query": "target",
                        "segmenter": "rawtext",
                    },
                }
                first = await session.call_tool("tracecite_retrieve", arguments=arguments)
                assert first.is_error is False
                assert first.structured_content is not None
                assert first.structured_content["status"] == "ok"
                assert first.structured_content["evidence"]
                assert first.structured_content["mcp_session"]["session_id"] == "stdio-smoke"

                repeated = await session.call_tool("tracecite_retrieve", arguments=arguments)
                assert repeated.is_error is False
                assert repeated.structured_content is not None
                assert repeated.structured_content["coverage"]["new_evidence"] == 0
                assert repeated.structured_content["coverage"]["repeated_evidence"] >= 1
                assert (
                    repeated.structured_content["mcp_session"]["revision"]
                    > first.structured_content["mcp_session"]["revision"]
                )

                aggregate = await session.call_tool(
                    "tracecite_aggregate",
                    arguments={
                        "source": str(source),
                        "query": "target",
                        "operation": "count",
                    },
                )
                assert aggregate.is_error is False
                assert aggregate.structured_content is not None
                assert aggregate.structured_content["operation"] == "aggregate"
                assert aggregate.structured_content["data"]["count"] == 1

    asyncio.run(run())
