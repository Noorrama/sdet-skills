---
name: backend-sdet-plan-generator
description: Generate the backend SDET test plan from extracted context files. Four modes: Upstream-context (full generation from the extracted upstream context), Code-change-context (post-build reconciliation against the merged diff, including code_change_context.reconciliation), Doc-change-context (upstream doc change), Review (human feedback via qa_analysis.md). Plus BrowserStack sync — a post-approval upload layered on top of any mode, always confirmed with the user first, never a fifth mode. Outputs sdet_plan.json, qa_analysis.md, and sdet_testcases.csv. RFC drives completeness, PRD drives priority, Tasks drive classification, regression drives deduplication.
---

# Backend SDET Plan Generator

Synthesise all extracted context into a structured test plan for human review before code generation begins.

## Model
Reasoning tier — Opus

## Modes of operation

| Mode | Trigger | Inputs | Output scope |
|---|---|---|---|
| Upstream-context | Pre-build, first run | prd + rfc + tasks + regression context | Full scenario set |
| Code-change-context | Post-build, Epic QA Ready | All Upstream-context inputs + `code_change_context` (incl. its `reconciliation` object) | Confirm, patch and extend against the merged diff; delta scenarios `is_delta: true` |
| Doc-change-context | Upstream doc changed | Existing `sdet_plan.json` + `doc_change_context` + human feedback | Patch affected scenarios only |
| Review | Human feedback written in `qa_analysis.md` | Existing `sdet_plan.json` + `qa_analysis.md` (feedback section filled) | Apply human corrections; add/modify/deprecate scenarios |

**BrowserStack sync is not a fifth mode.** It never generates, patches or reviews a scenario — it only uploads ones already `approved` and writes tracking fields back. It layers on top of any of the four modes above and on the no-op "already exists" state; see `## BrowserStack sync` after the CSV output section.

## Mode detection — determined by file presence

Check in **priority order** — use the first match:

| Priority | Check | Mode |
|---|---|---|
| 1 (highest) | `sdet_plan.json` present + `qa_analysis.md` present + `### Feedback` section in `qa_analysis.md` has content beyond the placeholder | **Review** — apply human feedback; other change files deferred until review is incorporated |
| 2 | `sdet_plan.json` absent | **Upstream-context** — generate full scenario set |
| 3 | `sdet_plan.json` present + `doc_change_context.json` present | **Doc-change-context** — patch affected scenarios only |
| 4 | `sdet_plan.json` present + `code_change_context.json` present | **Code-change-context** — reconcile against the merged diff; do not regenerate unaffected scenarios |
| 5 | `sdet_plan.json` present + no feedback and no change files + root `status: approved` + at least one scenario eligible for BrowserStack sync (see `## BrowserStack sync`) | **BrowserStack sync check** — ask the user; on "no" or no answer, fall through to priority 6 |
| 6 (error) | `sdet_plan.json` present + no feedback and no change files + (root not `approved`, or nothing eligible, or the priority-5 ask was declined) | **Error** — surface: "sdet_plan.json already exists. Write feedback in qa_analysis.md ## Human Review section, or provide code_change_context.json / doc_change_context.json." |

**Detecting Review mode:** Read `qa_analysis.md`. Find the `## Human Review` → `### Feedback` block. If it contains any text other than the placeholder comment `<!-- add feedback here -->`, trigger Review mode.

If `doc_change_context.json` or `code_change_context.json` is also present when Review mode is triggered: run Review first. After clearing the feedback section, the next invocation picks up the remaining change file. Note this in qa_analysis.md.

If both `code_change_context.json` and `doc_change_context.json` are present (no review feedback): prefer **Doc-change-context** (priority 3). Note that a Code-change-context run is also pending.

If more than one `code_change_context*.json` is present, use the one whose `extraction_date` is latest and name the file used in qa_analysis.md. A file whose name is not exactly `code_change_context.json` does not trigger the mode — say so rather than silently reading a copy.

Set `generation_mode` in the sdet_plan.json root to the detected mode: `upstream_context` | `code_change_context` | `doc_change_context` | `review`.

**An explicit user request to upload/sync to BrowserStack overrides this table entirely** — check the `## BrowserStack sync` eligibility gate directly rather than waiting to land on priority 5. It still refuses outright if root `status != "approved"`; being asked directly does not lower that bar.

## Stage 1 — Upstream Service Check / DoR gate (ALWAYS FIRST; on pass, continue to Upstream-context)

Run before anything else — before reading the files for content, before the team-scope
question, before any generation. Collect every failure — do not stop at the first — so the
rejection report is complete and one round trip fixes everything.

### DoR checks

1. **Presence** — all 4 context files (`prd_context.json`, `rfc_context.json`,
   `tasks_context.json`, `regression_context.json`) exist in the run directory.
2. **Valid JSON / schema-valid** — each file loads as JSON and matches its upstream
   extractor's output contract (verify only; no transformation, no merging, no re-emission).
3. **PRD has at least one `acceptance_criteria` entry** — without ACs, no scenarios can be
   derived.
4. **Regression file present even if empty** — empty coverage arrays are fine and expected;
   the **file's** absence is not, because legacy-regression status then cannot be determined
   for any scenario.
5. **Regression entries matchable** — every `automated_tests[]`/`manual_tests[]` entry has a
   `requirement_ref` or an `api_endpoint`. An entry with neither cannot be matched to a
   generated scenario — skip that entry for dedup purposes and report it; reject the run only
   when no usable entry remains.

### On reject — STOP

Any file missing/unparseable/schema-invalid, or zero PRD ACs: write `validation_report.json`
to the run directory and **stop — do not enter any generation mode**. No team question, no
scenarios, no other output files. Each failure names the file, the failed check, and the
owning extractor stage so the fix is routed to the right PIC and only the failing extractor
is re-run — not the whole batch.

```json
{
  "status": "REJECT",
  "failures": [
    { "file": "prd_context.json", "check": "min_acceptance_criteria", "detail": "0 ACs found", "owner_stage": "prd-extractor" }
  ]
}
```

### On pass — continue

Note observations worth carrying into generation (blocking open decisions, draft contracts,
empty coverage arrays, skipped regression entries) and continue into the detected mode,
starting with team resolution and the scope confirmation gate below.

**Degrade, do not reject** for everything inside a present-and-valid file — blocking
`open_decisions[]` / `needs_clarification[]` / `extraction_gaps[]` entries block *their own
area* via the Blocking gates section, never the run.

## Reads

