"""Thin MCP transport for TraceCite's canonical Evidence Runtime."""

from __future__ import annotations

from typing import Any, Mapping

from mcp.server import MCPServer

from tracecite import (
    AggregateRequest,
    EvidenceRequest,
    ProviderTarget,
    QueryTarget,
    RangeTarget,
    SourceTarget,
    TraversalLimits,
    aggregate,
    materialize,
    replay,
    retrieve,
    traverse,
    verify,
)
from tracecite.extension.evidence import EntityRef
from tracecite.extension.retrieval import RetrieveRequest

from .projection import compact_response
from .providers import resolve_providers
from .session import project_session, session_store
from .source_policy import require_allowed_path, require_safe_glob


mcp = MCPServer("TraceCite")

_RANGE_ARGUMENTS = {
    "start_line",
    "end_line",
    "line_count",
    "before",
    "after",
    "expected_sha256",
    "max_chars",
}


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _optional_int(payload: Mapping[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _int_value(payload: Mapping[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _bool_value(payload: Mapping[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _entities(values: Any) -> tuple[EntityRef, ...]:
    raw = values or []
    if not isinstance(raw, list):
        raise ValueError("entities must be an array")
    return tuple(
        item if isinstance(item, EntityRef) else EntityRef.from_mapping(item)
        for item in raw
    )


def _provider_request(payload: Mapping[str, Any]) -> RetrieveRequest:
    raw_ids = payload.get("evidence_ids") or []
    if not isinstance(raw_ids, list):
        raise ValueError("provider request evidence_ids must be an array")
    attributes = payload.get("attributes") or {}
    if not isinstance(attributes, Mapping):
        raise ValueError("provider request attributes must be an object")
    return RetrieveRequest(
        evidence_ids=tuple(str(item).strip() for item in raw_ids if str(item).strip()),
        entities=_entities(payload.get("entities")),
        limit=_int_value(payload, "limit", 100),
        depth=_int_value(payload, "depth", 0),
        reason=str(payload.get("reason") or "mcp"),
        attributes=dict(attributes),
    )


def _build_retrieve(target: Mapping[str, Any]):
    if not isinstance(target, Mapping):
        raise ValueError("target must be an object")
    kind = str(target.get("kind") or "").strip().lower()

    range_args = sorted(_RANGE_ARGUMENTS.intersection(target))
    if kind == "range" or range_args:
        detail = f"; remove retrieve target fields: {', '.join(range_args)}" if range_args else ""
        raise ValueError(
            "tracecite_retrieve does not read exact line ranges. "
            "Use tracecite_materialize(session_id, source, start_line, end_line, "
            f"before, after, expected_sha256, max_chars) instead{detail}"
        )

    if kind == "source":
        source = require_allowed_path(_required_text(target, "source"))
        return (
            SourceTarget(
                source=source,
                glob=require_safe_glob(str(target.get("glob") or "*")),
                recursive=_bool_value(target, "recursive", False),
                segmenter=str(target.get("segmenter") or "auto"),
            ),
            (),
        )

    if kind == "query":
        source = require_allowed_path(_required_text(target, "source"))
        return (
            QueryTarget(
                source=source,
                query=_required_text(target, "query"),
                regex=_bool_value(target, "regex", False),
                snapshot=_bool_value(target, "snapshot", True),
                segmenter=str(target.get("segmenter") or "auto"),
                last=str(target["last"]) if target.get("last") is not None else None,
                since=str(target["since"]) if target.get("since") is not None else None,
                until=str(target["until"]) if target.get("until") is not None else None,
                fold=_bool_value(target, "fold", False),
                max_evidence=_optional_int(target, "max_evidence"),
                max_line_chars=_optional_int(target, "max_line_chars"),
            ),
            (),
        )

    if kind == "provider":
        names = target.get("provider_names") or []
        if not isinstance(names, list):
            raise ValueError("provider_names must be an array")
        providers = resolve_providers(names)
        request_payload = target.get("request") or {}
        if not isinstance(request_payload, Mapping):
            raise ValueError("provider target request must be an object")
        return ProviderTarget(_provider_request(request_payload)), providers

    raise ValueError(
        "target.kind is required and must be 'query', 'source', or 'provider'. "
        "For exact line/range reads use tracecite_materialize, not tracecite_retrieve."
    )


def _range_target(
    source: str,
    start_line: int,
    end_line: int | None,
    before: int,
    after: int,
    expected_sha256: str | None,
    max_chars: int,
) -> RangeTarget:
    return RangeTarget(
        source=require_allowed_path(source),
        start_line=start_line,
        end_line=end_line,
        before=before,
        after=after,
        expected_sha256=expected_sha256,
        max_chars=max_chars,
    )


@mcp.tool()
def tracecite_retrieve(
    session_id: str,
    target: dict[str, Any],
    cache: bool = True,
) -> dict[str, Any]:
    """Search/acquire caller-selected evidence; not an exact-range reader.

    Reuse one stable session_id for the investigation. target.kind must be:
    query={source, query, regex?...}, source={source, glob?...}, or
    provider={provider_names, request}. Never put start_line/end_line/line_count
    in target; use tracecite_materialize for known ranges.

    Returns compact mechanical evidence plus provenance/coverage/session facts.
    coverage.new_evidence=0 means no new evidence identity entered this session;
    repeated evidence may still match the current query. A hit/no_match/complete
    scope is evidence mechanics, never a causal, sufficiency, or stop decision.
    """
    built_target, providers = _build_retrieve(target)
    store = session_store(session_id)
    result = retrieve(
        EvidenceRequest(target=built_target, cache=cache, providers=providers),
        session=store,
    )
    return compact_response(project_session(result.to_dict(), store))


@mcp.tool()
def tracecite_materialize(
    session_id: str,
    source: str,
    start_line: int,
    end_line: int | None = None,
    before: int = 3,
    after: int = 3,
    expected_sha256: str | None = None,
    max_chars: int = 20_000,
) -> dict[str, Any]:
    """Read exact bounded context for caller-selected known source lines.

    Use after retrieve gives a useful ref/line range. Reuse the investigation's
    session_id. Pass expected_sha256 when available to bind the read to the
    immutable source version already observed. Returned text/provenance are
    evidence; coverage/novelty describe the mechanical session, not causality.
    """
    store = session_store(session_id)
    result = materialize(
        _range_target(
            source,
            start_line,
            end_line,
            before,
            after,
            expected_sha256,
            max_chars,
        ),
        session=store,
    )
    return compact_response(project_session(result.to_dict(), store))


@mcp.tool()
def tracecite_replay(
    session_id: str,
    source: str,
    start_line: int,
    expected_sha256: str,
    end_line: int | None = None,
    before: int = 3,
    after: int = 3,
    max_chars: int = 20_000,
) -> dict[str, Any]:
    """Deliberately re-read previously covered immutable evidence.

    Requires the same investigation session_id, prior coverage, and immutable
    source SHA-256. Replay intentionally returns already-known evidence and
    keeps new_evidence=0; replay is not newly discovered support and does not
    imply the investigation is complete.
    """
    store = session_store(session_id)
    result = replay(
        _range_target(
            source,
            start_line,
            end_line,
            before,
            after,
            expected_sha256,
            max_chars,
        ),
        session=store,
    )
    return compact_response(project_session(result.to_dict(), store))


@mcp.tool()
def tracecite_aggregate(
    source: str,
    query: str,
    operation: str = "count",
    regex: bool = False,
    group_regex: str | None = None,
    max_groups: int = 100,
) -> dict[str, Any]:
    """Compute deterministic count/distinct/group facts over caller scope.

    Aggregation is stateless evidence mechanics. coverage.complete means the
    requested aggregation scope completed; frequency/dominance is not causal
    importance and this tool never chooses a hypothesis or stopping decision.
    """
    return compact_response(
        aggregate(
            AggregateRequest(
                source=require_allowed_path(source),
                query=query,
                regex=regex,
                operation=operation,
                group_regex=group_regex,
                max_groups=max_groups,
            )
        )
    )


@mcp.tool()
def tracecite_traverse(
    provider_names: list[str],
    seed_evidence_ids: list[str] | None = None,
    seed_entities: list[dict[str, Any]] | None = None,
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Traverse caller-selected identities through Host-registered providers.

    The caller chooses providers, seed Evidence IDs/EntityRefs, and hard limits.
    Providers are process-local Host objects, never model-supplied code or
    serialized snapshots. stop_reason/frontier exhaustion is a mechanical end
    condition, not proof, sufficiency, causal ranking, or a next-step decision.
    """
    providers = resolve_providers(provider_names)
    raw_limits = limits or {}
    if not isinstance(raw_limits, Mapping):
        raise ValueError("limits must be an object")
    result = traverse(
        providers,
        seed_evidence_ids=tuple(seed_evidence_ids or ()),
        seed_entities=_entities(seed_entities),
        exploration_policy=TraversalLimits(**dict(raw_limits)),
    )
    return compact_response(result.to_dict())


@mcp.tool()
def tracecite_verify(manifest_path: str) -> dict[str, Any]:
    """Verify evidence manifest/integrity facts mechanically.

    A successful verification means the requested integrity check passed. It
    does not validate a hypothesis, causal chain, evidence sufficiency, or stop.
    """
    return compact_response(verify(require_allowed_path(manifest_path)))


def main() -> None:
    """Run the evidence-only MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
