"""Compact MCP projection for bounded Evidence Compute batches."""

from __future__ import annotations

from typing import Any, Mapping


def _copy_present(source: Mapping[str, Any], target: dict[str, Any], *keys: str) -> None:
    for key in keys:
        if key in source and source[key] is not None:
            target[key] = source[key]


def _compact_output(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result: dict[str, Any] = {}
    _copy_present(
        value,
        result,
        "name",
        "status",
        "program",
        "aggregate",
        "reason",
        "error_code",
        "error",
        "guidance",
        "observed_at_least_tokens",
        "observed_at_least_bytes",
    )
    coverage = value.get("coverage")
    if isinstance(coverage, Mapping):
        compact = {
            key: coverage[key]
            for key in ("complete", "match_records", "selection_explicit")
            if key in coverage
        }
        if compact:
            result["coverage"] = compact
    return result


def _compact_time_scope(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = {
        key: value.get(key)
        for key in ("last", "since", "until")
        if key in value
    }
    return result or None


def compact_compute_response(
    payload: Mapping[str, Any],
    *,
    display_source: str,
) -> dict[str, Any]:
    """Keep only bounded mechanical batch outputs and stable session identity."""

    result: dict[str, Any] = {
        "operation": "evidence_compute",
        "status": str(payload.get("status") or "unknown"),
        "source": display_source,
    }
    coverage = payload.get("coverage")
    if isinstance(coverage, Mapping) and "complete" in coverage:
        result["coverage"] = {"complete": bool(coverage.get("complete"))}

    data = payload.get("data")
    if isinstance(data, Mapping):
        compact_data: dict[str, Any] = {}
        outputs = data.get("outputs")
        if isinstance(outputs, (list, tuple)):
            compact_outputs = [item for item in (_compact_output(row) for row in outputs) if item]
            compact_data["outputs"] = compact_outputs
        _copy_present(
            data,
            compact_data,
            "analysis_count",
            "source_version",
            "source_sha256",
            "execution_engine",
            "reason",
            "observed_at_least_tokens",
            "observed_at_least_bytes",
        )
        time_scope = _compact_time_scope(data.get("time_scope"))
        if time_scope is not None:
            compact_data["time_scope"] = time_scope
        if compact_data:
            result["data"] = compact_data

    session = payload.get("mcp_session")
    if isinstance(session, Mapping):
        compact_session: dict[str, Any] = {}
        _copy_present(session, compact_session, "session_id", "revision")
        if compact_session:
            result["mcp_session"] = compact_session
    return result


__all__ = ["compact_compute_response"]
