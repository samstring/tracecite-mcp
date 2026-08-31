from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from tracecite.extension.retrieval import ProviderEvidence, RetrieveResult
from tracecite_mcp import clear_providers, register_provider
from tracecite_mcp import server


EXPECTED_TOOLS = {
    "tracecite_retrieve",
    "tracecite_materialize",
    "tracecite_replay",
    "tracecite_aggregate",
    "tracecite_traverse",
    "tracecite_verify",
}


@pytest.fixture(autouse=True)
def isolate_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRACECITE_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("TRACECITE_MCP_ALLOWED_ROOTS", str(tmp_path))
    clear_providers()
    yield
    clear_providers()


def test_mcp_exposes_only_canonical_evidence_runtime_tools() -> None:
    tools = asyncio.run(server.mcp.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_TOOLS


def test_mcp_tool_descriptions_explain_usage_and_result_boundaries() -> None:
    tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}

    retrieve = tools["tracecite_retrieve"].description or ""
    assert 'target.kind' in retrieve
    assert 'tracecite_materialize' in retrieve
    assert 'new_evidence=0' in retrieve
    assert 'causal' in retrieve

    materialize = tools["tracecite_materialize"].description or ""
    assert 'expected_sha256' in materialize
    assert 'immutable source version' in materialize

    replay = tools["tracecite_replay"].description or ""
    assert 'new_evidence=0' in replay
    assert 'not newly discovered support' in replay

    aggregate = tools["tracecite_aggregate"].description or ""
    assert 'frequency/dominance is not causal' in aggregate

    traverse = tools["tracecite_traverse"].description or ""
    assert 'mechanical end' in traverse
    assert 'not proof' in traverse

    verify = tools["tracecite_verify"].description or ""
    assert 'does not validate a hypothesis' in verify


def test_retrieve_uses_persistent_core_retrieval_session(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")
    target = {
        "kind": "query",
        "source": str(source),
        "query": "target",
        "segmenter": "rawtext",
    }

    first = server.tracecite_retrieve("investigation-a", target)
    repeated = server.tracecite_retrieve("investigation-a", target)
    independent = server.tracecite_retrieve("investigation-b", target)

    assert first["status"] == "ok"
    assert first["evidence"]
    assert first["mcp_session"]["session_id"] == "investigation-a"
    assert repeated["coverage"]["new_evidence"] == 0
    assert repeated["coverage"]["repeated_evidence"] >= 1
    assert repeated["mcp_session"]["revision"] > first["mcp_session"]["revision"]
    assert independent["evidence"]


def test_materialize_then_replay_preserves_novelty_boundary(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    materialized = server.tracecite_materialize(
        "investigation-a",
        str(source),
        2,
        before=0,
        after=0,
        expected_sha256=digest,
    )
    replayed = server.tracecite_replay(
        "investigation-a",
        str(source),
        2,
        digest,
        before=0,
        after=0,
    )

    assert materialized["evidence"]
    assert replayed["operation"] == "replay"
    assert replayed["coverage"]["new_evidence"] == 0
    assert replayed["data"]["novelty"]["state"] == "replay"
    assert replayed["mcp_session"]["progress"]["operation_counts"]["replay"] == 1


def test_replay_requires_prior_coverage(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="has not been materialized"):
        server.tracecite_replay(
            "fresh-session",
            str(source),
            2,
            digest,
            before=0,
            after=0,
        )


def test_aggregate_is_mechanical_and_stateless(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("error A\nok\nerror B\nerror A\n", encoding="utf-8")

    result = server.tracecite_aggregate(str(source), "error", operation="count")

    assert result["operation"] == "aggregate"
    assert result["data"]["count"] == 3
    assert result["coverage"]["complete"] is True


class FakeProvider:
    name = "fake"

    def can_handle(self, request) -> bool:
        return True

    def retrieve(self, request) -> RetrieveResult:
        return RetrieveResult(
            status="ok",
            evidence=(
                ProviderEvidence(
                    id="e1",
                    kind="log",
                    source="fake-source",
                    evidence_uri="evidence://fake/e1",
                ),
            ),
            coverage={"complete": True},
        )


def test_traverse_uses_only_host_registered_providers() -> None:
    register_provider(FakeProvider())

    result = server.tracecite_traverse(
        ["fake"],
        seed_evidence_ids=["seed-1"],
        limits={"max_retrievals": 2, "max_wall_seconds": 1.0},
    )

    assert result["graph"]["nodes"] == 1
    assert result["coverage"]["retrievals"] == 1

    with pytest.raises(ValueError, match="unknown host provider"):
        server.tracecite_traverse(["not-registered"], seed_evidence_ids=["seed-1"])


def test_provider_retrieve_uses_same_host_registry_and_session() -> None:
    register_provider(FakeProvider())

    result = server.tracecite_retrieve(
        "provider-session",
        {
            "kind": "provider",
            "provider_names": ["fake"],
            "request": {"evidence_ids": ["seed-1"]},
        },
    )

    assert result["evidence"]
    assert result["mcp_session"]["session_id"] == "provider-session"


def test_source_policy_blocks_paths_outside_host_allowlist(tmp_path: Path) -> None:
    outside = tmp_path.parent / "tracecite-mcp-outside.log"
    outside.write_text("secret\n", encoding="utf-8")
    try:
        with pytest.raises(PermissionError, match="TRACECITE_MCP_ALLOWED_ROOTS"):
            server.tracecite_aggregate(str(outside), "secret")
    finally:
        outside.unlink(missing_ok=True)


def test_source_glob_cannot_escape_selected_root(tmp_path: Path) -> None:
    folder = tmp_path / "logs"
    folder.mkdir()
    with pytest.raises(PermissionError, match="glob"):
        server.tracecite_retrieve(
            "session",
            {"kind": "source", "source": str(folder), "glob": "../*.log"},
        )


def test_retrieve_range_is_not_a_compatibility_backdoor(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\n", encoding="utf-8")

    with pytest.raises(ValueError, match="tracecite_materialize"):
        server.tracecite_retrieve(
            "investigation-a",
            {"kind": "range", "source": str(source), "start_line": 1},
        )


def test_retrieve_old_read_style_gets_actionable_materialize_error(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        server.tracecite_retrieve(
            "investigation-a",
            {"source": str(source), "start_line": 1, "line_count": 100},
        )

    message = str(exc.value)
    assert "tracecite_materialize" in message
    assert "start_line" in message
    assert "line_count" in message


def test_retrieve_missing_kind_explains_valid_kinds_and_range_tool(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        server.tracecite_retrieve(
            "investigation-a",
            {"source": str(source), "query": "alpha"},
        )

    message = str(exc.value)
    assert "target.kind" in message
    assert "'query', 'source', or 'provider'" in message
    assert "tracecite_materialize" in message


def test_verify_is_thin_core_passthrough(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        server,
        "verify",
        lambda path: {"operation": "verify", "status": "ok", "path": str(path)},
    )

    result = server.tracecite_verify(str(manifest))

    assert result["operation"] == "verify"
    assert result["status"] == "ok"
    assert result["path"] == str(manifest.resolve())
