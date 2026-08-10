---
type: table
title: hr_bridge
resource: d2.hr_bridge
tags: [schema]
---
# Table: `hr_bridge`

| field | type | meaning |
|---|---|---|
| `sales_region` | string | Sales region of the rep (from HR, the certified source of region). (expression: `hr_bridge.region`) |
| `tenure_years` | number | Rep tenure in years (a known confounder for attainment). (expression: `hr_bridge.tenure_years`) |
