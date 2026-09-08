# BigQuery dialect spike

`scripts/bq_dialect_spike.sql` empirically answers the five BigQuery-vs-DuckDB dialect risks
the port rests on. It uses only literal/synthetic rows (`UNNEST([...])`) — **no loaded
tables, no dataset, no warehouse**. All it needs is a project that can run a query.

This is not a hypothetical exercise. `compiler/dialects.py` (`BigQueryDialect`) has already
been written against assumed answers to all five risks, and its rewrites are what condition S
will emit. This script is the evidence for those assumptions. Probes marked **[SHIPPED]**
reproduce the exact bytes the compiler emits today — those are the ones that decide whether
the BigQuery arm runs at all.

**Status: run in full against `joon-sandbox` on 2026-09-08, and independently re-run
end-to-end the same day against the loaded datasets. All 19 probes have measured results
below and both runs agree row-for-row.** One assumption (probe 1a) was falsified and the
code has since been changed; the other four risks were all confirmed.

`[SHIPPED]` is a claim about `compiler/dialects.py` as it stands, so it moves when the
dialect does. It has already moved once: when 1a falsified the CROSS JOIN assumption, **1a
became shipped, 1d stopped being, and 5b's join was rewritten** to the `ON TRUE` shape the
compiler actually emits. Re-check the labels against
`compile_plan(..., dialect="bigquery:…")` output after any change to `dialects.py`
(see "Regenerating the shipped shapes").

## Run it

```bash
python scripts/run_spike.py --project joon-sandbox
```

`run_spike.py` lifts each probe's SQL out of the `.sql` file — which stays the single source
of truth for what each probe says — and submits it as its own ordinary `SELECT`, catching
rejections client-side. Add `--json PATH` to save raw results, `--markdown` for README-ready
table rows, or `--time-zone America/Toronto` to re-run every probe under a non-UTC session
timezone. It exits non-zero if any `[SHIPPED]` probe is rejected.

**Do not run the `.sql` file directly.** The obvious `bq query` invocation fails twice over,
and both failures are about the harness rather than the dialect:

- Passing the file as a positional argument (`bq query "$(cat ...)"`) never reaches BigQuery:
  the file's first line starts with `--`, which the bq CLI parses as a command-line flag
  (`FATAL Flags parsing error: Unknown command line flag ' '`). It has to go in on stdin.
- Even on stdin (`bq query --use_legacy_sql=false --project_id=joon-sandbox < scripts/bq_dialect_spike.sql`)
  the script dies at line 104 with *"Billing has not been enabled for this project. DML
  queries are not allowed in the free tier."* The script accumulates findings with
  `INSERT INTO spike_results`, and that INSERT is DML. This is a real obstacle rather than a
  detail: the spike reads no tables and scans 0 bytes, so a project with BigQuery enabled but
  **no billing account** — exactly the cheapest way to run it — is precisely where it cannot
  run. `run_spike.py` exists to remove that dependency; it issues no DML.

Other notes:

- The probes read no tables, so they scan 0 bytes and cost nothing.
- Several probes are *expected* to be rejected — that rejection is the finding.

## Reading the output

| column | meaning |
| --- | --- |
| `probe` | probe id, matching the sections in the `.sql` and the table below |
| `name` | what is being tested; `[SHIPPED]` = the exact SQL the compiler emits today |
| `outcome` | `RAN` = BigQuery accepted and executed it; `ERROR` = it rejected it |
| `detail` | on `RAN`, the value(s) produced plus an in-query verdict; on `ERROR`, BigQuery's message |

`outcome='RAN'` is **not** automatically a pass. For probes 1a, 3a, 3c and 4a a successful
run is the *surprising* result and means an assumption baked into `compiler/dialects.py` was
unnecessary. Conversely, `outcome='ERROR'` on a `[SHIPPED]` probe is a hard blocker. Each
probe in the `.sql` carries a comment stating exactly what PASS and FAIL look like for it.

## Results

