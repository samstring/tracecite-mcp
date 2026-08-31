from __future__ import annotations

from tracecite_mcp.projection import compact_response


SHA = "a" * 64


def _evidence(line: int, label: str = "event") -> dict[str, object]:
    return {
        "id": f"e-{line}",
        "kind": "log",
        "source_path": "/tmp/internal/.snapshots/containerd.snapshot.log",
        "start_line": line,
        "end_line": line,
        "sha256": SHA,
        "evidence_uri": f"evidence://local/e-{line}",
        "label": label,
        "metadata": {"large": "y" * 5000},
    }


def test_compact_search_alias_preserves_only_agent_continuation_facts() -> None:
    payload = {
        "operation": "search",
        "status": "ok",
        "coverage": {
            "scoped_lines": 3967,
            "match_records": 448,
            "evidence_returned": 30,
            "evidence_truncated": True,
            "new_evidence": 30,
            "repeated_evidence": 0,
            "unmatched": {"top_unmatched_tokens": ["x"] * 1000},
        },
        "mcp_session": {
            "session_id": "investigation-a",
            "revision": 3,
            "progress": {
                "operation_counts": {"search": 2},
                "unique_evidence_seen": 60,
                "recent_window": 3,
            },
        },
        "evidence": [_evidence(index, "x" * 1000) for index in range(1, 13)],
        "data": {
            "query": "level=error",
            "source_sha256": SHA,
            "signal_hints": [
                {
                    "ref": "containerd.log:1040",
                    "line": 1040,
                    "end_line": 1040,
                    "severity": 3,
                    "count": 1,
                    "label": "A" * 300 + " WAIT_KILLABLE_RECV invalid argument",
                }
            ],
            "routing": {
                "mode": "bounded",
                "next_mode": "focused",
                "reasons": ["direct_output_exceeds_budget"],
                "source_bytes": 2_000_000,
                "direct_char_budget": 32768,
            },
            "progress": {"seen_evidence": 60, "coverage_status": "partial"},
            "internal_debug": "z" * 5000,
        },
        "stop_recommended": True,
    }

    result = compact_response(payload, display_source="/evidence/containerd.log")

    assert result["operation"] == "search"
    assert result["source"] == "/evidence/containerd.log"
    assert result["query"] == "level=error"
    assert result["coverage"]["match_records"] == 448
    assert "unmatched" not in result["coverage"]
    assert result["mcp_session"]["session_id"] == "investigation-a"
    assert result["source_sha256"] == SHA
    assert len(result["evidence"]) == 8
    assert result["evidence_omitted_from_transport"] == 4
    assert result["evidence"][0]["ref"] == "containerd.log:L1"
    assert "source" not in result["evidence"][0]
    assert "source_sha256" not in result["evidence"][0]
    assert "metadata" not in result["evidence"][0]
    assert result["data"]["routing"] == {
        "mode": "bounded",
        "next_mode": "focused",
        "reasons": ["direct_output_exceeds_budget"],
    }
    hint = result["data"]["signal_hints"][0]
    assert "WAIT_KILLABLE_RECV" in hint["label"]
    assert "internal_debug" not in result["data"]
    assert "stop_recommended" not in result


def test_compact_sample_alias_reduces_uniform_samples() -> None:
    samples = [
        {"text": f"line {index} " + ("x" * 500), "start_line": index, "end_line": index}
        for index in range(1, 37)
    ]
    payload = {
        "operation": "sample",
        "status": "ok",
        "coverage": {
            "scoped_lines": 3967,
            "records_returned": 36,
            "records_omitted": 3931,
            "truncated": True,
            "omissions": [{"detail": "bulky" * 1000}],
        },
        "data": {
            "samples": samples,
            "navigation_only": True,
            "navigation_note": "orientation only",
            "routing": {"mode": "bounded", "source_bytes": 2_000_000},
        },
    }

    result = compact_response(payload, display_source="/evidence/containerd.log")

    assert len(result["data"]["samples"]) == 6
    assert result["data"]["samples"][0]["ref"] == "containerd.log:L1"
    assert result["data"]["samples"][-1]["ref"] == "containerd.log:L36"
    assert "omissions" not in result["coverage"]


def test_compact_expand_alias_never_duplicates_exact_materialized_text() -> None:
    text = "line one\nline two\n" * 1000
    payload = {
        "operation": "expand",
        "status": "ok",
        "coverage": {
            "context_start_line": 1,
            "context_end_line": 2,
            "new_evidence": 1,
        },
        "evidence": [_evidence(1, "line one")],
        "data": {
            "text": text,
            "new_text": text,
            "progress": {"seen_lines": 2},
            "unseen_ranges": [[1, 2]],
            "debug_dump": "not-agent-facing",
        },
    }

    result = compact_response(payload, display_source="/tmp/app.log")

    assert result["data"]["text"] == text
    assert "new_text" not in result["data"]
    assert result["data"]["unseen_ranges"] == [[1, 2]]
    assert "debug_dump" not in result["data"]


def test_compact_materialize_prefers_only_new_subset_when_range_overlaps() -> None:
    payload = {
        "operation": "materialize",
        "status": "ok",
        "coverage": {"new_evidence": 1},
        "data": {
            "text": "1: old\n2: new\n",
            "new_text": "2: new\n",
            "unseen_ranges": [[2, 2]],
        },
    }

    result = compact_response(payload, display_source="/tmp/app.log")

    assert result["data"]["new_text"] == "2: new\n"
    assert "text" not in result["data"]


def test_bounded_non_retrieval_results_pass_through_without_semantic_rewrite() -> None:
    payload = {
        "operation": "aggregate",
        "status": "ok",
        "data": {"count": 3},
        "coverage": {"complete": True},
    }

    assert compact_response(payload) == payload
