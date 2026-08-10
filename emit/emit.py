#!/usr/bin/env python3
"""Emit the two grounding representations from ONE source of truth (semantic_models/*.yaml):
  - Condition G: a compact STRUCTURED serialization (metrics/joins/grains/vocab as a model).
  - Condition D: a conformant-ish OKF markdown bundle (the SAME facts as prose + md tables).
Parity by construction: both are generated here, so any D-vs-G delta is representation, not content.
Also emits the field catalog for condition S (what fields the model exposes).
"""
import os, yaml, textwrap

def load(path): return yaml.safe_load(open(path))

# ---------- Condition G: structured model serialization ----------
def emit_g(model):
    L = [f"# SEMANTIC MODEL (structured) — {model['title']}",
         f"# {model['description'].strip()}",
         f"# GRAIN: {model['grain_note'].strip()}", ""]
    L.append("JOINS (child -> parent, many-to-one):")
    for e in model["join_graph"]:
        L.append(f"  {e['from']} -> {e['to']}  ON {e['on_sql']}  [many_to_one]")
    L.append("")
    L.append("VOCABULARY (business term -> stored values):")
    for vn, v in model.get("vocabulary", {}).items():
        L.append(f"  {vn}: {v['description'].strip()}")
        for term, vals in v["map"].items():
            L.append(f"    '{term}' == {vals}")
    L.append("")
    L.append("DIMENSIONS:")
    for dn, d in model["dimensions"].items():
        extra = []
        if d.get("identity"): extra.append(f"IDENTITY of {d['identity']}")
        if d.get("label_for"): extra.append(f"LABEL for {d['label_for']} (not unique)")
        if d.get("vocabulary"): extra.append(f"vocab={d['vocabulary']}")
        L.append(f"  {dn} (source {d['source']}, {d['type']}): sql = {d['sql']}"
                 + (f"  [{'; '.join(extra)}]" if extra else "")
                 + (f"\n     -- {d['description'].strip()}" if d.get("description") else ""))
    L.append("")
    L.append("MEASURES (certified; each additive at its base grain):")
    for mn, m in model["measures"].items():
        if "ratio" in m:
            L.append(f"  {mn} (RATIO): {m['ratio']['numerator']} / {m['ratio']['denominator']}"
                     f"\n     -- {m['description'].strip()}")
        elif "expr" in m:
            L.append(f"  {mn} (DERIVED): {m['expr']}"
                     f"\n     components: {', '.join(m['components'])}"
                     f"\n     -- {m['description'].strip()}")
        else:
            L.append(f"  {mn} (base grain: {m['base']}):"
                     f"\n     agg    = {m['agg_sql']}"
                     + (f"\n     filter = {m['filter_sql']}" if m.get('filter_sql') else "")
                     + f"\n     -- {m['description'].strip()}")
        if m.get("synonyms"): L.append(f"     synonyms: {m['synonyms']}")
    return "\n".join(L) + "\n"

# ---------- Condition D: OKF-style markdown bundle ----------
def _frontmatter(d):
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in d.items()) + "---\n"

