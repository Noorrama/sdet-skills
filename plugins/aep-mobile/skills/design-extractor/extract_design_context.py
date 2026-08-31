#!/usr/bin/env python3
"""Extract design_context.json from a render_design.py pre-process output.

Consumes the ``_pre-process.json`` produced by ``render_design.py preprocess``
and writes a schema-valid ``design_context.temp.json`` (intermediate artifact).

Phase 1 scope
-------------
- ``design_source``   — envelope metadata from the original Figma JSON.
- ``app``             — inferred from filename / page-name keyword heuristic.
- ``screens``         — one object per logical screen (AUTO-collapsed state
                         variants with identical raw frame names). Elements
                         are populated from the pruned node_tree children
                         already present in ``_pre-process.json``.
- ``ui_flow``         — BFS-ordered edges (ENTRY first, then waves, then
                         orphans sorted by spatial position).
- ``extraction_gaps`` — INFO gaps for unresolved connectors and selection scope.
- ``extraction_status`` / ``visual_analysis_scratchpad`` / ``project_context``
                         — stubs required for schema validity.

Usage
-----
    python3 extract_design_context.py \\
        --preprocess  <workdir>/stem_pre-process.json \\
        --input       <original-input.json> \\
        [-w <workdir>] \\
        [-o <workdir>/design_context.temp.json]  # default
"""

import argparse
import json
import math
import os
import re
import sys
from collections import Counter, deque

INVENTORY_SUFFIX = "_inventory.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_QUALIFIER_RE = re.compile(r"\s*/\s*.+$")   # strip " / EN", " / Error", etc.
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def to_upper_snake(name: str) -> str:
    """Convert a Figma frame name to UPPER_SNAKE_CASE screen_id.

    Strips any trailing " / qualifier" suffix first so that "MPS / EN" and
    "MPS / Error" both become ``MPS``.
    """
    base = _QUALIFIER_RE.sub("", name).strip().upper()
    snake = _NON_ALNUM.sub("_", base).strip("_")
    return snake or "UNKNOWN"


