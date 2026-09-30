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
    [--task task_context.json] \\
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

PLATFORM_IN_TITLE_RE = re.compile(
    r"(?i)(?<![a-z])(android|ios)(?![a-z])|\(\s*(android|ios)\s*\)|android\s+vs\s+ios"
)

ALLOWED_TEST_CASE_TYPES = {
    "Happy Path",
    "Negative",
    "Boundary",
    "Interruption",
    "Permission",
    "Feature Flag",
    "Navigation",
    "Accessibility",
    "Localization",
    "Performance",
    "Platform Variance",
    "Sanity",
    "Regression",
}

# Soft legacy aliases still accepted (map toward taxonomy over time)
LEGACY_TEST_CASE_TYPES = {"Functional", "Smoke", "Story"}

JSONISH_PRECONDITION_RE = re.compile(
    r"(\[\s*\{)|(\{\s*[\"']entity[\"'])|(\"required_state\")"
)

VERIFY_IN_STEP_RE = re.compile(
    r"^\s*\d*\.?\s*(verify|assert|check|confirm that|ensure that)\b", re.I
)

NUMBERED_LINE_RE = re.compile(r"^\s*\d+\.\s*", re.M)

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
    """Every checklist item must be covered via requirement_ref.

    Scenario *count* may be lower than checklist length when same-flow cases
    are combined (multi-id requirement_ref). A hard row-count floor caused
    exhaustive suites for small features.
    """
    items = checklist.get("checklist") or []
    if not items:
        return
    refs_blob = " , ".join(
        str(sc.get("requirement_ref") or "") for sc in plan.get("scenario_list") or []
    )
    missing: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        req_id = str(item.get("req_id") or "").strip()
        if not item_id:
            continue
        # Prefer exact checklist id (e.g. BR-1:ac[0] or BR-1:boundary_conditions[2])
        covered = item_id in refs_blob
        if not covered and req_id and item.get("type") in ("requirement", "acceptance_criterion"):
            # Combined rows may only list the parent req_id
            covered = re.search(
                rf"(?<![\w-]){re.escape(req_id)}(?![\w-])", refs_blob
            ) is not None
        if not covered:
            missing.append(item_id)
    if missing:
        preview = ", ".join(missing[:8])
        more = f" (+{len(missing) - 8} more)" if len(missing) > 8 else ""
        errors.append(
            f"Checklist coverage gaps ({len(missing)}): {preview}{more}. "
            "Every checklist item needs a scenario whose requirement_ref names it "
            "(combine same-flow items into one row with multi-id requirement_ref; "
            "do not leave items uncovered)."
        )


