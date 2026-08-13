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
  visual_analysis_scratchpad, elements[].label refinement, extraction_gaps[],
  overall_ambiguity_rating. (purpose and states_represented are no longer produced:
  nothing downstream reads them and a board does not carry them.)
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
    "label_frames_resolved",
    "decision_nodes",
    "contracted_edges",
    "lane_entry_inferred",
    "unlabelled_branches",
    "non_descriptive_names",
    "screen_id_from_banner",
    "unreachable_screens",
    "notes_total",
    "notes_attached_by_connector",
    "notes_attached_by_geometry",
    "notes_unattached",
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

# The annotation component ships a heading layer; it is chrome, not content, and
# repeating it on every screen would drown the actual note.
NOTE_BOILERPLATE = frozenset({"notes / annotation", "notes", "note", "annotation", "comment"})

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


def normalise_question(text: str | None) -> str:
    """'Does user have GoPay+ ?' -> 'Does user have GoPay+?'.

    Designers space-pad punctuation for layout; the condition string is read by
    humans and pasted into test steps, so close the gap.
    """
    collapsed = re.sub(r"\s+", " ", (text or "").strip())
    return re.sub(r"\s+([?!:;,.])", r"\1", collapsed)


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


def is_non_descriptive(name: str | None) -> bool:
    return bool(NON_DESCRIPTIVE.match((name or "").strip()))


