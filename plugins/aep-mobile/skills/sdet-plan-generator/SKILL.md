---
name: mobile-sdet-plan-generator
description: Ingests pre-build contexts (plan, prd, design, rfc) to perform cross-stage gap analysis and generate master SDET Plan deliverables in JSON, MD, and CSV formats. Use during implementation planning to produce test scenarios, clickstream verifications, and testability feedback.
---

# Mobile SDET Plan Generator

## Purpose
Aggregates upstream extractor contexts (`plan_context`, `prd_context`, `design_context`, `rfc_context`) during implementation planning to generate 3 standardized pre-build deliverables:
1. `<feature_key>_SDET_plan.json` (Machine-readable master execution contract)
2. `<feature_key>_analysis.md` (Human-readable Markdown QA analysis asset)
3. `<feature_key>_test_cases.csv` (TMS bulk-import format)

---

## Input Contracts

- **`plan_context.json`**: Change surface, test hooks (`method:deeplink`, `hook_id`), feature flags, observable states.
- **`prd_context.json`**: Business rules, boundary rules, expected UI copy, and `clickstream_events` (telemetry specs).
- **`design_context.json`**: Screen definitions, UI elements with `screen_name:element_id_name` logical tokens, state variants, and flow matrix.
- **`rfc_context.json`**: Feature flag mappings, API contracts, error codes, and N-1 fallback rules.

> **Pipeline Alignment & Architecture:** Upstream extractor skills (`prd-extractor`, `design-extractor`, `rfc-extractor`) run independently in isolated silos per stage and **do not communicate with each other**. The `sdet-plan-generator` is the first convergence point in the pipeline. It is responsible for cross-referencing these decoupled contexts to detect drift, mismatches, and gaps.

---

## Execution Workflow

### 1. Ingest & Coverage Gates
- Ingest and aggregate whatever context inputs are provided (`plan_context`, `prd_context`, `design_context`, `rfc_context`).
- **Graceful Input Absence Handling:** If individual contexts (such as `plan_context.json` or `rfc_context.json`) are NOT provided, **do NOT fail execution.** Drive the generation with whatever inputs are given:
  - If `plan_context.json` is absent, proceed with `prd_context.json` and `design_context.json` as the baseline. 
  - Simply note the missing contexts clearly as an architectural observation or limitation inside the `<feature_key>_analysis.md` report (e.g., *"plan_context.json was not provided; test hooks and specific code-change view models are excluded from this analysis."*).
- **Hard Coverage Rules**:
  - Every P0 requirement $\rightarrow \ge 1$ scenario.
  - Every `boundary_rules` entry $\rightarrow \ge 1$ boundary scenario.
  - **Clickstream Telemetry Rules:** Clickstream verification is **NOT** a mandatory hard gate for the generator. If `clickstream_events` are explicitly provided/told in the input contexts, then generate $\ge 1$ verification step per event. If they are NOT provided or explicitly mentioned, **do NOT fail validation and do NOT generate telemetry tests.** Instead, simply list it as an Open Question / Clarification inside `<feature_key>_analysis.md` (e.g., *"Are clickstream telemetry events required for this feature?"*).
- Dedup against existing GMT/NLP tests retrieved from `config/<app>.json` repository paths.

### 2. Scenario Expansion
Expand scenarios across:
- **Core**: Happy path, boundary, negative, and contract flows.
- **Mobile Extras**: Generates mobile-specific scenarios (deep-link navigation, regional variants, feature flag toggles) and applies **Conditional Mobile-Native Interruption Rules** to ensure test suites remain highly focused and are only generated when technically valid:
  - **Network Loss / API Timeout**: Inject a poor-network or server-timeout scenario *only* if `rfc_context.json` declares active `api_contract_changes` or `plan_context.json` specifies `observable_states` (API success/failure signals). Skip if the touchpoint screen is entirely static/local.
  - **App Backgrounding & Process Death**: Inject a backgrounding/kill-and-restore state preservation scenario *only* if the screens in `design_context.json` contain interactive elements (inputs, forms, toggles) or view models are active in `plan_context.json`. Skip on purely static/read-only informational screens.
  - **Local Storage & DB Migration**: Inject an N-1 upgrade and schema migration scenario *only* if `rfc_context.json` defines active `local_data_changes` (e.g. SQLite, Room, CoreData, or SharedPrefs modifications).
  - **Runtime Permission Toggles**: Inject parallel Permission Granted vs Permission Denied scenarios *only* if `rfc_context.json` declares new or modified `permissions_required`.
- **Navigation Priority**: Prefer test hooks (`method:deeplink` or `hook_id`) over full UI walks.

