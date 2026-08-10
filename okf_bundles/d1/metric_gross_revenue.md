---
type: metric
title: gross_revenue
resource: d1.metric.gross_revenue
tags: [certified]
---
# Metric: gross_revenue

Revenue before line discounts, shipped/delivered only. Do NOT use the order_items.line_total column (it is pre-discount and unfiltered).

**Definition.** `SUM(order_items.quantity * order_items.unit_price)`

**Certified filter (always apply).** `orders.status IN (3,4)`

**Grain.** This measure is additive at the `order_items` grain. Breaking it down by a dimension finer than that grain double-counts.
