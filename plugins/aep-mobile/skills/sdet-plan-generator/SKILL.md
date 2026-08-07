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

## Preflight — resolve, or record and continue
**Never stop, never guess.** Always produce the three deliverables. Never synthesise a missing
context from the others, never reconstruct one from the source PRD/RFC/Figma, and never let a
missing input pass unmentioned — generate what the available inputs support and say plainly
what was not covered.

1. **Schemas.** Read `${CLAUDE_PLUGIN_ROOT}/schemas/sdet_plan.schema.json` and
   `${CLAUDE_PLUGIN_ROOT}/schemas/scenario.schema.json`. Unreadable → `WORTH_CHECKING` note on
   `ENVIRONMENT`, action *"run `claude plugin update aep-mobile@aep`, restart Claude, re-run"*.
   Fall back to the field lists in this document **only** then, and say so in the note.
2. **Required contexts.** `prd_context.json` and `design_context.json`. Either missing → carry
   on with what remains and add a `NEEDS_ANSWER` note: *"generated without <name> — requirement
   coverage / screen coverage is unverified"*. Set `extraction_status: PARTIAL`.
3. **Optional contexts.** `rfc_context.json` and `plan_context.json` may legitimately be
   absent (no RFC, no impl plan) → `FYI` note, that is a normal run, not a problem. A file that exists but
   **fails its schema** is different: use what parses, and raise a `NEEDS_ANSWER` note naming the
   file and the validation error. Never silently downgrade malformed to absent.
4. **Inherit upstream notes.** Every input context carries its own `extraction_notes[]`. Copy all
   of them into this plan's `extraction_notes[]`, prefixing `field` with the source
   (`prd_context.business_requirements[3].target_module`). Upstream notes do not disappear
   because a downstream skill ran successfully.
5. **Resolve the app before picking files.** Extractors write per-app files when a source
   document covers more than one app: `prd_context.<app_id>.json`, `rfc_context.<app_id>.json`,
   `design_context.<app_id>.json` (a single-app run writes the plain `prd_context.json` /
   `rfc_context.json` / `design_context.json`). The forms can be mixed — a PRD may cover two
   apps while the design was exported per app already, so match each stage independently.
   - Plain files only → use them.
   - Per-app files present → **generate a plan for one app per run.** Ask the QA which app if
     they did not say, then load only that app's files. Never merge two apps' contexts into one
     plan: `deeplink_scheme`, locators and repos differ per app, so a merged plan is wrong for
     both.
   - Both forms present for the same stage → prefer the per-app file and raise an `FYI` note
     naming the plain file you ignored.
   Stamp the chosen `app` into `feature_metadata`, and suffix `feature_key` per app
   (`insurance_sdk_gopay`) so two runs' deliverables don't collide on import.
6. **App agreement.** Every context loaded for the run must carry the same `app`. A mismatch
   means files for different apps were mixed — pick nothing, use the majority value, and raise a
   `NEEDS_ANSWER` note naming the conflicting files and values.
7. **Shared requirements across apps.** When a source document covered several apps, items that
   apply to all of them carry the **same id in every file** (`req_id`, `risk_id`, `flag_key`,
   `endpoint`). Generate scenarios for them normally — they are in scope for this app too — and
   list those ids under a *Shared across apps* note in `<feature_key>_analysis.md`, so the QA
   reviewing both plans knows which scenarios are duplicates rather than distinct coverage.

## Anti-hallucination rules
- **Every scenario traces to a real field in a real input context.** No scenario may rest on a
  requirement, screen, element, flag or endpoint that is not present in a supplied context.
- Never invent `element_id` or `screen_id` values. If a scenario needs an element the design
  context does not carry, that is a `blocking_issues` entry, not a guessed token.
- Never invent a deeplink or test hook. Absent hook → the scenario states the manual
  navigation path and is flagged in testability feedback.
- A cross-stage contradiction (PRD says one thing, design another) is reported as a gap. Do
  **not** silently resolve it by preferring one source.
- A required schema field that cannot be satisfied from the inputs is **left absent** with a
  `NEEDS_ANSWER` note — never filled to make the output validate.

## Open points — reported in all three deliverables
The same notes must appear everywhere the QA might look; putting them only in the JSON does not
count, because nobody opens the JSON.

Frame them as **what the source documents left open**, not as problems with the plan. Most
features are planned from work-in-progress docs, so a list of open points is the expected
result — say so, rather than letting it read as a failed run.

**`<feature_key>_SDET_plan.json`** — `extraction_status` plus `extraction_notes[]`
(`{ field, reason, action, follow_up }`), including everything inherited from upstream.

**`<feature_key>_analysis.md`** — open with a section titled `## Inputs & Open Points` **before**
any scenario content. It contains:
- A one-line summary in plain words: *"Generated from the PRD and design. No RFC or impl plan
  was supplied. 4 open points below — 1 needs an answer before the tests can cover it."*
- An inputs table — each context, `Present / Not supplied / Could not be read`, and its status.
- A table of open points — `Follow-up | Field | What we found | Next step`, `NEEDS_ANSWER` first.
- A one-line legend directly under it so the labels explain themselves:
  *"NEEDS_ANSWER — someone has to supply this. WORTH_CHECKING — produced, but confirm it.
  FYI — the document doesn't cover this; no action needed."*
- A plain-language line naming what the plan therefore does **not** cover, e.g. *"No RFC was
  supplied, so no feature-flag, N-1 compatibility or API-error scenarios were generated."*