def to_lower_snake(name: str) -> str:
    """Normalise a node name to lower_snake_case for element_id purposes."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return cleaned or "unknown"


# ---------------------------------------------------------------------------
# Element ID quality assessment
# ---------------------------------------------------------------------------

_ROLE_SUFFIXES = [
    "_btn", "_button", "_input", "_label", "_lbl", "_toggle", "_tab", "_list",
    "_container", "_img", "_image",
]
_MODIFIERS = {
    "content", "container", "frame", "group", "wrapper", "text", "label",
    "button", "btn", "icon", "image", "img", "div", "span", "view",
    "layout", "item", "component", "node", "default", "unknown",
    "unnamed", "temp", "test", "new", "copy", "layer", "artboard",
    "screen", "page", "section", "title", "subtitle", "header", "footer",
    "primary", "secondary", "tertiary", "default", "active", "inactive",
    "enabled", "disabled", "visible", "hidden", "selected", "focused",
    "hover", "pressed", "normal", "error", "success", "warning", "info",
    "large", "small", "medium", "big", "tiny", "huge", "mini",
    "left", "right", "top", "bottom", "center", "middle",
    "horizontal", "vertical", "row", "column", "grid", "flex",
    "margin", "padding", "border", "radius", "shadow", "elevation",
    "background", "foreground", "color", "colour", "font", "size",
    "weight", "style", "family", "line", "height", "spacing",
    "alignment", "align", "justify", "start", "end", "between", "around",
    "absolute", "relative", "fixed", "sticky", "static",
    "width", "height", "min", "max", "auto", "fit", "fill",
    "scroll", "overflow", "clip", "mask", "opacity", "zindex",
    "transform", "translate", "rotate", "scale", "skew",
    "animation", "transition", "duration", "delay", "easing",
    "keyframe", "frame", "timeline", "play", "pause", "stop",
    "loop", "reverse", "alternate", "infinite", "count",
    "svg", "path", "circle", "rect", "ellipse", "polygon",
    "line", "polyline", "gradient", "linear", "radial",
    "stop", "offset", "spread", "method", "units",
    "filter", "blur", "brightness", "contrast", "saturate",
    "hue", "rotate", "invert", "sepia", "grayscale", "opacity",
    "mix", "blend", "mode", "multiply", "screen", "overlay",
    "darken", "lighten", "difference", "exclusion", "color",
    "dodge", "burn", "hard", "soft", "light", "lighter",
    "replace", "copy", "destination", "source", "atop", "xor",
    "luminosity", "saturation", "hue", "color", "inherit",
    "initial", "unset", "revert", "all", "none", "auto",
}
_ENTROPY_THRESHOLD = 4.0
_MAX_TOKEN_LEN = 15
_MAX_PURPOSE_LEN = 50


def shannon_entropy(s: str) -> float:
    """Calculate Shannon entropy (bits per character)."""
    if not s:
        return 0.0
    freq = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def assess_element_id_quality(element_id: str) -> dict:
    """Assess quality of an element_id. Returns {'element_id': str, 'quality': 'GOOD'|'BAD'}."""
    if "." not in element_id:
        return {"element_id": element_id, "quality": "BAD"}
    purpose = element_id.split(".", 1)[1]

    # Check 1: Role suffix
    has_suffix = any(purpose.endswith(s) for s in _ROLE_SUFFIXES)

    # Check 2: Purpose length
    len_ok = len(purpose) <= _MAX_PURPOSE_LEN

    # Check 3: Token length (split by _)
    tokens = [t for t in purpose.split("_") if t]
    token_len_ok = all(len(t) <= _MAX_TOKEN_LEN for t in tokens)

    # Check 4: Entropy (gibberish detection)
    entropy_ok = shannon_entropy(purpose) < _ENTROPY_THRESHOLD

    # Check 5: All core words are generic modifiers (failure if yes)
    # Find role suffix token, remaining are core words
    core_words = []
    for token in tokens:
        if any(token.endswith(s.lstrip("_")) for s in _ROLE_SUFFIXES) or any(token == s.lstrip("_") for s in _ROLE_SUFFIXES):
            continue
        core_words.append(token)
    # Also check suffix at end of purpose string
    matched_suffix = next((s for s in _ROLE_SUFFIXES if purpose.endswith(s)), None)
    if matched_suffix:
        # Remove suffix from last token if it was combined
        pass
    # Core words are all tokens except the one that matched role suffix
    all_modifiers = all(w in _MODIFIERS for w in core_words) if core_words else True

    quality = "GOOD" if (has_suffix and len_ok and token_len_ok and entropy_ok and not all_modifiers) else "BAD"
    return {"element_id": element_id, "quality": quality}


# ---------------------------------------------------------------------------
# App inference
# ---------------------------------------------------------------------------

_APP_RULES = [
    (["gofood", "merchant"],                 "gofood-merchant"),
    (["gofood"],                             "gofood-consumer"),
    (["gopay", "merchant"],                  "gopay-merchant"),
    (["gopay", "driver"],                    "gopay-merchant"),   # treat driver-side gopay as merchant
    (["gopay"],                              "gopay-consumer"),
    (["gojek", "driver"],                    "gojek-driver"),
    (["gojek"],                              "gojek-consumer"),
]

_VALID_APPS = {
    "gojek-consumer", "gojek-driver",
    "gofood-consumer", "gofood-merchant",
    "gopay-consumer", "gopay-merchant",
}


def infer_app(file_name: str, page_name: str) -> str | None:
    """Return an app enum value inferred from filename and page name, or None."""
    combined = (file_name + " " + page_name).lower()
    for keywords, app in _APP_RULES:
        if all(kw in combined for kw in keywords):
            return app
    return None


# ---------------------------------------------------------------------------
# Connector / trigger mechanical heuristics
# ---------------------------------------------------------------------------

_MOCKUP_NAME_RE = re.compile(
    r"(screenshot|placeholder|mockup|overlay|wireframe)", re.IGNORECASE
)
_INTERACTION_INSTANCE_RE = re.compile(r"(selection_control|button/)", re.IGNORECASE)
_NON_INTERACTIVE_TRIGGER_TYPES = frozenset({
    "RECTANGLE", "VECTOR", "BOOLEAN_OPERATION", "LINE", "ELLIPSE",
})


def is_mockup_trigger_node(index: dict, node_id: str) -> bool:
    """True when a connector start node is likely a design mockup, not a real control."""
    node = index.get(node_id) or {}
    ntype = node.get("type", "")
    name = (node.get("name") or "").strip()
    if name.lower() == "screenshot":
        return True
    if ntype in _NON_INTERACTIVE_TRIGGER_TYPES and _MOCKUP_NAME_RE.search(name):
        return True
    return False


def collect_interaction_instance_ids(node: dict, max_depth: int = 4) -> list[str]:
    """INSTANCE ids under a frame that look like interactive controls."""
    ids: list[str] = []

    def walk(n: dict, depth: int) -> None:
        if depth > max_depth:
            return
        nid = n.get("id")
        name = n.get("name", "")
        if n.get("type") == "INSTANCE" and _INTERACTION_INSTANCE_RE.search(name):
            if nid:
                ids.append(nid)
        for child in n.get("children") or []:
            walk(child, depth + 1)

    walk(node, 0)
    return ids


def connector_destination_node_ids(pp: dict) -> set[str]:
    """Figma node ids that are the destination endpoint of any resolved connector."""
    dests: set[str] = set()
    for edge in (pp.get("edges") or []) + (pp.get("original_edges") or []):
        to_node = edge.get("original_to") or edge.get("to")
        if to_node:
            dests.add(to_node)
    return dests


def resolve_screen_for_connector_endpoint(
    edge: dict,
    endpoint: str,
    screen_ids: set[str],
    index: dict,
    node_id_to_screen: dict,
    contextual_map: dict,
) -> str | None:
    """Resolve a connector endpoint to a screen frame id using preprocess maps."""
    original_key = f"original_{endpoint}"
    node_id = edge.get(original_key) or edge.get(endpoint)
    if not node_id:
        return None

    is_screen_edge = edge.get("original_from") is not None or edge.get("original_to") is not None
    if is_screen_edge:
        resolved_screen = edge.get(endpoint)
        if resolved_screen in screen_ids:
            return resolved_screen

    if node_id in screen_ids:
        return node_id
    if node_id in node_id_to_screen:
        return node_id_to_screen[node_id]
    if node_id in contextual_map:
        return contextual_map[node_id]

    curr = node_id
    while curr:
        if curr in screen_ids:
            return curr
        curr = index.get(curr, {}).get("parent_id")
    return None


def resolve_trigger_node_id(
    trigger_node_id: str,
    from_screen: str,
    index: dict,
    outgoing_candidates: set[str],
) -> tuple[str, bool]:
    """Rewire mockup connector starts to a nearby interactive node when possible."""
    if not is_mockup_trigger_node(index, trigger_node_id):
        return trigger_node_id, False

    curr = trigger_node_id
    while curr and curr != from_screen:
        parent = index.get(curr, {}).get("parent_id")
        if not parent:
            break
        parent_node = index.get(parent, {})
        if parent_node.get("type") == "INSTANCE":
            pname = (parent_node.get("name") or "").lower()
            if any(tok in pname for tok in ("button", "actions/", "social/", "invite", "share")):
                return parent, True
        curr = parent

    for nid in sorted(outgoing_candidates):
        if nid == trigger_node_id or is_mockup_trigger_node(index, nid):
            continue
        node = index.get(nid, {})
        ntype = node.get("type", "")
        name = (node.get("name") or "").lower()
        text = (node.get("text") or "").lower()
        if ntype in ("INSTANCE", "COMPONENT"):
            return nid, True
        if ntype == "TEXT" and any(tok in name or tok in text for tok in ("share", "invite")):
            return nid, True

    return trigger_node_id, False


def build_outgoing_trigger_candidates(pp: dict, screen_ids: set[str]) -> dict[str, set[str]]:
    """Per-screen set of node ids used as connector start endpoints."""
    index = pp.get("index") or {}
    node_id_to_screen = pp.get("node_id_to_screen") or {}
    contextual_map = pp.get("contextual_node_id_to_screen") or {}
    candidates: dict[str, set[str]] = {}

    for edge in (pp.get("edges") or []) + (pp.get("original_edges") or []):
        from_node = edge.get("original_from") or edge.get("from")
        if not from_node:
            continue
        from_screen = resolve_screen_for_connector_endpoint(
            edge, "from", screen_ids, index, node_id_to_screen, contextual_map,
        )
        if from_screen:
            candidates.setdefault(from_screen, set()).add(from_node)
    return candidates


def connector_ui_flow_parity_gaps(
    pp: dict,
    ui_flow: list,
    inventory: dict | None,
) -> list[dict]:
    """WARN when inventory/preprocess connectors are missing from ui_flow."""
    gaps: list[dict] = []
    edges_raw = (pp.get("edges") or []) + (pp.get("original_edges") or [])
    edge_ids = {e.get("id") for e in edges_raw if e.get("id")}
    ui_connector_ids = {
        e.get("source_ref")
        for e in ui_flow
        if e.get("edge_source") in ("CONNECTOR", "CONNECTOR_INFERRED") and e.get("source_ref")
    }
    missing = sorted(edge_ids - ui_connector_ids)
    if not missing:
        return gaps

    inv_total = (inventory or {}).get("summary", {}).get("connectors_total")
    ui_count = len(ui_connector_ids)
    sample = ", ".join(missing[:8])
    if len(missing) > 8:
        sample += f", ... (+{len(missing) - 8} more)"

    gaps.append({
        "field": "ui_flow",
        "reason": (
            f"{len(missing)} connector(s) in preprocess are absent from ui_flow "
            f"(inventory total: {inv_total}, ui_flow connectors: {ui_count}). "
            f"Missing ids: {sample}."
        ),
        "action": (
            "Check connector endpoint screen resolution and self-loop filters; "
            "ensure preprocess includes node_id_to_screen maps."
        ),
        "severity": "WARN",
    })
    return gaps


def augment_screen_flow_ids(
    screen_flow_ids: dict[str, list[str]],
    pp: dict,
) -> dict[str, list[str]]:
    """Add connector start endpoints so share/mockup triggers resolve to real elements."""
    screen_ids = {s["id"] for s in (pp.get("screens") or [])}
    outgoing = build_outgoing_trigger_candidates(pp, screen_ids)
    augmented: dict[str, list[str]] = {}
    for sid, ids in screen_flow_ids.items():
        merged = set(ids) | outgoing.get(sid, set())
        augmented[sid] = sorted(merged)
    for sid, nodes in outgoing.items():
        if sid not in augmented:
            augmented[sid] = sorted(nodes)
    return augmented


def mockup_trigger_remap_gaps(remaps: list[dict]) -> list[dict]:
    """INFO entries when connector triggers were rewired off mockup nodes."""
    gaps: list[dict] = []
    for item in remaps:
        gaps.append({
            "field": "ui_flow",
            "reason": (
                f"Connector {item['connector_id']}: trigger remapped from mockup node "
                f"{item['from_node']} to {item['to_node']}."
            ),
            "action": "Verify trigger_element_id matches the real interactive control.",
            "severity": "INFO",
        })
    return gaps


# ---------------------------------------------------------------------------
# State / qualifier extraction
# ---------------------------------------------------------------------------

_STATE_KIND_MAP = {
    "default":    "DEFAULT",
    "loading":    "LOADING",
    "empty":      "EMPTY",
    "error":      "ERROR",
    "success":    "SUCCESS",
    "offline":    "OFFLINE",
    "disabled":   "DISABLED",
    "denied":     "PERMISSION_DENIED",
    "dark":       "DARK_THEME",
    "light":      "LIGHT_THEME",
    "rtl":        "RTL",
    "en":         "LOCALE_VARIANT",
    "id":         "LOCALE_VARIANT",
    "shimmer":    "LOADING",
    "closed":     "ERROR",
    "closing":    "ERROR",
    "scroll":     "DEFAULT",
    "dialog":     "OTHER",
    "overlay":    "OTHER",
}

_RULE_KEYWORDS = (
    "unable to", "cannot", "must", "should not", "if ", "when ", "min.",
    "max.", "sold out", "required", "only", "limit", "permission", "error",
    "warning", "note:", "make sure",
)
_ENTRY_HINT_KEYWORDS = ("entry point", "1st time", "starting point")
_NAV_TOKEN_ONLY = frozenset({"changes", "new screen", "existing"})
_NAME_SUFFIX_PATTERNS = (
    (re.compile(r"\s*-\s*Loading\s*$", re.IGNORECASE), "Loading"),
    (re.compile(r"\s*\(Empty\)\s*$", re.IGNORECASE), "Empty"),
    (re.compile(r"\s*\[Error\]\s*$", re.IGNORECASE), "Error"),
)
_FRAME_TYPE_QUALIFIERS = (
    (re.compile(r"shimmer", re.IGNORECASE), "Shimmer"),
    (re.compile(r"dialog", re.IGNORECASE), "Dialog"),
    (re.compile(r"loading", re.IGNORECASE), "Loading"),
)
_NON_NAV_REACTION_NAV = frozenset({"SWAP", "CHANGE_TO", "SCROLL_TO"})
_MAX_VALIDATIONS_PER_ELEMENT = 10
_MAX_VALIDATION_BIND_ELEMENTS = 5


def extract_qualifier(name: str) -> str | None:
    """Return the " / qualifier" part of a screen name, or None."""
    m = _QUALIFIER_RE.search(name)
    if m:
        return m.group().strip().lstrip("/").strip()
    return None


def qualifier_to_state_kind(qualifier: str) -> str:
    """Map a raw qualifier string to a state_kinds enum value."""
    lower = qualifier.lower()
    for keyword, kind in _STATE_KIND_MAP.items():
        if keyword in lower:
            return kind
    return "OTHER"


def _node_geom(node: dict) -> dict:
    """Return abs_x/abs_y/width/height from a contextual or index node."""
    return {
        "abs_x": node.get("abs_x", 0),
        "abs_y": node.get("abs_y", 0),
        "width": node.get("width", 0),
        "height": node.get("height", 0),
    }


def _horizontal_overlap(a: dict, b: dict) -> float:
    ax1, ax2 = a["abs_x"], a["abs_x"] + a["width"]
    bx1, bx2 = b["abs_x"], b["abs_x"] + b["width"]
    return max(0.0, min(ax2, bx2) - max(ax1, bx1))


def is_wide_banner(text: str, screen_geom: dict, node_geom: dict) -> bool:
    """True when an annotation spans most of the screen width (lane banner)."""
    if screen_geom.get("width", 0) <= 0:
        return False
    if node_geom.get("width", 0) >= screen_geom["width"] * 0.75:
        return True
    return len(text) > 80 and node_geom.get("width", 0) >= screen_geom["width"] * 0.5


def looks_like_rule(text: str) -> bool:
    """Keyword gate for validation / edge-case notes."""
    stripped = (text or "").strip()
    if len(stripped) < 12:
        return False
    lower = stripped.lower()
    if lower in _NAV_TOKEN_ONLY:
        return False
    if lower.replace(" ", "") in {t.replace(" ", "") for t in _NAV_TOKEN_ONLY}:
        return False
    if not any(kw in lower for kw in _RULE_KEYWORDS):
        return False
    if lower in ("changes", "new screen", "existing"):
        return False
    return True


def classify_contextual_annotation(
    node_meta: dict,
    text: str,
    screen_geom: dict,
) -> str:
    """Label contextual nodes: STATE_LABEL, VALIDATION_NOTE, LANE_BANNER, ENTRY_HINT, SCENARIO_NOTE."""
    name = (node_meta.get("name") or "").strip()
    label_text = (text or name).strip()
    lower_name = name.lower()

    if "screen label" in lower_name or "driver/screen label" in lower_name:
        return "STATE_LABEL"
    if "lane" in lower_name or is_wide_banner(label_text, screen_geom, _node_geom(node_meta)):
        return "LANE_BANNER"
    if looks_like_rule(label_text):
        return "VALIDATION_NOTE"
    if any(p in label_text.lower() for p in _ENTRY_HINT_KEYWORDS):
        return "ENTRY_HINT"
    return "SCENARIO_NOTE"


def extract_name_suffix_qualifier(name: str) -> str | None:
    for pattern, qualifier in _NAME_SUFFIX_PATTERNS:
        if pattern.search(name):
            return qualifier
    return None


def extract_frame_type_qualifier(name: str) -> str | None:
    for pattern, qualifier in _FRAME_TYPE_QUALIFIERS:
        if pattern.search(name):
            return qualifier
    return None


def pick_state_label_text(
    ctx_infos: list[dict],
    text_cache: dict,
    screen_geom: dict,
) -> str | None:
    """Prefer the STATE_LABEL chip directly above the frame (horizontal overlap)."""
    candidates: list[tuple[float, str]] = []
    for ctx in ctx_infos:
        txt = (text_cache.get(ctx.get("id", ""), "") or ctx.get("name", "")).strip()
        if not txt:
            continue
        kind = classify_contextual_annotation(ctx, txt, screen_geom)
        if kind != "STATE_LABEL":
            continue
        note_geom = _node_geom(ctx)
        if _horizontal_overlap(note_geom, screen_geom) <= 0:
            continue
        gap = screen_geom["abs_y"] - (note_geom["abs_y"] + note_geom["height"])
        if gap >= 0:
            candidates.append((gap, txt))
    if not candidates:
        for ctx in ctx_infos:
            txt = (text_cache.get(ctx.get("id", ""), "") or ctx.get("name", "")).strip()
            if not txt:
                continue
            if classify_contextual_annotation(ctx, txt, screen_geom) == "STATE_LABEL":
                return txt
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def derive_frame_qualifier(name: str, state_label_text: str | None) -> str | None:
    """Priority ladder for a single frame (steps 1–4)."""
    if state_label_text:
        return state_label_text.strip()
    qualifier = extract_qualifier(name)
    if qualifier:
        return qualifier
    suffix = extract_name_suffix_qualifier(name)
    if suffix:
        return suffix
    return extract_frame_type_qualifier(name)


def disambiguate_sibling_qualifiers(
    screens_raw: list[dict],
    qualifiers_by_id: dict[str, str | None],
) -> dict[str, str | None]:
    """Append Variant N when siblings share the same base qualifier."""
    base_name_groups: dict[str, list[str]] = {}
    for s in screens_raw:
        base = to_upper_snake(s.get("name", ""))
        base_name_groups.setdefault(base, []).append(s["id"])

    result = dict(qualifiers_by_id)
    for sibling_ids in base_name_groups.values():
        if len(sibling_ids) < 2:
            continue
        ordered = [s["id"] for s in screens_raw if s["id"] in sibling_ids]
        seen: dict[str, int] = {}
        for sid in ordered:
            q = qualifiers_by_id.get(sid) or ""
            count = seen.get(q, 0) + 1
            seen[q] = count
            if count > 1:
                result[sid] = f"Variant {count}"
    return result


def build_screen_notes(
    ctx_infos: list[dict],
    text_cache: dict,
    screen_geom: dict,
    state_label_text: str | None,
) -> str:
    """Lane banners and scenario notes only — no STATE_LABEL or VALIDATION_NOTE duplicates."""
    parts: list[str] = []
    state_norm = (state_label_text or "").strip().lower()
    for ctx in ctx_infos:
        txt = (text_cache.get(ctx.get("id", ""), "") or ctx.get("name", "")).strip()
        if not txt:
            continue
        kind = classify_contextual_annotation(ctx, txt, screen_geom)
        if kind in ("STATE_LABEL", "VALIDATION_NOTE", "ENTRY_HINT"):
            continue
        if state_norm and txt.strip().lower() == state_norm:
            continue
        parts.append(txt[:100])
        if len(parts) >= 3:
            break
    return " | ".join(parts)[:300]


def _append_validation(element: dict, text: str) -> bool:
    """Append a deduped validation string; return False when capped."""
    stripped = (text or "").strip()
    if not stripped:
        return True
    validations = element.setdefault("validations_and_edge_cases", [])
    if any(v.lower() == stripped.lower() for v in validations):
        return True
    if len(validations) >= _MAX_VALIDATIONS_PER_ELEMENT:
        return False
    validations.append(stripped)
    return True


def _collect_non_nav_reaction_validations(node: dict) -> list[str]:
    """Build validation strings for SWAP / CHANGE_TO / SCROLL_TO prototype reactions."""
    out: list[str] = []
    for reaction in node.get("reactions") or []:
        action = reaction.get("action") or {}
        action_type = action.get("type", "")
        navigation = action.get("navigation") or ""
        if navigation in _NON_NAV_REACTION_NAV:
            out.append(f"State change: {navigation} on trigger")
        elif action_type in _NON_NAV_REACTION_NAV:
            out.append(f"State change: {action_type} on trigger")
        for sub in reaction.get("actions") or []:
            sub_nav = sub.get("navigation") or ""
            sub_type = sub.get("type", "")
            if sub_nav in _NON_NAV_REACTION_NAV:
                out.append(f"State change: {sub_nav} on trigger")
            elif sub_type in _NON_NAV_REACTION_NAV:
                out.append(f"State change: {sub_type} on trigger")
    return out


def _element_maps(screens: list) -> tuple[dict[str, dict], dict[str, dict]]:
    by_source: dict[str, dict] = {}
    by_screen_source: dict[str, dict] = {}
    for screen in screens:
        by_screen_source[screen["source_ref"]] = screen
        for el in screen.get("elements", []):
            by_source[el["source_ref"]] = el
    return by_source, by_screen_source


def _closest_flow_element(
    note_geom: dict,
    flow_node_ids: list[str],
    el_by_source: dict[str, dict],
    index: dict,
    prefer_buttons: bool = True,
) -> dict | None:
    if not flow_node_ids:
        return None

    def distance(nid: str) -> float:
        node = index.get(nid, {})
        nx = node.get("abs_x", 0) + node.get("width", 0) / 2
        ny = node.get("abs_y", 0) + node.get("height", 0) / 2
        cx = note_geom.get("abs_x", 0) + note_geom.get("width", 0) / 2
        cy = note_geom.get("abs_y", 0) + note_geom.get("height", 0) / 2
        return math.hypot(nx - cx, ny - cy)

    ordered = sorted(flow_node_ids, key=distance)
    if prefer_buttons:
        for nid in ordered:
            el = el_by_source.get(nid)
            if el and el.get("role") == "BUTTON":
                return el
    for nid in ordered:
        el = el_by_source.get(nid)
        if el:
            return el
    return None


def attach_validations(
    screens: list,
    pp: dict,
    inventory: dict | None,
    ui_flow: list,
) -> list[dict]:
    """Attach VALIDATION_NOTE, connector-tethered notes, and non-nav reactions to elements."""
    gaps: list[dict] = []
    text_cache = pp.get("text_cache") or {}
    index = pp.get("index") or {}
    el_by_source, screen_by_source = _element_maps(screens)

    inv_elements = {
        e["id"]: e for e in (inventory or {}).get("elements", []) if e.get("id")
    }
    flow_ids_by_screen: dict[str, list[str]] = {}
    if inventory:
        for scr in inventory.get("screens") or []:
            sid = scr.get("id")
            flow_ids = scr.get("flow_element_ids") or []
            if sid and flow_ids:
                flow_ids_by_screen[sid] = flow_ids

    trigger_by_connector: dict[str, str] = {}
    for edge in ui_flow:
        if edge.get("navigation_kind") == "ENTRY":
            continue
        source_ref = edge.get("source_ref")
        trigger_id = edge.get("trigger_element_id")
        if source_ref and trigger_id:
            trigger_by_connector[source_ref] = trigger_id

    element_id_by_trigger: dict[str, dict] = {}
    for screen in screens:
        for el in screen.get("elements", []):
            element_id_by_trigger[el["element_id"]] = el

    unbound_rules: list[str] = []

    for screen in screens:
        source_ref = screen.get("source_ref", "")
        screen_geom = _node_geom(index.get(source_ref, {}))
        ctx_infos = []
        for raw in pp.get("screens") or []:
            if raw.get("id") == source_ref:
                ctx_infos = raw.get("contextual_informations") or []
                break

        validation_notes: list[tuple[dict, str]] = []
        for ctx in ctx_infos:
            txt = (text_cache.get(ctx.get("id", ""), "") or ctx.get("name", "")).strip()
            if not txt:
                continue
            if classify_contextual_annotation(ctx, txt, screen_geom) == "VALIDATION_NOTE":
                validation_notes.append((_node_geom(ctx), txt))

        flow_node_ids = flow_ids_by_screen.get(source_ref, [])
        if not flow_node_ids:
            flow_node_ids = [
                el["source_ref"]
                for el in screen.get("elements", [])
            ]

        for note_geom, rule_text in validation_notes:
            target = _closest_flow_element(
                note_geom, flow_node_ids, el_by_source, index,
            )
            if target and _append_validation(target, rule_text):
                continue
            bound = False
            candidates = [
                el for el in screen.get("elements", [])
                if el.get("role") == "BUTTON"
            ] or list(screen.get("elements", []))
            for el in candidates[:_MAX_VALIDATION_BIND_ELEMENTS]:
                if _append_validation(el, rule_text):
                    bound = True
                    break
            if not bound:
                unbound_rules.append(f"{source_ref}: {rule_text[:80]}")

    for connector in (inventory or {}).get("connectors") or []:
        connector_id = connector.get("id", "")
        texts: list[str] = []
        label = (connector.get("label") or "").strip()
        if label and looks_like_rule(label):
            texts.append(label)
        for endpoint_key in ("start", "end"):
            ep = connector.get(endpoint_key) or {}
            ep_id = ep.get("endpoint_node_id")
            if not ep_id:
                continue
            inv_el = inv_elements.get(ep_id)
            if inv_el and inv_el.get("classification") == "CONTEXTUAL_ANNOTATION":
                note_txt = (inv_el.get("label") or text_cache.get(ep_id, "")).strip()
                if note_txt and looks_like_rule(note_txt):
                    texts.append(note_txt)
            elif ep_id in inv_elements:
                note_txt = (text_cache.get(ep_id, "") or inv_elements[ep_id].get("label", "")).strip()
                if note_txt and looks_like_rule(note_txt):
                    texts.append(note_txt)

        if not texts:
            continue

        trigger_element_id = trigger_by_connector.get(connector_id)
        target_el = element_id_by_trigger.get(trigger_element_id) if trigger_element_id else None
        if not target_el:
            from_screen = (connector.get("resolution") or {}).get("from_screen_id")
            if from_screen and from_screen in screen_by_source:
                screen = screen_by_source[from_screen]
                buttons = [el for el in screen.get("elements", []) if el.get("role") == "BUTTON"]
                target_el = buttons[0] if buttons else None
        for txt in texts:
            if target_el:
                _append_validation(target_el, txt)

    for screen in screens:
        screen_node = None
        for raw in pp.get("screens") or []:
            if raw.get("id") == screen.get("source_ref"):
                screen_node_id = raw.get("id")
                break
        else:
            screen_node_id = screen.get("source_ref")

        def walk_reactions(node: dict) -> None:
            nid = node.get("id")
            el = el_by_source.get(nid)
            if el:
                for val in _collect_non_nav_reaction_validations(node):
                    _append_validation(el, val)
            for child in node.get("children") or []:
                walk_reactions(child)

        node_tree = pp.get("node_tree") or {}

        def find_screen_node(tree: dict, target_id: str) -> dict | None:
            if tree.get("id") == target_id:
                return tree
            for child in tree.get("children") or []:
                found = find_screen_node(child, target_id)
                if found:
                    return found
            return None

        screen_node = find_screen_node(node_tree, screen_node_id)
        if screen_node:
            walk_reactions(screen_node)

    if unbound_rules:
        gaps.append({
            "field": "screens",
            "reason": (
                f"{len(unbound_rules)} validation note(s) could not be bound to a flow "
                f"element: {'; '.join(unbound_rules[:5])}"
                f"{'...' if len(unbound_rules) > 5 else ''}."
            ),
            "action": "Review screen_notes or add flow elements for these rules.",
            "severity": "INFO",
        })

    return gaps


# ---------------------------------------------------------------------------
# Role heuristic
# ---------------------------------------------------------------------------

_ROLE_KEYWORDS = {
    "button": "BUTTON", "btn": "BUTTON", "cta": "BUTTON",
    "input": "INPUT", "field": "INPUT", "textfield": "INPUT",
    "label": "LABEL", "text": "LABEL", "title": "LABEL",
    "toggle": "TOGGLE", "switch": "TOGGLE",
    "tab": "TAB",
    "list": "LIST",
    "image": "IMAGE", "img": "IMAGE", "icon": "IMAGE",
    "link": "LINK",
    "dropdown": "DROPDOWN", "select": "DROPDOWN",
    "slider": "SLIDER",
    "carousel": "CAROUSEL",
}

_TYPE_ROLE_MAP = {
    "TEXT": "LABEL",
    "INSTANCE": "BUTTON",   # best-effort; name keywords may refine
    "FRAME": "CONTAINER",
    "RECTANGLE": "IMAGE",
    "ELLIPSE": "IMAGE",
    "VECTOR": "IMAGE",
}


def infer_role(node_type: str, node_name: str) -> str:
    lower = node_name.lower()
    for kw, role in _ROLE_KEYWORDS.items():
        if kw in lower:
            return role
    return _TYPE_ROLE_MAP.get(node_type, "OTHER")


# ---------------------------------------------------------------------------
# Inventory loading
# ---------------------------------------------------------------------------

def resolve_inventory_path(preprocess_path: str, inventory_override: str | None) -> str:
    """Resolve inventory JSON path from preprocess stem or CLI override."""
    if inventory_override:
        return inventory_override
    base = os.path.basename(preprocess_path)
    if base.endswith("_pre-process.json"):
        stem = base[: -len("_pre-process.json")]
    else:
        stem = os.path.splitext(base)[0]
    workdir = os.path.dirname(os.path.abspath(preprocess_path))
    return os.path.join(workdir, stem + INVENTORY_SUFFIX)


def build_screen_flow_ids(inventory: dict | None) -> dict[str, list[str]]:
    """Map raw screen frame id -> sorted flow_element_ids from inventory."""
    if not inventory:
        return {}
    result: dict[str, list[str]] = {}
    for screen in inventory.get("screens") or []:
        sid = screen.get("id")
        flow_ids = screen.get("flow_element_ids") or []
        if sid and flow_ids:
            result[sid] = sorted(flow_ids)
    return result


def merge_screen_flow_ids(
    frame_ids: list[str],
    screen_flow_ids: dict[str, list[str]] | None,
) -> list[str]:
    """Union inventory flow_element_ids across all frame ids in a collapse group."""
    merged: set[str] = set()
    for fid in frame_ids:
        merged.update((screen_flow_ids or {}).get(fid, []))
    return sorted(merged)


def normalize_element_label(label: str) -> str:
    """Lowercase label with punctuation stripped and whitespace collapsed."""
    cleaned = re.sub(r"[^\w\s]", " ", (label or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def purpose_stem_from_element_id(element_id: str) -> str:
    """Return purpose portion of element_id with trailing _N suffix stripped."""
    if "." not in element_id:
        return element_id
    purpose = element_id.split(".", 1)[1]
    return re.sub(r"_\d+$", "", purpose)


def compute_outgoing_flow_signature(frame_id: str, pp: dict) -> frozenset[tuple[str, str]]:
    """Sorted-set signature of (to_screen_frame_id, connector_label) for outgoing edges."""
    edges_raw = (pp.get("edges") or []) + (pp.get("original_edges") or [])
    screen_ids = {s["id"] for s in (pp.get("screens") or [])}
    index = pp.get("index") or {}
    node_id_to_screen = pp.get("node_id_to_screen") or {}
    contextual_map = pp.get("contextual_node_id_to_screen") or {}
    signature: set[tuple[str, str]] = set()
    for edge in edges_raw:
        from_screen = resolve_screen_for_connector_endpoint(
            edge, "from", screen_ids, index, node_id_to_screen, contextual_map,
        )
        if from_screen != frame_id:
            continue
        to_screen = resolve_screen_for_connector_endpoint(
            edge, "to", screen_ids, index, node_id_to_screen, contextual_map,
        )
        if not to_screen:
            continue
        label = (edge.get("label") or "").strip()
        signature.add((to_screen, label))
    return frozenset(signature)


def flow_signatures_compatible(signatures: list[frozenset]) -> bool:
    """True when every pair of flow signatures is subset-equal."""
    if len(signatures) <= 1:
        return True
    for i, sig_a in enumerate(signatures):
        for sig_b in signatures[i + 1:]:
            if not (sig_a <= sig_b or sig_b <= sig_a):
                return False
    return True


def plan_screen_groups(
    screens_raw: list[dict],
    pp: dict,
    qualifiers_by_id: dict[str, str | None],
) -> tuple[list[dict], dict]:
    """Plan screen collapse groups and the screen_collapse_map scaffold.

    Returns (build_groups, collapse_map) where build_groups drives
    :func:`build_screens` and collapse_map is written as screen_collapse_map.json.
    """
    screen_context = pp.get("screen_context") or {}
    index = pp.get("index") or {}
    raw_by_id = {s["id"]: s for s in screens_raw}

    by_screen_id: dict[str, list[str]] = {}
    for s in screens_raw:
        screen_id = to_upper_snake(s.get("name", ""))
        by_screen_id.setdefault(screen_id, []).append(s["id"])

    by_raw_name: dict[str, list[str]] = {}
    for s in screens_raw:
        by_raw_name.setdefault(s.get("name", ""), []).append(s["id"])

    build_groups: list[dict] = []
    auto_collapsed: list[dict] = []
    candidates: list[dict] = []

    def outgoing_summary(frame_ids: list[str]) -> dict[str, list[str]]:
        summary: dict[str, list[str]] = {}
        for fid in frame_ids:
            sig = compute_outgoing_flow_signature(fid, pp)
            targets = sorted({
                to_upper_snake(raw_by_id.get(to_frame, {}).get("name", to_frame))
                for to_frame, _label in sig
            })
            summary[fid] = targets
        return summary

    for raw_name, frame_ids in sorted(by_raw_name.items()):
        frame_ids = sorted(frame_ids)
        screen_id = to_upper_snake(raw_name)

        if len(frame_ids) == 1:
            build_groups.append({
                "screen_id": screen_id,
                "frame_ids": frame_ids,
                "tier": "SINGLE",
                "raw_names": [raw_name],
                "signals": [],
            })
            continue

        signatures = [compute_outgoing_flow_signature(fid, pp) for fid in frame_ids]
        if not flow_signatures_compatible(signatures):
            signals = ["divergent_outgoing_targets"]
            candidates.append({
                "screen_id": screen_id,
                "frame_ids": frame_ids,
                "tier": "AMBIGUOUS",
                "signals": signals,
                "raw_names": [raw_name],
                "outgoing_summary": outgoing_summary(frame_ids),
                "recommendation": "keep_split",
            })
            for fid in frame_ids:
                build_groups.append({
                    "screen_id": screen_id,
                    "frame_ids": [fid],
                    "tier": "AMBIGUOUS",
                    "raw_names": [raw_name],
                    "signals": signals,
                })
        else:
            auto_collapsed.append({
                "screen_id": screen_id,
                "frame_ids": frame_ids,
                "tier": "AUTO",
                "signals": [],
            })
            build_groups.append({
                "screen_id": screen_id,
                "frame_ids": frame_ids,
                "tier": "AUTO",
                "raw_names": [raw_name],
                "signals": [],
            })

    for screen_id, frame_ids in sorted(by_screen_id.items()):
        raw_names = sorted({raw_by_id[fid].get("name", "") for fid in frame_ids})
        if len(raw_names) <= 1:
            continue
        frame_ids = sorted(frame_ids)
        candidates.append({
            "screen_id": screen_id,
            "frame_ids": frame_ids,
            "tier": "AMBIGUOUS",
            "signals": ["name_variant"],
            "raw_names": raw_names,
            "outgoing_summary": outgoing_summary(frame_ids),
            "recommendation": "keep_split",
        })

    collapse_map = {
        "auto_collapsed": auto_collapsed,
        "candidates": candidates,
        "decisions": [],
    }
    return build_groups, collapse_map


def merge_semantic_elements(
    elements: list[dict],
    qualifiers_by_id: dict[str, str | None] | None = None,
) -> list[dict]:
    """Merge semantic twins on a collapsed screen into canonical element_id rows."""
    if not elements:
        return elements

    qualifiers_by_id = qualifiers_by_id or {}
    groups: dict[tuple, list[dict]] = {}
    order: list[tuple] = []
    for el in elements:
        key = (
            el.get("role", ""),
            normalize_element_label(el.get("label", "")),
            purpose_stem_from_element_id(el.get("element_id", "")),
        )
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(el)

    merged: list[dict] = []
    for key in order:
        twins = groups[key]
        screen_id = twins[0]["element_id"].split(".", 1)[0]
        canonical_element_id = f"{screen_id}.{purpose_stem_from_element_id(twins[0]['element_id'])}"
        for idx, twin in enumerate(twins):
            out = {k: v for k, v in twin.items() if not k.startswith("_")}
            out["element_id"] = canonical_element_id
            frame_id = twin.get("_frame_id")
            qual = twin.get("_frame_qualifier")
            if qual is None and frame_id:
                qual = qualifiers_by_id.get(frame_id)
            if qual:
                out["states_represented"] = [qual]
            elif len(twins) > 1:
                out["states_represented"] = [f"Variant {idx + 1}"]
            merged.append(out)
    return merged


def pick_representative_frame(
    frame_ids: list[str],
    screens_raw: list[dict],
    screen_context: dict,
    index: dict,
) -> str:
    """Pick entry-point frame when present, else top-left by spatial sort."""
    raw_by_id = {s["id"]: s for s in screens_raw}
    for fid in frame_ids:
        if screen_context.get(fid, {}).get("is_entry_point"):
            return fid
    return sorted(
        frame_ids,
        key=lambda fid: (
            raw_by_id[fid].get("abs_y", index.get(fid, {}).get("abs_y", 0)),
            raw_by_id[fid].get("abs_x", index.get(fid, {}).get("abs_x", 0)),
        ),
    )[0]


def write_screen_collapse_map(path: str, collapse_map: dict) -> None:
    """Write screen_collapse_map.json scaffold."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(collapse_map, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Element extraction
