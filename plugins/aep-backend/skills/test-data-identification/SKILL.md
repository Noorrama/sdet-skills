---
name: backend-test-data-identification
description: Identify, classify and associate every test-data fixture in the approved automation_plan.json with a Test Data Domain, a real TDP category, and the operation sequence needed to close the gap. Calls the TestBuddy MCP (TestDataAgent_get_supported_category / TestDataAgent_generate_testbuddy_prompt) and validates every returned category against the fixture's own signals — the matcher never reports a no-match, so an uncorroborated category is rejected rather than trusted. Never invents category or operation names. Emits test_data_manifest.json plus an enriched automation_plan.json carrying test_data_output per fixture. Identification only — it provisions nothing; test-data-provision consumes its output.
---

# Backend Test Data Identification

First of the two entrypoints of the **test-data-generation** stage. It runs straight after
`automation-plan-generator` and answers one question per fixture: *where does this data come from?*

For every fixture it decides the Test Data Domain, the exact TDP category, the ordered operations
needed to reach the required state, and whether TDP can serve the fixture at all — then emits an
execution-ready provisioning plan the downstream stage can consume without re-reasoning.

**Key design principle:** this stage **identifies, it does not create**. No entity is provisioned
here, no create/mutate tool is called. It reads catalogs and writes a plan.
`test-data-provision` executes that plan at code-generation / execution time.

## Reads

| Source | Purpose |
|---|---|
| `automation_plan.json` (approved) | `fixtures_summary[]` → `fixture_id`, `description`, `required_state`, `used_by_scenarios[]`. These three fields are the whole input signal. |
| `references/test_data_domains.md` | Step 1 knowledge — Test Data Domain definitions, signals and disambiguation rules |
| TestBuddy MCP → `TestDataAgent_get_supported_category` | Best-match TDP category for a domain + signal set, plus `candidates[]` and a ready-made `TDP_Request`. Returns a nearest match always — see the validation gate. |
| TestBuddy MCP → `get_supported_operations` | The supported-operation catalog per domain. **Not yet shipped** — until it is, fall back to the live `<Domain>Agent_*` tool inventory. |
| TestBuddy MCP → `TestDataAgent_generate_testbuddy_prompt` | Turns a resolved category into the prompt TestBuddy will execute |

