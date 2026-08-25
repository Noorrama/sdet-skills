#!/usr/bin/env bash
# Preflight + scaffold one run directory. Prints the run dir path to stdout on success.
# Reads the active TapMind profile ONCE for run_mode / platform / app id — this is the single
# authoritative source; nothing downstream should re-derive these from adb probing or
# guesswork. Writes device-info.json (runMode, platform, and a `capabilities` block) for the
# skill to read back instead of re-deriving any of this by hand.
#
# `capabilities` is the important part: it is resolved HERE, once, and it is what the
# exploration loop, health-check.sh and the focus-area library branch on. Before it existed,
# every adb-dependent step (screenshots, page source, lint, crash and ANR checks) was written
# as "run this adb command", which silently did nothing on a BrowserStack or iOS run — a
# BrowserStack run would complete and report clean having never once checked whether the app
# was still alive. Ask this file what's available; never infer it from a failed command.
#
# Usage: new-run.sh <slug> [app-id]
#   app-id overrides the profile's mobile_capabilities.android_only.appPackage (Android) or
#   mobile_capabilities.ios_only.bundleId (iOS); omit it in the common case.
set -euo pipefail

SLUG="${1:?usage: new-run.sh <slug> [app-id]}"
APP_PACKAGE_ARG="${2:-}"
BASE_DIR="${TAPMIND_RUNS_DIR:-$HOME/tapmind-runs}"
TAPMIND_PORT="${TAPMIND_SERVER_PORT:-7777}"
PROFILE_PATH="${TAPMIND_CONFIG:-$HOME/.tapmind/profile.json}"
HEALTH_URL="http://localhost:$TAPMIND_PORT/actuator/health"
TS="$(date +%Y%m%d-%H%M)"
RUN_DIR="$BASE_DIR/${TS}-${SLUG}"

mkdir -p "$RUN_DIR"/screens "$RUN_DIR"/pagesource "$RUN_DIR"/findings "$RUN_DIR"/logs
: > "$RUN_DIR/run.log"

log() { echo "$1" | tee -a "$RUN_DIR/run.log" >&2; }

log "== TapMind run: $RUN_DIR =="

# --- Read the active profile ONCE. This is the ground truth for run_mode and app package —
# nothing later in this script or in SKILL.md should re-derive either from adb probing.
read_profile() {
  python3 - "$PROFILE_PATH" "$1" <<'PY'
import json, sys
path, key = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(path))
except (FileNotFoundError, json.JSONDecodeError):
    print("")
    raise SystemExit
cur = d
for part in key.split("."):
    cur = cur.get(part) if isinstance(cur, dict) else None
print(cur if cur is not None else "")
PY
}

if [ -f "$PROFILE_PATH" ]; then
  RUN_MODE="$(read_profile run_mode)"
  PLATFORM_RAW="$(read_profile mobile_capabilities.appium_standard.platformName)"
  PROFILE_APP_PACKAGE="$(read_profile mobile_capabilities.android_only.appPackage)"
  PROFILE_BUNDLE_ID="$(read_profile mobile_capabilities.ios_only.bundleId)"
else
  log "WARNING: no profile at $PROFILE_PATH — assuming run_mode=local, platform=android, no app id known from config"
  RUN_MODE=""
  PLATFORM_RAW=""
  PROFILE_APP_PACKAGE=""
  PROFILE_BUNDLE_ID=""
fi
RUN_MODE="${RUN_MODE:-local}"

# platformName is spelled inconsistently across real profiles in the wild — the template says
# "android", the darkseid iOS profile says "iOS". Lowercase it once here so nothing downstream
# has to care.
PLATFORM="$(printf '%s' "$PLATFORM_RAW" | tr '[:upper:]' '[:lower:]')"
case "$PLATFORM" in
  ios|iphoneos) PLATFORM="ios" ;;
  android)      PLATFORM="android" ;;
  "")           PLATFORM="android"
                log "WARNING: profile has no mobile_capabilities.appium_standard.platformName — assuming android" ;;
  *)            log "ERROR: unrecognised platformName '$PLATFORM_RAW' in $PROFILE_PATH (expected android or iOS)"
                exit 1 ;;
