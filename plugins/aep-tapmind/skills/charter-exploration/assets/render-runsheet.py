#!/usr/bin/env python3
"""Render approved charters as a printable runsheet for a human tester.

Usage: render-runsheet.py <run-dir> [charter-id ...]
Reads  <run-dir>/charters.json (+ the focus-area library), writes <run-dir>/runsheet.html

WHY THIS EXISTS
Release QA at Gojek is manual. The source PRD assumes TapMind executes every charter, but its own
open questions concede TapMind's NLP fidelity is unvalidated — so in practice a human runs most of
these for a while. Without a runsheet that means charters get read off a chat transcript, run
inconsistently, and reported in prose that never reaches the suite report.

So: the same charter, rendered for a person. Crucially it produces observations in the SAME shape
an agent run produces, so `import-observations.py` can feed them to `aggregate.py` and one report
covers both. Human-run and agent-run charters sit side by side in the coverage grid.

The two fields that make a charter runnable by a human are `focus_area` (expanded here into
literal device steps, since a tester can't be expected to read the library) and `oracle` (the
checklist that turns "seemed fine" into a pass or a finding).
"""
import html
import json
import re
import sys
from pathlib import Path

RUNNABLE = ("approved", "proposed", "running", "timeboxed")

# Plain-language device instructions per focus area. The library is written for the agent; a
# tester needs the gesture, not the tool signature. Kept here rather than parsed out of
# focus-areas.md so a prose edit there can't silently produce an empty instruction on a printed
# sheet somebody is standing at a device holding.
FOCUS_STEPS = {
    "lifecycle-background": [
        "Press Home to background the app. Wait 5 seconds. Reopen it from the app switcher.",
        "Repeat once on the most state-heavy screen, waiting ~30 seconds before reopening.",
    ],
    "lifecycle-kill": [
        "Swipe the app away from the app switcher (force-kill it).",
        "Relaunch from the launcher icon — a cold start, not the switcher.",
    ],
    "permission-denial": [
        "Before reaching the screen, revoke the permission in Settings > Apps > Gojek > Permissions.",
        "Walk into the flow and Deny at the prompt. Try to continue.",
        "Grant the permission, return to the app, and retry the same flow WITHOUT restarting it.",
    ],
    "nav-back": [
        "At every screen of the flow, press the system Back button (Android) or swipe from the left edge (iOS).",
        "Do this mid-payment specifically, then go forward again and check nothing duplicated.",
    ],
    "deeplink-midflow": [
        "With the flow in progress, open the deep link named in the Probes below (paste it into a note and tap it, or use a QR).",
        "Then press Back and note exactly where you land.",
    ],
    "rapid-input": [
        "Double-tap the submit/Order button as fast as you can.",
        "Check the back end (order history) for duplicates — not just the screen.",
    ],
    "network-loss": [
        "At the moment between submitting and confirming, turn on Airplane Mode.",
        "Wait for the app to react, then turn Airplane Mode off and watch how it resolves.",
    ],
    "orientation": ["Rotate the device to landscape mid-flow, then back to portrait."],
    "locale-switch": [
        "Change the device language in Settings, then return to the app.",
        "Look for untranslated strings, raw keys, and broken layout.",
    ],
    "interrupt-call": ["Have someone call the device mid-payment. Decline, then return to the app."],
    "token-expiry": [
        "NO CONFIRMED METHOD — skip this charter and tell the test lead.",
    ],
}


def esc(s):
    return html.escape(str(s if s is not None else ""))


def as_list(v):
    if v is None:
        return []
    return [v] if isinstance(v, str) else list(v)


