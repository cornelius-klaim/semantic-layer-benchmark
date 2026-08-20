# Benchmark results — summary

> **Data version:** canonical run (v1, *pre-promotion*). The promotion (v2) and reaching-100 (v3) experiments are reported in `CHANGELOG_PER_LAYER.md` and the whitepaper. Suite-level S numbers below predate the 8 model/compiler edits that lift S to 100%.

Total scored runs: **4485** across 52 questions  
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
| gemini-3.1-pro | 141 | 141 | 141 | 141 | 7 | COMPLETE |
| gemini-3.5-flash | 55 | 55 | 53 | 50 | 1 | partial |
| gemini-3.7-flash | 235 | 235 | 235 | 235 | 7 | COMPLETE |

## U → D → G → S accuracy ladder (all pooled)

| U | D | G | S |
|---|---|---|---|
| 17.7% | 83.3% | 85.5% | 91.1% |

## Accuracy (%) by model × condition  _(n per cell in the coverage table above)_

| model | U | D | G | S |
|---|---|---|---|---|
| claude-haiku | 21.3 | 80.9 | 83 | 85.1 |
| claude-opus | 14.9 | 85.1 | 85.1 | 87.2 |
| claude-sonnet | 19.1 | 83 | 85.1 | 89.4 |
| gemini-2.5-flash | 16 | 78 | 80.8 | 84.4 |
| gemini-2.5-flash-lite | 16 | 61.6 | 69.6 | 84.8 |
| gemini-2.5-pro | 15.7 | 98 | 92.2 | 100 |
| gemini-3.1-pro | 19.1 | 92.2 | 91.5 | 100 |
| gemini-3.5-flash | 16.4 | 100 | 100 | 100 |
| gemini-3.7-flash | 20.9 | 100 | 100 | 97.9 |

## Accuracy (%) by suite × condition (models pooled)
> NOTE: for condition S, suites 2/3/5 include *un-modeled derived metrics* (shipping-%, avg-shipping, net-of-refunds, ratios, the advneg lift). Pre-promotion, S **legibly declines** these (returns modeled components / refuses) rather than hallucinating — scored as `declined_unmodeled`, not `correct`. The actual grain/fan-out and compound-key questions in those suites are answered correctly. See per-question CSV `scored.csv`.

| suite | U | D | G | S |
|---|---|---|---|---|
| 1 | 13.6 | 96.7 | 97.8 | 99.7 |
| 2 | 15.2 | 87.7 | 86.2 | 77.5 |
| 3 | 60 | 94.3 | 99 | 87.6 |
| 4 | 37.5 | 87.5 | 88.7 | 97 |
| 5 | 0 | 76.2 | 81 | 38.1 |
| 6 | 0 | 66.7 | 60 | 80 |
| 7 | 1.1 | 49.2 | 49.7 | 90.5 |
| 8 | 0 | 82.1 | 100 | 100 |

## Outcome-class breakdown for condition S (all models)

| class | count |
|---|---|
| correct | 889 |
| refusal_correct | 105 |
| declined_unmodeled | 71 |
| clarification | 24 |
| silent_guess | 18 |
| wrong | 11 |
