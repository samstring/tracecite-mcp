# TraceCite MCP

Thin Model Context Protocol adapter for TraceCite's canonical Evidence Runtime.

`tracecite-mcp` intentionally remains a separate project from `tracecite-core`. Core owns evidence mechanics and the Agent capability registry; this repository owns MCP transport, Host policy, session mapping, serialization, process-local provider resolution, and projection of installed Agent capabilities into MCP tools.

## Architecture

```text
Agent / Claude / Codex / Cursor / other MCP host
                    │
                    │ MCP
                    ▼
┌────────────────────────────────────────────┐
│               tracecite-mcp                │
│                                            │
│ retrieve   materialize   replay            │
│ aggregate  traverse      verify            │
│                                            │
│ installed AgentCapability → MCP tools      │
│ session mapping        Host provider registry│
│ local source policy    stdio transport     │
└──────────────────────┬─────────────────────┘
                       │ public TraceCite API
                       ▼
┌────────────────────────────────────────────┐
│              tracecite-core                │
│                                            │
│ provenance / source identity / coverage    │
│ novelty / repeated evidence / replay       │
│ bounded retrieval / deterministic traversal│
│ Extension Protocol / Capability Registry   │
└────────────────────────────────────────────┘
```

The boundary is:

> **Agent owns thinking and decisions. TraceCite owns evidence and capability mechanics.**

The MCP server does not choose hypotheses, investigation order, causal explanations, evidence sufficiency, root cause, or when an Agent should stop.

## Canonical Evidence MCP tool surface

TraceCite MCP always provides these six canonical Evidence tools:

| MCP tool | Core primitive | Responsibility |
|---|---|---|
| `tracecite_retrieve` | `retrieve` | caller-selected source/query/provider evidence acquisition |
| `tracecite_materialize` | `materialize` | exact caller-selected source range |
| `tracecite_replay` | `replay` | deliberate reread of already-covered immutable evidence |
| `tracecite_aggregate` | `aggregate` | deterministic `count` / `distinct` / `group` |
| `tracecite_traverse` | `traverse` | bounded deterministic traversal from caller-selected seeds |
| `tracecite_verify` | `verify` | mechanical manifest/integrity verification |

The generic MCP contract does not create a second Evidence semantic surface for `probe`, `sample`, `survey`, `search`, `expand`, Investigation/Finding APIs, Pi checkpoint logic, or benchmark guards.

## Installed extension capabilities

At server startup, MCP asks Core to discover installed `tracecite.extensions` entry points. Core registers each extension's `AgentCapability`; MCP then projects the currently registered capabilities into additional model-visible MCP tools.

MCP does not import Mobile or any other domain extension directly. The flow is:

```text
tracecite-mobile / another installed extension
        ↓ tracecite.extensions entry point
TraceCite Core Extension Protocol
        ↓ AgentCapability registry
tracecite-mcp
        ↓ dynamic MCP tool
Agent
```

A capability name is mapped deterministically to an MCP-safe tool name. For example:

```text
mobile.environment.probe  → tracecite_mobile_environment_probe
mobile.devices.list       → tracecite_mobile_devices_list
mobile.sessions.start     → tracecite_mobile_sessions_start
mobile.sessions.cut       → tracecite_mobile_sessions_cut
mobile.sessions.stop      → tracecite_mobile_sessions_stop
```

There is no Mobile-specific tool map in MCP. If an installed extension registers a new `AgentCapability`, MCP discovers it through Core's registry and projects it with the same generic mechanism.

Each dynamic tool description contains the canonical Core capability name, its safety level, authorization requirement, and its declared input schema. Capability arguments are passed inside the tool's `arguments` object.

Execution still goes through Core's `execute_capability()`. The model cannot grant itself live access or authorization. Those grants are Host-owned environment policy:

```bash
# Permit capabilities whose Core safety level is live_source.
export TRACECITE_MCP_ALLOW_LIVE_SOURCE=1

# Permit capabilities whose Core safety level is live_action.
export TRACECITE_MCP_ALLOW_LIVE_ACTION=1

# Explicit authorization gate for capabilities that require authorization.
# Comma-separated canonical Core capability names; `*` explicitly authorizes all.
export TRACECITE_MCP_AUTHORIZED_CAPABILITIES="mobile.sessions.start,mobile.sessions.cut,mobile.sessions.stop"
```

A capability can therefore be installed and visible while execution is still denied by Core until the Host supplies the required grant. This keeps discovery separate from authorization.

For TraceCite Mobile, `mobile.sessions.cut` is the normal way to obtain a stable sealed log segment while collection continues. The returned stable artifact should then be investigated through the canonical Evidence tools rather than by adding a Mobile-specific evidence API to MCP.

## RetrievalSession mapping

`retrieve`, `materialize`, and `replay` require a `session_id`.

Reuse the same ID for one investigation. MCP maps it directly to Core's `RetrievalSessionStore`; MCP does not keep a parallel novelty/coverage database.

By default session state is stored under:

```text
~/.tracecite/mcp/_retrieval_sessions/
```

The server owner can override the state root:

```bash
export TRACECITE_MCP_STATE_DIR=/path/to/state
```

Results from session-aware tools include an `mcp_session` projection containing only mechanical metadata: session ID, revision, and Core's retrieval summary. It is not a stop recommendation or evidence-sufficiency judgment.

## Local source access policy and recovery

Filesystem access is Host-owned policy, not a model-controlled option.

By default local Evidence operations can access only the MCP process working directory. A Host can explicitly widen the allowed roots:

