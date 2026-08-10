#!/usr/bin/env python3
"""Test B — Agentic multi-query self-join vs. the pre-joined semantic layer.

Condition MQ: the model may issue only SINGLE-TABLE SQL (no JOINs), one query at a time, in an
agentic loop; it sees each query's rows and must combine sources ITSELF (ferrying keys/values
between queries) before answering. This is the "two connections / two explores, let the LLM stitch
them" pattern. We compare it to condition S (one deterministic pre-joined query from the semantic
layer) on the D2 cross-domain questions, measuring accuracy, efficiency (#queries, tokens, latency),
and run-to-run variance.

Usage: agentic.py --models gemini-2.5-flash,... --runs 3 --out results/runs_agentic.jsonl
"""
import os, sys, json, re, argparse, time
import duckdb
HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "compiler")); sys.path.insert(0, os.path.join(HERE, "..", "emit"))
import run as R
from llm import call_chat, MODELS
ROOT = os.path.join(HERE, ".."); def_out = os.path.join(ROOT, "results", "runs_agentic.jsonl")
def _p(*a): return os.path.join(ROOT, *a)

MAX_QUERIES = 6
ROW_CAP = 60   # rows returned per query; forces the model to aggregate per-source or ferry keys

# the cross-domain questions that REQUIRE joining separate source systems
AGENTIC_QIDS = ["s4_attain_advneg", "s4_attain_no_advneg", "s4_attain_by_region",
                "s4_assess_emea", "s5_advneg_lift"]

D2_TABLES = ["opportunities", "hr_bridge", "learners", "courses", "course_completions",
             "assessment_scores", "sales_reps"]  # note: rep_course_flags is the layer's rollup, hidden

def schema_text():
    ddl = open(_p("schemas", "d2_ddl.sql")).read()
    return ddl

def is_single_table(sql):
    if re.search(r"\bjoin\b", sql, re.I): return False
    # reject a comma-join in FROM (FROM a, b)
    m = re.search(r"\bfrom\b\s+(.+?)(\bwhere\b|\bgroup\b|\border\b|\blimit\b|$)", sql, re.I | re.S)
    if m and "," in m.group(1): return False
    return True

def exec_sql(con, sql):
    try:
        rows = con.execute(sql).fetchall()
        cols = [d[0] for d in con.description]
        return cols, rows, None
    except Exception as e:
        return None, None, str(e)[:200]

SYS = ("You are a data analyst answering a business question, but you are connected to raw source "
       "tables through a restricted interface: you may run only SINGLE-TABLE SQL queries — NO JOINs, "
       "exactly one table in the FROM clause. The sources do not share a pre-joined view; if a "
       "question spans two tables you must query each separately and combine the results YOURSELF, "
       "carrying any keys or values between queries. Issue ONE query at a time inside a ```sql block. "
       f"I will return up to {ROW_CAP} rows. You may run up to {MAX_QUERIES} queries. When you have the "
       "final answer, reply with a line `FINAL: <answer>` — a single number for a scalar question, or "
       "for a breakdown a JSON list like [[\"label\", value], ...]. Do not put SQL and FINAL in the "
       "same message.")

def extract_sql(text):
    m = re.search(r"```sql\s*(.*?)```", text, re.S | re.I) or re.search(r"```\s*(SELECT.*?)```", text, re.S | re.I)
    return m.group(1).strip().rstrip(";") if m else None

def extract_final(text):
    m = re.search(r"FINAL:\s*(.+)", text, re.S)
    return m.group(1).strip() if m else None

def parse_answer(final):
    final = final.strip().strip("`")
    try:
        v = json.loads(final)
        if isinstance(v, list): return {"kind": "topn", "rows": [tuple(x) if isinstance(x, list) else (x,) for x in v]}
        if isinstance(v, (int, float)): return {"kind": "scalar", "rows": [(float(v),)]}
    except Exception:
        pass
    m = re.search(r"-?\d[\d,]*\.?\d*", final.replace(",", ""))
    if m:
        try: return {"kind": "scalar", "rows": [(float(m.group(0)),)]}
        except Exception: pass
    return {"kind": "text", "rows": None, "raw": final[:200]}

def run_one(qid, qtext, model_key, con):
    turns = [("user", f"{SYS}\n\nAVAILABLE SOURCE TABLES (query one at a time, no joins):\n{schema_text()}\n\nBusiness question: {qtext}")]
    nq = 0; tin = 0; tout = 0; t0 = time.time(); final = None; queries = []
    for step in range(MAX_QUERIES + 2):
        resp = call_chat(MODELS[model_key], turns, max_tokens=1200)
        tin += resp["in_tokens"]; tout += resp["out_tokens"]
        txt = resp["text"] or ""
        turns.append(("model", txt))
        if resp["error"]:
            return {"outcome": "error", "detail": resp["error"], "queries": nq, "in_tokens": tin,
                    "out_tokens": tout, "latency": round(time.time()-t0, 2), "rows": None, "ans_kind": None}
        fin = extract_final(txt)
        if fin is not None:
            final = fin; break
        sql = extract_sql(txt)
        if not sql:
            turns.append(("user", "Please issue a single-table SQL query in a ```sql block, or give me `FINAL: <answer>`."))
            continue
        if not is_single_table(sql):
            turns.append(("user", "That query uses a JOIN or multiple tables, which is not allowed. Query ONE table at a time and combine results yourself.")); nq += 1
            queries.append({"sql": sql, "rejected": True}); continue
        nq += 1; cols, rows, err = exec_sql(con, sql)
        queries.append({"sql": sql, "rejected": False, "err": err, "nrows": (len(rows) if rows else 0)})
        if err:
            turns.append(("user", f"Query error: {err}. Try again."))
        else:
            shown = rows[:ROW_CAP]
            body = "columns: " + ", ".join(cols) + "\n" + "\n".join(str(r) for r in shown)
            more = f"\n...({len(rows)-ROW_CAP} more rows not shown)" if len(rows) > ROW_CAP else ""
            turns.append(("user", f"Rows ({len(rows)} total):\n{body}{more}\n\nContinue with another query or give `FINAL:`."))
    out = {"queries": nq, "in_tokens": tin, "out_tokens": tout, "latency": round(time.time()-t0, 2),
           "query_log": queries}
    if final is None:
        out.update(outcome="error", detail="no_final", rows=None, ans_kind=None); return out
    ans = parse_answer(final)
    out.update(outcome="ok" if ans["kind"] != "text" else "error", detail=ans.get("raw"),
               rows=ans.get("rows"), ans_kind=ans["kind"]); return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="gemini-2.5-flash")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", default=def_out)
    a = ap.parse_args()
    qs = {q["id"]: q for q in R.load_questions()}
    con = duckdb.connect(_p("warehouse", "d2.duckdb"), read_only=True)
    fout = open(a.out, "a"); n = 0
    for mk in a.models.split(","):
        for qid in AGENTIC_QIDS:
            for run in range(a.runs):
                res = run_one(qid, qs[qid]["text"], mk, con)
                row = {"qid": qid, "suite": "B", "dataset": "d2", "condition": "MQ", "model": mk,
                       "run": run, **res}
                fout.write(json.dumps(row, default=str) + "\n"); fout.flush(); n += 1
                print(f"  {mk[:20]:20} {qid:20} run{run} q={res.get('queries')} {res['outcome']}", flush=True)
    fout.close(); print(f"TOTAL agentic runs: {n} -> {a.out}")

if __name__ == "__main__":
    main()
