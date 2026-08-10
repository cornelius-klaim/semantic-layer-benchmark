#!/usr/bin/env python3
"""Composability accounting for the gold-table-vs-Semantic-Gold-Layer argument.

A wide denormalized gold *table* serves many single-grain GROUP BYs fine (revenue by region, by
category, by month — one table, three group-bys). So the honest claim is NOT "a table per slice"; it
is the subset of question-shapes that cross a **grain, fact, or domain boundary** no single
pre-aggregated table spans. This script classifies every plan-based question-shape and counts them,
emitting the list so the numbers are auditable/reproducible. Merges results into paper_numbers.json.
"""
import os, sys, json, glob, collections
import yaml
HERE = os.path.dirname(__file__); ROOT = os.path.join(HERE, "..")
def _p(*a): return os.path.join(ROOT, *a)
sys.path.insert(0, _p("harness"))
import run as R

# fact (event) tables vs conformed dimension/lookup tables, per dataset. A single wide table is one
# fact denormalized with its dimensions; it CANNOT span two facts at different grains, nor two source
# systems, without a new build — that build is exactly the M step.
FACTS = {"d1": {"order_items", "orders", "returns", "marketing_spend"},
         "d2": {"opportunities", "assessment_scores", "course_completions"}}
# source-system grouping for the cross-domain (D2) bridge
DOMAIN = {"opportunities": "sales", "assessment_scores": "lms", "course_completions": "lms",
          "learners": "lms", "courses": "lms", "hr_bridge": "hr", "rep_course_flags": "hr",
          "sales_reps": "sales"}

def measure_grains(model, mname):
    """The GRAIN(s) a measure aggregates at = its base table(s), expanding ratio/expr components.
    We use base only (NOT `requires`): a measure that merely references a parent/lookup table for a
    filter or attribute is still single-grain and denormalizes onto one wide table. A measure is
    multi-grain only when it *combines* components that aggregate at different base grains (a ratio or
    difference of an order-grain and a line-grain measure)."""
    m = model["measures"].get(mname, {})
    if "ratio" in m:
        return measure_grains(model, m["ratio"]["numerator"]) | measure_grains(model, m["ratio"]["denominator"])
    if "expr" in m:
        out = set()
        for c in m.get("components", []): out |= measure_grains(model, c)
        return out
    return {m["base"]} if m.get("base") else set()

def classify():
    models = {ds: yaml.safe_load(open(_p("semantic_models", f"{ds}.yaml"))) for ds in ("d1", "d2")}
    qs = R.load_questions() + R.load_multiturn_questions()
    shapes = {}   # canonical shape -> example qid
    for q in qs:
        tp = q.get("truth_plan")
        if not tp: continue
        ds = q["dataset"]; model = models[ds]
        key = (ds, tuple(sorted(tp.get("measures", []))), tuple(sorted(tp.get("dimensions", []))),
               tuple(sorted(f["field"] for f in tp.get("filters", []))))
        shapes.setdefault(key, q["id"])
    rows = []
    for (ds, meas, dims, filt), qid in shapes.items():
        model = models[ds]
        # distinct base grains across all measures in the shape (expanding derived measures)
        grains = set()
        for mn in meas: grains |= (measure_grains(model, mn) & FACTS[ds])
        dim_srcs = {model["dimensions"][d]["source"] for d in dims if d in model["dimensions"]}
        filt_srcs = {model["dimensions"][f]["source"] for f in filt if f in model["dimensions"]}
        allsrc = grains | dim_srcs | filt_srcs
        reasons = []
        # GRAIN/FACT: the shape combines measures at MORE THAN ONE base grain / event — no single
        # wide table is at two grains at once (order-grain shipping alongside line-grain revenue;
        # sales alongside returns; any cross-grain ratio or difference).
        if len(grains) > 1:
            reasons.append("grain/fact")
        # DOMAIN: the shape spans more than one SOURCE SYSTEM (the D2 CRM×LMS×HR bridge) — a single
        # pre-aggregated table cannot span separate source systems without building the join first.
        domains = {DOMAIN.get(t) for t in allsrc if DOMAIN.get(t)}
        if len(domains) > 1:
            reasons.append("domain")
        rows.append({"qid": qid, "ds": ds, "measures": list(meas), "dims": list(dims),
                     "filters": list(filt), "boundary": bool(reasons), "reasons": reasons})
    return rows

def main():
    rows = classify()
    nshapes = len(rows); nbound = sum(r["boundary"] for r in rows)
    by_reason = collections.Counter()
    for r in rows:
        for x in r["reasons"]: by_reason[x] += 1
    nmeas = sum(len(yaml.safe_load(open(_p("semantic_models", f"{ds}.yaml")))["measures"]) for ds in ("d1","d2"))
    # net_revenue single-grain group-bys (what a wide table DOES handle) — reported honestly
    qs = R.load_questions() + R.load_multiturn_questions()
    nr = set()
    for q in qs:
        tp = q.get("truth_plan") or {}
        if "net_revenue" in tp.get("measures", []):
            nr.add((tuple(sorted(tp.get("dimensions", []))) or ("(total)",),
                    tuple(sorted(f["field"] for f in tp.get("filters", [])))))
    # authoring-cost footprint: the governed layer is a small, human-readable artifact; the compiler
    # is fixed-size and dataset-agnostic (does not grow with the model).
    d1 = yaml.safe_load(open(_p("semantic_models", "d1.yaml")))
    d1_lines = len(open(_p("semantic_models", "d1.yaml")).read().splitlines())
    comp_lines = len(open(_p("compiler", "compile.py")).read().splitlines())
    n_meas_d1 = len(d1["measures"]); n_dims_d1 = len(d1["dimensions"])
    out = {"n_measures": nmeas, "n_shapes": nshapes, "n_boundary": nbound,
           "boundary_grain": by_reason.get("grain/fact", 0), "boundary_domain": by_reason.get("domain", 0),
           "netrev_slices": len(nr),
           "d1_lines": d1_lines, "compiler_lines": comp_lines,
           "n_measures_d1": n_meas_d1, "n_dims_d1": n_dims_d1, "single_slices_d1": n_meas_d1*n_dims_d1,
           "boundary_qids": sorted(r["qid"] for r in rows if r["boundary"])}
    print(json.dumps(out, indent=2))
    print("\n--- boundary-crossing shapes ---")
    for r in rows:
        if r["boundary"]:
            print(f"  {r['qid']:24} {'+'.join(r['reasons']):12} {r['measures']} by {r['dims']} | {r['filters']}")
    # merge into paper_numbers
    pn = _p("results", "paper_numbers.json")
    if os.path.exists(pn):
        N = json.load(open(pn)); N.setdefault("composability", {}).update(out)
        json.dump(N, open(pn, "w"), indent=2)
    return out

if __name__ == "__main__":
    main()
