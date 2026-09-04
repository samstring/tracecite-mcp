from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


EXPECTED_TOOLS = {
    "tracecite_run",
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
    missing = tmp_path / "guessed-app.log"

    async def run() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tracecite_mcp.server"],
            cwd=str(tmp_path),
            env={
                "TRACECITE_MCP_ALLOWED_ROOTS": str(tmp_path),
                "TRACECITE_MCP_STATE_DIR": str(tmp_path / "state"),
                "TRACECITE_EVIDENCE_FILES": str(source),
                "TRACECITE_EVIDENCE_MAX_TOKENS": "12000",
                "TRACECITE_EVIDENCE_MAX_BYTES": str(64 * 1024),
            },
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                listed = await session.list_tools()
                assert {tool.name for tool in listed.tools} == EXPECTED_TOOLS

                recovery = await session.call_tool(
                    "tracecite_run",
                    arguments={
                        "session_id": "stdio-smoke",
                        "source": str(missing),
                        "program": "search target",
                    },
                )
                assert recovery.is_error is False
                assert recovery.structured_content is not None
                assert recovery.structured_content["status"] == "error"
                assert recovery.structured_content["error_code"] == "source_not_found"
                assert recovery.structured_content["available_sources"] == [str(source.resolve())]

                arguments = {
                    "session_id": "stdio-smoke",
                    "source": str(source),
                    "program": "search target",
                    "segmenter": "rawtext",
                }
                first = await session.call_tool("tracecite_run", arguments=arguments)
                assert first.is_error is False
                assert first.structured_content is not None
                assert first.structured_content["status"] == "ok"
                assert first.structured_content["evidence"]
                assert first.structured_content["mcp_session"]["session_id"] == "stdio-smoke"

                repeated = await session.call_tool("tracecite_run", arguments=arguments)
                assert repeated.is_error is False
                assert repeated.structured_content is not None
                assert repeated.structured_content["coverage"]["new_evidence"] == 0
                assert repeated.structured_content["coverage"]["repeated_evidence"] >= 1

                aggregate = await session.call_tool(
                    "tracecite_aggregate",
                    arguments={
                        "session_id": "stdio-smoke",
                        "source": str(source),
                        "query": "target",
                        "operation": "count",
                    },
                )
                assert aggregate.is_error is False
                assert aggregate.structured_content is not None
                assert aggregate.structured_content["operation"] == "evidence_shell"
                assert aggregate.structured_content["data"]["aggregate"]["count"] == 1

    asyncio.run(run())
