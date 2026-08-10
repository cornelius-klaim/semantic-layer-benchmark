-- Pre-aggregated GOLD tables (business-ready summaries). Detail below these grains has been
-- aggregated away and is not available.

CREATE TABLE gold_revenue_by_region_month (
  ship_region VARCHAR,     -- shipping region
  order_month DATE,        -- first day of the calendar month
  net_revenue DOUBLE,      -- net revenue (shipped/delivered), summed to region x month
  order_count BIGINT       -- distinct fulfilled orders in that region x month
);

CREATE TABLE gold_sales_by_category (
  product_category VARCHAR,-- product category
  net_revenue DOUBLE,      -- net revenue (shipped/delivered), summed to category
  units BIGINT             -- units sold in that category
);