### 3. Gap Analysis & Alignment Engine
As the single integration point, the generator must actively compute the following cross-stage gaps:
- **`prd_vs_figma_gaps`**: Cross-reference `prd_context.json` with `design_context.json`. Check `business_requirements[].context_screen` against Figma `screens[].screen_id`. Identify missing screens/frames, text copy mismatches, or personas with no design representation.
- **`prd_vs_rfc_gaps`**: Cross-reference `prd_context.json` with `rfc_context.json`. Compare PRD `feature_flags` against the RFC `experimentation_matrix` (finding flag key typos, missing defaults, or status mismatches). Verify business rule conditions align with RFC error codes or API paths.
- **`rfc_vs_impl_plan_gaps`**: Cross-reference `rfc_context.json` with the Implementation `plan_context.json`. Check if RFC architectural risks, local migrations, offline strategies, or required permissions are accounted for in the implementation's screens touched, view models, and components.
- **`element_locator_handoff`**: Map `screen_name:element_id_name` logical tokens to cross-platform accessibility attributes (`android_resource_id`, `ios_accessibility_identifier`, `flutter_key`). Only populate these fields if the matching locator values are provided by the upstream design/development context; do not use placeholders or "UNRESOLVED" strings.

---

## Output File Specifications

Generate the following 3 files in the current working directory, naming them dynamically using the `<feature_key>` defined in `feature_metadata`:

### 1. `<feature_key>_SDET_plan.json`
Full machine-readable master payload conforming strictly to `schemas/sdet_plan.schema.json`. Must include `created_at` and `updated_at` ISO date-time timestamps.

### 2. `<feature_key>_analysis.md` (QA Analysis Asset)
A human-readable Markdown asset automatically generated for engineering leads detailing parsed requirements gaps, architectural risks, and testability bottlenecks during the pre-build review.

**Note: Do NOT include individual scenario/test cases here.** Instead, you must match the exact structural layout, depth, and tone of the gold-standard **`birthday_feature_analysis best.md`** blueprint:

#### **Required Document Sections & Formatting**:

1. **Meta Header:**
   - Include clear, bold rows: **Feature Key**, **App**, **RFC (ID, Title, Status)**, **Analysis Date**, **SDET Plan File**, **Test Cases File**.

2. **Section 1: Missing Input Context:**
   - If any input context (like `plan_context.json` or `rfc_context.json`) is absent, list it and detail the exact consequences (e.g., missing test hooks, uncomputed gaps, unpopulated platform-specific locator attributes in JSON).

3. **Section 2: Cross-Stage Gap Analysis:**
   - **PRD vs Figma Gaps Table:** Must contain columns: `Req` (Requirement ID), `Severity` (`CRITICAL_BLOCKER` or `WARNING`), and `Gap` (highly detailed, context-aware analysis of broken prototype links, un-designed flows, dynamic text copy verification requirements).
   - **PRD vs RFC Gaps Table:** Must contain columns: `Req` and `Gap` (outlining architectural drift, scoped platform changes like Flutter single-build vs separate builds, feature flag mismatches, and specific environment IDs).
   - **RFC vs Implementation Plan Gaps:** List exact technical elements that require verification (e.g., specific cache invalidation strategies, database migrations with keys, lifecycle state preservation, and required Android/iOS permissions).

4. **Section 3: Architectural & Testability Risks Table:**
   - Columns: `Risk ID`, `Severity` (`Critical`, `High`, `Medium`, `Low`), `Description`, and `Testing Implication` (detailing specific manual/automated testing approaches to mitigate the risk). Focus on caching, state sync, stale name values, etc.

5. **Section 4: Open Questions & Clarifications:**
   - Must be categorized explicitly by current blocker status and owner:
     - **Blocked — Awaiting PM / Design Input Table** (Columns: `ID`, `Question`, `Test Impact`)
     - **Blocked — Awaiting Dev / RFC Author Input Table** (Columns: `ID`, `Question`, `Test Impact`)
     - **Resolved — Unblocked for Testing Table** (Columns: `ID`, `Resolution`, `Test Action`)
     - **Additional Clarifications Needed (for PM)** (Detailed bullet points covering telemetry payload schemas, copy approvals, sound packages, third-party libraries).

6. **Section 5: SDET Readiness & Testing Plan:**
   - **Environment Requirements Table:** (Columns: `Item`, `Specification`) detailing App, target release environment configs, kill switch flags, and local/time zones.
   - **Test Data Requirements Table:** (Columns: `Tag`, `Description`) mapping exact user segments, verification states, device permissions, and system configurations (e.g., `gallery_permission_denied`, `no_card_selected`).
   - **Device Matrix:** Reference targets from the configuration (e.g., `Pixel 7`, `iPhone 14`).
   - **Dependencies Before Test Execution:** Bullet points of absolute prerequisites (finalized copy, manifest declarations, design updates).
   - **Execution Guidelines:** Highly technical, actionable testing recipes detailing manual and automated procedures (e.g., using `adb shell am kill` for process death, configuring proxy tools like Charles Proxy or mitmproxy for network interception, and real physical device instructions).

### 3. `<feature_key>_test_cases.csv`
Flattened CSV strictly matching squad project template headers:

`Title`, `State`, `Priority`, `Type of Test Case`, `Automation Status`, `Preconditions`, `Steps`, `Expected Result`, `Execution Mode`, `Platform`, `Country v2`, `Android Automation Status v2`, `iOS Automation Status v2`, `TestType`

