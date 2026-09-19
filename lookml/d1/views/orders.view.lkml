# orders — ONE row per order (order grain). Shipping fees live here; summing them across the
# joined order LINES would fan out, so order_id is declared primary_key and every order-grain
# measure below is computed with Looker symmetric aggregates.
view: orders {
  sql_table_name: @{SCHEMA}.orders ;;

  dimension: order_id {
    primary_key: yes
    type: number
    sql: ${TABLE}.order_id ;;
  }
  dimension: customer_key {
    type: number
    sql: ${TABLE}.customer_key ;;
    description: "Customer identity key. THE identifier for a customer."
  }
  dimension: status_code {
    type: number
    sql: ${TABLE}.status ;;
    description: "Raw status code. 3=shipped, 4=delivered are the certified 'fulfilled' set."
  }
  dimension: order_status {
    type: string
    sql: CASE ${TABLE}.status WHEN 1 THEN 'pending' WHEN 2 THEN 'paid' WHEN 3 THEN 'shipped'
              WHEN 4 THEN 'delivered' WHEN 5 THEN 'cancelled' WHEN 6 THEN 'returned' END ;;
  }
  dimension: ship_region {
    type: string
    sql: ${TABLE}.ship_region ;;
  }
  dimension: channel {
    type: string
    sql: ${TABLE}.channel ;;
    description: "Marketing channel on the order (messy stored values)."
  }
  dimension: shipping_fee {
    type: number
    sql: ${TABLE}.shipping_fee ;;
  }
  dimension_group: order {
    type: time
    timeframes: [date, month, year, fiscal_year]
    sql: ${TABLE}.order_ts ;;
  }

  # ---- certified order-grain measures (fulfilled = shipped/delivered) ----
  measure: order_count {
    type: count_distinct
    sql: ${order_id} ;;
    filters: [status_code: "3,4"]
    description: "Count of distinct shipped/delivered orders."
  }
  measure: active_customers {
    type: count_distinct
    sql: ${customer_key} ;;
    filters: [status_code: "3,4"]
    description: "Distinct customers with >=1 shipped/delivered order. Counts identity, not name."
  }
  measure: shipping_fee_total {
    type: sum
    sql: ${shipping_fee} ;;
    filters: [status_code: "3,4"]
    value_format_name: usd
    description: "Total shipping fees at ORDER grain. Symmetric aggregate keeps it fan-out-safe."
  }
  measure: avg_shipping_fee {
    type: average
    sql: ${shipping_fee} ;;
    filters: [status_code: "3,4"]
    value_format_name: usd
    description: "Average shipping fee per fulfilled order."
  }
}
