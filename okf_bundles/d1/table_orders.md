---
type: table
title: orders
resource: d1.orders
tags: [schema]
---
# Table: `orders`

| field | type | meaning |
|---|---|---|
| `ship_region` | string | Region the order shipped to. (expression: `orders.ship_region`) |
| `order_status` | string | Human-readable order status decoded from the raw integer code. (expression: `CASE orders.status WHEN 1 THEN 'pending' WHEN 2 THEN 'paid' WHEN 3 THEN 'shipped' WHEN 4 THEN 'delivered' WHEN 5 THEN 'cancelled' WHEN 6 THEN 'returned' END`) |
| `order_month` | date |  (expression: `date_trunc('month', orders.order_ts)`) |
| `order_year` | date |  (expression: `date_trunc('year', orders.order_ts)`) |
| `fiscal_year` | date | Fiscal year (fiscal year starts Feb 1; shift +11 months). (expression: `date_trunc('year', orders.order_ts + INTERVAL 11 MONTH)`) |
| `order_channel` | string | Marketing channel on the order (messy stored values). (expression: `orders.channel`) |
| `customer_id` | id | Customer identity key. THE identifier for a customer. This is the IDENTITY of the customer; group and count by this, not by any name. (expression: `orders.customer_key`) |
