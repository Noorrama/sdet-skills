---
name: backend-sdet-plan-generator
description: Generate the backend SDET test plan from extracted context files. Four modes: Pass 1 (full generation), Pass 2 (code delta), Re-trigger (doc change), Review (human feedback via qa_analysis.md). Outputs sdet_plan.json, qa_analysis.md, and sdet_testcases.csv. RFC drives completeness, PRD drives priority, Tasks drive classification, regression drives deduplication.
---

# Backend SDET Plan Generator

Synthesise all extracted context into a structured test plan for human review before code generation begins.

## Model
Reasoning tier — Opus

## Modes of operation

| Mode | Trigger | Inputs | Output scope |
|---|---|---|---|
| Pass 1 | Pre-build, first run | prd + rfc + tasks + regression context | Full scenario set |
| Pass 2 | Post-build, Epic QA Ready | All Pass 1 inputs + `code_change_context` | Delta scenarios only (`is_delta: true`) |
| Re-trigger | Upstream doc changed | Existing `sdet_plan.json` + `doc_change_context` + human feedback | Patch affected scenarios only |
| Review | Human feedback written in `qa_analysis.md` | Existing `sdet_plan.json` + `qa_analysis.md` (feedback section filled) | Apply human corrections; add/modify/deprecate scenarios |

## Mode detection — determined by file presence

Check in **priority order** — use the first match:

| Priority | Check | Mode |
|---|---|---|
| 1 (highest) | `sdet_plan.json` present + `qa_analysis.md` present + `### Feedback` section in `qa_analysis.md` has content beyond the placeholder | **Review** — apply human feedback; other change files deferred until review is incorporated |
| 2 | `sdet_plan.json` absent | **Pass 1** — generate full scenario set |
| 3 | `sdet_plan.json` present + `doc_change_context.json` present | **Re-trigger** — patch affected scenarios only |
| 4 | `sdet_plan.json` present + `code_change_context.json` present | **Pass 2** — delta only, do not regenerate existing scenarios |
| 5 (error) | `sdet_plan.json` present + no feedback and no change files | **Error** — surface: "sdet_plan.json already exists. Write feedback in qa_analysis.md ## Human Review section, or provide code_change_context.json / doc_change_context.json." |

**Detecting Review mode:** Read `qa_analysis.md`. Find the `## Human Review` → `### Feedback` block. If it contains any text other than the placeholder comment `<!-- add feedback here -->`, trigger Review mode.

If `doc_change_context.json` or `code_change_context.json` is also present when Review mode is triggered: run Review first. After clearing the feedback section, the next invocation picks up the remaining change file. Note this in qa_analysis.md.

If both `code_change_context.json` and `doc_change_context.json` are present (no review feedback): prefer **Re-trigger** (priority 3). Note that a Pass 2 run is also pending.

Set `generation_mode` in the sdet_plan.json root to the detected mode: `pass1` | `pass2` | `retrigger` | `review`.

## Reads

| File | Read for |
|---|---|
| `rfc_context.json` | validation_sequence (business rules), flows, edge_cases, error_codes, contracts (all protocols), feature_flags, risk_areas, non_functional_requirements, extraction_gaps, open_questions, provenance |
| `prd_context.json` | `acceptance_criteria[]` (incl. `verifiable` flag), `user_flows[]` + `failure_states[]`, `requirements[]`, `boundary_values[]`, `boundary_conditions[]`, `error_codes[]`, `feature_flags[]`, `non_functional_requirements[]`, `risk_areas[]`, `open_decisions[]` (blocking gate), `needs_clarification[]` (blocking gate), `comment_resolutions[]` (`implication_for_sdet`), `rollout_plan.phases[].variants`, `in_scope`, `out_of_scope` |
| `tasks_context.json` | test_layer per story (authoritative), api_contract (authoritative endpoint + schema), validation_constraints (implementation confirmation), preconditions (contributing input for writing sdet_plan preconditions) |
| `regression_context.json` | Active non-legacy non-flaky tests — deduplication signal |
| `code_change_context.json` | Pass 2 only — new endpoints, new error mappings, new validation rules not in RFC |
| `qa_analysis.md` | Review mode — read the `## Human Review → ### Feedback` section for human corrections. Also read in all modes to preserve the Human Review section when regenerating. |
| `team_registry.json` | Canonical team resolution — maps free-form PRD/RFC team names and dashboard PDG labels to stable `canonical_id`, `code_module`, and `regression_id_prefix`. Read once at startup before scenario generation begins. |

## Team name resolution

PRD/RFC fields use free-form team names (`"Transport"`, `"GoTrip"`, `"payments-team"`). The test code repo uses module directory names (`transport`, `payments`). Dashboards use PDG labels (`"Transport PDG"`). These three naming systems rarely align exactly. The `team_registry.json` is the single source of truth that maps all three to a stable `canonical_id`.

### Why this matters

| Downstream consumer | What it needs | What goes wrong without registry |
|---|---|---|
| **automation-plan-generator** | Exact module directory name for Java package path | Wrong package → test code in wrong module, fails to compile |
| **regression-extractor** | `regression_id_prefix` to filter the correct team's suite | Pulls regression scenarios from a different team |
| **BrowserStack CSV upload** | `browserstack_project` for correct project routing | Tests uploaded to wrong project |

### Context fields that carry team identity

> ⚠️ **Do not confuse these.** Three different fields all contain the word "team" but serve completely different purposes.

| Field path | Example value | Purpose in this skill |
|---|---|---|
| `prd_context.team[]` | `["Transport"]` | **Owning team** — the product group responsible for the PRD. **Primary input for registry lookup.** |
| `prd_context.pdg[]` | `["Transport"]` | **PDG label** — the dashboard/reporting group name. **Secondary input for registry lookup** (matched against `aliases.pdg`). |
| `prd_context.owner` | `null` or a person name | Tertiary input only — rarely the team name; check for a team-like string as last resort. |
| `prd_context.involved_teams[].team` | `"Backend"`, `"Frontend"`, `"Product"` | **Functional roles** — NOT a team identity. These tell you *which discipline* implements each requirement. Used only to filter requirements for scenario generation (this backend skill processes requirements where `team == "Backend"`). Never use for registry lookup. |
| `rfc_context.team_ownership[].team` | `"Transport"` | **RFC owning team** — fallback when `prd_context.team` is absent or null. |

### Resolution algorithm

Run the matching steps below over **every** candidate and keep **every** distinct registry entry that matches — do not stop at the first hit. The candidate order still matters, but only to decide which match becomes the **primary** team: the first successful match is the primary, the rest are additional teams in scope.

Feeding the resolved set to the confirmation gate in *Multi-team features* below is mandatory whenever more than one entry matches.

**Step 1 — Read candidate names:**

```
candidates = []
if prd_context.team is non-empty:
    candidates.append( ("prd", "prd.team", prd_context.team[0]) )
if prd_context.pdg is non-empty:
    candidates.append( ("pdg", "prd.pdg", prd_context.pdg[0]) )
if rfc_context.team_ownership is non-empty:
    candidates.append( ("prd", "rfc.team_ownership", rfc_context.team_ownership[0].team) )
if prd_context.owner is non-null and looks like a team name (not a person name):
    candidates.append( ("prd", "prd.owner", prd_context.owner) )
```

**Step 2 — For each candidate, attempt registry match:**

For each `(alias_type, source_path, raw_name)` in candidates:
1. Normalise: lowercase → strip hyphens/underscores/spaces → strip trailing suffixes `team|platform|pdg|backend`.
2. Try **full match**: for each registry entry, normalise each alias in `aliases.{alias_type}[]` the same way. If normalised alias == normalised raw_name → **match**.
3. If no full match: try **substring match**: normalised alias is contained in normalised raw_name, or vice versa → **match**.
4. On match: use that registry entry. Record `source_path` in a `team_resolution_source` note in qa_analysis.md.

**Step 3 — On no match after all candidates:**
- Write `canonical_team_id: "unknown"`, `code_module: null`.
- Surface warning in qa_analysis.md (see Fallback behaviour below).

### Fallback behaviour

If **no** candidate matches any registry entry:
- Write `canonical_team_id: "unknown"`, `code_module: null` in `sdet_plan.json`
- Add to `qa_analysis.md` generated section:
  > ⚠️ **Team resolution warning:** Team name `"{raw_name}"` from PRD/RFC not found in `team_registry.json`. Downstream code generation and regression lookup will not work correctly. Add an entry or alias to `config/team_registry.json` before raising the MR.

If **some** candidates match and others do not, do not silently drop the unmatched ones. Carry each into `teams_in_scope[]` with `canonical_id: "unknown"`, `included: false` and the raw name that failed, and list it in the confirmation gate alongside the resolved teams. An unmatched name is far more often a missing registry alias than an irrelevant team, and the human at the gate is the person who can tell the difference.

