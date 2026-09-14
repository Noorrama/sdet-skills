"""Unit tests for ENTRY edge topology (no Figma bundle on disk)."""
from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from design_extractor.entry_points import build_entry_edges  # noqa: E402


def _screen(manifest_id: str, node_id: str, *, default_state_id: str | None = None) -> dict:
    state = {"id": node_id, "nodeId": node_id, "isDefault": default_state_id == node_id}
    return {
        "id": manifest_id,
        "defaultStateId": default_state_id or node_id,
        "states": [state],
    }


def test_topology_bfs_picks_widest_reach_not_mps():
    """Among zero in-degree screens, pick max forward BFS reach (no MPS special case)."""
    manifest = {
        "screens": [
            _screen("home_manifest", "n-home"),
            _screen("detail_manifest", "n-detail"),
            _screen("extra_manifest", "n-extra"),
            _screen("leaf_manifest", "n-leaf"),
        ],
    }
    sid_map = {
        "home_manifest": "HOME",
        "detail_manifest": "DETAIL",
        "extra_manifest": "EXTRA",
        "leaf_manifest": "LEAF",
    }
    in_degree = {"HOME": 0, "LEAF": 0, "DETAIL": 1, "EXTRA": 2}
    connector_ui_flow = [
        {
            "from_screen_id": "HOME",
            "to_screen_id": "DETAIL",
            "navigation_kind": "CONNECTOR",
        },
        {
            "from_screen_id": "DETAIL",
            "to_screen_id": "EXTRA",
            "navigation_kind": "CONNECTOR",
        },
        {
            "from_screen_id": "LEAF",
            "to_screen_id": "EXTRA",
            "navigation_kind": "CONNECTOR",
        },
    ]
    entry_edges, entry_targets, _gaps = build_entry_edges(
        manifest, sid_map, in_degree, connector_ui_flow
    )
    assert len(entry_edges) == 1
    assert entry_edges[0]["to_screen_id"] == "HOME"
    assert entry_edges[0]["edge_source"] == "ENTRY_TOPOLOGY"
    assert entry_targets == {"HOME"}


def test_closed_graph_default_state_without_mps():
    """Closed graph (all in-degree > 0): default-state screen, manifest has no MPS id."""
    manifest = {
        "screens": [
            _screen("alpha_manifest", "n-alpha", default_state_id="n-alpha"),
            _screen("beta_manifest", "n-beta", default_state_id="n-beta"),
        ],
    }
    sid_map = {"alpha_manifest": "ALPHA", "beta_manifest": "BETA"}
    in_degree = {"ALPHA": 1, "BETA": 1}
    connector_ui_flow = [
        {
            "from_screen_id": "ALPHA",
            "to_screen_id": "BETA",
            "navigation_kind": "CONNECTOR",
        },
        {
            "from_screen_id": "BETA",
            "to_screen_id": "ALPHA",
            "navigation_kind": "CONNECTOR",
        },
    ]
    entry_edges, entry_targets, gaps = build_entry_edges(
        manifest, sid_map, in_degree, connector_ui_flow
    )
    assert len(entry_edges) == 1
    assert entry_edges[0]["to_screen_id"] == "ALPHA"
    assert entry_targets == {"ALPHA"}
    assert any(g.get("severity") == "INFO" for g in gaps)
