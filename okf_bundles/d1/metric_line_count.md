---
type: metric
title: line_count
resource: d1.metric.line_count
tags: [certified]
---
# Metric: line_count

Count of order lines (items), shipped/delivered only.

**Definition.** `COUNT(*)`

**Certified filter (always apply).** `orders.status IN (3,4)`

**Grain.** This measure is additive at the `order_items` grain. Breaking it down by a dimension finer than that grain double-counts.
