-- =====================================================================================
-- bq_dialect_spike.sql — BigQuery dialect risk spike for the semantic-layer benchmark port
-- =====================================================================================
--
-- PURPOSE
--   Empirically answer the five BigQuery-vs-DuckDB dialect risks the port rests on, BEFORE
--   any data is loaded. Every probe is self-contained: literal / synthetic rows via
--   UNNEST([...]). No tables, no datasets, no loaded warehouse. All this needs is a project
--   that can run a query.
--
--   These are not hypothetical risks any more. compiler/dialects.py (BigQueryDialect) has
--   ALREADY been written against assumed answers to all five, and its rewrites are what
--   condition S will emit. This script is the evidence for those assumptions. Where a probe
--   below reproduces the exact bytes BigQueryDialect emits, the probe is labelled
--   [SHIPPED SHAPE] — those are the ones that decide whether the BigQuery arm runs at all.
--   Those labels track the compiler and must be re-checked whenever dialects.py changes:
--   they moved once already, when probe 1a falsified the CROSS JOIN assumption and the
--   rewrite was removed (1a became shipped, 1d stopped being, 5b changed its join).
--
-- HOW TO RUN
--   See scripts/README-spike.md. One command, one submission, ~20 rows of output.
--
-- HOW IT IS BUILT (and why it looks like this)
--   Several probes are EXPECTED to be rejected by BigQuery — that rejection IS the result.
--   A rejected statement written inline would abort the whole script, so every probe is
--   submitted as a string through EXECUTE IMMEDIATE inside BEGIN ... EXCEPTION WHEN ERROR.
--   SQL inside a string literal is not analysed when the script is parsed, so a syntax, a
--   type-signature, or a runtime error all arrive as a catchable runtime error and are
--   recorded as a row instead of killing the run. Nothing here can abort the script.
--
--   Each probe's inner query returns exactly ONE row with exactly ONE STRING column, so the
--   same `EXECUTE IMMEDIATE ... INTO r` shape works for all of them.
--
-- HOW TO READ THE OUTPUT
--   The final SELECT prints one row per probe:
--     probe    — probe id, matching the sections below and the table in README-spike.md
--     name     — what is being tested
--     outcome  — 'RAN'   BigQuery accepted and executed it
--                'ERROR' BigQuery rejected it (its message is in `detail`)
--     detail   — on RAN: the value(s) produced, plus an in-query verdict wherever the
--                expected answer is known from DuckDB. On ERROR: BigQuery's own message.
--
--   Read `outcome` together with the PASS/FAIL comment above each probe. `outcome='RAN'` is
--   NOT automatically a pass: for 1a, 3a, 3c, 4a a successful run is the SURPRISING result
--   and means an assumption baked into compiler/dialects.py was unnecessary. Conversely
--   `outcome='ERROR'` on a [SHIPPED SHAPE] probe is a hard blocker.
--
-- DUCKDB BASELINES QUOTED BELOW
--   Every "DuckDB ... baseline" line was MEASURED on this repo's environment (duckdb 1.5.5,
--   ~/miniforge3/envs/grounded), not recalled. Re-measure any of them with:
--     ~/miniforge3/envs/grounded/bin/python -c \
--       "import duckdb; print(duckdb.connect().execute(\"<sql>\").fetchall())"
--   BigQuery behaviour is asserted NOWHERE in this file. That is what running it answers.
-- =====================================================================================

DECLARE r STRING;

CREATE TEMP TABLE spike_results (
  probe   STRING,
  name    STRING,
  outcome STRING,
  detail  STRING
);


-- =====================================================================================
-- RISK 1 — FULL OUTER JOIN (subquery) alias ON TRUE
-- =====================================================================================
-- THE CRITICAL ONE. The compiler builds one subquery per base measure and stitches them
-- together in Dialect.combine_measures (compiler/dialects.py):
--     on = " AND ".join(f"{left_alias}.{d} = {alias}.{d}" for d in dims) or "TRUE"
-- so whenever a plan has NO grouping dimensions — i.e. EVERY scalar multi-measure query —
-- the DuckDB arm emits literally `FULL OUTER JOIN (subquery) m1 ON TRUE`. BigQuery has
-- historically restricted FULL OUTER JOIN to equality predicates.
--
-- SETTLED BY THIS SPIKE (2026-09-08): probe 1a came back RAN. BigQuery ACCEPTS `ON TRUE`.
-- Its restriction is on non-equality predicates that reference BOTH sides of the join; the
-- constant TRUE references neither. An earlier BigQueryDialect.combine_measures override
-- substituted CROSS JOIN when `dims` was empty on the opposite assumption; that override
-- has been REMOVED, and 1a is now the probe that must pass for the BigQuery arm to produce
-- a single number at all. 1d and 1c are retained as evidence that the alternatives would
-- have worked, but neither reproduces compiler output any more.
-- =====================================================================================

