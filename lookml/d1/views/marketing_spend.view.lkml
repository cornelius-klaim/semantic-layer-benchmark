# marketing_spend — a SEPARATE fact (spend by channel and month). No key shared with the
# sales grain, so it is exposed as its own explore rather than joined into order_items.
# Its channel vocabulary stores paid search as 'PPC'.
view: marketing_spend {
  sql_table_name: @{SCHEMA}.marketing_spend ;;

  dimension: pk {
    primary_key: yes
    type: string
    sql: ${TABLE}.channel || '-' || ${TABLE}.spend_month ;;
  }
  dimension: channel {
    type: string
    sql: ${TABLE}.channel ;;
  }
  dimension: spend_month {
    type: string
    sql: ${TABLE}.spend_month ;;
  }

  measure: marketing_spend_total {
    type: sum
    sql: ${TABLE}.spend ;;
    value_format_name: usd
    description: "Total marketing spend by channel/month."
  }
}
