---
type: metric
title: avg_quota_attainment
resource: d2.metric.avg_quota_attainment
tags: [certified]
---
# Metric: avg_quota_attainment

Average quota attainment across reps (1.0 = met quota). Certified from CRM.

**Definition.** `AVG(opportunities.quota_attainment)`

**Grain.** This measure is additive at the `opportunities` grain. Breaking it down by a dimension finer than that grain double-counts.

**Also called:** attainment, average attainment, quota attainment.
