# TraceCite MCP

Thin Model Context Protocol adapter for TraceCite's canonical Evidence Runtime.

`tracecite-mcp` intentionally remains a separate project from `tracecite-core`. Core owns evidence mechanics; this repository owns MCP transport, Host policy, session mapping, serialization, and process-local provider resolution.

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
└────────────────────────────────────────────┘
```

The boundary is:

> **Agent owns thinking and decisions. TraceCite owns evidence.**

The MCP server does not choose hypotheses, investigation order, causal explanations, evidence sufficiency, root cause, or when an Agent should stop.

## Canonical MCP tool surface

The Agent-visible surface is exactly six tools:

| MCP tool | Core primitive | Responsibility |
|---|---|---|
| `tracecite_retrieve` | `retrieve` | caller-selected source/query/provider evidence acquisition |
| `tracecite_materialize` | `materialize` | exact caller-selected source range |
| `tracecite_replay` | `replay` | deliberate reread of already-covered immutable evidence |
| `tracecite_aggregate` | `aggregate` | deterministic `count` / `distinct` / `group` |
| `tracecite_traverse` | `traverse` | bounded deterministic traversal from caller-selected seeds |
| `tracecite_verify` | `verify` | mechanical manifest/integrity verification |

The generic MCP contract does not expose `probe`, `sample`, `survey`, `search`, `expand`, Investigation/Finding APIs, Capability Registry actions, Pi checkpoint logic, or benchmark guards. Those concerns must not become a second Evidence semantic surface.

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

## Local source access policy

Filesystem access is Host-owned policy, not a model-controlled option.

By default local Evidence operations can access only the MCP process working directory. A Host can explicitly widen the allowed roots:

```bash
export TRACECITE_MCP_ALLOWED_ROOTS="/project/logs:/another/evidence/root"
```

Use the platform path separator (`:` on macOS/Linux, `;` on Windows). Symlinks are resolved before the allowlist check, and source globs may not escape with `..`.

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

`skills/tracecite/SKILL.md` is Agent-neutral. It explains the six tool semantics and evidence boundaries without encoding Pi/Codex/Claude-specific diagnosis strategy.

The same semantic content can be packaged into another Agent's skill system. Agent-specific wrappers should stay thin.

## What is deliberately not implemented here

- planner or hypothesis ordering;
- root-cause scoring;
- `next_best_query`;
- `evidence_sufficient` / `ready_for_reasoning`;
- `stop_recommended`;
- Pi-specific convergence checkpoints;
- automatic Mobile/CI/OTel extension loading;
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

## Dependency rule

`tracecite-mcp` may depend only on public `tracecite`, `tracecite.runtime`, and `tracecite.extension` contracts. If MCP needs a Core-private import, treat that as a Core public-contract design issue rather than solving it with a private dependency.
