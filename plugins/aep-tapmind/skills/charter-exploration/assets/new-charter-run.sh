#!/usr/bin/env bash
# Scaffold one charter-exploration run directory. Prints the run dir path to stdout.
#
# Deliberately lighter than goal-driven-exploration's new-run.sh: this skill touches NO device
# during scope/synthesis/gate, so there is nothing to health-check or gate on here. Each charter's
# execution sub-run calls goal-driven-exploration, whose own new-run.sh does the server health
# check and the adb device gate at the point where they actually matter. Duplicating those checks
# up front would only mean failing a run before the user has even seen the charters.
#
# Usage: new-charter-run.sh <slug>
set -euo pipefail

SLUG="${1:?usage: new-charter-run.sh <slug>}"
BASE_DIR="${TAPMIND_RUNS_DIR:-$HOME/tapmind-runs}"
TS="$(date +%Y%m%d-%H%M)"
RUN_DIR="$BASE_DIR/${TS}-charter-${SLUG}"

mkdir -p "$RUN_DIR/runs"
: > "$RUN_DIR/run.log"

echo "== TapMind charter run: $RUN_DIR ==" | tee -a "$RUN_DIR/run.log" >&2
echo "$RUN_DIR"