# ---------------------------------------------------------------------------

def find_node_in_subtree(root: dict, node_id: str) -> dict | None:
    """DFS lookup of a node dict by id within a screen subtree."""
    if root.get("id") == node_id:
        return root
    for child in root.get("children") or []:
        found = find_node_in_subtree(child, node_id)
        if found is not None:
            return found
    return None


def build_element_from_node(
    node: dict,
    screen_id: str,
    text_cache: dict,
    seen_purposes: dict[str, int],
) -> dict:
    """Build one element dict from a flow-relevant node."""
    node_id = node.get("id", "")
    node_type = node.get("type", "UNKNOWN")
    node_name = node.get("name", "")

    label = text_cache.get(node_id, "") or node_name
    role = infer_role(node_type, node_name)

    purpose_base = ""
    if label:
        cleaned_label = re.sub(r"[^a-zA-Z\s]", "", label).strip()
        words = [w for w in cleaned_label.split() if w]
        if words and len(words) <= 5:
            purpose_base = "_".join(w.lower() for w in words)
        elif words:
            purpose_base = "_".join(w.lower() for w in words[:4])

    if not purpose_base:
        purpose_base = to_lower_snake(node_name) if node_name else "element"

    if purpose_base.startswith("text_"):
        purpose_base = purpose_base.replace("text_", "", 1)

    role_suffix = {
        "BUTTON": "_btn", "INPUT": "_input", "LABEL": "_lbl",
        "TOGGLE": "_toggle", "TAB": "_tab", "LIST": "_list",
        "IMAGE": "_img", "LINK": "_link", "DROPDOWN": "_dropdown",
        "SLIDER": "_slider", "CAROUSEL": "_carousel",
        "CONTAINER": "_container", "OTHER": "",
    }.get(role, "")

    purpose = purpose_base + role_suffix
    count = seen_purposes.get(purpose, 0)
    seen_purposes[purpose] = count + 1
    if count > 0:
        purpose = f"{purpose}_{count + 1}"

    element_id = f"{screen_id}.{purpose}"

    interactions = []
    for reaction in node.get("reactions") or []:
        action = reaction.get("action") or {}
        trigger_type = (reaction.get("trigger") or {}).get("type", "ON_CLICK")
        dest_id = action.get("destinationId")
        interactions.append({
            "trigger": trigger_type,
            "action": action.get("type", "NAVIGATE"),
            **({"destination_node_id": dest_id} if dest_id else {}),
        })

    return {
        "element_id": element_id,
        "source_ref": node_id,
        "type": node_type,
        "role": role,
        "label": label[:200] if label else "",
        "interactions": interactions,
        "validations_and_edge_cases": [],
    }


