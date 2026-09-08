# Cross-backend agreement — DuckDB vs BigQuery (dialect control arm)

Every condition-S plan already logged in `results/runs_*.jsonl` was re-executed
against BigQuery through the same compiler and the same semantic models, and compared
run-for-run against the DuckDB arm. No model was called: the plans are frozen, and the
only thing that changes underneath them is the warehouse.

**Headline: 1190/1190 pairs agree (100.00%). 0 divergent, 0 refused-by-one, 0 error-by-one.**

That number is worth less than it looks until you know what it is counting, so the
rest of this document is mostly about what it does *not* establish.

---

## 1. What was run

| | |
|---|---|
| Repo state | `12786a6` on `bigquery-semantic-layers` (working tree, wave-1 changes unstaged) |
| Compiler | `compiler/compile.py` sha256:3425db936fb3 |
| Dialects | `compiler/dialects.py` sha256:a78527734c10 |
| Harness | `harness/replay_s.py` sha256:beedc3e46297 |
| Semantic models | `d1.yaml` sha256:d81e3da7fb62, `d2.yaml` sha256:d3cc47e7c2b3 |
| Arm A | `results/replay_duckdb.jsonl` — compiler/compile.py + DuckDB dialect -> `warehouse/{d1,d2}.duckdb` |
| Arm B | `results/replay_bq.jsonl` — compiler/compile.py + BigQueryDialect -> `joon-sandbox.{semantic_bench_d1,semantic_bench_d2}` |
| Condition-S rows replayed | 1190 (all of them; 1040 executed, 150 refused before touching a warehouse) |
| Distinct query plans behind them | 160 |
| Distinct BigQuery statements executed | 54 |

Both arms were produced back-to-back with the compiler hashes checked before and after,
so they are provably the same compiler. `results/runs_*.jsonl` was not modified.

---

## 2. The matrix

### Overall

| class | pairs | share |
|---|---:|---:|
| identical | 206 | 17.31% |
| within_tol | 834 | 70.08% |
| divergent | 0 | 0.00% |
| refused_by_one | 0 | 0.00% |
| error_by_one | 0 | 0.00% |
| both_refused | 150 | 12.61% |
| both_error | 0 | 0.00% |
| missing_in_one | 0 | 0.00% |
| **total** | **1190** | **100.00%** |

### By dataset

| dataset | pairs | identical | within_tol | divergent | refused_by_one | error_by_one | both_refused |
|---|---:|---:|---:|---:|---:|---:|---:|
| d1 | 959 | 206 | 648 | 0 | 0 | 0 | 105 |
| d2 | 231 | 0 | 186 | 0 | 0 | 0 | 45 |

### By question

`verdict` is the most severe class the question contains.

