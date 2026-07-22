---
name: mobile-sdet-plan-generator
description: Ingests pre-build contexts (plan, prd, design, rfc) to perform cross-stage gap analysis and generate master SDET Plan deliverables in JSON, MD, and CSV formats. Use during implementation planning to produce test scenarios, clickstream verifications, and testability feedback.
---

# Mobile SDET Plan Generator

## Purpose
Aggregates upstream extractor contexts (`plan_context`, `prd_context`, `design_context`, `rfc_context`) during implementation planning to generate 3 standardized pre-build deliverables:
1. `sdet_plan.json` (Machine-readable master execution contract)
2. `sdet_plan.md` (Human-readable RFC report)
3. `sdet_plan.csv` (TMS bulk-import format)

---

## Input Contracts

- **`plan_context.json`** *(PRIMARY DRIVER)*: Change surface, test hooks (`method:deeplink`, `hook_id`), feature flags, observable states.
- **`prd_context.json`**: Business rules, boundary rules, expected UI copy, and `clickstream_events` (telemetry specs).
- **`design_context.json`**: Screen definitions, UI elements with `screen_name:element_id_name` logical tokens, state variants, and flow matrix.
- **`rfc_context.json`**: Feature flag mappings, API contracts, error codes, and N-1 fallback rules.

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
- **Mobile Extras**: Offline/poor-network, permission prompts, feature flag toggles, deep-link navigation, and regional variants.
- **Navigation Priority**: Prefer test hooks (`method:deeplink` or `hook_id`) over full UI walks.

### 3. Gap Analysis & Testability Feedback
- **`prd_vs_figma_gaps`**: Missing screens, text copy mismatches, missing error/loading frames.
- **`prd_vs_rfc_gaps`**: PRD business rules/flags missing technical RFC specs.
- **`rfc_vs_impl_plan_gaps`**: Technical fallback/retry rules missing in task implementation scope.
- **`element_locator_handoff`**: Map `screen_name:element_id_name` logical tokens to cross-platform accessibility attributes (`resource-id`, `accessibilityIdentifier`, `Key / Semantics`).

---

## Output File Specifications

Generate the following 3 files in the current working directory:

### 1. `sdet_plan.json`
Full machine-readable master payload conforming strictly to `schemas/sdet_plan.schema.json`. Must include `created_at` and `updated_at` ISO date-time timestamps.

### 2. `sdet_plan.md`
Markdown report formatted with the following sections:
- Feature Metadata & Scope Summary
- Risk Assessment
- Scenario List Table (Priority, Execution Scope, Framework, Mode)
- Cross-Stage Gap Analysis Table
- Element Locator Handoff Mapping Table
- Clickstream Telemetry Verification Table

### 3. `sdet_plan.csv`
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

## Guardrails
- **Strict Determinism**: Do not extrapolate, infer, or hallucinate missing requirements. Map inputs directly to schemas without adding unmentioned fields or assumptions.
- **Contract Adherence**: Fail explicitly if mandatory input fields from upstream extractors (`plan_context`, `prd_context`, `design_context`, `rfc_context`) are missing.
- **Format Precision**: Outputs must strictly conform to `sdet_plan.schema.json` and the 15-column squad CSV schema without altering column headers or ordering.