def emit_d_files(model, outdir):
    os.makedirs(outdir, exist_ok=True)
    files = {}
    ds = model["dataset"]
    # index
    idx = [_frontmatter({"type":"dataset","title":model["title"],"resource":ds,"tags":"[retail, sales]"}),
           f"# {model['title']}\n", model["description"].strip(), "\n\n## Grain\n",
           model["grain_note"].strip(), "\n\n## Concept documents\n",
           "- Tables: " + ", ".join(f"[{t}](./table_{t}.md)" for t in
                 sorted({d['source'] for d in model['dimensions'].values()} |
                        {m.get('base') for m in model['measures'].values() if m.get('base')})),
           "\n- Metrics: " + ", ".join(f"[{mn}](./metric_{mn}.md)" for mn in model["measures"]),
           "\n\n## Joins\n"]
    for e in model["join_graph"]:
        idx.append(f"- `{e['from']}` relates to `{e['to']}` as **many-to-one**, joined on "
                   f"`{e['on_sql']}`. Because it is many-to-one, aggregating a `{e['to']}`-grain "
                   f"measure across joined `{e['from']}` rows will double-count (fan-out).\n")
    idx.append("\n## Vocabulary\n")
    for vn, v in model.get("vocabulary", {}).items():
        idx.append(f"### {vn}\n{v['description'].strip()}\n\n")
        for term, vals in v["map"].items():
            idx.append(f"- The business term **{term}** is stored as {', '.join('`'+x+'`' for x in vals)} "
                       f"across different tables.\n")
    files["index.md"] = "".join(idx)

    # per-table docs (schema + dimension prose)
    by_table = {}
    for dn, d in model["dimensions"].items():
        by_table.setdefault(d["source"], []).append((dn, d))
    for t, dims in by_table.items():
        doc = [_frontmatter({"type":"table","title":t,"resource":f"{ds}.{t}","tags":"[schema]"}),
               f"# Table: `{t}`\n\n| field | type | meaning |\n|---|---|---|\n"]
        for dn, d in dims:
            note = d.get("description","").strip()
            if d.get("identity"): note += " This is the IDENTITY of the "+d["identity"]+"; group and count by this, not by any name."
            if d.get("label_for"): note += " This is a display LABEL for the "+d["label_for"]+" and is NOT unique — never aggregate by it."
            doc.append(f"| `{dn}` | {d['type']} | {note} (expression: `{d['sql']}`) |\n")
        files[f"table_{t}.md"] = "".join(doc)

    # per-metric docs (definition as prose + the exact SQL)
    for mn, m in model["measures"].items():
        fm = _frontmatter({"type":"metric","title":mn,"resource":f"{ds}.metric.{mn}","tags":"[certified]"})
        body = [fm, f"# Metric: {mn}\n\n{m['description'].strip()}\n\n"]
        if "ratio" in m:
            body.append(f"**Definition.** This is a ratio: `{m['ratio']['numerator']}` divided by "
                        f"`{m['ratio']['denominator']}`. The two components are at different grains, so it must "
                        f"be computed as a ratio of the two certified measures — never as an `AVG()` over rows.\n")
        elif "expr" in m:
            body.append(f"**Definition.** This is a certified derived measure: `{m['expr']}`, computed from the "
                        f"certified measures {', '.join('`'+c+'`' for c in m['components'])}. Each component is "
                        f"aggregated at its own grain and then combined — do not re-derive it from raw columns.\n")
        else:
            body.append(f"**Definition.** `{m['agg_sql']}`\n\n")
            if m.get("filter_sql"):
                body.append(f"**Certified filter (always apply).** `{m['filter_sql']}`\n\n")
            body.append(f"**Grain.** This measure is additive at the `{m['base']}` grain. Breaking it down by a "
                        f"dimension finer than that grain double-counts.\n")
        if m.get("synonyms"): body.append(f"\n**Also called:** {', '.join(m['synonyms'])}.\n")
        files[f"metric_{mn}.md"] = "".join(body)

    for name, content in files.items():
        open(os.path.join(outdir, name), "w").write(content)
    return files

def emit_d_context(model):
    """Concatenate the OKF bundle into a single markdown context string for the prompt."""
    import io
    tmp = "/tmp/_okf_d_ctx"
    files = emit_d_files(model, tmp)
    order = ["index.md"] + sorted(f for f in files if f.startswith("table_")) + \
            sorted(f for f in files if f.startswith("metric_"))
    return "\n\n".join(f"<!-- FILE: {f} -->\n{files[f]}" for f in order)

if __name__ == "__main__":
    HERE = os.path.dirname(__file__)
    for ds in ["d1"]:
        model = load(os.path.join(HERE, "..", "semantic_models", f"{ds}.yaml"))
        g = emit_g(model)
        open(os.path.join(HERE, "..", "semantic_models", f"{ds}_G.txt"), "w").write(g)
        okfdir = os.path.join(HERE, "..", "okf_bundles", ds)
        emit_d_files(model, okfdir)
        d = emit_d_context(model)
        # token proxy: whitespace tokens
        print(f"{ds}: G={len(g.split())} words / D(OKF)={len(d.split())} words  "
              f"(D/G ratio {len(d.split())/max(len(g.split()),1):.1f}x)")
