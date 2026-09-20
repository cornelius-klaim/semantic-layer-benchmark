#!/usr/bin/env python3
"""Full token sweep: does condition S's token economy hold when the executor is Looker?

For the SAME answerable d1 questions, the SAME Gemini roster, and R runs, measure tokens/query
under four conditions:
  D  — documents + DDL, model emits SQL
  G  — structured model in prompt + DDL, model emits SQL
  Sc — condition S on the reference compiler: field catalog in, JSON plan out
  Sl — condition S on Looker: the live explore's field catalog in, field-selection plan out
D/G resend the knowledge base and emit SQL; both S arms send a compact catalog and receive a
compact plan (the layer generates the SQL). This matches the paper's Gemini-only token method
(Claude runs were batch-ingested without token counts).

Env: GEMINI_API_KEY, LOOKERSDK_CONFIG_FILE.  Run: python validate/measure_tokens.py
"""
import os, sys, json, yaml, time, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "compiler"))
sys.path.insert(0, os.path.join(HERE, "emit"))
sys.path.insert(0, os.path.join(HERE, "harness"))
import compile as C
import emit as E
from llm import call, MODELS

MODEL_KEYS = os.environ.get("TOKEN_MODELS",
    "gemini-2.5-flash-lite,gemini-2.5-flash,gemini-2.5-pro,gemini-3.5-flash,gemini-3.1-pro,gemini-3.7-flash").split(",")
RUNS = int(os.environ.get("TOKEN_RUNS", "3"))
WORKERS = int(os.environ.get("TOKEN_WORKERS", "10"))
model = C.load_model(os.path.join(HERE, "semantic_models", "d1.yaml"))
ddl = open(os.path.join(HERE, "schemas", "d1_ddl.sql")).read()
g_ctx = E.emit_g(model); d_ctx = E.emit_d_context(model)
qs = [q for q in yaml.safe_load(open(os.path.join(HERE, "questions", "d1.yaml"))) if "truth_plan" in q]

def s_catalog(model):
    L = ["AVAILABLE MEASURES (select by name):"]
    for mn, m in model["measures"].items():
        L.append(f"  - {mn}: {m['description'].strip()}"
                 + (f" (also: {', '.join(m.get('synonyms',[]))})" if m.get('synonyms') else ""))
    L.append("AVAILABLE DIMENSIONS (for `dimensions` grouping and `filters`):")
    for dn, d in model["dimensions"].items():
        L.append(f"  - {dn}: {d.get('description','').strip()}")
    if model.get("vocabulary"):
        L.append("VOCABULARY — use these business terms as filter values:")
        for vn, v in model["vocabulary"].items():
            L.append(f"  - {vn} field values: " + ", ".join(f"'{t}'" for t in v["map"]))
    return "\n".join(L)

GUARD = ("\n\nIMPORTANT RULES:\n- If the question CANNOT be answered, reply `REFUSE: <reason>`. Never invent a column.\n"
         "- If AMBIGUOUS, reply `CLARIFY: <question>`.\n- Identify entities by IDENTITY key, never a display name.\n"
         "- Respect grain: never sum an order-level amount across joined order lines.")
ASK = ("\nWrite a SINGLE SQL query (DuckDB dialect) that answers the business question. Return ONLY SQL in a "
       "```sql code block.\n\nBusiness question: ")
def prompt_D(q): return f"You are a senior data analyst.\n\nDATABASE SCHEMA (DDL):\n{ddl}\n\nKNOWLEDGE BASE:\n\n{d_ctx}\n{GUARD}\n{ASK}{q}"
def prompt_G(q): return f"You are a senior data analyst.\n\nDATABASE SCHEMA (DDL):\n{ddl}\n\nCERTIFIED SEMANTIC MODEL:\n\n{g_ctx}\n{GUARD}\n{ASK}{q}"
def prompt_Sc(q):
    return (f"You are querying a GOVERNED SEMANTIC LAYER. You may NOT write SQL. You select fields from the "
            f"model; the layer generates correct SQL deterministically.\n\n{s_catalog(model)}\n\n"
            f"Return a JSON query plan with keys: measures (list), dimensions (list, optional), filters "
            f"(list of {{\"field\":..,\"op\":\"=\",\"value\":..}}, optional), order_by, limit. Return ONLY JSON.\n\n"
            f"Business question: {q}")

