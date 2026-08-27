from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest

from tracecite import CapabilityError, CapabilitySpec, register_capability
from tracecite_mcp import server


def test_mcp_exposes_expected_thin_tool_surface() -> None:
    tools = asyncio.run(server.mcp.list_tools())
    names = {tool.name for tool in tools}
    assert {
        "tracecite_probe",
        "tracecite_sample",
        "tracecite_survey",
        "tracecite_search",
        "tracecite_expand",
        "tracecite_expand_many",
        "tracecite_verify",
        "tracecite_investigation_create",
        "tracecite_validate_finding",
        "tracecite_list_extensions",
        "tracecite_list_capabilities",
        "tracecite_execute_capability",
    } <= names


def test_probe_and_search_use_real_tracecite_core(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")

    probed = server.tracecite_probe(str(source), segmenter="rawtext")
    searched = server.tracecite_search(str(source), "target", segmenter="rawtext")

    assert probed["status"] == "ok"
    assert searched["status"] == "ok"
    assert searched["evidence"]
    assert searched["evidence"][0]["uri"].startswith("evidence://sha256/")


def test_stateful_search_returns_delta_and_expand_many_recovers_context(
    tmp_path: Path, monkeypatch
) -> None:
    state_dir = tmp_path / "mcp-state"
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")
    monkeypatch.setenv("TRACECITE_MCP_STATE_DIR", str(state_dir))

    first = server.tracecite_search(
        str(source),
        "target",
        segmenter="rawtext",
        context_id="case-1",
    )
    assert first["status"] == "ok"
    assert len(first["evidence"]) == 1
    assert first["data"]["context"]["new_evidence"] == 1
    assert first["data"]["context"]["repeated_evidence"] == 0
    assert first["data"]["recovery_tool"] == "tracecite_expand_many"
    result_id = first["data"]["result_id"]
    ref = first["evidence"][0]["uri"].split("#", 1)[1]

    second = server.tracecite_search(
        str(source),
        "target",
        segmenter="rawtext",
        context_id="case-1",
    )
    assert second["status"] == "ok"
    assert second["outcome"] == "supported"
    assert second["evidence"] == []
    assert second["data"]["result_id"] == result_id
    assert second["data"]["context"]["result_repeated"] is True
    assert second["data"]["context"]["repeated_evidence"] == 1

    expanded = server.tracecite_expand_many(result_id, [f"#{ref}"], before=0, after=0)
    assert expanded["status"] == "ok"
    assert expanded["coverage"]["returned"] == 1
    assert "target event" in expanded["contexts"][0]["text"]


def test_different_contexts_do_not_share_seen_state(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "app.log"
    source.write_text("target event\n", encoding="utf-8")
    monkeypatch.setenv("TRACECITE_MCP_STATE_DIR", str(tmp_path / "state"))

    first = server.tracecite_search(str(source), "target", context_id="a")
    second = server.tracecite_search(str(source), "target", context_id="b")

    assert len(first["evidence"]) == 1
    assert len(second["evidence"]) == 1


def test_investigation_create_persists_state(tmp_path: Path) -> None:
    path = tmp_path / "investigation.json"
    state = server.tracecite_investigation_create(
        str(path),
        "Why did the screen go blank?",
        scope={"platform": "ios"},
    )
    assert path.is_file()
    assert state["problem"]["question"] == "Why did the screen go blank?"
    assert state["scope"] == {"platform": "ios"}


def test_installed_mobile_extension_is_discovered_without_mcp_importing_mobile(monkeypatch) -> None:
    monkeypatch.setattr(server, "_EXTENSIONS_LOADED", False)
    monkeypatch.setattr(server, "_EXTENSION_LOAD_RESULT", [])
    monkeypatch.delenv("TRACECITE_MCP_ALLOW_LIVE_SOURCE", raising=False)
    monkeypatch.delenv("TRACECITE_MCP_ALLOW_LIVE_ACTION", raising=False)
    monkeypatch.delenv("TRACECITE_MCP_AUTHORIZED_CAPABILITIES", raising=False)

    extension_state = server.tracecite_list_extensions()
    installed = {item["id"]: item for item in extension_state["extensions"]}
    assert installed["mobile"]["protocol_version"] == "2"
    assert "runtimes" not in extension_state

    capabilities = {item["name"]: item for item in server.tracecite_list_capabilities()}
    assert capabilities["mobile.environment.probe"]["safety"] == "read"
    assert capabilities["mobile.devices.list"]["safety"] == "live_source"
    assert capabilities["mobile.processes.list"]["safety"] == "live_source"
    assert capabilities["mobile.sessions.list"]["safety"] == "live_source"

    for name in ("mobile.sessions.start", "mobile.sessions.stop", "mobile.app.launch"):
        assert capabilities[name]["safety"] == "live_action"
        assert capabilities[name]["requires_authorization"] is True

    with pytest.raises(CapabilityError, match="allow_live_source"):
        server.tracecite_execute_capability("mobile.devices.list", {"platform": "ios"})

    # This must fail at the Runtime gate before any device resolution or backend
    # side effect can occur in CI.
    with pytest.raises(CapabilityError, match="allow_live_action"):
        server.tracecite_execute_capability(
            "mobile.sessions.start",
            {"platform": "ios", "device": "not-a-real-device"},
        )

    monkeypatch.setenv("TRACECITE_MCP_ALLOW_LIVE_ACTION", "1")
    with pytest.raises(CapabilityError, match="authorization"):
        server.tracecite_execute_capability(
            "mobile.sessions.start",
            {"platform": "ios", "device": "not-a-real-device"},
        )


def test_live_grants_are_server_policy_not_model_arguments(monkeypatch) -> None:
    name = "test.live.collect"
    register_capability(
        CapabilitySpec(
            name=name,
            kind="action",
            description="Synthetic live source",
            safety="live_source",
            requires_authorization=True,
        ),
        lambda args: {"ok": True, "args": args},
        replace=True,
    )
    monkeypatch.setattr(server, "_EXTENSIONS_LOADED", True)
    monkeypatch.setattr(server, "_EXTENSION_LOAD_RESULT", [])
    monkeypatch.delenv("TRACECITE_MCP_ALLOW_LIVE_SOURCE", raising=False)
    monkeypatch.delenv("TRACECITE_MCP_AUTHORIZED_CAPABILITIES", raising=False)

    signature = inspect.signature(server.tracecite_execute_capability)
    assert "allow_live_source" not in signature.parameters
    assert "allow_live_action" not in signature.parameters
    assert "authorized" not in signature.parameters

    with pytest.raises(CapabilityError, match="allow_live_source"):
        server.tracecite_execute_capability(name, {"device": "A"})

    monkeypatch.setenv("TRACECITE_MCP_ALLOW_LIVE_SOURCE", "1")
    with pytest.raises(CapabilityError, match="authorization"):
        server.tracecite_execute_capability(name, {"device": "A"})

    monkeypatch.setenv("TRACECITE_MCP_AUTHORIZED_CAPABILITIES", name)
    result = server.tracecite_execute_capability(name, {"device": "A"})
    assert result == {"ok": True, "args": {"device": "A"}}
