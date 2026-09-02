# Backend QA Skills — Agentic PDLC

A production skill set for the **backend / API** QA track across GoTo services.
Covers the full agentic PDLC pipeline: pre-build scenario planning, post-build code generation, and upstream doc doc-change-context.

## Folder layout
```
aep-backend/
  README.md                        ← this guide
  schemas/                         ← JSON Schema validators for every context/output
    prd_context · rfc_context · tasks_context · regression_context
    code_change_context (embeds reconciliation) · doc_change_context
    sdet_plan · automation_plan · test_data_manifest · test_data_requests · validation_report
  skills/                          ← 13 SKILL.md files
    prd-extractor · rfc-extractor · tasks-extractor · regression-extractor
    code-change-extractor · doc-delta-extractor
    sdet-plan-generator · dedup-generator · automation-plan-generator
    test-data-identification · test-data-generator
    test-code-generator · test-code-validator
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
  sdet-plan-generator [Upstream-context]
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
  sdet-plan-generator [doc-change-context] → patch affected scenarios only → delta review

POST-BUILD (Epic reaches QA Ready)
  code-change-extractor  ← Jira Epic/Story/Task key
        │  Phase 1  discover MR links across every service (Atlassian MCP)
        │  Phase 2  fetch per-service diffs vs merge-base + CR notes (GitLab REST / glab)
        │  Phase 3  extract → code_change_context.json (per service, noise-filtered)
        │  Phase 4  reconcile vs a baseline (sdet_plan.json OR a Jira task/story's ACs)
        →   code_change_context.json.reconciliation (embedded) + code_diff_report.md
             (error-code mismatches · contract changes · info gaps · suggested tests)
             reconciliation is null when no baseline is supplied (extraction-only)
        ▼
  sdet-plan-generator [Code-change-context] → confirm / patch / extend from the extracted + reconciled signal
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
  test-data-identification         dedup-generator [method mode]
  → test_data_manifest.json               ↓
  → enriched automation_plan.json  test-code-generator
    (test_data_output per fixture) → GBT Java + TapMind NLP steps
        ▼                                   ↓
  test-data-generator              test-code-validator
  → test_data_requests.json        → validation_report.json
    (TDP / TestBuddy)                      │
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
- **Identify before provision** — test-data-identification is a pure planning step (catalog lookups only, nothing created). Splitting it from provisioning means a data gap surfaces at the automation-plan review gate instead of as a test failure at execution time, and re-identification is cheap when the plan changes.
- **Doc-change-context path** — upstream doc changes go through doc-delta-extractor + human feedback confirmation before sdet-plan-generator re-runs; does not re-run full extractors.

## Model tiers
- Reasoning (Opus): **sdet-plan-generator** only (~1/Epic).
- Fast (Haiku / Composer 2.5): extractors, automation-plan-generator, test-data-identification, test-data-generator, test-code-generator, test-code-validator, dedup-generator.

## Test data (TDP / TestBuddy)

The test-data-generation stage has two halves — **identify**, then **provision**:

| Stage | Skill | Output | When |
|---|---|---|---|
| Identify | `test-data-identification` | `test_data_manifest.json` + `automation_plan.json` enriched with `test_data_output` per fixture | Right after the automation plan is approved |
| Provision | `test-data-generator` (→ `test-data-provision`) | `test_data_requests.json` / live entities via TestBuddy | Code-generation or Phase B CI execution time |

Identification decides, per fixture: Test Data Domain → real TDP category → the ordered operation
sequence closing the gap → `test_data_status` (`TDP_SUPPORTED` · `TESTBUDDY_SUPPORTED` ·
`TESTBUDDY_HYBRID_FALLBACK` · `TESTBUDDY_OPERATION_FALLBACK` · `TDP_PARTIAL` ·
`TDP_NOT_SUPPORTED`) → the TestBuddy prompt. Support is resolved in one fixed order — TDP →
TestBuddy → Pertamax → GBT — and the status records how far down it the fixture got: fully served by
a TDP category match, fully served by TestBuddy, partly served with the rest built from Pertamax/GBT
operations, built entirely from those operations, partly served with an operation no tier fulfils
(`TDP_PARTIAL`), or served by nothing at all (`TDP_NOT_SUPPORTED`). It never provisions and
never invents a category or operation name — both come from the TestBuddy MCP catalog tools
(`TestDataAgent_get_supported_category`, `TestDataAgent_generate_testbuddy_prompt`; a
`get_supported_operations` counterpart is not shipped yet, so operations fall back to the live
`<Domain>Agent_*` tool inventory). The category matcher always returns its nearest match and never
reports a no-match, so the skill validates every returned category against the fixture's own signals
and rejects the uncorroborated ones instead of trusting them. Domain
definitions live in `skills/test-data-identification/references/test_data_domains.md`; adding a
domain is a file edit, not a skill change.

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

## Installing the plugin

### Claude Desktop (GUI)
1. Open **Settings → Capabilities → Plugins**
2. Click **Add plugin source** and paste the skills repo Git URL
3. Claude Desktop reads `marketplace.json` and lists available plugins
4. Click **Install** next to `aep-backend`
5. All 13 skills are immediately available
![alt text](<Screenshot 2026-07-30 at 11.51.25 AM.png>)


### Claude Code (CLI)
```bash
claude plugins install https://gitlab.com/<org>/skills --plugin aep-backend
```

### Using the skills

Skills auto-trigger based on their description. You can also invoke them explicitly:
```
/backend-prd-extractor
/backend-rfc-extractor
/backend-tasks-extractor
/backend-regression-extractor
/backend-sdet-plan-generator
/backend-automation-plan-generator
/backend-test-data-identification
/backend-test-data-generator
/backend-test-code-generator
/backend-test-code-validator
/backend-dedup-generator
/backend-code-change-extractor
/backend-doc-delta-extractor
```

Or naturally in conversation:
> *"Extract the RFC context from this RFC doc"* → triggers `backend-rfc-extractor`
> *"Generate the SDET plan for this feature"* → triggers `backend-sdet-plan-generator`
> *"The PRD was updated, doc-change-context the plan"* → triggers `backend-doc-delta-extractor`

### Running the pipeline end to end

```
1. Share PRD + RFC + TASKS.md with Claude
   → prd-extractor, rfc-extractor, tasks-extractor, regression-extractor run

