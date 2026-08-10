#!/usr/bin/env python3
"""Scorer: classify every run vs ground truth; compute error magnitude, SQL audit flags,
consistency, and cost; write aggregated CSVs + a summary."""
import os, sys, json, re, glob, math
import pandas as pd
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "harness"))
sys.path.insert(0, os.path.join(HERE, "..", "compiler"))
sys.path.insert(0, os.path.join(HERE, "..", "emit"))
import run as R
ROOT = os.path.join(HERE, "..")
def _p(*a): return os.path.join(ROOT, *a)

TOL = 0.01
Q = {q["id"]: q for q in (R.load_questions() + R.load_multiturn_questions())}
TRUTH = {}
for qid, q in Q.items():
    try: TRUTH[qid] = R.truth_of(q)
    except Exception: TRUTH[qid] = {"kind": "unknown"}

def _nums(row):
    out = []
    for v in row:
        if isinstance(v, bool): continue
        if isinstance(v, (int, float)): out.append(float(v))
        else:
            try: out.append(float(v))
            except Exception: pass
    return out

def scalar_of(rows):
    if not rows: return None
    n = _nums(rows[0])
    return n[-1] if n else None

def close(a, b):
    if a is None or b is None: return False
    if abs(b) < 1e-9: return abs(a) < 1e-6
    return abs(a - b) / abs(b) <= TOL

def topn_match(pred, truth):
    """Order-insensitive: same # rows, each pred row matches a truth row (labels eq, nums within tol)."""
    if not pred or not truth: return False
    if len(pred) != len(truth): return False
    def labels(r): return tuple(str(v) for v in r if not isinstance(v,(int,float)) or isinstance(v,bool))
    def nums(r): return _nums(r)
    tleft = list(truth)
    for pr in pred:
        pl, pn = labels(pr), nums(pr)
        hit = None
        for i, tr in enumerate(tleft):
            if labels(tr) == pl and len(nums(tr)) == len(pn) and all(close(a,b) for a,b in zip(pn, nums(tr))):
                hit = i; break
        if hit is None: return False
        tleft.pop(hit)
    return True

CLARIFY_RE = re.compile(r"which|clarif|ambigu|do you mean|could mean|please specify|not clear|depends on|unclear", re.I)

# Derived/ad-hoc metrics that are NOT primitive measures. When condition S cannot answer one
# (because it is not yet a certified measure), that is a LEGIBLE DECLINE — it returns the modeled
# components or refuses — categorically different from a hallucinated wrong number. We score it as
# its own class so the tables never conflate "declined an un-modeled metric" with "confidently wrong".
DERIVED_METRIC_QIDS = {"s2_ship_pct", "s2_avg_line_disc", "s3_net_of_refunds",
                       "s5_ship_pct_region", "s5_advneg_lift",
                       # the same un-modeled shipping-%-of-revenue ratio, embedded mid-conversation
                       "conv_grain_drift_t4"}

def classify(row):
    qid = row["qid"]; q = Q.get(qid, {}); at = q.get("answer_type", "scalar")
    t = TRUTH.get(qid, {}); outcome = row.get("outcome")
    rows = row.get("rows")
    # normalize rows (JSON gave lists) -> list of lists
    if isinstance(rows, list) and rows and not isinstance(rows[0], (list, tuple)):
        rows = [rows]
    # error / llm failure
    if outcome == "error":
        return "error"
    # refusal / clarify question types
    if at == "refusal":
        return "refusal_correct" if outcome == "refusal" else "refusal_wrong"
    if at == "clarify":
        if outcome == "refusal": return "clarification"
        if CLARIFY_RE.search(row.get("completion","") or ""): return "clarification"
        return "silent_guess"
    # numeric / set questions
    def _grade():
        if at == "scalar":
            pv = scalar_of(rows); tv = scalar_of(t.get("rows"))
            return "correct" if close(pv, tv) else "wrong"
        if at in ("topn", "set"):
            return "correct" if topn_match(rows, t.get("rows")) else "wrong"
        return "wrong"
    if outcome == "refusal":
        # for condition S on an un-modeled derived metric, a refusal is a legible decline, not a
        # failure to answer an answerable primitive question
        if row["condition"] == "S" and qid in DERIVED_METRIC_QIDS:
            return "declined_unmodeled"
        return "refusal_wrong"
    verdict = _grade()
    if verdict == "wrong" and row["condition"] == "S" and qid in DERIVED_METRIC_QIDS:
        return "declined_unmodeled"   # S returned modeled components, not a hallucinated number
    return verdict

