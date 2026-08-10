---
type: metric
title: order_count
resource: d1.metric.order_count
tags: [certified]
---
# Metric: order_count

Count of distinct shipped/delivered orders.

**Definition.** `COUNT(DISTINCT orders.order_id)`

**Certified filter (always apply).** `orders.status IN (3,4)`

**Grain.** This measure is additive at the `orders` grain. Breaking it down by a dimension finer than that grain double-counts.

**Also called:** number of orders, orders.
