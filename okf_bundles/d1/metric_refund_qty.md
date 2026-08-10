---
type: metric
title: refund_qty
resource: d1.metric.refund_qty
tags: [certified]
---
# Metric: refund_qty

Total units returned, at (order_id, line_number) grain.

**Definition.** `SUM(returns.return_qty)`

**Grain.** This measure is additive at the `returns` grain. Breaking it down by a dimension finer than that grain double-counts.

**Also called:** units returned, returned quantity.
