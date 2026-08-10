#!/usr/bin/env python3
"""Runner: for each (question, condition, model, run) build the prompt, call the model,
extract SQL (U/D/G) or a query-plan (S), execute on DuckDB, and log everything to JSONL."""
import os, sys, json, re, glob, time, argparse
import duckdb, yaml
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "compiler"))
sys.path.insert(0, os.path.join(HERE, "..", "emit"))
import compile as C
import emit as E
from llm import call, MODELS

ROOT = os.path.join(HERE, "..")
def _p(*a): return os.path.join(ROOT, *a)

# ---- cache models / contexts / connections per dataset ----
_cache = {}
def ctx(ds):
    if ds in _cache: return _cache[ds]
    model = C.load_model(_p("semantic_models", f"{ds}.yaml"))
    ddl = open(_p("schemas", f"{ds}_ddl.sql")).read()
    g = E.emit_g(model); d = E.emit_d_context(model)
    con = duckdb.connect(_p("warehouse", f"{ds}.duckdb"), read_only=True)
    _cache[ds] = (model, ddl, g, d, con)
    return _cache[ds]

def s_catalog(model):
    L = ["AVAILABLE MEASURES (select by name):"]
    for mn, m in model["measures"].items():
        L.append(f"  - {mn}: {m['description'].strip()}"
                 + (f" (also: {', '.join(m.get('synonyms',[]))})" if m.get('synonyms') else ""))
    L.append("AVAILABLE DIMENSIONS (for `dimensions` grouping and `filters`):")
    for dn, d in model["dimensions"].items():
        note = d.get("description", "").strip()
        L.append(f"  - {dn}: {note}")
    if model.get("vocabulary"):
        L.append("VOCABULARY — use these business terms as filter values:")
        for vn, v in model["vocabulary"].items():
            L.append(f"  - {vn} field values: " + ", ".join(f"'{t}'" for t in v["map"]))
    return "\n".join(L)

# ---- prompt builders ----
def prompt(cond, q, ds):
    model, ddl, g, d, _ = ctx(ds)
    ask = (f"\nWrite a SINGLE SQL query (DuckDB dialect) that answers the business question, "
           f"returning the answer directly. Return ONLY SQL in a ```sql code block, no prose.\n\n"
           f"Business question: {q}")
    # Shared guardrail added to the grounded free-form conditions (D, G): refuse the unanswerable,
    # clarify the ambiguous, and respect identity-vs-label / grain. A prompt-level instruction — it
    # can only *ask* the model to comply; unlike condition S it cannot enforce.
    guard = ("\n\nIMPORTANT RULES:\n"
             "- If the question CANNOT be answered from the available tables/columns, reply with "
             "exactly `REFUSE: <reason>` and no SQL. Never invent a column or table.\n"
             "- If the question is AMBIGUOUS (e.g. 'sales' could mean the number of orders or the "
             "revenue in dollars, or 'best product' has no defined metric), reply with exactly "
             "`CLARIFY: <the question you would ask>` and no SQL.\n"
             "- To identify a specific entity (e.g. the single top customer), group by its IDENTITY "
             "key, never a display name (names are not unique).\n"
             "- Respect grain: never sum an order-level amount across joined order lines.")
    if cond == "U":
        return f"You are a senior data analyst.\n\nDATABASE SCHEMA (DDL):\n{ddl}\n{ask}"
    if cond == "P0":
        # gold tables only, NAIVE prompt (no refuse affordance) — the typical "just answer" setup
        gold = open(_p("schemas", f"{ds}_gold_ddl.sql")).read()
        return f"You are a senior data analyst.\n\nDATABASE SCHEMA (DDL):\n{gold}\n{ask}"
    if cond == "P":
        gold = open(_p("schemas", f"{ds}_gold_ddl.sql")).read()
        return ("You are a senior data analyst. You have access to ONLY the following pre-aggregated "
                "summary ('gold') tables; the detailed records beneath them are not available.\n\n"
                f"DATABASE SCHEMA (DDL):\n{gold}\n"
                "\nAnswer the business question with a SINGLE DuckDB SQL query over these tables, returning "
                "the answer directly in a ```sql code block. If the question genuinely cannot be answered "
                "from these summary tables, reply with exactly `REFUSE: <reason>` instead of guessing.\n\n"
                f"Business question: {q}")
    if cond == "D":
        return (f"You are a senior data analyst.\n\nDATABASE SCHEMA (DDL):\n{ddl}\n\n"
                f"KNOWLEDGE BASE (read carefully — it defines the business meaning of the data):\n\n{d}\n{guard}\n{ask}")
    if cond == "G":
        return (f"You are a senior data analyst.\n\nDATABASE SCHEMA (DDL):\n{ddl}\n\n"
                f"CERTIFIED SEMANTIC MODEL (use these definitions exactly):\n\n{g}\n{guard}\n{ask}")
    if cond == "S":
        return (f"You are querying a GOVERNED SEMANTIC LAYER. You may NOT write SQL. You select fields "
                f"from the model; the layer generates correct SQL deterministically.\n\n{s_catalog(model)}\n\n"
                f"Return a JSON query plan with keys: measures (list of measure names), dimensions "
                f"(list, optional), filters (list of {{\"field\":..,\"op\":\"=\",\"value\":..}}, optional), "
                f"order_by ({{\"field\":..,\"dir\":\"desc\"}}, optional), limit (int, optional).\n"
                f"If the question CANNOT be answered with these fields, return {{\"refuse\":\"<reason>\"}}.\n"
                f"If the question is AMBIGUOUS (e.g. 'sales' could mean the number of orders OR revenue "
                f"in dollars), do NOT guess — return {{\"refuse\":\"clarify: <which measure did you mean>\"}}.\n"
                f"To rank or identify a specific entity (e.g. the single top customer), group by its "
                f"IDENTITY dimension (the one described as THE identifier), never by a display name/label.\n"
                f"Return ONLY JSON.\n\nBusiness question: {q}")

