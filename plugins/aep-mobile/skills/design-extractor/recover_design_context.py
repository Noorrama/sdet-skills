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
- When multiple elements share ``(screen_id, old_id)``, ``source_ref`` is
  required; otherwise the refinement is skipped as ambiguous.
- Every ``ui_flow`` edge whose ``trigger_element_id`` equals an applied
  ``old_id`` on the same screen frame is renamed too.
- If the suggested id already exists on the target screen, the rename is
  skipped and reported as a conflict.
- After all refinements, duplicate ``element_id`` values on the same logical
  screen (different ``source_ref``) cause validation to fail.

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

from __future__ import annotations

import argparse
import copy
import json
import os
import sys

from extract_design_context import (
    find_duplicate_element_ids,
    merge_semantic_elements,
)

APPLIED_CONFIDENCES = {"medium", "high"}
EMPTY_REFINEMENT_MAP: dict = {"refinements": []}
EMPTY_COLLAPSE_MAP: dict = {"auto_collapsed": [], "candidates": [], "decisions": []}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_refinement_map_scaffold(path: str) -> None:
    """Write an empty id_refinement_map.json scaffold."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(EMPTY_REFINEMENT_MAP, f, ensure_ascii=False, indent=2)


def write_screen_collapse_map_scaffold(path: str) -> None:
    """Write an empty screen_collapse_map.json scaffold."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(EMPTY_COLLAPSE_MAP, f, ensure_ascii=False, indent=2)


def ensure_screen_collapse_map(path: str) -> str:
    """Return collapse map path, creating an empty scaffold when missing."""
    if not os.path.exists(path):
        write_screen_collapse_map_scaffold(path)
    return path


def ensure_refinement_map(path: str) -> str:
    """Return refinements path, creating an empty scaffold when missing."""
    if not os.path.exists(path):
        write_refinement_map_scaffold(path)
    return path


def finalize_design_context(
    workdir: str,
    *,
    context_path: str | None = None,
    refinements_path: str | None = None,
    output_path: str | None = None,
    reset_refinements: bool = True,
) -> None:
    """Always emit id_refinement_map.json and design_context.json for a workdir."""
    context_path = context_path or os.path.join(workdir, "design_context.temp.json")
    refinements_path = refinements_path or os.path.join(workdir, "id_refinement_map.json")
    output_path = output_path or os.path.join(workdir, "design_context.json")
    if reset_refinements:
        write_refinement_map_scaffold(refinements_path)
    else:
        ensure_refinement_map(refinements_path)
    recover(context_path, refinements_path, output_path, in_place=False)


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


def count_refinement_targets(
    screens: list,
    screen_id: str,
    old_id: str,
    source_ref: str | None = None,
) -> int:
    """Count elements that would match a refinement before it is applied."""
    count = 0
    for screen in screens:
        if screen.get("screen_id") != screen_id:
            continue
        for el in screen.get("elements", []):
            if el.get("element_id") != old_id:
                continue
            if source_ref and el.get("source_ref") != source_ref:
                continue
            count += 1
    return count