**`<feature_key>_test_cases.csv`** — when `extraction_status` is not `COMPLETE`, the first data
row is a non-executable marker row: `id` = `REVIEW-FIRST`, `title` = *"N open points (M need an
answer) — see analysis.md before importing"*, all other columns empty. It is a deliberate speed
bump: this CSV gets bulk-imported into TMS without the analysis doc ever being opened.

**Never report `extraction_status: COMPLETE` when any note is open**, and never describe coverage
as complete while `NEEDS_ANSWER` items remain.

---

## Matching the source document — normalise, don't invent
Source docs are human-written. Labels and values vary; the schema does not. Reading a value that
**is** in the document and expressing it in the schema's vocabulary is normalisation, and it is
required. Supplying a value the document does not contain is invention, and it is forbidden.
Do not confuse the two — refusing to normalise is not caution, it is a false open-point report.

**Field labels — match by meaning, not by key name.** Schema keys are output names, never strings
to search for. Look for the concept, whatever the doc calls it.

**Enum values — match case-insensitively, emit the canonical spelling.** Compare the document's
value to the schema's allowed values ignoring:
- letter case — `DRAFT`, `draft`, `Draft` all → `"Draft"`
- surrounding whitespace, and any trailing punctuation or checkbox glyph (`☑ DRAFT` → `"Draft"`)
- separator style — `state injection`, `state_injection`, `State-Injection` → `"state-injection"`

Emit the schema's exact spelling, never the document's. This applies to **every** enum in the
schema, not just the ones named here.

**Synonyms — allowed when unambiguous, recorded when used.** `In Progress` → `"In Review"` is a
fair mapping; make it, and add an `FYI` note noting the source value so the mapping is auditable.
A pure case or whitespace fix needs no note — it is not a judgement call.

**When nothing matches, say what you found.** If no allowed value fits even case-insensitively,
leave the field absent and make the note specific — quote the document's value and list the legal
ones: *"header reads `PRD WALKTHROUGH`; not a legal value (allowed: …)"*. Never report it as
*"not found"* — the field was found, its value could not be expressed, and those send the reader
to different places. Never pick the nearest-looking value to dodge the note.

## Execution Workflow

### 0. Test-Category Selection Gate
Before scenario expansion, partition all FE-mobile test categories into tiers using the **Category Catalog** (see Appendix), then confirm the selection with the QA. Auto-selection depends **only** on the supplied input docs — it is fully feature-agnostic (a payments feature and a static info screen will auto-select different sets off *their own* fields).

- **AUTO-SELECTED (locked baseline):** every category whose detection signal fires in the supplied contexts. These are always generated — they guarantee full coverage of what the inputs actually contain. They are NOT removable in the normal flow; an explicit QA override to drop one is recorded in `coverage_categories.user_removed` with a reason.
- **OPTIONAL EXTRAS (unticked), two sub-tiers:**
  - `feature_adjacent` — the category's trigger field exists in the schema but was empty/absent for this feature (e.g. `deep_link_nav` when every `rfc.navigation_changes[].deep_link` is null).
  - `fe_baseline` — universal FE-mobile hygiene NOT derivable from the docs (e.g. same-account multi-device login, forced sign-out, rotation, app upgrade). Offered **only** when the group's applicability predicate matches the feature surface.

**Never label a category "not eligible."** A no-signal category simply moves to the appropriate extras sub-tier.

Flow:
1. **Emit the Coverage Matrix** to the user as a markdown table: `Category | Tier (🔒 Auto / ☐ Extra-adjacent / ☐ Extra-baseline) | Why`. The "Why" cites the exact input field that fired (auto) or the field checked as empty/absent (extra). Reasons are generated from *which field fired*, so they are feature-agnostic.
2. **Confirm via `AskUserQuestion`** (multiSelect), grouped into ≤4 themed questions, ≤4 options each. State the AUTO set as locked coverage; ask the QA which OPTIONAL EXTRAS to add. Each option's description = its auto-reason/rationale.
3. **Headless / non-interactive fallback:** if no user is available to answer (e.g. CI), skip the prompt and proceed with the **AUTO** set only — never block generation.
4. **Generate scenarios for `auto_selected ∪ optional_extras_selected`.** Stamp each scenario with `coverage_category` and a `source` (`input_derived` for AUTO/feature_adjacent, `fe_baseline`, or `qa_added`). Record the whole decision in `coverage_categories` (see Output spec) and echo it in `<feature_key>_analysis.md`.

**Scope rule:** generate scenarios **only** for selected categories — EXCEPT the Hard Coverage Rules below, which always apply (every P0 requirement and every `boundary_conditions` entry keeps ≥1 scenario regardless of selection).

### 1. Ingest & Coverage Gates
- Ingest and aggregate whatever context inputs are provided (`plan_context`, `prd_context`, `design_context`, `rfc_context`).
- **Optional Input Absence Handling** (applies to `plan_context.json` and `rfc_context.json` only — `prd_context.json` and `design_context.json` are required, see Preflight step 2). If an *optional* context is not provided, **do NOT fail execution.** Drive the generation with whatever inputs are given:
  - If `plan_context.json` is absent, proceed with `prd_context.json` and `design_context.json` as the baseline.
  - State the missing contexts clearly as a limitation inside the `<feature_key>_analysis.md` report (e.g., *"plan_context.json was not provided; test hooks and specific code-change view models are excluded from this analysis."*).
  - A missing context also means its Category Catalog triggers simply cannot fire (no failure) — those categories fall through to the extras tiers.
  - **Absent is not the same as malformed.** A context file that exists but fails its schema gets a `NEEDS_ANSWER` note naming the file and the validation error (Preflight step 3) — never a silent fall-through to "treat as absent", which drops coverage the QA believes they have.