esac

# The app identifier is platform-specific: appPackage on Android, bundleId on iOS. Downstream
# consumers read one field (`appPackage` in device-info.json) whichever platform this is.
if [ "$PLATFORM" = "ios" ]; then
  PROFILE_APP_ID="$PROFILE_BUNDLE_ID"
else
  PROFILE_APP_ID="$PROFILE_APP_PACKAGE"
fi
APP_PACKAGE="${APP_PACKAGE_ARG:-$PROFILE_APP_ID}"

log "run_mode=$RUN_MODE platform=$PLATFORM (from $PROFILE_PATH)"

# --- Health-check the server via its actual endpoint, not `tapmind status`'s exit code
# (cmd_status in the tapmind CLI always exits 0, even when the server is down — it prints
# DOWN in red but never fails the command. Curling the real health URL is the only check
# that's actually meaningful here.)
server_up() { curl -fsS -m 3 "$HEALTH_URL" >/dev/null 2>&1; }

if server_up; then
  log "TapMind server already up at $HEALTH_URL"
elif command -v tapmind >/dev/null 2>&1; then
  log "TapMind server not responding — starting it (tapmind start is idempotent)"
  tapmind start
  server_up || { log "ERROR: server still not responding at $HEALTH_URL after 'tapmind start'"; exit 1; }
else
  log "ERROR: server not responding at $HEALTH_URL and 'tapmind' CLI isn't on PATH — start it yourself, then retry"
  exit 1
fi

# --- Device info. The local device gate only applies when this run is actually local; a
# BrowserStack run has no local device to require or query. Within a local run the gate is
# platform-specific: adb for Android, simctl/libimobiledevice for iOS.
SERIAL=""
MODEL=""
OS_VERSION=""
IS_EMULATOR="false"
AVD_NAME=""
APP_VERSION_NAME=""
APP_VERSION_CODE=""
# One of: android-device, android-emulator, ios-simulator, ios-device, browserstack.
# This is what the capabilities block below is computed from.
DEVICE_KIND="browserstack"

if [ "$RUN_MODE" = "local" ] && [ "$PLATFORM" = "ios" ]; then
  # Booted simulator first — it's the common local-iOS case and the only one where crash
  # diagnosis is reliably available without extra tooling.
  # Parse simctl's JSON via a temp file and a *quoted* heredoc, then source the result.
  # Not `eval "$(python3 - <<PY ...)"` — nesting a heredoc inside a command substitution
  # inside an eval mis-parses on the parentheses in the Python, and it fails at the point
  # this script is meant to be the thing you can trust.
  xcrun simctl list devices booted -j >"$RUN_DIR/.booted.json" 2>/dev/null || echo '{}' >"$RUN_DIR/.booted.json"
  python3 - "$RUN_DIR/.booted.json" "$RUN_DIR/.sim.env" <<'PY'
import json, shlex, sys
src, out = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(src))
except Exception:
    d = {}
booted = [(rt, dev) for rt, devs in (d.get("devices") or {}).items() for dev in devs]
lines = [f"SIM_COUNT={len(booted)}"]
if len(booted) == 1:
    rt, dev = booted[0]
    # com.apple.CoreSimulator.SimRuntime.iOS-17-4 -> 17.4
    ver = rt.rsplit(".", 1)[-1].replace("iOS-", "").replace("-", ".")
    lines += [f"SIM_UDID={shlex.quote(dev.get('udid', ''))}",
              f"SIM_NAME={shlex.quote(dev.get('name', ''))}",
              f"SIM_OS={shlex.quote(ver)}"]
