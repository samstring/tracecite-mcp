"""Project Core-registered AgentCapabilities into MCP tools.

TraceCite Core owns extension discovery, capability metadata, and execution
safety checks.  MCP only turns the currently registered capabilities into
model-visible tools and supplies explicit host-controlled safety grants.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from mcp.server import MCPServer

from tracecite.extension import load_extensions
from tracecite.runtime import CapabilitySpec, execute_capability, list_capabilities


_TOOL_NAME_LIMIT = 64
_SCHEMA_DESCRIPTION_LIMIT = 3_000
_REGISTERED_TOOLS: dict[int, dict[str, str]] = {}


def _env_enabled(name: str) -> bool:
    value = str(os.environ.get(name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _authorized_capabilities() -> set[str]:
    configured = str(os.environ.get("TRACECITE_MCP_AUTHORIZED_CAPABILITIES") or "")
    return {
        item.strip().lower()
        for item in configured.split(",")
        if item.strip()
    }


def _capability_authorized(name: str) -> bool:
    authorized = _authorized_capabilities()
    return "*" in authorized or name.strip().lower() in authorized


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def capability_tool_name(capability_name: str) -> str:
    """Return a deterministic MCP-safe name for one dotted capability name."""

    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", capability_name.strip().lower()).strip("_")
    base = f"tracecite_{normalized}"
    if len(base) <= _TOOL_NAME_LIMIT:
        return base
    digest = hashlib.sha256(capability_name.encode("utf-8")).hexdigest()[:8]
    keep = _TOOL_NAME_LIMIT - len(digest) - 1
    return f"{base[:keep]}_{digest}"


def _capability_description(spec: CapabilitySpec) -> str:
    schema = json.dumps(dict(spec.input_schema), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(schema) > _SCHEMA_DESCRIPTION_LIMIT:
        schema = schema[: _SCHEMA_DESCRIPTION_LIMIT - 3] + "..."
    authorization = "required" if spec.requires_authorization else "not-required"
    return (
        f"{spec.description}\n\n"
        f"TraceCite extension capability: {spec.name}. "
        f"Safety={spec.safety}; authorization={authorization}. "
        "Pass capability arguments inside the `arguments` object. "
        f"Capability input schema: {schema}"
    )


def execute_registered_capability(
    name: str,
    arguments: Mapping[str, Any] | None = None,
) -> Any:
    """Execute through Core with grants controlled only by the MCP host."""

    payload = {} if arguments is None else dict(arguments)
    return _jsonable(
        execute_capability(
            name,
            payload,
            allow_live_source=_env_enabled("TRACECITE_MCP_ALLOW_LIVE_SOURCE"),
            allow_live_action=_env_enabled("TRACECITE_MCP_ALLOW_LIVE_ACTION"),
            authorized=_capability_authorized(name),
        )
    )


def _handler(spec: CapabilitySpec, tool_name: str):
    def invoke(arguments: dict[str, Any] | None = None) -> Any:
        return execute_registered_capability(spec.name, arguments)

    invoke.__name__ = tool_name
    invoke.__doc__ = _capability_description(spec)
    return invoke


def register_capability_tools(
    server: MCPServer,
    specs: Iterable[CapabilitySpec] | None = None,
) -> dict[str, str]:
    """Register Core capabilities as MCP tools and return tool->capability map."""

    selected = list(list_capabilities() if specs is None else specs)
    registered = _REGISTERED_TOOLS.setdefault(id(server), {})
    planned: dict[str, str] = {}

    for spec in selected:
        if not isinstance(spec, CapabilitySpec):
            raise TypeError("capability registry returned a non-CapabilitySpec value")
        tool_name = capability_tool_name(spec.name)
        other = planned.get(tool_name) or registered.get(tool_name)
        if other is not None and other != spec.name:
            # A sanitized-name collision should never silently replace another
            # extension capability. Add a stable digest and fail only if that
            # extremely unlikely name also collides.
            digest = hashlib.sha256(spec.name.encode("utf-8")).hexdigest()[:8]
            prefix = tool_name[: _TOOL_NAME_LIMIT - len(digest) - 1]
            tool_name = f"{prefix}_{digest}"
            other = planned.get(tool_name) or registered.get(tool_name)
            if other is not None and other != spec.name:
                raise ValueError(
                    f"MCP capability tool name collision: {spec.name!r} and {other!r}"
                )
        planned[tool_name] = spec.name

    for spec in selected:
        tool_name = next(name for name, capability in planned.items() if capability == spec.name)
        if registered.get(tool_name) == spec.name:
            continue
        server.add_tool(
            _handler(spec, tool_name),
            name=tool_name,
            description=_capability_description(spec),
        )
        registered[tool_name] = spec.name

    return dict(registered)


def discover_and_register_capability_tools(
    server: MCPServer,
    *,
    strict: bool = False,
) -> dict[str, str]:
    """Load installed TraceCite extensions and expose their AgentCapabilities."""

    load_extensions(strict=strict)
    return register_capability_tools(server)


__all__ = [
    "capability_tool_name",
    "discover_and_register_capability_tools",
    "execute_registered_capability",
    "register_capability_tools",
]