- **Hard Coverage Rules** — apply these as an explicit enumeration, NOT from memory. Iterate each input array and emit at least the required scenario(s) before doing anything else. Model-independence depends on this being a mechanical loop:
  - **For each** `prd.business_requirements[i]` → emit ≥1 scenario whose `requirement_ref` = that `req_id`. (A P0 requirement always keeps ≥1.)
  - **For each** `prd.boundary_conditions[i]` → emit ≥1 boundary scenario referencing that entry. Do NOT fold a boundary rule into an unrelated happy-path scenario as a substitute — it needs its own row. (This is the rule most often missed: e.g. a screenshot/privacy-mask boundary and a "shown once per customer" ordering boundary are distinct entries, each needing its own scenario.)
  - **For each** `rfc.lifecycle_considerations[i]` (if the lifecycle category is selected) → emit ≥1 scenario for that `event`.
  - **For each** feature flag in `rfc.experimentation_matrix[]` / `prd.feature_flags[]` (if the flag category is selected) → emit ≥1 kill-switch/toggle scenario.
  - Every scenario MUST carry a `requirement_ref` (the `req_id` / boundary index / event it satisfies) so Step 4 can audit coverage mechanically.
  - **Clickstream Telemetry Rules:** Clickstream verification is **NOT** a mandatory hard gate for the generator. If `clickstream_events` are explicitly provided/told in the input contexts, then generate $\ge 1$ verification step per event. If they are NOT provided or explicitly mentioned, **do NOT fail validation and do NOT generate telemetry tests.** Instead, simply list it as an Open Question / Clarification inside `<feature_key>_analysis.md` (e.g., *"Are clickstream telemetry events required for this feature?"*).
- Dedup against existing GMT/NLP tests retrieved from `${CLAUDE_PLUGIN_ROOT}/config/<app>.json` repository paths.

### 2. Scenario Expansion
Expand scenarios across:
- **Core**: Happy path, boundary, negative, and contract flows.
- **Mobile Extras**: Generates mobile-specific scenarios (deep-link navigation, regional variants, feature flag toggles) and applies **Conditional Mobile-Native Interruption Rules** to ensure test suites remain highly focused and are only generated when technically valid. These rules are the `interruption_*` / `local_data_migration` / `permission` detection triggers surfaced in Step 0 — only expand a category the gate selected:
  - **Network Loss / API Timeout**: Inject a poor-network or server-timeout scenario *only* if `rfc_context.json` declares active `api_contract_changes` or `plan_context.json` specifies `observable_states` (API success/failure signals). Skip if the touchpoint screen is entirely static/local.
  - **App Backgrounding & Process Death**: Inject a backgrounding/kill-and-restore state preservation scenario *only* if the screens in `design_context.json` contain interactive elements (inputs, forms, toggles) or view models are active in `plan_context.json`. Skip on purely static/read-only informational screens.
  - **Local Storage & DB Migration**: Inject an N-1 upgrade and schema migration scenario *only* if `rfc_context.json` defines active `local_data_changes` (e.g. SQLite, Room, CoreData, or SharedPrefs modifications).
  - **Runtime Permission Toggles**: Inject parallel Permission Granted vs Permission Denied scenarios *only* if `rfc_context.json` declares new or modified `permissions_required`.
- **FE-Baseline Extras**: If the QA selected any `fe_baseline` category in Step 0, expand best-effort hygiene scenarios for it, stamp `source: "fe_baseline"`, and record in analysis.md that expected behavior is not spec-derived and needs PM/dev confirmation.
- **Navigation Priority**: Prefer test hooks (`method:deeplink` or `hook_id`) over full UI walks.

### 3. Gap Analysis & Alignment Engine
As the single integration point, the generator must actively compute the following cross-stage gaps:
- **`prd_vs_figma_gaps`**: Cross-reference `prd_context.json` with `design_context.json`. Check `business_requirements[].context_screen` against Figma `screens[].screen_id`. Identify missing screens/frames, text copy mismatches, or personas with no design representation.
- **`prd_vs_rfc_gaps`**: Cross-reference `prd_context.json` with `rfc_context.json`. Compare PRD `feature_flags` against the RFC `experimentation_matrix` (finding flag key typos, missing defaults, or status mismatches). Verify business rule conditions align with RFC error codes or API paths.
- **`rfc_vs_impl_plan_gaps`**: Cross-reference `rfc_context.json` with the Implementation `plan_context.json`. Check if RFC architectural risks, local migrations, offline strategies, or required permissions are accounted for in the implementation's screens touched, view models, and components.
- **`element_locator_handoff`**: Map `screen_name:element_id_name` logical tokens to cross-platform accessibility attributes (`android_resource_id`, `ios_accessibility_identifier`, `flutter_key`). Only populate these fields if the matching locator values are provided by the upstream design/development context; do not use placeholders or "UNRESOLVED" strings.

### 4. Coverage Self-Audit Gate (MANDATORY — run before writing any output file)

This gate is what makes coverage model-independent: it does not rely on the model "remembering" to be thorough — it mechanically re-checks the generated scenario set against the inputs and forces a fix before output. Run it every time, in both interactive and headless modes.

