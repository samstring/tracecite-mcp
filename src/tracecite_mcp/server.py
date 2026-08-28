"""MCP projection of TraceCite's public Agent-facing API."""

from __future__ import annotations

import os
from typing import Any, Mapping

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
from tracecite.extension import (
    available_runtimes,
    list_extensions,
    load_extensions,
    loaded_plugins,
)
from tracecite.runtime import (
    EvidenceRequest,
    QueryTarget,
    RangeTarget,
    SourceTarget,
    retrieve,
)


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


def ensure_extensions_loaded() -> list[dict[str, Any]]:
    """Load installed TraceCite extensions once at the explicit MCP boundary."""
    global _EXTENSIONS_LOADED, _EXTENSION_LOAD_RESULT
    if not _EXTENSIONS_LOADED:
        _EXTENSION_LOAD_RESULT = list(load_extensions(strict=True))
        _EXTENSIONS_LOADED = True
    return list(_EXTENSION_LOAD_RESULT)


def _required_text(target: Mapping[str, Any], key: str) -> str:
    value = str(target.get(key) or "").strip()
    if not value:
        raise ValueError(f"retrieve target requires {key}")
    return value


def _optional_int(target: Mapping[str, Any], key: str) -> int | None:
    value = target.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"retrieve target {key} must be an integer")
    return value


def _build_retrieve_target(target: Mapping[str, Any]):
    if not isinstance(target, Mapping):
        raise ValueError("target must be an object")
    kind = str(target.get("kind") or "").strip().lower()
    source = _required_text(target, "source") if kind in {"source", "query", "range"} else ""

    if kind == "source":
        recursive = target.get("recursive", False)
        if not isinstance(recursive, bool):
            raise ValueError("retrieve target recursive must be a boolean")
        return SourceTarget(
            source=source,
            glob=str(target.get("glob") or "*"),
            recursive=recursive,
            segmenter=str(target.get("segmenter") or "auto"),
        )

    if kind == "query":
        return QueryTarget(
            source=source,
            query=_required_text(target, "query"),
            regex=bool(target.get("regex", False)),
            snapshot=bool(target.get("snapshot", True)),
            segmenter=str(target.get("segmenter") or "auto"),
            last=str(target["last"]) if target.get("last") is not None else None,
            since=str(target["since"]) if target.get("since") is not None else None,
            until=str(target["until"]) if target.get("until") is not None else None,
            fold=bool(target.get("fold", False)),
            max_evidence=_optional_int(target, "max_evidence"),
            max_line_chars=_optional_int(target, "max_line_chars"),
        )

    if kind == "range":
        start_line = _optional_int(target, "start_line")
        if start_line is None:
            raise ValueError("retrieve target requires start_line")
        return RangeTarget(
            source=source,
            start_line=start_line,
            end_line=_optional_int(target, "end_line"),
            before=int(target.get("before", 3)),
            after=int(target.get("after", 3)),
            expected_sha256=(
                str(target["expected_sha256"]).strip()
                if target.get("expected_sha256") is not None
                else None
            ),
            max_chars=int(target.get("max_chars", 20_000)),
        )

    if kind == "provider":
        raise ValueError(
            "provider targets require process-local EvidenceProvider objects and "
            "are not selectable through the generic MCP transport"
        )
    raise ValueError("retrieve target kind must be source, query, or range")


@mcp.tool()
def tracecite_retrieve(
    target: dict[str, Any],
    investigation_path: str | None = None,
    hypothesis_id: str | None = None,
    test_id: str | None = None,
    cache: bool = True,
) -> dict[str, Any]:
    """Acquire evidence through Core's canonical adaptive retrieve contract.

    ``target.kind`` is ``source``, ``query``, or ``range``. TraceCite Core owns
    adaptive routing, evidence novelty, coverage, signal hints, and stop reasons.
    """
    request = EvidenceRequest(
        target=_build_retrieve_target(target),
        investigation_path=investigation_path,
        hypothesis_id=hypothesis_id,
        test_id=test_id,
        cache=cache,
    )
    return retrieve(request).to_dict()


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
    """Compatibility wrapper: inspect source metadata without adaptive routing."""
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
) -> dict[str, Any]:
    """Compatibility wrapper: search without Core's adaptive retrieve routing."""
    return search(
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
    """Compatibility wrapper: expand one bounded cited range."""
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
    """List v2 extension manifests, load results, runtimes, and low-level plugins."""
    ensure_extensions_loaded()
    return {
        "extensions": list(_EXTENSION_LOAD_RESULT),
        "installed_extensions": list_extensions(),
        "runtimes": available_runtimes(),
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
