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


def session_store(session_id: str) -> RetrievalSessionStore:
    """Resolve one MCP session ID to Core's canonical RetrievalSessionStore."""
    return RetrievalSessionStore(
        state_root(),
        session_id,
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