| qid | pairs | identical | within_tol | divergent | refused_by_one | error_by_one | both_refused | verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `s1_netrev` | 29 | 0 | 29 | 0 | 0 | 0 | 0 | within_tol |
| `s1_netrev_p2` | 29 | 0 | 29 | 0 | 0 | 0 | 0 | within_tol |
| `s1_netrev_p3` | 29 | 0 | 29 | 0 | 0 | 0 | 0 | within_tol |
| `s1_aov` | 29 | 0 | 29 | 0 | 0 | 0 | 0 | within_tol |
| `s1_aov_p2` | 29 | 0 | 29 | 0 | 0 | 0 | 0 | within_tol |
| `s1_aov_p3` | 29 | 0 | 29 | 0 | 0 | 0 | 0 | within_tol |
| `s1_margin` | 29 | 0 | 29 | 0 | 0 | 0 | 0 | within_tol |
| `s1_active_cust` | 29 | 29 | 0 | 0 | 0 | 0 | 0 | identical |
| `s1_active_p2` | 29 | 29 | 0 | 0 | 0 | 0 | 0 | identical |
| `s1_active_p3` | 29 | 29 | 0 | 0 | 0 | 0 | 0 | identical |
| `s1_gross_rev` | 24 | 0 | 24 | 0 | 0 | 0 | 0 | within_tol |
| `s1_orders` | 24 | 24 | 0 | 0 | 0 | 0 | 0 | identical |
| `s1_top_customer` | 24 | 0 | 24 | 0 | 0 | 0 | 0 | within_tol |
| `s2_shipping_total` | 24 | 5 | 19 | 0 | 0 | 0 | 0 | within_tol |
| `s2_shipping_region` | 24 | 0 | 24 | 0 | 0 | 0 | 0 | within_tol |
| `s2_rev_and_ship` | 24 | 0 | 24 | 0 | 0 | 0 | 0 | within_tol |
| `s2_lines` | 24 | 24 | 0 | 0 | 0 | 0 | 0 | identical |
| `s2_ship_pct` | 21 | 0 | 16 | 0 | 0 | 0 | 5 | both_refused |
| `s2_avg_line_disc` | 21 | 0 | 16 | 0 | 0 | 0 | 5 | both_refused |
| `s3_refund_total` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s3_refund_by_cat` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s3_refund_units` | 21 | 21 | 0 | 0 | 0 | 0 | 0 | identical |
| `s3_net_of_refunds` | 21 | 0 | 16 | 0 | 0 | 0 | 5 | both_refused |
| `s3_refund_rev_by_cat` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s5_ship_pct_region` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s7_vocab_paidsearch` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s7_vocab_paidsearch_orders` | 21 | 21 | 0 | 0 | 0 | 0 | 0 | identical |
| `s7_unans_age` | 21 | 0 | 0 | 0 | 0 | 0 | 21 | both_refused |
| `s7_unans_supplier` | 21 | 0 | 0 | 0 | 0 | 0 | 21 | both_refused |
| `s7_unans_weather` | 21 | 0 | 0 | 0 | 0 | 0 | 21 | both_refused |
| `s7_ambiguous_sales` | 21 | 12 | 0 | 0 | 0 | 0 | 9 | both_refused |
| `s7_ambiguous_best` | 21 | 0 | 6 | 0 | 0 | 0 | 15 | both_refused |
| `s8_rev_2024` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s8_rev_fy2024` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s8_rev_by_month` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s8_rev_2023` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s4_attain_by_region` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s4_revenue_by_region` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s4_attain_advneg` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s4_attain_no_advneg` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s4_attain_by_advneg` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s4_assess_emea` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s4_attain_emea` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s4_attain_by_distract` | 21 | 0 | 21 | 0 | 0 | 0 | 0 | within_tol |
| `s5_advneg_lift` | 21 | 0 | 18 | 0 | 0 | 0 | 3 | both_refused |
| `s4_unans_manager` | 21 | 0 | 0 | 0 | 0 | 0 | 21 | both_refused |
| `s4_unans_age` | 21 | 0 | 0 | 0 | 0 | 0 | 21 | both_refused |
| `dd_top_customer` | 12 | 0 | 12 | 0 | 0 | 0 | 0 | within_tol |
| `dd_paidsearch` | 12 | 0 | 12 | 0 | 0 | 0 | 0 | within_tol |
| `dd_active_customers` | 12 | 12 | 0 | 0 | 0 | 0 | 0 | identical |
| `dd_region_by_category` | 12 | 0 | 12 | 0 | 0 | 0 | 0 | within_tol |
| `dd_ctrl_rev_by_region` | 12 | 0 | 12 | 0 | 0 | 0 | 0 | within_tol |
| `dd_ctrl_rev_by_category` | 12 | 0 | 12 | 0 | 0 | 0 | 0 | within_tol |
| `conv_grain_drift_t1` | 6 | 0 | 6 | 0 | 0 | 0 | 0 | within_tol |
| `conv_grain_drift_t2` | 6 | 0 | 6 | 0 | 0 | 0 | 0 | within_tol |
| `conv_grain_drift_t3` | 6 | 0 | 6 | 0 | 0 | 0 | 0 | within_tol |
| `conv_grain_drift_t4` | 6 | 0 | 3 | 0 | 0 | 0 | 3 | both_refused |
| `conv_grain_drift_t5` | 6 | 0 | 6 | 0 | 0 | 0 | 0 | within_tol |
| **TOTAL** | **1190** | **206** | **834** | **0** | **0** | **0** | **150** | |

