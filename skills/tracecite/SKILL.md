---
name: tracecite
description: Use TraceCite as a session-stable Evidence Compute Runtime. Batch already-chosen mechanical computations, keep intermediate evidence Runtime-side, and materialize exact immutable evidence only when its content is needed. The Agent owns hypotheses, causal reasoning, sufficiency, and stopping.
---

# TraceCite Evidence Compute Runtime

TraceCite is not a planner or root-cause oracle. You decide what you need to know, which hypotheses matter, how to interpret results, and when the investigation is sufficient. TraceCite performs mechanical evidence computation while preserving SourceVersion identity, provenance, coverage, novelty, and Host-owned transport limits.

The Host may expose TraceCite as direct tools. When `tracecite_analyze`, `tracecite_run`, `tracecite_materialize`, and/or `tracecite_replay` are already present in the tool list, use them directly. Do **not** load MCP scripting/proxy/discovery skills, search the filesystem for MCP helpers, inspect adapter internals, or probe an MCP CLI merely to rediscover tools that are already registered. Tool discovery is only appropriate when the Host has not provided the required direct capability.

## Usage contract

1. Reuse one `session_id` throughout an investigation so search, compute, materialize, and replay stay in one immutable evidence world.
2. When you have already decided on several mechanical computations over the same source and scope, submit them together with `tracecite_analyze` rather than alternating model/tool calls for each one.
3. Keep intermediate RecordSets inside TraceCite. Ask for bounded derived results such as counts, groups, distinct values, bounded top-K/min/max projections, or other supported compact computations.
4. Use `tracecite_run` when you need one bounded search/filter/navigation operation or raw Evidence pointers rather than a batch of derived results.
5. Use `tracecite_materialize` only after selecting exact Evidence whose body is needed for reasoning or citation. Use `tracecite_replay` only for an intentional reread of already covered immutable Evidence.
6. Do not repeat an identical computation. `novelty.query_repeated=true` is a mechanical indication that the exact request has already been made.
7. If `status=too_broad`, reduce the requested output mechanically: narrow the scope/predicate, ask for a compact aggregate, or make an explicit bounded selection. Do not enlarge Host budgets and do not treat an arbitrary first-N sample as complete evidence.
8. Evidence token/byte limits, source lifecycle/snapshot policy, materialization ceilings, and compute policy belong to the User/Host, not the Agent.
9. Do not bypass a TraceCite-only evidence boundary with native grep/read/bash.
10. Use request-level `last` / `since` / `until` for a whole-operation time scope when that is what you mean. A `where` stage is one field predicate; combine several predicates with additional pipeline stages unless the tool schema explicitly documents another boolean form.
11. If the task or environment explicitly names a small Evidence source whose contents are needed, read that named source through `tracecite_run` with an explicit bounded selection such as `head N`; do not switch to native `cat`/read merely because the source is small. This rule is about respecting the Evidence boundary, not about preferring any particular file, field, or investigation order.
12. `search TEXT` is literal text search. Use `regex PATTERN` when alternation, character classes, anchors, repetition, or other regular-expression semantics are intended. Do not encode several alternatives with regex metacharacters inside `search` and then interpret `no_match` as evidence that none of the alternatives occurred.
13. Do not fan out several parallel `tracecite_run` calls against the same source and scope when their results can be expressed as bounded derived computations. Before issuing sibling same-source calls, collapse all already-chosen `count` / `group` / `distinct` and `sort ... | head N | project ...` checks into one `tracecite_analyze` batch so TraceCite can share the physical scan. Use separate `tracecite_run` calls only for raw Evidence selections that cannot be represented as those bounded derived outputs, and defer those raw selections until the batch has identified the candidates that actually need bodies.

These rules organize computation only. They never prescribe which service, metric, event, time window, comparison, hypothesis, or stopping condition is correct for a task.

## Primary tools

| Need | Tool |
| --- | --- |
| Several already-chosen bounded computations over one source/scope | `tracecite_analyze` |
| One bounded search/filter/aggregate/navigation/evidence-selection program | `tracecite_run` |
| Exact body/context for a selected EvidencePointer | `tracecite_materialize` |
| Intentional reread of covered immutable Evidence | `tracecite_replay` |

Compatibility/provider/integrity tools may also exist, but they are not the default evidence-compute path.

## Batch first when the work is already known

`tracecite_analyze` accepts named mechanical programs. A batch may include compatible aggregates and bounded selections such as count/group/distinct or sort + bounded head + project. Optional `last` / `since` / `until` scope applies explicitly to the whole batch.

Example shape:

```json
{
  "session_id": "investigation-1",
  "source": "/evidence/events.jsonl",
  "since": "2026-09-05T10:00:00Z",
  "until": "2026-09-05T10:10:00Z",
  "analyses": [
    {"name": "row_count", "program": "count"},
    {"name": "by_type", "program": "group eventType | sort count desc | head 10"},
    {"name": "first_time", "program": "sort timestamp asc | head 1 | project timestamp"},
    {"name": "last_time", "program": "sort timestamp desc | head 1 | project timestamp"}
  ]
}
```

