# Inferential statistics

## Accuracy with 95% cluster-bootstrap CIs (resampling questions, B=2000)

| condition | accuracy | 95% CI |
|---|---|---|
| U ungrounded | 17.9% | [7.7, 28.9] |
| D doc-grounded (OKF) | 81.7% | [75.4, 88.0] |
| G prompt-grounded model | 84.5% | [77.9, 90.5] |
| S semantic layer | 90.2% | [83.9, 95.6] |

## McNemar exact paired tests (adjacent rungs)

| comparison | discordant (lo→hi wins) | discordant (hi→lo wins) | n pairs | p-value |
|---|---|---|---|---|
| U → D | 651 | 2 | 1017 | 1.14e-191 |
| D → G | 39 | 11 | 1017 | 9.02e-05 |
| G → S | 116 | 58 | 1017 | 1.31e-05 |
| U → S | 748 | 13 | 1017 | 6.98e-202 |

## Representation vs enforcement decomposition

- Adding grounding **content** (U→G, representation axis): **+66.6 pts** (U=17.9% → G=84.5%).
- Adding deterministic **enforcement** at equal content (G→S): **+5.7 pts** (G=84.5% → S=90.2%).
- Document vs structured representation of the SAME facts (D→G): **+2.8 pts**.
