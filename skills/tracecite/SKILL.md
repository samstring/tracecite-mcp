---
name: tracecite
description: Use TraceCite MCP as a session-stable Evidence Runtime. Batch already-chosen mechanical aggregates with tracecite_analyze, use tracecite_run for bounded search/filter work, and materialize exact immutable evidence when needed. The Agent owns hypotheses, causal reasoning, sufficiency and stopping.
---

# TraceCite MCP Agent Skill

TraceCite is an Evidence Runtime, not a planner or root-cause oracle. The Agent owns investigation strategy and conclusions. TraceCite owns mechanical retrieval/compute, one immutable SourceVersion per RetrievalSession/source, provenance, novelty, coverage, Evidence transport policy and exact materialization.

## Core rules

1. Reuse one `session_id` for the whole investigation.
2. When several mechanical aggregate checks over the same source are already chosen, prefer one `tracecite_analyze` batch instead of separate tool/model rounds.
3. For bounded text search, filtering, navigation or raw Evidence selection, use `tracecite_run`.
4. Put mechanical narrowing/aggregation that is already known into one pipe-composed program. Intermediate rows remain Runtime-side.
5. Evidence token/byte limits are User/Host policy, never Agent parameters.
6. If `status=too_broad`, make the requested output mechanically smaller or more selective. Never enlarge the budget or use arbitrary first-N as a fake complete search.
7. Materialize only caller-selected exact records needed for reasoning/citation.
8. `no_new_evidence` means the current query exposed no new Evidence identity. It does not prove a hypothesis or end the investigation.
9. When `novelty.query_repeated=true`, do not issue the exact same query again.
10. When all matches were previously seen, TraceCite returns an exact repeated count plus bounded representative receipts. Old Evidence remains recoverable with `tracecite_materialize`/`tracecite_replay`; do not request a complete repeated-locator dump.
11. Do not use native grep/read on a TraceCite-only evidence source.

These rules explain TraceCite mechanics only. They do not tell you which hypothesis, service, metric, time window, comparison, or stopping point is correct for the user's task.

## Preferred tools

| Need | Tool |
| --- | --- |
| Several caller-selected aggregate checks over one source | `tracecite_analyze` |
| Search/filter/aggregate/navigate/select Evidence | `tracecite_run` |
| Exact context for a selected pointer | `tracecite_materialize` |
| Intentional reread of covered immutable evidence | `tracecite_replay` |
| Legacy source/provider compatibility | `tracecite_retrieve` |
| Legacy count compatibility | `tracecite_aggregate` |
| Provider/entity traversal | `tracecite_traverse` |
| Integrity/manifest check | `tracecite_verify` |

## Batch mechanical analysis

`tracecite_analyze` accepts a bounded list of named Evidence Shell aggregate programs over one source. Use it only for analyses you have already decided are relevant. TraceCite may fuse compatible scans internally; it does not choose the analyses or interpret their causal meaning.

Example shape:

```json
{
  "session_id": "investigation-1",
  "source": "/evidence/traces.jsonl",
  "analyses": [
    {"name": "status", "program": "group statusCode"},
    {"name": "failed_services", "program": "where statusCode >= 500 | group serviceName | sort count desc | head 10"},
    {"name": "operations", "program": "distinct operationName | head 20"}
  ]
}
```

Each named output has its own status and coverage. Batch analysis currently accepts bounded scalar/aggregate programs (`count`, `group`, `distinct` and bounded post-processing). Use `tracecite_run` when you need raw Evidence pointers or navigation.

A batch can fall back to canonical execution internally when scan fusion is unsafe. That is an execution detail; SourceVersion and result semantics stay the same.

## Evidence Shell

`tracecite_run` accepts familiar read-only Unix-like query spelling but never executes host bash. Common `grep`, `rg`, `head`, `tail`, `wc -l`, `sort`, `uniq`, selected `sed -n`, simple `jq`, and TraceCite-native stages are normalized into a controlled Record pipeline.

```text
Agent program
  -> fixed SessionSourceView / SourceVersion
  -> raw hit scan
  -> Segmenter restores complete logical Record
  -> filters/transforms/aggregates stay Runtime-side
  -> User/Host Evidence budget gate
  -> admitted Evidence pointers, bounded derived result, or too_broad
```

### Search/filter