---

## 3. What the buckets actually mean here

### 3.1 `both_refused` (150 pairs, 12.6%) is agreement by construction and is EVIDENCE OF NOTHING

A refusal — the model declining, or the layer rejecting a plan for an unknown field or a
grain violation — is decided by `compile_plan` **before any SQL is generated**, and both
backends short-circuit on it without opening a connection. These 150 pairs could not have
disagreed no matter what the warehouses contained. Counting them in a headline agreement
percentage inflates it.

They are not completely vacuous — the refusal *reason* could still differ, because the
BigQuery arm compiles through a different dialect and a `DialectError` would surface as an
error rather than a refusal. It does not: **150/150 refusal strings are byte-identical across
the arms** (86 distinct reasons), and no plan produced a `dialect_gap:` error. So the
BigQuery translator covers every construct the shipped models express.

**The evidential population is the 1040 executed pairs, not 1190.**
Restated on that base: **1040/1040 = 100.00% agreement, 0 divergent.**

### 3.2 `identical` (206) vs `within_tol` (834) — and why the split is not what it sounds like

`within_tol` sounds like "agreed only after we allowed 1% slack". It is not. The scorer's
tolerance (`score/score.py:TOL = 0.01`) is the band this report inherits, but no pair comes
anywhere near needing it:

| largest relative gap in a pair | pairs |
|---|---:|
| <= 1e-13 | 87 |
| <= 1e-14 | 527 |
| <= 1e-15 | 220 |

Worst gap anywhere: **1.7394e-14** — the 1% band is **5.75e+11 times wider** than the largest
disagreement it had to forgive. Pairs needing more than `1e-10`: **0**.

This is IEEE-754 summation order, not semantics. Floating-point addition is not
associative, and the two engines partition a scan of the same 150,242 order lines
differently, so the last bits of a `SUM` over ~10^5 doubles are not expected to match —
no correct system makes them match. The `identical` bucket is precisely the queries
whose measures are
integer-valued (`COUNT(DISTINCT ...)`, `COUNT(*)`, `SUM` over an integer column), where
float accumulation cannot bite.

So the honest phrasing is: **206/1040 executed pairs agree exactly; the remaining 834 agree to
within 1.74e-14 relative.** Nothing in this arm needed the 1% tolerance; a band of 1e-12
would have produced the same matrix.

That last sentence is a claim, so it is measured rather than asserted. Re-running the
whole matrix at successively tighter tolerances:

| tolerance | identical | within_tol | divergent | both_refused |
|---|---:|---:|---:|---:|
| `0.01` | 206 | 834 | 0 | 150 |
| `0.001` | 206 | 834 | 0 | 150 |
| `1e-06` | 206 | 834 | 0 | 150 |
| `1e-09` | 206 | 834 | 0 | 150 |
| `1e-13` | 206 | 834 | 0 | 150 |
| `0 (bit-exact)` | 206 | 0 | 834 | 150 |

The matrix is unchanged across **eleven orders of magnitude** of tolerance and only
collapses at exactly zero, where `within_tol` becomes `divergent` wholesale. The 1%
band is therefore not load-bearing: it is inherited from the scorer for consistency,
not because this comparison needs any part of it.

### 3.3 Two normalisations were applied before comparing, and both are disclosed

Cells are serialised by `json.dumps(..., default=str)`, so a type difference in the client
library shows up as a string difference. Two canonicalisations run before equality
(`harness/replay_s.py:_canon_cell`), and the report counts every cell that needed one:

