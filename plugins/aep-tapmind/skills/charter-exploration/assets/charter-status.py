#!/usr/bin/env python3
"""Transition one charter's status (and record its run dir). Also recovers stale runs.

Why this is a script and not "edit charters.json": hand-editing a 5-charter plan means the model
re-reads and rewrites the whole file for a one-word change — tokens spent to risk clobbering the
user's gate edits. This does the one field, validates the transition, and leaves everything else
byte-identical.

Usage:
  charter-status.py <run-dir> <charter-id> <status> [run-dir-of-that-charter]
  charter-status.py <run-dir> <charter-id> --assign agent|manual
  charter-status.py <run-dir> --recover
  charter-status.py <run-dir> --list

Statuses: proposed | approved | dropped | running | done | timeboxed | aborted

--assign records who executes a charter (phase C.5). Manual charters are handed to a release QA
via `render-runsheet.py` and come back through `import-observations.py`; agent charters run as
goal-driven-exploration sub-runs. The distinction matters to --recover, which must not mark a
manual charter 'aborted' just because no agent trace exists yet.

--recover fixes the state a killed or crashed suite leaves behind: any charter still marked
`running` is resolved against what is actually on disk — `done` if its run dir has a trace with a
verdict, `aborted` otherwise. Run it before resuming a suite, and any time you are unsure whether
a previous run finished. A charter stuck in `running` otherwise counts as "pending" forever and
quietly understates what the report says was not covered.
"""
import json
import sys
from pathlib import Path

STATUSES = ("proposed", "approved", "dropped", "running", "done", "timeboxed", "aborted")


def load(run_dir):
    p = Path(run_dir) / "charters.json"
    if not p.is_file():
        sys.exit(f"missing {p}")
    return p, json.loads(p.read_text(encoding="utf-8"))


def save(p, doc):
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def verdict_on_disk(rd):
    """Did this charter's goal-driven-exploration run actually reach a verdict?"""
    if not rd:
        return None
    t = Path(rd).expanduser() / "trace.json"
    if not t.is_file():
        return None
    try:
        return (json.loads(t.read_text(encoding="utf-8")).get("run") or {}).get("verdict")
    except json.JSONDecodeError:
        return None


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    run_dir = sys.argv[1]
    p, doc = load(run_dir)
    charters = doc["charters"]

    if sys.argv[2] == "--list":
        for c in charters:
            print(f"  {c['id']:6} {c['status']:10} {c.get('executedBy','agent'):7} "
                  f"{c['area']:16} {c.get('runDir') or ''}")
        return

    if sys.argv[2] == "--recover":
        fixed = []
        for c in charters:
            if c["status"] != "running":
                continue
            # A manual charter marked 'running' means a runsheet is out with a tester. There is
            # no agent trace to find and there shouldn't be — recovering it to 'aborted' would
            # throw away work that is still in progress on someone's desk.
            if c.get("executedBy") == "manual":
                fixed.append((c["id"], "running", "manual charter — runsheet still out, left alone"))
                continue
            v = verdict_on_disk(c.get("runDir"))
            c["status"] = "done" if v else "aborted"
            fixed.append((c["id"], c["status"], v or "no trace/verdict on disk"))
        if not fixed:
            print("nothing to recover — no charter is stuck in 'running'")
            return
        save(p, doc)
        for cid, st, why in fixed:
            print(f"  {cid}: running -> {st} ({why})")
        print("Re-render the report so it reflects this.", file=sys.stderr)
        return

    if len(sys.argv) < 4:
        sys.exit(__doc__)
    cid, status = sys.argv[2], sys.argv[3]

    target = next((c for c in charters if c["id"] == cid), None)
    if target is None:
        sys.exit(f"no charter {cid!r} in {p} (have: {', '.join(c['id'] for c in charters)})")

    if status == "--assign":
        if len(sys.argv) < 5 or sys.argv[4] not in ("agent", "manual"):
            sys.exit("--assign takes 'agent' or 'manual'")
        target["executedBy"] = sys.argv[4]
        save(p, doc)
        print(f"{cid}: executedBy -> {sys.argv[4]}")
        return

    if status not in STATUSES:
        sys.exit(f"status must be one of {STATUSES}, got {status!r}")

    if len(sys.argv) > 4:
        target["runDir"] = sys.argv[4]

    # Guard the one transition that silently corrupts a report: claiming a verdict that isn't on
    # disk. The aggregator would then show the charter as covered with zero findings, which reads
    # as "clean" rather than "never ran".
    if status in ("done", "timeboxed") and not verdict_on_disk(target.get("runDir")):
        print(
            f"WARNING: marking {cid} '{status}' but no trace.json with a verdict exists at "
            f"{target.get('runDir') or '<no runDir set>'}. If the run really didn't finish, use "
            f"'aborted' — a false 'done' renders as covered-and-clean in the report.",
            file=sys.stderr,
        )

    prev = target["status"]
    target["status"] = status
    save(p, doc)
    print(f"{cid}: {prev} -> {status}" + (f"  runDir={target['runDir']}" if target.get("runDir") else ""))


if __name__ == "__main__":
    main()
