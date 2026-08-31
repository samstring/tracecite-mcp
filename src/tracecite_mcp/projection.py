"""Agent-facing mechanical response projection for TraceCite MCP.

The Core result remains authoritative. This module removes redundant or bulky
transport fields while preserving the facts an Agent needs to continue an
investigation. It never adds hypotheses, causal conclusions, sufficiency, or
stopping decisions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


_PREVIEW_CHARS = 420
_MAX_EVIDENCE_ROWS = 8
_MAX_SIGNAL_HINTS = 3
_MAX_SAMPLE_ROWS = 6
_MAX_REPEAT_REFS = 3

# Core operation names are target-specific. MCP tool names are intentionally
# smaller/stable, so projection must classify the actual Core operations rather
# than assuming they are named after the MCP tools.
_OPERATION_FAMILY = {
    "retrieve": "retrieve",
    "search": "retrieve",
    "probe": "source",
    "sample": "source",
    "survey": "source",
    "materialize": "materialize",
    "expand": "materialize",
    "replay": "replay",
}


def _copy_present(source: Mapping[str, Any], target: dict[str, Any], *keys: str) -> None:
    for key in keys:
        if key in source and source[key] is not None:
            target[key] = source[key]


def _source_name(value: Any) -> str:
    text = str(value or "").replace("\\", "/").rstrip("/")
    return text.rsplit("/", 1)[-1] if text else "evidence"


def _head_tail(value: Any, limit: int = _PREVIEW_CHARS) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    if limit < 16:
        return text[:limit]
    head = max(1, (limit - 5) // 2)
    tail = max(1, limit - 5 - head)
    return f"{text[:head]} ... {text[-tail:]}"


def _line_ref(row: Mapping[str, Any], display_source: str | None = None) -> str | None:
    start = row.get("start_line")
    if isinstance(start, bool) or not isinstance(start, int) or start <= 0:
        return None
    end = row.get("end_line")
    if isinstance(end, bool) or not isinstance(end, int) or end < start:
        end = start
    source = display_source or row.get("source_path") or row.get("source")
    name = _source_name(source)
    return f"{name}:L{start}" + (f"-L{end}" if end > start else "")


def _evidence_sha(row: Mapping[str, Any]) -> str | None:
    value = row.get("sha256") or row.get("source_sha256")
    text = str(value or "").strip().lower()
    if len(text) == 64 and all(ch in "0123456789abcdef" for ch in text):
        return text
    return None


def _compact_evidence(
    row: Any,
    *,
    display_source: str | None,
    common_sha: str | None,
) -> Any:
    if not isinstance(row, Mapping):
        return row

    projected: dict[str, Any] = {}
    _copy_present(row, projected, "id", "kind")

    ref = _line_ref(row, display_source)
    if ref is not None:
        projected["ref"] = ref
        _copy_present(row, projected, "start_line", "end_line")

    uri = row.get("evidence_uri") or row.get("uri")
    if uri is not None:
        projected["uri"] = uri

    # Source and digest are normally shared by every row, so keep them once at
    # the envelope. Preserve per-row values only when no common value exists.
    if display_source is None:
        source = row.get("source_path") or row.get("source")
        if source is not None:
            projected["source"] = source
    digest = _evidence_sha(row)
    if digest is not None and common_sha is None:
        projected["source_sha256"] = digest

    preview = row.get("preview")
    if preview is None:
        preview = row.get("label")
    if preview is not None:
        projected["preview"] = _head_tail(preview)

    _copy_present(row, projected, "entities")
    return projected


def _single_source_sha(payload: Mapping[str, Any], evidence: list[Any]) -> str | None:
    values = {
        digest
        for row in evidence
        if isinstance(row, Mapping)
        for digest in [_evidence_sha(row)]
        if digest is not None
    }
    if len(values) == 1:
        return next(iter(values))

    data = payload.get("data") or {}
    for source in (payload, data if isinstance(data, Mapping) else {}):
        for key in ("source_sha256", "sha256"):
            value = str(source.get(key) or "").strip().lower()
            if len(value) == 64 and all(ch in "0123456789abcdef" for ch in value):
                return value
    return None


def _compact_coverage(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    projected: dict[str, Any] = {}
    _copy_present(
        value,
        projected,
        "complete",
        "truncated",
        "scoped_lines",
        "scoped_records",
        "match_records",
        "match_lines",
        "selected_records",
        "records_returned",
        "records_omitted",
        "evidence_returned",
        "evidence_truncated",
        "signal_hints_returned",
        "context_start_line",
        "context_end_line",
        "new_evidence",
        "repeated_evidence",
    )
    return projected


def _compact_progress(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    projected: dict[str, Any] = {}
    _copy_present(
        value,
        projected,
        "delta",
        "seen_evidence",
        "seen_lines",
        "coverage_status",
        "source_complete",
        "frontier_exhausted",
        "scope_exhausted",
        "consecutive_no_growth",
        "actionable_gaps",
    )
    return projected


def _compact_session(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    projected: dict[str, Any] = {}
    _copy_present(value, projected, "session_id", "revision")
    progress = value.get("progress")
    if isinstance(progress, Mapping):
        compact: dict[str, Any] = {}
        _copy_present(
            progress,
            compact,
            "operation_counts",
            "unique_evidence_seen",
            "exact_duplicate_requests",
            "recent_window",
            "recent_with_new_evidence",
            "recent_repeated_only",
            "recent_no_match",
        )
        if compact:
            projected["progress"] = compact
    return projected


def _compact_routing(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    projected: dict[str, Any] = {}
    _copy_present(value, projected, "mode", "next_mode", "reasons", "max_match_records")
    return projected


def _evenly_spaced(values: Sequence[Any], limit: int) -> list[Any]:
    rows = list(values)
    if len(rows) <= limit:
        return rows
    if limit == 1:
        return [rows[0]]
    indexes = [round(index * (len(rows) - 1) / (limit - 1)) for index in range(limit)]
    return [rows[index] for index in dict.fromkeys(indexes)]


def _compact_samples(value: Any, display_source: str | None) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[dict[str, Any]] = []
    for row in _evenly_spaced(value, _MAX_SAMPLE_ROWS):
        if not isinstance(row, Mapping):
            continue
        item: dict[str, Any] = {}
        ref = _line_ref(row, display_source)
        if ref:
            item["ref"] = ref
        text = row.get("text")
        if text is not None:
            item["preview"] = _head_tail(text)
        if item:
            result.append(item)
    return result


def _compact_signal_hints(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[dict[str, Any]] = []
    for row in list(value)[:_MAX_SIGNAL_HINTS]:
        if not isinstance(row, Mapping):
            continue
        item: dict[str, Any] = {}
        _copy_present(row, item, "ref", "line", "end_line", "severity", "count")
        if row.get("label") is not None:
            item["label"] = _head_tail(row.get("label"))
        if item:
            result.append(item)
    return result


def _compact_repeat_refs(value: Any, display_source: str | None) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[dict[str, Any]] = []
    for row in list(value)[:_MAX_REPEAT_REFS]:
        if not isinstance(row, Mapping):
            continue
        item: dict[str, Any] = {}
        ref = _line_ref(row, display_source)
        if ref:
            item["ref"] = ref
        uri = row.get("uri")
        if uri:
            item["uri"] = uri
        if item:
            result.append(item)
    return result


def _compact_data(family: str, value: Any, display_source: str | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    projected: dict[str, Any] = {}

    if family == "materialize":
        text = value.get("text") if isinstance(value.get("text"), str) else ""
        new_text = value.get("new_text") if isinstance(value.get("new_text"), str) else ""
        # Never send the same exact materialized body twice. If only a subset is
        # new, prefer that subset because the rest was already delivered in the
        # same RetrievalSession.
        if new_text and text and new_text != text:
            projected["new_text"] = new_text
        elif text:
            projected["text"] = text
        elif new_text:
            projected["new_text"] = new_text
        _copy_present(value, projected, "unseen_ranges", "repeated_text_suppressed", "replayed")

    if family == "source":
        samples = _compact_samples(value.get("samples"), display_source)
        if samples:
            projected["samples"] = samples
        _copy_present(value, projected, "navigation_only", "navigation_note")

    hints = _compact_signal_hints(value.get("signal_hints"))
    if hints:
        projected["signal_hints"] = hints
        _copy_present(value, projected, "signal_hint_note")

    repeated = value.get("matched_existing_evidence")
    if isinstance(repeated, (list, tuple)) and repeated:
        projected["matched_existing_evidence_count"] = len(repeated)
        refs = _compact_repeat_refs(repeated, display_source)
        if refs:
            projected["matched_existing_evidence"] = refs

    routing = _compact_routing(value.get("routing"))
    if routing:
        projected["routing"] = routing
    progress = _compact_progress(value.get("progress"))
    if progress:
        projected["progress"] = progress

    _copy_present(
        value,
        projected,
        "novelty",
        "correlation_constraints",
        "missing_evidence",
        "acquisition_end_reason",
        "observed_references",
        "observed_relations",
    )
    return projected


def _compact_retrieval(
    payload: Mapping[str, Any],
    family: str,
    *,
    display_source: str | None,
) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    _copy_present(payload, projected, "operation", "status", "query", "regex", "error")

    data = payload.get("data") or {}
    if "query" not in projected and isinstance(data, Mapping):
        _copy_present(data, projected, "query", "regex")

    raw_evidence = payload.get("evidence")
    evidence = list(raw_evidence) if isinstance(raw_evidence, (list, tuple)) else []
    digest = _single_source_sha(payload, evidence)

    if display_source:
        projected["source"] = display_source
    elif payload.get("source") is not None:
        projected["source"] = payload.get("source")
    if digest is not None:
        projected["source_sha256"] = digest

    coverage = _compact_coverage(payload.get("coverage"))
    if coverage:
        projected["coverage"] = coverage

    if raw_evidence is not None:
        rows = evidence[:_MAX_EVIDENCE_ROWS]
        projected["evidence"] = [
            _compact_evidence(row, display_source=display_source, common_sha=digest)
            for row in rows
        ]
        if len(evidence) > len(rows):
            projected["evidence_omitted_from_transport"] = len(evidence) - len(rows)

    session = _compact_session(payload.get("mcp_session"))
    if session:
        projected["mcp_session"] = session

    compact_data = _compact_data(family, data, display_source)
    if compact_data:
        projected["data"] = compact_data
    return projected


def _compact_bounded(payload: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    _copy_present(payload, projected, *keys)
    return projected


def compact_response(
    payload: Mapping[str, Any],
    *,
    display_source: str | None = None,
) -> dict[str, Any]:
    """Return the canonical compact MCP transport projection.

    ``display_source`` is the caller-visible source selected in the MCP request;
    it prevents internal snapshot paths from becoming Agent-facing citations.
    Exact materialized text is not character-truncated by this projection.
    """

    operation = str(payload.get("operation") or "").strip().lower()
    family = _OPERATION_FAMILY.get(operation)
    if family is not None:
        return _compact_retrieval(payload, family, display_source=display_source)
    if operation == "aggregate":
        return _compact_bounded(
            payload,
            "operation",
            "status",
            "source",
            "source_sha256",
            "sha256",
            "query",
            "regex",
            "aggregate",
            "data",
            "coverage",
            "error",
        )
    if operation == "traverse":
        return _compact_bounded(
            payload,
            "operation",
            "status",
            "stop_reason",
            "coverage",
            "progress",
            "trace",
            "diagnostics",
            "graph",
            "grouping",
            "reduction",
            "acquisition_end_reason",
            "error",
        )
    if operation == "verify":
        return _compact_bounded(
            payload,
            "operation",
            "status",
            "path",
            "coverage",
            "verification",
            "data",
            "error",
        )
    return dict(payload)
