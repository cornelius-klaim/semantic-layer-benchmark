#!/usr/bin/env python3
"""Composability accounting for the gold-table-vs-Semantic-Gold-Layer argument.

A wide denormalized gold *table* serves many single-grain GROUP BYs fine (revenue by region, by
category, by month — one table, three group-bys). So the honest claim is NOT "a table per slice"; it
is the subset of question-shapes that cross a **grain, fact, or domain boundary** no single
pre-aggregated table spans. This script classifies every plan-based question-shape and counts them,
emitting the list so the numbers are auditable/reproducible. Merges results into paper_numbers.json.
"""
import os, sys, json, glob, collections, ast, re
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


# --------------------------------------------------------------------------------------
# Authoring-cost footprint of the enforcement machinery.
#
# The paper's claim about the compiler is an INVARIANCE claim, and the AXIS is the whole
# point. What is constant is growth with the SEMANTIC MODEL (more measures, more dimensions)
# and with the number of DATASETS: one unchanged compiler serves d1 and d2, and would serve a
# 500-measure model without a line added. That is the claim the authoring-cost argument rests
# on, and it is the claim `compiler_model_refs` below actually proves.
#
# It is NOT a claim that the compiler never grows for any reason. Supporting an additional
# WAREHOUSE (a SQL dialect) does add code -- the BigQuery backend is real work. That is a
# different axis, and folding it into one number invites a fair-to-make but wrong reading
# ("adding a single backend grew your constant"). So the axes are measured separately, and
# the total is published too, so nothing is hidden:
#
#   compiler_governance_lines  the compiler proper, minus its __main__ smoke block
#   compiler_seam_lines        the dialect-agnostic part of dialects.py (the hook contract,
#                              the identity dialect, the error type, the registry) -- a
#                              ONE-TIME cost of being multi-warehouse at all, not per-backend
#   compiler_core_lines        governance + seam: what ships regardless of warehouse, and the
#                              number that is invariant in model size and dataset count
#   compiler_backend_lines     per-warehouse SQL translation, over compiler_backends backends
#   compiler_total_lines       every shipping line under compiler/ (core + backends + smoke)
#   compiler_test_lines        the dialect acceptance/unit harness -- disclosed, not counted
#                              as machinery
#   compiler_model_refs        THE PROOF: shipping compiler lines (all of compile.py except
#                              the __main__ smoke block, plus ALL of dialects.py -- backends
#                              included, so the scan is wider than the core it certifies)
#                              that name any measure, dimension, table or dataset from either
#                              semantic model. It is 0.
#
# The __main__ smoke block is excluded from the core deliberately: it loads d1.yaml and names
# real measures, so it is the only dataset-specific code in the compiler. Excluding it is what
# makes "dataset-agnostic" literally true of the lines actually counted -- the previous metric
# counted compile.py whole and quietly included those dataset-bound lines.
# --------------------------------------------------------------------------------------

# Top-level names in compiler/dialects.py that are warehouse-neutral. The criterion is
# mechanical and checkable: a name is CORE iff it is reachable on the IDENTITY (DuckDB) path
# -- imported by compile.py, or defined/called by the `Dialect` base class or the registry --
# so it ships even in a single-warehouse build. Everything else exists only to serve a
# concrete backend.
#   DialectError / Dialect / DUCKDB / get_dialect  the error type, hook contract, identity
#                                                  dialect, and registry
#   dim_ref                                        imported by compile.py and called
#                                                  unconditionally at compile.py:225, and
#                                                  again by Dialect.combine_measures: it runs
#                                                  on the DuckDB arm with no backend loaded
# The BigQuery-only SQL scanners (_skip_quoted, _match_paren, _split_args, _find_keyword,
# _mask_quoted, _unquote, _QUOTES) are NOT here: every call site is inside BigQueryDialect.
#
# Unknown names default to BACKEND. Note that default is *not* conservative for the paper's
# sentence -- misfiling warehouse-neutral code as backend makes the claimed constant look
# SMALLER than it is, which flatters the claim -- so this set is verified against call sites
# by hand rather than trusted to drift safely. The assertion below catches renames of the
# names listed; it cannot catch a genuinely new warehouse-neutral helper, so re-check the
# call sites whenever dialects.py gains a top-level definition.
DIALECT_CORE_NAMES = {"DialectError", "Dialect", "DUCKDB", "get_dialect", "dim_ref"}

