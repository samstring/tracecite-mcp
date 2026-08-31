---
name: tracecite
description: Use TraceCite MCP's canonical Evidence Runtime tools while keeping hypotheses, causal reasoning, evidence sufficiency and stopping decisions with the Agent.
---

# TraceCite MCP Agent Skill

TraceCite is an Evidence Runtime. Use it to acquire, recover, summarize, traverse, and verify evidence. Do not treat TraceCite as a planner, root-cause oracle, or generic file reader.

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
- provenance and immutable source identity;
- session-scoped novelty and repeated-evidence accounting;
- deterministic aggregation;
- caller-scoped deterministic traversal;
- integrity verification;
- coverage/truncation/acquisition-end facts.

The MCP transport may compact or suppress redundant transport fields, but it must not add a hypothesis, root cause, evidence-sufficiency judgment, or stopping decision.

## Golden rules

1. Use one stable `session_id` for all `tracecite_retrieve`, `tracecite_materialize`, and `tracecite_replay` calls in one investigation. Do not invent a new session for every query.
2. Use `tracecite_retrieve` to search or acquire evidence. **Never pass `start_line`, `end_line`, `line_count`, `before`, or `after` inside a retrieve target.**
3. Use `tracecite_materialize` when you already know a concrete line/range and need exact bounded context.
4. Use `tracecite_replay` only when you deliberately need to see previously covered immutable evidence again.
5. Use `tracecite_aggregate` for deterministic counts/distinct/grouping, not for causal ranking.
6. Treat every returned coverage/novelty/end field as a mechanical fact about the requested scope, not an epistemic conclusion about the incident.
7. Prefer the smallest operation that answers the current unresolved question. Do not repeatedly query the same evidence without a materially different purpose.

## Tool selection

| Need | Tool | Do not use instead |
| --- | --- | --- |
| Search a log/file for a term or regex | `tracecite_retrieve` with `target.kind="query"` | native grep/read on a TraceCite-only evidence source |
| Acquire a caller-selected source/collection | `tracecite_retrieve` with `target.kind="source"` | range-shaped retrieve arguments |
| Ask registered evidence providers for bounded evidence | `tracecite_retrieve` with `target.kind="provider"` | model-supplied provider code |
| Read exact known lines with context | `tracecite_materialize` | `retrieve` + `start_line`/`line_count` |
| Intentionally re-read already covered exact evidence | `tracecite_replay` | pretending replay is new evidence |
| Count/distinct/group matching records | `tracecite_aggregate` | inferring causal importance from frequency |
| Follow caller-selected evidence/entity identities through registered providers | `tracecite_traverse` | asking TraceCite to choose the next hypothesis |
| Verify an evidence manifest/integrity fact | `tracecite_verify` | treating integrity as causal validation |

## Canonical call shapes

### Search a source

Use `target.kind="query"`:

```json
{
  "session_id": "incident-123",
  "target": {
    "kind": "query",
    "source": "/allowed/evidence/app.log",
    "query": "seccomp",
    "regex": false,
    "snapshot": true,
    "segmenter": "auto",
    "max_evidence": 20
  }
}
```

Useful optional query fields are `last`, `since`, `until`, `fold`, `max_evidence`, and `max_line_chars`.

For regex search:

```json
{
  "session_id": "incident-123",
  "target": {
    "kind": "query",
    "source": "/allowed/evidence/app.log",
    "query": "fail|error|panic",
    "regex": true
  }
}
```

### Acquire a source/collection

Use `target.kind="source"`:

```json
{
  "session_id": "incident-123",
  "target": {
    "kind": "source",
    "source": "/allowed/evidence/logs",
    "glob": "*.log",
    "recursive": false,
    "segmenter": "auto"
  }
}
```

The source and glob remain constrained by the MCP Host allowlist.

### Materialize known lines

When retrieval gives a useful `ref` such as `app.log:L120-L126`, read that concrete area with `tracecite_materialize`:

```json
{
  "session_id": "incident-123",
  "source": "/allowed/evidence/app.log",
  "start_line": 120,
  "end_line": 126,
  "before": 3,
  "after": 3,
  "expected_sha256": "<source_sha256 returned by TraceCite>"
}
```

`expected_sha256` is strongly preferred when available because it binds the reread to the immutable source version you actually observed.

### Replay covered evidence

Replay is deliberate rereading, not discovery:

```json
{
  "session_id": "incident-123",
  "source": "/allowed/evidence/app.log",
  "start_line": 120,
  "end_line": 126,
  "expected_sha256": "<same immutable source sha256>"
}
```

Replay requires prior coverage of that immutable range in the same RetrievalSession.

### Aggregate mechanically

```json
{
  "source": "/allowed/evidence/app.log",
  "query": "failed",
  "operation": "count",
  "regex": false
}
```

Supported aggregation semantics are deterministic properties of the selected scope. A high count does not mean high causal importance.

### Provider retrieval

Only select providers already registered by the MCP Host:

```json
{
  "session_id": "incident-123",
  "target": {
    "kind": "provider",
    "provider_names": ["provider-name"],
    "request": {
      "evidence_ids": ["seed-evidence-id"],
      "limit": 20,
      "depth": 0,
      "reason": "confirm caller-selected relationship"
    }
  }
}
```

Do not supply provider objects, executable code, or serialized provider snapshots.

## How to read TraceCite results

The compact MCP response is operation-specific. Fields that are absent were not needed for that operation; absence of a compacted field is not itself evidence.

### Top-level operation/status

- `operation`: the mechanical TraceCite operation that produced the response.
- `status="ok"`: the operation executed successfully. It does **not** mean the hypothesis is correct.
- `status="no_match"` or an equivalent no-match result: nothing matched in the requested scope. It does **not** prove the event is impossible or absent outside that scope.
- `error`: an execution/validation failure. Fix the call or scope; do not interpret it as evidence about the incident.

### `evidence[]`

Each evidence row is an addressable evidence identity, not a causal conclusion. Important projected fields can include:

- `id`: stable evidence identity when available;
- `kind`: evidence kind;
- `source`: source path/identity;
- `ref`: human-readable exact line reference such as `app.log:L120-L126`;
- `start_line` / `end_line`: exact source line bounds when present;
- `uri`: evidence URI/identity when present;
- `source_sha256`: immutable source digest. Preserve this for exact materialization/replay and provenance;
- `preview`: bounded preview for orientation, not necessarily all context needed for the conclusion;
- `entities`: mechanical entity identities that may be reused as caller-selected traversal seeds.

A hit means "this evidence matched/acquired under the requested mechanics". It does not mean "this caused the failure".

### Exact text and novelty data

For retrieve/materialize/replay, `data` may include:

- `text`: exact returned bounded text where the operation exposes exact text;
- `new_text`: text corresponding to newly surfaced evidence where available;
- `novelty`: mechanical novelty state for this RetrievalSession;
- `matched_existing_evidence`: evidence matched again even though its body may be suppressed;
- `replayed`: indicates deliberate replay rather than new discovery.

If a repeated evidence body is suppressed, the evidence still exists. Use `tracecite_replay` only if seeing the exact covered text again is genuinely necessary.

### `coverage`

Coverage describes what the requested operation mechanically covered. Common fields include:

- `new_evidence`: number of evidence identities newly observed by this RetrievalSession in this call;
- `repeated_evidence`: evidence identities already known to the session and encountered again;
- `complete`: completion of the requested mechanical scope when provided.

Interpretation rules:

```text
new_evidence > 0       = this session learned new evidence identities
new_evidence = 0       = this call added no new evidence identity
repeated_evidence > 0  = this call revisited evidence already known to the session
coverage.complete      = requested mechanical scope completed, when applicable
```

None of these means the investigation is complete or a hypothesis is proven.

### `mcp_session`

`mcp_session` is Host/session bookkeeping:

- `session_id`: the investigation ID you supplied;
- `revision`: monotonically advances as the RetrievalSession changes;
- `progress`: mechanical cumulative session summary such as operation counts/coverage facts.

Use it to maintain one coherent investigation and recognize repeated work. Do not treat session progress as a confidence score.

### End, missing, unseen, and correlation facts

Responses may contain:

- `acquisition_end_reason`: why a bounded acquisition mechanically ended;
- `unseen_ranges`: source ranges not covered by the operation/session when available;
- `missing_evidence`: mechanically known missing evidence requirements/facts when exposed;
- `correlation_constraints`: identity/correlation safety constraints;
- `observed_references` / `observed_relations`: mechanically observed references/relations;
- `progress`: operation/session progress facts.

These fields define the evidence boundary. They do not select the next hypothesis or decide whether the answer is sufficient.

### Aggregate/traverse/verify results