def connector_roles_for_nodes(pp: dict, node_ids: set[str]) -> dict[str, set[str]]:
    """Return node_id -> {'outgoing', 'incoming'} from preprocess edges."""
    roles: dict[str, set[str]] = {nid: set() for nid in node_ids}
    edges_raw = (pp.get("edges") or []) + (pp.get("original_edges") or [])
    for edge in edges_raw:
        from_node = edge.get("original_from") or edge.get("from")
        to_node = edge.get("original_to") or edge.get("to")
        if from_node in node_ids:
            roles.setdefault(from_node, set()).add("outgoing")
        if to_node in node_ids:
            roles.setdefault(to_node, set()).add("incoming")
    return roles


def _is_descendant_of(
    descendant_id: str,
    ancestor_id: str,
    screen_id: str,
    index: dict,
) -> bool:
    """True when descendant_id is nested under ancestor_id within the screen subtree."""
    curr = index.get(descendant_id, {}).get("parent_id")
    while curr and curr != screen_id:
        if curr == ancestor_id:
            return True
        curr = index.get(curr, {}).get("parent_id")
    return False


def select_flow_nodes_for_screen(
    screen_id: str,
    candidate_ids: list[str],
    pp: dict,
    connector_roles: dict[str, set[str]],
    connector_destinations: set[str] | None = None,
) -> list[str]:
    """Apply outgoing-prefer dedup: drop incoming-only ancestors superseded by descendants.

    Incoming-only nodes that are connector destinations are always kept.
    """
    if not candidate_ids:
        return []

    destinations = connector_destinations or set()
    candidates = set(candidate_ids)
    index = pp.get("index") or {}
    roles = connector_roles

    def is_incoming_only(nid: str) -> bool:
        node_roles = roles.get(nid, set())
        return "incoming" in node_roles and "outgoing" not in node_roles

    def has_outgoing(nid: str) -> bool:
        return "outgoing" in roles.get(nid, set())

    def is_candidate_leaf(nid: str) -> bool:
        return not any(
            other != nid and _is_descendant_of(other, nid, screen_id, index)
            for other in candidates
        )

    kept = []
    for node_id in candidate_ids:
        if node_id in destinations and is_incoming_only(node_id):
            kept.append(node_id)
            continue
        drop = False
        if is_incoming_only(node_id):
            for other in candidates:
                if other == node_id:
                    continue
                if not _is_descendant_of(other, node_id, screen_id, index):
                    continue
                if has_outgoing(other) or is_candidate_leaf(other):
                    drop = True
                    break
        if not drop:
            kept.append(node_id)
    return kept


