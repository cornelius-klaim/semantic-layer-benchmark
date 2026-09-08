#!/usr/bin/env python3
"""Negative control for the agreement matrix: prove the comparator can report disagreement.

A cross-backend comparison that reports 100% agreement is worth nothing on its own — a
comparator that always says "same" would report exactly the same number. This script
injects known faults into a COPY of the BigQuery replay file and checks that each one lands
in the bucket it should, then prints a table suitable for pasting into the report.

    scripts/mutation_check.py [--a results/replay_duckdb.jsonl] [--b results/replay_bq.jsonl]

Never writes to results/: mutants go to a temp directory and are deleted.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, os.path.join(ROOT, "compiler"))
sys.path.insert(0, os.path.join(ROOT, "harness"))

import replay_s as R  # noqa: E402

N = 3  # rows to mutate per fault


def _write(path, rows):
    with open(path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")


def _exact_pairs(a_rows, b_rows):
    """Keys whose rows are byte-identical — the population that must fall out of `identical`."""
    A = {(r.get("qid"), r.get("condition"), r.get("model"), r.get("run")): r for r in a_rows}
    out = set()
    for r in b_rows:
        k = (r.get("qid"), r.get("condition"), r.get("model"), r.get("run"))
        a = A.get(k)
        if a and r.get("outcome") == "ok" and r.get("rows") \
                and json.dumps(a.get("rows"), default=str) == json.dumps(r.get("rows"), default=str) \
                and isinstance(r["rows"][0][-1], (int, float)):
            out.add(k)
    return out


def mutants(a_rows, b_rows):
    """Yield (label, expected_class, mutated_rows)."""
    exact = _exact_pairs(a_rows, b_rows)

    def scale(factor, only_exact):
        rows, n = copy.deepcopy(b_rows), 0
        for r in rows:
            k = (r.get("qid"), r.get("condition"), r.get("model"), r.get("run"))
            if only_exact and k not in exact:
                continue
            if r.get("outcome") != "ok" or not r.get("rows"):
                continue
            if not isinstance(r["rows"][0][-1], (int, float)):
                continue
            r["rows"][0][-1] = float(r["rows"][0][-1]) * factor
            n += 1
            if n >= N:
                break
        return rows

    def outcome(new_outcome):
        rows, n = copy.deepcopy(b_rows), 0
        for r in rows:
            if r.get("outcome") != "ok":
                continue
            r["outcome"], r["rows"], r["detail"] = new_outcome, None, "synthetic"
            n += 1
            if n >= N:
                break
        return rows

    def droprow():
        rows, n = copy.deepcopy(b_rows), 0
        for r in rows:
            if r.get("outcome") == "ok" and r.get("rows") and len(r["rows"]) > 2:
                r["rows"] = r["rows"][:-1]
                n += 1
            if n >= N:
                break
        return rows

    def tzshift():
        rows, n = copy.deepcopy(b_rows), 0
        for r in rows:
            if r.get("outcome") != "ok" or not r.get("rows"):
                continue
            hit = False
            for row in r["rows"]:
                for i, v in enumerate(row):
                    if isinstance(v, str) and v.endswith(" 00:00:00+00:00"):
                        row[i] = v.replace(" 00:00:00+00:00", " 01:00:00+00:00")
                        hit = True
            if hit:
                n += 1
            if n >= N:
                break
        return rows

    yield ("scale one measure by 1.05 (outside the 1% band)", "divergent", scale(1.05, False))
    yield ("scale exactly-identical pairs by 1.005 (inside the band)", "within_tol", scale(1.005, True))
    yield ("turn `ok` into `refusal`", "refused_by_one", outcome("refusal"))
    yield ("turn `ok` into `error`", "error_by_one", outcome("error"))
    yield ("drop one row from a multi-row result", "divergent", droprow())
    yield ("shift a timestamp by one hour", "divergent", tzshift())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default=os.path.join(ROOT, "results", "replay_duckdb.jsonl"))
    ap.add_argument("--b", default=os.path.join(ROOT, "results", "replay_bq.jsonl"))
    args = ap.parse_args()

    a_rows, b_rows = R.read_jsonl(args.a), R.read_jsonl(args.b)
    base = R.agreement_report(args.a, args.b)["totals"]
    print(f"baseline: {dict(base)}\n")
    print(f"| mutation ({N} pairs each) | expected | observed | verdict |")
    print("|---|---|---|---|")

    tmp = tempfile.mkdtemp(prefix="agreement-mutants-")
    failures = 0
    try:
        for label, expected, rows in mutants(a_rows, b_rows):
            p = os.path.join(tmp, "mutant.jsonl")
            _write(p, rows)
            got = R.agreement_report(args.a, p)["totals"]
            delta = {k: got[k] - base.get(k, 0) for k in set(got) | set(base)
                     if got[k] - base.get(k, 0) != 0}
            ok = delta.get(expected, 0) > 0
            failures += 0 if ok else 1
            obs = ", ".join(f"{k} {v:+d}" for k, v in sorted(delta.items())) or "no change"
            print(f"| {label} | `{expected}` | {obs} | {'PASS' if ok else '**FAIL**'} |")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'ALL MUTANTS DETECTED' if not failures else f'{failures} MUTANT(S) MISSED'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
