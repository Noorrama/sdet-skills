#!/usr/bin/env python3
"""Recover design_context.json by applying id_refinement_map.json renames.

Consumes the ``id_refinement_map.json`` produced by the Step 3 agent review
(see SKILL.md) and rewrites ``element_id`` / ``trigger_element_id`` values in
``design_context.temp.json`` accordingly, producing the final ``design_context.json``.

Only refinements whose ``confidence`` is ``"medium"`` or ``"high"`` are
applied; ``low``-confidence proposals are reported but left untouched.

Accepted refinement keys (both spellings work):

- source element:  ``old_id`` or ``target_element_id``
- replacement:     ``suggested_id`` or ``new_element_id``

Matching rules
--------------
- Elements are matched by ``(screen_id, element_id)``. If a refinement entry
  carries a ``source_ref``, it must also match when present.
- Every ``ui_flow`` edge whose ``trigger_element_id`` equals an applied
  ``old_id`` on the same screen is renamed too.
- If the suggested id already exists on the target screen, the rename is
  skipped and reported as a conflict.

Usage
-----
    python3 recover_design_context.py \\
        --refinements <workdir>/id_refinement_map.json \\
        [-w <workdir>] \\
        [-c <workdir>/design_context.temp.json]  # default input \\
        [-o <workdir>/design_context.json]       # default output

The recovered context is revalidated against the plugin-level schema before
being written.
"""

import argparse
import copy
import json
import os
import sys

APPLIED_CONFIDENCES = {"medium", "high"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_refinements(refinements_doc: dict | list) -> list:
    """Accept either the full map document or a bare list of refinements."""
    if isinstance(refinements_doc, list):
        return refinements_doc
    return refinements_doc.get("refinements") or []


def rename_key(old: str, new: str):
    """Return a decorator that recursively renames string values under keys."""
    def _walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key_field and v == old:
                    node[k] = new
                else:
                    _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)
    return _walk


