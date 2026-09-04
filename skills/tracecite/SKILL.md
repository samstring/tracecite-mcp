---
name: tracecite
description: Use TraceCite MCP as a session-stable Evidence Runtime. Prefer one Evidence Shell program for mechanical search/filter/aggregate work, refine too-broad results, then materialize exact immutable evidence. The Agent owns hypotheses, causal reasoning, sufficiency and stopping.
---

# TraceCite MCP Agent Skill

TraceCite is an Evidence Runtime, not a planner or root-cause oracle. The Agent owns investigation strategy and conclusions. TraceCite owns mechanical retrieval, one immutable SourceVersion per RetrievalSession/source, provenance, novelty, coverage, Evidence transport policy and exact materialization.

## Core rules

1. Reuse one `session_id` for the entire conversation/investigation.
2. For text evidence, prefer `tracecite_run` over multiple `tracecite_retrieve`/aggregate calls.
3. Put all mechanical narrowing that can be decided in advance into one pipe-composed Evidence Shell program. Intermediate rows remain inside Runtime and do not enter model context.
4. Evidence token/byte limits are User/Host policy. They are not Agent parameters.
5. If TraceCite returns `status=too_broad`, change the search method. Never ask to increase a budget, invent a larger limit, request a complete locator dump, or treat arbitrary first-N truncation as a complete search.
6. After the final candidate set is small, materialize only the few records needed for reasoning/citation.
7. Repeated Evidence may be returned only as lightweight identities. `no_new_evidence` means no new Evidence identity was exposed, not that a hypothesis is proven or the investigation is complete.
8. Do not use native grep/read on a TraceCite-only evidence source.

## Preferred tools

| Need | Tool |
| --- | --- |
| Search/filter/aggregate/navigate text evidence | `tracecite_run` |
| Exact context for selected EvidencePointer | `tracecite_materialize` |
| Intentional reread of covered immutable evidence | `tracecite_replay` |
| Legacy query/source/provider compatibility | `tracecite_retrieve` |
| Legacy count compatibility | `tracecite_aggregate` |
| Provider/entity traversal | `tracecite_traverse` |
| Manifest/integrity check | `tracecite_verify` |

Installed extensions may add domain tools such as mobile capabilities. Those are explicit Core capabilities, not Evidence Shell commands.

## Evidence Shell

`tracecite_run` executes a controlled read-only evidence program, not arbitrary bash.

```text
Agent program
    ↓
fixed SessionSourceView / SourceVersion
    ↓
raw search hit
    ↓
Segmenter restores complete logical Record
    ↓
search/filter/aggregate/navigation stages remain Runtime-side
    ↓
User/Host Evidence budget gate
    ↓
complete admitted pointer set OR status=too_broad
```

Commands are pipe-composable with `|`.

### Search/filter

```text
all
search TEXT
grep TEXT
grep -F TEXT
grep -E REGEX
grep -i TEXT
grep -v TEXT
regex REGEX
exclude TEXT
exclude-regex REGEX
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

`FIELD` can be a Segmenter/JSON field, dotted nested field, `timestamp`, `source`, `line`/`start_line`, or `end_line`.

### Transform/select

```text
sort FIELD [asc|desc]
reverse
take N
head N
first N
last N
tail N
near LINE [BEFORE] [AFTER]
near line=LINE before=N after=N
seek LINE [BEFORE] [AFTER]
```

`take/head/first/last/tail` intentionally change query semantics. Do not add them merely to bypass `too_broad` unless a subset is actually the question being asked.

### Aggregate

```text
count
group FIELD
distinct FIELD
uniq FIELD
```

Prefer aggregate stages when the intermediate match set is large but the fact needed is small.

### Examples

```text
search 'statusCode' | where statusCode >= 500 | where serviceName == ts-route-service
```

```text
regex 'panic|fatal|error|failed' | search 'ts-route-service'
```

```text
search 'statusCode' | where statusCode >= 500 | group serviceName
```

```text
search 'request_id=abc' | near line=94771 before=3 after=5
```

Time/format scope can be passed to `tracecite_run` with `last`, `since`, `until`, and `segmenter`.

## `too_broad`

A normal Evidence Shell search has no hidden candidate-count truncation. The complete final matched Record set either fits the configured policy or TraceCite returns:

```text
status = too_broad
coverage.too_broad = true
data.reason = MATCHED_EVIDENCE_BUDGET_EXCEEDED
data.refine_query = true
evidence = []
```

An aggregate can similarly exceed its own transport budget.

When this happens, refine by adding more selective literals/regex/field predicates, narrowing time or line scope, or changing the question to an aggregate. Do not change the budget.

## SourceVersion / session stability

The RetrievalSession is the stability boundary. On first access to a logical source, TraceCite binds one immutable SourceVersion for that `session_id`.

For the rest of that session:

- mutable/live source changes do not silently refresh the version;
- snapshot/live cut/SHA work is not repeated for every Agent search;
- every `tracecite_run`, materialize and replay operates in the same stable evidence world.

A new RetrievalSession may reuse an already verified version if the source fingerprint is unchanged, or bind a new version if it changed.

The Agent does not control `snapshot`, `max_evidence`, `max_line_chars`, source mode, live cut policy, Evidence token budget, or Evidence byte budget. Do not pass those fields to compatibility query retrieval.

## Materialize

Each shell Evidence row may contain:

- `ref`: logical caller-visible source/line reference;
- `uri`: stable Evidence identity;
- `start_line` / `end_line`;
- `sha256`;
- `materialize_source`: exact immutable snapshot/segment path to use for exact recovery;
- `preview`: bounded orientation text.

For final reasoning/citation, call `tracecite_materialize` with the row's `materialize_source`, exact line/range and SHA when available. The Agent may choose `before`/`after`, but the maximum returned Evidence size remains a User/Host limit and is not an Agent argument.

Materialized raw text is Evidence. An unmaterialized preview/pointer is a navigation candidate, not surrounding context you have already inspected.

## Compatibility surfaces

`tracecite_retrieve` remains for source/provider operations and old clients. A query target is internally translated to Evidence Shell and must not contain `snapshot`, `max_evidence`, `max_line_chars`, or `fold`.

`tracecite_aggregate` is legacy count compatibility and requires `session_id`. For new group/distinct/count work, use `tracecite_run` so the operation is bound to the same SessionSourceView.

## Missing source recovery

If a tool returns `error_code=source_not_found` with `available_sources`, select an appropriate Host-allowed path from that inventory. Do not guess filesystem paths or scan outside the allowlist.

## Evidence semantics

```text
no_match                  != impossible event
new_evidence=0            != investigation complete
repeated_evidence>0       != useless evidence
coverage.complete         != causal chain complete
integrity verified        != causal conclusion verified
status=too_broad          != no evidence exists
```

TraceCite reports mechanical facts. The Agent decides what they mean.

## Extensions

Installed TraceCite extensions may expose dynamic capability tools. Read each tool description and declared schema. Never invent Host authorization/safety grants or bypass a denied capability. Live actions should only be used when the task explicitly requires that side effect.
