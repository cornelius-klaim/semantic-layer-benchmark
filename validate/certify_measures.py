#!/usr/bin/env python3
"""Emit results/certified_measures_d1.json — each measure's certified value, computed by the
benchmark's own compiler (condition S) over the seeded d1 warehouse. This is the ground truth
the LookML realization is validated against. Run after `make data`."""
import duckdb, os, json, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "compiler"))
import compile as C

model = C.load_model(os.path.join(HERE, "semantic_models", "d1.yaml"))
con = duckdb.connect(os.path.join(HERE, "warehouse", "d1.duckdb"), read_only=True)

certified = {}
for m in model["measures"]:
    r = C.run_plan(model, {"measures": [m]}, con)
    certified[m] = {"refuse": r["refuse"]} if "refuse" in r else {"value": r["rows"][0][0]}

breakdowns = {
 "net_revenue__by_ship_region": {"measures": ["net_revenue"], "dimensions": ["ship_region"]},
 "refund_total__by_category":   {"measures": ["refund_total"], "dimensions": ["product_category"]},
 "shipping_by_category_MUST_REFUSE": {"measures": ["shipping_fee_total"], "dimensions": ["product_category"]},
 "net_revenue__paid_search": {"measures": ["net_revenue"],
     "filters": [{"field": "order_channel", "op": "=", "value": "Paid Search"}]},
}
bd = {}
for k, p in breakdowns.items():
    r = C.run_plan(model, p, con)
    bd[k] = {"refuse": r["refuse"]} if "refuse" in r else {"rows": r["rows"]}

out = {"dataset": "d1", "measures_scalar": certified, "breakdowns": bd}
json.dump(out, open(os.path.join(HERE, "results", "certified_measures_d1.json"), "w"),
          indent=2, default=str)
print("wrote results/certified_measures_d1.json —",
      sum("value" in v for v in certified.values()), "certified scalar measures")