| normalisation | cells | why |
|---|---:|---|
| tz-aware -> instant | 252 | BigQuery's client always returns TIMESTAMP as `...+00:00`; DuckDB returns it naive |
| naive -> instant | 252 | the DuckDB side of the same 252 comparisons |
| DATE -> instant | 0 | would fire if a BigQuery DATE-typed dimension reached the SELECT list; **it never does** |
| numeric string -> float | 0 | no NUMERIC/BIGNUMERIC column exists in either warehouse, so this never fires |

The temporal normalisation forgives **representation only, never a shift**: it maps every
form onto an absolute instant, so a one-hour zone error stays a divergence. That was
verified by mutation (see §6). Independently, the two arms produce the same set of 12
distinct temporal literals once the offset is stripped (identical sets: yes), and the
per-pair temporal multisets match 21/21.

### 3.4 Row order differs on 232 pairs and is reported, not hidden

Rows are matched order-insensitively, the same convention `score/score.py:topn_match`
uses. This is not a convenience: a `SELECT` without an `ORDER BY` denotes a set, and row
order out of a `FULL OUTER JOIN` is not stable even *within* DuckDB — replaying the stored
plans on the same engine reproduces the committed rows as a multiset 1190/1190 but in the
same order only 1011/1190. Treating order as disagreement would report the DuckDB arm as
disagreeing with itself.

**That last figure is itself not reproducible, which is the point.** DuckDB's hash
aggregate emits groups in an order that depends on process-local hash iteration, so the
same replay run four times scored 1010, 1011, 1012 and 1009 rows in the committed order
(measured). The multiset match is 1190/1190 in every run; only the ordering wanders. Any
single number quoted here is one draw from that distribution — earlier drafts of this
document quoted a frozen `1012` in this paragraph while §6 recomputed it, so the two
sections disagreed with each other. Both now read the same computed value. This is the
same non-determinism `REVIEW-MEMO.md` F10 records for the emitted SQL text.

**Caveat that cuts the other way:** 986 of the 1040 executed pairs are repeats of the same
statement, and the BigQuery backend executes each distinct statement once and reuses the
result. Row order is therefore identical across repeats *by construction*, so the 232 figure
measures order stability between the arms, not within them.

---

## 4. Divergence triage

The brief asks every divergence to land in exactly one of three categories. **The final
matrix has zero divergent pairs**, so what follows is the triage of everything that was
found along the way, including one item that was a real divergence until it was fixed and
one that is a live defect in the reference compiler.

### (a) Dialect bug in our port — 1 found, fixed, re-run

**`BigQueryDialect.combine_measures` rewrote `FULL OUTER JOIN ... ON TRUE` into
`CROSS JOIN`.** The stated justification was that BigQuery rejects a non-equality
outer-join predicate. It does not — BigQuery's restriction is on predicates that reference
both sides non-equally, and a constant `TRUE` references neither:

```sql
SELECT m0.a AS a, m1.b AS b
FROM (SELECT SUM(1) AS a FROM `joon-sandbox.semantic_bench_d1.orders` AS orders) m0
FULL OUTER JOIN (SELECT SUM(2) AS b FROM `joon-sandbox.semantic_bench_d1.orders` AS orders) m1
  ON TRUE          -- returns (50000, 100000)
```

The rewrite produced the same *rows* (both sides are ungrouped aggregates returning one
row each), so it would never have shown up as a divergence in this matrix. That is exactly
what made it dangerous: it silently changed the join structure of the arm that exists to
prove the join structure is warehouse-neutral. Measured counterfactually by restoring it:

| | with the rewrite | without it (shipped) |
|---|---:|---:|
| BigQuery statements using `CROSS JOIN` | 8 | 0 |
| BigQuery statements using `FULL OUTER JOIN ... ON TRUE` | 0 | 8 |
| distinct statements whose join structure differs between arms | 8 / 54 | **0 / 54** |
| logged rows sitting on such a statement | 143 / 1040 | **0** |

Removed in `compiler/dialects.py`; the unit test that asserted the rewrite
(`compiler/test_dialects.py`) was inverted to assert the two dialects now emit the *same*
join. With it gone the two arms reconstruct exactly:

### The structural check that replaces "trust the dialect"

For all 160 distinct (dataset, plan) pairs, the BigQuery SQL was mechanically de-dialected
— qualified table name back to bare, `TIMESTAMP_TRUNC(x, U)` back to `date_trunc('u', x)`,
`DATE_TRUNC(DATE_ADD(DATE(x), INTERVAL n U), Y)` back to the DuckDB form, typed literal
back to `DATE '...'` — and compared to the DuckDB SQL:

| result | count |
|---|---:|
| BigQuery SQL reconstructs to the DuckDB SQL **exactly** | 74 |
| structural residual (an unforced divergence) | **0** |
| plans that refuse, with identical refusal text | 86 |
| plans that refuse differently across arms | **0** |

Join-keyword census, counted once per distinct plan (so a statement two plans
share is counted twice), both arms:

| keyword | DuckDB arm | BigQuery arm |
|---|---:|---:|
| `CROSS JOIN` | 0 | 0 |
| `FULL OUTER JOIN` | 19 | 19 |
| `ON TRUE` | 14 | 14 |
| `LEFT JOIN` | 75 | 75 |
| `COALESCE(` | 5 | 5 |

### (b) Genuine semantic differences between the engines — 3, all benign here

1. **Float summation order.** Covered in §3.2: worst relative gap 1.739e-14 over 834 pairs.
   Not fixable and should not be fixed; it is what the tolerance is for.
2. **TIMESTAMP is tz-aware in BigQuery, naive in DuckDB.** A representation difference in
   the client, normalised and counted in §3.3. The instants are identical.
3. **`fiscal_year` is DATE-typed on BigQuery and TIMESTAMP-typed on DuckDB.** This is real
   and forced: BigQuery cannot add a `MONTH` interval to a `TIMESTAMP` at all, so the
   expression must route through `DATE()`. It does not fire in this matrix because
   `fiscal_year` appears only in `WHERE` clauses across all 160 logged plans and never in a
   `SELECT` list — confirmed by the `DATE -> instant` normalisation firing 0 times. **If a
   future question groups by `fiscal_year`, the two arms will return different column
   types for the same certified dimension.** The comparison would still pass (both denote
   the same instant) but a consumer reading the type would not.

### (c) Defect in the reference compiler — 1 found, NOT fixed here, flagged loudly

> ### `compile.py` emits `ORDER BY <field> ASC` with no NULLS placement, and the two
> ### engines place NULLs differently. Same plan, same model, same data, different answer.

DuckDB sorts NULLs LAST in both directions. BigQuery sorts NULLs LAST for `DESC` but
**FIRST** for `ASC`. Verified directly on both engines:

```
ORDER BY v DESC   DuckDB [3, 1, NULL]     BigQuery [3, 1, NULL]     agree
ORDER BY v ASC    DuckDB [1, 3, NULL]     BigQuery [NULL, 1, 3]     DISAGREE
```

`compile.py:compile_plan` emits `ORDER BY {fld} {'ASC'|'DESC'}` and nothing else, so any
plan combining an ascending sort with a `LIMIT` over a nullable measure returns a
**different row** on the two warehouses. And the compiler *manufactures* the NULLs itself:
combining measures at different base grains with a `FULL OUTER JOIN` produces NULL measures
for any group one subquery does not contain.

Reproduction against the live warehouses, on an entirely ordinary business question
("which order status has the lowest refunds?"):

```python
plan = {"measures": ["net_revenue", "refund_total"],
        "dimensions": ["order_status"],
        "order_by": {"field": "refund_total", "dir": "asc"}, "limit": 1}
```
```
emitted:   ORDER BY refund_total ASC
DuckDB  -> ('delivered', 35286752.417, 2668316.54)
BigQuery-> ('shipped',   24899101.863, None)
```

Both are faithful executions of the SQL the semantic layer generated. The layer's central
promise — that a governed plan means the same thing regardless of warehouse — does not
hold for this plan shape.