The example demonstrates computation shape only. It does not imply that any particular field or time window should be used for a real investigation.

TraceCite may share scans or choose another semantics-preserving physical plan. An unsupported sibling must not change the meaning of supported computations. Execution planning is Runtime-owned; causal interpretation remains Agent-owned.

## One composed operation instead of mechanical chatter

If the complete mechanical pipeline is already known, express it in one `tracecite_run` call rather than splitting it across repeated tool/model turns. The tool schema and structured error feedback are the source of truth for supported syntax.

Examples of generic shapes:

```text
where FIELD >= VALUE | where OTHER_FIELD == VALUE | group THIRD_FIELD | sort count desc | head 10
sort FIELD asc numeric | head 3 | project FIELD
search TEXT | near line=LINE before=3 after=5
regex 'ERROR|WARN' | head 10
```

For an explicitly named small Evidence source, a bounded whole-source read is also a normal `tracecite_run` operation, for example `head 20`. The bound is chosen to fit the known source/task; it is not a rule to sample large sources.

Do not spend model turns discovering or re-describing TraceCite syntax when the direct tools are already available.

## Result semantics

Treat these as mechanical facts, not conclusions:

```text
no_match                  != impossible event
no_new_evidence           != investigation complete
query_repeated=true       -> exact request repetition fact
repeated_evidence>0       != new Evidence identity
coverage.complete         != causal chain complete
integrity verified        != causal conclusion verified
status=too_broad          != no evidence exists
projected/aggregate value != raw Evidence body
```

For repeated-only results, use bounded representative receipts for orientation and exact coverage/count fields for scope. Previously seen Evidence remains recoverable through explicit materialize/replay.

## Causal attribution discipline

A suspicious error signature is not automatically the incident trigger. Before calling an observed event a process/container failure or the root cause, reconcile it with lifecycle continuity and the user-visible failure sequence.

- Build the smallest supported causal sequence around the relevant interval: last healthy behavior → first observed failure → lifecycle transition if observed → recovery or continued failure.
- A message that sounds process-fatal does not prove the active workload process died. If normal application activity continues across that message, process identity/lifecycle remains unresolved unless Evidence directly links the message to that same process instance.
- Do not infer an orchestrator lifecycle state, restart policy, kill reason, or backoff mechanism from retry intervals alone. Require direct platform evidence or an unambiguous process/container lifecycle sequence.
- Errors observed during shutdown, startup, or recovery can be consequences or side-process artifacts. Do not promote them to the initiating trigger without temporal and identity support.
- Prefer the narrowest mechanism directly supported by Evidence. If telemetry proves shutdown/restart but not what initiated it, keep the external trigger unknown rather than guessing.

These are generic evidence standards, not a prescribed investigation order. The Agent still chooses which hypotheses and fields to test.

## Sufficiency checkpoint and stopping discipline

Evidence quality does not improve merely because more tool calls are possible. Re-evaluate sufficiency whenever a material causal-chain claim becomes supported or contradicted.

Stop gathering new Evidence and answer when all claims the task actually requires can already be made at an evidence-supported specificity, including appropriate uncertainty. In particular:

- the responsible entity or component is supported strongly enough for the requested conclusion;
- the concrete mechanism/fault type is supported at the narrowest defensible level;
- the causal chain needed by the task is supported by direct observations and clearly labeled inference;
- material counterevidence has been reconciled or explicitly left unresolved;
- exact Evidence needed for the final citations has already been selected/materialized;
- remaining unknowns would only make the explanation more specific, not change the supported responsible entity, mechanism, causal chain, or evidence boundary.

Once the supplied Evidence establishes the requested mechanism but does not expose a more upstream trigger, state that boundary and finish. Do **not** keep searching unrelated sources merely to invent or name an unobserved trigger, unless the user explicitly requires that upstream trigger or new contradictory Evidence could change the conclusion.

Before issuing another tool call after a plausible answer is already supported, ask what decision that call could change. If it cannot change the responsible entity, mechanism, causal chain, uncertainty boundary, or citation completeness, do not issue it.

This checkpoint controls investigation cost; it does not lower the evidentiary standard and does not prescribe which hypothesis should win.

## SourceVersion and citations

A RetrievalSession fixes one SourceVersion per logical source. Keep the same session so later computations and exact reads refer to the same evidence world.

When final reasoning needs an exact observation, materialize the selected pointer/range and cite that observed immutable content. Aggregate/projected results are derived mechanical facts; do not pretend they contain raw evidence bodies they did not return.

TraceCite reports what was mechanically computed and where it came from. You decide what it means.
