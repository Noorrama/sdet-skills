#!/usr/bin/env python3
"""
Emit the 15-column TMS CSV from an SDET plan JSON.

The model writes scenario_list[] (steps, expected_result, preconditions, etc.).
This script flattens that into <feature>_test_cases.csv so the runner never
types hundreds of KB of CSV into context.

Usage:
  python3 scripts/plan_to_csv.py \\
    --plan <feature>_SDET_plan.json \\
    --out  <feature>_test_cases.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

TMS_CSV_HEADERS = [
    "Title",
    "State",
    "Priority",
    "Type of Test Case",
    "Automation Status",
    "Preconditions",
    "Steps",
    "Expected Result",
    "Execution Mode",
    "Platform",
    "Country v2",
    "Android Automation Status v2",
    "iOS Automation Status v2",
    "TestType",
    "Existing Case Ref",
]


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value).strip()
    return [text] if text else []


def _numbered(lines: list[str]) -> str:
    out: list[str] = []
    for i, line in enumerate(lines, start=1):
        s = line.strip()
        if not s:
            continue
        if s[0].isdigit() and (". " in s[:4] or ") " in s[:4]):
            out.append(s)
        else:
            out.append(f"{i}. {s}")
    return "\n".join(out)


def _preconditions(sc: dict[str, Any]) -> str:
    lines: list[str] = []
    for fixture in sc.get("test_data") or []:
        if not isinstance(fixture, dict):
            continue
        desc = str(fixture.get("description") or "").strip()
        state = fixture.get("required_state")
        if desc and state:
            lines.append(f"{desc} ({state})")
        elif desc:
            lines.append(desc)
        elif state:
            lines.append(str(state))
    country = sc.get("country")
    if country:
        lines.append(f"Country: {country}")
    driver_type = sc.get("driver_type")
    if driver_type:
        lines.append(f"Driver type: {driver_type}")
    meta = sc.get("preconditions_metadata") or {}
    if isinstance(meta, dict):
        env = meta.get("target_environment")
        locale = meta.get("target_locale")
        if env:
            lines.append(f"Environment: {env}")
        if locale:
            lines.append(f"Locale: {locale}")
        deeplink = meta.get("entry_deeplink") or meta.get("deeplink")
        if deeplink:
            lines.append(f"Entry deeplink: {deeplink}")
        flags = meta.get("active_experiment_flags") or meta.get("feature_flags") or {}
        if isinstance(flags, dict):
            for k, v in flags.items():
                lines.append(f"Flag {k}={v}")
        elif isinstance(flags, list):
            for f in flags:
                lines.append(f"Flag {f}")
    return "\n".join(lines)


def _android_ios_status(platform: str, automation_status: str) -> tuple[str, str]:
    plat = (platform or "").lower()
    status = automation_status or "Manual"
    if "ios" in plat and "android" not in plat and "cross" not in plat:
        return "N/A", status
    if "android" in plat and "ios" not in plat and "cross" not in plat:
        return status, "N/A"
    return status, status


def scenario_to_row(sc: dict[str, Any]) -> dict[str, str]:
    title = str(sc.get("csv_title_association") or sc.get("description") or "").strip()
    platform = str(sc.get("platform") or "Cross-Platform")
    automation_status = str(sc.get("automation_status") or "Manual")
    android, ios = _android_ios_status(platform, automation_status)
    steps = _numbered(_as_list(sc.get("steps")))
    expected = sc.get("expected_result")
    if isinstance(expected, list):
        expected_s = _numbered([str(x) for x in expected])
    else:
        expected_s = str(expected or "").strip()
        # If unnumbered multi-line, leave as-is (validator counts numbered lines)
    return {
        "Title": title,
        "State": "Active",
        "Priority": str(sc.get("priority_tier") or "P1"),
        "Type of Test Case": str(sc.get("test_case_type") or "Regression"),
        "Automation Status": automation_status,
        "Preconditions": _preconditions(sc),
        "Steps": steps,
        "Expected Result": expected_s,
        "Execution Mode": str(sc.get("execution_mode") or "Manual"),
        "Platform": platform,
        "Country v2": str(sc.get("country") or ""),
        "Android Automation Status v2": android,
        "iOS Automation Status v2": ios,
        "TestType": "Story",
        "Existing Case Ref": str(sc.get("existing_case_ref") or ""),
    }


def review_first_row(open_count: int, needs_answer: int) -> dict[str, str]:
    row = {h: "" for h in TMS_CSV_HEADERS}
    row["Title"] = (
        f"{open_count} open points ({needs_answer} need an answer) — "
        "see analysis.md before importing"
    )
    row["State"] = "Active"
    row["Priority"] = "P2"
    row["Type of Test Case"] = "Regression"
    row["Automation Status"] = "Manual"
    row["Execution Mode"] = "Manual"
    row["Platform"] = "Cross-Platform"
    row["TestType"] = "Story"
    # Marker id lives in Title convention used by the skill (REVIEW-FIRST)
    row["Title"] = f"[REVIEW-FIRST] {row['Title']}"
    return row


def build_rows(plan: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    status = str(plan.get("extraction_status") or "COMPLETE").upper()
    notes = plan.get("extraction_notes") or []
    if status != "COMPLETE" and notes:
        needs = sum(
            1
            for n in notes
            if isinstance(n, dict) and str(n.get("follow_up") or "").upper() == "NEEDS_ANSWER"
        )
        rows.append(review_first_row(len(notes), needs))
    for sc in plan.get("scenario_list") or []:
        if isinstance(sc, dict):
            rows.append(scenario_to_row(sc))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    rows = build_rows(plan)
    if not rows:
        print("ERROR: plan has no scenario_list rows to emit", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TMS_CSV_HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} CSV row(s) → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
