---
name: backend-automation-plan-generator
description: Generate the automation plan from an approved sdet_plan.json. Outputs automation_plan.json as a flat list of automation_scenarios — one object per test scenario — with test class, package, method name, fixture IDs, required state, and curl references with fixture-scoped placeholders. response_fields_used[] and test_data_output are left null/empty for TDG to fill. Structural contract consumed by both test-data-generator and test-code-generator. Requires human review before code generation begins.
---

# Backend Automation Plan Generator

Bridge between *what to test* (SDET plan) and *how to implement it* (test code + test data). Locks in all structural decisions before code generation starts — errors here cascade into every generated test method.

## Reads

| File | Purpose |
|---|---|
| `sdet_plan.json` (approved) | Human-reviewed output from sdet-plan-generator, and the **only** source for test-data requirements. Source of `scenario_id`, `source_ref`, `is_legacy_regression`, `description`, `preconditions`, `step_descriptions`, `test_layer`, `tags`, `priority`, plus `scenario_group` (drives grouping), `execution_mode` (drives selection), `owning_team` (drives module and BrowserStack routing per scenario) and `existing_testcase_ids` (propagated verbatim). Also read `canonical_team_id`, `code_module` and `teams_in_scope[]` (root fields) — resolved by the team registry, never re-derived here. |
| `tasks_context.json` | Package/class naming conventions, component boundaries, api_contract, service_name, target_framework. |
| `code_change_context.json` | `curl_reference` construction from actual endpoint signatures. |
| `regression_context.json` (the resolver's `scope.json`) | Existing class naming patterns for consistency, and `resolvedServices[].testGroups` / `.testClasses` for the `regression_selection` block. Class-level only — it cannot locate a method, so `existing_test_ref` must come from the SDET plan, never be derived here. |

## Model
Fast tier — Haiku

## Approval gate — check before reading anything else

**Halt unless the plan root `sdet_plan.status == "approved"`.** Surface: *"sdet_plan.json is not approved (status: {value}). A human must review the plan and its qa_analysis.md, then set status to 'approved' before the automation plan can be generated."*

Approval is **two-level**. The root gate above says the plan was reviewed at all; each scenario then carries its own `status`. Once past the root gate, take only scenarios where **`status == "approved"`**. A plan may be partially approved — 60 scenarios cleared, 17 still in review — and the cleared ones generate now rather than waiting.

Report the split in the run log: *N approved / N draft / N in_review / N changes_requested / N deprecated*. A reviewer who forgot to approve half the plan should see that, not silently receive half an automation plan.

This skill has always described its input as "sdet_plan.json (approved)" without anything enforcing it. The field makes that real. Generating from a draft plan means locking in test classes, fixtures and method names from scenarios nobody has signed off — and every one of those decisions cascades into generated code.

Also check staleness: if `sdet_plan.updated_at` is later than `sdet_plan.approved_at`, the plan changed after approval. Halt and say so rather than proceeding on an approval that predates the content.

The automation plan this skill writes carries its own `status` (plan root), and the same rule applies one stage down: **always write `draft`**, never `approved`. `test-code-generator` gates on it before writing any code.

## Selection — decide what becomes a test method before filling any field

**Skip these scenarios entirely. None produces a new test method:**

| Condition | Why |
|---|---|
| `is_dedup: true` | Already covered by an existing regression test |
| `regression_action: "reuse"` | An existing case already covers this exact behaviour. The scenario exists so reviewers can see the coverage; there is nothing to build. |
| `execution_mode: "Manual"` | Tagged `deferred` or `underspecified` — blocked on an open decision or an unfinalised contract. A method here would assert behaviour nobody has defined yet. |

Report both counts in the log. A plan where a fifth of scenarios are Manual is normal for a feature built on a draft RFC, not an error.

**`regression_action: "modify"` produces an EDIT, not a new method.** Emit an entry, but carry `existing_test_ref` through verbatim — `class`, `method`, `file_path` and `change_required`. `test-code-generator` must modify that existing method rather than author a new one; a new method alongside the old leaves the insufficient assertion in place, which is the failure this disposition exists to prevent. Do not invent a `method_name` for these — the name already exists.

Propagate `regression_selection` to the plan root unchanged. It is the signoff run: the existing groups and classes CI executes alongside the new tests.

**Emit exactly one `automation_scenarios[]` object per surviving scenario.** One scenario, one test method, one result. Never merge scenarios into a shared method.

Merging looks tempting because `scenario_group` marks scenarios that share an Arrange, and sharing an Arrange feels like sharing a method. It is not:

- **The provisioning saving does not require merging.** Ten separate methods all referencing `FX-SG-HOST-OWNER-01` still resolve to one fixture. Repeating the `fixture_id` across entries is what keeps the runtime TDP call count down — merging buys nothing on top of that.
- **Merging destroys per-case reporting.** Each scenario is a test case with its own id in the test management system. Fold three into one method and a failure in the first aborts the rest, and three cases collapse into a single pass/fail.
- **Shared Arrange does not imply shared assertion shape.** A group typically holds a happy path, a rejection and a degradation case. Those assert structurally different things, and a single method covering them needs `if/else` in the body — a test smell, not a data-driven test.

### What `scenario_group` is for here

Propagate it onto the entry unchanged, and use it for two things — neither of which is merging:

| Use | How |
|---|---|
| Test-class grouping | Entries sharing a `scenario_group` belong in the same test class, so their common setup is declared once |
| Shared setup | Members share fixtures by construction, so their `test_data[]` entries repeat the same `fixture_id` values |

Do **not** emit a per-entry list of peer scenarios. The repeated `fixture_id` already records the sharing, and a peer list would restate it redundantly — a fixture used by 24 scenarios would need 552 cross-references to say what 24 repetitions of one id already say. It would also be incomplete: fixtures are routinely shared *across* `scenario_group` boundaries, which a group-derived peer list cannot capture.

## Per surviving scenario, generate one object in `automation_scenarios[]`

| Field | Details |
|---|---|
| `scenario_id` | From sdet_plan.json, one-to-one |
| `scenario_group` | Propagated verbatim from sdet_plan.json — drives test-class grouping and shared setup, never merging |
| `browserstack_test_id` | Propagated from sdet_plan; `null` until a sync has run. Together with `existing_testcase_ids[]` this forms the test-case id list on the generated method's tracking annotation. |
| `existing_testcase_ids[]` | Propagated **verbatim** from sdet_plan.json. Empty when `regression_context.json` was absent at plan time. **Never invent ids.** |
| `parameterised_steps` | See the data-driven section below. `null` for most scenarios. |
| `requirement_ref` | From sdet_plan.json `source_ref`, e.g. `RFC-78:step-9 / REQ-001 / AC-001` |
| `description` | From sdet_plan.json `name` |
| `is_legacy_regression` | From sdet_plan.json |
| `is_dedup` | `false` — dedup scenarios are skipped entirely |
| `target_framework` | From tasks_context.json, e.g. `GBT` |
| `service_name` | From tasks_context.json component field |
| `owning_team` | Propagated verbatim from sdet_plan. Determines this entry's module, package and BrowserStack project. |
| `module` | **Resolve from the registry entry for this entry's `owning_team`** — that equals the plan's root `code_module` only when `owning_team` is the primary team. A scenario testing another team's service must land in that team's module, not the primary's. If `owning_team` or the resolved module is `null` or `"unknown"`, flag an error and halt: *"code_module is unresolved in sdet_plan.json — add team alias to config/team_registry.json and re-run sdet-plan-generator."* Do not fall back to tasks_context for the module name. |
| `package` | `{resolved module}.test.{test_layer}.{feature_component}` — the module resolved above from `owning_team`, not the plan's root `code_module`; use `tasks_context` for `feature_component`. Example: `transport.test.component.pickup` |
| `test_class` | Class name based on `test_layer` + feature/component grouping. Group related scenarios — not one class per scenario. e.g. `SaveCardComponentTest`, `SaveCardIntegrationTest`, `CardRepositoryIntegrationTest` |
| `test_layer` | Copied **verbatim** from `sdet_plan.json`: `component` \| `integration` \| `e2e`. Never recomputed here, and never adjusted to suit a tidier `package` or `test_class` — it originates in `tasks_context`, which another team owns. If a value looks wrong for the scenario, flag it in the run notes and still propagate it unchanged. |
| `method_name` | `should[ExpectedOutcome]When[Condition]` — Java-valid camelCase. Append suffix if collision within class. |
| `assertion_class` | Derived from test_class, e.g. `SaveCardAssertions`, `CardRepositoryAssertions` |
| `endpoint` | HTTP method + path from tasks_context api_contract, e.g. `POST /payment/v1/cards`. Empty string for DB/infra-only tests (no HTTP call). |
| `curl_reference` | Minimal valid curl from code_change_context or tasks_context api_contract. Use fixture-scoped placeholders matching the id scheme below: `{{FX-SG-HOST-OWNER-01.bearerToken}}`, `{{FX-MERCHANT-GO-01.restaurantId}}`. Never an unscoped `{token}`. Placeholder field names are **candidates** — TDG confirms and corrects them against the catalog response schema. Empty string for DB/infra-only tests. |
| `step_descriptions[]` | **Propagated verbatim** from sdet_plan.json for the matching `scenario_id`. Copy all steps as-is — do not rewrite, deduplicate or summarise. `test-code-generator` builds the method body and its assertions from these; without them it cannot write the test. Each step pairs an `action` with a single `expected_result`, and that 1:1 pairing must survive. |
| `test_data[]` | One entry per independently provisioned entity the scenario needs. Derived from `preconditions[]` and `step_descriptions[]` only. See the ownership boundary and fixture guidance below. |
| `tags` | From sdet_plan.json tags + priority, e.g. `["negative", "P0"]` |
| `environments` | From tasks_context.json environments or default `["dev-cluster", "staging-cluster"]` |
| `execution_hints` | Default `{"retry_count": 2, "timeout_ms": 15000}`. Use `30000` for DB/infra tests, `60000` for performance tests. |
| `jira_ids` | Empty array `[]` unless tasks_context has JIRA references |

## Data-driven steps — state the fact, let code generation pick the mechanism

Some scenarios repeat one assertion over several inputs: a stop condition checked against three terminal statuses, a skip rule checked against four precondition failures, a gate checked against two membership states. Those are genuine data-driven tests, and the opportunity lives **inside** a scenario's steps — never across scenarios.

When a run of consecutive steps re-runs the same operation from the same starting state with only the input varying, record it:

```json
"parameterised_steps": {
  "steps": [1, 2, 3],
  "kind": "independent_variants",
  "varies": "gopay_stub_behaviour",
  "rows": [
    {"input": "timeout",                    "expected": "2xx, no group attached, no error surfaced"},
    {"input": "group id unresolved",        "expected": "2xx, no group attached, no error surfaced"},
    {"input": "host not ACTIVE on roster",  "expected": "2xx, no group attached, no error surfaced"}
  ],
  "shared_teardown_step": 4,
  "confirmed_by_human": false
}
```

Set it to `null` — the common case — whenever the steps are not independent variants.

### The distinction that matters: variants vs progression

Two step runs can read almost identically and mean opposite things.

| Shape | Test |
|---|---|
| **Independent variants** — each step restarts the same operation from the same arranged state with a different input. Rows are order-independent; any one could run alone. | `kind: "independent_variants"` |
| **Sequential progression** — each step advances state and depends on the one before. "Attach, then join, then re-fetch, then book." | `parameterised_steps: null` |

Turning a progression into data rows breaks the test, because the rows are not independent. Textual similarity is not the test — ask whether step 3 would still pass if step 2 had never run. If it would not, it is a progression.

### Why the fact and not the mechanism

`parameterised_steps` describes what the steps *are*. `test-code-generator` decides what to build from it — a `@DataProvider` with one row per entry, a loop, or several inline assertions — because that choice depends on module convention, and adoption of parameterised tests varies widely between modules. Do not emit framework constructs here.

Set `confirmed_by_human: false` on every block. Detection of a variant run is inference and it produces false positives on progressions, so it is checked at the automation-plan review gate before code generation, not trusted silently.

## test_data[] — per fixture entry in each scenario

Each scenario's `test_data[]` contains one entry per independently provisioned entity.

| Field | Details |
|---|---|
| `fixture_id` | Format: `{sdet_plan fixture label}-{NN}` — the label read from the scenario's `preconditions` `Test data:` line, plus a two-digit **instance ordinal**. e.g. `FX-SG-HOST-OWNER-01`. Scenarios needing the same state reuse the same id. See the instance-ordinal rule below. |
| `description` | Human-readable: what entity, what state — e.g. "Verified customer CX-001 with valid Bearer token; card not previously saved" |
| `required_state.entity` | Domain the test data service owns: `CUSTOMER` \| `DRIVER` \| `BOOKING` \| `MERCHANT` \| `PAYMENT_INSTRUMENT` \| `DB_INFRA`. Maps to `testDataEntity` in the service request. Use `DB_INFRA` for Testcontainers / migration fixtures. |
| `required_state.category` | Exact category name from the test data service catalog (e.g. `CUSTOMER_WITH_WALLET`, `CUSTOMER_WITH_SAVED_CARD`). Maps to `testDataCategory.testDataCategoryName`. For `DB_INFRA`: the infra type (e.g. `TESTCONTAINERS_POSTGRESQL`). |
| `required_state.count` | Number of entities to provision. Maps to `testDataCategory.count`. Default `1`. Omit for `DB_INFRA`. |
| `required_state.config` | Additional parameters for this category (e.g. `wallet_status`, `saved_card_type`). Merged into the `testDataCategory` request body. |
| `response_fields_used` | Set to `[]`. **Do not populate here.** TDG looks up the TDP catalog response schema and fills confirmed field names. |
| `test_data_output` | Set to `null`. TDG writes enrichment here: `test_data_status`, `test_data_details.test_data_operations[]`, `test_buddy_prompt`. |

### Ownership boundary — who decides what about test data

This split matters and is easy to get backwards.

| Layer | Owns | Does not own |
|---|---|---|
| `sdet_plan.json` | The **required state** in prose, and **which scenarios share it** (the equivalence classes, labelled in the `Test data:` precondition line) | How that state is provisioned |
| `automation_plan.json` | The **provisioning realisation** — `entity`, `category`, `count`, `config`, the single-call boundary, and whether a stub replaces provisioning entirely | What state the test needs, or which scenarios need the same one |

**This skill decides what the test data *is*.** The plan states the requirement; you choose the realisation against the TDP catalog. Do not copy a provisioning decision from upstream — there isn't one to copy.

**But do not re-derive the equivalence classes.** The plan already records which scenarios need the same state, and a human approved that at the review gate. Re-inferring it from prose can split or merge differently, which silently changes two things the plan was tuned for: how many TDP calls the suite makes at runtime, and whether a fixture one test mutates gets reused by another expecting the pre-mutation state — the classic order-dependence flake.

### How to identify fixtures

Read **only** `preconditions[]` and `step_descriptions[]`. Do not consult `prd_context`, `rfc_context` or `tasks_context` for test data — the plan is authoritative for the requirement.

| Field | What it contributes |
|---|---|
| `preconditions[]` `Test data:` line | The required state in prose, plus the fixture labels naming its equivalence class |
| `preconditions[]` other lines | Country, entry point and feature-flag state — flag state often implies a provisioning config value |
| `step_descriptions[].action` | Transactional records that must be set up or operated on — "3 completed bookings", "a group already at 100 members" |
| `step_descriptions[].expected_result` | Data that must exist to assert against — "returns array of 3 bookings with fare" signals 3 booking records |

For each entity identified, ask two questions:
1. *"Does this need to exist for test setup?"* (customer, driver) → goes into `test_data[]`
2. *"Does this need to exist to be asserted against?"* (past bookings, transaction history) → also goes into `test_data[]`

Both types need provisioning. The difference shows up in `category` and `count` — not in whether they appear in `test_data[]`.

**Example — history scenario:**
```
preconditions:  "Customer CX-001 with valid token", "Driver DRV-001 active",
                "3 completed bookings exist for CX-001 with DRV-001"
expected_result: "returns array of 3 bookings with fare, distance, driver_name"
```
→ Three fixtures: CUSTOMER (setup), DRIVER (setup), BOOKING count=3 (the actual test data being asserted)

**Example — card save scenario (no transactional records):**
```
preconditions:  "Customer CX-001 with wallet, card not previously saved"
expected_result: "returns 200 with token"
```
→ One fixture: CUSTOMER (setup only — no prior records needed)

**Grouping rule:** Same entity + same required state across scenarios → same `fixture_id` (reuse it).
Different state → new `fixture_id`. DB/infra setup → `entity: DB_INFRA`.

### Fixture id scheme — semantic label plus instance ordinal

Build the id from the fixture label the plan already carries in the `Test data:` precondition line, suffixed with a two-digit instance ordinal:

```
FX-SG-HOST-OWNER-01
FX-MERCHANT-GO-01
FX-SESSION-WITH-GROUP-01
```

The label keeps the id readable and traceable back to the reviewed plan; the ordinal disambiguates **instances of the same state**.

**The ordinal is not a global sequence.** It answers "which of several identical entities is this?", and it is the only way to express something `count` cannot:

| Need | Expression | Runtime cost |
|---|---|---|
| Two entities in the same state, addressed as a set | one fixture, `count: 2` | one TDP call |
| Two entities in the same state, **each independently addressable** | `…-01` and `…-02` | two TDP calls |

Use `count` by default. Use a second ordinal only when the scenario must reference the two entities separately — a concurrency test where two distinct callers each invoke a write and the assertions distinguish them, for instance. A curl containing `{{FX-SG-HOST-OWNER-01.bearerToken}}` and `{{FX-SG-HOST-OWNER-02.bearerToken}}` in the same scenario is the signal that two ordinals are genuinely needed.

Most fixtures will only ever be `-01`. Emit the ordinal anyway so the format is uniform and downstream parsing does not need to handle both shapes.

### Single-call boundary rule

One `fixture_id` = one call to the test data service at test runtime.
- If a scenario needs a customer AND a driver independently → two entries in `test_data[]` → two calls.
- If the test data service has a composite entity → one entry → one call → response includes all sub-entity fields.
- Mock stubs (WireMock) are never in `test_data[]` — they are infra setup, not test data service calls.

## Output → automation_plan.json

> **Emit every field explicitly, including nulls and defaults.** JSON Schema `default:` injects nothing — an unwritten field is an absent field.

Schema root structure:
- `epic_id` — from tasks_context epics[0].id
- `status: "draft"` at the **plan root** — never approve your own output. With `approved_by: null`, `approved_at: null`.
- `status: "draft"` on **every automation scenario** — these get their own human review before code generation, the same way SDET scenarios do. Never carry the approved value across from the SDET scenario: what was approved there is the *test case*, not the class name, method name, fixtures and package chosen here.
- `regression_selection` — propagated unchanged from `sdet_plan`.
- `browserstack_sync: null` — written only by the sync.
- `automation_scenarios[]` — flat list, one object per non-dedup scenario, with all fields above

## Guardrails
- Take a scenario only when **all four** hold: `status == "approved"`, `execution_mode == "Automatable"`, `is_dedup == false`, and the plan root is `approved`. Anything else — including `deprecated`, which a human explicitly marked for removal — never becomes a test method.
- Emit one entry per distinct `scenario_group`, not one per scenario. `covers_scenario_ids[]` must list every member.
- Derive test data from `preconditions[]` and `step_descriptions[]` only. Do not read `prd_context`, `rfc_context` or `tasks_context` for it.
- `required_state` is **your** decision, not the plan's. The plan states the requirement; you choose entity, category, count and config against the TDP catalog.
- Do not re-derive which scenarios share a state — reuse the equivalence classes the plan's fixture labels record.
- `existing_testcase_ids[]` is propagated verbatim and may be empty. Never invent a test-case id.
- `test_class` groups related scenarios — not one class per scenario. Group by `(test_layer + feature_component)`.
- If endpoint not in code_change_context, use tasks_context api_contract. If neither has it, flag it.
- `required_state` must use the structured `{entity, category, count, config}` shape — no prose strings.
- `response_fields_used` must be `[]` for every fixture — TDG populates after catalog lookup. Pre-filling is a generation error.
- `test_data_output` must be `null` for every fixture — TDG writes to it. Pre-filling is a generation error.
- `curl_reference` placeholder field names (e.g. `{{FX-SG-HOST-OWNER-01.bearerToken}}`) are candidates derived from context — TDG validates and corrects them against the catalog response schema.
- `curl_reference` must use fixture-scoped `{{<label>-NN.field}}` placeholders — never unscoped `{token}`. Every placeholder must resolve to a `fixture_id` present in that entry's own `test_data[]`.
- `endpoint` and `curl_reference` must be empty string `""` for DB/infra-only tests (no HTTP call).

## Validate
`jsonschema.validate(output, schemas/automation_plan.schema.json)`

## Log
N groups emitted, N scenarios covered, N skipped as dedup, N skipped as Manual, N unique fixture_ids, and the total fixture references across all entries — the last is the runtime TDP call count and the dominant flake driver, so log it explicitly.
