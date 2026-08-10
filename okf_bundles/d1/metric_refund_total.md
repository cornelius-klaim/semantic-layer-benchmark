---
type: metric
title: refund_total
resource: d1.metric.refund_total
tags: [certified]
---
# Metric: refund_total

Total refunds. Lives at order-LINE grain, keyed by (order_id, line_number). Joining to lines on order_id alone fans out each refund across the order's lines.

**Definition.** `SUM(returns.refund_amount)`

**Grain.** This measure is additive at the `returns` grain. Breaking it down by a dimension finer than that grain double-counts.

**Also called:** refunds, total refunded, returns value.
