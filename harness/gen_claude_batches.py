#!/usr/bin/env python3
"""Generate self-contained prompt files for the Claude arm (run via Claude Code subagents).

For each (dataset, condition) we emit ONE prompt showing the grounding once, then listing every
question for that dataset, and asking for a single JSON object mapping qid -> answer (SQL for
U/D/G; a query plan or {"refuse":...} for S). A subagent answers each question INDEPENDENTLY and
writes the JSON to a fixed output path; `ingest_claude.py` then executes/compiles and scores it
through the identical pipeline used for the Gemini arm.

Per-(dataset,condition) batching (grounding shown once, questions answered independently) is the
Claude-arm protocol; it is documented as a methodological variant of the per-call Gemini arm.
"""
import os, sys, json
HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "compiler"))
sys.path.insert(0, os.path.join(HERE, "..", "emit"))
import run as R
ROOT = os.path.join(HERE, "..");
def _p(*a): return os.path.join(ROOT, *a)

PROMPT_DIR = _p("results", "claude_prompts"); os.makedirs(PROMPT_DIR, exist_ok=True)
RAW_DIR    = _p("results", "claude_raw");     os.makedirs(RAW_DIR, exist_ok=True)

HEAD = {
 "U": "You are a senior data analyst. You are given ONLY the physical database schema.",
 "D": "You are a senior data analyst. You are given the schema plus a KNOWLEDGE BASE that defines the business meaning of the data — read it carefully and apply it.",
 "G": "You are a senior data analyst. You are given the schema plus a CERTIFIED SEMANTIC MODEL — use these definitions exactly.",
 "S": "You are querying a GOVERNED SEMANTIC LAYER. You may NOT write SQL. You select fields from the model; the layer generates correct SQL deterministically.",
}

def grounding(cond, ds):
    model, ddl, g, d, _ = R.ctx(ds)
    if cond == "U": return f"DATABASE SCHEMA (DDL):\n{ddl}"
    if cond == "D": return f"DATABASE SCHEMA (DDL):\n{ddl}\n\nKNOWLEDGE BASE:\n\n{d}"
    if cond == "G": return f"DATABASE SCHEMA (DDL):\n{ddl}\n\nCERTIFIED SEMANTIC MODEL:\n\n{g}"
    if cond == "S": return R.s_catalog(model)

def answer_spec(cond):
    if cond == "S":
        return ('For each question return a query PLAN: a JSON object with keys "measures" (list of '
                'measure names), "dimensions" (list, optional), "filters" (list of '
                '{"field":..,"op":"=","value":..}, optional), "order_by" ({"field":..,"dir":"desc"}, '
                'optional), "limit" (int, optional). If a question CANNOT be answered from the listed '
                'fields, return {"refuse":"<reason>"} for it. If a question is AMBIGUOUS (e.g. "sales" '
                'could mean order count or revenue dollars), do NOT guess — return '
                '{"refuse":"clarify: ..."}. To identify a top entity, group by its IDENTITY dimension '
                '(the one described as THE identifier), never a display-name label.')
    return ('For each question return a SINGLE DuckDB SQL query string that answers it directly.')

def build(ds, cond, questions):
    qs = [q for q in questions if q["dataset"] == ds
          and cond in q.get("conditions", ["U","D","G","S"])]
    outpath = os.path.join(RAW_DIR, f"{{tier}}__{ds}__{cond}.json")
    lines = [
        HEAD[cond], "",
        grounding(cond, ds), "",
        "="*70,
        "Answer EACH of the following business questions INDEPENDENTLY (do not let one question "
        "influence another). " + answer_spec(cond), "",
        'Return ONE JSON object mapping each question id to its answer, e.g. '
        + ('{"q1": {"measures":["net_revenue"]}, "q2": {"refuse":"no such field"}}' if cond=="S"
           else '{"q1": "SELECT ...", "q2": "SELECT ..."}') + "",
        "", "QUESTIONS:",
    ]
    for q in qs:
        lines.append(f'  [{q["id"]}] {q["text"]}')
    return "\n".join(lines), outpath, [q["id"] for q in qs]

def main():
    questions = R.load_questions()
    manifest = []
    for ds in ["d1", "d2"]:
        for cond in ["U", "D", "G", "S"]:
            body, outpath, qids = build(ds, cond, questions)
            fname = f"{ds}__{cond}.txt"
            open(os.path.join(PROMPT_DIR, fname), "w").write(body)
            manifest.append({"dataset": ds, "condition": cond, "prompt_file": fname,
                             "out_template": os.path.basename(outpath), "qids": qids,
                             "n_questions": len(qids)})
    json.dump(manifest, open(os.path.join(PROMPT_DIR, "manifest.json"), "w"), indent=2)
    total = sum(m["n_questions"] for m in manifest)
    print(f"wrote {len(manifest)} batch prompts ({total} question-answers per tier) -> {PROMPT_DIR}")
    for m in manifest:
        print(f"  {m['dataset']} {m['condition']}: {m['n_questions']} questions -> {m['prompt_file']}")

if __name__ == "__main__":
    main()
