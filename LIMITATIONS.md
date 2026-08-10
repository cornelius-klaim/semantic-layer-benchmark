# Limitations and threats to validity

This benchmark is designed to isolate one causal question — *does the form in which business
semantics are supplied to an LLM change the correctness of the analytics it produces?* — under
controlled, reproducible conditions. Several deliberate scoping choices bound what the results
support. We state them plainly so the reader can calibrate.

## Construct and internal validity

1. **Vendor coverage and the Claude-arm protocol.** We test two vendors and seven models —
   Google Gemini (`gemini-2.5-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-pro`,
   `gemini-3.5-flash`) and Anthropic Claude (`claude-haiku`, `claude-sonnet`, `claude-opus`) —
   and the U < D ≲ G < S ordering replicates across both. We do **not** claim coverage of all
   model families. Importantly, the two vendors are administered by *different protocols*: the
   Gemini arm issues one API call per (question, condition); the Claude arm is administered via
   subagents in a **batched** form (grounding shown once per condition, every question answered
   independently in one pass, single run). The within-Claude ladder is therefore internally
   valid and the cross-vendor agreement is corroborating, but the two arms are not matched
   call-for-call, and the Claude tiers have fewer runs (n=1) than the two five-run Gemini tiers.
   Condition **S** is the most robust to all of this: S never asks a model to author SQL, so its
   correctness is a property of the compiler, not the model or the protocol. *(One author is
   employed on the Looker team at Google; the benchmark, data, and scorer are fully open and
   deterministic precisely so this result does not rest on trust.)*

2. **Representation parity between D and G.** Conditions D (OKF markdown documents) and G
   (structured model) are emitted from **one** source of truth (`emit/emit.py`), so any D-vs-G
   gap is representation, not content. But the two serializations are not matched on token
   count (D is ≈1.9× longer prose); part of any observed difference may be prompt-length or
   attention effects rather than structure per se. We report token counts alongside accuracy so
   this is visible.

3. **Condition S can only be as good as its model.** S's ceiling is the semantic model we
   authored. A question the model does not cover is *refused* — correctly, by construction — but
   a *miscertified* measure would produce a confidently wrong answer in S just as elsewhere. The
   benchmark measures fidelity of enforcement given a correct model; it does not measure the
   organisational cost or error rate of authoring that model. The refusal behaviour we reward is
   "refuse when out of scope," not "never be wrong if the model is wrong."

4. **Scorer scope.** Numeric answers are graded against ground truth computed *by construction*
   from the seeded generators (1% relative tolerance); set/top-N answers by order-insensitive
   match. SQL audits (fan-out, partial-key joins, missing certified filters, identity-vs-label)
   are heuristic regex flags over generated SQL and may under- or over-count specific patterns;
   they are reported as corroborating evidence, not as the primary accuracy metric.

5. **Ambiguity/refusal grading.** Clarification questions are scored by detecting a
   clarifying response versus a silent guess. Natural-language clarification detection is
   keyword-based and imperfect; a model that clarifies in unusual phrasing may be undercounted.

## External validity

6. **Synthetic data.** D1 (NorthStar retail) and D2 (cross-domain LMS×Sales×HR) are seeded
   synthetic warehouses. Synthesis is what makes ground truth exact and the planted effects
   (identity collisions, grain traps, compound keys, a +0.12 causal lift with a tenure
   confounder, messy channel/email vocabularies) *known*. Real warehouses are messier in ways we
   did not model; absolute accuracies would likely fall for all conditions on production data.
   The **ordering** U < D ≈ G < S is the claim, not the absolute numbers.

7. **TPC-DS and Spider/BIRD not run.** The specification scopes standard text-to-SQL corpora
   (TPC-DS, Spider, BIRD) as external-validity anchors. This release reports the two purpose-built
   datasets that carry the planted semantic traps; the public corpora are left as a
   straightforward extension (the harness is dataset-agnostic — it reads a DDL, a semantic model,
   and a questions file), and are **not** claimed here.

8. **Execution engine.** All SQL is executed on DuckDB. BigQuery execution (in the spec) would
   test dialect portability; we do not claim it. Because ground truth is computed through the same
   certified compiler used by condition S, an engine-specific SQL quirk would affect all
   conditions symmetrically.

9. **Prompt sensitivity.** Each condition uses one prompt template. We fixed temperature at 0 and
   took multiple runs to quantify residual nondeterminism, but we did not sweep prompt wording.
   Prompt engineering could raise U/D/G somewhat; it cannot supply the *enforcement* guarantee
   that distinguishes S.

## What the design does control for

- **Same questions, same data, same ground truth** across all conditions (paired design;
  differences tested with McNemar).
- **Same underlying semantics** for D and G (single emitter).
- **Business-language questions** (no leakage of schema column names into the prompt).
- **Multiple runs** per cell to separate signal from sampling noise, with 95% cluster-bootstrap
  confidence intervals that resample *questions* (the unit of generalisation), not just runs.
