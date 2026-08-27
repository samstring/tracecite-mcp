"""MCP projection of TraceCite's public Agent-facing API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from tracecite import (
    InvestigationStore,
    execute_capability,
    expand,
    list_capabilities,
    probe,
    sample,
    search,
    survey,
    validate_finding,
    verify,
)
from tracecite.extension import list_extensions, load_extensions, loaded_plugins
from tracecite.integrations import ContextEngine
from tracecite.integrations.evidence_ledger import EvidenceLedger, expand_many


mcp = MCPServer("TraceCite")
_EXTENSIONS_LOADED = False
_EXTENSION_LOAD_RESULT: list[dict[str, Any]] = []


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _authorized_capabilities() -> set[str]:
    raw = os.environ.get("TRACECITE_MCP_AUTHORIZED_CAPABILITIES", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _state_root() -> Path:
    """Return the server-owner context root; models never choose this path."""

    configured = os.environ.get("TRACECITE_MCP_STATE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".tracecite" / "mcp").resolve()


def _ledger() -> EvidenceLedger:
    return EvidenceLedger(_state_root() / "ledger")


def ensure_extensions_loaded() -> list[dict[str, Any]]:
    """Load installed TraceCite extensions once at the explicit MCP boundary."""
    global _EXTENSIONS_LOADED, _EXTENSION_LOAD_RESULT
    if not _EXTENSIONS_LOADED:
        _EXTENSION_LOAD_RESULT = list(load_extensions(strict=True))
        _EXTENSIONS_LOADED = True
    return list(_EXTENSION_LOAD_RESULT)


@mcp.tool()
def tracecite_probe(
    input_path: str,
    glob: str = "*",
    recursive: bool = False,
    segmenter: str = "auto",
    investigation_path: str | None = None,
    hypothesis_id: str | None = None,
    test_id: str | None = None,
) -> dict[str, Any]:
    """Inspect source metadata, format and time coverage without diagnosing it."""
    return probe(
        input_path,
        glob=glob,
        recursive=recursive,
        segmenter=segmenter,
        investigation_path=investigation_path,
        hypothesis_id=hypothesis_id,
        test_id=test_id,
    )


@mcp.tool()
def tracecite_sample(
    input_path: str,
    strategy: str = "head-tail",
    count: int = 10,
    max_chars: int = 8000,
    snapshot: bool = True,
    segmenter: str = "auto",
) -> dict[str, Any]:
    """Read bounded raw context from a source without making a causal claim."""
    return sample(
        input_path,
        strategy=strategy,
        count=count,
        max_chars=max_chars,
        snapshot=snapshot,
        segmenter=segmenter,
    )


@mcp.tool()
def tracecite_survey(
    input_path: str,
    snapshot: bool = True,
    segmenter: str = "auto",
    max_templates: int = 20,
    samples_per_template: int = 2,
) -> dict[str, Any]:
    """Return a bounded descriptive overview of an unfamiliar source."""
    return survey(
        input_path,
        snapshot=snapshot,
        segmenter=segmenter,
        max_templates=max_templates,
        samples_per_template=samples_per_template,
    )


@mcp.tool()
def tracecite_search(
    input_path: str,
    query: str,
    regex: bool = False,
    snapshot: bool = True,
    segmenter: str = "auto",
    max_evidence: int | None = None,
    investigation_path: str | None = None,
    hypothesis_id: str | None = None,
    test_id: str | None = None,
    context_id: str | None = None,
) -> dict[str, Any]:
    """Search and optionally return only evidence new to one Agent context.

    Without ``context_id`` this returns the canonical Runtime Result exactly as
    before. With ``context_id`` the canonical Result is retained in a private
    content-addressed Ledger and the response becomes a lossless delta over the
    evidence already seen by that context.
    """

    canonical = search(
        input_path,
        query,
        regex=regex,
        snapshot=snapshot,
        segmenter=segmenter,
        max_evidence=max_evidence,
        investigation_path=investigation_path,
        hypothesis_id=hypothesis_id,
        test_id=test_id,
    )
    if not context_id:
        return canonical
    if canonical.get("status") not in {"ok", "no_match"}:
        return canonical

    ledger = _ledger()
    result_id = ledger.store(canonical)
    projected = ContextEngine(_state_root(), context_id).project_search(
        canonical,
        result_id=result_id,
    )
    data = dict(projected.get("data") or {})
    data["result_id"] = result_id
    data["recovery_tool"] = "tracecite_expand_many"
    projected["data"] = data
    return projected


@mcp.tool()
def tracecite_expand(
    source_path: str,
    start_line: int,
    end_line: int | None = None,
    before: int = 3,
    after: int = 3,
    expected_sha256: str | None = None,
    max_chars: int = 20000,
) -> dict[str, Any]:
    """Expand bounded context around a cited line range with hash checking."""
    return expand(
        source_path,
        start_line,
        end_line=end_line,
        before=before,
        after=after,
        expected_sha256=expected_sha256,
        max_chars=max_chars,
    )


@mcp.tool()
def tracecite_expand_many(
    result_id: str,
    refs: list[str],
    before: int = 3,
    after: int = 3,
    max_chars: int = 20000,
) -> dict[str, Any]:
    """Recover several immutable evidence refs from a stateful search Result."""

    return expand_many(
        _ledger(),
        result_id,
        refs,
        before=before,
        after=after,
        max_chars=max_chars,
    )


@mcp.tool()
def tracecite_verify(manifest_path: str) -> dict[str, Any]:
    """Verify the integrity of a completed TraceCite evidence manifest."""
    return verify(manifest_path)


@mcp.tool()
def tracecite_investigation_create(
    path: str,
    question: str,
    scope: dict[str, Any] | None = None,
    created_by: str = "mcp",
) -> dict[str, Any]:
    """Create a persistent InvestigationState document."""
    state = InvestigationStore(path).create(question, scope=scope, created_by=created_by)
    return state.to_dict()


@mcp.tool()
def tracecite_validate_finding(
    investigation_path: str,
    hypothesis_id: str,
    outcome: str,
    supporting_evidence: list[str] | None = None,
    contradicting_evidence: list[str] | None = None,
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mechanically validate a proposed Finding against persisted Test evidence."""
    result = validate_finding(
        InvestigationStore(investigation_path),
        hypothesis_id,
        outcome,
        supporting_evidence=supporting_evidence or (),
        contradicting_evidence=contradicting_evidence or (),
        coverage=coverage,
    )
    return result.to_dict()


