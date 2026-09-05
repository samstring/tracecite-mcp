from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracecite_mcp import server
from tracecite_mcp.shell_projection import compact_shell_response


def test_host_pinned_session_absorbs_agent_session_churn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRACECITE_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("TRACECITE_MCP_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("TRACECITE_MCP_SESSION_ID", "host-investigation")

    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")

    first = server.tracecite_run("agent-1", str(source), "search target")
    repeated = server.tracecite_run("agent-2", str(source), "search target")

    assert first["mcp_session"]["session_id"] == "host-investigation"
    assert repeated["mcp_session"]["session_id"] == "host-investigation"
    assert repeated["coverage"]["new_evidence"] == 0
    assert repeated["coverage"]["repeated_evidence"] >= 1


def test_shell_projection_keeps_all_pointers_without_repeating_identity() -> None:
    digest = "a" * 64
    evidence = [
        {
            "uri": f"evidence://sha256/{digest}#L{i}",
            "source_path": "/tmp/evidence/logs.jsonl",
            "sha256": digest,
            "start_line": i,
            "end_line": i,
            "label": f"ERROR service=route request={i} " + ("x" * 500),
        }
        for i in range(1, 11)
    ]
    payload = {
        "status": "ok",
        "coverage": {
            "complete": False,
            "selection_explicit": True,
            "match_records": 10,
            "evidence_returned": 10,
            "new_evidence": 10,
            "repeated_evidence": 0,
        },
        "evidence": evidence,
        "data": {
            "program": "search ERROR | head 10",
            "source_version": "version-1",
        },
        "mcp_session": {"session_id": "investigation", "revision": 1},
    }

    result = compact_shell_response(payload, display_source="/tmp/evidence/logs.jsonl")
    encoded = json.dumps(result, ensure_ascii=False)

    assert len(result["evidence"]) == 10
    assert result["source_sha256"] == digest
    assert all("sha256" not in row for row in result["evidence"])
    assert all("uri" not in row for row in result["evidence"])
    assert all("materialize_source" not in row for row in result["evidence"])
    assert all(len(row.get("preview", "")) <= 180 for row in result["evidence"])
    assert len(encoded.encode("utf-8")) < 8_000
