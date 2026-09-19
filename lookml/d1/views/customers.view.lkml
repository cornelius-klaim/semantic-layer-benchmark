# customers — ONE row per customer identity. full_name is a LABEL on the identity, not the
# identity itself (names are not unique: the seed plants 40 "John Smith" collisions).
view: customers {
  sql_table_name: @{SCHEMA}.customers ;;

  dimension: customer_id {
    primary_key: yes
    type: number
    sql: ${TABLE}.customer_id ;;
    description: "Customer identity key."
  }
  dimension: full_name {
    type: string
    sql: ${TABLE}.full_name ;;
    description: "Customer display name. A LABEL, not the identity. Not unique."
  }
  dimension: region {
    type: string
    sql: ${TABLE}.region ;;
  }
  dimension: acquisition_channel {
    type: string
    sql: ${TABLE}.acquisition_channel ;;
  }
  dimension: email {
    type: string
    sql: ${TABLE}.email ;;
  }
}