| File | Read for |
|---|---|
| `rfc_context.json` | validation_sequence (business rules), flows, edge_cases, error_codes, contracts (all protocols), feature_flags, risk_areas, non_functional_requirements, extraction_gaps, open_questions, provenance |
| `prd_context.json` | `acceptance_criteria[]` (incl. `verifiable` flag), `user_flows[]` + `failure_states[]`, `requirements[]`, `boundary_values[]`, `boundary_conditions[]`, `error_codes[]`, `feature_flags[]`, `non_functional_requirements[]`, `risk_areas[]`, `open_decisions[]` (blocking gate), `needs_clarification[]` (blocking gate), `comment_resolutions[]` (`implication_for_sdet`), `rollout_plan.phases[].variants`, `in_scope`, `out_of_scope` |
| `tasks_context.json` | `test_layer` at **story and task** level (authoritative — see below), `api_contract` (authoritative endpoint + schema), `validation_gates[]` (ordered gate chain with `is_remote`), `validation_constraints` (implementation confirmation), `canonical_team_id`, `external_systems[]`, `non_functional_targets[].has_backend_surface`, `preconditions` (contributing). **Never** `priority`. |
| `regression_context.json` (the resolver's `scope.json`) | Existing coverage in the blast radius, scoped by **service** not feature. Read `testCases[]` (id + name), `resolvedServices[]` (`testGroups`/`testClasses` for the signoff run), `unresolvedServices[]`, `unmatchedTestCaseIds[]` and `browserstack.status`. Field names are camelCase. |
| `code_change_context.json` | Code-change-context mode. **Read the whole file, not a subset.** Extraction arrays: `new_endpoints`, `changed_endpoints`, `validation_rules`, `error_mappings`, `db_changes`, `new_enums`, `dependency_changes`, `auth_changes`, `feature_flags`, `proto_changes`. Plus `reconciliation` — `baseline_type`, `sdet_plan_ref`, `error_code_mismatches[]`, `contract_changes[]`, `info_gaps[]`, `impacted_scenarios[]`, `suggested_scenarios[]`, `unresolved[]`. `code-change-extractor` has always emitted `reconciliation`; a reader that skips it discards the pre-matched signal it exists to carry. |
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

  1. One team        — generate only scenarios owned by the team you name
  2. Multiple teams  — name any subset (multi-select); generate only scenarios
     owned by the selected teams, each tagged with its owning team
  3. All teams (e2e) — generate the full set, each scenario tagged with its owning team
  4. Primary + foreign-tagged — generate for the primary team, and tag the
     scenarios whose system under test belongs to another team
```

**The selection is multi-select** — the SDET may pick one team, any subset of teams, or all
teams (e2e). Do not guess the answer and do not proceed on the first match. The choice changes
which module the code lands in, which regression suite the scenarios are counted against, and
which BrowserStack project receives the upload — three routings a wrong guess silently corrupts.

Record the answer and the full resolved set in `qa_analysis.md`, including the teams the human
excluded, so the decision is auditable. When multiple teams are selected, the checklist,
coverage ledger and audit run against the selected subset; items owned by unselected teams are
listed in the excluded-by-scope table, never silently dropped.

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
| Test layer assignment | `tasks_context.test_layer` — task-level for task-derived scenarios, story-level for story-spanning ones | `rfc_context.validation_sequence[].layer` (signal only — never use to assign test_layer) |
| Package / class naming | `tasks_context` component + package | — |
| Test-data / preconditions | `sdet_plan.json` — **this output is authoritative once written** | `prd_context` (business state) · `tasks_context.preconditions` · `rfc_context.flows[].trigger` |
| Scenario priority | `prd_context` priority · `rfc_context.risk_areas[].priority` (P0 escalates) | — (**never** `tasks_context` priority — see below) |
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

### `tasks_context` is an evolving contract — read it defensively

`tasks_context.json` is produced by another team whose extractor is still in development. Any sample of it seen during this skill's development is a **sample, not the contract** — field shapes, derivations and coverage will change. Two standing rules follow:

1. **Treat every field below `feature_name` and `epics[]` as optional.** Only `id`/`title`/`stories` on an epic and `id`/`type`/`component` on a task are guaranteed. Check presence before reading; never let an absent field become a default value. Absent is *undetermined*, not zero, not empty, not false.
2. **Never re-implement their derivations here.** Where they own a value, read it. A copy of their rule in this skill is a copy that drifts silently the moment their branch moves.

Degrade per field — a missing field costs one input, never the run:

| Absent field | Degrade to |
|---|---|
| `test_layer` | our own fallback rule (below) |
| `api_contract` | `rfc_context.contracts.rest[]`; flag endpoints as unconfirmed |
| `validation_gates[]` | `rfc_context.validation_sequence` order; treat `is_remote` as unknown, not false |
| `validation_constraints` | `rfc_context.validation_sequence` alone; scenarios stay valid, implementation detail is thinner |
| `canonical_team_id` | resolve via the team registry from the service name |
| `external_systems[]` | do **not** infer a layer from its absence — see rule 1 |
| `non_functional_targets[].has_backend_surface` | treat as unknown; include the scenario and mark it for confirmation |
| `preconditions` | `prd_context` business state + `rfc_context.flows[].trigger` (already the A/C order) |
| `environments` | the market resolution order already defined below |
| `component` / `package` | derive naming from the feature and module; flag as derived |

Record in `qa_analysis.md` which authoritative inputs were actually present, as one line. When their extractor lands for real, that line is what shows whether a thin plan was thin because the feature was small or because the input was.

### Test layer — read it at the matching scope, do not re-derive it

`tasks_context` carries `test_layer` at both story and task level. These are **not in conflict**; they describe different scopes:

| Scenario covers | Read layer from |
|---|---|
| One task's behaviour — an endpoint, a migration, a worker job | that **task's** `test_layer` |
| A flow spanning several tasks in one story | that **story's** `test_layer` |
| A flow spanning stories or epics | the widest layer among the stories it crosses |

A story is the widest layer among its tasks, so applying story-level uniformly would over-classify: in one real breakdown STORY-01 is `e2e` while its four tasks are integration, e2e, integration and component. A component-level scenario derived from the component-level task must not inherit the story's `e2e`.

**Read the value; do not re-derive it and do not second-guess it.** `tasks_context` is produced by the planning team and its layer derivation is theirs to own — it may change without changing anything here. Take `test_layer` verbatim at the matching scope, even where our own reading of the scenario would have chosen differently. If a value looks wrong, note it in `qa_analysis.md` under extraction concerns and carry on with their value; never silently override it, and never build a correction rule here that has to track theirs.

Read `external_systems[]` and `test_layer_derivation.basis` only as context for a reviewer. **Absent is not empty** — a missing `external_systems` means undetermined, never zero, and must never be turned into `component`.

Internal layers of the same service — controller, service, gateway, repository — are **not** external systems. A task is not component-level merely because it looks small: an API task whose logic calls a downstream service crosses one boundary and is integration. A DB migration crosses one boundary and is integration; it cannot be proven against a mock.

**Stubbing a downstream does not lower the layer.** This is the mistake to avoid: a scenario is not `component` because its downstream *could* be stubbed. Backend suites here run against real deployed services — TestNG groups are suite and environment labels (`REGRESSION`, `SANITY`, `PHOENIX`), not layer labels, and there is no stubbed component tier to fall back to. `component` means the behaviour is provable **inside one service with no boundary crossed at all** — request validation, field defaulting, in-service state transitions, serialisation. Everything else is at least `integration`. Expect `component` to be a small minority of scenarios; if it comes out as a third of the plan, the rule has been applied as "mockable" instead of "no boundary crossed".

**When `tasks_context` is absent entirely**, derive the layer here — this fallback is ours, and it is written for what we consume `test_layer` for: choosing where the test file lands (`package` and `test_class` in the automation plan). Component vs integration is about *boundaries crossed*; integration vs e2e is about *entry points chained*. Do not use one measure for both.

| Layer | Fallback rule |
|---|---|
| `component` | No boundary crossed — provable inside one service. |
| `integration` | At least one boundary crossed, driven by a **single entry point** — one API call or one consumed event — however many downstreams it fans out to. |
| `e2e` | **Multiple chained entry points** — a journey, where a later call depends on state left by an earlier one. |

A fan-out is not a journey: an endpoint calling two downstreams is `integration`. Count boundaries from `rfc_context.contracts.*` and `cross_service_dependencies[]`; count chained calls from the scenario's own steps.

Record in `qa_analysis.md` that layers were derived rather than read, and that this fallback rule was used — if `tasks_context` later arrives with a different derivation, that note is what makes the divergence visible.

### Never take scenario priority from `tasks_context`

`tasks_context` carries `priority` at epic, story and task level. **None of it may drive scenario priority.** Planning priority reflects development sequencing — what must be built first given dependencies and team capacity. Scenario priority reflects business and user-journey risk — what breaks worst for a user. Those are different questions, and a task being built first says nothing about whether its failure matters most.

The observed data makes this concrete: in one real breakdown every task carried `priority: P0` with `priority_derivation.basis` reading *"Inherited from EPIC-01 (P0); planning marks no priority on tasks."* The epic's own priority was derived from a feature spec whose priorities were themselves derived, with an open question noting the RFC states no explicit tiers. Reading that as business priority would mark an entire plan P0 on the strength of one inherited value.

Priority comes from `prd_context` priority and PRD risk severity, escalated by `rfc_context.risk_areas[priority: P0]`. If neither source states a priority, say so in `qa_analysis.md` rather than borrowing planning's.

`priority_derivation.confidence` is still worth reading — not to set priority, but to know how much of the planning artifact is inference when weighing anything else it says.

**READ FROM `tasks_context` (A) for test layer and endpoint schema:**
- `test_layer` per story → authoritative for all scenarios in that story; do not infer test_layer from `rfc_context.validation_sequence[].layer`
- `api_contract.route + method` → authoritative endpoint; cross-check with `rfc_context.contracts.rest[].path` and flag drift in qa_analysis.md
- `api_contract.request_fields + response_fields` → authoritative schema; use for precondition field names in step_descriptions
- `validation_constraints[]` → confirms RFC rules are implemented; adds implementation-specific error code strings as C input — does not override `validation_sequence` rule order or logic

**READ FROM `code_change_context` (C) — Code-change-context mode only:**
- New endpoints not in RFC → new scenarios; flag as `rfc_gap`
- New error handling → new negative scenarios
- New feature flags → new flag-state scenarios
- DB, dependency, enum, auth and proto changes → new scenarios where nothing asserts them
- `reconciliation.impacted_scenarios[]` → the confirm / patch / deprecate shortlist, **after** the Job 0 binding gate
- `reconciliation.suggested_scenarios[]` → net-new hints; this skill mints the `SC-` id, the extractor never does

**Still C, not A.** The diff never overrides `tasks_context.api_contract` or `rfc_context.validation_sequence` on its own — see the Job 2 gate.

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

### Failure paths — check the module can stub before writing a stub

Where request-level stubbing is available, prefer it to provisioned entities for downstream-failure scenarios (timeout, 5xx, unreachable dependency): stubs are deterministic and cost no runtime provisioning call. This is a **data** technique, not a layer technique — a stubbed downstream failure is still an `integration` scenario. See the test-layer rule above.

**Stubbing is not available in every module, so confirm it before relying on it.** The gofood suite has no WireMock/`stubFor`/MockServer usage across 2,315 Java files. In a module like that, a step reading a stub call log is an instruction nobody can carry out — assert the observable absence of the downstream's side effect instead, and record the limitation in `qa_analysis.md`.

Either way, list only the fixtures the scenario genuinely needs in `fixture_ids`.

### Scenarios are BrowserStack test cases, not Java test methods

These are two different granularities and must not be conflated. In `gojek-backend-tests` a single test method carries a mean of **2.26** BrowserStack case ids via `@TestInfo(testCaseIds={...})` (max observed 17), a mean of **5.1** assertions, and **89%** of methods drive permutations through a TestNG `dataProvider` rather than duplicated methods.

Set `scenario_group` on every scenario, keyed by its Arrange — the same precondition state and triggering call. This records a test-design fact that downstream tooling needs but cannot reliably re-derive from prose preconditions, and it is what stops `automation-plan-generator` emitting one test method per scenario.

Do not size the plan to the method count. Scenarios may legitimately outnumber test methods; the ratio depends on how many natural permutation axes the feature has (service type, payment method, country). A feature with no such axis will sit near 1:1 and that is correct.

## Writing scenarios an engineer can execute

A scenario is read by someone who was not in the room when it was written. Everything below is calibrated against the team's own manually drafted GoFood group-order cases in BrowserStack, so it matches house convention rather than a general style preference.

### Titles — `Verify …`, and name the condition

`name` is what lands in the BrowserStack `Title` column and is the only field most readers ever see. In the team's existing group-order set, **87% of titles open with `Verify`**. Match it:

> `Verify <what happens> when <condition>`

`Verify the create session API rejects a request carrying both invite fields` — not `Reject a create request carrying both invite fields`. Imperative phrasing reads as a task, not a test case.

**Never ship a title whose condition is a filler word.** These say nothing about what is being tested and are the most common defect in generated titles:

`correctly` · `properly` · `gracefully` · `as expected` · `appropriate` · `relevant` · `any <noun>` · a bare `handle`/`work`/`behaviour`

If the scenario body enumerates the cases, the title names them or names the axis. `Verify create session degrades gracefully on any social group error` becomes `Verify create session still succeeds when the social group call times out, returns an unknown id, or the host is not ACTIVE`. Longer is fine — the team's median title is 74 characters, and titles routinely run past 100.

### Steps — every state check names its artifact

Steps split into two kinds, and the second is where generated plans go wrong:

| Kind | Executable because | Verb |
|---|---|---|
| A call to a service | `curl_reference` carries the request | `Call` |
| A read of resulting state | **only** if the step names the artifact | `Read` |

An API step is self-documenting; the curl says exactly what to run. A state-read step has no curl, so the prose is the entire instruction — and `Read the session row`, `Inspect the job queue`, `Check the cache` are not instructions. The reader cannot act without knowing *which*.

**Every state-read step must name the concrete artifact**: the table, the job or queue by name, the cache key, the topic, the log.

| Not this | This |
|---|---|
| `Read the session row` | `Read the group_order_sessions row for the session id` |
| `Inspect the worker job queue` | `Inspect the queue for the send-social-group-chat-extension job` |
| `Inspect the job queue after all three attempts` | `Inspect the auto-detect-or-auto-create job queue after all three attempts` |

The artifact name comes from `tasks_context.api_contract`, `external_systems[]` and `rfc_context.contracts.*`. **If no source names it, that is a gap — record it in `qa_analysis.md` rather than writing a vague step.** A step nobody can perform is worse than a missing step, because it looks complete.

### Use two step verbs, not five

`Read`, `Inspect`, `Fetch` and `Check` all mean *look at something*, and mixing them makes one plan read as though several people wrote it. Use **`Call`** for a request to a service and **`Read`** for any state check — DB row, queue, cache, log, response body alike. Other verbs are fine only where they carry real meaning: `Create`, `Publish`, `Compare`, `Run`, `Enqueue`, `Let … run` for an async wait.

### Do not write steps against capabilities the suite lacks

Check before assuming a verification mechanism exists. `Inspect the Gopay stub call log` assumes request-level stubbing; the gofood suite has **no** WireMock/`stubFor`/MockServer usage in 2,315 Java files, so that step cannot be run. Where "the downstream was not called" must be proven and no stub exists, assert the observable absence of its side effect instead, and flag the limitation in `qa_analysis.md`. See also the test-layer rule: stubbing is not a layer-lowering mechanism, and here it may not be available at all.

## Scenario generation rules

> Every rule below is subject to **Scenario granularity** above. Where a rule says "one scenario per X", it means one scenario per X **unless** two or more X share the same precondition and trigger — in which case they become steps of a single scenario.

### RFC validation_sequence — business logic (A)

For each step:
- **Happy path** — step succeeds with valid inputs → `tags: ["happy_path"]`
- **Failure** — one negative scenario per `failure_error_code` the step can produce → `tags: ["negative"]`
- **Boundary** — quantitative constraints in `constraint` field (min/max/edge) → `tags: ["boundary"]`

Use `tasks_context.test_layer` at the scope the scenario covers — never infer test_layer from `validation_sequence[].layer`.

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

### Code-change-context — code_change_context (C)

- New endpoint not in RFC → scenario + `rfc_gap` flag
- New validation rule not in RFC → scenario + `rfc_gap` flag
- New error mapping → negative scenario
- DB column/table, dependency, enum, auth or proto change nothing asserts → scenario + `rfc_gap` flag
- All scenarios this mode mints: `generated_by_mode: "code_change_context"`, `is_delta: true`, `source: CODE_DIFF`
- Full rules, including the binding gate and the auto-apply gate, are in **Code-change-context mode rules**

## Regression disposition — classify against existing coverage before writing a scenario

A backend feature almost always lands on endpoints that already have regression. For GoFood group order, 48 existing methods across 13 classes covered the endpoints this RFC touches before a line was written. Treating regression context purely as a dedup filter misses the larger half of the work: existing tests that must be **re-run**, and existing tests that must be **edited**.

Scope is by **service**, not feature. Any change to a service has blast radius across that service and the impacted services its mapping declares, so the question is not "does a case duplicate my scenario" but "what must keep working".

For every scenario about to be written, check `regression_context.testCases[]` and assign one disposition:

| Situation | `is_legacy_regression` | `existing_case_ref` | `regression_action` | Scenario emitted? |
|---|---|---|---|---|
| **Exact match** — a case already covers this exact behaviour | `true` | set | `reuse` | Yes — a row so reviewers see it exists, but no code is generated |
| **Directly impacted** — the change alters what an existing test should assert | `true` | set | `modify` | Yes — **plus** `existing_test_ref` naming the class, method and required change |
| **No match** | `false` | omit | `none` | Yes — normal generation |
| **Indirectly impacted** — shares a service but the behaviour is untouched | `false` | — | — | **No** — goes to `regression_selection` for the run, not to `scenarios[]` |

**Never set `is_legacy_regression: true` without `existing_case_ref`.** A bare flag is untraceable — nobody can audit which case it claims to match.

### What this file can tell you — depends on whether `steps` are present

Always available per case: `id`, `name`, `projectId`. Optionally: `steps`, `expectedResults` and `stepsSource`. That optional block changes what may be concluded, so check for it before choosing a matching strategy.

| Output | Titles only | With `steps` |
|---|---|---|
| `regression_selection` | **Yes, fully** — `resolvedServices[].testGroups` / `.testClasses` / `.testCaseIds` | same |
| `existing_case_ref` | Yes, once matched — `testCases[].id` verbatim | same |
| `regression_action: reuse` / `none` | **Weak** — title similarity only | **Strong** — behaviour-level match |
| `regression_action: modify` | **No** | **Only when `stepsSource` is `repo`** — see below |
| `existing_test_ref` | **No** | **No** — steps still name no class or method |

### Matching with `steps` present

Match on `steps` and `expectedResults` first, falling back to `name` only when steps are absent. Steps resolve the ambiguity titles cannot: in one real driver-platform scope, 20 cases shared the byte-identical title `"verify driver metadata with valid metadata key and value"` while each exercised a different metadata key — indistinguishable by title, trivially separable by steps.

Record which signal produced the match in `qa_analysis.md`. A `reuse` justified by steps and one justified by a title guess deserve different levels of reviewer trust.

### Matching without `steps`

Title similarity only, and it is weak enough to need an explicit rule: **several candidates is not a match.** Leave `is_legacy_regression: false` rather than picking one. Under-claiming costs a duplicate test; over-claiming hides a real gap behind a case id that does not cover the behaviour.

### Ids carry two prefixes — always

One project renders cases as both `TC-{n}` and `C{n}` (298 and 61 respectively in that same scope). Strip both before comparing; matching on the raw `id` silently drops every case using the other form. Store the id **verbatim** in `existing_case_ref` and normalise only for comparison.

### When `modify` may be concluded

Only when `stepsSource` is `repo` **and** the steps or expected results state an assertion the change makes insufficient — a masking rule the change extends to new fields, an exact field set or collection size the change adds to, an error-code set gaining a code.

`stepsSource: browserstack` is **not** sufficient. Human-written case steps describe intent and drift from the code; a step reading "verify the response is correct" says nothing about whether the Java asserts an exact field set or a bare `assertNotNull`. Treat browserstack-sourced steps as evidence for `reuse`, never for `modify`.

**`existing_test_ref` still cannot be derived from this file at all**, because nothing here names a method. So a `modify` conclusion drawn from repo-sourced steps must be recorded as a finding in `qa_analysis.md` for a reviewer to convert, with `regression_action` left at `reuse` or `none` until the reference exists. Emitting `modify` with a null `existing_test_ref` fails the self-check by design — an edit instruction with no target sends a coding agent to guess which method to change.

**One case does not mean one method.** In that same scope, 14 case ids sat on a single `dataProvider`-driven method. When method linkage does become available, `existing_test_ref.case_numbers[]` must list every case the method serves, or someone edits a shared method believing it belongs to one case.

### Before trusting an empty result

Read `browserstack.status` and `unresolvedServices[]` first. A failed fetch and genuinely-no-existing-coverage produce the same short `testCases[]`, and only these fields distinguish them. Note `unmatchedTestCaseIds[]` too — those ids were in scope but returned no detail, so they cannot be matched against and are not evidence of absence.

### When `regression_context.json` is absent

Leave `is_legacy_regression: false`, `existing_case_ref` and `existing_test_ref` null, `regression_action: "none"` and `regression_selection: null` on every scenario, and state in `qa_analysis.md` that the regression check did not run. Do **not** infer coverage from the RFC or the codebase — an unverified `true` is worse than an honest `false`.

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

> **Emit every field listed here explicitly, including the ones whose value is `null`, `false` or a default.** JSON Schema `default:` is annotation only — no validator injects it — so a field the generator does not write is simply absent, and every downstream consumer then has to distinguish "absent" from "not yet set". Write the key.

Schema root:
- `feature_name`, `plan_version`, `generation_mode: upstream_context|code_change_context|doc_change_context|review`, `created_at`, `updated_at`
- `status: draft|in_review|changes_requested|approved` — **always write `draft`**; see Approval gate. With `approved_by: null` and `approved_at: null`.
- `teams_in_scope[]` — every resolved team with `canonical_id`, `raw_name`, `matched_via`, `code_module`, `regression_id_prefix`, `browserstack_project`, `is_primary`, `included`. Includes teams the human excluded at the scope gate.
- `regression_selection: {test_groups[], test_classes[], case_ids[], rationale} | null` — the signoff run, copied from `regression_context.resolvedServices[]`. `null` when no regression context was available.
- `browserstack_sync: null` — always `null` at generation. Written only by the BrowserStack MCP sync after upload.
- `canonical_team_id: string` — resolved from `team_registry.json`. `"unknown"` if no match; triggers warning in qa_analysis.md. Stable across plan versions even if team renames (update registry alias instead).
- `code_module: string | null` — exact test code module directory name from `team_registry.json code.module`. Consumed verbatim by `automation-plan-generator` for Java package path construction. `null` when resolution failed.
- `scenarios[]` — each with:
  - `scenario_id`, `name` (`Verify …` — see *Writing scenarios an engineer can execute*), `description`
  - `test_layer: component|integration|e2e`
  - `priority: P0|P1|P2`
  - `source: RFC|PRD|CODE_DIFF|DOC_CHANGE|REVIEW`, `source_ref`
  - `generated_by_mode: upstream_context|code_change_context|doc_change_context|review` — which execution mode **created** this scenario. Set once at creation; never overwritten. `review` = scenario added purely from human review feedback; `code_change_context` = scenario minted from the merged diff; `doc_change_context` = scenario added because an upstream document changed.
  - `review_round: integer` — which review round last touched this scenario. `0` = not yet reviewed. Incremented on every Review-mode run that modifies or creates the scenario. Unmodified scenarios retain their current `review_round`.
  - `provisional: boolean` — true when `approach_finalised: false` or `edge_case.inferred: true`
  - `is_delta: boolean` — true for code_change_context, doc_change_context, and review-added scenarios (shorthand for `generated_by_mode != upstream_context`; kept for downstream tool compatibility)
  - `is_legacy_regression`, `is_dedup`
  - `test_type: string[]` — BrowserStack TestType. **Multi-select array** — collect all applicable values (see CSV section). Minimum one entry; never null or empty.
  - `execution_mode: Automatable|Manual` — BrowserStack Execution Mode. `Manual` for scenarios tagged `deferred` or `underspecified`; `Automatable` for all others.
  - `markets: array` — Countries this scenario applies to. Values: `Indonesia` | `Singapore`. Derived from `tasks_context.environments`; default `["Indonesia", "Singapore"]` when not specified.
  - `type_of_test: functional|performance` — BrowserStack Type of Test Case. `performance` **only** when tags contain `load` or `nfr` — i.e. the scenario measures a throughput or latency target. Everything else is `functional`, including `reliability` and `concurrency` scenarios: a timeout, retry-exhaustion, circuit-breaker or race-condition test asserts *functional* behaviour under adverse conditions, it does not measure performance.
  - `owning_team: string` — canonical id of the team owning this scenario's system under test. Defaults to the primary `canonical_team_id`; set explicitly on every scenario.
  - `regression_action: none|reuse|modify` — disposition against existing coverage. `none` unless a regression match was made.
  - `existing_case_ref: string | null` — the matched BrowserStack case id, verbatim. Never `is_legacy_regression: true` without it.
  - `existing_test_ref: object | null` — `{class, method, file_path, case_numbers[], change_required}`. Required when `regression_action` is `modify`; `null` otherwise, and `null` is the only correct value when the regression context carries no method linkage.
  - `change_reason: string` — set by doc_change_context and review modes only.
  - `dedup_reason: string` — set by `dedup-generator`, not here.
  - `step_descriptions[]` — `step`, `action`, `curl_reference`, `expected_result`. Target 4–6 steps per scenario (see Scenario granularity). Every `expected_result` is a concrete assertion phrased as `Verify …`. `action` is imperative and, when it reads state rather than calling a service, **names the artifact it reads** — see *Writing scenarios an engineer can execute*. Steps and expected results are 1:1.
  - `preconditions[]`, `fixture_ids[]`
  - `scenario_group: string` — key shared by scenarios that rest on the **same Arrange**: the same precondition state and the same triggering call, differing only in the data row exercised. A test-design fact, not an automation instruction — it applies equally to `Manual` scenarios, where it tells a human tester which cases can be executed back-to-back off one setup. A scenario with no sibling gets its own unique key. Format: `{feature_component}-{behaviour}`, e.g. `chatextension-terminal-status`. Downstream consumers decide what to do with the grouping; see `automation-plan-generator` for how it maps to test methods.
  - `browserstack_test_id: string | null` — BrowserStack's own id for this scenario, assigned when the plan is uploaded through the BrowserStack MCP. **Emit `null` at generation time and never author a value.** The sync writes it back after upload, which is what makes the plan round-trippable: re-running Review or Code-change-context can then update the existing case instead of creating a duplicate. Do not confuse it with `existing_testcase_ids[]` — that names cases which existed *before* this plan; this names the case *this* scenario became.
  - `existing_testcase_ids: string[]` — BrowserStack case ids (e.g. `TC-302383`) that this scenario extends, replaces, or re-runs under a new flag state. Populated from `regression_context.json` when present; empty otherwise. Rendered into the `Preconditions` block as `Existing regression case:` and consumed downstream for `@TestInfo(testCaseIds={...})`. Do **not** invent ids — leave empty when `regression_context.json` is absent.
  - `tags[]` — `happy_path|negative|boundary|flag_on|flag_off|e2e|load|concurrency|security|reliability|compliance|nfr|deferred|underspecified|provisional`
  - `human_corrected: boolean` — `false` at generation time. Set to `true` in Review mode when the scenario is modified or deprecated by human feedback. Never reset to false. For scenarios with `generated_by_mode: "review"`, this is implicitly `true` (the scenario is itself a human addition) but the field is still set explicitly.
  - `human_correction_types: string[]` — empty at generation. Appended per review round with the type of correction applied: `"field_change"` (one or more fields corrected), `"deprecated"` (LLM generated an incorrect/duplicate scenario), `"missed_scenario"` (LLM failed to generate this; set on review-added scenarios). Multiple rounds may push multiple entries.
  - `code_reconciled: boolean` — `false` at generation. Set `true` by Code-change-context mode when any code-diff finding binds to this scenario. **Never merged with `human_corrected`** — see Provenance in the Code-change-context mode rules.
  - `code_reconciliation_types: string[]` — empty at generation. Appended per code-change run: `"confirmed"`, `"field_change"`, `"deprecated"`, `"blocked_by_code_gap"`, `"conflict_pending"`, `"new_from_diff"`.
  - `code_change_round: integer` — `0` until a Code-change-context run touches the scenario; incremented per run that binds a finding to it.
  - `code_refs: object[]` — `{mr, service, file, class, line, condition}` copied from the finding's `code_ref`, so a reviewer can click through to the diff line. Empty at generation.
- `coverage_summary` — `total`, `by_layer`, `by_priority`, `rfc_steps_covered`, `rfc_steps_total`, `rfc_gaps[]`
- `llm_quality` — updated after each Review run; tracks LLM generation accuracy:
  - `auto_approved: integer` — scenarios not touched by any review round
  - `human_modified: integer` — scenarios with `human_correction_types` containing `"field_change"`
  - `human_deprecated: integer` — scenarios deprecated by review (LLM over-generated)
  - `human_added: integer` — scenarios added by review (LLM under-generated; `generated_by_mode: "review"`)
  - `llm_accuracy_pct: float` — `auto_approved / (auto_approved + human_modified + human_deprecated)` × 100. Excludes `human_added` from denominator (can't penalise the LLM for what it never generated)
  - `review_rounds_completed: integer`

## Approval gate

Approval happens at **two levels**, and the generator writes `draft` at both.

| Level | Field | Means |
|---|---|---|
| Plan | root `status` | this plan has been through review at all |
| Scenario | `scenarios[].status` | **this** scenario is signed off |

Both use `draft` → `in_review` → `changes_requested` → `approved`; scenarios add a fifth terminal value, `deprecated`. **Always write `draft` at both levels.** The generator never approves its own output — `approved` is set by a person after reading the plan and its analysis document, and nothing downstream may run until they do.

Two levels exist because a plan is reviewed case by case: a reviewer may approve 60 scenarios and request changes on 17, and the 60 should not be held up by the 17. `automation-plan-generator` halts on the root value, then selects per scenario.

**INVARIANT: root may not be `approved` while any scenario is still `draft` or `in_review`.** An approved plan holding unreviewed scenarios is ambiguous about what was actually signed off. `changes_requested` and `deprecated` scenarios do not block root approval — both are decisions a human has already made.

| Value | Meaning |
|---|---|
| `draft` | generated, not yet reviewed. The only value this skill ever writes. |
| `in_review` | a reviewer has picked it up |
| `changes_requested` | feedback is written in the `qa_analysis.md` Feedback block; a Review-mode run is pending |
| `approved` | cleared to flow to `automation-plan-generator` |

**Any run that changes scenario content resets `status` to `draft` at BOTH levels** — the plan root, and every scenario whose content that run actually changed. Scenarios the run left untouched keep their approval. Code-change-context, doc-change-context and review all qualify. An approval attaches to the content a person actually read, not to the filename. Set `approved_by` and `approved_at` to null at the same time; a plan whose `updated_at` is later than its `approved_at` has been edited since approval and the approval is stale.

Keep this consistent with the `**Status:**` line in the `qa_analysis.md` Human Review block — the markdown is what the reviewer edits, the JSON field is what downstream tooling gates on. They must not disagree.

## Output → qa_analysis.md

`qa_analysis.md` is a **living document** — the generated analysis sections are above a `---` divider; the `## Human Review` section below the divider is written once and preserved across all subsequent regenerations (Code-change-context, Doc-change-context). Never overwrite the Human Review section during generation.

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
- **BrowserStack sync** — after a sync has run, how many scenarios carry a `browserstack_test_id` and how many are still null, with the project they landed in and `synced_at`. List every scenario this run created and every one it updated by id, and — since the JSON schema has no slot for it — name every **update failure** explicitly here (a scenario that already had an id whose push failed; `unsynced_count` only ever catches creates that stayed null). If eligible scenarios spanned more than one team's project, name the other project(s) and how many scenarios are waiting for a separate run. Before the first sync, state plainly that none are tracked yet.
- **Regression disposition** — counts by `regression_action`, a table of every `modify` scenario with its case id, target class/method and required change, and the `regression_selection` contents. When `regression_context.json` was unavailable, say so in one line rather than printing an empty table.
- **Team scope** — the full `teams_in_scope[]` table with each team's module, regression prefix and BrowserStack project, which team is primary, the scope the human confirmed at the gate, and an **excluded-by-scope table** naming every scenario dropped for team reasons with its `owning_team`, entry point and what it covered. An excluded scenario that leaves no trace here is indistinguishable from a coverage gap.
- **Coverage ledger** — the full table with every unmapped row and its stated reason. This is the section a reviewer scans to find what the plan does not cover, so unmapped rows belong here in full rather than summarised.
- **Completeness sweep results** — how many scenarios or steps each of the four sweeps contributed. A sweep contributing zero is a signal it was skipped, not that the feature had nothing to find.
- **Code-change reconciliation** (Code-change-context runs only) — the MR ids, services and `extraction_date` read, and which `code_change_context*.json` file was used. Then, in this order:
  1. **Binding table** — every finding id with the scenario id the extractor named, the scenario ids actually bound, and `bound_by` (`id` / `behaviour` / `unbound`). State plainly whether `reconciliation.sdet_plan_ref` resolved to this plan; when it did not, say that every id was rebound by behaviour and why that was necessary.
  2. **Counts** — confirmations, auto-applied, conflicts pending, deprecated, scenarios minted, suggestions skipped as already covered.
  3. **Conflicts pending** — one row per finding held back by the Job 2 gate, quoting *both* sides: what the code does, and what the A source (`tasks_context.api_contract` / `rfc_context.validation_sequence` / PRD AC) says. This is the table a human arbitrates from, so neither side may be paraphrased away.
  4. **Blocked by code gap** — scenarios that cannot pass yet because the diff shows a stub dependency or a missing flag, with the `info_gaps` id.
  5. **Out of this MR's scope** — `unresolved[reason: "diff_unavailable"]` entries, stated as *not* coverage gaps.
  6. **Unbound findings** — findings no scenario in this plan asserts, which are real coverage gaps.

### Human Review section (below `---`, written once, never regenerated)

Append this block when first generating `qa_analysis.md`. On subsequent Upstream-context, Code-change-context or Doc-change-context runs, preserve it verbatim — do not regenerate it.

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

> **⚠ Generation guard — read this section before writing the CSV, every time.**
>
> This section is written last, after a long JSON generation pass. That makes it the most
> likely place to drift from the spec — using JSON key names as column headers instead of
> the BrowserStack import names, or omitting content columns because they were never in the
> earlier summary CSV.
>
> Before writing a single CSV row:
> 1. **Re-read this section in full.** Do not rely on memory of the JSON field names.
> 2. **Use only the column names in the tables below** as CSV headers — never the JSON key
>    names (`scenario_id`, `name`, `markets`, `test_type`, `priority`, `type_of_test`,
>    `arrange`, `expected_result`). Those are the source fields; the column headers are
>    different.
> 3. **Write every column listed**, in the order listed. Omitting a content column
>    (`Preconditions`, `Steps`, `Expected Result`) is a generation error — these fields
>    exist in the plan JSON and must be projected into the CSV.
> 4. **Derive `Expected Result` from `step_descriptions[].check`** (per-step), not from the
>    top-level `expected_result` field. The 1:1 step-to-result numbering is mandatory.
> 5. **`Execution Mode` value is `Automatable`**, not `Automated`. The spec's exact word.
> 6. **`Tags` in tracking columns are pipe-separated** (`happy_path|P0`), not
>    comma-separated — commas are reserved as the CSV delimiter inside quoted fields but
>    confuse tag-filtering tools that split on commas.

### BrowserStack columns

| CSV column | Maps from | Notes |
|---|---|---|
| `Id` | `scenario_id` | External ID for traceability |
| `Title` | `name` | `Verify <what> when <condition>` — house convention, no filler adjectives. See *Writing scenarios an engineer can execute*. |
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
| `generated_by_mode` | `generated_by_mode` | upstream_context / code_change_context / doc_change_context — audit trail |
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

## BrowserStack sync — post-approval upload, always asks first

Wired into this skill, not a separate tool or a fifth generation mode. It changes tracking
fields only — `browserstack_test_id` per scenario and root `browserstack_sync` — never scenario
content, `status`, `generated_by_mode`, or `review_round`. A sync is not a review round.

Triggered two ways, both landing on the same eligibility gate and the same ask:
1. **Explicit request** — the user directly asks to upload or sync to BrowserStack, at any
   point, in any mode.
2. **Detected opportunity** — Mode detection priority 5: no feedback, no change files, root
   already `approved`, and eligible work exists.

### Eligibility gate — check before asking anything

Sync is available only when root `status == "approved"`. This is the *same* Approval gate
invariant already defined above — not a separate bar, and not one an explicit request can
lower. If root `status != "approved"`, say so plainly (*"root status is `{status}`; BrowserStack
sync is available only once a human sets it to approved"*) and stop — do not ask the
confirmation question below.

Given root `approved`, a scenario is **eligible this run** when its own `status == "approved"`
**and** it is owned by the team whose project this run targets (see routing, below). Eligible
work exists when at least one scenario matches.

If nothing is eligible — because no scenario is approved yet, or every approved scenario for
this project already carries a `browserstack_test_id` and there is nothing left to push — say so
and stop. Do not ask the confirmation question with nothing behind it.

### Always ask before doing anything else

Never upload without an explicit yes, on any invocation, in any mode. When eligible work
exists, ask something equivalent to:

> `{N}` approved scenario(s) are ready for `{browserstack_project}` — `{C}` new, `{U}` to
> update. Upload now?

A "no" or no answer ends the check for this invocation — generation, or the priority-6 error,
continues exactly as if sync had never been considered. This question is asked **every time**
eligible work exists; a prior "no" is never remembered as a standing decision, because new
scenarios reach `approved` between runs and each run's set of eligible scenarios can differ.

### Routing — one project per sync run

The schema's `browserstack_sync` holds one `project`, not a list — **one sync run targets one
BrowserStack project.** Resolve which:
- If every eligible scenario shares one `owning_team`, target that team's `browserstack_project`
  from `teams_in_scope[]` — no need to ask which.
- If eligible scenarios span more than one `owning_team`, name the projects and their scenario
  counts, and ask which project this run targets. Scenarios for the other project(s) are counted
  in `unsynced_count` (below) and left for a separate run — never push a foreign-owned scenario
  into the primary team's project to avoid a second ask.

### Resolving project_identifier, folder_id, and this project's BrowserStack conventions

**`team_registry.json` is the only source for `project_identifier` — no separate mapping
file.** Read `teams_in_scope[].browserstack_project` (or the registry entry directly). Validate
its *shape* only: it must match `PR-<digits>` (e.g. `PR-40`). No live call is made to confirm
it further and nothing else is consulted.

- **Matches the shape → trust it and proceed.** Pass it straight through to
  `createTestCase`/`updateTestCase` as `project_identifier`.
- **Does not match (empty, a slug like `"gofood-backend"`, or any form other than
  `PR-<digits>`) → reject the upload outright.** Do not ask the user to type a correction, do
  not attempt a live lookup, do not guess a variant spelling — there is no
  `listProjects`-equivalent tool to fall back on, so a malformed value is a data problem to fix
  at the source (`team_registry.json`), the same way a missing DoR-gate file is: name the exact
  field and value that failed the shape check, and stop before asking anything else.

**`PR-<number>` is also TestRail's own project-id format — worth knowing, not a gate to
enforce.** TestRail-sourced `PR-###` values already exist elsewhere in this pipeline's data
(regression context files carry a `projectId` in this exact shape, distinguishable by a
`caseIdNamespace: "testrail"` field and plain-numeric case ids rather than `TC-xxxxxx`). The
shape check above cannot tell a TestRail id from a BrowserStack one — both look identical — so
if an upload targets a project that turns out to be wrong, a mismatched `caseIdNamespace`
elsewhere in the same data is the first place to look, not evidence the shape check itself is
insufficient.

- **`folder_id` — always ask the user when not already known.** Nothing resolves this
  automatically: call `listFolders(project_identifier)` (and one level of sub-folders) first,
  present the real folder tree with case counts, and let the human pick an existing one or
  choose to create a new one via `createProjectOrFolder` — never default to an arbitrary
  existing folder, including when only one exists, because folder semantics (what content
  belongs where) is a judgement call this skill has no way to infer. Nothing is cached between
  runs; ask again next time unless the human says otherwise.
- **`priority` — send the plan's `P0`/`P1`/`P2` string verbatim. Never shift or relabel it.**
  The tool's own field description states valid values are per-project, which invites
  translating to the platform default (`Critical`/`High`/`Medium`/`Low`) or guessing a shifted
  scale (`P0→P1`, assuming the target starts at `P1` not `P0`) — **both were tried and both were
  wrong** for the one project confirmed so far (human-corrected 2026-09-01: the project's own
  `priority` field takes `P0`/`P1`/`P2` directly, no translation). Default to the direct,
  unmapped pass-through; only deviate if something concrete says otherwise — the call is
  rejected, or a human who can see the BrowserStack UI says the project uses different labels.
- **`case_type` — still omit; no tool discovers valid per-project values.** The project default
  applies automatically (observed default: `"Regression"`).
- **`custom_fields` — attempt confirmed names, never assume the rest exist.** Confirmed live
  against one project (human-corrected 2026-09-01, after an initial upload wrongly omitted all
  of them on the assumption none existed — the create response's `custom_fields: []` reflected
  only what was *sent*, not what the project has configured):
  - `Country v2` — from `markets[]`, e.g. `["Indonesia"]`.
  - `Platform` — constant `"Backend"`.
  - `Execution Mode` — **depends on `execution_mode`, sent verbatim.** `Automatable`/`Manual`
    needs no translation; the custom field uses this skill's own vocabulary exactly.
  - `TapMind Automated` — **ignore. Never send this field, under any value.** This skill has no
    TapMind linkage data for any scenario it generates; its project default (`false`) is left
    to sit as the project's own concern, not something this skill has an opinion on.

  **`"Type of Test Case"` was tried and rejected — do not attempt it again without a
  human-confirmed exact name.** `updateTestCase` reported success and `last_updated_at`
  advanced, but a live read afterward showed no such field landed — the four above were
  unchanged. The tool's own success message is not proof a specific field took effect; only a
  live read is. `type_of_test` (and `test_type[]`, never attempted as a custom field at all)
  stay hedged into `tags[]` (`type_of_test:functional`, `test_type:smoke`/`test_type:story`) —
  that is the *only* confirmed home for these two values on this project, not a fallback held in
  reserve.

  Send the confirmed fields on the `createTestCase` call itself rather than a separate update;
  verify via a live read after regardless (the case-creation response does not reliably echo
  defaulted custom fields — a second read is what surfaced `Execution Mode` defaulting to the
  wrong value once, on the one field this skill didn't explicitly set at create time). If a
  *different* project's response shows even these confirmed names come back empty or rejected,
  fall back to the `tags[]` hedge for that project specifically — the fallback is per-project,
  not a global default once one project is confirmed.

### What actually uploads — create-or-update, never a diff

Filter to scenarios where `status == "approved"` **at the scenario level** — never by root
status alone. A root-approved plan can still hold `changes_requested` or `deprecated`
scenarios; neither uploads, ever, regardless of team or project.

For each eligible scenario, in `scenario_id` order:

| `browserstack_test_id` | Action |
|---|---|
| `null` | **Create.** Map fields per the table below — this is a *different* shape from the CSV export, not a re-use of it. |
| already set | **Update** the existing case by that id. Push current content unconditionally — this is an idempotent upsert, not a diff against a remembered prior state (the schema carries no per-scenario "last synced" marker to diff against, and none should be added: `additionalProperties: false` on both the scenario and `browserstack_sync` objects is deliberate). Never create a second case for the same scenario. `updateTestCase` has no `folder_id` parameter — an already-synced case cannot be relocated between folders through this tool; a routing change after first sync needs a deliberate create-new/deprecate-old decision, not attempted here. |

**Discover the BrowserStack MCP's actual tool names and parameter shapes at run time — do not
hard-code a guess.** MCP server tool names and field shapes vary by version; load the connected
server's real tool schemas before the first call. If no BrowserStack MCP tool is available when
the user says yes, say so plainly and stop — never fabricate a result or claim a case was
created or updated.

### Field mapping — `sdet_plan.json` scenario → `createTestCase` / `updateTestCase`

**This is not the CSV mapping.** The CSV's `## Output → sdet_testcases.csv` column contract is
a separate, flatter shape for BrowserStack's *file import*; the MCP tool's own parameters are
structured differently (a `test_case_steps[]` array rather than two newline-joined columns, a
single `priority` string rather one styled for a spreadsheet cell) and some plan fields have no
parameter at all. Use this table for MCP calls specifically:

| Plan field | → parameter | Notes |
|---|---|---|
| `name` | `name` | verbatim |
| `description` | `description` | verbatim — this parameter exists but the CSV mapping never captured it; genuinely additive here |
| `step_descriptions[]` | `test_case_steps[]` (`{step, result}`) | `step` = `action`; append the `curl_reference` as a second line on `step` when non-null (the real shape has no separate curl field — dropping it silently loses the "how do you run this" detail); `result` = `expected_result` |
| `preconditions[]` | `preconditions` (joined string) | newline-join; append `Existing regression case: <id>` per entry in `existing_testcase_ids[]` when non-empty |
| `priority` (`P0`/`P1`/`P2`) | `priority` | **verbatim, no mapping** — see resolution above; never shift or relabel |
| `tags[]` | `tags` | direct array; also carries the `type_of_test`/`test_type[]` hedge (`"Type of Test Case"` was tried as a custom field and confirmed rejected — this is their only home, not a fallback) |
| `execution_mode` | `automation_status: "not_automated"` **and** `custom_fields: {"Execution Mode": <verbatim>}` | two different destinations for the same plan field, not a conflict — `automation_status` means "has test code been written yet" (always `not_automated` at first upload, matching the CSV's `Backend Automation Status: Not Automated`); the confirmed custom field `Execution Mode` means "can this be automated at all" and takes `Automatable`/`Manual` verbatim, same vocabulary as the plan's own |
| `markets[]` | `custom_fields: {"Country v2": [...]}` | confirmed field name — send the array as-is |
| `"Backend"` platform constant | `custom_fields: {"Platform": "Backend"}` | confirmed field name |
| `type_of_test` | `tags[]` only | `"Type of Test Case"` tried as a custom field and confirmed rejected (silent no-op — the update call reported success, a live read showed it never landed); `tags[]` is the confirmed mechanism, not a hedge pending confirmation |
| — | `case_type` | omit unless confirmed for this project (see above) |
| — | `owner`, `issues`, `issue_tracker` | omit — no plan field carries an email or issue-tracker id |
| — | `status` (BrowserStack's own case review-status: `active`/`draft`/`in_review`/`outdated`/`rejected`) | **do not confuse with the plan's `scenarios[].status` approval field** — unrelated concepts sharing a name; never set from plan data |

**Fields with no BrowserStack destination at all — CSV/JSON-only, never attempted here:**
`test_layer`, `generated_by_mode`, `is_delta`, `is_legacy_regression`, `source_ref`,
`human_corrected`, `human_correction_types`, `owning_team`. These are explicitly the CSV's own
"internal tracking columns appended after BrowserStack columns" — the skill's own structure
already signals they were never meant to leave the CSV/JSON.

### Writing results back

After the upload attempt — whether it fully succeeded, partially succeeded, or failed entirely:

1. Write `browserstack_test_id` on every scenario that was created this run; leave it `null` on
   any that failed to create. Scenarios that were updated keep the id they already had.
2. Write root `browserstack_sync` using exactly its existing schema shape — `project`,
   `suite_id`, `synced_at`, `synced_count`, `unsynced_count`. This **replaces** the prior sync
   record; it is the latest sync's summary, not an accumulating history.
   - `synced_count` — scenarios that hold a valid `browserstack_test_id` as of *this* run:
     new creates plus successful updates. (Broader than the field's literal wording — "received
     a browserstack_test_id" — because the schema has no separate counter for updates; recording
     updates only in prose and not in this count would make the JSON undercount every run after
     the first.)
   - `unsynced_count` — approved scenarios still carrying `browserstack_test_id: null` after this
     run: create failures, plus any eligible-but-different-project scenarios left for a separate
     run. An **update failure** (case already had an id; the push failed) does not flip the id to
     null, so it is *not* caught by this count — name it explicitly in `qa_analysis.md` instead
     (next step). Do not let a clean `unsynced_count: 0` be read as "zero failures" when an update
     failure exists nowhere else to be seen.
3. **Regenerate `sdet_testcases.csv`** so it reflects the now-populated `browserstack_test_id`
   column — the CSV section already documents this column as *"populated only when the CSV is
   re-exported after a sync."* This is that re-export.
4. Update the `qa_analysis.md` BrowserStack sync section (below) with this run's create/update/
   failure detail — the JSON stays to its terse closed schema; the narrative gap (especially
   update failures, which the schema cannot represent) belongs there.
5. **Never touch `scenarios[].status`, root `status`, `generated_by_mode`, or `review_round`.**

### BrowserStack sync only — self-check

- Never upload a scenario whose `status != "approved"`.
- Never call create for a scenario that already carries a `browserstack_test_id`.
- Never proceed past the eligibility gate without asking the user this specific invocation.
- Never pass a `project_identifier` that doesn't match `PR-<digits>` to any BrowserStack
  call — reject the upload and name the exact field/value instead of guessing or asking for a
  correction.
- Never write `browserstack_test_id` or `browserstack_sync` from any mode *other than* this
  sync — the generator writes `null` at generation, always; only this action assigns a value.
- Never claim a create or update succeeded without a corresponding successful MCP response — a
  fabricated success is worse than a stated failure.
- If any update failed, name it in `qa_analysis.md` even though `unsynced_count` cannot carry it.
- Never conclude a project has no configured custom fields from a `createTestCase` response
  showing `custom_fields: []` — that reflects only what was *sent*, not what the project has
  configured or defaults to. A live `listTestCases`/read call is what actually confirms
  presence or absence; skipping it on this exact assumption is what produced a wrong
  `Execution Mode` value and two omitted fields (`Country v2`, `Platform`) on the first upload
  this rule exists because of.

## Code-change-context mode rules

Reads the post-build code diff and reconciles the plan against what was actually merged. This mode
**replaces the former Pass 2** — Pass 2 read only four of the file's arrays and had no branch that could
touch an existing scenario, so the `reconciliation` object that `code-change-extractor` has always emitted
had no consumer.

The mode does five jobs, strictly in order. Job 0 is a safety gate: skip it and the rest of the mode will
corrupt scenarios.

### Job 0 — Bind the reconciliation to THIS plan before reading a single finding

`reconciliation.impacted_scenarios[].scenario_id` and `error_code_mismatches[].expected_in_plan.scenario_id`
are ids **from whatever baseline the extractor was pointed at**, which is very often not the plan in this run
directory. Scenario ids are sequential per plan, so a stale baseline does not fail loudly — it silently
addresses a different scenario that happens to hold the same number.

| Check | Action |
|---|---|
| `reconciliation` is `null` or `{}` | Extraction-only run, no baseline. Skip Jobs 1, 2 and 4; run Job 3 over the extraction arrays only. Note it in qa_analysis.md. |
| `reconciliation.baseline_type != "sdet_plan"` | The diff was reconciled against an automation plan or a Jira task, not against test design. **Every scenario id is unbound.** Rebind by behaviour. |
| `reconciliation.sdet_plan_ref` does not resolve to the `sdet_plan.json` being updated | **Every scenario id is unverified.** Rebind by behaviour. Never trust the number. |
| `sdet_plan_ref` does resolve to this file | Ids may be bound directly, but still verify each one (below) before applying. |

**Verify every id even on a matching ref.** For each finding, compare the finding's `reason` /
`change_required` / `resolution` against the target scenario's `name` and its
`step_descriptions[].expected_result`. If the scenario does not assert the behaviour the finding is talking
about, the id is wrong regardless of what `sdet_plan_ref` says.

**Rebinding by behaviour.** Match the finding's `resolution` and `change_required` text against
`scenarios[].step_descriptions[].expected_result` and `scenarios[].name`. Bind to **every** scenario that
asserts the affected behaviour — a single contract change routinely touches many scenarios, and the
extractor's shortlist is a sample of the baseline it saw, never a complete list for this plan.

Record the outcome on every finding and print it as a binding table in qa_analysis.md:

| `bound_by` | Meaning |
|---|---|
| `id` | `sdet_plan_ref` resolved to this plan **and** the named scenario asserts the behaviour |
| `behaviour` | Rebound by assertion text; record both the id the extractor gave and the ids actually bound |
| `unbound` | No scenario in this plan asserts the behaviour — a coverage gap, not a no-op |

**An `unbound` finding is never silently dropped.** It goes to `coverage_summary.rfc_gaps[]` and to the
binding table. A finding the plan has no scenario for is the most interesting kind.

### Job 1 — Confirmations

`impacted_scenarios[].suggested_action: "reuse"`, and `error_code_mismatches[].disposition` of `covered` or
`matched`, mean the code agrees with the plan. **Change no scenario content.** On each bound scenario set
`code_reconciled: true`, append `"confirmed"` to `code_reconciliation_types[]`, and increment
`code_change_round`. Because no content changed, `status` is **not** reset — an approval a human already gave
survives a confirmation.

Confirmations are the cheapest signal in the file and worth reporting prominently: they are the scenarios a
merged MR has already validated the design of.

### Job 2 — Impacted scenarios, gated by the ownership contract

`code_change_context` is a **C** source in every row of the A/C matrix. A merged MR is evidence of what was
built, not authority over what should have been built. That distinction decides whether a finding may be
applied automatically:

| The finding contradicts… | Action |
|---|---|
| Nothing — the plan left the value unspecified, or the code fills in a detail the plan guessed at | **Auto-apply.** Update the step or assertion, set `change_reason` quoting the finding id, set `code_reconciled: true`, append `"field_change"`, reset that scenario's `status` to `draft`. |
| An **A** source — `tasks_context.api_contract`, `rfc_context.validation_sequence`, `rfc_context.business_logic`, `prd_context` acceptance criteria or priority | **Do not apply.** Set the scenario's `status` to `changes_requested`, append `"conflict_pending"`, and record a `code_conflict` entry naming both sides. A human arbitrates. |
| Any finding with `blocking: true` | **Never auto-apply**, whatever it contradicts. Always `changes_requested`. |

`suggested_action: "deprecate"` sets `status: "deprecated"` and `change_reason`. **Never delete** — the
human decides final removal.

**Why the gate matters.** A partially-built feature reports its own incompleteness as a contract change. A
view that has not yet been given `members_count`, a dependency still wired to a stub, a flag that lands in a
later MR — all three look identical to a genuine contract change from inside one diff. Auto-applying them
would delete the very assertions that are supposed to fail until the work is finished.

### Job 3 — Net-new scenarios

Run the delta-matching skip test first for every candidate; a suggestion already covered is skipped **with a
recorded reason**, never dropped silently.

| Source | Rule |
|---|---|
| `reconciliation.suggested_scenarios[]` | Mint a real `SC-` id (the extractor may only emit `SUG-###`). Honour `test_layer`, `priority_hint`, `tags`, `owning_team`, `curl_reference`; apply every standard derivation — `test_type`, `execution_mode`, `markets`, `type_of_test`, `scenario_group`, the `preconditions` block. |
| `new_endpoints[]` | `(method + path)` absent from every `step_descriptions[].curl_reference` → new scenario + `rfc_gap` |
| `error_mappings[]` | Error code string absent from every `expected_result` → new negative scenario |
| `validation_rules[]` | Rule not asserted by any scenario → new scenario + `rfc_gap` |
| `feature_flags[]` | Flag name absent from every `tags[]` → flag_on + flag_off pair |
| `changed_endpoints[]` | `what_changed` / `new_contract` describes behaviour no scenario asserts → new scenario |
| `db_changes[]` | A column, table or migration no scenario asserts → new persistence scenario; a **column set** differing from `rfc_context.db_schema_changes` is a contract conflict, not just a gap |
| `dependency_changes[]` | A new client, method or `needs_mock: true` dependency no scenario drives → new integration scenario |
| `new_enums[]` · `auth_changes[]` · `proto_changes[]` | Same test: absent from every assertion → new scenario |

The last five rows are the arrays the former Pass 2 never read. They are where DB shape drift and stubbed
dependencies hide.

Every scenario this job mints: `generated_by_mode: "code_change_context"`, `is_delta: true`,
`source: "CODE_DIFF"`, `status: "draft"`, `code_reconciled: true`, `code_reconciliation_types: ["new_from_diff"]`,
and `code_refs[]` copied from the finding's `code_ref`. Items with no RFC match also go to
`coverage_summary.rfc_gaps[]`.

### Job 4 — Information gaps and unresolved entries

| Input | Action |
|---|---|
| `info_gaps[category: "dependency"]` reporting a stub or hardcoded client | Every scenario that drives the real dependency is **not runnable yet**. Append `"blocked_by_code_gap"` to `code_reconciliation_types[]` and list them in qa_analysis.md. Leaving them `Automatable` with no note tells an automation agent to write tests that cannot pass. |
| `info_gaps[category: "feature_flag"]` reporting no flag in the diff | The `flag_off` half of every flag pair cannot pass. Mark the same way. |
| `info_gaps` of any other category | Record against the bound scenarios; auto-apply only under the Job 2 gate. |
| `unresolved[reason: "diff_unavailable"]` | **Not a gap.** The MR simply did not touch those endpoints. Record as out-of-MR-scope so nobody reads it as missing coverage. |
| `unresolved[reason: "no_sdet_plan"]` | The extractor had no baseline; treat as Job 0's null-reconciliation path. |

### Provenance — never merged with human review

This mode writes its own fields and **must not touch** `human_corrected` or `human_correction_types`:

| Field | Meaning |
|---|---|
| `code_reconciled: boolean` | `false` at generation; `true` once any code-diff finding bound to this scenario |
| `code_reconciliation_types: string[]` | `confirmed` · `field_change` · `deprecated` · `blocked_by_code_gap` · `conflict_pending` · `new_from_diff` |
| `code_change_round: integer` | `0` until the first code-change run touches the scenario; incremented per run |
| `code_refs[]` | `{mr, service, file, class, line, condition}` copied from the finding's `code_ref` — lets a reviewer click through to the diff line |

`llm_quality.llm_accuracy_pct` measures how well the generator's output matched **human** judgement. Folding
a code-diff correction into `human_modified` would score the generator down because the code diverged from
the RFC it was told to generate from — the opposite of what happened. Keep the two axes separate.

### Approval gate

Reset root `status` to `draft` (with `approved_by` and `approved_at` null) if **any** scenario's content
changed. A run consisting only of confirmations changes nothing and leaves the root alone. Scenarios this run
did not touch keep the approval they had.


## Doc-change-context rules

Do not regenerate unaffected scenarios. Patch only what the doc change touched.

**Scenario matching — find what to patch:**

Doc-change-context mode uses `source_ref` on each existing scenario to trace back to the source AC, flow, or validation step. When `doc_change_context.json` reports a change:

| doc_change_context item | Find affected scenarios by | Action |
|---|---|---|
| AC modified | `source_ref` contains the AC ID | Update step_descriptions, assertions, preconditions. Set `generated_by_mode: "doc_change_context"`, add `change_reason`. |
| AC removed | `source_ref` contains the AC ID | Set `status: "deprecated"`, add `change_reason`. Do not delete — human reviewer decides final removal. |
| AC added | No existing match | Generate new scenario. `generated_by_mode: "doc_change_context"`, `is_delta: true`. |
| Flow changed | `source_ref` contains the flow name | Update outcome assertion and steps. Set `generated_by_mode: "doc_change_context"`, add `change_reason`. |
| Validation step changed | `source_ref` contains the step ref | Update constraint / failure_code assertions. Set `generated_by_mode: "doc_change_context"`, add `change_reason`. |

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

Total scenarios, RFC coverage %, gaps count, blocked gaps count, provisional count, delta count (Code-change-context/Doc-change-context).

On a Code-change-context run also log: findings read, bound by id, rebound by behaviour, unbound; confirmations; auto-applied; conflicts pending; deprecated; scenarios minted; suggestions skipped as already covered; scenarios marked blocked_by_code_gap.

On a BrowserStack sync, log instead: root status at the eligibility check; eligible scenario count and how many teams'/projects' worth; whether the user was asked and their answer; project targeted; created count; updated count; failed-create count; failed-update count (the one the JSON schema cannot carry); final `synced_count` / `unsynced_count` written to `browserstack_sync`.

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
- `status` is anything other than `draft` on a freshly generated plan — at the root **or** on any scenario; the generator never approves its own output
- root `status` is `approved` while any scenario sits at `draft` or `in_review` — violates the two-level invariant
- a code_change_context, doc_change_context or review run left `status` at `approved` — at the root, or on a scenario whose content that run changed — instead of resetting it to `draft`
- `scenario_group` is missing on any scenario, or every scenario has a unique one (it was not derived from the Arrange)
- any scenario has `is_legacy_regression: true` with no `existing_case_ref`
- any scenario has `regression_action: "modify"` with no `existing_test_ref`, or an `existing_test_ref` whose `change_required` is empty
- `regression_context.json` was present and `regression_selection` is null
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
- **Code-change-context mode only:**
- any `reconciliation` finding left `bound_by: "unbound"` with no `coverage_summary.rfc_gaps[]` entry
- any finding with `blocking: true` that was auto-applied instead of set to `changes_requested`
- any finding applied by id while `reconciliation.sdet_plan_ref` does not resolve to this plan
- any scenario whose `code_reconciled` is `true` with an empty `code_reconciliation_types[]`
- `human_corrected` or `human_correction_types[]` changed by this mode — it must never write them
- any `suggested_scenarios[]` entry neither minted as a scenario nor recorded as skipped with a reason
- a scenario minted from the diff without `source: CODE_DIFF`, or carrying a `SUG-` id instead of a minted `SC-` id
- `generation_mode` left at `upstream_context` after a code-change run
- **BrowserStack sync only:**
- a scenario was uploaded whose `status != "approved"`
- a create was called for a scenario that already carried a `browserstack_test_id`
- the confirmation question was skipped for any invocation that had eligible work
- `browserstack_test_id` or root `browserstack_sync` was written by a mode other than the sync itself
- an update failure exists with no corresponding line in `qa_analysis.md`
- more than one team's project had eligible scenarios and this run pushed to more than one project, or picked one without asking