def usable_as_screen_name(text: str) -> bool:
    """A banner names a SCREEN only if it is short and is not a state word.

    Measured rejections on a real board: 'Scroll View with Loading State' and
    'Loading' name a state, not a screen; '1KYC | NON-Progressive Flow (Screens
    are only for reference, not owned by MSME Team)' is a lane header sentence.
    """
    text = (text or "").strip()
    if not text or len(text) > 40 or len(text.split()) > 5:
        return False
    return state_kind(text) in ("DEFAULT", "OTHER")


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
        self.by_trigger: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        # screen_id -> display name, when a banner supplied it.
        self.screen_names: dict[str, str] = {}
        # screen_id -> state texts recovered from label frames.
        self.label_states: dict[str, list[str]] = {}
        # (note_node_id, other_endpoint_id, other_kind) for every note connector.
        self.note_links: list[tuple[str, str | None, str | None]] = []

        self.groups: dict[str, list[str]] = defaultdict(list)
        for node_id, cls in board.node_class.items():
            if cls == "SCREEN":
                self.groups[split_name(board.nodes[node_id]["name"])[0]].append(node_id)

        # Renaming MUST happen here — before frame_to_screen exists and before any
        # element or edge is built. screen_id is the prefix of every element_id and
        # both ends of every ui_flow edge; renaming later leaves dangling ids.
        self.screen_renames: list[dict[str, str]] = []
        self._rename_from_banners()

        # EVERY collapsed frame maps to the screen. Resolving against only the
        # representative is what silently drops flows drawn from other states.
        self.frame_to_screen = {
            frame: screen for screen, frames in self.groups.items() for frame in frames
        }

    # --- naming ---

    def _banner_above(self, screen_frame: str) -> dict | None:
        """Nearest wide, short strip above this frame in the same parent.

        Wide is the discriminator: a lane/section banner spans far past a single
        screen, while a state label matches the screen's own width.
        """
        board = self.board
        node = board.nodes[screen_frame]
        parent_id = board.parent.get(screen_frame)
        if not parent_id or "x" not in node:
            return None
        candidates = [
            c
            for c in board.nodes[parent_id].get("children", [])
            if "x" in c
            and c["id"] not in self.groups.get(split_name(node["name"])[0], [])
            and (c.get("height") or 0) < BANNER_MAX_HEIGHT
            and (c.get("width") or 0) > 1.5 * (node.get("width") or 0)
            and c["y"] < node["y"]
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda c: -c["y"])
        return candidates[0]

    def _rename_from_banners(self) -> None:
        """Give a gibberish-named screen the name of the section banner above it.

        Only fires when the screen's own name is already useless, and only when
        the banner reads like a screen name rather than a state or a sentence.
        """
        for screen_id in sorted(self.groups):
            frames = self.groups[screen_id]
            representative = min(
                frames, key=lambda i: (self.board.nodes[i].get("y", 0), self.board.nodes[i].get("x", 0))
            )
            name = self.board.nodes[representative].get("name")
            if not is_non_descriptive(split_name(name)[1]):
                continue
            banner = self._banner_above(representative)
            if not banner:
                continue
            text = (self.board.texts(banner["id"], 1) or [""])[0]
            if not usable_as_screen_name(text):
                continue
            new_id = split_name(text)[0]
            if new_id in self.groups:          # never collide with a real screen
                continue
            self.groups[new_id] = self.groups.pop(screen_id)
            self.screen_names[new_id] = text
            self.screen_renames.append(
                {
                    "from": screen_id,
                    "to": new_id,
                    "banner_text": text,
                    "banner_node_id": banner["id"],
                    "screen_source_ref": representative,
                }
            )
            self.counts["screen_id_from_banner"] += 1

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

    def label_frame_target(self, node_id: str) -> tuple[str, str] | None:
        """Is this gibberish-named strip the label of exactly one screen below it?

        Fires only as a fallback, when a connector has already failed to resolve.
        All five conditions must hold — the point is to confirm the pattern, not
        to assume it. Returns (screen_id, label_text) or None.

        Measured on a real board: accepts the two genuine label frames, rejects
        an external-file pointer and the decision box (both score zero aligned
        screens), so the branch labels are structurally out of reach.
        """
        board = self.board
        top = node_id
        while board.parent.get(top) and board.nodes[board.parent[top]]["type"] not in STRUCTURAL_TYPES:
            top = board.parent[top]
        node = board.nodes[top]

        # 1. its own name must be the thing that failed us
        if not is_non_descriptive(node.get("name")):
            return None
        # 2. text-only: a real screen carries dozens of nested nodes
        subtree = []
        def walk(n):
            subtree.append(n)
            for c in n.get("children", []):
                walk(c)
        walk(node)
        if len(subtree) > 4 or any(n.get("type") not in ("TEXT", "FRAME", "GROUP") for n in subtree):
            return None
        # 3. a label is a strip
        if "x" not in node or (node.get("height") or 0) >= BANNER_MAX_HEIGHT:
            return None

        parent_id = board.parent.get(top)
        if not parent_id:
            return None
        screens = [
            c for c in board.nodes[parent_id].get("children", [])
            if c["id"] in self.frame_to_screen and "x" in c
        ]
        if not screens:
            return None
        # 4. not a lane banner — those head a band and belong to lane_entry
        if (node.get("width") or 0) > 1.5 * max(c["width"] for c in screens):
            return None

        # 5. exactly ONE column-aligned screen below. Column alignment is the
        # rule; y-proximity alone pairs a label with a screen in another column.
        aligned = []
        for candidate in screens:
            overlap = min(node["x"] + node["width"], candidate["x"] + candidate["width"]) - max(
                node["x"], candidate["x"]
            )
            gap = candidate["y"] - (node["y"] + node["height"])
            if overlap >= 0.8 * min(node["width"], candidate["width"]) and 0 <= gap <= 120:
                aligned.append((gap, candidate))
        if len(aligned) != 1:
            return None
        neighbour = aligned[0][1]
        # 6. the screen it labels must itself be properly named — that is the
        # pattern being relied on
        if is_non_descriptive(split_name(neighbour["name"])[1]):
            return None

        text = (board.texts(top, 1) or [""])[0].strip()
        if not text:
            return None
        return self.frame_to_screen[neighbour["id"]], text

    def _record_state(self, screen_id: str, text: str) -> None:
        self.label_states.setdefault(screen_id, []).append(text)

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
            # Keyed by the RAW start node, not the resolved screen: interactions
            # belong to the element the designer drew from. A trigger with two
            # connectors gets two interactions — a single stub would drop one.
            if start:
                self.by_trigger[start].append((conn["id"], end))

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
                # Remember the pairing now, while the classification is in hand.
                # The note pass reads only this list — it never re-examines a
                # connector that reached a flow bucket, so attaching note text
                # cannot disturb the branch labels or any conservation count.
                note_id, other, other_kind = (
                    (src, end, dst_kind) if src_kind == "NOTE" else (dst, start, src_kind)
                )
                self.note_links.append((note_id, other, other_kind))
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
                    continue

                # Fallback: the destination may be a label frame naming the state
                # of the screen directly below it. Only reached once normal
                # resolution has failed.
                labelled = self.label_frame_target(dst)
                if labelled:
                    screen, text = labelled
                    self.counts["label_frames_resolved"] += 1
                    self._record_state(screen, text)
                    if screen != src:
                        self.counts["connectors_inferred_to_screen"] += 1
                        edges.append(
                            self._edge(
                                src, screen, label, "CONNECTOR_INFERRED", "INFERRED", conn["id"]
                            )
                        )
                    else:
                        # The label names a state of the SOURCE screen, so this is
                        # a state change, not navigation.
                        self.counts["connectors_intra_screen"] += 1
                    continue

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

        question = normalise_question((self.board.texts(decision_id, 1) or [""])[0])

        for exit_end, exit_label, exit_conn_id in exits:
            target, target_kind = self.resolve(exit_end)
            if target_kind == "CAPTION":
                entry = self.lane_entry(target)
                target = self.frame_to_screen.get(entry) if entry else None
                if target:
                    self.counts["lane_entry_inferred"] += 1
            elif target_kind != "SCREEN":
                target = None

            # "<question> — <value>", with any label on the connector INTO the
            # decision kept in front so no authored text is lost.
            branch = f"{question} — {exit_label}" if question and exit_label else (question or exit_label)
            condition = " / ".join(x for x in (label, branch) if x)

            if target and target != src:
                self.counts["contracted_edges"] += 1
                edge = self._edge(
                    src, target, condition, "CONNECTOR_CONTRACTED", "INFERRED", exit_conn_id
                )
                # The box is carried explicitly, so source_ref can stay what it
                # is on every other edge: the connector this edge came from.
                edge["decision_node_id"] = decision_id
                if question:
                    edge["decision_question"] = question
                if exit_label:
                    edge["decision_value"] = exit_label
                edges.append(edge)
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
            renamed = self.screen_names.get(screen_id)
            _, base, _ = split_name(renamed or board.nodes[representative]["name"])

            qualifiers, kinds = [], set()
            for frame in frames:
                _, _, qualifier = split_name(board.nodes[frame]["name"])
                if qualifier and qualifier not in qualifiers:
                    qualifiers.append(qualifier)
                kinds.add(state_kind(qualifier))
            for recovered in self.label_states.get(screen_id, []):
                if recovered not in qualifiers:
                    qualifiers.append(recovered)
                    kinds.add(state_kind(recovered))
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
                    "screen_name": renamed or board.nodes[representative]["name"],
                    "source_ref": representative,
                    "source_refs": frames,
                    "node_class": "SCREEN",
                    "classified_by": "GEOMETRY" if board.has_geometry else "DESCENDANT_COUNT",
                    "entry_point": any(f in entry_points for f in frames),
                    "screen_states": qualifiers,
                    "state_kinds": sorted(kinds),
                    "elements": self._elements(screen_id, triggers.get(screen_id, [])),
                    "screen_notes": "",
                }
            )
        return screens

    def _interactions(self, trigger_id: str, owning_screen: str) -> list[dict]:
        """One entry per outgoing connector, naming where it goes.

        A note tether is an annotation, not behaviour, so it produces no
        interaction — its text reaches the element through
        validations_and_edge_cases instead.
        """
        board = self.board
        out: list[dict] = []
        for connector_id, end in self.by_trigger.get(trigger_id, []):
            target, kind = self.resolve(end) if end else (None, None)
            if kind == "NOTE":
                continue

            entry: dict[str, Any] = {"trigger": "onTap", "connector_id": connector_id}
            if end:
                entry["destination_node_id"] = end

            if kind == "SCREEN":
                entry["destination_screen_id"] = target
                if target == owning_screen:
                    # Lands on a different state frame of this same collapsed
                    # screen. Real behaviour, but not navigation — ui_flow counts
                    # it under connectors_intra_screen and emits no edge, so the
                    # wording must not read as a transition between screens.
                    state = board.nodes.get(end, {}).get("name") or end
                    entry["action"] = (
                        f"Changes state within {target} (to frame {state!r}) via "
                        f"connector {connector_id} — same screen, no navigation."
                    )
                else:
                    entry["action"] = f"Navigates to {target} via connector {connector_id}."
            elif kind == "DECISION":
                question = normalise_question((board.texts(target, 1) or [""])[0])
                entry["action"] = (
                    f"Enters decision {question!r} via connector {connector_id}."
                    if question
                    else f"Enters a decision box via connector {connector_id}."
                )
            elif kind == "CAPTION":
                caption = (board.texts(target, 1) or ["(no text)"])[0][:60]
                resolved = self.lane_entry(target)
                screen = self.frame_to_screen.get(resolved) if resolved else None
                # Same self-loop guard the flow layer applies. Without it an
                # interaction advertises a destination that ui_flow refused, and
                # the two halves of the file disagree.
                if screen == owning_screen:
                    screen = None
                if screen:
                    entry["destination_screen_id"] = screen
                    entry["action"] = (
                        f"Points at caption {caption!r} via connector {connector_id} — "
                        f"destination screen {screen} inferred from the lane it fronts."
                    )
                else:
                    entry["action"] = (
                        f"Points at caption {caption!r} via connector {connector_id} — "
                        f"fronts no distinct destination screen, unresolved."
                    )
            else:
                entry["action"] = f"Connector {connector_id} has no resolvable destination."

            out.append(entry)
        return out

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
                    "interactions": self._interactions(node_id, screen_id),
                    "validations_and_edge_cases": [],
                }
            )
        return elements

    # --- notes ---

    def note_text(self, note_id: str) -> str:
        """Body text of a note, minus the component's own heading layer."""
        lines = [
            t for t in self.board.texts(note_id, 12)
            if t.strip().lower() not in NOTE_BOILERPLATE and t.strip()
        ]
        return "\n".join(lines).strip()

    def _centre(self, node_id: str) -> tuple[float, float] | None:
        node = self.board.nodes.get(node_id, {})
        if not all(k in node for k in ("x", "y", "width", "height")):
            return None
        return (node["x"] + node["width"] / 2, node["y"] + node["height"] / 2)

    def _screen_by_position(self, note_id: str) -> str | None:
        """Containment first, then nearest centre WITHIN THE SAME PARENT.

        The parent restriction matters: without it a stray note attaches to
        whichever screen happens to be closest across a whole SECTION, which is
        an attachment nobody drew and nobody can verify.
        """
        board = self.board
        top = note_id
        while board.parent.get(top) and board.nodes[board.parent[top]]["type"] not in STRUCTURAL_TYPES:
            top = board.parent[top]
        parent_id = board.parent.get(top)
        centre = self._centre(top)
        if not parent_id or not centre:
            return None

        siblings = [
            c for c in board.nodes[parent_id].get("children", []) if c["id"] in self.frame_to_screen
        ]
        for sib in siblings:
            if all(k in sib for k in ("x", "y", "width", "height")):
                if (
                    sib["x"] <= centre[0] <= sib["x"] + sib["width"]
                    and sib["y"] <= centre[1] <= sib["y"] + sib["height"]
                ):
                    return self.frame_to_screen[sib["id"]]

        best, best_distance = None, None
        for sib in siblings:
            sib_centre = self._centre(sib["id"])
            if not sib_centre:
                continue
            distance = (sib_centre[0] - centre[0]) ** 2 + (sib_centre[1] - centre[1]) ** 2
            if best_distance is None or distance < best_distance:
                best, best_distance = self.frame_to_screen[sib["id"]], distance
        return best

    def attach_notes(self, screens: list[dict]) -> list[str]:
        """Route every note's text to the screen or element it describes.

        Returns the ids of notes that could not be attached. Reads self.note_links
        only — connectors already bucketed as flows are never revisited, so
        convention_compliance is unaffected by anything here.
        """
        board = self.board
        by_screen: dict[str, list[tuple[float, float, str]]] = defaultdict(list)
        element_by_source = {
            el["source_ref"]: el for screen in screens for el in screen["elements"]
        }
        handled: set[str] = set()
        unattached: list[str] = []

        all_notes = [i for i, cls in board.node_class.items() if cls == "NOTE"]
        linked = {note_id: (other, kind) for note_id, other, kind in self.note_links}

        for note_id in all_notes:
            text = self.note_text(note_id)
            if not text:
                handled.add(note_id)
                continue

            target_screen = None
            other, kind = linked.get(note_id, (None, None))

            # An element-targeted note goes to validations_and_edge_cases — the
            # one intent field with a real downstream consumer.
            if other is not None:
                element = next(
                    (element_by_source[a] for a in board.ancestors(other) if a in element_by_source),
                    None,
                )
                if element is not None:
                    element["validations_and_edge_cases"].append(text)
                    self.counts["notes_attached_by_connector"] += 1
                    handled.add(note_id)
                    continue
                if kind == "SCREEN":
                    target_screen, _ = self.resolve(other)

            if target_screen:
                self.counts["notes_attached_by_connector"] += 1
            else:
                target_screen = self._screen_by_position(note_id)
                if target_screen:
                    self.counts["notes_attached_by_geometry"] += 1

            if not target_screen:
                self.counts["notes_unattached"] += 1
                unattached.append(note_id)
                continue

            node = board.nodes[note_id]
            by_screen[target_screen].append((node.get("y", 0), node.get("x", 0), text))
            handled.add(note_id)

        for screen in screens:
            entries = by_screen.get(screen["screen_id"])
            if entries:
                entries.sort(key=lambda e: (e[0], e[1]))
                screen["screen_notes"] = "\n\n".join(text for _, _, text in entries)

        self.counts["notes_total"] = len(all_notes)
        return unattached

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

    unattached_notes = extractor.attach_notes(screens)
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

    # One entry, not one per note: an orphan note is information for the
    # designer, never a blocker, and a board with no notes produces nothing.
    gaps: list[dict[str, str]] = []
    if unattached_notes:
        gaps.append(
            {
                "field": "screens[].screen_notes",
                "severity": "INFO",
                "reason": (
                    f"{len(unattached_notes)} note(s) sit outside every screen and have no "
                    f"connector, so the screen they describe could not be determined: "
                    f"{', '.join(sorted(unattached_notes)[:10])}."
                ),
                "action": (
                    "Draw a connector from each note to the frame it describes (standard #5), "
                    "or move it inside that frame."
                ),
            }
        )

    # Gaps the script can PROVE from its own counters. Deriving them here is the
    # point: a model asked to judge whether an empty field is a gap invented a
    # BLOCKING one for a field nothing reads. These are mechanical and true.
    counts = extractor.counts
    if counts["connectors_unresolvable"]:
        gaps.append(
            {
                "field": "ui_flow",
                "severity": "BLOCKING",
                "reason": (
                    f"{counts['connectors_unresolvable']} of {counts['connectors_total']} connectors "
                    f"end on a caption, a label strip or a node with no board ancestor, so no "
                    f"destination screen could be resolved. See project_context.blocking_issues for "
                    f"the specific connectors."
                ),
                "action": (
                    "Redraw those connectors so they terminate on the destination FRAME rather than "
                    "on its label (standard #1)."
                ),
            }
        )
    if counts["non_descriptive_names"]:
        gaps.append(
            {
                "field": "screens[].screen_id",
                "severity": "DEGRADED",
                "reason": (
                    f"{counts['non_descriptive_names']} screen(s) derive from default Figma frame "
                    f"names such as 'Frame', so their screen_id carries no meaning and is unstable."
                ),
                "action": "Rename those frames to describe the screen (standard #3).",
            }
        )
    if counts["unreachable_screens"]:
        gaps.append(
            {
                "field": "ui_flow",
                "severity": "INFO",
                "reason": (
                    f"{counts['unreachable_screens']} screen(s) are in the design but no connector "
                    f"reaches them — either dead design or a missing connector."
                ),
                "action": "Confirm with design whether each is still in scope.",
            }
        )
    if export.get("export", {}).get("truncatedCount"):
        gaps.append(
            {
                "field": "design_source.truncated_count",
                "severity": "DEGRADED",
                "reason": (
                    f"The depth cap dropped children of "
                    f"{export['export']['truncatedCount']} node(s), so some elements were never "
                    f"exported."
                ),
                "action": "Flatten the reported groups or raise maxDepth and re-export.",
            }
        )

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
        "extraction_status": "INCOMPLETE" if gaps else "OK",
        "extraction_gaps": gaps,
        "visual_analysis_scratchpad": "",
        "project_context": {
            "overall_ambiguity_rating": "MEDIUM",
            "blocking_issues": extractor.blocking_issues,
        },
        "screens": screens,
        "ui_flow": flow,
    }
    if app:
        doc = {"app": app, **doc}

    # Tallies live beside the context, not inside it: they are feedback about how
    # the board was authored, while design_context is consumed for screens,
    # elements and flow. The conservation proof travels with them.
    report = {
        "generated_at": export.get("exportedAt", ""),
        "convention_compliance": {k: int(extractor.counts[k]) for k in COMPLIANCE_KEYS},
        "screen_renames": extractor.screen_renames,
    }
    if app:
        report["app"] = app
    return doc, report, extractor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", help="Figma raw-JSON export from the Export Design Raw JSON plugin")
    parser.add_argument("--app", help="app id stamped onto the output")
    parser.add_argument("--config", help="path to config/<app>.json")
    parser.add_argument("-o", "--output", help="write here instead of stdout")
    parser.add_argument("--report", action="store_true", help="summary on stderr")
    parser.add_argument("--report-out", help="where to write the sidecar (default: <output>.report.json)")
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

    doc, report, extractor = build(export, args.app, config)

    text = json.dumps(doc, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        report_path = args.report_out or re.sub(r"\.json$", "", args.output) + ".report.json"
        report["design_context_file"] = args.output.rsplit("/", 1)[-1]
        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(f"report written to {report_path}", file=sys.stderr)
    else:
        sys.stdout.write(text + "\n")

    if args.report:
        counts = report["convention_compliance"]
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
