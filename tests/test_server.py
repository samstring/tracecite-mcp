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
