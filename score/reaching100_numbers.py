#!/usr/bin/env python3
"""Compute the 'reaching 100%' cost-per-layer numbers from the v3 (fully-iterated) scored data and
merge them into results/paper_numbers.json under a 'reaching100' key."""
import json, os
import pandas as pd
HERE = os.path.dirname(__file__); ROOT = os.path.join(HERE, "..")
CLEAN = ["gemini-2.5-flash-lite", "claude-haiku", "claude-sonnet", "claude-opus"]
REFQ = ["s7_unans_age","s7_unans_supplier","s7_unans_weather","s7_ambiguous_sales",
        "s7_ambiguous_best","s4_unans_age","s4_unans_manager"]

v3 = pd.read_csv(os.path.join(ROOT, "results_v3", "scored.csv"))
v1 = pd.read_csv(os.path.join(ROOT, "results_v1", "scored.csv"))
def acc(df, cond, models=CLEAN, qids=None):
    d = df[(df.condition==cond) & (df.model.isin(models))]
    if qids is not None: d = d[d.qid.isin(qids)]
    return round(float(d["correct"].mean()*100), 1) if len(d) else None

# Reaching-100 is measured on the models with COMPLETE coverage in BOTH the baseline (v1) and the
# iterated (v3) runs — i.e. the CLEAN subset (flash-lite + 3 Claude tiers). flash was only partially
# re-run in the iteration, and the partial pro/3.5-flash tiers never reached the hard suites, so none
# of those can support a full "reached 100% across all questions" claim.
COMPLETE_BOTH = CLEAN
R = {
    "complete_models": COMPLETE_BOTH,
    "complete_count": len(COMPLETE_BOTH),
    "S_complete_final": round(float(v3[(v3.condition=="S")&(v3.model.isin(COMPLETE_BOTH))]["correct"].mean()*100), 1),
    "S_all_models": round(float(v3[v3.condition=="S"]["correct"].mean()*100), 1),
    "S_start": acc(v1, "S"), "S_final": acc(v3, "S"),
    "G_start": acc(v1, "G"), "G_final": acc(v3, "G"),
    "D_start": acc(v1, "D"), "D_final": acc(v3, "D"),
    "U_start": acc(v1, "U"), "U_final": acc(v3, "U"),
    "S_edits": 8,
    "DG_edits": 1,
    "refusal_G_start": acc(v1, "G", qids=REFQ), "refusal_G_final": acc(v3, "G", qids=REFQ),
    "refusal_D_start": acc(v1, "D", qids=REFQ), "refusal_D_final": acc(v3, "D", qids=REFQ),
    "refusal_S_final": acc(v3, "S", qids=REFQ),
}
pn = os.path.join(ROOT, "results", "paper_numbers.json")
N = json.load(open(pn)); N["reaching100"] = R
json.dump(N, open(pn, "w"), indent=2)
print(json.dumps(R, indent=2))
