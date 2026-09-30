#!/usr/bin/env python3
"""Extract design_context.json from a figma-design-bundle directory."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .elements import (
    collect_interactive_elements,
    dedupe_elements_by_source_ref,
    ensure_connector_source_element,
    is_loader_instance,
    merge_elements_by_source_ref,
)
from .entry_points import apply_entry_point_flags, build_entry_edges
from .gaps import (
    ambiguity_rating,
    blocking_issues_from_gaps,
    build_extraction_gaps,
    extraction_status,
)
from .screen_ids import manifest_id_to_screen_id
from .state_kinds import state_kinds_for_screen
from .tree_index import build_node_index


def load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def is_bundle_dir(path: Path) -> bool:
    manifest = path / "manifest.json"
    if not manifest.is_file():
        return False
    try:
        data = load_json(manifest)
    except (json.JSONDecodeError, OSError):
        return False
    gen = data.get("generator") or {}
    return gen.get("name") == "figma-design-bundle" and data.get("formatVersion") == 1


def load_manifest(bundle: Path) -> Dict[str, Any]:
    return load_json(bundle / "manifest.json")


def state_dir_path(bundle: Path, screen: Dict[str, Any], state: Dict[str, Any]) -> Path:
    state_dir = str(state.get("dir") or "")
    if state_dir:
        candidate = bundle / state_dir
        if candidate.is_dir():
            return candidate
    screen_dir = str(screen.get("dir") or screen.get("id") or "")
    return bundle / screen_dir / state_dir


def load_state_raw(bundle: Path, screen: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    return load_json(state_dir_path(bundle, screen, state) / "raw.json")


def load_state_connectors(bundle: Path, screen: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    path = state_dir_path(bundle, screen, state) / "connectors.json"
    if not path.is_file():
        return {"connectors": []}
    return load_json(path)


def screen_id_map(manifest: Dict[str, Any]) -> Dict[str, str]:
    return {s["id"]: manifest_id_to_screen_id(s["id"]) for s in manifest.get("screens") or []}


def default_state(manifest_screen: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    default_id = manifest_screen.get("defaultStateId")
    states = manifest_screen.get("states") or []
    if default_id:
        for st in states:
            if st.get("id") == default_id or st.get("nodeId") == default_id:
                return st
    for st in states:
        if st.get("isDefault"):
            return st
    return states[0] if states else None


def aggregate_design_source(manifest: Dict[str, Any], bundle: Path) -> Dict[str, Any]:
    source = manifest.get("source") or {}
    stats = manifest.get("stats") or {}
    node_count = int(stats.get("nodeCount") or 0)
    truncated = int(stats.get("truncatedCount") or 0)
    max_depth = 0
    has_geometry = False
    if not node_count:
        for screen in manifest.get("screens") or []:
            for state in screen.get("states") or []:
                try:
                    raw = load_state_raw(bundle, screen, state)
                except (OSError, json.JSONDecodeError):
                    continue
                export = raw.get("export") or {}
                max_depth = max(max_depth, int(export.get("maxDepth") or 0))
                truncated += int(export.get("truncatedCount") or 0)
                node_count += int(export.get("nodeCount") or 0)
                for node in _walk_nodes(raw.get("nodes") or []):
                    if "x" in node and "y" in node:
                        has_geometry = True
                        break
    else:
        for screen in manifest.get("screens") or []:
            for state in screen.get("states") or []:
                try:
                    raw = load_state_raw(bundle, screen, state)
                except (OSError, json.JSONDecodeError):
                    continue
                export = raw.get("export") or {}
                max_depth = max(max_depth, int(export.get("maxDepth") or 0))
                for node in _walk_nodes(raw.get("nodes") or []):
                    if "x" in node and "y" in node:
                        has_geometry = True
                        break
                if has_geometry:
                    break
            if has_geometry:
                break
    return {
        "file_name": source.get("fileName") or source.get("file_name") or "",
        "page_name": source.get("pageName") or source.get("page_name") or "",
        "scope": source.get("scope") or "page",
        "exported_at": manifest.get("exportedAt") or "",
        "max_depth": max_depth,
        "node_count": node_count,
        "truncated_count": truncated,
        "has_geometry": has_geometry,
    }


def _walk_nodes(nodes: List[Dict[str, Any]]):
    for n in nodes:
        yield n
        for c in n.get("children") or []:
            yield from _walk_nodes([c])


def collect_outgoing_connectors(
    bundle: Path,
    manifest: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """Deduped outgoing connectors and per-state outgoing lists."""
    seen: Set[str] = set()
    deduped: List[Dict[str, Any]] = []
    per_state: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for screen in manifest.get("screens") or []:
        for state in screen.get("states") or []:
            conn_data = load_state_connectors(bundle, screen, state)
            key = f"{screen['id']}:{state.get('id') or state.get('nodeId')}"
            for conn in conn_data.get("connectors") or []:
                if conn.get("role") != "outgoing":
                    continue
                cid = str(conn.get("id") or "")
                per_state[key].append(conn)
                if cid and cid not in seen:
                    seen.add(cid)
                    deduped.append(conn)
    return deduped, per_state


def connector_endpoints(conn: Dict[str, Any]) -> Tuple[str, str]:
    start = conn.get("connectorStart") or conn.get("source") or {}
    end = conn.get("connectorEnd") or conn.get("target") or {}
    from_ref = str(start.get("endpointNodeId") or start.get("nodeId") or "")
    to_ref = str(end.get("endpointNodeId") or end.get("nodeId") or "")
    return from_ref, to_ref


def owner_screen_id(conn: Dict[str, Any], sid_map: Dict[str, str]) -> Tuple[str, str]:
    source = conn.get("source") or {}
    target = conn.get("target") or {}
    src_owner = source.get("owner") or {}
    tgt_owner = target.get("owner") or {}
    from_sid = sid_map.get(str(src_owner.get("screenId") or ""), "")
    to_sid = sid_map.get(str(tgt_owner.get("screenId") or ""), "")
    return from_sid, to_sid


def backfill_interactions(
    elements: List[Dict[str, Any]],
    outgoing: List[Dict[str, Any]],
    sid_map: Dict[str, str],
) -> None:
    by_ref = {e["source_ref"]: e for e in elements}
    seen_pairs: Set[Tuple[str, str]] = set()
    for conn in outgoing:
        if conn.get("role") != "outgoing":
            continue
        source = conn.get("source") or {}
        src_id = str(source.get("nodeId") or "")
        el = by_ref.get(src_id)
        if not el:
            continue
        cid = str(conn.get("id") or "")
        pair = (src_id, cid)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        tgt_owner = (conn.get("target") or {}).get("owner") or {}
        dest_screen = sid_map.get(str(tgt_owner.get("screenId") or ""), "")
        target = conn.get("target") or {}
        el.setdefault("interactions", []).append(
            {
                "trigger": "tap",
                "action": f"Navigate to {dest_screen or 'unknown'} via connector {conn.get('id')}",
                "connector_id": cid,
                "destination_node_id": str(target.get("nodeId") or ""),
                "destination_screen_id": dest_screen or None,
            }
        )


def sort_ui_flow_bfs(
    ui_flow: List[Dict[str, Any]],
    entry_screens: Set[str],
) -> List[Dict[str, Any]]:
    if not ui_flow:
        return ui_flow
    entry_edges = [e for e in ui_flow if e.get("navigation_kind") == "ENTRY"]
    rest = [e for e in ui_flow if e.get("navigation_kind") != "ENTRY"]
    bfs_seeds = set(entry_screens)
    for e in entry_edges:
        bfs_seeds.add(e["to_screen_id"])

    by_from: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for edge in rest:
        by_from[edge["from_screen_id"]].append(edge)
    order: List[str] = []
    q = deque(sorted(bfs_seeds))
    seen: Set[str] = set()
    while q:
        s = q.popleft()
        if s in seen:
            continue
        seen.add(s)
        order.append(s)
        for e in by_from.get(s, []):
            dest = e["to_screen_id"]
            if dest not in seen:
                q.append(dest)
    ordered: List[Dict[str, Any]] = list(entry_edges)
    placed: Set[str] = set()
    for s in order:
        for e in by_from.get(s, []):
            key = e.get("source_ref") or json.dumps(e, sort_keys=True)
            if key not in placed:
                ordered.append(e)
                placed.add(key)
    for e in rest:
        key = e.get("source_ref") or json.dumps(e, sort_keys=True)
        if key not in placed:
            ordered.append(e)
            placed.add(key)
    return ordered


def _state_owner_key(screen_manifest_id: str, state: Dict[str, Any]) -> str:
    return f"{screen_manifest_id}:{state.get('id') or state.get('nodeId')}"


def _is_same_state(a: Dict[str, Any], b: Optional[Dict[str, Any]]) -> bool:
    if not b:
        return False
    return a.get("nodeId") == b.get("nodeId") and a.get("id") == b.get("id")


def extract_bundle(
    bundle: Path,
    plugin_root: Path,
    app: Optional[str] = None,
    scratchpad: Optional[str] = None,
) -> Dict[str, Any]:
    if not is_bundle_dir(bundle):
        raise ValueError(f"Not a figma-design-bundle directory: {bundle}")

    manifest = load_manifest(bundle)
    sid_map = screen_id_map(manifest)
    conventions = manifest.get("conventions") or {}
    smart_missing = 0

    all_outgoing, _ = collect_outgoing_connectors(bundle, manifest)
    ui_flow_trigger_gaps: List[Dict[str, Any]] = []
    screens_out: List[Dict[str, Any]] = []

    # element maps per screen_id for triggers
    screen_elements: Dict[str, List[Dict[str, Any]]] = {}
    screen_element_by_ref: Dict[str, Dict[str, Dict[str, Any]]] = {}
    state_element_by_ref: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for mscreen in manifest.get("screens") or []:
        screen_id = sid_map[mscreen["id"]]
        states = mscreen.get("states") or []
        state_names = [str(s.get("name") or s.get("id") or "") for s in states]
        default_st = default_state(mscreen)
        used_ids: Set[str] = set()
        elements: List[Dict[str, Any]] = []

        connector_sources: Set[str] = set()
        for state in states:
            conn_data = load_state_connectors(bundle, mscreen, state)
            for conn in conn_data.get("connectors") or []:
                if conn.get("role") != "outgoing":
                    continue
                src = str((conn.get("source") or {}).get("nodeId") or "")
                if src:
                    connector_sources.add(src)

        for state in states:
            raw = load_state_raw(bundle, mscreen, state)
            sname = str(state.get("name") or "")
            owner_key = _state_owner_key(str(mscreen["id"]), state)
            state_elems: List[Dict[str, Any]] = []

            if _is_same_state(state, default_st):
                state_used: Set[str] = set(used_ids)
                state_elems = collect_interactive_elements(
                    raw, screen_id, sname, state_used, connector_sources
                )
                conn_data = load_state_connectors(bundle, mscreen, state)
                for conn in conn_data.get("connectors") or []:
                    if conn.get("role") != "outgoing":
                        continue
                    src = str((conn.get("source") or {}).get("nodeId") or "")
                    if not src:
                        continue
                    state_elems = ensure_connector_source_element(
                        state_elems,
                        src,
                        raw,
                        screen_id,
                        sname,
                        state_used,
                        connector_text=str(conn.get("text") or ""),
                    )
                used_ids = state_used
            else:
                conn_data = load_state_connectors(bundle, mscreen, state)
                state_used = set(used_ids)
                for conn in conn_data.get("connectors") or []:
                    if conn.get("role") != "outgoing":
                        continue
                    src = str((conn.get("source") or {}).get("nodeId") or "")
                    if not src:
                        continue
                    state_elems = ensure_connector_source_element(
                        state_elems,
                        src,
                        raw,
                        screen_id,
                        sname,
                        state_used,
                        connector_text=str(conn.get("text") or ""),
                    )
                used_ids = state_used

            state_element_by_ref[owner_key] = {e["source_ref"]: e for e in state_elems}
            elements = merge_elements_by_source_ref(elements, state_elems)

        elements = dedupe_elements_by_source_ref(elements)

        for state in states:
            files = state.get("files") or {}
            if files.get("smart") and not (state_dir_path(bundle, mscreen, state) / "smart.json").is_file():
                smart_missing += 1

        for state in states:
            conn_data = load_state_connectors(bundle, mscreen, state)
            backfill_interactions(elements, conn_data.get("connectors") or [], sid_map)

        source_refs = [str(s.get("nodeId") or "") for s in states if s.get("nodeId")]
        default_ref = str(default_st.get("nodeId") or (source_refs[0] if source_refs else ""))

        screens_out.append(
            {
                "screen_id": screen_id,
                "screen_name": mscreen.get("name") or mscreen.get("id") or screen_id,
                "source_ref": default_ref,
                "source_refs": source_refs,
                "screen_states": state_names,
                "state_kinds": state_kinds_for_screen(state_names, conventions),
                "elements": elements,
                "screen_notes": (
                    f"{len(state_names)} states from label-instance grouping."
                    if len(state_names) > 1
                    else ""
                ),
            }
        )
        screen_elements[screen_id] = elements
        screen_element_by_ref[screen_id] = {e["source_ref"]: e for e in elements}

    ui_flow: List[Dict[str, Any]] = []
    in_degree: Dict[str, int] = {sid: 0 for sid in sid_map.values()}

    for conn in all_outgoing:
        from_sid, to_sid = owner_screen_id(conn, sid_map)
        if not from_sid or not to_sid:
            continue
        if from_sid != to_sid:
            in_degree[to_sid] = in_degree.get(to_sid, 0) + 1

        from_ref, to_ref = connector_endpoints(conn)
        source = conn.get("source") or {}
        src_node = str(source.get("nodeId") or from_ref)
        src_owner = source.get("owner") or {}
        owner_key = f"{src_owner.get('screenId')}:{src_owner.get('stateId')}"
        state_map = state_element_by_ref.get(str(owner_key), {})
        el_map = screen_element_by_ref.get(from_sid, {})

        trigger_element_id: Optional[str] = None
        trigger_source_ref: Optional[str] = None

        def _eligible_trigger(candidate: Optional[Dict[str, Any]]) -> bool:
            if not candidate:
                return False
            label = str(candidate.get("label") or "")
            eid = str(candidate.get("element_id") or "")
            if is_loader_instance(label) or is_loader_instance(eid):
                return False
            if "spinner" in label.lower() or "spinner" in eid.lower():
                return False
            return True

        el = state_map.get(src_node) or el_map.get(src_node)
        if _eligible_trigger(el):
            trigger_element_id = el["element_id"]
            trigger_source_ref = el["source_ref"]
        else:
            el = state_map.get(from_ref) or el_map.get(from_ref)
            if _eligible_trigger(el):
                trigger_element_id = el["element_id"]
                trigger_source_ref = el["source_ref"]

        edge: Dict[str, Any] = {
            "from_screen_id": from_sid,
            "to_screen_id": to_sid,
            "condition": str(conn.get("text") or ""),
            "edge_source": "CONNECTOR",
            "confidence": "EXPLICIT",
            "source_ref": str(conn.get("id") or ""),
            "navigation_kind": "NAVIGATE",
        }
        if from_ref:
            edge["from_source_ref"] = from_ref
        if to_ref:
            edge["to_source_ref"] = to_ref
        if trigger_element_id:
            edge["trigger_element_id"] = trigger_element_id
            edge["trigger_source_ref"] = trigger_source_ref
        else:
            idx = len(ui_flow)
            ui_flow_trigger_gaps.append(
                {
                    "field": f"ui_flow[{idx}].trigger_element_id",
                    "reason": (
                        f"Connector {conn.get('id')} from {from_sid} has no resolvable trigger "
                        f"element for source node {src_node}."
                    ),
                    "action": "Verify connector attachment in Figma or improve label heuristics.",
                    "severity": "WARN",
                }
            )
        ui_flow.append(edge)

    entry_screens_topo = {sid for sid, deg in in_degree.items() if deg == 0}
    entry_edges, entry_targets, entry_gaps = build_entry_edges(
        manifest, sid_map, in_degree, ui_flow
    )
    ui_flow = entry_edges + ui_flow
    gaps_pre = list(entry_gaps)

    apply_entry_point_flags(screens_out, entry_targets, entry_screens_topo)

    ui_flow = sort_ui_flow_bfs(ui_flow, entry_screens_topo | entry_targets)

    gaps = build_extraction_gaps(manifest, smart_missing, ui_flow_trigger_gaps)
    gaps.extend(gaps_pre)
    blocking = blocking_issues_from_gaps(gaps)
    for w in manifest.get("warnings") or []:
        if w.get("code") == "CONNECTOR_DANGLING":
            msg = str(w.get("message") or "")
            if msg and msg not in blocking:
                blocking.append(msg)

    state_count = sum(len(s.get("states") or []) for s in manifest.get("screens") or [])
    pad = scratchpad or (
        f"Figma design bundle: {len(manifest.get('screens') or [])} screens, "
        f"{state_count} states, {len(all_outgoing)} deduplicated outgoing connectors."
    )

    degraded = False
    if app:
        cfg = plugin_root / "config" / f"{app}.json"
        if not cfg.is_file():
            degraded = True
            gaps.append(
                {
                    "field": "ENVIRONMENT",
                    "reason": f"Config not found: {cfg}",
                    "action": "Add config or pass --app with existing config.",
                    "severity": "DEGRADED",
                }
            )

    result: Dict[str, Any] = {
        "extraction_status": extraction_status(gaps, degraded),
        "extraction_gaps": gaps,
        "visual_analysis_scratchpad": pad,
        "project_context": {
            "overall_ambiguity_rating": ambiguity_rating(manifest, gaps),
            "blocking_issues": blocking,
        },
        "screens": screens_out,
        "ui_flow": ui_flow,
        "design_source": aggregate_design_source(manifest, bundle),
    }
    if app:
        result["app"] = app
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Extract design_context.json from figma-design-bundle")
    parser.add_argument("--bundle", type=Path, required=True, help="Bundle root directory")
    parser.add_argument("--plugin-root", type=Path, required=True, help="aep-mobile plugin root")
    parser.add_argument("--app", type=str, default=None, help="App id (e.g. gofood-consumer)")
    parser.add_argument("--out", type=Path, required=True, help="Output design_context.json path")
    parser.add_argument("--scratchpad", type=str, default=None)
    args = parser.parse_args(argv)

    try:
        ctx = extract_bundle(args.bundle, args.plugin_root, app=args.app, scratchpad=args.scratchpad)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(ctx, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