@mcp.tool()
def tracecite_list_extensions() -> dict[str, Any]:
    """List declarative Extension v2 state without exposing Runtime internals."""
    ensure_extensions_loaded()
    return {
        "extensions": list_extensions(),
        "load_results": list(_EXTENSION_LOAD_RESULT),
        "loaded_plugins": loaded_plugins(),
    }


@mcp.tool()
def tracecite_list_capabilities() -> list[dict[str, Any]]:
    """List Agent-facing capabilities registered by installed TraceCite extensions."""
    ensure_extensions_loaded()
    return [spec.to_dict() for spec in list_capabilities()]


@mcp.tool()
def tracecite_execute_capability(
    name: str,
    arguments: dict[str, Any] | None = None,
) -> Any:
    """Execute one registered capability under server-owner safety policy.

    Live grants are intentionally NOT model-controlled tool arguments. The MCP
    server owner grants them through environment configuration.
    """
    ensure_extensions_loaded()
    authorized_names = _authorized_capabilities()
    return execute_capability(
        name,
        arguments or {},
        allow_live_source=_env_bool("TRACECITE_MCP_ALLOW_LIVE_SOURCE"),
        allow_live_action=_env_bool("TRACECITE_MCP_ALLOW_LIVE_ACTION"),
        authorized="*" in authorized_names or name.strip().lower() in authorized_names,
    )


def main() -> None:
    """Run the server over stdio, the default local Agent-host transport."""
    ensure_extensions_loaded()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
