#!/usr/bin/env python3
"""Camera-ready figures from scored.csv -> paper_assets/figures/*.png (+ .pdf).
Restrained academic palette; one idea per figure. Deterministic."""
import os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

HERE = os.path.dirname(__file__); ROOT = os.path.join(HERE, "..")
def _p(*a): return os.path.join(ROOT, *a)
FIG = _p("paper_assets", "figures"); os.makedirs(FIG, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 160, "savefig.dpi": 160, "font.size": 11,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "font.family": "DejaVu Sans",
})
# U/D/G/S palette — the book's design tokens (red / gold / blue / green).
C = {"U": "#C5221F", "D": "#B06000", "G": "#1A73E8", "S": "#188038"}
CONDS = ["U", "D", "G", "S"]
LAB = {"U": "U\nungrounded", "D": "D\ndoc-grounded", "G": "G\nprompt-model", "S": "S\nsemantic layer"}

def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, name + ".png"), bbox_inches="tight")
    fig.savefig(os.path.join(FIG, name + ".pdf"), bbox_inches="tight")
    plt.close(fig)

def fig_ladder(df):
    ci = None
    cip = _p("results","ci_by_condition.csv")
    if os.path.exists(cip): ci = pd.read_csv(cip).set_index("condition")
    acc = df.groupby("condition")["correct"].mean().mul(100).reindex(CONDS)
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    x = range(len(CONDS)); vals = [acc[c] for c in CONDS]
    err = None
    if ci is not None:
        err = [[acc[c]-ci.loc[c,"ci_lo"] for c in CONDS], [ci.loc[c,"ci_hi"]-acc[c] for c in CONDS]]
    bars = ax.bar(x, vals, color=[C[c] for c in CONDS], width=0.62,
                  yerr=err, capsize=4, ecolor="#444", error_kw={"lw":1.1})
    for xi, v in zip(x, vals):
        ax.text(xi, v+1.5, f"{v:.0f}%", ha="center", va="bottom", fontweight="bold")
    ax.set_xticks(list(x)); ax.set_xticklabels([LAB[c] for c in CONDS])
    ax.set_ylabel("Accuracy (%)"); ax.set_ylim(0, 105)
    ax.set_title("The grounding ladder: representation raises accuracy,\nenforcement (S) secures it",
                 fontsize=12, loc="left")
    save(fig, "fig_ladder")

def fig_suite(df):
    ps = (df.groupby(["suite","condition"])["correct"].mean().mul(100)
            .reset_index().pivot(index="suite", columns="condition", values="correct")
            .reindex(columns=CONDS))
    names = {1:"Certified\nmetrics",2:"Grain /\nfan-out",3:"Compound\nkeys",4:"Cross-\ndomain",
             5:"Multi-query\nsynthesis",6:"Multi-turn",7:"Ambiguity /\nrefusal",8:"Time\nintelligence"}
    ps.index = [names.get(i, str(i)) for i in ps.index]
    fig, ax = plt.subplots(figsize=(9.2, 4.6))
    x = np.arange(len(ps)); w = 0.2
    for k, c in enumerate(CONDS):
        if c in ps.columns:
            ax.bar(x + (k-1.5)*w, ps[c].values, w, label=c, color=C[c])
    ax.set_xticks(x); ax.set_xticklabels(ps.index, fontsize=9)
    ax.set_ylabel("Accuracy (%)"); ax.set_ylim(0, 105)
    ax.legend(title="condition", ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.13), frameon=False)
    ax.set_title("Accuracy by test suite × condition", fontsize=12, loc="left", pad=22)
    save(fig, "fig_suite")