Measured against project `joon-sandbox`, 2026-09-08, server default session timezone (UTC).
BigQuery error text is abridged to its first sentence; `run_spike.py --json` keeps it in full.

| Probe | Risk | What it tests | Expected | Result (`outcome` / `detail`) | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1a | 1 | **[SHIPPED]** `FULL OUTER JOIN (subquery) alias ON TRUE` — the zero-dimension shape | ERROR (risk confirmed) | `RAN` — `net_revenue=175.0 order_count=7 rows=1` | ❌ **ASSUMPTION FALSIFIED** — BigQuery accepts `ON TRUE`. This is now the shipped shape. See "Risk 1 was wrong" below. |
| 1b | 1 | **[SHIPPED]** `FULL OUTER JOIN ... ON m0.dim = m1.dim` | RAN, `rows=3 both=1 left_only=1 right_only=1 dim_label_lost=1` | `RAN` — `rows=3 both=1 left_only=1 right_only=1 dim_label_lost=1` | ✅ PASS — exact match; non-matching groups retained from both sides |
| 1c | 1 | `FULL OUTER JOIN ... ON 1 = 1` — is the restriction syntactic or semantic? | either; only matters if 1a failed | `RAN` — `net_revenue=175.0 order_count=7 rows=1` | ✅ accepted (moot — 1a passed) |
| 1d | 1 | `CROSS JOIN` — the zero-dimension rewrite that *used* to ship | RAN, `net_revenue=175.0 order_count=7 rows=1` | `RAN` — `net_revenue=175.0 order_count=7 rows=1` | ✅ works, but **no longer shipped** (rewrite removed after 1a); kept as the fallback if 1a ever regresses |
| 2a | 2 | **[SHIPPED]** `TIMESTAMP_TRUNC(ts, MONTH/YEAR)` == DuckDB `date_trunc` | RAN, `all_match=true` | `RAN` — `all_match=true` (all 3 inputs) | ✅ PASS |
| 2b | 2 | timezone sensitivity of `TIMESTAMP_TRUNC` (the UTC assumption) | RAN, `differ=true` | `RAN` — `utc=2024-05-01 00:00:00+00 toronto=2024-04-01 04:00:00+00 differ=true` | ✅ confirmed — assumption is real and load-bearing |
| 3a | 3 | `TIMESTAMP + INTERVAL 11 MONTH` — the DuckDB expression verbatim | ERROR (risk confirmed) | `ERROR` — *TIMESTAMP +/- INTERVAL is not supported for intervals with non-zero MONTH or YEAR part.* | ✅ risk CONFIRMED |
| 3b | 3 | **[SHIPPED]** `DATE_TRUNC(DATE_ADD(DATE(ts), INTERVAL 11 MONTH), YEAR)` | RAN, `all_match=true` | `RAN` — `all_match=true` (all 4 inputs, incl. both FY boundaries) | ✅ PASS |
| 3c | 3 | `TIMESTAMP_ADD(ts, INTERVAL 11 MONTH)` — the obvious translation | ERROR (MONTH unsupported) | `ERROR` — *TIMESTAMP_ADD does not support the MONTH date part when the argument is TIMESTAMP type* | ✅ risk CONFIRMED |
| 3d | 3 | `DATE_ADD` month-end clamping == DuckDB | RAN, `all_match=true` | `RAN` — `2023-03-29→2024-02-29`, `2024-03-31→2025-02-28`, `all_match=true` | ✅ PASS — leap-year and month-end clamping agree |
| 3e | 3+4 | **[SHIPPED]** fiscal_year filter vs `DATE '...'` literal | RAN, `matched=1 of 4` | `RAN` — `matched=1 of 4` | ✅ PASS |
| 4a | 4 | `TIMESTAMP_TRUNC(...) = DATE '...'` uncast — the pre-dialect emit | ERROR (risk confirmed) | `ERROR` — *No matching signature for operator = for argument types: TIMESTAMP, DATE* | ✅ risk CONFIRMED |
| 4b | 4 | **[SHIPPED]** `TIMESTAMP_TRUNC(...) = TIMESTAMP '2024-05-01'` (bare-date literal) | RAN, `eq_shipped=true eq_explicit_time=true both_agree=true` | `RAN` — `eq_shipped=true eq_explicit_time=true both_agree=true` | ✅ PASS |
| 4c | 4 | `DATE(TIMESTAMP_TRUNC(...)) = DATE '...'` — the fallback fix | RAN, `eq=true` | `RAN` — `eq=true` | ✅ works (unused fallback) |
| 4d | 4 | half-open range == TRUNC equality (sargable form) | RAN, `in_range=true agrees_with_trunc=true` | `RAN` — `in_range=true agrees_with_trunc=true` | ✅ works (unused alternative) |
| 5a | 5 | unguarded `x/0` from data | ERROR (risk confirmed) | `ERROR` — *division by zero: 100 / 0* | ✅ risk CONFIRMED |
| 5b | 5 | **[SHIPPED]** `NULLIF` ratio guard inside `FULL OUTER JOIN … ON TRUE` | RAN, `result=NULL` | `RAN` — `result=NULL` | ✅ PASS — verified against the compiled `aov` SQL |
| 5c | 5 | `SAFE_DIVIDE(x, 0)` | RAN, `result=NULL` | `RAN` — `result=NULL` | ✅ works (unused alternative) |
| 5d | 5 | `IEEE_DIVIDE(x, 0)` — the DuckDB-identical option | RAN, `result=inf` | `RAN` — `result=CAST("inf" AS FLOAT64)` | ✅ matches DuckDB's `inf` |

