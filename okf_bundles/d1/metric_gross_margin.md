---
type: metric
title: gross_margin
resource: d1.metric.gross_margin
tags: [certified]
---
# Metric: gross_margin

Net revenue minus product cost, at line grain, shipped/delivered only.

**Definition.** `SUM(order_items.quantity * order_items.unit_price * (1 - order_items.discount_rate) - order_items.quantity * products.unit_cost)`

**Certified filter (always apply).** `orders.status IN (3,4)`

**Grain.** This measure is additive at the `order_items` grain. Breaking it down by a dimension finer than that grain double-counts.

**Also called:** margin, profit.