def fig_error_mag(df):
    d = df[(df["class"]=="wrong") & df["rel_err"].notna()].copy()
    if not len(d): return
    d["rel_err_pct"] = (d["rel_err"]*100).clip(upper=300)
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    data = [d[d["condition"]==c]["rel_err_pct"].values for c in CONDS if (d["condition"]==c).any()]
    labs = [c for c in CONDS if (d["condition"]==c).any()]
    bp = ax.boxplot(data, vert=True, patch_artist=True, showfliers=False, widths=0.55)
    for patch, c in zip(bp["boxes"], labs): patch.set_facecolor(C[c]); patch.set_alpha(0.75)
    for med in bp["medians"]: med.set_color("#222"); med.set_linewidth(1.4)
    # annotate n (count of wrong answers) and median under each box
    for i, c in enumerate(labs):
        vals = d[d["condition"]==c]["rel_err_pct"]
        ax.text(i+1, -18, f"n={len(vals)}\nmed {vals.median():.0f}%", ha="center", va="top", fontsize=8.5)
    ax.axhspan(20, 60, color="#C5221F", alpha=0.06, zorder=0)
    ax.text(len(labs)+0.35, 40, "20–60%:\n'plausible on a\ndashboard' zone", fontsize=8, color="#8a1512", va="center")
    ax.set_xticklabels([LAB[c] for c in labs]); ax.set_ylabel("Relative error on wrong answers (%)")
    ax.set_ylim(bottom=-30)
    ax.set_title("When a number IS wrong, how wrong is it?\nUngrounded is wrong far more OFTEN, and lands in the plausible 20–60% zone;\ngrounded errors are rare but strike the hardest synthesis questions",
                 fontsize=10.5, loc="left")
    save(fig, "fig_error_mag")

def fig_drift(df):
    mt = df[df["suite"]==6].copy()
    if not len(mt) or "turn" not in mt.columns: return
    mt["turn"] = pd.to_numeric(mt["turn"], errors="coerce")
    acc = (mt.groupby(["turn","condition"])["correct"].mean().mul(100)
             .reset_index().pivot(index="turn", columns="condition", values="correct").reindex(columns=CONDS))
    # "never returns a wrong number" = not (hallucinated wrong / silent guess / wrongly-refused-answerable)
    mt["notwrong"] = (~mt["class"].isin(["wrong","silent_guess","refusal_wrong"])).astype(int)
    nw = mt[mt.condition=="S"].groupby("turn")["notwrong"].mean().mul(100)
    turns = sorted(mt["turn"].dropna().astype(int).unique())
    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    for c in CONDS:
        if c in acc.columns:
            ax.plot(acc.index, acc[c], marker="o", color=C[c], label=f"{c} accuracy", lw=2)
    ax.plot(nw.index, nw.values, marker="s", color=C["S"], lw=1.6, ls="--",
            label="S never-wrong (correct or legible decline)")
    # mark the un-modeled ratio turn
    if 4 in turns:
        ax.axvline(4, color="#999", lw=0.8, ls=":")
        ax.text(4, 8, "turn 4:\nun-modeled\nratio → S declines\n(not wrong)", ha="center", fontsize=7.5, color="#555")
    ax.set_xlabel("Conversation turn"); ax.set_ylabel("%"); ax.set_ylim(-2, 106)
    ax.set_xticks(turns)
    ax.legend(fontsize=7.8, frameon=False, loc="lower left", ncol=1)
    ax.set_title("Multi-turn case study (1 scenario × 2 models × 3 runs, n=6/point):\nD and G silently degrade at turns 3–4; S is correct on governed turns and\ndeclines the one un-modeled ratio — it never returns a wrong number",
                 fontsize=9.5, loc="left")
    save(fig, "fig_drift")

