#!/usr/bin/env python3
"""D1 — NorthStar Commerce: seeded synthetic retail dataset (ground truth by construction).

Generates a Northwind-class retail warehouse with deliberate traps that exercise every
failure mode the semantic-layer paper claims to prevent:
  - shipping_fee at ORDER grain (fan-out trap when summed at line grain)
  - status codes that certified metrics must filter (cancelled=5, returned=6)
  - a `line_total` column that is WRONG (pre-discount) — the "convenient column" trap
  - marketing channel vocabulary that is messy across tables (paid_search / Paid-Search / PPC)
  - duplicate customer NAMES with distinct customer_id (identity != label)
  - composite natural key on order lines (order_id, line_number)

Outputs parquet files + a DuckDB database at warehouse/d1.duckdb, plus schema DDL.
Everything is deterministic under SEED, so ground truth is computable by construction.
"""
import os, numpy as np, pandas as pd, duckdb

SEED = 42
rng = np.random.default_rng(SEED)
HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "warehouse", "d1")
os.makedirs(OUT, exist_ok=True)

N_CUST, N_PROD, N_ORDERS = 5000, 1000, 50000

# ---- customers (identity trap: reuse a few common names across distinct ids) ----
first = ["John","Mary","James","Patricia","Robert","Jennifer","Michael","Linda","David","Susan",
         "Aisha","Wei","Diego","Priya","Sven","Fatima","Hiro","Olga","Kwame","Lucia"]
last = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Chen","Kumar",
        "Okafor","Nguyen","Silva","Haddad","Larsson","Yilmaz","Rossi","Novak","Mbeki","Ivanova"]
regions = ["Northeast","Midwest","South","West","EMEA","APAC"]
# channel vocabulary is DELIBERATELY messy across the dataset
chan_cust = rng.choice(["paid_search","organic","referral","social","email"], N_CUST, p=[.3,.3,.15,.15,.1])
cust = pd.DataFrame({
    "customer_id": np.arange(1, N_CUST+1),
    "first_name": rng.choice(first, N_CUST),
    "last_name": rng.choice(last, N_CUST),
    "region": rng.choice(regions, N_CUST),
    "acquisition_channel": chan_cust,
})
# force ~40 exact-duplicate full names spread over distinct ids (the "John Smith" trap)
dup_ids = rng.choice(cust.customer_id.values, 40, replace=False)
cust.loc[cust.customer_id.isin(dup_ids), "first_name"] = "John"
cust.loc[cust.customer_id.isin(dup_ids), "last_name"] = "Smith"
cust["full_name"] = cust.first_name + " " + cust.last_name
cust["email"] = (cust.first_name.str.lower()+"."+cust.last_name.str.lower()+cust.customer_id.astype(str)+"@example.com")

# ---- products ----
cats = ["Beverages","Confections","Dairy","Produce","Seafood","Grains","Household","Electronics"]
prod = pd.DataFrame({
    "product_key": np.arange(1, N_PROD+1),
    "product_name": [f"Product {i}" for i in range(1, N_PROD+1)],
    "category": rng.choice(cats, N_PROD),
    "unit_cost": np.round(rng.uniform(1, 80, N_PROD), 2),
})
prod["list_price"] = np.round(prod.unit_cost * rng.uniform(1.3, 2.6, N_PROD), 2)

# ---- orders (order grain: shipping_fee, status, region, ts) ----
cust_key = rng.integers(1, N_CUST+1, N_ORDERS)
order_ts = pd.to_datetime("2023-01-01") + pd.to_timedelta(rng.integers(0, 730, N_ORDERS), unit="D")
# status distribution: 1 pending,2 paid,3 shipped,4 delivered,5 cancelled,6 returned
status = rng.choice([1,2,3,4,5,6], N_ORDERS, p=[.05,.08,.30,.42,.10,.05])
orders = pd.DataFrame({
    "order_id": np.arange(1, N_ORDERS+1),
    "customer_key": cust_key,
    "order_ts": order_ts,
    "status": status,
    "ship_region": cust.set_index("customer_id").loc[cust_key, "region"].values,
    "shipping_fee": np.round(rng.uniform(0, 25, N_ORDERS), 2),  # ORDER grain
    "channel": rng.choice(["Paid-Search","Organic","Referral","Social","Email"], N_ORDERS,
                          p=[.3,.3,.15,.15,.1]),  # messy variant of channel vocab
})

# ---- order_items (line grain; composite key (order_id, line_number)) ----
lines_per = rng.integers(1, 6, N_ORDERS)
oi_order = np.repeat(orders.order_id.values, lines_per)
oi_line = np.concatenate([np.arange(1, k+1) for k in lines_per])
M = len(oi_order)
oi_prod = rng.integers(1, N_PROD+1, M)
qty = rng.integers(1, 15, M)
unit_price = prod.set_index("product_key").loc[oi_prod, "list_price"].values
disc = np.round(rng.choice([0,0,0,.05,.1,.15,.2], M), 2)  # line grain
order_items = pd.DataFrame({
    "order_id": oi_order,
    "line_number": oi_line,
    "product_key": oi_prod,
    "quantity": qty,
    "unit_price": np.round(unit_price, 2),
    "discount_rate": disc,
    # TRAP: line_total is WRONG on purpose — pre-discount (ignores discount_rate)
    "line_total": np.round(qty * unit_price, 2),
})

# ---- marketing_spend (channel grain; messy vocab: PPC == paid search) ----
mk_rows = []
for month in pd.date_range("2023-01-01","2024-12-01",freq="MS"):
    for ch in ["PPC","organic","referral","social","email"]:  # PPC = paid search vocab variant
        mk_rows.append((month, ch, round(float(rng.uniform(2000, 20000)),2)))
marketing = pd.DataFrame(mk_rows, columns=["spend_month","channel","spend"])

# ---- write parquet + duckdb ----
tables = {"customers":cust.drop(columns=["first_name","last_name"]),
          "products":prod, "orders":orders, "order_items":order_items, "marketing_spend":marketing}
for name, df in tables.items():
    df.to_parquet(os.path.join(OUT, f"{name}.parquet"), index=False)

dbp = os.path.join(HERE, "..", "warehouse", "d1.duckdb")
if os.path.exists(dbp): os.remove(dbp)
con = duckdb.connect(dbp)
for name, df in tables.items():
    con.register("t_df", df); con.execute(f"CREATE TABLE {name} AS SELECT * FROM t_df"); con.unregister("t_df")
con.close()

# ---- emit DDL (for condition U) ----
ddl = []
types = {"int64":"BIGINT","float64":"DOUBLE","object":"VARCHAR","datetime64[ns]":"TIMESTAMP"}
for name, df in tables.items():
    cols = ",\n".join(f"  {c} {types.get(str(t),'VARCHAR')}" for c,t in df.dtypes.items())
    ddl.append(f"CREATE TABLE {name} (\n{cols}\n);")
os.makedirs(os.path.join(HERE,"..","schemas"), exist_ok=True)
open(os.path.join(HERE,"..","schemas","d1_ddl.sql"),"w").write("\n\n".join(ddl)+"\n")

print(f"D1 generated: customers={len(cust)}, products={len(prod)}, orders={len(orders)}, "
      f"order_items={len(order_items)}, marketing={len(marketing)}  (seed={SEED})")
print(f"  duplicate 'John Smith' customer_ids: {len(dup_ids)}")
print(f"  duckdb: {dbp}")
