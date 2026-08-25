#!/usr/bin/env bash
# Work out which TapMind profile the ALREADY-RUNNING server is actually using, and print its path.
#
# Why this exists: new-run.sh reads $TAPMIND_CONFIG (or ~/.tapmind/profile.json) to learn
# `run_mode`. But the server itself resolves its config as
#     System.getProperty("config", System.getenv("DARKSEID"))     [SessionInitializer.java:220]
# i.e. the -Dconfig JVM flag first, DARKSEID env second. The `tapmind` CLI bridges the two by
# reading $TAPMIND_CONFIG and forwarding it as -Dconfig — but anyone launching the jar by hand
# sets -Dconfig directly and never sets TAPMIND_CONFIG. new-run.sh then finds no profile,
# defaults to run_mode=local, and a BrowserStack run silently loses every adb-dependent capture.
# That is a real production incident, not a hypothetical.
#
# The fix: the running JVM's -Dconfig is visible in its command line, so just read it. That is
# authoritative — whatever that process was started with IS the config every session will use,
# regardless of what any shell variable says.
#
# Usage:  eval "$(resolve-config.sh)"      # exports TAPMIND_CONFIG for new-run.sh
#     or: resolve-config.sh --path         # just print the resolved path
set -euo pipefail

PORT="${TAPMIND_SERVER_PORT:-7777}"
MODE="${1:-eval}"
note() { echo "$1" >&2; }

RESOLVED=""
SOURCE=""

# 1. The running server's -Dconfig — authoritative when the server is already up.
SRV_PID="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
if [ -n "$SRV_PID" ]; then
  FROM_PROC="$(ps -o args= -p "$SRV_PID" 2>/dev/null | tr ' ' '\n' | grep -m1 '^-Dconfig=' | cut -d= -f2- || true)"
  if [ -n "$FROM_PROC" ]; then RESOLVED="$FROM_PROC"; SOURCE="running server (pid $SRV_PID, -Dconfig)"; fi
fi

# 2..4 — only consulted when the server isn't up, or was started without -Dconfig.
if [ -z "$RESOLVED" ] && [ -n "${TAPMIND_CONFIG:-}" ]; then
  RESOLVED="$TAPMIND_CONFIG"; SOURCE="\$TAPMIND_CONFIG"
fi
if [ -z "$RESOLVED" ] && [ -n "${DARKSEID:-}" ]; then
  RESOLVED="$DARKSEID"; SOURCE="\$DARKSEID (the server's own env fallback)"
fi
if [ -z "$RESOLVED" ] && [ -f "$HOME/.tapmind/profile.json" ]; then
  RESOLVED="$HOME/.tapmind/profile.json"; SOURCE="~/.tapmind/profile.json (tapmind CLI default)"
fi

if [ -z "$RESOLVED" ]; then
  note "ERROR: cannot determine which TapMind profile is in use."
  note "  The server on port $PORT ${SRV_PID:+(pid $SRV_PID) }was not started with -Dconfig, and"
  note "  neither \$TAPMIND_CONFIG nor \$DARKSEID is set, and ~/.tapmind/profile.json doesn't exist."
  note "  Without it the run cannot know run_mode, and a remote run would be misread as local."
  note "  Fix: restart the server with -Dconfig=/path/to/profile.json, or export TAPMIND_CONFIG."
  exit 1
fi

if [ ! -f "$RESOLVED" ]; then
  note "ERROR: resolved config path does not exist: $RESOLVED  (from $SOURCE)"
  exit 1
fi

# Loud mismatch warning — this is the exact confusion this script exists to prevent.
if [ -n "${TAPMIND_CONFIG:-}" ] && [ "$TAPMIND_CONFIG" != "$RESOLVED" ]; then
  note "WARNING: \$TAPMIND_CONFIG points at"
  note "           $TAPMIND_CONFIG"
  note "         but the running server was started with"
  note "           $RESOLVED"
  note "         The SERVER wins — sessions use its config, not the shell's. Using the server's."
fi

RUN_MODE="$(python3 -c "
import json
try: print(json.load(open('$RESOLVED')).get('run_mode') or 'local')
except Exception: print('local')
")"

note "TapMind profile: $RESOLVED"
note "  source:   $SOURCE"
note "  run_mode: $RUN_MODE"

if [ "$MODE" = "--path" ]; then
  echo "$RESOLVED"
else
  # new-run.sh reads TAPMIND_CONFIG; hand it the path the server is really using.
  echo "export TAPMIND_CONFIG=$(printf '%q' "$RESOLVED")"
fi
