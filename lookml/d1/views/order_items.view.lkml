# order_items — ONE row per order LINE, keyed by (order_id, line_number). The certified
# revenue surface: net/gross revenue, margin, and the cross-grain ratios live here. The
# shipped/delivered filter is enforced on every measure via orders.status_code.
view: order_items {
  sql_table_name: @{SCHEMA}.order_items ;;

  # composite grain -> a single primary_key so symmetric aggregates de-duplicate correctly
  dimension: pk {
    primary_key: yes
    type: string
    sql: ${TABLE}.order_id || '-' || ${TABLE}.line_number ;;
  }
  dimension: order_id {
    type: number
    sql: ${TABLE}.order_id ;;
  }
  dimension: line_number {
    type: number
    sql: ${TABLE}.line_number ;;
  }
  dimension: product_key {
    type: number
    sql: ${TABLE}.product_key ;;
  }
  dimension: quantity {
    type: number
    sql: ${TABLE}.quantity ;;
  }
  dimension: unit_price {
    type: number
    sql: ${TABLE}.unit_price ;;
  }
  dimension: discount_rate {
    type: number
    sql: ${TABLE}.discount_rate ;;
  }

  # ---- certified line-grain measures (shipped/delivered only) ----
  measure: net_revenue {
    type: sum
    sql: ${quantity} * ${unit_price} * (1 - ${discount_rate}) ;;
    filters: [orders.status_code: "3,4"]
    value_format_name: usd
    description: "Certified net revenue: qty x unit_price x (1 - discount), shipped/delivered only."
  }
  measure: gross_revenue {
    type: sum
    sql: ${quantity} * ${unit_price} ;;
    filters: [orders.status_code: "3,4"]
    value_format_name: usd
    description: "Revenue before line discounts, shipped/delivered. NOT the line_total column."
  }
  measure: gross_margin {
    type: sum
    sql: ${quantity} * ${unit_price} * (1 - ${discount_rate}) - ${quantity} * ${products.unit_cost} ;;
    filters: [orders.status_code: "3,4"]
    value_format_name: usd
    description: "Net revenue minus product cost, at line grain, shipped/delivered only."
  }
  measure: line_count {
    type: count
    filters: [orders.status_code: "3,4"]
    description: "Count of order lines (items), shipped/delivered only."
  }

  # ---- certified cross-grain ratios / expressions (measures of measures) ----
  measure: aov {
    type: number
    sql: 1.0 * ${net_revenue} / NULLIF(${orders.order_count}, 0) ;;
    value_format_name: usd
    description: "Average Order Value = net_revenue / order_count. Ratio of two measures at different grains."
  }
  measure: shipping_pct_of_revenue {
    type: number
    sql: 100.0 * ${orders.shipping_fee_total} / NULLIF(${net_revenue}, 0) ;;
    value_format: "0.0000"
    description: "Order-grain shipping fees as a percentage of line-grain net revenue."
  }
  measure: net_revenue_after_refunds {
    type: number
    sql: ${net_revenue} - ${returns.refund_total} ;;
    value_format_name: usd
    description: "Net revenue minus the dollar value of refunds issued."
  }
}