### Multi-team features — resolve every team, then confirm scope with the human

A PRD or RFC routinely names several teams. `prd_context.team` is an **array**, `rfc_context.team_ownership[]` has one entry per owning group, and `rfc_context.service_level_changes[]` lists services that often span them. Resolving only the first candidate and discarding the rest is a silent data loss: the dropped teams appear nowhere in the plan, nowhere in `qa_analysis.md`, and the reviewer cannot tell a choice was made.

**Resolve every candidate, not just the first.** Run the matching algorithm over each entry in `prd_context.team[]`, `prd_context.pdg[]` and `rfc_context.team_ownership[]`, and keep every distinct registry entry that matches.

**Then stop and ask the human before generating any scenario.** Present the resolved set with what each one routes to, and offer three choices:

```
The PRD and RFC name these teams. Which scope should this plan cover?

  Team (as written)        canonical_id          code module           regression   BrowserStack
  Food                     gofood                gofood                GOFOOD-      gofood-backend
  CP                       customer-platforms    customer-platforms    CP-          customer-platforms-backend
  ICP                      icp                   icp                   ICP-         icp-backend
  GoPay                    gopay                 gopay                 GOPAY-       gopay-backend

  1. One team  — generate only scenarios owned by the team you name
  2. All teams — generate the full set, each scenario tagged with its owning team
  3. Primary + foreign-tagged — generate for the primary team, and tag the
     scenarios whose system under test belongs to another team
```

Do not guess the answer and do not proceed on the first match. The choice changes which module the code lands in, which regression suite the scenarios are counted against, and which BrowserStack project receives the upload — three routings a wrong guess silently corrupts.

Record the answer and the full resolved set in `qa_analysis.md`, including the teams the human excluded, so the decision is auditable.

**If a candidate does not resolve**, list it as unresolved in the same prompt rather than dropping it. An unmatched team name usually means a missing registry alias, not an irrelevant team.

### `owning_team` — per-scenario ownership

The plan has one primary team, but individual scenarios may test a service another team owns. Set `owning_team` on every scenario.

**Derivation — use the entry point, not the dependency.** Ownership follows the surface the scenario drives, not every service the flow touches.

| The scenario drives... | Owner | Generate it? |
|---|---|---|
| Our endpoint, their service stubbed | primary | yes |
| Our endpoint or worker, reaching into their live service | primary | yes — an integration flow crossing a team boundary is still ours |
| Our surface degrading when their service is down | primary | yes — the assertion is about our degradation |
| **Their endpoint directly, in isolation** | that team | **no — do not generate** |

The last row is the only exclusion, and it is narrow: a **component-layer** scenario whose entry point is another team's endpoint is that team's unit to test, not ours. Everything else — including integration and e2e flows that traverse their service — belongs to the primary team, because the primary team's behaviour is what fails when the test fails.

The practical test is the entry point in `step_descriptions[].curl_reference`. If the first call goes to our host, the scenario is ours regardless of how many of their services it reaches afterwards. If the first call goes to their host and the layer is `component`, it is theirs.

**Do not silently drop the excluded ones.** Record each in `qa_analysis.md` with its `owning_team`, the surface it would have tested, and why it was excluded, so the owning team can pick it up. A dropped scenario that leaves no trace is indistinguishable from a coverage gap.

A dependency being *involved* does not transfer ownership. Expect the excluded set to be a small minority; a plan where most scenarios are foreign-owned usually means the primary team was resolved wrongly.

Build the service-to-team mapping from `rfc_context.team_ownership[].scope_ref` cross-referenced with `rfc_context.service_level_changes[].service`, and **present it at the same confirmation gate** — it is inference over prose and the human should correct it before it routes anything.

Default `owning_team` to the primary `canonical_team_id`. Set it explicitly on every scenario, including primary-owned ones, so a downstream reader never has to infer it from absence.

### What resolution populates in `sdet_plan.json`

| Field | Source |
|---|---|
| `canonical_team_id` (root) | the **primary** team's `canonical_id` — the team that owns the plan and its review gate |
| `code_module` (root) | the primary team's `code.module` |
| `teams_in_scope[]` (root) | every resolved team: `canonical_id`, `code_module`, `regression_id_prefix`, `browserstack_project`, the raw name it matched, and whether the human included it |
| `owning_team` (per scenario) | the `canonical_id` owning that scenario's system under test |

> **`code_module` is still the contract field for the primary team**, but it is no longer sufficient on its own. `automation-plan-generator` must resolve the module per scenario from `owning_team` via the registry, falling back to the root `code_module` when `owning_team` equals the primary. Uploading a foreign-owned scenario to the primary team's BrowserStack project puts it in the wrong suite and bills it to the wrong team's coverage.

## Ownership contract — A = authoritative (wins conflicts), C = contributes

This is the RFC's formal A/C matrix applied per dimension. When sources conflict, A wins. C sources confirm or add detail but never override A.

| Dimension | Authoritative (A) | Contributing (C) |
|---|---|---|
| API endpoints + schema | `tasks_context.api_contract` (route, request_fields, response_fields) | `rfc_context.contracts.rest[]` · `code_change_context` |
| Business logic / validation rules | `rfc_context.validation_sequence` (ordered steps, constraints, failure codes) | `tasks_context.validation_constraints` · `code_change_context` |
| Acceptance criteria + error scenarios | `prd_context` (business classification, AC list) | `tasks_context` (impl error code strings) · `rfc_context.error_codes[]` · `code_change_context` |
| Test layer assignment | `tasks_context.test_layer` per story | `rfc_context.validation_sequence[].layer` (signal only — do not use to assign test_layer) |
| Package / class naming | `tasks_context` component + package | — |
| Test-data / preconditions | `sdet_plan.json` — **this output is authoritative once written** | `prd_context` (business state) · `tasks_context.preconditions` · `rfc_context.flows[].trigger` |
| Scenario priority | `prd_context` priority · `rfc_context.risk_areas[].priority` (P0 escalates) | `tasks_context` story priority |
| Protocol contracts (gRPC, Kafka) | `rfc_context.contracts.grpc[]` / `kafka[]` | `code_change_context` |
| Feature flag behaviour | `rfc_context.feature_flags[]` | `tasks_context` (implementation of the flag) |

### Field-level reading contract

**READ FROM `rfc_context` (A) for business logic and scenario completeness:**

| Field | What it drives in scenario generation |
|---|---|
| `validation_sequence[]` | Happy-path + failure + boundary scenarios per step |
| `flows[].type + outcome` | One scenario per flow; `type` → tag; `outcome` → assertion prose |
| `edge_cases[]` | One scenario per edge case; `inferred: true` → mark `provisional: true` |
| `error_codes[]` | Cross-story error scenario dedup; `is_retriable: true` → add retry-behaviour scenario |
| `contracts.rest[]` | API-level scenarios per endpoint; skip if `underspecified: true` |
| `contracts.grpc[]` | gRPC method scenarios (happy + error + stream interruption if not unary) |
| `contracts.kafka[]` | Producer → message-published scenario; consumer → processing scenario; `dlq` set → poison-message scenario |
| `contracts.other[]` | Scheduled worker / DB-direct / migration scenarios per trigger |
| `feature_flags[]` | flag_on + flag_off pair; `kill_switch: true` → kill-switch scenario |
| `risk_areas[]` | P0 risk → force P0 on covering scenario; uncovered P0 → generate scenario + surface in gaps |
| `non_functional_requirements.performance_targets[]` | Load scenario per entry (see NFR rules below) |
| `non_functional_requirements.nfr_statements[]` | Qualitative NFR scenarios from prose (see NFR rules below) |
| `non_functional_requirements.security_compliance[]` | Data masking + auth + compliance scenarios |
| `non_functional_requirements.reliability_targets[]` | Timeout + retry-exhaustion + circuit-breaker scenarios |
| `extraction_gaps[]` | Blocking gate — see section below |
| `open_questions[]` | Deferred scenarios — see section below |
| `provenance` | Staleness warning in qa_analysis.md if `extracted_at` is stale |

**READ FROM `prd_context` (A) for priority, business intent, and scenario completeness:**

