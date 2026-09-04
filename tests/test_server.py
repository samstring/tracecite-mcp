from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from tracecite.extension.retrieval import ProviderEvidence, RetrieveResult
from tracecite_mcp import clear_providers, register_provider
from tracecite_mcp import server


EXPECTED_TOOLS = {
    "tracecite_run",
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
    monkeypatch.setenv("TRACECITE_EVIDENCE_MAX_TOKENS", "12000")
    monkeypatch.setenv("TRACECITE_EVIDENCE_MAX_BYTES", str(64 * 1024))
    clear_providers()
    yield
    clear_providers()


def _tools():
    return {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}


def test_mcp_exposes_evidence_shell_and_canonical_helpers() -> None:
    assert set(_tools()) == EXPECTED_TOOLS


def test_agent_tool_schemas_do_not_expose_host_budget_or_snapshot_controls() -> None:
    tools = _tools()
    run_schema = tools["tracecite_run"].input_schema
    run_text = str(run_schema)
    for forbidden in (
        "max_evidence",
        "max_evidence_tokens",
        "max_evidence_bytes",
        "max_line_chars",
        "snapshot",
        "source_mode",
        "max_chars",
    ):
        assert forbidden not in run_text

    materialize_text = str(tools["tracecite_materialize"].input_schema)
    assert "max_chars" not in materialize_text
    replay_text = str(tools["tracecite_replay"].input_schema)
    assert "max_chars" not in replay_text


def test_tool_descriptions_teach_refine_not_budget_bypass() -> None:
    tools = _tools()
    run = tools["tracecite_run"].description or ""
    assert "too_broad" in run
    assert "user/Host" in run
    assert "never ask" in run

    retrieve_desc = tools["tracecite_retrieve"].description or ""
    assert "prefer tracecite_run" in retrieve_desc
    assert "snapshot" in retrieve_desc

    materialize = tools["tracecite_materialize"].description or ""
    assert "cannot pass max_chars" in materialize


def test_run_uses_persistent_core_retrieval_session(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")

    first = server.tracecite_run("investigation-a", str(source), "search target")
    repeated = server.tracecite_run("investigation-a", str(source), "search target")
    independent = server.tracecite_run("investigation-b", str(source), "search target")

    assert first["status"] == "ok"
    assert first["evidence"]
    assert first["mcp_session"]["session_id"] == "investigation-a"
    assert repeated["coverage"]["new_evidence"] == 0
    assert repeated["coverage"]["repeated_evidence"] >= 1
    assert repeated["mcp_session"]["revision"] > first["mcp_session"]["revision"]
    assert independent["evidence"]


def test_same_session_keeps_fixed_source_version_when_original_changes(tmp_path: Path) -> None:
    source = tmp_path / "live-ish.log"
    source.write_text("ERROR old\n", encoding="utf-8")

    first = server.tracecite_run("conversation", str(source), "search ERROR")
    version = first["data"]["source_version"]
    source.write_text("ERROR new\n", encoding="utf-8")

    same_session = server.tracecite_run("conversation", str(source), "search new")
    new_session = server.tracecite_run("conversation-2", str(source), "search new")

    assert same_session["data"]["source_version"] == version
    assert same_session["status"] == "no_match"
    assert new_session["status"] == "ok"
    assert new_session["data"]["source_version"] != version


def test_shell_transport_does_not_first_n_truncate_after_core_budget_admission(tmp_path: Path) -> None:
    source = tmp_path / "many.log"
    source.write_text("".join(f"ERROR n={i}\n" for i in range(12)), encoding="utf-8")

    result = server.tracecite_run("session", str(source), "search ERROR")

    assert result["status"] == "ok"
    assert result["coverage"]["match_records"] == 12
    assert len(result["evidence"]) == 12
    assert "evidence_omitted_from_transport" not in result


def test_too_broad_is_host_policy_and_returns_no_partial_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "large.log"
    source.write_text("".join(f"ERROR {'x' * 80} n={i}\n" for i in range(50)), encoding="utf-8")
    monkeypatch.setenv("TRACECITE_EVIDENCE_MAX_TOKENS", "30")
    monkeypatch.setenv("TRACECITE_EVIDENCE_MAX_BYTES", "256")

    result = server.tracecite_run("session", str(source), "search ERROR")

    assert result["status"] == "too_broad"
    assert result["evidence"] == []
    assert result["coverage"]["too_broad"] is True
    assert result["data"]["refine_query"] is True
    assert result["data"]["reason"] == "MATCHED_EVIDENCE_BUDGET_EXCEEDED"


def test_compat_query_rejects_agent_policy_fields(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("ERROR one\n", encoding="utf-8")
    for field, value in (
        ("snapshot", True),
        ("max_evidence", 8),
        ("max_line_chars", 640),
        ("fold", False),
    ):
        with pytest.raises(ValueError, match="user/Host"):
            server.tracecite_retrieve(
                "session",
                {"kind": "query", "source": str(source), "query": "ERROR", field: value},
            )


def test_compat_query_is_translated_to_shell(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")
    target = {
        "kind": "query",
        "source": str(source),
        "query": "target",
        "segmenter": "rawtext",
    }

    result = server.tracecite_retrieve("investigation-a", target)

    assert result["operation"] == "evidence_shell"
    assert result["status"] == "ok"
    assert result["evidence"]


def test_materialize_selected_shell_pointer(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")
    found = server.tracecite_run("investigation-a", str(source), "search target")
    pointer = found["evidence"][0]

    materialized = server.tracecite_materialize(
        "investigation-a",
        pointer["materialize_source"],
        pointer["start_line"],
        end_line=pointer["end_line"],
        before=0,
        after=0,
        expected_sha256=pointer["sha256"],
    )

    assert materialized["status"] == "ok"
    assert "target event" in (materialized.get("data") or {}).get("text", "")


def test_materialize_then_replay_preserves_novelty_boundary(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    materialized = server.tracecite_materialize(
        "investigation-a", str(source), 2, before=0, after=0, expected_sha256=digest
    )
    replayed = server.tracecite_replay(
        "investigation-a", str(source), 2, digest, before=0, after=0
    )

    assert materialized["evidence"]
    assert replayed["operation"] == "replay"
    assert replayed["coverage"]["new_evidence"] == 0
    assert replayed["data"]["novelty"]["state"] == "replay"


def test_replay_requires_prior_coverage(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="has not been materialized"):
        server.tracecite_replay("fresh-session", str(source), 2, digest, before=0, after=0)


def test_aggregate_compatibility_is_session_bound_count(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("error A\nok\nerror B\nerror A\n", encoding="utf-8")

    result = server.tracecite_aggregate("session", str(source), "error", operation="count")

    assert result["operation"] == "evidence_shell"
    assert result["data"]["aggregate"]["count"] == 3
    assert result["coverage"]["complete"] is True

    with pytest.raises(ValueError, match="tracecite_run"):
        server.tracecite_aggregate("session", str(source), "error", operation="group")


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
        ["fake"], seed_evidence_ids=["seed-1"], limits={"max_retrievals": 2, "max_wall_seconds": 1.0}
    )
    assert result["graph"]["nodes"] == 1
    with pytest.raises(ValueError, match="unknown host provider"):
        server.tracecite_traverse(["not-registered"], seed_evidence_ids=["seed-1"])


def test_provider_retrieve_uses_same_host_registry_and_session() -> None:
    register_provider(FakeProvider())
    result = server.tracecite_retrieve(
        "provider-session",
        {"kind": "provider", "provider_names": ["fake"], "request": {"evidence_ids": ["seed-1"]}},
    )
    assert result["evidence"]
    assert result["mcp_session"]["session_id"] == "provider-session"


def test_source_policy_blocks_paths_outside_host_allowlist(tmp_path: Path) -> None:
    outside = tmp_path.parent / "tracecite-mcp-outside.log"
    outside.write_text("secret\n", encoding="utf-8")
    try:
        with pytest.raises(PermissionError, match="TRACECITE_MCP_ALLOWED_ROOTS"):
            server.tracecite_run("session", str(outside), "search secret")
    finally:
        outside.unlink(missing_ok=True)


def test_source_glob_cannot_escape_selected_root(tmp_path: Path) -> None:
    folder = tmp_path / "logs"
    folder.mkdir()
    with pytest.raises(PermissionError, match="glob"):
        server.tracecite_retrieve(
            "session", {"kind": "source", "source": str(folder), "glob": "../*.log"}
        )


def test_retrieve_range_is_not_a_compatibility_backdoor(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\n", encoding="utf-8")
    with pytest.raises(ValueError, match="tracecite_materialize"):
        server.tracecite_retrieve(
            "investigation-a", {"kind": "range", "source": str(source), "start_line": 1}
        )


def test_retrieve_missing_kind_explains_valid_kinds(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\n", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        server.tracecite_retrieve("investigation-a", {"source": str(source), "query": "alpha"})
    assert "target.kind" in str(exc.value)


def test_verify_is_thin_core_passthrough(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        server, "verify", lambda path: {"operation": "verify", "status": "ok", "path": str(path)}
    )
    result = server.tracecite_verify(str(manifest))
    assert result["operation"] == "verify"
    assert result["status"] == "ok"
    assert result["path"] == str(manifest.resolve())
