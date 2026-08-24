#!/usr/bin/env python3
"""The `folder-diff` selection strategy: keep only cases that are new or changed since last run.

Usage: folder-diff.py <project-identifier> <run-dir> [--snapshot-dir DIR] [--no-update]
Reads/rewrites <run-dir>/source-cases.json; maintains ~/.tapmind/bs-snapshots/<project>.json

WHY A SNAPSHOT AND NOT A TIMESTAMP QUERY
The PRD asks for a "new folders" strategy. `listFolders` returns no created/updated timestamps to
query on, so there is nothing to ask BrowserStack for. Diffing a persisted snapshot needs no such
support, and it catches strictly more: a case whose steps were rewritten inside an old folder is
exactly as interesting as a brand-new folder, and a timestamp-on-folders approach would miss it.

(Cases *do* carry `last_updated_at` — that's the `recently-changed` strategy, which is a different
question: "touched in the last N days" vs "changed since we last looked". Use that one when you
want a fixed window; use this one when you want "what moved since the previous exploration run".)

FIRST RUN
There is no baseline, so nothing can be called new. It keeps every case, says so, and writes the
snapshot for next time. It does NOT filter to zero — a first run that silently selected nothing
would look like "no changes" when it means "no baseline".
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Fields whose change makes a case worth re-exploring. Deliberately excludes bookkeeping that
# churns without changing what the case tests (updated_by, last_updated_at itself) — otherwise a
# bulk re-tag would mark the whole corpus as changed and the strategy would select everything.
TRACKED = ("title", "gist", "priority", "artifacts", "observed", "preconditions",
           "automationStatus", "executionMode", "folder")


def fingerprint(case):
    return json.dumps({k: case.get(k) for k in TRACKED}, sort_keys=True, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("run_dir")
    ap.add_argument("--snapshot-dir", default=str(Path.home() / ".tapmind" / "bs-snapshots"))
    ap.add_argument("--no-update", action="store_true",
                    help="diff but don't write the snapshot (for a dry run)")
    a = ap.parse_args()

    run_dir = Path(a.run_dir)
    src = run_dir / "source-cases.json"
    if not src.is_file():
        sys.exit(f"missing {src} — run the scoping steps first")
    doc = json.loads(src.read_text(encoding="utf-8"))
    cases = doc.get("cases") or []

    snap_dir = Path(a.snapshot_dir)
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / f"{a.project}.json"

    now = datetime.now(timezone.utc).isoformat()
    current = {c["id"]: fingerprint(c) for c in cases if c.get("id")}

    if not snap_path.is_file():
        if not a.no_update:
            snap_path.write_text(json.dumps(
                {"project": a.project, "updatedAt": now, "cases": current},
                indent=2), encoding="utf-8")
        print(f"NO BASELINE: first folder-diff run for {a.project}. Kept all {len(cases)} case(s) "
              f"and wrote a snapshot to {snap_path}. The next run can diff against it.",
              file=sys.stderr)
        print(f"strategy: folder-diff (no baseline) — kept {len(cases)}/{len(cases)}")
        return

    prev = json.loads(snap_path.read_text(encoding="utf-8"))
    prev_cases = prev.get("cases") or {}

    added, changed = [], []
    for cid, fp in current.items():
        if cid not in prev_cases:
            added.append(cid)
        elif prev_cases[cid] != fp:
            changed.append(cid)
    removed = [cid for cid in prev_cases if cid not in current]

    keep = set(added) | set(changed)
    kept = [c for c in cases if c.get("id") in keep]
    for c in kept:
        c.setdefault("selectedBy", []).append("folder-diff")
        c["diffKind"] = "added" if c["id"] in set(added) else "changed"

    doc["cases"] = kept
    doc["casesIngested"] = len(kept)
    doc.setdefault("selection", {})["folderDiff"] = {
        "baselineAt": prev.get("updatedAt"),
        "added": len(added), "changed": len(changed), "removed": len(removed),
        "fetched": len(cases),
    }
    src.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    if not a.no_update:
        snap_path.write_text(json.dumps(
            {"project": a.project, "updatedAt": now, "cases": current}, indent=2),
            encoding="utf-8")

    # Removed cases can't be explored, but they are worth saying out loud: a case deleted between
    # runs is a coverage change nobody asked about, and it will never show up in a charter.
    if removed:
        print(f"NOTE: {len(removed)} case(s) present at the last snapshot are gone now "
              f"(e.g. {removed[:3]}). Deleted or moved out of scope — not explorable either way.",
              file=sys.stderr)
    if not kept:
        print(f"ZERO SELECTED: nothing has changed in {a.project} since "
              f"{prev.get('updatedAt')}. That is a real answer — do not fall back to 'all'. "
              f"Either widen the scope or use a different strategy.", file=sys.stderr)

    print(f"strategy: folder-diff — kept {len(kept)}/{len(cases)} "
          f"({len(added)} added, {len(changed)} changed, {len(removed)} removed) "
          f"vs baseline {prev.get('updatedAt')}")


if __name__ == "__main__":
    main()
