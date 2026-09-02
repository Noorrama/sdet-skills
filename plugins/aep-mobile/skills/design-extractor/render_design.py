#!/usr/bin/env python3
"""Render the Figma golden export as a single self-contained HTML wireframe.

Each Figma node becomes an HTML element with all its original JSON data attached
as attributes. The `data-node` attribute stores the full node JSON with the
`children` array omitted (children are represented by nested DOM elements).

Before rendering, a spatial analysis pass:
  - detects screen frames via modal-size clustering,
  - collects contextual information (labels, annotations) and associates them
    to nearby screens by direct bounding-box proximity (overlap plus a
    distance threshold, not lane clustering),
  - snaps connector endpoints that are not attached to screen frames,
  - infers entry-point screens from topology and contextual labels.

Connectors are drawn as SVG lines overlaying the DOM.
"""

import argparse
import html
import json
import math
import os
import sys
import uuid
from collections import Counter, defaultdict, deque


OUTPUT_SUFFIX = "_render.html"
PREPROCESS_SUFFIX = "_pre-process.json"
INVENTORY_SUFFIX = "_inventory.json"


def _collapse_text_subtree(node):
    """Bottom-up: if every child of `node` is (or itself collapses to) a
    TEXT leaf, merge them into `node` in place — set its own type to TEXT,
    combine the children's characters, and drop the children — then report
    success so an ancestor can do the same.

    `node`'s own x/y/width/height are left untouched throughout, so nothing
    ever shifts: this only ever deletes now-empty wrapper levels, it never
    recomputes a position or size.

    Returns True if `node` is now (or already was) a TEXT leaf.
    """
    children = node.get("children")
    if not children:
        return node.get("type") == "TEXT"

    fully_collapsed = True
    for child in children:
        if not _collapse_text_subtree(child):
            fully_collapsed = False
    if not fully_collapsed:
        return False

    node["type"] = "TEXT"
    node["characters"] = " ".join(
        c.get("characters", "") for c in children if c.get("characters")
    )
    node["children"] = []
    return True


def flatten_label_instances(node):
    """Collapse component INSTANCEs whose entire subtree is nested wrapper
    frames around pure text into a single TEXT leaf (see
    `_collapse_text_subtree`), repeating up through the tree until either
    the whole instance became one TEXT node or some descendant isn't
    text-only and blocks it.

    Not tied to any specific component name — any INSTANCE qualifies, since
    it's the structural shape (every descendant bottoms out in TEXT) that
    makes flattening safe, not the name. Non-INSTANCE nodes (screens,
    sections, plain frames) are left alone even when they happen to be
    all-text, since collapsing those would destroy real structure rather
    than decorative labels.
    """
    if node.get("type") == "INSTANCE":
        _collapse_text_subtree(node)
    for child in node.get("children", []) or []:
        flatten_label_instances(child)


def _is_screen_like_frame(node, parent_type):
    """The single shape check for "is this node a screen": `FRAME`,
    portrait-ish, and at least 300x700. Real screens also live directly
    under a non-FRAME container (section/group/page), not nested inside
    another frame, so we track the parent type while walking to replicate
    that. This is the one source of truth for screen detection — used by
    both `detect_screens` (the rendered `screens` list) and
    `build_screen_connector_maps` (connector counting / pruning) so the two
    never diverge.
    """
    if node.get("type") != "FRAME":
        return False
    if parent_type == "FRAME":
        return False
    w = node.get("width") or 0
    h = node.get("height") or 0
    if not w or not h:
        return False
    return w >= 300 and h >= 700 and h / w >= 1.2


def build_screen_connector_maps(root, screens):
    """Single traversal that assigns every node to the screen-like frame it
    lives inside (nodeIdToScreen), counts, per screen, how many connector
    endpoints land inside that screen's subtree, split by direction
    (screenConnectorCount: totalConnectorCount / outgoingConnectorCount /
    incomingConnectorCount), and collects the set of node ids that are
    actually relevant to the UI flow (flowRelevantIds) — a node touched by
    a connector endpoint anywhere in the document, or one carrying a Figma
    prototype `reactions` entry whose `destinationId` actually resolves to
    a node in this document.

    Also builds contextualNodeIdToScreen: contextual-information nodes
    (labels/annotations attached to screens by `associate_contextual_info`,
    already present on `screens` by the time this runs) live outside every
    screen's subtree by construction, so nodeIdToScreen never covers them.
    This map lets connectors anchored to those labels still resolve back to
    the screen they annotate — see `resolve_endpoint`/`snap_connectors`,
    and the fallback lookup below.

    That last check matters: in partial/section-only exports like these,
    `reactions` routinely point at a component's own internal variant-swap
    target (e.g. a stepper's other state) rather than a real screen
    transition, and that destination id simply isn't present anywhere in
    the file. A `reactions` list alone doesn't mean "this leads somewhere
    in this flow" — only a resolvable destination does — so such nodes are
    intentionally left out of flowRelevantIds and get pruned by
    `flatten_screens_to_relevant_content` like any other irrelevant node.

    connectorStart's endpoint counts as outgoing (this screen is the
    connector's source); connectorEnd's endpoint counts as incoming (this
    screen is the destination) — matching the "from"/"to" convention used
    elsewhere in this file (e.g. `snap_connectors`). Both also bump
    totalConnectorCount, and both endpoints are added to flowRelevantIds
    regardless of whether they resolve to a screen.

    Connector counting, and reaction-destination resolution, both happen in
    a second pass once the main walk has finished and every node id in the
    document is known — a connector's endpoint, or a reaction's
    destination, may belong to a node the walk hasn't reached yet in
    document order, so resolving either inline during the walk would miss
    those.

    Once inside a screen, nested frames that also happen to match the shape
    heuristic don't start a new region: `current_screen` is only assigned
    when none is active yet, so every descendant of a screen keeps mapping
    back to that same outer screen.
    """
    nodeIdToScreen = {}
    screenConnectorCount = {}
    screenNodes = {}
    flowRelevantIds = set()
    connectors = []
    allIds = set()
    reactionCandidates = []

    def walk(node, parent_type, current_screen):
        node_id = node.get("id")
        if node_id:
            allIds.add(node_id)
        if current_screen is None and _is_screen_like_frame(node, parent_type):
            current_screen = node_id
            screenConnectorCount[current_screen] = {
                "totalConnectorCount": 0,
                "outgoingConnectorCount": 0,
                "incomingConnectorCount": 0,
            }
            screenNodes[current_screen] = node
        if current_screen is not None and node_id:
            nodeIdToScreen[node_id] = current_screen
        if node.get("type") == "CONNECTOR":
            connectors.append(node)
        reactions = node.get("reactions")
        if reactions and node_id:
            reactionCandidates.append((node_id, reactions))
        for child in node.get("children", []) or []:
            walk(child, node.get("type"), current_screen)

    walk(root, None, None)

    for node_id, reactions in reactionCandidates:
        for reaction in reactions:
            destination_id = reaction.get("action", {}).get("destinationId")
            if destination_id and destination_id in allIds:
                flowRelevantIds.add(node_id)
                break

    # Map every contextual-info node (and its descendants, mirroring how
    # nodeIdToScreen covers every descendant of a screen, not just the
    # screen id itself) to the single nearest screen it's attached to. A
    # candidate can be attached to more than one screen (e.g. a label
    # spanning a row of variants), so keep whichever screen is closest.
    contextualNodeIdToScreen = {}
    contextualNodeDistance = {}

    def subtree_ids(node):
        node_id = node.get("id")
        if node_id:
            yield node_id
        for child in node.get("children", []) or []:
            yield from subtree_ids(child)

    for s in screens:
        for c in s.get("contextual_informations", []) or []:
            dist = bbox_distance(c, s)
            for cid in subtree_ids(c):
                if cid not in contextualNodeIdToScreen or dist < contextualNodeDistance[cid]:
                    contextualNodeIdToScreen[cid] = s["id"]
                    contextualNodeDistance[cid] = dist

    for c in connectors:
        start_id = c.get("connectorStart", {}).get("endpointNodeId")
        if start_id:
            flowRelevantIds.add(start_id)
        start_screen = nodeIdToScreen.get(start_id) or contextualNodeIdToScreen.get(start_id)
        if start_screen:
            counts = screenConnectorCount[start_screen]
            counts["totalConnectorCount"] += 1
            counts["outgoingConnectorCount"] += 1

        end_id = c.get("connectorEnd", {}).get("endpointNodeId")
        if end_id:
            flowRelevantIds.add(end_id)
        end_screen = nodeIdToScreen.get(end_id) or contextualNodeIdToScreen.get(end_id)
        if end_screen:
            counts = screenConnectorCount[end_screen]
            counts["totalConnectorCount"] += 1
            counts["incomingConnectorCount"] += 1

    return (
        nodeIdToScreen,
        screenConnectorCount,
        screenNodes,
        flowRelevantIds,
        contextualNodeIdToScreen,
        reactionCandidates,
    )