def apply_refinement(context: dict, ref: dict) -> tuple[str, str]:
    """Apply one refinement.

    Returns ``(status, detail)`` where status is one of
    ``applied``, ``skipped_confidence``, ``skipped_not_found``,
    ``skipped_conflict``.
    """
    confidence = str(ref.get("confidence", "")).lower()
    if confidence not in APPLIED_CONFIDENCES:
        return ("skipped_confidence",
                f"confidence '{confidence or 'missing'}' not in "
                f"{sorted(APPLIED_CONFIDENCES)}")

    screen_id = ref.get("screen_id")
    old_id = ref.get("old_id") or ref.get("target_element_id")
    new_id = ref.get("suggested_id") or ref.get("new_element_id")

    if not (screen_id and old_id and new_id):
        return ("skipped_not_found",
                "refinement missing required fields "
                "(screen_id, old_id/target_element_id, suggested_id)")

    if old_id == new_id:
        return ("skipped_confidence", "old_id == suggested_id; nothing to do")

    screens = [s for s in context.get("screens", [])
               if s.get("screen_id") == screen_id]
    if not screens:
        return ("skipped_not_found", f"no screens with screen_id '{screen_id}'")

    # Conflict check: suggested id must not already exist on that screen.
    for s in screens:
        for el in s.get("elements", []):
            if el.get("element_id") == new_id:
                return ("skipped_conflict",
                        f"suggested_id '{new_id}' already exists on "
                        f"'{screen_id}'")

    source_ref = ref.get("source_ref")
    renamed_elements = 0
    for s in screens:
        for el in s.get("elements", []):
            if el.get("element_id") != old_id:
                continue
            if source_ref and el.get("source_ref") != source_ref:
                continue
            el["element_id"] = new_id
            renamed_elements += 1

    # Rename matching ui_flow triggers on the same screen.
    renamed_edges = 0
    for edge in context.get("ui_flow", []):
        if edge.get("trigger_element_id") == old_id:
            from_screen = edge.get("from_screen_id")
            if from_screen is None or from_screen == screen_id:
                edge["trigger_element_id"] = new_id
                renamed_edges += 1

    if renamed_elements == 0 and renamed_edges == 0:
        return ("skipped_not_found",
                f"'{old_id}' not found on screen '{screen_id}'"
                + (f" with source_ref '{source_ref}'" if source_ref else ""))

    return ("applied",
            f"{renamed_elements} element(s), {renamed_edges} ui_flow edge(s)")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate(output: dict, schema_path: str) -> bool:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        print("WARNING: jsonschema not installed — skipping schema validation.",
              file=sys.stderr)
        return True

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.validate(instance=output, schema=schema)
        return True
    except jsonschema.ValidationError as exc:
        print(f"ERROR: Schema validation failed: {exc.message}", file=sys.stderr)
        print(f"  at path: {list(exc.absolute_path)}", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"ERROR: Could not validate schema: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def recover(context_path: str, refinements_path: str, output_path: str,
            in_place: bool = False) -> None:
    context = load_json(context_path)
    refinements_doc = load_json(refinements_path)
    refinements = normalize_refinements(refinements_doc)

    results = []
    counts = {"applied": 0, "skipped_confidence": 0,
              "skipped_not_found": 0, "skipped_conflict": 0}

    for ref in refinements:
        status, detail = apply_refinement(context, ref)
        counts[status] += 1
        label = (ref.get("old_id") or ref.get("target_element_id") or "?")
        new_id = (ref.get("suggested_id") or ref.get("new_element_id") or "?")
        results.append((status, f"{ref.get('screen_id', '?')}: "
                                f"{label} -> {new_id} :: {detail}"))

    # --- Schema validation ---
    skill_dir = os.path.dirname(os.path.abspath(__file__))
    schema_path = os.path.join(skill_dir, "..", "..", "schemas",
                               "design_context.schema.json")
    schema_path = os.path.normpath(schema_path)
    valid = validate(context, schema_path)

    # --- Write output ---
    target = context_path if (in_place or not output_path) else output_path
    if target == context_path and not in_place:
        target = context_path.replace(".json", ".recovered.json")
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)

    print(f"Read   {context_path}")
    print(f"Map    {refinements_path} ({len(refinements)} refinement(s))")
    for status, msg in results:
        marker = {"applied": "✓", "skipped_confidence": "-",
                  "skipped_not_found": "?", "skipped_conflict": "!"}[status]
        print(f"  [{marker}] {status}: {msg}")
    print(f"Wrote  {target}")
    print(f"  applied:            {counts['applied']}")
    print(f"  skipped (confidence): {counts['skipped_confidence']}")
    print(f"  skipped (not found):  {counts['skipped_not_found']}")
    print(f"  skipped (conflict):   {counts['skipped_conflict']}")
    print(f"  schema valid:       {valid}")

    if not valid:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Apply id_refinement_map.json renames to design_context.temp.json. "
            "Only 'medium'/'high' confidence refinements are applied."
        )
    )
    parser.add_argument(
        "--workdir", "-w",
        metavar="WORKDIR",
        help="Working directory. Defaults to directory of --refinements file.",
    )
    parser.add_argument(
        "--refinements", "-r", required=True, metavar="REFINEMENT_MAP_JSON",
        help="Path to the id_refinement_map.json produced by the Step 3 review.",
    )
    parser.add_argument(
        "--context", "-c", metavar="DESIGN_CONTEXT_JSON",
        help="Path to the design_context.temp.json to update. Defaults to <workdir>/design_context.temp.json.",
    )
    parser.add_argument(
        "--output", "-o", metavar="OUTPUT_JSON",
        help="Destination path. Defaults to <workdir>/design_context.json.",
    )

    args = parser.parse_args()
    # Resolve workdir
    if args.workdir:
        workdir = args.workdir
    else:
        workdir = os.path.dirname(os.path.abspath(args.refinements))
    # Resolve context path
    if args.context:
        context_path = args.context
    else:
        context_path = os.path.join(workdir, "design_context.temp.json")
    # Resolve output path
    if args.output:
        output_path = args.output
    else:
        output_path = os.path.join(workdir, "design_context.json")
    recover(context_path, args.refinements, output_path, in_place=False)


if __name__ == "__main__":
    main()
