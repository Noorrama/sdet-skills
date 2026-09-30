"""extraction_gaps and project_context from manifest."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Tuple


def _group_warnings(warnings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_code: Counter[str] = Counter()
    samples: Dict[str, str] = {}
    for w in warnings:
        code = str(w.get("code") or "UNKNOWN")
        by_code[code] += 1
        if code not in samples:
            samples[code] = str(w.get("message") or "")
    gaps: List[Dict[str, Any]] = []
    for code, count in sorted(by_code.items()):
        severity = "WARN"
        if code == "CONNECTOR_DANGLING":
            severity = "BLOCKING"
        elif code in ("NO_DEFAULT_STATE",):
            severity = "INFO"
        gaps.append(
            {
                "field": f"manifest.warnings.{code}",
                "reason": f'{count} manifest warning(s): {samples.get(code, "")}',
                "action": "Re-export bundle after fixing connectors in the design source.",
                "severity": severity,
            }
        )
    return gaps


def build_extraction_gaps(
    manifest: Dict[str, Any],
    smart_missing_count: int,
    ui_flow_trigger_gaps: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    gaps: List[Dict[str, Any]] = []
    source = manifest.get("source") or {}
    if source.get("scope") == "selection":
        gaps.append(
            {
                "field": "design_source.scope",
                "reason": "manifest.source.scope is selection; flows outside selectionIds are not in the export.",
                "action": "Re-export full page from the design source when flows outside the selection are required.",
                "severity": "WARN",
            }
        )
    gaps.extend(_group_warnings(manifest.get("warnings") or []))
    if smart_missing_count:
        gaps.append(
            {
                "field": "smart.json",
                "reason": f"manifest lists smart.json for {smart_missing_count} state(s) but files are absent on disk.",
                "action": "Regenerate bundle when exporter writes smart.json consistently.",
                "severity": "INFO",
            }
        )
    gaps.extend(ui_flow_trigger_gaps)
    return gaps


def blocking_issues_from_gaps(gaps: List[Dict[str, Any]]) -> List[str]:
    issues: List[str] = []
    for g in gaps:
        if g.get("field", "").endswith("CONNECTOR_DANGLING") or g.get("severity") == "BLOCKING":
            reason = str(g.get("reason") or "")
            if "Connector" in reason or "connector" in reason.lower():
                # pull connector messages from manifest-style reason
                msg = reason.split(": ", 1)[-1] if ": " in reason else reason
                if msg and msg not in issues:
                    issues.append(msg)
    return issues


def ambiguity_rating(manifest: Dict[str, Any], gaps: List[Dict[str, Any]]) -> str:
    codes = {str(w.get("code") or "") for w in (manifest.get("warnings") or [])}
    if "CONNECTOR_DANGLING" in codes or any(g.get("severity") == "BLOCKING" for g in gaps):
        return "MEDIUM"
    if codes & {"LABEL_HEURISTIC_USED", "NON_STANDARD_STATE", "DUPLICATE_STATE_NAME"}:
        return "MEDIUM"
    return "LOW"


def extraction_status(gaps: List[Dict[str, Any]], degraded: bool) -> str:
    if degraded:
        return "DEGRADED"
    if gaps:
        return "INCOMPLETE"
    return "OK"
