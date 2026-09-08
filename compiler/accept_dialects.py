#!/usr/bin/env python3
"""ACCEPTANCE TEST for the dialect seam: the DuckDB arm must be unchanged.

Replays every stored condition-S plan in results/*.jsonl through BOTH compilers and
compares them:

    baseline   a copy of compile.py from before the dialect refactor
    current    compiler/compile.py with its default (DuckDB) dialect

  1. compile_plan() outputs must be EQUAL — byte-identical SQL, identical refusal text.
  2. Every distinct generated statement, executed on the DuckDB warehouse, must return
     identical rows under both.
  3. (informational) how the replay compares to the rows stored in the jsonl.

It also compiles every plan through BigQueryDialect to prove the translator covers the
shipped models — that arm is NOT executed (no BigQuery credentials are used or needed).

READ-ONLY. It opens the warehouses read_only and never writes to results/. Still, the
safest way to run it is in a scratch copy of the repo:

    rsync -a --exclude .git <repo>/ /tmp/dialect-check/
    git show <pre-refactor-ref>:compiler/compile.py > /tmp/dialect-check/compiler/compile_baseline.py
    python /tmp/dialect-check/compiler/accept_dialects.py

Options:
    --baseline PATH   baseline compiler (default: compiler/compile_baseline.py)
    --dump PATH       write one sample of each distinct BigQuery statement shape
"""
import argparse
import glob
import importlib.util
import json
import os
import sys
import traceback
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, HERE)

import duckdb                                          # noqa: E402
import compile as NEW                                  # noqa: E402
from dialects import BigQueryDialect, DialectError     # noqa: E402


