# products — ONE row per product. Parent of order_items (many_to_one). Supplies unit_cost
# for gross_margin and category for product-grain breakdowns.
view: products {
  sql_table_name: @{SCHEMA}.products ;;

  dimension: product_key {
    primary_key: yes
    type: number
    sql: ${TABLE}.product_key ;;
  }
  dimension: product_name {
    type: string
    sql: ${TABLE}.product_name ;;
  }
  dimension: category {
    type: string
    sql: ${TABLE}.category ;;
    description: "Product category."
  }
  dimension: unit_cost {
    type: number
    sql: ${TABLE}.unit_cost ;;
  }
  dimension: list_price {
    type: number
    sql: ${TABLE}.list_price ;;
  }
}
