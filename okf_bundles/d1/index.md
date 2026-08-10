---
type: dataset
title: NorthStar Commerce
resource: d1
tags: [retail, sales]
---
# NorthStar Commerce
Line-item retail sales joined to orders, customers, and products. The certified revenue surface. Shipping fees live at ORDER grain; discounts at LINE grain.

## Grain
order_items is one row per order LINE, keyed by (order_id, line_number). orders is one row per order. Summing an order-grain measure (shipping_fee) across joined lines fans out.

## Concept documents
- Tables: [customers](./table_customers.md), [marketing_spend](./table_marketing_spend.md), [order_items](./table_order_items.md), [orders](./table_orders.md), [products](./table_products.md), [returns](./table_returns.md)
- Metrics: [net_revenue](./metric_net_revenue.md), [gross_revenue](./metric_gross_revenue.md), [order_count](./metric_order_count.md), [line_count](./metric_line_count.md), [aov](./metric_aov.md), [gross_margin](./metric_gross_margin.md), [active_customers](./metric_active_customers.md), [shipping_fee_total](./metric_shipping_fee_total.md), [marketing_spend_total](./metric_marketing_spend_total.md), [refund_total](./metric_refund_total.md), [refund_qty](./metric_refund_qty.md)

## Joins
- `order_items` relates to `orders` as **many-to-one**, joined on `order_items.order_id = orders.order_id`. Because it is many-to-one, aggregating a `orders`-grain measure across joined `order_items` rows will double-count (fan-out).
- `order_items` relates to `products` as **many-to-one**, joined on `order_items.product_key = products.product_key`. Because it is many-to-one, aggregating a `products`-grain measure across joined `order_items` rows will double-count (fan-out).
- `orders` relates to `customers` as **many-to-one**, joined on `orders.customer_key = customers.customer_id`. Because it is many-to-one, aggregating a `customers`-grain measure across joined `orders` rows will double-count (fan-out).
- `returns` relates to `order_items` as **many-to-one**, joined on `returns.order_id = order_items.order_id AND returns.line_number = order_items.line_number`. Because it is many-to-one, aggregating a `order_items`-grain measure across joined `returns` rows will double-count (fan-out).

## Vocabulary
### channel
Marketing channel. Stored inconsistently across tables.

- The business term **Paid Search** is stored as `paid_search`, `Paid-Search`, `PPC` across different tables.
- The business term **Organic** is stored as `organic`, `Organic` across different tables.
- The business term **Referral** is stored as `referral`, `Referral` across different tables.
- The business term **Social** is stored as `social`, `Social` across different tables.
- The business term **Email** is stored as `email`, `Email` across different tables.
