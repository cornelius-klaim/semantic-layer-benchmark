# Reaching 100% — the cost per layer

The experiment (the user's design): starting from the v1 model, iterate until each condition is as
accurate as it can be made, and **count the edits each layer needs** — and whether those edits are
*durable* (verified once, correct forever, transfer to every model) or *fragile* (prompt nudges the
model may ignore). This quantifies "get there faster."

Result, on the clean subset (Gemini flash-lite + Claude haiku/sonnet/opus, complete in every run):

| Layer | Start | After edits | Edits | Nature of edits | Ceiling |
|------:|:-----:|:-----------:|:-----:|:----------------|:--------|
| **S** semantic layer | 84.9% | **100.0%** | **8** | durable: certified measures + deterministic compiler hardening | **100% reached, and it holds across ALL 7 models** |
| **G** prompt-model    | 74.9% | 76.0% | 1 (attempted) | fragile: one prompt guardrail | **plateaus <100%** |
| **D** doc-grounded    | 69.3% | 72.4% | 1 (attempted) | fragile: one prompt guardrail | **plateaus <100%** |
| **U** ungrounded      | 16.9% | 16.3% | 0 possible | — | **cannot reach 100% by construction** |

## Condition S — the 8 edits that reached 100%

Every edit was verified against ground truth by construction; each is deterministic and transferred
to all seven models at once (S never asks a model to write SQL — the model only names a field).

Semantic-model edits (the architect's domain):
1. Promoted 3 certified measures: `avg_shipping_fee`, `shipping_pct_of_revenue` (derived),
   `net_revenue_after_refunds` (derived).  → fixed s2_avg_line_disc, s2_ship_pct, s5_ship_pct_region, s3_net_of_refunds
2. Promoted the Advanced-Negotiation contrast: `attainment_advneg_yes/no` + `advneg_attainment_lift`
   (derived).  → fixed s5_advneg_lift
3. Tightened `net_revenue_after_refunds` / `net_revenue` descriptions so "excluding returned orders"
   maps to net_revenue, not the refund-subtraction measure.  → fixed s1_netrev_p2
4. Catalog guidance: refuse ambiguous questions ("sales" → clarify); rank by IDENTITY not label.
   → fixed s7_ambiguous_sales, conv_vocab_identity_t3
5. Truth correction: `conv_grain_drift_t3` ("*also* show shipping by region") is cumulative.

Deterministic compiler hardening (one-time infrastructure; benefits every future dataset/model):
6. Expression-measures (derived measures combining certified measures at different grains).
7. Tolerate filter key/operator variants (`field|dimension|name|column`, `op|operator`, eq/in/...).
   → fixed conv_vocab_identity_t1/t2/t5
8. Tolerate order_by key variants (`field|measure|dimension`, `dir|order|direction`) and treat a
   single date value with op `in` as `=`.  → fixed conv_vocab_identity_t3/t5

Of the 8, five were deterministic and required **no model re-run at all** — the already-logged
plans simply recompiled correctly. Only three (the new measures / tightened descriptions / guidance)
needed the models to pick a different field, and once the definition was right, **all seven models
picked it**.

## Conditions D and G — one comparable edit, then a wall

We added the single highest-leverage guardrail available to a free-form condition: an instruction to
`REFUSE:` the unanswerable, `CLARIFY:` the ambiguous, rank by identity, and respect grain. On the
seven refusal/ambiguity questions this lifted them sharply — but not to 100%:

- G refusal/ambiguity cluster: ~10% → **77.2%**.  D: ~10% → **73.5%**.  (S on the same cluster: 100%.)

The residual is the point. Even *told explicitly* to refuse, ~23% of the time the free-form models
still fabricated SQL against an unrelated column (`error`/`refusal_wrong`) or answered an ambiguous
question anyway (`silent_guess`). A prompt can *ask* for refusal; it cannot *enforce* it. And the
other failure families — fan-out on ad-hoc ratios, the identity trap, vocabulary — persisted even
with the certified definitions sitting in the prompt: the definitions were present, but the model
still authored the SQL, and authored it wrong.

To push D/G further would mean writing a bespoke, exact SQL specification into the prose for every
remaining question — at which point one has rebuilt the semantic layer in text, **minus** the
enforcement guarantee, and *still* cannot certify that a given model on a given run will comply.
There is no finite, durable edit set that pins D/G at 100%.

## Condition U — zero edits possible

U is the physical schema only. Any edit that supplies the missing meaning turns U into D/G/S. By
construction U cannot reach 100%: the semantics the questions require are not in the schema. It sits
at ~16% — and that is the entire point of the ladder.

## The headline

- **S: 8 durable, verifiable edits → 100%, identical across 7 models and 2 vendors.**
- **D/G: comparable edits help (+7 pts) but hit an irreducible wall well below 100% — the model
  ignoring instructions it was given.**
- **U: no edit can get there.**

Correctness is *cheap and permanent* to reach through enforcement, and *expensive, fragile, and
ultimately unreachable* through prompting alone. That is "get there faster," measured.

## Cost and tokens (Gemini arm — the one with per-call token accounting)

### Runtime cost per query
| layer | in tok | out tok | total/query | latency | ~$ / 1000 queries |
|------:|-------:|--------:|------------:|--------:|------------------:|
| U | 331 | 75 | 406 | 3.19s | $0.20 |
| D | 3,044 | 85 | 3,129 | 2.63s | $1.02 |
| G | 1,769 | 85 | 1,854 | 2.23s | $0.64 |
| **S** | **717** | **40** | **757** | **1.56s** | **$0.26** |

S is the **cheapest grounded layer and the fastest** — ~4× cheaper than D, ~2.5× cheaper than G,
and nearly as cheap as ungrounded U — because it sends a compact field catalog and receives a compact
plan, while D and G resend the entire knowledge base on every call and emit full SQL. (Blended Gemini
rate ≈ $0.30 / 1M input, $1.20 / 1M output.)

### Total tokens across the benchmark
D + G together burned **3.0M tokens**; S used **455K** — a 6.6× difference for the two free-form
grounded layers over the enforced one.

### Cost to REACH 100%
- **S: 96 model-calls, ~110K tokens — and it converged.** Five of the eight edits needed *zero*
  model calls (the logged plans simply recompiled); only the failing questions were ever re-run.
- **D/G guard attempt: 161 model-calls, ~478K tokens — and it did NOT converge** (refusal plateaued
  at 43–50%). Roughly **4× the tokens of S’s fixes, for a result that never reaches 100%.**

So enforcement is cheaper on every axis that matters: cheaper per query at runtime, cheaper in total,
and dramatically cheaper to drive to correctness — because most of its fixes cost no inference at all,
and the ones that do touch only the handful of questions that failed.
