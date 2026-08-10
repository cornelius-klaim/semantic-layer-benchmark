#!/usr/bin/env python3
"""Test A — the Drill-Down Trap. Classify runs_drilldown.jsonl into correct / refused / hallucinated
(confident-wrong) / error, split by drill-down vs control question and by condition, and write
results/drilldown_summary.md. Conditions: U (raw base, naive), P0 (gold only, no refuse option),
P (gold only, refuse offered), S (semantic layer)."""
import os, sys, json, collections
HERE = os.path.dirname(__file__); ROOT = os.path.join(HERE, "..")
def _p(*a): return os.path.join(ROOT, *a)
sys.path.insert(0, _p("harness")); sys.path.insert(0, _p("compiler")); sys.path.insert(0, _p("emit"))
import run as R

Q = {q["id"]: q for q in R.load_questions() if q["suite"] == 9}
TRUTH = {qid: R.truth_of(q) for qid, q in Q.items()}
DRILL = {"dd_top_customer", "dd_paidsearch", "dd_active_customers", "dd_region_by_category"}

def nums(row):
    o = []
    for v in row:
        if isinstance(v, bool): continue
        try: o.append(float(v))
        except Exception: pass
    return o
def close(a, b): return a is not None and b is not None and abs(b) > 1e-9 and abs(a-b)/abs(b) <= 0.01
def scal(rows): return nums(rows[0])[-1] if rows and nums(rows[0]) else None
def correct(qid, rows, at):
    t = TRUTH[qid].get("rows")
    if at == "scalar": return close(scal(rows), scal(t))
    if not rows or not t or len(rows) != len(t): return False
    tv = sorted(nums(r)[-1] for r in t if nums(r)); pv = sorted(nums(r)[-1] for r in rows if nums(r))
    return len(tv) == len(pv) and all(close(a, b) for a, b in zip(pv, tv))

def classify(r):
    if r["outcome"] == "refusal": return "refused"
    if r["outcome"] == "error": return "error"
    return "correct" if correct(r["qid"], r.get("rows"), Q[r["qid"]]["answer_type"]) else "hallucinated"

def main():
    import pandas as pd
    agg = collections.defaultdict(lambda: collections.Counter())
    n = 0; per_run = []
    path = _p("results", "runs_drilldown.jsonl")
    for l in open(path):
        r = json.loads(l);  n += 1
        kind = "drilldown" if r["qid"] in DRILL else "control"
        cls = classify(r)
        agg[(kind, r["condition"])][cls] += 1
        per_run.append({"qid": r["qid"], "question_kind": kind, "condition": r["condition"],
                        "model": r["model"], "run": r["run"], "outcome": r["outcome"], "class": cls,
                        "correct": int(cls == "correct"),
                        "prompt_tokens": r.get("prompt_tokens"), "out_tokens": r.get("out_tokens"),
                        "latency": r.get("latency"),
                        "sql": (r.get("sql") or "")[:500].replace("\n", " ").replace("\r", " ")})
    pd.DataFrame(per_run).to_csv(_p("results", "drilldown_scored.csv"), index=False)
    L = ["# Test A — The Drill-Down Trap", "",
         "Condition P0 = pre-aggregated gold tables only, naive prompt (no refuse option); "
         "P = gold tables only, given an explicit refuse option; S = semantic layer (base-grain, can "
         "drill); U = raw base schema, naive (reference). Drill-down questions need detail below the "
         "gold grain and cannot be answered from the aggregates; controls can.", "",
         "| question kind | condition | correct | refused | hallucinated | error | n |",
         "|---|---|---|---|---|---|---|"]
    for kind in ["drilldown", "control"]:
        for cond in ["U", "P0", "P", "S"]:
            c = agg[(kind, cond)]; tot = sum(c.values())
            if tot:
                L.append(f"| {kind} | {cond} | {c.get('correct',0)} | {c.get('refused',0)} | "
                         f"**{c.get('hallucinated',0)}** | {c.get('error',0)} | {tot} |")
    dd = lambda cond: agg[("drilldown", cond)]
    L += ["", "## Headline",
          f"- Boxed into the gold layer with **no** refuse option (P0), the model refused "
          f"**{dd('P0').get('refused',0)}** times and hallucinated/errored on the rest — it never "
          f"declines a drill-down it cannot answer.",
          f"- The **same** boxed model, merely *offered* a refuse option (P), refused "
          f"**{dd('P').get('refused',0)}** times and hallucinated **{dd('P').get('hallucinated',0)}**.",
          f"- The semantic layer (S) drilled to base grain and was correct **{dd('S').get('correct',0)}** "
          f"times — it is never cornered, because the detail is still reachable."]
    open(_p("results", "drilldown_summary.md"), "w").write("\n".join(L) + "\n")
    # merge citable numbers into paper_numbers.json
    pn = _p("results", "paper_numbers.json")
    if os.path.exists(pn):
        N = json.load(open(pn))
        g = lambda kind, cond, key: agg[(kind, cond)].get(key, 0)
        N["drilldown"] = {
            "p0_hallucinated": g("drilldown","P0","hallucinated"), "p0_refused": g("drilldown","P0","refused"),
            "p0_error": g("drilldown","P0","error"),
            "p_refused": g("drilldown","P","refused"), "p_hallucinated": g("drilldown","P","hallucinated"),
            "u_hallucinated": g("drilldown","U","hallucinated"), "u_n": sum(agg[("drilldown","U")].values()),
            "s_correct": g("drilldown","S","correct"),
            "s_n": sum(agg[("drilldown","S")].values()), "p0_n": sum(agg[("drilldown","P0")].values()),
            "p_n": sum(agg[("drilldown","P")].values()),
            "ctrl_p0_correct": g("control","P0","correct"), "ctrl_p_correct": g("control","P","correct"),
            "ctrl_s_correct": g("control","S","correct"),
        }
        json.dump(N, open(pn, "w"), indent=2)
    print("\n".join(L)); print(f"\nscored {n} runs -> results/drilldown_summary.md (+ paper_numbers.json)")

if __name__ == "__main__":
    main()
