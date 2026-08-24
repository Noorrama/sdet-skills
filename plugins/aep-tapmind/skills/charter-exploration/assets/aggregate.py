#!/usr/bin/env python3
"""Roll charters.json + every executed charter's trace.json up into report.json.

Run this after EVERY charter finishes, not once at the end. It is idempotent and cheap
(pure file reads), so re-running it mid-suite is how the live report stays current without
the user waiting for the whole suite. Charters that haven't run yet render as pending.

The model never computes any of this — no summing findings, no building the coverage matrix,
no cost arithmetic. That is the entire point: aggregation is deterministic, so it belongs in
a script, and a 10-charter suite would otherwise re-read ten traces into context to do it.

Usage: aggregate.py <run-dir>
Reads  <run-dir>/charters.json and each charter's runDir/trace.json
Writes <run-dir>/report.json
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

SEVERITIES = ("high", "medium", "low")
# Stability findings get their own headline count, separate from the severity roll-up. They are
# the mandate this suite is judged on ("find bugs, ANRs and crashes"), and folded into a severity
# total they're invisible — "12 high" doesn't tell a release manager whether the app crashed.
STABILITY_TYPES = ("crash", "anr", "hang")
# Terminal statuses whose run dir is worth reading a trace from. "aborted" is here because an
# abort can still leave a partial trace behind.
TERMINAL = ("done", "timeboxed", "aborted")
# ...but an aborted charter did NOT run, and must not be counted as coverage. It gets a row in
# "Not covered" instead. Conflating the two would let a suite where half the charters died on a
# flaky device report as fully run.
RAN = ("done", "timeboxed")


def load_trace(run_dir_str):
    """Read one charter's goal-driven-exploration trace. Never raise — a charter whose run
    dir is missing or whose trace is malformed must still render, flagged, rather than
    taking the whole report down at the point the user most wants to see it."""
    if not run_dir_str:
        return None, "no run directory recorded"
    p = Path(run_dir_str).expanduser() / "trace.json"
    if not p.is_file():
        return None, f"trace.json not found at {p}"
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as e:
        return None, f"trace.json is not valid JSON ({e})"


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: aggregate.py <run-dir>")
    run_dir = Path(sys.argv[1])
    doc = json.loads((run_dir / "charters.json").read_text(encoding="utf-8"))
    run, charters = doc.get("run", {}), doc["charters"]

    out_charters = []
    all_findings = []
    sev_total = Counter()
    area_sev = defaultdict(Counter)      # coverage matrix cell: area -> severity counts
    area_charters = defaultdict(list)
    tokens = Counter()
    cost = 0.0
    cost_estimated = False
    steps_used = steps_budget = 0
    stability = Counter()            # crash / anr / hang counts across the suite
    undiagnosed = []                 # stability findings with no stack trace behind them
    coverage_gaps = []               # what the targets could not check, per charter

    for c in charters:
        entry = {
            "id": c["id"], "area": c["area"], "mission": c["mission"],
            "priority": c["priority"], "status": c["status"],
            "sourceTestCaseIds": c["source_test_case_ids"],
            "rationale": c["rationale"], "riskAreas": c.get("risk_areas", []),
            "probes": c.get("probes", []),
            "outOfScope": c.get("out_of_scope", []),
            "preconditions": c.get("preconditions", []),
            "dataNeeds": c.get("data_needs"),
            "timebox": c["timebox"], "runDir": c.get("runDir"),
            "focusArea": c.get("focus_area"), "oracle": c.get("oracle", []),
            "executedBy": c.get("executedBy", "agent"),
            "verdict": None, "verdictReason": None, "traceError": None,
            "stepsUsed": 0, "nodes": [], "edges": [], "findings": [],
            "device": None, "app": None, "themes": [], "durationMs": None,
            "reportPath": None,
        }
        area_charters[c["area"]].append(c["id"])
        if c["status"] != "dropped":
            steps_budget += c["timebox"]["steps"]

        if c["status"] in TERMINAL:
            trace, err = load_trace(c.get("runDir"))
            if err:
                entry["traceError"] = err
            else:
                t_run = trace.get("run", {})
                entry["verdict"] = t_run.get("verdict")
                entry["verdictReason"] = t_run.get("verdictReason")
                entry["device"] = t_run.get("device")
                entry["app"] = t_run.get("app")
                entry["themes"] = t_run.get("themes", [])
                entry["durationMs"] = t_run.get("durationMs")
                entry["nodes"] = trace.get("nodes", [])
                entry["edges"] = trace.get("edges", [])
                entry["stepsUsed"] = len(trace.get("edges", []))
                steps_used += entry["stepsUsed"]
                rp = Path(c["runDir"]).expanduser() / "report.html"
                entry["reportPath"] = str(rp) if rp.is_file() else None

                # What this charter's target couldn't check. Carried up so the suite report can
                # distinguish "clean" from "never looked" — see goal-driven-exploration's
                # design-notes.md (run.coverageGaps).
                entry["capabilities"] = t_run.get("capabilities")
                entry["deviceKind"] = t_run.get("deviceKind")
                # A manual trace declares itself; trust it over the charter's assignment, since
                # the trace is what actually happened.
                if t_run.get("executedBy"):
                    entry["executedBy"] = t_run["executedBy"]
                    entry["tester"] = t_run.get("tester")
                entry["coverageGaps"] = t_run.get("coverageGaps") or []
                for g in entry["coverageGaps"]:
                    coverage_gaps.append({"charterId": c["id"], "area": c["area"], "gap": g})

                for f in trace.get("findings", []):
                    f = dict(f, charterId=c["id"], area=c["area"])
                    entry["findings"].append(f)
                    all_findings.append(f)
                    sev = f.get("severity", "low")
                    sev_total[sev] += 1
                    area_sev[c["area"]][sev] += 1
                    ftype = f.get("type")
                    if ftype in STABILITY_TYPES:
                        stability[ftype] += 1
                        # A crash we detected but couldn't diagnose is still a real crash — it
                        # just can't be triaged from this report alone. Surfaced separately so
                        # nobody reads "3 crashes, no stack traces" as "3 soft findings".
                        if f.get("diagnosis") == "detection-only":
                            undiagnosed.append({"id": f.get("id"), "charterId": c["id"],
                                                "type": ftype, "deviceKind": t_run.get("deviceKind")})

                tu = t_run.get("tokenUsage") or {}
                for k in ("inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens"):
                    if isinstance(tu.get(k), int):
                        tokens[k] += tu[k]
                if isinstance(t_run.get("costUsd"), (int, float)):
                    cost += t_run["costUsd"]
                cost_estimated = cost_estimated or bool(t_run.get("costEstimated"))

        out_charters.append(entry)

    # Coverage matrix. A "cold" area is one that had charters proposed but none actually run,
    # or ran with zero findings AND zero explored nodes — both mean the matrix cell is not
    # evidence of health, and the report must say so rather than render a reassuring blank.
    matrix = []
    for area, ids in area_charters.items():
        ran_ids = [e["id"] for e in out_charters if e["area"] == area and e["status"] in RAN]
        explored = sum(len(e["nodes"]) for e in out_charters if e["area"] == area)
        src = sorted({s for e in out_charters if e["area"] == area for s in e["sourceTestCaseIds"]})
        matrix.append({
            "area": area, "charterIds": ids, "ranCharterIds": ran_ids,
            "sourceTestCaseIds": src, "nodesExplored": explored,
            "severity": {s: area_sev[area][s] for s in SEVERITIES},
            "cold": not ran_ids or explored == 0,
        })
    matrix.sort(key=lambda m: (-sum(m["severity"].values()), m["area"]))

    not_covered = {
        "dropped": [{"id": e["id"], "area": e["area"], "mission": e["mission"]}
                    for e in out_charters if e["status"] == "dropped"],
        "timeboxed": [{"id": e["id"], "area": e["area"], "stepsUsed": e["stepsUsed"],
                       "stepsBudget": e["timebox"]["steps"], "verdictReason": e["verdictReason"]}
                      for e in out_charters if e["status"] == "timeboxed"],
        "aborted": [{"id": e["id"], "area": e["area"], "reason": e["verdictReason"] or e["traceError"]}
                    for e in out_charters if e["status"] == "aborted"],
        "notRun": [{"id": e["id"], "area": e["area"], "mission": e["mission"]}
                   for e in out_charters if e["status"] in ("proposed", "approved", "running")],
        "coldAreas": [m["area"] for m in matrix if m["cold"]],
    }

    report = {
        "run": {
            **run,
            "chartersDerived": len(charters),
            "chartersApproved": sum(1 for c in charters if c["status"] != "dropped"),
            "chartersRun": sum(1 for e in out_charters if e["status"] in RAN),
            "chartersPending": sum(1 for e in out_charters if e["status"] in ("proposed", "approved", "running")),
            "findingsBySeverity": {s: sev_total[s] for s in SEVERITIES},
            "findingsTotal": sum(sev_total.values()),
            # Headline stability numbers — the suite's stated purpose, reported on their own.
            "stability": {t: stability[t] for t in STABILITY_TYPES},
            "stabilityTotal": sum(stability.values()),
            "undiagnosedStability": undiagnosed,
            "stepsUsed": steps_used,
            "stepsBudget": steps_budget,
            "tokenUsage": dict(tokens) or None,
            "costUsd": round(cost, 4) if cost else None,
            "costEstimated": cost_estimated,
            "complete": all(c["status"] not in ("proposed", "approved", "running") for c in charters),
        },
        "charters": out_charters,
        "coverageMatrix": matrix,
        "findings": sorted(all_findings, key=lambda f: SEVERITIES.index(f.get("severity", "low"))),
        "notCovered": not_covered,
        # Everything the executed targets structurally could not check (no lint on iOS, no crash
        # diagnosis on BrowserStack, screens where liveness wasn't checked). Belongs next to
        # "Not covered": both answer "what does this report NOT establish".
        "coverageGaps": coverage_gaps,
    }

    out = run_dir / "report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(out)

    r = report["run"]
    print(f"{r['chartersRun']}/{r['chartersApproved']} charters run · "
          f"{r['findingsTotal']} findings "
          f"(high {r['findingsBySeverity']['high']}, medium {r['findingsBySeverity']['medium']}, "
          f"low {r['findingsBySeverity']['low']}) · {r['stepsUsed']}/{r['stepsBudget']} steps",
          file=sys.stderr)
    if r["stabilityTotal"]:
        print(f"STABILITY: {r['stability']['crash']} crash · {r['stability']['anr']} ANR · "
              f"{r['stability']['hang']} hang", file=sys.stderr)
    if undiagnosed:
        kinds = sorted({u["deviceKind"] for u in undiagnosed if u["deviceKind"]})
        print(f"NOTE: {len(undiagnosed)} stability finding(s) are detection-only (no stack trace) "
              f"— target{'s' if len(kinds) != 1 else ''} {', '.join(kinds) or 'unknown'} cannot "
              f"produce one. They are real crashes; they just can't be triaged from this report. "
              f"Pull logs from the device/session to diagnose.", file=sys.stderr)
    if coverage_gaps:
        print(f"NOTE: {len(coverage_gaps)} coverage gap(s) recorded across charters — checks that "
              f"structurally could not run on these targets. Lead with these when summarising; "
              f"an unmeasured area is not a clean one.", file=sys.stderr)
    for e in out_charters:
        if e["traceError"]:
            print(f"WARNING: {e['id']} ran but its trace could not be read — {e['traceError']}. "
                  f"Its findings are missing from this report.", file=sys.stderr)

    # A charter stuck in "running" means a previous suite died mid-charter (killed, crashed, lost
    # its device). It counts as pending forever and understates the Not-covered section, so surface
    # it loudly with the exact fix rather than letting the report quietly misreport.
    stuck = [e["id"] for e in out_charters if e["status"] == "running"]
    if stuck:
        print(f"WARNING: {len(stuck)} charter(s) still marked 'running' ({', '.join(stuck)}) — a "
              f"previous run did not finish. Resolve them against what is on disk with: "
              f"charter-status.py {run_dir} --recover", file=sys.stderr)


if __name__ == "__main__":
    main()
