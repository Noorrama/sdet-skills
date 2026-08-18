#!/usr/bin/env bash
# Inline <run-dir>/trace.json into report-template.html -> <run-dir>/report.html.
# Usage: render-report.sh <run-dir>
set -euo pipefail

RUN_DIR="${1:?usage: render-report.sh <run-dir>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/report-template.html"
TRACE="$RUN_DIR/trace.json"
OUT="$RUN_DIR/report.html"

[ -f "$TEMPLATE" ] || { echo "missing template: $TEMPLATE" >&2; exit 1; }
[ -f "$TRACE" ] || { echo "missing trace: $TRACE" >&2; exit 1; }

python3 - "$TEMPLATE" "$TRACE" "$OUT" "$RUN_DIR" <<'PY'
import json, os, re, sys

template_path, trace_path, out_path, run_dir = sys.argv[1:5]
template = open(template_path, encoding="utf-8").read()
trace_text = open(trace_path, encoding="utf-8").read()
trace = json.loads(trace_text)  # fail loudly if the trace isn't valid JSON, before inlining it

# Safety net: warn (don't fail) when screens/ has captured PNGs that no node references —
# that mismatch is exactly what makes a report fall back to placeholder art despite screenshots
# existing on disk. This is a symptom of trace.json's writer, not of this script or the template.
screens_dir = os.path.join(run_dir, "screens")
if os.path.isdir(screens_dir):
    captured = {f for f in os.listdir(screens_dir) if f.endswith(".png")}
    referenced = {os.path.basename(n.get("screenshot", "")) for n in trace.get("nodes", []) if n.get("screenshot")}
    missing = sorted(captured - referenced)
    nodes_without_shot = [n["id"] for n in trace.get("nodes", []) if not n.get("screenshot")]
    if missing:
        print(f"WARNING: {len(missing)} screenshot(s) on disk are not referenced by any node "
              f"in trace.json (e.g. {missing[:3]}) — the report will show placeholder art for "
              f"them. Fix the trace writer, not this script.", file=sys.stderr)
    if nodes_without_shot:
        print(f"WARNING: {len(nodes_without_shot)} node(s) have no screenshot field at all: "
              f"{nodes_without_shot}", file=sys.stderr)

# What this target was ever able to do. Resolved once by new-run.sh; the warnings below are
# gated on it so they flag real omissions instead of crying wolf about checks that structurally
# cannot run on iOS or BrowserStack.
caps = (trace.get("run", {}) or {}).get("capabilities") or {}
device_kind = (trace.get("run", {}) or {}).get("deviceKind")

# Safety net #2: catch an abbreviated loop — a run with several steps but an empty pagesource/
# or findings/ dir means uiautomator dumps and lint.py were skipped for the whole run (a real
# incident: the model incorrectly assumed adb wasn't available and silently dropped every
# adb-dependent step for the rest of the run).
n_edges = len(trace.get("edges", []))
findings_dir_empty = not os.listdir(os.path.join(run_dir, "findings")) if os.path.isdir(os.path.join(run_dir, "findings")) else True
# Only meaningful where a bounds-bearing dump exists at all. Where pageSource is "none" the
# empty dirs are expected, and safety net #4 covers the reporting risk instead.
if caps.get("pageSource", "uiautomator") == "uiautomator":
    for sub, label in (("pagesource", "page-source dumps"), ("findings", "lint.py output files")):
        d = os.path.join(run_dir, sub)
        count = len(os.listdir(d)) if os.path.isdir(d) else 0
        if n_edges >= 3 and count == 0:
            print(f"WARNING: {sub}/ is empty despite {n_edges} steps — {label} were likely skipped "
                  f"for this entire run.", file=sys.stderr)

if findings_dir_empty:
    lint_findings = [f["id"] for f in trace.get("findings", []) if f.get("source") == "lint"]
    if lint_findings:
        print(f"WARNING: {len(lint_findings)} finding(s) tagged source:\"lint\" ({lint_findings}) "
              f"despite findings/ being empty — lint.py can't have produced these; they're "
              f"almost certainly model-reasoning findings mislabeled as script output.",
              file=sys.stderr)

# Safety net #4: a run that never checked whether the app was alive, or that quietly lost its
# only defect source, must not render as a clean run. This is the reporting half of the fix that
# put `capabilities` in device-info.json — before it, a BrowserStack run would complete, find
# nothing, and be indistinguishable from a run that genuinely found nothing.
if caps:
    if not caps.get("liveness"):
        print("WARNING: run.capabilities has no liveness mechanism — crash detection did not run "
              "for this session. The report cannot claim the app stayed up.", file=sys.stderr)
    if caps.get("crashDiagnosis") == "detection-only":
        undiagnosed = [f["id"] for f in trace.get("findings", [])
                       if f.get("type") in ("crash", "anr", "hang")
                       and f.get("diagnosis") != "detection-only"]
        if undiagnosed:
            print(f"WARNING: {len(undiagnosed)} crash/hang finding(s) ({undiagnosed}) are missing "
                  f"diagnosis:\"detection-only\" on a {device_kind} target, which cannot produce a "
                  f"stack trace. Either the diagnosis was copied wrong or a cause was inferred "
                  f"that nobody captured.", file=sys.stderr)
    if caps.get("pageSource") == "none" and not (trace.get("run", {}) or {}).get("coverageGaps"):
        print(f"WARNING: lint.py cannot run on a {device_kind} target (pageSource: none) but "
              f"run.coverageGaps is empty — the report will read as 'checked and clean' when the "
              f"deterministic UI checks never ran. Populate coverageGaps (SKILL.md §4).",
              file=sys.stderr)
elif trace.get("run"):
    print("WARNING: trace.run has no capabilities block — copy it from device-info.json at "
          "close-out (SKILL.md §4). Without it the report can't say what was checkable.",
          file=sys.stderr)

goal = trace.get("run", {}).get("goal", "TapMind Exploration")
title = f"TapMind Exploration — {goal}"

out = re.sub(
    r'<script type="application/json" id="trace">.*?</script>',
    lambda _: f'<script type="application/json" id="trace">\n{trace_text}\n</script>',
    template,
    count=1,
    flags=re.S,
)
out = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", out, count=1, flags=re.S)

# Strip the template's own demo-only disclaimer, if present.
out = re.sub(
    r'\s*<div class="note">\s*<b>Sample report\.</b>.*?</div>\n',
    "\n",
    out,
    count=1,
    flags=re.S,
)

with open(out_path, "w", encoding="utf-8") as f:
    f.write(out)

print(out_path)
PY