def _collect_relevant_nodes(node, offset_x, offset_y, relevant_ids, out):
    """Depth-first search for flow-relevant nodes, folding in the x/y of
    every skipped wrapper along the way so a relevant node's absolute
    position is unchanged even after being reparented directly under the
    screen. Once a relevant node is found, recursion stops there — its own
    subtree is kept completely intact rather than being searched further.
    """
    total_x = offset_x + (node.get("x") or 0)
    total_y = offset_y + (node.get("y") or 0)
    if node.get("id") in relevant_ids:
        node["x"] = total_x
        node["y"] = total_y
        out.append(node)
        return
    for child in node.get("children", []) or []:
        _collect_relevant_nodes(child, total_x, total_y, relevant_ids, out)


def flatten_screens_to_relevant_content(screen_nodes, flow_relevant_ids):
    """Collapse every screen's subtree down to just the nodes that matter to
    the UI flow (see `build_screen_connector_maps`): a connector endpoint or
    a node carrying prototype `reactions`. Intermediate wrapper containers
    (e.g. a "Content" frame that holds one relevant chip among other
    unrelated siblings) are discarded — the relevant node becomes a direct
    child of the screen instead, with its x/y adjusted to preserve its
    absolute position. A screen with no relevant descendants at all ends up
    with an empty `children` list (its own x/y/width/height are untouched,
    so it still renders as an empty box; see `render_node`) — this is a
    superset of the old zero-connector wipe this function replaces.
    """
    for screen in screen_nodes.values():
        relevant = []
        for child in screen.get("children", []) or []:
            _collect_relevant_nodes(child, 0, 0, flow_relevant_ids, relevant)
        screen["children"] = relevant


def is_skippable_frame(node):
    """Return True for frames that are empty or only contain images/rectangles."""
    if node.get("type") != "FRAME":
        return False
    children = node.get("children", [])
    if not children:
        return True
    return all(
        c.get("type") == "RECTANGLE" or is_skippable_frame(c)
        for c in children
    )


def build_spatial_index(root):
    """Walk the tree and return a flat spatial index and canvas bbox."""
    index = {}
    bbox = [float("inf"), float("inf"), float("-inf"), float("-inf")]

    def walk(node, parent_x, parent_y, parent_id):
        x = node.get("x", 0)
        y = node.get("y", 0)
        w = node.get("width", 0)
        h = node.get("height", 0)
        abs_x = parent_x + x
        abs_y = parent_y + y
        node_id = node.get("id")

        if node_id:
            node_copy = {k: v for k, v in node.items() if k != "children"}
            text = node.get("characters", "") if node.get("type") == "TEXT" else ""
            children_ids = [c.get("id") for c in node.get("children", []) if c.get("id")]
            index[node_id] = {
                "id": node_id,
                "type": node.get("type"),
                "name": node.get("name", ""),
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "abs_x": abs_x,
                "abs_y": abs_y,
                "parent_id": parent_id,
                "text": text,
                "node": node_copy,
                "children_ids": children_ids,
            }

        if w and h:
            bbox[0] = min(bbox[0], abs_x)
            bbox[1] = min(bbox[1], abs_y)
            bbox[2] = max(bbox[2], abs_x + w)
            bbox[3] = max(bbox[3], abs_y + h)

        for child in node.get("children", []):
            walk(child, abs_x, abs_y, node_id)

    walk(root, 0, 0, None)
    return index, bbox


def build_text_cache(index):
    """Return a node-id -> visible text map for every node in the index."""
    cache = {}

    def compute(nid):
        if nid in cache:
            return cache[nid]
        node = index.get(nid)
        if not node:
            cache[nid] = ""
            return ""
        if node["type"] == "TEXT":
            cache[nid] = node["text"] or ""
            return cache[nid]
        parts = [node["name"] or ""]
        for child_id in node.get("children_ids", []):
            parts.append(compute(child_id))
        cache[nid] = " ".join(p for p in parts if p).strip()
        return cache[nid]

    for nid in index:
        compute(nid)
    return cache


def detect_screens(index):
    """Detect screen frames using the shared `_is_screen_like_frame` heuristic.

    Uses the same predicate as `build_screen_connector_maps` /
    `flatten_screens_to_relevant_content` so there is one source of truth
    for "is this node a screen" — this used to run a separate modal-size
    clustering pass that could silently exclude legitimate screens whose
    size didn't match the file's most common screen dimensions.
    """
    screens = []
    
    def is_descendant_of_screen(node):
        curr = index.get(node.get("parent_id"))
        while curr:
            curr_parent = index.get(curr.get("parent_id"))
            curr_parent_type = curr_parent["type"] if curr_parent else None
            if _is_screen_like_frame(curr, curr_parent_type):
                return True
            curr = curr_parent
        return False

    for node in index.values():
        if node["type"] != "FRAME":
            continue
        # The indexed node has no children array, only children_ids. Skip empty frames.
        if not node.get("children_ids"):
            continue
        parent = index.get(node.get("parent_id"))
        parent_type = parent["type"] if parent else None
        if _is_screen_like_frame(node, parent_type) and not is_descendant_of_screen(node):
            screens.append(node)

    # Stable sort by position.
    screens.sort(key=lambda s: (s["abs_y"], s["abs_x"]))
    return screens


def ranges_overlap(a, b):
    """Return True if the two (min, max) ranges overlap."""
    return a[0] <= b[1] and b[0] <= a[1]


def point_to_bbox_distance(px, py, s):
    """Distance from a point to the nearest point on a screen's bounding box."""
    sx, sy, sw, sh = s["abs_x"], s["abs_y"], s["width"], s["height"]
    nx = max(sx, min(px, sx + sw))
    ny = max(sy, min(py, sy + sh))
    return math.hypot(px - nx, py - ny)


def bbox_distance(a, b):
    """Minimum distance between two bounding boxes."""
    dx = max(0, max(b["abs_x"] - (a["abs_x"] + a["width"]),
                    a["abs_x"] - (b["abs_x"] + b["width"])))
    dy = max(0, max(b["abs_y"] - (a["abs_y"] + a["height"]),
                    a["abs_y"] - (b["abs_y"] + b["height"])))
    return math.hypot(dx, dy)


def collect_contextual_info_candidates(index, screens, text_cache):
    """Collect non-screen annotation nodes that carry text and sit near the screen grid."""
    if not screens:
        return []

    screen_ids = {s["id"] for s in screens}
    min_x = min(s["abs_x"] for s in screens)
    max_x = max(s["abs_x"] + s["width"] for s in screens)
    min_y = min(s["abs_y"] for s in screens)
    max_y = max(s["abs_y"] + s["height"] for s in screens)

    # Pad generously to catch labels above/below and notes to the sides.
    pad_x = max(400, (max_x - min_x) * 0.25)
    pad_y = max(400, (max_y - min_y) * 0.25)

    # Precompute ancestor/descendant relationships to screen nodes.
    screen_ancestor_ids = set()
    for s in screens:
        ancestor_id = s["parent_id"]
        while ancestor_id and ancestor_id in index:
            screen_ancestor_ids.add(ancestor_id)
            ancestor_id = index[ancestor_id].get("parent_id")

    def is_descendant_of_screen(node):
        ancestor_id = node.get("parent_id")
        while ancestor_id and ancestor_id in index:
            if ancestor_id in screen_ids:
                return True
            ancestor_id = index[ancestor_id].get("parent_id")
        return False

    candidates = []
    for node in index.values():
        if node["id"] in screen_ids or node["id"] in screen_ancestor_ids:
            continue
        t = node["type"]
        if t in ("CONNECTOR", "RECTANGLE", "ELLIPSE", "PAGE"):
            continue

        if not text_cache.get(node["id"], "").strip() and not node["name"].strip():
            continue

        nx, ny = node["abs_x"], node["abs_y"]
        nw, nh = node["width"], node["height"]
        if nx + nw < min_x - pad_x or nx > max_x + pad_x:
            continue
        if ny + nh < min_y - pad_y or ny > max_y + pad_y:
            continue

        # Exclude UI elements nested inside screens.
        if is_descendant_of_screen(node):
            continue

        candidates.append(node)

    # Keep only the topmost candidate in each hierarchy branch so that label
    # instances are stored once, not once per internal frame/text child.
    candidate_ids = {c["id"] for c in candidates}

    def has_candidate_ancestor(node):
        ancestor_id = node.get("parent_id")
        while ancestor_id and ancestor_id in index:
            if ancestor_id in candidate_ids:
                return True
            ancestor_id = index[ancestor_id].get("parent_id")
        return False

    return [c for c in candidates if not has_candidate_ancestor(c)]


