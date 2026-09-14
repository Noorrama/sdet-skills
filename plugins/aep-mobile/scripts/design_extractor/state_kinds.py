"""Map manifest state names to state_kinds enum."""
from __future__ import annotations

from typing import Any, Dict, List

VOCABULARY_TO_KIND = {
    "default": "DEFAULT",
    "loading": "LOADING",
    "empty": "EMPTY",
    "error": "ERROR",
    "success": "SUCCESS",
    "partial": "OTHER",
    "disabled": "DISABLED",
    "offline": "OFFLINE",
    "skeleton": "LOADING",
}


def state_name_to_kind(name: str, vocabulary: List[str]) -> str:
    lower = name.strip().lower()
    if lower == "loading":
        return "LOADING"
    for token in vocabulary:
        if token.lower() == lower or lower.startswith(token.lower()):
            mapped = VOCABULARY_TO_KIND.get(token.lower())
            if mapped:
                return mapped
    for key, kind in VOCABULARY_TO_KIND.items():
        if key in lower:
            return kind
    return "OTHER"


def state_kinds_for_screen(
    state_names: List[str],
    conventions: Dict[str, Any],
) -> List[str]:
    vocab = conventions.get("stateVocabulary") or []
    if isinstance(vocab, dict):
        vocab = list(vocab.keys())
    return [state_name_to_kind(n, list(vocab)) for n in state_names]
