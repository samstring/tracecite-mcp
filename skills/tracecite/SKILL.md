---
name: tracecite
description: Use TraceCite MCP's canonical Evidence Runtime tools while keeping hypotheses, causal reasoning, evidence sufficiency and stopping decisions with the Agent.
---

# TraceCite MCP Agent Skill

TraceCite is an Evidence Runtime. Use it to acquire, recover, summarize, traverse, and verify evidence. Do not treat TraceCite as a planner or root-cause oracle.

## Responsibility boundary

The Agent owns:

- understanding the task;
- hypotheses and alternatives;
- which source/query/entity/range to inspect;
- investigation order;
- causal interpretation;
- whether evidence is sufficient for a particular conclusion;
- the final answer;
- when to stop.

TraceCite owns mechanical evidence facts:

- bounded retrieval;
- exact materialization;
- replay;
- provenance and source identity;
- session-scoped novelty and repeated-evidence accounting;
- deterministic aggregation;
- caller-scoped deterministic traversal;
- integrity verification;
- coverage/truncation/acquisition-end facts.

## Canonical MCP tools

```text
tracecite_retrieve
tracecite_materialize
tracecite_replay
tracecite_aggregate
tracecite_traverse
tracecite_verify
```

Use one stable `session_id` for `retrieve`, `materialize`, and `replay` calls that belong to the same investigation. A different investigation should use a different ID.

## `tracecite_retrieve`

Use for caller-selected source, query, or host-provider retrieval.

- `target.kind=source` inspects a caller-selected source/collection mechanically.
- `target.kind=query` searches a caller-selected query.
- `target.kind=provider` addresses process-local providers that the MCP Host already registered; select them by `provider_names` and provide an explicit bounded provider request.
- A hit is evidence, not proof of causality.
- `no_match` means no match in the searched scope; it does not prove real-world absence.
- `new_evidence=0` means this RetrievalSession received no new Evidence identity from this call.
- Repeated evidence can still be relevant to the current query even when its body is suppressed.

Do not use `retrieve` for exact range rereads; use `materialize` or `replay`.

## `tracecite_materialize`

Use when you have selected a concrete line/range and need exact bounded context.

Preserve returned provenance and SHA-256. Suppressed duplicate bodies do not mean the evidence ceased to exist; the same immutable range can be deliberately replayed later.

## `tracecite_replay`

Use when you intentionally need to see already-covered immutable evidence again.

Replay requires the immutable source SHA-256 and prior coverage in the same RetrievalSession. It returns evidence intentionally while keeping `new_evidence=0`. Do not pretend replayed evidence is newly discovered support.

## `tracecite_aggregate`

Use for deterministic `count`, `distinct`, or `group` work over a caller-selected query/scope. Aggregation values are mechanical properties. Frequency or dominance is not causal importance.

## `tracecite_traverse`

Use only after you have selected both:

- one or more provider names already registered by the MCP Host; and
- seed Evidence IDs and/or EntityRefs.

You also select explicit traversal limits. Provider objects are never supplied by the model and serialized provider snapshots are not an MCP capability. Traversal follows stable identity/entity relationships mechanically. It does not choose which sibling/entity is most important and does not select a new investigation hypothesis.

## `tracecite_verify`

Use to verify integrity/manifest facts. Verification does not validate a causal conclusion just because the underlying evidence artifact is intact.

## Evidence and correlation safety

Treat provenance, source version, line/range and identity constraints as part of the evidence contract. If TraceCite reports that identifier-only correlation is unsafe, do not collapse distinct scopes using that identifier alone. This is an identity-safety fact, not a claim that the ambiguity caused the incident.

## Evidence boundaries

Keep observed facts, supported inference, and unsupported deeper claims distinct. If the available sources cannot establish a deeper cause or fix, state that boundary rather than presenting outside knowledge as observed evidence.

Mechanical exhaustion is not an epistemic conclusion:

```text
no_match                  != impossible event
new_evidence=0            != investigation complete
frontier exhausted        != hypothesis proven
integrity verified        != causal conclusion verified
```

TraceCite provides evidence mechanics; the Agent remains responsible for the decision made from that evidence.