**4a. Build the required-coverage checklist** directly from the inputs (this is a deterministic list, not a judgment):
- every `prd.business_requirements[].req_id`
- every `prd.boundary_conditions[]` entry (by index + `req_id` + `edge_case_description`)
- every `rfc.lifecycle_considerations[].event` (if lifecycle selected)
- every flag in `rfc.experimentation_matrix[]` / `prd.feature_flags[]` (if flag category selected)
- every event in `prd.clickstream_events[]` / `rfc…observability.clickstream_events[]` **only if** such a structured array is non-empty (per the Telemetry Rules — never invent this list)

**4b. Match generated scenarios to the checklist** using each scenario's `requirement_ref`. Produce a coverage map: `checklist_item → [scenario titles covering it]`.

**4c. If any checklist item has zero covering scenarios → the plan is INCOMPLETE.** Do not write the output files yet. Generate the missing scenario(s), then re-run 4b. Repeat until every item is covered. A boundary rule "covered" only by being mentioned inside an unrelated scenario does NOT count — it needs a scenario whose `requirement_ref` names it.

**4d. Emit the audit result** into the SDET plan as a `coverage_audit` object and echo it as a table in `<feature_key>_analysis.md`:
```
"coverage_audit": {
  "required": { "business_requirements": [...], "boundary_conditions": [...], "lifecycle_events": [...], "feature_flags": [...], "clickstream_events": [...] },
  "covered": { "<checklist_item>": ["<scenario title>", ...], ... },
  "gaps_closed_in_this_pass": ["<item that was missing and got a new scenario>", ...],
  "still_blocked": [ { "item": "...", "reason": "expected behavior undefined (e.g. OQ-open)" } ]
}
```
An item may legitimately remain uncovered ONLY if its expected behavior is undefined in every input (e.g. an OPEN open-question). In that case it goes in `still_blocked` with the reason — it is never silently dropped.

**Determinism note:** two different models running this gate on the same inputs must arrive at the same `required` checklist and the same set of items in `covered` vs `still_blocked`. Scenario *wording* may differ between models; scenario *coverage* must not.

---

## Output File Specifications

Generate the following files in the current working directory, naming them dynamically using the `<feature_key>` defined in `feature_metadata`. The first three are always produced in `GENERATE`/`SYNC` mode; the fourth (`automation_plan_generator.json`) is produced on CSV feedback, per the *Automation-Plan-Generator emission* section:

### 1. `<feature_key>_SDET_plan.json`
Full machine-readable master payload conforming strictly to `${CLAUDE_PLUGIN_ROOT}/schemas/sdet_plan.schema.json`. Must include `created_at` and `updated_at` ISO date-time timestamps.

Must also include the `coverage_categories` object produced by Step 0:
- `auto_selected[]` — `{ category, reason }` where `reason` = the exact input field that fired (e.g. `"rfc.lifecycle_considerations[0].event = PROCESS_DEATH"`).
- `optional_extras_available` — `{ feature_adjacent[] , fe_baseline[] }`.
- `optional_extras_selected[]` — categories the QA ticked.
- `user_removed[]` — `{ category, reason }` for any AUTO category the QA explicitly overrode out of scope.

It must also include the `coverage_audit` object produced by Step 4 (the mechanical coverage proof).

Generate scenarios ONLY for `auto_selected ∪ optional_extras_selected`, and tag each scenario with `coverage_category` + `source`. Every scenario also carries a `requirement_ref` linking it to the checklist item it satisfies.

#### Lossless carry-over — never drop extractor data
The SDET plan is a **superset** of its inputs, not a lossy summary. Every field the extractors
produced must survive into the plan.
- Map each extractor field to its proper schema home first (a PRD business rule → a scenario, a
  persona → `test_data`, an RFC flag → coverage + `test_data`, etc.).
- **Anything you cannot place in a defined field goes into the top-level `unmapped_extractor_data`
  object, verbatim**, keyed by source (`prd` / `rfc` / `design` / `plan`). Do not summarise,
  truncate, or paraphrase it — copy it as received.
- `unmapped_extractor_data` is `{}` only when genuinely everything mapped cleanly. If you find
  yourself about to discard an extractor field because "there's no field for it", that field
  belongs in `unmapped_extractor_data` instead. Dropping it is never the answer.
- This is a safety net, not a dumping ground: prefer the real field. The bucket exists so that a
  schema gap can never silently lose information the QA supplied.

#### `test_data` — structured, sourced from PRD + RFC (replaces `test_data_tags`)
Each scenario carries a `test_data` array (was `test_data_tags`). One entry per fixture, built
from the structured upstream fields — **not** flattened to tag strings:
- `required_state` is assembled from `prd_context.target_personas[].prerequisites` and
  `boundary_conditions`, expressed as structured predicates
  (`"KYCed GoPay user"` + prereq `"confirmed Date of Birth"` → `{ "kyc_status": "VERIFIED",
  "gopay_active": true, "date_of_birth": "CONFIRMED" }`). Restate the source in schema vocabulary;
  never invent an attribute the source doesn't state.
- `type_signals` carries the short labels that used to be `test_data_tags`
  (`["kyc_verified_user","birthday_d_day"]`). They summarise; `required_state` is the source of
  truth. Keep both.
- **Conditions that are not static entity attributes** — a birthday-on-D-day, an N-th
  transaction, any clock- or relationship-dependent need — go in `dynamic_conditions` with the
  right `kind` (`TEMPORAL` / `RELATIONAL` / `SELECTION`), **not** in `required_state`. Forcing
  `birthday_d_day` into `required_state` produces a predicate no test-data category can match.
- `fixture_id` is stable and reused across scenarios needing the same entity+state, so downstream
  can dedup. `source_refs` traces every fixture back to the PRD/RFC field it came from.