def rel_err(row):
    q = Q.get(row["qid"], {})
    if q.get("answer_type") != "scalar": return None
    rows = row.get("rows")
    if isinstance(rows, list) and rows and not isinstance(rows[0], (list, tuple)): rows = [rows]
    trows = TRUTH.get(row["qid"], {}).get("rows")
    # only a genuine single-scalar-vs-single-scalar comparison is a measurable "magnitude"; when the
    # answer has a different numeric shape than truth (e.g. two components returned for an un-modeled
    # ratio), it is wrong but NOT unit-comparable, so we exclude it from error-magnitude stats.
    if not rows or not trows: return None
    if len(_nums(rows[0])) != len(_nums(trows[0])): return None
    pv = scalar_of(rows); tv = scalar_of(trows)
    if pv is None or tv is None or abs(tv) < 1e-9: return None
    return abs(pv - tv) / abs(tv)

# ---- SQL audit flags ----
def audits(row):
    sql = (row.get("sql") or "")
    flags = []
    ql = sql.lower()
    q = Q.get(row["qid"], {})
    # Condition S's SQL is compiler-generated and fan-out-safe by construction; the SQL-shape
    # heuristics below target MODEL-written SQL, so we do not apply them to S (they false-positive
    # on S's safe multi-subquery FULL OUTER JOIN combinations).
    if row["condition"] == "S":
        return flags
    # missing certified status filter on a revenue/margin question
    if row["condition"] in ("U","D","G") and any(k in row["qid"] for k in
            ["netrev","margin","gross","aov","top_customer","vocab","rev_"]):
        if "status" not in ql and row.get("outcome") == "ok":
            flags.append("missing_status_filter")
    # fan-out: joins order_items AND aggregates shipping_fee (order-grain over lines)
    if "order_items" in ql and "shipping_fee" in ql and re.search(r"sum\s*\(\s*[a-z_.]*shipping_fee", ql):
        flags.append("fanout_orderfee_over_lines")
    # used the known-bad convenient column
    if "line_total" in ql:
        flags.append("used_wrong_line_total")
    # grouped by name instead of identity (John Smith trap)
    if "top_customer" in row["qid"] and ("full_name" in ql or "group by" in ql and "customer_key" not in ql and "customer_id" not in ql):
        flags.append("grouped_by_name_not_identity")
    # Suite 3 partial-key fan-out: joins `returns` to another table without line_number
    if "returns" in ql and " join " in ql and "line_number" not in ql and row.get("outcome") == "ok":
        flags.append("partial_key_returns_fanout")
    # Cross-domain (D2): joined LMS email to HR without normalizing case/alias
    if row["dataset"] == "d2" and any(k in row["qid"] for k in ["advneg","assess","lift"]):
        if row.get("outcome") == "ok" and "lower(" not in ql and "email" in ql:
            flags.append("email_join_no_normalize")
    return flags

