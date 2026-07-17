---
name: mobile-prd-extractor
description: Extract QA-relevant structure from a mobile PRD into prd_context.json — requirements, eligibility/boundary business rules, personas, payment constraints, feature flags, data signals, and a needs_clarification list. App-agnostic; works for any of the 5 GoTo apps via the per-app config. First step of the mobile QA pipeline.
---

# Mobile PRD Extractor (all 5 GoTo apps)

Turns PRD prose into a small structured context. Two jobs: normalise what is stated, and run the
Definition-of-Ready check — surface what is missing rather than inventing it.

## Config
Read `config/<app>.json` for `app_id`. Set `prd_context.app = app_id`. The skill is otherwise
app-agnostic.

## Reads
PRD text (Lark/Confluence) + optional JIRA epic key.

## Model
Fast tier — Haiku / Composer 2.5. Escalate to reasoning only if the PRD is long/ambiguous.

## Extract (→ prd_context.schema.json)
1. **requirements** — id, testable statement, priority, area, high_risk (payments/wallet/auth → P0).
2. **business_rules** — id, condition, boundary values, error message (if stated).
3. **personas**, **payment_constraints**, **feature_flags**.
4. **data_signals** — entity + state the rules imply (precursor to per-scenario data_needs).
5. **needs_clarification** — non-verifiable statements, implicit boundaries, undefined values, missing error copy.

## Definition of Ready — reject/flag if
No testable statement or priority; a numeric rule with no boundary; an undefined value
(discount %, threshold); missing error copy; "first-time/eligible/sufficient" used without a definition.

## Guardrails
- Never invent values — unknowns go to `needs_clarification`.
- `data_signals` are hints; the scenario generator writes concrete `data_needs`.
- Output valid JSON only, conforming to `schemas/prd_context.schema.json`.

## Validate
`jsonschema.validate(output, schemas/prd_context.schema.json)`