def fig_cost(df):
    d = df[df["outcome"].isin(["ok","refusal"])]
    tokd = d[d["prompt_tokens"].fillna(0) > 0]   # token counts exist for the Gemini arm only
    inp = tokd.groupby("condition")["prompt_tokens"].mean().reindex(CONDS)
    out = tokd.groupby("condition")["out_tokens"].mean().reindex(CONDS)
    lat = d.groupby("condition")["latency"].mean().reindex(CONDS)
    fig, (a0, a1, a2) = plt.subplots(1, 3, figsize=(11.4, 3.8))
    a0.bar(range(len(CONDS)), [inp[c] for c in CONDS], color=[C[c] for c in CONDS], width=0.62)
    for i,c in enumerate(CONDS): a0.text(i, inp[c], f"{inp[c]:.0f}", ha="center", va="bottom", fontsize=8.5)
    a0.set_xticks(range(len(CONDS))); a0.set_xticklabels(CONDS)
    a0.set_ylabel("Mean INPUT tokens / query"); a0.set_title("Input (context) cost — the real asymmetry", fontsize=11, loc="left")
    a1.bar(range(len(CONDS)), [out[c] for c in CONDS], color=[C[c] for c in CONDS], width=0.62)
    for i,c in enumerate(CONDS): a1.text(i, out[c], f"{out[c]:.0f}", ha="center", va="bottom", fontsize=8.5)
    a1.set_xticks(range(len(CONDS))); a1.set_xticklabels(CONDS); a1.set_ylabel("Mean output tokens / query")
    a1.set_title("Generation cost", fontsize=11, loc="left")
    a2.bar(range(len(CONDS)), [lat[c] for c in CONDS], color=[C[c] for c in CONDS], width=0.62)
    a2.set_xticks(range(len(CONDS))); a2.set_xticklabels(CONDS); a2.set_ylabel("Mean latency (s)")
    a2.set_title("Latency", fontsize=11, loc="left")
    save(fig, "fig_cost")

def fig_decomp(df):
    acc = df.groupby("condition")["correct"].mean().mul(100).reindex(CONDS)
    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    base = acc["U"]
    steps = [("U", base, "#B0413E", "start"),
             ("→G", acc["G"]-acc["U"], "#3E7CB1", "representation\n(add certified content)"),
             ("→S", acc["S"]-acc["G"], "#2E7D5B", "enforcement\n(deterministic layer)")]
    ax.bar(0, base, color="#B0413E", width=0.6)
    ax.text(0, base/2, f"U\n{base:.0f}%", ha="center", va="center", color="white", fontweight="bold")
    running = base
    for i,(lab, delta, col, note) in enumerate(steps[1:], start=1):
        ax.bar(i, delta, bottom=running, color=col, width=0.6)
        ax.text(i, running+delta/2, f"{delta:+.0f}", ha="center", va="center", color="white", fontweight="bold")
        ax.text(i, running+delta+2, note, ha="center", va="bottom", fontsize=8.5)
        running += delta
    ax.bar(3, running, color="#2E7D5B", width=0.6)
    ax.text(3, running/2, f"S\n{running:.0f}%", ha="center", va="center", color="white", fontweight="bold")
    ax.set_xticks(range(4)); ax.set_xticklabels(["ungrounded","+representation","+enforcement","semantic layer"], fontsize=9)
    ax.set_ylabel("Accuracy (%)"); ax.set_ylim(0, 108)
    ax.set_title("Decomposing the gain: what content buys vs what enforcement buys",
                 fontsize=12, loc="left")
    save(fig, "fig_decomp")

def fig_vendor(df):
    if "vendor" not in df.columns:
        df["vendor"] = df["model"].str.split("-").str[0]
    vendors = sorted(df["vendor"].unique())
    if len(vendors) < 2: return
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    x = np.arange(len(CONDS)); w = 0.8/len(vendors)
    hatch = {"gemini": "", "claude": "//"}
    for k, v in enumerate(vendors):
        acc = df[df["vendor"]==v].groupby("condition")["correct"].mean().mul(100).reindex(CONDS)
        ax.bar(x + (k-(len(vendors)-1)/2)*w, [acc[c] for c in CONDS], w,
               label=v, color=[C[c] for c in CONDS], edgecolor="#222",
               hatch=hatch.get(v,""), linewidth=0.6)
    ax.set_xticks(x); ax.set_xticklabels([LAB[c] for c in CONDS]); ax.set_ylim(0,105)
    ax.set_ylabel("Accuracy (%)")
    from matplotlib.patches import Patch
    leg = [Patch(facecolor="#999", hatch=hatch.get(v,""), edgecolor="#222", label=v) for v in vendors]
    ax.legend(handles=leg, title="vendor", frameon=False, loc="upper left")
    ax.set_title("The ladder holds across vendors\n(solid = Gemini, hatched = Claude)",
                 fontsize=12, loc="left")
    save(fig, "fig_vendor")

