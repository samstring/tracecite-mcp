"""Compact Agent projection for budget-admitted Evidence Shell results."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


_PREVIEW_CHARS = 420


def _source_name(value: Any) -> str:
    text = str(value or "").replace("\\", "/").rstrip("/")
    return text.rsplit("/", 1)[-1] if text else "evidence"


def _preview(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) <= _PREVIEW_CHARS:
        return text
    head = (_PREVIEW_CHARS - 5) // 2
    return f"{text[:head]} ... {text[-(_PREVIEW_CHARS - 5 - head):]}"


def _compact_pointer(row: Mapping[str, Any], display_source: str) -> dict[str, Any]:
    item: dict[str, Any] = {}
    start = row.get("start_line")
    end = row.get("end_line")
    if isinstance(start, int) and not isinstance(start, bool) and start > 0:
        if not isinstance(end, int) or isinstance(end, bool) or end < start:
            end = start
        item["ref"] = f"{_source_name(display_source)}:L{start}" + (
            f"-L{end}" if end > start else ""
        )
        item["start_line"] = start
        item["end_line"] = end
    uri = str(row.get("uri") or "").strip()
    if uri:
        item["uri"] = uri
    sha = str(row.get("sha256") or "").strip()
    if sha:
        item["sha256"] = sha
    label = row.get("label")
    if label is not None:
        item["preview"] = _preview(label)

    # Search citations should display the logical caller source, while exact
    # materialization must target the immutable snapshot/segment selected by
    # SessionSourceView when it differs from the logical path.
    materialize_source = str(row.get("source_path") or "").strip()
    if materialize_source:
        item["materialize_source"] = materialize_source
    return item


def compact_shell_response(
    payload: Mapping[str, Any],
    *,
    display_source: str,
) -> dict[str, Any]:
    """Project one Evidence Shell result without a second first-N truncation.

    Core has already applied the user/Host Evidence token+byte gate to the
    complete final match set. MCP therefore returns every admitted pointer or a
    Core `too_broad` response; it never silently drops a suffix of pointers.
    """

    result: dict[str, Any] = {
        "operation": "evidence_shell",
        "status": str(payload.get("status") or "unknown"),
        "source": display_source,
    }
    if payload.get("error") is not None:
        result["error"] = payload.get("error")
    if payload.get("warnings"):
        result["warnings"] = list(payload.get("warnings") or ())

    coverage = payload.get("coverage")
    if isinstance(coverage, Mapping):
        keep = (
            "complete",
            "selection_explicit",
            "match_records",
            "evidence_returned",
            "new_evidence",
            "repeated_evidence",
            "too_broad",
            "evidence_tokens",
            "evidence_bytes",
            "observed_at_least_tokens",
            "observed_at_least_bytes",
        )
        compact = {key: coverage[key] for key in keep if key in coverage}
        if compact:
            result["coverage"] = compact

    evidence = payload.get("evidence")
    if isinstance(evidence, (list, tuple)):
        # No MCP row cap here. The Runtime budget gate is authoritative.
        result["evidence"] = [
            _compact_pointer(row, display_source)
            for row in evidence
            if isinstance(row, Mapping)
        ]

    data = payload.get("data")
    if isinstance(data, Mapping):
        compact_data: dict[str, Any] = {}
        for key in (
            "program",
            "source_version",
            "aggregate",
            "reason",
            "refine_query",
            "novelty",
            "evidence_budget",
        ):
            if key in data and data[key] is not None:
                compact_data[key] = data[key]
        repeated = data.get("matched_existing_evidence")
        if isinstance(repeated, (list, tuple)) and repeated:
            compact_data["matched_existing_evidence"] = [
                {
                    key: row[key]
                    for key in ("uri", "start_line", "end_line", "sha256")
                    if key in row
                }
                for row in repeated
                if isinstance(row, Mapping)
            ]
        if compact_data:
            result["data"] = compact_data

    session = payload.get("mcp_session")
    if isinstance(session, Mapping):
        compact_session = {
            key: session[key]
            for key in ("session_id", "revision", "progress")
            if key in session
        }
        if compact_session:
            result["mcp_session"] = compact_session

    return result


__all__ = ["compact_shell_response"]