All seven `[SHIPPED]` probes (1a, 1b, 2a, 3b, 3e, 4b, 5b) ran and matched their expected
detail exactly, so nothing blocks the BigQuery arm. The only four `ERROR` rows are the four
probes that were *supposed* to be rejected.

> **Two `[SHIPPED]` labels were stale and have been corrected in the `.sql`.** Both were
> left behind by the removal of the CROSS JOIN rewrite: probe **1d** was still marked
> `[SHIPPED SHAPE]` although the compiler no longer emits `CROSS JOIN` anywhere, and probe
> **5b** — the division-guard gate — was testing `NULLIF` inside a `CROSS JOIN` for the
> stated reason that a risk-1 failure should not be mistaken for a division failure. That
> reason expired with the rewrite, and it left the one `[SHIPPED]` probe for risk 5 asserting
> a join shape the compiler does not emit. 5b now uses `FULL OUTER JOIN … ON TRUE`, matching
> `compile_plan(m, {"measures": ["aov"]}, dialect="bigquery:…")`, and still returns
> `result=NULL`. This mattered beyond tidiness: `run_spike.py` gates on the string
> `[SHIPPED]`, so a stale label decides what counts as a blocker.

## Risk 1 was wrong: BigQuery accepts `FULL OUTER JOIN ... ON TRUE`

Probe 1a was expected to fail and did not. BigQuery's restriction is on non-equality
predicates that *reference both sides* of the join; the constant `TRUE` references neither,
so it is accepted. This was verified three times — on the synthetic probe above, on the
real compiled query against the loaded `semantic_bench_d1` tables, and again on an
independent re-run against the same tables — where both spellings return identical values:

```
FULL OUTER JOIN ON TRUE : rows=1 (60185854.28000051, 35996)
CROSS JOIN              : rows=1 (60185854.28000051, 35996)
```

The consequence was not a bug but an **unforced divergence between the arms**:
`BigQueryDialect.combine_measures` was rewriting the join structure of every scalar
multi-measure query (`aov`, `shipping_pct_of_revenue`, `net_revenue_after_refunds`,
`advneg_attainment_lift`) to work around a restriction that does not exist — weakening
exactly the comparison the dialect exists to support. The override has since been removed
from `compiler/dialects.py`; both arms now emit the same join structure and only the
spelling of leaves differs.

## The UTC assumption

