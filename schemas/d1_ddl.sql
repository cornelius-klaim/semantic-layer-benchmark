CREATE TABLE customers (
  customer_id BIGINT,
  region VARCHAR,
  acquisition_channel VARCHAR,
  full_name VARCHAR,
  email VARCHAR
);

CREATE TABLE products (
  product_key BIGINT,
  product_name VARCHAR,
  category VARCHAR,
  unit_cost DOUBLE,
  list_price DOUBLE
);

CREATE TABLE orders (
  order_id BIGINT,
  customer_key BIGINT,
  order_ts TIMESTAMP,
  status BIGINT,
  ship_region VARCHAR,
  shipping_fee DOUBLE,
  channel VARCHAR
);

CREATE TABLE order_items (
  order_id BIGINT,
  line_number BIGINT,
  product_key BIGINT,
  quantity BIGINT,
  unit_price DOUBLE,
  discount_rate DOUBLE,
  line_total DOUBLE
);

CREATE TABLE marketing_spend (
  spend_month TIMESTAMP,
  channel VARCHAR,
  spend DOUBLE
);


CREATE TABLE returns (
  order_id BIGINT,
  line_number BIGINT,
  return_qty BIGINT,
  refund_amount DOUBLE,
  return_reason VARCHAR
);
