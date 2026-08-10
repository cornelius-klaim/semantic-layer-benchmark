# Inferential statistics

## Accuracy with 95% cluster-bootstrap CIs (resampling questions, B=2000)

| condition | accuracy | 95% CI |
|---|---|---|
| U ungrounded | 16.5% | [6.9, 27.1] |
| D doc-grounded (OKF) | 72.7% | [62.5, 82.0] |
| G prompt-grounded model | 77.2% | [66.7, 86.6] |
| S semantic layer | 85.2% | [75.6, 93.8] |

## McNemar exact paired tests (adjacent rungs)

| comparison | discordant (lo→hi wins) | discordant (hi→lo wins) | n pairs | p-value |
|---|---|---|---|---|
| U → D | 362 | 2 | 641 | 3.54e-105 |
| D → G | 37 | 8 | 641 | 1.54e-05 |
| G → S | 104 | 53 | 641 | 5.74e-05 |
| U → S | 453 | 13 | 641 | 7.16e-116 |

## Representation vs enforcement decomposition

- Adding grounding **content** (U→G, representation axis): **+60.7 pts** (U=16.5% → G=77.2%).
- Adding deterministic **enforcement** at equal content (G→S): **+8.0 pts** (G=77.2% → S=85.2%).
- Document vs structured representation of the SAME facts (D→G): **+4.5 pts**.