open(out, "w").write("\n".join(lines) + "\n")
PY
  # shellcheck source=/dev/null
  . "$RUN_DIR/.sim.env"
  rm -f "$RUN_DIR/.booted.json" "$RUN_DIR/.sim.env"
  SIM_COUNT="${SIM_COUNT:-0}"

  if [ "$SIM_COUNT" -gt 1 ]; then
    log "ERROR: multiple booted iOS simulators — shut down all but one before continuing:"
    xcrun simctl list devices booted >&2
    exit 1
  elif [ "$SIM_COUNT" -eq 1 ]; then
    DEVICE_KIND="ios-simulator"
    IS_EMULATOR="true"
    SERIAL="${SIM_UDID:-}"
    MODEL="${SIM_NAME:-}"
    OS_VERSION="${SIM_OS:-}"
    AVD_NAME="${SIM_NAME:-}"
  elif command -v idevice_id >/dev/null 2>&1; then
    # No simulator booted — fall back to a physical device via libimobiledevice.
    UDIDS="$(idevice_id -l 2>/dev/null || true)"
    UDID_COUNT="$(printf '%s\n' "$UDIDS" | grep -c . || true)"
    if [ "$UDID_COUNT" -eq 0 ]; then
      log "ERROR: run_mode=local platform=ios but no booted simulator and no physical iOS device"
      exit 1
    elif [ "$UDID_COUNT" -gt 1 ]; then
      log "ERROR: multiple physical iOS devices attached — disconnect all but one:"
      printf '%s\n' "$UDIDS" >&2
      exit 1
    fi
    DEVICE_KIND="ios-device"
    SERIAL="$(printf '%s\n' "$UDIDS" | head -n1)"
    MODEL="$(ideviceinfo -u "$SERIAL" -k DeviceName 2>/dev/null | tr -d '\r\n' || true)"
    OS_VERSION="$(ideviceinfo -u "$SERIAL" -k ProductVersion 2>/dev/null | tr -d '\r\n' || true)"
  else
    log "ERROR: run_mode=local platform=ios but no booted simulator, and libimobiledevice"
    log "       (idevice_id) isn't on PATH to look for a physical device. Boot a simulator, or"
    log "       'brew install libimobiledevice' to use a real device."
    exit 1
  fi

  # App version from the installed bundle's Info.plist. Simulator only — on a physical device
  # the container isn't readable without more tooling, and a missing version is not fatal.
  if [ -n "$APP_PACKAGE" ] && [ "$DEVICE_KIND" = "ios-simulator" ]; then
    APP_CONTAINER="$(xcrun simctl get_app_container "$SERIAL" "$APP_PACKAGE" app 2>/dev/null || true)"
    if [ -n "$APP_CONTAINER" ] && [ -f "$APP_CONTAINER/Info.plist" ]; then
      APP_VERSION_NAME="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP_CONTAINER/Info.plist" 2>/dev/null | tr -d '\r\n' || true)"
      APP_VERSION_CODE="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP_CONTAINER/Info.plist" 2>/dev/null | tr -d '\r\n' || true)"
    else
      log "WARNING: could not locate an installed container for $APP_PACKAGE on $SERIAL — is it installed?"
    fi
  fi