| Field | What it drives in scenario generation |
|---|---|
| `acceptance_criteria[]` | One scenario minimum per AC. `verifiable: false` → mark scenario `provisional: true`, tag `["provisional"]`, note in qa_analysis.md that deterministic assertion is not yet possible |
| `acceptance_criteria[].condition` | Given/When/Then text; extract exact thresholds and preconditions from the condition string |
| `user_flows[]` | One end-to-end scenario per flow (`tags: ["happy_path"]` or `["fallback"]` per flow type) |
| `user_flows[].failure_states[]` | One negative scenario per failure state; `outcome` → assertion prose; tag `["negative"]` |
| `requirements[].product_requirement` | Read alongside AC — encodes implementation constraints and edge cases the AC condition may abbreviate |
| `boundary_values[]` | One boundary scenario per entry; use the exact `value` in assertions (e.g. `distance ≤ 20m` → test at exactly 20m, 21m) |
| `boundary_conditions[]` | One edge case scenario per entry; `proposed_default` → expected system behaviour to assert |
| `error_codes[]` | One negative scenario per error code; `trigger` → precondition; `expected_recovery` → assertion on fallback behaviour |
| `feature_flags[]` | flag-on + flag-off pair per flag; cross-reference with `rfc_context.feature_flags[]` for richer metadata (default_state, kill_switch) |
| `non_functional_requirements[]` | Latency/SLA scenario per entry with `target` as the assertion threshold; tag `["nfr"]` |
| `risk_areas[]` | `severity: high` → force P0 on covering scenario; `mitigation` → add a destructive/chaos variant scenario |
| `comment_resolutions[]` | Read `implication_for_sdet` — use as additional scenario hints or constraints. `status: "unanswered"` → mark covering scenarios `provisional: true` |
| `rollout_plan.phases[].variants` | If multiple experiment variants exist (e.g. ≤30m vs ≤40m distance gate) → generate one scenario per variant, tag with variant name |
| `in_scope` | Cross-check: every in-scope item must have at least one scenario; flag gaps in qa_analysis.md |
| `out_of_scope` | Do not generate scenarios for flagged flows; note in coverage_summary.rfc_gaps[] if RFC has steps for them |
| `open_decisions[]` | `blocking: true` → see Blocking gates; `blocking: false` → mark covering scenarios `provisional: true` |
| `needs_clarification[]` | `blocking: true` → see Blocking gates; `blocking: false` → mark covering scenarios `provisional: true` |

**READ FROM `tasks_context` (A) for test layer and endpoint schema:**
- `test_layer` per story → authoritative for all scenarios in that story; do not infer test_layer from `rfc_context.validation_sequence[].layer`
- `api_contract.route + method` → authoritative endpoint; cross-check with `rfc_context.contracts.rest[].path` and flag drift in qa_analysis.md
- `api_contract.request_fields + response_fields` → authoritative schema; use for precondition field names in step_descriptions
- `validation_constraints[]` → confirms RFC rules are implemented; adds implementation-specific error code strings as C input — does not override `validation_sequence` rule order or logic

**READ FROM `code_change_context` (C) — Pass 2 only:**
- New endpoints not in RFC → new component scenarios; flag as `rfc_gap`
- New error handling → new negative scenarios
- New feature flags → new flag-state scenarios

## Conflict resolution

| Conflict | Resolution |
|---|---|
| `tasks_context.api_contract.route` ≠ `rfc_context.contracts.rest[].path` | tasks wins; flag drift in qa_analysis.md RFC ↔ Tasks conflicts section |
| `tasks_context.test_layer` ≠ layer implied by `rfc_context.validation_sequence[].layer` | tasks wins unconditionally; RFC layer is a signal, not an assignment |
| `rfc_context.error_codes[]` error name ≠ `tasks_context.api_contract.error_codes` string | tasks wins for the exact code string; RFC wins for the business condition that triggers it — combine both |
| PRD marks a flow out-of-scope but RFC has validation steps for it | PRD wins; do not generate; note in coverage_summary.rfc_gaps[] |
| `rfc_context.validation_sequence` rule conflicts with `tasks_context.validation_constraints` rule | RFC wins for rule logic and order; tasks wins for implementation fields (exact class name, field path) |
| `rfc_context.risk_areas[priority: P0]` but PRD assigns P1 to the same scenario | Escalate to P0; flag in qa_analysis.md for human review |

## Blocking gates — check before generating any scenario

Run in order. Blocked areas must not produce scenarios.

| Check | Action |
|---|---|
| `rfc_context.extraction_gaps[blocking: true]` | Do not generate scenarios for the affected `field` path; add entry in `coverage_summary.rfc_gaps[]` with `blocked_by_extraction_gap: true` |
| `rfc_context.approach_finalised: false` | Generate scenarios but mark all contract-derived assertions `provisional: true`; add warning in qa_analysis.md |
| `rfc_context.contracts.rest[underspecified: true]` | Skip concrete request/response assertions for that endpoint; generate a placeholder scenario with `tags: ["underspecified"]` |
| `rfc_context.open_questions[]` not empty | For each question add a deferred scenario with `tags: ["deferred"]`, `source_ref` pointing to the question; do not block other scenarios |
| `rfc_context.provenance` stale (extracted_at old relative to current date) | Surface warning in qa_analysis.md: "rfc_context was extracted on {extracted_at} — verify RFC has not changed since extraction" |
| `prd_context.open_decisions[blocking: true]` | Do not generate final scenarios for areas affected by the decision; generate a placeholder with `tags: ["deferred"]` and `source_ref` pointing to the open decision ID; surface in qa_analysis.md as a blocking PRD gap |
| `prd_context.needs_clarification[blocking: true]` | Same as above — deferred placeholder per item; `reason` field → note in placeholder description; surface in qa_analysis.md |
| `prd_context.acceptance_criteria[verifiable: false]` | Generate scenario but mark `provisional: true`; note in qa_analysis.md that assertion cannot be deterministic until clarified by product/design |

## Scenario granularity — apply BEFORE the per-source rules below

Everything in "Scenario generation rules" is a **multiplier**: a dozen separate rules each saying "one scenario per X". Left unchecked they yield roughly one assertion per scenario, which inflates the plan, multiplies test-data provisioning calls at runtime, and does not match how backend tests are actually written in `gojek-backend-tests`.

Apply this rule first. It bounds every rule that follows.

### The unit of a scenario is one Arrange — not one assertion

**Group into ONE scenario every check that shares the same precondition state and the same triggering call.**
**Split into separate scenarios only when the precondition differs** — never when only the assertion differs.

| Situation | Correct treatment |
|---|---|
| Endpoint response gains 4 new fields | ONE scenario, 4 steps — not 4 scenarios |
| Worker must stop for COMPLETED, CANCELLED and DELETED | ONE scenario, 3 steps — same arrange, three data rows |
| Skip rule fires when a field is absent OR empty | ONE scenario, 2 steps |
| Caller is ACTIVE vs caller is PENDING | TWO scenarios — the precondition differs |
| 400 bad_request vs 404 not_found | TWO scenarios — different request state |
| flag ON vs flag OFF | TWO scenarios — the precondition differs |

Target step counts by layer — a single global band mis-fits validation gates:

| Layer | Target steps | Typical shape |
|---|---|---|
| component | 3–4 | act, assert the response, assert no side effect |
| integration | 4–6 | act, assert the response, assert persisted state, assert enqueued jobs or downstream effect |
| e2e | 4–8 | one step per hop across the chain |

A 1-step scenario is almost always under-grouped. A scenario needing more than 3 distinct `fixture_ids` is over-grouped — split it.

### Why the Arrange boundary specifically

Per-scenario flake risk rises with the number of fixtures and async waits the scenario needs; total suite flake is that summed over scenarios. Grouping assertions that need **no additional fixture** strictly lowers total flake. Grouping beyond that point starts adding fixtures per scenario and stops helping — a scenario provisioning six entities fails if any one of the six flakes. The Arrange boundary is therefore a genuine minimum, not a style preference.

Backend has no equivalent of the frontend's `login → deeplink → navigate` preamble, so grouping here is justified by provisioning cost and flake, not by execution time.

### Async boundaries get grouped harder

Scenarios that cross Kafka → consumer → Redis → downstream-read each need their own polling window, and each window is an independent flake source. Write **one** scenario that walks the full async chain with explicit waits, and have the remaining scenarios seed the downstream state directly and assert the read path synchronously. Do not give every async assertion its own wait.

### Never share a fixture that a scenario mutates

If a scenario mutates fixture state (adds a member, attaches an entity, changes status), that fixture must not be reused by other scenarios expecting the pre-mutation state. Reusing a mutated fixture creates order-dependence — the classic "passes alone, fails in suite" flake. Give mutating scenarios their own `fixture_ids`.

### Prefer stubs over provisioned data for failure paths

Downstream-failure scenarios (timeout, 5xx, unreachable dependency) should be driven by request-level stubs, not by provisioned entities. Stubs are deterministic and cost no runtime provisioning call. List only the fixtures the scenario genuinely needs in `fixture_ids`.

### Scenarios are BrowserStack test cases, not Java test methods