def fig_drilldown(N):
    dd = N.get("drilldown")
    if not dd: return
    import numpy as np
    conds = ["P0", "P", "S"]
    labels = {"P0": "P0\ngold only,\nno refuse", "P": "P\ngold only,\nrefuse offered", "S": "S\nsemantic\nlayer"}
    hall = [dd["p0_hallucinated"], dd["p_hallucinated"], 0]
    ref  = [dd["p0_refused"], dd["p_refused"], 0]
    cor  = [0, 0, dd["s_correct"]]
    err  = [dd["p0_error"], dd.get("p_n",48)-dd["p_refused"]-dd["p_hallucinated"]-0, 0]
    err  = [dd["p0_error"], max(0, dd.get("p_n",48)-dd["p_refused"]), 0]
    x = np.arange(3)
    fig, ax = plt.subplots(figsize=(7, 4.4))
    ax.bar(x, cor, 0.6, label="correct", color="#188038")
    ax.bar(x, ref, 0.6, bottom=cor, label="refused (safe)", color="#B06000")
    ax.bar(x, hall, 0.6, bottom=[c+r for c,r in zip(cor,ref)], label="hallucinated (confident-wrong)", color="#C5221F")
    ax.set_xticks(x); ax.set_xticklabels([labels[c] for c in conds])
    ax.set_ylabel("runs (drill-down questions)")
    ax.legend(frameon=False, fontsize=8.5, loc="center left", bbox_to_anchor=(1.01, 0.5))
    ax.set_title("The drill-down trap: boxed into a gold aggregate with no refuse option (P0),\n"
                 "the model hallucinates and never declines; an escape hatch (P) converts that to\n"
                 "refusal; the semantic layer (S) drills to base grain and answers",
                 fontsize=9.5, loc="left")
    save(fig, "fig_drilldown")

def fig_agentic(N):
    ag = N.get("agentic")
    if not ag: return
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.6, 3.9))
    a1.bar([0,1], [ag["acc"], ag["s_acc"]], color=["#C5221F","#188038"], width=0.6)
    a1.set_xticks([0,1]); a1.set_xticklabels(["MQ\nself-join","S\npre-joined"]); a1.set_ylim(0,105)
    a1.set_ylabel("Accuracy (%)"); a1.set_title("Accuracy", fontsize=11, loc="left")
    for i,v in enumerate([ag["acc"],ag["s_acc"]]): a1.text(i, v+2, f"{v:.0f}%", ha="center", fontweight="bold")
    a2.bar([0,1], [ag["tokens"], ag["s_tokens"]], color=["#C5221F","#188038"], width=0.6)
    a2.set_xticks([0,1]); a2.set_xticklabels(["MQ\nself-join","S\npre-joined"])
    a2.set_ylabel("Tokens per question")
    for i,v in enumerate([ag["tokens"],ag["s_tokens"]]): a2.text(i, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=9)
    a2.set_title(f"Cost (~{ag['token_x']:.0f}× more tokens, {ag['queries']:.1f} queries vs 1)", fontsize=11, loc="left")
    save(fig, "fig_agentic")

def main():
    import json as _json
    df = pd.read_csv(_p("results","scored.csv"))
    df["correct"] = df["correct"].astype(int)
    _N = _json.load(open(_p("results","paper_numbers.json"))) if os.path.exists(_p("results","paper_numbers.json")) else {}
    fig_drilldown(_N); fig_agentic(_N)
    # figures use COMPLETE-coverage tiers only (partial single-run tiers would skew pooled bars)
    nq = df["qid"].nunique(); nsuite = df["suite"].nunique()
    qcov = df.groupby("model")["qid"].nunique(); ssee = df.groupby("model")["suite"].nunique()
    COMPLETE = [m for m in qcov.index if qcov[m] >= 0.9*nq and ssee[m] >= nsuite-1]
    df = df[df["model"].isin(COMPLETE)].copy()
    fig_ladder(df); fig_suite(df); fig_error_mag(df); fig_drift(df); fig_cost(df); fig_decomp(df)
    fig_vendor(df)
    print("figures ->", FIG)
    print(os.listdir(FIG))

if __name__ == "__main__":
    main()
