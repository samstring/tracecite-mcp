from __future__ import annotations

from tracecite_mcp.projection import compact_response


SHA = "a" * 64


def test_compact_retrieve_preserves_agent_continuation_facts() -> None:
    payload = {
        "operation": "retrieve",
        "status": "ok",
        "coverage": {"new_evidence": 1, "repeated_evidence": 0},
        "mcp_session": {"session_id": "investigation-a", "revision": 3},
        "evidence": [
            {
                "id": "e-1",
                "kind": "log",
                "source_path": "/tmp/runtime/containerd.log",
                "start_line": 20,
                "end_line": 21,
                "sha256": SHA,
                "evidence_uri": "evidence://local/e-1",
                "label": "x" * 1000,
                "entities": [{"type": "container", "id": "abc"}],
                "metadata": {"large": "y" * 5000},
            }
        ],
        "data": {
            "novelty": {"state": "new"},
            "matched_existing_evidence": [],
            "correlation_constraints": {"identifier_only_correlation_safe": False},
            "internal_debug": "z" * 5000,
        },
        "stop_recommended": True,
    }

    result = compact_response(payload)

    assert result["operation"] == "retrieve"
    assert result["coverage"]["new_evidence"] == 1
    assert result["mcp_session"]["session_id"] == "investigation-a"
    assert result["source_sha256"] == SHA
    assert result["evidence"] == [
        {
            "id": "e-1",
            "kind": "log",
            "source": "/tmp/runtime/containerd.log",
            "ref": "containerd.log:L20-L21",
            "start_line": 20,
            "end_line": 21,
            "uri": "evidence://local/e-1",
            "source_sha256": SHA,
            "preview": "x" * 420,
            "entities": [{"type": "container", "id": "abc"}],
        }
    ]
    assert result["data"]["novelty"] == {"state": "new"}
    assert "internal_debug" not in result["data"]
    assert "metadata" not in result["evidence"][0]
    assert "stop_recommended" not in result


def test_compact_materialize_never_truncates_exact_materialized_text() -> None:
    text = "line one\nline two\n" * 1000
    payload = {
        "operation": "materialize",
        "status": "ok",
        "coverage": {"new_evidence": 1},
        "evidence": [
            {
                "source_path": "/tmp/app.log",
                "start_line": 1,
                "end_line": 2,
                "sha256": SHA,
                "label": "line one",
            }
        ],
        "data": {
            "new_text": text,
            "novelty": {"state": "new"},
            "unseen_ranges": [[1, 2]],
            "debug_dump": "not-agent-facing",
        },
    }

    result = compact_response(payload)

    assert result["data"]["new_text"] == text
    assert result["data"]["novelty"] == {"state": "new"}
    assert result["data"]["unseen_ranges"] == [[1, 2]]
    assert "debug_dump" not in result["data"]


def test_bounded_non_retrieval_results_pass_through_without_semantic_rewrite() -> None:
    payload = {
        "operation": "aggregate",
        "status": "ok",
        "data": {"count": 3},
        "coverage": {"complete": True},
    }

    assert compact_response(payload) == payload
