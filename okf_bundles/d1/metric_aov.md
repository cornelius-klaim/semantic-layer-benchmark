---
type: metric
title: aov
resource: d1.metric.aov
tags: [certified]
---
# Metric: aov

Average Order Value = net_revenue / order_count. A ratio of two certified measures at different grains — never AVG() over rows.

**Definition.** This is a ratio: `net_revenue` divided by `order_count`. The two components are at different grains, so it must be computed as a ratio of the two certified measures — never as an `AVG()` over rows.

**Also called:** average order value, avg order value.