def load_baseline(path):
    if not os.path.exists(path):
        sys.exit(f"baseline compiler not found: {path}\n"
                 f"produce it with:  git show <pre-refactor-ref>:compiler/compile.py > {path}")
    spec = importlib.util.spec_from_file_location("compile_baseline", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=os.path.join(HERE, "compile_baseline.py"))
    ap.add_argument("--dump", default=None)
    a = ap.parse_args()

    BASE = load_baseline(a.baseline)
    datasets = [os.path.basename(p)[:-5]
                for p in sorted(glob.glob(os.path.join(ROOT, "semantic_models", "*.yaml")))]
    # a separate load per compiler, so neither can mutate the other's model dict
    models_n = {ds: NEW.load_model(os.path.join(ROOT, "semantic_models", f"{ds}.yaml"))
                for ds in datasets}
    models_b = {ds: BASE.load_model(os.path.join(ROOT, "semantic_models", f"{ds}.yaml"))
                for ds in datasets}
    cons, bq = {}, {}

    def con(ds):
        if ds not in cons:
            cons[ds] = duckdb.connect(os.path.join(ROOT, "warehouse", f"{ds}.duckdb"),
                                      read_only=True)
        return cons[ds]

    cache = {}

    def run_sql(ds, sql):
        if (ds, sql) not in cache:
            try:
                cache[(ds, sql)] = ("ok", con(ds).execute(sql).fetchall())
            except Exception as e:      # noqa: BLE001
                cache[(ds, sql)] = ("error", str(e)[:300])
        return cache[(ds, sql)]

    def norm(rows):
        return None if rows is None else json.dumps(rows, default=str, sort_keys=True)

    files = sorted(glob.glob(os.path.join(ROOT, "results", "*.jsonl")))
    c = Counter()
    compile_bad, exec_bad, bq_bad, samples = [], [], [], {}

    for f in files:
        for lineno, line in enumerate(open(f), 1):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("condition") != "S":
                continue
            c["S_rows"] += 1
            plan, ds = r.get("plan"), r.get("dataset")
            if not isinstance(plan, dict):
                c["S_rows_without_dict_plan"] += 1
                continue
            if ds not in models_n:
                c["S_rows_unknown_dataset"] += 1
                continue
            c["replayed"] += 1

            b = BASE.compile_plan(models_b[ds], plan)
            n = NEW.compile_plan(models_n[ds], plan)       # default dialect = DuckDB
            if b == n:
                c["compile_identical"] += 1
                c["compile_identical_sql" if "sql" in b else "compile_identical_refusal"] += 1
            else:
                c["compile_MISMATCH"] += 1
                if len(compile_bad) < 5:
                    compile_bad.append((os.path.basename(f), lineno, r.get("qid"), b, n))

            if "sql" in b and "sql" in n:
                bs, br = run_sql(ds, b["sql"])
                ns, nr = run_sql(ds, n["sql"])
                if bs == ns and norm(br) == norm(nr):
                    c["exec_identical"] += 1
                    c[f"exec_{bs}"] += 1
                else:
                    c["exec_MISMATCH"] += 1
                    if len(exec_bad) < 5:
                        exec_bad.append((os.path.basename(f), lineno, r.get("qid"),
                                         bs, ns, str(br)[:200], str(nr)[:200]))
                if bs == "ok" and r.get("outcome") == "ok":
                    # row ORDER out of a FULL OUTER JOIN is not deterministic, so compare
                    # as a multiset — an ordering change is not a change of answer
                    def ms(rows):
                        return sorted(json.dumps(list(x), default=str) for x in rows)
                    c["stored_same_multiset" if ms(br) == ms(r["rows"])
                      else "stored_VALUES_DIFFER"] += 1
                    c["stored_same_order"] += int(norm(br) == norm(r.get("rows")))
            elif "sql" in b or "sql" in n:
                c["exec_MISMATCH"] += 1

            # BigQuery arm — generated only, never executed
            if ds not in bq:
                bq[ds] = BigQueryDialect("demo-project", ds)
            try:
                q = NEW.compile_plan(models_n[ds], plan, bq[ds])
                c["bq_compiled_sql" if "sql" in q else "bq_refusal"] += 1
                if "sql" in q:
                    samples.setdefault(
                        (ds, tuple(plan.get("measures") or []),
                         tuple(plan.get("dimensions") or []),
                         tuple(sorted(str(x) for x in (plan.get("filters") or [])))), q["sql"])
            except DialectError as e:
                c["bq_DIALECT_ERROR"] += 1
                if len(bq_bad) < 5:
                    bq_bad.append((r.get("qid"), str(e)))
            except Exception:           # noqa: BLE001
                c["bq_UNEXPECTED_EXC"] += 1
                if len(bq_bad) < 5:
                    bq_bad.append((r.get("qid"), traceback.format_exc()[-400:]))

    print("=" * 78)
    print("ACCEPTANCE — dialect seam vs pre-refactor compiler (DuckDB arm must be identical)")
    print("=" * 78)
    print(f"baseline: {a.baseline}")
    print(f"files scanned: {len(files)}")
    for k in sorted(c):
        print(f"  {k:32} {c[k]}")
    for label, items in (("compile mismatches", compile_bad),
                         ("execution mismatches", exec_bad),
                         ("BigQuery dialect errors", bq_bad)):
        print(f"\n--- {label} (first 5) ---")
        print("NONE" if not items else "\n".join(str(x) for x in items))

    ok = (c["replayed"] > 0 and c["compile_MISMATCH"] == 0 and c["exec_MISMATCH"] == 0
          and c["compile_identical"] == c["replayed"] and c["stored_VALUES_DIFFER"] == 0
          and c["bq_DIALECT_ERROR"] == 0 and c["bq_UNEXPECTED_EXC"] == 0)
    print("\nRESULT:", "PASS" if ok else "FAIL")
    print(f"distinct BigQuery statement shapes generated: {len(samples)} (not executed)")
    if a.dump:
        with open(a.dump, "w") as out:
            for key, sql in sorted(samples.items(), key=lambda kv: str(kv[0])):
                out.write(f"-- {key}\n{sql}\n\n")
        print(f"samples written -> {a.dump}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
