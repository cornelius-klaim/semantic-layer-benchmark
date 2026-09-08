# Review: semantic-layer-benchmark

To: Cornelius
Re: independent review of the benchmark behind *The Semantic Gold Layer*
At: commit `12786a6`

Everything below was re-derived from the repo rather than read off the prose. Where I say a published number is wrong, I reproduced it exactly first, then got a different answer a second way. Longer working notes and the code are in the branch; this is the part worth your time.

## What holds up

The ladder is a real experimental design, not a demo. Emitting D's markdown and G's structured model from one source of truth is what turns "the D-vs-G difference is representation, not content" into a claim you can actually defend, and most benchmarks in this space compare a good prompt to a bad prompt and call it architecture. The planted traps are the failures I actually see in production: the undeclared compound key on `returns`, the pre-discount `line_total` decoy, the February fiscal year. Those are designed so a well-formed query still returns a wrong number, which is the whole thesis.

Two things I want to name specifically. `LIMITATIONS.md` concedes the hard ones rather than the easy ones, including that a miscertified measure would be confidently wrong in S too. And the artifacts regenerate: I rsync'd the repo to scratch, re-ran the scorer, and `summary.md` came back byte-identical. That is rarer than it should be.

The ordering U < D < G < S survives everything below. I'd say that in your first paragraph if I were you, because most of what follows is hygiene.

## The one finding that changes what you can claim

`score/stats.py:34-45` runs `binomtest` over 1,017 pairs as if they were independent trials. They aren't. They're 52 questions times 7 model tiers times up to 3 runs, about 19.6 observations per question, and outcomes inside a question are correlated by construction. When S refuses `s7_unans_weather` it refuses on all 21 of that question's pairs. That's one question's worth of evidence, not 21.

Twelve lines above, `cluster_bootstrap_ci()` already resamples questions and its docstring says why. The file names the right unit of analysis for the intervals and then drops it for the tests. `extract_numbers.py:41-51` carries a second copy of the same naive test, and that's the one feeding `{{mcnemar.GS_p}}` into the paper, so it ships twice.

I reproduced your published p-values exactly before touching anything. Clustered, two ways that share no code:

| rung | published p | cluster permutation | Wilcoxon (n=52) | questions for/against |
|---|---|---|---|---|
| U → D | 1.14e-191 | < 0.0001 | < 0.0001 | 45 / 0 |
| D → G | 9.02e-05 | 0.050 | 0.108 | 12 / 4 |
| G → S | 1.31e-05 | 0.155 | 0.094 | 15 / 6 |
| U → S | 6.98e-202 | < 0.0001 | | 44 / 1 |

Design effect on G→S is 8.8, so those 1,017 pairs carry roughly 116 observations' worth of information, and the 174 discordant pairs sit in 21 of the 52 questions.

Your own CIs already said this. `ci_by_condition.csv` has G at 84.5 [77.9, 90.5] and S at 90.2 [83.9, 95.6], overlapping across more than half their width. The correct analysis was in the repo, shipping, telling the truth. Only the p-value hid it.

### Where the increment actually lives

This is the part I'd most want to know if it were my paper. Decompose the 52 question-level differences and the G→S gain isn't diffuse at all. It's five questions:

```
all 52 questions      G 82.8%   S 89.5%   +6.7   p = 0.094
the 5 unanswerable    G 39.0%   S 100.0%  +61.0
the 47 answerable     G 87.4%   S 88.3%   +0.9   p = 0.836
```

On questions that have an answer, S and G are indistinguishable. The entire enforcement increment is refusal.

I don't think that's bad news. Refusing the unanswerable is enforcement working, it's one of the three guarantees you enumerate, and S earns those wins honestly because G invents a `weather` column and S structurally cannot. But it's a narrower result than "deterministic compilation makes answers more correct," and your decomposition sentence invites the broader reading. The claim the data supports is that enforcement converts hallucination into refusal, and it does not measurably improve answers to answerable questions. That version is both true and much harder to attack.

I checked this isn't a provenance artifact: v1 tiers alone give +8.6 (p=0.15), v3 alone +1.9 (p=0.25). Same story.

The fix is more questions, not more runs or more models. That's the trap, because runs and models add correlated observations, which is exactly what got you here. Roughly 120 to 150 questions would settle it.

## The oracle grades itself, and we tested it for you

For 50 of 63 questions, ground truth is computed by `compile.py` over `semantic_models/*.yaml`. Condition S is answered by the same code over the same YAML. In 90% of those runs the two sides compile to byte-identical SQL, so the comparison is one string executed twice against one file.

