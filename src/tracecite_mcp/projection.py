"""Agent-facing mechanical response projection for TraceCite MCP.

The Core result remains authoritative.  This module only removes redundant or
bulky transport fields while preserving the facts an Agent needs to continue an
investigation: provenance, immutable source identity, exact materialized text,
coverage, RetrievalSession state, mechanical novelty, aggregate/traversal
results, and integrity facts.  It must never infer hypotheses, sufficiency, or
stopping.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_PREVIEW_CHARS = 420


def _copy_present(source: Mapping[str, Any], target: dict[str, Any], *keys: str) -> None:
    for key in keys:
        if key in source and source[key] is not None:
            target[key] = source[key]


def _source_name(value: Any) -> str:
    text = str(value or "").replace("\\", "/").rstrip("/")
    return text.rsplit("/", 1)[-1] if text else "evidence"


def _line_ref(row: Mapping[str, Any]) -> str | None:
    start = row.get("start_line")
    if isinstance(start, bool) or not isinstance(start, int) or start <= 0:
        return None
    end = row.get("end_line")
    if isinstance(end, bool) or not isinstance(end, int) or end < start:
        end = start
    source = row.get("source_path") or row.get("source")
    name = _source_name(source)
    return f"{name}:L{start}" + (f"-L{end}" if end > start else "")


def _evidence_sha(row: Mapping[str, Any]) -> str | None:
    value = row.get("sha256") or row.get("source_sha256")
    text = str(value or "").strip().lower()
    if len(text) == 64 and all(ch in "0123456789abcdef" for ch in text):
        return text
    return None


def _compact_evidence(row: Any) -> Any:
    if not isinstance(row, Mapping):
        return row

    projected: dict[str, Any] = {}
    _copy_present(row, projected, "id", "kind")

    source = row.get("source_path") or row.get("source")
    if source is not None:
        projected["source"] = source

    ref = _line_ref(row)
    if ref is not None:
        projected["ref"] = ref
        _copy_present(row, projected, "start_line", "end_line")

    uri = row.get("evidence_uri") or row.get("uri")
    if uri is not None:
        projected["uri"] = uri

    digest = _evidence_sha(row)
    if digest is not None:
        projected["source_sha256"] = digest

    preview = row.get("preview")
    if preview is None:
        preview = row.get("label")
    if preview is not None:
        projected["preview"] = str(preview)[:_PREVIEW_CHARS]

    # Provider identities are mechanical evidence facts and may be needed as
    # caller-selected traversal seeds. Preserve them even when other provider
    # metadata is omitted from the transport projection.
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

    for key in ("source_sha256", "sha256"):
        value = str(payload.get(key) or "").strip().lower()
        if len(value) == 64 and all(ch in "0123456789abcdef" for ch in value):
            return value
    return None


def _compact_data(operation: str, value: Any) -> Any:
    if not isinstance(value, Mapping):
        return value
    if operation not in {"retrieve", "materialize", "replay"}:
        return dict(value)

    projected: dict[str, Any] = {}
    _copy_present(
        value,
        projected,
        "text",
        "new_text",
        "novelty",
        "matched_existing_evidence",
        "progress",
        "correlation_constraints",
        "missing_evidence",
        "acquisition_end_reason",
        "unseen_ranges",
        "observed_references",
        "observed_relations",
        "replayed",
    )
    return projected


def _compact_retrieval(payload: Mapping[str, Any], operation: str) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    _copy_present(
        payload,
        projected,
        "operation",
        "status",
        "source",
        "query",
        "regex",
        "coverage",
        "progress",
        "missing_evidence",
        "unseen_ranges",
        "observed_references",
        "observed_relations",
        "correlation_constraints",
        "acquisition_end_reason",
        "error",
        "mcp_session",
    )

    raw_evidence = payload.get("evidence")
    evidence = list(raw_evidence) if isinstance(raw_evidence, (list, tuple)) else []
    if raw_evidence is not None:
        projected["evidence"] = [_compact_evidence(row) for row in evidence]

    digest = _single_source_sha(payload, evidence)
    if digest is not None:
        projected["source_sha256"] = digest

    if "data" in payload:
        data = _compact_data(operation, payload.get("data"))
        if data:
            projected["data"] = data
    return projected


def _compact_bounded(payload: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    _copy_present(payload, projected, *keys)
    return projected


def compact_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical compact MCP transport projection.

    Projection is intentionally operation-specific and mechanical. Exact
    materialized text is never truncated. No planner, causal, sufficiency, or
    stopping fields are synthesized.
    """

    operation = str(payload.get("operation") or "")
    if operation in {"retrieve", "materialize", "replay"}:
        return _compact_retrieval(payload, operation)
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
