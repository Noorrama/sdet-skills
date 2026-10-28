#!/usr/bin/env python3
"""Parse a BrowserStack Test Management CSV export into release_suite.json.

BrowserStack writes one header row, then one or more body rows per case:
the first row of a case has Test Case ID + title + metadata; extra step rows
leave those cells empty and only fill Steps / Expected Result.

Usage:
  python3 parse-bs-csv.py <export.csv>
  python3 parse-bs-csv.py <export.csv> > release_suite.json

Prints JSON on stdout. Never invents a case id or step.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

_TDP_PREFIXES = ("test data:", "user:", "tdp:")
_LOCATION_COORDS = re.compile(
    r"\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)"
)


def _parse_preconditions(pre: str) -> dict:
    """Extract release emit hints from the Preconditions cell."""
    out: dict = {
        "test_data_prompt": "",
        "location_label": "",
        "location_lat": None,
        "location_lng": None,
        "not_for_tapmind": "",
    }
    if not pre:
        return out
    for line in pre.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if low.startswith("not for tapmind:"):
            out["not_for_tapmind"] = stripped.split(":", 1)[1].strip()
            continue
        for prefix in _TDP_PREFIXES:
            if low.startswith(prefix):
                out["test_data_prompt"] = stripped.split(":", 1)[1].strip()
                break
        if low.startswith("location:"):
            rest = stripped.split(":", 1)[1].strip()
            out["location_label"] = rest
            m = _LOCATION_COORDS.search(rest)
            if m:
                out["location_lat"] = float(m.group(1))
                out["location_lng"] = float(m.group(2))
    return out


def _s(row: dict, *names: str) -> str:
    for name in names:
        if name in row and row[name] is not None:
            return str(row[name]).strip()
    return ""


def parse(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    cases: list[dict] = []
    current: dict | None = None
    for row in rows:
        tid = _s(row, "Test Case ID", "ID", "Case ID")
        if tid:
            if current:
                cases.append(current)
            current = {
                "id": tid,
                "title": _s(row, "Title"),
                "folder_id": _s(row, "Folder ID"),
                "folder_path": _s(row, "Folder Path"),
                "state": _s(row, "State"),
                "owner": _s(row, "Owner"),
                "priority": _s(row, "Priority"),
                "platform": _s(row, "Platform"),
                "preconditions": _s(row, "Preconditions"),
                "description": _s(row, "Description"),
                "android_status": _s(row, "Android Automation Status v2"),
                "ios_status": _s(row, "iOS Automation Status v2"),
                "tapmind_automated": _s(row, "TapMind Automated"),
                "execution_mode": _s(row, "Execution Mode"),
                "steps": [],
            }
        if current is None:
            continue
        step = _s(row, "Steps")
        expected = _s(row, "Expected Result")
        if step:
            current["steps"].append({"action": step, "expected": expected})
    if current:
        cases.append(current)

    for case in cases:
        case["preconditions_parsed"] = _parse_preconditions(case.get("preconditions") or "")

    folders = sorted({c["folder_path"] for c in cases if c["folder_path"]})
    return {
        "source": str(path),
        "case_count": len(cases),
        "folder_paths": folders,
        "cases": cases,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: parse-bs-csv.py <browserstack-export.csv>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"ERROR: not a file: {path}", file=sys.stderr)
        return 2
    json.dump(parse(path), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