elif [ "$RUN_MODE" = "local" ]; then
  DEVICE_COUNT="$(adb devices | tail -n +2 | grep -c "device$" || true)"
  if [ "$DEVICE_COUNT" -eq 0 ]; then
    log "ERROR: run_mode=local but no adb device attached"
    exit 1
  elif [ "$DEVICE_COUNT" -gt 1 ]; then
    log "ERROR: multiple adb devices attached — pick one before continuing:"
    adb devices | tail -n +2 | grep "device$" | tee -a "$RUN_DIR/run.log" >&2
    exit 1
  fi

  SERIAL="$(adb devices | tail -n +2 | grep "device$" | cut -f1)"
  MODEL="$(adb -s "$SERIAL" shell getprop ro.product.model 2>/dev/null | tr -d '\r\n' || true)"
  OS_VERSION="$(adb -s "$SERIAL" shell getprop ro.build.version.release 2>/dev/null | tr -d '\r\n' || true)"
  DEVICE_KIND="android-device"
  if [ "$(adb -s "$SERIAL" shell getprop ro.kernel.qemu 2>/dev/null | tr -d '\r\n')" = "1" ] \
     || [[ "$SERIAL" == emulator-* ]]; then
    IS_EMULATOR="true"
    DEVICE_KIND="android-emulator"
    AVD_NAME="$(adb -s "$SERIAL" emu avd name 2>/dev/null | head -n1 | tr -d '\r\n' || true)"
  fi

  if [ -n "$APP_PACKAGE" ]; then
    DUMP="$(adb -s "$SERIAL" shell dumpsys package "$APP_PACKAGE" 2>/dev/null || true)"
    # `|| true` on each: with pipefail, grep finding no match (app not installed on this
    # device) exits 1, and that failure would otherwise silently kill this whole script
    # under `set -e` — even inside a `VAR=$(...)` assignment. This is not a hypothetical:
    # it's exactly what happens when the target app isn't installed on the connected device.
    APP_VERSION_NAME="$( (echo "$DUMP" | grep -m1 versionName= | sed -E 's/.*versionName=([^ ]+).*/\1/' | tr -d '\r') || true)"
    APP_VERSION_CODE="$( (echo "$DUMP" | grep -m1 versionCode= | sed -E 's/.*versionCode=([0-9]+).*/\1/' | tr -d '\r') || true)"
    [ -z "$APP_VERSION_NAME" ] && log "WARNING: could not read versionName for $APP_PACKAGE via dumpsys — is it installed on $SERIAL?"
  else
    log "WARNING: no app package from profile or CLI arg — skipping app version detection"
  fi
else
  log "run_mode=$RUN_MODE — skipping the local adb device gate and adb-based version lookup."
  log "Get the real device/app version from the live Appium session's capabilities once it starts, not from this profile's devices[] list (that's a menu of BrowserStack options, not a confirmed assignment)."
fi

HAS_IDEVICESYSLOG="false"
command -v idevicesyslog >/dev/null 2>&1 && HAS_IDEVICESYSLOG="true"

python3 - "$RUN_DIR/device-info.json" "$RUN_MODE" "$PLATFORM" "$DEVICE_KIND" "$SERIAL" "$MODEL" \
         "$OS_VERSION" "$IS_EMULATOR" "$AVD_NAME" "$APP_PACKAGE" "$APP_VERSION_NAME" \
         "$APP_VERSION_CODE" "$HAS_IDEVICESYSLOG" <<'PY'
import json, sys
(out, run_mode, platform, device_kind, serial, model, os_version, is_emulator, avd_name,
 app_package, version_name, version_code, has_idevicesyslog) = sys.argv[1:14]

