#!/usr/bin/env bash
# Is the app still alive, and if not, why? One call per new screen (SKILL.md §3a.4-5).
#
# Usage: health-check.sh <run-dir> <step> [hierarchy-text-file]
#   <step>              zero-padded step number, e.g. 07 — names the log file
#   hierarchy-text-file  optional: a file holding this screen's hierarchy text. Required for
#                        targets whose liveness/hang signal is the hierarchy itself (iOS device,
#                        BrowserStack); ignored elsewhere.
#
# Prints ONE line of JSON to stdout:
#   {"alive":true,"crashed":false,"hung":false,"diagnosis":"stacktrace","logPath":null,
#    "mechanism":"pidof","note":null}
#
# WHY THIS IS A SCRIPT AND NOT INSTRUCTIONS
# The crash and ANR checks used to be written in SKILL.md as literal adb commands. On any
# non-Android-local target those commands quietly did nothing, so a BrowserStack run could
# complete, report clean, and never once have checked whether the process was alive. Detection
# is the whole mandate of this skill; it cannot be a step the model is trusted to translate per
# platform. Ask this script.
#
# DETECTION vs DIAGNOSIS — the distinction the report depends on
# Detection ("the app died") needs only process liveness or the view hierarchy, so it works on
# every target. Diagnosis ("here is the stack trace") needs device logs, which some targets
# don't give us. `diagnosis` says which one you got, and it must be carried onto the finding:
#   stacktrace      → logPath has the trace; report it
#   detection-only  → we know it died, we cannot say why. Say exactly that in the finding
#                     rather than implying a cause nobody captured.
#
# ANR is an Android concept: a system "isn't responding" dialog. iOS has no such dialog — the
# watchdog kills the app (0x8badf00d) with no warning — so on iOS/BrowserStack a hang is
# detected from timing instead: the caller passes the same hierarchy twice across an
# interaction and this script reports `hung` when nothing moved. See `hangSignal` in
# device-info.json.
set -euo pipefail

RUN_DIR="${1:?usage: health-check.sh <run-dir> <step> [hierarchy-file]}"
STEP="${2:?usage: health-check.sh <run-dir> <step> [hierarchy-file]}"
HIER_FILE="${3:-}"

INFO="$RUN_DIR/device-info.json"
[ -f "$INFO" ] || { echo "missing $INFO — run new-run.sh first" >&2; exit 1; }

jget() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."): d = d.get(k) if isinstance(d, dict) else None
print(d if d is not None else "")' "$INFO" "$1"; }

SERIAL="$(jget serial)"
APP_ID="$(jget appPackage)"
DEVICE_KIND="$(jget deviceKind)"
LIVENESS="$(jget capabilities.liveness)"
DIAGNOSIS="$(jget capabilities.crashDiagnosis)"
LOGS="$(jget capabilities.deviceLogs)"
HANG_SIGNAL="$(jget capabilities.hangSignal)"

LOG_PATH=""
NOTE=""
ALIVE="true"
HUNG="false"

# Run a command with a hard time limit, discarding it if it overruns. Every log capture below
# goes through this. `adb logcat -d` against an unreachable device blocks indefinitely, and
# `idevicesyslog` is a stream that never ends on its own - either one would stall the whole
# exploration run at the moment it is trying to record a crash. macOS has no coreutils
# `timeout`, so this is done by hand rather than assuming gtimeout is installed.
run_bounded() {
  local secs="$1"; shift
  "$@" & local pid=$!
  local waited=0
  while kill -0 "$pid" 2>/dev/null; do
    [ "$waited" -ge "$secs" ] && { kill -9 "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; return 124; }
    sleep 1; waited=$((waited + 1))
  done
  wait "$pid" 2>/dev/null || true
  return 0
}

# Emit and exit. Keeps every return path identical in shape — a caller should never have to
# handle a partial or missing field.
emit() {
  python3 - "$ALIVE" "$HUNG" "$DIAGNOSIS" "$LOG_PATH" "$LIVENESS" "$NOTE" <<'PY'
import json, sys
alive, hung, diagnosis, log_path, mechanism, note = sys.argv[1:7]
alive_b = alive == "true"
print(json.dumps({
    "alive": alive_b,
    "crashed": not alive_b,
    "hung": hung == "true",
    # A live app has nothing to diagnose; only report the capability when it matters.
    "diagnosis": None if alive_b else diagnosis,
    "logPath": log_path or None,
    "mechanism": mechanism,
    "note": note or None,
}))
PY
  exit 0
}

if [ -z "$APP_ID" ]; then
  NOTE="no app id in device-info.json - liveness cannot be checked"
  emit
fi

# --- Liveness -----------------------------------------------------------------------------
case "$LIVENESS" in
  pidof)
    # Confirm the DEVICE answers before trusting an empty pid list. Without this guard a
    # detached cable or a dead adb server makes `pidof` return empty on every screen, and the
    # run fills up with high-severity crash findings that never happened. "I could not check"
    # and "the app is dead" are different answers and must never collapse into each other.
    if ! adb ${SERIAL:+-s "$SERIAL"} get-state 2>/dev/null | grep -q '^device$'; then
      NOTE="adb did not answer (device offline or adb server down) - liveness NOT checked"
    else
      PID="$(adb ${SERIAL:+-s "$SERIAL"} shell pidof "$APP_ID" 2>/dev/null | tr -d '\r\n' || true)"
      [ -z "$PID" ] && ALIVE="false"
    fi
    ;;
  simctl)
    # Same guard: a shut-down simulator must read as "couldn't check", not "app crashed".
    if ! xcrun simctl list devices booted 2>/dev/null | grep -q "$SERIAL"; then
      NOTE="simulator $SERIAL is not booted - liveness NOT checked"
    # `launchctl list` on the booted sim lists running services; the app appears under its
    # bundle id (as UIKitApplication:<bundle-id>...) only while its process is alive.
    elif ! xcrun simctl spawn "$SERIAL" launchctl list 2>/dev/null | grep -q -- "$APP_ID"; then
      ALIVE="false"
    fi
    ;;
  hierarchy)
    # No shell to the device. Infer from what's on screen: if the hierarchy shows the home
    # screen / launcher instead of our app, the app is gone. This is a weaker signal than a
    # pid — it can't tell "crashed" from "user navigated out" — so the caller must only pass a
    # hierarchy captured immediately after an in-app action.
    if [ -n "$HIER_FILE" ] && [ -f "$HIER_FILE" ]; then
      if grep -qiE 'SpringBoard|com\.apple\.springboard|launcher|Icon-Grid|workspace_home' "$HIER_FILE"; then
        ALIVE="false"
        NOTE="inferred from hierarchy (home screen visible), not from a process id"
      fi
    else
      NOTE="liveness=hierarchy but no hierarchy file passed - liveness NOT checked this step"
    fi
    ;;
  *)
    NOTE="unknown liveness mechanism '$LIVENESS' - liveness NOT checked"
    ;;
