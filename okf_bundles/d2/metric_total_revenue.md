---
type: metric
title: total_revenue
resource: d2.metric.total_revenue
tags: [certified]
---
# Metric: total_revenue

Total closed revenue across reps.

**Definition.** `SUM(opportunities.closed_revenue)`

**Grain.** This measure is additive at the `opportunities` grain. Breaking it down by a dimension finer than that grain double-counts.

**Also called:** revenue, closed revenue, sales.