# --- The capabilities contract.
#
# Resolved once, here, from device_kind. Everything downstream (the exploration loop,
# health-check.sh, the focus-area library) READS this and never re-derives it by trying a
# command and seeing whether it fails. Each value names the MECHANISM, not just yes/no, so a
# consumer knows which command to reach for without re-testing the platform.
#
# The honest part is `crashDiagnosis`. Detection ("the app died") is available everywhere,
# because it only needs process liveness or the view hierarchy. Diagnosis ("here is the stack
# trace") is not. A run that can detect but not diagnose must say so in its findings rather
# than quietly reporting a crash with no cause — see design-notes.md.
CAPS = {
    "android-emulator": {
        "screenshots": "adb", "pageSource": "uiautomator", "deviceLogs": "logcat",
        "liveness": "pidof", "crashDiagnosis": "stacktrace", "hangSignal": "anr-dialog",
        "networkToggle": "adb", "rotation": "adb", "locale": "adb", "phoneCall": "adb-emu",
        "permissionControl": "mcp",
    },
    "android-device": {
        "screenshots": "adb", "pageSource": "uiautomator", "deviceLogs": "logcat",
        "liveness": "pidof", "crashDiagnosis": "stacktrace", "hangSignal": "anr-dialog",
        "networkToggle": "adb", "rotation": "adb", "locale": "adb", "phoneCall": "none",
        "permissionControl": "mcp",
    },
    "ios-simulator": {
        # No uiautomator equivalent, so lint.py has no bounds-bearing XML to read and every
        # deterministic UI check is unavailable. That is a real coverage gap on iOS, not an
        # oversight — findings there come from the hierarchy and from vision review instead.
        "screenshots": "simctl", "pageSource": "none", "deviceLogs": "simctl",
        "liveness": "simctl", "crashDiagnosis": "stacktrace", "hangSignal": "timing",
        "networkToggle": "none", "rotation": "none", "locale": "none", "phoneCall": "none",
        "permissionControl": "none",
    },
    "ios-device": {
        "screenshots": "none", "pageSource": "none",
        "deviceLogs": "idevicesyslog" if has_idevicesyslog == "true" else "none",
        "liveness": "hierarchy",
        "crashDiagnosis": "stacktrace" if has_idevicesyslog == "true" else "detection-only",
        "hangSignal": "timing",
        "networkToggle": "none", "rotation": "none", "locale": "none", "phoneCall": "none",
        "permissionControl": "none",
    },
    # BrowserStack is the one kind where the PLATFORM still matters. There's no local shell
    # either way, but a remote Android device still shows the system "isn't responding" dialog
    # in its hierarchy, and `appium_update_app_permission` still works there (it's an Appium
    # call, and the tool is Android-only by platform, not by locality). Collapsing both
    # platforms into one row would throw away real ANR detection on remote Android.
    "browserstack": {
        # Screenshots cost context (base64 through the MCP) so they're for key screens only;
        # logs and video live on the BrowserStack session and are linked, not fetched.
        "screenshots": "appium", "pageSource": "none", "deviceLogs": "session",
        "liveness": "hierarchy", "crashDiagnosis": "detection-only",
        "hangSignal": "anr-dialog" if platform == "android" else "timing",
        "networkToggle": "none", "rotation": "none", "locale": "none", "phoneCall": "none",
        "permissionControl": "mcp" if platform == "android" else "none",
    },
}

json.dump({
    "runMode": run_mode,
    "platform": platform,
    "deviceKind": device_kind,
    "serial": serial or None,
    "model": model or None,
    "osVersion": os_version or None,
    "isEmulator": is_emulator == "true",
    "avdName": avd_name or None,
    "appPackage": app_package or None,
    "appVersionName": version_name or None,
    "appVersionCode": version_code or None,
    "capabilities": CAPS[device_kind],
}, open(out, "w"), indent=2)
PY

if [ "$RUN_MODE" = "local" ]; then
  OS_LABEL="Android"; [ "$PLATFORM" = "ios" ] && OS_LABEL="iOS"
  log "Device: ${AVD_NAME:-$MODEL} · ${OS_LABEL} ${OS_VERSION} (id=$SERIAL, kind=$DEVICE_KIND)"
fi
[ -n "$APP_PACKAGE" ] && log "App: $APP_PACKAGE ${APP_VERSION_NAME:+$APP_VERSION_NAME }${APP_VERSION_CODE:+(build $APP_VERSION_CODE)}"

# Say out loud what this run can and cannot check. A run that can't diagnose a crash, or can't
# run lint at all, should be visible at preflight — not discovered when the report comes back
# thin and nobody can tell whether the app was clean or the checks never ran.
CAP_CRASH="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["capabilities"]["crashDiagnosis"])' "$RUN_DIR/device-info.json")"
CAP_PAGESRC="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["capabilities"]["pageSource"])' "$RUN_DIR/device-info.json")"
log "Capabilities: deviceKind=$DEVICE_KIND crashDiagnosis=$CAP_CRASH pageSource=$CAP_PAGESRC"
[ "$CAP_CRASH" = "detection-only" ] && \
  log "NOTE: crashes will be DETECTED but not diagnosed on this target — findings get diagnosis:\"detection-only\", no stack trace."
[ "$CAP_PAGESRC" = "none" ] && \
  log "NOTE: no bounds-bearing page source on this target — lint.py cannot run; UI findings come from the hierarchy and vision review only."

echo "$RUN_DIR"
