"""Thin MCP projection of TraceCite's canonical Evidence Runtime."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from mcp.server import MCPServer

from tracecite import (
    AggregateRequest,
    EvidenceRequest,
    QueryTarget,
    RangeTarget,
    RetrievalSessionStore,
    SourceTarget,
    TraversalLimits,
    aggregate,
    materialize,
    replay,
    retrieve,
    traverse,
    verify,
)
from tracecite.extension.evidence import EntityRef, EvidenceRelation
from tracecite.extension.retrieval import (
    ProviderEvidence,
    RetrieveRequest as ProviderRetrieveRequest,
    RetrieveResult as ProviderRetrieveResult,
)


mcp = MCPServer("TraceCite")


def _session_root() -> Path:
    configured = str(os.environ.get("TRACECITE_MCP_SESSION_ROOT") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".tracecite" / "mcp").resolve()


def _session_store(session_id: str | None) -> RetrievalSessionStore:
    resolved = str(
        session_id
        or os.environ.get("TRACECITE_MCP_SESSION_ID")
        or "default"
    ).strip()
    return RetrievalSessionStore(
        _session_root(),
        resolved,
        namespace="_retrieval_sessions",
        legacy_evidence_context=False,
    )


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} must be non-empty")
    return value


def _optional_int(payload: Mapping[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _build_retrieve_target(target: Mapping[str, Any]) -> SourceTarget | QueryTarget:
    if not isinstance(target, Mapping):
        raise ValueError("target must be an object")
    kind = str(target.get("kind") or "").strip().lower()
    source = _required_text(target, "source")

    if kind == "source":
        recursive = target.get("recursive", False)
        if not isinstance(recursive, bool):
            raise ValueError("recursive must be a boolean")
        return SourceTarget(
            source=source,
            glob=str(target.get("glob") or "*"),
            recursive=recursive,
            segmenter=str(target.get("segmenter") or "auto"),
        )

    if kind == "query":
        regex = target.get("regex", False)
        snapshot = target.get("snapshot", True)
        fold = target.get("fold", False)
        for name, value in (("regex", regex), ("snapshot", snapshot), ("fold", fold)):
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be a boolean")
        return QueryTarget(
            source=source,
            query=_required_text(target, "query"),
            regex=regex,
            snapshot=snapshot,
            segmenter=str(target.get("segmenter") or "auto"),
            last=str(target["last"]) if target.get("last") is not None else None,
            since=str(target["since"]) if target.get("since") is not None else None,
            until=str(target["until"]) if target.get("until") is not None else None,
            fold=fold,
            max_evidence=_optional_int(target, "max_evidence"),
            max_line_chars=_optional_int(target, "max_line_chars"),
        )

    if kind == "range":
        raise ValueError("range retrieval is exposed as tracecite_materialize")
    if kind == "provider":
        raise ValueError("provider traversal is exposed as tracecite_traverse")
    raise ValueError("target.kind must be source or query")


def _range_target(
    source: str,
    start_line: int,
    *,
    end_line: int | None,
    before: int,
    after: int,
    expected_sha256: str | None,
    max_chars: int,
) -> RangeTarget:
    return RangeTarget(
        source=source,
        start_line=start_line,
        end_line=end_line,
        before=before,
        after=after,
        expected_sha256=expected_sha256,
        max_chars=max_chars,
    )


class _SerializedProvider:
    """Process-local adapter for caller-supplied provider-shaped evidence."""

    def __init__(self, payload: Mapping[str, Any]) -> None:
        if not isinstance(payload, Mapping):
            raise ValueError("provider must be an object")
        self.name = str(payload.get("name") or "mcp-provider").strip()
        if not self.name:
            raise ValueError("provider.name must be non-empty")

        evidence = payload.get("evidence") or []
        relations = payload.get("relations") or []
        if not isinstance(evidence, list) or not isinstance(relations, list):
            raise ValueError("provider evidence and relations must be arrays")
        self._evidence = tuple(ProviderEvidence.from_mapping(item) for item in evidence)
        self._relations = tuple(EvidenceRelation.from_mapping(item) for item in relations)

    @staticmethod
    def _entity_keys(request: ProviderRetrieveRequest) -> set[tuple[str, str, str]]:
        return {item.key for item in request.entities}

    def _selected(self, request: ProviderRetrieveRequest) -> tuple[ProviderEvidence, ...]:
        evidence_ids = set(request.evidence_ids)
        entity_keys = self._entity_keys(request)
        selected: list[ProviderEvidence] = []
        for row in self._evidence:
            by_id = bool(evidence_ids and row.id in evidence_ids)
            by_entity = bool(
                entity_keys and any(entity.key in entity_keys for entity in row.entities)
            )
            if by_id or by_entity:
                selected.append(row)
        return tuple(selected)

    def can_handle(self, request: ProviderRetrieveRequest) -> bool:
        return bool(self._selected(request))

    def retrieve(self, request: ProviderRetrieveRequest) -> ProviderRetrieveResult:
        selected_all = self._selected(request)
        selected = selected_all[: request.limit]
        selected_ids = {item.id for item in selected}
        relations = tuple(
            item
            for item in self._relations
            if item.source_id in selected_ids or item.target_id in selected_ids
        )
        return ProviderRetrieveResult(
            status="ok",
            evidence=selected,
            relations=relations,
            coverage={"complete": len(selected_all) <= len(selected)},
            diagnostics={"adapter": "mcp_serialized_provider"},
        )


def _seed_entities(raw: list[dict[str, Any]] | None) -> tuple[EntityRef, ...]:
    return tuple(EntityRef.from_mapping(item) for item in (raw or []))


@mcp.tool()
def tracecite_retrieve(
    target: dict[str, Any],
    session_id: str = "default",
) -> dict[str, Any]:
    """Retrieve caller-selected evidence with provenance, coverage and session novelty.

    ``target.kind`` is ``source`` or ``query``. The Agent chooses the source and
    query. ``session_id`` scopes mechanical evidence memory only; it never stores
    hypotheses, conclusions, evidence sufficiency, or stopping decisions.
    """
    session = _session_store(session_id)
    result = retrieve(
        EvidenceRequest(_build_retrieve_target(target)),
        session=session,
    )
    return result.to_dict()


@mcp.tool()
def tracecite_materialize(
    source: str,
    start_line: int,
    end_line: int | None = None,
    before: int = 3,
    after: int = 3,
    expected_sha256: str | None = None,
    max_chars: int = 20_000,
    session_id: str = "default",
) -> dict[str, Any]:
    """Materialize exact bounded source context selected by the Agent."""
    session = _session_store(session_id)
    result = materialize(
        _range_target(
            source,
            start_line,
            end_line=end_line,
            before=before,
            after=after,
            expected_sha256=expected_sha256,
            max_chars=max_chars,
        ),
        session=session,
    )
    return result.to_dict()


@mcp.tool()
def tracecite_replay(
    source: str,
    start_line: int,
    expected_sha256: str,
    end_line: int | None = None,
    before: int = 3,
    after: int = 3,
    max_chars: int = 20_000,
    session_id: str = "default",
) -> dict[str, Any]:
    """Re-read already-covered immutable evidence without counting it as new."""
    session = _session_store(session_id)
    result = replay(
        _range_target(
            source,
            start_line,
            end_line=end_line,
            before=before,
            after=after,
            expected_sha256=expected_sha256,
            max_chars=max_chars,
        ),
        session=session,
    )
    return result.to_dict()


@mcp.tool()
def tracecite_aggregate(
    source: str,
    query: str,
    operation: str = "count",
    regex: bool = False,
    group_regex: str | None = None,
    max_groups: int = 100,
) -> dict[str, Any]:
    """Run deterministic count/distinct/group over caller-selected local evidence."""
    request = AggregateRequest(
        source=source,
        query=query,
        regex=regex,
        operation=operation,  # type: ignore[arg-type]
        group_regex=group_regex,
        max_groups=max_groups,
    )
    return aggregate(request)


@mcp.tool()
def tracecite_traverse(
    provider: dict[str, Any],
    seed_evidence_ids: list[str] | None = None,
    seed_entities: list[dict[str, Any]] | None = None,
    max_depth: int = 3,
    max_retrievals: int = 12,
    max_evidence: int = 500,
    max_wall_seconds: float = 5.0,
    per_request_limit: int = 100,
) -> dict[str, Any]:
    """Run bounded deterministic traversal from caller-selected IDs/entities.

    ``provider`` is a serialized provider snapshot with ``name``, ``evidence[]``
    and optional ``relations[]``. The Agent owns seeds and limits; TraceCite does
    not choose the investigation direction.
    """
    ids = tuple(str(item).strip() for item in (seed_evidence_ids or []) if str(item).strip())
    entities = _seed_entities(seed_entities)
    if not ids and not entities:
        raise ValueError("traverse requires seed_evidence_ids or seed_entities")

    result = traverse(
        (_SerializedProvider(provider),),
        seed_evidence_ids=ids,
        seed_entities=entities,
        exploration_policy=TraversalLimits(
            max_depth=max_depth,
            max_retrievals=max_retrievals,
            max_evidence=max_evidence,
            max_wall_seconds=max_wall_seconds,
            per_request_limit=per_request_limit,
        ),
    )
    return result.to_dict()


@mcp.tool()
def tracecite_verify(manifest_path: str) -> dict[str, Any]:
    """Verify mechanical integrity of a caller-selected evidence manifest."""
    return verify(Path(manifest_path))


def main() -> None:
    """Run the evidence-only MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