- Absent test-data need → `test_data: []`. Never fabricate a fixture to fill the array.

### 2. `<feature_key>_analysis.md` (QA Analysis Asset)
A human-readable Markdown asset automatically generated for engineering leads detailing parsed requirements gaps, architectural risks, and testability bottlenecks during the pre-build review.

**Note: Do NOT include individual scenario/test cases here.** Instead, you must match the exact structural layout, depth, and tone of the gold-standard **`birthday_feature_analysis best.md`** blueprint:

#### **Required Document Sections & Formatting**:

1. **Meta Header:**
   - Include clear, bold rows: **Feature Key**, **App**, **RFC (ID, Title, Status)**, **Analysis Date**, **SDET Plan File**, **Test Cases File**.

2. **Section 0: Selected Test Coverage Categories:**
   - A table mirroring `coverage_categories` with columns: `Category`, `Tier` (`Auto` / `Extra — feature-adjacent` / `Extra — fe_baseline`), `Selected?`, and `Why` (the field that fired, or why it was offered as an extra).
   - Note explicitly which extras were QA-added and that `fe_baseline` scenarios are hygiene, not spec-backed.
   - Immediately after the category table, render the **Coverage Audit table** from `coverage_audit`: one row per required checklist item (`Item`, `Type`, `Covered By` (scenario titles), `Status` = Covered / Blocked-with-reason). This is the reviewer-facing proof that every requirement and boundary rule has a scenario.

3. **Section 1: Missing Input Context:**
   - If any input context (like `plan_context.json` or `rfc_context.json`) is absent, list it and detail the exact consequences (e.g., missing test hooks, uncomputed gaps, unpopulated platform-specific locator attributes in JSON).

4. **Section 2: Cross-Stage Gap Analysis:**
   - **PRD vs Figma Gaps Table:** Must contain columns: `Req` (Requirement ID), `Severity` (`CRITICAL_BLOCKER` or `WARNING`), and `Gap` (highly detailed, context-aware analysis of broken prototype links, un-designed flows, dynamic text copy verification requirements).
   - **PRD vs RFC Gaps Table:** Must contain columns: `Req` and `Gap` (outlining architectural drift, scoped platform changes like Flutter single-build vs separate builds, feature flag mismatches, and specific environment IDs).
   - **RFC vs Implementation Plan Gaps:** List exact technical elements that require verification (e.g., specific cache invalidation strategies, database migrations with keys, lifecycle state preservation, and required Android/iOS permissions).

5. **Section 3: Architectural & Testability Risks Table:**
   - Columns: `Risk ID`, `Severity` (`Critical`, `High`, `Medium`, `Low`), `Description`, and `Testing Implication` (detailing specific manual/automated testing approaches to mitigate the risk). Focus on caching, state sync, stale name values, etc.

6. **Section 4: Open Questions & Clarifications:**
   - Must be categorized explicitly by current blocker status and owner:
     - **Blocked — Awaiting PM / Design Input Table** (Columns: `ID`, `Question`, `Test Impact`)
     - **Blocked — Awaiting Dev / RFC Author Input Table** (Columns: `ID`, `Question`, `Test Impact`)
     - **Resolved — Unblocked for Testing Table** (Columns: `ID`, `Resolution`, `Test Action`)
     - **Additional Clarifications Needed (for PM)** (Detailed bullet points covering telemetry payload schemas, copy approvals, sound packages, third-party libraries).

7. **Section 5: SDET Readiness & Testing Plan:**
   - **Environment Requirements Table:** (Columns: `Item`, `Specification`) detailing App, target release environment configs, kill switch flags, and local/time zones.
   - **Test Data Requirements Table:** (Columns: `Tag`, `Description`) mapping exact user segments, verification states, device permissions, and system configurations (e.g., `gallery_permission_denied`, `no_card_selected`).
   - **Device Matrix:** Reference targets from the configuration (e.g., `Pixel 7`, `iPhone 14`).
   - **Dependencies Before Test Execution:** Bullet points of absolute prerequisites (finalized copy, manifest declarations, design updates).
   - **Execution Guidelines:** Highly technical, actionable testing recipes detailing manual and automated procedures (e.g., using `adb shell am kill` for process death, configuring proxy tools like Charles Proxy or mitmproxy for network interception, and real physical device instructions).

> Sections 1–5 keep their original meaning and internal references; Section 0 is additive and appears directly after the Meta Header.

### 3. `<feature_key>_test_cases.csv`
Flattened CSV strictly matching squad project template headers:

`Title`, `State`, `Priority`, `Type of Test Case`, `Automation Status`, `Preconditions`, `Steps`, `Expected Result`, `Execution Mode`, `Platform`, `Country v2`, `Android Automation Status v2`, `iOS Automation Status v2`, `TestType`

