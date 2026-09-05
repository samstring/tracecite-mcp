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

## Evidence source names

For `source`, use either:

- an exact Host-allowed path returned by TraceCite; or
- a unique relative logical name such as `app.log` when that name resolves to exactly one Host-authorized evidence file.

Do not spend investigation turns discovering container-specific absolute paths. TraceCite resolves a unique logical name inside the Host evidence roots/inventory. If a logical name is missing or ambiguous, use the structured source error / `available_sources` to select an exact allowed path.

## Evidence Shell

`tracecite_run` accepts familiar read-only Unix-like data-query spelling, but it does **not** execute arbitrary host bash. Common `grep`, `rg`, `head`, `tail`, `wc -l`, `sort`, `uniq`, selected `sed -n`, and simple `jq` forms are normalized into TraceCite's controlled Record pipeline, so the same SourceVersion, logical-Record, provenance, novelty and Evidence-budget rules always apply.

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
complete admitted pointer set OR bounded derived result OR status=too_broad
```

Commands are pipe-composable with `|` when the mapped TraceCite stage is composable. Aggregate/projection stages remain terminal.

### Familiar grep / rg syntax

Common `grep` forms are accepted, including combined short flags:

```text
grep TEXT
grep -i TEXT
grep -E REGEX
grep -F TEXT
grep -v TEXT
grep -c TEXT
grep -Ei REGEX
grep -ic TEXT
grep -n TEXT
grep -e PATTERN
grep -m N PATTERN
grep --ignore-case TEXT
grep --extended-regexp REGEX
grep --fixed-strings TEXT
grep --invert-match TEXT
grep --count TEXT
grep --max-count N PATTERN
```

Default `grep` follows the common basic-regex expectation, so escaped alternation such as `grep 'error\|failed'` works. Use `-E` for extended regex and `-F` when regex metacharacters must stay literal.

`rg` uses regex semantics by default and supports the common investigation flags below:

```text
rg REGEX
rg -i REGEX
rg -F TEXT
rg -v REGEX
rg -c REGEX
rg -n REGEX
rg -e REGEX
rg -m N REGEX
```

For both commands, `-c` becomes a Runtime-side count aggregate. `-m N` intentionally selects the first N matches and changes completeness semantics.

### Familiar count / selection / transform syntax

```text
head 30
head -30
head -n 30
tail 30
tail -30
tail -n 30
wc -l
wc --lines
sort
sort -r
sort -n
sort -nr
sort -rn
uniq
uniq -c
sed -n '100p'
sed -n '100,150p'
```

Unix-style `sort` without a field sorts complete Record text. Numeric mode is intentionally limited to numeric Record text; for structured values prefer native `sort FIELD [asc|desc] [numeric]`.

`uniq` maps to distinct complete Record text and `uniq -c` maps to grouped Record-text counts. Because TraceCite aggregates are terminal, do not append another stage after `uniq`/`uniq -c`; use native `group FIELD` when structured grouping is clearer.

`sed` compatibility is intentionally limited to read-only line selection. Other sed scripts are not executed.

### Simple jq compatibility

Simple structured filtering/projection can use familiar jq spelling:

```text
jq 'select(.statusCode >= 500)'
jq 'select(.serviceName == "route")'
jq -r '.serviceName'
jq 'select(.statusCode >= 500) | .serviceName'
```

Supported `select` comparisons are `==`, `!=`, `>`, `>=`, `<`, and `<=` on dotted fields. A field projection maps to terminal `project FIELD`; it returns a bounded derived projection with source/SHA/line provenance for each row, not raw Evidence bodies. Complex jq programs are intentionally not emulated.

### TraceCite-native search/filter

```text
all
search TEXT
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

`FIELD` can be a Segmenter/JSON field, dotted nested field, `timestamp`, `source`, `text`, `line`/`start_line`, or `end_line`.

### Transform/select

```text
sort FIELD [asc|desc] [numeric]
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

### Aggregate / derived projection

```text
count
group FIELD
distinct FIELD
uniq FIELD
project FIELD
```

Prefer aggregate stages when the intermediate match set is large but the fact needed is small. `project FIELD` is terminal and returns derived values plus provenance. It does not turn transformed values into raw Evidence.

### Compose work into one call

Prefer one pipeline when you already know the mechanical narrowing steps. Do not repeatedly search, inspect a count, and then issue another equivalent search when the same operations can stay Runtime-side.

```text
grep -Ei 'panic|fatal|error|failed' | grep -i 'runtime' | head -30
```

```text
rg -i 'panic|fatal|error|failed' | wc -l
```

```text
search 'statusCode' | where statusCode >= 500 | where serviceName == ts-route-service
```

```text
search 'statusCode' | where statusCode >= 500 | group serviceName
```

```text
search 'request_id=abc' | near line=94771 before=3 after=5
```

Time/format scope can be passed to `tracecite_run` with `last`, `since`, `until`, and `segmenter`.

If a familiar Unix option is not supported, use the error to rewrite that stage with `search`, `regex`, `where`, `count`, `group`, `project`, `head` or another documented TraceCite stage. Do not switch to native shell access for a TraceCite-only evidence file.

## `too_broad`

A normal Evidence Shell search has no hidden candidate-count truncation. The complete final matched Record set either fits the configured policy or TraceCite returns:

```text
status = too_broad
coverage.too_broad = true
data.reason = MATCHED_EVIDENCE_BUDGET_EXCEEDED
data.refine_query = true
evidence = []
```

An aggregate or derived projection can similarly exceed its own transport budget.

When this happens, refine by adding more selective literals/regex/field predicates, narrowing time or line scope, or changing the question to a compact aggregate. Do not change the budget.

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

Materialized raw text is Evidence. An unmaterialized preview/pointer or projected value is a navigation/derived result, not surrounding raw context you have already inspected.

## Compatibility surfaces

`tracecite_retrieve` remains for source/provider operations and old clients. A query target is internally translated to Evidence Shell and must not contain `snapshot`, `max_evidence`, `max_line_chars`, or `fold`.

`tracecite_aggregate` is legacy count compatibility and requires `session_id`. For new group/distinct/count work, use `tracecite_run` so the operation is bound to the same SessionSourceView.

## Missing source recovery

If a tool returns `error_code=source_not_found` with `available_sources`, select an appropriate Host-allowed path from that inventory. Do not guess paths outside the allowlist or scan the host filesystem.

## Evidence semantics

```text
no_match                  != impossible event
new_evidence=0            != investigation complete
repeated_evidence>0       != useless evidence
coverage.complete         != causal chain complete
integrity verified        != causal conclusion verified
status=too_broad          != no evidence exists
projected/aggregate value != raw Evidence body
```

TraceCite reports mechanical facts. The Agent decides what they mean.

## Extensions

Installed TraceCite extensions may expose dynamic capability tools. Read each tool description and declared schema. Never invent Host authorization/safety grants or bypass a denied capability. Live actions should only be used when the task explicitly requires that side effect.
