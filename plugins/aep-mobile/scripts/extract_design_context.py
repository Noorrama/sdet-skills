#!/usr/bin/env python3
"""Build the mechanical half of a design_context from a Figma raw-JSON export.

Everything here is a graph operation over the export tree — indexing, classifying
board nodes, collapsing state frames, resolving connector endpoints, contracting
decision boxes, tallying conservation buckets. A language model executing this in
prose produces schema-valid output with wrong values (measured: 94 screen objects
for 33 screens, 6 of 47 connectors resolved, zero gaps reported), so it lives in
code and the model keeps only the semantic fields.

    ./extract_design_context.py export.json --app gopay-merchant -o design_context.json --report

Semantic fields the model still fills afterwards:
  visual_analysis_scratchpad, screens[].purpose, screens[].screen_notes,
  elements[].label refinement, extraction_gaps[], overall_ambiguity_rating.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from typing import Any, Iterable

# --- classification thresholds ----------------------------------------------

# A screen is device-WIDTH. There is deliberately no upper height bound: real
# boards carry 360x2066 scrolling screens beside 360x918 dialogs, and an upper
# cap rejects exactly the long screens that matter. The height floor is only
# there to exclude label strips (measured: 360x37, 302x116, 358x118).
SCREEN_MIN_WIDTH = 300
SCREEN_MAX_WIDTH = 520
SCREEN_MIN_HEIGHT = 500

# Fallback when the export predates geometry. Measured split on a real board:
# screens hold 200-690 descendants, caption/decision/note boxes hold <= 6.
DESCENDANT_SCREEN_MIN = 30

# A lane banner is a wide, short strip fronting a group of screens.
BANNER_MAX_HEIGHT = 150
BANNER_WIDTH_RATIO = 0.8

# Contraction bounds. Unbounded contraction on a real board produced 853 edges
# with 595 fabricated conditions, because lane/section containers act as hubs.
MAX_HOP_FANOUT = 4

STRUCTURAL_TYPES = frozenset({"PAGE", "CANVAS", "SECTION", "GROUP"})
BOARD_TYPES = frozenset({"FRAME", "COMPONENT", "INSTANCE"})

# Emitted even when zero. A sparse block cannot distinguish "no note connectors
# on this board" from "note detection never ran" — and that ambiguity is what let
# an all-zero run look plausible.
COMPLIANCE_KEYS = (
    "connectors_total",
    "connectors_resolved_to_screen",
    "connectors_inferred_to_screen",
    "connectors_unresolvable",
    "connectors_intra_screen",
    "connectors_to_decision",
    "note_connectors",
    "caption_endpoints",
    "decision_nodes",
    "contracted_edges",
    "lane_entry_inferred",
    "unlabelled_branches",
    "non_descriptive_names",
    "unreachable_screens",
)

# The buckets every connector must land in exactly once.
CONSERVED_BUCKETS = (
    "connectors_resolved_to_screen",
    "connectors_inferred_to_screen",
    "connectors_unresolvable",
    "connectors_intra_screen",
    "connectors_to_decision",
    "note_connectors",
)

DEFAULT_ANNOTATION_COMPONENTS = ["Notes", "Note", "Annotation", "Comment", "tooltip*"]

DEFAULT_ROLE_VOCABULARY = ["_btn", "_input", "_label", "_toggle", "_tab", "_list"]

ROLE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("BUTTON", ("button", "btn", "cta", "fab")),
    ("INPUT", ("field", "input", "search", "textfield", "form")),
    ("TOGGLE", ("toggle", "switch", "checkbox", "check_box", "radio")),
    ("TAB", ("tab", "segment", "chip")),
    ("LIST", ("list", "row", "card", "cell", "carousel", "item")),
)
ROLE_SUFFIX = {
    "BUTTON": "_btn",
    "INPUT": "_input",
    "LABEL": "_label",
    "TOGGLE": "_toggle",
    "TAB": "_tab",
    "LIST": "_list",
}

NON_DESCRIPTIVE = re.compile(r"^(frame|group|rectangle|component|ellipse|vector)\b", re.I)
# Split once, from the LEFT, and keep element 0. Splitting from the right (or
# keeping element 1) turns "Confirm account / EN" into a screen called EN.
QUALIFIER_SPLIT = re.compile(r"\s+[—–-]\s+|\s*/\s*")

STATE_KIND_PATTERNS: tuple[tuple[str, str], ...] = (
    ("error", "ERROR"),
    ("loading", "LOADING"),
    ("empty", "EMPTY"),
    ("success", "SUCCESS"),
    ("offline", "OFFLINE"),
    ("disable", "DISABLED"),
    ("permission", "PERMISSION_DENIED"),
    ("dark", "DARK_THEME"),
    ("light", "LIGHT_THEME"),
    ("rtl", "RTL"),
)
LOCALE_TOKENS = frozenset({"en", "id", "th", "vn", "sg", "ph"})


class Board:
    """The export tree, indexed and classified."""

    def __init__(self, export: dict[str, Any], annotation_components: Iterable[str]):
        self.export = export
        self.nodes: dict[str, dict] = {}
        self.parent: dict[str, str | None] = {}
        self.annotation = [c.lower() for c in annotation_components]

        for root in export.get("nodes", []):
            self._index(root, None)

        self.connectors = [n for n in self.nodes.values() if n.get("type") == "CONNECTOR"]
        self.has_geometry = any("width" in n for n in self.nodes.values())

        self._descendants: dict[str, int] = {}
        self._out_degree = Counter()
        for conn in self.connectors:
            start = endpoint_id(conn, "connectorStart")
            if start:
                self._out_degree[start] += 1

        self.node_class: dict[str, str] = {}
        self._classify()

    # --- indexing ---

    def _index(self, node: dict, parent_id: str | None) -> None:
        self.nodes[node["id"]] = node
        self.parent[node["id"]] = parent_id
        for child in node.get("children", []):
            self._index(child, node["id"])

    def ancestors(self, node_id: str | None) -> list[str]:
        out = []
        while node_id:
            out.append(node_id)
            node_id = self.parent.get(node_id)
        return out

    def descendants(self, node_id: str) -> int:
        cached = self._descendants.get(node_id)
        if cached is not None:
            return cached
        total = 1 + sum(self.descendants(c["id"]) for c in self.nodes[node_id].get("children", []))
        self._descendants[node_id] = total
        return total

    def texts(self, node_id: str, limit: int = 6) -> list[str]:
        found: list[str] = []

        def walk(node: dict) -> None:
            if len(found) >= limit:
                return
            if node.get("type") == "TEXT" and node.get("characters"):
                found.append(node["characters"].strip())
            for child in node.get("children", []):
                walk(child)

        walk(self.nodes[node_id])
        return found

    # --- classification ---

    def _is_board_node(self, node: dict) -> bool:
        """Top-level object on the flow board: only structural nodes above it."""
        if node.get("type") not in BOARD_TYPES:
            return False
        parent_id = self.parent.get(node["id"])
        while parent_id:
            if self.nodes[parent_id].get("type") not in STRUCTURAL_TYPES:
                return False
            parent_id = self.parent.get(parent_id)
        return True

    def _is_annotation_name(self, name: str | None) -> bool:
        lowered = (name or "").strip().lower()
        for pattern in self.annotation:
            if pattern.endswith("*"):
                if lowered.startswith(pattern[:-1]):
                    return True
            elif lowered == pattern:
                return True
        return False

    def _outgoing(self, node_id: str) -> int:
        """Connectors leaving this node or its immediate children."""
        return self._out_degree[node_id] + sum(
            self._out_degree[c["id"]] for c in self.nodes[node_id].get("children", [])
        )

    def _screen_sized(self, node: dict) -> bool | None:
        """True/False by geometry, None when the export carries no geometry."""
        width, height = node.get("width"), node.get("height")
        if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
            return None
        return SCREEN_MIN_WIDTH <= width <= SCREEN_MAX_WIDTH and height >= SCREEN_MIN_HEIGHT

    def _classify(self) -> None:
        for node in self.nodes.values():
            if not self._is_board_node(node):
                continue
            node_id = node["id"]

            if self._is_annotation_name(node.get("name")) or any(
                self._is_annotation_name(self.nodes[a].get("name"))
                for a in self.ancestors(node_id)[1:]
            ):
                self.node_class[node_id] = "NOTE"
                continue

            sized = self._screen_sized(node)
            if sized is None:
                sized = self.descendants(node_id) >= DESCENDANT_SCREEN_MIN
            if sized:
                self.node_class[node_id] = "SCREEN"
                continue

            body = self.texts(node_id)
            if any(t.endswith("?") for t in body) and self._outgoing(node_id) >= 2:
                self.node_class[node_id] = "DECISION"
            elif body:
                self.node_class[node_id] = "CAPTION"
            else:
                self.node_class[node_id] = "UNKNOWN"


def endpoint_id(connector: dict, key: str) -> str | None:
    """A floating endpoint carries `position` and no id — nothing to resolve."""
    endpoint = connector.get(key)
    if isinstance(endpoint, dict):
        target = endpoint.get("endpointNodeId")
        if isinstance(target, str):
            return target
    return None


def connector_label(connector: dict) -> str:
    sublayer = connector.get("text")
    if isinstance(sublayer, dict):
        return (sublayer.get("characters") or "").strip()
    return ""


def split_name(name: str | None) -> tuple[str, str, str | None]:
    """'Confirm account / EN' -> ('CONFIRM_ACCOUNT', 'Confirm account', 'EN')."""
    raw = (name or "").strip()
    parts = QUALIFIER_SPLIT.split(raw, maxsplit=1)
    base = parts[0].strip()
    qualifier = parts[1].strip() if len(parts) > 1 else None
    screen_id = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_").upper() or "UNNAMED"
    return screen_id, base, qualifier


def state_kind(qualifier: str | None) -> str:
    if not qualifier:
        return "DEFAULT"
    lowered = qualifier.lower()
    for needle, kind in STATE_KIND_PATTERNS:
        if needle in lowered:
            return kind
    if lowered in LOCALE_TOKENS or "locale" in lowered:
        return "LOCALE_VARIANT"
    return "OTHER"


def role_of(name: str | None) -> str:
    lowered = (name or "").lower()
    for role, keywords in ROLE_KEYWORDS:
        if any(k in lowered for k in keywords):
            return role
    return "LABEL"


def slugify(text: str | None, max_words: int = 5) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_").lower()
    return "_".join([w for w in cleaned.split("_") if w][:max_words])


class Extractor:
    def __init__(self, board: Board, app: str | None, role_vocabulary: list[str]):
        self.board = board
        self.app = app
        self.role_suffix = {
            role: suffix for role, suffix in ROLE_SUFFIX.items() if suffix in role_vocabulary
        } or dict(ROLE_SUFFIX)
        self.counts = Counter()
        self.blocking_issues: list[str] = []

        self.groups: dict[str, list[str]] = defaultdict(list)
        for node_id, cls in board.node_class.items():
            if cls == "SCREEN":
                self.groups[split_name(board.nodes[node_id]["name"])[0]].append(node_id)
        # EVERY collapsed frame maps to the screen. Resolving against only the
        # representative is what silently drops flows drawn from other states.
        self.frame_to_screen = {
            frame: screen for screen, frames in self.groups.items() for frame in frames
        }

    # --- resolution ---

    def resolve(self, node_id: str | None) -> tuple[str | None, str | None]:
        for ancestor in self.board.ancestors(node_id):
            if ancestor in self.frame_to_screen:
                return self.frame_to_screen[ancestor], "SCREEN"
            cls = self.board.node_class.get(ancestor)
            if cls in ("NOTE", "DECISION", "CAPTION"):
                return ancestor, cls
        return None, None

    def lane_entry(self, banner_id: str) -> str | None:
        """A banner fronts the screens BELOW it, above the next banner.

        The banner is a strip beside the screens, not a container of them, so
        walking up its ancestors reaches only the SECTION — and then every
        banner in that section resolves to the same screen, silently merging
        two branches of one decision.
        """
        board = self.board
        top = banner_id
        while board.parent.get(top) and board.nodes[board.parent[top]]["type"] not in STRUCTURAL_TYPES:
            top = board.parent[top]
        parent_id = board.parent.get(top)
        if not parent_id:
            return None
        me = board.nodes.get(top, {})
        if "y" not in me:
            return None

        siblings = [c for c in board.nodes[parent_id].get("children", []) if "y" in c]
        my_y = me["y"]
        my_width = me.get("width") or 0
        next_banners = sorted(
            c["y"]
            for c in siblings
            if c["y"] > my_y
            and (c.get("width") or 0) >= my_width * BANNER_WIDTH_RATIO
            and (c.get("height") or 0) < BANNER_MAX_HEIGHT
        )
        limit = next_banners[0] if next_banners else float("inf")
        band = [
            c for c in siblings if c["id"] in self.frame_to_screen and my_y < c["y"] < limit
        ]
        if not band:
            return None
        band.sort(key=lambda c: (c["y"], c["x"]))
        return band[0]["id"]

    # --- flow ---

    def build_flow(self) -> list[dict]:
        board = self.board
        self.counts["connectors_total"] = len(board.connectors)

        outgoing: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for conn in board.connectors:
            start, end = endpoint_id(conn, "connectorStart"), endpoint_id(conn, "connectorEnd")
            if start and end:
                anchor, _ = self.resolve(start)
                outgoing[anchor or start].append((end, connector_label(conn), conn["id"]))

        edges: list[dict] = []
        for conn in board.connectors:
            start = endpoint_id(conn, "connectorStart")
            end = endpoint_id(conn, "connectorEnd")
            label = connector_label(conn)

            if not start or not end:
                self.counts["connectors_unresolvable"] += 1
                self.blocking_issues.append(
                    f"Connector {conn['id']} has a floating endpoint — destination unresolvable."
                )
                continue

            src, src_kind = self.resolve(start)
            dst, dst_kind = self.resolve(end)

            if src_kind == "NOTE" or dst_kind == "NOTE":
                self.counts["note_connectors"] += 1
                continue

            if src_kind != "SCREEN":
                self.counts["connectors_unresolvable"] += 1
                self.blocking_issues.append(
                    f"Connector {conn['id']} starts on a "
                    f"{src_kind or 'node with no board ancestor'} — no source screen."
                )
                continue

            if dst_kind == "SCREEN":
                if src == dst:
                    self.counts["connectors_intra_screen"] += 1
                    continue
                self.counts["connectors_resolved_to_screen"] += 1
                edges.append(self._edge(src, dst, label, "CONNECTOR", "EXPLICIT", conn["id"]))
                continue

            if dst_kind == "DECISION":
                self.counts["connectors_to_decision"] += 1
                self._contract(src, dst, end, label, conn, outgoing, edges)
                continue

            if dst_kind == "CAPTION":
                self.counts["caption_endpoints"] += 1
                entry = self.lane_entry(dst)
                target = self.frame_to_screen.get(entry) if entry else None
                if target and target != src:
                    self.counts["connectors_inferred_to_screen"] += 1
                    self.counts["lane_entry_inferred"] += 1
                    edges.append(
                        self._edge(src, target, label, "CONNECTOR_INFERRED", "INFERRED", conn["id"])
                    )
                else:
                    self.counts["connectors_unresolvable"] += 1
                    caption = (self.board.texts(dst, 1) or ["(no text)"])[0][:60]
                    self.blocking_issues.append(
                        f"Connector {conn['id']} from {src} ends on caption {caption!r}, "
                        f"which fronts no screen — destination unstated (standard #1)."
                    )
                continue

            self.counts["connectors_unresolvable"] += 1
            self.blocking_issues.append(
                f"Connector {conn['id']} from {src} ends on a node with no board ancestor."
            )

        return self._dedupe(edges)

    def _contract(self, src, decision_id, raw_end, label, conn, outgoing, edges) -> None:
        exits = [
            x
            for x in (outgoing.get(decision_id, []) + outgoing.get(raw_end, []))
            if x[2] != conn["id"]
        ]
        if not exits or len(exits) > MAX_HOP_FANOUT:
            self.counts["connectors_unresolvable"] += 1
            self.counts["connectors_to_decision"] -= 1
            self.blocking_issues.append(
                f"Connector {conn['id']} ends on a decision box with {len(exits)} exits — "
                f"outside the one-hop / fan-out<={MAX_HOP_FANOUT} bound, not contracted."
            )
            return

        for exit_end, exit_label, _ in exits:
            target, target_kind = self.resolve(exit_end)
            if target_kind == "CAPTION":
                entry = self.lane_entry(target)
                target = self.frame_to_screen.get(entry) if entry else None
                if target:
                    self.counts["lane_entry_inferred"] += 1
            elif target_kind != "SCREEN":
                target = None

            condition = " / ".join(x for x in (label, exit_label) if x)
            if target and target != src:
                self.counts["contracted_edges"] += 1
                edges.append(
                    self._edge(
                        src, target, condition, "CONNECTOR_CONTRACTED", "INFERRED", decision_id
                    )
                )
            else:
                self.blocking_issues.append(
                    f"Branch {condition!r} out of decision box {decision_id} has no resolvable "
                    f"destination screen."
                )

    @staticmethod
    def _edge(src, dst, condition, edge_source, confidence, source_ref) -> dict:
        return {
            "from_screen_id": src,
            "to_screen_id": dst,
            "condition": condition,
            "navigation_kind": "NAVIGATE",
            "edge_source": edge_source,
            "confidence": confidence,
            "source_ref": source_ref,
        }

    @staticmethod
    def _dedupe(edges: list[dict]) -> list[dict]:
        seen, out = set(), []
        for edge in edges:
            key = (edge["from_screen_id"], edge["to_screen_id"], edge["condition"])
            if key not in seen:
                seen.add(key)
                out.append(edge)
        return out

    # --- screens & elements ---

    def build_screens(self) -> list[dict]:
        board = self.board
        triggers: dict[str, list[str]] = defaultdict(list)
        for conn in board.connectors:
            start = endpoint_id(conn, "connectorStart")
            if not start or start not in board.nodes:
                continue
            screen, kind = self.resolve(start)
            if kind == "SCREEN":
                triggers[screen].append(start)

        entry_points = {
            fsp.get("nodeId")
            for root in board.export.get("nodes", [])
            for fsp in (root.get("flowStartingPoints") or [])
        }

        screens = []
        for screen_id, frames in sorted(self.groups.items()):
            frames = sorted(frames, key=lambda i: (board.nodes[i].get("y", 0), board.nodes[i].get("x", 0)))
            representative = frames[0]
            _, base, _ = split_name(board.nodes[representative]["name"])

            qualifiers, kinds = [], set()
            for frame in frames:
                _, _, qualifier = split_name(board.nodes[frame]["name"])
                if qualifier and qualifier not in qualifiers:
                    qualifiers.append(qualifier)
                kinds.add(state_kind(qualifier))
            if not qualifiers:
                qualifiers = ["Default"]

            if NON_DESCRIPTIVE.match(base):
                self.counts["non_descriptive_names"] += 1
                self.blocking_issues.append(
                    f"Screen {screen_id} comes from a frame literally named {base!r} — no stable "
                    f"screen_id can be derived (standard #3)."
                )

            screens.append(
                {
                    "screen_id": screen_id,
                    "screen_name": board.nodes[representative]["name"],
                    "source_ref": representative,
                    "source_refs": frames,
                    "node_class": "SCREEN",
                    "classified_by": "GEOMETRY" if board.has_geometry else "DESCENDANT_COUNT",
                    "purpose": "",
                    "entry_point": any(f in entry_points for f in frames),
                    "screen_states": qualifiers,
                    "state_kinds": sorted(kinds),
                    "elements": self._elements(screen_id, triggers.get(screen_id, [])),
                    "screen_notes": "",
                }
            )
        return screens

    def _elements(self, screen_id: str, trigger_ids: list[str]) -> list[dict]:
        board = self.board
        elements, used = [], set()
        for node_id in dict.fromkeys(trigger_ids):
            node = board.nodes[node_id]
            role = role_of(node.get("name"))
            label = (board.texts(node_id, 1) or [""])[0]
            stem = slugify(label) or slugify(node.get("name")) or "element"
            element_id = f"{screen_id}.{stem}{self.role_suffix.get(role, '_label')}"
            if element_id in used:
                continue
            used.add(element_id)
            elements.append(
                {
                    "element_id": element_id,
                    "source_ref": node_id,
                    "type": node["type"],
                    "role": role,
                    "label": label,
                    "states_represented": [],
                    "interactions": [
                        {
                            "trigger": "onTap",
                            "action": "Navigates via a design connector — see ui_flow.",
                        }
                    ],
                    "validations_and_edge_cases": [],
                }
            )
        return elements

    # --- conservation ---

    def check_conservation(self) -> None:
        total = sum(self.counts[b] for b in CONSERVED_BUCKETS)
        expected = self.counts["connectors_total"]
        if total != expected:
            raise SystemExit(
                f"conservation check FAILED: buckets sum to {total}, "
                f"connectors_total is {expected}. {abs(expected - total)} connector(s) were "
                f"dropped without landing in a bucket — that is the silent-drop bug this check "
                f"exists to prevent."
            )


def build(export: dict, app: str | None, config: dict) -> tuple[dict, Extractor]:
    components = (config.get("design_components") or {}).get("annotation") or DEFAULT_ANNOTATION_COMPONENTS
    vocabulary = (config.get("naming_convention") or {}).get("role_vocabulary") or DEFAULT_ROLE_VOCABULARY

    board = Board(export, components)
    extractor = Extractor(board, app, vocabulary)

    flow = extractor.build_flow()
    screens = extractor.build_screens()
    extractor.check_conservation()

    extractor.counts["decision_nodes"] = sum(
        1 for cls in board.node_class.values() if cls == "DECISION"
    )
    reached = {e["from_screen_id"] for e in flow} | {e["to_screen_id"] for e in flow}
    unreachable = sorted({s["screen_id"] for s in screens} - reached)
    extractor.counts["unreachable_screens"] = len(unreachable)
    for screen_id in unreachable:
        extractor.blocking_issues.append(
            f"Screen {screen_id} appears in the design but no connector reaches it."
        )

    # Attach trigger elements where the connector started on a known element.
    by_screen = {s["screen_id"]: s for s in screens}
    for edge in flow:
        source = edge.get("source_ref")
        screen = by_screen.get(edge["from_screen_id"])
        if not screen:
            continue
        match = next((e["element_id"] for e in screen["elements"] if e["source_ref"] == source), None)
        if match:
            edge["trigger_element_id"] = match

    export_meta = export.get("export", {})
    doc = {
        "design_source": {
            "file_name": export.get("file", {}).get("name", ""),
            "page_name": export.get("file", {}).get("page", ""),
            "scope": export.get("scope", "page"),
            "exported_at": export.get("exportedAt", ""),
            "max_depth": export_meta.get("maxDepth", 0),
            "node_count": export_meta.get("nodeCount", 0),
            "truncated_count": export_meta.get("truncatedCount", 0),
            "has_geometry": board.has_geometry,
        },
        "extraction_status": "INCOMPLETE",
        "extraction_gaps": [],
        "visual_analysis_scratchpad": "",
        "project_context": {
            "overall_ambiguity_rating": "MEDIUM",
            "blocking_issues": extractor.blocking_issues,
            "convention_compliance": {k: int(extractor.counts[k]) for k in COMPLIANCE_KEYS},
        },
        "screens": screens,
        "ui_flow": flow,
    }
    if app:
        doc = {"app": app, **doc}
    return doc, extractor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", help="Figma raw-JSON export from the Export Design Raw JSON plugin")
    parser.add_argument("--app", help="app id stamped onto the output")
    parser.add_argument("--config", help="path to config/<app>.json")
    parser.add_argument("-o", "--output", help="write here instead of stdout")
    parser.add_argument("--report", action="store_true", help="summary on stderr")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as handle:
        export = json.load(handle)
    if "nodes" not in export:
        raise SystemExit(
            f"{args.input} is not an Export Design Raw JSON payload: no `nodes` key."
        )

    config: dict[str, Any] = {}
    if args.config:
        try:
            with open(args.config, encoding="utf-8") as handle:
                config = json.load(handle)
        except OSError as exc:
            print(f"warning: cannot read {args.config} ({exc}); using defaults", file=sys.stderr)

    doc, extractor = build(export, args.app, config)

    text = json.dumps(doc, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")

    if args.report:
        counts = extractor.counts
        conditions = sum(1 for e in doc["ui_flow"] if e["condition"])
        print(
            f"screens {len(doc['screens'])} "
            f"(collapsed from {sum(len(s['source_refs']) for s in doc['screens'])} frames) | "
            f"elements {sum(len(s['elements']) for s in doc['screens'])} | "
            f"edges {len(doc['ui_flow'])} ({conditions} with a condition) | "
            f"connectors {counts['connectors_total']} "
            f"[screen {counts['connectors_resolved_to_screen']}, "
            f"inferred {counts['connectors_inferred_to_screen']}, "
            f"decision {counts['connectors_to_decision']}, "
            f"note {counts['note_connectors']}, "
            f"intra {counts['connectors_intra_screen']}, "
            f"unresolved {counts['connectors_unresolvable']}] | "
            f"blockers {len(doc['project_context']['blocking_issues'])} | "
            f"geometry {'yes' if extractor.board.has_geometry else 'NO (descendant-count fallback)'}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
