#!/usr/bin/env python3
"""Self-test for compiler/dialects.py. No test framework needed:

    python compiler/test_dialects.py

The stored condition-S plans exercise only the expressions the shipped models happen to
contain. These cases cover the edges around them — the ones that decide whether a future
model change gets translated correctly or blows up loudly instead of silently emitting
SQL that BigQuery would reject.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import compile as C          # noqa: E402
from dialects import (       # noqa: E402
    DUCKDB, BigQueryDialect, Dialect, DialectError, dim_ref, get_dialect,
)

BQ = BigQueryDialect("my-proj", "d1")

TS_MONTH = "date_trunc('month', orders.order_ts)"
TS_YEAR = "date_trunc('year', orders.order_ts)"
FISCAL = "date_trunc('year', orders.order_ts + INTERVAL 11 MONTH)"

_fails = []


def eq(got, want, label):
    if got != want:
        _fails.append(f"{label}\n     got: {got!r}\n    want: {want!r}")


def raises(fn, label, needle=None):
    try:
        got = fn()
    except DialectError as e:
        if needle and needle.lower() not in str(e).lower():
            _fails.append(f"{label}: DialectError raised but message lacks {needle!r}: {e}")
        return
    _fails.append(f"{label}: expected DialectError, got {got!r}")


# ---------------------------------------------------------------- DuckDB is the identity
eq(DUCKDB.name, "duckdb", "duckdb name")
eq(DUCKDB.table_ref("orders"), "orders", "duckdb table_ref")
eq(DUCKDB.expr(FISCAL), FISCAL, "duckdb expr is identity")
eq(DUCKDB.date_predicate(TS_MONTH, "=", "2024-05-01"),
   "date_trunc('month', orders.order_ts) = DATE '2024-05-01'", "duckdb date_predicate")
eq(DUCKDB.combine_measures("m0", [], "SELECT 1", "m1"),
   "\nFULL OUTER JOIN (SELECT 1) m1 ON TRUE", "duckdb cartesian join")
eq(DUCKDB.combine_measures("m0", ["a", "b"], "SELECT 1", "m1"),
   "\nFULL OUTER JOIN (SELECT 1) m1 ON m0.a = m1.a AND m0.b = m1.b", "duckdb equi join")
eq(get_dialect(None) is DUCKDB and get_dialect("duckdb") is DUCKDB, True, "get_dialect duckdb")
eq(type(Dialect()) is Dialect, True, "base Dialect instantiable")

# ------------------------------------------------------------------------ BigQuery basics
eq(BQ.table_ref("orders"), "`my-proj.d1.orders` AS orders", "bq table_ref")
# The zero-dimension join is NOT rewritten. BigQuery accepts a constant `ON TRUE` outer
# join (verified against a live instance); rewriting it to CROSS JOIN would make the two
# arms structurally different for every scalar multi-measure query, for no reason.
eq(BQ.combine_measures("m0", [], "SELECT 1", "m1"),
   "\nFULL OUTER JOIN (SELECT 1) m1 ON TRUE", "bq cartesian join stays FULL OUTER JOIN ON TRUE")
eq(BQ.combine_measures("m0", [], "SELECT 1", "m1"),
   DUCKDB.combine_measures("m0", [], "SELECT 1", "m1"), "bq join structure == duckdb join structure")
eq(BQ.combine_measures("m0", ["a"], "SELECT 1", "m1"),
   "\nFULL OUTER JOIN (SELECT 1) m1 ON m0.a = m1.a", "bq equi join unchanged")
raises(lambda: BigQueryDialect("bad;project", "d1"), "bq rejects injected project id")
raises(lambda: BQ.table_ref("orders; DROP"), "bq rejects injected table id")
raises(lambda: get_dialect("bigquery:onlyonepart"), "get_dialect rejects malformed spec")
eq(get_dialect("bigquery:p.ds").table_ref("t"), "`p.ds.t` AS t", "get_dialect bigquery spec")

# ------------------------------------------------------------------- date_trunc rewriting
eq(BQ.expr(TS_MONTH), "TIMESTAMP_TRUNC(orders.order_ts, MONTH)", "month trunc")
eq(BQ.expr(TS_YEAR), "TIMESTAMP_TRUNC(orders.order_ts, YEAR)", "year trunc")
eq(BQ.expr(FISCAL),
   "DATE_TRUNC(DATE_ADD(DATE(orders.order_ts), INTERVAL 11 MONTH), YEAR)", "fiscal year")
eq(BQ.expr("DATE_TRUNC('MONTH', orders.order_ts)"),
   "TIMESTAMP_TRUNC(orders.order_ts, MONTH)", "trunc is case-insensitive")
eq(BQ.expr("date_trunc('months', orders.order_ts)"),
   "TIMESTAMP_TRUNC(orders.order_ts, MONTH)", "plural unit accepted")
# embedded in a larger expression, and nested
eq(BQ.expr("CASE WHEN date_trunc('year', orders.order_ts) = x THEN 1 ELSE 0 END"),
   "CASE WHEN TIMESTAMP_TRUNC(orders.order_ts, YEAR) = x THEN 1 ELSE 0 END", "embedded trunc")
eq(BQ.expr("COUNT(DISTINCT date_trunc('day', orders.order_ts))"),
   "COUNT(DISTINCT TIMESTAMP_TRUNC(orders.order_ts, DAY))", "trunc inside a call")
eq(BQ.expr("date_trunc('year', date_trunc('month', orders.order_ts))"),
   "TIMESTAMP_TRUNC(TIMESTAMP_TRUNC(orders.order_ts, MONTH), YEAR)", "nested trunc")
# a string literal that merely LOOKS like a call must not be rewritten
eq(BQ.expr("'date_trunc(''month'', x)'"), "'date_trunc(''month'', x)'", "literal untouched")

# ------------------------------------------------------------------ interval arithmetic
eq(BQ.expr("orders.order_ts + INTERVAL '11' MONTH"),
   "DATE_ADD(DATE(orders.order_ts), INTERVAL 11 MONTH)", "quoted-count interval")
eq(BQ.expr("orders.order_ts + INTERVAL '11 months'"),
   "DATE_ADD(DATE(orders.order_ts), INTERVAL 11 MONTH)", "fully quoted interval")
eq(BQ.expr("orders.order_ts - INTERVAL 1 YEAR"),
   "DATE_SUB(DATE(orders.order_ts), INTERVAL 1 YEAR)", "minus a year -> DATE_SUB")
# sub-day units stay on TIMESTAMP so time-of-day is preserved
eq(BQ.expr("orders.order_ts + INTERVAL 3 HOUR"),
   "TIMESTAMP_ADD(orders.order_ts, INTERVAL 3 HOUR)", "hours stay TIMESTAMP")
eq(BQ.expr("orders.order_ts - INTERVAL 7 DAY"),
   "TIMESTAMP_SUB(orders.order_ts, INTERVAL 7 DAY)", "days stay TIMESTAMP")

# ------------------------------------------------- literal typing follows the column type
eq(BQ.date_predicate(TS_MONTH, "=", "2024-05-01"),
   "TIMESTAMP_TRUNC(orders.order_ts, MONTH) = TIMESTAMP '2024-05-01'", "timestamp literal")
eq(BQ.date_predicate(FISCAL, ">=", "2024-01-01"),
   "DATE_TRUNC(DATE_ADD(DATE(orders.order_ts), INTERVAL 11 MONTH), YEAR) >= DATE '2024-01-01'",
   "date literal for the fiscal-year column")
eq(BQ.date_predicate("orders.order_date", "=", "2024-01-01"),
   "orders.order_date = TIMESTAMP '2024-01-01'", "bare column defaults to TIMESTAMP")

# column_types resolves a bare column that is really a DATE
BQD = BigQueryDialect("p", "d1", column_types={"orders.order_date": "DATE"})
eq(BQD.expr("date_trunc('month', orders.order_date)"),
   "DATE_TRUNC(orders.order_date, MONTH)", "declared DATE column -> DATE_TRUNC")
eq(BQD.date_predicate("orders.order_date", "=", "2024-01-01"),
   "orders.order_date = DATE '2024-01-01'", "declared DATE column -> DATE literal")

# ------------------------------------------------------------- untranslatable = loud error
raises(lambda: BQ.expr("orders.order_ts::DATE"), "'::' cast refused", "::")
raises(lambda: BQ.expr("strftime(orders.order_ts, '%Y')"), "strftime refused", "strftime")
raises(lambda: BQ.expr("date_part('year', orders.order_ts)"), "date_part refused", "date_part")
raises(lambda: BQ.expr("date_diff('day', a, b)"), "duckdb date_diff refused", "date_diff")
raises(lambda: BQ.expr("regexp_matches(a, 'x')"), "regexp_matches refused", "regexp_matches")
raises(lambda: BQ.expr("a ILIKE 'x%'"), "ILIKE refused", "ilike")
raises(lambda: BQ.expr("list_sum(a)"), "list_*() refused", "list_")
raises(lambda: BQ.expr("date_trunc('millennium', orders.order_ts)"),
       "unknown trunc part refused", "millennium")
raises(lambda: BQ.expr("date_trunc('month')"), "1-arg date_trunc refused", "2 arguments")
raises(lambda: BQ.expr("INTERVAL 3 MONTH"), "bare interval refused", "interval")
raises(lambda: BQ.expr("orders.order_ts + INTERVAL 3 DECADE"), "bad interval unit refused")
raises(lambda: BQ.expr("date_trunc('month', orders.order_ts"), "unbalanced parens refused",
       "unbalanced")
raises(lambda: BQ.expr("'unterminated"), "unterminated literal refused", "unterminated")

# ---------------------------------------------- a dialect gap is NOT a governance refusal
MODEL = {
    "join_graph": [],
    "dimensions": {"bad": {"source": "t", "sql": "x::DATE", "type": "string"}},
    "measures": {"m": {"base": "t", "agg_sql": "SUM(t.v)"}},
}
eq(C.compile_plan(MODEL, {"measures": ["m"]})["sql"],
   "SELECT m0.m AS m\nFROM (SELECT SUM(t.v) AS m\nFROM t\n) m0",
   "duckdb path through compile_plan")
eq("refuse" in C.compile_plan(MODEL, {"measures": ["nope"]}), True, "unknown measure refused")
try:
    C.compile_plan(MODEL, {"measures": ["m"], "dimensions": ["bad"]}, BQ)
    _fails.append("compile_plan swallowed a DialectError into a refusal")
except DialectError:
    pass
# ...and the same plan on the DuckDB arm is unaffected
eq("refuse" in C.compile_plan(MODEL, {"measures": ["m"], "dimensions": ["bad"]}), False,
   "duckdb arm unaffected by a BigQuery-only gap")
# a dialect can also be named by spec string
eq(C.compile_plan(MODEL, {"measures": ["m"]}, "bigquery:p.ds")["sql"],
   "SELECT m0.m AS m\nFROM (SELECT SUM(t.v) AS m\nFROM `p.ds.t` AS t\n) m0",
   "compile_plan accepts a dialect spec")

# ------------------------------------------------- multi-measure combine (dim survival)
# Measure subqueries do not share a domain: each sits at its own base grain and carries its
# own certified filter, so a group can appear in m1 and not in m0. The join key and the
# output dimension must therefore be COALESCE'd across every subquery. Reading them off m0
# alone loses the label with two measures and SPLITS the group into one row per measure
# with three or more — a fan-out in the output, in the one place the compiler is supposed
# to guarantee there is none.
eq(dim_ref("m0", "d"), "m0.d", "dim_ref: a bare alias is a plain column reference")
eq(dim_ref(["m0"], "d"), "m0.d", "dim_ref: one alias needs no COALESCE")
eq(dim_ref(["m0", "m1", "m2"], "d"), "COALESCE(m0.d, m1.d, m2.d)", "dim_ref: COALESCE chain")
# the ON key chains across everything already joined, so m2 can match a group only m1 has
eq(DUCKDB.combine_measures(["m0", "m1"], ["a"], "SELECT 1", "m2"),
   "\nFULL OUTER JOIN (SELECT 1) m2 ON COALESCE(m0.a, m1.a) = m2.a", "duckdb chained key")
eq(BQ.combine_measures(["m0", "m1"], ["a"], "SELECT 1", "m2"),
   "\nFULL OUTER JOIN (SELECT 1) m2 ON COALESCE(m0.a, m1.a) = m2.a",
   "bq chained key (COALESCE in a FULL OUTER JOIN predicate is accepted by BigQuery)")

# end to end: three measures over ONE dimension whose domains differ. m0 has only 'a',
# m1 only 'b', m2 both. Every group must come back exactly once, labelled.
SPLIT = {
    "join_graph": [],
    "dimensions": {"g": {"source": "t", "sql": "t.g", "type": "string"}},
    "measures": {
        "only_a": {"base": "t", "agg_sql": "SUM(t.v)", "filter_sql": "t.g = 'a'"},
        "only_b": {"base": "t", "agg_sql": "SUM(t.v)", "filter_sql": "t.g = 'b'"},
        "both":   {"base": "t", "agg_sql": "SUM(t.v)"},
    },
}
_split_sql = C.compile_plan(SPLIT, {"measures": ["only_a", "only_b", "both"],
                                    "dimensions": ["g"]})["sql"]
eq(_split_sql.splitlines()[0],
   "SELECT COALESCE(m0.g, m1.g, m2.g) AS g, m0.only_a AS only_a, m1.only_b AS only_b, "
   "m2.both AS both",
   "3-measure select coalesces the dimension across all subqueries")
eq(_split_sql.count("ON COALESCE(m0.g, m1.g) = m2.g"), 1,
   "the third subquery joins on the chained key, not on m0 alone")
eq(_split_sql.count("ON m0.g = m1.g"), 1, "the second subquery still joins straight to m0")
try:
    import duckdb as _dd
    _c = _dd.connect()
    _c.execute("CREATE TABLE t AS SELECT * FROM (VALUES ('a',1),('b',2)) v(g,v)")
    eq(sorted(_c.execute(_split_sql).fetchall(), key=str),
       [("a", 1, None, 1), ("b", None, 2, 2)],
       "each group comes back as ONE labelled row, not one row per measure")
    _c.close()
except ImportError:                                   # duckdb is optional for this file
    pass

# --- ORDER BY must pin NULL placement, on every dialect -----------------------------
# The combine step MANUFACTURES NULLs (a group present in one measure's subquery but not
# another's). Engines disagree on where those sort: DuckDB puts NULLs last in both
# directions, BigQuery puts them FIRST for ASC. Without an explicit NULLS LAST the same
# plan returns a DIFFERENT ROW per warehouse under `ORDER BY ... ASC` + `LIMIT`.
# Verified live on both engines: {net_revenue, refund_total} by order_status,
# ORDER BY refund_total ASC LIMIT 1 gave ('delivered', ...) on DuckDB and
# ('shipped', ..., None) on BigQuery before this fix, and agrees after it.
# The published corpus dodges this only by luck: all 25 logged condition-S plans that
# combine ORDER BY with LIMIT sort DESC, and the divergence only bites on ASC.
_NL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_nl_model = C.load_model(os.path.join(_NL_ROOT, "semantic_models", "d1.yaml"))
for _dir in ("asc", "desc"):
    for _spec in (None, "bigquery:proj.ds"):
        _nl_plan = {"measures": ["net_revenue", "refund_total"],
                    "dimensions": ["order_status"],
                    "order_by": {"field": "refund_total", "dir": _dir}, "limit": 1}
        _nl_sql = C.compile_plan(_nl_model, _nl_plan, dialect=get_dialect(_spec))["sql"]
        _ob = [l for l in _nl_sql.splitlines() if l.startswith("ORDER BY")]
        eq(bool(_ob) and _ob[0].endswith("NULLS LAST"), True,
           f"ORDER BY {_dir.upper()} pins NULLS LAST on {_spec or 'duckdb'} "
           f"(got {_ob[0] if _ob else 'no ORDER BY'!r})")

# -----------------------------------------------------------------------------------
if _fails:
    print(f"FAIL — {len(_fails)} case(s):")
    for f in _fails:
        print("  - " + f)
    sys.exit(1)
print("dialects self-test: OK")
