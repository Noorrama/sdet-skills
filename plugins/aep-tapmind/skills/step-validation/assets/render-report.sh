#!/usr/bin/env bash
# Inline <run-dir>/trace.json into report-template.html -> <run-dir>/report.html.
# Checks the step-mode invariants from references/trace-schema.md and warns on stderr for each
# violation. Warnings are bugs in whatever wrote trace.json, not noise from this script.
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
trace = json.loads(trace_text)   # fail loudly on invalid JSON before inlining it

run = trace.get("run", {})
steps = trace.get("steps", [])
warn = lambda m: print("WARNING: " + m, file=sys.stderr)

if run.get("mode") != "steps":
    warn(f'run.mode is {run.get("mode")!r}, expected "steps" — this template renders step runs. '
         f"For an exploration run use goal-driven-exploration's renderer instead.")

executed = [s for s in steps if s.get("verdict") != "not_reached"]
authored = [s for s in steps if s.get("origin") == "author"]

# runMode decides which gaps are real defects and which are inherent to the environment.
# device-info.json is authoritative (new-run.sh resolved it once at preflight); run.runMode is
# a copy of it and disagreement between the two means the trace writer re-derived it by hand.
disk_mode = None
try:
    disk_mode = json.load(open(os.path.join(run_dir, "device-info.json"))).get("runMode")
except Exception:
    pass
run_mode = run.get("runMode") or disk_mode or "local"
if disk_mode and run.get("runMode") and disk_mode != run.get("runMode"):
    warn(f'run.runMode is "{run.get("runMode")}" but device-info.json says "{disk_mode}". '
         f"§6 says copy it, never re-derive. Trusting device-info.json.")
    run_mode = disk_mode
remote = run_mode != "local"

# --- 1. screenshots on every executed step -----------------------------------------------
# Screenshots go through TapMind's HTTP endpoint (assets/capture.sh), which works identically
# on local and BrowserStack. There is no run mode in which missing screenshots are acceptable.
no_shots = [s.get("id") for s in executed if not s.get("screenBefore") or not s.get("screenAfter")]
if no_shots:
    extra = (" This run is runMode=%s — note that screenshots still work there via "
             "assets/capture.sh; adb does NOT. If the loop used `adb exec-out screencap`, that "
             "is the bug." % run_mode) if remote else ""
    warn(f"{len(no_shots)} executed step(s) missing screenBefore and/or screenAfter: "
         f"{no_shots[:6]}. The report shows placeholder art for these. Fix the loop (SKILL.md "
         f"§2.1/§2.7), not this script — capture is free and must never be skipped.{extra}")

screens_dir = os.path.join(run_dir, "screens")
if os.path.isdir(screens_dir):
    captured = {f for f in os.listdir(screens_dir) if f.endswith(".png")}
    referenced = set()
    for s in steps:
        for k in ("screenBefore", "screenAfter"):
            if s.get(k):
                referenced.add(os.path.basename(s[k]))
    orphans = sorted(captured - referenced)
    if orphans:
        warn(f"{len(orphans)} screenshot(s) on disk are referenced by no step "
             f"(e.g. {orphans[:3]}) — the trace writer dropped them.")
    dangling = sorted(referenced - captured)
    if dangling:
        warn(f"{len(dangling)} step screenshot path(s) point at files that don't exist "
             f"(e.g. {dangling[:3]}).")

# --- 2/3. counters agree with steps[] ----------------------------------------------------
expected = {
    "stepsGiven":    len(authored),
    "actionsTaken":  len(executed),
    "insertedSteps": len([s for s in steps if s.get("origin") == "inserted"]),
    "interruptions": len([s for s in steps if s.get("origin") == "interruption"]),
    "deviations":    len([s for s in authored if s.get("verdict") == "pass_with_deviation"]),
    "appFaults":     len([s for s in steps if s.get("fault") == "app"]),
}
for key, want in expected.items():
    got = run.get(key)
    if got is not None and got != want:
        warn(f"run.{key} is {got} but steps[] contains {want}. The report's headline tiles read "
             f"run.*, so this would display a number the step table contradicts.")
    if got is None:
        warn(f"run.{key} is missing — the report tile will read 0. Expected {want}.")

# --- 4. deviations carry a reason --------------------------------------------------------
bad_dev = [s.get("id") for s in steps
           if s.get("verdict") == "pass_with_deviation"
           and not (s.get("deviation") or {}).get("why")]
