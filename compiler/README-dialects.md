# The dialect seam

`compiler/compile.py` decides **what** to emit: which measures, at which base grain, which
joins are legal, which filters are certified, and when to refuse. That is the governance
logic and it is what the benchmark measures.

A **dialect** (`compiler/dialects.py`) decides **how** that gets spelled for a particular
warehouse. Nothing else changes. The point of the split is that the fan-out guarantee — one
subquery per measure at its own grain, combined on shared dimensions — is warehouse-neutral
and must never be re-implemented per backend, only re-rendered.

```
plan (JSON)  ──►  compile.py          ──►  SQL
                  (grain safety,          ▲
                   vocabulary,            │  Dialect: table_ref / expr /
                   refusals)              │  date_predicate / combine_measures
```

## The four hooks

Everything `compile.py` emits that is not pure structure goes through one of these. That is
the whole interface; a new warehouse means implementing at most four methods.

| Hook | Called from | What it decides |
|---|---|---|
| `table_ref(table)` | `_measure_subquery` (FROM), `_joins_for` (LEFT JOIN) | How a base table is named |
| `expr(sql)` | every SQL string that came from the semantic **model** — dimension `sql`, `agg_sql`, `filter_sql`, join `on_sql`, composite measure `expr` | Function and operator spelling |
| `date_predicate(dim_sql, op, iso)` | `_measure_subquery`, the `type: date` filter branch | How a calendar literal is typed against a date column |
| `combine_measures(left_alias, dims, sub_sql, alias)` | `compile_plan`, stitching per-measure subqueries | How the multi-measure join is written |

`compile_plan(model, plan, dialect=None)` and `run_plan(model, plan, con, dialect=None)`
take the dialect as an optional trailing argument — either a `Dialect` instance or a spec
string (`"duckdb"`, `"bigquery:<project>.<dataset>"`). Every existing caller passes two
positional arguments and therefore gets DuckDB, unchanged.

## DuckDB is the identity dialect

`DUCKDB` returns exactly the bytes the pre-dialect compiler produced. This is not a
best-effort claim; it is the acceptance test:

```
1190 stored condition-S plans (results/*.jsonl, all 12 run files, both datasets)
  1190 / 1190  compile_plan() output identical to the pre-refactor compiler
               (1040 byte-identical SQL, 150 identical refusal strings)
  1040 / 1040  executed on DuckDB: identical rows under both compilers
     0         mismatches
```

`compiler/accept_dialects.py` is that test. Re-run it after any change to this seam. It is
read-only, but run it in a scratch copy anyway so there is no chance of touching `results/`:

```sh
rsync -a --exclude .git --exclude __pycache__ <repo>/ /tmp/dialect-check/
git show <pre-refactor-ref>:compiler/compile.py > /tmp/dialect-check/compiler/compile_baseline.py
python /tmp/dialect-check/compiler/accept_dialects.py
python compiler/test_dialects.py     # translator edge cases the shipped models don't reach
```

One informational number in that report needs context: replayed rows match the rows stored
in `results/*.jsonl` as a **multiset** 1040/1040, but in the same **order** only ~845/1040.
Row order out of a `FULL OUTER JOIN` is not deterministic in DuckDB. That is pre-existing
and independent of this seam — it reproduces identically under the baseline compiler.

### One deliberate departure from byte-identity: the multi-measure dimension

The identity above describes the SEAM. A later correctness fix to `compile.py` — unrelated
to dialects — does change the emitted bytes, in exactly 72 of the 1040 executable
statements, and `accept_dialects.py` will report those 72 as `compile_MISMATCH` against a
pre-refactor baseline. That is expected, not a regression:

Measure subqueries do not share a domain. Each is aggregated at its own base grain under
its own certified filter, so a group can be present in `m1` and absent from `m0`. The
compiler used to read the output dimension off `m0` alone and to join every later subquery
back to `m0` alone. With two measures that emitted `NULL` in place of the label for any
group `m0` did not produce; with three or more it split such a group into one row per
measure. Both are now fixed by `COALESCE`ing the dimension — and the join key — across
every subquery already in the `FROM` clause (`dialects.dim_ref`).

The change is confined to the SELECT-list dimension and, for three or more measures, the
`ON` predicate. Verified on the stored plans:

```
72 / 1190   statements whose SQL text changed (the 4 qids that request >=2 measures
            WITH a dimension: s2_rev_and_ship, s3_refund_rev_by_cat, s5_ship_pct_region,
            conv_grain_drift_t3)
72 / 72     return an IDENTICAL result multiset before and after
 0          changed outcomes, 0 changed values, 0 new refusals
```

