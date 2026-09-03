from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from tracecite.runtime import CapabilitySpec, register_capability
from tracecite_mcp import capability_transport


def _spec(
    name: str = "mobile.devices.list",
    *,
    safety: str = "read",
    requires_authorization: bool = False,
) -> CapabilitySpec:
    return CapabilitySpec(
        name=name,
        kind="query" if safety != "live_action" else "action",
        description="List mobile devices available to the host.",
        input_schema={
            "type": "object",
            "properties": {"platform": {"type": "string"}},
            "additionalProperties": False,
        },
        safety=safety,
        requires_authorization=requires_authorization,
    )


def test_registered_core_capability_becomes_model_visible_mcp_tool() -> None:
    target = MCPServer("capability-test")
    spec = _spec()

    mapping = capability_transport.register_capability_tools(target, [spec])
    tools = {tool.name: tool for tool in asyncio.run(target.list_tools())}

    assert mapping == {"tracecite_mobile_devices_list": "mobile.devices.list"}
    assert "tracecite_mobile_devices_list" in tools
    description = tools["tracecite_mobile_devices_list"].description or ""
    assert "mobile.devices.list" in description
    assert "Safety=read" in description
    assert "Capability input schema" in description


def test_mcp_reads_and_executes_the_real_core_capability_registry() -> None:
    target = MCPServer("core-registry-test")
    spec = _spec("test.transport.echo")

    def echo(arguments):
        return {"echo": arguments.get("value")}

    register_capability(spec, echo, replace=True)

    mapping = capability_transport.register_capability_tools(target)
    tools = {tool.name for tool in asyncio.run(target.list_tools())}

    assert mapping["tracecite_test_transport_echo"] == "test.transport.echo"
    assert "tracecite_test_transport_echo" in tools
    assert capability_transport.execute_registered_capability(
        "test.transport.echo",
        {"value": "ok"},
    ) == {"echo": "ok"}


def test_extension_discovery_loads_core_registry_before_registering(
    monkeypatch,
) -> None:
    target = MCPServer("discovery-test")
    spec = _spec("mobile.processes.list")
    calls: list[bool] = []

    monkeypatch.setattr(
        capability_transport,
        "load_extensions",
        lambda *, strict: calls.append(strict),
    )
    monkeypatch.setattr(capability_transport, "list_capabilities", lambda: [spec])

    mapping = capability_transport.discover_and_register_capability_tools(target)

    assert calls == [False]
    assert mapping == {"tracecite_mobile_processes_list": "mobile.processes.list"}


def test_mobile_cut_is_discovered_without_mcp_specific_mapping(monkeypatch) -> None:
    target = MCPServer("mobile-cut-discovery")
    spec = _spec(
        "mobile.sessions.cut",
        safety="live_action",
        requires_authorization=True,
    )
    calls: list[bool] = []

    monkeypatch.setattr(
        capability_transport,
        "load_extensions",
        lambda *, strict: calls.append(strict),
    )
    monkeypatch.setattr(capability_transport, "list_capabilities", lambda: [spec])

    mapping = capability_transport.discover_and_register_capability_tools(target)
    tools = {tool.name: tool for tool in asyncio.run(target.list_tools())}

    assert calls == [False]
    assert mapping == {"tracecite_mobile_sessions_cut": "mobile.sessions.cut"}
    description = tools["tracecite_mobile_sessions_cut"].description or ""
    assert "mobile.sessions.cut" in description
    assert "Safety=live_action" in description
    assert "authorization" in description.lower()


def test_capability_execution_uses_host_grants_not_model_arguments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_execute(name, arguments, **policy):
        calls.append({"name": name, "arguments": arguments, **policy})
        return {"path": tmp_path / "capture.log"}

    monkeypatch.setattr(capability_transport, "execute_capability", fake_execute)
    monkeypatch.setenv("TRACECITE_MCP_ALLOW_LIVE_SOURCE", "true")
    monkeypatch.setenv("TRACECITE_MCP_ALLOW_LIVE_ACTION", "0")
    monkeypatch.setenv(
        "TRACECITE_MCP_AUTHORIZED_CAPABILITIES",
        "mobile.sessions.start,mobile.sessions.cut,mobile.sessions.stop",
    )

    result = capability_transport.execute_registered_capability(
        "mobile.sessions.cut",
        {"device_id": "device-1"},
    )

    assert calls == [
        {
            "name": "mobile.sessions.cut",
            "arguments": {"device_id": "device-1"},
            "allow_live_source": True,
            "allow_live_action": False,
            "authorized": True,
        }
    ]
    assert result == {"path": str(tmp_path / "capture.log")}


def test_registering_same_capability_twice_is_idempotent() -> None:
    target = MCPServer("idempotent-test")
    spec = _spec()

    capability_transport.register_capability_tools(target, [spec])
    capability_transport.register_capability_tools(target, [spec])

    tools = asyncio.run(target.list_tools())
    assert [tool.name for tool in tools] == ["tracecite_mobile_devices_list"]