If the plan carries fixtures inline as per-scenario `test_data[]` (the RFC's illustrative shape)
instead of a root `fixtures_summary[]`, treat each entry identically — `fixture_id` + `description`
+ `required_state` is the contract, not its position in the document.

## Model
Fast tier — Haiku. The work is catalog lookup plus semantic match; only operation sequencing reasons.

## MCP contract — the three calls

TestBuddy owns the category vocabulary and the prompt wording. The skill classifies, **validates**,
and sequences. Tool names below are the live ones as verified against TestBuddy v1.28.1 — note the
singular `category` and the lowercase `testbuddy`; the RFC's spellings do not resolve.

| # | Call | Send | Get back | Writes |
|---|---|---|---|---|
| 1 | `TestDataAgent_get_supported_category` | `test_data_domain` (required), `test_data_type_signals[]`, `description` (fallback signal source) | `tdp_test_data_category` (single best match), `candidates[]`, `TDP_Request`, `TDP_Payload` | `test_data_details.tdp_test_data_category` — **only after the validation gate below** |
| 2 | *(not yet shipped)* `get_supported_operations` | The domains of the signals the category does **not** cover — primary domain **plus** any neighbour domain a leftover signal belongs to | Supported operation names + each one's input contract | `test_data_details.test_data_operations[]` — verbatim names, ordered by the sequencing rules |
| 3 | `TestDataAgent_generate_testbuddy_prompt` | The resolved category + assembled record | The executable TestBuddy prompt | `test_buddy_prompt` |

- Calls 1 and 2 are **read-only catalog lookups** — they identify what TDP can serve; they neither reserve nor create anything. Note that *provisioning* tools in the same server (`DriverAgent_get_driver_data`, `CustomerAgent_get_customer_data`, …) allocate from the shared TDP pool — never call those here.
- **Operations cross domain boundaries; categories do not.** A `CUSTOMER` fixture needing a card is category `CUSTOMER_WITH_*` from the CUSTOMER catalog plus `CREATE_CREDIT_CARD` / `ADD_CREDIT_CARD_TO_USER` from the PAYMENT_INSTRUMENT catalog. Look up operations in every domain a leftover signal touches, keep `test_data_domain` as the primary entity, and never widen the category search beyond that domain.
- `test_data_status` is a *conclusion* of calls 1 and 2 (see the decision table), never an independent guess.
- Call 3 runs only once 1 and 2 have settled, so the prompt describes the final plan. Skip it for `TDP_COMPLETE_FALLBACK` — there is nothing TestBuddy can execute — and write `test_buddy_prompt: null`.
- **Batch by domain.** Call 1 is LLM-backed and slow — measured 33–91s per call against a 379-candidate DRIVER catalog. Resolve one category per distinct `(domain, signal-set)`, reuse it across every fixture and scenario sharing that set, and allow a timeout of at least 120s. The per-`(scenario, fixture)` fan-out applies to *records*, never to calls.
- **On tool failure, stop that fixture** — record it in `unidentified_fixtures[]` with `reason: CATALOG_UNAVAILABLE`. Never substitute a remembered or plausible-looking category/operation name for a failed lookup.
- Until call 2 ships, derive candidate operations from the live per-domain tool inventory (`<Domain>Agent_*` tool names and their input schemas) and mark every one `operationSupported: false` unless the tool exists. Do not invent operation names outside that inventory; a needed capability with no tool is a `missing_operations` entry, not an operation.

### Validation gate — call 1 never reports "no match"

`get_supported_category` always returns its nearest match out of the whole catalog. It has no
no-match answer. Verified: `["progressing_yearly_mjg"]` and `["baseline_driver"]` both returned
`DRIVER__ID__CAR`, a category neither signal mentions, out of 379 candidates. Taking the response at
face value would silently mis-provision every fixture whose state TDP does not model, and would make
`TDP_OPERATION_FALLBACK` unreachable.

So treat `tdp_test_data_category` as a **candidate, not an answer**. Accept it only if the category
name or its documented meaning is corroborated by the fixture's own signals:

| Check | Accept | Reject |
|---|---|---|
| At least one `test_data_type_signals[]` entry maps to a discriminating token in the returned category name (vehicle type, country, product, wallet/instrument state) | `["Bike","Polygon"]` → `DRIVER__ID__BIKE` — *Bike* corroborates | `["progressing_yearly_mjg"]` → `DRIVER__ID__CAR` — nothing says *car* |
| The signals that drove the match describe entity **selection**, not entity **mutation** | `["Active","Linked Wallet"]` → `CUSTOMER_WITH_GO_PAY` | `["broken_yearly_streak"]` → any category; a streak is state to be set, not a pool attribute |

On reject, set `tdp_test_data_category: null`, record the returned value and the top few
`candidates[]` in `identification_notes` so the reviewer can see what the matcher proposed, and let
the decision table place the fixture in `TDP_OPERATION_FALLBACK` or `TDP_COMPLETE_FALLBACK`. Set
`match_confidence: low` on every accepted-but-unanimous-signal case so it still reaches review.

### TDP_Request / TDP_Payload

Call 1 also returns a ready-made TDP request for the resolved category. Carry it through verbatim as
`test_data_details.tdp_request` — it is structured and unambiguous, where the prompt is prose that
TestBuddy must re-parse. Provisioning should prefer `tdp_request` and treat `test_buddy_prompt` as
the human-readable rendering for review gates and logs. Drop `tdp_request` when the category is
rejected by the validation gate — a request built on a wrong category is worse than none.

## Step 1 — Test Data Domain definition (knowledge)

`references/test_data_domains.md` is the maintained memory for this stage: what each domain owns,
the signals that point to it, and how to disambiguate neighbours (CUSTOMER vs USER,
WALLET_BALANCE vs CUSTOMER, PAYMENT_INSTRUMENT vs CUSTOMER).

Extending the vocabulary is a **file edit, not a skill change**:
- new domain → add a section to `references/test_data_domains.md`
- new category or operation → nothing to do; it arrives through the MCP catalog tools

Never hardcode a domain, category, or operation list in this skill or in generated output.

## Step 2 — Domain & category identification (per fixture)

| Field | How it is derived |
|---|---|
| `scenario_id` | Copied from the plan. One record per `(scenario_id, fixture_id)` pair — a fixture shared by 3 scenarios yields 3 records. |
| `fixture_id` | Copied verbatim from `fixtures_summary[]`. |
| `test_data_domain` | Fixture details (`description` + `required_state`) matched against `references/test_data_domains.md`. |
| `test_data_type_signals[]` | Atomic state signals lifted from `description` + `required_state` — one signal per concept, wording taken from the fixture where possible (`"Bike"`, `"4w"`, `"SDF"`, `"Polygon"`, `"non jabo"`, `"Linked Wallet"`). These signals, not the prose, drive the category and operation lookups. **Signal, not state:** a description carries entity state *and* harness setup; only entity state becomes a signal (see the exclusion rule below). |
| `test_data_details.tdp_test_data_category` | Best match returned by `TestDataAgent_get_supported_category(test_data_domain, test_data_type_signals, description)`, **then passed through the validation gate**. Verbatim from the response when accepted; `null` when rejected or when the call fails. `required_state.category` from the plan is likewise a **candidate, not an answer** (see below). |
| `test_data_details.test_data_operations[]` | For every signal the chosen category does **not** already satisfy, the operation that closes it — from `get_supported_operations` once shipped, else from the live `<Domain>Agent_*` tool inventory — ordered (see sequencing rules). `null` when the category satisfies everything. `[]` when a needed operation is unsupported. |
| `test_data_details.count` | `required_state.count`, default `1`. |
| `test_data_status` | Decision table below. |
| `test_buddy_prompt` | `TestDataAgent_generate_testbuddy_prompt` on the resolved category — TestBuddy owns the wording, this skill does not compose it by hand. `null` for `TDP_COMPLETE_FALLBACK` or a rejected category. |
| `test_data_details.tdp_request` | `TDP_Request` from call 1, carried through verbatim. `null` when the category is rejected. Provisioning prefers this over the prose prompt. |
| `identification_notes` | Free text for the reviewer: the category the matcher proposed and the top `candidates[]` when the validation gate rejects it. |
| `match_confidence` | `high` / `medium` / `low` for the domain + category match. `low` routes the fixture to human review before provisioning. |
| `actual_test_data` | `null`. Written later by `test-data-provision`. |

### `required_state.category` is a candidate, not an answer

`automation-plan-generator` pre-fills `required_state.entity` and `required_state.category` from
context. Both are **candidates for this stage to confirm** — the same way it leaves
`curl_reference` placeholders for downstream correction:

- Candidate category present and returned by `get_supported_category` → adopt it verbatim, `match_confidence: high`.
- Candidate present but **not what the matcher returns** (e.g. the plan asks for `CUSTOMER_WITH_SAVED_CARD` and TDP only has `CUSTOMER_WITH_WALLET`) → take the nearest real category and cover the difference with operations. Set `match_confidence: medium` and name the rejected candidate in the log — a plan repeatedly asking for a category TDP lacks is a TDP backlog item.
- Candidate absent, or the catalog contradicts `required_state.entity` (the state clearly belongs to another domain) → identify from the fixture details, set `match_confidence: medium`, and keep `test_data_domain` as the entity the fixture actually provisions.

Never pass a candidate category through unverified. It is the one field most likely to be stale.

### What is *not* a test-data signal

Fixture descriptions routinely carry harness setup alongside entity state. Only entity state is
identified here — everything below is `test-code-generator`'s job and must not produce a signal,
a category, or an operation:

- **Mock / stub state** — "vault-service stubbed to return HTTP 503", "6000ms fixed delay". WireMock setup, not data. (`automation-plan-generator` already rules that `mock_setup` is never a fixture.)
- **Feature flags** — "flag payment.card_save.enabled=OFF". Spring test context / flag override.
- **Container and migration state** — Testcontainers, Flyway. These arrive as `entity: DB_INFRA` and the whole fixture is skipped.
- **Assertion expectations** — the expected status code or error code.

A fixture whose description is *only* harness setup still has entity state underneath ("customer
with active wallet; vault stubbed 503") — identify the customer, ignore the stub.

### Status decision table

| TDP category match | Gap-closing operations | `test_data_status` | `test_data_operations` |
|---|---|---|---|
| Covers the full required state | none needed | `TDP_SUPPORTED` | `null` |
| Covers part of the required state | all supported | `TDP_HYBRID_FALLBACK` | ordered `[...]` |
| No category matches | all supported | `TDP_OPERATION_FALLBACK` | ordered `[...]`, category `null` |
| Required state not covered | one or more unsupported | `TDP_COMPLETE_FALLBACK` | `[]` |

The status is a **conclusion of the two catalog lookups**, never a guess: derive it from what
`get_supported_category` returned **and survived the validation gate**, plus what the operation
lookup actually returned. If a catalog call
fails, stop — do not downgrade the status to a fallback to keep the run moving.

### Operation sequencing rules

The sequence is derived from the fixture details, the operation input contracts in the tool
descriptions, and the examples below.

- **Dependency first** — an entity must exist before it can be associated or mutated.
- **Lookup before mutate** — `IDENTIFY_*` / `FETCH_*` precede `ASSIGN_*` / `ADD_*` / `UPDATE_*` when the mutation needs an ID the lookup returns.
- **Create before associate** — `CREATE_CREDIT_CARD` → `ADD_CREDIT_CARD_TO_USER`.
- **One operation per unmet signal** — no operation for state the category already provides.
- **`operationInput` is sourced, never invented** — values come from `required_state` / `required_state.config`, from a preceding operation's output, or from the fixture description. If a needed input is unknown, emit the key with `null` and flag the fixture for review rather than fabricating an ID.
- **`operationSupported: true` only when the operation actually exists** — in `get_supported_operations` once shipped, else in the live `<Domain>Agent_*` tool inventory. If a required step is missing from the catalog, the fixture becomes `TDP_COMPLETE_FALLBACK` with `test_data_operations: []`, and the missing names go to `unidentified_fixtures[].missing_operations` so the gap is actionable for the TDP team.

### Worked examples

**Fully served by TDP** — *"User account in ACTIVE status with a linked wallet"*, `{account_status: ACTIVE, wallet_linked: true}`
→ domain `CUSTOMER`, signals `["Active", "Linked Wallet"]`, category `CUSTOMER_WITH_GO_PAY` covers both
→ `TDP_SUPPORTED`, operations `null`.

**Category plus operations** — *"A valid Visa card not previously saved by this user"*, `{card_type: VISA, is_expired: false, already_saved: false}`
→ domain `PAYMENT_INSTRUMENT`, the customer comes from `CUSTOMER_WITH_GO_PAY` but the card does not
→ `TDP_HYBRID_FALLBACK`, operations `CREATE_CREDIT_CARD {cardType: Visa}` → `ADD_CREDIT_CARD_TO_USER {userType: customer}`.

**Lookup then assign** — *"A Bike driver with positive wallet balance associated with a polygon"*
→ domain `DRIVER`, category `DRIVER__ID__BIKE`, the polygon association is not part of the category
→ `TDP_HYBRID_FALLBACK`, operations `IDENTIFY_POLYGON {polygonCollectionId: daily_income_delivery}` → `ASSIGN_POLYGON {polygonId: <from IDENTIFY_POLYGON>}`.

**No category, operations only** — *"6 stop locations by route distance in service area 3"*
→ domain `LOCATION`, no category matches, `FETCH_LOCATION` is supported
→ `TDP_OPERATION_FALLBACK`, category `null`, operations `[FETCH_LOCATION {...}]`.

**Dead end** — *"A Bike driver who has opted into and started a shift"*
→ domain `DRIVER`, no category carries shift state and no shift operation exists in the catalog
→ `TDP_COMPLETE_FALLBACK`, operations `[]`, `test_buddy_prompt: null`, fixture listed in
`unidentified_fixtures[]` with `missing_operations: ["OPT_INTO_SHIFT", "START_SHIFT"]`.

## Outputs

**1 → `test_data_manifest.json`**
- `epic_id`, `manifest_version`, `source_plan_version`, `identified_at`
- `records[]` — one `test_data_output` object per `(scenario_id, fixture_id)`
- `unidentified_fixtures[]` — `fixture_id`, `scenario_ids[]`, `reason` (`NO_DOMAIN_MATCH` | `NO_CATEGORY_MATCH` | `UNSUPPORTED_OPERATION` | `CATALOG_UNAVAILABLE`), `missing_operations[]`
- `identification_summary` — per-status counts, `unidentified`, `skipped_db_infra`, `needs_human_review[]`, `domains_seen[]`

**2 → enriched `automation_plan.json`**
For each fixture in `fixtures_summary[]`, write its records into the existing `output` field:
`output = { "test_data_output": [ <records for this fixture> ] }`.
Everything else in the plan is left byte-identical — no edits to test classes, methods,
`curl_reference`, `required_state`, or `response_fields_used`. Enrichment is additive.

A fixture that lands in `unidentified_fixtures[]` keeps `output: null` — no `test_data_output` is
emitted for it, so no downstream stage tries to provision something TDP cannot serve.

## Guardrails
- **Never invent a category name.** It must be verbatim from `TestDataAgent_get_supported_category`. If the catalog is unreachable, stop and report `CATALOG_UNAVAILABLE` — do not guess a plausible name.
- **Never accept a category the signals do not corroborate.** The matcher has no no-match answer; an unvalidated category is a silent mis-provision. Reject, null the category, keep the proposal in `identification_notes`.
- **Never invent an operation name.** It must be verbatim from `get_supported_operations` or the live `<Domain>Agent_*` inventory. A needed capability with no tool is a `missing_operations` entry, never an operation.
- **Never invent identifiers or values** — polygon IDs, customer IDs, service-area IDs come from `required_state` / `config` / a preceding operation's output.
- **No secrets or PII anywhere** — signals, `operationInput` and prompts carry categories and states only. Never a real card number, token, phone number or account number. Sensitive states are described, not populated.
- **Identification only** — call no create, mutate, lease or recharge tool. Provisioning is `test-data-provision`.
- Skip fixtures with `required_state.entity: DB_INFRA` — Testcontainers / migration fixtures are not TDP-served. Count them as `skipped_db_infra`.
- One record per `(scenario_id, fixture_id)`; the same fixture reused across scenarios produces one record per scenario, all under that fixture's single `output`.
- `test_data_type_signals[]` must be traceable to the fixture text — do not enrich the fixture with state the plan never asked for.
- `count` never exceeds what `required_state.count` states; default `1`, never `0`.
- The status enum is exactly the four values in the decision table. (The RFC's sample JSON shows `TDP_HYBRID_SUPPORTED` in one place — that is an alias of `TDP_HYBRID_FALLBACK`; normalise to the four.)

## Re-identification

Re-runs are the norm, not the exception — the upstream plan changes as scenarios are added.

- Triggered when `automation_plan.json` changes. Diff on `(fixture_id, description, required_state)`: re-identify changed and new fixtures only, carry unchanged records forward, drop records for removed fixtures.
- Also re-run fixtures currently in a fallback status when the TDP catalog gains categories or operations — yesterday's `TDP_OPERATION_FALLBACK` may be today's `TDP_SUPPORTED`.
- Bump `manifest_version` and set `source_plan_version` on every run.

## Output flow
Goes to the SDET review gate together with the automation plan. Fixtures in
`needs_human_review[]` (low confidence) and `unidentified_fixtures[]` are reviewed before
`test-data-provision` runs — an unnoticed fallback surfaces as a test failure at execution time.

## Validate
`jsonschema.validate(output, schemas/test_data_manifest.schema.json)`
Re-validate the enriched plan against `schemas/automation_plan.schema.json`.

## Log
N fixtures identified; per-status counts (supported / hybrid / operation / complete fallback);
N unidentified with reasons; N low-confidence for review; N skipped (DB_INFRA); domains seen.