def apply_refinement(context: dict, ref: dict) -> tuple[str, str]:
    """Apply one refinement.

    Returns ``(status, detail)`` where status is one of
    ``applied``, ``skipped_confidence``, ``skipped_not_found``,
    ``skipped_conflict``, ``skipped_ambiguous``.
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

    source_ref = ref.get("source_ref")
    match_count = count_refinement_targets(screens, screen_id, old_id, source_ref)
    if match_count == 0:
        return ("skipped_not_found",
                f"'{old_id}' not found on screen '{screen_id}'"
                + (f" with source_ref '{source_ref}'" if source_ref else ""))
    if not source_ref:
        ambiguous_count = count_refinement_targets(screens, screen_id, old_id)
        if ambiguous_count > 1:
            return ("skipped_ambiguous",
                    f"'{old_id}' matches {ambiguous_count} elements on "
                    f"'{screen_id}'; provide source_ref to disambiguate")

    # Conflict check: suggested id must not already exist on that screen.
    for s in screens:
        for el in s.get("elements", []):
            if el.get("element_id") == new_id:
                return ("skipped_conflict",
                        f"suggested_id '{new_id}' already exists on "
                        f"'{screen_id}'")

    target_frame_refs: set[str] = set()
    renamed_elements = 0
    for s in screens:
        for el in s.get("elements", []):
            if el.get("element_id") != old_id:
                continue
            if source_ref and el.get("source_ref") != source_ref:
                continue
            frame_ref = s.get("source_ref")
            if frame_ref:
                target_frame_refs.add(frame_ref)
            el["element_id"] = new_id
            renamed_elements += 1

    # Rename matching ui_flow triggers scoped by trigger_source_ref or frame.
    renamed_edges = 0
    for edge in context.get("ui_flow", []):
        if edge.get("trigger_element_id") != old_id:
            continue
        if edge.get("from_screen_id") not in (None, screen_id):
            continue
        trigger_ref = edge.get("trigger_source_ref")
        if source_ref and trigger_ref:
            if trigger_ref != source_ref:
                continue
        elif source_ref:
            frame_ref = edge.get("from_source_ref")
            if target_frame_refs and frame_ref not in target_frame_refs:
                continue
        elif target_frame_refs:
            frame_ref = edge.get("from_source_ref")
            if frame_ref not in target_frame_refs:
                continue
        edge["trigger_element_id"] = new_id
        renamed_edges += 1

    if renamed_elements == 0 and renamed_edges == 0:
        return ("skipped_not_found",
                f"'{old_id}' not found on screen '{screen_id}'"
                + (f" with source_ref '{source_ref}'" if source_ref else ""))

    return ("applied",
            f"{renamed_elements} element(s), {renamed_edges} ui_flow edge(s)")


def apply_screen_collapse(context: dict, collapse_map: dict) -> list[tuple[str, str]]:
    """Merge screens per agent collapse decisions before id refinements."""
    screens = context.get("screens", [])
    results: list[tuple[str, str]] = []

    for decision in collapse_map.get("decisions") or []:
        if decision.get("action") != "collapse":
            continue

        confidence = str(decision.get("confidence", "")).lower()
        if confidence not in APPLIED_CONFIDENCES:
            results.append((
                "skipped_confidence",
                f"confidence '{confidence or 'missing'}' not in "
                f"{sorted(APPLIED_CONFIDENCES)}",
            ))
            continue

        screen_id = decision.get("screen_id")
        frame_ids = set(decision.get("frame_ids") or [])
        if not screen_id or not frame_ids:
            results.append(("skipped_not_found", "missing screen_id or frame_ids"))
            continue

        matching = []
        for screen in screens:
            if screen.get("screen_id") != screen_id:
                continue
            refs = set(screen.get("source_refs") or [screen.get("source_ref")])
            if refs & frame_ids:
                matching.append(screen)

        if len(matching) <= 1:
            results.append((
                "skipped_not_found",
                f"found {len(matching)} screen record(s) for '{screen_id}'",
            ))
            continue

        rep = matching[0]
        all_frame_ids = set(rep.get("source_refs") or [rep.get("source_ref")])
        merged_elements = list(rep.get("elements") or [])
        merged_states = list(rep.get("screen_states") or [])
        merged_kinds = list(rep.get("state_kinds") or [])
        notes_parts = [rep.get("screen_notes", "")] if rep.get("screen_notes") else []
        entry_point = rep.get("entry_point", False)

        for screen in matching[1:]:
            all_frame_ids.update(screen.get("source_refs") or [screen.get("source_ref")])
            for state in screen.get("screen_states") or []:
                if state not in merged_states:
                    merged_states.append(state)
            for kind in screen.get("state_kinds") or []:
                if kind not in merged_kinds:
                    merged_kinds.append(kind)
            if screen.get("screen_notes") and screen["screen_notes"] not in notes_parts:
                notes_parts.append(screen["screen_notes"])
            entry_point = entry_point or screen.get("entry_point", False)
            frame_state = (screen.get("screen_states") or [None])[0]
            for el in screen.get("elements") or []:
                tagged = dict(el)
                if not tagged.get("states_represented") and frame_state:
                    tagged["states_represented"] = [frame_state]
                tagged["_frame_qualifier"] = frame_state
                merged_elements.append(tagged)
            screens.remove(screen)

        for el in merged_elements:
            if not el.get("states_represented") and el.get("_frame_qualifier"):
                el["states_represented"] = [el["_frame_qualifier"]]

        rep["source_refs"] = sorted(all_frame_ids)
        rep["source_ref"] = (
            decision.get("representative_frame")
            or rep.get("source_ref")
            or sorted(all_frame_ids)[0]
        )
        rep["screen_states"] = merged_states
        rep["state_kinds"] = merged_kinds
        rep["screen_notes"] = " | ".join(n for n in notes_parts if n)[:300]
        rep["entry_point"] = entry_point
        rep["elements"] = merge_semantic_elements(merged_elements)
        results.append((
            "applied",
            f"merged {len(matching)} screen record(s) for '{screen_id}'",
        ))

    context["screens"] = screens
    return results


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
            in_place: bool = False,
            collapse_map_path: str | None = None) -> bool:
    refinements_path = ensure_refinement_map(refinements_path)
    context = load_json(context_path)
    refinements_doc = load_json(refinements_path)
    refinements = normalize_refinements(refinements_doc)

    collapse_results: list[tuple[str, str]] = []
    if collapse_map_path and os.path.exists(collapse_map_path):
        collapse_map = load_json(collapse_map_path)
        collapse_results = apply_screen_collapse(context, collapse_map)

    results = []
    counts = {"applied": 0, "skipped_confidence": 0,
              "skipped_not_found": 0, "skipped_conflict": 0,
              "skipped_ambiguous": 0}

    for ref in refinements:
        status, detail = apply_refinement(context, ref)
        counts[status] = counts.get(status, 0) + 1
        label = (ref.get("old_id") or ref.get("target_element_id") or "?")
        new_id = (ref.get("suggested_id") or ref.get("new_element_id") or "?")
        results.append((status, f"{ref.get('screen_id', '?')}: "
                                f"{label} -> {new_id} :: {detail}"))

    duplicate_ids = find_duplicate_element_ids(context.get("screens", []))
    unique_ids_valid = len(duplicate_ids) == 0

    # --- Schema validation ---
    skill_dir = os.path.dirname(os.path.abspath(__file__))
    schema_path = os.path.join(skill_dir, "..", "..", "schemas",
                               "design_context.schema.json")
    schema_path = os.path.normpath(schema_path)
    valid = validate(context, schema_path) and unique_ids_valid

    # --- Write output ---
    target = context_path if (in_place or not output_path) else output_path
    if target == context_path and not in_place:
        target = context_path.replace(".json", ".recovered.json")
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)

    print(f"Read   {context_path}")
    print(f"Map    {refinements_path} ({len(refinements)} refinement(s))")
    if collapse_map_path:
        print(f"Collapse {collapse_map_path} ({len(collapse_results)} decision(s) processed)")
        for status, msg in collapse_results:
            marker = {"applied": "✓", "skipped_confidence": "-",
                      "skipped_not_found": "?"}[status]
            print(f"  [{marker}] collapse {status}: {msg}")
    for status, msg in results:
        marker = {"applied": "✓", "skipped_confidence": "-",
                  "skipped_not_found": "?", "skipped_conflict": "!",
                  "skipped_ambiguous": "~"}[status]
        print(f"  [{marker}] {status}: {msg}")
    if duplicate_ids:
        print("ERROR: Duplicate element_id values remain after refinements:",
              file=sys.stderr)
        for dup in duplicate_ids:
            refs = ", ".join(dup["source_refs"])
            print(f"  {dup['screen_id']}.{dup['element_id']}: {refs}",
                  file=sys.stderr)
    print(f"Wrote  {target}")
    print(f"  applied:            {counts['applied']}")
    print(f"  skipped (confidence): {counts['skipped_confidence']}")
    print(f"  skipped (not found):  {counts['skipped_not_found']}")
    print(f"  skipped (conflict):   {counts['skipped_conflict']}")
    print(f"  skipped (ambiguous):  {counts.get('skipped_ambiguous', 0)}")
    print(f"  unique element_ids: {unique_ids_valid}")
    print(f"  schema valid:       {valid}")

    if not valid:
        sys.exit(1)
    return valid


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Apply id_refinement_map.json renames to design_context.temp.json. "
            "Only 'medium'/'high' confidence refinements are applied."
        )
    )
    parser.add_argument(
        "--write-scaffold",
        action="store_true",
        help=(
            "Write an empty id_refinement_map.json to the workdir and exit. "
            "Used by run_design_extractor.py Step 3."
        ),
    )
    parser.add_argument(
        "--write-collapse-scaffold",
        action="store_true",
        help=(
            "Write an empty screen_collapse_map.json to the workdir and exit. "
            "Used by run_design_extractor.py Step 3b when Step 2 did not emit one."
        ),
    )
    parser.add_argument(
        "--workdir", "-w",
        metavar="WORKDIR",
        help="Working directory. Defaults to directory of --refinements file.",
    )
    parser.add_argument(
        "--refinements", "-r", metavar="REFINEMENT_MAP_JSON",
        help=(
            "Path to id_refinement_map.json. Defaults to "
            "<workdir>/id_refinement_map.json; an empty scaffold is created "
            "when the file is missing."
        ),
    )
    parser.add_argument(
        "--context", "-c", metavar="DESIGN_CONTEXT_JSON",
        help="Path to the design_context.temp.json to update. Defaults to <workdir>/design_context.temp.json.",
    )
    parser.add_argument(
        "--collapse-map", metavar="SCREEN_COLLAPSE_MAP_JSON",
        help=(
            "Path to screen_collapse_map.json. Defaults to "
            "<workdir>/screen_collapse_map.json when present."
        ),
    )
    parser.add_argument(
        "--output", "-o", metavar="OUTPUT_JSON",
        help="Destination path. Defaults to <workdir>/design_context.json.",
    )

    args = parser.parse_args()
    if args.write_scaffold:
        if not args.workdir:
            parser.error("--write-scaffold requires --workdir")
        refinements_path = os.path.join(args.workdir, "id_refinement_map.json")
        write_refinement_map_scaffold(refinements_path)
        print(f"Wrote {refinements_path} (empty scaffold)")
        return
    if args.write_collapse_scaffold:
        if not args.workdir:
            parser.error("--write-collapse-scaffold requires --workdir")
        collapse_path = os.path.join(args.workdir, "screen_collapse_map.json")
        write_screen_collapse_map_scaffold(collapse_path)
        print(f"Wrote {collapse_path} (empty scaffold)")
        return
    if not args.refinements and not args.workdir:
        parser.error("one of --refinements or --workdir is required")
    # Resolve workdir
    if args.workdir:
        workdir = args.workdir
    elif args.refinements:
        workdir = os.path.dirname(os.path.abspath(args.refinements))
    else:
        workdir = "."
    # Resolve refinements path
    if args.refinements:
        refinements_path = args.refinements
    else:
        refinements_path = os.path.join(workdir, "id_refinement_map.json")
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
    collapse_map_path = args.collapse_map
    if not collapse_map_path:
        default_collapse = os.path.join(workdir, "screen_collapse_map.json")
        if os.path.exists(default_collapse):
            collapse_map_path = default_collapse
    recover(
        context_path,
        refinements_path,
        output_path,
        in_place=False,
        collapse_map_path=collapse_map_path,
    )


if __name__ == "__main__":
    main()
