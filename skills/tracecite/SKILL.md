---
name: tracecite
description: Use TraceCite MCP's canonical Evidence Runtime tools while keeping hypotheses, causal reasoning, evidence sufficiency and stopping decisions with the Agent.
---

# TraceCite MCP Agent Skill

TraceCite is an Evidence Runtime, not a planner or root-cause oracle. Use it for bounded evidence acquisition, exact recovery, provenance, novelty, aggregation, traversal and integrity. The Agent still owns hypotheses, investigation order, causal interpretation, sufficiency, the final answer and when to stop.

## Responsibility boundary

TraceCite owns mechanical facts:

- bounded retrieval and exact materialization;
- provenance and immutable source identity;
- RetrievalSession novelty / repeated-evidence accounting;
- deterministic count / distinct / grouping;
- caller-seeded deterministic traversal;
- coverage, truncation, acquisition-end and integrity facts.

The Agent owns:

- what question or hypothesis is unresolved;
- which source/query/entity/range to inspect next;
- what evidence means causally;
- whether the supplied evidence is sufficient;
- the final conclusion and stopping decision.

MCP may compact redundant transport fields. Missing compacted fields are not evidence. Mechanical completion is never proof of a causal conclusion.

## Evidence-efficient investigation rules

These rules are the default cadence for runtime evidence:

1. **Reuse one `session_id`** for the entire investigation.
2. **One broad retrieval at a time per source/session.** Do not fire several broad TraceCite searches in parallel before reading the first result; use that result to choose the next focused step.
3. For a broad `target.kind="query"`, normally request **`max_evidence <= 8`**. The MCP transport may enforce an even smaller focused bound after prior searches.
4. If a truncated search returns `data.signal_hints`, prefer **materializing one strong hint** before issuing another broad synonym query. Hints are navigation candidates, not formal cited evidence until materialized.
5. When a concrete line is known, use `tracecite_materialize` with a **small window, normally ±3–5 lines**. Do not expand dozens of lines unless the unresolved question needs that span.
6. For repeated-pattern questions, use **`tracecite_aggregate` first**. Retrieve only a few representative rows afterward if exact examples are needed.
7. If `coverage.new_evidence=0`, repeated-only results, or the same immutable range has already been covered, do not issue a synonym/replay unless you can name a materially different purpose.
8. Once runtime evidence yields a strong exact error/signature, switch to the Agent's normal source-code tools for source exploration when source code is outside the TraceCite-only evidence boundary. Do not use TraceCite as a generic source-code reader.
9. Prefer the smallest operation that resolves the current uncertainty. Do not continue exploring downstream wrapper symptoms after the causal mechanism is already strongly localized unless an alternative hypothesis still requires it.

A typical efficient flow is:

```text
broad query (<=8)
→ representative evidence + signal_hints
→ materialize one selected line ±3–5
→ Agent source-code reasoning
→ aggregate / one focused verification if needed
→ answer when the Agent judges the evidence sufficient
```

## Tool selection

| Need | Tool |
| --- | --- |
| Search/acquire caller-selected runtime evidence | `tracecite_retrieve` |
| Read exact known lines with bounded context | `tracecite_materialize` |
| Deliberately re-read already-covered immutable evidence | `tracecite_replay` |
| Count/distinct/group deterministic matches | `tracecite_aggregate` |
| Follow caller-selected provider identities/entities | `tracecite_traverse` |
| Verify evidence manifest/integrity | `tracecite_verify` |

Do not use native grep/read on a TraceCite-only evidence source. Do not put `start_line`, `end_line`, `line_count`, `before`, or `after` inside a retrieve target; exact ranges belong to `tracecite_materialize`.

## Canonical calls

### Broad or focused query

```json
{
  "session_id": "incident-123",
  "target": {
    "kind": "query",
    "source": "/allowed/evidence/app.log",
    "query": "fail|error|panic",
    "regex": true,
    "snapshot": true,
    "max_evidence": 8
  }
}
```

Useful optional query fields: `last`, `since`, `until`, `fold`, `max_evidence`, `max_line_chars`, `segmenter`.