# ---- extraction ----
def extract_sql(text):
    m = re.search(r"```sql\s*(.*?)```", text, re.S | re.I) or re.search(r"```\s*(SELECT.*?)```", text, re.S | re.I)
    sql = (m.group(1) if m else text).strip()
    m2 = re.search(r"(SELECT|WITH)\b.*", sql, re.S | re.I)
    return (m2.group(0) if m2 else sql).strip().rstrip(";")

def extract_json(text):
    m = re.search(r"```json\s*(.*?)```", text, re.S | re.I) or re.search(r"(\{.*\})", text, re.S)
    if not m: return None
    try: return json.loads(m.group(1))
    except Exception:
        try: return json.loads(re.sub(r",\s*}", "}", m.group(1)))
        except Exception: return None

# ---- execution ----
def exec_sql(con, sql):
    try:
        rows = con.execute(sql).fetchall()
        return {"rows": rows, "error": None}
    except Exception as e:
        return {"rows": None, "error": str(e)[:300]}

def run_condition(cond, q, ds, model_key, temperature=0.0):
    model, ddl, g, d, con = ctx(ds)
    pr = prompt(cond, q, ds)
    resp = call(MODELS[model_key], pr, temperature=temperature)
    out = {"prompt_tokens": resp["in_tokens"], "out_tokens": resp["out_tokens"],
           "latency": resp["latency"], "llm_error": resp["error"], "completion": resp["text"][:4000]}
    if resp["error"] or not resp["text"].strip():
        out.update(outcome="error", detail="llm_error", rows=None, sql=None); return out
    if cond == "S":
        plan = extract_json(resp["text"])
        out["plan"] = plan
        if plan is None:
            out.update(outcome="error", detail="unparseable_plan", rows=None, sql=None); return out
        comp = C.compile_plan(model, plan)
        if "refuse" in comp:
            out.update(outcome="refusal", detail=comp["refuse"], rows=None, sql=None); return out
        out["sql"] = comp["sql"]
        r = exec_sql(con, comp["sql"])
        if r["error"]: out.update(outcome="error", detail=r["error"], rows=None); return out
        out.update(outcome="ok", detail=None, rows=r["rows"]); return out
    else:
        sql = extract_sql(resp["text"]); out["sql"] = sql
        # refusal detection for SQL conditions (model declines)
        if not re.search(r"\b(SELECT|WITH)\b", sql, re.I):
            out.update(outcome="refusal", detail=sql[:200], rows=None); return out
        r = exec_sql(con, sql)
        if r["error"]: out.update(outcome="error", detail=r["error"], rows=None); return out
        out.update(outcome="ok", detail=None, rows=r["rows"]); return out

