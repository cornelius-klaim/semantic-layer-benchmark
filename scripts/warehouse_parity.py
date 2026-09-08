#!/usr/bin/env python3
"""Independent data-parity check: does BigQuery hold the same rows as the DuckDB warehouse?

The cross-backend agreement matrix only means something if the two warehouses contain the
same data. That is easy to assume and expensive to be wrong about — a partial load would
show up as a semantic disagreement and get triaged as an engine difference. So it is
checked directly, below the semantic layer: for every table, row count plus one aggregate
per column, chosen by type.

    scripts/warehouse_parity.py            # all 16 tables
    scripts/warehouse_parity.py --dataset d1

Read-only on both sides. Opens the DuckDB files with read_only=True.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))

PROJECT = os.environ.get("SEMBENCH_BQ_PROJECT", "")   # set this, or pass --project
DSMAP = {"d1": "semantic_bench_d1", "d2": "semantic_bench_d2"}


def aggs_for(cols, quote, dbl, txt):
    """One comparable aggregate per column. Types differ between the engines, so the
    expression is built per dialect and only the VALUE is compared."""
    out = []
    for name, T in cols:
        q = f"{quote}{name}{quote}"
        if any(x in T for x in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC")):
            out.append((name, f"ROUND(CAST(SUM({q}) AS {dbl}),4)"))
        elif "BOOL" in T:
            out.append((name, f"CAST(SUM(CASE WHEN {q} THEN 1 ELSE 0 END) AS {dbl})"))
        elif "TIMESTAMP" in T or T == "DATE":
            out.append((name, f"CONCAT(CAST(MIN({q}) AS {txt}),'|',CAST(MAX({q}) AS {txt}))"))
        else:
            out.append((name, f"CONCAT(CAST(COUNT(DISTINCT {q}) AS {txt}),'|',"
                              f"CAST(MIN({q}) AS {txt}),'|',CAST(MAX({q}) AS {txt}))"))
    return out


def same(x, y):
    if isinstance(x, float) and isinstance(y, float):
        return abs(x - y) <= 1e-6 * max(1.0, abs(y))
    # DuckDB renders a naive TIMESTAMP bare; BigQuery appends a UTC offset ("+00" or
    # "+00:00"). Both warehouses were loaded from the same instants, so the offset is
    # representation. A real shift changes the digits and still fails.
    return str(x).replace("+00:00", "").replace("+00", "").strip() == \
        str(y).replace("+00:00", "").replace("+00", "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=sorted(DSMAP), default=None)
    args = ap.parse_args()

    import duckdb
    from google.cloud import bigquery

    bq = bigquery.Client(project=PROJECT)
    checked = bad = ntab = 0
    for ds in ([args.dataset] if args.dataset else sorted(DSMAP)):
        path = os.path.join(ROOT, "warehouse", f"{ds}.duckdb")
        con = duckdb.connect(path, read_only=True)
        tables = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY table_name").fetchall()]
        for t in tables:
            ntab += 1
            cols = [(r[1], str(r[2]).upper())
                    for r in con.execute(f"PRAGMA table_info('{t}')").fetchall()]
            da = aggs_for(cols, '"', "DOUBLE", "VARCHAR")
            ba = aggs_for(cols, "`", "FLOAT64", "STRING")
            d = con.execute("SELECT CAST(COUNT(*) AS DOUBLE), "
                            + ", ".join(e for _, e in da) + f" FROM {t}").fetchall()[0]
            b = list(list(bq.query(
                "SELECT CAST(COUNT(*) AS FLOAT64), " + ", ".join(e for _, e in ba)
                + f" FROM `{PROJECT}.{DSMAP[ds]}.{t}`").result())[0].values())
            for i, name in enumerate(["__rowcount__"] + [n for n, _ in da]):
                checked += 1
                if not same(d[i], b[i]):
                    bad += 1
                    print(f"  MISMATCH {ds}.{t}.{name}: duckdb={d[i]!r} bigquery={b[i]!r}")
        con.close()
    print(f"\n{checked} column-level checks across {ntab} tables — {bad} mismatches")
    print("PARITY OK" if not bad else "PARITY FAILED")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