esac

# --- Crash diagnosis (only when it actually died) -------------------------------------------
if [ "$ALIVE" = "false" ]; then
  case "$LOGS" in
    logcat)
      LOG_PATH="$RUN_DIR/logs/step-$STEP.log"
      capture_logcat() { adb ${SERIAL:+-s "$SERIAL"} logcat -b crash -d >"$LOG_PATH" 2>/dev/null; }
      run_bounded 15 capture_logcat || NOTE="logcat capture timed out - crash detected but not diagnosed"
      ;;
    simctl)
      LOG_PATH="$RUN_DIR/logs/step-$STEP.log"
      # Most recent crash report for this app from the simulator's diagnostic reports.
      CRASH_DIR="$HOME/Library/Logs/DiagnosticReports"
      SHORT="${APP_ID##*.}"
      LATEST="$(ls -t "$CRASH_DIR"/*.ips 2>/dev/null | head -n1 || true)"
      if [ -n "$LATEST" ] && grep -qi -e "$APP_ID" -e "$SHORT" "$LATEST" 2>/dev/null; then
        cp "$LATEST" "$LOG_PATH"
      else
        # The report can lag the process death by a second or two; a miss is not a failure.
        capture_simlog() {
          xcrun simctl spawn "$SERIAL" log show --last 2m --predicate "process CONTAINS \"$SHORT\"" \
            >"$LOG_PATH" 2>/dev/null
        }
        run_bounded 20 capture_simlog || true
        NOTE="no .ips crash report matched $APP_ID; captured recent process log instead"
      fi
      ;;
    idevicesyslog)
      LOG_PATH="$RUN_DIR/logs/step-$STEP.log"
      # syslog is a stream, not a buffer - it never ends on its own, so it MUST be bounded.
      capture_syslog() { idevicesyslog -u "$SERIAL" >"$LOG_PATH" 2>/dev/null; }
      run_bounded 8 capture_syslog || true
      ;;
    session)
      # BrowserStack keeps device logs and video on the session itself. Nothing to fetch from
      # here; the report links the session instead.
      NOTE="crash detected - device logs live on the BrowserStack session, link it in trace.run.sessionUrl"
      ;;
    none|"")
      NOTE="crash detected but no log mechanism on this target - cause not captured"
      ;;
  esac
fi

# --- Hang / ANR ------------------------------------------------------------------------------
# Only meaningful while the app is still alive; a dead process is a crash, not a hang.
if [ "$ALIVE" = "true" ] && [ -n "$HIER_FILE" ] && [ -f "$HIER_FILE" ]; then
  case "$HANG_SIGNAL" in
    anr-dialog)
      if grep -qiE "isn't responding|is not responding|Close app|Wait" "$HIER_FILE"; then
        HUNG="true"
        LOG_PATH="$RUN_DIR/logs/step-$STEP.log"
        capture_anr() {
          adb ${SERIAL:+-s "$SERIAL"} logcat -d 2>/dev/null \
            | grep -E "ANR in|Input dispatching timed out" >"$LOG_PATH" 2>/dev/null || true
        }
        run_bounded 15 capture_anr || NOTE="ANR detected but logcat capture timed out"
      fi
      ;;
    timing)
      # No system dialog to look for. The caller decides "nothing moved across an interaction"
      # (SKILL.md §3a.5) and signals it by passing a hierarchy file named *.unresponsive.
      case "$HIER_FILE" in
        *.unresponsive)
          HUNG="true"
          NOTE="hang inferred from an unresponsive interaction, not a system dialog - iOS/remote targets give no ANR dialog"
          ;;
      esac
      ;;
  esac
fi

emit
