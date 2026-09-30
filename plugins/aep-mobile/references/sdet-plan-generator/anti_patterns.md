# SDET Plan Generator — Anti-Patterns (org-wide)

These outputs violate `SKILL.md` regardless of feature, app, or model. The compliance
validator (`scripts/validate_sdet_deliverables.py`) rejects them mechanically.

## FORBIDDEN — CSV format

| Anti-pattern | Why |
|---|---|
| Columns `id`, `requirement_ref`, `automation_steps`, `execution_scope` | Internal pipeline format, not BrowserStack TMS |
| Rows titled `SDET-001: …` as the primary Title column | SDET ids belong in JSON metadata; CSV Title is human-readable scenario name |
| `Verify …` / `Assert …` lines in the **Steps** column | Actions and assertions must be split (Steps vs Expected Result) |
| `TestType` other than `Story` | Squad template requires literal `Story` |

**Correct:** Copy `templates/test_cases.csv` header verbatim; fill rows from `scenario_list`.

## FORBIDDEN — Scenario set shape

| Anti-pattern | Why |
|---|---|
| Exactly one scenario per `req_id` when PRD has multiple acceptance criteria that need **different paths** | Hard Coverage Rule: alternate paths still need coverage |
| One physical row per acceptance criterion when criteria share the **same flow** and only assert different elements | Scenario Economy — combine into one Happy Path with multi-line Expected Result |
| Zero **End-to-end** / **E2E** scenarios when design `ui_flow` or multi-screen PRD exists | Hard Coverage Rule: business flows first |
| Near-duplicate Android + iOS rows that differ only by OS in the title | Platform belongs in the Platform column; default Cross-Platform |
| `Android` / `iOS` tokens inside `csv_title_association` / CSV Title | Title is behaviour-only; OS is Platform column |
| `positive_pct < 50%` without documented `under_target` escape after regeneration | Step 4c-mix balance gate |
| Clickstream/telemetry scenarios when inputs have **no** event names/schema | Telemetry Rules — open question only |
| iOS/dark-mode **placeholder scenarios** when OQ blocks expected behavior | Report blocked in Section 4; do not invent tests |
| Mobile scenario for admin-only / backend-only requirements (Frontend Focus) | Out of FE scope — block in analysis |
| Raw JSON objects/arrays in CSV Preconditions | Tester-facing column must be numbered plain language |
| `test_case_type` missing or not in the Happy Path / Negative / Boundary / … taxonomy | CSV Type of Test Case carries categorisation |
## FORBIDDEN — JSON / steps

| Anti-pattern | Why |
|---|---|
| `is_legacy_regression: true` without `existing_case_ref` | Regression dedup must be auditable |
| `existing_case_ref` with `is_legacy_regression: false` | Contradictory legacy marking |
| Collapsing JSON `expected_result` numbered lines into one CSV Expected Result paragraph | CSV Expected Result must be a verbatim copy of `scenario.expected_result` — same line count, same `\n` breaks |
| CSV Expected Result line count < JSON `expected_result` line count | Summarization defect — compliance validator fails |
| Verification lines inside JSON `steps[]` | Belongs in `expected_result` |
| Invented deeplinks, flags, event names, API paths | Provenance rule |

## FORBIDDEN — SYNC / BrowserStack upload

| Anti-pattern | Why |
|---|---|
| Uploading rows with `is_legacy_regression: true` | Legacy cases already exist in BrowserStack from regression-extractor — re-upload creates duplicates |
| Excluding Manual rows from BrowserStack upload when `is_legacy_regression: false` | Manual non-legacy cases still belong in TMS; only the automation plan excludes them |
| Including Manual rows in `<feature_key>_automation_plan_generator.json` | Automation plan is Automatable-only |
| Overwriting `existing_case_ref` with a newly uploaded `TC-*` id on a legacy scenario | The regression case owns that TMS entry |

## FORBIDDEN — analysis.md

| Anti-pattern | Why |
|---|---|
| Missing Section 0 Coverage Audit / Coverage Balance tables | Mechanical coverage proof for reviewers |
| Cross-stage gaps only in JSON, not Section 2 tables | Human-readable QA asset |
| Abbreviated Section 5 (no env / test data / device matrix) | Gold-standard layout |

## REQUIRED before shipping deliverables

```bash
python3 scripts/build_coverage_checklist.py --prd prd_context.json [--design ...] [--rfc ...] --out coverage_checklist.json

python3 scripts/validate_sdet_deliverables.py \
  --prd prd_context.json \
  --plan <feature_key>_SDET_plan.json \
  --csv <feature_key>_test_cases.csv \
  --analysis <feature_key>_analysis.md \
  [--design design_context.json] \
  [--rfc rfc_context.json] \
  [--task task_context.json] \
  [--checklist coverage_checklist.json] \
  [--compliance <feature_key>_compliance_report.json]
```

Exit code **must be 0** before writing or importing deliverables.