I corrupted `net_revenue`'s `agg_sql` in memory to drop the discount. Truth moved from 60,185,854 to 64,793,930. S was still scored 100% correct, and a D or G answer carrying the semantically correct number was scored wrong. A miscertified measure is invisible in S and charged to the free-form conditions instead.

`LIMITATIONS.md` §8 names this, and you'd reasonably say it's disclosed. The problem is that disclosure doesn't bound it, because nothing in the repo checks a compiled measure against independently written SQL. The cheap fix is hand-written `truth_sql` for the fifteen trap questions. The harness already supports it and six questions already use it.

We also did the expensive fix, since it's the only real evidence available: we rebuilt the d1 semantic model as LookML on Looker over BigQuery, and ran the certified measures head to head.

```
12 of 12 certified measures match, compiler-on-DuckDB vs LookML-on-BigQuery
net_revenue  60,185,854.28   gross_margin  27,199,313.82   aov  1,672.015
order_count  35,996          active_customers  4,996       refund_total  2,668,316.54
```

Two implementations sharing only a YAML file agree on every certified number. That's the corroboration the repo can't produce from inside itself, and it's also the first actual test of `whitepaper.src.qmd:185`, where you call condition S vendor-neutral without testing a vendor.

## Enforcement turns out to be two different things

This one is a contribution rather than a correction, and I think it's a section you could write.

Ask both layers for an order-grain measure sliced by a line-grain dimension. Your compiler refuses: "finer grain would fan out." Looker answers, using symmetric aggregates.

```
Looker's 8 category rows sum to   1,147,012.54
true order-grain total               450,531.23
naive fan-out (what U/D/G emit)    1,353,518.89   (3.00x)
```

Symmetric aggregates genuinely worked. They de-duplicated inside each category and pulled 3.00x down to 2.55x. What they cannot do is make an order-grain measure additive across line-grain groups, because an order spanning three categories legitimately appears in three rows carrying its full shipping fee. Mean categories per order is 2.549, which predicts 1,148,193 against the 1,147,012 Looker returned.

So neither layer is safe, and they fail in opposite directions. Yours declines and gives the user nothing. Looker returns eight individually defensible cells in a column that silently sums to 2.55 times the truth, with no visual signal it isn't additive. Your benchmark scores only one of those as correct, which is a defensible choice but currently an invisible one.

## One small embarrassing thing

`requirements.txt` pins `pandas>=2.0` with no upper bound. On pandas 3, `score.py:124` dies with `AttributeError: 'float' object has no attribute 'lower'`, because a missing `sql` is NaN, NaN is truthy, so the `or ""` guard never fires. A fresh `pip install -r requirements.txt` today breaks `make score`, `make reproduce` and `make paper` outright. One line to guard, one line to pin. Worth doing before anyone clones it.

## The rest

None of these move a published number.

| | | |
|---|---|---|
| `summary.md` provenance banner | false for 33.5% of rows (v1/v3 mixed) | contamination narrows G→S, so it works against you |
| identity-vs-label | prompt instruction in S, not compiler-enforced; `compile.py` never reads `identity:` | your three enumerated guarantees don't include it, but the trap list implies they do |
| multi-measure combine | joined every subquery to `m0`, losing group labels and splitting groups | fixed; 0 of 1,190 logged rows affected, fires today on a certified d2 measure |
| `ORDER BY` NULL placement | unpinned, so the same plan returns a different row per engine | fixed; your corpus dodges it because all 25 logged sorts are DESC |
| `composability.py` | counts one file, so "256 lines and does not grow" regenerates as 300 | measure model growth, not backend growth |
| cost aggregation | averages 565 zero-token Claude rows; four D-token values ship in one repo | no published number wrong, README stale |
| enterprise dollar table | uncached list price, roughly 3x high | the ratio claims survive caching, the dollars don't |
| U has no refusal affordance | while D, G and S all do | excluding the affected suite widens D−U, so this favours you too |
| compiler join order | built from a Python set, so emitted SQL text differs across processes | values identical every time, but the SQL is not byte-reproducible and `LIMITATIONS.md` doesn't say so |

## What's available

The branch has a BigQuery execution arm (closes your LIMITATIONS §8), a pluggable dialect layer, a plan-replay harness that re-runs logged condition-S plans against any backend with no model calls, and the LookML project. The dialect control came back at 0 divergences across 1,190 plans, worst relative gap 1.7e-14, re-run with BigQuery's cache disabled so it isn't a cached-result artifact.

Take any of it or none of it. If you only act on one thing, make it the clustering, because it's the one a methods reviewer finds in an afternoon and it's much better coming from you than from them.
