#!/usr/bin/env python3
"""
Org-wide compliance gate for sdet-plan-generator deliverables.

Validates JSON plan + TMS CSV + analysis.md against skill rules (feature-agnostic).
Run BEFORE writing/shipping deliverables. Exit 0 = pass, 1 = fail.

Usage:
  python3 validate_sdet_deliverables.py \\
    --prd prd_context.json \\
    --plan <feature>_SDET_plan.json \\
    --csv <feature>_test_cases.csv \\
    --analysis <feature>_analysis.md \\
    [--design design_context.json] \\
    [--rfc rfc_context.json] \\
    [--checklist coverage_checklist.json] \\
    [--schema schemas/sdet_plan.schema.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

# Import checklist builder from same directory
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from build_coverage_checklist import build_checklist, _clickstream_defined  # noqa: E402

TMS_CSV_HEADERS = [
    "Title",
    "State",
    "Priority",
    "Type of Test Case",
    "Automation Status",
    "Preconditions",
    "Steps",
    "Expected Result",
    "Execution Mode",
    "Platform",
    "Country v2",
    "Android Automation Status v2",
    "iOS Automation Status v2",
    "TestType",
    "Existing Case Ref",
]

FORBIDDEN_CSV_HEADERS = {"id", "requirement_ref", "automation_steps", "execution_scope"}

POSITIVE_CATEGORY_MARKERS = (
    "functional/positive",
    "functional",
)

NON_POSITIVE_CATEGORY_MARKERS = (
    "negative",
    "boundary",
    "permission",
    "interruption",
    "migration",
    "offline",
    "telemetry",
    "platform_variance",
    "theming",
    "non_functional",
    "deep_link",
    "feature_flag",
    "local_data",
)

E2E_TITLE_RE = re.compile(r"\b(end-to-end|e2e)\b", re.I)

VERIFY_IN_STEP_RE = re.compile(
    r"^\s*\d*\.?\s*(verify|assert|check|confirm that|ensure that)\b", re.I
)

ANALYSIS_REQUIRED_SECTIONS = [
    r"##\s+Inputs\s+&\s+Open\s+Points",
    r"##\s+Section\s+0\s+[—\-]\s+Selected\s+Test\s+Coverage\s+Categories",
    r"###\s+Coverage\s+Audit",
    r"###\s+Coverage\s+Balance",
    r"##\s+Section\s+1\s+[—\-]\s+Missing\s+Input\s+Context",
    r"##\s+Section\s+2\s+[—\-]\s+Cross-Stage\s+Gap\s+Analysis",
    r"##\s+Section\s+3\s+[—\-]\s+Architectural",
    r"##\s+Section\s+4\s+[—\-]\s+Open\s+Questions",
    r"##\s+Section\s+5\s+[—\-]\s+SDET\s+Readiness",
]

BLOCKED_TELEMETRY_TITLE_RE = re.compile(
    r"\b(clickstream|telemetry|event tracker|analytics event)\b", re.I
)


class ValidationError(Exception):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _errors() -> list[str]:
    return []


def validate_csv_format(csv_path: Path, errors: list[str]) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            errors.append("CSV is empty")
            return []

    header_set = {h.strip() for h in header}
    if header_set & FORBIDDEN_CSV_HEADERS:
        errors.append(
            f"CSV uses internal pipeline columns {sorted(header_set & FORBIDDEN_CSV_HEADERS)}; "
            f"required BrowserStack TMS format with columns: {', '.join(TMS_CSV_HEADERS)}"
        )

    if [h.strip() for h in header] != TMS_CSV_HEADERS:
        missing = set(TMS_CSV_HEADERS) - header_set
        extra = header_set - set(TMS_CSV_HEADERS)
        if missing or extra or [h.strip() for h in header] != TMS_CSV_HEADERS:
            errors.append(
                "CSV header must match TMS template exactly (order and names). "
                f"Expected: {TMS_CSV_HEADERS}. Got: {header}"
            )

    rows: list[dict[str, str]] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            title = (row.get("Title") or "").strip()
            if not title or title.startswith("REVIEW-FIRST") or "open points" in title.lower():
                continue
            rows.append(row)

    for i, row in enumerate(rows, start=1):
        steps = row.get("Steps") or ""
        for line in steps.split("\n"):
            if VERIFY_IN_STEP_RE.search(line.strip()):
                errors.append(
                    f"CSV row {i} ({row.get('Title', '')[:60]}): "
                    "Steps column must not contain Verify/Assert/Check lines — "
                    "move assertions to Expected Result"
                )
                break
        if (row.get("TestType") or "").strip() not in ("", "Story"):
            errors.append(
                f"CSV row {i}: TestType must be 'Story', got {row.get('TestType')!r}"
            )

    return rows


def classify_scenario(scenario: dict[str, Any]) -> str:
    cat = str(scenario.get("coverage_category") or "").lower()
    title = str(scenario.get("csv_title_association") or "").lower()
    source = str(scenario.get("source") or "").lower()

    if source == "fe_baseline":
        return "non_positive"
    if E2E_TITLE_RE.search(title):
        return "positive"
    if any(m in cat for m in POSITIVE_CATEGORY_MARKERS) and not any(
        n in cat for n in ("negative", "boundary", "interruption", "offline")
    ):
        return "positive"
    if any(m in cat for m in NON_POSITIVE_CATEGORY_MARKERS):
        return "non_positive"
    if "positive" in cat:
        return "positive"
    return "non_positive"


def validate_balance(plan: dict[str, Any], analysis_text: str, errors: list[str]) -> None:
    scenarios = plan.get("scenario_list") or []
    pos = non = 0
    for sc in scenarios:
        bucket = classify_scenario(sc)
        if bucket == "positive":
            pos += 1
        else:
            non += 1
    total = pos + non
    if total == 0:
        errors.append("Plan has zero scenarios")
        return
    pct = pos / total
    under_target_ok = bool(
        re.search(
            r"under_target|regenerated_positives|51\.|50\.|≥\s*50|>=\s*50|Action taken.*balanced",
            analysis_text,
            re.I,
        )
        and pct >= 0.45
    )
    if pct < 0.50 and not under_target_ok:
        errors.append(
            f"Coverage balance FAIL: positive_pct={pct:.1%} ({pos} positive, {non} non-positive). "
            "Skill requires ≥50% positive OR documented under_target escape in analysis.md "
            "after a regeneration pass"
        )


def validate_e2e(plan: dict[str, Any], checklist: dict[str, Any], errors: list[str]) -> None:
    min_e2e = checklist.get("summary", {}).get("min_e2e_scenarios", 0)
    if min_e2e <= 0:
        return
    scenarios = plan.get("scenario_list") or []
    e2e_count = sum(
        1
        for sc in scenarios
        if E2E_TITLE_RE.search(str(sc.get("csv_title_association") or ""))
    )
    if e2e_count < min_e2e:
        errors.append(
            f"Missing end-to-end scenario(s): checklist requires min_e2e={min_e2e}, "
            f"found {e2e_count} (title must contain 'End-to-end' or 'E2E')"
        )


def validate_telemetry(plan: dict[str, Any], prd: dict[str, Any], rfc: dict[str, Any], errors: list[str]) -> None:
    if _clickstream_defined(prd, rfc):
        return
    for sc in plan.get("scenario_list") or []:
        cat = str(sc.get("coverage_category") or "").lower()
        title = str(sc.get("csv_title_association") or "")
        if "telemetry" in cat or "clickstream" in cat:
            errors.append(
                f"Forbidden telemetry scenario (no event schema in inputs): {title[:80]}"
            )
        if BLOCKED_TELEMETRY_TITLE_RE.search(title) and "blocked" not in title.lower():
            errors.append(
                f"Forbidden clickstream/telemetry scenario when inputs lack event schema: {title[:80]}"
            )


def validate_legacy_flags(plan: dict[str, Any], errors: list[str]) -> None:
    for sc in plan.get("scenario_list") or []:
        title = str(sc.get("csv_title_association") or "")[:70]
        legacy = sc.get("is_legacy_regression")
        ref = sc.get("existing_case_ref")
        if legacy and not ref:
            errors.append(f"is_legacy_regression=true without existing_case_ref: {title}")
        if ref and legacy is False:
            errors.append(f"existing_case_ref set but is_legacy_regression=false: {title}")


def validate_scenario_floor(
    plan: dict[str, Any], checklist: dict[str, Any], errors: list[str]
) -> None:
    floor = checklist.get("summary", {}).get("min_total_scenarios_floor", 0)
    count = len(plan.get("scenario_list") or [])
    if count < floor:
        errors.append(
            f"Scenario count {count} below checklist floor {floor} "
            "(expand per acceptance criteria / boundaries / flags — not one row per req_id only)"
        )


def validate_steps_in_json(plan: dict[str, Any], errors: list[str]) -> None:
    for sc in plan.get("scenario_list") or []:
        title = str(sc.get("csv_title_association") or "")[:60]
        for step in sc.get("steps") or []:
            if VERIFY_IN_STEP_RE.search(str(step).strip()):
                errors.append(
                    f"JSON steps[] contains verification (belongs in expected_result): {title}"
                )
                break


def validate_analysis(analysis_path: Path, errors: list[str]) -> str:
    text = analysis_path.read_text(encoding="utf-8")
    for pattern in ANALYSIS_REQUIRED_SECTIONS:
        if not re.search(pattern, text, re.I):
            errors.append(f"analysis.md missing required section matching /{pattern}/")
    if "Coverage Audit" not in text:
        errors.append("analysis.md must include a Coverage Audit table (Section 0)")
    if "Coverage Balance" not in text and "Coverage balance" not in text:
        errors.append("analysis.md must include Coverage Balance (Section 0)")
    return text


def validate_json_schema(plan_path: Path, schema_path: Path | None, errors: list[str]) -> None:
    if not schema_path or not schema_path.is_file():
        errors.append(f"WORTH_CHECKING: schema not found at {schema_path} — JSON not schema-validated")
        return
    try:
        import jsonschema
    except ImportError:
        errors.append(
            "WORTH_CHECKING: jsonschema not installed — run: pip3 install jsonschema"
        )
        return
    plan = _load_json(plan_path)
    schema = _load_json(schema_path)
    try:
        jsonschema.validate(plan, schema)
    except jsonschema.ValidationError as e:
        errors.append(f"SDET plan JSON schema validation failed: {e.message}")


def validate_compliance_sidecar(
    plan: dict[str, Any], compliance_path: Path | None, errors: list[str]
) -> None:
    """Optional <feature>_compliance_report.json sidecar (schema-safe audit proof)."""
    if compliance_path is None or not compliance_path.is_file():
        return
    report = _load_json(compliance_path)
    balance = report.get("balance") or {}
    action = str(balance.get("action_taken") or "")
    if not action:
        errors.append("compliance_report.json missing balance.action_taken")


def run_validation(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []

    for label, path in (
        ("--prd", args.prd),
        ("--plan", args.plan),
        ("--csv", args.csv),
        ("--analysis", args.analysis),
    ):
        if not path.is_file():
            errors.append(f"{label} file not found: {path}")
    if errors:
        return errors

    prd = _load_json(args.prd)
    plan = _load_json(args.plan)
    rfc = _load_json(args.rfc) if args.rfc and args.rfc.is_file() else {}
    design = _load_json(args.design) if args.design and args.design.is_file() else {}

    if args.checklist and args.checklist.is_file():
        checklist = _load_json(args.checklist)
    else:
        checklist = build_checklist(prd, design=design, rfc=rfc, plan=plan)

    validate_csv_format(args.csv, errors)
    analysis_text = validate_analysis(args.analysis, errors)
    validate_json_schema(args.plan, args.schema, errors)
    validate_scenario_floor(plan, checklist, errors)
    validate_e2e(plan, checklist, errors)
    validate_balance(plan, analysis_text, errors)
    validate_telemetry(plan, prd, rfc, errors)
    validate_legacy_flags(plan, errors)
    validate_steps_in_json(plan, errors)
    if args.compliance:
        validate_compliance_sidecar(plan, args.compliance, errors)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SDET plan generator deliverables")
    parser.add_argument("--prd", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--design", type=Path)
    parser.add_argument("--rfc", type=Path)
    parser.add_argument("--checklist", type=Path)
    parser.add_argument("--compliance", type=Path, help="Optional compliance_report.json")
    parser.add_argument(
        "--schema",
        type=Path,
        help="sdet_plan.schema.json path (default: sibling ../schemas/ from script)",
    )
    args = parser.parse_args()

    if args.schema is None:
        default_schema = _SCRIPT_DIR.parent / "schemas" / "sdet_plan.schema.json"
        args.schema = default_schema if default_schema.is_file() else None

    errors = run_validation(args)
    if errors:
        print("SDET deliverables validation FAILED:", file=sys.stderr)
        for i, err in enumerate(errors, 1):
            print(f"  {i}. {err}", file=sys.stderr)
        return 1

    print("SDET deliverables validation PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
