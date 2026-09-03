# Mobile QA skills — Agentic PDLC (all 5 GoTo apps)

A production skill set for the **frontend / mobile** QA track, reusable across **Gojek Consumer,
Gojek Driver, GoFood Merchant, GoPay Consumer, GoPay Merchant**. Three entry-point skills plus one
shared test-data skill; extraction/generation logic lives in model-pinned `agents/`.
**App-agnostic** — each app is a config file, not a fork.

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
  skills/                       ← 4 user-facing SKILL.md (orchestrators + shared TDP)
    mobile-context-extraction · mobile-sdet-plan-generator · mobile-postbuild
    test-data-provisioner
  agents/                       ← model-pinned subagents (Claude Code: sonnet / opus)
    prd-extractor · rfc-extractor · design-extractor · task-extractor
    regression-extractor · setup · sdet-plan-runner
    code-change-extractor · impact-shortlister · test-code-generator
  .cursor/agents/               ← same subagents, Cursor model IDs (claude-sonnet-5 / claude-opus-5)
  examples/gojek-consumer-save20/   ← worked example across the whole pipeline
```

## Pipeline & run order
```
PRE-BUILD
  /mobile-context-extraction     (setup preflight, then parallel extractors)
    prd-extractor        → prd_context.json
    design-extractor     → design_context.json        (frontend-primary)
    rfc-extractor        → rfc_context.json            (optional — skip if no RFC)
    task-extractor       → task_context.json           ★ PRIMARY DRIVER (+ test hooks/deeplinks)
    regression-extractor → regression_context.json     (BrowserStack; skip if MCP down)
        │
        ▼
  /mobile-sdet-plan-generator    (human loop here; computation in sdet-plan-runner @ opus)
        → sdet_plan.json + analysis.md + test_cases.csv
        │
   ── HUMAN REVIEW GATE (SDET / Feature Lead; CSV edits → SYNC) ──
        ▼
POST-BUILD
  /mobile-postbuild              (sequential pipeline)
    code-change-extractor → change_context.json + compliance.json
    impact-shortlister    → impact_shortlist.json
    test-code-generator   → TAPMIND_NLP → aep-tapmind:nlp-codegen;
                            GMT_JAVA here; data via /mobile-test-data-provisioner
```
Shared at both stages: **test-data-provisioner** (TestBuddy → GBT fallback → synthetic) —
still its own command, not folded into post-build.

## Design decisions baked in
- **Reuse:** app-agnostic skills + `config/<app>.json`. Add an app = copy `_template.json`, fill it.
- **Both platforms:** `element_id` → `android_locator` (resource-id) + `ios_locator` (accessibilityId), from `change_context`.
- **NLP-primary output:** TapMind steps are the default; GMT coded is emitted where NLP can't express a case. (Precondition for reliable NLP self-heal in Phase B: TapMind must expose step-level diagnostics + grounding.)
- **Grounding = the GMT coded repo** for *both* output forms (page objects/navigation live there; the TapMind repo alone is too thin).
- **Navigation:** prefer a PLAN **deeplink/state-injection hook** to reach the screen; fall back to a Design **flow** UI walk.
- **data_needs:** authored by the scenario generator (Impl. Planning) from PRD `data_signals` + boundaries; resolved by the provisioner (Code Generation). Coverage gate: every `data_signal` → ≥1 scenario.

## Model tiers (per SOP)
- Orchestrator `SKILL.md` files inherit the parent session — they never pin a model.
- Reasoning (Opus / `claude-opus-5` on Cursor): **sdet-plan-runner** only (accuracy-critical, ~1/EPIC).
- Fast (Sonnet / `claude-sonnet-5` on Cursor): the extractors, test-code-generator, setup, provisioner.
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

See `agents/sdet-plan-generator/workflow.md` and `anti_patterns.md`. JSON schema-only check:

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

Each `skills/<name>/SKILL.md` is a loadable skill (folder name = skill id) and becomes a
user-facing `/command`. Subagents in `agents/` are **not** commands. Schemas and config
are referenced with paths relative to the plugin root (`schemas/`, `config/`, `scripts/`).

### Claude Code (CLI / Desktop)

```
claude plugin marketplace add https://source.golabs.io/aep/skills.git
claude plugin install aep-mobile@aep
```

Then ask to **check aep-mobile dependencies** (or *"Run aep-mobile-setup and tell me what
is missing"*) — that routes to `mobile-context-extraction`, which runs the preflight first
and stops if you only asked for setup.

### Cursor

1. Install the plugin from the AEP marketplace (same repo as Claude Code), or symlink/copy
   `plugins/aep-mobile/.cursor/skills/` (or `plugins/aep-mobile/skills/`) into your project's
   `.cursor/skills/` or personal `~/.cursor/skills/`. Cursor subagents load from
   `.cursor/agents/` (declared in `.cursor-plugin/plugin.json`).
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
4. Ask the agent to **check aep-mobile dependencies** (same `mobile-context-extraction`
   setup-only path). python3 + jsonschema are needed by every skill; **BrowserStack MCP**
   is needed only by `regression-extractor` and SDET-plan upload, which hard-stop without
   it — the prd/rfc/design/task extractors run fine without it.

### Updating

Bump pulls require a version change in `.claude-plugin/plugin.json` / `.cursor-plugin/plugin.json`:

```
claude plugin update aep-mobile@aep    # Claude Code
```

Then restart your editor. In Cursor, reinstall or refresh the plugin if skills don't update.

### Using the skills

Skills auto-trigger from their description. Four user-facing commands:

| Command | What it does |
|---|---|
| `mobile-context-extraction` | Preflight + parallel PRD/RFC/design/task/regression extractors |
| `mobile-sdet-plan-generator` | Human-gated SDET plan (GENERATE → review → SYNC) |
| `mobile-postbuild` | Sequential code-change → impact-shortlist → test-code |
| `mobile-test-data-provisioner` | Shared TestBuddy provisioner (not folded into post-build) |

Or naturally in conversation:
> *"Extract the PRD context for this mobile feature"* → `mobile-context-extraction` (fires prd-extractor; skips missing inputs)
> *"Generate the SDET plan"* → `mobile-sdet-plan-generator`
> *"Run aep-mobile-setup and tell me what is missing"* → `mobile-context-extraction` (setup-only; stops after the preflight table)
> *"The build is in — generate the tests"* → `mobile-postbuild`
