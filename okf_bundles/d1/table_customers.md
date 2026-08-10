---
type: table
title: customers
resource: d1.customers
tags: [schema]
---
# Table: `customers`

| field | type | meaning |
|---|---|---|
| `customer_name` | string | Customer display name. A LABEL on the customer identity, not the identity. Names are not unique. This is a display LABEL for the customer and is NOT unique — never aggregate by it. (expression: `customers.full_name`) |
