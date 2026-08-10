#!/usr/bin/env python3
"""Test A — the Drill-Down Trap. Build conventional *pre-aggregated gold tables* from the D1 base
data: business-ready summaries whose detail below their grain has been summed away. Condition P is
given ONLY these tables. Questions that need sub-grain detail (a specific customer, a channel, a
region×category cross) cannot be answered from them — so we can measure whether the model *declines*
or *confidently hallucinates* a number from the aggregate it does have.

These tables are added to the existing d1.duckdb and their DDL written to schemas/d1_gold_ddl.sql.
"""
import os, duckdb
HERE = os.path.dirname(__file__)
dbp = os.path.join(HERE, "..", "warehouse", "d1.duckdb")
con = duckdb.connect(dbp)

NETREV = "oi.quantity*oi.unit_price*(1-oi.discount_rate)"
BASE = f"FROM order_items oi JOIN orders o USING(order_id) WHERE o.status IN (3,4)"

# Gold table 1: revenue & orders by region × calendar month. No customer, product, or channel.
con.execute("DROP TABLE IF EXISTS gold_revenue_by_region_month")
con.execute(f"""
CREATE TABLE gold_revenue_by_region_month AS
SELECT o.ship_region,
       date_trunc('month', o.order_ts) AS order_month,
       ROUND(SUM({NETREV}),2) AS net_revenue,
       COUNT(DISTINCT o.order_id) AS order_count
{BASE} GROUP BY 1,2
""")

# Gold table 2: revenue & units by product category. No region, time, customer, or channel.
con.execute("DROP TABLE IF EXISTS gold_sales_by_category")
con.execute(f"""
CREATE TABLE gold_sales_by_category AS
SELECT p.category AS product_category,
       ROUND(SUM({NETREV}),2) AS net_revenue,
       SUM(oi.quantity) AS units
FROM order_items oi JOIN orders o USING(order_id) JOIN products p USING(product_key)
WHERE o.status IN (3,4) GROUP BY 1
""")

rows_rm = con.execute("SELECT COUNT(*) FROM gold_revenue_by_region_month").fetchone()[0]
rows_cat = con.execute("SELECT COUNT(*) FROM gold_sales_by_category").fetchone()[0]
con.close()

# DDL shown to condition P — ONLY the gold tables, nothing below their grain.
ddl = """-- Pre-aggregated GOLD tables (business-ready summaries). Detail below these grains has been
-- aggregated away and is not available.

CREATE TABLE gold_revenue_by_region_month (
  ship_region VARCHAR,     -- shipping region
  order_month DATE,        -- first day of the calendar month
  net_revenue DOUBLE,      -- net revenue (shipped/delivered), summed to region x month
  order_count BIGINT       -- distinct fulfilled orders in that region x month
);

CREATE TABLE gold_sales_by_category (
  product_category VARCHAR,-- product category
  net_revenue DOUBLE,      -- net revenue (shipped/delivered), summed to category
  units BIGINT             -- units sold in that category
);
"""
open(os.path.join(HERE, "..", "schemas", "d1_gold_ddl.sql"), "w").write(ddl)
print(f"gold tables built: gold_revenue_by_region_month ({rows_rm} rows), gold_sales_by_category ({rows_cat} rows)")
print("DDL -> schemas/d1_gold_ddl.sql")