**Column Value Directives**:
- `Title`: Concise scenario description.
- `State`: `"Active"`
- `Priority`: `"P0"`, `"P1"`, or `"P2"`
- `Type of Test Case`: `"Regression"` or `"Sanity"`
- `Automation Status`: By default, set to `"Manual"` (representing not-automated) for newly generated test cases. Set to `"Automated"` only if matched with an existing automated test case.
- `Preconditions`: Multiline string with environment, locale, deep links, and active feature flags, **using a new line break (`\n`) after each statement/line.** Any feature-flag name written here MUST be copied verbatim from `rfc.experimentation_matrix[].flag_key` / `prd.feature_flags[]` — never paraphrase or append suffixes (e.g. do not turn `birthday_feature_litmus` into `birthday_feature_litmus_content`).
- `Steps`: Numbered sequential actions inside double quotes with line breaks (`\n`). **Write steps using clean, action-oriented, declarative NLP-style commands** (e.g., `1. Open deeplink "gopay://affiliate/welcome"`, `2. Enter "CODE123" into "Referral Code"`, `3. Tap "Lanjut"`). Never use long, vague prose or technical automation/logical IDs (e.g., do NOT write `Tap WELCOME_PAGE.TAP_BUTTON_CTA`; instead, write `Tap "Daftar Program Affiliate"`). Must include telemetry emission checks.
- `Expected Result`: Numbered sequential assertions matching the numbered steps in the `Steps` column 1-to-1, inside double quotes with line breaks (`\n`) after each statement. **Write assertions using clean, declarative NLP-style verification commands** (e.g., `1. Verify "Confirm Account" is visible`, `2. Verify "Error: Code incorrect" is visible`). Describe functional and telemetry outcomes in user-friendly, non-technical language.
- `Execution Mode`: `"Automatable"` or `"Manual"`
- `Platform`: `"Android"`, `"iOS"`, or `"Cross-Platform"`
- `Country v2`: MUST be derived from `prd.applicable_countries` (map ISO code → name, e.g. `ID`→`"Indonesia"`, `SG`→`"Singapore"`, `VN`→`"Vietnam"`). Never pick a country the inputs do not list. If `applicable_countries` has one entry, every row uses that country.
- `Android Automation Status v2`: By default, set to `"Manual"` (or `"N/A"` if platform is iOS-only). Set to `"Automated"` only if matched with an existing automated Android case.
- `iOS Automation Status v2`: By default, set to `"Manual"` (or `"N/A"` if platform is Android-only). Set to `"Automated"` only if matched with an existing automated iOS case.
- `TestType`: always the literal `"Story"` for every row. Do NOT substitute `"FCT"`, `"Non-FCT"`, or any other value.

> **Enum validation (run as part of the Step 4 gate):** before writing the CSV, verify every row's `State` / `Priority` / `Type of Test Case` / `Execution Mode` / `Platform` / `TestType` / `Country v2` holds only a value allowed above; reject and fix any other value.

---

