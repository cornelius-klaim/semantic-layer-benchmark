#!/usr/bin/env python3
"""Suite 3 augmentation — add a `returns` table to D1, keyed by the COMPOUND key
(order_id, line_number) referencing order_items. The FK is undeclared in the DDL.

Trap: a return belongs to one order LINE. Joining returns to order_items (or orders) on
order_id ALONE — forgetting line_number — multiplies each refund by the number of lines in
the order (partial-key fan-out). The certified model joins on the FULL compound key.
"""
import os, numpy as np, pandas as pd, duckdb
SEED = 43
rng = np.random.default_rng(SEED)
HERE = os.path.dirname(__file__)
dbp = os.path.join(HERE, "..", "warehouse", "d1.duckdb")
con = duckdb.connect(dbp)   # read-write; run only after D1 jobs release the DB

# candidate lines: those in delivered orders (status 4) — realistic return population
lines = con.execute("""
  SELECT oi.order_id, oi.line_number, oi.quantity, oi.unit_price, oi.discount_rate
  FROM order_items oi JOIN orders o USING(order_id)
  WHERE o.status = 4
""").df()
# ~14% of delivered lines get a (partial) return
mask = rng.random(len(lines)) < 0.14
r = lines[mask].copy().reset_index(drop=True)
r["return_qty"] = np.maximum(1, np.floor(r["quantity"] * rng.uniform(0.2, 1.0, len(r)))).astype(int)
r["refund_amount"] = np.round(r["return_qty"] * r["unit_price"] * (1 - r["discount_rate"]), 2)
r["return_reason"] = rng.choice(["damaged", "wrong_item", "no_longer_needed", "late"], len(r))
returns = r[["order_id", "line_number", "return_qty", "refund_amount", "return_reason"]]

con.execute("DROP TABLE IF EXISTS returns")
con.register("t", returns)
con.execute("CREATE TABLE returns AS SELECT * FROM t")
con.unregister("t")
returns.to_parquet(os.path.join(HERE, "..", "warehouse", "d1", "returns.parquet"), index=False)

# ground-truth sanity (correct = full compound key)
tot = con.execute("SELECT SUM(refund_amount) FROM returns").fetchone()[0]
n = con.execute("SELECT COUNT(*) FROM returns").fetchone()[0]
correct_by_cat = con.execute("""
  SELECT p.category, ROUND(SUM(rt.refund_amount),2) refunds
  FROM returns rt
  JOIN order_items oi ON rt.order_id=oi.order_id AND rt.line_number=oi.line_number
  JOIN products p ON oi.product_key=p.product_key
  GROUP BY 1 ORDER BY 2 DESC LIMIT 3
""").fetchall()
# what the PARTIAL-key (order_id only) join would wrongly produce, in total
wrong_tot = con.execute("""
  SELECT SUM(rt.refund_amount)
  FROM returns rt JOIN order_items oi ON rt.order_id=oi.order_id
""").fetchone()[0]
con.close()

# append returns to the DDL shown to U/D/G (FK intentionally NOT declared)
ddl_add = ("\n\nCREATE TABLE returns (\n  order_id BIGINT,\n  line_number BIGINT,\n"
           "  return_qty BIGINT,\n  refund_amount DOUBLE,\n  return_reason VARCHAR\n);\n")
ddlp = os.path.join(HERE, "..", "schemas", "d1_ddl.sql")
cur = open(ddlp).read()
if "CREATE TABLE returns" not in cur:
    open(ddlp, "a").write(ddl_add)

print(f"returns rows: {n}   total refunds (correct): {tot:.2f}")
print(f"PARTIAL-key (order_id only) total would be: {wrong_tot:.2f}  "
      f"(inflation {wrong_tot/tot:.2f}x)")
print("refunds by category (correct, top3):", correct_by_cat)