-- ---------------------------------------------------------------------------
-- PROBE 1a — FULL OUTER JOIN ... ON TRUE   (the DuckDB arm's zero-dimension shape)
--   [SHIPPED] since the CROSS JOIN override was removed: this IS the zero-dimension shape
--   BigQueryDialect emits today, byte-for-byte modulo the leaf subqueries.
--   PASS (risk ABSENT):    outcome='RAN', detail='net_revenue=175.0 order_count=7 rows=1'
--         -> BigQuery accepts ON TRUE; both arms can share one join structure. MEASURED.
--   FAIL (risk CONFIRMED): outcome='ERROR', message about FULL OUTER JOIN requiring an
--         equality / equijoin predicate.
--         -> hard blocker: reinstate a CROSS JOIN branch in BigQueryDialect.combine_measures
--            (1d proves it works) and accept the divergence between the arms.
--   DuckDB 1.5.5 baseline: accepted; exactly one row, (175.0, 7).
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('net_revenue=%T order_count=%T rows=%T',
                  ANY_VALUE(net_revenue), ANY_VALUE(order_count), COUNT(*))
    FROM (
      SELECT m0.net_revenue, m1.order_count
      FROM      (SELECT SUM(v)   AS net_revenue FROM UNNEST([100.0, 50.0, 25.0]) AS v) m0
      FULL OUTER JOIN
                (SELECT COUNT(*) AS order_count FROM UNNEST([1,2,3,4,5,6,7])      AS v) m1
        ON TRUE
    )
  """ INTO r;
  INSERT INTO spike_results VALUES ('1a', '[SHIPPED] FULL OUTER JOIN (subquery) alias ON TRUE', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('1a', '[SHIPPED] FULL OUTER JOIN (subquery) alias ON TRUE', 'ERROR', @@error.message);
END;

-- ---------------------------------------------------------------------------
-- PROBE 1b — [SHIPPED SHAPE] FULL OUTER JOIN ... ON m0.dim = m1.dim
--   BigQueryDialect keeps the FULL OUTER JOIN untouched when dimensions are present, so
--   this is emitted verbatim for every grouped multi-measure query.
--   PASS: outcome='RAN' and detail='rows=3 both=1 left_only=1 right_only=1 dim_label_lost=1'
--         -> the equality form works AND, as in DuckDB, keeps non-matching groups from BOTH
--            sides. That retention is the whole point: a measure that has no value for a
--            group must not delete the group.
--   FAIL: outcome='ERROR'; or rows!=3; or left_only/right_only = 0, which would mean the
--         join silently degraded to INNER/LEFT and groups are being dropped. A silent
--         degradation is worse than an error — check these counts, not just `rows`.
--   DuckDB 1.5.5 baseline: 3 rows — ('EMEA',50.0,NULL), ('West',175.0,7), (NULL,NULL,3).
--
--   NOTE FOR THE REVIEWER — `dim_label_lost=1` is EXPECTED here and is NOT a dialect
--   difference; it reproduces identically in DuckDB, so it is a pre-existing compiler
--   issue, not a port regression. compile.py emits the output dimension as
--   `{alias_of_FIRST_measure}.{d} AS {d}`. For a group present only in the second subquery
--   m0.region is NULL, so the dimension LABEL is lost while its measure value survives.
--   The correct emit is COALESCE over every measure alias. Flagged here because the port is
--   when someone will next read this join; fixing it is out of scope for this spike.
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('rows=%T both=%T left_only=%T right_only=%T dim_label_lost=%T',
                  COUNT(*),
                  COUNTIF(r0 IS NOT NULL AND r1 IS NOT NULL),
                  COUNTIF(r1 IS NULL),
                  COUNTIF(r0 IS NULL),
                  COUNTIF(r0 IS NULL))
    FROM (
      SELECT m0.region AS r0, m1.region AS r1
      FROM (
        SELECT region, SUM(v) AS net_revenue
        FROM UNNEST([STRUCT('West' AS region, 100.0 AS v),
                     STRUCT('West' AS region,  75.0 AS v),
                     STRUCT('EMEA' AS region,  50.0 AS v)])
        GROUP BY region
      ) m0
      FULL OUTER JOIN (
        SELECT region, COUNT(*) AS order_count
        FROM UNNEST([STRUCT('West' AS region), STRUCT('West' AS region), STRUCT('West' AS region),
                     STRUCT('West' AS region), STRUCT('West' AS region), STRUCT('West' AS region),
                     STRUCT('West' AS region),
                     STRUCT('APAC' AS region), STRUCT('APAC' AS region), STRUCT('APAC' AS region)])
        GROUP BY region
      ) m1
        ON m0.region = m1.region
    )
  """ INTO r;
  INSERT INTO spike_results VALUES ('1b', '[SHIPPED] FULL OUTER JOIN ON dim equality', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('1b', '[SHIPPED] FULL OUTER JOIN ON dim equality', 'ERROR', @@error.message);
END;

-- ---------------------------------------------------------------------------
-- PROBE 1c — FULL OUTER JOIN ... ON 1 = 1   (a cheaper patch than CROSS JOIN, if 1a fails)
--   Only interesting if 1a FAILED. `1=1` IS an equality predicate but not one over fields,
--   so this separates a syntactic restriction (an equality operator must be present) from a
--   semantic one (it must equate columns from both inputs).
--   PASS: outcome='RAN', detail='net_revenue=175.0 order_count=7 rows=1'
--         -> the restriction is syntactic. A one-token alternative to the CROSS JOIN branch
--            exists. Prefer CROSS JOIN anyway — it states the intent — but record this.
--   FAIL: outcome='ERROR' -> the restriction is semantic; CROSS JOIN (1d) is the only route.
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('net_revenue=%T order_count=%T rows=%T',
                  ANY_VALUE(net_revenue), ANY_VALUE(order_count), COUNT(*))
    FROM (
      SELECT m0.net_revenue, m1.order_count
      FROM      (SELECT SUM(v)   AS net_revenue FROM UNNEST([100.0, 50.0, 25.0]) AS v) m0
      FULL OUTER JOIN
                (SELECT COUNT(*) AS order_count FROM UNNEST([1,2,3,4,5,6,7])      AS v) m1
        ON 1 = 1
    )
  """ INTO r;
  INSERT INTO spike_results VALUES ('1c', 'FULL OUTER JOIN ON 1 = 1 (alternative patch)', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('1c', 'FULL OUTER JOIN ON 1 = 1 (alternative patch)', 'ERROR', @@error.message);
END;

-- ---------------------------------------------------------------------------
-- PROBE 1d — CROSS JOIN   (the zero-dimension rewrite that WAS shipped, now removed)
--   NOT the shipped shape any more. BigQueryDialect.combine_measures used to emit this when
--   `dims` was empty; probe 1a showed the rewrite was never necessary and it was removed, so
--   the shipped zero-dimension shape is 1a's `ON TRUE`. Kept as standing evidence that the
--   fallback works, should 1a ever start failing on a future BigQuery.
--   Why the substitution is correct and not merely convenient: with zero grouping
--   dimensions each subquery is an UNGROUPED aggregate, so each returns exactly one row
--   (possibly all-NULL) and never zero. A FULL OUTER JOIN of two guaranteed-single-row
--   inputs is the same relation as their cartesian product.
--   PASS: outcome='RAN', detail='net_revenue=175.0 order_count=7 rows=1'
--   FAIL: outcome='ERROR', or rows!=1 -> the fallback is gone too. Not a blocker on its own
--         (1a is what ships), but it would mean there is no way back if 1a ever regresses.
--   SCOPE WARNING: this equivalence holds ONLY for the dims-empty case. CROSS JOIN is wrong
--   when dimensions are present — there the equijoin in 1b is required.
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('net_revenue=%T order_count=%T rows=%T',
                  ANY_VALUE(net_revenue), ANY_VALUE(order_count), COUNT(*))
    FROM (
      SELECT m0.net_revenue, m1.order_count
      FROM      (SELECT SUM(v)   AS net_revenue FROM UNNEST([100.0, 50.0, 25.0]) AS v) m0
      CROSS JOIN
                (SELECT COUNT(*) AS order_count FROM UNNEST([1,2,3,4,5,6,7])      AS v) m1
    )
  """ INTO r;
  INSERT INTO spike_results VALUES ('1d', 'CROSS JOIN (former zero-dimension rewrite, no longer shipped)', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('1d', 'CROSS JOIN (former zero-dimension rewrite, no longer shipped)', 'ERROR', @@error.message);
END;


-- =====================================================================================
-- RISK 2 — TIMESTAMP_TRUNC(ts, MONTH)  vs  DuckDB date_trunc('month', ts)
-- =====================================================================================
-- semantic_models/d1.yaml:
--     order_month: date_trunc('month', orders.order_ts)
--     order_year:  date_trunc('year',  orders.order_ts)
-- orders.order_ts is TIMESTAMP (warehouse/d1/orders.parquet stores timestamp[ns]), so
-- BigQueryDialect._trunc_call emits TIMESTAMP_TRUNC — verified by compiling a real plan:
--     TIMESTAMP_TRUNC(orders.order_ts, MONTH) AS order_month
-- This probe checks that rewrite is value-for-value equivalent, at boundaries included.
-- =====================================================================================

-- ---------------------------------------------------------------------------
-- PROBE 2a — [SHIPPED SHAPE] TIMESTAMP_TRUNC(ts, MONTH) and (ts, YEAR) equivalence
--   PASS: outcome='RAN' and detail ends with 'all_match=true'
--         -> TIMESTAMP_TRUNC is a faithful drop-in; the name rewrite is the whole change.
--   FAIL: outcome='ERROR', or detail ends with 'all_match=false'. The per-row values are
--         printed before the verdict, so the diverging input is visible.
--   DuckDB 1.5.5 baselines (measured):
--     month: 2024-05-17 13:45:09        -> 2024-05-01 00:00:00
--            2024-01-01 00:00:00        -> 2024-01-01 00:00:00   (already on a boundary)
--            2024-12-31 23:59:59.999999 -> 2024-12-01 00:00:00   (last microsecond of a year)
--     year:  2024-05-17 13:45:09        -> 2024-01-01 00:00:00
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('%s || all_match=%T',
                  STRING_AGG(line, ' | ' ORDER BY ts),
                  LOGICAL_AND(got_month = expect_month AND got_year = expect_year))
    FROM (
      SELECT ts, expect_month, expect_year,
             TIMESTAMP_TRUNC(ts, MONTH) AS got_month,
             TIMESTAMP_TRUNC(ts, YEAR)  AS got_year,
             FORMAT('%T->m:%T,y:%T', ts,
                    TIMESTAMP_TRUNC(ts, MONTH), TIMESTAMP_TRUNC(ts, YEAR)) AS line
      FROM UNNEST([
        STRUCT(TIMESTAMP '2024-05-17 13:45:09'        AS ts,
               TIMESTAMP '2024-05-01 00:00:00'        AS expect_month,
               TIMESTAMP '2024-01-01 00:00:00'        AS expect_year),
        STRUCT(TIMESTAMP '2024-01-01 00:00:00'        AS ts,
               TIMESTAMP '2024-01-01 00:00:00'        AS expect_month,
               TIMESTAMP '2024-01-01 00:00:00'        AS expect_year),
        STRUCT(TIMESTAMP '2024-12-31 23:59:59.999999' AS ts,
               TIMESTAMP '2024-12-01 00:00:00'        AS expect_month,
               TIMESTAMP '2024-01-01 00:00:00'        AS expect_year)
      ])
    )
  """ INTO r;
  INSERT INTO spike_results VALUES ('2a', '[SHIPPED] TIMESTAMP_TRUNC == DuckDB date_trunc', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('2a', '[SHIPPED] TIMESTAMP_TRUNC == DuckDB date_trunc', 'ERROR', @@error.message);
END;

-- ---------------------------------------------------------------------------
-- PROBE 2b — the UTC assumption underneath 2a  (INFORMATIONAL — record it, do not "fix" it)
--   DuckDB TIMESTAMP is timezone-naive; BigQuery TIMESTAMP is an absolute instant and
--   TIMESTAMP_TRUNC truncates in UTC unless given a timezone argument. 2a therefore holds
--   only because the parquet load leaves the values UTC and the generated SQL never passes a
--   timezone. This probe makes that dependency visible and testable instead of implicit.
--   PASS: outcome='RAN' and detail ends with 'differ=true'
--         -> assumption confirmed AND load-bearing: never let a timezone argument into
--            generated SQL, and load the parquet timestamps as UTC.
--   FAIL: outcome='ERROR' (unexpected); or 'differ=false', which means the chosen input was
--         not actually near a boundary and the probe proved nothing — pick another input.
--   (2024-05-01 00:30:00 UTC is 2024-04-30 20:30 in America/Toronto, so the Toronto-truncated
--    month is April while the UTC-truncated month is May.)
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('input=%T utc=%T toronto=%T differ=%T',
                  ts,
                  TIMESTAMP_TRUNC(ts, MONTH),
                  TIMESTAMP_TRUNC(ts, MONTH, 'America/Toronto'),
                  TIMESTAMP_TRUNC(ts, MONTH) != TIMESTAMP_TRUNC(ts, MONTH, 'America/Toronto'))
    FROM (SELECT TIMESTAMP '2024-05-01 00:30:00' AS ts)
  """ INTO r;
  INSERT INTO spike_results VALUES ('2b', 'TIMESTAMP_TRUNC timezone sensitivity (UTC assumption)', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('2b', 'TIMESTAMP_TRUNC timezone sensitivity (UTC assumption)', 'ERROR', @@error.message);
END;


-- =====================================================================================
-- RISK 3 — fiscal year:  date_trunc('year', ts + INTERVAL 11 MONTH)
-- =====================================================================================
-- semantic_models/d1.yaml:
--     fiscal_year: date_trunc('year', orders.order_ts + INTERVAL 11 MONTH)
-- A February-start fiscal year labelled by its ENDING calendar year: +11 months pushes
-- Feb-2024 into Jan-2025, so FY2025 = Feb 2024 .. Jan 2025.
--
-- BigQueryDialect._interval assumes BigQuery cannot add a MONTH interval to a TIMESTAMP at
-- all and routes through DATE. Compiling the real plan confirms what ships:
--     DATE_TRUNC(DATE_ADD(DATE(orders.order_ts), INTERVAL 11 MONTH), YEAR) AS fiscal_year
-- Note the result type changes from TIMESTAMP (DuckDB) to DATE — which is why the filter
-- literal for fiscal_year stays `DATE '...'` while order_month's becomes `TIMESTAMP '...'`.
-- =====================================================================================

-- ---------------------------------------------------------------------------
-- PROBE 3a — TIMESTAMP + INTERVAL 11 MONTH   (the DuckDB expression, verbatim)
--   PASS (risk CONFIRMED — the expected result): outcome='ERROR', typically a
--         "No matching signature for operator +" or an interval-month-part message.
--         -> BigQueryDialect._interval's DATE detour is justified and load-bearing.
--   FAIL (risk ABSENT): outcome='RAN'. Do NOT read this as "nothing to do". Check the
--         VALUE in detail against the DuckDB baseline first — BigQuery could accept the
--         syntax and still land on a different instant, which would be the worst case
--         (silently different fiscal-year buckets rather than a loud error).
--   DuckDB 1.5.5 baseline: TIMESTAMP '2024-02-01 00:00:00' + INTERVAL 11 MONTH
--                          -> 2025-01-01 00:00:00
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('shifted=%T duckdb_baseline=2025-01-01_00:00:00 matches=%T', v,
                  v = TIMESTAMP '2025-01-01 00:00:00')
    FROM (SELECT TIMESTAMP '2024-02-01 00:00:00' + INTERVAL 11 MONTH AS v)
  """ INTO r;
  INSERT INTO spike_results VALUES ('3a', 'TIMESTAMP + INTERVAL 11 MONTH (expect rejection)', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('3a', 'TIMESTAMP + INTERVAL 11 MONTH (expect rejection)', 'ERROR', @@error.message);
END;

-- ---------------------------------------------------------------------------
-- PROBE 3b — [SHIPPED SHAPE] DATE_TRUNC(DATE_ADD(DATE(ts), INTERVAL 11 MONTH), YEAR)
--   The exact fiscal_year expression BigQueryDialect emits. Four inputs pin the FY boundary
--   from both sides, so an off-by-one-month rewrite cannot pass by accident.
--   PASS: outcome='RAN' and detail ends with 'all_match=true'
--         -> the rewrite reproduces DuckDB's fiscal_year bucket-for-bucket.
--   FAIL: outcome='ERROR', or 'all_match=false' — per-row values are printed, so the
--         offending boundary is visible. A boundary-only mismatch is the dangerous case:
--         totals stay plausible while a month's revenue lands in the wrong fiscal year.
--   DuckDB 1.5.5 baselines (measured), date_trunc('year', ts + INTERVAL 11 MONTH):
--     2024-01-31 23:59:59 -> 2024-01-01   (Jan is still the LAST month of FY2024)
--     2024-02-01 00:00:00 -> 2025-01-01   (first day of FY2025)
--     2024-12-31 00:00:00 -> 2025-01-01
--     2025-01-31 00:00:00 -> 2025-01-01   (last day of FY2025)
--   TYPE NOTE: DuckDB yields TIMESTAMP here, this rewrite yields DATE. That is the right
--   call (d1.yaml types the dimension `date`), but it is exactly why RISK 4 splits into two
--   literal spellings — see 4b (order_month, TIMESTAMP) vs 3e (fiscal_year, DATE).
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('%s || all_match=%T',
                  STRING_AGG(line, ' | ' ORDER BY ts),
                  LOGICAL_AND(got = expect))
    FROM (
      SELECT ts, expect,
             DATE_TRUNC(DATE_ADD(DATE(ts), INTERVAL 11 MONTH), YEAR) AS got,
             FORMAT('%T->%T', ts,
                    DATE_TRUNC(DATE_ADD(DATE(ts), INTERVAL 11 MONTH), YEAR)) AS line
      FROM UNNEST([
        STRUCT(TIMESTAMP '2024-01-31 23:59:59' AS ts, DATE '2024-01-01' AS expect),
        STRUCT(TIMESTAMP '2024-02-01 00:00:00' AS ts, DATE '2025-01-01' AS expect),
        STRUCT(TIMESTAMP '2024-12-31 00:00:00' AS ts, DATE '2025-01-01' AS expect),
        STRUCT(TIMESTAMP '2025-01-31 00:00:00' AS ts, DATE '2025-01-01' AS expect)
      ])
    )
  """ INTO r;
  INSERT INTO spike_results VALUES ('3b', '[SHIPPED] fiscal_year via DATE_ADD(DATE(ts), 11 MONTH)', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('3b', '[SHIPPED] fiscal_year via DATE_ADD(DATE(ts), 11 MONTH)', 'ERROR', @@error.message);
END;

-- ---------------------------------------------------------------------------
-- PROBE 3c — TIMESTAMP_ADD(ts, INTERVAL 11 MONTH)   (the "obvious" translation)
--   Probed so the port note can say the obvious substitution was tried, and why it is not
--   the answer. TIMESTAMP_ADD is documented to accept MICROSECOND..DAY parts only, which is
--   the assumption encoded in BigQueryDialect._BQ_TS_INTERVAL_UNITS.
--   PASS (expected): outcome='ERROR' naming MONTH as an unsupported date part
--         -> _BQ_TS_INTERVAL_UNITS is correct; 3b stands as the rewrite.
--   FAIL: outcome='RAN' -> a second viable route exists and _BQ_TS_INTERVAL_UNITS is too
--         narrow. Compare its value to 3a's DuckDB baseline (2025-01-01 00:00:00) before
--         preferring it — a TIMESTAMP-preserving route would avoid the DATE type change,
--         which would in turn simplify RISK 4.
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('shifted=%T', TIMESTAMP_ADD(TIMESTAMP '2024-02-01 00:00:00', INTERVAL 11 MONTH))
  """ INTO r;
  INSERT INTO spike_results VALUES ('3c', 'TIMESTAMP_ADD(..., INTERVAL 11 MONTH) (expect rejection)', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('3c', 'TIMESTAMP_ADD(..., INTERVAL 11 MONTH) (expect rejection)', 'ERROR', @@error.message);
END;

-- ---------------------------------------------------------------------------
-- PROBE 3d — month-end clamping in DATE_ADD   (does month arithmetic agree at month ends?)
--   Irrelevant to fiscal_year itself, since a YEAR truncation erases the day — but month
--   arithmetic at month ends is the one place two engines silently disagree, and any future
--   month-shift dimension would inherit it. Recorded now so nobody re-derives it later.
--   PASS: outcome='RAN' and detail ends with 'all_match=true'
--         -> BigQuery clamps to the last valid day exactly as DuckDB does.
--   FAIL: 'all_match=false' -> month arithmetic diverges at month ends; any month-shift
--         dimension beyond fiscal_year needs its own translation note and its own test.
--   DuckDB 1.5.5 baselines (measured):
--     2024-03-31 09:00:00 + 11 MONTH -> 2025-02-28   (clamped; 2025 is not a leap year)
--     2023-03-29 00:00:00 + 11 MONTH -> 2024-02-29   (leap day reachable)
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('%s || all_match=%T',
                  STRING_AGG(line, ' | ' ORDER BY ts),
                  LOGICAL_AND(got = expect))
    FROM (
      SELECT ts, expect,
             DATE_ADD(DATE(ts), INTERVAL 11 MONTH) AS got,
             FORMAT('%T->%T', ts, DATE_ADD(DATE(ts), INTERVAL 11 MONTH)) AS line
      FROM UNNEST([
        STRUCT(TIMESTAMP '2024-03-31 09:00:00' AS ts, DATE '2025-02-28' AS expect),
        STRUCT(TIMESTAMP '2023-03-29 00:00:00' AS ts, DATE '2024-02-29' AS expect)
      ])
    )
  """ INTO r;
  INSERT INTO spike_results VALUES ('3d', 'DATE_ADD month-end clamping == DuckDB', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('3d', 'DATE_ADD month-end clamping == DuckDB', 'ERROR', @@error.message);
END;

-- ---------------------------------------------------------------------------
-- PROBE 3e — [SHIPPED SHAPE] the fiscal_year WHERE-clause predicate
--   BigQueryDialect.date_predicate types the literal to match the column, and since 3b makes
--   fiscal_year DATE-typed the emitted filter is (verified by compiling a real plan):
--     DATE_TRUNC(DATE_ADD(DATE(orders.order_ts), INTERVAL 11 MONTH), YEAR) = DATE '2024-01-01'
--   DATE = DATE, so this should be the easy half of RISK 4 — but it is only easy BECAUSE of
--   the type change in 3b, so it needs its own confirmation rather than an inference.
--   PASS: outcome='RAN' and detail='matched=1 of 4' -> exactly the one FY2024 input matches
--         (2024-01-31, the last month of FY2024). Types line up; no cast needed.
--   FAIL: outcome='ERROR' (a type mismatch, meaning date_predicate's literal choice is
--         wrong for the DATE branch); or 'matched=0 of 4', which would mean it compiles and
--         silently matches nothing — the dangerous failure, since it looks like "no data".
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('matched=%T of %T', COUNTIF(hit), COUNT(*))
    FROM (
      SELECT DATE_TRUNC(DATE_ADD(DATE(ts), INTERVAL 11 MONTH), YEAR) = DATE '2024-01-01' AS hit
      FROM UNNEST([TIMESTAMP '2024-01-31 23:59:59',
                   TIMESTAMP '2024-02-01 00:00:00',
                   TIMESTAMP '2024-12-31 00:00:00',
                   TIMESTAMP '2025-01-31 00:00:00']) AS ts
    )
  """ INTO r;
  INSERT INTO spike_results VALUES ('3e', '[SHIPPED] fiscal_year filter vs DATE literal', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('3e', '[SHIPPED] fiscal_year filter vs DATE literal', 'ERROR', @@error.message);
END;


-- =====================================================================================
-- RISK 4 — comparing a TRUNC result against a calendar literal
-- =====================================================================================
-- compile.py routes every `date`-typed dimension filter through Dialect.date_predicate.
-- The identity (DuckDB) dialect emits `{dim_sql} {op} DATE '{iso}'`, which for order_month
-- is:
--     date_trunc('month', orders.order_ts) = DATE '2024-05-01'     -- TIMESTAMP vs DATE
-- DuckDB 1.5.5 accepts that via an implicit cast and returns TRUE. BigQuery does not
-- implicitly cast between TIMESTAMP and DATE in a comparison.
--
-- BigQueryDialect.date_predicate assumes this and types the literal to the column's type.
-- Compiling a real plan confirms the shipped emit for order_month is:
--     TIMESTAMP_TRUNC(orders.order_ts, MONTH) = TIMESTAMP '2024-05-01'
-- Note the literal has NO time component — a date-shaped string in a TIMESTAMP literal.
-- Probe 4b tests those exact bytes; do not assume it is interchangeable with 4c.
--
-- If this is wrong, EVERY date-filtered condition-S query is affected — most of the
-- time-sliced suite, not an edge case.
-- =====================================================================================

-- ---------------------------------------------------------------------------
-- PROBE 4a — TIMESTAMP_TRUNC(ts, MONTH) = DATE '2024-05-01'   (pre-dialect emit)
--   PASS (risk CONFIRMED — expected): outcome='ERROR', typically
--         "No matching signature for operator = for argument types: TIMESTAMP, DATE".
--         -> BigQueryDialect.date_predicate's typed-literal logic is load-bearing.
--   FAIL (risk ABSENT): outcome='RAN' with 'eq=true' -> BigQuery casts implicitly and the
--         typed-literal logic is belt-and-braces. If it RAN with 'eq=false', that is the
--         WORST outcome available in this whole script: the comparison compiles, matches
--         nothing, and every date-filtered query silently returns empty. Treat as a blocker.
--   DuckDB 1.5.5 baseline: accepted, returns TRUE.
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('eq=%T',
                  TIMESTAMP_TRUNC(TIMESTAMP '2024-05-17 13:45:09', MONTH) = DATE '2024-05-01')
  """ INTO r;
  INSERT INTO spike_results VALUES ('4a', 'TIMESTAMP_TRUNC = DATE literal, uncast (expect rejection)', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('4a', 'TIMESTAMP_TRUNC = DATE literal, uncast (expect rejection)', 'ERROR', @@error.message);
END;

-- ---------------------------------------------------------------------------
-- PROBE 4b — [SHIPPED SHAPE] TIMESTAMP_TRUNC(ts, MONTH) = TIMESTAMP '2024-05-01'
--   The exact order_month filter BigQueryDialect emits, date-shaped literal and all.
--   Two things are under test at once: that TIMESTAMP=TIMESTAMP compares, and that a
--   TIMESTAMP literal written without a time component is accepted and means midnight UTC.
--   PASS: outcome='RAN' and detail='eq_shipped=true eq_explicit_time=true both_agree=true'
--         -> the shipped predicate is correct as written.
--   FAIL: outcome='ERROR' -> date-filtered condition-S queries do not run; hard blocker.
--         Or 'eq_shipped=false' while 'eq_explicit_time=true' -> the bare-date TIMESTAMP
--         literal is the problem, not the comparison: change date_predicate to emit
--         `TIMESTAMP '<iso> 00:00:00'`. That is a one-line fix, but only this probe
--         distinguishes it from a wholesale type failure.
--   DuckDB 1.5.5 baseline for the equivalent comparison: TRUE.
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('eq_shipped=%T eq_explicit_time=%T both_agree=%T', a, b, a = b)
    FROM (
      SELECT TIMESTAMP_TRUNC(TIMESTAMP '2024-05-17 13:45:09', MONTH) = TIMESTAMP '2024-05-01' AS a,
             TIMESTAMP_TRUNC(TIMESTAMP '2024-05-17 13:45:09', MONTH) = TIMESTAMP '2024-05-01 00:00:00' AS b
    )
  """ INTO r;
  INSERT INTO spike_results VALUES ('4b', '[SHIPPED] TIMESTAMP_TRUNC = TIMESTAMP literal', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('4b', '[SHIPPED] TIMESTAMP_TRUNC = TIMESTAMP literal', 'ERROR', @@error.message);
END;

-- ---------------------------------------------------------------------------
-- PROBE 4c — DATE(TIMESTAMP_TRUNC(ts, MONTH)) = DATE '2024-05-01'   (the road not taken)
--   The alternative fix: cast the COLUMN to DATE and keep a DATE literal everywhere, rather
--   than typing the literal to the column. It would make all three date dimensions DATE and
--   remove the two-spellings split between 3e and 4b. Recorded as a fallback if 4b fails,
--   and as the answer to "why wasn't it done this way?".
--   PASS: outcome='RAN' and detail='eq=true' -> viable fallback; adopt only if 4b fails.
--   FAIL: outcome='ERROR' or 'eq=false' -> not viable; if 4b also failed, escalate.
--   Cost note: wrapping the column in yet another function is no worse than the TRUNC
--   already there, but neither form prunes partitions — see 4d.
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('eq=%T',
                  DATE(TIMESTAMP_TRUNC(TIMESTAMP '2024-05-17 13:45:09', MONTH)) = DATE '2024-05-01')
  """ INTO r;
  INSERT INTO spike_results VALUES ('4c', 'DATE(TIMESTAMP_TRUNC(...)) = DATE literal (fallback)', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('4c', 'DATE(TIMESTAMP_TRUNC(...)) = DATE literal (fallback)', 'ERROR', @@error.message);
END;

-- ---------------------------------------------------------------------------
-- PROBE 4d — half-open range instead of equality   (sargable form)
--   `ts >= TIMESTAMP '2024-05-01' AND ts < TIMESTAMP '2024-06-01'` leaves the column bare,
--   so it can prune partitions where 4b and 4c cannot. This probe checks CORRECTNESS only —
--   the synthetic row is not partitioned, so the pruning benefit is a separate measurement
--   against a real partitioned table, and this probe does not and cannot demonstrate it.
--   PASS: outcome='RAN' and detail='in_range=true agrees_with_trunc=true'
--         -> a valid, and on real tables cheaper, emit for `=` on a date dimension IF anyone
--            later wants it. It covers `=` only; other operators need their own range logic.
--   FAIL: outcome='ERROR', or 'agrees_with_trunc=false' -> not equivalent; drop the idea.
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('in_range=%T agrees_with_trunc=%T', in_range,
                  in_range = (TIMESTAMP_TRUNC(ts, MONTH) = TIMESTAMP '2024-05-01'))
    FROM (
      SELECT ts, (ts >= TIMESTAMP '2024-05-01' AND ts < TIMESTAMP '2024-06-01') AS in_range
      FROM (SELECT TIMESTAMP '2024-05-17 13:45:09' AS ts)
    )
  """ INTO r;
  INSERT INTO spike_results VALUES ('4d', 'half-open range == TRUNC equality (sargable form)', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('4d', 'half-open range == TRUNC equality (sargable form)', 'ERROR', @@error.message);
END;


-- =====================================================================================
-- RISK 5 — division by zero
-- =====================================================================================
-- compile.py already guards every ratio measure, and no dialect hook touches it:
--     ({num_alias}.{num} * 1.0 / NULLIF({den_alias}.{den}, 0)) AS {mname}
-- so condition S should be safe on both engines. The exposure is conditions U/D/G, where
-- the MODEL writes the SQL and will sometimes divide without a guard.
--
-- IMPORTANT CORRECTION TO THE STATED RISK. This was framed to me as "BigQuery raises where
-- DuckDB returns NULL". That is NOT what DuckDB 1.5.5 in this repo's environment does.
-- Measured, not recalled:
--     SELECT 1/0    -> inf      SELECT 1.0/0 -> inf
--     SELECT -1.0/0 -> -inf     SELECT 0.0/0 -> nan
--     SELECT 100 * 1.0 / NULLIF(0,0) -> NULL
-- DuckDB returns IEEE infinity, NOT NULL. (Some older DuckDB releases differed; if the
-- version pin ever moves, re-measure rather than trusting this comment.)
--
-- That makes the divergence WORSE than described, and it is a SCORING problem, not just a
-- syntax one: an unguarded division in a U/D/G answer yields `inf` on DuckDB — a value,
-- scored as a wrong number — while on BigQuery the same SQL is expected to abort the query,
-- scored as an error. Identical model output lands in a different scoring bucket purely
-- because of the engine. Decide and document which bucket is intended BEFORE running the
-- BigQuery arm, or the two arms are not comparable and the cross-engine claim is unsupported.
-- =====================================================================================

-- ---------------------------------------------------------------------------
-- PROBE 5a — unguarded division by a zero that comes from data, not a folded constant
--   Driven from UNNEST so this is a genuine runtime division rather than something the
--   planner can constant-fold and reject (or accept) at analysis time.
--   PASS (risk CONFIRMED — expected): outcome='ERROR', typically "division by zero".
--         -> unguarded model SQL becomes a hard query failure on BigQuery. Write down the
--            scoring rule for it (see the block comment above) before running the arm.
--   FAIL (risk ABSENT): outcome='RAN'. Read the value: 'result=inf' means BigQuery matches
--         DuckDB and there is nothing to reconcile; 'result=NULL' means the engines still
--         disagree, just in the other direction, and scoring still needs a decision.
--   DuckDB 1.5.5 baseline: inf, no error.
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('result=%T', ANY_VALUE(num / den))
    FROM UNNEST([STRUCT(100.0 AS num, 0.0 AS den)])
  """ INTO r;
  INSERT INTO spike_results VALUES ('5a', 'unguarded x/0 from data (expect BQ error)', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('5a', 'unguarded x/0 from data (expect BQ error)', 'ERROR', @@error.message);
END;

-- ---------------------------------------------------------------------------
-- PROBE 5b — [SHIPPED SHAPE] the compiler's NULLIF guard, in its BigQuery join shape
--   Exactly what compile.py + BigQueryDialect emit for a ratio measure with no grouping
--   dimensions: the guard, inside the `FULL OUTER JOIN ... ON TRUE` from 1a. This probe
--   used CROSS JOIN while BigQueryDialect still rewrote the join; that rewrite was removed
--   after 1a came back RAN, so the shipped shape is the one below. Verified against
--   `compile_plan(m, {"measures": ["aov"]}, dialect="bigquery:...")`.
--   PASS: outcome='RAN' and detail='result=NULL'
--         -> the existing guard ports unchanged; condition S needs no division work at all.
--   FAIL: outcome='ERROR' with a division-by-zero message -> NULLIF does not short-circuit
--         the division as assumed, and the guard must be rewritten (SAFE_DIVIDE, 5c).
--         outcome='ERROR' with a join message -> that is RISK 1, not RISK 5; see 1a.
--   DuckDB 1.5.5 baseline for the same expression: NULL.
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('result=%T', m0.net_revenue * 1.0 / NULLIF(m1.order_count, 0))
    FROM            (SELECT SUM(v) AS net_revenue FROM UNNEST([100.0, 75.0]) AS v) m0
    FULL OUTER JOIN (SELECT COUNTIF(FALSE) AS order_count FROM UNNEST([1,2,3]) AS v) m1
      ON TRUE
  """ INTO r;
  INSERT INTO spike_results VALUES ('5b', '[SHIPPED] NULLIF ratio guard in FULL OUTER JOIN ON TRUE shape', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('5b', '[SHIPPED] NULLIF ratio guard in FULL OUTER JOIN ON TRUE shape', 'ERROR', @@error.message);
END;

-- ---------------------------------------------------------------------------
-- PROBE 5c — SAFE_DIVIDE   (BigQuery-native NULL-on-zero)
--   PASS: outcome='RAN' and detail='result=NULL' -> available as an alternative guard.
--         Equivalent to the NULLIF form's RESULT, but NOT to DuckDB's raw `/` (inf).
--         Switch to it only if 5b fails; switching otherwise is churn that breaks the
--         byte-for-byte correspondence between the two arms' generated SQL.
--   FAIL: outcome='ERROR' (would be astonishing; escalate).
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('result=%T', ANY_VALUE(SAFE_DIVIDE(num, den)))
    FROM UNNEST([STRUCT(100.0 AS num, 0.0 AS den)])
  """ INTO r;
  INSERT INTO spike_results VALUES ('5c', 'SAFE_DIVIDE(x, 0) -> NULL', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('5c', 'SAFE_DIVIDE(x, 0) -> NULL', 'ERROR', @@error.message);
END;

-- ---------------------------------------------------------------------------
-- PROBE 5d — IEEE_DIVIDE   (BigQuery-native inf-on-zero)
--   The only BigQuery construct expected to reproduce DuckDB 1.5.5's raw `/` semantics.
--   Relevant only if the port must be numerically comparable with the DuckDB arm rather
--   than merely "both refuse". Recorded as an option, not a recommendation.
--   PASS: outcome='RAN' and detail='result=inf' (BigQuery may render it 'inf' or 'Infinity';
--         either counts) -> a DuckDB-identical division exists, so bit-comparability is an
--         available scoring rule for the U/D/G arms.
--   FAIL: outcome='ERROR', or a NULL/0 result -> no DuckDB-identical option; the scoring
--         rule must reconcile the engines some other way (e.g. normalise inf and hard
--         errors into the same bucket in score/score.py).
--   DuckDB 1.5.5 baseline for raw `/`: inf.
-- ---------------------------------------------------------------------------
BEGIN
  EXECUTE IMMEDIATE """
    SELECT FORMAT('result=%T', ANY_VALUE(IEEE_DIVIDE(num, den)))
    FROM UNNEST([STRUCT(100.0 AS num, 0.0 AS den)])
  """ INTO r;
  INSERT INTO spike_results VALUES ('5d', 'IEEE_DIVIDE(x, 0) -> inf (DuckDB-identical option)', 'RAN', r);
EXCEPTION WHEN ERROR THEN
  INSERT INTO spike_results VALUES ('5d', 'IEEE_DIVIDE(x, 0) -> inf (DuckDB-identical option)', 'ERROR', @@error.message);
END;


-- =====================================================================================
-- RESULTS — the only statement that returns rows, so `bq query` prints exactly this.
-- =====================================================================================
SELECT probe, name, outcome, detail
FROM spike_results
ORDER BY probe;
