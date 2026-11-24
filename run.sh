#!/usr/bin/env bash
# Runs the benchmark, then writes the comparison table to results/README.md.
#
#   ./run.sh --results-dir my-results          all three setups, 3 runs per scenario
#   ./run.sh lg-high --results-dir my-results  one setup
#   ./run.sh --smoke                           one short conversation per setup, results in logs/smoke
#
# Without --results-dir, runs go to results/ next to the published ones, and the
# tables are built from all of them.
set -euo pipefail
cd "$(dirname "$0")"

[ -x .venv-rasa/bin/python ] || { echo "Run ./setup.sh first." >&2; exit 1; }
if [ "${1:-}" = "--smoke" ]; then
  shift
  set -- mantle lg lg-high --sets 1 --runs 1 --scenario order_status_happy_path --results-dir logs/smoke "$@"
fi
case "${1:-}" in
  ""|-*) set -- mantle lg lg-high "$@" ;;
esac
# On macOS, keep the machine awake: sleep freezes the timeouts and drops the
# open connections to OpenAI, which wrecks the conversations in flight.
if command -v caffeinate >/dev/null; then
  exec caffeinate -i .venv-rasa/bin/python harness/run.py "$@"
fi
exec .venv-rasa/bin/python harness/run.py "$@"
