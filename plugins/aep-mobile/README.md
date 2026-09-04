# Mobile QA skills — Agentic PDLC (all 5 GoTo apps)

A production skill set for the **frontend / mobile** QA track, reusable across **Gojek Consumer,
Gojek Driver, GoFood Merchant, GoPay Consumer, GoPay Merchant**. Two entry-point skills;
extraction/generation/provisioning logic lives in model-pinned `agents/`.
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
  skills/                       ← 2 user-facing SKILL.md (orchestrators only)
    mobile-sdet-plan-generator · mobile-postbuild
  agents/                       ← instruction bodies + Claude Code model pins (sonnet / opus)
    prd-extractor · rfc-extractor · design-extractor · task-extractor
    regression-extractor · setup · sdet-plan-runner
    code-change-extractor · impact-shortlister · test-code-generator
    test-data-provisioner       ← spawned by test-code-generator (not a /command)
  agents-cursor/                ← thin Cursor stubs only (same names; pin Cursor model IDs)
  examples/gojek-consumer-save20/   ← worked example across the whole pipeline
```

## Pipeline & run order
```
PRE-BUILD
  /mobile-sdet-plan-generator    (setup → parallel extractors → human loop;
                                  computation in sdet-plan-runner @ opus)
    prd-extractor        → prd_context.json
    design-extractor     → design_context.json        (frontend-primary)
    rfc-extractor        → rfc_context.json            (optional — skip if no RFC)
    task-extractor       → task_context.json           ★ PRIMARY DRIVER (+ test hooks/deeplinks)
    regression-extractor → regression_context.json     (BrowserStack; skip if MCP down)
        │
        ▼
        sdet-plan-runner → sdet_plan.json + analysis.md + test_cases.csv
        │
   ── HUMAN REVIEW GATE (SDET / Feature Lead; CSV edits → SYNC) ──
        ▼
POST-BUILD
  /mobile-postbuild              (sequential pipeline)
    code-change-extractor → change_context.json + compliance.json
    impact-shortlister    → impact_shortlist.json
    test-code-generator   → TAPMIND_NLP → aep-tapmind:nlp-codegen; GMT_JAVA here
         └─ test-data-provisioner (agent) → TestBuddy handles
```
**test-data-provisioner** is an agent (not a `/command`), spawned by `test-code-generator`.

## Design decisions baked in
- **Reuse:** app-agnostic skills + `config/<app>.json`. Add an app = copy `_template.json`, fill it.
- **Both platforms:** `element_id` → `android_locator` (resource-id) + `ios_locator` (accessibilityId), from `change_context`.
- **NLP-primary output:** TapMind steps are the default; GMT coded is emitted where NLP can't express a case. (Precondition for reliable NLP self-heal in Phase B: TapMind must expose step-level diagnostics + grounding.)
- **Grounding = the GMT coded repo** for *both* output forms (page objects/navigation live there; the TapMind repo alone is too thin).
- **Navigation:** prefer a PLAN **deeplink/state-injection hook** to reach the screen; fall back to a Design **flow** UI walk.
- **data_needs:** authored by the scenario generator (Impl. Planning) from PRD `data_signals` + boundaries; resolved by the provisioner (Code Generation). Coverage gate: every `data_signal` → ≥1 scenario.

## Model tiers (per SOP)
- Orchestrator `SKILL.md` files inherit the parent session — they never pin a model.
- Edit logic only in `agents/*.md`. `agents-cursor/` is pin-only stubs for Cursor Desktop
  (same agent names; they load the shared body from `agents/`).

| Role | Claude Code (`agents/`) | Cursor (`agents-cursor/`) |
|---|---|---|
| Extractors, setup, postbuild agents | `sonnet` | `composer-2.5` (stand-in for Sonnet) |
| SDET plan runner | `opus` | `claude-opus-5` |

- Claude Code discovers `agents/` by default. Cursor loads `agents-cursor/` via
  `.cursor-plugin/plugin.json`. Skills stay shared under `skills/`.
- Escalate fast → reasoning only on ambiguity / repeated failure.

## Test data (TestBuddy)
The `test-data-provisioner` **agent** calls the **TestBuddy MCP** as the source of truth — e.g.
`CustomerAgent` (GoPay balance/recharge, segments, saved address, token), `VoucherAgent` (SAVE20),
`BookingAgent`, `DriverAgent`, `PaymentAgent` (dynamic QR). GBT builder fallback for states
TestBuddy lacks; synthetic for sensitive (KYC/PII). Always returns handles, never raw values;
secrets from vault. Invoked by `test-code-generator`, not as a user command.

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
is missing"*) — that routes to `mobile-sdet-plan-generator`, which runs the preflight first
and stops if you only asked for setup.

### Cursor

1. Install the plugin from the AEP marketplace (same repo as Claude Code), or symlink/copy
   `plugins/aep-mobile/skills/` into your project's `.cursor/skills/` or personal
   `~/.cursor/skills/`. Subagents load from `agents-cursor/` (declared in
   `.cursor-plugin/plugin.json`); each stub follows the shared body in `agents/`.
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
4. Ask the agent to **check aep-mobile dependencies** (same `mobile-sdet-plan-generator`
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

Skills auto-trigger from their description. Two user-facing commands:

| Command | What it does |
|---|---|
| `mobile-sdet-plan-generator` | Setup + parallel extractors + human-gated SDET plan (GENERATE → review → SYNC) |
| `mobile-postbuild` | Sequential code-change → impact-shortlist → test-code (TDP agent inside) |

Or naturally in conversation:
> *"Extract the PRD context for this mobile feature"* → `mobile-sdet-plan-generator` (fires prd-extractor; skips missing inputs; stops if you only asked to extract)
> *"Generate the SDET plan"* → `mobile-sdet-plan-generator` (extracts first, then GENERATE)
> *"Run aep-mobile-setup and tell me what is missing"* → `mobile-sdet-plan-generator` (setup-only; stops after the preflight table)
> *"The build is in — generate the tests"* → `mobile-postbuild`
