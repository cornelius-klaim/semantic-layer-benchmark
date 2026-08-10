#!/usr/bin/env python3
"""Suite 6 — multi-turn runner. Plays each scripted conversation in a single chat session
per (condition, model, run) and logs a row per TURN. Grounding is provided once at the first
user turn (U: DDL; D: DDL+OKF; G: DDL+structured model; S: the field catalog + plan protocol).

Drift is what we measure: for U/D/G the full history is resent each turn, so a certified
definition established at turn 1 can silently mutate by turn 5. For S every turn is an
independent deterministic compile — drift is structurally impossible.
"""
import os, sys, json, re, glob, argparse
import yaml
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "compiler"))
sys.path.insert(0, os.path.join(HERE, "..", "emit"))
import compile as C
from llm import call_chat, MODELS
import run as R   # reuse prompt scaffolding, extraction, execution, ctx

ROOT = os.path.join(HERE, "..")
def _p(*a): return os.path.join(ROOT, *a)

def load_convos():
    return yaml.safe_load(open(_p("questions", "multiturn.yaml"))) or []

def _grounding(cond, ds):
    """The first-turn preamble that establishes the grounding for the whole conversation."""
    model, ddl, g, d, _ = R.ctx(ds)
    if cond == "U":
        return (f"You are a senior data analyst answering an ongoing series of questions about one "
                f"database. For EACH question, reply with a SINGLE DuckDB SQL query in a ```sql block.\n\n"
                f"DATABASE SCHEMA (DDL):\n{ddl}")
    if cond == "D":
        return (f"You are a senior data analyst answering an ongoing series of questions. For EACH "
                f"question reply with a SINGLE DuckDB SQL query in a ```sql block.\n\nDATABASE SCHEMA:\n{ddl}\n\n"
                f"KNOWLEDGE BASE (defines the business meaning; apply it consistently every turn):\n\n{d}")
    if cond == "G":
        return (f"You are a senior data analyst answering an ongoing series of questions. For EACH "
                f"question reply with a SINGLE DuckDB SQL query in a ```sql block.\n\nDATABASE SCHEMA:\n{ddl}\n\n"
                f"CERTIFIED SEMANTIC MODEL (use these exact definitions on every turn):\n\n{g}")
    if cond == "S":
        return (f"You are querying a GOVERNED SEMANTIC LAYER over a series of questions. You may NOT "
                f"write SQL. For EACH question return a JSON query plan with keys measures, dimensions, "
                f"filters, order_by, limit — or {{\"refuse\":\"...\"}} if unanswerable or ambiguous "
                f"(e.g. 'sales' could mean order count or revenue — refuse and ask which). To identify a "
                f"top entity, group by its IDENTITY dimension, never a display-name label.\n\n{R.s_catalog(model)}")

def run_convo(convo, cond, model_key, temperature=0.0):
    ds = convo["dataset"]; model, ddl, g, d, con = R.ctx(ds)
    history = [("user", _grounding(cond, ds))]
    # seed a model ack so the first real question reads as a follow-up
    history.append(("model", "Understood. I will apply these definitions consistently. Ask your first question."))
    rows = []
    for turn in convo["turns"]:
        history.append(("user", turn["text"]))
        resp = call_chat(MODELS[model_key], history, temperature=temperature)
        history.append(("model", resp["text"] or ""))
        out = {"prompt_tokens": resp["in_tokens"], "out_tokens": resp["out_tokens"],
               "latency": resp["latency"], "llm_error": resp["error"],
               "completion": (resp["text"] or "")[:2000]}
        if resp["error"] or not (resp["text"] or "").strip():
            out.update(outcome="error", detail="llm_error", rows=None, sql=None, plan=None)
        elif cond == "S":
            plan = R.extract_json(resp["text"]); out["plan"] = plan
            if plan is None:
                out.update(outcome="error", detail="unparseable_plan", rows=None, sql=None)
            else:
                comp = C.compile_plan(model, plan)
                if "refuse" in comp:
                    out.update(outcome="refusal", detail=comp["refuse"], rows=None, sql=None)
                else:
                    r = R.exec_sql(con, comp["sql"]); out["sql"] = comp["sql"]
                    out.update(outcome=("error" if r["error"] else "ok"),
                               detail=r["error"], rows=r["rows"])
        else:
            sql = R.extract_sql(resp["text"]); out["sql"] = sql
            if not re.search(r"\b(SELECT|WITH)\b", sql, re.I):
                out.update(outcome="refusal", detail=sql[:200], rows=None, plan=None)
            else:
                r = R.exec_sql(con, sql)
                out.update(outcome=("error" if r["error"] else "ok"), detail=r["error"],
                           rows=r["rows"], plan=None)
        row = {"qid": f"{convo['id']}_t{turn['t']}", "suite": 6, "dataset": ds,
               "condition": cond, "model": model_key, "run": 0, "turn": turn["t"],
               "conv": convo["id"], **out}
        rows.append((turn, row))
    return rows

def truth_of_turn(convo, turn):
    ds = convo["dataset"]; model, *_, con = R.ctx(ds)
    q = {"dataset": ds, "answer_type": turn.get("answer_type", "scalar"), **turn}
    return R.truth_of(q)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="gemini-2.5-flash")
    ap.add_argument("--conditions", default="U,D,G,S")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", default=_p("results", "runs_multiturn.jsonl"))
    a = ap.parse_args()
    convos = load_convos(); conds = a.conditions.split(","); models = a.models.split(",")
    fout = open(a.out, "a"); n = 0
    for convo in convos:
        for mk in models:
            for cond in conds:
                for run in range(a.runs):
                    for turn, row in run_convo(convo, cond, mk):
                        row["run"] = run
                        fout.write(json.dumps(row, default=str) + "\n"); fout.flush(); n += 1
                print(f"  {convo['id']:20} {cond} {mk} done ({n} turn-rows)", flush=True)
    fout.close(); print(f"TOTAL turn-rows: {n} -> {a.out}")

if __name__ == "__main__":
    main()
