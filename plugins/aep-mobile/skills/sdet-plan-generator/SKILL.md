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
- **`regression_context.json`**: **Generator-internal, not a QA-supplied file.** Produced by invoking the `regression-extractor` skill from *within* this generator (Preflight step 9), before any scenario is created — never something the QA hands in alongside the other four contexts.

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
   - **Also inherit `design_context.project_context.blocking_issues[]`.** Each blocker becomes (a)
     an `extraction_notes` entry with `follow_up: NEEDS_ANSWER` (a design blocker blocks test
     authoring), and (b) a row in `<feature_key>_analysis.md` **Section 4 → Blocked — Awaiting PM /
     Design Input**. A design blocker also forbids inventing the screen/element it names — it routes
     to `blocking_issues`, consistent with the anti-hallucination rule.
   - **Read `design_context.project_context.overall_ambiguity_rating`** as a confidence signal, never
     a gate — scenarios still generate. `HIGH` → add a `NEEDS_ANSWER` note ("design ambiguity HIGH —
     screen/element-derived scenarios need design confirmation before automation") and set
     `extraction_status: PARTIAL`. `MEDIUM` → a `WORTH_CHECKING` note. `LOW` → nothing. Surface the
     rating on a row in analysis.md Section 5 (SDET Readiness).
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
7. **Team resolution — one team per plan.** Collect distinct `team_name` values across
   `prd_context.business_requirements[]`. Requirements with no `team_name` are **shared** — they
   stay in scope for every team's plan.
   - **One team (or none)** → proceed; no prompt needed. If every requirement has the same
     `team_name`, or none have one at all, there is nothing to disambiguate.
   - **Two or more teams** → ask the QA via `AskUserQuestion`: *"PRD contains requirements from
     N teams: [list]. Which team should this SDET plan cover?"* Options = the distinct team
     names. Once selected:
     - Filter `business_requirements[]` to keep only requirements where `team_name` matches the
       selected team **or** `team_name` is absent (shared). Drop the rest — they belong to the
       other team's plan run.
     - Also filter `boundary_conditions[]` — keep only entries whose `req_id` traces to a
       retained requirement.
     - Suffix `feature_key` with the team slug (`save_group_go_food_order`) so two teams'
       deliverables don't collide on import, same pattern as per-app suffixing.
     - Stamp `team_name` into `feature_metadata`.
   - **RFC cross-check.** After team selection, if `rfc_context` is loaded, compare the RFC's
     scope (`affected_modules`, `affected_services`, or any team-scoped sections) against the
     selected team. If the RFC clearly scopes to a different team, emit a `WORTH_CHECKING` note:
     *"RFC scopes to [X] but selected team is [Y] — confirm the RFC applies to this team's
     plan."* If the RFC covers the selected team (or is team-agnostic), no note needed.
   - **Headless fallback:** if no user is available to answer, generate for **all teams
     combined** (no filtering) and add a `WORTH_CHECKING` note: *"PRD has N teams — generating a
     combined plan; re-run interactively to scope to one team."*
8. **Shared requirements across apps.** When a source document covered several apps, items that
   apply to all of them carry the **same id in every file** (`req_id`, `risk_id`, `flag_key`,
   `endpoint`). Generate scenarios for them normally — they are in scope for this app too — and
   list those ids under a *Shared across apps* note in `<feature_key>_analysis.md`, so the QA
   reviewing both plans knows which scenarios are duplicates rather than distinct coverage.
9. **Invoke `regression-extractor` as a subagent — before any scenario is created, not after.**
   Use the `Agent` tool to spawn the regression-extractor in an isolated context. Pass it the
   resolved `app` and `module_namespace` (plus `rfc.affected_modules` for impacted-area
   coverage). The subagent does all BrowserStack MCP querying, nav_index joins, and deeplink
   extraction, writes `regression_context.json` to disk, and exits. The main generator then
   reads only the final JSON file — the raw MCP responses and intermediate corpus data never
   enter the generator's context window. This is critical for token efficiency: a single
   BrowserStack query can return 30-60K tokens of case data that would otherwise persist in
   context for the rest of the generation run.
   Wait for the subagent to complete, then read `regression_context.json` from the working
   directory. This is an internal call — not something to wait on the QA for.
   - **BrowserStack MCP unavailable → STOP.** If the regression-extractor reports that
     BrowserStack MCP is unreachable or unauthorised (no `regression_context.json` written),
     **do NOT proceed with generation.** Stop and tell the user:
     *"BrowserStack MCP is not connected. Run `/aep-mobile:setup` for setup steps, then re-run."*
     Generating without regression dedup risks duplicating the entire existing suite into TMS
     on CSV import — that is not recoverable, so it is a hard gate.
   - **`extraction_status: LIMITED` for a non-MCP reason is different — continue.**
     The two merchant apps have `NO_COVERAGE` in the automation repo (no cases to query) —
     that is a legitimate zero-result, not a connection failure. The extractor writes
     `regression_context.json` with `[]` and `COMPLETE`/`LIMITED` with an `FYI` note. That is
     fine — proceed with zero regression context.
   - **A schema-invalid or unreadable `regression_context.json` is different** — treat it like
     any other malformed input context (Preflight step 3): use nothing from it, raise a
     `NEEDS_ANSWER` note naming the failure, never silently treat malformed as merely absent.
   - Inherit its `extraction_notes[]` the same way as every other input context (step 4), so a
     regression case with weak/unverified steps is visible in this plan's own open points, not
     lost at the boundary.

## Anti-hallucination rules
- **Every scenario traces to a real field in a real input context.** No scenario may rest on a
  requirement, screen, element, flag or endpoint that is not present in a supplied context.
- Never invent `element_id` or `screen_id` values. If a scenario needs an element the design
  context does not carry, that is a `blocking_issues` entry, not a guessed token.
- **`element_id` / `screen_id` are schema identifiers — this rule does NOT suppress step
  authoring.** When the design context is DEGRADED or has empty `elements[]`, scenarios still
  owe granular, action-level `steps[]` drawn from the PRD and RFC. A PRD requirement that
  describes entering an amount, choosing a split method, and confirming is **three steps**, not
  one vague line. Write them as human-readable NLP (`Enter the split amount`, `Select "Equal
  split"`, `Tap the confirm button`) — these are tester actions sourced from the PRD/RFC, not
  invented `element_id` tokens. Collapsing a multi-action flow into a single high-level line
  like *"Complete the creation"* is a **step-authoring defect**: it is untestable (a tester
  cannot execute it without guessing what to do) and it hides the actions the PRD/RFC actually
  describe. The identifier provenance rule governs `element_id` fields and schema tokens; it
  never governs the NLP wording of `steps[]`.
- Never invent a deeplink or test hook. Absent hook → the scenario states the manual
  navigation path and is flagged in testability feedback.
- **Never assume a screen is "just open."** Reaching every screen a scenario needs — including
  the login/authenticated starting state — must be resolved through the Navigation Resolution
  Ladder (Step 2: hook/deep link → `design_context.ui_flow` → `regression_context.navigation` →
  explicit `[NAVIGATION NOT CONFIRMED]` flag). A scenario whose first step starts mid-flow with no
  resolution trace behind it is an invented fact, not a stylistic shortcut.
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
   - **Directly under the matrix, print the projected balance** so the skew is visible at
     selection time rather than after generation: the count of selected POSITIVE-producing
     categories (`functional`/`positive`, plus the business-flow rule which always fires) vs
     NON-POSITIVE-producing ones (negative/boundary/permission/interruption/migration/offline
     + every `fe_baseline` group), and one line naming the risk if extras are ticked heavily —
     *"selecting all 6 extras would put this suite at ~20% business coverage; Step 4c-mix will
     force positive regeneration."*
   - **`functional` / `positive` is never offered as removable**, even under an explicit QA
     override — it is the suite's baseline, not a discretionary category.
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
  - **For each** `prd.business_requirements[i]` → emit ≥1 scenario **per distinct acceptance
    criterion / stated behaviour** in that requirement, each with `requirement_ref` = that
    `req_id`. One row per `req_id` is the floor, not the target: a requirement stating three
    outcomes owes three positive scenarios. Where the requirement names user segments, entry
    points, or valid states that change the expected outcome, **each gets its own positive
    row** — these are alternate valid paths, not variants of one row. (A P0 requirement always
    keeps ≥1.)
  - **For each end-to-end business flow** → emit ≥1 multi-screen scenario that walks the whole
    path and asserts the business outcome at its end. A business flow is a path through
    `design_context.ui_flow[]` from a `flowStartingPoints` entry to a terminal/success screen,
    or a journey the PRD narrates across more than one requirement. Stamp
    `coverage_category: functional`, `source: input_derived`, and set `requirement_ref` to the
    req_ids the flow satisfies (a flow may satisfy several — list them). **`ui_flow` is a
    source of scenarios here, not only a navigation lookup for the Resolution Ladder** — a plan
    that consumes `ui_flow` purely as plumbing has skipped this rule. These flows are the
    backbone of the suite: generate them before any negative, boundary, or interruption
    expansion.
  - **For each** `prd.boundary_conditions[i]` → emit ≥1 boundary scenario referencing that entry. Do NOT fold a boundary rule into an unrelated happy-path scenario as a substitute — it needs its own row. (This is the rule most often missed: e.g. a screenshot/privacy-mask boundary and a "shown once per customer" ordering boundary are distinct entries, each needing its own scenario.) The scenario's setup/Steps come from `edge_case_description`; its **expected outcome is taken verbatim from `proposed_default`**. If `proposed_default` is empty, still emit the scenario (the edge case must be exercised) but leave its Expected Result as a `NEEDS_ANSWER` open point — never invent the default behaviour.
  - **For each** `rfc.lifecycle_considerations[i]` (if the lifecycle category is selected) → emit ≥1 scenario for that `event`.
  - **For each** feature flag in `rfc.experimentation_matrix[]` / `prd.feature_flags[]` (if the flag category is selected) → emit ≥1 kill-switch/toggle scenario. **Flag record precedence: RFC is authoritative.** When the same flag appears in both, take the RFC `experimentation_matrix[]` record (`flag_key` verbatim + `default_variant` + `variants` + `kill_switch`) as the source of truth; the PRD entry is name-only corroboration. A PRD-only flag (absent from RFC) still gets a toggle scenario from its name **and** a `prd_vs_rfc_gap` note ("flag in PRD, undocumented in RFC — no variants/default"). An RFC-only flag is fine.
  - Every scenario MUST carry a `requirement_ref` (the `req_id` / boundary index / event it satisfies) so Step 4 can audit coverage mechanically.
  - **Clickstream Telemetry Rules:** Clickstream verification is **NOT** a mandatory hard gate for the generator. If `clickstream_events` are explicitly provided/told in the input contexts, then generate $\ge 1$ verification step per event. If they are NOT provided or explicitly mentioned, **do NOT fail validation and do NOT generate telemetry tests.** Instead, simply list it as an Open Question / Clarification inside `<feature_key>_analysis.md` (e.g., *"Are clickstream telemetry events required for this feature?"*).
- **Regression dedup — using `regression_context.json` from Preflight step 9, before writing any scenario:**
  - For each requirement/boundary/flag about to get a Hard-Coverage scenario, check `regression_context.json.regression_tests[]` for a case whose `title` or `steps` clearly cover the same behaviour.
  - **Exact match (the existing case already covers this exact behaviour)** → do not create a new scenario. Still emit a row for it (QA needs to see it exists), with `is_legacy_regression: true` and `existing_case_ref` set to that case's `id` (e.g. `C2879733`) — never `is_legacy_regression: true` with no ref; that's a flag nobody can audit or trace back.
  - **Partial overlap (related but not identical — e.g. the existing case covers the happy path, this requirement needs a boundary variant)** → still create the new scenario (the Hard Coverage Rule requires it), but set `existing_case_ref` to the related case anyway, so the analysis doc shows the relationship instead of two disconnected-looking rows.
  - **No match** → proceed normally, no `existing_case_ref`.
  - This never overrides a Hard Coverage Rule (Step 1 above) — every P0 requirement and boundary condition still gets ≥1 row in the plan even if a legacy case already covers it; the point of dedup is to avoid generating a *second, redundant automation target*, not to avoid *documenting* coverage.

### 2. Scenario Expansion
Expand scenarios across:
- **Core (generate these first — before any Mobile Extras or FE-Baseline expansion).** This is
  the centre of gravity of the suite, and it is the part most often under-expanded. Expand, in
  order:
  1. **Primary happy path** per `prd.business_requirements[]` acceptance criterion — the
     feature doing what it exists to do, with valid data, on the intended screen.
  2. **End-to-end business flows** per the Hard Coverage Rule above — full journeys through
     `design_context.ui_flow[]` / the PRD's narrated flow, asserting the business outcome at
     the terminal screen, not just the next screen's render.
  3. **Alternate valid paths** — every *valid* segment, persona, entry point, tier, or state
     the PRD names that reaches the same outcome by a different route. These are positive
     scenarios; do not collapse them into a single row or demote them to negatives.
  4. **Positive state transitions** — the produced value surviving a legitimate re-entry
     (re-open the screen, navigate away and back, pull-to-refresh) with the business state
     intact. This is a positive assertion about persistence, distinct from the
     process-death/interruption negatives below.
  5. **Boundary, negative, and contract flows** — the valid-input edges, error copy, and API
     contract behaviour required by the Hard Coverage Rules.
  Steps 1–4 must exist before step 5 and the Extras below are expanded. Negative and edge
  coverage complements the business suite; it never substitutes for it.
- **Mobile Extras**: Generates mobile-specific scenarios (deep-link navigation, regional variants, feature flag toggles) and applies **Conditional Mobile-Native Interruption Rules** to ensure test suites remain highly focused and are only generated when technically valid. These rules are the `interruption_*` / `local_data_migration` / `permission` detection triggers surfaced in Step 0 — only expand a category the gate selected:
  - **Network Loss / API Timeout**: Inject a poor-network or server-timeout scenario *only* if `rfc_context.json` declares active `api_contract_changes` or `plan_context.json` specifies `observable_states` (API success/failure signals). Skip if the touchpoint screen is entirely static/local.
  - **App Backgrounding & Process Death**: Inject a backgrounding/kill-and-restore state preservation scenario *only* if the screens in `design_context.json` contain interactive elements (inputs, forms, toggles) or view models are active in `plan_context.json`. Skip on purely static/read-only informational screens.
  - **Local Storage & DB Migration**: Inject an N-1 upgrade and schema migration scenario *only* if `rfc_context.json` defines active `local_data_changes` (e.g. SQLite, Room, CoreData, or SharedPrefs modifications).
  - **Runtime Permission Toggles**: Inject parallel Permission Granted vs Permission Denied scenarios *only* if `rfc_context.json` declares new or modified `permissions_required`.
  - **Platform variance**: Only meaningful when the feature resolves to **more than one** target
    platform (per the Platform resolution precedence: `prd.applicable_platforms`, else
    `rfc.scope.target_platforms`, else inferred from design). When it does, generate the variance
    scenario **only across those resolved platforms**. When the feature resolves to a **single**
    platform, there is no variance to test — do **not** emit a platform-variance scenario; if the
    `platform_variance` trigger fired only because `rfc.platform_specific.<os>` documents
    platform-specific handling for that one platform, generate at most a plain render/behaviour
    check *on that platform*, never a cross-platform one.
    - **Never put an off-target platform inside a scenario — not as a step, not as a caution.** A
      platform the app *supports* (per `config.<app_id>.json`) but the PRD/RFC does **not** scope
      into this feature (e.g. the RFC scopes `target_platforms: ["android"]` and never mentions
      iOS) is **out of scope for every scenario**. Do not write a step like *"iOS coverage cannot
      be scripted…"* or *"verify on iOS"* — a step naming a platform the feature doesn't target is
      both untestable and not a tester action (same rule as automation-scaffolding: notes never
      live in `steps[]`). The legitimate concern — "the app ships on iOS but this RFC is
      Android-only; is iOS a separate effort?" — is surfaced **once**, as an inherited/authored
      `extraction_notes` entry and an analysis.md open-question row, and nowhere else. The CSV's
      own `iOS Automation Status v2` / `Android Automation Status v2` columns already encode
      "doesn't apply" via `N/A`; that is the *only* place an untargeted platform appears in the
      deliverables.
- **FE-Baseline Extras**: If the QA selected any `fe_baseline` category in Step 0, expand best-effort hygiene scenarios for it, stamp `source: "fe_baseline"`, and record in analysis.md that expected behavior is not spec-derived and needs PM/dev confirmation.
- **Navigation Resolution Ladder (mandatory — run per scenario, before writing `steps[]`).**
  A scenario's `steps[]` is the *only* place reachability lives in this schema (there is no
  separate `navigation` field on `scenario_list` items, unlike the standalone
  `scenario.schema.json`). That means every step sequence must be self-contained: never open a
  scenario mid-flow as if arriving at its screen were free. Resolve reachability in this order,
  stopping at the first rung that produces a concrete, sourced answer:

  1. **Test hook / deep link — check all three deep-link sources, in this order.** A deep link is
     the ideal rung: one `Open deeplink "<uri>"` step replaces a whole tap chain. Three sources
     carry them; the target screen is resolved by the **first** that names it:
     a. `plan_context.json` test hooks (`method: deeplink` / `hook_id`) — the primary source of
        *test* hooks, when an impl plan was supplied.
     b. `rfc.navigation_changes[].deep_link` — a non-null deep link whose destination screen
        matches (a deep link the RFC itself introduces for the new feature).
     c. **`regression_context.deeplink_dictionary`** — the repo's extracted deeplink dictionary
        (`{ module: { SCREEN: "<uri>" } }`), surfaced by the regression-extractor from the
        automation repo's own deeplink constants. **This is the primary navigation mechanism in the
        corpus and resolves most screens** (the repo uses deep links far more than UI walks), so it
        must be checked before falling through to the UI-walk rungs below — a screen with a real
        repo deeplink is *not* `[NAVIGATION NOT CONFIRMED]`. Match the scenario's target screen to a
        dictionary key by meaning (e.g. a "Manfaat & Pencapaian Anda" / benefits-rewards screen →
        `LOYALTY_REWARDS = "gojekdriver://loyalty/rewards"`; a "Loyalty Home / Level Saya" screen →
        `LOYALTY_HOME`). Use the URI **verbatim** — never edit, complete, or invent a path; a screen
        the dictionary does not name is simply not resolved at this rung, fall through to rung 2.
     Found at any of a/b/c → the scenario opens with `Open deeplink "<uri>"`, no UI walk needed.
     Tag the scenario's provenance as hook-resolved and cite the source (plan hook / rfc / repo
     deeplink dictionary); no note required, this is the ideal case. Only when **none** of the three
     names the screen does resolution fall through to rung 2.
  2. **Design's own resolved flow (`design_context.ui_flow[]`).** If design_context has real
     screens (not an empty/failed extraction), search `ui_flow[]` for a path from a reachable
     entry screen (a `flowStartingPoints` entry, or a screen already resolved by an earlier rung)
     to this scenario's target `screen_id`. Prefer `confidence: "EXPLICIT"` edges. Turn each edge
     into a step using the trigger element's `label` (never its raw `element_id` — e.g. `Tap
     "8 level Program Apresiasi Mitra"`, not `Tap PROFILE_PAGE.pam_entry_btn`). A path that only
     reaches an intermediate screen is a partial answer — carry it forward and let rung 3 supply
     the missing segment (see *Reconciling two sources* below).
  3. **Regression corpus navigation (`regression_context.json`).** Search
     `regression_tests[].navigation` for a case reaching the same screen (or a close-enough
     ancestor to bridge a rung-2 partial path), preferring `nav_source: "existing_test"`
     (repo-confirmed) over `"figma"` over `"needs_answer"` (never usable — that value means the
     regression-extractor itself couldn't resolve it, so it cannot resolve it for you either).

     **Normalize, don't transcribe.** `regression_tests[].navigation`/`.steps` are repo Gherkin or
     BrowserStack prose written for an automation engineer, not for a manual tester — copying them
     into `steps[]` unedited is the single most common quality defect in this skill's output. Before
     a regression-sourced line becomes a scenario step:
     - **Resolve Scenario Outline placeholders — from a source, never a guess.** A step like
       `"Driver Login to <Vehicle Type> as a <Driver Account> through backdoor"` is a Cucumber
       Examples-table template, not literal text — the angle brackets are unbound variables, not
       something a tester can act on. Substituting a value here follows the same anti-hallucination
       rule as everything else in this skill: only use a value a source actually states —
       the case's own Examples table (if fetched), an explicit PRD/RFC statement (e.g. PAM-06's
       `"SDF, Kilat, or Box service type"`), or a fact directly observed elsewhere in the corpus
       (e.g. a BrowserStack case's own `DriverType` custom field listing which types it already
       covers). If nothing sources a concrete value, do **not** invent one (a "2-wheeler" or
       "pilot-city" default with no source behind it is exactly the fabrication this skill's
       provenance rule forbids) — instead generalize the wording to what the step actually needs
       (`"Log in as a driver using the test backdoor login"`) and add an `extraction_notes` entry
       (`follow_up: WORTH_CHECKING` or `NEEDS_ANSWER` depending on how much it blocks the scenario)
       naming the unresolved placeholder. Whichever path you take, record it in the scenario's
       `test_data`/`preconditions_metadata` so it stays traceable. A literal `<...>` token
       surviving into a manual-facing step is a defect, not a faithful quote — it means the
       normalization step was skipped.
     - **Drop pure test-harness scaffolding.** Lines with no on-screen tester action (`"Given Test
       case info for AEP DASHBOARD"`, `"turn off Spotlight and LeakCanary"`, feature-toggle setup
       lines) describe automation rigging, not something a manual tester does on the device — they
       belong in `preconditions_metadata` (and the CSV `Preconditions` column), never in `steps[]`.
     - **Translate automation-harness vocabulary into what a tester actually does.** Repo steps name
       mechanisms that exist only inside the harness — a login *backdoor* or bypass, a seeded
       session, a stubbed response, an internal UI codename (`"tap on profile icon konmari"`), a
       page-object or Fragment/ViewController class name. A manual tester can neither see nor
       perform any of them. The test is one question: **could a person holding the device do this,
       using only what is on screen?** If not, it is automation vocabulary and must be converted —
       never passed through, and never merely deleted. Convert by *intent*:
       - The mechanism **substitutes for a real user action** (backdoor/bypass login, injected
         session) → write the real action that reaches the same state: `"Driver Login to <X>
         through backdoor"` → `"Launch the app and log in with a test driver account"`. Dropping
         the line instead would strand the scenario mid-flow — the ladder still owes an arrival path.
       - The mechanism **has no user-facing counterpart** (harness plumbing, flag/state injection,
         fixture seeding) → it is a precondition, not a step; move it per the bullet above.
       - An **internal codename or code identifier** (`konmari`, a `*Fragment.kt`, a page-object
         method) → name the element as it appears on screen (`"Tap the profile icon"`).
       This governs **assertions as much as actions**: a manual step cannot verify *"the API
       returns null"* or *"`show_claimed_once_banner` is true"* — only what the screen shows in
       that case. Reframe backend-shaped expectations into their observable UI outcome; the
       endpoint/field detail stays in the scenario's contract metadata and the analysis doc, where
       it is useful, rather than in a step no tester can execute. Where a scenario genuinely needs
       a backend condition forced (an error state, a timeout), write the **tester-executable**
       instruction — *"using a proxy tool, force `<endpoint>` to return 500, then …"* — not a bare
       *"simulate an API failure"*, which names an outcome without an action.
     - **Rephrase into declarative NLP**, the same style rung 2 already uses (`Tap "Daftar Program
       Affiliate"`, never a raw element id): third-person test-script prose (`"driver tap on
       profile icon konmari"`) becomes a clean imperative tester action (`Tap the profile icon`).
       Preserve the screens/order/meaning exactly — normalizing wording is not a license to change
       the path or drop a real step.
     Cite the source case id (e.g. `C5542964`) in the scenario's `test_data[].source_refs` so the
     now-normalized path is still auditable back to the repo-confirmed original.
     - **Cross-case corroboration for login/session preambles.** The most common reachability gap
       isn't the target screen, it's getting to an authenticated starting state at all. If
       `plan_context` has no login/state-injection hook, look for a leading step-subsequence
       shared identically across **3 or more independent** `regression_tests[].navigation`
       entries for this app (e.g. a repeated "login via backdoor → skip walkthrough → dismiss
       vehicle card → tap profile icon" prefix). A sequence corroborated across that many
       independent cases is the app's standard entry preamble, not a one-off guess — reuse it
       (normalized per the rule above) for any scenario needing a logged-in starting point.
  4. **Reconciling two sources.** When both rung 2 (design) and rung 3 (regression) produce a
     path to the same screen: if they agree (same screens/actions, or one is a superset of the
     other) use the more complete one — this is corroboration, not a conflict, and needs no note.
     If they genuinely disagree (different entry banners, different login mechanism, different
     screen order) **do not silently pick one.** Emit the design-derived path as the primary
     steps, add one inline flag line noting the regression-derived alternative and where it
     diverges, and add an `extraction_notes` entry (`follow_up: NEEDS_ANSWER`) naming the specific
     conflicting screens/elements from both sources. Merging them into a single path neither
     source actually states is inventing a fact.
  5. **Nothing resolves.** No plan/RFC/repo-dictionary deep link (all three rung-1 sources
     checked), no usable design `ui_flow` edge, and either no regression match or only
     `nav_source: "needs_answer"`. Do **not** write a plausible-sounding step like "Open the X page"
     — that is the exact failure mode this ladder exists to prevent. Instead the scenario's steps
     open with exactly one line:
     `[NAVIGATION NOT CONFIRMED] Manually navigate to <screen_id> — no deeplink (plan, RFC, or repo
     dictionary), design flow, or regression precedent was found.` The destination-screen
     verification steps still follow
     normally below it. Add a `testability_feedback.missing_hooks` entry naming the exact screen
     and what was checked, plus a matching `extraction_notes` entry (`follow_up: NEEDS_ANSWER`).
     The scenario still counts as covered for the Step 4 audit — the requirement is exercised —
     but the gap stays visible instead of being papered over with an assumed arrival.

  This ladder is feature-agnostic by construction: it never depends on this being a loyalty
  feature, a payments flow, or any specific app — it only depends on which of `plan_context`,
  `rfc.navigation_changes`, `regression_context.deeplink_dictionary`, `design_context.ui_flow`,
  and `regression_context.navigation` actually resolved something, the same fields every run of
  this generator already has (or explicitly lacks) by Preflight.

- **`automation_steps[]` — a consolidated action + verification sequence for code generation.**
  Placed **immediately after `steps[]`** in the scenario object. Unlike the CSV (where `Steps` =
  pure actions and `Expected Result` = pure verifications, kept apart for manual testers),
  `automation_steps` **interleaves actions and their verifications in execution order** — this is
  what the downstream code-gen stage needs to produce a runnable test method. Each action is
  immediately followed by its corresponding verification(s), forming a single linear sequence:
  ```
  "automation_steps": [
    "Open deeplink \"gojek://food/group-order\"",
    "Verify \"Group Order\" screen is visible",
    "Tap \"Invite Friends\"",
    "Verify share sheet is displayed",
    "Enter \"CODE123\" into \"Referral Code\"",
    "Tap \"Apply\"",
    "Verify \"Code applied successfully\" toast is visible"
  ]
  ```
  This is *not* a full runnable automation script — the downstream **code-gen stage** fills in the
  exact constants, credential tokens, toggle names, and setup scaffolding. The generator's job
  here is to hand code-gen a clean, ordered sequence of what-to-do and what-to-check in the right
  dialect. So:
  - **Merge `steps[]` (actions) and `expected_result` (verifications) into one ordered list.**
    After each action step, insert its corresponding verification(s) from `expected_result`.
    An action with no verification (`—` in expected result) has no verify line after it.
  - **One action or verification per line — split every compound step.** No line may contain two
    actions. Split a step at a top-level " and " / " then " that joins **distinct actions**, and
    inherit the first fragment's leading verb into a verbless second fragment: "Skip the
    walkthrough and tooltip prompts" → "Skip the walkthrough" + "Skip the tooltip prompts";
    "Verify the red card marks the end month and the green card marks the start month" → two
    "Verify …" lines. Applies to **all** steps — but do **not** split where the connector is not
    a real action boundary:
    - inside parentheses, or a comma-list ("monthly, yearly, and special tiers"), or an Oxford
      ", and "/", then ";
    - when the word **before** the connector is a preposition/article — "up to **and** including
      2028", "for X **and** Y" — the "and" is mid-phrase, not two actions;
    - when the left side is a bare shared verb (<2 words) whose object comes after the second verb
      — "Uninstall **and** reinstall the app" stays one line (splitting would strand "Uninstall").
  - **Use these TapMind helper calls verbatim, nothing invented; everything else is plain NLP text
    (no `runStep(...)` wrapper — code-gen adds that):**
    - a login / "launch + log in" step → `loginToDriver(<account>)` (or the app's login helper —
      `loginWithRegisteredMerchant(...)`, etc.); the placeholder account is fine, code-gen resolves
      the real credential constant.
    - a step that explicitly opens a deep link → `openDeeplink("<uri from the step>")`.
    - a step that explicitly sets/toggles a flag → `setDriverToggle(<flag_key>, <true|false>)`
      (flag key verbatim from the step).
    - **every other action or assertion → the plain step text itself** (`Tap the profile icon`,
      `Verify 'Pusat bantuan' is visible`) — NOT wrapped in `runStep("...")`. The runStep ceremony,
      exact constants, and any setup are the code-gen stage's job; here we only hand it clean,
      single-action NLP lines in the right dialect.
  - The exact toggle constants, credential constants, and any setup the code-gen stage needs are
    **explicitly out of scope here** — never fabricate them. If a scenario maps to an existing case
    that already has a real TapMind test (`regression_context.regression_tests[].tapmind_steps`),
    prefer copying that verbatim over restyling, and cite the case id.
  - **Nothing to automate** (out-of-scope/placeholder scenario) → `automation_steps: []`.
  Add **one** `extraction_notes` entry (`follow_up: WORTH_CHECKING`) stating automation_steps are a
  consolidated action+verification sequence in TapMind dialect and the code-gen stage owns exact
  constants/setup. `automation_steps` is **JSON-only** — not a CSV column (the CSV keeps actions
  in `Steps` and verifications in `Expected Result` as separate columns for manual testers).

### 3. Gap Analysis & Alignment Engine
As the single integration point, the generator must actively compute the following cross-stage gaps:
- **`prd_vs_figma_gaps`**: Cross-reference `prd_context.json` with `design_context.json`. Check `business_requirements[].context_screen` against Figma `screens[].screen_id`. Identify missing screens/frames, text copy mismatches, or personas with no design representation.
- **`prd_vs_rfc_gaps`**: Cross-reference `prd_context.json` with `rfc_context.json`. Compare PRD `feature_flags` against the RFC `experimentation_matrix` (finding flag key typos, missing defaults, or status mismatches). Verify business rule conditions align with RFC error codes or API paths.
- **`rfc_vs_impl_plan_gaps`**: Cross-reference `rfc_context.json` with the Implementation `plan_context.json`. Check if RFC architectural risks, local migrations, offline strategies, or required permissions are accounted for in the implementation's screens touched, view models, and components.
- **`element_locator_handoff`**: Map `screen_name:element_id_name` logical tokens to cross-platform accessibility attributes (`android_resource_id`, `ios_accessibility_identifier`, `flutter_key`). Only populate these fields if the matching locator values are provided by the upstream design/development context; do not use placeholders or "UNRESOLVED" strings.

### 4. Coverage Self-Audit Gate (MANDATORY — run before writing any output file)

This gate is what makes coverage model-independent: it does not rely on the model "remembering" to be thorough — it mechanically re-checks the generated scenario set against the inputs and forces a fix before output. Run it every time, in both interactive and headless modes.

**4a. Build the required-coverage checklist** directly from the inputs (this is a deterministic list, not a judgment):
- every `prd.business_requirements[].req_id`, **plus each distinct acceptance criterion inside
  it** (by index, so a 3-criterion requirement contributes 3 checklist items, not 1)
- every **end-to-end business flow**: each `design_context.ui_flow[]` path from a
  `flowStartingPoints` entry to a terminal/success screen, and each journey the PRD narrates
  across multiple requirements
- every `prd.boundary_conditions[]` entry (by index + `req_id` + `edge_case_description`)
- every `rfc.lifecycle_considerations[].event` (if lifecycle selected)
- every flag in `rfc.experimentation_matrix[]` / `prd.feature_flags[]` (if flag category selected)
- every event in `prd.clickstream_events[]` / `rfc…observability.clickstream_events[]` **only if** such a structured array is non-empty (per the Telemetry Rules — never invent this list)

**4b. Match generated scenarios to the checklist** using each scenario's `requirement_ref`. Produce a coverage map: `checklist_item → [scenario titles covering it]`.

**4c. If any checklist item has zero covering scenarios → the plan is INCOMPLETE.** Do not write the output files yet. Generate the missing scenario(s), then re-run 4b. Repeat until every item is covered. A boundary rule "covered" only by being mentioned inside an unrelated scenario does NOT count — it needs a scenario whose `requirement_ref` names it.

**4c-nav. Navigation audit (mechanical, not from memory).** For every scenario in `scenario_list`,
confirm its `steps[]` opens with one of: a deep-link open (from a plan hook, `rfc.navigation_changes`,
**or `regression_context.deeplink_dictionary`**), a navigation chain traceable to
`design_context.ui_flow` or `regression_context.navigation` (per the Navigation Resolution
Ladder, Step 2), or an explicit `[NAVIGATION NOT CONFIRMED]` line. **Before accepting a
`[NAVIGATION NOT CONFIRMED]` line, re-check `regression_context.deeplink_dictionary` for a key
matching the target screen — an unresolved flag on a screen the repo dictionary actually names is a
defect, not a valid outcome** (this is the exact miss the deeplink rung exists to prevent). A
scenario whose first step assumes arrival at a screen (e.g. "Open the X page" with nothing before
it) with none of the above behind it is likewise a defect — fix it (resolve the ladder properly, or
replace the assumed step with the unresolved-flag line) before writing any output file. This check
is what would have caught steps starting cold at a destination screen with no login/navigation path
before it; it must run on every pass, not just when something looks off.

**4c-mix. Coverage-balance audit (mechanical, runs on every pass).** The checklist audit above
proves every input item has *a* scenario; it cannot see that the suite is 3 happy paths and 25
negatives. This step does.

Classify every scenario in `scenario_list` into exactly one bucket:
- **POSITIVE** — `coverage_category: functional`/`positive`, end-to-end business flows,
  alternate valid paths, and positive state-transition scenarios (Step 2 Core items 1–4).
- **NON-POSITIVE** — negative/error, boundary, permission-denied, interruption (network,
  lifecycle, OS), local-data migration, offline, and every `source: fe_baseline` scenario.

Compute `positive_pct = POSITIVE / (POSITIVE + NON_POSITIVE)`.

**If `positive_pct < 50%` the plan is UNBALANCED — do not write any output file.** Return to
Step 2 Core and generate the missing business coverage (re-read `prd.business_requirements[]`
for un-expanded acceptance criteria and `design_context.ui_flow[]` for un-walked journeys),
then re-run 4b and 4c-mix. **Never satisfy the ratio by deleting negative scenarios** — the
negatives are Hard-Coverage-mandated and removing one drops real coverage; the only legal fix
is adding the positive scenarios that were missed.

If a genuine second pass still cannot reach 50% because the inputs really do describe a
mostly-edge-case feature, write the files, record `action_taken: "under_target — inputs
describe N requirements against M boundary/error entries"` in the balance block, and raise a
`WORTH_CHECKING` note. That is an escape hatch for a real input shape, not a way to skip the
regeneration pass — it is only legal *after* a documented retry.

**4d. Emit the audit result** into the SDET plan as a `coverage_audit` object and echo it as a table in `<feature_key>_analysis.md`:
```
"coverage_audit": {
  "required": { "business_requirements": [...], "business_flows": [...], "boundary_conditions": [...], "lifecycle_events": [...], "feature_flags": [...], "clickstream_events": [...] },
  "covered": { "<checklist_item>": ["<scenario title>", ...], ... },
  "gaps_closed_in_this_pass": ["<item that was missing and got a new scenario>", ...],
  "still_blocked": [ { "item": "...", "reason": "expected behavior undefined (e.g. OQ-open)" } ],
  "balance": { "positive": 0, "non_positive": 0, "positive_pct": 0.0, "action_taken": "balanced | regenerated_positives | under_target — <reason>" }
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
- **Fold in the feature's stated baseline facts, not only the boundary/persona-specific ones.**
  `country` (from `prd.applicable_countries`, or the specific country this fixture targets),
  `driver_type`/service-type cohort (`prd...target_personas[].prerequisites`, e.g. `"SDF, Kilat,
  or Box service type"`), and any other flat fact the PRD/RFC states for *this* fixture belong in
  `required_state` whenever the source names them — even when the fixture's distinguishing trait
  is a `dynamic_conditions` entry. A fixture for "driver mid-way through a yearly eligibility
  period" still states `country`/cohort if the source does; the dynamic condition explains *when*,
  it doesn't excuse omitting *what else is known*. `required_state: {}` should be rare — it means
  the source genuinely stated no static fact at all for this fixture, not merely that the one
  interesting condition happens to be dynamic.
- **Unstated variant dimension → fan out one fixture per variant; never collapse it to a guess.**
  A *variant dimension* is any attribute that partitions the entity population into groups the
  feature could behave differently for, and which the source docs left **unrestricted**: a driver
  app's vehicle type (2W/4W) or service type, a consumer app's payment instrument, user tier,
  account type, or subscription state. This is deliberately app- and domain-agnostic — the rule is
  about *an unrestricted partition*, never about a hardcoded list of dimensions.

  Resolve each dimension in this order:
  1. **PRD/RFC restricts it** → one fixture, that value in `required_state`, done. (`"Driver
     cohort: SDF, Kilat, or Box service type"` → `{"service_type": "SDF|Kilat|Box"}`.) A stated
     restriction is never widened.
  2. **Unrestricted, and a source enumerates the real values** → **emit one fixture per value.**
     Each gets its own stable `fixture_id` suffixed by the variant, carries the dimension inside
     `required_state`, and keeps the rest of the base fixture's state identical. This is the case
     the QA is usually owed two rows of data for and silently gets one.

     **The dimension's name, its `required_state` key, its `fixture_id` suffix, and its values all
     come from the enumerating source's own vocabulary — never from this rule's examples.** The
     examples below are illustrative of the *shape*, not a template to copy. Read what the source
     actually enumerated and mirror that:
     - A driver feature whose cases are tagged `DriverType: ["IDBike","IDCar"]` → two fixtures
       `…-2w` / `…-4w` with `{"vehicle_type": "2W"}` / `{"vehicle_type": "4W"}`.
     - A consumer feature whose cases are tagged `PaymentInstrument: ["GoPay","Card","PayLater"]`
       → three fixtures `…-gopay` / `…-card` / `…-paylater` with
       `{"payment_instrument": "GoPay"}` etc. — **there is no `vehicle_type` here; a consumer plan
       that never saw a vehicle dimension must never grow one.**
     - A merchant app with `NO_COVERAGE` (no regression corpus) enumerates nothing at rung 2a → it
       does not fan out on an invented dimension; it falls to 2b/2c or to case 3 below.
     Enumeration sources, in priority order — all *observed*, never a list you compose yourself:
     a. `regression_context.observed_variant_dimensions` / `regression_tests[].variant_dimensions`
        — the variants this app's **existing coverage actually splits on** (`DriverType:
        ["IDBike","IDCar"]` for one app, `PaymentInstrument: [...]` or `UserTier: [...]` for
        another — whatever *that* app's cases carry). Strongest evidence: real cases already run
        every way. Whatever key appears here is the dimension; do not translate it into a term from
        these examples.
     b. `config/<app_id>.json`, when it enumerates the dimension.
     c. An explicit enumeration elsewhere in the PRD/RFC — an impact/estimate table listing the
        segments, a rollout table naming cohorts — even where the requirement text itself is silent.
     Cite the enumeration's origin in every fanned-out fixture's `source_refs`, and add **one**
     `extraction_notes` entry per dimension (`follow_up: WORTH_CHECKING`) recording the assumption:
     *"PRD/RFC does not restrict <dimension>; fixtures fanned out across <values> observed in
     <source>. Confirm the feature behaves identically across them, or state the restriction."*
     That note is what makes this an auditable assumption rather than a silent invention.
  3. **Unrestricted and nothing enumerates it** → a single fixture that simply omits the dimension,
     plus a `WORTH_CHECKING` note naming the unresolved dimension. Never fabricate a plausible
     default (`"2-wheeler"`, `"credit card"`) to fill the gap — that is the provenance rule's
     exact failure mode, and it silently narrows coverage to a variant nobody chose.

  **Bound the fan-out — vary one dimension at a time, not the cartesian product.** With two
  unrestricted dimensions of 2 and 3 values, emit the base fixture plus one fixture per *additional*
  value of each dimension (`1 + 1 + 2 = 4`), holding the other dimensions at the base value — not
  all 6 combinations. Take the full product **only** when the PRD/RFC states the dimensions
  interact. If a single dimension enumerates more than ~4 values, fan out only to the values the
  regression corpus actually exercises and note the remainder as uncovered, so a broad enum cannot
  detonate the test-data ask.
- `type_signals` carries the short labels that used to be `test_data_tags`
  (`["kyc_verified_user","birthday_d_day"]`). They summarise; `required_state` is the source of
  truth. Keep both. When fixtures are fanned out across a variant, the variant belongs in every
  copy's signals too — named after the actual dimension, e.g. `[...,"vehicle_2w"]` for a driver
  app or `[...,"payment_gopay"]` for a consumer one — so downstream can group them.
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
   - Include clear, bold rows: **Feature Key**, **App**, **Team** (selected team from Preflight step 7, or "All teams" if single/none), **RFC (ID, Title, Status)**, **Analysis Date**, **SDET Plan File**, **Test Cases File**.

2. **Section 0: Selected Test Coverage Categories:**
   - A table mirroring `coverage_categories` with columns: `Category`, `Tier` (`Auto` / `Extra — feature-adjacent` / `Extra — fe_baseline`), `Selected?`, and `Why` (the field that fired, or why it was offered as an extra).
   - Note explicitly which extras were QA-added and that `fe_baseline` scenarios are hygiene, not spec-backed.
   - Immediately after the category table, render the **Coverage Audit table** from `coverage_audit`: one row per required checklist item (`Item`, `Type`, `Covered By` (scenario titles), `Status` = Covered / Blocked-with-reason). This is the reviewer-facing proof that every requirement and boundary rule has a scenario.
   - Immediately after the Coverage Audit table, render a one-row **Coverage Balance** line from
     `coverage_audit.balance`: `Positive (business/use-case) | Non-positive (negative, boundary,
     hygiene) | Positive % | Action taken`. If `action_taken` is `under_target`, state the reason
     in plain words directly beneath it, so a reviewer sees the tilt without opening the JSON.
   - Immediately after that, if any scenario in this plan carries `existing_case_ref`, render a **Regression Coverage table**: `Scenario` (title), `Existing Case` (the BrowserStack id), `Relationship` (`Duplicate — not re-created` / `Related — new variant still generated`). If `regression_context.json` itself was unavailable this run (Preflight step 9), say so in one line instead of an empty table — e.g. *"Regression check did not run this pass: <reason from the note>."*

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
- `Priority`: `"P0"`, `"P1"`, or `"P2"` — **derived from business criticality, not from how
  exotic the scenario is.** Map mechanically:
  - `P0` — end-to-end business flows, primary happy paths, and any scenario whose
    `requirement_ref` names a P0 requirement. The core use case is always P0.
  - `P1` — alternate valid paths, positive state transitions, boundary conditions with a
    stated `proposed_default`, and documented error/contract behaviour.
  - `P2` — `source: fe_baseline` hygiene, interruption scenarios (network/lifecycle/OS), and
    boundary conditions whose expected outcome is still an open point.
  A hygiene or interruption scenario is never P0; a core business flow is never below P0.
- `Type of Test Case`: `"Regression"` or `"Sanity"`
- `Automation Status`: By default, set to `"Manual"` (representing not-automated) for newly generated test cases. Set to `"Automated"` only if matched with an existing automated test case.
- `Preconditions`: Multiline string, **using a new line break (`\n`) after each statement/line.** Render, in this order, only the lines that actually apply:
  1. One line per `scenario.test_data[]` fixture, using its `description` (plus any `required_state` facts that change setup, e.g. `"Driver who joined Gojek before 2017"`, `"Driver cohort: SDF, Kilat, or Box"`) — a manual tester needs to know *which account/state to use* before environment plumbing. This is the line most often dropped; a `Preconditions` cell with only environment/locale and no fixture description has lost information the JSON already carries.
  2. `country` / `driver_type` if the scenario carries them and they narrow the setup (a scenario scoped to one cohort or country should say so here, not only in the CSV's own `Country v2` column).
  3. Environment and locale.
  4. Target entry deep link, if any.
  5. Active feature flags — copied verbatim from `rfc.experimentation_matrix[].flag_key` / `prd.feature_flags[]`, never paraphrased or suffixed (e.g. do not turn `birthday_feature_litmus` into `birthday_feature_litmus_content`). When a flag is in both, use the RFC record (`flag_key` + `default_variant`); PRD is name-only corroboration.
  A scenario with `test_data: []` and no country/flag/deeplink simply omits those lines — never pad `Preconditions` with a fixed template when the scenario has nothing to say for a given line.
- `Steps`: Numbered sequential **actions only** inside double quotes with line breaks (`\n`).
  **Write steps using clean, action-oriented, declarative NLP-style commands** (e.g.,
  `1. Open deeplink "gopay://affiliate/welcome"`, `2. Enter "CODE123" into "Referral Code"`,
  `3. Tap "Lanjut"`). **No "Verify" / "Assert" / "Check" lines in this column** — all
  verifications belong in `Expected Result`. A step is something the tester *does* on the
  device (tap, scroll, enter, open, navigate, wait); an assertion is something they *observe*
  after doing it. Mixing them makes the CSV unusable for both manual testers (who read Steps
  as a to-do list) and automation (which needs actions separated from assertions).
  Never use long, vague prose or technical automation/logical IDs (e.g., do NOT write
  `Tap WELCOME_PAGE.TAP_BUTTON_CTA`; instead, write `Tap "Daftar Program Affiliate"`).
  This column is a direct 1-to-1 join of `scenario.steps[]`. A `steps[]` entry still carrying
  a Gherkin placeholder (`<Vehicle Type>`), third-person test-script phrasing, or a pure
  automation-scaffolding line (no on-screen tester action) is a defect to fix at the source.
  **A single high-level line that collapses a multi-action flow (e.g. "Complete the split bill
  creation") is equally a defect — each discrete tester action must be its own numbered step.**
- `Expected Result`: Numbered sequential assertions inside double quotes with line breaks
  (`\n`) after each statement. **ALL verifications live here, not in Steps.** Each assertion
  corresponds to the action step at the same number — after step 3 (an action), expected
  result 3 states what the tester should observe. **Write assertions using clean, declarative
  NLP-style verification commands** (e.g., `1. Verify "Confirm Account" is visible`,
  `2. Verify "Error: Code incorrect" is visible`). Describe functional and telemetry outcomes
  in user-friendly, non-technical language. **For boundary scenarios the assertion derives from
  `prd.boundary_conditions[].proposed_default`; if it is absent, write an open-point marker
  rather than a guessed outcome.** When multiple actions share one observable outcome, the
  earlier actions' expected results can be `—` (no assertion at that step) with the combined
  assertion on the final action's line.
- `Execution Mode`: `"Automatable"` or `"Manual"`
- `Platform`: `"Android"`, `"iOS"`, or `"Cross-Platform"`. **Resolution precedence: (1) `prd.applicable_platforms` (PRD is the scope authority), (2) else `rfc.scope.target_platforms`, (3) else infer from `design`.** One platform → `"Android"`/`"iOS"`; more than one → `"Cross-Platform"`. If PRD and RFC conflict, use PRD and raise it as a `prd_vs_rfc_gap` — never silently prefer one.
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
   - **Then upload to BrowserStack and emit the automation plan.** After the merge, run the
     *BrowserStack Upload & Case-ID Resolution* step below, then the *Automation-Plan-Generator
     emission* — the CSV feedback is precisely the trigger to (re)produce
     `<feature_key>_automation_plan_generator.json` with real BrowserStack case IDs for the
     downstream Test-Data-Generation stage.

---

## BrowserStack Upload & Case-ID Resolution

**SYNC mode only.** This step runs only when the user provides a modified CSV (SYNC mode trigger).
It does NOT run during GENERATE mode — generation produces the CSV for the first time; there is
nothing to upload yet.

After the SYNC merge completes, upload the finalised test cases to BrowserStack Test Management
and stamp the returned case IDs back into `<feature_key>_SDET_plan.json` before emitting the
automation plan.

### 1. Resolve Upload Target (project + folder)

Use the first source that resolves — do not search all BrowserStack projects:

1. **`regression_context.json` exists** → read `browserstack_project` (e.g. `PR-176`) and
   `resolved_folders` (the folder IDs the extractor already queried). Use the first
   `resolved_folders[]` entry as the upload folder.
2. **No `regression_context.json`** → read
   `/Users/adarsh/.claude/plugins/cache/aep/aep-mobile/0.8.4/config/browserstack_project_map.json` and resolve
   the project from `app_id` → module → `consumer_super_app.folders` or `separate_projects`,
   same logic as the regression-extractor's Step 1b.
3. **Feature subfolder** — look for a folder matching `feature_key` under the resolved project
   (use `listFolders`). If found → use it. If not → create it via `createProjectOrFolder` with
   the `feature_key` as the folder name.
4. **Project unresolvable** (module not in the map, or `browserstack_project: null`) → ask the
   user for the BrowserStack project identifier. Do not guess a `PR-` id.

### 2. Upload Test Cases

Use the BrowserStack MCP tool `createTestCasesFromFile` with the finalised
`<feature_key>_test_cases.csv` and the resolved project + folder.

- **BrowserStack MCP unavailable at upload time → do not block.** The SYNC and automation-plan
  emission still complete. Add a `WORTH_CHECKING` note:
  *"BrowserStack upload skipped — MCP unavailable. Run `/aep-mobile:setup`, then re-run SYNC
  to upload and stamp case IDs."*
  Scenarios that already carry a `browserstack_case_id` from regression context keep it;
  new scenarios simply omit the field (never set it to `null`).

### 3. Stamp Case IDs

`createTestCasesFromFile` returns the created case identifiers (e.g. `TC-XXXXXX`). Map each
returned ID back to its scenario by matching on `csv_title_association` (the title column is the
join key between the CSV rows and the returned results).

- Write `browserstack_case_id` into each matched scenario in `<feature_key>_SDET_plan.json`.
- Existing regression cases already carry a `browserstack_case_id` from
  `regression_context.json` (e.g. `C2879733`) — **keep the original ID**, do not overwrite.
  Only stamp new IDs onto scenarios that don't already have one.
- Scenarios with no BS ID (upload failed or not applicable) simply **omit** the field — never
  set it to `null`.
- Update `<feature_key>_SDET_plan.json`'s `updated_at` timestamp.

### 4. Summary

Print a one-line summary: *"Uploaded N test cases to BrowserStack project PR-XXX / folder
<feature_key>. M existing cases kept their original IDs."*

---

## Automation-Plan-Generator emission (Test-Data-Generation handoff)
When the QA feeds the edited CSV back, the point of the round-trip is to produce the handoff the
Backend QA Test-Data-Generation RFC consumes. Emit `<feature_key>_automation_plan_generator.json`
conforming to `${CLAUDE_PLUGIN_ROOT}/schemas/automation_plan_generator.schema.json`.

**Build from the synced JSON, never from the raw CSV.** The CSV has no test-data column, so the
fixtures only exist in `<feature_key>_SDET_plan.json`. Order of operations: SYNC the CSV into the
JSON first (above), then emit from that merged JSON. The JSON is the single source of truth; the
CSV only carried the QA's column edits.

**Filter.** Include a scenario **only if its post-sync `execution_mode` matches `Automatable`
(case-insensitive — `automatable`, `AUTOMATABLE`, `Automatable` all qualify).** Manual scenarios
stay in the SDET plan and are omitted from the automation plan. (For a purely backend consumer
you may additionally scope to `execution_scope` ∈ {`BACKEND_ONLY`, `END_TO_END`}; state it if
you do.)

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
- `browserstack_case_id` — the real BrowserStack case identifier. For regression cases this is
  the existing ID from `regression_context.json` (e.g. `C2879733`); for newly uploaded cases
  this is the `TC-XXXXXX` returned by `createTestCasesFromFile`. Carry verbatim from the
  scenario's `browserstack_case_id` field. **Omit entirely** when the scenario has no BS ID —
  never emit `null`.

**Backend-only fields** (`service_name`, `package`, `test_class`, `assertion_class`, `endpoint`,
`curl_reference`) — a mobile SDET plan does not carry these. **Never fabricate them.** Emit them
only when the plan actually has the value. When a `BACKEND_ONLY`/`END_TO_END` scenario needs one
that is absent, omit the field and add an `emit_notes` entry (`follow_up: NEEDS_ANSWER`) naming
the scenario and field. For `FRONTEND_ONLY` scenarios they are simply not applicable — no note.

**Validate** the emitted file against its schema with the same report-never-block rule as every
other output: on failure, still write it, record the validator error, and say so.

---

## Appendix: Category Catalog

**Read `category_catalog.md`** (in this skill's directory) when you reach Step 0
(Test-Category Selection Gate). It contains the detection rules table (Section A)
and the FE-Baseline extras library (Section B). Do NOT read it at skill load —
only when Step 0 needs it.

---

## Guardrails
- **Strict Determinism**: Do not extrapolate, infer, or hallucinate missing requirements. Map inputs directly to schemas without adding unmentioned fields or assumptions.
- **No Fabricated Values (provenance rule)**: Every concrete identifier in the output — feature-flag keys, Litmus/experiment release IDs, deep-link URIs, clickstream event names, API paths, error codes, permission names — MUST be traceable to a specific input field. If a value is not present in any provided context, write `TBD — not in context` (or omit the field / use `null` where the schema allows) and record it as an Open Question in `<feature_key>_analysis.md`. Never invent a plausible-looking value (e.g. a UUID release ID or an event name like `birthday_animation_viewed`) to fill a gap. Clickstream event names in particular come ONLY from a non-empty `clickstream_events` array; if that array is empty, do not name events (per the Telemetry Rules).
- **Category Gate**: AUTO-SELECTED categories (signal-derived) are the mandatory baseline and are always covered; only OPTIONAL EXTRAS are QA-discretionary. Generate for `auto_selected ∪ optional_extras_selected`. The P0 and boundary Hard Coverage Rules override the gate and are always covered.
- **Coverage Audit is blocking**: The Step 4 Coverage Self-Audit Gate MUST pass (every checklist item either `covered` or in `still_blocked` with a reason) — **including the 4c-mix balance audit** — before any output file is written. Coverage is a mechanical property of the inputs, not a model judgment — two different models must produce the same `required` checklist and the same covered/blocked partition, even if scenario wording differs.
- **Business-flow primacy**: the suite's centre of gravity is what the feature is *for*. Core
  business/use-case scenarios — happy paths, end-to-end journeys, alternate valid paths — are
  generated first and form the majority of the suite. Negative, boundary, interruption and
  hygiene scenarios are **complementary**: they are mandatory where the Hard Coverage Rules
  require them, but they must never dominate. Enforced mechanically by Step 4c-mix's balance
  audit, not left to model judgment. Never rebalance by deleting negative coverage — the only
  legal fix is generating the business coverage that was missed.
- **Baseline Determinism**: `fe_baseline` scenarios are curated hygiene, NOT input-derived requirements — stamp `source: "fe_baseline"` and note in `analysis.md` that expected behavior needs PM/dev confirmation. Never present them as spec-backed requirements.
- **Contract Adherence**: Fail explicitly if *all* context files are missing or if essential keys within provided contexts are missing. However, do NOT fail if individual files (like `plan_context.json` or `rfc_context.json`) are absent; instead, proceed with the inputs that are provided, noting the missing contexts in `<feature_key>_analysis.md`.
- **Format Precision**: Outputs must strictly conform to `sdet_plan.schema.json` and the 15-column squad CSV schema without altering column headers or ordering.
- **Frontend Focus**: Test cases/scenarios must be generated *exclusively* for Frontend (FE) context (e.g., client-side UI, mobile views, offline transitions, local error copy, and client-side telemetry verifications). Do not generate backend-only validation or server-side test cases.
- **Navigation Resolution**: every scenario's `steps[]` must reach its screen (including the
  logged-in starting state) through a traceable path — a test hook/deep link, a
  `design_context.ui_flow` walk, or `regression_context.navigation` — or an explicit
  `[NAVIGATION NOT CONFIRMED]` flag when none resolves. Never an assumed or invented arrival.
  Enforced mechanically by Step 4's navigation audit (4c-nav), not left to memory.