"""Compact Agent projection for budget-admitted Evidence Shell results."""

from __future__ import annotations

from typing import Any, Mapping


_PREVIEW_CHARS = 180


def _source_name(value: Any) -> str:
    text = str(value or "").replace("\\", "/").rstrip("/")
    return text.rsplit("/", 1)[-1] if text else "evidence"


def _preview(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) <= _PREVIEW_CHARS:
        return text
    head = (_PREVIEW_CHARS - 5) // 2
    return f"{text[:head]} ... {text[-(_PREVIEW_CHARS - 5 - head):]}"


def _sha(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if len(text) == 64 and all(ch in "0123456789abcdef" for ch in text):
        return text
    return None


def _common_sha(rows: list[Mapping[str, Any]]) -> str | None:
    values = {_sha(row.get("sha256")) for row in rows}
    values.discard(None)
    return next(iter(values)) if len(values) == 1 else None


def _compact_pointer(
    row: Mapping[str, Any],
    display_source: str,
    *,
    common_sha: str | None,
) -> dict[str, Any]:
    """Keep one line-addressable pointer while dropping redundant URI text."""

    item: dict[str, Any] = {}
    start = row.get("start_line")
    end = row.get("end_line")
    has_ref = isinstance(start, int) and not isinstance(start, bool) and start > 0
    if has_ref:
        if not isinstance(end, int) or isinstance(end, bool) or end < start:
            end = start
        item["ref"] = f"{_source_name(display_source)}:L{start}" + (
            f"-L{end}" if end > start else ""
        )
        item["start_line"] = start
        item["end_line"] = end

    # Preserve the established materialize/replay pointer contract. URI is the
    # most redundant field for ordinary line-addressable evidence, so omit only
    # that duplicated identity. A common SHA is also projected once at the
    # envelope for compact inspection, while per-pointer SHA remains available
    # to existing callers.
    digest = _sha(row.get("sha256"))
    if digest is not None:
        item["sha256"] = digest
    materialize_source = str(row.get("source_path") or row.get("source") or "").strip()
    if materialize_source:
        item["materialize_source"] = materialize_source
    if not has_ref:
        uri = str(row.get("uri") or "").strip()
        if uri:
            item["uri"] = uri

    label = row.get("label")
    if label is not None:
        item["preview"] = _preview(label)
    return item


def _compact_existing_summary(
    value: Mapping[str, Any],
    display_source: str,
    *,
    common_sha: str | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("count", "all_matches_previously_seen", "replay_hint"):
        if key in value:
            result[key] = value[key]
    representative = value.get("representative")
    if isinstance(representative, (list, tuple)):
        result["representative"] = [
            _compact_pointer(row, display_source, common_sha=common_sha)
            for row in representative
            if isinstance(row, Mapping)
        ]
    return result


def compact_shell_response(
    payload: Mapping[str, Any],
    *,
    display_source: str,
) -> dict[str, Any]:
    """Project one Evidence Shell result without a second first-N truncation.

    Core has already applied the user/Host Evidence token+byte gate to the
    complete final match set. MCP therefore returns every newly admitted pointer
    or a Core `too_broad` response. Pointer identity shared by the whole result
    is carried once where possible so the MCP adapter does not spill ordinary
    result sets merely because bulky URI text was repeated for every row.
    """

    result: dict[str, Any] = {
        "operation": "evidence_shell",
        "status": str(payload.get("status") or "unknown"),
        "source": display_source,
    }
    if payload.get("error_code") is not None:
        result["error_code"] = payload.get("error_code")
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
    evidence_rows = [row for row in evidence or () if isinstance(row, Mapping)] if isinstance(evidence, (list, tuple)) else []

    data = payload.get("data")
    repeated_rows: list[Mapping[str, Any]] = []
    representative_rows: list[Mapping[str, Any]] = []
    if isinstance(data, Mapping):
        repeated = data.get("matched_existing_evidence")
        if isinstance(repeated, (list, tuple)):
            repeated_rows = [row for row in repeated if isinstance(row, Mapping)]
        existing_summary = data.get("existing_evidence_summary")
        if isinstance(existing_summary, Mapping):
            representative = existing_summary.get("representative")
            if isinstance(representative, (list, tuple)):
                representative_rows = [row for row in representative if isinstance(row, Mapping)]

    common_sha = _common_sha(evidence_rows + repeated_rows + representative_rows)
    if common_sha is not None:
        result["source_sha256"] = common_sha

    if isinstance(evidence, (list, tuple)):
        result["evidence"] = [
            _compact_pointer(row, display_source, common_sha=common_sha)
            for row in evidence_rows
        ]

    if isinstance(data, Mapping):
        compact_data: dict[str, Any] = {}
        for key in (
            "program",
            "requested_program",
            "normalized_program",
            "source_version",
            "aggregate",
            "reason",
            "refine_query",
            "novelty",
            "evidence_budget",
            "supported_hint",
        ):
            if key in data and data[key] is not None:
                compact_data[key] = data[key]

        if repeated_rows:
            compact_data["matched_existing_evidence"] = [
                _compact_pointer(row, display_source, common_sha=common_sha)
                for row in repeated_rows
            ]

        existing_summary = data.get("existing_evidence_summary")
        if isinstance(existing_summary, Mapping):
            compact_data["existing_evidence_summary"] = _compact_existing_summary(
                existing_summary,
                display_source,
                common_sha=common_sha,
            )
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
