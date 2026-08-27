#!/usr/bin/env python3
"""Extract design_context.json from a render_design.py pre-process output.

Consumes the ``_pre-process.json`` produced by ``render_design.py preprocess``
and writes a schema-valid ``design_context.temp.json`` (intermediate artifact).

Phase 1 scope
-------------
- ``design_source``   — envelope metadata from the original Figma JSON.
- ``app``             — inferred from filename / page-name keyword heuristic.
- ``screens``         — one object per raw screen frame (no collapsing).
                         Elements are populated from the pruned node_tree
                         children already present in ``_pre-process.json``.
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

_ROLE_SUFFIXES = ["_btn", "_button", "_input", "_label", "_lbl", "_toggle", "_tab", "_list"]
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
    (["gofood"],                             "gofood-merchant"),
    (["gopay", "merchant"],                  "gopay-merchant"),
    (["gopay", "driver"],                    "gopay-merchant"),   # treat driver-side gopay as merchant
    (["gopay"],                              "gopay-consumer"),
    (["gojek", "driver"],                    "gojek-driver"),
    (["gojek"],                              "gojek-consumer"),
]

_VALID_APPS = {
    "gojek-consumer", "gojek-driver",
    "gofood-merchant",
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
}


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
# Element extraction
# ---------------------------------------------------------------------------

def extract_elements(screen_node: dict, screen_id: str, text_cache: dict) -> list:
    """Build elements[] from the direct flow-relevant children of a screen node.

    The node_tree has already been pruned by render_design.py to only keep
    children that are connector endpoints or carry prototype reactions, so
    every child here is flow-relevant by construction.
    """
    elements = []
    seen_purposes: dict[str, int] = {}

    children = screen_node.get("children") or []
    for child in children:
        node_id = child.get("id", "")
        node_type = child.get("type", "UNKNOWN")
        node_name = child.get("name", "")

        label = text_cache.get(node_id, "") or node_name
        role = infer_role(node_type, node_name)

        # Build purpose token (deduplicated within the screen)
        purpose_base = ""
        if label:
            # Try to extract a concise contextual name from the label (only alphabets)
            cleaned_label = re.sub(r'[^a-zA-Z\s]', '', label).strip()
            words = [w for w in cleaned_label.split() if w]
            if words and len(words) <= 5:
                # If label is short (e.g. "Add to cart"), use it
                purpose_base = "_".join(w.lower() for w in words)
            elif words:
                # If label is long, just take the first 3-4 words as a hint
                purpose_base = "_".join(w.lower() for w in words[:4])
                
        if not purpose_base:
            purpose_base = to_lower_snake(node_name) if node_name else "element"

        # Prevent excessively generic names if label gave us something like "Text Price 120000"
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

        # Interactions from prototype reactions
        interactions = []
        for reaction in child.get("reactions") or []:
            action = reaction.get("action") or {}
            trigger_type = (reaction.get("trigger") or {}).get("type", "ON_CLICK")
            dest_id = action.get("destinationId")
            interactions.append({
                "trigger": trigger_type,
                "action": action.get("type", "NAVIGATE"),
                **({"destination_node_id": dest_id} if dest_id else {}),
            })

        elem = {
            "element_id": element_id,
            "source_ref": node_id,
            "type": node_type,
            "role": role,
            "label": label[:200] if label else "",
            "interactions": interactions,
            "validations_and_edge_cases": [],
        }
        elements.append(elem)

    return elements


# ---------------------------------------------------------------------------
# Screen extraction
# ---------------------------------------------------------------------------

def build_screens(pp: dict, input_data: dict | None) -> list:
    """Build screens[] — one object per raw screen frame."""
    screens_raw = pp.get("screens") or []
    screen_context = pp.get("screen_context") or {}
    text_cache = pp.get("text_cache") or {}
    node_tree = pp.get("node_tree") or {}

    # Build a lookup from screen node id -> node in node_tree (for elements).
    screen_node_lookup: dict[str, dict] = {}

    def _find_screens(node):
        nid = node.get("id", "")
        if nid in {s["id"] for s in screens_raw}:
            screen_node_lookup[nid] = node
        for child in node.get("children") or []:
            _find_screens(child)

    _find_screens(node_tree)

    # Group raw screens by base name so we can derive screen_states from siblings.
    base_name_groups: dict[str, list[str]] = {}
    for s in screens_raw:
        base = to_upper_snake(s.get("name", ""))
        base_name_groups.setdefault(base, []).append(s["id"])

    result = []
    for s in screens_raw:
        sid = s["id"]
        name = s.get("name", "")
        screen_id = to_upper_snake(name)
        ctx = screen_context.get(sid, {})

        # screen_states: qualifier of this frame + qualifiers of all siblings
        qualifier = extract_qualifier(name)
        sibling_ids = base_name_groups.get(screen_id, [])
        sibling_qualifiers = []
        for sibling_raw in screens_raw:
            if sibling_raw["id"] in sibling_ids and sibling_raw["id"] != sid:
                q = extract_qualifier(sibling_raw.get("name", ""))
                if q and q not in sibling_qualifiers:
                    sibling_qualifiers.append(q)

        screen_states = []
        if qualifier:
            screen_states.append(qualifier)
        screen_states.extend(sibling_qualifiers)

        state_kinds = list({qualifier_to_state_kind(q) for q in screen_states}) if screen_states else []

        # screen_notes from contextual_informations
        ctx_infos = s.get("contextual_informations") or []
        notes_parts = []
        for c in ctx_infos[:3]:
            txt = text_cache.get(c["id"], "") or c.get("name", "")
            if txt:
                notes_parts.append(txt[:100])
        screen_notes = " | ".join(notes_parts)[:300]

        # Elements from pruned node_tree children
        screen_node = screen_node_lookup.get(sid)
        elements = []
        if screen_node:
            elements = extract_elements(screen_node, screen_id, text_cache)

        obj = {
            "screen_id": screen_id,
            "screen_name": name,
            "source_ref": sid,
            "source_refs": [sid],
            "node_class": "SCREEN",
            "classified_by": "GEOMETRY",
            "entry_point": ctx.get("is_entry_point", False),
            "screen_states": screen_states,
            "state_kinds": state_kinds,
            "elements": elements,
            "screen_notes": screen_notes,
        }
        result.append(obj)

    return result


# ---------------------------------------------------------------------------
# ui_flow — BFS ordered
# ---------------------------------------------------------------------------

def build_ui_flow(pp: dict, screens: list) -> list:
    """Build ui_flow[] in BFS order.

    Order:
    1. ENTRY pseudo-edges (one per entry point, in entry_points list order).
    2. BFS waves from all entry-point node ids simultaneously.
    3. Orphan edges (unreachable screens), sorted by source screen (abs_y, abs_x).
    """
    edges_raw = (pp.get("edges") or []) + (pp.get("original_edges") or [])
    entry_points = pp.get("entry_points") or []
    screens_raw = pp.get("screens") or []
    index = pp.get("index") or {}

    screen_ids = {s["id"] for s in screens_raw}
    node_id_to_screen_id: dict[str, str] = {
        s["source_ref"]: s["screen_id"] for s in screens
    }
    node_id_to_screen_raw: dict[str, dict] = {
        s["id"]: s for s in screens_raw
    }

    def get_screen_for_node(node_id: str | None) -> str | None:
        curr = node_id
        while curr:
            if curr in screen_ids:
                return curr
            curr = index.get(curr, {}).get("parent_id")
        return None

    node_id_to_element_id = {}
    for s in screens:
        for el in s.get("elements", []):
            node_id_to_element_id[el["source_ref"]] = el["element_id"]

    # Resolve each connector to its originating and destination screen
    resolved_edges = []
    for e in edges_raw:
        from_node = e.get("original_from") or e.get("from")
        to_node = e.get("original_to") or e.get("to")
        from_screen = get_screen_for_node(from_node)
        to_screen = get_screen_for_node(to_node)

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

    def _make_flow_edge(e: dict) -> dict:
        from_s_id = e["from_screen"]
        to_s_id = e["to_screen"]
        
        trigger_node_id = e["from_source_ref"]
        trigger_element_id = node_id_to_element_id.get(trigger_node_id)
        
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

    return result


# ---------------------------------------------------------------------------
# Extraction gaps
# ---------------------------------------------------------------------------

def build_gaps(pp: dict, input_data: dict | None) -> list:
    gaps = []
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

def extract(preprocess_path: str, input_path: str, output_path: str, workdir: str) -> None:
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

    # --- screens ---
    screens = build_screens(pp, input_data)

    # --- ui_flow ---
    ui_flow = build_ui_flow(pp, screens)

    # --- element_id quality assessment ---
    trigger_ids = {e["trigger_element_id"] for e in ui_flow if e.get("trigger_element_id")}
    quality_results = [assess_element_id_quality(eid) for eid in trigger_ids]
    quality_path = os.path.join(workdir, "element_id_quality.json")
    with open(quality_path, "w", encoding="utf-8") as f:
        json.dump(quality_results, f, ensure_ascii=False, indent=2)

    # --- extraction_gaps ---
    gaps = build_gaps(pp, input_data)

    # --- extraction_status ---
    status = "OK" if not gaps else "INCOMPLETE"

    # --- visual_analysis_scratchpad (auto stub) ---
    n_screens = len(screens)
    n_edges = len([e for e in ui_flow if e.get("navigation_kind") != "ENTRY"])
    scope_str = (input_data or {}).get("scope", "unknown")
    scratchpad = (
        f"[auto] {n_screens} screen frame(s) detected, {n_edges} connector edge(s) resolved. "
        f"Scope: {scope_str}. Review _render.html for visual confirmation. "
        f"Element and interaction extraction is Phase 1 (mechanical derivation from pruned node_tree)."
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
    extract(args.preprocess, args.input or "", output_path, workdir)


if __name__ == "__main__":
    main()