**Why it does not move the matrix:** of the 5 distinct statements in the logged corpus
that carry a `LIMIT`, **0 sort `ASC`** and **0 have no `ORDER BY` at all** — all 5 sort
`DESC`, where the two engines agree. None has a tie at the cut either (checked: the
boundary value is unique in every one, so `LIMIT` never has to choose between equals).
The corpus misses this by luck, not by design.

**The fix, verified on both engines but deliberately not applied:** append an explicit
`NULLS LAST` to the emitted `ORDER BY`. `NULLS LAST` is DuckDB's existing default, so the
published DuckDB arm's *results* do not change (confirmed: the `s1_top_customer` answer is
byte-identical with and without it), and BigQuery then matches. Both engines accept the
syntax. With the fix, the reproduction above returns `('delivered', ...)` on both.

It is left unapplied because it changes the SQL the **published** condition-S arm emits,
which is a reviewed change to the benchmark's reference compiler, not something a control
arm should smuggle in — and `compiler/compile.py` is concurrently being edited by another
workstream. It is a one-line change at `compile.py:compile_plan`, in the `ORDER BY` branch.

---

## 5. Coverage — what the BigQuery arm actually exercised

54 distinct statements is a much smaller evidential base than 1040 logged rows. The rows are
a weighting by how often the models produced each plan, not independent trials. Feature
coverage over the distinct statements:

| feature | distinct statements | logged rows |
|---|---:|---:|
| `project.dataset.table` AS table | 54 | 1040 |
| FULL OUTER JOIN ... ON TRUE | 8 | 143 |
| FULL OUTER JOIN ... ON <equality> | 8 | 104 |
| COALESCE across measure aliases | 4 | 72 |
| LEFT JOIN (model join graph) | 43 | 778 |
| TIMESTAMP_TRUNC(ts, UNIT) | 4 | 63 |
| DATE_TRUNC(DATE_ADD(DATE(ts),...)) | 1 | 21 |
| typed TIMESTAMP calendar literal | 4 | 63 |
| typed DATE calendar literal | 1 | 21 |
| CASE decode (order_status) | 1 | 5 |
| COUNT(DISTINCT ...) | 5 | 251 |
| NULLIF ratio guard | 3 | 103 |
| lower()/replace() identity bridge | 1 | 21 |
| IN (vocabulary expansion) | 3 | 54 |
| ORDER BY | 9 | 51 |
| LIMIT | 5 | 42 |

Every construct the dialect can emit is exercised at least once, including the hardest
translation (the fiscal-year `DATE_TRUNC(DATE_ADD(DATE(...)))` chain).

---

## 6. Why this matrix should be believed — the comparator was tested against mutants

A comparison that reports 100% agreement is worth nothing until it is shown capable of
reporting less. `scripts/mutation_check.py` injects known faults into a copy of the
BigQuery arm and re-runs the matrix; the table below is generated by running it, not
transcribed.

| mutation (3 pairs each) | expected bucket | observed change | verdict |
|---|---|---|---|
| scale one measure by 1.05 (outside the 1% band) | `divergent` | `divergent` +3, `within_tol` -3 | detected |
| scale exactly-identical pairs by 1.005 (inside the band) | `within_tol` | `identical` -3, `within_tol` +3 | detected |
| turn `ok` into `refusal` | `refused_by_one` | `refused_by_one` +3, `within_tol` -3 | detected |
| turn `ok` into `error` | `error_by_one` | `error_by_one` +3, `within_tol` -3 | detected |
| drop one row from a multi-row result | `divergent` | `divergent` +3, `within_tol` -3 | detected |
| shift a timestamp by one hour | `divergent` | `divergent` +3, `within_tol` -3 | detected |

The last row is the important one: it proves the temporal canonicalisation of §3.3
forgives representation but **not** a zone shift, which is the failure mode the UTC
caveat is about. Without that check, §3.3 would be indistinguishable from quietly
normalising a real bug out of existence.

Four further independent checks:

