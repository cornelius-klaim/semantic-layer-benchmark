---
type: metric
title: net_revenue
resource: d1.metric.net_revenue
tags: [certified]
---
# Metric: net_revenue

Certified net revenue: quantity x unit_price x (1 - discount), for shipped or delivered orders only. Excludes pending, paid-not-shipped, cancelled, and returned. Certified by Finance.

**Definition.** `SUM(order_items.quantity * order_items.unit_price * (1 - order_items.discount_rate))`

**Certified filter (always apply).** `orders.status IN (3,4)`

**Grain.** This measure is additive at the `order_items` grain. Breaking it down by a dimension finer than that grain double-counts.

**Also called:** revenue, net sales, sales.