**Column Value Directives**:
- `Title`: Concise scenario description.
- `State`: `"Active"`
- `Priority`: `"P0"`, `"P1"`, or `"P2"`
- `Type of Test Case`: `"Regression"` or `"Sanity"`
- `Automation Status`: By default, set to `"Manual"` (representing not-automated) for newly generated test cases. Set to `"Automated"` only if matched with an existing automated test case.
- `Preconditions`: Multiline string with environment, locale, deep links, and active feature flags, **using a new line break (`\n`) after each statement/line.**
- `Steps`: Numbered sequential actions inside double quotes with line breaks (`\n`). **Write steps using clean, action-oriented, declarative NLP-style commands** (e.g., `1. Open deeplink "gopay://affiliate/welcome"`, `2. Enter "CODE123" into "Referral Code"`, `3. Tap "Lanjut"`). Never use long, vague prose or technical automation/logical IDs (e.g., do NOT write `Tap WELCOME_PAGE.TAP_BUTTON_CTA`; instead, write `Tap "Daftar Program Affiliate"`). Must include telemetry emission checks.
- `Expected Result`: Numbered sequential assertions matching the numbered steps in the `Steps` column 1-to-1, inside double quotes with line breaks (`\n`) after each statement. **Write assertions using clean, declarative NLP-style verification commands** (e.g., `1. Verify "Confirm Account" is visible`, `2. Verify "Error: Code incorrect" is visible`). Describe functional and telemetry outcomes in user-friendly, non-technical language.
- `Execution Mode`: `"Automatable"` or `"Manual"`
- `Platform`: `"Android"`, `"iOS"`, or `"Cross-Platform"`
- `Country v2`: `"Indonesia"`, `"Singapore"`, `"Vietnam"`, etc.
- `Android Automation Status v2`: By default, set to `"Manual"` (or `"N/A"` if platform is iOS-only). Set to `"Automated"` only if matched with an existing automated Android case.
- `iOS Automation Status v2`: By default, set to `"Manual"` (or `"N/A"` if platform is Android-only). Set to `"Automated"` only if matched with an existing automated iOS case.
- `TestType`: `"Story"`

---

## Bidirectional Sync Workflow

The skill supports a two-way synchronization flow to allow human QA to review, refine, and add test cases manually in the CSV, and feed those corrections back to keep the master JSON in perfect alignment.

### Dual Execution Modes

1. **`GENERATE` Mode (Default):**
   - **Trigger:** Upstream extractor contexts are provided as input.
   - **Action:** Generates `<feature_key>_SDET_plan.json`, `<feature_key>_analysis.md`, and `<feature_key>_test_cases.csv` from scratch.

2. **`SYNC` Mode (Reverse Sync):**
   - **Trigger:** A modified `<feature_key>_test_cases.csv` is uploaded/provided as input. The skill automatically reads the existing `<feature_key>_SDET_plan.json` directly from the working directory.
   - **Action:** Parses the modified CSV and merges all human edits back into `<feature_key>_SDET_plan.json` strictly following these reconciliation rules:
     - **Mapping Anchor:** Correlate rows in the CSV to scenario objects in `<feature_key>_SDET_plan.json` using `Title` $\leftrightarrow$ `csv_title_association` as the primary key.
     - **Synchronize Overridden Properties:** If the human QA modified fields in a correlated CSV row (e.g., changed `Automation Status` from "Manual" to "Automated", tweaked `Execution Mode` from "Manual" to "Automatable", altered priority, or edited steps), update those exact property values in `<feature_key>_SDET_plan.json` to match the CSV.
     - **Ingest New Manual Scenarios:** If a row exists in the CSV but has no matching `csv_title_association` in `<feature_key>_SDET_plan.json`, it represents a new test case added by the QA. Create a new scenario object for it inside `<feature_key>_SDET_plan.json` with:
       - `is_legacy_regression: true`
       - `automatable: false`
       - All standard properties parsed from the CSV columns.
     - **Preserve Un-mapped Context Metadata:** Advanced technical properties inside `<feature_key>_SDET_plan.json` (such as `mapped_user_flow`, `test_data_tags`, `clickstream_events`, or specific `target_execution_framework` metadata) which do not exist in the flat 15-column CSV layout **must be preserved verbatim** for existing scenarios. Do not delete or overwrite them.
     - **Update Timestamps:** Automatically update the `updated_at` timestamp in `<feature_key>_SDET_plan.json` to reflect the synchronization event.

---

## Guardrails
- **Strict Determinism**: Do not extrapolate, infer, or hallucinate missing requirements. Map inputs directly to schemas without adding unmentioned fields or assumptions.
- **Contract Adherence**: Fail explicitly if *all* context files are missing or if essential keys within provided contexts are missing. However, do NOT fail if individual files (like `plan_context.json` or `rfc_context.json`) are absent; instead, proceed with the inputs that are provided, noting the missing contexts in `<feature_key>_analysis.md`.
- **Format Precision**: Outputs must strictly conform to `sdet_plan.schema.json` and the 15-column squad CSV schema without altering column headers or ordering.
- **Frontend Focus**: Test cases/scenarios must be generated *exclusively* for Frontend (FE) context (e.g., client-side UI, mobile views, offline transitions, local error copy, and client-side telemetry verifications). Do not generate backend-only validation or server-side test cases.