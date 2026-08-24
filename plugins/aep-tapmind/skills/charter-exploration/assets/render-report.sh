#!/usr/bin/env bash
# Aggregate the suite and inline report.json into report-template.html -> <run-dir>/report.html.
#
# Safe and cheap to run after EVERY charter — that is the intended cadence. The report is the
# same document at every point; it just fills in. Nobody should have to wait for charter 10 to
# see charter 1.
#
# Usage: render-report.sh <run-dir>
set -euo pipefail

RUN_DIR="${1:?usage: render-report.sh <run-dir>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/report-template.html"

[ -f "$TEMPLATE" ] || { echo "missing template: $TEMPLATE" >&2; exit 1; }
[ -f "$RUN_DIR/charters.json" ] || { echo "missing $RUN_DIR/charters.json" >&2; exit 1; }

python3 "$SCRIPT_DIR/aggregate.py" "$RUN_DIR" >/dev/null

python3 - "$TEMPLATE" "$RUN_DIR/report.json" "$RUN_DIR/report.html" <<'PY'
import json, re, sys

template_path, report_path, out_path = sys.argv[1:4]
template = open(template_path, encoding="utf-8").read()
report_text = open(report_path, encoding="utf-8").read()
report = json.loads(report_text)  # fail loudly before inlining garbage

run = report.get("run", {})
label = run.get("scopeLabel") or run.get("project") or "run"
state = "" if run.get("complete") else " (in progress)"
title = f"TapMind Charter Exploration — {label}{state}"

out = re.sub(
    r'<script type="application/json" id="report">.*?</script>',
    lambda _: f'<script type="application/json" id="report">\n{report_text}\n</script>',
    template, count=1, flags=re.S,
)
if '<script type="application/json" id="report">\n{' not in out:
    sys.exit("ERROR: could not find the report JSON placeholder in the template")
out = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", out, count=1, flags=re.S)

open(out_path, "w", encoding="utf-8").write(out)
print(out_path)
PY
