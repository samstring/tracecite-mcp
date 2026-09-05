---
name: tracecite
description: Use TraceCite as a session-stable Evidence Compute Runtime. Batch already-chosen mechanical computations, keep intermediate evidence Runtime-side, and materialize exact immutable evidence only when its content is needed. The Agent owns hypotheses, causal reasoning, sufficiency, and stopping.
---

# TraceCite Evidence Compute Runtime

TraceCite is not a planner or root-cause oracle. You decide what you need to know, which hypotheses matter, how to interpret results, and when the investigation is sufficient. TraceCite performs mechanical evidence computation while preserving SourceVersion identity, provenance, coverage, novelty, and Host-owned transport limits.

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
where FIELD >= VALUE | group OTHER_FIELD | sort count desc | head 10
sort FIELD asc numeric | head 3 | project FIELD
search TEXT | near line=LINE before=3 after=5
```

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

## SourceVersion and citations

A RetrievalSession fixes one SourceVersion per logical source. Keep the same session so later computations and exact reads refer to the same evidence world.

When final reasoning needs an exact observation, materialize the selected pointer/range and cite that observed immutable content. Aggregate/projected results are derived mechanical facts; do not pretend they contain raw evidence bodies they did not return.

TraceCite reports what was mechanically computed and where it came from. You decide what it means.