# Keys this script used to emit. They are deleted from paper_numbers.json on merge so a stale
# value cannot survive and silently resolve a {{token}} in the paper with a number that no
# longer means what the sentence around it says.
RETIRED_KEYS = ("compiler_lines",)


def _top_level_spans(src):
    """[(node, first_line, last_line)] for each top-level statement, every line accounted for.

    A statement's span is extended backwards over the blank lines and comment banner that
    introduce it, so a `# ---- BigQuery ----` header is attributed to the block it heads
    rather than to whatever happened to precede it."""
    tree = ast.parse(src); lines = src.splitlines()
    out, prev_end = [], 0
    for node in tree.body:
        start = node.lineno
        for d in getattr(node, "decorator_list", None) or []:
            start = min(start, d.lineno)
        while start - 1 > prev_end:
            s = lines[start - 2].strip()
            if s and not s.startswith("#"):
                break
            start -= 1
        out.append((node, start, node.end_lineno)); prev_end = node.end_lineno
    return out, len(lines)


def _node_name(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None   # imports, module docstring, `if __name__ == "__main__"` -- all core


def _model_vocab(models):
    """Every identifier the semantic models contribute: dataset ids, measure and dimension
    names, and the tables those are sourced from. If the compiler branched on any of these it
    would not be model-agnostic, and the claim would be false."""
    v = set()
    for ds, m in models.items():
        v.add(ds)
        for mn, mv in (m.get("measures") or {}).items():
            v.add(mn)
            if isinstance(mv, dict) and mv.get("base"): v.add(mv["base"])
        for dn, dv in (m.get("dimensions") or {}).items():
            v.add(dn)
            if isinstance(dv, dict) and dv.get("source"): v.add(dv["source"])
    return v


def _code_model_refs(path, vocab, lo, hi):
    """Model-vocabulary tokens appearing in real CODE on lines lo..hi of `path`.

    Comments are invisible to ast, and docstrings are skipped explicitly: dialects.py explains
    its own contract with examples like `orders.order_ts`, which is prose about the seam and
    not a dependency on the retail model. What would actually falsify the invariance claim is
    the compiler *branching on* a model name, and that has to show up as an identifier or a
    string literal in executable code."""
    tree = ast.parse(open(path).read())
    docstrings = set()
    for n in ast.walk(tree):
        body = getattr(n, "body", None)
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
           and body and isinstance(body[0], ast.Expr) \
           and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            docstrings.add(id(body[0].value))
    hits = set()
    for n in ast.walk(tree):
        ln = getattr(n, "lineno", None)
        if ln is None or not (lo <= ln <= hi):
            continue
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings:
            for w in vocab:
                if re.search(rf"\b{re.escape(w)}\b", n.value): hits.add((ln, w))
        elif isinstance(n, ast.Name) and n.id in vocab:
            hits.add((ln, n.id))
        elif isinstance(n, ast.Attribute) and n.attr in vocab:
            hits.add((ln, n.attr))
    return sorted(hits)


def compiler_footprint(models):
    """Split compiler/ along the two axes and prove the model-invariance claim."""
    cpath, dpath = _p("compiler", "compile.py"), _p("compiler", "dialects.py")

    # compile.py: importable governance machinery vs the dataset-bound __main__ smoke block
    spans, c_total = _top_level_spans(open(cpath).read())
    smoke = sum(b - a + 1 for node, a, b in spans
                if isinstance(node, ast.If) and "__main__" in ast.dump(node.test))
    governance = c_total - smoke

    # dialects.py: warehouse-neutral seam vs per-warehouse backends
    seam = backend = d_total = n_backends = 0
    backend_detail = []
    if os.path.exists(dpath):
        spans, d_total = _top_level_spans(open(dpath).read())
        missing = DIALECT_CORE_NAMES - {_node_name(n) for n, _, _ in spans}
        if missing:
            raise SystemExit(f"composability: compiler/dialects.py no longer defines "
                             f"{sorted(missing)} at top level. Update DIALECT_CORE_NAMES "
                             f"before trusting these line counts.")
        for node, a, b in spans:
            name = _node_name(node)
            if name is None or name in DIALECT_CORE_NAMES:
                continue
            backend += b - a + 1; backend_detail.append((name, a, b))
            # a concrete warehouse = a Dialect subclass that is not the identity dialect
            if isinstance(node, ast.ClassDef) and any(
                    getattr(base, "id", None) == "Dialect" for base in node.bases):
                n_backends += 1
        seam = d_total - backend

    core = governance + seam
    total = c_total + d_total
    assert core + backend + smoke == total, (core, backend, smoke, total)

    # the acceptance/unit harness -- disclosed so the total cannot be called concealed, but it
    # is verification, not machinery, so it is not part of any compiler count above
    test_lines = sum(len(open(f).read().splitlines())
                     for f in sorted(glob.glob(_p("compiler", "test_*.py"))
                                     + glob.glob(_p("compiler", "accept_*.py"))))

    # THE PROOF. Every line of core machinery, checked against the model vocabulary.
    vocab = _model_vocab(models)
    refs = _code_model_refs(cpath, vocab, 1, governance)
    if os.path.exists(dpath):
        refs += _code_model_refs(dpath, vocab, 1, d_total)

    return {"compiler_governance_lines": governance, "compiler_seam_lines": seam,
            "compiler_core_lines": core, "compiler_backend_lines": backend,
            "compiler_backends": n_backends, "compiler_smoke_lines": smoke,
            "compiler_total_lines": total, "compiler_test_lines": test_lines,
            "compiler_model_refs": len(refs), "compiler_datasets": len(models)}, refs, backend_detail


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
    # authoring-cost footprint: the governed layer is a small, human-readable artifact, and the
    # enforcement machinery is constant in the size of that artifact. See compiler_footprint().
    models = {ds: yaml.safe_load(open(_p("semantic_models", f"{ds}.yaml"))) for ds in ("d1", "d2")}
    d1 = models["d1"]
    d1_lines = len(open(_p("semantic_models", "d1.yaml")).read().splitlines())
    footprint, model_refs, backend_detail = compiler_footprint(models)
    n_meas_d1 = len(d1["measures"]); n_dims_d1 = len(d1["dimensions"])
    out = {"n_measures": nmeas, "n_shapes": nshapes, "n_boundary": nbound,
           "boundary_grain": by_reason.get("grain/fact", 0), "boundary_domain": by_reason.get("domain", 0),
           "netrev_slices": len(nr),
           "d1_lines": d1_lines,
           "n_measures_d1": n_meas_d1, "n_dims_d1": n_dims_d1, "single_slices_d1": n_meas_d1*n_dims_d1,
           "boundary_qids": sorted(r["qid"] for r in rows if r["boundary"])}
    out.update(footprint)
    print(json.dumps(out, indent=2))
    print("\n--- boundary-crossing shapes ---")
    for r in rows:
        if r["boundary"]:
            print(f"  {r['qid']:24} {'+'.join(r['reasons']):12} {r['measures']} by {r['dims']} | {r['filters']}")
    print("\n--- compiler footprint (two axes, kept apart) ---")
    print(f"  governance (compile.py, no __main__)  {footprint['compiler_governance_lines']:5}")
    print(f"  dialect seam (warehouse-neutral)      {footprint['compiler_seam_lines']:5}")
    print(f"  = CORE, invariant in model & dataset  {footprint['compiler_core_lines']:5}")
    print(f"  backends ({footprint['compiler_backends']}) -- grows per warehouse   "
          f"{footprint['compiler_backend_lines']:5}")
    print(f"  __main__ smoke (dataset-bound demo)   {footprint['compiler_smoke_lines']:5}")
    print(f"  = TOTAL shipping lines in compiler/   {footprint['compiler_total_lines']:5}")
    print(f"  acceptance/unit harness (disclosed)   {footprint['compiler_test_lines']:5}")
    for name, a, b in backend_detail:
        print(f"      backend: {name:24} L{a}-{b}")
    print(f"\n  model-vocabulary references in all shipping compiler code (core + backends, "
          f"excluding the __main__ smoke block): {len(model_refs)} "
          f"(over {len(_model_vocab(models))} model identifiers, {len(models)} datasets)")
    for ln, w in model_refs:
        print(f"      L{ln}: {w}")
    if model_refs:
        raise SystemExit("composability: the compiler now names model/dataset identifiers in "
                         "core code. 'does not grow with the model' is no longer proven -- fix "
                         "the compiler or fix the paper sentence.")

    # merge into paper_numbers
    pn = _p("results", "paper_numbers.json")
    if os.path.exists(pn):
        N = json.load(open(pn))
        comp = N.setdefault("composability", {})
        for k in RETIRED_KEYS:
            comp.pop(k, None)   # a stale value must not silently resolve a {{token}}
        comp.update(out)
        json.dump(N, open(pn, "w"), indent=2)
    return out

if __name__ == "__main__":
    main()
