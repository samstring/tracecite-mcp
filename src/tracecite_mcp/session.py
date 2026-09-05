"""Host-owned mapping from MCP investigation IDs to Core RetrievalSession."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from tracecite import RetrievalSessionStore


def state_root() -> Path:
    """Return the server-owned persistence root for retrieval sessions."""
    configured = os.environ.get("TRACECITE_MCP_STATE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".tracecite" / "mcp").resolve()


def effective_session_id(session_id: str) -> str:
    """Return the Host-pinned investigation ID when one is configured.

    Some Agent transports synthesize a fresh request/session token for every
    tool call. That must not silently fragment one evidence investigation into
    many Core RetrievalSessions. A Host that knows the conversation boundary may
    therefore pin one stable ID with ``TRACECITE_MCP_SESSION_ID``. When the Host
    does not pin an ID, the caller-provided value keeps the existing behavior.
    """

    pinned = str(os.environ.get("TRACECITE_MCP_SESSION_ID") or "").strip()
    if pinned:
        return pinned
    supplied = str(session_id or "").strip()
    if not supplied:
        raise ValueError("session_id is required")
    return supplied


def session_store(session_id: str) -> RetrievalSessionStore:
    """Resolve one MCP investigation to Core's canonical RetrievalSessionStore."""
    return RetrievalSessionStore(
        state_root(),
        effective_session_id(session_id),
        namespace="_retrieval_sessions",
        legacy_evidence_context=False,
    )


def project_session(
    payload: Mapping[str, Any],
    store: RetrievalSessionStore,
) -> dict[str, Any]:
    """Attach only mechanical Host/session metadata to a Core result."""
    result = dict(payload)
    state = store.load()
    result["mcp_session"] = {
        "session_id": state.context_id,
        "revision": state.revision,
        "progress": state.retrieval_summary(),
    }
    return result


__all__ = ["effective_session_id", "project_session", "session_store", "state_root"]
