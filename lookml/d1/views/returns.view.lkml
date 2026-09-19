# returns — refund events at order-LINE grain, keyed by (order_id, line_number). Joining to
# order_items on order_id ALONE would fan each refund out across every line in the order
# (the seed inflates the total 3.66x that way); the explore joins on the FULL compound key.
view: returns {
  sql_table_name: @{SCHEMA}.returns ;;

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
  dimension: return_reason {
    type: string
    sql: ${TABLE}.return_reason ;;
  }

  measure: refund_total {
    type: sum
    sql: ${TABLE}.refund_amount ;;
    value_format_name: usd
    description: "Total refunds at (order_id, line_number) grain."
  }
  measure: refund_qty {
    type: sum
    sql: ${TABLE}.return_qty ;;
    description: "Total units returned, at (order_id, line_number) grain."
  }
}