These are two different granularities and must not be conflated. In `gojek-backend-tests` a single test method carries a mean of **2.26** BrowserStack case ids via `@TestInfo(testCaseIds={...})` (max observed 17), a mean of **5.1** assertions, and **89%** of methods drive permutations through a TestNG `dataProvider` rather than duplicated methods.

Set `scenario_group` on every scenario, keyed by its Arrange — the same precondition state and triggering call. This records a test-design fact that downstream tooling needs but cannot reliably re-derive from prose preconditions, and it is what stops `automation-plan-generator` emitting one test method per scenario.

Do not size the plan to the method count. Scenarios may legitimately outnumber test methods; the ratio depends on how many natural permutation axes the feature has (service type, payment method, country). A feature with no such axis will sit near 1:1 and that is correct.

## Scenario generation rules

> Every rule below is subject to **Scenario granularity** above. Where a rule says "one scenario per X", it means one scenario per X **unless** two or more X share the same precondition and trigger — in which case they become steps of a single scenario.

### RFC validation_sequence — business logic (A)

For each step:
- **Happy path** — step succeeds with valid inputs → `tags: ["happy_path"]`
- **Failure** — one negative scenario per `failure_error_code` the step can produce → `tags: ["negative"]`
- **Boundary** — quantitative constraints in `constraint` field (min/max/edge) → `tags: ["boundary"]`

Use `tasks_context.test_layer` for the story that implements this step — never infer test_layer from `validation_sequence[].layer`.

**Assert the short-circuit, not just the rejection.** `validation_sequence` is ordered, and the `layer` field (`controller` → `service` → `gateway`) records where each gate sits. The ordering is itself a contract: a cheap local gate must reject before an expensive remote one runs. "Returns 422" does not prove that; "returns 422 **and the gateway was never invoked**" does.

For each failure scenario on step *N*, where any later step *M > N* involves an external call, add an assertion that step *M*'s dependency was **not** called. Without it a reordered implementation — one that calls the dependency first and validates afterwards — passes every test while doing an unnecessary remote call on every rejected request, and leaking existence information about ids the caller has no right to probe.

### RFC flows — end-to-end scenario paths

For each flow:
- One scenario covering the full step sequence
- `tags`: `happy_path` | `fallback` | `deviation` — match `flows[].type`
- Assertion prose: use `flows[].outcome` verbatim as the expected result

### RFC edge_cases

- One scenario per edge case
- `inferred: true` → add `provisional: true`; note in qa_analysis.md as "extractor-inferred, verify against RFC"
- `validation_step_ref` set → mark scenario as related to the parent step scenario

### RFC contracts — gRPC

For each `contracts.grpc[]` entry:
- Happy path: valid request → correct response → `test_layer: component`
- Error: dependency unavailable → correct gRPC status code asserted
- `streaming_type != unary` → add stream-interruption scenario

### RFC contracts — Kafka

For each `contracts.kafka[]` entry:
- `produces_to` → message-published scenario: trigger operation, assert message on topic with correct schema
- `consumes_from` → message-received scenario: publish test message, assert correct service side effect
- `dlq` set → poison-message scenario: malformed message → assert routed to DLQ, not silently dropped
- `delivery_guarantee: exactly_once` → duplicate-message scenario: assert exactly-once semantics hold

### RFC contracts — other (workers, DB-direct, migration pipelines)

For each `contracts.other[]` entry:
- One scenario per `trigger`; `test_layer: integration`
- `frequency` contains deadline → add deadline-breach scenario (simulate delay past deadline, assert correct behaviour)

### RFC feature_flags

For each flag:
- `flag_on` scenario + `flag_off` scenario → `tags: ["flag_on"]` / `tags: ["flag_off"]`
- `kill_switch: true` → kill-switch scenario: enable flag, assert feature fully disabled
- Use `gated_behavior` as the assertion description

### RFC risk_areas — priority escalation

- `P0` risk with no covering scenario → generate one; `priority: P0`
- `P0` risk with existing scenario → force that scenario to `priority: P0`
- `P1` risk → ensure covering scenario exists at `priority: P1` minimum
- All uncovered P0 risks → surface in `coverage_summary.rfc_gaps[]`

### RFC non_functional_requirements

**performance_targets[]** — structured load signals:
- `throughput_tps` or `throughput_ops_per_day` present → load scenario: note target TPS as assertion parameter; `tags: ["load", "nfr"]`
- `concurrency_ceiling` present → concurrency scenario: at `safe_tps` assert 0% failure; if `degraded_onset_tps` set, add second scenario asserting documented failure behaviour
- `slo_deadline` present → deadline-breach scenario: simulate slow execution past deadline, assert system handles it correctly; `tags: ["nfr", "reliability"]`

**nfr_statements[]** — qualitative NFR prose:
- Read each statement for intent signal:
  - "eliminate deadlocks / race conditions" → concurrent-write scenario; `tags: ["concurrency", "nfr"]`
  - "data integrity / balance consistency" → consistency-assertion scenario; `tags: ["nfr"]`
  - "resumable after failure" → failure-and-resume scenario; `tags: ["reliability", "nfr"]`
  - "near-zero-downtime rollout" → rollout-cutover scenario; `tags: ["nfr"]`
- Do not generate duplicate scenarios if a structured `performance_targets[]` entry already covers the same NFR

**security_compliance[]** — one scenario per entry:
- `data_masking` → assert target field absent or masked in response body AND logs; `tags: ["security", "nfr"]`
- `auth` → expired-token scenario + missing-token scenario; `tags: ["security", "negative"]`
- `PCI-DSS` → card PAN must not appear in API response or log output; `tags: ["security", "compliance", "nfr"]`
- `GDPR` → personal data handling assertion per requirement description

**reliability_targets[]** — one scenario per entry per relevant field:
- `timeout_ms` → slow-downstream scenario: inject latency above `timeout_ms`, assert timeout fires and correct error is surfaced
- `retry_count` → retry-exhaustion scenario: downstream fails `retry_count + 1` times, assert final error is surfaced correctly and no infinite loop
- `circuit_breaker_error_rate_pct` → circuit-breaker-activation scenario: sustain error rate above threshold, assert circuit opens and fallback activates; `tags: ["reliability", "nfr"]`

### PRD — full scenario generation (A)

**acceptance_criteria[]** — one scenario minimum per AC:
- PRD error classification is authoritative: if PRD says 409 for duplicate card, generate that scenario regardless of whether RFC names the error
- `verifiable: false` → `provisional: true`; note in qa_analysis.md that assertion is not yet deterministic
- If RFC already has a matching scenario → link via `source_ref`, do not duplicate

**user_flows[]** — one end-to-end scenario per flow:
- `trigger` → Given precondition; `steps[]` → step_descriptions actions in sequence
- `tags: ["happy_path"]` for normal flows; `tags: ["fallback"]` for fallback flows
- `failure_states[]` — one negative scenario per failure state:
  - `name` → scenario name; `outcome` → expected_result assertion; `tags: ["negative"]`
  - Priority: `P0` if the flow failure can cause user-visible mismatch (e.g. wrong pickup location); `P1` otherwise

**boundary_values[]** — one boundary scenario per entry:
- Generate three test points per threshold: at exactly the boundary, one unit below, one unit above
- Use the exact numeric `value` in assertions (e.g. `≤20m` → test at 20m, 19m, 21m)
- `source_ref` → `requirement_ref` from the boundary_values entry
- `tags: ["boundary"]`

**boundary_conditions[]** — one edge case scenario per entry:
- `edge_case_description` → scenario description and Given precondition
- `proposed_default` → expected system behaviour; use as the assertion in expected_result
- `tags: ["boundary"]`; mark `provisional: true` if `proposed_default` says "TBD" or is vague

**error_codes[]** — one negative scenario per error code:
- `trigger` → precondition; `expected_recovery` → fallback assertion; `user_facing_message` → assert displayed to user
- `source_ref` → `"prd_context.error_codes[{code}]"`

**feature_flags[]** — flag-on + flag-off pair per flag string:
- Cross-reference with `rfc_context.feature_flags[]` for richer metadata (default_state, kill_switch)
- PRD flag list is the source of truth for flag names; RFC flag metadata drives scenario variants

**non_functional_requirements[]** — one scenario per entry:
- `target` → assertion threshold (e.g. `p95 ≤ 500ms`)
- `tags: ["nfr"]`; `type_of_test: "performance"`

**risk_areas[]** — one destructive/chaos scenario per `severity: high` risk:
- `risk` → scenario description; `mitigation` → what the scenario verifies
- `priority: P0`; `tags: ["reliability"]` or `["security"]` as appropriate

**rollout_plan.phases[].variants** — if experiment variants exist:
- One scenario per variant, tagged with the variant name (e.g. `["variant_30m"]`, `["variant_40m"]`)
- If open_decisions[blocking] covers the variant choice → mark all variant scenarios `provisional: true`