### Acquire source orientation

```json
{
  "session_id": "incident-123",
  "target": {
    "kind": "source",
    "source": "/allowed/evidence/app.log",
    "segmenter": "auto"
  }
}
```

Source orientation is navigation, not diagnosis. For failure investigation, a broad severe-signal query is often more useful than repeatedly sampling the source.

### Materialize a selected hint/hit

```json
{
  "session_id": "incident-123",
  "source": "/allowed/evidence/app.log",
  "start_line": 120,
  "end_line": 120,
  "before": 3,
  "after": 3,
  "expected_sha256": "<source_sha256>"
}
```

Prefer `expected_sha256` when available so the exact read is bound to the immutable source version already observed.

### Aggregate before fetching many repeated examples

```json
{
  "source": "/allowed/evidence/app.log",
  "query": "failed",
  "operation": "count",
  "regex": false
}
```

A count is a mechanical property, not causal importance.

### Replay

```json
{
  "session_id": "incident-123",
  "source": "/allowed/evidence/app.log",
  "start_line": 120,
  "end_line": 120,
  "expected_sha256": "<same immutable source sha256>"
}
```

Replay requires prior coverage in the same RetrievalSession and is deliberate rereading, not discovery.

### Provider retrieval / traversal

Only use providers registered by the MCP Host. The Agent selects provider names, seed Evidence IDs/EntityRefs and bounded limits. Never supply executable provider code or serialized provider snapshots.

## Reading compact results

### `evidence[]`

Evidence rows are addressable mechanical evidence, not causal conclusions. Common fields:

- `ref`: exact human-readable line reference;
- `start_line` / `end_line`;
- `uri`: stable evidence identity when present;
- `preview`: bounded orientation text;
- `entities`: reusable mechanical identities when present.

Shared `source` and `source_sha256` may appear once at the top level instead of being repeated on every row.

### `data.signal_hints`

Signal hints are bounded, line-addressable navigation candidates selected mechanically from a truncated match set. They are not EvidencePointers and are not root-cause rankings. Select a useful hint yourself, then materialize its line before citing it.

### Exact text

`data.text` or `data.new_text` contains exact bounded materialized text. MCP may suppress a duplicate copy when the same body was already delivered in the RetrievalSession. Use replay only when rereading covered text is genuinely necessary.

### `coverage`

Important facts include:

```text
new_evidence > 0       = new evidence identities entered this session
new_evidence = 0       = this call added no new evidence identity
repeated_evidence > 0  = current request matched already-known evidence
complete / truncated   = mechanics of the requested scope
```

These do not mean the investigation is complete or a hypothesis is proven.

### `mcp_session`

- `session_id`: stable investigation ID;
- `revision`: session state revision;
- `progress`: compact operation/novelty summary.

Use it to recognize repeated work. It is not a confidence score.

### Routing/progress/end facts

`routing.mode`, `routing.next_mode`, novelty/progress, `acquisition_end_reason`, `unseen_ranges`, `missing_evidence`, correlation constraints and traversal stop reasons describe evidence transport/acquisition. They do not select a hypothesis or decide that the answer is sufficient.

## Investigation loop

```text
1. Name the exact unresolved question.
2. Choose the smallest TraceCite operation that can add relevant evidence.
3. Read provenance + compact evidence + signal hints + novelty/coverage.
4. Update your own causal model.
5. Prefer focused materialization/aggregation over another broad search.
6. If the next call would repeat covered evidence, require a materially different purpose.
7. Continue only while a distinct evidence frontier or necessary deterministic check remains.
8. Otherwise answer at the evidence boundary and state what is inference/unproven.
```

This is Agent policy, not a TraceCite causal gate.

## Evidence boundaries

Keep observed facts, supported inference and unsupported deeper claims distinct:

```text
no_match                  != impossible event
new_evidence=0            != investigation complete
repeated_evidence>0       != useless evidence
coverage.complete         != causal chain complete
frontier exhausted        != hypothesis proven
integrity verified        != causal conclusion verified
```

TraceCite provides evidence mechanics; the Agent remains responsible for the decision made from that evidence.
