#!/usr/bin/env python3
"""Ingest Claude-arm subagent outputs (results/claude_raw/{tier}__{ds}__{cond}.json) and turn them
into scored JSONL rows identical in shape to the Gemini arm, executing SQL (U/D/G) or compiling the
plan (S) through the SAME compiler/executor/truth pipeline. Usage: ingest_claude.py <tier> [run]"""
import os, sys, json, re, glob
HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "compiler"))
sys.path.insert(0, os.path.join(HERE, "..", "emit"))
import run as R
import compile as C
ROOT = os.path.join(HERE, ".."); RAW = os.path.join(ROOT, "results", "claude_raw")
def _p(*a): return os.path.join(ROOT, *a)

QMAP = {q["id"]: q for q in R.load_questions()}

def clean_sql(s):
    if not isinstance(s, str): return ""
    m = re.search(r"```sql\s*(.*?)```", s, re.S | re.I) or re.search(r"```\s*(.*?)```", s, re.S)
    if m: s = m.group(1)
    return s.strip().rstrip(";")

def row_for(qid, cond, ds, ans, model, run):
    out = {"qid": qid, "suite": QMAP[qid]["suite"], "dataset": ds, "condition": cond,
           "model": model, "run": run, "prompt_tokens": 0, "out_tokens": 0, "latency": 0,
           "llm_error": None, "completion": json.dumps(ans)[:2000], "plan": None, "sql": None}
    _, _, _, _, con = R.ctx(ds); model_def = R.ctx(ds)[0]
    if ans is None:
        out.update(outcome="error", detail="missing_answer", rows=None); return out
    if cond == "S":
        if isinstance(ans, str):
            ans = R.extract_json(ans) or {"refuse": "unparseable"}
        out["plan"] = ans
        if isinstance(ans, dict) and "refuse" in ans and len(ans) == 1:
            out.update(outcome="refusal", detail=str(ans.get("refuse"))[:200], rows=None); return out
        comp = C.compile_plan(model_def, ans if isinstance(ans, dict) else {})
        if "refuse" in comp:
            out.update(outcome="refusal", detail=comp["refuse"], rows=None); return out
        out["sql"] = comp["sql"]; r = R.exec_sql(con, comp["sql"])
        out.update(outcome=("error" if r["error"] else "ok"), detail=r["error"], rows=r["rows"]); return out
    else:
        sql = clean_sql(ans); out["sql"] = sql
        if not re.search(r"\b(SELECT|WITH)\b", sql, re.I):
            out.update(outcome="refusal", detail=sql[:200], rows=None); return out
        r = R.exec_sql(con, sql)
        out.update(outcome=("error" if r["error"] else "ok"), detail=r["error"], rows=r["rows"]); return out

def main():
    tier = sys.argv[1]                       # e.g. claude-opus
    run = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    model = tier
    outp = _p("results", f"runs_{tier.replace('-','_')}.jsonl")
    fout = open(outp, "a"); n = 0; miss = 0
    for f in sorted(glob.glob(os.path.join(RAW, f"{tier}__*.json"))):
        base = os.path.basename(f)[:-5]           # tier__ds__cond
        _, ds, cond = base.split("__")
        try:
            data = json.load(open(f))
        except Exception as e:
            print("  BAD JSON", f, str(e)[:80]); continue
        # tolerate {qid:answer} or [{id:..,answer:..}]
        if isinstance(data, list):
            data = {d.get("id") or d.get("qid"): (d.get("answer") or d.get("sql") or d.get("plan"))
                    for d in data}
        for qid in [q for q in QMAP if QMAP[q]["dataset"] == ds
                    and cond in QMAP[q].get("conditions", ["U","D","G","S"])]:
            ans = data.get(qid)
            if ans is None: miss += 1
            row = row_for(qid, cond, ds, ans, model, run)
            fout.write(json.dumps(row, default=str) + "\n"); n += 1
    fout.close()
    print(f"{tier}: wrote {n} rows ({miss} missing answers) -> {outp}")

if __name__ == "__main__":
    main()
