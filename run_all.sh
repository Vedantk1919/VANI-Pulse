#!/usr/bin/env bash
# Full pipeline: features -> model -> backtest -> sample plans
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
$PY -m src.features
$PY -m src.model
$PY -m src.backtest
$PY -m src.samples
