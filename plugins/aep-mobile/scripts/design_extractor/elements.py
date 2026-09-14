"""Element extraction heuristics from raw state trees."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .tree_index import (
    build_node_index,
    build_parent_index,
    button_label_from_tree,
    is_junk_characters,
    iter_nodes,
    meaningful_text_near,
    node_name,
    normalize_component_label,
    text_characters,
    text_in_subtree,
)

LOADER_PATTERNS = (
    "indicator/spinner",
    "spinner/full",
    "loader",
    "loading/full",
    "skeleton",
)

BUTTON_PREFIXES = ("button/",)
TOGGLE_PREFIXES = ("selection_control/",)
LIST_HINTS = ("sku", "list", "row", "merchant_profile_sku")

_GENERIC_LABEL_RE = re.compile(
    r"^(text|button/circular|properties/|navigation/|selection_control/)",
    re.I,
)


def _slug(text: str, max_len: int = 48) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return (s[:max_len] if s else "element")


def is_loader_instance(name: str) -> bool:
    lower = name.lower()
    return any(p in lower for p in LOADER_PATTERNS)


def is_generic_label(label: str) -> bool:
    t = (label or "").strip()
    if not t or t == "Text":
        return True
    if _GENERIC_LABEL_RE.match(t):
        return True
    if "properties/" in t.lower() and "chips" in t.lower():
        return True
    if t.lower().startswith("button/") and "text" not in t.lower():
        return True
    return False


def label_quality_score(label: str) -> int:
    if not label:
        return 0
    if is_generic_label(label):
        return 2
    lower = label.lower()
    if "edit" in lower or "checkout" in lower or "go to" in lower:
        return 9
    if re.search(r"Rp|\d{1,3}(?:\.\d{3})+", label):
        return 8
    if " " in label and len(label) > 6:
        return 10
    if "/" in label:
        return 4
    return 6


def classify_instance(name: str) -> Tuple[str, str, str]:
    """Return (type, role, role_suffix)."""
    lower = name.lower()
    if is_loader_instance(lower):
        return ("loader", "OTHER", "_btn")
    if any(lower.startswith(p) for p in BUTTON_PREFIXES):
        return ("button", "BUTTON", "_btn")
    if any(lower.startswith(p) for p in TOGGLE_PREFIXES):
        return ("selection_control", "TOGGLE", "_toggle")
    if any(h in lower for h in LIST_HINTS):
        return ("list", "LIST", "_list")
    return ("instance", "OTHER", "_btn")


def is_interactive_instance(name: str) -> bool:
    lower = name.lower()
    if is_loader_instance(lower):
        return False
    if any(lower.startswith(p) for p in BUTTON_PREFIXES + TOGGLE_PREFIXES):
        return True
    if any(h in lower for h in LIST_HINTS):
        return True
    return False


def element_id_for(
    screen_id: str,
    label: str,
    role_suffix: str,
    name: str,
    used_ids: Set[str],
) -> str:
    base = _slug(label) if label and not label.startswith(("button/", "selection_control/")) else _slug(name.split("/")[-1])
    if not base or base == "element":
        base = _slug(name.replace("/", "_"))
    candidate = f"{screen_id}.{base}{role_suffix}"
    if candidate in used_ids:
        n = 2
        while f"{screen_id}.{base}_{n}{role_suffix}" in used_ids:
            n += 1
        candidate = f"{screen_id}.{base}_{n}{role_suffix}"
    used_ids.add(candidate)
    return candidate


def resolve_label(
    node: Dict[str, Any],
    node_id: str,
    index: Dict[str, Dict[str, Any]],
    parents: Dict[str, Optional[str]],
) -> Tuple[str, Optional[Dict[str, str]]]:
    name = node_name(node)
    if node.get("type") == "TEXT":
        chars = text_characters(node)
        if chars and not is_junk_characters(chars):
            return chars, None
        return chars or "", None
    if node.get("type") in ("FRAME", "GROUP", "COMPONENT"):
        sub = text_in_subtree(node)
        if sub:
            return sub, None
    if node.get("type") == "INSTANCE":
        btn = button_label_from_tree(node_id, index, parents)
        if btn and not is_junk_characters(btn):
            return btn, None
        near = meaningful_text_near(node_id, index, parents)
        if near:
            return near, None
        normalized = normalize_component_label(name)
        if normalized and not is_generic_label(normalized):
            return normalized, None
        sibling = meaningful_text_near(node_id, index, parents) or ""
        if not sibling:
            from .tree_index import sibling_text_in_frame

            sibling = sibling_text_in_frame(node_id, index, parents)
        if sibling and not is_junk_characters(sibling):
            return sibling, None
        if is_interactive_instance(name):
            if "/" in name:
                return name, {"rating": "MEDIUM", "reason": f"Label derived from instance name '{name}'."}
    return "", None


def detect_radio_row_elements(
    raw: Dict[str, Any],
    screen_id: str,
    state_name: str,
    used_ids: Set[str],
) -> List[Dict[str, Any]]:
    """FRAME rows with selection_control/radio + TEXT label."""
    out: List[Dict[str, Any]] = []

    for node in iter_nodes(raw.get("nodes") or []):
        if node.get("type") != "FRAME":
            continue
        children = node.get("children") or []
        radio = None
        label_text = ""
        for ch in children:
            cname = node_name(ch)
            if ch.get("type") == "INSTANCE" and "selection_control/radio" in cname.lower():
                radio = ch
            if ch.get("type") == "TEXT":
                label_text = text_characters(ch) or label_text
            for sub in ch.get("children") or []:
                if sub.get("type") == "TEXT":
                    label_text = text_characters(sub) or label_text
        if not radio or not label_text:
            continue
        rid = radio.get("id")
        if not rid:
            continue
        eid = element_id_for(screen_id, label_text, "_toggle", label_text, used_ids)
        out.append(
            {
                "element_id": eid,
                "source_ref": str(rid),
                "type": "selection_control",
                "role": "TOGGLE",
                "label": label_text,
                "states_represented": [state_name],
                "interactions": [],
                "validations_and_edge_cases": [],
            }
        )
    return out


def collect_interactive_elements(
    raw: Dict[str, Any],
    screen_id: str,
    state_name: str,
    used_ids: Set[str],
    connector_source_ids: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    index = build_node_index(raw)
    parents = build_parent_index(raw)
    elements: List[Dict[str, Any]] = []
    connector_source_ids = connector_source_ids or set()

    radio_rows = detect_radio_row_elements(raw, screen_id, state_name, used_ids)
    radio_refs = {e["source_ref"] for e in radio_rows}
    elements.extend(radio_rows)

    for node in iter_nodes(raw.get("nodes") or []):
        if node.get("type") != "INSTANCE":
            continue
        name = node_name(node)
        if not is_interactive_instance(name):
            continue
        nid = node.get("id")
        if not nid:
            continue
        nid_s = str(nid)
        if "selection_control/radio" in name.lower() and nid_s in radio_refs:
            continue
        typ, role, suffix = classify_instance(name)
        if typ == "loader":
            continue
        if typ == "list" and nid_s not in connector_source_ids:
            continue
        label, ambiguity = resolve_label(node, nid_s, index, parents)
        if not label:
            label = name
        eid = element_id_for(screen_id, label, suffix, name, used_ids)
        row: Dict[str, Any] = {
            "element_id": eid,
            "source_ref": nid_s,
            "type": typ,
            "role": role,
            "label": label,
            "states_represented": [state_name],
            "interactions": [],
            "validations_and_edge_cases": [],
        }
        if ambiguity:
            row["element_ambiguity"] = ambiguity
        elements.append(row)

    existing_refs = {e["source_ref"] for e in elements}
    for node in iter_nodes(raw.get("nodes") or []):
        if node.get("type") != "TEXT":
            continue
        chars = text_characters(node)
        if len(chars) < 8:
            continue
        nid = node.get("id")
        if not nid or str(nid) in existing_refs:
            continue
        lower = chars.lower()
        if "learn more" in lower or lower.startswith("http"):
            eid = element_id_for(screen_id, chars, "_label", chars, used_ids)
            elements.append(
                {
                    "element_id": eid,
                    "source_ref": str(nid),
                    "type": "TEXT",
                    "role": "LINK",
                    "label": chars,
                    "states_represented": [state_name],
                    "interactions": [],
                    "validations_and_edge_cases": [],
                }
            )
            existing_refs.add(str(nid))

    return elements


def merge_elements_by_source_ref(
    seeded: List[Dict[str, Any]],
    incoming: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_ref: Dict[str, Dict[str, Any]] = {e["source_ref"]: dict(e) for e in seeded}
    for el in incoming:
        ref = el["source_ref"]
        if ref in by_ref:
            states = set(by_ref[ref].get("states_represented") or [])
            states.update(el.get("states_represented") or [])
            by_ref[ref]["states_represented"] = sorted(states)
        else:
            by_ref[ref] = dict(el)
    return list(by_ref.values())


def dedupe_elements_by_source_ref(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_ref: Dict[str, List[Dict[str, Any]]] = {}
    for el in elements:
        by_ref.setdefault(el["source_ref"], []).append(el)

    out: List[Dict[str, Any]] = []
    for ref, group in by_ref.items():
        if len(group) == 1:
            out.append(group[0])
            continue
        best = max(
            group,
            key=lambda e: (
                label_quality_score(str(e.get("label") or "")),
                0 if e.get("element_ambiguity") else 1,
            ),
        )
        merged = dict(best)
        states: Set[str] = set()
        for g in group:
            states.update(g.get("states_represented") or [])
        merged["states_represented"] = sorted(states)
        out.append(merged)
    return out


def should_prefer_connector_text(label: str, connector_text: str) -> bool:
    ct = (connector_text or "").strip()
    if not ct:
        return False
    if is_generic_label(label):
        return True
    lower_ct = ct.lower()
    if ("plus" in lower_ct or "minus" in lower_ct) and re.search(
        r"Rp|\d{1,3}(?:\.\d{3})+|\d+\.\d{3}", label or ""
    ):
        return True
    return False


def _apply_connector_text_label(row: Dict[str, Any], connector_text: str) -> None:
    text = (connector_text or "").strip()
    if not text or not should_prefer_connector_text(str(row.get("label") or ""), text):
        return
    row["label"] = text
    row["element_ambiguity"] = {
        "rating": "MEDIUM",
        "reason": "Label from connector text; source layer has no readable TEXT.",
    }


def ensure_connector_source_element(
    elements: List[Dict[str, Any]],
    source_node_id: str,
    raw: Dict[str, Any],
    screen_id: str,
    state_name: str,
    used_ids: Set[str],
    connector_text: Optional[str] = None,
) -> List[Dict[str, Any]]:
    for el in elements:
        if el["source_ref"] == source_node_id:
            _apply_connector_text_label(el, connector_text or "")
            return elements

    index = build_node_index(raw)
    parents = build_parent_index(raw)
    node = index.get(source_node_id)
    if not node:
        return elements
    name = node_name(node)
    typ, role, suffix = classify_instance(name) if node.get("type") == "INSTANCE" else ("frame", "BUTTON", "_btn")
    if typ == "loader":
        return elements
    label, ambiguity = resolve_label(node, source_node_id, index, parents)
    if not label:
        label = name or source_node_id
    row: Dict[str, Any] = {
        "element_id": element_id_for(screen_id, label, suffix, name or "node", used_ids),
        "source_ref": source_node_id,
        "type": typ if typ != "frame" else "button",
        "role": role,
        "label": label,
        "states_represented": [state_name],
        "interactions": [],
        "validations_and_edge_cases": [],
    }
    if ambiguity:
        row["element_ambiguity"] = ambiguity
    _apply_connector_text_label(row, connector_text or "")
    return elements + [row]
