---
name: mobile-sdet-plan-generator
description: Ingests pre-build contexts (plan, prd, design, rfc) to perform cross-stage gap analysis and generate master SDET Plan deliverables in JSON, MD, and CSV formats. Use during implementation planning to produce test scenarios, clickstream verifications, and testability feedback.
---

# Mobile SDET Plan Generator

## Purpose
Aggregates upstream extractor contexts (`plan_context`, `prd_context`, `design_context`, `rfc_context`) during implementation planning to generate 3 standardized pre-build deliverables:
1. `<feature_key>.json` (Machine-readable master execution contract)
2. `<feature_key>_analysis.md` (Human-readable Markdown QA analysis asset)
3. `<feature_key>.csv` (TMS bulk-import format)

---

## Input Contracts

- **`plan_context.json`** *(PRIMARY DRIVER)*: Change surface, test hooks (`method:deeplink`, `hook_id`), feature flags, observable states.
- **`prd_context.json`**: Business rules, boundary rules, expected UI copy, and `clickstream_events` (telemetry specs).
- **`design_context.json`**: Screen definitions, UI elements with `screen_name:element_id_name` logical tokens, state variants, and flow matrix.
- **`rfc_context.json`**: Feature flag mappings, API contracts, error codes, and N-1 fallback rules.

> **Pipeline Alignment & Architecture:** Upstream extractor skills (`prd-extractor`, `design-extractor`, `rfc-extractor`) run independently in isolated silos per stage and **do not communicate with each other**. The `sdet-plan-generator` is the first convergence point in the pipeline. It is responsible for cross-referencing these decoupled contexts to detect drift, mismatches, and gaps.

---

## Execution Workflow

### 1. Ingest & Coverage Gates
- Use `plan_context` as primary driver to define reachable test surface; supplement with PRD acceptance criteria.
- **Hard Coverage Rules**:
  - Every P0 requirement $\rightarrow \ge 1$ scenario.
  - Every `clickstream_events` entry $\rightarrow \ge 1$ verification step.
  - Every `boundary_rules` entry $\rightarrow \ge 1$ boundary scenario.
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
- **`element_locator_handoff`**: Map `screen_name:element_id_name` logical tokens to cross-platform accessibility attributes (`resource-id`, `accessibilityIdentifier`, `Key / Semantics`).

---

## Output File Specifications

Generate the following 3 files in the current working directory, naming them dynamically using the `<feature_key>` defined in `feature_metadata`:

### 1. `<feature_key>.json`
Full machine-readable master payload conforming strictly to `schemas/sdet_plan.schema.json`. Must include `created_at` and `updated_at` ISO date-time timestamps.

### 2. `<feature_key>_analysis.md` (QA Analysis Asset)
A human-readable Markdown asset automatically generated for engineering leads detailing parsed requirements gaps, architectural risks, and testability bottlenecks during the pre-build review.

**Note: Do NOT include individual scenario/test cases here.** Instead, focus on high-level pre-build analysis:
- **Open Questions & Clarifications:** Specific lists of unresolved questions and follow-ups for PMs and Devs.
- **Cross-Stage Gaps:** Extracted mismatches between the inputs (PRD vs Figma, PRD vs RFC, RFC vs Implementation Plan).
- **Architectural & Testability Risks:** Missing hooks, unstable element IDs, or fallback concerns.
- **SDET Readiness & Testing Plan:** Actionable instructions on how the QA team should start testing, what environments/data setup to prepare, what dependencies to take, and execution guidelines.

### 3. `<feature_key>.csv`
Flattened CSV strictly matching squad project template headers:

`Title`, `State`, `Priority`, `Type of Test Case`, `Automation Status`, `Preconditions`, `Steps`, `Expected Result`, `Execution Mode`, `Platform`, `Country v2`, `Android Automation Status v2`, `iOS Automation Status v2`, `TestType`, `DriverType`

