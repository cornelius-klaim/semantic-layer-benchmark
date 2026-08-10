---
type: metric
title: active_customers
resource: d1.metric.active_customers
tags: [certified]
---
# Metric: active_customers

Distinct customers with at least one shipped/delivered order. Counts customer IDENTITY (customer_key), not name.

**Definition.** `COUNT(DISTINCT orders.customer_key)`

**Certified filter (always apply).** `orders.status IN (3,4)`

**Grain.** This measure is additive at the `orders` grain. Breaking it down by a dimension finer than that grain double-counts.

**Also called:** active customers, number of customers, distinct customers.
