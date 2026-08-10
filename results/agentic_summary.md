# Test B — Agentic multi-query self-join (MQ) vs. pre-joined semantic layer (S)

D2 cross-domain questions (5 shapes) that require joining separate source systems. MQ may issue only single-table queries and must stitch results itself; S issues one deterministic pre-joined query. MQ runs scored: 41.

| metric | MQ (agentic self-join) | S (semantic layer) |
|---|---|---|
| accuracy | 7% | 80% |
| queries per question | 4.3 | 1 (by construction) |
| tokens per question | 13,255 | 460 |
| latency per question | 26.5s | 1.00s |
| answers correct by construction | no | **yes** |

## Headline
- The agentic self-join issues **4.3 queries per question** (vs 1), spends **~29× the tokens** and **~27× the latency**, and is **7% accurate** where the pre-joined layer is 80% — because stitching sources by hand (ferrying keys between capped result sets, aggregating before vs. after the join, normalizing the email bridge) is exactly where it slips.
- On determinism, the honest finding: at temperature 0 the self-join was **consistently wrong, not flaky** (0/14 cells varied across runs). The layer's advantage is not 'less random' — it is *correct by construction*: one compiled query, the right answer every time, at a fraction of the cost.

## Per-model MQ accuracy (capability does not fix orchestration)
| model | n | accuracy |
|---|---|---|
| gemini-2.5-flash | 15 | 20% |
| gemini-2.5-flash-lite | 15 | 0% |
| gemini-2.5-pro | 11 | 0% |

## Caveats
- **Shared-model comparison.** MQ ran on the three Gemini tiers; the S arm above is restricted to those same Gemini models so the two arms compare like with like and tokens are single-sourced. Robustness: S is 80% on the Gemini subset, 80% on the Claude subset, and 80% pooled — identical, so the choice does not affect the result.
- **Partial pro arm.** gemini-2.5-pro completed 11 of 15 MQ runs (the ~26s orchestration loop timed out on one question); its completed runs scored 0%, consistent with the other tiers.
- The single-query interface caps returned rows at 60, as a real tool interface would; part of the self-join's failure is that it cannot ferry hundreds of join keys through that cap. Without a cap it would instead pass hundreds of literals between queries — trading the accuracy failure for an even larger token bill. Either way the pre-joined single query dominates.
- S here is scored on the canonical (pre-promotion) model, where the tenure-lift metric is a legible decline; once that measure is promoted (a one-time edit) S reaches 100% on these five. MQ has no comparable one-time fix — every query re-derives the join.