**comment_resolutions[]** — read `implication_for_sdet` for each entry:
- `status: "resolves"` → use `what_is_now_clear` to refine existing AC-derived scenario assertions
- `status: "clarifies"` → add detail from `implication_for_sdet` to relevant scenario step_descriptions
- `status: "unanswered"` → mark covering scenarios `provisional: true`

**in_scope cross-check** — after generating all scenarios:
- Every item in `in_scope[]` must map to at least one generated scenario; flag unmapped items in qa_analysis.md

### Pass 2 — code_change_context (C)

- New endpoint not in RFC → component scenario + `rfc_gap` flag
- New validation rule not in RFC → scenario + `rfc_gap` flag
- New error mapping → negative scenario
- All Pass 2 scenarios: `is_delta: true`

## Completeness sweeps — run AFTER the per-source rules, BEFORE the granularity check

The rules above generate from what the documents **state**. These four sweeps generate from what documents systematically **omit**. An RFC records the rules it intends; it does not record that a job can run twice, that an array can be empty, or that a condition has an inverse. Those gaps are structural, not accidental, so they need mechanical sweeps rather than careful reading.

**These sweeps must not re-inflate the plan.** Each finding folds into an existing scenario as an extra step wherever it shares that scenario's Arrange. Only create a new scenario when the check genuinely needs a different precondition — which, for the concurrency sweep, it usually does.

### Sweep 1 — Repeat, concurrent and out-of-order execution

Trigger on the **existence of a retry, an async job, or a write path reachable by more than one actor** — never on a `delivery_guarantee` or `retry_dlq` field being populated. Those fields are usually null, and their absence is not evidence that redelivery cannot happen; at-least-once is the safe default assumption.

| Structure in the RFC | Required scenario |
|---|---|
| Any enqueued job or worker | Job runs twice → assert the effect happened exactly once |
| Any documented retry (`the job retry re-runs it`) | Retry after partial success → assert no duplicate entity is created |
| Any Kafka consumer | Duplicate message delivered → assert the write is idempotent |
| Any endpoint that creates or attaches a singleton | Two concurrent calls → assert exactly one wins and the loser gets the documented error |
| Any request that a client may resend (booking, checkout, submit) | Same request sent twice → assert one downstream effect |
| Any job whose trigger fires from more than one path | Two triggers converge → assert one outcome, not two |
| **Any endpoint documented as returning a retryable error** (502, timeout, any 5xx) | Failure then retry → assert the retry succeeds cleanly and the failed attempt left no partial state |

Three distinct shapes live here and are easy to conflate. Generate each one that applies:

| Shape | Sequence | Asserts |
|---|---|---|
| Duplicate submission | success, success | one downstream effect |
| Retry after failure | failure, success | clean success, no residue from the failed attempt |
| Concurrent double-run | two in parallel | the lock or upsert holds; exactly one winner |

A synchronous endpoint that can return 502 needs the retry-after-failure case just as much as an async job does — the concept is not specific to workers. Where an operation is both retried and concurrently reachable, generate the sequential and concurrent cases separately.

### Sweep 2 — Cardinality boundaries on every collection

For each array or collection field in a contract request, response, or stored payload, generate the **empty, one, and at-limit** cases. Do not wait for `boundary_values[]` to name them — documents state numeric thresholds and almost never state that a list can be empty or hold exactly one element.

Split the sweep by side, because the two sides have different yield and different enumeration units.

**Read side — enumerate per collection, once.**

| Collection | Cases |
|---|---|
| Request array (`user_ids`, `participants`, `members`) | empty array · single element |
| Response array | empty · single |
| Stored collection (map, list) | zero entries · one entry |

Zero and one are the highest-yield cases: an empty array frequently reaches a downstream call it should have short-circuited, and a single-element collection frequently exposes logic written for the plural case.

**Write side — enumerate per `(collection × mutating operation)`, not per collection.**

For each collection, list **every endpoint or job that mutates it**, and generate at-limit and over-limit for each mutator independently. A collection with three write paths needs three at-limit scenarios, because the behaviour differs by path: reaching the limit, and acting when already at the limit, are different states and often different code.

| Step | Action |
|---|---|
| 1 | List every collection in the contracts and stored payloads |
| 2 | For each, list every operation that adds to it — endpoint, worker, consumer |
| 3 | For each `(collection, mutator)` pair, generate: mutate to reach the limit exactly · mutate when already at the limit |

Reading a full collection is rarely where a bug lives; writing to one at its boundary almost always is. A single at-limit scenario covering only the read path does **not** discharge this sweep.

### Sweep 3 — Assert the negative of every conditional

For each rule of the form *"X happens when C"*, generate the **NOT-C** case asserting X does **not** happen. The per-source rules cover the positive branch; the inverse is what catches a condition that was implemented as always-true.

Apply the same to design decisions recorded as out of scope. Distinguish two kinds of `out_of_scope` entry:
- **Scope exclusion** ("Manage Participant is not in M5") → generate nothing, per the blocking gates.
- **Design decision** ("we do not persist this in the Waiter DB", "at most one social group per session", "MPS carries only the id") → **assert the absence**. These are deliberate constraints that a future change can silently violate, and nothing else in the plan protects them.

### Sweep 4 — Contract request-field validation

For each contract with a documented `request_body` or query parameters, generate validation coverage the error table does not enumerate:
- each `required: true` field omitted → assert rejection, not a 5xx
- a field present with the wrong type or an out-of-enum value
- assert what the response must **not** contain, where the contract says a field is deliberately absent (e.g. a detail response that omits the member roster)
- **each optional parameter whose alternate value is never exercised in the documented flows** → generate the non-default case

The last rule is scoped deliberately. An optional field the happy paths already exercise both ways needs nothing. The target is a parameter the RFC only ever shows at one value — a query flag documented solely as `=true`, an enum with one usage — because the other branch has no coverage anywhere and nobody notices it is missing.

### Sweep 5 — Dependency degradation

For every dependency the feature runs through, assert what the user-facing surface does when that dependency is unavailable, and that upstream state stays correct.

**Enumerate the dependency set from the union of three fields — never from `cross_service_dependencies[]` alone.** That field routinely lists only the named external services and omits infrastructure, so a feature whose critical path runs through a queue or a cache will have no degradation coverage for the hop most likely to break.

| Source field | Contributes |
|---|---|
| `service_level_changes[]` | every service the feature touches, including internal ones |
| `protocols_used[]` | REST, gRPC, Kafka, Redis, DB-direct — each is a failure domain |
| `contracts.other[]` | workers, caches, direct-DB mechanisms and scheduled jobs |
| `cross_service_dependencies[]` | the documented `failure_behavior`, where one is stated |

For each dependency in the union, generate one scenario asserting:
- what the user-facing surface renders or returns while the dependency is down
- that upstream state written before the failure remains correct and is not rolled back or corrupted
- that the surface recovers once the dependency returns, where recovery is expected

Where `cross_service_dependencies[].failure_behavior` states the expected behaviour, assert it. Where it does not, assert the surface degrades without erroring and record the undefined expectation as a gap — do not skip the scenario because the behaviour is unstated.

### Coverage ledger — mandatory before writing output

Two of these gap classes come from rules that already exist but were skipped, not from missing rules. Enumeration catches those; careful reading does not. Build an explicit ledger and refuse to write output while any row is unmapped:

| Source item | Every instance must map to ≥1 scenario |
|---|---|
| `rfc.validation_sequence[]` | each step |
| `rfc.error_codes[]` | each code |
| `rfc.business_logic[]` | each rule id |
| `rfc.contracts.*[]` | each endpoint, topic and mechanism |
| `rfc.contracts.*.request_body[required: true]` | each field (Sweep 4) |
| `rfc.in_scope[]` | each item |
| `rfc.out_of_scope[]` classified as a design decision | each item (Sweep 3) |
| `rfc.open_questions[]` | each question with a testable surface |
| `prd.acceptance_criteria[]` | each AC, or an explicit no-backend-surface note |
| `prd.user_flows[].failure_states[]` | **each failure state** |
| `prd.boundary_values[]` and `boundary_conditions[]` | each entry |
| `prd.risk_areas[]` | each `High` or `Blocking` risk |
| Every async job, retry and multi-actor write path | Sweep 1 |
| Every collection field in a contract | Sweep 2, read side |
| Every `(collection × mutating operation)` pair | Sweep 2, write side |
| Every `(endpoint × documented retryable error)` pair | Sweep 1, retry-after-failure |
| Every `(dependency × user-facing surface)` pair, from the three-field union | Sweep 5 |
| Every optional parameter with an unexercised alternate value | Sweep 4 |
| Every `(ordered validation step × later external call)` pair | short-circuit assertion |

