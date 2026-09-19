# d1 — "NorthStar Commerce": the LookML realization of the benchmark's certified model.
#
# Connection: set to a BigQuery connection whose default dataset holds the seeded d1 tables
# (loaded by validate/load_d1_to_bigquery.py into dataset @{SCHEMA}). Update the name below to
# match the target instance's connection before deploying.
connection: "bigquery"

include: "/views/*.view.lkml"

# The certified revenue surface. Base = order_items (line grain). Parent tables join
# many_to_one; order-grain measures (order_count, shipping_fee_total, ...) stay fan-out-safe
# through the declared primary keys + Looker symmetric aggregates. returns joins on the FULL
# compound key so refunds are not fanned out across lines.
explore: order_items {
  label: "NorthStar Commerce (certified)"

  join: orders {
    type: left_outer
    relationship: many_to_one
    sql_on: ${order_items.order_id} = ${orders.order_id} ;;
  }
  join: products {
    type: left_outer
    relationship: many_to_one
    sql_on: ${order_items.product_key} = ${products.product_key} ;;
  }
  join: customers {
    type: left_outer
    relationship: many_to_one
    sql_on: ${orders.customer_key} = ${customers.customer_id} ;;
  }
  join: returns {
    type: left_outer
    relationship: one_to_one
    sql_on: ${order_items.order_id} = ${returns.order_id}
        AND ${order_items.line_number} = ${returns.line_number} ;;
  }
}

# marketing_spend shares no key with the sales grain — exposed on its own.
explore: marketing_spend {
  label: "Marketing spend (separate fact)"
}
