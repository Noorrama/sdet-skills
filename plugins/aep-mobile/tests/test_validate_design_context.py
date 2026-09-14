"""Tests for validate_design_context.py extraction_status consistency."""
from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from validate_design_context import validate_extraction_status  # noqa: E402


def _minimal_doc(**overrides):
    base = {
        "extraction_status": "INCOMPLETE",
        "extraction_gaps": [],
        "visual_analysis_scratchpad": "stub",
        "project_context": {
            "overall_ambiguity_rating": "HIGH",
            "blocking_issues": [],
        },
        "screens": [],
        "ui_flow": [],
    }
    base.update(overrides)
    return base


def test_incomplete_with_gaps_no_status_warnings():
    doc = _minimal_doc(
        extraction_gaps=[
            {"field": "input", "reason": "no bundle", "severity": "BLOCKING"},
        ],
    )
    errors, warnings = validate_extraction_status(doc, strict=False)
    assert not errors
    assert not warnings


def test_ok_with_gaps_warns_by_default():
    doc = _minimal_doc(
        extraction_status="OK",
        extraction_gaps=[
            {"field": "manifest.warnings.X", "reason": "x", "severity": "WARN"},
        ],
        screens=[{"screen_id": "A", "screen_name": "A", "elements": [], "screen_states": []}],
    )
    errors, warnings = validate_extraction_status(doc, strict=False)
    assert not errors
    assert any("extraction_gaps" in w for w in warnings)


def test_ok_with_gaps_strict_is_error():
    doc = _minimal_doc(
        extraction_status="OK",
        extraction_gaps=[
            {"field": "input", "reason": "x", "severity": "BLOCKING"},
        ],
    )
    errors, warnings = validate_extraction_status(doc, strict=True)
    assert warnings == []
    assert len(errors) >= 2  # non-empty gaps + BLOCKING


def test_url_only_stub_schema_shape_passes_status_check():
    doc = _minimal_doc(
        extraction_status="INCOMPLETE",
        extraction_gaps=[
            {
                "field": "input",
                "reason": "Figma URL only: https://www.figma.com/design/abc/file?node-id=1-2",
                "action": "Export figma-design-bundle to disk and re-run.",
                "severity": "BLOCKING",
            },
        ],
        project_context={
            "overall_ambiguity_rating": "HIGH",
            "blocking_issues": ["No bundle on disk"],
        },
    )
    errors, warnings = validate_extraction_status(doc, strict=False)
    assert not errors
    assert not warnings


def test_ok_empty_screens_warns():
    doc = _minimal_doc(extraction_status="OK")
    errors, warnings = validate_extraction_status(doc, strict=False)
    assert not errors
    assert any("screens[]" in w for w in warnings)