`accept_dialects.py`'s per-statement execution check compares row lists in order, so those
72 also show up as `exec_MISMATCH`; that is the same `FULL OUTER JOIN` ordering noise
described above (two different SQL strings are two separate DuckDB executions). Compared
as multisets they are identical.

## BigQuery

`BigQueryDialect(project, dataset, column_types=None)`. Four differences, every one of them
forced by BigQuery being stricter than DuckDB.

**1. Qualified table names.** `orders` becomes ``` `project.dataset.orders` AS orders ```.
The explicit alias is what keeps the model's `orders.order_id` references resolving.
BigQuery's implicit alias for a qualified path is the last identifier anyway, so the alias
is belt-and-braces — but it costs nothing and removes a dependency on that rule.

**2. The cartesian measure join — NOT rewritten.** With no dimensions, `compile.py` joins
measure subqueries with `FULL OUTER JOIN (…) m1 ON TRUE`. An earlier draft of this dialect
rewrote that to `CROSS JOIN`, believing BigQuery rejects a non-equality outer-join
predicate. **It does not.** BigQuery's restriction applies to predicates that reference
both sides non-equally; a constant `TRUE` references neither, and the statement runs. That
was checked directly against `joon-sandbox`:

```sql
SELECT m0.a AS a, m1.b AS b
FROM (SELECT SUM(1) AS a FROM `joon-sandbox.semantic_bench_d1.orders` AS orders) m0
FULL OUTER JOIN (SELECT SUM(2) AS b FROM `joon-sandbox.semantic_bench_d1.orders` AS orders) m1
  ON TRUE          -- returns (50000, 100000)
```

The rewrite has been removed. It was an *unforced* divergence: it changed the join
structure of every scalar multi-measure query (`aov`, `shipping_pct_of_revenue`,
`net_revenue_after_refunds`, `advneg_attainment_lift`) — the exact queries the
cross-backend comparison most needs to be structurally comparable. **Both arms now emit
the same join structure**; only the spelling of leaves differs.

**3. Date expressions in the model.** The truncations live in `semantic_models/d1.yaml`,
not in the compiler, so the dialect translates them on the way out. `d1.yaml` is untouched
— the DuckDB arm still needs its expressions verbatim.

| `d1.yaml` (DuckDB) | BigQuery | Result type |
|---|---|---|
| `date_trunc('month', orders.order_ts)` | `TIMESTAMP_TRUNC(orders.order_ts, MONTH)` | TIMESTAMP |
| `date_trunc('year', orders.order_ts)` | `TIMESTAMP_TRUNC(orders.order_ts, YEAR)` | TIMESTAMP |
| `date_trunc('year', orders.order_ts + INTERVAL 11 MONTH)` | `DATE_TRUNC(DATE_ADD(DATE(orders.order_ts), INTERVAL 11 MONTH), YEAR)` | DATE |

The fiscal-year case is the interesting one: **BigQuery cannot add a month-or-larger
INTERVAL to a TIMESTAMP at all.** The value has to go through `DATE()` first, which is why
that column comes out DATE-typed while the other two stay TIMESTAMP. Sub-day intervals do
not have this problem and stay on TIMESTAMP (`TIMESTAMP_ADD`), preserving time-of-day.

`DATE(timestamp)` interprets the timestamp in UTC. The warehouse stores naive local
timestamps loaded as UTC, so the civil date is unchanged — but if this ever runs against
timestamps with a real zone offset, pass the zone explicitly.

**4. Typed calendar literals.** DuckDB coerces TIMESTAMP↔DATE implicitly, so the old
compiler could always emit `DATE '2024-05-01'`. BigQuery does not coerce, and (3) leaves the
date dimensions with *mixed* types, so the literal is typed per column:

```sql
-- order_month / order_year
TIMESTAMP_TRUNC(orders.order_ts, MONTH) = TIMESTAMP '2024-05-01'
-- fiscal_year
DATE_TRUNC(DATE_ADD(DATE(orders.order_ts), INTERVAL 11 MONTH), YEAR) = DATE '2024-01-01'
```

This is why `date_predicate` receives the **raw** model expression rather than an
already-translated string: the translator knows the type of what it just produced, and
handing it the raw expression keeps that knowledge in one place instead of in a lookup
table that could drift.

### How the translation works

Not a SQL parser and not a regex pass over finished SQL — a small quote- and paren-aware
scanner (`_match_paren`, `_split_args`, `_find_keyword`) that recognises exactly two
constructs, `date_trunc(...)` and `± INTERVAL n UNIT`, and recurses through them. Anything
else passes through untouched, which is correct because the rest of what the shipped models
contain (`CASE`, `NULLIF`, `COUNT(DISTINCT …)`, `SUM`, `AVG`, `LOWER`, `REPLACE`, the d2
email-normalisation join predicate) is already valid GoogleSQL.