def charter_html(c, idx):
    focus = c.get("focus_area", "")
    steps = FOCUS_STEPS.get(focus, ["(no device steps recorded for this focus area)"])
    tb = c.get("timebox", {})
    dn = c.get("data_needs") or {}
    recipe = dn.get("recipe") if isinstance(dn, dict) else dn
    notes = dn.get("notes") if isinstance(dn, dict) else None

    def ul(items):
        items = as_list(items)
        return ("<ul>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>") if items \
            else "<p class='none'>—</p>"

    # 6 blank observation rows: enough to record a real session, few enough to fit one page.
    rows = "".join(
        "<tr><td></td><td></td><td></td><td></td></tr>" for _ in range(6))

    return f"""
<section class="charter">
  <h2>{idx}. {esc(c['id'])} — {esc(c.get('area',''))} <span class="pri">{esc(c.get('priority',''))}</span></h2>
  <p class="mission">{esc(c.get('mission',''))}</p>
  <div class="meta">
    <span><b>Timebox</b> {esc(tb.get('minutes','?'))} min</span>
    <span><b>Focus area</b> <code>{esc(focus)}</code></span>
    <span><b>Test data</b> <code>{esc(recipe or '—')}</code>{(' — ' + esc(notes)) if notes else ''}</span>
    <span><b>From cases</b> {esc(', '.join(c.get('source_test_case_ids', [])))}</span>
  </div>

  <h3>1 · Set up</h3>
  {ul(c.get('preconditions'))}

  <h3>2 · Get into position</h3>
  <p class="hint">Openers, not a script. Go past them — that's the point of a charter.</p>
  {ul(c.get('probes'))}

  <h3>3 · Apply the focus area <span class="tag">{esc(focus)}</span></h3>
  <p class="hint">Do this at screens holding state you'd hate to lose — a filled cart, a chosen
     address, a selected payment method, an order in flight. Not on a splash or loading screen.</p>
  <ol>{''.join(f'<li>{esc(s)}</li>' for s in steps)}</ol>

  <h3>4 · Check the oracle — any clause failing is a bug</h3>
  <p class="hint">Tick each one. If you cannot tell, write that down: "couldn't check" is a
     result, "seemed fine" is not.</p>
  <ul class="oracle">{''.join(
      f'<li><span class="box"></span>{esc(o)}</li>' for o in as_list(c.get('oracle')))}</ul>

  <h3>5 · Watch for</h3>
  {ul(c.get('risk_areas'))}
  <p class="hint"><b>Out of scope:</b> {esc('; '.join(as_list(c.get('out_of_scope'))) or '—')}</p>

  <h3>6 · Observations</h3>
  <table>
    <thead><tr><th style="width:12%">Time</th><th style="width:16%">Bug / Concern / Note</th>
      <th style="width:14%">Severity</th><th>What happened</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <p class="verdict"><b>Verdict:</b> PASSED &nbsp;/&nbsp; PARTIAL &nbsp;/&nbsp; FAILED &nbsp;&nbsp;
     <b>Steps done:</b> ______ &nbsp;&nbsp; <b>Time used:</b> ______ min &nbsp;&nbsp;
     <b>Tester:</b> ________________</p>
</section>"""


