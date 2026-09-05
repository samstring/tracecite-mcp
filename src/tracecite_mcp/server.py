"""Thin MCP transport for TraceCite's canonical Evidence Runtime."""

from __future__ import annotations

import os
import shlex
from typing import Any, Mapping

from mcp.server import MCPServer

from tracecite import (
    EvidenceRequest,
    ProviderTarget,
    QueryTarget,
    RangeTarget,
    SourceTarget,
    TraversalLimits,
    materialize,
    replay,
    retrieve,
    traverse,
    verify,
)
from tracecite.runtime import (
    DEFAULT_MAX_EVIDENCE_BYTES,
    DEFAULT_MAX_EVIDENCE_TOKENS,
    EvidenceAnalysisSpec,
    EvidenceComputeRequest,
    EvidenceShellPolicy,
    EvidenceShellRequest,
    run_evidence_compute,
    run_evidence_shell,
)
from tracecite.extension.evidence import EntityRef
from tracecite.extension.retrieval import RetrieveRequest

from .capability_transport import discover_and_register_capability_tools
from .compute_projection import compact_compute_response
from .projection import compact_response
from .providers import resolve_providers
from .session import project_session, session_store
from .shell_projection import compact_shell_response
from .source_policy import available_evidence_sources, require_allowed_path, require_safe_glob


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
_QUERY_POLICY_ARGUMENTS = {
    "snapshot",
    "max_evidence",
    "max_line_chars",
    "fold",
}


def _positive_env_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _host_evidence_policy() -> EvidenceShellPolicy:
    """Resolve user/Host Evidence policy. Agent tool arguments cannot modify it."""

    return EvidenceShellPolicy(
        max_evidence_tokens=_positive_env_int(
            "TRACECITE_EVIDENCE_MAX_TOKENS", DEFAULT_MAX_EVIDENCE_TOKENS
        ),
        max_evidence_bytes=_positive_env_int(
            "TRACECITE_EVIDENCE_MAX_BYTES", DEFAULT_MAX_EVIDENCE_BYTES
        ),
    )


def _materialize_char_budget() -> int:
    policy = _host_evidence_policy()
    configured = _positive_env_int("TRACECITE_MATERIALIZE_MAX_CHARS", 8_000)
    return max(
        1,
        min(
            configured,
            policy.max_evidence_bytes,
            policy.max_evidence_tokens * 4,
        ),
    )


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
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


def _build_nonquery_retrieve(target: Mapping[str, Any]):
    if not isinstance(target, Mapping):
        raise ValueError("target must be an object")
    kind = str(target.get("kind") or "").strip().lower()

    range_args = sorted(_RANGE_ARGUMENTS.intersection(target))
    if kind == "range" or range_args:
        detail = f"; remove retrieve target fields: {', '.join(range_args)}" if range_args else ""
        raise ValueError(
            "tracecite_retrieve does not read exact line ranges. "
            "Use tracecite_materialize(session_id, source, start_line, end_line, "
            f"before, after, expected_sha256) instead{detail}"
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
        "target.kind must be 'query', 'source', or 'provider'. "
        "Text query work should normally use tracecite_run."
    )


def _range_target(
    source: str,
    start_line: int,
    end_line: int | None,
    before: int,
    after: int,
    expected_sha256: str | None,
) -> RangeTarget:
    return RangeTarget(
        source=require_allowed_path(source),
        start_line=start_line,
        end_line=end_line,
        before=before,
        after=after,
        expected_sha256=expected_sha256,
        max_chars=_materialize_char_budget(),
    )


def _display_source(target: object) -> str | None:
    source = getattr(target, "source", None)
    return str(source) if source is not None else None


def _missing_path_response(
    operation: str,
    requested_path: Any,
    error: FileNotFoundError,
    *,
    field: str = "source",
    error_code: str = "source_not_found",
) -> dict[str, Any]:
    resolved = str(getattr(error, "filename", None) or requested_path or "").strip()
    payload: dict[str, Any] = {
        "operation": operation,
        "status": "error",
        "error_code": error_code,
        "error": (
            f"evidence path does not exist: {resolved}"
            if resolved
            else "evidence path does not exist"
        ),
    }
    if resolved:
        payload[field] = resolved
    available = available_evidence_sources()
    if available:
        payload["available_sources"] = list(available)
    return compact_response(
        payload,
        display_source=resolved if field == "source" else None,
    )


def _operation_error_response(
    operation: str,
    error: Exception | str,
    *,
    source: str | None = None,
    error_code: str,
    guidance: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "operation": operation,
        "status": "error",
        "error_code": error_code,
        "error": str(error),
    }
    if guidance:
        payload["guidance"] = guidance
    return compact_response(payload, display_source=source)


