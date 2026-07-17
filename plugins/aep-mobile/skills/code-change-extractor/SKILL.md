---
name: mobile-code-change-extractor
description: Post-build. Extract the changed surface for an EPIC from its GitLab MR(s) into change_context.json — changed screens, logical element_id → real per-platform locators (Android resource-id + iOS accessibilityId), routes/deeplinks, API shapes, flags, analytics, app↔API version, and reviewer edge cases from CR notes. App-agnostic. Feeds code/NLP generation, not scenario generation.
---

# Mobile Code-Change Extractor (post-build; all 5 GoTo apps)

Runs after the dev shares the build. Pins the exact changed surface and — the key job — joins each
logical `element_id` to its **real per-platform locator**, so NLP/coded automation can bind to it.
Covers both the Code Diff and CR-Notes inputs (both read from the MR).

## Config
`config/<app>.json` → `locator_keys` (android=resource-id, ios=accessibilityId), platforms.

## Reads
The EPIC's MR(s). **Scope rule:** use the GitLab MR *changes* API (three-dot diff vs target
merge-base) so other features already on `main` and merge commits are excluded. Take the **union of
all MRs linked to the EPIC** (by JIRA key/label), then **intersect with the SDET_PLAN scope** — hunks
outside the EPIC's scenarios are ignored. Also read the MR review comments (CR notes).

## Model
Fast tier — Haiku / Composer 2.5.

## Extract (→ change_context.schema.json)
- `epic_ref`, `merge_requests`, `changed_screens`.
- **elements** — `element_id` → `android_locator` (resource-id) + `ios_locator` (accessibilityId), for both platforms.
- `routes`/deeplinks, `api` (endpoint + request/response + error_codes), `flags`, `analytics`, `app_api_version` (incl. N-1).
- **cr_risks** — id, area, category, suggested_test, severity, disposition (becomes-scenario/becomes-bug/acknowledged).

## Rules
- The stable-ID gate: every P0 element touched must expose a locator mapped to its `element_id`.
  A P0 element changed/added without a locator → testability gap (never infer brittle XPath/text).
- If `naming_convention.developer_locator_equals_role` is false, emit the explicit element_id→locator map (no 1:1 assumption).

## Guardrails
Report only what the diff/CR show. Output valid JSON only, conforming to `schemas/change_context.schema.json`.