# ---- ground truth from the certified model (compiler) over seeded data ----
def truth_of(q):
    ds = q["dataset"]; model, *_ , con = ctx(ds)
    if "truth_plan" in q:
        r = C.run_plan(model, q["truth_plan"], con)
        if "refuse" in r: return {"kind": "refusal"}
        return {"kind": q.get("answer_type", "scalar"), "rows": r["rows"]}
    if "truth_sql" in q:
        rows = con.execute(q["truth_sql"]).fetchall()
        return {"kind": q.get("answer_type", "scalar"), "rows": rows}
    if q.get("answer_type") in ("refusal","clarify"):
        return {"kind": q["answer_type"]}
    if False:
        return {"kind": "refusal"}
    return {"kind": "unknown"}

def load_questions():
    qs = []
    for f in sorted(glob.glob(_p("questions", "*.yaml"))):
        if os.path.basename(f) == "multiturn.yaml":  # different shape; flattened separately
            continue
        qs += yaml.safe_load(open(f)) or []
    return qs

def load_multiturn_questions():
    """Flatten conversations into per-turn pseudo-questions keyed '<conv>_t<turn>'."""
    out = []
    path = _p("questions", "multiturn.yaml")
    if not os.path.exists(path): return out
    for convo in (yaml.safe_load(open(path)) or []):
        for turn in convo["turns"]:
            q = {"id": f"{convo['id']}_t{turn['t']}", "suite": 6, "dataset": convo["dataset"],
                 "turn": turn["t"], "conv": convo["id"]}
            q.update({k: v for k, v in turn.items() if k != "t"})
            out.append(q)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="gemini-2.5-flash")
    ap.add_argument("--conditions", default="U,D,G,S")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--suites", default="")   # comma list to filter
    ap.add_argument("--qids", default="")      # comma list of specific question ids to filter
    ap.add_argument("--out", default=_p("results", "runs.jsonl"))
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(_p("results"), exist_ok=True)
    qs = load_questions()
    if a.suites:
        keep = set(a.suites.split(",")); qs = [q for q in qs if str(q["suite"]) in keep]
    if a.qids:
        keepq = set(a.qids.split(",")); qs = [q for q in qs if q["id"] in keepq]
    if a.limit: qs = qs[:a.limit]
    models = a.models.split(","); conds = a.conditions.split(",")
    fout = open(a.out, "a")
    n = 0
    for q in qs:
        qconds = [c for c in conds if c in q.get("conditions", ["U","D","G","S"])]
        for mk in models:
            for cond in qconds:
                for run in range(a.runs):
                    try:
                        res = run_condition(cond, q["text"], q["dataset"], mk)
                    except Exception as e:
                        res = {"outcome": "error", "detail": f"harness_exc:{type(e).__name__}:{str(e)[:200]}",
                               "rows": None, "sql": None, "prompt_tokens": 0, "out_tokens": 0,
                               "latency": 0, "llm_error": None, "completion": ""}
                    row = {"qid": q["id"], "suite": q["suite"], "dataset": q["dataset"],
                           "condition": cond, "model": mk, "run": run, **res}
                    fout.write(json.dumps(row, default=str) + "\n"); fout.flush()
                    n += 1
        print(f"  {q['id']:16} done ({n} runs so far)", flush=True)
    fout.close()
    print(f"TOTAL runs logged: {n} -> {a.out}")

if __name__ == "__main__":
    main()