## Validate — report, never block
```
python3 -c "import json,jsonschema; jsonschema.validate(
  json.load(open('<feature_key>_SDET_plan.json')),
  json.load(open('${CLAUDE_PLUGIN_ROOT}/schemas/sdet_plan.schema.json')))"
```
- Passes and `extraction_notes` is empty → `extraction_status: COMPLETE`.
- Fails → **still write all three files.** Convert each validator error into an
  `extraction_notes` entry (`field` = the validator's JSON path, `follow_up: NEEDS_ANSWER`), set
  `extraction_status: PARTIAL`, and carry it into the analysis doc's gap table. Never patch
  a value in just to make validation pass.
- Validator unavailable (`jsonschema` not installed) → write the files, add a `WORTH_CHECKING` note on
  `ENVIRONMENT`, **and say so in your reply to the user** — not only in the JSON, which they may
  not open. Give them the command for their platform:
  - macOS / Linux with a system Python: `pip3 install --break-system-packages jsonschema`
    (plain `pip3 install` fails with an *externally-managed-environment* error under PEP 668)
  - inside a virtualenv, or with `uv`: `pip install jsonschema` / `uv pip install jsonschema`
  Never report an unvalidated output as valid — well-formed JSON is not schema conformance.
  Do not attempt the install yourself; it is the user's environment to change.

Also validate each **input** context against its own schema during Preflight, with the same
report-never-block rule — an upstream file that fails validation gets a `NEEDS_ANSWER` note naming
the file and the error.

In `SYNC` mode, validate the emitted `<feature_key>_automation_plan_generator.json` against
`${CLAUDE_PLUGIN_ROOT}/schemas/automation_plan_generator.schema.json` the same way — write it even
on failure, record the validator error, and never report an unvalidated handoff as valid.

---

## Bidirectional Sync Workflow

The skill supports a two-way synchronization flow to allow human QA to review, refine, and add test cases manually in the CSV, and feed those corrections back to keep the master JSON in perfect alignment.

### Execution Modes

1. **`GENERATE` Mode (Default):**
   - **Trigger:** Upstream extractor contexts are provided as input.
   - **Action:** Generates `<feature_key>_SDET_plan.json`, `<feature_key>_analysis.md`, and `<feature_key>_test_cases.csv` from scratch.

2. **`SYNC` Mode (Reverse Sync + automation-plan emission):**
   - **Trigger:** A modified `<feature_key>_test_cases.csv` is uploaded/provided as input. The skill automatically reads the existing `<feature_key>_SDET_plan.json` directly from the working directory.
   - **Action:** Parses the modified CSV and merges all human edits back into `<feature_key>_SDET_plan.json` strictly following these reconciliation rules:
     - **Mapping Anchor:** Correlate rows in the CSV to scenario objects in `<feature_key>_SDET_plan.json` using `Title` $\leftrightarrow$ `csv_title_association` as the primary key.
     - **Synchronize Overridden Properties:** If the human QA modified fields in a correlated CSV row (e.g., changed `Automation Status` from "Manual" to "Automated", tweaked `Execution Mode` from "Manual" to "Automatable", altered priority, or edited steps), update those exact property values in `<feature_key>_SDET_plan.json` to match the CSV.
     - **Ingest New Manual Scenarios:** If a row exists in the CSV but has no matching `csv_title_association` in `<feature_key>_SDET_plan.json`, it represents a new test case added by the QA. Create a new scenario object for it inside `<feature_key>_SDET_plan.json` with:
       - `is_legacy_regression: true`
       - `automatable: false`
       - `source: "qa_added"`
       - All standard properties parsed from the CSV columns.
     - **Preserve Un-mapped Context Metadata:** Advanced technical properties inside `<feature_key>_SDET_plan.json` (such as `mapped_user_flow`, `test_data`, `unmapped_extractor_data`, `clickstream_events`, `coverage_category`, `source`, `requirement_ref`, the top-level `coverage_categories` / `coverage_audit` blocks, or specific `target_execution_framework` metadata) which do not exist in the flat 15-column CSV layout **must be preserved verbatim** for existing scenarios. Do not delete or overwrite them.
     - **Re-run the Step 4 Coverage Self-Audit** after merging and refresh the `coverage_audit` block, so QA-added/removed rows keep the coverage proof accurate.
     - **Update Timestamps:** Automatically update the `updated_at` timestamp in `<feature_key>_SDET_plan.json` to reflect the synchronization event.
   - **Then emit the automation plan.** After the merge, run the *Automation-Plan-Generator emission* below — the CSV feedback is precisely the trigger to (re)produce `<feature_key>_automation_plan_generator.json` for the downstream Test-Data-Generation stage.

---

## Automation-Plan-Generator emission (Test-Data-Generation handoff)
When the QA feeds the edited CSV back, the point of the round-trip is to produce the handoff the
Backend QA Test-Data-Generation RFC consumes. Emit `<feature_key>_automation_plan_generator.json`
conforming to `${CLAUDE_PLUGIN_ROOT}/schemas/automation_plan_generator.schema.json`.

**Build from the synced JSON, never from the raw CSV.** The CSV has no test-data column, so the
fixtures only exist in `<feature_key>_SDET_plan.json`. Order of operations: SYNC the CSV into the
JSON first (above), then emit from that merged JSON. The JSON is the single source of truth; the
CSV only carried the QA's column edits.

**Filter.** Include a scenario **only if its post-sync `execution_mode` is `Automatable`.** Manual
scenarios stay in the SDET plan and are omitted from the automation plan. (For a purely backend
consumer you may additionally scope to `execution_scope` ∈ {`BACKEND_ONLY`, `END_TO_END`}; state
it if you do.)

**Field mapping** (SDET scenario → automation_scenario):
- `scenario_id` — assign `SC-001`, `SC-002`… in scenario order; **reuse the same id on
  re-generation** so downstream references stay valid.
- `requirement_ref` → `requirement_ref`; `csv_title_association` → `description`;
  `is_legacy_regression` → `is_legacy_regression`; `target_execution_framework` →
  `target_framework` (verbatim); `execution_scope` → `execution_scope`;
  `preconditions_metadata.target_environment` → `environments`.
- **`test_data` is carried straight across** — copy each fixture's `fixture_id`, `description`,
  `required_state` (and `entity`/`dynamic_conditions`/`count` if present) **verbatim**. Do NOT
  re-derive `required_state` here; it was already assembled at generation time. Emit the
  identification INPUT only — never add `test_data_output`, that is the test-data stage's job.
- `epic_id` — the EPIC/Jira id from `feature_metadata` if present, else `feature_key`.

**Backend-only fields** (`service_name`, `package`, `test_class`, `assertion_class`, `endpoint`,
`curl_reference`) — a mobile SDET plan does not carry these. **Never fabricate them.** Emit them
only when the plan actually has the value. When a `BACKEND_ONLY`/`END_TO_END` scenario needs one
that is absent, omit the field and add an `emit_notes` entry (`follow_up: NEEDS_ANSWER`) naming
the scenario and field. For `FRONTEND_ONLY` scenarios they are simply not applicable — no note.

**Validate** the emitted file against its schema with the same report-never-block rule as every
other output: on failure, still write it, record the validator error, and say so.

---

## Appendix: Category Catalog

The auto/extra partition is computed **solely** from the presence/values of schema fields across the supplied contexts — it is feature-independent. For each category: evaluate its trigger; if it fires → `auto_selected` (with the field as `reason`); if it does not → `optional_extras.feature_adjacent`. Universal hygiene categories with no schema trigger live in `optional_extras.fe_baseline`, gated by an applicability predicate.

### A. Detection Rules (AUTO when the field fires)

| Category | AUTO when |
|---|---|
| `functional` / `positive` | `prd.business_requirements[]` non-empty **or** `design.screens[]` non-empty |
| `negative_error` | `prd.boundary_conditions[]` has invalid/edge entries **or** any `rfc.api_contract_changes[].error_codes` |
| `boundary` | `prd.boundary_conditions[]` non-empty |
| `permission` | `rfc.permissions_required[]` non-empty **or** any design element's `validations_and_edge_cases` mentions a permission |
| `interruption_network` | `rfc.api_contract_changes[]` non-empty **or** `plan.observable_states` present **or** `rfc.offline_behavior.offline_capable`/`sync_strategy` **or** a network/remote-asset `architectural_risk` |
| `interruption_lifecycle` (background/process-death) | `rfc.lifecycle_considerations[]` non-empty **or** design has interactive elements (input/toggle/form/carousel) **or** `plan` active view-models |
| `local_data_migration` (N-1) | `rfc.local_data_changes[]` with non-null `migration_version`/`migration_strategy` **or** `rfc.compatibility_mandates[]` non-empty |
| `feature_flag_killswitch` | `rfc.experimentation_matrix[]` **or** `prd.feature_flags[]` **or** `plan.feature_flags` non-empty |
| `deep_link_nav` | `plan` test hook `method:deeplink` **or** any `rfc.navigation_changes[].deep_link` non-null |
| `telemetry_clickstream` | `prd.clickstream_events[]` **or** `rfc.cross_cutting_concerns.observability.clickstream_events[]` non-empty |
| `localization_regional` | `prd.applicable_countries.length > 1` **or** multiple locales / localized copy in design |
| `platform_variance` | `rfc.platform_specific.android`/`.ios` non-null **or** `target_platforms.length > 1` |
| `theming_darkmode` | design theme-state variants **or** an `open_question` matching theme/dark-mode |
| `accessibility` | `rfc.accessibility_impacts[]` non-empty |
| `non_functional_perf` | `rfc.cross_cutting_concerns.performance` has any non-null target/impact |
| `offline` | `rfc.offline_behavior.offline_capable == true` **or** a `sync_strategy` present |

> A category whose trigger does NOT fire → `optional_extras.feature_adjacent` (rationale = the field checked was empty/absent). A missing context file simply means its triggers cannot fire — no failure.

### B. FE-Baseline Extras Library (`fe_baseline` pool; offer only when the predicate matches)

| Group | Categories | Offer only if… |
|---|---|---|
| `session_auth` | `multi_device_concurrent_login`, `forced_signout_mid_flow`, `session_expiry`, `logout_during_flow` | feature needs auth/identity (design uses login/AuthSDK, or `prd.target_personas` require an account) |
| `app_upgrade` | `n_minus_1_upgrade`, `fresh_vs_upgrade`, `uninstall_reinstall`, `data_migration` | app ships incrementally (always true for the 5 GoTo apps) |
| `device_env` | `rotation`, `split_screen`, `font_scaling`, `low_storage`, `low_battery`, `system_locale_tz_change` | screens not locked-portrait in `config.<app>.json` |
| `os_interruptions` | `incoming_call`, `notification_shade`, `background_foreground`, `permission_revoked_runtime`, `network_flip` | any interactive/networked screen |
| `nav_gesture` | `hardware_back`, `deeplink_tamper`, `up_navigation`, `restore_after_death` | any multi-screen flow |
| `privacy_security` | `screenshot_screenrecord`, `background_snapshot_mask`, `clipboard_exposure`, `log_leakage` | UI shows sensitive data (`rfc…data_sensitivity`, balance/PII) |
| `a11y_baseline` | `screenreader_traversal`, `contrast`, `touch_target` | any interactive screen |
| `l10n_baseline` | `rtl`, `string_truncation`, `number_date_currency` | `config.<app>.json` supports the relevant locale surface |
| `resilience` | `double_tap_debounce`, `offline_cold_start`, `empty_error_states` | any networked/stateful screen |

> When a `fe_baseline` extra is selected, generate best-effort hygiene scenarios, stamp `source: "fe_baseline"`, and note in `analysis.md` that expected behavior is not spec-derived and needs PM/dev confirmation.

---

## Guardrails
- **Strict Determinism**: Do not extrapolate, infer, or hallucinate missing requirements. Map inputs directly to schemas without adding unmentioned fields or assumptions.
- **No Fabricated Values (provenance rule)**: Every concrete identifier in the output — feature-flag keys, Litmus/experiment release IDs, deep-link URIs, clickstream event names, API paths, error codes, permission names — MUST be traceable to a specific input field. If a value is not present in any provided context, write `TBD — not in context` (or omit the field / use `null` where the schema allows) and record it as an Open Question in `<feature_key>_analysis.md`. Never invent a plausible-looking value (e.g. a UUID release ID or an event name like `birthday_animation_viewed`) to fill a gap. Clickstream event names in particular come ONLY from a non-empty `clickstream_events` array; if that array is empty, do not name events (per the Telemetry Rules).
- **Category Gate**: AUTO-SELECTED categories (signal-derived) are the mandatory baseline and are always covered; only OPTIONAL EXTRAS are QA-discretionary. Generate for `auto_selected ∪ optional_extras_selected`. The P0 and boundary Hard Coverage Rules override the gate and are always covered.
- **Coverage Audit is blocking**: The Step 4 Coverage Self-Audit Gate MUST pass (every checklist item either `covered` or in `still_blocked` with a reason) before any output file is written. Coverage is a mechanical property of the inputs, not a model judgment — two different models must produce the same `required` checklist and the same covered/blocked partition, even if scenario wording differs.
- **Baseline Determinism**: `fe_baseline` scenarios are curated hygiene, NOT input-derived requirements — stamp `source: "fe_baseline"` and note in `analysis.md` that expected behavior needs PM/dev confirmation. Never present them as spec-backed requirements.
- **Contract Adherence**: Fail explicitly if *all* context files are missing or if essential keys within provided contexts are missing. However, do NOT fail if individual files (like `plan_context.json` or `rfc_context.json`) are absent; instead, proceed with the inputs that are provided, noting the missing contexts in `<feature_key>_analysis.md`.
- **Format Precision**: Outputs must strictly conform to `sdet_plan.schema.json` and the 15-column squad CSV schema without altering column headers or ordering.
- **Frontend Focus**: Test cases/scenarios must be generated *exclusively* for Frontend (FE) context (e.g., client-side UI, mobile views, offline transitions, local error copy, and client-side telemetry verifications). Do not generate backend-only validation or server-side test cases.