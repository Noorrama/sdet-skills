# Mobile QA skills — Agentic PDLC (all 5 GoTo apps)

A production skill set for the **frontend / mobile** QA track, reusable across **Gojek Consumer,
Gojek Driver, GoFood Merchant, GoPay Consumer, GoPay Merchant**. One skill per SDLC stage + one
shared test-data skill. **App-agnostic** — each app is a config file, not a fork.

## Folder layout
```
mobile-qa-skills/
  README.md                     ← this guide
  config/
    app-config.schema.json      ← per-app config contract
    gojek-consumer.json         ← filled example
    _template.json              ← copy per app (driver, gofood-merchant, gopay-consumer, gopay-merchant)
  schemas/                      ← JSON-schema validators for every context/output
    prd_context · design_context · rfc_context · plan_context · change_context · scenario · data_handle
  skills/                       ← 8 SKILL.md (app-agnostic)
    prd-extractor · design-extractor · rfc-extractor · impl-plan · code-change-extractor
    sdet-plan-generator · test-code-generator · test-data-provisioner
  examples/gojek-consumer-save20/   ← worked example across the whole pipeline
```

## Pipeline & run order
```
PRE-BUILD (parallel with implementation)
  prd-extractor        → prd_context.json
  design-extractor     → design_context.json        (frontend-primary)
  rfc-extractor        → rfc_context.json            (optional)
  impl-plan            → plan_context.json           ★ PRIMARY DRIVER (+ test hooks/deeplinks)
        │  (+ existing GMT/NLP tests via retrieval → dedup)
        ▼
  sdet-plan-generator  → sdet_plan.json (scenarios + navigation + data_needs) + testability_feedback
        │
   ── HUMAN REVIEW GATE (SDET / Feature Lead) ──
        ▼
POST-BUILD (dev shares the build)
  code-change-extractor → change_context.json        (real per-platform locators, API, CR edges)
        ▼
  test-code-generator   → TapMind NLP steps (primary) + GMT coded (where needed), both Android & iOS
                          (test data wired via test-data-provisioner → TestBuddy)
```
Shared at both stages: **test-data-provisioner** (TestBuddy → GBT fallback → synthetic).

## Design decisions baked in
- **Reuse:** app-agnostic skills + `config/<app>.json`. Add an app = copy `_template.json`, fill it.
- **Both platforms:** `element_id` → `android_locator` (resource-id) + `ios_locator` (accessibilityId), from `change_context`.
- **NLP-primary output:** TapMind steps are the default; GMT coded is emitted where NLP can't express a case. (Precondition for reliable NLP self-heal in Phase B: TapMind must expose step-level diagnostics + grounding.)
- **Grounding = the GMT coded repo** for *both* output forms (page objects/navigation live there; the TapMind repo alone is too thin).
- **Navigation:** prefer a PLAN **deeplink/state-injection hook** to reach the screen; fall back to a Design **flow** UI walk.
- **data_needs:** authored by the scenario generator (Impl. Planning) from PRD `data_signals` + boundaries; resolved by the provisioner (Code Generation). Coverage gate: every `data_signal` → ≥1 scenario.

## Model tiers (per SOP)
- Reasoning (Opus / GPT 5.5): **sdet-plan-generator** only (accuracy-critical, ~1/EPIC).
- Fast (Composer 2.5 default, Haiku light): the extractors, test-code-generator, provisioner.
- Escalate fast → reasoning only on ambiguity / repeated failure.

## Test data (TestBuddy)
`test-data-provisioner` calls the **TestBuddy MCP** as the source of truth — e.g. `CustomerAgent`
(GoPay balance/recharge, segments, saved address, token), `VoucherAgent` (SAVE20), `BookingAgent`,
`DriverAgent`, `PaymentAgent` (dynamic QR). GBT builder fallback for states TestBuddy lacks;
synthetic for sensitive (KYC/PII). Always returns handles, never raw values; secrets from vault.

## Validation
Every skill output must validate against its schema:
```
python3 -c "import json,jsonschema; jsonschema.validate(
  json.load(open('examples/gojek-consumer-save20/sdet_plan.json')),
  json.load(open('schemas/scenario.schema.json')))"
```

## Before this is fully runnable — you must supply (marked <TODO> in configs/skills)
1. A real sanitized **GMT test + page object** (one app) → so coded output matches house style.
2. The real **TapMind NLP step grammar** + a sample test → so NLP output is runnable (the example uses an illustrative shape).
3. The **naming convention** (`element_id` rule) + whether existing screens follow it (brownfield).
4. Per-app config values (repos, deeplink scheme, package/bundle, device matrix, TestBuddy segment names).

## Installing a skill
Each `skills/<name>/SKILL.md` is a loadable skill (folder name = skill id). Point your skills
directory at `skills/`, or install per Settings → Capabilities. Schemas are referenced from `schemas/`.