- **The BigQuery arm was computed, not replayed from BigQuery's cache.** A statement
  BigQuery has already materialised is returned from its server-side result cache
  without re-scanning anything, billing 0 bytes — which would make a re-run re-affirm
  an earlier run instead of independently recomputing it, while looking merely cheap.
  `scripts/bq_recompute_check.py` re-executes all 54 distinct statements with
  `use_query_cache=False` and compares against the logged rows: **54/54 statements
  re-scanned (0 served from cache, 1.17 GB billed), 0 value mismatches**. Run on demand,
  not as part of this generator, because it costs real bytes.
- **The warehouses hold the same data.** `scripts/warehouse_parity.py` compares row
  counts and one aggregate per column, below the semantic layer: **79 column-level
  checks across 16 tables, 0 mismatches**. Agreement at the measure level is therefore
  not resting on an assumption about the load.
- **The DuckDB arm is the published arm.** Replaying the stored plans through DuckDB
  reproduces the committed `results/runs_*.jsonl` rows **1190/1190** as multisets (**1011/1190**
  in the same order), with **0** value differences. Arm A is not a re-derivation that
  might have drifted from what the paper reports.
- **UTC is asserted, not assumed.** `BigQueryBackend._verify_utc` runs a probe at connect
  time checking `TIMESTAMP_TRUNC`, `DATE(TIMESTAMP)` and the fiscal-year shift all
  evaluate in UTC. A zone shift would not raise anywhere else — it would quietly move
  boundary rows into the next month bucket and read as a data disagreement.

---

## 7. What this arm does NOT prove

Stated plainly, because the number in §2 invites over-reading.

1. **Both arms share `compiler/compile.py`.** Only the ~120 lines of
   `BigQueryDialect` differ. This tests that the *dialect port* is faithful and that
   BigQuery evaluates the generated SQL the same way DuckDB does. It does **not**
   independently test the compiler's grain logic, its refusals, or its certified filters —
   a bug there is present identically in both arms and would agree perfectly with itself.
   (This is the same shared-oracle concern as `REVIEW-MEMO.md` F1, applied to a second
   axis.) An independent semantic layer — the Looker arm — is what would test that, and
   it is not implemented.
2. **150/1190 of the headline is refusals that never reached a warehouse** (§3.1).
3. **54 distinct statements, not 1190 independent trials** (§5).
4. **The corpus does not exercise the one construct that would break** — ascending sorts
   with a limit over a nullable measure (§4c). The agreement is partly a property of which
   questions the models happened to ask.
5. **Row order is not compared** (§3.4), and for the multi-measure statements it genuinely
   differs between the arms.

---

## 8. Reproducing this

```sh
compiler/test_dialects.py                  # dialect unit tests
scripts/warehouse_parity.py                # do the two warehouses hold the same rows?
harness/replay_s.py --backend duckdb --in 'results/runs_*.jsonl' --out results/replay_duckdb.jsonl
harness/replay_s.py --backend bq     --in 'results/runs_*.jsonl' --out results/replay_bq.jsonl
scripts/mutation_check.py                  # negative control on the comparator
scripts/bq_recompute_check.py              # was BigQuery's arm computed or cache-served?
harness/replay_s.py --agreement results/replay_duckdb.jsonl results/replay_bq.jsonl
scripts/agreement_matrix.py                # regenerates this file and results/agreement_duckdb_vs_bq.csv
```

Run the two replays back to back and check `compiler/compile.py` and
`compiler/dialects.py` hash the same before and after: if the compiler changes between
the arms, the matrix is comparing two different compilers and means nothing.

The BigQuery arm needs `gcloud` application-default credentials for `joon-sandbox` and costs
well under a dollar (54 distinct statements over tables of at most 8 MB; the backend
executes each distinct statement once and reuses the result for the 986 repeats).

`results/runs_*.jsonl` is never written by any of this — `replay_s.py` refuses an
`--out` that is one of its inputs, and refuses an `--out` named `runs_*.jsonl` at all.