def associate_contextual_info(screens, candidates):
    """Attach contextual information to screens using spatial proximity.

    Two association rules are used:
      1. Vertical / above-below label: the candidate overlaps the screen
         horizontally and is within a modest vertical distance.
      2. Horizontal row / left-right note: the candidate overlaps the screen
         vertically and sits outside the screen horizontally (e.g. a left-side
         scenario note or a row-spanning label that does not overlap this screen).

    Classification of the attached information (label, note, entry hint) is
    left to later consumers; this pass only records the spatial association.
    """
    if not screens or not candidates:
        return

    # Scale the vertical search distance to this file's typical screen size
    # (screens no longer share a single modal size — `detect_screens` allows
    # any size that passes `_is_screen_like_frame` — so the median stands in
    # for what "modal height" used to represent).
    heights = sorted(s["height"] for s in screens)
    median_height = heights[len(heights) // 2]
    vertical_threshold = max(200, median_height * 0.5)

    for s in screens:
        s["contextual_informations"] = []

    for c in candidates:
        cx1, cy1 = c["abs_x"], c["abs_y"]
        cx2, cy2 = cx1 + c["width"], cy1 + c["height"]

        for s in screens:
            sx1, sy1 = s["abs_x"], s["abs_y"]
            sx2, sy2 = sx1 + s["width"], sy1 + s["height"]

            x_overlap = max(0, min(sx2, cx2) - max(sx1, cx1))
            y_overlap = max(0, min(sy2, cy2) - max(sy1, cy1))
            y_dist = max(0, max(sy1 - cy2, cy1 - sy2))

            # Vertical label / above-below note.
            if x_overlap > 0 and y_dist < vertical_threshold:
                s["contextual_informations"].append(c)
                continue

            # Horizontal row / left-right note.
            if y_overlap > 0 and x_overlap == 0:
                s["contextual_informations"].append(c)

    # Deduplicate and sort by proximity so the closest context is first.
    for s in screens:
        seen = set()
        unique = []
        for c in sorted(s["contextual_informations"], key=lambda c: bbox_distance(c, s)):
            if c["id"] not in seen:
                seen.add(c["id"])
                unique.append(c)
        s["contextual_informations"] = unique


def resolve_endpoint(endpoint, screens, index, contextual_node_id_to_screen):
    """Return the screen id, snap flag, and resolution method for a connector endpoint.

    Resolution order:
      1. The endpoint node id itself is a screen.
      2. Any ancestor of the endpoint node is a screen.
      3. The endpoint is a contextual-info node (label/annotation) already
         associated with a specific screen by `associate_contextual_info`
         (via `contextual_node_id_to_screen`, from `build_screen_connector_maps`).
      4. Snap to the nearest screen by distance (using the explicit position or
         the node center).

    method is one of: direct_screen, ancestor, contextual, distance_snap, unresolved.
    """
    endpoint_id = endpoint.get("endpointNodeId")
    position = endpoint.get("position")
    screen_ids = {s["id"] for s in screens}

    if not screens:
        return None, False, "unresolved"

    # Direct hit.
    if endpoint_id in screen_ids:
        return endpoint_id, False, "direct_screen"

    # Ancestor hit.
    if endpoint_id in index:
        ancestor_id = endpoint_id
        while ancestor_id:
            if ancestor_id in screen_ids:
                return ancestor_id, True, "ancestor"
            ancestor_id = index[ancestor_id].get("parent_id")

    # Contextual-info hit: the endpoint is a label/annotation, not a
    # descendant of any screen, but already mapped to the screen it
    # annotates.
    contextual_screen_id = contextual_node_id_to_screen.get(endpoint_id)
    if contextual_screen_id:
        return contextual_screen_id, True, "contextual"

    # Distance-based snap. Connector positions are relative to the endpoint node.
    point = None
    if position:
        endpoint_node = index.get(endpoint_id)
        if endpoint_node:
            point = (endpoint_node["abs_x"] + position["x"], endpoint_node["abs_y"] + position["y"])
        else:
            point = (position["x"], position["y"])
    elif endpoint_id in index:
        node = index[endpoint_id]
        point = (node["abs_x"] + node["width"] / 2, node["abs_y"] + node["height"] / 2)

    if point:
        px, py = point
        nearest = min(screens, key=lambda s: point_to_bbox_distance(px, py, s))
        dist = point_to_bbox_distance(px, py, nearest)
        threshold = max(500, nearest["width"] * 1.5)
        if dist <= threshold:
            return nearest["id"], True, "distance_snap"

    return None, False, "unresolved"


def resolve_node_screen(node_id, screens, index, node_id_to_screen, contextual_node_id_to_screen):
    """Return the screen id and resolution method for an inventory element node.

    Resolution order:
      1. Precomputed subtree assignment (`node_id_to_screen` from
         `build_screen_connector_maps`).
      2. Same fallback chain as `resolve_endpoint`: direct screen id, ancestor
         walk, contextual map, nearest-screen distance snap.

    method is one of: subtree, contextual, distance_snap, unresolved.
    direct_screen and ancestor hits from `resolve_endpoint` are reported as
    subtree for inventory audit consistency.
    """
    screen_id = node_id_to_screen.get(node_id)
    if screen_id:
        return screen_id, "subtree"

    endpoint = {"endpointNodeId": node_id}
    screen_id, _snapped, method = resolve_endpoint(
        endpoint, screens, index, contextual_node_id_to_screen,
    )
    if method in ("direct_screen", "ancestor"):
        method = "subtree"
    return screen_id, method


def _connector_endpoint_detail(endpoint, index):
    """Build the start/end detail block for a connector inventory record."""
    endpoint_id = endpoint.get("endpointNodeId")
    node = index.get(endpoint_id, {})
    detail = {
        "endpoint_node_id": endpoint_id,
        "endpoint_node_type": node.get("type"),
        "endpoint_node_name": node.get("name", ""),
    }
    position = endpoint.get("position")
    if position:
        detail["position"] = {"x": position["x"], "y": position["y"]}
    return detail


def build_connector_inventory(connectors, screens, index, contextual_node_id_to_screen):
    """Build a canonical connector list with resolution metadata for each connector."""
    screen_ids = {s["id"] for s in screens}
    inventory = []

    for c in connectors:
        c_id = c.get("id")
        start = c.get("connectorStart", {})
        end = c.get("connectorEnd", {})
        text = c.get("text", {}).get("characters", "") if c.get("text") else ""
        start_cap = c.get("connectorStartStrokeCap", "")
        end_cap = c.get("connectorEndStrokeCap", "")

        start_id = start.get("endpointNodeId")
        end_id = end.get("endpointNodeId")
        start_node = index.get(start_id)
        end_node = index.get(end_id)
        start_is_screen = start_id in screen_ids
        end_is_screen = end_id in screen_ids
        start_is_section = start_node and start_node["type"] == "SECTION"
        end_is_section = end_node and end_node["type"] == "SECTION"
        start_is_contextual = start_id in contextual_node_id_to_screen
        end_is_contextual = end_id in contextual_node_id_to_screen

        record = {
            "id": c_id,
            "label": text,
            "start": _connector_endpoint_detail(start, index),
            "end": _connector_endpoint_detail(end, index),
            "stroke_caps": {"start": start_cap, "end": end_cap},
            "resolution": {},
        }

        if start_is_screen and end_is_screen:
            record["resolution"] = {
                "status": "SCREEN_EDGE",
                "from_screen_id": start_id,
                "to_screen_id": end_id,
                "from_method": "direct_screen",
                "to_method": "direct_screen",
                "snapped": False,
            }
        elif start_is_section or end_is_section or start_is_contextual or end_is_contextual:
            from_id, from_snapped, from_method = resolve_endpoint(
                start, screens, index, contextual_node_id_to_screen,
            )
            to_id, to_snapped, to_method = resolve_endpoint(
                end, screens, index, contextual_node_id_to_screen,
            )
            if from_id and to_id:
                record["resolution"] = {
                    "status": "SCREEN_EDGE",
                    "from_screen_id": from_id,
                    "to_screen_id": to_id,
                    "from_method": from_method,
                    "to_method": to_method,
                    "snapped": from_snapped or to_snapped,
                }
            else:
                record["resolution"] = {
                    "status": "UNRESOLVED",
                    "from_screen_id": from_id,
                    "to_screen_id": to_id,
                    "from_method": from_method,
                    "to_method": to_method,
                    "snapped": False,
                    "reason": "could not resolve section/contextual-attached connector to a screen",
                }
        elif start_id in index and end_id in index:
            record["resolution"] = {
                "status": "ORIGINAL_EDGE",
                "from_screen_id": None,
                "to_screen_id": None,
                "from_method": None,
                "to_method": None,
                "snapped": False,
            }
        else:
            record["resolution"] = {
                "status": "UNRESOLVED",
                "from_screen_id": None,
                "to_screen_id": None,
                "from_method": None,
                "to_method": None,
                "snapped": False,
                "reason": "one or both original endpoints not found",
            }

        inventory.append(record)

    return inventory


def snap_connectors(connectors, screens, index, contextual_node_id_to_screen):
    """Resolve connectors into screen-to-screen edges or original node-to-node edges.

    A connector is "recovered" to a screen-to-screen edge when at least one
    endpoint is a SECTION (the designer attached the connector to the
    container) or a contextual-info node already mapped to a screen by
    `contextual_node_id_to_screen` (the designer attached the connector to a
    label/annotation near the screen instead of the screen frame itself).
    Connectors whose endpoints are already screens are kept as-is. All other
    connectors are rendered between their original endpoints.
    """
    inventory = build_connector_inventory(connectors, screens, index, contextual_node_id_to_screen)
    screen_edges = []
    original_edges = []
    unresolved = []

    for c in inventory:
        c_id = c["id"]
        res = c["resolution"]
        cap_info = {
            "start_cap": c["stroke_caps"]["start"],
            "end_cap": c["stroke_caps"]["end"],
        }
        label = c.get("label", "")
        start_id = c["start"]["endpoint_node_id"]
        end_id = c["end"]["endpoint_node_id"]

        if res["status"] == "SCREEN_EDGE":
            screen_edges.append({
                "id": c_id,
                "from": res["from_screen_id"],
                "to": res["to_screen_id"],
                "original_from": start_id,
                "original_to": end_id,
                "snapped": res["snapped"],
                "from_snapped": res["from_method"] != "direct_screen",
                "to_snapped": res["to_method"] != "direct_screen",
                "label": label,
                **cap_info,
            })
        elif res["status"] == "ORIGINAL_EDGE":
            original_edges.append({
                "id": c_id,
                "from": start_id,
                "to": end_id,
                "label": label,
                **cap_info,
            })
        else:
            unresolved.append({
                "id": c_id,
                "original_from": start_id,
                "original_to": end_id,
                "reason": res.get("reason", "unresolved"),
                **cap_info,
            })

    return screen_edges, original_edges, unresolved, inventory


def build_flow_audit(screens, connector_inventory, entry_points):
    """Build reachability graph and validation checks from connector inventory."""
    screen_ids = {s["id"] for s in screens}
    entry_point_screen_ids = [ep["id"] for ep in entry_points if ep["id"] in screen_ids]

    graph = defaultdict(list)
    incoming = defaultdict(set)
    outgoing = defaultdict(set)

    for c in connector_inventory:
        res = c["resolution"]
        if res["status"] != "SCREEN_EDGE":
            continue
        from_id = res.get("from_screen_id")
        to_id = res.get("to_screen_id")
        if from_id in screen_ids and to_id in screen_ids:
            graph[from_id].append(to_id)
            outgoing[from_id].add(to_id)
            incoming[to_id].add(from_id)

    reachability_map = {}
    queue = deque()
    for eid in entry_point_screen_ids:
        reachability_map[eid] = 0
        queue.append(eid)

    while queue:
        current = queue.popleft()
        for nxt in graph.get(current, []):
            if nxt not in reachability_map:
                reachability_map[nxt] = reachability_map[current] + 1
                queue.append(nxt)

    reachable_screen_ids = sorted(reachability_map.keys())
    unreachable_screen_ids = sorted(screen_ids - set(reachable_screen_ids))
    isolated_screen_ids = sorted(
        sid for sid in screen_ids
        if not incoming.get(sid) and not outgoing.get(sid)
    )

    by_status = Counter(c["resolution"]["status"] for c in connector_inventory)
    total = len(connector_inventory)
    unresolved_count = by_status.get("UNRESOLVED", 0)
    unreachable_count = len(unreachable_screen_ids)

    checks = [
        {
            "id": "connectors_fully_resolved",
            "passed": unresolved_count == 0,
            "detail": f"{unresolved_count} of {total} connectors unresolved",
        },
        {
            "id": "all_screens_reachable",
            "passed": unreachable_count == 0,
            "detail": (
                f"{unreachable_count} of {len(screen_ids)} screens unreachable "
                "from entry points via screen-to-screen edges"
            ),
        },
    ]

    return {
        "entry_point_screen_ids": entry_point_screen_ids,
        "graph": {k: sorted(v) for k, v in sorted(graph.items())},
        "reachable_screen_ids": reachable_screen_ids,
        "unreachable_screen_ids": unreachable_screen_ids,
        "isolated_screen_ids": isolated_screen_ids,
        "connector_resolution": {
            "total": total,
            "by_status": dict(by_status),
            "all_resolved": unresolved_count == 0,
        },
        "checks": checks,
        "_reachability_map": reachability_map,
    }


def build_screen_inventory(screens, screen_context, screen_connector_count, entry_points, reachability_map):
    """Build per-screen inventory records with connector counts and reachability."""
    entry_reasons = {ep["id"]: ep["reason"] for ep in entry_points}
    records = []

    for s in screens:
        sid = s["id"]
        ctx = screen_context.get(sid, {})
        counts = screen_connector_count.get(sid, {})
        is_entry = ctx.get("is_entry_point", False)
        records.append({
            "id": sid,
            "name": s.get("name", ""),
            "geometry": {
                "x": s.get("x", 0),
                "y": s.get("y", 0),
                "width": s.get("width", 0),
                "height": s.get("height", 0),
                "abs_x": s.get("abs_x", 0),
                "abs_y": s.get("abs_y", 0),
            },
            "parent_id": s.get("parent_id"),
            "is_entry_point": is_entry,
            "entry_reason": entry_reasons.get(sid) if is_entry else None,
            "connector_counts": {
                "total": counts.get("totalConnectorCount", 0),
                "outgoing": counts.get("outgoingConnectorCount", 0),
                "incoming": counts.get("incomingConnectorCount", 0),
            },
            "contextual_information_ids": [
                c["id"] for c in s.get("contextual_informations", [])
            ],
            "reachability": {
                "reachable_from_entry": sid in reachability_map,
                "hop_distance": reachability_map.get(sid),
            },
        })

    return records


def build_elements_inventory(
    index,
    text_cache,
    flow_relevant_ids,
    contextual_node_id_to_screen,
    connectors,
    reaction_candidates,
    node_id_to_screen,
    screens,
):
    """Build inventory of flow-relevant and contextual-annotation elements."""
    all_ids = set(index.keys())
    element_ids = set(flow_relevant_ids) | set(contextual_node_id_to_screen.keys())

    connector_roles = defaultdict(set)
    for c in connectors:
        start_id = c.get("connectorStart", {}).get("endpointNodeId")
        end_id = c.get("connectorEnd", {}).get("endpointNodeId")
        if start_id:
            connector_roles[start_id].add("connector_start")
        if end_id:
            connector_roles[end_id].add("connector_end")

    reaction_map = defaultdict(list)
    has_reactions = set()
    for node_id, reactions in reaction_candidates:
        for reaction in reactions:
            destination_id = reaction.get("action", {}).get("destinationId")
            trigger = reaction.get("trigger", {}).get("type", "")
            resolves = bool(destination_id and destination_id in all_ids)
            reaction_map[node_id].append({
                "trigger": trigger,
                "destination_id": destination_id,
                "destination_resolves": resolves,
            })
            if resolves:
                has_reactions.add(node_id)

    records = []
    for node_id in sorted(element_ids):
        node = index.get(node_id)
        if not node:
            continue

        classification = (
            "FLOW_RELEVANT" if node_id in flow_relevant_ids else "CONTEXTUAL_ANNOTATION"
        )
        screen_id, screen_resolution_method = resolve_node_screen(
            node_id,
            screens,
            index,
            node_id_to_screen,
            contextual_node_id_to_screen,
        )

        roles = []
        if node_id in connector_roles:
            roles.append("connector_endpoint")
            roles.extend(sorted(connector_roles[node_id]))
        if node_id in has_reactions:
            roles.append("has_reactions")

        record = {
            "id": node_id,
            "type": node.get("type"),
            "name": node.get("name", ""),
            "label": text_cache.get(node_id, ""),
            "screen_id": screen_id,
            "screen_resolution_method": screen_resolution_method,
            "classification": classification,
            "roles": roles,
            "geometry": {
                "abs_x": node.get("abs_x", 0),
                "abs_y": node.get("abs_y", 0),
                "width": node.get("width", 0),
                "height": node.get("height", 0),
            },
        }
        if node_id in reaction_map:
            record["reactions"] = reaction_map[node_id]
        records.append(record)

    return records


def build_inventory(
    input_path,
    file_name,
    screens,
    screen_context,
    screen_connector_count,
    entry_points,
    connector_inventory,
    index,
    text_cache,
    flow_relevant_ids,
    contextual_node_id_to_screen,
    connectors,
    reaction_candidates,
    node_id_to_screen,
):
    """Assemble the full inventory sidecar dict."""
    flow_audit = build_flow_audit(screens, connector_inventory, entry_points)
    reachability_map = flow_audit.pop("_reachability_map")

    screen_records = build_screen_inventory(
        screens, screen_context, screen_connector_count, entry_points, reachability_map,
    )
    element_records = build_elements_inventory(
        index,
        text_cache,
        flow_relevant_ids,
        contextual_node_id_to_screen,
        connectors,
        reaction_candidates,
        node_id_to_screen,
        screens,
    )

    screen_element_groups = defaultdict(lambda: {"flow": [], "contextual": []})
    for element in element_records:
        screen_id = element.get("screen_id")
        if not screen_id:
            continue
        bucket = (
            "flow"
            if element["classification"] == "FLOW_RELEVANT"
            else "contextual"
        )
        screen_element_groups[screen_id][bucket].append(element["id"])

    for screen_record in screen_records:
        sid = screen_record["id"]
        groups = screen_element_groups.get(sid, {"flow": [], "contextual": []})
        screen_record["flow_element_ids"] = sorted(groups["flow"])
        screen_record["contextual_element_ids"] = sorted(groups["contextual"])

    elements_without_screen = sum(1 for e in element_records if e.get("screen_id") is None)
    by_status = flow_audit["connector_resolution"]["by_status"]
    return {
        "metadata": {
            "input_path": input_path,
            "file_name": file_name,
            "generated_by": "render_design.py",
            "inventory_version": 1,
        },
        "summary": {
            "screens_total": len(screen_records),
            "elements_total": len(element_records),
            "connectors_total": len(connector_inventory),
            "connectors_resolved_screen_edge": by_status.get("SCREEN_EDGE", 0),
            "connectors_resolved_original_edge": by_status.get("ORIGINAL_EDGE", 0),
            "connectors_unresolved": by_status.get("UNRESOLVED", 0),
            "entry_points": len(entry_points),
            "reachable_screens": len(flow_audit["reachable_screen_ids"]),
            "unreachable_screens": len(flow_audit["unreachable_screen_ids"]),
            "elements_without_screen": elements_without_screen,
        },
        "screens": screen_records,
        "elements": element_records,
        "connectors": connector_inventory,
        "flow_audit": flow_audit,
    }


def infer_entry_points(screens, edges, flow_starting_points, index, text_cache, screen_connector_count):
    """Infer entry-point screens from explicit signals, context labels, and topology.

    Entry points pass a connector gate: must have outgoing connectors and no
    incoming connectors — except incoming from other entry points (e.g. chained
    flows where one entry point connects to another). This allows cases where
    a screen has entry-point context but receives an edge from another entry point.
    """
    screen_ids = {s["id"] for s in screens}
    entry_points = []
    entry_ids = set()

    def add_entry(sid, reason):
        if sid in screen_ids and sid not in entry_ids:
            entry_points.append({"id": sid, "reason": reason})
            entry_ids.add(sid)

    # --- Build incoming-edge source map (screen -> set of source screen ids) ---
    incoming_from = defaultdict(set)
    out_edges = defaultdict(list)
    for e in edges:
        if e["from"] in screen_ids and e["to"] in screen_ids:
            incoming_from[e["to"]].add(e["from"])
            out_edges[e["from"]].append(e["to"])

    # --- Phase 1: Primary signals (EXPLICIT + CONTEXT) ---
    # These are authoritative; pass gate unconditionally (only need outgoing connectors).
    if flow_starting_points:
        for fs in flow_starting_points:
            node_id = fs.get("nodeId") or fs.get("id")
            add_entry(node_id, "EXPLICIT")

    entry_phrases = ("entry point", "1st time", "starting point")
    for s in screens:
        sid = s["id"]
        texts = []
        for c in s.get("contextual_informations", []):
            texts.append(text_cache.get(c["id"], ""))
        combined = " ".join(t for t in texts if t).lower()
        if any(phrase in combined for phrase in entry_phrases):
            add_entry(sid, "CONTEXT")

    # Primary gate: must have outgoing connectors
    primary_entry_ids = set(entry_ids)

    def passes_primary_gate(sid):
        counts = screen_connector_count.get(sid, {})
        return counts.get("outgoingConnectorCount", 0) > 0

    entry_points = [ep for ep in entry_points if passes_primary_gate(ep["id"])]
    entry_ids = {ep["id"] for ep in entry_points}

    # --- Phase 2: Topological inference with relaxed gate ---
    # Allow incoming edges ONLY from already-accepted entry points (transitive).
    def forward_reach(root):
        visited = set()
        stack = [root]
        while stack:
            n = stack.pop()
            if n in visited:
                continue
            visited.add(n)
            for nxt in out_edges.get(n, []):
                if nxt not in visited:
                    stack.append(nxt)
        return len(visited) - 1

    def passes_relaxed_gate(sid):
        counts = screen_connector_count.get(sid, {})
        if counts.get("outgoingConnectorCount", 0) == 0:
            return False
        sources = incoming_from.get(sid, set())
        return all(src in entry_ids for src in sources)

    # Roots: screens with outgoing edges that are either true roots or
    # only receive from entry points
    roots = [s for s in screens if out_edges.get(s["id"])]
    roots.sort(key=lambda s: forward_reach(s["id"]), reverse=True)
    for s in roots:
        sid = s["id"]
        if sid in entry_ids:
            continue
        reach = forward_reach(sid)
        if reach >= 5 or (not primary_entry_ids and len(entry_points) < 3):
            if passes_relaxed_gate(sid):
                add_entry(sid, "TOPOLOGY")

    # Apply relaxed gate to any remaining CONTEXT/EXPLICIT that were filtered by primary gate
    # (shouldn't happen, but safety)
    entry_points = [ep for ep in entry_points if passes_relaxed_gate(ep["id"])]
    entry_ids = {ep["id"] for ep in entry_points}

    for s in screens:
        s["is_entry_point"] = s["id"] in entry_ids

    return entry_points


def make_screen_title(screen, text_cache):
    """Build a short title combining the screen name and nearby context."""
    title = screen.get("name", "")
    snippets = []
    for c in screen.get("contextual_informations", [])[:3]:
        text = text_cache.get(c["id"], "")
        if text:
            snippets.append(text[:60])
        elif c.get("name"):
            snippets.append(c["name"][:60])
    if snippets:
        title = f"{title} | {' / '.join(snippets)}"
    if len(title) > 160:
        title = title[:157] + "..."
    return title


def render_node(node, parent_x, parent_y, context, parts, under_named_section=False):
    """Recursively emit nested HTML for one node."""
    node_id = node.get("id", "")
    is_screen = node_id in context.get("screen_context", {})

    # A flattened screen (see `flatten_screens_to_relevant_content`) may have
    # few or no children left, which would otherwise make it look
    # "skippable" here and vanish from the render entirely — but flattening
    # only trims content, not the screen box itself, so recognized screens
    # always render regardless of emptiness.
    if not is_screen and is_skippable_frame(node):
        return 0, Counter()

    node_type = node.get("type", "UNKNOWN")
    name = node.get("name", "")
    x = node.get("x", 0)
    y = node.get("y", 0)
    w = node.get("width", 0)
    h = node.get("height", 0)
    abs_x = parent_x + x
    abs_y = parent_y + y

    if node_type == "RECTANGLE":
        return 0, Counter()

    is_named_section = node_type == "SECTION" and name.strip()

    if node_type == "GROUP":
        if not under_named_section and not is_named_section:
            return 0, Counter()
        parts.append(f'<div style="position:absolute;left:{x}px;top:{y}px;">')
        subtree_count = 1
        subtree_counts = Counter(["GROUP"])
        for child in node.get("children", []):
            child_count, child_counts = render_node(child, abs_x, abs_y, context, parts, under_named_section=True)
            subtree_count += child_count
            subtree_counts.update(child_counts)
        parts.append("</div>")
        return subtree_count, subtree_counts

    if node_type != "PAGE" and not is_named_section and not under_named_section:
        return 0, Counter()

    class_name = f"node figma-{node_type}"
    if is_screen:
        class_name += " is-screen"

    attrs = [
        ("class", class_name),
        ("data-id", node_id),
        ("data-type", node_type),
        ("data-name", name),
        ("title", name),
    ]

    if node_type != "PAGE":
        attrs.extend([
            ("data-x", str(x)),
            ("data-y", str(y)),
            ("data-width", str(w)),
            ("data-height", str(h)),
            ("data-abs-x", str(abs_x)),
            ("data-abs-y", str(abs_y)),
        ])

    if node_type == "TEXT":
        attrs.append(("data-characters", node.get("characters", "")))

    node_copy = {k: v for k, v in node.items() if k != "children"}
    attrs.append(("data-node", json.dumps(node_copy, ensure_ascii=False, separators=(",", ":"))))

    if is_screen:
        screen_context = context["screen_context"][node_id]
        text_cache = context["text_cache"]
        title = make_screen_title(screen_context, text_cache)
        attrs.append(("data-screen-title", title))
        attrs.append(("data-is-entry", str(screen_context.get("is_entry_point", False)).lower()))
        context_json = []
        for c in screen_context.get("contextual_informations", [])[:10]:
            text = text_cache.get(c["id"], "")
            if len(text) > 500:
                text = text[:497] + "..."
            context_json.append({
                "id": c["id"],
                "type": c["type"],
                "name": c["name"],
                "text": text,
            })
        attrs.append(("data-contextual", json.dumps(context_json, ensure_ascii=False, separators=(",", ":"))))

    if node_type == "PAGE":
        # #canvas already carries the (-min_x, -min_y) shift so every
        # descendant's local-offset chain lands at canvas-relative (0, 0) for
        # the top-left-most content. Applying that same shift again here
        # would double-offset the whole tree.
        style = (
            f"position:absolute;"
            f"left:0px;"
            f"top:0px;"
            f"width:{context['canvas_w']}px;"
            f"height:{context['canvas_h']}px;"
        )
    else:
        style = f"position:absolute;left:{x}px;top:{y}px;"
        if w:
            style += f"width:{w}px;"
        if h:
            style += f"height:{h}px;"
        if node_type == "FRAME":
            style += "overflow:hidden;"

    attr_str = " ".join(f'{k}="{html.escape(str(v))}"' for k, v in attrs)

    if node_type == "CONNECTOR":
        context["connectors"].append(node)

    parts.append(f'<div {attr_str} style="{style}">')
    if is_screen:
        screen_context = context["screen_context"][node_id]
        text_cache = context["text_cache"]
        title = make_screen_title(screen_context, text_cache)
        parts.append(f'<div class="screen-title-bar">{html.escape(title)}</div>')
        if screen_context.get("is_entry_point"):
            reason = screen_context.get("entry_reason", "ENTRY")
            parts.append(f'<div class="entry-badge" title="Entry point ({reason})">{reason}</div>')
    if node_type == "TEXT":
        chars = node.get("characters", "")
        if chars:
            parts.append(f'<span class="text-content">{html.escape(chars)}</span>')
    if node_type == "SECTION":
        section_name = node.get("name", "").strip()
        if section_name:
            parts.append(f'<span class="section-label">{html.escape(section_name)}</span>')

    subtree_count = 1
    subtree_counts = Counter([node_type])
    child_under_named_section = under_named_section or is_named_section
    for child in node.get("children", []):
        child_count, child_counts = render_node(child, abs_x, abs_y, context, parts, child_under_named_section)
        subtree_count += child_count
        subtree_counts.update(child_counts)
    parts.append("</div>")
    return subtree_count, subtree_counts


def _arrow_markers(edge):
    """Return SVG marker attributes based on Figma stroke caps."""
    start_cap = edge.get("start_cap", "")
    end_cap = edge.get("end_cap", "")
    start_arrow = "ARROW" in start_cap
    end_arrow = "ARROW" in end_cap
    markers = []
    if start_arrow:
        markers.append('marker-start="url(#arrow-start)"')
    if end_arrow:
        markers.append('marker-end="url(#arrow-end)"')
    return " " + " ".join(markers) if markers else ""


def render_connectors(screen_edges, original_edges, unresolved, screens, index):
    """Render SVG lines for screen-to-screen, original node-to-node, and unresolved edges.

    The SVG is nested inside #canvas, so it shares the same local coordinate
    frame as every other rendered node: raw abs_x/abs_y, with the
    (-min_x, -min_y) shift applied exactly once via #canvas's own CSS
    position. Subtracting min_x/min_y here would double-shift the lines away
    from the boxes they connect.
    """
    screen_lookup = {s["id"]: s for s in screens}
    lines = []

    for e in screen_edges:
        s = screen_lookup.get(e["from"])
        t = screen_lookup.get(e["to"])
        if not s or not t:
            continue
        x1 = s["abs_x"] + s["width"] / 2
        y1 = s["abs_y"] + s["height"] / 2
        x2 = t["abs_x"] + t["width"] / 2
        y2 = t["abs_y"] + t["height"] / 2
        snapped_class = ' class="snapped"' if e["snapped"] else ""
        label_attr = f' data-label="{html.escape(e["label"])}"' if e["label"] else ""
        parts = [
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"',
            snapped_class,
            _arrow_markers(e),
            f' data-start-id="{html.escape(e["original_from"] or "")}"',
            f' data-end-id="{html.escape(e["original_to"] or "")}"',
            f' data-from="{html.escape(e["from"])}" data-to="{html.escape(e["to"])}"',
            f' data-snapped="{str(e["snapped"]).lower()}"',
            label_attr,
            ' />',
        ]
        lines.append("".join(parts))

    for e in original_edges:
        s = index.get(e["from"])
        t = index.get(e["to"])
        if not s or not t:
            continue
        x1 = s["abs_x"] + s["width"] / 2
        y1 = s["abs_y"] + s["height"] / 2
        x2 = t["abs_x"] + t["width"] / 2
        y2 = t["abs_y"] + t["height"] / 2
        label_attr = f' data-label="{html.escape(e["label"])}"' if e["label"] else ""
        parts = [
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"',
            ' class="original"',
            _arrow_markers(e),
            f' data-start-id="{html.escape(e["from"])}"',
            f' data-end-id="{html.escape(e["to"])}"',
            f' data-from="{html.escape(e["from"])}" data-to="{html.escape(e["to"])}"',
            label_attr,
            ' />',
        ]
        lines.append("".join(parts))

    for e in unresolved:
        s = index.get(e.get("original_from"))
        t = index.get(e.get("original_to"))
        if not s or not t:
            continue
        x1 = s["abs_x"] + s["width"] / 2
        y1 = s["abs_y"] + s["height"] / 2
        x2 = t["abs_x"] + t["width"] / 2
        y2 = t["abs_y"] + t["height"] / 2
        parts = [
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"',
            ' class="unresolved"',
            _arrow_markers(e),
            f' data-start-id="{html.escape(e.get("original_from", ""))}"',
            f' data-end-id="{html.escape(e.get("original_to", ""))}"',
            f' data-reason="{html.escape(e.get("reason", ""))}"',
            ' />',
        ]
        lines.append("".join(parts))

    return lines


CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; height: 100%; overflow: hidden; font-family: ui-sans-serif, system-ui, -apple-system, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
#header { position: fixed; top: 0; left: 0; right: 0; height: 48px; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; z-index: 100; }
#header h1 { margin: 0; font-size: 16px; font-weight: 600; }
#header .stats { font-size: 12px; color: #94a3b8; }
#controls { position: fixed; top: 48px; left: 0; right: 0; height: 40px; background: #f1f5f9; border-bottom: 1px solid #cbd5e1; display: flex; align-items: center; gap: 16px; padding: 0 16px; z-index: 100; font-size: 12px; }
#controls label { display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
#viewport { position: fixed; top: 88px; left: 0; right: 0; bottom: 0; overflow: auto; background: #f8fafc; }
#canvas { position: absolute; background: #ffffff; box-shadow: 0 0 0 1px #cbd5e1; transform-origin: 0 0; }
.node { position: absolute; pointer-events: none; white-space: nowrap; border-style: solid; }
.figma-PAGE { border: none; background: transparent; }
.figma-SECTION { border-width: 4px; border-color: #2563eb; background: rgba(37, 99, 235, 0.10); }
.section-label { position: absolute; top: -20px; left: 0; background: #2563eb; color: #ffffff; padding: 2px 6px; font-size: 14px; line-height: 1.2; white-space: normal; pointer-events: none; z-index: 10; max-width: 100%; max-height: 20px; overflow: hidden; text-overflow: ellipsis; }
.figma-FRAME { border-width: 2px; border-color: #16a34a; background: rgba(22, 163, 74, 0.14); }
.figma-FRAME.is-screen { border-color: #15803d; background: rgba(22, 163, 74, 0.22); }
.figma-INSTANCE { border-width: 1px; border-color: #ea580c; background: rgba(234, 88, 12, 0.14); }
.figma-RECTANGLE { border-width: 2px; border-color: #64748b; background: rgba(100, 116, 139, 0.22); }
.figma-TEXT { border-width: 2px; border-color: #dc2626; background: rgba(220, 38, 38, 0.08); border-style: dashed; white-space: normal; overflow: hidden; }
.figma-TEXT .text-content { display: block; font-size: 14px; line-height: 1.2; color: #dc2626; pointer-events: none; padding: 1px 2px; overflow: hidden; max-width: 100%; max-height: 100%; white-space: pre-wrap; word-break: break-word; }
.figma-CONNECTOR { border-width: 2px; border-color: #c026d3; background: rgba(192, 38, 211, 0.12); }
.figma-ELLIPSE { border-width: 2px; border-color: #7c3aed; border-radius: 50%; background: rgba(124, 58, 237, 0.12); }
#viewport.hide-SECTION .figma-SECTION { display: none; }
#viewport.hide-FRAME .figma-FRAME { display: none; }
#viewport.hide-INSTANCE .figma-INSTANCE { display: none; }
#viewport.hide-RECTANGLE .figma-RECTANGLE { display: none; }
#viewport.hide-TEXT .figma-TEXT { display: none; }
#viewport.hide-CONNECTOR .figma-CONNECTOR { display: none; }
#viewport.hide-ELLIPSE .figma-ELLIPSE { display: none; }
#viewport svg { position: absolute; left: 0; top: 0; pointer-events: none; overflow: visible; }
#viewport svg line { stroke: #000000; stroke-width: 3; }
#viewport svg line.snapped { stroke: #000000; stroke-dasharray: 6 4; }
#viewport svg line.original { stroke: #000000; stroke-width: 3; }
#viewport svg line.unresolved { stroke: #000000; stroke-width: 3; stroke-dasharray: 2 4; }
.screen-title-bar { position: absolute; top: 0; left: 0; right: 0; background: rgba(21, 128, 61, 0.92); color: #ffffff; font-size: 12px; line-height: 1.3; padding: 2px 4px; white-space: normal; overflow: hidden; text-overflow: ellipsis; z-index: 5; pointer-events: none; max-height: 3.9em; }
.entry-badge { position: absolute; top: 0; right: 0; background: #ef4444; color: #ffffff; font-size: 10px; font-weight: 700; padding: 2px 5px; border-radius: 0 0 0 4px; z-index: 6; pointer-events: none; }
"""


JS = """
(function() {
  const canvas = document.getElementById('canvas');
  const viewport = document.getElementById('viewport');
  const typeToggles = document.querySelectorAll('.type-toggle');

  // #canvas is offset by (-minX, -minY) so its content lands at local (0,0).
  // The scale transform must anchor on that same point (expressed in canvas-
  // local coordinates, i.e. (minX, minY)) or the offset and the scale no
  // longer cancel out and the whole board shifts off-screen.
  const minX = parseFloat(canvas.dataset.minX || '0');
  const minY = parseFloat(canvas.dataset.minY || '0');
  canvas.style.transformOrigin = minX + 'px ' + minY + 'px';
  // Fixed scale: no zooming capability. Default view is 50%.
  canvas.style.transform = 'scale(0.5)';

  function updateTypes() {
    const classes = [];
    typeToggles.forEach(cb => {
      if (!cb.checked) classes.push('hide-' + cb.value);
    });
    viewport.className = 'fixed' + (classes.length ? ' ' + classes.join(' ') : '');
  }

  typeToggles.forEach(cb => cb.addEventListener('change', updateTypes));

  updateTypes();

  // The transform-origin fix above makes the content's top-left land at
  // viewport-relative (0, 0) by construction, so no extra scroll is needed.
  viewport.scrollLeft = 0;
  viewport.scrollTop = 0;
})();
"""


def preprocess(input_path, flatten=True):
    """Read the golden input and run the full spatial analysis pass.

    Returns a tuple of (preprocess_dict, inventory_dict). The preprocess dict
    contains the full node tree, the flat spatial index, all derived
    screens/edges/entry points, and the lightweight rendering context. The
    inventory dict is a separate audit sidecar with screens, elements,
    connectors, and flow validation checks.

    `flatten` controls whether the tree-simplification passes run: collapsing
    each screen down to its flow-relevant content (see
    `flatten_screens_to_relevant_content`) and label-instance flattening
    (see `flatten_label_instances`). Both are on by default and only
    disabled when the caller wants the full, unmodified node tree (`--full`).
    """
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    root = data["nodes"][0]
    if flatten:
        flatten_label_instances(root)

    index, bbox = build_spatial_index(root)
    min_x, min_y, max_x, max_y = bbox
    canvas_w = max_x - min_x
    canvas_h = max_y - min_y
    text_cache = build_text_cache(index)

    screens = detect_screens(index)
    candidates = collect_contextual_info_candidates(index, screens, text_cache)
    associate_contextual_info(screens, candidates)

    node_id_to_screen, screen_connector_count, screen_nodes, flow_relevant_ids, contextual_node_id_to_screen, reaction_candidates = (
        build_screen_connector_maps(root, screens)
    )

    connectors = []
    def collect_connectors(node):
        if node.get("type") == "CONNECTOR":
            connectors.append(node)
        for child in node.get("children", []):
            collect_connectors(child)
    collect_connectors(root)

    edges, original_edges, unresolved, connector_inventory = snap_connectors(
        connectors, screens, index, contextual_node_id_to_screen,
    )


    flow_starting_points = data.get("prototype", {}).get("flowStartingPoints", [])
    entry_points = infer_entry_points(
        screens, edges, flow_starting_points, index, text_cache, screen_connector_count,
    )

    if flatten:
        flatten_screens_to_relevant_content(screen_nodes, flow_relevant_ids)

    # Strip the heavy per-node copy of the original node from the index and
    # screens; the full node tree is kept separately for rendering.
    stripped_index = {nid: {k: v for k, v in n.items() if k != "node"}
                      for nid, n in index.items()}
    stripped_screens = []
    for s in screens:
        stripped = {k: v for k, v in s.items() if k != "node"}
        stripped["contextual_informations"] = [
            {k: v for k, v in c.items() if k != "node"}
            for c in s.get("contextual_informations", [])
        ]
        stripped_screens.append(stripped)

    entry_reasons = {ep["id"]: ep["reason"] for ep in entry_points}
    screen_context = {}
    for s in stripped_screens:
        screen_context[s["id"]] = {
            "name": s.get("name", ""),
            "is_entry_point": s.get("is_entry_point", False),
            "entry_reason": entry_reasons.get(s["id"], "ENTRY"),
            "contextual_informations": [
                {"id": c["id"], "type": c["type"], "name": c["name"]}
                for c in s.get("contextual_informations", [])
            ],
        }

    return {
        "metadata": {
            "input_path": input_path,
            "file_name": data.get("file", {}).get("name", "Figma Render"),
            "total_nodes": data.get("export", {}).get("nodeCount", 0),
        },
        "canvas": {
            "min_x": min_x,
            "min_y": min_y,
            "canvas_w": canvas_w,
            "canvas_h": canvas_h,
        },
        "node_tree": root,
        "index": stripped_index,
        "text_cache": text_cache,
        "screens": stripped_screens,
        "screen_context": screen_context,
        "edges": edges,
        "original_edges": original_edges,
        "unresolved": unresolved,
        "entry_points": entry_points,
        "node_id_to_screen": node_id_to_screen,
        "contextual_node_id_to_screen": contextual_node_id_to_screen,
    }, build_inventory(
        input_path=input_path,
        file_name=data.get("file", {}).get("name", "Figma Render"),
        screens=stripped_screens,
        screen_context=screen_context,
        screen_connector_count=screen_connector_count,
        entry_points=entry_points,
        connector_inventory=connector_inventory,
        index=stripped_index,
        text_cache=text_cache,
        flow_relevant_ids=flow_relevant_ids,
        contextual_node_id_to_screen=contextual_node_id_to_screen,
        connectors=connectors,
        reaction_candidates=reaction_candidates,
        node_id_to_screen=node_id_to_screen,
    )


def render_html(preprocess_path, output_path):
    """Render workdir/render.html using only the information in pre-process.json."""
    with open(preprocess_path, "r", encoding="utf-8") as f:
        pp = json.load(f)

    metadata = pp["metadata"]
    canvas = pp["canvas"]
    root = pp["node_tree"]
    index = pp["index"]
    text_cache = pp["text_cache"]
    screens = pp["screens"]
    screen_context = pp["screen_context"]
    edges = pp["edges"]
    original_edges = pp["original_edges"]
    unresolved = pp["unresolved"]

    min_x = canvas["min_x"]
    min_y = canvas["min_y"]
    canvas_w = canvas["canvas_w"]
    canvas_h = canvas["canvas_h"]

    context = {
        "min_x": min_x,
        "min_y": min_y,
        "canvas_w": canvas_w,
        "canvas_h": canvas_h,
        "connectors": [],
        "screen_context": screen_context,
        "text_cache": text_cache,
    }

    dom_parts = []
    rendered_count, type_counts = render_node(root, 0, 0, context, dom_parts)
    dom_html = "".join(dom_parts)

    svg_lines = render_connectors(edges, original_edges, unresolved, screens, index)

    total_nodes = metadata.get("total_nodes", rendered_count)
    skipped_count = total_nodes - rendered_count
    snapped_count = sum(1 for e in edges if e.get("snapped"))

    type_options = ["SECTION", "FRAME", "INSTANCE", "TEXT", "CONNECTOR", "ELLIPSE"]
    toggle_html = "".join(
        f'<label><input type="checkbox" class="type-toggle" value="{t}" checked> {t} ({type_counts.get(t, 0)})</label>'
        for t in type_options
    )

    out_parts = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8"><title>Figma Render</title><style>',
        CSS,
        "</style></head><body>",
        '<div id="header">',
        f'<h1>{html.escape(metadata.get("file_name", "Figma Render"))}</h1>',
        f'<div class="stats">Nodes: {rendered_count} rendered / {total_nodes} total ({skipped_count} skipped) | '
        f'Screens: {len(screens)} | '
        f'Edges: {len(edges)} ({snapped_count} snapped, {len(original_edges)} original) | '
        f'Entry: {len(pp["entry_points"])} | '
        f'Canvas: {int(canvas_w)} x {int(canvas_h)}</div>',
        "</div>",
        '<div id="controls">',
        toggle_html,
        "</div>",
        '<div id="viewport">',
        f'<div id="canvas" data-min-x="{int(min_x)}" data-min-y="{int(min_y)}" '
        f'style="width:{int(canvas_w)}px;height:{int(canvas_h)}px;left:{-min_x}px;top:{-min_y}px;">',
        dom_html,
        f'<svg width="{int(canvas_w)}" height="{int(canvas_h)}">',
        '<defs>'
        '<marker id="arrow-end" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#000000" /></marker>'
        '<marker id="arrow-start" markerWidth="10" markerHeight="10" refX="1" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M9,0 L9,6 L0,3 z" fill="#000000" /></marker>'
        '</defs>',
        "".join(svg_lines),
        "</svg>",
        "</div>",
        "</div>",
        "<script>",
        JS,
        "</script></body></html>",
    ]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("".join(out_parts))

    return {
        "rendered_count": rendered_count,
        "total_nodes": total_nodes,
        "skipped_count": skipped_count,
        "snapped_count": snapped_count,
        "screens_count": len(screens),
        "edges_count": len(edges),
        "original_edges_count": len(original_edges),
        "unresolved_count": len(unresolved),
        "entry_points_count": len(pp["entry_points"]),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Render a Figma design export as a self-contained HTML wireframe."
    )
    parser.add_argument(
        "-i", "--input",
        dest="input_path",
        required=True,
        help="Path to the input JSON; output filenames are derived from this name",
    )
    parser.add_argument(
        "-w", "--workdir",
        dest="workdir",
        help="Working directory for output files (default: random folder in /tmp)",
    )
    parser.add_argument(
        "--full",
        dest="full",
        action="store_true",
        help="Disable label-instance flattening; keep the full, unflattened node tree",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["preprocess", "render"],
        default=None,
        help="Pipeline phase to run (default: run both preprocess and render)",
    )

    args = parser.parse_args()

    if args.command == "render":
        run_preprocess = False
        run_render = True
    elif args.command == "preprocess":
        run_preprocess = True
        run_render = False
    else:
        # Default: run both phases.
        run_preprocess = True
        run_render = True

    input_path = args.input_path

    if args.workdir:
        workdir = args.workdir
    else:
        workdir = os.path.join("/tmp", f"render_design_{uuid.uuid4().hex}")
    os.makedirs(workdir, exist_ok=True)

    input_stem = os.path.splitext(os.path.basename(input_path))[0]
    preprocess_path = os.path.join(workdir, input_stem + PREPROCESS_SUFFIX)
    inventory_path = os.path.join(workdir, input_stem + INVENTORY_SUFFIX)
    output_path = os.path.join(workdir, input_stem + OUTPUT_SUFFIX)

    if run_preprocess:
        pp, inventory = preprocess(input_path, flatten=not args.full)
        os.makedirs(os.path.dirname(preprocess_path), exist_ok=True)
        with open(preprocess_path, "w", encoding="utf-8") as f:
            json.dump(pp, f, ensure_ascii=False, separators=(",", ":"))
        print(f"Wrote {preprocess_path}")
        with open(inventory_path, "w", encoding="utf-8") as f:
            json.dump(inventory, f, ensure_ascii=False, separators=(",", ":"))
        print(f"Wrote {inventory_path}")
        summary = inventory["summary"]
        print(
            f"Inventory: {summary['screens_total']} screens, "
            f"{summary['elements_total']} elements, "
            f"{summary['connectors_total']} connectors "
            f"({summary['connectors_resolved_screen_edge']} screen-edge, "
            f"{summary['connectors_resolved_original_edge']} original, "
            f"{summary['connectors_unresolved']} unresolved), "
            f"{summary['entry_points']} entry points, "
            f"{summary['reachable_screens']} reachable, "
            f"{summary['unreachable_screens']} unreachable"
        )

    if run_render:
        stats = render_html(preprocess_path, output_path)
        print(f"Wrote {output_path}")
        print(f"Nodes: {stats['rendered_count']} rendered / {stats['total_nodes']} total ({stats['skipped_count']} skipped)")
        print(f"Screens: {stats['screens_count']}")
        print(f"Edges: {stats['edges_count']} ({stats['snapped_count']} snapped, {stats['original_edges_count']} original, {stats['unresolved_count']} unresolved)")
        print(f"Entry points: {stats['entry_points_count']}")


if __name__ == "__main__":
    main()
