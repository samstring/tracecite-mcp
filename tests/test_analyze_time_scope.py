from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tracecite_mcp import server


@pytest.fixture(autouse=True)
def isolate_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRACECITE_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("TRACECITE_MCP_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("TRACECITE_EVIDENCE_MAX_TOKENS", "12000")
    monkeypatch.setenv("TRACECITE_EVIDENCE_MAX_BYTES", str(64 * 1024))


def _tool(name: str):
    tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}
    return tools[name]


def test_analyze_schema_exposes_mechanical_time_scope() -> None:
    schema = _tool("tracecite_analyze").input_schema
    text = str(schema)
    assert "last" in text
    assert "since" in text
    assert "until" in text
    for forbidden in (
        "max_evidence",
        "max_evidence_tokens",
        "max_evidence_bytes",
        "snapshot",
        "source_mode",
    ):
        assert forbidden not in text


def test_analyze_applies_absolute_time_scope_to_whole_batch(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    rows = [
        {"timestamp": "2026-09-05T10:00:00Z", "service": "edge", "status": 200},
        {"timestamp": "2026-09-05T10:05:00Z", "service": "route", "status": 503},
        {"timestamp": "2026-09-05T10:10:00Z", "service": "route", "status": 500},
        {"timestamp": "2026-09-05T10:20:00Z", "service": "auth", "status": 503},
    ]
    source.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = server.tracecite_analyze(
        "scope-session",
        str(source),
        [
            {"name": "failures", "program": "where status >= 500 | count"},
            {"name": "services", "program": "where status >= 500 | group service"},
        ],
        since="2026-09-05T10:04:00Z",
        until="2026-09-05T10:15:00Z",
    )

    assert result["status"] == "ok"
    assert result["data"]["time_scope"] == {
        "last": None,
        "since": "2026-09-05T10:04:00Z",
        "until": "2026-09-05T10:15:00Z",
    }
    outputs = {item["name"]: item for item in result["data"]["outputs"]}
    assert outputs["failures"]["aggregate"]["count"] == 2
    assert outputs["services"]["aggregate"]["groups"] == [
        {"key": "route", "count": 2}
    ]
