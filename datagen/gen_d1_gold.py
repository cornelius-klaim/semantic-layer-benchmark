#!/usr/bin/env python3
"""Test A — the Drill-Down Trap. Build conventional *pre-aggregated gold tables* from the D1 base
data: business-ready summaries whose detail below their grain has been summed away. Condition P is
given ONLY these tables. Questions that need sub-grain detail (a specific customer, a channel, a
region×category cross) cannot be answered from them — so we can measure whether the model *declines*
or *confidently hallucinates* a number from the aggregate it does have.

These tables are added to the existing d1.duckdb, exported to warehouse/d1/*.parquet (the portable
copy every other table in this repo also gets, and the form the BigQuery port loads from), and
their DDL written to schemas/d1_gold_ddl.sql.
"""
import os, duckdb
HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "warehouse", "d1")
os.makedirs(OUT, exist_ok=True)
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

# Parquet export — same convention as gen_d1.py / gen_d2.py (one <table>.parquet per table under
# warehouse/d1/). Without this the two gold tables lived only inside d1.duckdb and would be the
# only tables in the repo missing from a parquet-driven load (e.g. the BigQuery port).
# ORDER BY ALL is not cosmetic: these tables come from a parallel hash aggregate, so their row
# order differs on every rebuild. Sorting here makes the exported file byte-identical run to run,
# which keeps a git-tracked artifact from churning on every `python datagen/gen_d1_gold.py`.
# (The DuckDB tables themselves still permute on rebuild — pre-existing, see the CREATE statements.)
# Export via DuckDB's native COPY, NOT pandas .df(): SUM(quantity) is HUGEINT, and pandas
# round-trips it as float64, which lands in BigQuery as FLOAT64 while schemas/d1_gold_ddl.sql
# declares `units BIGINT`. Casting to BIGINT here makes DuckDB, the parquet, the DDL and the
# warehouse all agree. COPY also preserves the declared types for every other column.
CASTS = {"gold_sales_by_category": "* REPLACE (units::BIGINT AS units)",
         "gold_revenue_by_region_month": "*"}
for name in ("gold_revenue_by_region_month", "gold_sales_by_category"):
    tgt = os.path.join(OUT, f"{name}.parquet").replace("'", "''")
    con.execute(f"COPY (SELECT {CASTS[name]} FROM {name} ORDER BY ALL) "
                f"TO '{tgt}' (FORMAT PARQUET)")

con.close()

# DDL shown to condition P — ONLY the gold tables, nothing below their grain.
ddl = """-- Pre-aggregated GOLD tables (business-ready summaries). Detail below these grains has been
-- aggregated away and is not available.

CREATE TABLE gold_revenue_by_region_month (
  ship_region VARCHAR,     -- shipping region
  order_month TIMESTAMP,   -- first day of the calendar month, at midnight (physical type is
                           -- TIMESTAMP in DuckDB, the parquet export and BigQuery alike)
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
print(f"  duckdb:  {dbp}")
print(f"  parquet: {os.path.join(OUT, 'gold_revenue_by_region_month.parquet')}")
print(f"           {os.path.join(OUT, 'gold_sales_by_category.parquet')}")
print("DDL -> schemas/d1_gold_ddl.sql")
