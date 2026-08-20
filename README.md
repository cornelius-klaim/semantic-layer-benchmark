# The Grounding Ladder — Semantic Layer Benchmark

A controlled benchmark measuring how the **representation of business semantics** supplied to an LLM
changes the **correctness** of the analytics it produces. Accompanies the book *The Semantic Gold
Layer*. Everything here is open, seeded, and deterministic; the paper's numbers reproduce with
`make reproduce`.

## The question

The hard part of enterprise analytics is not SQL syntax — modern models write fluent SQL. It is
*semantics*: which rows are revenue, at what grain a number is additive, which column is an identity
vs. a label, how two systems that share no key are joined. We hold the questions, the data, and the
ground truth fixed and vary only the grounding along a four-rung ladder:

| Condition | Name | What the model gets | Writes SQL? | Enforced? |
|---|---|---|---|---|
| **U** | Ungrounded | Physical schema (DDL) only | yes | no |
| **D** | Document-grounded | DDL + OKF-style markdown knowledge base | yes | no |
| **G** | Prompt-grounded model | DDL + the *same facts* as a structured semantic model | yes | no |
| **S** | Semantic-layer-mediated | A field catalog; returns a **query plan**, compiled deterministically, refuses out-of-model questions | **no** | **yes** |

`D` and `G` are emitted from a **single source of truth** (`emit/emit.py`), so any D-vs-G difference
is *representation*, not content. `D→G` isolates representation; `G→S` isolates **enforcement**.

## Token economics — the single most significant fact

Higher accuracy usually costs more tokens. Here it costs **fewer**. `D` and `G` resend the entire
knowledge base (DDL + OKF markdown / structured model) on every call and ask the model to emit full
SQL; `S` sends a compact field catalog and receives a compact query plan that is compiled
deterministically. The result is that the *most* accurate condition is also the *cheapest* grounded
one. Measured on the Gemini arm (the arm with per-call token accounting), pooled across all questions
and models:

| Layer | In tok/query | Out tok/query | Total/query | Latency | ~$ / 1,000 queries | Tokens vs **S** |
|---|--:|--:|--:|--:|--:|--:|
| U ungrounded | 331 | 75 | 406 | 3.19s | $0.20 | 0.54× (but 16% accurate — useless) |
| D doc-grounded (OKF) | 3,044 | 85 | 3,129 | 2.63s | $1.02 | **4.1× more** |
| G prompt-grounded model | 1,769 | 85 | 1,854 | 2.23s | $0.64 | **2.4× more** |
| **S semantic layer** | **717** | **40** | **757** | **1.56s** | **$0.26** | **1.0× (baseline)** |

Against the layers that actually work, `S` cuts tokens **~76% vs D** and **~59% vs G** per query,
while being the **fastest** and the **most accurate**. Across the full benchmark, `D + G` together
burned **3.0M tokens**; `S` used **455K** — a **6.6×** difference.

*(Blended Gemini rate used for the dollar column: ≈ $0.30 / 1M input, $1.20 / 1M output.)*

### Cost at enterprise scale (extrapolation)

The per-query deltas are small; at enterprise query volumes they compound. Taking the measured
per-query token cost above and scaling by analytical-query volume (each query answered once by the
LLM):

| Analytical queries | D / year | G / year | **S / year** | Saved vs D | Saved vs G |
|---|--:|--:|--:|--:|--:|
| 10k / day (3.65M/yr) | $3,720 | $2,340 | **$950** | $2,770 | $1,390 |
| 100k / day (36.5M/yr) | $37,200 | $23,400 | **$9,500** | $27,700 | $13,900 |
| 1M / day (365M/yr) | $372,000 | $234,000 | **$95,000** | $277,000 | $139,000 |

Two multipliers make this conservative. **Model tier:** the table uses a cheap flash-class model; a
frontier reasoning model priced ~20–30× higher scales every figure by the same factor (S's per-query
edge is a *ratio*, so it holds). **Retries and agentic loops:** free-form `D`/`G` fail ~15–25% of
governed questions and get re-run or human-corrected; `S`'s deterministic compile means a governed
question is answered right the first time, so the effective cost gap is wider than the single-call
table shows. The dominant enterprise cost — a *wrong* number reaching a decision — is the axis the
token table cannot price at all.

## Headline result

Across **2 vendors (Gemini + Claude), 9 models — including the current-generation `gemini-3.7-flash`
and `gemini-3.1-pro-preview` — and ~4,500 scored trials**, accuracy climbs the
ladder **U 18% → D 82% → G 84% → S 90%**, with the identical ordering for both vendors. Certified
*content* (U→G) delivers most of the gain (+63 pts) and can be done in-prompt; deterministic
*enforcement* (G→S) adds a further significant increment (+6.5 pts, McNemar p≈1e-4) concentrated in
the highest-stakes failures — silent fan-out, confident answers to unanswerable questions (S refuses:
85% vs ~18%), and multi-turn definition drift. Enforcement is a **trade**: the layer is near-perfect
on governed questions but can only answer what is modeled, so it underperforms the free-form
conditions on ad-hoc metrics it was never given. It also **compresses the capability gap** — the
weakest model gains the most from the layer. See `results/summary.md`, `results/stats.md`, and
`paper/whitepaper.qmd`.

## Repository layout

