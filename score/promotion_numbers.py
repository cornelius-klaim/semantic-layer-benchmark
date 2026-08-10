#!/usr/bin/env python3
"""Compute the v1->v2 promotion-experiment numbers on the subset of models COMPLETE in both
versions (Gemini flash-lite + the three Claude tiers), and merge them into
results/paper_numbers.json under a 'promotion' key. This isolates the effect of promoting three
ad-hoc metrics to certified measures from the noise of the partially-re-run Gemini tiers."""
import json, os
import pandas as pd
HERE = os.path.dirname(__file__); ROOT = os.path.join(HERE, "..")
CLEAN = ["gemini-2.5-flash-lite", "claude-haiku", "claude-sonnet", "claude-opus"]

def ladder(path, cond=None):
    d = pd.read_csv(path); d = d[d["model"].isin(CLEAN)]
    if cond: d = d[d["condition"] == cond]
    return d

v1 = os.path.join(ROOT, "results_v1", "scored.csv")
v2 = os.path.join(ROOT, "results_v2", "scored.csv")
d1, d2 = ladder(v1), ladder(v2)
lad1 = d1.groupby("condition")["correct"].mean().mul(100)
lad2 = d2.groupby("condition")["correct"].mean().mul(100)
s1 = d1[d1.condition=="S"].groupby("suite")["correct"].mean().mul(100)
s2 = d2[d2.condition=="S"].groupby("suite")["correct"].mean().mul(100)

P = {"models": CLEAN, "n_models": len(CLEAN)}
for c in ["U","D","G","S"]:
    P[f"{c}_v1"] = round(float(lad1.get(c, float('nan'))),1)
    P[f"{c}_v2"] = round(float(lad2.get(c, float('nan'))),1)
    P[f"{c}_delta"] = round(float(lad2.get(c,0)-lad1.get(c,0)),1)
P["S_suite"] = {int(s): {"v1": round(float(s1.get(s,float('nan'))),1),
                         "v2": round(float(s2.get(s,float('nan'))),1),
                         "delta": round(float(s2.get(s,0)-s1.get(s,0)),1)}
                for s in sorted(set(s1.index)|set(s2.index))}

# per-model S
P["S_by_model"] = {}
for m in CLEAN:
    a = d1[(d1.model==m)&(d1.condition=="S")]["correct"].mean()*100
    b = d2[(d2.model==m)&(d2.condition=="S")]["correct"].mean()*100
    P["S_by_model"][m] = {"v1": round(float(a),1), "v2": round(float(b),1), "delta": round(float(b-a),1)}

pn_path = os.path.join(ROOT, "results", "paper_numbers.json")
N = json.load(open(pn_path))
N["promotion"] = P
json.dump(N, open(pn_path, "w"), indent=2)
print(json.dumps(P, indent=2))