CSS = """
*{box-sizing:border-box} body{font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  color:#111;max-width:900px;margin:0 auto;padding:24px}
h1{font-size:22px;margin:0 0 4px} h2{font-size:17px;margin:0 0 6px;border-bottom:2px solid #111;padding-bottom:4px}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#555;margin:14px 0 4px}
.sub{color:#555;margin:0 0 18px}
.charter{page-break-after:always;margin-bottom:40px}
.charter:last-child{page-break-after:auto}
.mission{font-size:15px;font-style:italic;background:#f6f6f6;padding:8px 10px;border-left:3px solid #999;margin:8px 0}
.meta{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:#444;margin:8px 0 4px}
.pri{font-size:12px;background:#111;color:#fff;padding:1px 6px;border-radius:3px;vertical-align:middle}
.tag{font-size:11px;background:#eee;padding:1px 6px;border-radius:3px;font-family:ui-monospace,monospace}
.hint{color:#666;font-size:12px;margin:2px 0 6px}
ul,ol{margin:4px 0 4px 20px;padding:0} li{margin:2px 0}
.none{color:#999;margin:4px 0}
.oracle{list-style:none;margin-left:0}
.oracle li{display:flex;gap:8px;align-items:flex-start;margin:5px 0}
.box{display:inline-block;width:13px;height:13px;border:1.5px solid #333;border-radius:2px;flex:none;margin-top:3px}
table{width:100%;border-collapse:collapse;margin-top:4px}
th,td{border:1px solid #bbb;padding:6px;text-align:left;font-size:12px;vertical-align:top}
th{background:#f0f0f0} td{height:34px}
.verdict{margin-top:10px;font-size:12px}
code{font-family:ui-monospace,monospace;font-size:12px}
@media print{body{padding:0;max-width:none} .noprint{display:none}}
"""


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: render-runsheet.py <run-dir> [charter-id ...]")
    run_dir = Path(sys.argv[1])
    wanted = set(sys.argv[2:])
    doc = json.loads((run_dir / "charters.json").read_text(encoding="utf-8"))
    run = doc.get("run", {})

    charters = [c for c in doc["charters"]
                if c.get("status") in RUNNABLE and (not wanted or c["id"] in wanted)]
    if not charters:
        sys.exit("no runnable charters matched (dropped charters are never rendered)")

    # Group by test-data recipe so a tester provisions once and runs the group back to back.
    # That amortisation is what makes 15-minute charters practical for a human.
    charters.sort(key=lambda c: ((c.get("data_needs") or {}).get("recipe") or "",
                                 c.get("priority", "P9"), c["id"]))

    total = sum((c.get("timebox") or {}).get("minutes", 0) for c in charters)
    recipes = {}
    for c in charters:
        recipes.setdefault((c.get("data_needs") or {}).get("recipe") or "—", []).append(c["id"])

    body = "".join(charter_html(c, i + 1) for i, c in enumerate(charters))
    out = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Exploratory runsheet — {esc(run.get('scopeLabel',''))}</title><style>{CSS}</style></head><body>
<h1>Exploratory testing runsheet — {esc(run.get('scopeLabel',''))}</h1>
<p class="sub">{esc(run.get('project',''))} · {len(charters)} charter(s) · ~{total} min total ·
 derived from documented BrowserStack cases</p>
<div class="charter" style="page-break-after:always">
  <h2>Before you start</h2>
  <ul>
    <li>Each charter is <b>one question</b>, not a script. Follow the probes into the area, then
        explore — you are looking for what nobody wrote a test case for.</li>
    <li><b>Record what you could not check</b>, not just what failed. An unchecked item is not a
        pass, and the report needs to know the difference.</li>
    <li>Anything unexpected is worth a row in the Observations table even if it isn't clearly a
        bug. Concerns and notes are wanted, not just defects.</li>
    <li>If the app crashes or freezes, note the exact step and what was on screen — that is the
        highest-value thing you can bring back.</li>
  </ul>
  <h3>Test data — provision once per group</h3>
  <ul>{''.join(f'<li><code>{esc(r)}</code> — {esc(", ".join(ids))}</li>' for r, ids in recipes.items())}</ul>
  <p class="hint">Charters are ordered so that everything sharing a recipe runs back to back.
     Set up the data once, then work down the group.</p>
</div>
{body}
</body></html>"""

    dest = run_dir / "runsheet.html"
    dest.write_text(out, encoding="utf-8")
    print(dest)
    print(f"{len(charters)} charter(s), ~{total} min, grouped into {len(recipes)} data setup(s). "
          f"Print or open in a browser.", file=sys.stderr)

    missing = [c["id"] for c in charters if not as_list(c.get("oracle"))]
    if missing:
        print(f"WARNING: {missing} have no oracle — a tester has nothing to check against and "
              f"will report 'seemed fine'. Fix the charter before handing this out.",
              file=sys.stderr)
    unknown = sorted({c.get("focus_area") for c in charters
                      if c.get("focus_area") not in FOCUS_STEPS})
    if unknown:
        print(f"WARNING: no plain-language device steps for focus area(s) {unknown} — the sheet "
              f"will tell the tester nothing about what to actually do. Add them to FOCUS_STEPS "
              f"in this script.", file=sys.stderr)


if __name__ == "__main__":
    main()
