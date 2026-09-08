#!/usr/bin/env python3
"""Prove the BigQuery arm was COMPUTED, not served from BigQuery's result cache.

Why this check exists
---------------------
`results/replay_bq.jsonl` is produced by executing 54 distinct statements. Two caches sit
between the plan and the number in that file:

  1. `BigQueryBackend`'s own in-process cache, which executes each distinct statement once
     and reuses the rows for the 986 repeats. That one is disclosed in the report (§5) and
     is the reason the arm costs cents rather than dollars.
  2. BigQuery's SERVER-SIDE result cache, which returns a previously materialised result
     for a byte-identical statement without re-scanning anything, and bills 0 bytes.

Cache (2) is the dangerous one for a control arm. If a run re-executes statements that an
earlier run already materialised, the arm re-affirms the earlier run's numbers rather than
independently recomputing them — and the tell (`total_bytes_billed == 0`) is easy to read
as "the tables are small" instead of "nothing was actually scanned".

This script re-executes every distinct statement in the BigQuery arm with
`use_query_cache=False`, so BigQuery must re-scan the tables, and compares the rows it
gets back against what the arm recorded. It asserts three things:

    * every statement really was re-run (`cache_hit` is False for all of them),
    * bytes were genuinely scanned (billed > 0),
    * the recomputed rows match the logged rows for every statement.

Rows are compared order-insensitively as multisets: a statement without an ORDER BY
denotes a set, and BigQuery is a distributed shuffle, so row order is not a property of
the answer (the agreement report makes the same choice — see its §3.4).

Cost: re-scanning all 54 statements bills roughly 1.2 GB, i.e. well under a cent, but it
is NOT free and it is NOT run as part of `scripts/agreement_matrix.py`. It is a
run-on-demand audit, which is why it lives in its own script.

    scripts/bq_recompute_check.py [--b results/replay_bq.jsonl]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))

DEFAULT_B = os.path.join(ROOT, "results", "replay_bq.jsonl")


def _multiset(rows):
    """Order-insensitive, representation-stable key for a result set."""
    return sorted(json.dumps(r, default=str, sort_keys=True) for r in rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--b", default=DEFAULT_B, metavar="JSONL",
                    help="the BigQuery replay file to audit (default results/replay_bq.jsonl)")
    ap.add_argument("--project", default=os.environ.get("SEMBENCH_BQ_PROJECT", ""))
    a = ap.parse_args()

    from google.cloud import bigquery

    by_sql = {}
    with open(a.b) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("sql") and r.get("outcome") == "ok":
                by_sql.setdefault(r["sql"], r["rows"])
    if not by_sql:
        sys.exit(f"no executed statements found in {a.b}")

    client = bigquery.Client(project=a.project)
    cfg = bigquery.QueryJobConfig(use_query_cache=False)

    mismatches, served_from_cache, billed = [], 0, 0
    for sql, logged in by_sql.items():
        job = client.query(sql, job_config=cfg)
        got = [list(row.values()) for row in job.result()]
        if job.cache_hit:
            served_from_cache += 1
        billed += job.total_bytes_billed or 0
        if _multiset(got) != _multiset(logged):
            mismatches.append(sql)

    print(f"distinct statements re-executed with the cache disabled : {len(by_sql)}")
    print(f"served from BigQuery's result cache anyway              : {served_from_cache}")
    print(f"bytes billed (0 would mean nothing was scanned)         : {billed / 1e6:.1f} MB")
    print(f"statements whose recomputed rows differ from the log    : {len(mismatches)}")
    for sql in mismatches[:5]:
        print("  MISMATCH:", " ".join(sql.split())[:120])

    ok = not mismatches and served_from_cache == 0 and billed > 0
    print("\nRECOMPUTE OK — the BigQuery arm is a real computation, not a cached replay"
          if ok else "\nRECOMPUTE CHECK FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