Probe 2b confirms `TIMESTAMP_TRUNC` is timezone-sensitive, but it only proves it for an
*explicit* `time_zone` argument — and the compiler never emits one. The sharper question is
whether anything **outside** the SQL can move the result. It can: BigQuery's session
variable `@@time_zone` changes the default for `TIMESTAMP_TRUNC` and `DATE()` on a fixed
instant, with no timezone argument anywhere in the query.

| session `@@time_zone` | `TIMESTAMP_TRUNC(ts, MONTH)` | `DATE(ts)` |
| --- | --- | --- |
| `UTC` (server default) | `2024-05-01 00:00:00+00` | `2024-05-01` |
| `America/Toronto` | `2024-04-01 04:00:00+00` | `2024-04-30` |
| `Asia/Tokyo` | `2024-04-30 15:00:00+00` | `2024-05-01` |

*(input `TIMESTAMP '2024-05-01 00:30:00+00'`)*

`DATE()` is what the fiscal-year expression runs through, so **both** `order_month`/
`order_year` and `fiscal_year` are exposed.

### The precise rule

Every one of the 50,000 `orders.order_ts` values is **exactly midnight UTC** (measured:
`distinct_hours = 1`, `midnight_utc = 50000`, range 2023-01-01 … 2024-12-30). The data is
date-only. That makes the failure condition sharp and asymmetric:

- **Negative UTC offsets change which bucket a row lands in.** Midnight UTC minus any offset
  lands on the *previous* civil date, so all 50,000 orders shift back a day and the 1,650
  orders dated the 1st of a month move into the previous month. Measured: `DATE(order_ts)`
  differs from UTC for **50,000/50,000** rows under `America/Toronto`, and for **0/50,000**
  under `Asia/Saigon` and `Asia/Tokyo`.
- **Positive UTC offsets preserve bucket MEMBERSHIP but still move the LABEL.** Midnight UTC
  plus any offset up to +23:59 lands on the same civil date, so no row changes group and the
  aggregates are identical *to the cent*: measured, `Asia/Saigon` (+07) reproduces all three
  scalar time-intelligence answers exactly. But `TIMESTAMP_TRUNC(order_ts, MONTH)` returns the
  *instant* at which that month begins **in the session zone**, and that instant is not the
  same one: measured, the month label differs from UTC for **50,000/50,000** rows under
  `Asia/Saigon` and `Asia/Tokyo` as well as `America/Toronto` — January 2024 comes back as
  `2023-12-31 17:00:00+00` under Saigon instead of `2024-01-01 00:00:00+00`.

  That distinction is not cosmetic. `score/score.py::topn_match` compares non-numeric cells
  with `str(v)`, and `scripts/agreement_matrix.py::same` only strips a `+00`/`+00:00` suffix
  before comparing digits. Both see `2023-12-31 17:00:00` ≠ `2024-01-01 00:00:00` and fail the
  row. So `s8_rev_by_month` breaks under a *"safe"* positive offset too — with every number
  right. **There is no harmless non-UTC session zone here; there is only a zone that corrupts
  the values and a zone that corrupts only the labels.**

This matters because the maintainer's own zone is `America/Toronto` — the value-corrupting
direction — and the live Looker connection `joon-sandbox` is configured
`query_timezone = Asia/Saigon` (`db_timezone = UTC`), the label-corrupting one. Neither is
UTC. That is precisely what `convert_tz: no` in `lookml/views/orders.view.lkml` defends
against.

### Blast radius

Five question turns depend on these dimensions:

| id | dimension | UTC | America/Toronto | drift |
| --- | --- | --- | --- | --- |
| `s8_rev_2024` | `order_year` | 30,156,768.82 | 30,080,994.14 | 0.251% |
| `s8_rev_fy2024` | `fiscal_year` | 30,005,743.09 | 29,958,838.09 | 0.156% |
| `s8_rev_2023` | `order_year` | 30,029,085.46 | 30,009,967.81 | 0.064% |
| `s8_rev_by_month` | `order_month` + `order_year` | 12 rows | 12 rows | 0.135% – 3.678% |
| `multiturn` t5 | `fiscal_year` | *(same plan as `s8_rev_fy2024`)* | | 0.156% |

