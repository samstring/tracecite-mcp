# TraceCite MCP

Thin Model Context Protocol adapter for TraceCite.

TraceCite MCP does not implement a second investigation runtime and does not hard-code Mobile, CI, OTel, or other domain packages. It projects TraceCite's public Agent-facing API and Capability Registry to MCP hosts.

## Architecture

```text
Agent Host / Claude / Codex / Cursor
                 ↓
           tracecite-mcp
                 ↓
        TraceCite public API
                 ↓
      Investigation Runtime
          /             \
 Evidence Core     Capability Registry
                       ↓
                   Extensions
                   ├─ mobile.*
                   ├─ ci.*
                   └─ third-party.*
```

The adapter follows the TraceCite rule: **constrain conclusions, not exploration**.

## MCP SDK

This branch targets the current stable v2 line of the official MCP Python SDK:

```python
from mcp.server import MCPServer
```

Python 3.10+ is supported.

## Tools

The first MCP surface intentionally stays small:

- `tracecite_probe`
- `tracecite_sample`
- `tracecite_survey`
- `tracecite_search`
- `tracecite_expand`
- `tracecite_verify`
- `tracecite_investigation_create`
- `tracecite_validate_finding`
- `tracecite_list_extensions`
- `tracecite_list_capabilities`
- `tracecite_execute_capability`

Domain abilities are not added as hard-coded MCP functions. Installed extensions register `CapabilitySpec` objects with TraceCite and the adapter exposes them through `list_capabilities` / `execute_capability`.

## Safety

Live execution is denied by default.

The model cannot pass `allow_live_source`, `allow_live_action`, or `authorized` as MCP tool arguments. These are server-owner policy controls:

```bash
export TRACECITE_MCP_ALLOW_LIVE_SOURCE=1
export TRACECITE_MCP_ALLOW_LIVE_ACTION=1
export TRACECITE_MCP_AUTHORIZED_CAPABILITIES='mobile.ios.collect_logs,mobile.android.collect_logs'
```

Use `*` in `TRACECITE_MCP_AUTHORIZED_CAPABILITIES` only when the host deliberately grants authorization to every capability that declares `requires_authorization=true`.

Starting `tracecite-mcp` is the explicit extension-loading boundary. Installed `tracecite.extensions` entry points are loaded once when the MCP server starts.

## Development

The `feature_for_agent` branch currently develops against the matching TraceCite Core feature branch because the Capability Registry has not yet been released as a newer PyPI version.

```bash
python -m pip install 'git+https://github.com/samstring/tracecite-core.git@feature_for_agent'
python -m pip install -e '.[dev]'
python -m pytest -q
tracecite-mcp
```

The default transport is stdio.

## Implementation plan

### Phase 1 — foundation

- [x] package scaffold
- [x] MCP Python SDK v2 server
- [x] deterministic TraceCite evidence tools
- [x] Investigation creation and Finding validation
- [x] Capability Registry projection
- [x] server-owned live/authorization gates
- [x] Python 3.10–3.14 + macOS CI

### Phase 2 — extension integration

- [ ] register useful `mobile.*` capabilities in `tracecite-mobile`
- [ ] integration test MCP + Mobile capability discovery
- [ ] test live-source denial and explicit host grant end-to-end

### Phase 3 — production hardening

- [ ] privacy/redaction policy before freezing sensitive live evidence
- [ ] bounded MCP transport/result projection for large AgentResult payloads
- [ ] MCP Inspector / real-host acceptance tests
- [ ] publish versioned compatibility matrix for TraceCite Core and MCP SDK
