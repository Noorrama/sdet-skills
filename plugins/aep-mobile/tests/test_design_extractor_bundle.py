"""Tests for figma-design-bundle design_context extraction."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import pytest
except ImportError:  # pragma: no cover
    pytest = None

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
FIXTURE_BUNDLE = PLUGIN_ROOT / "tests" / "fixtures" / "gofood-bundling-min"
SCHEMA = PLUGIN_ROOT / "schemas" / "design_context.schema.json"

sys.path.insert(0, str(SCRIPTS))
from design_extractor.extract_from_bundle import extract_bundle  # noqa: E402
from design_extractor.screen_ids import manifest_id_to_screen_id  # noqa: E402


def test_manifest_id_to_screen_id():
    assert manifest_id_to_screen_id("Bundling_-_Full_data") == "BUNDLING_FULL_DATA"
    assert manifest_id_to_screen_id("Shared_cart") == "SHARED_CART"


def test_minimal_fixture_extraction():
    ctx = extract_bundle(FIXTURE_BUNDLE, PLUGIN_ROOT, app="gofood-consumer")
    assert ctx["app"] == "gofood-consumer"
    assert ctx["extraction_status"] == "INCOMPLETE"
    assert len(ctx["screens"]) == 2
    landing = next(s for s in ctx["screens"] if s["screen_id"] == "LANDING")
    labels = {e["label"] for e in landing["elements"]}
    assert "Create & invite friends" in labels
    assert "Everyone pays for their items" in labels
    assert "Everyone pays an equal share" in labels
    assert "You pay for everyone" in labels
    toggle_refs = {e["source_ref"] for e in landing["elements"] if e["role"] == "TOGGLE"}
    assert len(toggle_refs) == 3

    entry_edge = next((e for e in ctx["ui_flow"] if e.get("from_screen_id") == "ENTRY"), None)
    assert entry_edge is not None
    assert ctx["ui_flow"][0]["from_screen_id"] == "ENTRY"
    assert entry_edge["to_screen_id"] == "MPS"
    mps = next(s for s in ctx["screens"] if s["screen_id"] == "MPS")
    assert mps.get("entry_point") is True

    triggers = sum(1 for e in ctx["ui_flow"] if e.get("trigger_element_id"))
    assert triggers >= 1
    mps_to_landing = next(
        e for e in ctx["ui_flow"] if e["from_screen_id"] == "MPS" and e["to_screen_id"] == "LANDING"
    )
    assert mps_to_landing.get("trigger_element_id")


def test_validate_design_context_minimal(tmp_path):
    out = tmp_path / "design_context.json"
    ctx = extract_bundle(FIXTURE_BUNDLE, PLUGIN_ROOT, app="gofood-consumer")
    out.write_text(json.dumps(ctx, indent=2), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "validate_design_context.py"),
            str(out),
            "--schema",
            str(SCHEMA),
        ],
        capture_output=True,
        text=True,
        cwd=str(PLUGIN_ROOT),
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_full_trial_bundle_extraction():
    if not os.environ.get("AEP_TRIAL_BUNDLE"):
        if pytest:
            pytest.skip("Set AEP_TRIAL_BUNDLE to full trial export root")
        return
    bundle = Path(os.environ["AEP_TRIAL_BUNDLE"])
    ctx = extract_bundle(bundle, PLUGIN_ROOT, app="gofood-consumer")
    assert len(ctx["screens"]) == 8
    entry_edges = [e for e in ctx["ui_flow"] if e.get("from_screen_id") == "ENTRY"]
    assert entry_edges, "expected at least one ENTRY ui_flow edge"
    mps = next(s for s in ctx["screens"] if s["screen_id"] == "MPS")
    assert mps.get("entry_point") is True

    def trigger_label(connector_id: str) -> str:
        edge = next(e for e in ctx["ui_flow"] if e.get("source_ref") == connector_id)
        trig = edge.get("trigger_element_id")
        scr = next(s for s in ctx["screens"] if s["screen_id"] == edge["from_screen_id"])
        el = next(e for e in scr["elements"] if e["element_id"] == trig)
        return str(el.get("label") or "")

    assert "checkout" in trigger_label("14107:120764").lower()
    assert "edit" in trigger_label("14107:120070").lower()
    assert "plus" in trigger_label("15959:86946").lower()

    total_elements = sum(len(s.get("elements") or []) for s in ctx["screens"])
    assert total_elements < 800

    triggers = sum(1 for e in ctx["ui_flow"] if e.get("trigger_element_id"))
    assert triggers >= 12

    entry_label_edges = [e for e in ctx["ui_flow"] if e.get("edge_source") == "ENTRY_LABEL"]
    assert entry_label_edges, "trial bundle expects ENTRY_LABEL edge (MPS entry point label)"

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "design_context.json"
        out.write_text(json.dumps(ctx, indent=2), encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "validate_design_context.py"),
                str(out),
                "--schema",
                str(SCHEMA),
                "--fixture",
                "gofood-group-order-bundling",
            ],
            capture_output=True,
            text=True,
            cwd=str(PLUGIN_ROOT),
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
