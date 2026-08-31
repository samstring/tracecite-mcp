from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from tracecite_mcp import server


EXPECTED_TOOLS = {
    "tracecite_retrieve",
    "tracecite_materialize",
    "tracecite_replay",
    "tracecite_aggregate",
    "tracecite_traverse",
    "tracecite_verify",
}


def _use_session_root(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setenv("TRACECITE_MCP_SESSION_ROOT", str(root))
    monkeypatch.delenv("TRACECITE_MCP_SESSION_ID", raising=False)


def test_mcp_exposes_only_canonical_evidence_runtime_tools() -> None:
    tools = asyncio.run(server.mcp.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_TOOLS


def test_retrieve_uses_persistent_retrieval_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_session_root(monkeypatch, tmp_path / "sessions")
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")
    target = {
        "kind": "query",
        "source": str(source),
        "query": "target",
        "segmenter": "rawtext",
    }

    first = server.tracecite_retrieve(target, session_id="investigation-a")
    repeated = server.tracecite_retrieve(target, session_id="investigation-a")
    independent = server.tracecite_retrieve(target, session_id="investigation-b")

    assert first["status"] == "ok"
    assert first["evidence"]
    assert repeated["coverage"]["new_evidence"] == 0
    assert repeated["coverage"]["repeated_evidence"] >= 1
    assert independent["evidence"]


def test_materialize_then_replay_preserves_novelty_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_session_root(monkeypatch, tmp_path / "sessions")
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    materialized = server.tracecite_materialize(
        str(source),
        2,
        before=0,
        after=0,
        expected_sha256=digest,
        session_id="investigation-a",
    )
    replayed = server.tracecite_replay(
        str(source),
        2,
        digest,
        before=0,
        after=0,
        session_id="investigation-a",
    )

    assert materialized["evidence"]
    assert replayed["operation"] == "replay"
    assert replayed["coverage"]["new_evidence"] == 0
    assert replayed["data"]["novelty"]["state"] == "replay"


def test_replay_requires_prior_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_session_root(monkeypatch, tmp_path / "sessions")
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="has not been materialized"):
        server.tracecite_replay(
            str(source),
            2,
            digest,
            before=0,
            after=0,
            session_id="fresh-session",
        )


def test_aggregate_is_mechanical_and_stateless(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("error A\nok\nerror B\nerror A\n", encoding="utf-8")

    result = server.tracecite_aggregate(str(source), "error", operation="count")

    assert result["operation"] == "aggregate"
    assert result["data"]["count"] == 3
    assert result["coverage"]["complete"] is True


def test_traverse_accepts_serialized_provider_snapshot() -> None:
    provider = {
        "name": "fixture",
        "evidence": [
            {
                "id": "e1",
                "kind": "log",
                "source": "runtime.log",
                "label": "request started",
                "entities": [{"kind": "request", "value": "7"}],
            },
            {
                "id": "e2",
                "kind": "log",
                "source": "runtime.log",
                "label": "request failed",
                "entities": [{"kind": "request", "value": "7"}],
            },
        ],
    }

    result = server.tracecite_traverse(provider, seed_evidence_ids=["e1"])

    assert result["status"] in {"ok", "partial"}
    assert result["graph"]["nodes"] >= 1
    assert "progress" in result


def test_retrieve_range_is_not_a_compatibility_backdoor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_session_root(monkeypatch, tmp_path / "sessions")
    source = tmp_path / "app.log"
    source.write_text("alpha\n", encoding="utf-8")

    with pytest.raises(ValueError, match="tracecite_materialize"):
        server.tracecite_retrieve(
            {"kind": "range", "source": str(source), "start_line": 1},
            session_id="investigation-a",
        )


def test_verify_is_a_thin_core_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        server,
        "verify",
        lambda path: {"operation": "verify", "status": "ok", "path": str(path)},
    )

    result = server.tracecite_verify("manifest.json")

    assert result == {
        "operation": "verify",
        "status": "ok",
        "path": "manifest.json",
    }