def extract_elements(
    screen_node: dict,
    screen_id: str,
    text_cache: dict,
    flow_node_ids: list[str] | None = None,
    pp: dict | None = None,
    seen_purposes: dict[str, int] | None = None,
    connector_destinations: set[str] | None = None,
) -> tuple[list, list[str]]:
    """Build elements[] from inventory flow ids (nested) or direct children (fallback).

    Returns (elements, missing_flow_ids) where missing_flow_ids lists inventory ids
    not found in the screen subtree.

    ``seen_purposes`` is keyed by purpose stem and scoped to one logical ``screen_id``
    across all state frames. Pass a shared registry from :func:`build_screens` so
  sibling frames do not reuse the same ``element_id``.
    """
    elements = []
    purpose_registry = seen_purposes if seen_purposes is not None else {}
    missing: list[str] = []

    if flow_node_ids is not None and pp is not None:
        connector_roles = connector_roles_for_nodes(pp, set(flow_node_ids))
        destinations = connector_destinations or set()
        selected_ids = select_flow_nodes_for_screen(
            screen_node.get("id", ""),
            flow_node_ids,
            pp,
            connector_roles,
            connector_destinations=destinations,
        )
        expanded_ids: list[str] = list(selected_ids)
        seen_expanded = set(expanded_ids)
        for node_id in selected_ids:
            if node_id not in destinations:
                continue
            node = find_node_in_subtree(screen_node, node_id)
            if not node or node.get("type") not in ("FRAME", "GROUP"):
                continue
            for iid in collect_interaction_instance_ids(node):
                if iid not in seen_expanded:
                    seen_expanded.add(iid)
                    expanded_ids.append(iid)
        for node_id in expanded_ids:
            node = find_node_in_subtree(screen_node, node_id)
            if node is None:
                missing.append(node_id)
                continue
            elements.append(
                build_element_from_node(node, screen_id, text_cache, purpose_registry)
            )
        return elements, missing

    children = screen_node.get("children") or []
    for child in children:
        elements.append(
            build_element_from_node(child, screen_id, text_cache, purpose_registry)
        )
    return elements, missing


