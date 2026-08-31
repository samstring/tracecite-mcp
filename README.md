# TraceCite MCP

Thin Model Context Protocol projection of TraceCite's canonical Evidence Runtime.

TraceCite MCP is intentionally **not** a second Agent. It does not choose hypotheses, investigation order, causal explanations, evidence sufficiency, or when an Agent should stop. It exposes deterministic evidence mechanics and keeps Agent reasoning outside the server.

## Architecture

```text
Agent / Claude / Codex / Cursor / other MCP host
                    │
                    │ MCP tools
                    ▼
┌────────────────────────────────────────────┐
│               tracecite-mcp                │
│                                            │
│  retrieve      materialize      replay     │
│  aggregate     traverse         verify     │
│                                            │
│  session_id -> RetrievalSessionStore       │
└──────────────────────┬─────────────────────┘
                       │ public canonical API
                       ▼
┌────────────────────────────────────────────┐
│              tracecite-core                │
│                                            │
│ provenance / source identity / coverage    │
│ novelty / repeated evidence / replay       │
│ bounded retrieval / deterministic traversal│
└────────────────────────────────────────────┘
```

The boundary is simple:

> **Agent owns thinking and decisions. TraceCite owns evidence mechanics.**

## Canonical tools

The MCP surface intentionally contains exactly six TraceCite Evidence Runtime tools:

| MCP tool | Core primitive | Responsibility |
|---|---|---|
| `tracecite_retrieve` | `retrieve` | caller-selected source/query retrieval with provenance, coverage and session novelty |
| `tracecite_materialize` | `materialize` | exact bounded caller-selected source context |
| `tracecite_replay` | `replay` | exact reread of already-covered immutable evidence without creating new novelty |
| `tracecite_aggregate` | `aggregate` | deterministic `count` / `distinct` / `group` over caller-selected local text |
| `tracecite_traverse` | `traverse` | bounded deterministic traversal from caller-selected evidence IDs/entities |
| `tracecite_verify` | `verify` | mechanical manifest/integrity verification |

The server does **not** expose compatibility wrappers such as `probe`, `sample`, `survey`, `search`, or `expand`. It also does not project Investigation/Finding semantics or Extension Capability Registry actions into this generic MCP surface. Those are separate secondary concerns and must not redefine the canonical Evidence contract.

## Retrieval sessions

`retrieve`, `materialize`, and `replay` accept a `session_id`.

The MCP server maps that ID to Core's canonical `RetrievalSessionStore`. A session may remember only mechanical evidence state such as:

- previously delivered Evidence identities;
- covered immutable ranges;
- repeated-evidence accounting;
- request fingerprints;
- bounded recent retrieval operations;
- replay history.

It does not remember or infer:

- hypotheses;
- root cause;
- causal confidence;
- evidence sufficiency;
- stopping decisions.

Use one stable `session_id` for one Agent investigation. Different IDs have independent evidence novelty state.

By default, session files are stored under:

```text
~/.tracecite/mcp/_retrieval_sessions/
```

The server owner can override the root:

```bash
export TRACECITE_MCP_SESSION_ROOT=/path/to/session-root
```

A host may also provide a default session ID:

```bash
export TRACECITE_MCP_SESSION_ID=my-investigation
```

Explicit tool arguments take precedence.

## Tool semantics

### `tracecite_retrieve`

The Agent supplies `target.kind=source|query` and chooses the source/query. Range access is deliberately separate through `tracecite_materialize`.

A hit is an observation, not proof of causality. `no_match` is a retrieval result, not proof that an event never occurred. `new_evidence=0` means no new Evidence identity was exposed in that RetrievalSession; it does not mean the investigation is complete.

### `tracecite_materialize`

The Agent selects the exact source and line/range. Immutable `expected_sha256` should be supplied when exact source identity matters.

### `tracecite_replay`

Replay requires the immutable SHA-256 and the requested range must already be covered in the same RetrievalSession. Replay returns the old evidence body intentionally while keeping novelty at zero.

### `tracecite_aggregate`

Aggregation is mechanical only. A dominant count/group is not automatically important or causal.

### `tracecite_traverse`

MCP cannot transport process-local Python provider objects directly, so the generic tool accepts a serialized provider snapshot with `name`, `evidence[]`, and optional `relations[]`. The Agent supplies `seed_evidence_ids` and/or `seed_entities` plus explicit traversal limits. The server does not select a next-best entity or investigation direction.

### `tracecite_verify`

Verification proves mechanical integrity/manifest facts. It does not validate an Agent's causal conclusion merely because an evidence artifact is intact.

## Agent skill

`skills/tracecite/SKILL.md` contains an Agent-neutral usage contract for these six MCP tools. Hosts may adapt the packaging to their own skill system, but the semantic content should remain shared rather than maintaining Pi/Codex/Claude-specific investigation rules.

## Development

The `feature_for_agent` branch develops against the matching TraceCite Core branch:

```bash
python -m pip install 'git+https://github.com/samstring/tracecite-core.git@feature_for_agent'
python -m pip install -e '.[dev]'
python -m pytest -q
tracecite-mcp
```

The default transport is stdio.

## Design guardrails

1. MCP maps tools; it does not implement a second Evidence Runtime.
2. Session memory remains Core-owned `RetrievalSessionStore` state.
3. MCP may expose mechanical telemetry, but must not turn it into root-cause or stop advice.
4. No benchmark-specific investigation hints belong in tool descriptions or skills.
5. New domain integrations should compose around the canonical six primitives rather than add competing evidence semantics.