### Untranslatable input fails loudly

After translation the output is checked against a deny-list of DuckDB-isms (`::` casts,
`strftime`, `date_part`, DuckDB-argument-order `date_trunc`/`date_diff`, `ILIKE`, `~~`,
`list_*()`, `regexp_matches`, and any surviving `INTERVAL` used as an operand). The check
masks string literals first, so a *value* that happens to look like a call is left alone.

A hit raises **`DialectError`**, and `compile_plan` explicitly re-raises it rather than
folding it into the generic `except Exception → {"refuse": ...}` handler:

> A refusal is a governance decision about the **question**. A `DialectError` is a gap in
> our coverage of the **warehouse**. If a dialect gap were returned as a refusal it would be
> scored as the semantic layer correctly declining to answer — the benchmark's headline
> result would then be partly measuring our own translation gaps. It must crash instead.

The DuckDB arm cannot raise `DialectError` (the identity dialect never inspects anything),
so this changes nothing about the shipped numbers.

### Status of the BigQuery arm — executed and measured

**The generated BigQuery SQL has been executed.** All 1190 stored condition-S plans were
replayed through this dialect against `joon-sandbox.semantic_bench_{d1,d2}` and compared
run-for-run with the DuckDB arm: **0 divergent, 0 refused-by-one, 0 error-by-one**, and no
`DialectError` on any plan. The matrix, its triage and — more usefully — its caveats are in
`results/AGREEMENT-duckdb-vs-bq.md`. Two findings from that run belong here:

- The `CROSS JOIN` rewrite described above was **wrong and has been removed** (see item 2).
- The two arms are structurally identical, not merely value-equal: for all 160 distinct
  (dataset, plan) pairs, mechanically de-dialecting the BigQuery SQL reproduces the DuckDB
  SQL **exactly**, with 0 structural residual.

Remaining limits:

- A bare column handed to `date_trunc()` is assumed TIMESTAMP (true of this warehouse). If
  a model ever truncates a real DATE column, pass
  `column_types={"orders.order_date": "DATE"}` — the dialect then emits `DATE_TRUNC` and a
  `DATE` literal for it.
- **`fiscal_year` has a different TYPE in the two arms** — DATE on BigQuery, TIMESTAMP on
  DuckDB — because BigQuery cannot add a month-or-larger interval to a TIMESTAMP and the
  value must route through `DATE()`. Harmless today only because no logged plan puts
  `fiscal_year` in a `SELECT` list; it appears exclusively in `WHERE`. A question that
  groups by fiscal year would surface it.
- Neither warehouse has a NUMERIC/BIGNUMERIC column, so the anticipated `Decimal`-vs-`float`
  problem never materialised. The agreement report still canonicalises for it.
- The two engines' `SUM` over the same doubles differs in the last bits (worst observed
  relative gap 1.74e-14). That is IEEE-754 associativity, not a dialect concern, and a
  backend must not round it away.
- **This dialect is not an independent oracle.** Both arms run the same `compile.py`; only
  the ~120 lines of `BigQueryDialect` differ. A bug in the grain logic or the certified
  filters is present identically in both and agrees perfectly with itself.

## Adding a dialect

Subclass `Dialect`, override only the hooks that differ, register it in `get_dialect`. If
the new warehouse needs a construct the models do not yet express, add the rule to that
dialect's translator and a case to `compiler/test_dialects.py` — do **not** add a
dialect-specific expression to a `semantic_models/*.yaml`, because the models are shared
across arms and the DuckDB expressions are load-bearing for every committed result.

## Wiring a backend

`harness/replay_s.py:BigQueryBackend` is wired and executed. Its compile step is the one
line this seam exists to make possible:

```python
comp = C.compile_plan(semantic_model, plan,
                      BigQueryDialect(self.project, self.dataset_map[semantic_model["dataset"]]))
```

Everything else in that backend is execution plumbing, plus two things a second warehouse
forces you to be explicit about:

- **`DialectError` is caught and reported as `outcome="error"` with a `dialect_gap:`
  prefix, never as a refusal.** A refusal is a governance decision about the question; a
  dialect gap is a hole in our coverage of the warehouse. Folding one into the other would
  let a translation failure be scored as the semantic layer correctly declining.
- **UTC is asserted at connect time**, not assumed. `TIMESTAMP_TRUNC` and `DATE(timestamp)`
  default to UTC, which is what makes this arm comparable to DuckDB's naive timestamps — but
  a wrong zone raises nothing, it just moves boundary rows into the neighbouring month. One
  probe query at startup (`_verify_utc`) turns that silent failure into a loud one.

The Looker backend remains a stub, and it is the one that would actually test the compiler
rather than the dialect.