**Column Value Directives**:
- `Title`: Concise scenario description.
- `State`: `"Active"`
- `Priority`: `"P0"`, `"P1"`, or `"P2"`
- `Type of Test Case`: `"Regression"` or `"Sanity"`
- `Automation Status`: `"Manual"` or `"Automated"`
- `Preconditions`: Multiline string with environment, locale, deep links, and active feature flags.
- `Steps`: Numbered sequential steps inside double quotes with line breaks (`\n`). Must include telemetry emission checks.
- `Expected Result`: Clear functional and telemetry assertions.
- `Execution Mode`: `"Automatable"` or `"Manual"`
- `Platform`: `"Android"`, `"iOS"`, or `"Cross-Platform"`
- `Country v2`: `"Indonesia"`, `"Singapore"`, `"Vietnam"`, etc.
- `Android Automation Status v2`: `"Automated"`, `"Manual"`, or `"N/A"`
- `iOS Automation Status v2`: `"Automated"`, `"Manual"`, or `"N/A"`
- `TestType`: `"Story"`
- `DriverType`: `"IDBike"`, `"IDCar"`, or `"N/A"`

---

## Bidirectional Sync Workflow

The skill supports a two-way synchronization flow to allow human QA to review, refine, and add test cases manually in the CSV, and feed those corrections back to keep the master JSON in perfect alignment.

### Dual Execution Modes

1. **`GENERATE` Mode (Default):**
   - **Trigger:** Upstream extractor contexts are provided as input.
   - **Action:** Generates `<feature_key>.json`, `<feature_key>_analysis.md`, and `<feature_key>.csv` from scratch.

2. **`SYNC` Mode (Reverse Sync):**
   - **Trigger:** A modified `<feature_key>.csv` is uploaded/provided as input. The skill automatically reads the existing `<feature_key>.json` directly from the working directory.
   - **Action:** Parses the modified CSV and merges all human edits back into `<feature_key>.json` strictly following these reconciliation rules:
     - **Mapping Anchor:** Correlate rows in the CSV to scenario objects in `<feature_key>.json` using `Title` $\leftrightarrow$ `csv_title_association` as the primary key.
     - **Synchronize Overridden Properties:** If the human QA modified fields in a correlated CSV row (e.g., changed `Automation Status` from "Manual" to "Automated", tweaked `Execution Mode` from "Manual" to "Automatable", altered priority, or edited steps), update those exact property values in `<feature_key>.json` to match the CSV.
     - **Ingest New Manual Scenarios:** If a row exists in the CSV but has no matching `csv_title_association` in `<feature_key>.json`, it represents a new test case added by the QA. Create a new scenario object for it inside `<feature_key>.json` with:
       - `is_legacy_regression: true`
       - `automatable: false`
       - All standard properties parsed from the CSV columns.
     - **Preserve Un-mapped Context Metadata:** Advanced technical properties inside `<feature_key>.json` (such as `mapped_user_flow`, `test_data_tags`, `clickstream_events`, or specific `target_execution_framework` metadata) which do not exist in the flat 15-column CSV layout **must be preserved verbatim** for existing scenarios. Do not delete or overwrite them.
     - **Update Timestamps:** Automatically update the `updated_at` timestamp in `<feature_key>.json` to reflect the synchronization event.

---

## Guardrails
- **Strict Determinism**: Do not extrapolate, infer, or hallucinate missing requirements. Map inputs directly to schemas without adding unmentioned fields or assumptions.
- **Contract Adherence**: Fail explicitly if mandatory input fields from upstream extractors (`plan_context`, `prd_context`, `design_context`, `rfc_context`) are missing.
- **Format Precision**: Outputs must strictly conform to `sdet_plan.schema.json` and the 15-column squad CSV schema without altering column headers or ordering.
- **Frontend Focus**: Test cases/scenarios must be generated *exclusively* for Frontend (FE) context (e.g., client-side UI, mobile views, offline transitions, local error copy, and client-side telemetry verifications). Do not generate backend-only validation or server-side test cases.