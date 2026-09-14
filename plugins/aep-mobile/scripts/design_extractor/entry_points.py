"""ENTRY pseudo-edges and screen entry_point flags from bundle manifest."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

ENTRY_HINT_KEYWORDS = ("entry point", "1st time", "starting point")


def _label_hints_entry(label: str) -> bool:
    lower = (label or "").lower()
    return any(kw in lower for kw in ENTRY_HINT_KEYWORDS)


def _default_state_node(manifest_screen: Dict[str, Any]) -> Optional[str]:
    default_id = manifest_screen.get("defaultStateId")
    states = manifest_screen.get("states") or []
    if default_id:
        for st in states:
            if st.get("id") == default_id or st.get("nodeId") == default_id:
                return str(st.get("nodeId") or "")
    for st in states:
        if st.get("isDefault"):
            return str(st.get("nodeId") or "")
    if states:
        return str(states[0].get("nodeId") or "")
    return None


def _bfs_reach(from_screen: str, adj: Dict[str, Set[str]]) -> int:
    seen: Set[str] = {from_screen}
    q = deque([from_screen])
    while q:
        s = q.popleft()
        for nxt in adj.get(s, ()):
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return len(seen)


def build_entry_edges(
    manifest: Dict[str, Any],
    sid_map: Dict[str, str],
    in_degree: Dict[str, int],
    connector_ui_flow: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Set[str], List[Dict[str, Any]]]:
    """
    Return (entry_edges, entry_target_screen_ids, info_gaps).
    """
    info_gaps: List[Dict[str, Any]] = []
    label_hits: List[Tuple[str, str, str]] = []

    for mscreen in manifest.get("screens") or []:
        mid = str(mscreen.get("id") or "")
        screen_id = sid_map.get(mid, "")
        if not screen_id:
            continue
        for state in mscreen.get("states") or []:
            node_id = str(state.get("nodeId") or "")
            for label in state.get("labels") or []:
                if _label_hints_entry(str(label)):
                    label_hits.append((screen_id, node_id, str(label)))

    entry_edges: List[Dict[str, Any]] = []
    entry_targets: Set[str] = set()

    if label_hits:
        seen_screens: Set[str] = set()
        for screen_id, node_id, _label in label_hits:
            if screen_id in seen_screens:
                continue
            seen_screens.add(screen_id)
            entry_targets.add(screen_id)
            entry_edges.append(
                {
                    "from_screen_id": "ENTRY",
                    "to_screen_id": screen_id,
                    "condition": "",
                    "edge_source": "ENTRY_LABEL",
                    "confidence": "EXPLICIT",
                    "source_ref": node_id,
                    "to_source_ref": node_id,
                    "navigation_kind": "ENTRY",
                }
            )
        return entry_edges, entry_targets, info_gaps

    zero_in = {sid for sid, deg in in_degree.items() if deg == 0}
    if not zero_in:
        fallback_sid: Optional[str] = None
        for mscreen in manifest.get("screens") or []:
            if mscreen.get("defaultStateId") or any(
                s.get("isDefault") for s in (mscreen.get("states") or [])
            ):
                fallback_sid = sid_map.get(str(mscreen.get("id") or ""))
                break
        if not fallback_sid and manifest.get("screens"):
            fallback_sid = sid_map.get(str(manifest["screens"][0].get("id") or ""))
        node_id = ""
        if fallback_sid:
            for mscreen in manifest.get("screens") or []:
                if sid_map.get(str(mscreen.get("id") or "")) == fallback_sid:
                    node_id = _default_state_node(mscreen) or ""
                    break
        if fallback_sid and node_id:
            entry_targets.add(fallback_sid)
            entry_edges.append(
                {
                    "from_screen_id": "ENTRY",
                    "to_screen_id": fallback_sid,
                    "condition": "",
                    "edge_source": "ENTRY_TOPOLOGY",
                    "confidence": "INFERRED",
                    "source_ref": node_id,
                    "to_source_ref": node_id,
                    "navigation_kind": "ENTRY",
                }
            )
            info_gaps.append(
                {
                    "field": "ui_flow",
                    "reason": "No entry-point labels in manifest; ENTRY edge inferred from closed-graph topology fallback.",
                    "action": "Add states[].labels[] containing \"entry point\" or verify flow starting screen.",
                    "severity": "INFO",
                }
            )
        return entry_edges, entry_targets, info_gaps

    adj: Dict[str, Set[str]] = defaultdict(set)
    for edge in connector_ui_flow:
        if edge.get("navigation_kind") == "ENTRY":
            continue
        fr = edge.get("from_screen_id")
        to = edge.get("to_screen_id")
        if fr and to and fr != to:
            adj[fr].add(to)

    pick: Optional[str] = None
    best_reach = -1
    for sid in sorted(zero_in):
        reach = _bfs_reach(sid, adj)
        if reach > best_reach:
            best_reach = reach
            pick = sid

    if pick:
        node_id = ""
        for mscreen in manifest.get("screens") or []:
            if sid_map.get(str(mscreen.get("id") or "")) == pick:
                node_id = _default_state_node(mscreen) or ""
                break
        entry_targets.add(pick)
        entry_edges.append(
            {
                "from_screen_id": "ENTRY",
                "to_screen_id": pick,
                "condition": "",
                "edge_source": "ENTRY_TOPOLOGY",
                "confidence": "INFERRED",
                "source_ref": node_id,
                "to_source_ref": node_id,
                "navigation_kind": "ENTRY",
            }
        )

    return entry_edges, entry_targets, info_gaps


def apply_entry_point_flags(
    screens_out: List[Dict[str, Any]],
    entry_targets: Set[str],
    zero_in_degree: Set[str],
) -> None:
    flagged = entry_targets | zero_in_degree
    for scr in screens_out:
        if scr["screen_id"] in flagged:
            scr["entry_point"] = True