def validate_titles_platform_category(
    plan: dict[str, Any], csv_rows: list[dict[str, str]], errors: list[str]
) -> None:
    """Platform stays in Platform column; Type of Test Case carries category."""
    titles_norm: dict[str, list[str]] = {}
    for sc in plan.get("scenario_list") or []:
        title = str(sc.get("csv_title_association") or "").strip()
        short = title[:70]
        if PLATFORM_IN_TITLE_RE.search(title):
            errors.append(
                f"Title must not include Android/iOS platform tokens (use Platform column): {short}"
            )
        tct = str(sc.get("test_case_type") or "").strip()
        if not tct:
            errors.append(f"Missing test_case_type (Happy Path / Negative / Boundary / …): {short}")
        elif tct not in ALLOWED_TEST_CASE_TYPES and tct not in LEGACY_TEST_CASE_TYPES:
            errors.append(
                f"Unknown test_case_type '{tct}' on '{short}'. "
                f"Use one of: {', '.join(sorted(ALLOWED_TEST_CASE_TYPES))}"
            )
        plat = str(sc.get("platform") or "").strip().lower()
        # Detect near-duplicate Android/iOS pairs (same title after stripping OS tokens)
        norm = PLATFORM_IN_TITLE_RE.sub("", title)
        norm = re.sub(r"\s+", " ", norm).strip().lower()
        if norm:
            titles_norm.setdefault(norm, []).append(plat or "cross-platform")

    for norm, plats in titles_norm.items():
        has_android = any("android" in p and "ios" not in p and "cross" not in p for p in plats)
        has_ios = any("ios" in p and "android" not in p and "cross" not in p for p in plats)
        if has_android and has_ios and len(plats) >= 2:
            errors.append(
                f"Duplicate Android/iOS scenarios for the same behaviour '{norm[:60]}' — "
                "use one Cross-Platform row unless the path/outcome truly differs; "
                "never split only to put OS in the title"
            )

    for i, row in enumerate(csv_rows, start=1):
        title = (row.get("Title") or "").strip()
        if not title or "open points" in title.lower():
            continue
        if PLATFORM_IN_TITLE_RE.search(title):
            errors.append(
                f"CSV row {i}: Title contains Android/iOS — move OS to Platform column only"
            )
        pre = row.get("Preconditions") or ""
        if JSONISH_PRECONDITION_RE.search(pre):
            errors.append(
                f"CSV row {i}: Preconditions looks like raw JSON — use numbered plain language"
            )
        tct = (row.get("Type of Test Case") or "").strip()
        if tct and tct not in ALLOWED_TEST_CASE_TYPES and tct not in LEGACY_TEST_CASE_TYPES:
            errors.append(
                f"CSV row {i}: Type of Test Case '{tct}' is not in the category taxonomy"
            )


def _count_numbered_lines(text: str) -> int:
    """Count lines that start with 'N. ' (numbered assertion/action lines)."""
    if not text:
        return 0
    return sum(1 for line in text.split("\n") if NUMBERED_LINE_RE.match(line))


