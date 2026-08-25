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
        │
  impact-shortlister    → impact_shortlist.json       (which existing regression cases the merged
        │                                            code actually impacts — deterministic evidence
        │                                            match + one agent judgment pass, no scoring
        │                                            service; roll-up appended to sdet_plan.impact_shortlist)
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

Every skill output must validate against its schema. **SDET plan deliverables** also require the
org-wide compliance gate (any feature, any app):

```bash
python3 scripts/build_coverage_checklist.py --prd prd_context.json [--design ...] [--rfc ...] --out coverage_checklist.json

python3 scripts/validate_sdet_deliverables.py \
  --prd prd_context.json \
  --plan <feature_key>_SDET_plan.json \
  --csv <feature_key>_test_cases.csv \
  --analysis <feature_key>_analysis.md \
  [--design design_context.json] [--rfc rfc_context.json] \
  --checklist coverage_checklist.json
```

See `skills/sdet-plan-generator/workflow.md` and `anti_patterns.md`. JSON schema-only check:

```bash
python3 -c "import json,jsonschema; jsonschema.validate(
  json.load(open('examples/gojek-consumer-save20/sdet_plan.json')),
  json.load(open('schemas/scenario.schema.json')))"
```

## Before this is fully runnable — you must supply (marked <TODO> in configs/skills)
1. A real sanitized **GMT test + page object** (one app) → so coded output matches house style.
2. The real **TapMind NLP step grammar** + a sample test → so NLP output is runnable (the example uses an illustrative shape).
3. The **naming convention** (`element_id` rule) + whether existing screens follow it (brownfield).
4. Per-app config values (repos, deeplink scheme, package/bundle, device matrix, TestBuddy segment names).

## Installing the plugin

Each `skills/<name>/SKILL.md` is a loadable skill (folder name = skill id). Schemas and config
are referenced with paths relative to the plugin root (`schemas/`, `config/`, `scripts/`).

### Claude Code (CLI / Desktop)

```
claude plugin marketplace add https://source.golabs.io/aep/skills.git
claude plugin install aep-mobile@aep
```

Then run the **aep-mobile-setup** skill to verify dependencies.

### Cursor

1. Install the plugin from the AEP marketplace (same repo as Claude Code), or symlink/copy
   `plugins/aep-mobile/skills/` into your project's `.cursor/skills/` or personal
   `~/.cursor/skills/`.
2. **Configure BrowserStack MCP** (required only for `regression-extractor` and SDET-plan upload; the prd/rfc/design/task extractors don't need it) in Cursor Settings → MCP (or `~/.cursor/mcp.json`):

   ```json
   {
     "mcpServers": {
       "browserstack": {
         "command": "npx",
         "args": ["-y", "@browserstack/mcp-server@latest"],
         "env": {
           "BROWSERSTACK_USERNAME": "<your-username>",
           "BROWSERSTACK_ACCESS_KEY": "<your-access-key>"
         }
       }
     }
   }
   ```

3. Restart Cursor.
4. Ask the agent to run the **aep-mobile-setup** skill. python3 + jsonschema are needed by
   every skill; **BrowserStack MCP** is needed only by `regression-extractor` and
   `sdet-plan-generator` (upload), which hard-stop without it — the prd/rfc/design/task
   extractors run fine without it.

### Updating

Bump pulls require a version change in `.claude-plugin/plugin.json` / `.cursor-plugin/plugin.json`:

```
claude plugin update aep-mobile@aep    # Claude Code
```

Then restart your editor. In Cursor, reinstall or refresh the plugin if skills don't update.

### Using the skills

Skills auto-trigger from their description. You can also invoke them explicitly by name, e.g.
`mobile-prd-extractor`, `mobile-regression-extractor`, `mobile-sdet-plan-generator`,
`aep-mobile-setup`.

Or naturally in conversation:
> *"Extract the PRD context for this mobile feature"* → triggers `mobile-prd-extractor`
> *"Generate the SDET plan"* → triggers `mobile-sdet-plan-generator`
> *"Check aep-mobile dependencies"* → triggers `aep-mobile-setup`
