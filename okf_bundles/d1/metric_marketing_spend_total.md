---
type: metric
title: marketing_spend_total
resource: d1.metric.marketing_spend_total
tags: [certified]
---
# Metric: marketing_spend_total

Total marketing spend by channel/month (separate fact; channel vocab is 'PPC' for paid search).

**Definition.** `SUM(marketing_spend.spend)`

**Grain.** This measure is additive at the `marketing_spend` grain. Breaking it down by a dimension finer than that grain double-counts.
