#!/usr/bin/env bash
# Full pipeline: features -> model -> backtest -> global context -> allocator -> checks -> sample plans
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
$PY -m src.features          # Problem 3: call-attempt features
$PY -m src.model             # Problem 3: ensemble timing model + retry-gap curve
$PY -m src.backtest          # Problem 3: September backtest, equal-dials metric, lead tiers
$PY -m src.timeline          # Problem 2: cross-channel event timeline (needs data/gc)
$PY -m src.gc_validation     # Problem 2 -> 3: which context signals change the best time
$PY -m src.gc_eval           # Problem 2: seller.md size, coverage, freshness
$PY -m src.allocator         # batch allocator demo + latency
if [ -f data/persona/incorrect_mf.parquet ] || compgen -G "data/persona/ps07_evaluator_outputs_*.csv" >/dev/null; then
  $PY -m src.label_check     # meeting-label robustness (needs the evaluator outputs)
fi
$PY -m src.samples           # sample call plans + seller.md files
