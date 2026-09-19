# LookML realization of the certified model — a second, independent implementation

The paper's condition **S** is a deliberately vendor-neutral **compiler** (see the whitepaper,
*"our condition S is vendor-neutral: a generic deterministic compiler … so the result is a
property of enforcement itself rather than of any product"*). This directory adds the **second
implementation** of the *same* d1 model in **LookML**, so the certified surface can be shown to
reproduce on a real production semantic layer — not only on the reference compiler.

Two implementations that share only a model definition, agreeing to the cent, is the evidence
that the result is a property of the **modeling discipline**, not of one engine.

## What's here

```
lookml/d1/
  manifest.lkml            @{SCHEMA} constant (target BigQuery dataset)
  d1.model.lkml            connection + the order_items explore (joins) + marketing_spend
  views/                   orders, order_items, products, customers, returns, marketing_spend
```

Every certified measure in `semantic_models/d1.yaml` is encoded as LookML. Fan-out safety —
which the compiler gets by aggregating each measure at its base grain and FULL OUTER JOINing on
shared dimensions — LookML gets from **declared primary keys + symmetric aggregates**:

- `orders.order_id`, `products.product_key`, `customers.customer_id` are `primary_key: yes`;
  `order_items` and `returns` declare a composite `pk` (`order_id || '-' || line_number`).
- Order-grain measures (`shipping_fee_total`, `avg_shipping_fee`, `order_count`,
  `active_customers`) therefore stay correct when queried beside line-grain revenue.
- `returns` joins on the **full compound key**, so refunds are not fanned out across an order's
  lines (joining on `order_id` alone inflates the total 3.66×).
- The certified shipped/delivered filter (`status IN (3,4)`) is applied on every measure via
  `filters: [orders.status_code: "3,4"]`.

## Validation — two engines

**1. Reproducible, no account required** — `validate/validate_lookml_duckdb.py`
Builds the exact denormalized join the `order_items` explore defines on the seeded warehouse and
computes every measure the fan-out-safe way the LookML model does, checking each against
`results/certified_measures_d1.json`. Result: **14/14 measures to the cent**, and it prints the
two traps (shipping fan-out 3.00×; returns partial-key 3.66×). Run:

```
make data
python validate/validate_lookml_duckdb.py
```

**2. Live Looker (second engine)** — `validate/validate_lookml.py`
Runs each measure through the LookML model on a real Looker instance (Looker compiles to
BigQuery SQL with its own symmetric aggregates) and checks the same certified values.
**Result: 14/14 certified measures reproduced to the cent on live Looker over BigQuery**
(`results/lookml_validation_looker.json`) — net_revenue $60,185,854.28, gross_margin
$27,199,313.82, order_count 35,996, fan-out-safe shipping_fee_total $450,531.23, compound-key
refund_total $2,647,155.56, and the rest — including the product-category refund breakdown,
which sums back to the certified total through Looker's symmetric aggregates.

One-time setup:

```
# 1. load the seeded warehouse into BigQuery (dataset = @{SCHEMA})
BQ_PROJECT=<proj> python validate/load_d1_to_bigquery.py

# 2. create a Looker project from lookml/d1 (its own repo, LookML at root), set the three
#    manifest constants (connection_name, gcp_project, SCHEMA) for your instance, and register
#    a LookML model named d1 whose connection points at that BigQuery project.

# 3. validate
LOOKERSDK_CONFIG_FILE=looker.ini LOOKER_WORKSPACE=production \
  python validate/validate_lookml.py     # -> 14/14 to the cent
```

`certified_measures_d1.json` is regenerated from the compiler by `validate/certify_measures.py`.

> Note: `datagen/gen_d1_returns.py` was fixed to sort its candidate lines before applying the
> seeded return mask — without a deterministic `ORDER BY`, the refund totals drifted run to run.
> The refund figures are now reproducible; the partial-key fan-out ratio (~3.68×) is unaffected.