```bash
export TRACECITE_MCP_ALLOWED_ROOTS="/project/logs:/another/evidence/root"
```

Use the platform path separator (`:` on macOS/Linux, `;` on Windows). Symlinks are resolved before the allowlist check, and source globs may not escape with `..`.

Allowed roots are only a permission boundary. They are **not** treated as the current task's source inventory and MCP never scans them to guess which files the Agent should use.

A Host can separately declare the bounded evidence files for the current task:

```bash
export TRACECITE_EVIDENCE_FILES="/project/logs/containerd.log:/project/logs/kubelet.log"
```

`TRACECITE_EVIDENCE_FILES` also uses the platform path separator. MCP de-duplicates the list, keeps Host order, returns at most 50 entries, ignores missing/non-file entries, and never returns an entry outside `TRACECITE_MCP_ALLOWED_ROOTS`.

If an Agent supplies a missing path that is otherwise inside the allowlist, MCP returns structured recovery metadata instead of forcing the Agent to guess filenames, for example:

```json
{
  "operation": "retrieve",
  "status": "error",
  "error_code": "source_not_found",
  "source": "/project/logs/containerd-6772.log",
  "available_sources": [
    "/project/logs/containerd.log",
    "/project/logs/kubelet.log"
  ]
}
```

The Agent should retry with a relevant declared source. Paths outside the allowlist remain hard permission errors and do not receive inventory-based recovery.

## Host-registered EvidenceProviders

Core `EvidenceProvider` objects are process-local Python objects. The model must not send executable providers or serialized provider snapshots through MCP.

The Host registers providers before serving:

```python
from tracecite_mcp import register_provider

register_provider(my_provider)
```

The Agent can then select already-registered provider names through:

- `tracecite_retrieve` with `target.kind="provider"`, `provider_names`, and an explicit bounded provider request; or
- `tracecite_traverse` with `provider_names` plus explicit seed IDs/entities and hard limits.

Provider registration is a Host boundary. MCP does not rank providers, select a preferred provider, or choose an investigation direction.

## Generic Agent skill

`skills/tracecite/SKILL.md` is Agent-neutral. It explains the canonical Evidence semantics, missing-source recovery, dynamic extension capability boundary, and evidence responsibilities without encoding Pi/Codex/Claude-specific diagnosis strategy.

The same semantic content can be packaged into another Agent's skill system. Agent-specific wrappers should stay thin.

## Verified MCP hosts

The repository has end-to-end Host smoke coverage in `.github/workflows/agent-host-smoke.yml`. These tests exercise real Host implementations rather than calling `tracecite_mcp.server` functions directly.

### Codex CLI

The baseline Codex smoke installs Core + MCP without an additional domain extension, so Codex sees the six canonical Evidence tools and calls `tracecite_retrieve` through Codex's MCP tool-call API. It also verifies RetrievalSession repeated-evidence behavior across two calls.

The successful path is:

```text
Codex CLI / app-server
        ↓ MCP
tracecite-mcp
        ↓ public API
tracecite-core
```

When an extension such as TraceCite Mobile is installed in the same MCP environment, its registered Agent capabilities are additive to that six-tool Evidence baseline.

### Pi Agent

Pi does not provide the same native MCP client surface, so the Host smoke installs `pi-mcp-adapter`. The shared project `.mcp.json` contains only the TraceCite stdio server definition. A Pi-specific `.pi/mcp.json` override enables `directTools`, sets `toolPrefix` to `none`, and disables the generic proxy once the direct tools are available.

The controlled baseline benchmark explicitly selects the six canonical Evidence tools:

```text
tracecite_retrieve
tracecite_materialize
tracecite_replay
tracecite_aggregate
tracecite_traverse
tracecite_verify
```

A deterministic local OpenAI-compatible fake model drives a real Pi Agent tool-call loop. The model calls `tracecite_retrieve` directly, the adapter routes it over MCP, TraceCite returns evidence, and Pi sends the real `role=tool` result back into the Agent loop.

The preferred Pi path is therefore:

```text
Pi Agent
   ↓ canonical direct tool call
pi-mcp-adapter directTools
   ↓ standard .mcp.json / MCP
tracecite-mcp
   ↓ public API
tracecite-core
```

For completeness, the adapter's default proxy mode internally namespaces remote tools as `<server>_<tool>`, so a server named `tracecite` plus MCP tool `tracecite_retrieve` appears there as `tracecite_tracecite_retrieve`. That is an adapter-only routing name and is not TraceCite's public MCP tool name.

## What is deliberately not implemented here

- planner or hypothesis ordering;
- root-cause scoring;
- `next_best_query`;
- `evidence_sufficient` / `ready_for_reasoning`;
- `stop_recommended`;
- Pi-specific convergence checkpoints;
- MCP-owned copies of domain extension registries or Mobile-specific imports;
- benchmark-only native-tool restrictions.

## Development

The `feature_for_agent` branch develops against the matching Core branch:

```bash
python -m pip install \
  'git+https://github.com/samstring/tracecite-core.git@feature_for_agent'
python -m pip install -e '.[dev]'
python -m pytest -q
tracecite-mcp
```

The default transport is stdio.

For Host-level validation, run or inspect:

```text
.github/workflows/agent-host-smoke.yml
scripts/codex_app_server_smoke.py
scripts/pi_fake_openai_server.py
```

## Dependency rule

`tracecite-mcp` may depend only on public `tracecite`, `tracecite.runtime`, and `tracecite.extension` contracts. If MCP needs a Core-private import, treat that as a Core public-contract design issue rather than solving it with a private dependency.