Record the ledger's unmapped rows in `qa_analysis.md` with a reason for each. An item with no backend surface is a legitimate reason; being overlooked is not.

**The ledger is the backstop, not the sweeps.** The sweeps are prose heuristics and their triggers have repeatedly turned out narrower than the concept they describe — a collection sweep that fired once instead of per write path, a repeat-execution sweep that reached async jobs but not synchronous endpoints, a failure sweep that read only `cross_service_dependencies[]`. The ledger does not depend on the prose being worded correctly: it enumerates cross-products mechanically and refuses to write output while a cell is unjustified. When a sweep and the ledger disagree, the ledger wins. When a new class of miss is found, add a ledger row for it before rewording the sweep.

## Ownership note — sdet_plan.json is authoritative for preconditions

Once `sdet_plan.json` is written and approved by a human:
- It becomes the authoritative (A) source for test-data needs and preconditions per the RFC's A/C matrix
- PRD and tasks were contributing (C) inputs used to write this plan; the plan now owns the output
- Downstream skills (automation-plan-generator, test-data-generator) read preconditions from `sdet_plan.json`
- They do NOT re-read `prd_context`, `rfc_context`, or `tasks_context` for preconditions or fixture decisions

## Output → sdet_plan.json

Schema root:
- `feature_name`, `plan_version`, `generation_mode: pass1|pass2|retrigger|review`
- `canonical_team_id: string` — resolved from `team_registry.json`. `"unknown"` if no match; triggers warning in qa_analysis.md. Stable across plan versions even if team renames (update registry alias instead).
- `code_module: string | null` — exact test code module directory name from `team_registry.json code.module`. Consumed verbatim by `automation-plan-generator` for Java package path construction. `null` when resolution failed.
- `scenarios[]` — each with:
  - `scenario_id`, `name`, `description`
  - `test_layer: component|integration|e2e`
  - `priority: P0|P1|P2`
  - `source: RFC|PRD|CODE_DIFF|RETRIGGER|REVIEW`, `source_ref`
  - `generated_by_mode: pass1|pass2|retrigger|review` — which execution mode **created** this scenario. Set once at creation; never overwritten. `review` = scenario added purely from human review feedback (not present in any automated pass).
  - `review_round: integer` — which review round last touched this scenario. `0` = not yet reviewed. Incremented on every Review-mode run that modifies or creates the scenario. Unmodified scenarios retain their current `review_round`.
  - `provisional: boolean` — true when `approach_finalised: false` or `edge_case.inferred: true`
  - `is_delta: boolean` — true for pass2, retrigger, and review-added scenarios (shorthand for `generated_by_mode != pass1`; kept for downstream tool compatibility)
  - `is_legacy_regression`, `is_dedup`
  - `test_type: string[]` — BrowserStack TestType. **Multi-select array** — collect all applicable values (see CSV section). Minimum one entry; never null or empty.
  - `execution_mode: Automatable|Manual` — BrowserStack Execution Mode. `Manual` for scenarios tagged `deferred` or `underspecified`; `Automatable` for all others.
  - `markets: array` — Countries this scenario applies to. Values: `Indonesia` | `Singapore`. Derived from `tasks_context.environments`; default `["Indonesia", "Singapore"]` when not specified.
  - `type_of_test: functional|performance` — BrowserStack Type of Test Case. `performance` **only** when tags contain `load` or `nfr` — i.e. the scenario measures a throughput or latency target. Everything else is `functional`, including `reliability` and `concurrency` scenarios: a timeout, retry-exhaustion, circuit-breaker or race-condition test asserts *functional* behaviour under adverse conditions, it does not measure performance.
  - `step_descriptions[]` — `step`, `action`, `curl_reference`, `expected_result`. Target 4–6 steps per scenario (see Scenario granularity). Every `expected_result` is a concrete assertion phrased as `Verify …`; `action` is imperative. Steps and expected results are 1:1.
  - `preconditions[]`, `fixture_ids[]`
  - `scenario_group: string` — key shared by scenarios that rest on the **same Arrange**: the same precondition state and the same triggering call, differing only in the data row exercised. A test-design fact, not an automation instruction — it applies equally to `Manual` scenarios, where it tells a human tester which cases can be executed back-to-back off one setup. A scenario with no sibling gets its own unique key. Format: `{feature_component}-{behaviour}`, e.g. `chatextension-terminal-status`. Downstream consumers decide what to do with the grouping; see `automation-plan-generator` for how it maps to test methods.
  - `browserstack_test_id: string | null` — BrowserStack's own id for this scenario, assigned when the plan is uploaded through the BrowserStack MCP. **Emit `null` at generation time and never author a value.** The sync writes it back after upload, which is what makes the plan round-trippable: re-running Review or Pass 2 can then update the existing case instead of creating a duplicate. Do not confuse it with `existing_testcase_ids[]` — that names cases which existed *before* this plan; this names the case *this* scenario became.
  - `existing_testcase_ids: string[]` — BrowserStack case ids (e.g. `TC-302383`) that this scenario extends, replaces, or re-runs under a new flag state. Populated from `regression_context.json` when present; empty otherwise. Rendered into the `Preconditions` block as `Existing regression case:` and consumed downstream for `@TestInfo(testCaseIds={...})`. Do **not** invent ids — leave empty when `regression_context.json` is absent.
  - `tags[]` — `happy_path|negative|boundary|flag_on|flag_off|e2e|load|concurrency|security|reliability|compliance|nfr|deferred|underspecified|provisional`
  - `human_corrected: boolean` — `false` at generation time. Set to `true` in Review mode when the scenario is modified or deprecated by human feedback. Never reset to false. For scenarios with `generated_by_mode: "review"`, this is implicitly `true` (the scenario is itself a human addition) but the field is still set explicitly.
  - `human_correction_types: string[]` — empty at generation. Appended per review round with the type of correction applied: `"field_change"` (one or more fields corrected), `"deprecated"` (LLM generated an incorrect/duplicate scenario), `"missed_scenario"` (LLM failed to generate this; set on review-added scenarios). Multiple rounds may push multiple entries.