2. sdet-plan-generator (Upstream-context) produces:
   → <feature>_sdet_plan.json + qa_analysis.md + testcases.csv

3. SDET + PM review the plan in Claude
   → approve → BrowserStack upload
   → gaps found → regenerate → re-review

4. Post-build: give the Epic (or Story/Task) Jira key
   → code-change-extractor discovers the MR links, fetches per-service diffs,
     extracts code_change_context.json, and (if a baseline is supplied — sdet_plan.json
     OR a Jira task/story's ACs) reconciles into its embedded reconciliation object
     → code_change_context.json + code_diff_report.md (triage at the QA-Ready gate)
   → sdet-plan-generator Code-change-context → delta review
   (needs GITLAB_TOKEN + GITLAB_HOST, or an authenticated glab, to fetch diffs)

5. Approved → automation-plan-generator → SDET reviews automation plan

6. Parallel:
   → test-data-identification (domain + TDP category + operations per fixture)
     → test-data-generator / test-data-provision (TDP fixtures)
   → dedup-generator + test-code-generator (GBT Java)

7. test-code-validator → SDET reviews code → raises MR
```

### If an upstream doc changes mid-sprint
```
Share the updated PRD/RFC/Tasks with Claude
→ doc-delta-extractor extracts what changed
→ SDET + PM confirm scope (human feedback gate)
→ sdet-plan-generator re-triggered with delta only
→ review delta scenarios → re-upload to BrowserStack
```

Each `skills/<name>/SKILL.md` is a loadable skill (folder name = skill id).
Schemas are referenced from `schemas/`.

