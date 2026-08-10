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

## Headline result

Across **2 vendors (Gemini + Claude), 7 models, and ~3,000 scored trials**, accuracy climbs the
ladder **U 16% → D 76% → G 80% → S 86%**, with the identical ordering for both vendors. Certified
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

## Limitations

See `LIMITATIONS.md`. In brief: two vendors (not all model families), with the Claude arm run via a
batched subagent protocol (single run) distinct from the Gemini per-call protocol; synthetic data
(which is what makes ground truth exact); TPC-DS/Spider/BIRD and BigQuery execution scoped out;
condition S is only as good as its model and, by design, does not synthesize un-modeled ad-hoc
metrics (it refuses or returns components). The claim rests on the *ordering* U < D ≲ G < S and the
content-vs-enforcement decomposition, not the absolute numbers.
