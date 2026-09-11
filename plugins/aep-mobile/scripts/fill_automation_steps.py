#!/usr/bin/env python3
"""
Fill scenario_list[].automation_steps from steps[] + expected_result when missing.

The GENERATE runner authors human-facing steps and expected_result. Typing a second
interleaved copy (automation_steps) into context is mostly waste — this script builds
the interleaved sequence on disk.

Does not invent TapMind helpers (loginToDriver, openDeeplink wrappers, etc.). If a
scenario already has non-empty automation_steps, it is left alone unless --force.

Usage:
  python3 scripts/fill_automation_steps.py --plan <feature>_SDET_plan.json [--force]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _is_noop_verify(line: str) -> bool:
    s = line.strip()
    return s in {"—", "-", "–", "N/A", "n/a", ""}


def interleave(steps: list[str], expected: list[str]) -> list[str]:
    """Pair actions with verifications; leftover verifies append at end."""
    out: list[str] = []
    if not steps and not expected:
        return out
    if not steps:
        return [e for e in expected if not _is_noop_verify(e)]

    n = len(steps)
    m = len(expected)
    if m == 0:
        return list(steps)
    # Single verify blob vs many actions → keep after last action (don't glue to step 1)
    if m == 1 and n > 1 and not _is_noop_verify(expected[0]):
        return list(steps) + [expected[0]]
    if m == n:
        for a, v in zip(steps, expected):
            out.append(a)
            if not _is_noop_verify(v):
                out.append(v)
        return out
    # Uneven: attach one verify per step when available, rest at end
    for i, a in enumerate(steps):
        out.append(a)
        if i < m and not _is_noop_verify(expected[i]):
            out.append(expected[i])
    for v in expected[n:]:
        if not _is_noop_verify(v):
            out.append(v)
    return out


def fill_plan(plan: dict[str, Any], *, force: bool) -> tuple[int, int]:
    filled = 0
    skipped = 0
    for sc in plan.get("scenario_list") or []:
        if not isinstance(sc, dict):
            continue
        existing = sc.get("automation_steps")
        if isinstance(existing, list) and existing and not force:
            skipped += 1
            continue
        mode = str(sc.get("execution_mode") or "").lower()
        if mode == "manual" and not force:
            # Manual scenarios may still carry [] for code-gen skip
            if existing == []:
                skipped += 1
                continue
        steps = _as_list(sc.get("steps"))
        expected = _as_list(sc.get("expected_result"))
        sc["automation_steps"] = interleave(steps, expected)
        filled += 1
    return filled, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan", required=True, type=Path)
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing non-empty automation_steps",
    )
    args = ap.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    filled, skipped = fill_plan(plan, force=args.force)
    args.plan.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Filled automation_steps on {filled} scenario(s); left {skipped} unchanged → {args.plan}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
