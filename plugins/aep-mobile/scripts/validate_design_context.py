#!/usr/bin/env python3
"""
Validate design_context.json: jsonschema + cross-field rules + optional fixture spot-checks.

Exit 0 = pass (warnings may still print unless --strict).
Exit 1 = schema or ERROR-level cross-field failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

FIXTURE_SPOT_CHECKS: Dict[str, List[Tuple[str, str]]] = {
    "gofood-group-order-bundling": [
        ("LANDING", "Create & invite friends"),
        ("LANDING", "Everyone pays for their items"),
        ("LANDING", "Everyone pays an equal share"),
        ("LANDING", "You pay for everyone"),
        ("LANDING", "Learn more"),
    ],
}


def load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def validate_schema(doc: Dict[str, Any], schema_path: Path) -> List[str]:
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema package not installed (pip install jsonschema)"]
    schema = load_json(schema_path)
    validator = jsonschema.Draft7Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.path)):
        errors.append(f"schema: {err.message} at {list(err.path)}")
    return errors


def screen_index(doc: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {s["screen_id"]: s for s in doc.get("screens") or []}


def cross_field_validate(doc: Dict[str, Any], strict: bool) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    screens = screen_index(doc)
    screen_ids: Set[str] = set(screens.keys())

    for i, edge in enumerate(doc.get("ui_flow") or []):
        from_id = edge.get("from_screen_id")
        to_id = edge.get("to_screen_id")
        if from_id != "ENTRY" and from_id not in screen_ids:
            errors.append(f"ui_flow[{i}].from_screen_id unknown screen {from_id}")
        if to_id not in screen_ids:
            errors.append(f"ui_flow[{i}].to_screen_id unknown screen {to_id}")

        trig = edge.get("trigger_element_id")
        trig_ref = edge.get("trigger_source_ref")
        if trig:
            scr = screens.get(from_id)
            if not scr:
                continue
            matches = [e for e in scr.get("elements") or [] if e.get("element_id") == trig]
            if not matches:
                errors.append(
                    f"ui_flow[{i}].trigger_element_id {trig} not on screen {from_id}"
                )
            elif trig_ref:
                ref_match = [e for e in matches if e.get("source_ref") == trig_ref]
                if not ref_match:
                    warnings.append(
                        f"ui_flow[{i}].trigger_source_ref {trig_ref} "
                        f"does not match element {trig} on {from_id}"
                    )
        elif from_id != "ENTRY":
            warnings.append(
                f"ui_flow[{i}] ({from_id} -> {to_id}) has no trigger_element_id"
            )

    for scr in doc.get("screens") or []:
        sid = scr["screen_id"]
        seen: Dict[str, List[Dict[str, Any]]] = {}
        for el in scr.get("elements") or []:
            eid = el.get("element_id")
            seen.setdefault(eid, []).append(el)
        for eid, group in seen.items():
            if len(group) < 2:
                continue
            refs = {g.get("source_ref") for g in group}
            labels = {g.get("label") for g in group}
            if len(refs) > 1 and len(labels) == 1:
                warnings.append(
                    f"screens.{sid}.elements duplicate {eid} with same label "
                    f"and different source_ref ({len(refs)} refs)"
                )

    if strict and warnings:
        errors.extend(warnings)
        warnings = []
    return errors, warnings


def spot_check_fixture(doc: Dict[str, Any], fixture: str) -> List[str]:
    checks = FIXTURE_SPOT_CHECKS.get(fixture)
    if not checks:
        return [f"unknown fixture name: {fixture}"]
    failures: List[str] = []
    screens = screen_index(doc)
    for screen_id, substring in checks:
        scr = screens.get(screen_id)
        if not scr:
            failures.append(f"spot-check: missing screen {screen_id}")
            continue
        labels = " ".join(str(e.get("label") or "") for e in scr.get("elements") or [])
        if substring.lower() not in labels.lower():
            failures.append(
                f"spot-check: screen {screen_id} missing label substring '{substring}'"
            )
    return failures


def validate_extraction_status(doc: Dict[str, Any], strict: bool) -> Tuple[List[str], List[str]]:
    """WARN when extraction_status claims OK but gaps/screens contradict; strict promotes to ERROR."""
    errors: List[str] = []
    warnings: List[str] = []
    status = doc.get("extraction_status")
    if status != "OK":
        return errors, warnings

    gaps = doc.get("extraction_gaps") or []
    if gaps:
        msg = (
            "extraction_status is OK but extraction_gaps is non-empty "
            f"({len(gaps)} gap(s))"
        )
        if strict:
            errors.append(msg)
        else:
            warnings.append(msg)

    screens = doc.get("screens") or []
    if not screens:
        msg = "extraction_status is OK but screens[] is empty"
        if strict:
            errors.append(msg)
        else:
            warnings.append(msg)

    blocking = [g for g in gaps if g.get("severity") == "BLOCKING"]
    if blocking:
        msg = (
            f"extraction_status is OK but {len(blocking)} BLOCKING gap(s) present"
        )
        if strict:
            errors.append(msg)
        else:
            warnings.append(msg)

    return errors, warnings


def validate_entry_edges(doc: Dict[str, Any], strict: bool) -> Tuple[List[str], List[str]]:
    """WARN if ENTRY edges target screens without entry_point; strict promotes to ERROR."""
    errors: List[str] = []
    warnings: List[str] = []
    screens = screen_index(doc)
    for i, edge in enumerate(doc.get("ui_flow") or []):
        if edge.get("from_screen_id") != "ENTRY":
            continue
        to_id = edge.get("to_screen_id")
        target = screens.get(to_id or "")
        if not target:
            continue
        if not target.get("entry_point"):
            msg = (
                f"ui_flow[{i}] ENTRY -> {to_id}: screens.{to_id}.entry_point is not true"
            )
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)
    return errors, warnings


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate design_context.json")
    parser.add_argument("design_context", type=Path)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--fixture", type=str, default=None)
    parser.add_argument("--strict", action="store_true", help="Treat WARN cross-field as failure")
    args = parser.parse_args(argv)

    doc = load_json(args.design_context)
    schema_errors = validate_schema(doc, args.schema)
    if schema_errors:
        for e in schema_errors:
            print(e, file=sys.stderr)
        return 1

    errors, warnings = cross_field_validate(doc, args.strict)
    status_errors, status_warnings = validate_extraction_status(doc, args.strict)
    errors.extend(status_errors)
    warnings.extend(status_warnings)
    entry_errors, entry_warnings = validate_entry_edges(doc, args.strict)
    errors.extend(entry_errors)
    warnings.extend(entry_warnings)
    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if args.fixture:
        spot_failures = spot_check_fixture(doc, args.fixture)
        if spot_failures:
            for f in spot_failures:
                print(f"ERROR: {f}", file=sys.stderr)
            return 1
        entry_edges = [e for e in doc.get("ui_flow") or [] if e.get("from_screen_id") == "ENTRY"]
        if args.fixture == "gofood-group-order-bundling":
            if not entry_edges:
                msg = "fixture gofood-group-order-bundling: missing ENTRY ui_flow edge"
                if args.strict:
                    print(f"ERROR: {msg}", file=sys.stderr)
                    return 1
                print(f"WARN: {msg}")
        print(f"Spot-check fixture '{args.fixture}' passed.")

    triggers = sum(1 for e in doc.get("ui_flow") or [] if e.get("trigger_element_id"))
    total = len(doc.get("ui_flow") or [])
    print(f"ui_flow trigger coverage: {triggers}/{total}")
    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