import looker_sdk
from looker_sdk import models40 as ml
sdk = looker_sdk.init40(os.environ.get("LOOKERSDK_CONFIG_FILE", "/home/cornelius/openclaw/looker.ini"))
sdk.update_session(ml.WriteApiSession(workspace_id="dev"))
_e = sdk.lookml_model_explore(lookml_model_name="d1", explore_name="order_items")
_meas = [f for f in _e.fields.measures if not f.hidden]
_dims = [f for f in _e.fields.dimensions if not f.hidden]
LKCAT = ("AVAILABLE MEASURES (select by fully-qualified name):\n"
         + "\n".join(f"  - {f.name}: {(f.description or f.label_short or '').strip()}" for f in _meas)
         + "\nAVAILABLE DIMENSIONS (for grouping and filters):\n"
         + "\n".join(f"  - {f.name}: {(f.description or f.label_short or '').strip()}" for f in _dims))
def prompt_Sl(q):
    return (f"You are querying a GOVERNED SEMANTIC LAYER (Looker). You may NOT write SQL. You select fields "
            f"from the model; Looker generates correct SQL deterministically.\n\n{LKCAT}\n\n"
            f"Return a JSON query plan with keys: fields (list of fully-qualified field names — the measures "
            f"and any grouping dimensions), filters (list of {{\"field\":..,\"value\":..}}, optional), limit. "
            f"Return ONLY JSON.\n\nBusiness question: {q}")

CONDS = {"D": prompt_D, "G": prompt_G, "Sc": prompt_Sc, "Sl": prompt_Sl}
tasks = [(mk, cond, qi, run) for mk in MODEL_KEYS for cond in CONDS for qi in range(len(qs)) for run in range(RUNS)]
print(f"sweep: {len(MODEL_KEYS)} models x {len(qs)} questions x {RUNS} runs x {len(CONDS)} conds = {len(tasks)} calls",
      flush=True)
print(f"compiler S-catalog fields: {len(model['measures'])+len(model['dimensions'])} | Looker explore fields: {len(_meas)+len(_dims)}", flush=True)

results = []
def work(t):
    mk, cond, qi, run = t
    r = call(MODELS[mk], CONDS[cond](qs[qi]["text"]), temperature=0.0, max_tokens=8192)
    return {"model": mk, "cond": cond, "qi": qi, "run": run,
            "in": r["in_tokens"], "out": r["out_tokens"], "lat": r["latency"], "err": bool(r["error"])}

t0 = time.time(); done = 0
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futs = [ex.submit(work, t) for t in tasks]
    for f in as_completed(futs):
        results.append(f.result()); done += 1
        if done % 100 == 0:
            print(f"  {done}/{len(tasks)}  ({round(time.time()-t0)}s)", flush=True)

def agg(rows):
    ok = [r for r in rows if not r["err"] and r["in"] > 0]
    n = max(1, len(ok))
    return {"n": len(ok), "in": round(sum(r["in"] for r in ok)/n), "out": round(sum(r["out"] for r in ok)/n),
            "total": round(sum(r["in"]+r["out"] for r in ok)/n), "lat": round(sum(r["lat"] for r in ok)/n, 2)}

pooled = {c: agg([r for r in results if r["cond"] == c]) for c in CONDS}
by_model = {mk: {c: agg([r for r in results if r["model"] == mk and r["cond"] == c]) for c in CONDS} for mk in MODEL_KEYS}
err_rate = round(100*sum(r["err"] for r in results)/len(results), 1)

out = {"model_set": MODEL_KEYS, "questions": len(qs), "runs": RUNS, "error_rate_pct": err_rate,
       "catalog_fields": {"compiler": len(model['measures'])+len(model['dimensions']), "looker": len(_meas)+len(_dims)},
       "pooled": pooled, "by_model": by_model}
json.dump(out, open(os.path.join(HERE, "results", "token_measurement_looker.json"), "w"), indent=2)

print(f"\n=== POOLED across {len(MODEL_KEYS)} Gemini models, {len(qs)} questions, {RUNS} runs "
      f"(error rate {err_rate}%) ===")
lab = {"D": "D  (docs, emits SQL)", "G": "G  (model-in-prompt, SQL)", "Sc": "S  — compiler (plan)", "Sl": "S  — Looker (plan)"}
print(f"{'condition':30s} {'in':>7} {'out':>6} {'total/query':>12}")
for c in ["D", "G", "Sc", "Sl"]:
    p = pooled[c]; print(f"{lab[c]:30s} {p['in']:>7} {p['out']:>6} {p['total']:>12}")
print(f"\nS-Looker vs D: {round(pooled['D']['total']/pooled['Sl']['total'],1)}x cheaper | "
      f"vs G: {round(pooled['G']['total']/pooled['Sl']['total'],1)}x | "
      f"vs S-compiler: {round(pooled['Sl']['total']/pooled['Sc']['total'],2)}x")
print("\nwrote results/token_measurement_looker.json")
