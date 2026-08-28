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
        "tracecite_retrieve",
        "tracecite_probe",
        "tracecite_sample",
        "tracecite_survey",
        "tracecite_search",
        "tracecite_expand",
        "tracecite_verify",
        "tracecite_investigation_create",
        "tracecite_validate_finding",
        "tracecite_list_extensions",
        "tracecite_list_capabilities",
        "tracecite_execute_capability",
    } <= names


def test_canonical_retrieve_projects_adaptive_core_contract(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")

    result = server.tracecite_retrieve(
        {
            "kind": "query",
            "source": str(source),
            "query": "target",
            "segmenter": "rawtext",
        }
    )

    assert result["status"] == "ok"
    assert result["evidence"]
    assert result["evidence"][0]["uri"].startswith("evidence://sha256/")
    assert result["data"]["routing"]["route"] in {"direct", "bounded", "investigate"}
    assert "progress" in result["data"]


def test_probe_and_search_remain_compatibility_wrappers(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("alpha\ntarget event\nomega\n", encoding="utf-8")

    probed = server.tracecite_probe(str(source), segmenter="rawtext")
    searched = server.tracecite_search(str(source), "target", segmenter="rawtext")

    assert probed["operation"] == "probe"
    assert probed["status"] == "ok"
    assert searched["operation"] == "search"
    assert searched["status"] == "ok"
    assert searched["evidence"]


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
    installed = {item["id"]: item for item in extension_state["installed_extensions"]}
    assert installed["mobile"]["protocol_version"] == "2"

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