def find_duplicate_element_ids(screens: list) -> list[dict]:
    """Return true-collision duplicates — not intentional canonical twins."""
    grouped: dict[tuple[str, str], list[dict]] = {}
    for screen in screens:
        screen_id = screen.get("screen_id", "")
        for el in screen.get("elements", []):
            element_id = el.get("element_id", "")
            source_ref = el.get("source_ref", "")
            if not element_id or not source_ref:
                continue
            key = (screen_id, element_id)
            grouped.setdefault(key, []).append(el)

    duplicates = []
    for (screen_id, element_id), elements in sorted(grouped.items()):
        if len(elements) <= 1:
            continue
        labels = {normalize_element_label(el.get("label", "")) for el in elements}
        all_have_states = all(el.get("states_represented") for el in elements)
        if len(labels) == 1 and all_have_states:
            continue
        source_refs = []
        for el in elements:
            ref = el.get("source_ref", "")
            if ref and ref not in source_refs:
                source_refs.append(ref)
        duplicates.append({
            "screen_id": screen_id,
            "element_id": element_id,
            "source_refs": source_refs,
        })
    return duplicates


def find_intentional_canonical_dupes(screens: list) -> list[dict]:
    """Return canonical duplicate groups allowed by the collapse policy."""
    grouped: dict[tuple[str, str], list[dict]] = {}
    for screen in screens:
        screen_id = screen.get("screen_id", "")
        for el in screen.get("elements", []):
            element_id = el.get("element_id", "")
            source_ref = el.get("source_ref", "")
            if not element_id or not source_ref:
                continue
            key = (screen_id, element_id)
            grouped.setdefault(key, []).append(el)

    intentional = []
    for (screen_id, element_id), elements in sorted(grouped.items()):
        if len(elements) <= 1:
            continue
        labels = {normalize_element_label(el.get("label", "")) for el in elements}
        all_have_states = all(el.get("states_represented") for el in elements)
        if len(labels) == 1 and all_have_states:
            source_refs = []
            for el in elements:
                ref = el.get("source_ref", "")
                if ref and ref not in source_refs:
                    source_refs.append(ref)
            intentional.append({
                "screen_id": screen_id,
                "element_id": element_id,
                "source_refs": source_refs,
            })
    return intentional


def duplicate_element_gaps(
    duplicates: list[dict],
    intentional: list[dict] | None = None,
) -> list[dict]:
    """Build extraction_gaps entries for duplicate element_id collisions."""
    gaps = []
    for dup in duplicates:
        refs = ", ".join(dup["source_refs"])
        gaps.append({
            "field": "screens",
            "reason": (
                f"Duplicate element_id '{dup['element_id']}' on screen "
                f"'{dup['screen_id']}' for {len(dup['source_refs'])} distinct "
                f"Figma nodes: {refs}."
            ),
            "action": (
                "Ensure mechanical _N suffixes are applied per logical screen_id, "
                "or refine with source_ref so each node keeps a unique element_id."
            ),
            "severity": "WARN",
        })
    for dup in intentional or []:
        refs = ", ".join(dup["source_refs"])
        gaps.append({
            "field": "screens",
            "reason": (
                f"Intentional canonical duplicate '{dup['element_id']}' on screen "
                f"'{dup['screen_id']}' across {len(dup['source_refs'])} state "
                f"variants: {refs}."
            ),
            "action": (
                "Use states_represented and trigger_source_ref on ui_flow edges "
                "to disambiguate twins during automation."
            ),
            "severity": "INFO",
        })
    return gaps


def collect_flow_element_instances(
    pp: dict,
    screens: list,
    ui_flow: list,
) -> list[dict]:
    """Return one record per flow-relevant element instance (not deduped by element_id)."""
    flow_node_ids: set[str] = set()
    for edge in ui_flow:
        trigger_id = edge.get("trigger_element_id")
        if not trigger_id:
            continue
        for screen in screens:
            for el in screen.get("elements", []):
                if el.get("element_id") == trigger_id:
                    flow_node_ids.add(el["source_ref"])

    el_by_source: dict[str, dict] = {}
    for screen in screens:
        for el in screen.get("elements", []):
            el_by_source[el["source_ref"]] = {
                "element_id": el["element_id"],
                "source_ref": el["source_ref"],
                "screen_id": screen.get("screen_id", ""),
            }

    for edge in (pp.get("edges") or []) + (pp.get("original_edges") or []):
        for key in ("original_to", "to", "original_from", "from"):
            node_id = edge.get(key)
            if node_id:
                flow_node_ids.add(node_id)

    instances = []
    for node_id in sorted(flow_node_ids):
        if node_id in el_by_source:
            instances.append(el_by_source[node_id])
    return instances


