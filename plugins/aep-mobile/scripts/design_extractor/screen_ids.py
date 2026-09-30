"""Manifest screen id → design_context screen_id."""
from __future__ import annotations

import re


def manifest_id_to_screen_id(manifest_id: str) -> str:
    s = manifest_id.replace("-", "_")
    s = re.sub(r"_+", "_", s)
    return s.upper().strip("_")
