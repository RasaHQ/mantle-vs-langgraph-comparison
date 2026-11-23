#!/usr/bin/env bash
# Runs the benchmark, then writes the comparison table to results/README.md.
#
#   ./run.sh                         all three setups, 3 batches each (9 runs per scenario)
#   ./run.sh lg-high                 one setup
#   ./run.sh mantle lg --batches 1   fewer batches
#   ./run.sh --smoke                 one short conversation per setup, results in logs/smoke
set -euo pipefail
cd "$(dirname "$0")"

[ -x .venv-rasa/bin/python ] || { echo "Run ./setup.sh first." >&2; exit 1; }
if [ "${1:-}" = "--smoke" ]; then
  shift
  set -- mantle lg lg-high --batches 1 --runs 1 --scenario order_status_happy_path --results-dir logs/smoke "$@"
fi
case "${1:-}" in
  ""|-*) set -- mantle lg lg-high "$@" ;;
esac
exec .venv-rasa/bin/python harness/run.py "$@"