def validate_csv_json_parity(
    plan: dict[str, Any], csv_rows: list[dict[str, str]], errors: list[str]
) -> None:
    """CSV Steps / Expected Result must mirror JSON steps[] / expected_result (no summarization)."""
    by_title = {
        str(sc.get("csv_title_association") or "").strip(): sc
        for sc in plan.get("scenario_list") or []
    }
    for i, row in enumerate(csv_rows, start=1):
        title = (row.get("Title") or "").strip()
        if not title:
            continue
        sc = by_title.get(title)
        if not sc:
            continue
        short = title[:55]

        json_steps = sc.get("steps") or []
        csv_step_lines = _count_numbered_lines(row.get("Steps") or "")
        json_step_count = len(json_steps)
        if json_step_count > 0 and csv_step_lines != json_step_count:
            errors.append(
                f"CSV row {i} ({short}): Steps has {csv_step_lines} numbered line(s) "
                f"but JSON steps[] has {json_step_count} — copy each steps[] entry as its own "
                "numbered CSV line"
            )

        json_er = str(sc.get("expected_result") or "")
        csv_er = row.get("Expected Result") or ""
        json_er_n = _count_numbered_lines(json_er)
        csv_er_n = _count_numbered_lines(csv_er)
        if json_er_n > 0 and csv_er_n < json_er_n:
            errors.append(
                f"CSV row {i} ({short}): Expected Result has {csv_er_n} numbered line(s) "
                f"but JSON expected_result has {json_er_n} — do not collapse or summarize; "
                "copy scenario.expected_result verbatim to CSV Expected Result"
            )
        elif json_er_n > 0 and csv_er_n > json_er_n:
            errors.append(
                f"CSV row {i} ({short}): Expected Result has {csv_er_n} numbered lines "
                f"but JSON expected_result has {json_er_n} — keep CSV in sync with JSON"
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


_OUT_OF_SCOPE_RE = re.compile(
    r"out[\s-]?of[\s-]?scope|blocked|deferred|not\s+covered|"
    r"backend[\s-]?only|admin[\s-]?only|different\s+milestone|fast[\s-]?follow",
    re.IGNORECASE,
)


def _prd_req_ids(prd: dict[str, Any]) -> list[str]:
    ids = []
    for b in prd.get("business_requirements") or []:
        rid = b.get("req_id")
        if rid and rid not in ids:
            ids.append(rid)
    return ids


def _task_context_req_ids(task_ctx: dict[str, Any]) -> set[str]:
    """Every PRD requirement id the task tree claims to satisfy."""
    ids: set[str] = set()
    for epic in task_ctx.get("epics") or []:
        for story in epic.get("user_stories") or []:
            rid = story.get("requirement_id")
            if rid:
                ids.add(rid)
    for row in task_ctx.get("traceability") or []:
        rid = row.get("requirement_id")
        if rid:
            ids.add(rid)
    return ids


def _excused_in_analysis(req_id: str, analysis_text: str) -> bool:
    """A gap is auditable-excused only if analysis.md names the req_id on a
    line that also states it is out of scope / blocked / deferred."""
    for line in analysis_text.splitlines():
        if req_id in line and _OUT_OF_SCOPE_RE.search(line):
            return True
    return False


def validate_requirement_traceability(
    prd: dict[str, Any],
    plan: dict[str, Any],
    task_ctx: dict[str, Any],
    analysis_text: str,
    errors: list[str],
) -> None:
    """PRD is the source of truth for the coverage floor. Every PRD req_id must
    (a) be picked up by a story in task_context and (b) be covered by >=1 scenario
    in the SDET plan. An uncovered req_id is excused only when analysis.md documents
    it as out-of-scope/blocked/deferred.

    Opt-in and fully backward-compatible: this whole gate runs ONLY when a
    task_context is supplied (--task). With no task_context, behaviour is
    unchanged from before this check existed."""
    if not task_ctx:
        return
    prd_ids = _prd_req_ids(prd)
    if not prd_ids:
        return  # nothing to trace against

    # (a) PRD -> task_context
    task_ids = _task_context_req_ids(task_ctx)
    for rid in prd_ids:
        if rid not in task_ids and not _excused_in_analysis(rid, analysis_text):
            errors.append(
                f"Requirement traceability: PRD req_id '{rid}' has no user story "
                f"in task_context (task generation did not cover it). Add a story "
                f"with requirement_id '{rid}', or document it as out-of-scope in analysis.md."
            )

    # (b) PRD -> sdet_plan scenarios
    refs = " , ".join(
        str(sc.get("requirement_ref") or "") for sc in plan.get("scenario_list") or []
    )
    for rid in prd_ids:
        covered = re.search(rf"(?<![\w-]){re.escape(rid)}(?![\w-])", refs) is not None
        if not covered and not _excused_in_analysis(rid, analysis_text):
            errors.append(
                f"Requirement coverage: PRD req_id '{rid}' is not referenced by any scenario's "
                f"requirement_ref in the SDET plan. Add >=1 scenario for it, or document it as "
                f"out-of-scope/blocked in analysis.md."
            )


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
    task_ctx = _load_json(args.task) if args.task and args.task.is_file() else {}

    if args.checklist and args.checklist.is_file():
        checklist = _load_json(args.checklist)
    else:
        checklist = build_checklist(prd, design=design, rfc=rfc, plan=plan)

    csv_rows = validate_csv_format(args.csv, errors)
    analysis_text = validate_analysis(args.analysis, errors)
    validate_json_schema(args.plan, args.schema, errors)
    validate_scenario_floor(plan, checklist, errors)
    validate_titles_platform_category(plan, csv_rows, errors)
    validate_requirement_traceability(prd, plan, task_ctx, analysis_text, errors)
    validate_e2e(plan, checklist, errors)
    validate_balance(plan, analysis_text, errors)
    validate_telemetry(plan, prd, rfc, errors)
    validate_legacy_flags(plan, errors)
    validate_steps_in_json(plan, errors)
    validate_csv_json_parity(plan, csv_rows, errors)
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
    parser.add_argument("--task", type=Path, help="task_context.json (PRIMARY DRIVER) — enables PRD→task_context→plan requirement traceability")
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
