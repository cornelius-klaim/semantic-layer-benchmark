---
type: metric
title: shipping_fee_total
resource: d1.metric.shipping_fee_total
tags: [certified]
---
# Metric: shipping_fee_total

Total shipping fees. Lives at ORDER grain — summing it across order lines double-counts (fan-out). Breakable down only by order-level dimensions, never by product.

**Definition.** `SUM(orders.shipping_fee)`

**Certified filter (always apply).** `orders.status IN (3,4)`

**Grain.** This measure is additive at the `orders` grain. Breaking it down by a dimension finer than that grain double-counts.

**Also called:** shipping fees, freight, shipping revenue.
