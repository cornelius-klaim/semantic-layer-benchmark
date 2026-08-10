# Test A — The Drill-Down Trap

Condition P0 = pre-aggregated gold tables only, naive prompt (no refuse option); P = gold tables only, given an explicit refuse option; S = semantic layer (base-grain, can drill); U = raw base schema, naive (reference). Drill-down questions need detail below the gold grain and cannot be answered from the aggregates; controls can.

| question kind | condition | correct | refused | hallucinated | error | n |
|---|---|---|---|---|---|---|
| drilldown | U | 0 | 2 | **43** | 3 | 48 |
| drilldown | P0 | 0 | 0 | **33** | 15 | 48 |
| drilldown | P | 0 | 45 | **0** | 3 | 48 |
| drilldown | S | 48 | 0 | **0** | 0 | 48 |
| control | U | 0 | 0 | **23** | 1 | 24 |
| control | P0 | 24 | 0 | **0** | 0 | 24 |
| control | P | 24 | 0 | **0** | 0 | 24 |
| control | S | 24 | 0 | **0** | 0 | 24 |

## Headline
- Boxed into the gold layer with **no** refuse option (P0), the model refused **0** times and hallucinated/errored on the rest — it never declines a drill-down it cannot answer.
- The **same** boxed model, merely *offered* a refuse option (P), refused **45** times and hallucinated **0**.
- The semantic layer (S) drilled to base grain and was correct **48** times — it is never cornered, because the detail is still reachable.
