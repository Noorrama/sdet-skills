#!/usr/bin/env python3
"""
Build a slim regression_context.json from MCP payloads saved on disk.

The agent writes raw BrowserStack listTestCases (and optional listFolders)
responses to disk, then runs this script. The model never keeps the large MCP
payload in context while formatting the final context file.

Usage:
  python3 scripts/parse_regression_mcp.py \\
    --cases-json /tmp/bs_cases_PR-176.json \\
    [--cases-json /tmp/bs_cases_other.json] \\
    --out regression_context.json \\
    [--app-id gojek-consumer] \\
    [--feature-key MyFeature] \\
    [--project PR-176] \\
    [--folder-id 12345]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKIP_CUSTOM_FIELDS = {
    "execution mode",
    "platform",
    "android automation status v2",
    "ios automation status v2",
    "automation status",
    "type of test case",
    "testtype",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _cases_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [c for c in payload if isinstance(c, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("test_cases", "testCases", "cases", "data", "items", "results"):
        val = payload.get(key)
        if isinstance(val, list):
            return [c for c in val if isinstance(c, dict)]
        if isinstance(val, dict):
            nested = _cases_from_payload(val)
            if nested:
                return nested
    # Single case object
    if any(k in payload for k in ("id", "case_id", "identifier", "title", "name")):
        return [payload]
    return []


def _case_id(case: dict[str, Any]) -> str:
    for key in ("id", "case_id", "identifier", "test_case_id"):
        if case.get(key):
            return str(case[key])
    return ""


def _case_number(cid: str) -> str:
    s = cid.strip()
    if s.upper().startswith("C") and s[1:].isdigit():
        return s[1:]
    if s.upper().startswith("TC-"):
        return s[3:]
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits or s


def _variant_dimensions(case: dict[str, Any]) -> dict[str, list[str]] | None:
    custom = case.get("custom_fields") or case.get("customFields") or []
    out: dict[str, list[str]] = {}
    if isinstance(custom, dict):
        custom = [{"name": k, "value": v} for k, v in custom.items()]
    if not isinstance(custom, list):
        return None
    for item in custom:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("field_name") or item.get("key") or "").strip()
        if not name or name.lower() in SKIP_CUSTOM_FIELDS:
            continue
        raw = item.get("value")
        if raw is None:
            raw = item.get("values")
        values: list[str]
        if isinstance(raw, list):
            values = [str(v) for v in raw if str(v).strip()]
        elif raw is None or raw == "":
            continue
        else:
            values = [str(raw)]
        if values:
            out.setdefault(name, [])
            for v in values:
                if v not in out[name]:
                    out[name].append(v)
    return out or None


def _steps(case: dict[str, Any]) -> list[str]:
    steps = case.get("steps") or case.get("Steps") or []
    if isinstance(steps, str):
        return [s.strip() for s in steps.split("\n") if s.strip()]
    out: list[str] = []
    if isinstance(steps, list):
        for s in steps:
            if isinstance(s, dict):
                text = s.get("step") or s.get("action") or s.get("text") or s.get("description")
                if text:
                    out.append(str(text).strip())
            elif s:
                out.append(str(s).strip())
    return out


_PRECONDITIONS_CAP = 150


def normalize_case(case: dict[str, Any], *, repo: str | None, module: str | None) -> dict[str, Any]:
    cid = _case_id(case)
    entry: dict[str, Any] = {
        "id": cid or str(case.get("title") or case.get("name") or "UNKNOWN"),
        "case_number": _case_number(cid) if cid else "",
        "title": str(case.get("title") or case.get("name") or "").strip(),
        "priority": str(case.get("priority") or case.get("Priority") or ""),
    }
    # preconditions: capped — full setup text lives in BrowserStack; fetch on demand
    raw_pre = str(case.get("preconditions") or case.get("pre_conditions") or "").strip()
    if raw_pre:
        entry["preconditions"] = (
            raw_pre[:_PRECONDITIONS_CAP] + f"…[see BrowserStack {cid}]"
            if len(raw_pre) > _PRECONDITIONS_CAP
            else raw_pre
        )
    steps = _steps(case)
    if steps:
        entry["steps"] = steps
    variants = _variant_dimensions(case)
    if variants:
        entry["variant_dimensions"] = variants
    if repo:
        entry["source_repo"] = repo
    if module:
        entry["source_module"] = module
    return entry


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--cases-json",
        action="append",
        required=True,
        type=Path,
        help="Path to a saved listTestCases MCP JSON payload (repeatable)",
    )
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--app-id", default="")
    ap.add_argument("--feature-key", default="")
    ap.add_argument("--project", default="")
    ap.add_argument("--folder-id", action="append", default=[])
    ap.add_argument("--repo", default="")
    ap.add_argument("--module", default="")
    args = ap.parse_args()

    tests: list[dict[str, Any]] = []
    seen: set[str] = set()
    notes: list[dict[str, str]] = []

    for path in args.cases_json:
        if not path.exists():
            notes.append(
                {
                    "field": "mcp_payload",
                    "reason": f"missing file {path}",
                    "action": "re-run listTestCases and save JSON to disk",
                    "follow_up": "NEEDS_ANSWER",
                }
            )
            continue
        payload = _load(path)
        cases = _cases_from_payload(payload)
        if not cases:
            notes.append(
                {
                    "field": str(path),
                    "reason": "no test cases found in MCP payload shape",
                    "action": "confirm listTestCases response was saved raw",
                    "follow_up": "WORTH_CHECKING",
                }
            )
            continue
        for case in cases:
            entry = normalize_case(case, repo=args.repo or None, module=args.module or None)
            key = entry["id"]
            if key in seen:
                continue
            seen.add(key)
            # Prefer Active; keep others but mark
            status = str(entry.get("status") or "").lower()
            if status and status not in {"active", "ready", "published"}:
                continue
            tests.append(entry)

    context: dict[str, Any] = {
        "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "extraction_status": "COMPLETE" if tests and not notes else ("PARTIAL" if tests else "LIMITED"),
        "extraction_notes": notes,
        "regression_tests": tests,
    }
    if args.app_id:
        context["app_id"] = args.app_id
    if args.feature_key:
        context["feature_key"] = args.feature_key
    if args.project:
        context["browserstack_project"] = args.project
    if args.folder_id:
        context["resolved_folders"] = args.folder_id

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(context, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(tests)} regression case(s) → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