if bad_dev:
    warn(f'{len(bad_dev)} step(s) marked "pass_with_deviation" with no deviation.why: '
         f"{bad_dev[:6]}. A deviation the author can't act on is the one thing this report "
         f"exists to avoid.")

# --- 5. assertions carry evidence --------------------------------------------------------
bad_assert = [s.get("id") for s in steps
              if s.get("kind") == "assertion" and s.get("verdict") != "not_reached"
              and not (s.get("assertion") or {}).get("evidence")]
if bad_assert:
    warn(f"{len(bad_assert)} assertion step(s) with no assertion.evidence: {bad_assert[:6]}. "
         f'An assertion without evidence is unresolved, not passed (references/assertions.md).')

# --- 6. interruptions are fully described ------------------------------------------------
bad_intr = [s.get("id") for s in steps
            if s.get("origin") == "interruption"
            and (not s.get("impact") or not s.get("dismissedBy"))]
if bad_intr:
    warn(f"{len(bad_intr)} interruption row(s) missing impact and/or dismissedBy: "
         f"{bad_intr[:6]}. Whether a dismissal changed app state is the whole point of the "
         f"interruption ledger.")

# --- 7. lint findings need lint output behind them ---------------------------------------
findings_dir = os.path.join(run_dir, "findings")
findings_empty = not os.listdir(findings_dir) if os.path.isdir(findings_dir) else True
pagesource_dir = os.path.join(run_dir, "pagesource")
ps_count = len(os.listdir(pagesource_dir)) if os.path.isdir(pagesource_dir) else 0

# A lint-sourced finding is impossible without lint output in EITHER mode — on remote it's
# doubly impossible, since there's no page source to lint in the first place.
lint_ids = [f.get("id") for f in trace.get("findings", []) if f.get("source") == "lint"]
if lint_ids and findings_empty:
    warn(f'{len(lint_ids)} finding(s) tagged source:"lint" ({lint_ids}) despite findings/ '
         f"being empty — lint.py cannot have produced these. They are model findings "
         f"mislabeled as deterministic script output."
         + (" On a remote run lint.py cannot run at all, so no finding here may be "
            "source:\"lint\"." if remote else ""))

if remote:
    # Absent page source and lint are inherent to a remote run, not defects — but the report
    # must SAY so, or a reader takes "no lint findings" for "no defects found".
    lim = " ".join(str(x) for x in (run.get("captureLimitations") or []))
    if not run.get("captureLimitations"):
        warn(f"runMode={run_mode} but run.captureLimitations is empty. On a remote run there is "
             f"no page source, no lint.py and no logcat — record that so the report doesn't "
             f"read as 'nothing was wrong' when it means 'those checks never ran' (SKILL.md §1a).")
    elif "lint" not in lim.lower():
        warn(f"run.captureLimitations doesn't mention lint, but runMode={run_mode} means lint.py "
             f"could not have run. Readers will assume the screens were clean.")
else:
    if findings_empty and len(executed) >= 3:
        warn(f"findings/ is empty despite {len(executed)} executed steps on a LOCAL run — "
             f"lint.py was likely skipped for the whole run (SKILL.md §2.4).")
    if ps_count == 0 and len(executed) >= 3:
        warn(f"pagesource/ is empty despite {len(executed)} executed steps on a LOCAL run — "
             f"uiautomator dumps were skipped, so every geometry-based lint check silently "
             f"did nothing.")

# --- 8. seq is dense and unique ----------------------------------------------------------
seqs = [s.get("seq") for s in steps]
if seqs:
    if len(set(seqs)) != len(seqs):
        dupes = sorted({x for x in seqs if seqs.count(x) > 1})
        warn(f"duplicate seq values in steps[]: {dupes}. Screenshot filenames are derived from "
             f"seq, so duplicates mean steps are overwriting each other's captures.")
    if sorted(x for x in seqs if x is not None) != list(range(1, len(seqs) + 1)):
        warn(f"steps[].seq is not a dense 1..{len(seqs)} sequence — the filmstrip renders in seq "
             f"order and will be wrong.")

# --- 9. the corrected step list exists AND has the right shape ---------------------------
corr = run.get("correctedSteps") or []
if authored and not corr:
    warn("run.correctedSteps is empty. That list is the artifact the step author actually "
         "copy-pastes back into their test — it is the point of the run (SKILL.md §6).")
