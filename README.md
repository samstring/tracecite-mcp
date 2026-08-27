# TraceCite MCP

Thin Model Context Protocol adapter for TraceCite.

TraceCite MCP does not implement a second investigation runtime and does not hard-code Mobile, CI, OTel, or other domain packages. It projects TraceCite's public Agent-facing API, Extension Protocol v2, and Capability Registry to MCP hosts.

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
       ↑                 ↑
 Ledger + Context     Extensions v2
 Engine              mobile / ci / ...
```

The adapter follows the TraceCite rule: **constrain conclusions, not exploration**. Canonical evidence stays recoverable; MCP may return a bounded Agent-facing delta without changing the canonical Runtime Result.

## MCP SDK

This branch targets the stable v2 line of the official MCP Python SDK:

```python
from mcp.server import MCPServer
```

Python 3.10+ is supported.

## Tools

The MCP surface intentionally stays generic:

- `tracecite_probe`
- `tracecite_sample`
- `tracecite_survey`
- `tracecite_search`
- `tracecite_expand`
- `tracecite_expand_many`
- `tracecite_verify`
- `tracecite_investigation_create`
- `tracecite_validate_finding`
- `tracecite_list_extensions`
- `tracecite_list_capabilities`
- `tracecite_execute_capability`

Domain abilities are not added as hard-coded MCP functions. Installed Extension Protocol v2 packages publish declarative capabilities; MCP discovers them through TraceCite and exposes the generic `list_capabilities` / `execute_capability` pair.

`tracecite_list_extensions` reports declarative Extension v2 state and load results. It intentionally does not expose internal `ScenarioRuntime` objects or a domain-runtime registry as an MCP contract.

## Stateful Agent context

`tracecite_search` keeps its previous canonical behavior when `context_id` is omitted.

When a host supplies a stable `context_id`, the server:

1. executes the canonical TraceCite search;
2. stores that complete Result in a private content-addressed Evidence Ledger;
3. records which Evidence URIs that Agent context has already seen;
4. returns only newly seen Evidence plus explicit delta metadata;
5. returns a `result_id` that can be used with `tracecite_expand_many` to recover immutable context.

This reduces repeated tool payload without changing Evidence, Coverage, or the canonical Result on disk. Different context IDs do not share seen-state.

The storage location is server-owned, not model-selected:

```bash
export TRACECITE_MCP_STATE_DIR="$HOME/.tracecite/mcp"
```

If unset, the same path is used by default. Context state is bounded; it is transport memory, not trusted investigation evidence.

## Safety

Live execution is denied by default.

The model cannot pass `allow_live_source`, `allow_live_action`, or `authorized` as MCP tool arguments. These are server-owner policy controls:

```bash
export TRACECITE_MCP_ALLOW_LIVE_SOURCE=1
export TRACECITE_MCP_ALLOW_LIVE_ACTION=1
export TRACECITE_MCP_AUTHORIZED_CAPABILITIES='mobile.sessions.start,mobile.sessions.stop'
```

Use `*` in `TRACECITE_MCP_AUTHORIZED_CAPABILITIES` only when the host deliberately grants authorization to every capability that declares `requires_authorization=true`.

Starting `tracecite-mcp` is the explicit extension-loading boundary. Installed `tracecite.extensions` entry points are loaded once when the MCP server starts. Extension loading never grants live-source or live-action permission by itself.

## Development

The `refactor/agent-v2` branch validates against the matching Core and Mobile refactor branches:

```bash
python -m pip install 'git+https://github.com/samstring/tracecite-core.git@refactor/agent-v2'
python -m pip install 'git+https://github.com/samstring/tracecite-mobile.git@refactor/agent-v2'
python -m pip install -e '.[dev]'
python -m pytest -q
tracecite-mcp
```

The default transport is stdio.

## Implementation status

### Foundation

- [x] MCP Python SDK v2 server
- [x] deterministic TraceCite evidence tools
- [x] Investigation creation and Finding validation
- [x] Capability Registry projection
- [x] server-owned live/authorization gates
- [x] Python 3.10–3.14 + macOS CI

### Extension Protocol v2 integration

- [x] discover declarative Mobile Extension v2 without importing Mobile internals
- [x] expose Mobile `agent.capability` declarations through the generic registry
- [x] test live-source denial and explicit host authorization end-to-end
- [x] stop exposing internal domain runtimes as MCP API

### Context transport

- [x] optional per-context search delta
- [x] private canonical Evidence Ledger
- [x] `tracecite_expand_many` recovery path
- [x] independent seen-state per Agent context
- [ ] host-specific benchmark of repeated-turn token savings

### Production hardening

- [ ] privacy/redaction policy before freezing sensitive live evidence
- [ ] MCP Inspector / real-host acceptance tests
- [ ] publish versioned compatibility matrix for TraceCite Core, Mobile, and MCP SDK

## License

MIT
