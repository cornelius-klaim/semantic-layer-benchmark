#!/usr/bin/env python3
"""Reproducible (no-Looker) parity check for the d1 LookML realization.

Builds the exact denormalized join the `order_items` explore defines, then computes every
certified measure the way the LookML model computes it — line-grain measures directly, and
order-grain measures (shipping_fee_total, avg_shipping_fee, order_count, active_customers) with
the fan-out-safe form Looker's SYMMETRIC AGGREGATES emit given the declared primary keys. Each
result is checked against results/certified_measures_d1.json (the compiler's certified values).

It also prints the two traps the model must survive: the shipping-fee fan-out (naive SUM over
the joined lines) and the returns partial-key fan-out (joining on order_id alone).

Run:  python validate/validate_lookml_duckdb.py   (needs warehouse/d1.duckdb; `make data` first)
"""
import duckdb, json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
con = duckdb.connect(os.path.join(HERE, "warehouse", "d1.duckdb"), read_only=True)
cert = json.load(open(os.path.join(HERE, "results", "certified_measures_d1.json")))["measures_scalar"]

# The explore's base row set: order_items with its many_to_one / one_to_one joins. None of these
# joins duplicate a line, so this view is at line grain (one row per order_item).
JOIN = """
FROM order_items oi
LEFT JOIN orders    o ON oi.order_id   = o.order_id
LEFT JOIN products  p ON oi.product_key= p.product_key
LEFT JOIN returns   r ON oi.order_id   = r.order_id AND oi.line_number = r.line_number
"""
FULFILLED = "o.status IN (3,4)"          # the certified shipped/delivered filter

# Each measure as the LookML model computes it. Order-grain measures are de-duplicated to one
# row per order_id first — exactly what a symmetric aggregate does on the fanned-out join.
DISTINCT_ORDERS = f"(SELECT DISTINCT o.order_id, o.customer_key, o.shipping_fee FROM order_items oi LEFT JOIN orders o ON oi.order_id=o.order_id WHERE {FULFILLED})"

measures = {
 "net_revenue":       f"SELECT SUM(oi.quantity*oi.unit_price*(1-oi.discount_rate)) {JOIN} WHERE {FULFILLED}",
 "gross_revenue":     f"SELECT SUM(oi.quantity*oi.unit_price) {JOIN} WHERE {FULFILLED}",
 "gross_margin":      f"SELECT SUM(oi.quantity*oi.unit_price*(1-oi.discount_rate) - oi.quantity*p.unit_cost) {JOIN} WHERE {FULFILLED}",
 "line_count":        f"SELECT COUNT(*) {JOIN} WHERE {FULFILLED}",
 "order_count":       f"SELECT COUNT(DISTINCT oi.order_id) {JOIN} WHERE {FULFILLED}",
 "active_customers":  f"SELECT COUNT(DISTINCT o.customer_key) {JOIN} WHERE {FULFILLED}",
 "shipping_fee_total":f"SELECT SUM(shipping_fee) FROM {DISTINCT_ORDERS}",
 "avg_shipping_fee":  f"SELECT AVG(shipping_fee) FROM {DISTINCT_ORDERS}",
 "refund_total":      f"SELECT SUM(r.refund_amount) {JOIN}",
 "refund_qty":        f"SELECT SUM(r.return_qty) {JOIN}",
 "marketing_spend_total": "SELECT SUM(spend) FROM marketing_spend",
}
# ratio / expression measures (measures of measures)
def val(sql): return con.execute(sql).fetchone()[0]
nr = val(measures["net_revenue"]); oc = val(measures["order_count"])
sft = val(measures["shipping_fee_total"]); rt = val(measures["refund_total"])
derived = {
 "aov": nr/oc,
 "shipping_pct_of_revenue": 100.0*sft/nr,
 "net_revenue_after_refunds": nr - rt,
}

def close(a, b):
    if a is None or b is None: return False
    return abs(float(a)-float(b)) <= max(0.01, abs(float(b))*1e-9)

print(f"{'measure':26s} {'LookML (duckdb)':>20s} {'certified':>20s}  ok")
print("-"*72)
passed = failed = 0
rows = {}
for m in list(measures) + list(derived):
    got = val(measures[m]) if m in measures else derived[m]
    exp = cert[m].get("value")
    ok = close(got, exp)
    rows[m] = {"lookml": float(got), "certified": float(exp), "ok": bool(ok)}
    passed += ok; failed += (not ok)
    print(f"{m:26s} {float(got):>20.4f} {float(exp):>20.4f}  {'PASS' if ok else 'FAIL'}")

print("-"*72)
print(f"{passed}/{passed+failed} measures reproduce the certified value to the cent.\n")

# --- the two traps the model must survive ---
naive_ship = val(f"SELECT SUM(o.shipping_fee) {JOIN} WHERE {FULFILLED}")
print(f"TRAP 1 (shipping fan-out): naive SUM over joined lines = {naive_ship:,.2f} "
      f"vs fan-out-safe {sft:,.2f}  (inflation {naive_ship/sft:.2f}x)")
partial = val("SELECT SUM(r.refund_amount) FROM returns r JOIN order_items oi ON r.order_id=oi.order_id")
print(f"TRAP 2 (returns partial key): join on order_id alone = {partial:,.2f} "
      f"vs compound-key {rt:,.2f}  (inflation {partial/rt:.2f}x)")

json.dump({"engine":"duckdb-lookml-parity","measures":rows},
          open(os.path.join(HERE,"results","lookml_validation_duckdb.json"),"w"), indent=2)
sys.exit(1 if failed else 0)
