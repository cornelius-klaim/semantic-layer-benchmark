# LookML realization of the certified model — reproduce it on a real semantic layer

The certified d1 model is implemented here in **LookML**, so the governed surface can be run on
a production semantic layer and shown to reproduce the compiler's certified values to the cent.
Two implementations that share only a model definition, agreeing exactly, is the evidence that
the result is a property of the **modeling discipline**, not of one engine.

## What's here

```
lookml/d1/
  manifest.lkml            connection_name / gcp_project / SCHEMA constants (set for your instance)
  d1.model.lkml            connection + the order_items explore (joins) + marketing_spend
  views/                   orders, order_items, products, customers, returns, marketing_spend
```

Every certified measure in `semantic_models/d1.yaml` is encoded as LookML. Fan-out safety —
which the compiler gets by aggregating each measure at its base grain and FULL OUTER JOINing on
shared dimensions — LookML gets from **declared primary keys + symmetric aggregates**:

```lookml
# a composite grain -> one primary_key so symmetric aggregates de-duplicate correctly
dimension: pk {
  primary_key: yes
  type: string
  sql: ${TABLE}.order_id || '-' || ${TABLE}.line_number ;;
}
```

```lookml
# returns joins on the FULL compound key — on order_id alone, refunds fan out 3.68x
join: returns {
  type: left_outer
  relationship: one_to_one
  sql_on: ${order_items.order_id}   = ${returns.order_id}
      AND ${order_items.line_number} = ${returns.line_number} ;;
}
```

```lookml
# cross-grain ratio: a measure of two measures at different base grains
measure: aov {
  type: number
  sql: 1.0 * ${net_revenue} / NULLIF(${orders.order_count}, 0) ;;
  value_format_name: usd
}
```

## Validate #1 — reproducible, no Looker account

Builds the exact denormalized join the `order_items` explore defines on the seeded warehouse and
computes every measure the fan-out-safe way the LookML model does, checking each against the
compiler's certified values.

```bash
make data                                     # seed the warehouse (deterministic)
python validate/certify_measures.py           # compiler -> results/certified_measures_d1.json
python validate/validate_lookml_duckdb.py     # -> 14/14 to the cent
```

Expected tail:

```
14/14 measures reproduce the certified value to the cent.
TRAP 1 (shipping fan-out): naive SUM over joined lines = 1,353,518.89 vs fan-out-safe 450,531.23  (inflation 3.00x)
TRAP 2 (returns partial key): join on order_id alone = 9,734,783.71 vs compound-key 2,647,155.56  (inflation 3.68x)
```

## Validate #2 — live Looker over BigQuery (the second engine)

Looker compiles the LookML to BigQuery SQL with its own symmetric aggregates. **Result: 14/14
certified measures to the cent** (`results/lookml_validation_looker.json`).

**Step 1 — load the seeded warehouse into BigQuery** (dataset name = the `SCHEMA` constant):

```bash
pip install google-cloud-bigquery
BQ_PROJECT=<your-project> BQ_DATASET=sgl_grounding_ladder_d1 \
  python validate/load_d1_to_bigquery.py
```

**Step 2 — create the Looker project.** Put the contents of `lookml/d1/` at the **root** of a
git repo (Looker reads the project root), then in Looker *Develop → Manage LookML Projects → New
Project → connect that repo*. Set the three constants in `manifest.lkml` for your instance:

```lookml
constant: connection_name { value: "your_bigquery_connection" export: override_optional }
constant: gcp_project     { value: "your-gcp-project"         export: override_optional }
constant: SCHEMA          { value: "sgl_grounding_ladder_d1"  export: override_optional }
```

Point a BigQuery connection at the project holding the dataset, and register a LookML model
named `d1` on that connection. (Programmatically, the same steps are `create_project`,
`update_project(git_remote_url=…)`, `create_git_deploy_key`, `create_lookml_model`.)

**Step 3 — validate:**

```bash
LOOKERSDK_CONFIG_FILE=looker.ini LOOKER_MODEL=d1 LOOKER_WORKSPACE=production \
  python validate/validate_lookml.py
```

Expected tail:

```
14/14 certified measures reproduced on live Looker to the cent.
refund_total over product-category breakdown (symmetric aggregate): 2,647,155.56 (certified 2,647,155.56)
```

---

`certified_measures_d1.json` is regenerated from the compiler by `validate/certify_measures.py`,
so both validations check against the same ground truth the benchmark uses everywhere else.
