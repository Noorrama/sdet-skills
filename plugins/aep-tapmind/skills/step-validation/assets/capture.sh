#!/usr/bin/env bash
# Capture one screen state into a run dir. Works on BOTH local-adb and remote/BrowserStack runs.
#
# Screenshots always go through TapMind's own HTTP endpoint
#   GET /tapmind/screenshot/{conversationId}  ->  {"metadata":{"screenshot":"<base64 png>"}}
# which is backed by driver.getScreenshotAs(BASE64) — the Appium driver, so it works wherever the
# session lives. The base64 is decoded straight to disk by python here; it never passes through
# the model's context, so this costs zero tokens (unlike the appium_get_screenshot MCP tool,
# which returns the image into the conversation and deletes its temp file server-side).
#
# Page source (uiautomator XML, the only source of element `bounds` and therefore the only input
# lint.py can use) requires adb and is captured only when adb can actually reach a device.
#
# Usage: capture.sh <run-dir> <seq> <before|after> <conversationId>
# Prints one line per artifact captured, and a WARN line for anything unavailable in this mode.
set -euo pipefail

RUN_DIR="${1:?usage: capture.sh <run-dir> <seq> <before|after> <conversationId>}"
SEQ="${2:?missing seq}"
PHASE="${3:?missing phase (before|after)}"
CONV="${4:?missing conversationId}"
PORT="${TAPMIND_SERVER_PORT:-7777}"
NN="$(printf '%02d' "$SEQ")"

case "$PHASE" in before|after) ;; *) echo "phase must be 'before' or 'after', got: $PHASE" >&2; exit 2 ;; esac
[ -d "$RUN_DIR" ] || { echo "no such run dir: $RUN_DIR" >&2; exit 2; }
mkdir -p "$RUN_DIR/screens" "$RUN_DIR/pagesource"

RUN_MODE="$(python3 -c "
import json,sys
try: print(json.load(open('$RUN_DIR/device-info.json')).get('runMode') or 'local')
except Exception: print('local')
")"

# ---------- screenshot: same path in every run mode ----------
SHOT="$RUN_DIR/screens/step-${NN}-${PHASE}.png"
HTTP="http://localhost:$PORT/tapmind/screenshot/$CONV"
BODY="$(mktemp)"; trap 'rm -f "$BODY"' EXIT

if curl -sS -m 30 -o "$BODY" "$HTTP"; then
  if python3 - "$BODY" "$SHOT" <<'PY'
import base64, json, sys
body, out = sys.argv[1:3]
try:
    d = json.load(open(body, encoding="utf-8"))
except Exception as e:
    print(f"screenshot endpoint returned non-JSON: {e}", file=sys.stderr); raise SystemExit(1)
b64 = (d.get("metadata") or {}).get("screenshot")
if not b64:
    print(f'no metadata.screenshot in response: {d.get("message") or d.get("error") or d}',
          file=sys.stderr)
    raise SystemExit(1)
raw = base64.b64decode(b64)
if not raw.startswith(b"\x89PNG"):
    print("decoded payload is not a PNG", file=sys.stderr); raise SystemExit(1)
open(out, "wb").write(raw)
# stdout is the artifact list the caller parses — keep diagnostics on stderr only
print(f"{len(raw)} bytes", file=sys.stderr)
PY
  then
    echo "screens/step-${NN}-${PHASE}.png"
  else
    echo "WARN screenshot FAILED for seq $SEQ ($PHASE) — see the error above. Do NOT write a" >&2
    echo "WARN screenshot path into trace.json for this step; leave it null and say so." >&2
  fi
else
  echo "WARN screenshot endpoint unreachable at $HTTP — is the session still alive?" >&2
fi

# ---------- page source: adb only, and only worth taking once per step ----------
if [ "$PHASE" = "before" ]; then
  XML="$RUN_DIR/pagesource/step-${NN}.xml"
  if [ "$RUN_MODE" = "local" ] && command -v adb >/dev/null 2>&1 \
     && [ "$(adb devices | tail -n +2 | grep -c 'device$' || true)" -eq 1 ]; then
    if adb shell uiautomator dump /sdcard/window_dump.xml >/dev/null 2>&1 \
       && adb pull /sdcard/window_dump.xml "$XML" >/dev/null 2>&1; then
      echo "pagesource/step-${NN}.xml"
    else
      echo "WARN uiautomator dump failed for seq $SEQ — lint.py has no input for this screen." >&2
    fi
  else
    # Not an error, and not something to work around: no HTTP endpoint exposes raw
    # driver.getPageSource(), and get_view_hierarchy's JSON has `bounds` stripped server-side,
    # so there is no bounds-bearing page source on a remote run. lint.py cannot run. Say this
    # in the report rather than quietly producing zero findings.
    echo "SKIP pagesource — runMode=$RUN_MODE, no adb. lint.py cannot run on this screen." >&2
  fi
fi