- `coverage_summary` — `total`, `by_layer`, `by_priority`, `rfc_steps_covered`, `rfc_steps_total`, `rfc_gaps[]`
- `llm_quality` — updated after each Review run; tracks LLM generation accuracy:
  - `auto_approved: integer` — scenarios not touched by any review round
  - `human_modified: integer` — scenarios with `human_correction_types` containing `"field_change"`
  - `human_deprecated: integer` — scenarios deprecated by review (LLM over-generated)
  - `human_added: integer` — scenarios added by review (LLM under-generated; `generated_by_mode: "review"`)
  - `llm_accuracy_pct: float` — `auto_approved / (auto_approved + human_modified + human_deprecated)` × 100. Excludes `human_added` from denominator (can't penalise the LLM for what it never generated)
  - `review_rounds_completed: integer`

## Output → qa_analysis.md

`qa_analysis.md` is a **living document** — the generated analysis sections are above a `---` divider; the `## Human Review` section below the divider is written once and preserved across all subsequent regenerations (Pass 2, Re-trigger). Never overwrite the Human Review section during generation.

### Generated sections (above `---`)

Human-readable summary for SDET + PM review gate:
- Total scenarios by layer and priority
- RFC coverage % (scenarios / validation steps)
- Gaps — RFC steps with no scenario, blocked extraction gaps, provisional scenarios
- New vs existing regression coverage
- Risk areas and their covering scenarios; uncovered P0 risks flagged
- RFC ↔ Tasks contract conflicts (endpoint drift, schema drift)
- Open questions surfaced as deferred scenarios
- Provenance staleness warning if applicable
- LLM generation quality (after first Review run): auto-approved count, human-modified, human-deprecated, human-added, accuracy %
- **Granularity check** — mean steps per scenario, count of 1-step scenarios, scenarios exceeding 3 fixtures, and the `scenario_group`-to-scenario ratio (see Log). Call out explicitly if the plan drifted toward one-assertion-per-scenario.
- **Market assumption** — which market(s) were set and on what basis, flagged for confirmation whenever they were inferred rather than read from `tasks_context.environments`.
- **BrowserStack sync** — after a sync has run, how many scenarios carry a `browserstack_test_id` and how many are still null, with the project they landed in. Before the first sync, state plainly that none are tracked yet.
- **Team scope** — the full `teams_in_scope[]` table with each team's module, regression prefix and BrowserStack project, which team is primary, the scope the human confirmed at the gate, and an **excluded-by-scope table** naming every scenario dropped for team reasons with its `owning_team`, entry point and what it covered. An excluded scenario that leaves no trace here is indistinguishable from a coverage gap.
- **Coverage ledger** — the full table with every unmapped row and its stated reason. This is the section a reviewer scans to find what the plan does not cover, so unmapped rows belong here in full rather than summarised.
- **Completeness sweep results** — how many scenarios or steps each of the four sweeps contributed. A sweep contributing zero is a signal it was skipped, not that the feature had nothing to find.

### Human Review section (below `---`, written once, never regenerated)

Append this block when first generating `qa_analysis.md`. On subsequent Pass 1/2/Re-trigger runs, preserve it verbatim — do not regenerate it.

```markdown
---

## Human Review

**Review Round:** 0
**Status:** `pending`

### Feedback

<!-- add feedback here -->

### Applied

_(History of incorporated feedback rounds appears here after each Review run.)_
```

**Feedback format:** free-form text — one item per line works well. No JSON required. Examples:
```
SC-EPIC1122-003: change test_layer to integration, priority to P1 — spans multiple services
SC-EPIC1122-018: remove — duplicate of SC-006
Add: card save when vault is under degraded load — should queue and retry, not fail (ties to NFR-02)
General: missing coverage for concurrent same-customer saves
```

The human writes in the `### Feedback` block and re-invokes the skill. The LLM interprets the free-form text and applies corrections.

## Output → sdet_testcases.csv

Flat CSV for BrowserStack upload via BrowserStack MCP after human approval. Column names must match BrowserStack's import contract exactly.

### BrowserStack columns

| CSV column | Maps from | Notes |
|---|---|---|
| `Id` | `scenario_id` | External ID for traceability |
| `Title` | `name` | Human-readable scenario name |
| `Priority` | `priority` | P0 / P1 / P2. P3/P4 not generated by this skill. |
| `Platform` | Constant `Backend` | This skill generates backend test cases only |
| `Execution Mode` | `execution_mode` | `Automatable` or `Manual` (see derivation below) |
| `Backend Automation Status` | Constant `Not Automated` | Initial upload value — updated to `Automated` after test-code-generator merges code |
| `Country v2` | `markets[]` joined | e.g. `Indonesia, Singapore`. Determines which country Automation Status cells are active |
| `TestType` | `test_type` | See derivation below |
| `Type of Test Case` | `type_of_test` | `functional` or `performance`. See derivation below — `reliability` and `concurrency` are functional, not performance. |
| `Preconditions` | `preconditions[]` | Rendered as the templated block below. **Required** — a Manual scenario with no preconditions is not executable by a human tester. |
| `Steps` | `step_descriptions[].action` | Newline-joined and numbered `1.`, `2.`, `3.` … |
| `Expected Result` | `step_descriptions[].expected_result` | Newline-joined and numbered to **exactly match** the Steps numbering — step *n* maps to expected result *n*. Each line starts with `Verify …`. |

> **Steps and Expected Result must have identical line counts.** This 1:1 numbering is the house convention across existing GoFood and Transport test cases; a mismatch makes the case unexecutable and is a generation error.

### `Preconditions` block format

Render `preconditions[]` as a newline-separated block. The first four lines are mandatory on every scenario:

```
Test data: <what must be provisioned, referencing fixture_ids>
Country: <Indonesia | Singapore>
Entry point: <endpoint or trigger under test>
<feature_flag_name>: is_enabled = <true | false>
```

Then, when applicable:
```
Existing regression case: <TC-xxxxxx from existing_testcase_ids>
```

**Every scenario pins feature-flag state explicitly, including scenarios that are not themselves flag tests.** Scenarios covering pre-existing BAU behaviour declare the new feature's flag as `is_enabled = false (default)` — that is how the plan proves the feature does not break existing behaviour.

### Internal tracking columns (appended after BrowserStack columns)

| CSV column | Maps from | Purpose |
|---|---|---|
| `test_layer` | `test_layer` | component / integration / e2e — for filtering in CI |
| `generated_by_mode` | `generated_by_mode` | pass1 / pass2 / retrigger — audit trail |
| `is_delta` | `is_delta` | Filter new scenarios from existing in PR reviews |
| `is_legacy_regression` | `is_legacy_regression` | Flag pre-existing covered scenarios |
| `source_ref` | `source_ref` | Traceability back to RFC step / PRD AC |
| `tags` | `tags[]` joined | Pipe-separated for filtering |
| `human_corrected` | `human_corrected` | `true` if any review round modified or deprecated this scenario — LLM accuracy signal |
| `human_correction_types` | `human_correction_types[]` joined | Pipe-separated: `field_change`, `deprecated`, `missed_scenario` |
| `owning_team` | `owning_team` | Which team's module and BrowserStack project this scenario routes to |
| `browserstack_test_id` | `browserstack_test_id` | Empty on the upload CSV — BrowserStack assigns it. Populated only when the CSV is re-exported after a sync, so a reviewer can see what is already tracked. |

### `TestType` derivation — additive multi-select (collect **all** that apply)

`test_type` is an array. Evaluate every rule independently and ADD the value when the condition is true. A scenario can carry multiple types (e.g. `["Regression","Smoke"]`).

| Rule | Condition | Value added |
|---|---|---|
| 1 | `is_legacy_regression: true` | `Regression` |
| 2 | tags ∩ {`load`, `nfr`, `reliability`, `concurrency`, `security`, `compliance`} ≠ ∅ | `Non-FCT` |
| 3 | `priority: P0` **AND** `happy_path` in tags | `Smoke` |
| 4 | NOT `is_legacy_regression` (scenario is new work for current epic) | `Story` |
| 5 | None of rules 1–4 matched (empty set fallback) | `Automation` |

**Examples:**
- Legacy P0 happy-path → `["Regression", "Smoke"]`
- New scenario with `security` tag → `["Non-FCT", "Story"]`
- New P1 boundary negative → `["Story"]`
- New scenario with `load` + `nfr` tags → `["Non-FCT", "Story"]`

**CSV serialisation:** join with `,` — e.g. `Regression,Smoke`. BrowserStack parses the comma-delimited string as multiple selected values on import.

### `Execution Mode` derivation

| Condition | Value |
|---|---|
| tags contain `deferred` or `underspecified` | `Manual` |
| All other scenarios | `Automatable` |

### `Country v2` / `markets[]` derivation

Read from `tasks_context.environments` per story. Map environment names to BrowserStack country values:

| environments value | Country v2 value |
|---|---|
| `id`, `id-*`, `staging-id`, `prod-id` | `Indonesia` |
| `sg`, `sg-*`, `staging-sg`, `prod-sg` | `Singapore` |
| `dev-cluster`, `staging-cluster` (no country suffix) | Cannot be inferred — see below |

**Do not default to both markets.** `Country v2` decides which per-country Automation Status cells are active in BrowserStack, so listing a market the feature does not ship to creates permanently-unfilled cells and overstates scope.

When `tasks_context.environments` is absent or carries no country suffix, resolve in this order:
1. A market named in `prd_context` (title, `rollout_plan`, or scope text) — e.g. a PRD titled `[M5][GO]` or naming an Indonesia-only launch.
2. The market used by the team's existing test cases for this surface, if `regression_context.json` is present.
3. Fall back to `["Indonesia"]` — the default market for GoTo backend services.

In cases 2 and 3, record the assumption in `qa_analysis.md` and ask the human reviewer to confirm before the BrowserStack upload. Only set both markets when a source explicitly says the feature ships to both.

### `Type of Test Case` derivation

| Condition | Value |
|---|---|
| tags contain `load` or `nfr` | `performance` |
| All other scenarios — including `reliability`, `concurrency`, `security`, `compliance` | `functional` |

`reliability` and `concurrency` describe *what adverse condition* the scenario sets up, not that it measures a performance target. A retry-exhaustion or lost-update test is functional. Only a scenario asserting a throughput or latency number is `performance`.

## Pass 2 rules

Do not regenerate the full plan. Append delta scenarios only.

**Delta matching — skip if already covered:**

For each item in `code_change_context.json`, check whether an existing scenario in `sdet_plan.json` already covers it:

| code_change_context item | Match criterion | If matched | If not matched |
|---|---|---|---|
| New endpoint | `(method + path)` appears in any scenario's `step_descriptions[].curl_reference` or `endpoint` | Skip | Generate new scenario |
| New error code | Error code string appears in any scenario's `step_descriptions[].expected_result` | Skip | Generate new negative scenario |
| New validation rule | Rule description closely matches any scenario's `step_descriptions[].action` or `expected_result` | Skip | Generate new scenario + flag as `rfc_gap` |
| New feature flag | Flag name appears in any scenario's `tags[]` (flag_on / flag_off pair) | Skip | Generate flag_on + flag_off pair |

All generated scenarios: `generated_by_mode: "pass2"`, `is_delta: true`.
Flag code-diff items that have no RFC match with `source: CODE_DIFF` and add to `coverage_summary.rfc_gaps[]`.

## Re-trigger rules

Do not regenerate unaffected scenarios. Patch only what the doc change touched.

**Scenario matching — find what to patch:**

Re-trigger uses `source_ref` on each existing scenario to trace back to the source AC, flow, or validation step. When `doc_change_context.json` reports a change:

| doc_change_context item | Find affected scenarios by | Action |
|---|---|---|
| AC modified | `source_ref` contains the AC ID | Update step_descriptions, assertions, preconditions. Set `generated_by_mode: "retrigger"`, add `change_reason`. |
| AC removed | `source_ref` contains the AC ID | Set `status: "deprecated"`, add `change_reason`. Do not delete — human reviewer decides final removal. |
| AC added | No existing match | Generate new scenario. `generated_by_mode: "retrigger"`, `is_delta: true`. |
| Flow changed | `source_ref` contains the flow name | Update outcome assertion and steps. Set `generated_by_mode: "retrigger"`, add `change_reason`. |
| Validation step changed | `source_ref` contains the step ref | Update constraint / failure_code assertions. Set `generated_by_mode: "retrigger"`, add `change_reason`. |

`change_reason` field: one sentence stating what changed and why the scenario was updated, e.g. "AC-003 updated: error code changed from 409 to 422 per PRD v2".

## Review Incorporation rules

Read and apply the human's free-form feedback from the `### Feedback` block in `qa_analysis.md`. Do not regenerate unaffected scenarios.

### Reading the feedback

The `### Feedback` block is free-form text. Parse it as a list of intent statements. For each statement, classify the intent:

| Intent | Signal words / patterns | Action |
|---|---|---|
| **Modify** | Scenario ID mentioned + correction described | Find the scenario; apply the correction |
| **Remove** | "remove", "delete", "drop", "duplicate of" | Deprecate the scenario |
| **Add** | "add", "missing", "add a scenario for", no scenario ID | Generate a new scenario |
| **General comment** | No specific scenario, no action implied | Capture in review summary; no plan change |

If a statement is ambiguous, apply the most conservative interpretation and surface the ambiguity in the review summary for human follow-up.

### Per-intent behaviour

**Modify** — find by scenario ID mentioned in the feedback text:
- Apply the stated change (priority, test_layer, name, description, preconditions, tags, step corrections, etc.)
- Re-derive `test_type`, `execution_mode`, `type_of_test` after applying the change
- Increment `review_round` on the scenario
- Set `change_reason` to a one-sentence summary of what changed and why (from the feedback text)
- Set `human_corrected: true`
- Append `"field_change"` to `human_correction_types[]` (if not already present)

**Remove** — find by scenario ID:
- Set `status: "deprecated"`, `change_reason: <reason from feedback>`
- **Do not delete** — human decides final removal in a later pass
- Increment `review_round`
- Set `human_corrected: true`
- Append `"deprecated"` to `human_correction_types[]`

**Add** — generate a new scenario from the description:
- Apply all standard scenario generation rules (test_type derivation, execution_mode, markets, type_of_test, step_descriptions, preconditions)
- Assign next `scenario_id` in sequence
- Set `generated_by_mode: "review"`, `is_delta: true`, `review_round: <current round>`
- Set `source: REVIEW`, `source_ref: "human-review-r{N}"`
- Set `human_corrected: true`, `human_correction_types: ["missed_scenario"]`

### Invariants

- **`generated_by_mode` is never changed** on existing scenarios — only `review_round` is updated.
- **`is_legacy_regression`** is immutable — cannot be changed by review feedback.
- **Unmodified scenarios** keep their current `review_round`; do not touch them.
- If a scenario ID mentioned in feedback does not exist in the plan → surface a warning in the review summary; skip, do not crash.
- After all items are applied, re-derive `test_type` for every modified scenario.

### Post-application steps

1. Increment `plan_version` in the root (`1.0` → `1.1`).
2. Set root `generation_mode: "review"`.
3. Recompute `llm_quality` block in `coverage_summary`:
   - Count `auto_approved` = scenarios where `human_corrected: false` and `generated_by_mode != "review"`
   - Count `human_modified` = scenarios where `human_correction_types` contains `"field_change"`
   - Count `human_deprecated` = scenarios where `human_correction_types` contains `"deprecated"`
   - Count `human_added` = scenarios where `generated_by_mode: "review"` (i.e. `human_correction_types` contains `"missed_scenario"`)
   - Compute `llm_accuracy_pct` = `auto_approved / (auto_approved + human_modified + human_deprecated) * 100` (round to 1 decimal)
   - Increment `review_rounds_completed`
4. Regenerate `sdet_testcases.csv` with the full updated scenario set.
5. **Update `qa_analysis.md`** — this is the key step:
   - Increment `Review Round` counter in the Human Review section header.
   - **Clear** the `### Feedback` block — replace its content with `<!-- add feedback here -->` so the next invocation does not re-apply the same feedback.
   - **Append** to the `### Applied` block a round summary:

```markdown
#### Round {N} — {date}

- **Modified** SC-EPIC1122-003: test_layer component → integration; priority P0 → P1
- **Removed** SC-EPIC1122-018: deprecated (duplicate of SC-006)
- **Added** SC-EPIC1122-023: vault degraded load resilience (NFR-02)
- ⚠️ Ambiguous: "check concurrent saves" — no scenario ID found; please clarify in next round

**LLM generation quality after round {N}:**
Auto-approved: {N} | Human-modified: {N} | Human-deprecated: {N} | Human-added (missed): {N}
LLM accuracy: {X}% ({auto_approved}/{auto_approved+modified+deprecated} scenarios needed no correction)
```

This preserves the full audit trail in the same file the human is reading. The LLM accuracy metric accumulates across rounds — each round adds to `human_corrected` counts so the figure reflects total corrections over the plan's lifetime, not just the latest round.

## Validate

`jsonschema.validate(output, schemas/sdet_plan.schema.json)`

## Log

Total scenarios, RFC coverage %, gaps count, blocked gaps count, provisional count, delta count (Pass 2/Re-trigger).

Also log the granularity metrics, so drift back to one-assertion-per-scenario is visible:
- mean `step_descriptions` per scenario — **expect 4–6**; below 3 means the granularity rule was not applied
- count of 1-step scenarios — expect near zero
- count of scenarios with more than 3 `fixture_ids` — expect zero
- distinct `scenario_group` values vs total scenarios — report it, do **not** tune the plan to hit a number. The ratio is a property of the feature, not of plan quality: it rises only when the feature has natural permutation axes (service type, payment method, country) that let sibling scenarios share one Arrange. `gojek-backend-tests` averages 2.26 case-ids per test method largely on the strength of such matrices; a feature without one will sit near 1.2:1 and that is the correct answer. Investigate only a ratio of exactly 1.0 across the whole plan, which usually means `scenario_group` was assigned arbitrarily rather than derived from the Arrange.
- total `fixture_ids` references across automatable scenarios — the runtime provisioning-call count, and the dominant flake driver

### Self-check before writing output

Reject and regroup if any of these hold:
- mean steps per scenario < 3
- more than 20% of scenarios have exactly 1 step
- `scenario_group` is missing on any scenario, or every scenario has a unique one (it was not derived from the Arrange)
- `owning_team` is missing on any scenario, or names a `canonical_id` absent from `teams_in_scope[]`
- more than one registry entry matched and the scope confirmation gate was not run
- a scenario was excluded for team scope without a corresponding entry in the `qa_analysis.md` excluded-by-scope table
- `teams_in_scope[]` omits a team named in `prd_context.team[]`, `prd_context.pdg[]` or `rfc_context.team_ownership[]`, whether it resolved or not
- the coverage ledger has an unmapped row with no stated reason
- any async job, retry or multi-actor write path has no repeat-execution scenario (Sweep 1)
- any endpoint with a documented retryable error has no retry-after-failure scenario (Sweep 1)
- any contract collection field has no empty-case scenario (Sweep 2, read side)
- any `(collection × mutating operation)` pair has no at-limit scenario (Sweep 2, write side)
- any `prd.user_flows[].failure_states[]` entry has no covering scenario
- any `out_of_scope` design decision has no absence assertion (Sweep 3)
- any optional parameter with an unexercised alternate value has no non-default scenario (Sweep 4)
- any dependency in the three-field union has no degradation scenario (Sweep 5)
- any ordered validation step followed by an external call lacks a dependency-not-invoked assertion
- any two scenarios share a fixture set, a trigger, and a precondition but differ only in which field they assert — those must be merged
- `Steps` and `Expected Result` line counts differ for any scenario
