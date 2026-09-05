---
name: tracecite
description: Use TraceCite MCP as a session-stable Evidence Runtime. Prefer one Evidence Shell program for mechanical search/filter/aggregate work, refine too-broad results, then materialize exact immutable evidence. The Agent owns hypotheses, causal reasoning, sufficiency and stopping.
---

# TraceCite MCP Agent Skill

TraceCite is an Evidence Runtime, not a planner or root-cause oracle. The Agent owns investigation strategy and conclusions. TraceCite owns mechanical retrieval, one immutable SourceVersion per RetrievalSession/source, provenance, novelty, coverage, Evidence transport policy and exact materialization.

## Core rules

1. Reuse one `session_id` for the whole investigation.
2. For text evidence, prefer `tracecite_run`.
3. Put mechanical narrowing/aggregation that is already known into one pipe-composed program. Intermediate rows remain Runtime-side.
4. Evidence token/byte limits are User/Host policy, never Agent parameters.
5. If `status=too_broad`, make the query more selective or ask for a compact aggregate. Never enlarge the budget or use arbitrary first-N as a fake complete search.
6. Materialize only the few exact records needed for reasoning/citation.
7. `no_new_evidence` means the current query exposed no new Evidence identity. It does not prove a hypothesis or end the whole investigation.
8. When `novelty.query_repeated=true`, do not issue the same query again.
9. When all matches were previously seen, TraceCite returns an exact repeated count plus at most two representative receipts. Old Evidence remains recoverable with `tracecite_materialize`/`tracecite_replay`; do not request a complete repeated-locator dump.
10. If the evidence already establishes the root component and causal chain but the remaining lower-level mechanism is not observable in the supplied telemetry, state that evidence boundary and answer. Do not keep issuing equivalent searches merely to force a more specific conclusion.
11. Before promoting an error, warning, configuration defect, or resource anomaly to the incident root cause, test temporal contrast. Check whether the same signal is present during a clearly healthy period before the incident and whether it persists after recovery. A signal that is materially unchanged across healthy and faulty periods is background evidence unless another observation shows an incident-correlated change or causal mechanism.
12. Do not use native grep/read on a TraceCite-only evidence source.

## Preferred tools

| Need | Tool |
| --- | --- |
| Search/filter/aggregate/navigate text | `tracecite_run` |
| Exact context for a selected pointer | `tracecite_materialize` |
| Intentional reread of covered immutable evidence | `tracecite_replay` |
| Legacy source/provider compatibility | `tracecite_retrieve` |
| Legacy count compatibility | `tracecite_aggregate` |
| Provider/entity traversal | `tracecite_traverse` |
| Integrity/manifest check | `tracecite_verify` |

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

Prefer aggregates when a large internal match set can answer the question with a small result. `group FIELD` already returns groups ordered by count, so do not split a simple service/error distribution into many separate searches.

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

Prefer:

```text
grep -Ei 'panic|fatal|error|failed' | grep -i runtime | head -30
search statusCode | where statusCode >= 500 | group serviceName
search request_id=abc | near line=94771 before=3 after=5
```

instead of repeatedly issuing equivalent broad searches and inspecting each result separately.

A scalar count may scan an arbitrarily large Runtime-internal set while returning only the scalar. Familiar no-op spelling such as `grep -c PATTERN | head 5` is accepted as the same scalar count.

## Causal contrast before attribution

Finding a severe-looking message is not enough to call it the root cause. Before promoting a recurring signal, compare at least one healthy period against the incident period when the data permits it.

Useful checks include:

```text
# Is the candidate signal already present before the incident?
search CANDIDATE | sort timestamp asc | head 3

# Does it remain after the service has recovered?
search CANDIDATE | sort timestamp desc | head 3

# Did frequency/severity materially change near the incident?
search CANDIDATE | group container_name
```

If the same warning/configuration defect occurs while the service is demonstrably healthy before and after the outage, treat it as a background defect unless there is separate evidence that its state, frequency, severity, or causal effect changed at the incident. Prefer a narrower evidence-boundary statement over attaching the incident to an attractive but non-discriminating error message.

## Program errors

Unsupported read-only syntax returns a normal tool result:

```text
status = error
error_code = unsupported_program
error = <specific unsupported stage/reason>
data.supported_hint = <canonical alternatives>
```

Rewrite the unsupported stage once using `search`, `regex`, `where`, `sort`, `count`, `group`, `distinct`, `project`, or explicit selection. Do not interpret this as a malformed MCP parameter call and do not switch to native shell access for TraceCite-only evidence.

## Novelty / repeated Evidence

For a repeated-only match, expect a compact receipt such as:

```text
data.novelty.state = no_new_evidence
data.novelty.new_evidence = 0
data.novelty.repeated_evidence = N
data.novelty.matched_evidence = N
data.novelty.query_repeated = true|false
data.existing_evidence_summary.count = N
data.existing_evidence_summary.representative = [at most two pointers]
```

The representative pointer is orientation/recovery metadata, not proof that only those two records matched. Use the exact count for coverage. If another look at old evidence is genuinely needed, materialize/replay a known pointer instead of asking TraceCite to resend every repeated locator.

`no_new_evidence` applies to the current query direction only. A genuinely different hypothesis may justify a different query. Repeating equivalent queries does not.

## `too_broad`

A normal Evidence search has no hidden first-N candidate truncation. The complete final matched Record set either fits the Host policy or TraceCite returns `status=too_broad`, `evidence=[]`, and `data.refine_query=true`.

Refine with a more selective literal/regex, field predicate, time/line scope, or compact aggregate. Do not change the budget.

## SourceVersion / materialize

The RetrievalSession is the stability boundary. First access binds one immutable SourceVersion for that logical source. Reuse the same session so later search/materialize/replay operate in the same evidence world.

Shell Evidence pointers may contain `ref`, `uri`, `start_line`, `end_line`, `sha256`, `materialize_source`, and a bounded `preview`. For final reasoning/citation, materialize the exact selected range with its SHA when available.

The Agent does not control snapshot mode, Evidence budgets, source-mode policy, or materialize output ceilings.

## Evidence semantics

```text
no_match                  != impossible event
no_new_evidence           != investigation complete
query_repeated=true       -> do not repeat that query
repeated_evidence>0       != new information
coverage.complete         != causal chain complete
integrity verified        != causal conclusion verified
status=too_broad          != no evidence exists
projected/aggregate value != raw Evidence body
healthy-before-and-after  -> candidate signal is non-discriminating unless another causal change is shown
```

TraceCite reports mechanical facts. The Agent decides what they mean, and must keep conclusion precision within the precision supported by the evidence.