The failure mode is **heterogeneous, and that is the dangerous part**:

- The three scalars drift **0.064%–0.251% — inside the 1% scoring tolerance.** They would be
  scored *correct* while being wrong. A silent zone shift is indistinguishable from float
  noise at the report level.
- `s8_rev_by_month` is loud: 3 of its 12 rows drift past 1% (October 2.360%, November 1.636%,
  December 3.678%), and **all 12 `order_month` labels shift** (`2024-11-01 00:00:00+00` →
  `2024-11-01 04:00:00+00`), which a set-based `topn` comparison fails outright.

So a zone shift produces three quietly-wrong scalars and one loudly-wrong breakdown — the
kind of split that gets triaged as "one flaky question" rather than "the clock is wrong".

Under a *positive* offset (`Asia/Saigon`) the same table is inverted: the three scalars are
byte-identical to UTC and `s8_rev_by_month`'s twelve values are identical to the cent, but all
twelve labels move to `…-31 17:00:00+00` / `…-30 17:00:00+00`, so that one question fails and
nothing else does. Either way exactly one of the five turns fails loudly — which is why the
connect-time guard, not the agreement report, is what has to catch this.

### This is already defended, and the defences work

The assumption is **not** undocumented. It is stated in five places, and the two
load-bearing ones are enforced, not just described:

| where | what it says |
| --- | --- |
| `harness/replay_s.py` — *"THE UTC CAVEAT (load-bearing; the whole comparison turns on it)"* | names both `TIMESTAMP_TRUNC` and `DATE()`-in-fiscal-year, and lists three defences |
| `harness/replay_s.py::_verify_utc` | **runtime guard** — probes the server at connect time and refuses to run if truncation is not UTC |
| `lookml/views/orders.view.lkml` | `convert_tz: no` marked deliberate and load-bearing |
| `lookml/TRANSLATION-NOTES.md` §7.2 | predicts the exact symptom: *"drifts by a fraction of a percent — small enough to look like rounding, large enough to fail a 1% tolerance check"* |
| `dbt/tests/parity/assert_d1_timestamp_grain.sql` | **parity test** — asserts every `order_ts` is midnight, catching a zone shift on load that leaves row counts and column sums untouched |

`_verify_utc` was tested against deliberately wrong session zones — in both directions — and
trips on every one of them (measured by injecting `SET @@time_zone` ahead of the guard's own
probe query):

```
UTC (server default)  TIMESTAMP_TRUNC -> 2024-05-01 00:00:00+00  ->  guard passes
America/Toronto (-04) TIMESTAMP_TRUNC -> 2024-05-01 04:00:00+00  ->  guard TRIPS
Asia/Saigon     (+07) TIMESTAMP_TRUNC -> 2024-04-30 17:00:00+00  ->  guard TRIPS
Asia/Tokyo      (+09) TIMESTAMP_TRUNC -> 2024-04-30 15:00:00+00  ->  guard TRIPS
```

The positive-offset rows are the ones worth noting: the guard rejects Saigon and Tokyo even
though every *value* under those zones is correct. That is the right call, because the labels
are not.

One honest caveat on that guard: under a *session-timezone* shift only its first check
(`TIMESTAMP_TRUNC`) fires — confirmed in all three failing runs above, each of which reported
only the `TIMESTAMP_TRUNC` line. Its `DATE()` and fiscal-year checks compare against
`TIMESTAMP '...'` literals, which BigQuery parses in the same session zone, so the two shifts
cancel and those two checks stay green. They still do their job against a *load-time* zone
shift, which is the other way this can go wrong. The guard as a whole trips either way — but
if it ever fires, the failing check does not by itself tell you which of the two happened.

## What each risk decides