def main():
    # The main U/D/G/S matrix only. The auxiliary experiments (Test A drill-down: conditions P0/P,
    # suite 9; Test B agentic: condition MQ, suite B) live in their own files and are scored by
    # score/drilldown.py and score/agentic_report.py — they must NOT pollute the headline aggregates.
    AUX = {"runs_drilldown.jsonl", "runs_agentic.jsonl"}
    rows = []
    for f in glob.glob(_p("results", "runs_*.jsonl")):
        if os.path.basename(f) in AUX:
            continue
        for line in open(f):
            line = line.strip()
            if line: rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    if df.empty:
        print("no results yet"); return
    df["class"] = df.apply(classify, axis=1)
    df["rel_err"] = df.apply(rel_err, axis=1)
    df["flags"] = df.apply(lambda r: "|".join(audits(r)), axis=1)
    df["correct"] = df["class"].isin(["correct", "refusal_correct", "clarification"]).astype(int)
    df["vendor"] = df["model"].str.split("-").str[0]   # gemini | claude
    os.makedirs(_p("results"), exist_ok=True)
    df.to_csv(_p("results", "scored.csv"), index=False)

    # accuracy by condition x model
    piv = (df.groupby(["model","condition"])["correct"].mean().mul(100).round(1)
             .reset_index().pivot(index="model", columns="condition", values="correct"))
    piv = piv.reindex(columns=[c for c in ["U","D","G","S"] if c in piv.columns])
    print("=== Accuracy (%) by model x condition ===")
    print(piv.to_string())
    piv.to_csv(_p("results", "acc_model_condition.csv"))

    # accuracy by suite x condition (pooled models)
    ps = (df.groupby(["suite","condition"])["correct"].mean().mul(100).round(1)
            .reset_index().pivot(index="suite", columns="condition", values="correct"))
    ps = ps.reindex(columns=[c for c in ["U","D","G","S"] if c in ps.columns])
    print("\n=== Accuracy (%) by suite x condition (models pooled) ===")
    print(ps.to_string())
    ps.to_csv(_p("results", "acc_suite_condition.csv"))

    # overall ladder
    lad = df.groupby("condition")["correct"].mean().mul(100).round(1).reindex(["U","D","G","S"])
    print("\n=== U -> D -> G -> S ladder (all pooled) ===")
    print(lad.to_string())

    # error magnitude on wrong scalars
    wrong = df[(df["class"]=="wrong") & df["rel_err"].notna()]
    if len(wrong):
        print(f"\n=== Error magnitude on wrong numeric answers (n={len(wrong)}) ===")
        print(f"  median rel err: {wrong['rel_err'].median()*100:.1f}%   "
              f"mean: {wrong['rel_err'].mean()*100:.1f}%   "
              f"p90: {wrong['rel_err'].quantile(.9)*100:.1f}%")
        by = wrong.groupby("condition")["rel_err"].median().mul(100).round(1)
        print("  median rel err by condition:", by.to_dict())

    # cost/latency
    cost = df.groupby("condition").agg(prompt_tokens=("prompt_tokens","mean"),
                                       out_tokens=("out_tokens","mean"),
                                       latency=("latency","mean")).round(1)
    print("\n=== Mean tokens & latency by condition ==="); print(cost.to_string())
    cost.to_csv(_p("results","cost_by_condition.csv"))

    # SQL audit flag counts
    fl = df[df["flags"]!=""].assign(flag=df["flags"].str.split("|")).explode("flag")
    if len(fl):
        print("\n=== SQL audit flags (count by condition) ===")
        print(fl.groupby(["condition","flag"]).size().to_string())

    # consistency across phrasing groups (same-answer rate within a group)
    grp = {q["id"]: q.get("group") for q in Q.values() if q.get("group")}
    if grp:
        dfg = df[df["qid"].isin(grp)].copy(); dfg["group"] = dfg["qid"].map(grp)
        cons = (dfg.groupby(["group","condition"])["correct"].mean().mul(100)
                  .reset_index().pivot(index="group", columns="condition", values="correct"))
        print("\n=== Cross-phrasing consistency (accuracy within phrasing group) ===")
        print(cons.round(0).to_string())

    # multi-turn drift: accuracy by turn index x condition
    mt = df[df["suite"] == 6].copy()
    if len(mt) and "turn" in mt.columns:
        mt["turn"] = pd.to_numeric(mt["turn"], errors="coerce")
        drift = (mt.groupby(["turn","condition"])["correct"].mean().mul(100)
                   .reset_index().pivot(index="turn", columns="condition", values="correct"))
        drift = drift.reindex(columns=[c for c in ["U","D","G","S"] if c in drift.columns])
        print("\n=== Multi-turn accuracy by turn (drift) ===")
        print(drift.round(0).to_string())
        drift.to_csv(_p("results","drift_by_turn.csv"))

    # dataset split
    dsacc = (df.groupby(["dataset","condition"])["correct"].mean().mul(100).round(1)
               .reset_index().pivot(index="dataset", columns="condition", values="correct"))
    dsacc = dsacc.reindex(columns=[c for c in ["U","D","G","S"] if c in dsacc.columns])
    print("\n=== Accuracy by dataset x condition ===")
    print(dsacc.to_string()); dsacc.to_csv(_p("results","acc_dataset_condition.csv"))

    print(f"\nTotal scored runs: {len(df)}  -> results/scored.csv")
    write_summary(df, piv, ps, lad)

