#!/usr/bin/env python3
"""Turn a human tester's observations into a trace.json aggregate.py can read.

Usage: import-observations.py <suite-run-dir> <charter-id> <observations.csv|.json>
       [--verdict PASSED|PARTIAL|FAILED] [--tester NAME] [--minutes N] [--steps N]
Writes <suite-run-dir>/manual/<charter-id>/trace.json and points the charter's runDir at it.

WHY
A manual charter and an agent charter must land in the SAME report, or the manual ones quietly
don't count and the practice dies. The suite report's value is the coverage grid, and a grid with
holes where humans did the work is worse than no grid. So a filled runsheet becomes a trace in the
identical shape goal-driven-exploration writes, and `aggregate.py` treats the two the same.

The trace is honest about what it is: `run.executedBy = "manual"`, no nodes/edges (a human didn't
record a screen graph), and `coverageGaps` carrying the automated checks a human run structurally
does not perform. That last part matters — a manual charter reporting zero findings must not be
read as "lint and crash detection came back clean", because neither ran.

CSV columns (header row required, case-insensitive, extra columns ignored):
    time, kind, severity, detail
  kind      Bug | Concern | Note     (matches the runsheet's Observations table)
  severity  high | medium | low      (blank defaults: Bug->medium, Concern->low, Note->low)
JSON: a list of objects with those same keys.
"""
import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

KIND_TO_TYPE = {"bug": "manual-bug", "concern": "manual-concern", "note": "manual-note"}
DEFAULT_SEV = {"bug": "medium", "concern": "low", "note": "low"}
# A human saying "it crashed" is a stability finding and must reach the report's headline count.
CRASH_RE = re.compile(r"\bcrash(ed|ing|es)?\b|force[- ]close|app closed", re.I)
HANG_RE = re.compile(r"\bhang|hung|frozen|freeze|not responding|anr\b|stuck (?:on|at)\b", re.I)

# What a human run structurally cannot do, stated once so every manual trace carries it.
MANUAL_GAPS = [
    "lint.py did not run - manual session, no page-source dumps captured",
    "no automated crash/hang polling - stability findings are only those the tester noticed",
    "no screenshots or view hierarchies captured for the report",
]


def read_rows(path):
    p = Path(path)
    if not p.is_file():
        sys.exit(f"missing {p}")
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            sys.exit("JSON observations must be a list of objects")
        return [{str(k).strip().lower(): v for k, v in row.items()} for row in data]
    with p.open(newline="", encoding="utf-8-sig") as fh:
        return [{(k or "").strip().lower(): v for k, v in row.items()}
                for row in csv.DictReader(fh)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("charter_id")
    ap.add_argument("observations")
    ap.add_argument("--verdict", default="PARTIAL",
                    choices=["PASSED", "PARTIAL", "FAILED"])
    ap.add_argument("--tester", default=None)
    ap.add_argument("--minutes", type=int, default=None)
    ap.add_argument("--steps", type=int, default=0)
    a = ap.parse_args()

    run_dir = Path(a.run_dir)
    charters_path = run_dir / "charters.json"
    doc = json.loads(charters_path.read_text(encoding="utf-8"))
    charter = next((c for c in doc["charters"] if c["id"] == a.charter_id), None)
    if charter is None:
        sys.exit(f"no charter {a.charter_id} in {charters_path}")

    rows = [r for r in read_rows(a.observations)
            if (r.get("detail") or "").strip()]   # blank runsheet rows aren't observations

    findings = []
    for i, r in enumerate(rows, 1):
        kind = (r.get("kind") or "note").strip().lower()
        if kind not in KIND_TO_TYPE:
            kind = "note"
        detail = (r.get("detail") or "").strip()
        sev = (r.get("severity") or "").strip().lower() or DEFAULT_SEV[kind]
        if sev not in ("high", "medium", "low"):
            sev = DEFAULT_SEV[kind]

        ftype = KIND_TO_TYPE[kind]
        diagnosis = None
        # Promote to a stability type so it reaches the report's crash/ANR headline. A tester who
        # writes "app crashed at payment" has found the thing this whole suite exists to find;
        # burying it as a generic manual-bug would hide it from the one number people read.
        if CRASH_RE.search(detail):
            ftype, sev, diagnosis = "crash", "high", "detection-only"
        elif HANG_RE.search(detail):
            ftype, sev, diagnosis = "hang", "high", "detection-only"

        f = {
            "id": f"{a.charter_id}-m{i}",
            "severity": sev,
            "confidence": "high" if kind == "bug" else "medium",
            "source": "model",      # never "lint" — no script produced this
            "type": ftype,
            "node": None,
            "step": None,
            "title": detail[:90],
            "detail": detail,
            "evidence": f"Reported by tester{' ' + a.tester if a.tester else ''}"
                        f"{' at ' + str(r.get('time')).strip() if r.get('time') else ''}",
        }
        if diagnosis:
            f["diagnosis"] = diagnosis
        findings.append(f)

    dest = run_dir / "manual" / a.charter_id
    dest.mkdir(parents=True, exist_ok=True)
    trace = {
        "run": {
            "id": f"manual-{a.charter_id}",
            "goal": charter.get("mission"),
            "executedBy": "manual",
            "tester": a.tester,
            "verdict": a.verdict,
            "verdictReason": f"Manual session, {len(findings)} observation(s) recorded",
            "runMode": "manual",
            "deviceKind": "manual",
            "focusArea": charter.get("focus_area"),
            "durationMs": (a.minutes * 60000) if a.minutes else None,
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "themes": [],
            "capabilities": None,
            "coverageGaps": MANUAL_GAPS,
        },
        "nodes": [],
        "edges": [{"id": f"m{i}", "step": i, "phase": "manual"}
                  for i in range(1, (a.steps or 0) + 1)],
        "findings": findings,
        "logs": [],
    }
    (dest / "trace.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False),
                                     encoding="utf-8")

    charter["runDir"] = str(dest)
    charter["executedBy"] = "manual"
    if charter.get("status") in ("approved", "proposed", "running"):
        charter["status"] = "done"
    charters_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    stability = sum(1 for f in findings if f["type"] in ("crash", "hang"))
    print(dest / "trace.json")
    print(f"{a.charter_id}: imported {len(findings)} observation(s)"
          f"{f', {stability} promoted to stability findings' if stability else ''}. "
          f"Status -> done, runDir set. Re-run aggregate.py/render-report.sh to fold it in.",
          file=sys.stderr)
    if not findings:
        print("NOTE: zero observations imported. A manual charter with no observations is not a "
              "clean charter — it means nothing was written down. Confirm with the tester before "
              "this lands in the report as covered.", file=sys.stderr)


if __name__ == "__main__":
    main()
