#!/usr/bin/env python3
"""Recompile condition-S rows from their STORED plans using the current compiler, re-executing on
DuckDB and updating outcome/rows/sql/detail in place. No new model calls — this only re-derives the
deterministic compile+execute step, so a compiler improvement (e.g. date-value coercion) is applied
uniformly and fairly to every already-collected S plan. Usage: recompile_s.py <file1.jsonl> ..."""
import os, sys, json
HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "compiler"))
sys.path.insert(0, os.path.join(HERE, "..", "emit"))
import run as R
import compile as C

def recompile_row(r):
    if r.get("condition") != "S": return r, False
    plan = r.get("plan")
    if not isinstance(plan, dict): return r, False
    ds = r["dataset"]; model, *_ , con = R.ctx(ds)
    if "refuse" in plan and len(plan) == 1:
        r.update(outcome="refusal", detail=str(plan["refuse"])[:200], rows=None, sql=None); return r, True
    comp = C.compile_plan(model, plan)
    if "refuse" in comp:
        r.update(outcome="refusal", detail=comp["refuse"], rows=None, sql=None); return r, True
    res = R.exec_sql(con, comp["sql"])
    r["sql"] = comp["sql"]
    if res["error"]:
        r.update(outcome="error", detail=res["error"], rows=None)
    else:
        r.update(outcome="ok", detail=None, rows=res["rows"])
    return r, True

def main():
    files = sys.argv[1:] or []
    for f in files:
        if not os.path.exists(f): print("skip (missing):", f); continue
        rows = [json.loads(l) for l in open(f) if l.strip()]
        n = 0
        for i, r in enumerate(rows):
            rows[i], changed = recompile_row(r)
            n += int(changed)
        with open(f, "w") as out:
            for r in rows: out.write(json.dumps(r, default=str) + "\n")
        print(f"{os.path.basename(f)}: recompiled {n} S rows (of {len(rows)})")

if __name__ == "__main__":
    main()
