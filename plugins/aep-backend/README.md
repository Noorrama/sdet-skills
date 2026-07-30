# Backend QA Skills — Agentic PDLC

A production skill set for the **backend / API** QA track across GoTo services.
Covers the full agentic PDLC pipeline: pre-build scenario planning, post-build code generation, and upstream doc re-trigger.

## Folder layout
```
aep-backend/
  README.md                        ← this guide
  schemas/                         ← JSON Schema validators for every context/output
    prd_context · rfc_context · tasks_context · regression_context
    code_change_context · doc_change_context
    sdet_plan · automation_plan · test_data_requests · validation_report
  skills/                          ← 12 SKILL.md files
    prd-extractor · rfc-extractor · tasks-extractor · regression-extractor
    code-change-extractor · doc-delta-extractor
    sdet-plan-generator · dedup-generator · automation-plan-generator
    test-data-generator · test-code-generator · test-code-validator
  examples/                        ← worked examples per feature
```

## Pipeline & run order

```
PRE-BUILD (parallel with dev implementation)
  prd-extractor          → prd_context.json        (product intent)
  rfc-extractor          → rfc_context.json         (design intent + validation sequence)
  tasks-extractor        → tasks_context.json       ★ AUTHORITATIVE on API contracts
  regression-extractor   → regression_context.json  (existing coverage)
        │
        ▼
  sdet-plan-generator [Pass 1]
        → <feature>_sdet_plan.json + <feature>_qa_analysis.md + <feature>_testcases.csv
        │
  dedup-generator [scenario mode] → flags duplicate scenarios
        │
   ── HUMAN REVIEW GATE (SDET + PM) ──
        │  approved → BrowserStack upload
        │  gaps found → regenerate (vN+1) → re-review
        ▼

  [RE-TRIGGER — if PRD/RFC/Tasks doc changes mid-sprint]
  doc-delta-extractor → doc_change_context.json
        │  Human Feedback gate (SDET + PM confirm scope)
        ▼
  sdet-plan-generator [re-trigger] → patch affected scenarios only → delta review

POST-BUILD (Epic reaches QA Ready)
  code-change-extractor  → code_change_context.json (GitLab unified diff + CR notes)
        ▼
  sdet-plan-generator [Pass 2] → delta scenarios from CR signals
        │
  dedup-generator [scenario mode]
        │
   ── HUMAN REVIEW GATE (SDET — delta only) ──
        │  approved → BrowserStack upload
        ▼

  CODE GENERATION
  automation-plan-generator → automation_plan.json (class · package · fixtures · curl_reference)
        │
   ── HUMAN REVIEW GATE (SDET — automation plan) ──
        │
        ├──────────────────────────────────────┐
        ▼                                      ▼
  test-data-generator              dedup-generator [method mode]
  → test_data_requests.json               ↓
    (TDP / TestBuddy)           test-code-generator
                                → GBT Java + TapMind NLP steps
                                        ↓
                                test-code-validator
                                → validation_report.json
                                        │
                                 ── HUMAN REVIEW (SDET) → raises MR ──
```

## Three-source model for scenario generation

| Source | Role in SDET plan |
|---|---|
| RFC | Master scenario list — completeness guarantee. RFC coverage % = scenario coverage % |
| PRD | Priority and risk weighting — P0/P1/P2, business error scenarios |
| Tasks | Scenario classification — which test layer (component / integration / e2e), preconditions |
| Regression | Deduplication — what is already covered and what needs updating |

## Design decisions

- **Tasks (A) on API contracts** — tasks-extractor output is authoritative post codebase reconciliation; RFC is design-level (C). Conflicts are flagged, never silently resolved.
- **RFC (A) on validation sequence** — RFC owns the complete ordered sequence + WHY; Tasks own per-component slices.
- **Dedup has two distinct modes** — scenario-level (after sdet-plan-generator) and method-level (in code lane after automation-plan-generator). Same skill, different inputs and scopes.
- **Parallel code lanes** — test-data-generator and test-code-generator run in parallel after automation plan approval; fixtures resolved at execution time (Phase B CI), not embedded in code.
- **Re-trigger path** — upstream doc changes go through doc-delta-extractor + human feedback confirmation before sdet-plan-generator re-runs; does not re-run full extractors.

## Model tiers
- Reasoning (Opus): **sdet-plan-generator** only (~1/Epic).
- Fast (Haiku / Composer 2.5): extractors, automation-plan-generator, test-data-generator, test-code-generator, test-code-validator, dedup-generator.

## Test data (TDP / TestBuddy)
`test-data-generator` produces fixture requests consumed by TDP / TestBuddy at Phase B CI execution time.
Fixtures are referenced by `fixture_id` in test code — never hardcoded entity IDs. Secrets from vault only.

## Validation
Every skill output must validate against its schema:
```
python3 -c "import json,jsonschema; jsonschema.validate(
  json.load(open('examples/<feature>/sdet_plan.json')),
  json.load(open('schemas/sdet_plan.schema.json')))"
```

## Before this is fully runnable — supply these (<TODO> in skills)
1. A real sanitized **GBT Java test class** (one service) → so code output matches house style.
2. The real **TapMind NLP step grammar** for backend API steps + a sample test.
3. The **naming convention** for test classes and methods (`should[Outcome]When[Condition]`).
4. TDP / TestBuddy fixture provisioning API contract.

## Installing a skill
Each `skills/<name>/SKILL.md` is a loadable skill (folder name = skill id).
Point your skills directory at `skills/`, or install per Settings → Capabilities.
Schemas are referenced from `schemas/`.