elif corr:
    strings = [i for i, c in enumerate(corr) if isinstance(c, str)]
    if strings:
        warn(f"run.correctedSteps has {len(strings)} plain-string entr{'y' if len(strings)==1 else 'ies'} "
             f"(index {strings[:5]}). The schema is a list of OBJECTS "
             f'{{"n","text","change","was","why"}} — with strings, every field reads as undefined '
             f"and the Corrected-steps tab renders BLANK ROWS. The template now salvages them by "
             f"regex, but fix the writer: that tab is the point of the run.")
    objs = [c for c in corr if isinstance(c, dict)]
    VALID_CHANGE = {"unchanged", "reworded", "inserted", "guard", "not-verified"}
    bad_shape = [i for i, c in enumerate(corr) if isinstance(c, dict)
                 and (not c.get("text") or not c.get("n") or not c.get("change"))]
    if bad_shape:
        warn(f"run.correctedSteps entries at {bad_shape[:5]} are missing n/text/change — "
             f"all three are required for the row to render.")
    bad_change = sorted({c.get("change") for c in objs
                         if c.get("change") and c.get("change") not in VALID_CHANGE})
    if bad_change:
        warn(f"run.correctedSteps uses unknown change value(s) {bad_change}. Valid: "
             f"{sorted(VALID_CHANGE)}. Unknown values get no colour coding in the report.")

# --- 10. findings are routable --------------------------------------------------------
# Every one of these has come back null from a real run, producing a report with an empty
# evidence box, a "seq undefined" chip, and an app navigation defect filed under
# "step-authoring issues" purely because `fault` was missing.
for f in trace.get("findings", []):
    fid = f.get("id", "?")
    if f.get("fault") not in ("app", "authoring"):
        warn(f'finding {fid} has fault={f.get("fault")!r}. It must be "app" (the app is broken, '
             f'file it) or "authoring" (the step needs rewriting) — that split is what routes it '
             f"in the report. Unclassified findings land in a separate section and help nobody.")
    if not f.get("evidence"):
        warn(f"finding {fid} has no evidence. The report renders an empty box. Every finding "
             f"needs the hierarchy line, attribute value, or screenshot region it came from.")
    if not f.get("detail"):
        warn(f"finding {fid} has no detail — the title alone rarely tells a reader what to do.")
    if f.get("step") is None and f.get("seq") is None:
        warn(f'finding {fid} has neither step nor seq, so the report cannot say where it '
             f'occurred (the chip reads "step not recorded").')
    if f.get("severity") not in ("high", "medium", "low"):
        warn(f"finding {fid} has severity={f.get('severity')!r}; expected high|medium|low.")

# --- 11. findings are wired to the steps that raised them --------------------------------
linked = {fid for s in steps for fid in (s.get("findings") or [])}
declared = {f.get("id") for f in trace.get("findings", [])}
orphans = sorted(declared - linked)
if orphans:
    warn(f"finding(s) {orphans} are not referenced by any step's findings[] — they won't appear "
         f"in any step's detail panel, only in the Findings tab. Add the id to the step that "
         f"raised it.")
dangling_f = sorted(linked - declared)
if dangling_f:
    warn(f"step(s) reference finding id(s) {dangling_f} that don't exist in findings[].")
null_lists = [s.get("id") for s in executed if s.get("findings") is None]
if len(null_lists) == len(executed) and executed:
    warn(f"every step has findings=null rather than []. If any finding was raised, it is not "
         f"linked to the step it came from.")

# A step that FAILED on the app needs a finding carrying the evidence. The reverse does NOT
# hold: plenty of app defects (a missing a11y label, truncated text) are spotted on a screen
# where the step itself passed, so counts are not expected to match — only this direction is.
app_fault_steps = [s for s in steps if s.get("fault") == "app"]
unevidenced = [s.get("id") for s in app_fault_steps
               if not any((trace_f.get("fault") == "app")
                          for trace_f in trace.get("findings", [])
                          if trace_f.get("id") in (s.get("findings") or []))]
if unevidenced:
    warn(f'step(s) {unevidenced} are marked fault="app" but link no fault="app" finding. '
         f"Blaming the app without attaching the evidence gives the reader nothing to file.")

# --- inline ------------------------------------------------------------------------------
title = f"TapMind Step Validation — {run.get('title', 'step run')}"
out = re.sub(r'<script type="application/json" id="trace">.*?</script>',
             lambda _: f'<script type="application/json" id="trace">\n{trace_text}\n</script>',
             template, count=1, flags=re.S)
out = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", out, count=1, flags=re.S)
out = re.sub(r'\s*<div class="note" id="sampleNote">.*?</div>\n', "\n", out, count=1, flags=re.S)

with open(out_path, "w", encoding="utf-8") as f:
    f.write(out)

print(out_path)
PY
