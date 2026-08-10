#!/usr/bin/env python3
"""Inferential statistics over scored.csv:
  - cluster bootstrap 95% CIs for accuracy per condition (resampling QUESTIONS, the unit of
    analysis, so CIs reflect question-to-question variation not just run noise);
  - McNemar exact paired tests between adjacent rungs (U<D<G<S), pairing by (qid, model, run);
  - the representation (D-U... actually U->D->G) vs enforcement (G->S) decomposition.
Writes results/stats.md and results/ci_by_condition.csv. Deterministic (fixed RNG seed).
"""
import os, sys, json
import numpy as np, pandas as pd
from scipy.stats import binomtest
HERE = os.path.dirname(__file__); ROOT = os.path.join(HERE, "..")
def _p(*a): return os.path.join(ROOT, *a)
RNG = np.random.default_rng(12345)
CONDS = ["U", "D", "G", "S"]

def cluster_bootstrap_ci(df, B=2000):
    """95% CI for mean accuracy per condition, resampling qids with replacement."""
    out = {}
    for c in CONDS:
        d = df[df["condition"] == c]
        if not len(d): continue
        qids = d["qid"].unique()
        by_q = {q: d[d["qid"] == q]["correct"].values for q in qids}
        point = d["correct"].mean() * 100
        boots = np.empty(B)
        for b in range(B):
            samp = RNG.choice(qids, size=len(qids), replace=True)
            vals = np.concatenate([by_q[q] for q in samp])
            boots[b] = vals.mean() * 100
        out[c] = (point, np.percentile(boots, 2.5), np.percentile(boots, 97.5))
    return out

def mcnemar(df, a, b):
    """Exact McNemar between conditions a and b, paired by (qid, model, run)."""
    da = df[df["condition"] == a].set_index(["qid","model","run"])["correct"]
    db = df[df["condition"] == b].set_index(["qid","model","run"])["correct"]
    j = pd.concat([da.rename("a"), db.rename("b")], axis=1).dropna()
    b01 = int(((j["a"] == 0) & (j["b"] == 1)).sum())   # a wrong, b right
    b10 = int(((j["a"] == 1) & (j["b"] == 0)).sum())   # a right, b wrong
    n = b01 + b10
    if n == 0: return {"n_pairs": len(j), "b_a0b1": b01, "b_a1b0": b10, "p": 1.0}
    p = binomtest(b01, n, 0.5).pvalue
    return {"n_pairs": len(j), "b_a0b1": b01, "b_a1b0": b10, "p": p}

def main():
    df = pd.read_csv(_p("results","scored.csv"))
    df["correct"] = df["correct"].astype(int)
    # restrict to COMPLETE-coverage tiers (exclude partial single-run tiers that skew CIs)
    nq = df["qid"].nunique(); nsuite = df["suite"].nunique()
    qcov = df.groupby("model")["qid"].nunique(); ssee = df.groupby("model")["suite"].nunique()
    COMPLETE = [m for m in qcov.index if qcov[m] >= 0.9*nq and ssee[m] >= nsuite-1]
    df = df[df["model"].isin(COMPLETE)].copy()
    ci = cluster_bootstrap_ci(df)
    rows = [{"condition": c, "accuracy": round(v[0],1), "ci_lo": round(v[1],1), "ci_hi": round(v[2],1)}
            for c, v in ci.items()]
    pd.DataFrame(rows).to_csv(_p("results","ci_by_condition.csv"), index=False)

    L = ["# Inferential statistics\n",
         "## Accuracy with 95% cluster-bootstrap CIs (resampling questions, B=2000)\n",
         "| condition | accuracy | 95% CI |", "|---|---|---|"]
    labels = {"U":"U ungrounded","D":"D doc-grounded (OKF)","G":"G prompt-grounded model","S":"S semantic layer"}
    for c in CONDS:
        if c in ci:
            pt, lo, hi = ci[c]; L.append(f"| {labels[c]} | {pt:.1f}% | [{lo:.1f}, {hi:.1f}] |")
    L.append("\n## McNemar exact paired tests (adjacent rungs)\n")
    L.append("| comparison | discordant (lo→hi wins) | discordant (hi→lo wins) | n pairs | p-value |")
    L.append("|---|---|---|---|---|")
    for a, b in [("U","D"),("D","G"),("G","S"),("U","S")]:
        m = mcnemar(df, a, b)
        L.append(f"| {a} → {b} | {m['b_a0b1']} | {m['b_a1b0']} | {m['n_pairs']} | "
                 f"{m['p']:.2e} |")
    # decomposition
    acc = {c: (ci[c][0] if c in ci else float('nan')) for c in CONDS}
    L.append("\n## Representation vs enforcement decomposition\n")
    L.append(f"- Adding grounding **content** (U→G, representation axis): "
             f"**{acc['G']-acc['U']:+.1f} pts** (U={acc['U']:.1f}% → G={acc['G']:.1f}%).")
    L.append(f"- Adding deterministic **enforcement** at equal content (G→S): "
             f"**{acc['S']-acc['G']:+.1f} pts** (G={acc['G']:.1f}% → S={acc['S']:.1f}%).")
    L.append(f"- Document vs structured representation of the SAME facts (D→G): "
             f"**{acc['G']-acc['D']:+.1f} pts**.")
    open(_p("results","stats.md"),"w").write("\n".join(L)+"\n")
    print("\n".join(L))

if __name__ == "__main__":
    main()
