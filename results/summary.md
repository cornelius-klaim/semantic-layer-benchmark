# Benchmark results — summary

> **Data version:** canonical run (v1, *pre-promotion*). The promotion (v2) and reaching-100 (v3) experiments are reported in `CHANGELOG_PER_LAYER.md` and the whitepaper. Suite-level S numbers below predate the 8 model/compiler edits that lift S to 100%.

Total scored runs: **2981** across 52 questions  
Conditions: U (ungrounded), D (doc-grounded/OKF), G (prompt-grounded model), S (semantic-layer)  
Datasets: d1, d2

## Coverage — runs per (model × condition), and suites reached
> COMPLETE = full multi-run coverage; **partial** tiers (fewer runs) did not reach every suite, so their high/near-100 scores reflect easier questions only — do not read them as perfect. `gemini-3.5-flash` and `gemini-2.5-pro` are partial single-run tiers.

| model | U | D | G | S | suites_reached | coverage |
|---|---|---|---|---|---|---|
| claude-haiku | 47 | 47 | 47 | 47 | 7 | COMPLETE |
| claude-opus | 47 | 47 | 47 | 47 | 7 | COMPLETE |
| claude-sonnet | 47 | 47 | 47 | 47 | 7 | COMPLETE |
| gemini-2.5-flash | 250 | 250 | 250 | 250 | 8 | COMPLETE |
| gemini-2.5-flash-lite | 250 | 250 | 250 | 250 | 8 | COMPLETE |
| gemini-2.5-pro | 51 | 51 | 51 | 51 | 2 | partial |
| gemini-3.5-flash | 55 | 55 | 53 | 50 | 1 | partial |

## U → D → G → S accuracy ladder (all pooled)

| U | D | G | S |
|---|---|---|---|
| 16.5% | 76.4% | 79.9% | 87.2% |

## Accuracy (%) by model × condition  _(n per cell in the coverage table above)_

| model | U | D | G | S |
|---|---|---|---|---|
| claude-haiku | 21.3 | 80.9 | 83 | 85.1 |
| claude-opus | 14.9 | 85.1 | 85.1 | 87.2 |
| claude-sonnet | 19.1 | 83 | 85.1 | 89.4 |
| gemini-2.5-flash | 16 | 78 | 80.8 | 84.4 |
| gemini-2.5-flash-lite | 16 | 61.6 | 69.6 | 84.8 |
| gemini-2.5-pro | 15.7 | 98 | 92.2 | 100 |
| gemini-3.5-flash | 16.4 | 100 | 100 | 100 |

## Accuracy (%) by suite × condition (models pooled)
> NOTE: for condition S, suites 2/3/5 include *un-modeled derived metrics* (shipping-%, avg-shipping, net-of-refunds, ratios, the advneg lift). Pre-promotion, S **legibly declines** these (returns modeled components / refuses) rather than hallucinating — scored as `declined_unmodeled`, not `correct`. The actual grain/fan-out and compound-key questions in those suites are answered correctly. See per-question CSV `scored.csv`.

| suite | U | D | G | S |
|---|---|---|---|---|
| 1 | 11.4 | 95.4 | 96.9 | 99.6 |
| 2 | 14.4 | 81.1 | 78.9 | 65.6 |
| 3 | 60 | 90.8 | 98.5 | 80 |
| 4 | 37.5 | 87.5 | 90.4 | 100 |
| 5 | 0 | 73.1 | 80.8 | 0 |
| 6 | 0 | 66.7 | 60 | 80 |
| 7 | 1.7 | 17.9 | 18.8 | 84.6 |
| 8 | 0 | 71.2 | 100 | 100 |

## Outcome-class breakdown for condition S (all models)

| class | count |
|---|---|
| correct | 574 |
| declined_unmodeled | 71 |
| refusal_correct | 65 |
| silent_guess | 18 |
| clarification | 8 |
| wrong | 6 |
