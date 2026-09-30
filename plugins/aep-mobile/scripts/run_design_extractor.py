#!/usr/bin/env python3
"""Thin CLI wrapper around design_extractor package."""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from design_extractor.extract_from_bundle import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