```text
search TEXT
regex REGEX
grep TEXT
grep -i TEXT
grep -E REGEX
grep -F TEXT
grep -v TEXT
grep -c TEXT
grep -m N TEXT
rg REGEX
rg -i REGEX
rg -F TEXT
rg -v REGEX
rg -c REGEX
where FIELD == VALUE
where FIELD != VALUE
where FIELD > VALUE
where FIELD >= VALUE
where FIELD < VALUE
where FIELD <= VALUE
where FIELD contains VALUE
where FIELD startswith VALUE
where FIELD endswith VALUE
where FIELD matches REGEX
exists FIELD
missing FIELD
lines START [END]
```

`FIELD` may be a Segmenter/JSON field, dotted field, `timestamp`, `source`, `text`, `line`/`start_line`, or `end_line`.

### Select/transform

```text
sort FIELD [asc|desc] [numeric]
reverse
head N
tail N
take N
first N
last N
near LINE [BEFORE] [AFTER]
near line=LINE before=N after=N
seek LINE [BEFORE] [AFTER]
```

Familiar forms such as `head -30`, `head -n 30`, `sort -n`, `sort -nr`, and `sed -n '100,150p'` are accepted when mechanically equivalent.

### Aggregate / projection

```text
count
group FIELD
distinct FIELD
project FIELD
```

Aggregates may scan a large Runtime-internal set while returning a small result. `group FIELD` returns groups ordered by count by default. Aggregate output is still subject to Host transport policy.

Projection is terminal internally, but common Agent spelling is rewritten when equivalent. For example:

```text
project timestamp | sort timestamp asc numeric | head 3
jq -r '.timestamp' | sort -n | head -3
```

is executed as sort/select first and project last.

Simple jq filters include:

```text
jq 'select(.statusCode >= 500)'
jq 'select(.serviceName == "route")'
jq 'select(.message | test("503"))'
jq -r '.serviceName'
```

Complex jq/sed programs are intentionally not emulated.

### Compose work into one call

When the mechanical pipeline is already known, keep compatible steps in one call:

```text
grep -Ei 'panic|fatal|error|failed' | grep -i runtime | head -30
search statusCode | where statusCode >= 500 | group serviceName
search request_id=abc | near line=94771 before=3 after=5
```

A scalar count may scan an arbitrarily large Runtime-internal set while returning only the scalar. Familiar no-op spelling such as `grep -c PATTERN | head 5` is accepted as the same scalar count.

## Program errors

Unsupported read-only syntax returns a normal tool result:

```text
status = error
error_code = unsupported_program
error = <specific unsupported stage/reason>
data.supported_hint = <canonical alternatives>
```

Rewrite the unsupported stage using supported mechanical syntax. Do not interpret this as a malformed MCP parameter call and do not switch to native shell access for a TraceCite-only evidence source.

## Novelty / repeated Evidence

For a repeated-only match, expect a compact receipt such as:

```text
data.novelty.state = no_new_evidence
data.novelty.new_evidence = 0
data.novelty.repeated_evidence = N
data.novelty.matched_evidence = N
data.novelty.query_repeated = true|false
data.existing_evidence_summary.count = N
data.existing_evidence_summary.representative = [bounded pointers]
```

The representative pointer is orientation/recovery metadata, not proof that only those records matched. Use the exact count/coverage fields for mechanical scope. Previously seen Evidence remains recoverable through explicit materialize/replay.

`no_new_evidence` applies only to the current retrieval result. TraceCite does not decide what that means for a hypothesis or whether the investigation should continue.

## `too_broad`

A normal Evidence search has no hidden first-N candidate truncation. The complete final matched Record set either fits the Host policy or TraceCite returns `status=too_broad`, `evidence=[]`, and a mechanical reason/refinement requirement.

Make the requested output mechanically smaller with a narrower predicate/scope, a compact aggregate, or explicit selection. Do not change the Host budget.

## SourceVersion / materialize

The RetrievalSession is the stability boundary. First access binds one immutable SourceVersion for that logical source. Reuse the same session so later search/analyze/materialize/replay operate in the same evidence world.

Shell Evidence pointers may contain `ref`, `uri`, `start_line`, `end_line`, `sha256`, `materialize_source`, and a bounded `preview`. For exact reading/citation, materialize the selected range with its SHA when available.

The Agent does not control snapshot mode, Evidence budgets, source-mode policy, or materialize output ceilings.

## Evidence semantics

```text
no_match                  != impossible event
no_new_evidence           != investigation complete
query_repeated=true       -> exact query repetition fact
repeated_evidence>0       != new Evidence identity
coverage.complete         != causal chain complete
integrity verified        != causal conclusion verified
status=too_broad          != no evidence exists
projected/aggregate value != raw Evidence body
```

TraceCite reports mechanical facts. The Agent decides what they mean.
