#!/usr/bin/env python3
"""Live second-engine validation: run every certified measure through the d1 LookML model on a
real Looker instance (Looker compiles the LookML to BigQuery SQL, with its own symmetric
aggregates) and check it reproduces results/certified_measures_d1.json to the cent.

This is the independent cross-check: the compiler (condition S) and Looker are two separate
implementations of one model; agreement to the cent is evidence that the result is a property
of the modeling discipline, not of one engine.

One-time Looker setup (see lookml/README.md): create a project from this LookML, point its
connection at the BigQuery dataset loaded by load_d1_to_bigquery.py, and register a model
named $LOOKER_MODEL.

Env:
  LOOKERSDK_CONFIG_FILE  looker.ini with API creds (or use env-var SDK config)
  LOOKER_MODEL           model name (default: d1)
  LOOKER_WORKSPACE       'dev' to validate an un-deployed dev branch, else 'production'
Run:  python validate/validate_lookml.py
"""
import os, json, looker_sdk
from looker_sdk import models40 as ml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.environ.get("LOOKER_MODEL", "d1")
WORKSPACE = os.environ.get("LOOKER_WORKSPACE", "production")
cert = json.load(open(os.path.join(HERE, "results", "certified_measures_d1.json")))["measures_scalar"]

# certified measure -> (explore, fully-qualified LookML field)
FIELD = {
 "net_revenue": ("order_items", "order_items.net_revenue"),
 "gross_revenue": ("order_items", "order_items.gross_revenue"),
 "gross_margin": ("order_items", "order_items.gross_margin"),
 "line_count": ("order_items", "order_items.line_count"),
 "aov": ("order_items", "order_items.aov"),
 "shipping_pct_of_revenue": ("order_items", "order_items.shipping_pct_of_revenue"),
 "net_revenue_after_refunds": ("order_items", "order_items.net_revenue_after_refunds"),
 "order_count": ("order_items", "orders.order_count"),
 "active_customers": ("order_items", "orders.active_customers"),
 "shipping_fee_total": ("order_items", "orders.shipping_fee_total"),
 "avg_shipping_fee": ("order_items", "orders.avg_shipping_fee"),
 "refund_total": ("order_items", "returns.refund_total"),
 "refund_qty": ("order_items", "returns.refund_qty"),
 "marketing_spend_total": ("marketing_spend", "marketing_spend.marketing_spend_total"),
}

sdk = looker_sdk.init40()
if WORKSPACE == "dev":
    sdk.update_session(ml.WriteApiSession(workspace_id="dev"))

def run(explore, fields):
    return json.loads(sdk.run_inline_query("json", ml.WriteQuery(
        model=MODEL, view=explore, fields=fields, limit="5000")))

def close(a, b):
    if a is None or b is None: return False
    return abs(float(a)-float(b)) <= max(0.01, abs(float(b))*1e-9)

print(f"{'measure':26s} {'Looker (BigQuery)':>20s} {'certified':>20s}  ok")
print("-"*72)
rows, passed, failed = {}, 0, 0
for m, (explore, field) in FIELD.items():
    got = run(explore, [field])[0][field]
    exp = cert[m].get("value")
    ok = close(got, exp)
    rows[m] = {"looker": got, "certified": float(exp), "ok": bool(ok)}
    passed += ok; failed += (not ok)
    print(f"{m:26s} {float(got):>20.4f} {float(exp):>20.4f}  {'PASS' if ok else 'FAIL'}")
print("-"*72)
print(f"{passed}/{passed+failed} certified measures reproduced on live Looker to the cent.")

# fan-out safety exercised through real Looker symmetric aggregates
bd = {}
bd["net_revenue_by_ship_region"] = run("order_items", ["orders.ship_region", "order_items.net_revenue"])
bd["refund_total_by_category"] = run("order_items", ["products.category", "returns.refund_total"])
ref_total = round(sum((r["returns.refund_total"] or 0) for r in bd["refund_total_by_category"]), 2)
print(f"refund_total over product-category breakdown (symmetric aggregate): {ref_total:,.2f} "
      f"(certified {cert['refund_total']['value']:,.2f})")

json.dump({"engine": "looker-bigquery", "instance": "<redacted Looker instance>",
           "model": MODEL, "passed": passed, "total": passed+failed,
           "measures": rows, "refund_by_category_total": ref_total,
           "net_revenue_by_region": bd["net_revenue_by_ship_region"]},
          open(os.path.join(HERE, "results", "lookml_validation_looker.json"), "w"),
          indent=2, default=str)
raise SystemExit(1 if failed else 0)