```
datagen/          seeded data generators (ground truth by construction)
  gen_d1.py         D1 NorthStar retail (grain, identity, vocabulary, time traps)
  gen_d1_returns.py Suite 3 compound-key returns table (undeclared FK, partial-key fan-out)
  gen_d2.py         D2 cross-domain Learning×Sales×HR (email-bridge + planted causal effect)
schemas/          physical DDL shown to U/D/G (certified rollups deliberately excluded)
semantic_models/  the single source of truth (d1.yaml, d2.yaml)
emit/             emit_g (structured, condition G) + emit_d (OKF markdown, condition D)
compiler/         condition S — deterministic, fan-out-safe plan→SQL compiler with refusal
harness/          run.py (U/D/G/S runner), multiturn.py (Suite 6), llm.py (Gemini adapter)
questions/        business-language questions + by-construction truth (d1, d2, multiturn)
truth/            planted-effect ground truth (D2)
score/            score.py (classify+audit), stats.py (bootstrap CI + McNemar),
                  plots.py (figures), extract_numbers.py (paper_numbers.json)
results/          all logged runs (*.jsonl), scored.csv, aggregates, summary.md, stats.md
paper/            the whitepaper (whitepaper.src.qmd + fill_numbers.py → whitepaper.qmd)
paper_assets/     camera-ready figures (png + pdf)
```

## Reproduce

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...            # required for the model-calling step only
make reproduce                       # data → run → score → stats → plots
# or, faster wall-clock:
make data && make run-parallel       # backgrounds the four run jobs
make paper                           # score + stats + plots from existing runs
python3 paper/fill_numbers.py        # bake numbers into paper/whitepaper.qmd
```

## Datasets and planted traps

- **D1 NorthStar** — order-grain `shipping_fee` vs. line-grain discounts (fan-out); a deliberately
  wrong `line_total` column; 40 customers named "John Smith" (identity vs. label); a `returns` table
  keyed by compound `(order_id, line_number)` (joining on `order_id` alone inflates refunds 3.65×);
  channel vocabulary stored three different ways; a February-start fiscal year.
- **D2 Cross-Domain** — Sales keyed by `employee_id`, an LMS keyed by a messy email, joinable only
  through an HR bridge after email normalization; a planted **+0.12** tenure-adjusted causal effect
  of a course on quota attainment, confounded by tenure (naïve gap is larger), with a null-effect
  placebo course. The certified identity rollup is present only to condition S.

## Scoring

Numeric answers: 1% relative tolerance. Set/top-N: order-insensitive match. Refusal to an
unanswerable question is correct; refusal to an answerable one is wrong. We additionally report
error magnitude on wrong answers, heuristic SQL audit flags (fan-out, partial-key, missing certified
filter, identity-vs-label), cross-paraphrase consistency, and multi-turn drift. Statistics: 95%
cluster-bootstrap CIs (resampling questions) and McNemar exact paired tests between adjacent rungs.

## The accuracy ceiling — S reaches 100%, the free-form layers plateau

Runtime accuracy is only half the story; the other half is **how far each layer can be pushed, and at
what cost**. We took the v1 models and iterated each condition to its ceiling, counting the edits and
whether they were *durable* (verified once, correct forever, transfer to every model) or *fragile*
(prompt nudges a model may ignore). On the clean subset (Gemini flash-lite + Claude haiku/sonnet/opus,
complete in every run):

| Layer | Start | After edits | Edits | Nature | Ceiling |
|---|--:|--:|--:|---|---|
| **S** semantic layer | 84.9% | **100.0%** | **8** | durable: certified measures + deterministic compiler hardening | **100% — and it holds across all 7 models / 2 vendors** |
| G prompt-model | 74.9% | 76.0% | 1 (attempted) | fragile: one prompt guardrail | **plateaus < 100%** |
| D doc-grounded | 69.3% | 72.4% | 1 (attempted) | fragile: one prompt guardrail | **plateaus < 100%** |
| U ungrounded | 16.9% | 16.3% | 0 possible | — | **cannot reach 100% by construction** |

`S` reached **100%** with **8 durable edits** — five of which required *zero* model re-runs (the
already-logged plans simply recompiled correctly), and the three that did touched only the handful of
questions that had failed. Every edit transferred to all seven models at once, because `S` never asks
a model to write SQL — the model only *names a field*.

`D` and `G` cannot get there. Given the single highest-leverage guardrail — an explicit instruction
to refuse the unanswerable, clarify the ambiguous, and respect grain — their refusal cluster rose from
~10% to ~73–77%, then hit a wall: **even told explicitly to refuse, ~23% of the time the free-form
models still fabricated SQL or answered anyway.** A prompt can *ask* for refusal; it cannot *enforce*
it. Pushing further would mean writing a bespoke exact-SQL spec into prose for every question — at
which point you have rebuilt the semantic layer in text, minus the enforcement guarantee, and *still*
cannot certify compliance on a given run. There is no finite, durable edit set that pins `D`/`G` at
100%.

The cost of *reaching* correctness runs the same direction: `S` converged in **96 model-calls /
~110K tokens**; the `D`/`G` guard attempt spent **161 calls / ~478K tokens (≈4×)** and never
converged. Correctness is **cheap and permanent** through enforcement, and **expensive, fragile, and
ultimately unreachable** through prompting alone. Full detail in `results/CHANGELOG_PER_LAYER.md`.

## Limitations

See `LIMITATIONS.md`. In brief: two vendors (not all model families), with the Claude arm run via a
batched subagent protocol (single run) distinct from the Gemini per-call protocol; synthetic data
(which is what makes ground truth exact); TPC-DS/Spider/BIRD and BigQuery execution scoped out;
condition S is only as good as its model and, by design, does not synthesize un-modeled ad-hoc
metrics (it refuses or returns components). The claim rests on the *ordering* U < D ≲ G < S and the
content-vs-enforcement decomposition, not the absolute numbers.
