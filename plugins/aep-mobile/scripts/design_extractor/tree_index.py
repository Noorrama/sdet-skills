"""Build id → node maps from Export Design Raw JSON v2 state trees."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Optional, Tuple


def iter_nodes(nodes: List[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
    for node in nodes:
        yield node
        children = node.get("children") or []
        if children:
            yield from iter_nodes(children)


def build_node_index(raw: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    roots = raw.get("nodes") or []
    for node in iter_nodes(roots):
        nid = node.get("id")
        if nid:
            index[str(nid)] = node
    return index


def build_parent_index(raw: Dict[str, Any]) -> Dict[str, Optional[str]]:
    parents: Dict[str, Optional[str]] = {}

    def walk(nodes: List[Dict[str, Any]], parent_id: Optional[str]) -> None:
        for node in nodes:
            nid = node.get("id")
            if nid:
                parents[str(nid)] = parent_id
            children = node.get("children") or []
            if children:
                walk(children, str(nid) if nid else parent_id)

    walk(raw.get("nodes") or [], None)
    return parents


def node_name(node: Dict[str, Any]) -> str:
    return str(node.get("name") or "")


def is_text_node(node: Dict[str, Any]) -> bool:
    return node.get("type") == "TEXT"


def text_characters(node: Dict[str, Any]) -> str:
    if not is_text_node(node):
        return ""
    return str(node.get("characters") or "").strip()


def find_ancestor(
    node_id: str,
    parents: Dict[str, Optional[str]],
    index: Dict[str, Dict[str, Any]],
    predicate,
) -> Optional[Dict[str, Any]]:
    current: Optional[str] = node_id
    while current:
        node = index.get(current)
        if node and predicate(node):
            return node
        current = parents.get(current)
    return None


def sibling_text_in_frame(
    node_id: str,
    index: Dict[str, Dict[str, Any]],
    parents: Dict[str, Optional[str]],
) -> str:
    """TEXT label in the same row FRAME as node_id."""
    row = find_ancestor(
        node_id,
        parents,
        index,
        lambda n: n.get("type") == "FRAME" and "row" in node_name(n).lower(),
    )
    if not row:
        row = find_ancestor(node_id, parents, index, lambda n: n.get("type") == "FRAME")
    if not row:
        return ""
    for child in row.get("children") or []:
        label = text_characters(child)
        if label:
            return label
        for grand in child.get("children") or []:
            label = text_characters(grand)
            if label:
                return label
    return ""


def text_in_subtree(node: Dict[str, Any]) -> str:
    if is_text_node(node):
        t = text_characters(node)
        if t and not is_junk_characters(t):
            return t
    for ch in node.get("children") or []:
        found = text_in_subtree(ch)
        if found:
            return found
    return ""


def button_label_from_tree(
    node_id: str,
    index: Dict[str, Dict[str, Any]],
    parents: Dict[str, Optional[str]],
) -> str:
    node = index.get(node_id)
    if not node:
        return ""

    def walk_subtree(n: Dict[str, Any]) -> str:
        name = node_name(n)
        if "button text" in name.lower() or name.lower() == "button_text":
            t = text_characters(n)
            if t:
                return t
        if n.get("type") == "TEXT":
            t = text_characters(n)
            if t:
                return t
        for ch in n.get("children") or []:
            found = walk_subtree(ch)
            if found:
                return found
        return ""

    if node:
        found = walk_subtree(node)
        if found:
            return found

    return sibling_text_in_frame(node_id, index, parents)


_JUNK_TEXT = re.compile(r"^(properties|navigation)/", re.I)
_PRICE = re.compile(r"Rp|\d{1,3}(?:\.\d{3})+")


def is_junk_characters(chars: str) -> bool:
    t = (chars or "").strip()
    if not t or t == "Text":
        return True
    if len(t) == 1 and not t.isalnum():
        return True
    if _JUNK_TEXT.match(t):
        return True
    return False


def meaningful_text_near(
    node_id: str,
    index: Dict[str, Dict[str, Any]],
    parents: Dict[str, Optional[str]],
) -> str:
    """Readable TEXT in ancestor FRAME rows/footers (excluding design-system junk)."""
    current: Optional[str] = node_id
    while current:
        node = index.get(current)
        if node and node.get("type") == "FRAME":
            for child in node.get("children") or []:
                if child.get("type") == "TEXT":
                    t = text_characters(child)
                    if t and not is_junk_characters(t):
                        return t
                for grand in child.get("children") or []:
                    if grand.get("type") == "TEXT":
                        t = text_characters(grand)
                        if t and not is_junk_characters(t):
                            return t
        current = parents.get(current)
    return ""


def normalize_component_label(raw: str) -> str:
    """Prefer human CTA tokens from instance/path names."""
    s = (raw or "").strip().lstrip("_")
    if not s:
        return ""
    lower = s.lower()
    if "go to checkout" in lower:
        idx = lower.index("go to checkout")
        return s[idx : idx + len("go to checkout")]
    if "checkout" in lower and " " in s:
        for part in re.split(r"[/\n]", s):
            if "checkout" in part.lower() and len(part.strip()) > 8:
                return part.strip()
    if "edit" in lower:
        for part in re.split(r"[/\n]", s):
            if "edit" in part.lower():
                return part.strip()
    if _PRICE.search(s):
        for part in re.split(r"[/\n]", s):
            if _PRICE.search(part):
                return part.strip()
    tail = s.split("/")[-1].strip()
    if tail and not tail.lower().startswith(("button", "properties", "navigation", "selection_control")):
        return tail.replace("_", " ")
    return s.split("/")[-1] if "/" in s else s