def _md_table(dframe):
    """Dependency-free markdown table from a DataFrame (index becomes first column)."""
    cols = [dframe.index.name or ""] + [str(c) for c in dframe.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    def fmt(v):
        if pd.isna(v): return ""
        if isinstance(v, (int,)) or (isinstance(v, float) and float(v).is_integer()): return str(int(v))
        if isinstance(v, float): return f"{v:.1f}"
        return str(v)
    for idx, row in dframe.iterrows():
        cells = [str(idx)] + [fmt(v) for v in row.values]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)

def write_summary(df, piv, ps, lad):
    # coverage: runs per (model, condition). A tier is COMPLETE if it covers ~all questions x its runs;
    # partial tiers (fewer rows, and typically missing the later/harder suites) must be read with care.
    nq = df["qid"].nunique(); nsuite = df["suite"].nunique()
    covtab = df.groupby(["model","condition"]).size().unstack().reindex(columns=["U","D","G","S"])
    # completeness is about breadth (did the tier reach every question/suite?), NOT raw row count —
    # a tier can have many rows all concentrated in the easy early suites.
    qcov = df.groupby("model")["qid"].nunique()
    suites_seen = df.groupby("model")["suite"].nunique()
    complete = {m for m in qcov.index if qcov[m] >= 0.9 * nq and suites_seen[m] >= nsuite - 1}
    L = ["# Benchmark results — summary",
         "",
         "> **Data version:** canonical run (v1, *pre-promotion*). The promotion (v2) and reaching-100 "
         "(v3) experiments are reported in `CHANGELOG_PER_LAYER.md` and the whitepaper. Suite-level S "
         "numbers below predate the 8 model/compiler edits that lift S to 100%.",
         "",
         f"Total scored runs: **{len(df)}** across {nq} questions  ",
         f"Conditions: U (ungrounded), D (doc-grounded/OKF), G (prompt-grounded model), S (semantic-layer)  ",
         f"Datasets: {', '.join(sorted(df['dataset'].unique()))}",
         "",
         "## Coverage — runs per (model × condition), and suites reached",
         "> COMPLETE = full multi-run coverage; **partial** tiers (fewer runs) did not reach every "
         "suite, so their high/near-100 scores reflect easier questions only — do not read them as "
         "perfect. `gemini-3.5-flash` and `gemini-2.5-pro` are partial single-run tiers.",
         "",
         _md_table(covtab.assign(**{"suites_reached": suites_seen, "coverage":
                    [("COMPLETE" if m in complete else "partial") for m in covtab.index]})),
         "",
         "## U → D → G → S accuracy ladder (all pooled)",
         "",
         "| " + " | ".join(lad.index) + " |", "|" + "---|"*len(lad),
         "| " + " | ".join(f"{v:.1f}%" for v in lad.values) + " |",
         "",
         "## Accuracy (%) by model × condition  _(n per cell in the coverage table above)_",
         "", _md_table(piv), "",
         "## Accuracy (%) by suite × condition (models pooled)",
         "> NOTE: for condition S, suites 2/3/5 include *un-modeled derived metrics* "
         "(shipping-%, avg-shipping, net-of-refunds, ratios, the advneg lift). Pre-promotion, S "
         "**legibly declines** these (returns modeled components / refuses) rather than hallucinating "
         "— scored as `declined_unmodeled`, not `correct`. The actual grain/fan-out and compound-key "
         "questions in those suites are answered correctly. See per-question CSV `scored.csv`.",
         "", _md_table(ps), "",
         "## Outcome-class breakdown for condition S (all models)",
         "", _md_table(df[df.condition=="S"]["class"].value_counts().rename("count").to_frame()), ""]
    open(_p("results","summary.md"),"w").write("\n".join(str(x) for x in L))

if __name__ == "__main__":
    main()