1. **`FULL OUTER JOIN ... ON TRUE`** — the critical one, and **the one assumption that was
   wrong**. `Dialect.combine_measures` falls back to `ON TRUE` when a plan has no grouping
   dimensions, i.e. *every scalar multi-measure query*. `BigQueryDialect` used to substitute
   `CROSS JOIN` there. 1a proved the substitution was never necessary; it has been removed.
2. **`TIMESTAMP_TRUNC` vs `date_trunc`** — `order_month` and `order_year` are the most-used
   dimensions in the suite. 2a is a straight equivalence check and passed; 2b pins the UTC
   assumption that makes 2a true. See "The UTC assumption" above.
3. **Fiscal year** — `date_trunc('year', order_ts + INTERVAL 11 MONTH)` (a February-start FY
   labelled by its ending year). 3a and 3c both confirmed BigQuery will not do month
   arithmetic on a TIMESTAMP, so `BigQueryDialect` routes it through `DATE`, which also
   changes the dimension's type from TIMESTAMP to DATE — which is why risk 4 has two
   different literal spellings (3e for DATE, 4b for TIMESTAMP).
4. **TRUNC result vs calendar literal** — affects every date-filtered condition-S query. 4a
   confirmed BigQuery will not compare TIMESTAMP to DATE at all. That is the *good* outcome:
   it fails loudly at compile time rather than silently matching nothing.
5. **Division by zero** — a **scoring** problem, not a syntax one. Condition S is already
   guarded by `NULLIF`; conditions U/D/G are not, because the model writes that SQL. 5a
   confirmed BigQuery raises where DuckDB 1.5.5 returns `inf` (measured — `SELECT 1.0/0` →
   `inf`, `SELECT 0.0/0` → `nan`). So the same unguarded model answer is scored as a wrong
   *number* on DuckDB and as an *error* on BigQuery. **Decide which bucket is intended before
   running the BigQuery arm**, or the two arms are not comparable. 5d shows `IEEE_DIVIDE` is
   available if the decision is to match DuckDB exactly.

## DuckDB baselines

Every "DuckDB baseline" in the `.sql` was measured on this repo's environment
(duckdb 1.5.5, `~/miniforge3/envs/grounded`), not recalled. Re-measure any of them with:

```bash
~/miniforge3/envs/grounded/bin/python -c \
  "import duckdb; print(duckdb.connect().execute(\"SELECT 1.0/0\").fetchall())"
```

If the DuckDB version pin ever moves, re-measure rather than trusting the comments — risk 5
in particular is version-sensitive.

## Regenerating the shipped shapes

The `[SHIPPED]` probes were taken from the compiler's actual output, not written by hand.
To confirm they still match after any change to `compiler/dialects.py`:

```bash
~/miniforge3/envs/grounded/bin/python - <<'EOF'
import sys; sys.path.insert(0, "compiler")
from compile import load_model, compile_plan
m = load_model("semantic_models/d1.yaml")
plans = {
  "scalar multi-measure (risk 1, probe 1a)": {"measures": ["net_revenue", "order_count"]},
  "scalar ratio measure (risk 5, probe 5b)": {"measures": ["aov"]},
  "grouped multi-measure (risk 1b)": {"measures": ["net_revenue", "order_count"],
                                      "dimensions": ["ship_region"]},
  "order_month + filter (risks 2, 4)": {"measures": ["net_revenue"],
        "dimensions": ["order_month"],
        "filters": [{"field": "order_month", "op": "=", "value": "2024-05"}]},
  "fiscal_year + filter (risk 3)": {"measures": ["net_revenue"],
        "dimensions": ["fiscal_year"],
        "filters": [{"field": "fiscal_year", "op": "=", "value": 2024}]},
}
for label, plan in plans.items():
    print("=" * 80); print(label)
    print(compile_plan(m, plan, dialect="bigquery:my-project.bench_d1")["sql"])
EOF
```

If that output stops matching a `[SHIPPED]` probe, update the probe — the point of those
probes is that they are the real emitted SQL, not an approximation of it.
