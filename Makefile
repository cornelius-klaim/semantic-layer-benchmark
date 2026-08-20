# Semantic Layer Benchmark — reproducible pipeline.
# Requires: python3 with duckdb, pandas, numpy, scipy, matplotlib, pyyaml (see requirements.txt),
# and GEMINI_API_KEY in the environment for the model-calling steps.
PY=python3
MODELS_LITE=gemini-2.5-flash-lite
MODELS_MID=gemini-2.5-flash
MODELS_PRO=gemini-2.5-pro
ALL_MODELS=gemini-2.5-flash-lite,gemini-2.5-flash,gemini-2.5-pro
# Current-generation Gemini tiers (added in review). NOTE: gemini-3.1-pro maps to the
# preview build gemini-3.1-pro-preview (a rolling/preview alias — exact cell-level
# reproduction is not guaranteed; see the paper's version-pinning note). The ladder
# suites (1-5,7,8) exclude suite 6 (multi-turn, run separately) and suite 9 (drill-down).
MODELS_FLASH37=gemini-3.7-flash
MODELS_PRO31=gemini-3.1-pro
LADDER_SUITES=1,2,3,4,5,7,8

.PHONY: reproduce data run score stats plots paper clean

## Full pipeline: data -> run models -> score -> stats -> plots
reproduce: data run score stats plots
	@echo "Reproduction complete. See results/summary.md, results/stats.md, paper_assets/figures/."

## 1. Build seeded warehouses + ground truth by construction
data:
	$(PY) datagen/gen_d1.py
	$(PY) datagen/gen_d1_returns.py
	$(PY) datagen/gen_d2.py
	$(PY) emit/emit.py

## 2. Run the full matrix (3 tiers x U/D/G/S x all questions) + multi-turn
run:
	$(PY) harness/run.py --models $(MODELS_LITE) --runs 5 --out results/runs_lite.jsonl
	$(PY) harness/run.py --models $(MODELS_MID)  --runs 5 --out results/runs_flash.jsonl
	$(PY) harness/run.py --models $(MODELS_PRO)  --runs 3 --out results/runs_pro.jsonl
	$(PY) harness/run.py --models $(MODELS_FLASH37) --runs 5 --suites $(LADDER_SUITES) --out results/runs_g37flash.jsonl
	$(PY) harness/run.py --models $(MODELS_PRO31)   --runs 3 --suites $(LADDER_SUITES) --out results/runs_g31pro.jsonl
	$(PY) harness/multiturn.py --models $(ALL_MODELS) --runs 3 --out results/runs_multiturn.jsonl

## Parallel variant of `run` (backgrounded; faster wall-clock)
run-parallel:
	setsid $(PY) harness/run.py --models $(MODELS_LITE) --runs 5 --out results/runs_lite.jsonl  >results/log_lite.txt  2>&1 &
	setsid $(PY) harness/run.py --models $(MODELS_MID)  --runs 5 --out results/runs_flash.jsonl >results/log_flash.txt 2>&1 &
	setsid $(PY) harness/run.py --models $(MODELS_PRO)  --runs 3 --out results/runs_pro.jsonl   >results/log_pro.txt   2>&1 &
	setsid $(PY) harness/run.py --models $(MODELS_FLASH37) --runs 5 --suites $(LADDER_SUITES) --out results/runs_g37flash.jsonl >results/log_g37flash.txt 2>&1 &
	setsid $(PY) harness/run.py --models $(MODELS_PRO31)   --runs 3 --suites $(LADDER_SUITES) --out results/runs_g31pro.jsonl   >results/log_g31pro.txt   2>&1 &
	setsid $(PY) harness/multiturn.py --models $(ALL_MODELS) --runs 3 --out results/runs_multiturn.jsonl >results/log_mt.txt 2>&1 &

## Claude arm (2nd vendor). The prompts are generated here; answering is done by Claude Code
## subagents that read results/claude_prompts/<ds>__<cond>.txt and write
## results/claude_raw/<tier>__<ds>__<cond>.json. `claude-ingest` scores those raw files.
claude-batches:
	$(PY) harness/gen_claude_batches.py
claude-ingest:
	$(PY) harness/ingest_claude.py claude-opus 0
	$(PY) harness/ingest_claude.py claude-sonnet 0
	$(PY) harness/ingest_claude.py claude-haiku 0

## Recompile all condition-S rows from their stored plans with the current compiler (no model calls).
recompile-s:
	$(PY) harness/recompile_s.py results/runs_*.jsonl

## 3-5. Analysis
score:
	$(PY) score/score.py
stats:
	$(PY) score/stats.py
plots:
	$(PY) score/plots.py
## Build results/paper_numbers.json. extract_numbers writes the base object (overwriting); every
## other script MERGES its keys in, so ORDER MATTERS — extract_numbers must run first.
numbers:
	$(PY) score/extract_numbers.py
	$(PY) score/composability.py
	$(PY) score/reaching100_numbers.py
	$(PY) score/promotion_numbers.py
	$(PY) score/drilldown.py
	$(PY) score/agentic_report.py

## Score the auxiliary experiments (Test A drill-down, Test B agentic) — separate from the main matrix
aux:
	$(PY) score/drilldown.py
	$(PY) score/agentic_report.py

## Regenerate the analysis + assets from existing runs, and fill the paper's numbers.
## numbers before plots (fig_drilldown/fig_agentic read paper_numbers.json), fill last.
paper: score stats numbers plots
	$(PY) paper/fill_numbers.py

clean:
	rm -f results/runs_*.jsonl results/log_*.txt results/*.csv results/summary.md results/stats.md
	rm -f paper_assets/figures/*.png paper_assets/figures/*.pdf
