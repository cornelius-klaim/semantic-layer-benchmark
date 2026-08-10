---
type: metric
title: rep_count
resource: d2.metric.rep_count
tags: [certified]
---
# Metric: rep_count

Number of distinct reps.

**Definition.** `COUNT(DISTINCT opportunities.employee_id)`

**Grain.** This measure is additive at the `opportunities` grain. Breaking it down by a dimension finer than that grain double-counts.

**Also called:** number of reps, headcount.