def _run_shell(
    *,
    session_id: str,
    source: str,
    program: str,
    segmenter: str = "auto",
    last: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    try:
        resolved_source = require_allowed_path(source)
        store = session_store(session_id)
        payload = run_evidence_shell(
            EvidenceShellRequest(
                source=resolved_source,
                program=program,
                segmenter=segmenter,
                last=last,
                since=since,
                until=until,
            ),
            policy=_host_evidence_policy(),
            session=store,
        )
    except FileNotFoundError as exc:
        return _missing_path_response("evidence_shell", source, exc)
    return compact_shell_response(
        project_session(payload, store),
        display_source=resolved_source,
    )


@mcp.tool()
def tracecite_run(
    session_id: str,
    source: str,
    program: str,
    segmenter: str = "auto",
    last: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    """Run one safe Evidence Shell program against the session-fixed SourceVersion.

    Compose literal/regex search, structured filtering, selection, near/seek,
    count/group/distinct and related mechanical operations in one pipeline.
    Intermediate rows remain inside TraceCite. Evidence token/byte limits and
    source snapshot/live policy are user/Host settings and are not Agent
    arguments. If status=too_broad, refine the program; never ask to enlarge
    the budget or request a complete locator dump.
    """

    return _run_shell(
        session_id=session_id,
        source=source,
        program=program,
        segmenter=segmenter,
        last=last,
        since=since,
        until=until,
    )


@mcp.tool()
def tracecite_analyze(
    session_id: str,
    source: str,
    analyses: list[dict[str, str]],
    segmenter: str = "auto",
    last: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    """Run several caller-selected bounded computations in one tool call.

    Use this when the Agent has already decided that multiple mechanical
    aggregate or bounded top-K/project checks are needed over the same evidence
    source. Optional last/since/until are explicit mechanical scopes applied to
    the whole batch. TraceCite may fuse compatible scans internally. This tool
    does not choose which analyses or windows are relevant and does not perform
    causal reasoning.
    """

    if not isinstance(analyses, list):
        raise ValueError("analyses must be an array")
    specs: list[EvidenceAnalysisSpec] = []
    for item in analyses:
        if not isinstance(item, Mapping):
            raise ValueError("each analysis must be an object with name and program")
        specs.append(
            EvidenceAnalysisSpec(
                name=_required_text(item, "name"),
                program=_required_text(item, "program"),
            )
        )

    try:
        resolved_source = require_allowed_path(source)
        store = session_store(session_id)
        payload = run_evidence_compute(
            EvidenceComputeRequest(
                source=resolved_source,
                analyses=tuple(specs),
                segmenter=segmenter,
                last=last,
                since=since,
                until=until,
            ),
            policy=_host_evidence_policy(),
            session=store,
        )
    except FileNotFoundError as exc:
        return _missing_path_response("evidence_compute", source, exc)
    return compact_compute_response(
        project_session(payload, store),
        display_source=resolved_source,
    )


@mcp.tool()
def tracecite_retrieve(
    session_id: str,
    target: dict[str, Any],
    cache: bool = True,
) -> dict[str, Any]:
    """Compatibility retrieval surface; prefer tracecite_run for text queries.

    Query targets are translated to one Evidence Shell search under the fixed
    Host policy. Agent-controlled snapshot/max_evidence/max_line_chars/fold
    fields are rejected. Source/provider targets remain canonical compatibility
    operations.
    """

    if not isinstance(target, Mapping):
        raise ValueError("target must be an object")
    kind = str(target.get("kind") or "").strip().lower()
    if kind == "query":
        forbidden = sorted(_QUERY_POLICY_ARGUMENTS.intersection(target))
        if forbidden:
            raise ValueError(
                "query policy is owned by the user/Host; remove fields: "
                + ", ".join(forbidden)
            )
        source = _required_text(target, "source")
        query = _required_text(target, "query")
        regex = _bool_value(target, "regex", False)
        command = "regex" if regex else "search"
        return _run_shell(
            session_id=session_id,
            source=source,
            program=f"{command} {shlex.quote(query)}",
            segmenter=str(target.get("segmenter") or "auto"),
            last=str(target["last"]) if target.get("last") is not None else None,
            since=str(target["since"]) if target.get("since") is not None else None,
            until=str(target["until"]) if target.get("until") is not None else None,
        )

    source_hint = target.get("source") if kind == "source" else None
    try:
        built_target, providers = _build_nonquery_retrieve(target)
        store = session_store(session_id)
        result = retrieve(
            EvidenceRequest(target=built_target, cache=cache, providers=providers),
            session=store,
        )
    except FileNotFoundError as exc:
        if source_hint is None:
            raise
        return _missing_path_response("retrieve", source_hint, exc)
    return compact_response(
        project_session(result.to_dict(), store),
        display_source=_display_source(built_target),
    )


@mcp.tool()
def tracecite_materialize(
    session_id: str,
    source: str,
    start_line: int,
    end_line: int | None = None,
    before: int = 3,
    after: int = 3,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Read exact context for a caller-selected EvidencePointer.

    The output ceiling is user/Host policy; the Agent cannot pass max_chars.
    Prefer the pointer's immutable materialize source and expected SHA when
    supplied. Reuse the same session_id for the whole conversation.
    """

    try:
        store = session_store(session_id)
        resolved_source = require_allowed_path(source)
        result = materialize(
            _range_target(
                resolved_source,
                start_line,
                end_line,
                before,
                after,
                expected_sha256,
            ),
            session=store,
        )
    except FileNotFoundError as exc:
        return _missing_path_response("materialize", source, exc)
    return compact_response(
        project_session(result.to_dict(), store),
        display_source=resolved_source,
    )


@mcp.tool()
def tracecite_replay(
    session_id: str,
    source: str,
    start_line: int,
    expected_sha256: str | None = None,
    end_line: int | None = None,
    before: int = 3,
    after: int = 3,
) -> dict[str, Any]:
    """Deliberately re-read previously covered immutable Evidence.

    Replay is bounded by the same user/Host Evidence policy and does not expose
    a caller-controlled output limit. Semantic replay failures are returned as
    structured tool results so MCP adapters do not misreport them as missing
    parameters and provoke blind retries.
    """

    expected = str(expected_sha256 or "").strip()
    if not expected:
        return _operation_error_response(
            "replay",
            "expected_sha256 is required for immutable replay identity",
            source=source,
            error_code="replay_requires_sha256",
            guidance="Reuse the SHA from the EvidencePointer or prior materialize result.",
        )

    try:
        store = session_store(session_id)
        resolved_source = require_allowed_path(source)
        result = replay(
            _range_target(
                resolved_source,
                start_line,
                end_line,
                before,
                after,
                expected,
            ),
            session=store,
        )
    except FileNotFoundError as exc:
        return _missing_path_response("replay", source, exc)
    except (TypeError, ValueError) as exc:
        message = str(exc)
        guidance = (
            "Replay only works for immutable context already materialized in this RetrievalSession. "
            "Reuse the same source/SHA and the same or a smaller before/after range."
            if "materialized" in message or "covered" in message
            else "Use the exact source, line range and SHA returned by TraceCite materialize/evidence pointers."
        )
        return _operation_error_response(
            "replay",
            exc,
            source=source,
            error_code="replay_unavailable",
            guidance=guidance,
        )
    return compact_response(
        project_session(result.to_dict(), store),
        display_source=resolved_source,
    )


@mcp.tool()
def tracecite_aggregate(
    session_id: str,
    source: str,
    query: str,
    operation: str = "count",
    regex: bool = False,
) -> dict[str, Any]:
    """Compatibility aggregate surface bound to the RetrievalSession SourceVersion.

    New Agent flows should use tracecite_run with `| count`, `| group FIELD`, or
    `| distinct FIELD`. This compatibility tool supports count only so it cannot
    bypass SessionSourceView through the old stateless aggregate implementation.
    """

    if str(operation or "").strip().lower() != "count":
        raise ValueError(
            "tracecite_aggregate compatibility supports count only; "
            "use tracecite_run for group/distinct"
        )
    command = "regex" if regex else "search"
    return _run_shell(
        session_id=session_id,
        source=source,
        program=f"{command} {shlex.quote(query)} | count",
    )


@mcp.tool()
def tracecite_traverse(
    provider_names: list[str],
    seed_evidence_ids: list[str] | None = None,
    seed_entities: list[dict[str, Any]] | None = None,
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Traverse caller-selected identities through Host-registered providers."""

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
    """Verify evidence manifest/integrity facts mechanically."""

    try:
        result = verify(require_allowed_path(manifest_path))
    except FileNotFoundError as exc:
        return _missing_path_response(
            "verify",
            manifest_path,
            exc,
            field="path",
            error_code="manifest_not_found",
        )
    return compact_response(result)


def initialize_extension_tools(*, strict: bool = False) -> dict[str, str]:
    """Discover installed TraceCite extensions and project AgentCapabilities."""

    return discover_and_register_capability_tools(mcp, strict=strict)


def main() -> None:
    """Run the evidence MCP server plus installed extension capabilities."""

    initialize_extension_tools(strict=False)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