- `aggregate` / aggregate `data`: deterministic values over the caller-selected query/scope. Frequency is not causality.
- `traverse.stop_reason` / `acquisition_end_reason`: why bounded traversal mechanically stopped. Frontier exhaustion is not proof.
- `trace`, `graph`, `grouping`, `reduction`, `diagnostics`: mechanical traversal products; the Agent decides which relationships matter.
- `verification`: integrity/manifest facts. Integrity verified does not mean causal conclusion verified.

## Investigation loop

A good evidence loop is:

1. State the current hypothesis or exact unresolved question to yourself.
2. Choose the smallest TraceCite operation that can obtain materially relevant evidence for that question.
3. Read provenance, coverage, novelty, exact text, and acquisition-end facts mechanically.
4. Update your own causal model. Do not convert `no_match`, `new_evidence=0`, replay, or frontier exhaustion into a causal conclusion.
5. If the next call would inspect the same covered evidence again, first ask what materially different evidence it is expected to add. Prefer a different query, range, source, entity, or evidence class when one exists.
6. After repeated low-novelty calls, explicitly reassess the strongest supported conclusion, the exact unresolved question, and whether the supplied inputs contain the evidence class required to resolve it.
7. Continue only when you can identify a materially different evidence frontier or a necessary deterministic check. Otherwise answer at the current evidence boundary and state what remains unproven.

This is Agent policy, not a TraceCite gate. TraceCite may report mechanical novelty facts; only the Agent decides whether to continue or stop.

## Canonical MCP tools

```text
tracecite_retrieve
tracecite_materialize
tracecite_replay
tracecite_aggregate
tracecite_traverse
tracecite_verify
```

## Per-tool semantic reminders

### `tracecite_retrieve`

Use for caller-selected source, query, or Host-provider retrieval.

- `target.kind="source"` acquires a caller-selected source/collection mechanically.
- `target.kind="query"` searches a caller-selected source/query.
- `target.kind="provider"` addresses process-local providers that the MCP Host already registered; select them by `provider_names` and provide an explicit bounded provider request.
- `target.kind="range"` is intentionally unsupported. Use `materialize` or `replay` for exact ranges.
- A hit is evidence, not proof of causality.
- `no_match` means no match in the searched scope; it does not prove real-world absence.
- `new_evidence=0` means this RetrievalSession received no new Evidence identity from this call.
- Repeated evidence can still be relevant to the current query even when its body is suppressed.

### `tracecite_materialize`

Use when you have selected a concrete line/range and need exact bounded context. Preserve returned provenance and SHA-256. Suppressed duplicate bodies do not mean the evidence ceased to exist; the same immutable range can be deliberately replayed later.

### `tracecite_replay`

Use when you intentionally need to see already-covered immutable evidence again. Replay requires the immutable source SHA-256 and prior coverage in the same RetrievalSession. It returns evidence intentionally while keeping `new_evidence=0`. Do not pretend replayed evidence is newly discovered support.

### `tracecite_aggregate`

Use for deterministic `count`, `distinct`, or `group` work over a caller-selected query/scope. Aggregation values are mechanical properties. Frequency or dominance is not causal importance.

### `tracecite_traverse`

Use only after you have selected both one or more provider names already registered by the MCP Host and seed Evidence IDs and/or EntityRefs. You also select explicit traversal limits. Provider objects are never supplied by the model and serialized provider snapshots are not an MCP capability. Traversal follows stable identity/entity relationships mechanically. It does not choose which sibling/entity is most important and does not select a new investigation hypothesis.

### `tracecite_verify`

Use to verify integrity/manifest facts. Verification does not validate a causal conclusion just because the underlying evidence artifact is intact.

## Evidence and correlation safety

Treat provenance, source version, line/range and identity constraints as part of the evidence contract. If TraceCite reports that identifier-only correlation is unsafe, do not collapse distinct scopes using that identifier alone. This is an identity-safety fact, not a claim that the ambiguity caused the incident.

## Evidence boundaries

Keep observed facts, supported inference, and unsupported deeper claims distinct. If the available sources cannot establish a deeper cause or fix, state that boundary rather than presenting outside knowledge as observed evidence.

Mechanical exhaustion is not an epistemic conclusion:

```text
no_match                  != impossible event
new_evidence=0            != investigation complete
repeated_evidence>0       != useless evidence
coverage.complete         != causal chain complete
frontier exhausted        != hypothesis proven
integrity verified        != causal conclusion verified
```

TraceCite provides evidence mechanics; the Agent remains responsible for the decision made from that evidence.
