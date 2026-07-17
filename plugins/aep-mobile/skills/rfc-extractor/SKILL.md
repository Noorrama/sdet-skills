---
name: mobile-rfc-extractor
description: Extract scope, risk register, feature flags, cross-team deps, min app version and N-1 compatibility from a mobile RFC into rfc_context.json. App-agnostic; optional (only when an RFC exists). Tells the SDET_PLAN where to concentrate depth and which flags/N-1 versions to parameterise.
---

# Mobile RFC Extractor (all 5 GoTo apps)

Distils the RFC into the risk/scope signals that shape test prioritisation. Skipped when an EPIC
has no RFC.

## Config
`config/<app>.json` → set `rfc_context.app = app_id`.

## Reads
RFC document (Lark/Confluence).

## Model
Fast tier — Haiku / Composer 2.5.

## Extract (→ rfc_context.schema.json)
- **scope**, **risk_areas**, and a **risk_register** (id, area, severity, likelihood, test_focus, p0).
- **feature_flags** (key + states) and **cross_team_deps**.
- **min_app_version**, **n1_compat** (how N-1 must behave), **rollout** (staged/cohort).

## Definition of Ready — reject/flag if
Impact/blast-radius absent; no N-1 compatibility statement; risks unrated.

## Guardrails
Do not infer risks not stated. Output valid JSON only, conforming to `schemas/rfc_context.schema.json`.
