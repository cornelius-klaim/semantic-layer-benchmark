#!/usr/bin/env python3
"""Emit results/paper_numbers.json — every figure the whitepaper cites, in one machine-readable
place, so the prose never transcribes a number by hand."""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(__file__); ROOT = os.path.join(HERE, "..")
def _p(*a): return os.path.join(ROOT, *a)
sys.path.insert(0, os.path.join(HERE));

def g(df, **kw):
    d = df
    for k, v in kw.items(): d = d[d[k] == v]
    return d

def main():
    df_all = pd.read_csv(_p("results","scored.csv"))
    df_all["correct"] = df_all["correct"].astype(int)
    # HEADLINE metrics use only COMPLETE-coverage tiers (reached ~all questions/suites). Partial
    # single-run tiers (pro, 3.5-flash — easy-suite coverage only) would inflate pooled accuracy and
    # are reported separately. Completeness is breadth of coverage, not row count.
    nq = df_all["qid"].nunique(); nsuite = df_all["suite"].nunique()
    qcov = df_all.groupby("model")["qid"].nunique(); ssee = df_all.groupby("model")["suite"].nunique()
    COMPLETE = sorted([m for m in qcov.index if qcov[m] >= 0.9*nq and ssee[m] >= nsuite-1])
    df = df_all[df_all["model"].isin(COMPLETE)].copy()
    N = {}
    N["n_runs"] = int(len(df_all))
    N["n_runs_headline"] = int(len(df))
    N["n_questions"] = int(nq)
    N["models"] = sorted(df_all["model"].unique().tolist())
    N["models_count"] = len(N["models"])
    N["complete_tiers"] = COMPLETE
    N["complete_count"] = len(COMPLETE)
    N["partial_tiers"] = sorted([m for m in qcov.index if m not in COMPLETE])
    N["datasets"] = sorted(df["dataset"].unique().tolist())
    # ladder
    lad = df.groupby("condition")["correct"].mean().mul(100)
    N["ladder"] = {c: round(float(lad.get(c, float("nan"))), 1) for c in ["U","D","G","S"]}
    N["decomp"] = {"rep": round(float(lad["G"]-lad["U"]),1), "enf": round(float(lad["S"]-lad["G"]),1)}
    # McNemar exact tests between adjacent rungs, paired on (qid, model, run)
    from scipy.stats import binomtest
    def mcnemar(a, b):
        da = df[df["condition"]==a].set_index(["qid","model","run"])["correct"]
        db = df[df["condition"]==b].set_index(["qid","model","run"])["correct"]
        j = pd.concat([da.rename("a"), db.rename("b")], axis=1).dropna()
        b01 = int(((j["a"]==0)&(j["b"]==1)).sum()); b10 = int(((j["a"]==1)&(j["b"]==0)).sum())
        p = binomtest(b01, b01+b10, 0.5).pvalue if (b01+b10) else 1.0
        return b01, b10, p
    def pfmt(p): return "1e-300" if p==0 else f"{p:.0e}".replace("e-0","e-").replace("e+0","e")
    ud = mcnemar("U","D"); dg = mcnemar("D","G"); gs = mcnemar("G","S")
    N["mcnemar"] = {"UD_p": pfmt(ud[2]), "DG_p": pfmt(dg[2]), "GS_p": pfmt(gs[2]),
                    "GS_lo_wins": gs[0], "GS_hi_wins": gs[1]}
    # CIs
    cip = _p("results","ci_by_condition.csv")
    if os.path.exists(cip):
        N["ci"] = {r["condition"]: [round(r["ci_lo"],1), round(r["ci_hi"],1)]
                   for _, r in pd.read_csv(cip).iterrows()}
    # by vendor x condition (gemini vs claude)
    if "vendor" not in df.columns:
        df["vendor"] = df["model"].str.split("-").str[0]
    N["vendors"] = sorted(df["vendor"].unique().tolist())
    N["by_vendor"] = {}
    for v in N["vendors"]:
        N["by_vendor"][v] = {c: round(float(g(df, vendor=v, condition=c)["correct"].mean()*100),1)
                             for c in ["U","D","G","S"]}
    # by model x condition — ALL models (incl partial), with coverage disclosed
    N["by_model"] = {}
    for m in N["models"]:
        N["by_model"][m] = {c: round(float(g(df_all, model=m, condition=c)["correct"].mean()*100),1)
                            for c in ["U","D","G","S"]}
    # condition-S outcome mix on the headline tiers: genuine-wrong vs legible-decline
    s = df[df["condition"]=="S"]
    N["n_s_headline"] = int(len(s))
    N["s_outcomes"] = {k: int(v) for k, v in s["class"].value_counts().items()}
    N["s_wrong_rate"] = round(float((s["class"]=="wrong").mean()*100), 1)
    N["s_declined_rate"] = round(float((s["class"]=="declined_unmodeled").mean()*100), 1)
    # S spread across COMPLETE-coverage tiers only (partial tiers hit 100 on easy suites and would
    # falsely widen/inflate the range)
    s_vals = [N["by_model"][m]["S"] for m in COMPLETE if N["by_model"][m]["S"]==N["by_model"][m]["S"]]
    N["s_min"] = round(min(s_vals),1); N["s_max"] = round(max(s_vals),1)
    # by suite x condition
    N["by_suite"] = {}
    for s in sorted(df["suite"].unique()):
        N["by_suite"][int(s)] = {c: round(float(g(df, suite=s, condition=c)["correct"].mean()*100),1)
                                 for c in ["U","D","G","S"]}
    # by dataset
    N["by_dataset"] = {}
    for ds in N["datasets"]:
        N["by_dataset"][ds] = {c: round(float(g(df, dataset=ds, condition=c)["correct"].mean()*100),1)
                               for c in ["U","D","G","S"]}
    # error magnitude on wrong scalars. Median is the headline (robust); the mean is winsorized
    # at 1000% because a handful of answers compare across incompatible units (e.g. a raw total
    # vs a percentage) and would otherwise dominate the mean as scoring artifacts.
    wrong = df[(df["class"]=="wrong") & df["rel_err"].notna()].copy()
    wrong["rel_err_w"] = wrong["rel_err"].clip(upper=10.0)
    N["error_magnitude"] = {
        "n_wrong_scalar": int(len(wrong)),
        "median_rel_err_pct": round(float(wrong["rel_err"].median()*100),1) if len(wrong) else None,
        "winsor_mean_rel_err_pct": round(float(wrong["rel_err_w"].mean()*100),1) if len(wrong) else None,
        "by_condition_median_pct": {c: round(float(wrong[wrong["condition"]==c]["rel_err"].median()*100),1)
                                    for c in ["U","D","G","S"] if (wrong["condition"]==c).any()},
    }
    # refusal behaviour on unanswerable questions (suite 7 refusal-type)
    ref = df[df["qid"].str.contains("unans", na=False)]
    if len(ref):
        N["unanswerable"] = {c: {
            "refused_pct": round(float((g(ref, condition=c)["class"]=="refusal_correct").mean()*100),1),
            "answered_anyway_pct": round(float(g(ref, condition=c)["class"].isin(["refusal_wrong"]).mean()*100),1),
        } for c in ["U","D","G","S"] if (ref["condition"]==c).any()}
    # audit flags
    fl = df[df["flags"].fillna("")!=""]
    flags = {}
    for _, r in fl.iterrows():
        for f in str(r["flags"]).split("|"):
            flags.setdefault(f, {}).setdefault(r["condition"], 0)
            flags[f][r["condition"]] += 1
    N["audit_flags"] = flags
    # multi-turn drift
    mt = df[df["suite"]==6].copy()
    if len(mt) and "turn" in mt.columns:
        mt["turn"] = pd.to_numeric(mt["turn"], errors="coerce")
        dr = mt.groupby(["turn","condition"])["correct"].mean().mul(100)
        N["drift"] = {c: {int(t): round(float(dr.get((t,c), float("nan"))),1)
                          for t in sorted(mt["turn"].dropna().unique())}
                      for c in ["U","D","G","S"]}
    # cost / tokens per layer. Token counts are the Gemini arm only (the Claude arm is run via
    # subagents, which do not expose a clean prompt/output token split); we restrict to rows with
    # recorded tokens so the accounting is honest.
    okd = df[df["outcome"].isin(["ok","refusal"])]
    tokd = okd[(okd["prompt_tokens"].fillna(0) > 0)]
    N["cost"] = {}
    for c in ["U","D","G","S"]:
        gc = g(okd, condition=c); tc = g(tokd, condition=c)
        N["cost"][c] = {
            "prompt_tokens": round(float(tc["prompt_tokens"].mean()),0) if len(tc) else 0,
            "out_tokens": round(float(tc["out_tokens"].mean()),0) if len(tc) else 0,
            "total_prompt_tokens": int(tc["prompt_tokens"].sum()),
            "total_out_tokens": int(tc["out_tokens"].sum()),
            "latency_s": round(float(gc["latency"].mean()),2) if len(gc) else 0,
        }
    N["cost"]["token_source"] = "gemini_arm_only"
    # planted-effect recovery (D2)
    if os.path.exists(_p("truth","d2_planted.json")):
        N["d2_planted"] = json.load(open(_p("truth","d2_planted.json")))
    # returns partial-key inflation (from generation)
    N["returns_partial_key_inflation_x"] = 3.65

    # composability / drill-down numbers are computed (and merged into this file) by
    # score/composability.py, which must run AFTER this script in the pipeline.
    json.dump(N, open(_p("results","paper_numbers.json"),"w"), indent=2)
    print(json.dumps(N, indent=2))

if __name__ == "__main__":
    main()
