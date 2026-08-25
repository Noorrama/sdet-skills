#!/usr/bin/env python3
"""Produce a DRY-RUN plan of what would be written back to BrowserStack. Writes nothing.

Usage: writeback-plan.py <run-dir> [--include-notes]
Reads  <run-dir>/report.json, writes <run-dir>/writeback-plan.json + prints a summary

THIS SCRIPT NEVER CALLS BROWSERSTACK. It only decides what *should* be written and renders it for
a human to approve. The actual `createTestRun` / `addTestResult` / `updateTestCase` calls are made
by the skill, one at a time, after the user says yes to this plan (SKILL.md phase F).

That separation is the point. Write-back is outward-facing and effectively irreversible — a test
run posted into a shared project is visible to the whole team and cannot be quietly undone. The
failure to avoid is an agent deciding mid-report that it may as well file results, and creating
fifty entries nobody reviewed. So: compute the plan deterministically here, show it, and let a
person authorise it.

Three kinds of entry:
  result     an addTestResult against a source case a charter actually exercised
  defect     a finding worth a linked issue - only high-severity, high-confidence ones
  doc-gap    an updateTestCase for a case whose documentation the run found to be broken
             (placeholder text, missing preconditions) - proposed text only, never auto-applied
"""
import argparse
import json
import sys
from pathlib import Path

RAN = ("done", "timeboxed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--include-notes", action="store_true",
                    help="also propose results for low-severity notes (off by default)")
    a = ap.parse_args()

    run_dir = Path(a.run_dir)
    rp = run_dir / "report.json"
    if not rp.is_file():
        sys.exit(f"missing {rp} — run aggregate.py first")
    report = json.loads(rp.read_text(encoding="utf-8"))
    run = report.get("run", {})

    results, defects, doc_gaps, skipped = [], [], [], []

    for c in report.get("charters", []):
        if c["status"] not in RAN:
            # Never post a result for a charter that didn't run. A dropped or aborted charter
            # posted as a result is a false coverage claim inside the system of record - strictly
            # worse than no entry at all.
            skipped.append({"charterId": c["id"], "status": c["status"],
                            "reason": "charter did not run"})
            continue

        findings = c.get("findings", [])
        high = [f for f in findings if f.get("severity") == "high"]
        # A charter is exploratory: its verdict is about the mission, not a pass/fail of the
        # source case. Map conservatively and say why in the comment.
        status = "failed" if high else ("passed" if c.get("verdict") == "PASSED" else "untested")

        for case_id in c.get("sourceTestCaseIds", []):
            results.append({
                "action": "addTestResult",
                "testCaseId": case_id,
                "status": status,
                "charterId": c["id"],
                "comment": (
                    f"Exploratory charter {c['id']} ({c.get('focusArea') or 'no focus area'}) - "
                    f"{c.get('verdictReason') or c.get('verdict') or 'no verdict'}. "
                    f"{len(findings)} observation(s), {len(high)} high severity. "
                    f"Executed by {c.get('executedBy', 'agent')}."
                ),
            })

        for f in findings:
            if f.get("severity") == "high" and f.get("confidence") in ("high", None):
                defects.append({
                    "action": "createTestCase|linkIssue",
                    "charterId": c["id"],
                    "type": f.get("type"),
                    "severity": f.get("severity"),
                    "title": f.get("title"),
                    "detail": f.get("detail"),
                    "diagnosis": f.get("diagnosis"),
                    "relatedTestCaseIds": c.get("sourceTestCaseIds", []),
                })
            elif a.include_notes:
                skipped.append({"charterId": c["id"], "findingId": f.get("id"),
                                "reason": f"severity={f.get('severity')} - below the defect bar"})

    plan = {
        "project": run.get("project"),
        "suiteRunId": run.get("id"),
        "generatedFrom": str(rp),
        "dryRun": True,
        "results": results,
        "defects": defects,
        "docGaps": doc_gaps,
        "skipped": skipped,
        # Carried into every comment's context: a report that could not run half its checks must
        # not post results that imply it did.
        "coverageGaps": report.get("coverageGaps", []),
    }
    out = run_dir / "writeback-plan.json"
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    print(out)

    print(f"\nDRY RUN - nothing has been written to BrowserStack.\n", file=sys.stderr)
    print(f"  {len(results):3} test result(s) across "
          f"{len({r['testCaseId'] for r in results})} case(s)", file=sys.stderr)
    print(f"  {len(defects):3} defect(s) proposed (high severity only)", file=sys.stderr)
    print(f"  {len(skipped):3} skipped", file=sys.stderr)
    if plan["coverageGaps"]:
        print(f"\n  {len(plan['coverageGaps'])} coverage gap(s) on this suite. Any 'passed' result "
              f"below is narrower than it looks - say so in the comment or don't post it.",
              file=sys.stderr)
    print("\n  Review writeback-plan.json, then confirm before anything is posted.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
