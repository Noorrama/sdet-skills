#!/usr/bin/env bash
# Bundle one run's evidence into a retained, tagged archive.
#
# Usage: archive-run.sh <run-dir> [charter-id] [--retain-days N] [--prune]
#   charter-id     tags the bundle so it can be found from the suite report (default: the run
#                  dir's own basename)
#   --retain-days  default 90, about one release cycle plus slack
#   --prune        also delete archives past their retention date
#
# WHY
# The source PRD asks for full log bundles retained at least one release cycle, tagged with the
# charter id and session timestamp, so that a "worked fine but felt slow" observation can be
# revisited when a related crash shows up later. Run dirs alone don't satisfy that: they're
# scattered under ~/tapmind-runs, named by slug, and nothing links them to the charter that
# produced them or says when they stop being worth keeping.
#
# The archive is a plain tar.gz plus a sidecar manifest, deliberately not a database. It has to
# still be readable by a person in three months with no tooling.
set -euo pipefail

RUN_DIR="${1:?usage: archive-run.sh <run-dir> [charter-id] [--retain-days N] [--prune]}"
shift
CHARTER_ID=""
RETAIN_DAYS=90
PRUNE="false"

while [ $# -gt 0 ]; do
  case "$1" in
    --retain-days) RETAIN_DAYS="${2:?--retain-days needs a number}"; shift 2 ;;
    --prune)       PRUNE="true"; shift ;;
    *)             CHARTER_ID="$1"; shift ;;
  esac
done

[ -d "$RUN_DIR" ] || { echo "no such run dir: $RUN_DIR" >&2; exit 1; }

ARCHIVE_DIR="${TAPMIND_ARCHIVE_DIR:-$HOME/tapmind-runs/_archive}"
mkdir -p "$ARCHIVE_DIR"

RUN_BASE="$(basename "$RUN_DIR")"
CHARTER_ID="${CHARTER_ID:-$RUN_BASE}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="${CHARTER_ID}-${TS}"

# Only evidence. Deliberately excludes report.html, which is a rendering of trace.json and is
# regenerable — archiving it doubles the bundle for nothing.
INCLUDE=()
for d in logs screens pagesource findings; do
  [ -d "$RUN_DIR/$d" ] && INCLUDE+=("$d")
done
for f in trace.json device-info.json run.log; do
  [ -f "$RUN_DIR/$f" ] && INCLUDE+=("$f")
done

if [ ${#INCLUDE[@]} -eq 0 ]; then
  echo "ERROR: $RUN_DIR holds no evidence to archive (no logs/screens/pagesource/findings, no trace.json)" >&2
  exit 1
fi

tar -czf "$ARCHIVE_DIR/$NAME.tar.gz" -C "$RUN_DIR" "${INCLUDE[@]}"

python3 - "$ARCHIVE_DIR/$NAME.json" "$RUN_DIR" "$CHARTER_ID" "$TS" "$RETAIN_DAYS" "$NAME.tar.gz" <<'PY'
import json, os, sys
from datetime import datetime, timedelta, timezone
out, run_dir, charter_id, ts, retain_days, bundle = sys.argv[1:7]

def read(name):
    p = os.path.join(run_dir, name)
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}

trace, dev = read("trace.json"), read("device-info.json")
run = trace.get("run") or {}
created = datetime.now(timezone.utc)

json.dump({
    "charterId": charter_id,
    "archivedAt": created.isoformat(),
    "retainUntil": (created + timedelta(days=int(retain_days))).isoformat(),
    "bundle": bundle,
    "sourceRunDir": run_dir,
    # Enough to decide whether this bundle is worth opening, without opening it.
    "goal": run.get("goal"),
    "verdict": run.get("verdict"),
    "focusArea": run.get("focusArea"),
    "executedBy": run.get("executedBy", "agent"),
    "deviceKind": run.get("deviceKind") or dev.get("deviceKind"),
    "platform": run.get("platform") or dev.get("platform"),
    "app": run.get("app") or dev.get("appPackage"),
    "sessionUrl": run.get("sessionUrl"),
    "findings": [
        {"id": f.get("id"), "type": f.get("type"), "severity": f.get("severity"),
         "title": f.get("title"), "diagnosis": f.get("diagnosis")}
        for f in (trace.get("findings") or [])
    ],
    "coverageGaps": run.get("coverageGaps") or [],
}, open(out, "w"), indent=2)
PY

SIZE="$(du -h "$ARCHIVE_DIR/$NAME.tar.gz" | cut -f1 | tr -d ' ')"
echo "$ARCHIVE_DIR/$NAME.tar.gz"
echo "archived $SIZE as $NAME (charter=$CHARTER_ID, retain ${RETAIN_DAYS}d)" >&2

if [ "$PRUNE" = "true" ]; then
  python3 - "$ARCHIVE_DIR" <<'PY'
import glob, json, os, sys
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
removed = 0
for m in glob.glob(os.path.join(sys.argv[1], "*.json")):
    try:
        meta = json.load(open(m, encoding="utf-8"))
        until = datetime.fromisoformat(meta["retainUntil"])
    except Exception:
        # An unreadable manifest is never grounds for deleting evidence.
        continue
    if until < now:
        bundle = os.path.join(sys.argv[1], meta.get("bundle", ""))
        if os.path.isfile(bundle):
            os.remove(bundle)
        os.remove(m)
        removed += 1
print(f"pruned {removed} expired archive(s)", file=sys.stderr)
PY
fi
