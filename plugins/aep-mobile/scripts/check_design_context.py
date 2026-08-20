#!/usr/bin/env python3
"""Post-run self-check for design_context.json.

This replaces a prose checklist. A model asked to walk nine bullets skips them —
a real run reported `blocking_issues: []` while dropping 41 of 47 connectors, and
passed schema validation while doing it. Every check here is one the schema
cannot express or a model demonstrably got wrong.

    ./check_design_context.py design_context.json --schema ../schemas/design_context.schema.json

Prints one line per failure and exits non-zero; prints OK and a summary otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from typing import Any

# Buckets every connector must land in exactly once. Mirrors CONSERVED_BUCKETS
# in extract_design_context.py.
CONSERVED_BUCKETS = (
    "connectors_resolved_to_screen",
    "connectors_inferred_to_screen",
    "connectors_unresolvable",
    "connectors_intra_screen",
    "connectors_to_decision",
    "note_connectors",
)

NOTE_BUCKETS = (
    "notes_attached_by_connector",
    "notes_attached_by_geometry",
    "notes_unattached",
)

# Fields describing intent rather than structure. A board carries them only when
# a designer wrote one down, so an empty one is never a BLOCKING gap.
INTENT_FIELDS = (
    "purpose",
    "screen_notes",
    "states_represented",
    "validations_and_edge_cases",
    "visual_analysis_scratchpad",
)

# Removed from the contract: nothing downstream reads them.
DROPPED_FIELDS = ("purpose", "states_represented")

ELEMENT_ID = re.compile(r"^[A-Z0-9_]+\.[a-z0-9_]+(\.[a-z0-9_]+)?$")
SCREEN_ID = re.compile(r"^[A-Z0-9_]+$")


def check(
    doc: dict[str, Any],
    schema: dict[str, Any] | None,
    report: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    skipped: list[str] = []
    screens = doc.get("screens") or []
    flow = doc.get("ui_flow") or []
    gaps = doc.get("extraction_gaps") or []
    # Tallies live in the sidecar now, not in the context file.
    compliance = (report or {}).get("convention_compliance") or {}

    # 1. Schema. Well-formed JSON is not conformance.
    if schema is not None:
        try:
            from jsonschema import Draft7Validator

            errors = sorted(
                Draft7Validator(schema).iter_errors(doc), key=lambda e: list(e.absolute_path)
            )
            for error in errors[:5]:
                path = ".".join(str(p) for p in error.absolute_path) or "$"
                failures.append(f"schema: {path}: {error.message[:120]}")
            if len(errors) > 5:
                failures.append(f"schema: … and {len(errors) - 5} more error(s)")
        except ImportError:
            failures.append(
                "schema: jsonschema not installed — cannot validate. "
                "Install with: pip3 install --break-system-packages jsonschema"
            )

    # 2. Duplicate screen_id. JSON Schema draft-07 cannot express uniqueness by
    # property, and this is the signature of state frames not being collapsed —
    # a run once emitted 94 screen objects for 33 screens with zero schema errors.
    ids = [s.get("screen_id") for s in screens]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        failures.append(
            f"duplicate screen_id: {', '.join(duplicates[:6])} — state frames were emitted as "
            f"separate screens instead of collapsed, which drops every flow drawn from the others"
        )

    # 3. Connector conservation.
    if compliance:
        total = compliance.get("connectors_total")
        summed = sum(compliance.get(b, 0) for b in CONSERVED_BUCKETS)
        if total is not None and summed != total:
            failures.append(
                f"connector conservation: buckets sum to {summed}, connectors_total is {total} — "
                f"{abs(total - summed)} connector(s) vanished without landing in a bucket"
            )

        # 4. Every counter present, including zeroes. An absent key and a zero
        # look identical to a reader, which is how a broken run passes review.
        missing = [b for b in CONSERVED_BUCKETS + NOTE_BUCKETS if b not in compliance]
        if missing:
            failures.append(
                f"convention_compliance missing {len(missing)} counter(s): {', '.join(missing[:6])} "
                f"— the block was written by hand rather than by the extractor"
            )

        # 5. Note accounting.
        notes_total = compliance.get("notes_total")
        note_sum = sum(compliance.get(b, 0) for b in NOTE_BUCKETS)
        if notes_total is not None and note_sum != notes_total:
            failures.append(
                f"note accounting: buckets sum to {note_sum}, notes_total is {notes_total} — "
                f"note extraction dropped {abs(notes_total - note_sum)} note(s) silently"
            )
    else:
        # No sidecar: say the checks did not run. A check that silently passes
        # when its input is missing is worse than one that reports SKIPPED.
        skipped.append(
            "connector conservation, counters-complete and note accounting — no --report sidecar "
            "supplied, so there was nothing to verify them against"
        )

    # 6. No BLOCKING gap on an intent field. This is the reported bug: a model
    # judging that an empty intent field is a blocker.
    for gap in gaps:
        field = gap.get("field", "")
        if gap.get("severity") == "BLOCKING" and any(f in field for f in INTENT_FIELDS):
            failures.append(
                f"BLOCKING gap on intent field {field!r} — a board carries these only when a "
                f"designer wrote one; empty is never blocking. Use INFO, or omit the gap"
            )

    # 7. Status and gaps must agree.
    status = doc.get("extraction_status")
    if status and status != "OK" and not gaps:
        failures.append(
            f"extraction_status is {status!r} but extraction_gaps is empty — say what was not resolved"
        )
    if status == "OK" and gaps:
        failures.append(f"extraction_status is OK but {len(gaps)} gap(s) are open")

    # 8. Dropped fields must not creep back.
    for name in DROPPED_FIELDS:
        if any(name in s for s in screens) or any(
            name in e for s in screens for e in (s.get("elements") or [])
        ):
            failures.append(
                f"{name!r} is present — it was removed from the contract (no downstream reader); "
                f"the extractor must not emit it"
            )

    # 9. Referential integrity: ids must resolve.
    known = {s.get("screen_id") for s in screens}
    for element in (e for s in screens for e in (s.get("elements") or [])):
        eid = element.get("element_id", "")
        if not ELEMENT_ID.match(eid):
            failures.append(f"element_id {eid!r} does not match <SCREEN_ID>.<element_role>")
        elif eid.split(".")[0] not in known:
            failures.append(f"element_id {eid!r} has no matching screen_id")
    for i, edge in enumerate(flow):
        for key in ("from_screen_id", "to_screen_id"):
            value = edge.get(key)
            if value not in known:
                failures.append(f"ui_flow[{i}].{key} {value!r} is not a screen_id in this file")
        if edge.get("from_screen_id") == edge.get("to_screen_id"):
            failures.append(
                f"ui_flow[{i}] is a self-loop on {edge.get('from_screen_id')!r} — an intra-screen "
                f"connector is a state change, not navigation"
            )

    return failures, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", help="design_context.json to check")
    parser.add_argument("--schema", help="path to design_context.schema.json")
    parser.add_argument("--report", help="path to the <design_context>.report.json sidecar")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as handle:
        doc = json.load(handle)
    schema = None
    if args.schema:
        with open(args.schema, encoding="utf-8") as handle:
            schema = json.load(handle)

    report = None
    if args.report:
        with open(args.report, encoding="utf-8") as handle:
            report = json.load(handle)

    failures, skipped = check(doc, schema, report)
    for note in skipped:
        print(f"SKIPPED — {note}", file=sys.stderr)
    if failures:
        print(f"FAILED — {len(failures)} problem(s) in {args.input}", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    screens = doc.get("screens") or []
    compliance = (report or {}).get("convention_compliance") or {}
    gaps = doc.get("extraction_gaps") or []
    print(
        f"OK — {len(screens)} screens, "
        f"{sum(len(s.get('elements') or []) for s in screens)} elements, "
        f"{len(doc.get('ui_flow') or [])} flow edges, "
        f"{compliance.get('connectors_total', '?')} connectors all accounted for, "
        f"{compliance.get('notes_total', 0)} notes "
        f"({compliance.get('notes_unattached', 0)} unattached), "
        f"{len(gaps)} gap(s): {Counter(g.get('severity') for g in gaps) or 'none'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