def build_element_id_quality_report(
    instances: list[dict],
    screens: list | None = None,
) -> list[dict]:
    """Assess flow element IDs; flag DUPLICATE when one id maps to multiple source_refs."""
    element_meta: dict[tuple[str, str, str], dict] = {}
    if screens:
        for screen in screens:
            screen_id = screen.get("screen_id", "")
            for el in screen.get("elements", []):
                element_meta[(screen_id, el.get("element_id", ""), el.get("source_ref", ""))] = el

    grouped: dict[tuple[str, str], list[str]] = {}
    for inst in instances:
        key = (inst["screen_id"], inst["element_id"])
        refs = grouped.setdefault(key, [])
        if inst["source_ref"] not in refs:
            refs.append(inst["source_ref"])

    results = []
    seen: set[tuple[str, str, str]] = set()
    for inst in instances:
        dedupe_key = (
            inst["screen_id"],
            inst["element_id"],
            inst["source_ref"],
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        entry = assess_element_id_quality(inst["element_id"])
        entry["screen_id"] = inst["screen_id"]
        entry["source_ref"] = inst["source_ref"]
        refs = grouped.get((inst["screen_id"], inst["element_id"]), [])
        if len(refs) > 1:
            dup_els = [
                element_meta[(inst["screen_id"], inst["element_id"], ref)]
                for ref in refs
                if (inst["screen_id"], inst["element_id"], ref) in element_meta
            ]
            labels = {normalize_element_label(el.get("label", "")) for el in dup_els}
            all_have_states = all(el.get("states_represented") for el in dup_els)
            if not (len(labels) == 1 and all_have_states and dup_els):
                entry["quality"] = "DUPLICATE"
                entry["source_refs"] = refs
        results.append(entry)

    return sorted(results, key=lambda row: (row["element_id"], row["source_ref"]))


# ---------------------------------------------------------------------------
# Screen extraction
# ---------------------------------------------------------------------------

def build_screens(
    pp: dict,
    input_data: dict | None,
    screen_flow_ids: dict[str, list[str]] | None = None,
    use_inventory: bool = False,
) -> tuple[list, list[dict], dict]:
    """Build screens[] — one object per logical screen (AUTO-collapsed variants).

    Returns (screens, inventory_extraction_gaps, collapse_map).
    """
    screens_raw = pp.get("screens") or []
    screen_context = pp.get("screen_context") or {}
    text_cache = pp.get("text_cache") or {}
    node_tree = pp.get("node_tree") or {}
    index = pp.get("index") or {}
    connector_destinations = connector_destination_node_ids(pp)

    screen_node_lookup: dict[str, dict] = {}

    def _find_screens(node):
        nid = node.get("id", "")
        if nid in {s["id"] for s in screens_raw}:
            screen_node_lookup[nid] = node
        for child in node.get("children") or []:
            _find_screens(child)

    _find_screens(node_tree)

    qualifiers_by_id: dict[str, str | None] = {}
    for s in screens_raw:
        sid = s["id"]
        screen_geom = _node_geom(s)
        state_label = pick_state_label_text(
            s.get("contextual_informations") or [],
            text_cache,
            screen_geom,
        )
        qualifiers_by_id[sid] = derive_frame_qualifier(s.get("name", ""), state_label)
    qualifiers_by_id = disambiguate_sibling_qualifiers(screens_raw, qualifiers_by_id)

    build_groups, collapse_map = plan_screen_groups(screens_raw, pp, qualifiers_by_id)
    raw_by_id = {s["id"]: s for s in screens_raw}

    result = []
    inventory_gaps: list[dict] = []
    seen_purposes_by_screen: dict[str, dict[str, int]] = {}

    for group in build_groups:
        frame_ids = group["frame_ids"]
        screen_id = group["screen_id"]
        rep_frame = pick_representative_frame(
            frame_ids, screens_raw, screen_context, index,
        )
        rep_raw = raw_by_id[rep_frame]

        screen_states: list[str] = []
        state_kinds: list[str] = []
        for fid in frame_ids:
            q = qualifiers_by_id.get(fid)
            if q and q not in screen_states:
                screen_states.append(q)
        state_kinds = list({qualifier_to_state_kind(q) for q in screen_states}) if screen_states else []

        screen_notes_parts: list[str] = []
        for fid in frame_ids:
            s = raw_by_id[fid]
            screen_geom = _node_geom(s)
            state_label_text = pick_state_label_text(
                s.get("contextual_informations") or [],
                text_cache,
                screen_geom,
            )
            notes = build_screen_notes(
                s.get("contextual_informations") or [],
                text_cache,
                screen_geom,
                state_label_text,
            )
            if notes and notes not in screen_notes_parts:
                screen_notes_parts.append(notes)
        screen_notes = " | ".join(screen_notes_parts)[:300]

        purpose_registry = seen_purposes_by_screen.setdefault(screen_id, {})
        all_elements: list[dict] = []

        for fid in frame_ids:
            s = raw_by_id[fid]
            screen_node = screen_node_lookup.get(fid)
            if not screen_node:
                continue
            frame_flow_ids = (screen_flow_ids or {}).get(fid) if use_inventory else None
            if use_inventory and frame_flow_ids is not None:
                elements, missing = extract_elements(
                    screen_node,
                    screen_id,
                    text_cache,
                    frame_flow_ids,
                    pp,
                    seen_purposes=purpose_registry,
                    connector_destinations=connector_destinations,
                )
                if missing:
                    inventory_gaps.append({
                        "field": "screens",
                        "reason": (
                            f"Screen {screen_id} ({fid}): {len(missing)} inventory "
                            f"flow_element_id(s) not found in screen subtree: "
                            f"{', '.join(missing[:10])}"
                            f"{'...' if len(missing) > 10 else ''}."
                        ),
                        "action": (
                            "Check inventory/preprocess version skew or pruned node_tree "
                            "coverage for this screen."
                        ),
                        "severity": "INFO",
                    })
            else:
                elements, _ = extract_elements(
                    screen_node,
                    screen_id,
                    text_cache,
                    seen_purposes=purpose_registry,
                )
            for el in elements:
                tagged = dict(el)
                tagged["_frame_id"] = fid
                tagged["_frame_qualifier"] = qualifiers_by_id.get(fid)
                all_elements.append(tagged)

        elements = merge_semantic_elements(all_elements, qualifiers_by_id)

        obj = {
            "screen_id": screen_id,
            "screen_name": rep_raw.get("name", ""),
            "source_ref": rep_frame,
            "source_refs": sorted(frame_ids),
            "node_class": "SCREEN",
            "classified_by": "GEOMETRY",
            "entry_point": any(
                screen_context.get(fid, {}).get("is_entry_point") for fid in frame_ids
            ),
            "screen_states": screen_states,
            "state_kinds": state_kinds,
            "elements": elements,
            "screen_notes": screen_notes,
        }
        result.append(obj)

    return result, inventory_gaps, collapse_map


# ---------------------------------------------------------------------------
# ui_flow — BFS ordered
# ---------------------------------------------------------------------------

def collect_flow_element_ids(pp: dict, screens: list, ui_flow: list) -> list[str]:
    """Union of outgoing trigger IDs and incoming connector-destination element IDs."""
    ids: set[str] = set()
    for edge in ui_flow:
        trigger_id = edge.get("trigger_element_id")
        if trigger_id:
            ids.add(trigger_id)

    node_id_to_element_id: dict[str, str] = {}
    for screen in screens:
        for el in screen.get("elements", []):
            node_id_to_element_id[el["source_ref"]] = el["element_id"]

    edges_raw = (pp.get("edges") or []) + (pp.get("original_edges") or [])
    for edge in edges_raw:
        to_node = edge.get("original_to") or edge.get("to")
        if to_node:
            element_id = node_id_to_element_id.get(to_node)
            if element_id:
                ids.add(element_id)

    return sorted(ids)


def build_ui_flow(pp: dict, screens: list) -> tuple[list, list[dict]]:
    """Build ui_flow[] in BFS order.

    Order:
    1. ENTRY pseudo-edges (one per entry point, in entry_points list order).
    2. BFS waves from all entry-point node ids simultaneously.
    3. Orphan edges (unreachable screens), sorted by source screen (abs_y, abs_x).

    Returns (ui_flow, trigger_remaps) where trigger_remaps logs mockup trigger rewires.
    """
    edges_raw = (pp.get("edges") or []) + (pp.get("original_edges") or [])
    entry_points = pp.get("entry_points") or []
    screens_raw = pp.get("screens") or []
    index = pp.get("index") or {}
    node_id_to_screen = pp.get("node_id_to_screen") or {}
    contextual_map = pp.get("contextual_node_id_to_screen") or {}

    screen_ids = {s["id"] for s in screens_raw}
    node_id_to_screen_id: dict[str, str] = {}
    for s in screens:
        for ref in s.get("source_refs") or [s["source_ref"]]:
            node_id_to_screen_id[ref] = s["screen_id"]
    node_id_to_screen_raw: dict[str, dict] = {
        s["id"]: s for s in screens_raw
    }
    outgoing_candidates = build_outgoing_trigger_candidates(pp, screen_ids)

    node_id_to_element_id = {}
    for s in screens:
        for el in s.get("elements", []):
            node_id_to_element_id[el["source_ref"]] = el["element_id"]

    # Resolve each connector to its originating and destination screen
    resolved_edges = []
    for e in edges_raw:
        from_node = e.get("original_from") or e.get("from")
        to_node = e.get("original_to") or e.get("to")
        from_screen = resolve_screen_for_connector_endpoint(
            e, "from", screen_ids, index, node_id_to_screen, contextual_map,
        )
        to_screen = resolve_screen_for_connector_endpoint(
            e, "to", screen_ids, index, node_id_to_screen, contextual_map,
        )

        # Drop true self-loops (same screen AND same source element)
        if from_screen and to_screen:
            if from_screen == to_screen and from_node == to_node:
                continue
            resolved_edges.append({
                "id": e.get("id") or f"{from_node}->{to_node}",
                "from_screen": from_screen,
                "to_screen": to_screen,
                "from_source_ref": from_node,
                "to_source_ref": to_node,
                "label": e.get("label") or "",
                "snapped": e.get("snapped", False),
            })

    # Group by from_screen
    edges_by_from: dict[str, list[dict]] = {}
    for e in resolved_edges:
        edges_by_from.setdefault(e["from_screen"], []).append(e)

    trigger_remaps: list[dict] = []

    def _make_flow_edge(e: dict) -> dict:
        from_s_id = e["from_screen"]
        to_s_id = e["to_screen"]

        trigger_node_id = e["from_source_ref"]
        resolved_trigger, remapped = resolve_trigger_node_id(
            trigger_node_id,
            from_s_id,
            index,
            outgoing_candidates.get(from_s_id, set()),
        )
        final_trigger_node_id = resolved_trigger
        trigger_element_id = node_id_to_element_id.get(resolved_trigger)

        mockup_trigger = (
            is_mockup_trigger_node(index, trigger_node_id)
            or is_mockup_trigger_node(index, resolved_trigger)
        )
        if mockup_trigger or not trigger_element_id:
            for nid in sorted(outgoing_candidates.get(from_s_id, set())):
                if is_mockup_trigger_node(index, nid):
                    continue
                candidate_id = node_id_to_element_id.get(nid)
                if candidate_id:
                    if nid != resolved_trigger:
                        trigger_remaps.append({
                            "connector_id": e["id"],
                            "from_node": trigger_node_id,
                            "to_node": nid,
                        })
                    trigger_element_id = candidate_id
                    final_trigger_node_id = nid
                    break
        elif remapped:
            trigger_remaps.append({
                "connector_id": e["id"],
                "from_node": trigger_node_id,
                "to_node": resolved_trigger,
            })

        edge = {
            "from_screen_id": node_id_to_screen_id.get(from_s_id, to_upper_snake(
                node_id_to_screen_raw.get(from_s_id, {}).get("name", from_s_id)
            )),
            "to_screen_id": node_id_to_screen_id.get(to_s_id, to_upper_snake(
                node_id_to_screen_raw.get(to_s_id, {}).get("name", to_s_id)
            )),
            "from_source_ref": from_s_id,
            "to_source_ref": to_s_id,
            "condition": e["label"],
            "navigation_kind": "NAVIGATE",
            "edge_source": "CONNECTOR" if not e["snapped"] else "CONNECTOR_INFERRED",
            "confidence": "EXPLICIT" if not e["snapped"] else "INFERRED",
            "source_ref": e["id"],
        }

        if trigger_element_id:
            edge["trigger_element_id"] = trigger_element_id
            edge["trigger_source_ref"] = final_trigger_node_id

        return edge

    result: list[dict] = []

    # --- 1. ENTRY pseudo-edges ---
    entry_node_ids = [ep["id"] for ep in entry_points]
    entry_reasons = {ep["id"]: ep.get("reason", "ENTRY_TOPOLOGY") for ep in entry_points}

    for ep_id in entry_node_ids:
        screen_id = node_id_to_screen_id.get(ep_id, to_upper_snake(
            node_id_to_screen_raw.get(ep_id, {}).get("name", ep_id)
        ))
        reason = entry_reasons.get(ep_id, "ENTRY_TOPOLOGY")
        edge_source = "ENTRY_LABEL" if reason in ("EXPLICIT", "CONTEXT") else "ENTRY_TOPOLOGY"
        confidence = "EXPLICIT" if reason in ("EXPLICIT", "CONTEXT") else "INFERRED"
        result.append({
            "from_screen_id": "ENTRY",
            "to_screen_id": screen_id,
            "to_source_ref": ep_id,
            "condition": "",
            "navigation_kind": "ENTRY",
            "edge_source": edge_source,
            "confidence": confidence,
            "source_ref": ep_id,
        })

    # --- 2. BFS waves ---
    visited: set[str] = set(entry_node_ids)
    queue: deque[str] = deque(entry_node_ids)
    emitted_edge_ids: set[str] = set()

    while queue:
        current = queue.popleft()
        for e in edges_by_from.get(current, []):
            eid = e["id"]
            if eid in emitted_edge_ids:
                continue
            emitted_edge_ids.add(eid)
            result.append(_make_flow_edge(e))
            dest = e["to_screen"]
            if dest not in visited:
                visited.add(dest)
                queue.append(dest)

    # --- 3. Orphan edges (BFS-unreachable sources) ---
    orphan_edges = [
        e for e in resolved_edges
        if e["id"] not in emitted_edge_ids
    ]

    def _spatial_key(e: dict):
        src = index.get(e["from_screen"]) or {}
        return (src.get("abs_y", 0), src.get("abs_x", 0))

    orphan_edges.sort(key=_spatial_key)
    for e in orphan_edges:
        if e["id"] not in emitted_edge_ids:
            emitted_edge_ids.add(e["id"])
            result.append(_make_flow_edge(e))

    return result, trigger_remaps


# ---------------------------------------------------------------------------
# Extraction gaps
# ---------------------------------------------------------------------------

def build_gaps(
    pp: dict,
    input_data: dict | None,
    inventory_gaps: list[dict] | None = None,
    inventory_missing: bool = False,
) -> list:
    gaps = list(inventory_gaps or [])

    if inventory_missing:
        gaps.append({
            "field": "screens",
            "reason": (
                "Inventory file missing; used direct-child fallback for element extraction."
            ),
            "action": (
                "Re-run render_design.py preprocess to generate <stem>_inventory.json."
            ),
            "severity": "INFO",
        })
    scope = (input_data or {}).get("scope", "page") if input_data else "unknown"

    if scope == "selection":
        gaps.append({
            "field": "ui_flow",
            "reason": (
                "Export scope is 'selection': connectors leaving the selected frames "
                "are not present, so ui_flow coverage cannot be verified."
            ),
            "action": "Re-export the full page to get a complete flow graph.",
            "severity": "INFO",
        })

    for u in pp.get("unresolved") or []:
        gaps.append({
            "field": "ui_flow",
            "reason": (
                f"Connector {u.get('id', '?')} could not be resolved to a screen-to-screen edge: "
                f"{u.get('reason', 'unknown reason')}."
            ),
            "action": "Check connector endpoints in Figma; re-attach to the target screen frame.",
            "severity": "INFO",
        })

    return gaps


# ---------------------------------------------------------------------------
# design_source
# ---------------------------------------------------------------------------

def build_design_source(input_data: dict) -> dict:
    file_info = input_data.get("file") or {}
    export_info = input_data.get("export") or {}
    truncated_nodes = export_info.get("truncatedNodes") or []
    return {
        "file_name": file_info.get("name", ""),
        "page_name": file_info.get("page", ""),
        "scope": input_data.get("scope", "page"),
        "exported_at": input_data.get("exportedAt", ""),
        "max_depth": export_info.get("maxDepth"),
        "node_count": export_info.get("nodeCount"),
        "truncated_count": export_info.get("truncatedCount", 0),
        "has_geometry": True,
        "truncated_nodes": [
            {k: v for k, v in n.items() if k in ("id", "name", "type")}
            for n in truncated_nodes[:20]
        ],
    }


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate(output: dict, schema_path: str) -> bool:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        print("WARNING: jsonschema not installed — skipping schema validation.", file=sys.stderr)
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
# Main assembly
# ---------------------------------------------------------------------------

def extract(
    preprocess_path: str,
    input_path: str,
    output_path: str,
    workdir: str,
    inventory_path: str | None = None,
) -> None:
    # Load pre-process JSON
    with open(preprocess_path, "r", encoding="utf-8") as f:
        pp = json.load(f)

    # Load original input for design_source + app inference
    input_data: dict | None = None
    if input_path and os.path.exists(input_path):
        with open(input_path, "r", encoding="utf-8") as f:
            input_data = json.load(f)

    # --- design_source ---
    design_source: dict | None = None
    if input_data:
        design_source = build_design_source(input_data)

    # --- app inference ---
    file_name = (input_data or {}).get("file", {}).get("name", "")
    page_name = (input_data or {}).get("file", {}).get("page", "")
    if not file_name:
        file_name = os.path.splitext(os.path.basename(input_path or preprocess_path))[0]
    app = infer_app(file_name, page_name)

    # --- inventory (optional) ---
    resolved_inventory_path = resolve_inventory_path(preprocess_path, inventory_path)
    inventory: dict | None = None
    use_inventory = False
    if os.path.exists(resolved_inventory_path):
        with open(resolved_inventory_path, "r", encoding="utf-8") as f:
            inventory = json.load(f)
        use_inventory = True
    screen_flow_ids = build_screen_flow_ids(inventory)
    if use_inventory and screen_flow_ids:
        screen_flow_ids = augment_screen_flow_ids(screen_flow_ids, pp)

    # --- screens ---
    screens, inventory_extraction_gaps, collapse_map = build_screens(
        pp, input_data, screen_flow_ids, use_inventory=use_inventory
    )
    collapse_map_path = os.path.join(workdir, "screen_collapse_map.json")
    write_screen_collapse_map(collapse_map_path, collapse_map)

    # --- ui_flow ---
    ui_flow, trigger_remaps = build_ui_flow(pp, screens)

    # --- validations enrichment ---
    validation_gaps = attach_validations(screens, pp, inventory, ui_flow)

    # --- element_id quality assessment ---
    flow_instances = collect_flow_element_instances(pp, screens, ui_flow)
    quality_results = build_element_id_quality_report(flow_instances, screens)
    quality_path = os.path.join(workdir, "element_id_quality.json")
    with open(quality_path, "w", encoding="utf-8") as f:
        json.dump(quality_results, f, ensure_ascii=False, indent=2)

    # --- extraction_gaps ---
    duplicate_ids = find_duplicate_element_ids(screens)
    intentional_dupes = find_intentional_canonical_dupes(screens)
    gaps = build_gaps(
        pp,
        input_data,
        inventory_gaps=inventory_extraction_gaps,
        inventory_missing=not use_inventory,
    )
    gaps.extend(connector_ui_flow_parity_gaps(pp, ui_flow, inventory))
    gaps.extend(mockup_trigger_remap_gaps(trigger_remaps))
    gaps.extend(duplicate_element_gaps(duplicate_ids, intentional_dupes))
    gaps.extend(validation_gaps)

    # --- extraction_status ---
    status = "OK" if not gaps else "INCOMPLETE"

    # --- visual_analysis_scratchpad (auto stub) ---
    n_screens = len(screens)
    n_edges = len([e for e in ui_flow if e.get("navigation_kind") != "ENTRY"])
    scope_str = (input_data or {}).get("scope", "unknown")
    scratchpad = (
        f"[auto] {n_screens} screen frame(s) detected, {n_edges} connector edge(s) resolved. "
        f"Scope: {scope_str}. Review _render.html for visual confirmation. "
        f"Element extraction uses inventory flow_element_ids when available "
        f"(inventory: {'yes' if use_inventory else 'no — direct-child fallback'})."
    )

    # --- Assemble output ---
    output: dict = {
        "extraction_status": status,
        "extraction_gaps": gaps,
        "visual_analysis_scratchpad": scratchpad,
        "project_context": {
            "overall_ambiguity_rating": "LOW",
            "blocking_issues": [],
        },
    }

    if app:
        output["app"] = app
    if design_source:
        output["design_source"] = design_source

    output["screens"] = screens
    output["ui_flow"] = ui_flow

    # --- Schema validation ---
    skill_dir = os.path.dirname(os.path.abspath(__file__))
    schema_path = os.path.join(skill_dir, "..", "..", "schemas", "design_context.schema.json")
    schema_path = os.path.normpath(schema_path)
    valid = validate(output, schema_path)

    # --- Write output ---
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {output_path}")
    print(f"  app:               {app or '(not inferred)'}")
    print(f"  screens:           {n_screens}")
    print(f"  ui_flow edges:     {len(ui_flow)} "
          f"({sum(1 for e in ui_flow if e.get('navigation_kind') == 'ENTRY')} ENTRY + "
          f"{n_edges} CONNECTOR)")
    print(f"  extraction_gaps:   {len(gaps)}")
    print(f"  extraction_status: {status}")
    print(f"  schema valid:      {valid}")

    if not valid:
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extract design_context.json from a render_design.py pre-process output. "
            "Phase 1: screens + ui_flow."
        )
    )
    parser.add_argument(
        "--preprocess", "-p",
        required=True,
        metavar="PRE_PROCESS_JSON",
        help="Path to the _pre-process.json produced by render_design.py preprocess.",
    )
    parser.add_argument(
        "--input", "-i",
        metavar="ORIGINAL_JSON",
        help=(
            "Path to the original Figma JSON input. Used for design_source metadata "
            "and app inference. Optional but recommended."
        ),
    )
    parser.add_argument(
        "--workdir", "-w",
        metavar="WORKDIR",
        help="Working directory for outputs. Defaults to directory of --preprocess file.",
    )
    parser.add_argument(
        "--inventory",
        metavar="INVENTORY_JSON",
        help=(
            "Path to <stem>_inventory.json. Defaults to the inventory sidecar "
            "alongside --preprocess."
        ),
    )
    parser.add_argument(
        "--output", "-o",
        metavar="OUTPUT_JSON",
        help="Destination path. Defaults to <workdir>/design_context.temp.json.",
    )

    args = parser.parse_args()
    # Resolve workdir
    if args.workdir:
        workdir = args.workdir
    else:
        workdir = os.path.dirname(os.path.abspath(args.preprocess))
    # Resolve output path
    if args.output:
        output_path = args.output
    else:
        output_path = os.path.join(workdir, "design_context.temp.json")
    extract(
        args.preprocess,
        args.input or "",
        output_path,
        workdir,
        inventory_path=args.inventory,
    )


if __name__ == "__main__":
    main()
