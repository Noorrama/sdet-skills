#!/usr/bin/env python3
"""
Build a deterministic coverage checklist from extractor contexts (Step 4a).

Feature-agnostic: works for any app/feature that supplies prd_context (+ optional
design_context, rfc_context). Output drives validate_sdet_deliverables.py.

Usage:
  python3 build_coverage_checklist.py \\
    --prd prd_context.json \\
    [--design design_context.json] \\
    [--rfc rfc_context.json] \\
    [--out coverage_checklist.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _acceptance_criterion_count(req: dict[str, Any]) -> int:
    """Count distinct testable outcomes for one business requirement."""
    ac = req.get("acceptance_criteria")
    if isinstance(ac, list) and ac:
        return len(ac)
    copy = req.get("expected_ui_copy")
    if isinstance(copy, list) and copy:
        return len(copy)
    personas = req.get("target_personas")
    if isinstance(personas, list) and len(personas) > 1:
        return len(personas)
    return 1


def _ui_flow_path_count(design: dict[str, Any]) -> int:
    ui_flow = design.get("ui_flow") or []
    if not isinstance(ui_flow, list) or not ui_flow:
        return 0
    screens = design.get("screens") or []
    screen_ids = {s.get("screen_id") for s in screens if isinstance(s, dict)}
    paths = 0
    for edge in ui_flow:
        if not isinstance(edge, dict):
            continue
        to_id = edge.get("to_screen_id") or edge.get("to")
        if to_id and (not screen_ids or to_id in screen_ids):
            paths += 1
    return max(paths, 1 if len(ui_flow) >= 2 else 0)


def _distinct_screens(prd: dict[str, Any]) -> int:
    screens: set[str] = set()
    for req in prd.get("business_requirements") or []:
        if not isinstance(req, dict):
            continue
        cs = req.get("context_screen")
        if cs:
            screens.add(str(cs).strip())
        for item in req.get("expected_ui_copy") or []:
            if isinstance(item, dict) and item.get("screen"):
                screens.add(str(item["screen"]).strip())
    return len(screens)


def _flags(rfc: dict[str, Any], prd: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for entry in rfc.get("experimentation_matrix") or []:
        if isinstance(entry, dict) and entry.get("flag_key"):
            keys.append(str(entry["flag_key"]))
    if not keys:
        for entry in prd.get("feature_flags") or []:
            if entry:
                keys.append(str(entry))
    return keys


def _lifecycle_events(rfc: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for entry in rfc.get("lifecycle_considerations") or []:
        if isinstance(entry, dict) and entry.get("event"):
            out.append(str(entry["event"]))
    return out


def _clickstream_defined(prd: dict[str, Any], rfc: dict[str, Any]) -> bool:
    """True only when inputs carry concrete event names/schema — not placeholder refs."""

    def _events_usable(events: Any) -> bool:
        if not isinstance(events, list) or not events:
            return False
        for ev in events:
            if isinstance(ev, dict):
                name = ev.get("event_name") or ev.get("name") or ev.get("event")
                if name and str(name).strip():
                    return True
            elif isinstance(ev, str):
                low = ev.lower()
                if any(
                    p in low
                    for p in (
                        "not specified",
                        "not defined",
                        "details not",
                        "no event",
                        "tbd",
                        "see jira",
                    )
                ):
                    continue
                if len(ev.strip()) > 3:
                    return True
        return False

    if _events_usable(prd.get("clickstream_events")):
        return True
    obs = (rfc.get("cross_cutting_concerns") or {}).get("observability") or {}
    return _events_usable(obs.get("clickstream_events"))


def _category_selected(plan: dict[str, Any] | None, needle: str) -> bool:
    if not plan:
        return False
    cats = plan.get("coverage_categories") or {}
    auto = cats.get("auto_selected") or []
    extra = cats.get("optional_extras_selected") or []
    for block in auto + extra:
        if isinstance(block, dict):
            cat = str(block.get("category", "")).lower()
            if needle in cat:
                return True
    return False


def build_checklist(
    prd: dict[str, Any],
    design: dict[str, Any] | None = None,
    rfc: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    design = design or {}
    rfc = rfc or {}

    requirements = prd.get("business_requirements") or []
    boundaries = prd.get("boundary_conditions") or []

    checklist: list[dict[str, Any]] = []

    for req in requirements:
        if not isinstance(req, dict):
            continue
        req_id = req.get("req_id") or "UNKNOWN"
        ac_count = _acceptance_criterion_count(req)
        for i in range(ac_count):
            suffix = f":ac[{i}]" if ac_count > 1 else ""
            checklist.append(
                {
                    "id": f"{req_id}{suffix}",
                    "type": "acceptance_criterion" if ac_count > 1 else "requirement",
                    "req_id": req_id,
                    "min_scenarios": 1,
                }
            )

    for i, bc in enumerate(boundaries):
        if not isinstance(bc, dict):
            continue
        req_id = bc.get("req_id") or "UNKNOWN"
        checklist.append(
            {
                "id": f"{req_id}:boundary_conditions[{i}]",
                "type": "boundary",
                "req_id": req_id,
                "min_scenarios": 1,
            }
        )

    for event in _lifecycle_events(rfc):
        checklist.append(
            {
                "id": event,
                "type": "lifecycle",
                "min_scenarios": 1,
            }
        )

    for flag in _flags(rfc, prd):
        checklist.append(
            {
                "id": flag,
                "type": "feature_flag",
                "min_scenarios": 1,
            }
        )

    ui_paths = _ui_flow_path_count(design)
    distinct_screens = _distinct_screens(prd)
    min_e2e = 0
    if ui_paths >= 1:
        min_e2e = max(min_e2e, 1)
    if distinct_screens >= 3 and len(requirements) >= 2:
        min_e2e = max(min_e2e, 1)

    telemetry_allowed = _clickstream_defined(prd, rfc)

    return {
        "feature_key": prd.get("feature_key") or (plan or {}).get("feature_metadata", {}).get(
            "feature_key", "unknown"
        ),
        "checklist": checklist,
        "summary": {
            "requirement_count": len(requirements),
            "checklist_item_count": len(checklist),
            "boundary_count": len(boundaries),
            "min_e2e_scenarios": min_e2e,
            "min_total_scenarios_floor": len(checklist),
            "telemetry_scenarios_allowed": telemetry_allowed,
            "distinct_prd_screens": distinct_screens,
            "ui_flow_edges": ui_paths,
        },
        "rules_version": "1.0.0",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SDET coverage checklist from contexts")
    parser.add_argument("--prd", required=True, type=Path, help="prd_context.json path")
    parser.add_argument("--design", type=Path, help="design_context.json path")
    parser.add_argument("--rfc", type=Path, help="rfc_context.json path")
    parser.add_argument("--plan", type=Path, help="Optional draft SDET plan (for categories)")
    parser.add_argument("--out", type=Path, help="Write checklist JSON here (default: stdout)")
    args = parser.parse_args()

    prd = _load(args.prd)
    if not prd:
        print("ERROR: --prd file missing or empty", file=sys.stderr)
        return 1

    result = build_checklist(
        prd,
        design=_load(args.design),
        rfc=_load(args.rfc),
        plan=_load(args.plan),
    )

    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
