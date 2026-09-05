from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracecite_mcp import server
from tracecite_mcp.projection import compact_response
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


def test_shell_projection_keeps_all_pointers_without_repeating_uri_text() -> None:
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
    assert all(row["sha256"] == digest for row in result["evidence"])
    assert all("uri" not in row for row in result["evidence"])
    assert all(row["materialize_source"] == "/tmp/evidence/logs.jsonl" for row in result["evidence"])
    assert all(len(row.get("preview", "")) <= 180 for row in result["evidence"])
    assert len(encoded.encode("utf-8")) < 8_000


def test_project_aggregate_transport_hoists_repeated_identity() -> None:
    digest = "b" * 64
    rows = [
        {
            "value": float(index),
            "uri": f"evidence://sha256/{digest}#L{880 + index}",
            "source": "/tmp/private/snapshot/metrics.jsonl",
            "sha256": digest,
            "start_line": 880 + index,
            "end_line": 880 + index,
        }
        for index in range(26)
    ]
    payload = {
        "status": "ok",
        "coverage": {"complete": True, "match_records": 26},
        "data": {
            "program": "lines 880 905 | project cpu",
            "aggregate": {"field": "cpu", "rows": rows, "row_total": 26},
            "source_version": "version-1",
        },
        "mcp_session": {"session_id": "investigation", "revision": 2},
    }

    result = compact_shell_response(payload, display_source="/tmp/evidence/metrics.jsonl")
    encoded = json.dumps(result, ensure_ascii=False)
    projected = result["data"]["aggregate"]["rows"]

    assert result["source_sha256"] == digest
    assert len(projected) == 26
    assert [row["value"] for row in projected] == [float(index) for index in range(26)]
    assert projected[0]["ref"] == "metrics.jsonl:L880"
    assert projected[-1]["ref"] == "metrics.jsonl:L905"
    assert all("uri" not in row and "source" not in row and "sha256" not in row for row in projected)
    assert len(encoded.encode("utf-8")) < 8_000


def test_materialize_structural_metadata_is_bounded_without_truncating_text() -> None:
    text = "line one\nline two\nline three\n"
    references = [
        {
            "kind": "trace-id",
            "key": "traceId",
            "value": f"trace-{index}",
            "visible_occurrences": 1,
            "visible_lines": list(range(1, 40)),
        }
        for index in range(40)
    ]
    relations = [
        {
            "kind": "parent-child",
            "relation": "parent",
            "relation_id": f"rel-{index}",
            "subject": f"span-{index}",
            "object": f"span-{index + 1}",
            "visible_lines": list(range(1, 40)),
        }
        for index in range(40)
    ]
    payload = {
        "operation": "materialize",
        "status": "ok",
        "coverage": {"context_start_line": 10, "context_end_line": 12},
        "data": {
            "text": text,
            "observed_references": references,
            "observed_relations": relations,
        },
        "mcp_session": {"session_id": "investigation", "revision": 3},
    }

    result = compact_response(payload, display_source="/tmp/evidence/traces.jsonl")
    encoded = json.dumps(result, ensure_ascii=False)
    data = result["data"]

    assert data["text"] == text
    assert data["observed_reference_count"] == 40
    assert data["observed_relation_count"] == 40
    assert len(data["observed_references"]) == 8
    assert len(data["observed_relations"]) == 8
    assert data["observed_references_omitted_from_transport"] == 32
    assert data["observed_relations_omitted_from_transport"] == 32
    assert all(len(row.get("visible_lines", [])) <= 8 for row in data["observed_references"])
    assert all(len(row.get("visible_lines", [])) <= 8 for row in data["observed_relations"])
    assert len(encoded.encode("utf-8")) < 8_000
