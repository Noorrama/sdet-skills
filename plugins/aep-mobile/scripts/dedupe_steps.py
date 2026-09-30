#!/usr/bin/env python3
"""
Hoist shared Gherkin preamble from repo-sourced regression cases.

After corpus_lookup.py joins have enriched regression_context.json with repo
steps, many cases in the same module share an identical boilerplate opening
sequence (Given/And login, device setup, etc.). That preamble adds no signal
for dedup matching or coverage analysis — only the differentiating tail lines do.

This script:
  1. Finds the longest common prefix across repo-sourced cases (steps_source=repo).
  2. Emits it once as `module_step_preamble` at the run level.
  3. Strips it from each case's `steps`, keeping at least one differentiating step.

Run AFTER all corpus_lookup.py joins are complete and before validation.

Usage:
  python3 scripts/dedupe_steps.py --context regression_context.json
  python3 scripts/dedupe_steps.py --context regression_context.json --min-cases 3
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


_MIN_PREAMBLE_LINES = 2   # don't hoist a prefix shorter than this


def _common_prefix(lists: list[list[str]]) -> list[str]:
    if not lists:
        return []
    prefix = list(lists[0])
    for lst in lists[1:]:
        trimmed: list[str] = []
        for a, b in zip(prefix, lst):
            if a == b:
                trimmed.append(a)
            else:
                break
        prefix = trimmed
        if not prefix:
            break
    return prefix


def dedupe(context: dict, min_cases: int) -> tuple[dict, int]:
    tests = context.get("regression_tests", [])
    repo_cases = [t for t in tests if t.get("steps_source") == "repo" and t.get("steps")]

    if len(repo_cases) < min_cases:
        return context, 0

    preamble = _common_prefix([t["steps"] for t in repo_cases])
    if len(preamble) < _MIN_PREAMBLE_LINES:
        return context, 0

    context["module_step_preamble"] = preamble
    stripped = 0
    for t in tests:
        if t.get("steps_source") == "repo" and t.get("steps"):
            tail = t["steps"][len(preamble):]
            if tail:
                t["steps"] = tail
                stripped += 1
            # if no tail (case IS the preamble), leave steps untouched — don't blank a case
    return context, stripped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--context", required=True, type=Path)
    ap.add_argument(
        "--min-cases",
        type=int,
        default=5,
        help="Minimum repo-sourced cases sharing a prefix before hoisting (default 5)",
    )
    args = ap.parse_args()

    if not args.context.exists():
        print(f"ERROR: {args.context} not found")
        return 1

    context = json.loads(args.context.read_text(encoding="utf-8"))
    context, stripped = dedupe(context, args.min_cases)

    if stripped:
        preamble_len = len(context.get("module_step_preamble", []))
        args.context.write_text(json.dumps(context, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Hoisted {preamble_len}-line preamble; stripped from {stripped} repo cases → {args.context}")
    else:
        print("No common preamble found (or fewer cases than --min-cases) — file unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
