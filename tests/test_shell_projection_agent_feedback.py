from __future__ import annotations

from tracecite_mcp.shell_projection import compact_shell_response


def test_projection_keeps_structured_program_error() -> None:
    result = compact_shell_response(
        {
            "status": "error",
            "error_code": "unsupported_program",
            "error": "unsupported evidence shell command: awk",
            "evidence": [],
            "data": {
                "program": "awk '{print $1}'",
                "supported_hint": "Use search/where/project",
            },
        },
        display_source="/evidence/runtime.jsonl",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "unsupported_program"
    assert "awk" in result["error"]
    assert "supported_hint" in result["data"]


def test_projection_keeps_only_bounded_repeated_receipts() -> None:
    digest = "a" * 64
    result = compact_shell_response(
        {
            "status": "ok",
            "coverage": {"new_evidence": 0, "repeated_evidence": 20},
            "evidence": [],
            "data": {
                "novelty": {
                    "state": "no_new_evidence",
                    "new_evidence": 0,
                    "repeated_evidence": 20,
                    "matched_evidence": 20,
                    "query_repeated": True,
                },
                "matched_existing_evidence": [
                    {
                        "uri": f"evidence://sha256/{digest}#L10-L11",
                        "sha256": digest,
                        "start_line": 10,
                        "end_line": 11,
                        "source": "/evidence/runtime.jsonl",
                    },
                    {
                        "uri": f"evidence://sha256/{digest}#L99",
                        "sha256": digest,
                        "start_line": 99,
                        "end_line": 99,
                        "source": "/evidence/runtime.jsonl",
                    },
                ],
                "existing_evidence_summary": {
                    "count": 20,
                    "all_matches_previously_seen": True,
                    "representative": [
                        {
                            "uri": f"evidence://sha256/{digest}#L10-L11",
                            "sha256": digest,
                            "start_line": 10,
                            "end_line": 11,
                            "source": "/evidence/runtime.jsonl",
                        },
                        {
                            "uri": f"evidence://sha256/{digest}#L99",
                            "sha256": digest,
                            "start_line": 99,
                            "end_line": 99,
                            "source": "/evidence/runtime.jsonl",
                        },
                    ],
                },
            },
        },
        display_source="/evidence/runtime.jsonl",
    )

    assert result["coverage"]["repeated_evidence"] == 20
    assert len(result["data"]["matched_existing_evidence"]) == 2
    summary = result["data"]["existing_evidence_summary"]
    assert summary["count"] == 20
    assert len(summary["representative"]) == 2
    assert summary["representative"][0]["ref"] == "runtime.jsonl:L10-L11"
