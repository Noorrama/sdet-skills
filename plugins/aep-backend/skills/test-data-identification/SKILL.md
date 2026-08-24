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
| `references/index.md` | **Step 1 entry point** — the QA Knowledge Catalog. Routes to per-domain OKF bundles and carries the procedure for reading a natural-language statement. |
| `references/customer/index.md` · `references/driver/index.md` | Populated domain bundles: real TDP category enums (with `isEnabled`), the account-vs-wallet-amount split, signal→token vocabulary |
| `references/sequence/sequence.md` | **Operation authority** — every Consumer/Driver function as an ordered call sequence, plus the composite booking flow. Use it for sequencing instead of inferring order. |
| `references/test_data_domains.md` | Domain vocabulary for the domains with no bundle yet (MERCHANT, VOUCHER, PAYMENT_INSTRUMENT, BOOKING, LOCATION) + cross-domain disambiguation |
| TestBuddy MCP → `TestDataAgent_get_supported_category` | Best-match TDP category for a domain + signal set, plus `candidates[]` and a ready-made `TDP_Request`. Returns a nearest match always — see the validation gate. |
| TestBuddy MCP → `TestDataAgent_get_supported_operation` | Operation catalog for a domain + signal set. Federates TestBuddy's own `<Domain>Agent_*` tools and Pertamax features; returns names, `operationSupported`, and descriptions. Prefer a TestBuddy/TDP tool, fall back to Pertamax. |
| TestBuddy MCP → `TestDataAgent_generate_testbuddy_prompt` | Turns a resolved category into the prompt TestBuddy will execute |

If the plan carries fixtures inline as per-scenario `test_data[]` (the RFC's illustrative shape)
instead of a root `fixtures_summary[]`, treat each entry identically — `fixture_id` + `description`
+ `required_state` is the contract, not its position in the document.

## Preflight — one hard stop, everything else degrades

**The hard stop is the TestBuddy MCP.** If the connection fails, or a required tool is absent, or the
first real call errors — **stop. Do not proceed to any fixture, do not write output.** Without the
category and operation catalogs there is nothing to identify against, and continuing would express an
infrastructure outage as a data verdict: fixtures labelled `TDP_NOT_SUPPORTED` when the truth is
"the skill could not reach TestBuddy".

| Check | On failure |
|---|---|
| TestBuddy MCP reachable | **ABORT RUN** |
| `TestDataAgent_get_supported_category` present | **ABORT RUN** |
| `TestDataAgent_get_supported_operation` present | **ABORT RUN** |
| Input plan missing / unparseable / zero fixtures | **ABORT RUN** — there is no work to do |

Check TestBuddy **first**, before reading knowledge or looping fixtures: a 3-second connect test
saves a run that would otherwise fail after minutes of catalog calls.

### Knowledge gaps degrade, they do not abort

A knowledge problem is scoped to the fixtures that depend on it, so it must not kill the whole run:

| Situation | Behaviour |
|---|---|
| Domain bundle missing for a domain the plan uses | Identify from `test_data_domains.md`; cap `match_confidence` at `medium`; add the fixture to `needs_human_review` |
| Bundle loads but parses partially (e.g. 7 of 8 category rows) | Continue with what parsed, record the shortfall in `run_log`, and cap affected fixtures at `medium` — an `isEnabled` check against an incomplete table cannot be trusted |
| `sequence/sequence.md` missing | Continue; operation ordering falls back to the sequencing rules in this skill, flagged in `run_log` |
| `references/index.md` missing | Continue via `test_data_domains.md`; every fixture caps at `medium` |

Every degradation must be **visible**: an entry in `run_log.json` naming the missing or partial
source, and reduced confidence on the records it touched. Silent degradation is the failure this
section exists to prevent — a run that looks clean while built on knowledge it never loaded.

### Single-fixture failures

Once TestBuddy proved reachable, a later lookup failure is that fixture's problem alone:
`unidentified_fixtures[].reason: CATALOG_UNAVAILABLE`, and the run continues.

On an abort, write **no** `enriched_automation_plan.json` and **no** `test_data_manifest.json` —
leaving the previous run's files intact beats replacing them with a partial. Emit `run_log.json`
with the failed check, and stop.

## Model
Fast tier — Haiku. The work is catalog lookup plus semantic match; only operation sequencing reasons.

## MCP contract — the three calls

TestBuddy owns the category vocabulary and the prompt wording. The skill classifies, **validates**,
and sequences. Tool names below are the live ones as verified against TestBuddy v1.28.1 — note the
singular `category` and the lowercase `testbuddy`; the RFC's spellings do not resolve.

| # | Call | Send | Get back | Writes |
|---|---|---|---|---|
| 1 | `TestDataAgent_get_supported_category` | `test_data_domain` (required), `test_data_type_signals[]`, `description` (fallback signal source) | `tdp_test_data_category` (single best match), `candidates[]`, `TDP_Request`, `TDP_Payload` | `test_data_details.tdp_test_data_category` — **only after the validation gate below** |
| 2 | `TestDataAgent_get_supported_operation` | The domains of the signals the category does **not** cover — primary domain **plus** any neighbour domain a leftover signal belongs to | Supported operation names with `operationSupported` and descriptions | `test_data_details.test_data_operations[]` — verbatim names, ordered by the sequencing rules |
| 3 | `TestDataAgent_generate_testbuddy_prompt` | The resolved category + assembled record | The executable TestBuddy prompt | `test_buddy_prompt` |

- Calls 1 and 2 are **read-only catalog lookups** — they identify what TDP can serve; they neither reserve nor create anything. Note that *provisioning* tools in the same server (`DriverAgent_get_driver_data`, `CustomerAgent_get_customer_data`, …) allocate from the shared TDP pool — never call those here.
- **Operations cross domain boundaries; categories do not.** A `CUSTOMER` fixture needing a card is category `CUSTOMER_WITH_*` from the CUSTOMER catalog plus `CREATE_CREDIT_CARD` / `ADD_CREDIT_CARD_TO_USER` from the PAYMENT_INSTRUMENT catalog. Look up operations in every domain a leftover signal touches, keep `test_data_domain` as the primary entity, and never widen the category search beyond that domain.
- `test_data_status` is a *conclusion* of calls 1 and 2 (see the decision table), never an independent guess.
- Call 3 runs only once 1 and 2 have settled, so the prompt describes the final plan. Skip it for `TDP_NOT_SUPPORTED` — there is nothing TestBuddy can execute — and write `test_buddy_prompt: null`.
- **Batch by domain.** Call 1 is LLM-backed and slow — measured 33–91s per call against a 379-candidate DRIVER catalog. Resolve one category per distinct `(domain, signal-set)`, reuse it across every fixture and scenario sharing that set, and allow a timeout of at least 120s. The per-`(scenario, fixture)` fan-out applies to *records*, never to calls.
- **On tool failure, stop that fixture** — record it in `unidentified_fixtures[]` with `reason: CATALOG_UNAVAILABLE`. Never substitute a remembered or plausible-looking category/operation name for a failed lookup.
- Until call 2 ships, resolve operations from two grounded sources: `references/sequence/sequence.md` for **which** function and **in what order** (it catalogs every Consumer/Driver function as a call sequence, plus the composite booking flow where both wallets are topped up before the booking is created), and the live `<Domain>Agent_*` tool inventory for **whether a callable tool exists**. Mark `operationSupported: false` unless the tool exists. Never invent an operation name; a capability in neither source is a `missing_operations` entry, not an operation.
- **Don't emit an operation the pool already satisfies.** Per the bundles, TDP pre-provisions by category, so a linked wallet, a default balance, or a saved address that comes with the category needs no operation. Operations exist only to close the gap the category leaves.

### Validation gate — call 1 never reports "no match"

`get_supported_category` always returns its nearest match out of the whole catalog. It has no
no-match answer. Verified: `["progressing_yearly_mjg"]` and `["baseline_driver"]` both returned
`DRIVER__ID__CAR`, a category neither signal mentions, out of 379 candidates. Taking the response at
face value would silently mis-provision every fixture whose state TDP does not model, and would make
`TDP_OPERATION_FALLBACK` unreachable.

So treat `tdp_test_data_category` as a **candidate, not an answer**. Corroborate it against the
signal→token vocabulary in the domain bundle (`references/<domain>/index.md`) — not against tokens
you infer. Accept only when:

| Check | Accept | Reject |
|---|---|---|
| At least one `test_data_type_signals[]` entry maps to a discriminating token in the returned category name (vehicle type, country, product, wallet/instrument state) | `["Bike","Polygon"]` → `DRIVER__ID__BIKE` — *Bike* corroborates | `["progressing_yearly_mjg"]` → `DRIVER__ID__CAR` — nothing says *car* |
| The signals that drove the match describe entity **selection**, not entity **mutation** | `["Active","Linked Wallet"]` → `CUSTOMER_WITH_GO_PAY` | `["broken_yearly_streak"]` → any category; a streak is state to be set, not a pool attribute |
| The category is `isEnabled: true` in its domain bundle | `CUSTOMER_WITH_GO_PAY` — enabled | `Customer_With_Go_Pay_coins` — **disabled**; reject however well the signals read, and record `TDP_NOT_SUPPORTED` |
| **Every** token in the returned name is corroborated, not just one — driver names are composite (`DRIVER__<COUNTRY>__<TYPE>`) | `["Bike","ID"]` → `DRIVER__ID__BIKE` — both segments accounted for | `["Bike"]` → `DRIVER__ID__CAR_ECONOMY_SHIELD` — `CAR`, `ECONOMY`, `SHIELD` all unsupported |

On reject, set `tdp_test_data_category: null`, record the returned value and the top few
`candidates[]` as an `identification_steps` entry so the reviewer can see what the matcher proposed, and let
the decision table place the fixture in `TDP_OPERATION_FALLBACK` or `TDP_NOT_SUPPORTED`. Set
`match_confidence: low` on every accepted-but-unanimous-signal case so it still reaches review.

### TDP_Request / TDP_Payload

Call 1 also returns a ready-made TDP request for the resolved category. Carry it through verbatim as
`test_data_details.tdp_request` — it is structured and unambiguous, where the prompt is prose that
TestBuddy must re-parse. Provisioning should prefer `tdp_request` and treat `test_buddy_prompt` as
the human-readable rendering for review gates and logs. Drop `tdp_request` when the category is
rejected by the validation gate — a request built on a wrong category is worse than none.

## Step 1 — Test Data Domain definition (knowledge)

`references/index.md` is the entry point: a QA Knowledge Catalog whose domains are OKF bundles.
Read it first — it names each domain's identifying keys and gives the procedure for turning a
natural-language statement into a domain + signals (identify the noun, then the payment/wallet
mention, then vehicle/service tokens, then any downstream use that spills into another domain).

| Read | For |
|---|---|
| `references/index.md` | Which domain, and how to parse the statement |
| `references/<domain>/index.md` | That domain's real TDP category enum and signal→token vocabulary |
| `references/sequence/sequence.md` | Which operation, and in what order |
| `references/test_data_domains.md` | Domains without a bundle yet, and cross-domain disambiguation |

Bundles exist today for **Consumer** and **Driver** only. For every other domain, fall back to
`test_data_domains.md` and treat the identification as `match_confidence: medium` at best — there is
no grounded category enum to corroborate against.

Extending the vocabulary stays a **file edit, not a skill change**: a new domain becomes a bundle
directory plus a row in `references/index.md`. Never hardcode a domain, category, or operation list
in this skill.

### What the bundles change about identification

Three things in the bundles override the skill's generic behaviour:

- **Pooling is the default path.** TDP pre-provisions accounts by category; most fixtures are a *select from pool*, not a create. `CREATE_CUSTOMER` / `POST /driver/create` are pool-miss cases only. Do not emit a creation operation for a state the pool already serves.
- **The account-vs-wallet-amount split.** Whether an instrument is *linked* is the category; how much is *in it* is a mutable balance. "A user with gopay" is `CUSTOMER_WITH_GO_PAY` and needs **no** operation. Only when the amount itself is under test does a recharge operation join the record.
- **`isEnabled: false` is a hard stop.** `Customer_With_Go_Pay_coins` and `Customer_With_Partial_Go_Pay_coins` are disabled in `TestDataCategoryCustomer`. A coins category coming back from the matcher must be rejected by the validation gate and recorded as `TDP_NOT_SUPPORTED`, however well the signals seem to corroborate it.

## Step 2 — Domain & category identification (per fixture)

**Refer to the fixture description and check it against the knowledge to identify the
`test_data_domain`.** This is the first action for every fixture, and it is not optional:

1. Read the fixture's `description` **and** `required_state` — together they are the statement.
2. Check that statement against the knowledge in `references/` — `index.md` for the domain table and
   the statement-reading procedure, then the matching `<domain>/index.md` bundle.
3. Only then assign `test_data_domain`.

Never assign a domain from the `fixture_id` name, from the plan's `required_state.entity` alone, or
from memory. `required_state.entity` is a **candidate to confirm against the knowledge** — when the
description describes state the knowledge assigns to a different domain, the knowledge wins and the
disagreement is recorded as an `identification_steps` entry. The same two inputs (description + required_state),
read through the same knowledge, then produce `test_data_type_signals[]`.


| Field | How it is derived |
|---|---|
| `scenario_id` | Copied from the plan. One record per `(scenario_id, fixture_id)` pair — a fixture shared by 3 scenarios yields 3 records. |
| `fixture_id` | Copied verbatim from `fixtures_summary[]`. |
| `test_data_domain` | Fixture details (`description` + `required_state`) resolved via `references/index.md` — its domain table and statement-reading procedure; `test_data_domains.md` for domains with no bundle. |
| `test_data_type_signals[]` | Atomic state signals lifted from `description` + `required_state` — one signal per concept, wording taken from the fixture where possible (`"Bike"`, `"4w"`, `"SDF"`, `"Polygon"`, `"non jabo"`, `"Linked Wallet"`). These signals, not the prose, drive the category and operation lookups. **Signal, not state:** a description carries entity state *and* harness setup; only entity state becomes a signal (see the exclusion rule below).  |
| `test_data_details.tdp_test_data_category` | Best match returned by `TestDataAgent_get_supported_category(test_data_domain, test_data_type_signals, description)`, **then passed through the validation gate**. Verbatim from the response when accepted; `null` when rejected or when the call fails. `required_state.category` from the plan is likewise a **candidate, not an answer** (see below). |
| `test_data_details.test_data_operations[]` | For every signal the chosen category does **not** already satisfy, the operation that closes it — from `get_supported_operations` once shipped, else from the live `<Domain>Agent_*` tool inventory — ordered (see sequencing rules). `null` when the category satisfies everything. `[]` when a needed operation is unsupported. |
| `test_data_details.count` | `required_state.count`, default `1`. |
| `test_data_status` | Decision table below. |
| `test_buddy_prompt` | `TestDataAgent_generate_testbuddy_prompt` on the resolved category — TestBuddy owns the wording, this skill does not compose it by hand. `null` for `TDP_NOT_SUPPORTED` or a rejected category. |
| `test_data_details.tdp_request` | `TDP_Request` from call 1, carried through verbatim. `null` when the category is rejected. Provisioning prefers this over the prose prompt. |
| `identification_steps[]` | **Ordered list of short sentences** — what the agent actually did for this fixture, one entry per action, in the order taken. Not free-form prose and not a summary. |
| `match_confidence` | `high` / `medium` / `low` for the domain + category match. `low` routes the fixture to human review before provisioning. |

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

### `test_data_type_signals[]` must be sequentially meaningful

Signals are not an unordered bag of adjectives. **Emit them in the order the state must come into
existence**, because the operation chain is derived from that order — a signal list that reads out of
order produces an out-of-order provisioning sequence that fails at execution time.

The dependency rules come from the knowledge (`references/sequence/sequence.md`), not from the
fixture's prose order:

| Statement | Wrong (as-written order) | Right (dependency order) |
|---|---|---|
| "A recharged Bike driver" | `["Recharge", "Bike"]` — recharge cannot happen before the driver exists | `["Bike", "Recharge"]` |
| "Book a ride with a topped-up GoPay customer" | `["Ride booking", "Wallet recharge", "Customer"]` | `["Customer", "Wallet recharge", "Ride booking"]` — booking cannot be done before customer creation **and** recharge |

Two invariants to apply every time:

- **Entity before mutation** — the entity's selecting signals (vehicle type, country, instrument
  linked) precede any signal describing a change to it (recharge, assign, set).
- **Prerequisite before consumer** — a signal whose operation consumes another's output comes after
  it. Booking consumes a customer and a funded wallet, so it is last.

Check the emitted list against `sequence/sequence.md` before writing the record: if the derived
operation chain would violate a sequence documented there, the signal order is wrong, not the
sequence.

### `identification_steps[]` — what the agent did, per fixture

One short sentence per action, in the order taken. A reviewer should be able to explain a wrong
category or a missing operation from this list alone, without opening `run_log.json`:

```json
"identification_steps": [
  "Read references/index.md and customer/index.md; confirmed domain CUSTOMER from description + required_state.",
  "Extracted signals in dependency order: Customer, Wallet recharge, GoPay payment, Ride booking.",
  "get_supported_category returned CUSTOMER_WITH_GO_PAY out of 15 candidates.",
  "Accepted the category: GO_PAY corroborated by the 'Active wallet' signal; isEnabled true.",
  "Plan proposed CUSTOMER_WITH_WALLET_RECHARGE, which the catalog does not contain — substituted the returned category.",
  "Decomposed into 3 capabilities: acquire Customer, Wallet recharge, Ride booking.",
  "Resolved Wallet recharge to CustomerAgent_recharge_customer_gopay (TestBuddy preferred over Pertamax handle_gopay_wallet_topup).",
  "Concluded TDP_HYBRID_FALLBACK: category covers the entity, operations close the rest."
]
```

Rules:
- **Every step the agent took**, including the ones that changed nothing — a rejected category, a retried lookup, a capability that found no operation. Silence about a step reads as "it never happened".
- **State what was decided and why**, not just what was called. `"Rejected CUSTOMER_WITH_GO_PAY_COINS: isEnabled false in the knowledge"` is useful; `"called get_supported_category"` is not.
- **Name the disagreements**: the plan's proposed category vs the catalog's, the alternatives not chained, the tier a tool came from.
- It is **per fixture**, so a fixture used by 14 scenarios repeats the same list across its 14 records. `run_log.json` remains the run-level trail with timings; this is the record-level explanation.

### Status decision table

| TDP category match | Gap-closing operations | `test_data_status` | `test_data_operations` |
|---|---|---|---|
| A TDP category covers the full required state | none needed | `TDP_SUPPORTED` | `null` |
| No TDP category, but a TestBuddy agent tool serves the entity directly | none needed | `TESTBUDDY_SUPPORTED` | `null` |
| Partial support in TDP **or** TestBuddy | all supported (via MCP: TestBuddy or Pertamax) | `TDP_HYBRID_FALLBACK` | ordered `[...]` |
| No category matches | all supported | `TDP_OPERATION_FALLBACK` | ordered `[...]`, category `null` |
| Required state not covered | one or more unsupported | `TDP_NOT_SUPPORTED` | `[]` |

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
- **Operation *inputs* are not this stage's output.** Identification names the operation and its source; the argument values belong to provisioning, which knows the runtime IDs (a customer id only exists after the customer is fetched). Do not emit an `operationInput` object.
### Operation provenance — required per operation

Every operation carries where it comes from, so provisioning knows which client to call:

| Field | Value |
|---|---|
| `operation` | The logical operation name (e.g. `CREATE_CREDIT_CARD`, `ASSIGN_POLYGON`) |
| `operationSource` | `tdp` · `testbuddy` · `pertamax` — the two callable MCP tools today are TestBuddy and Pertamax. `gbt` is planned for a later stage; do not emit it until a GBT MCP server is reachable. |
| `operationMcpTool` | The exact MCP tool/feature that performs it (e.g. `CustomerAgent_recharge_customer_gopay`, `handle_set_gopay_pin`). `null` when unresolved. |
| `operationMcpToolDescription` | The tool's own description, carried through verbatim so reviewers and provisioning see its contract without re-querying |
| `operationSupported` | `true` only when `operationMcpTool` resolves to a tool that exists |

- **`operationSupported: true` only when the operation actually exists** — in `get_supported_operations` once shipped, else in the live `<Domain>Agent_*` tool inventory. If a required step is missing from the catalog, the fixture becomes `TDP_NOT_SUPPORTED` with `test_data_operations: []`, and the missing names go to `unidentified_fixtures[].missing_operations` so the gap is actionable for the TDP team.

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
→ `TDP_NOT_SUPPORTED`, operations `[]`, `test_buddy_prompt: null`, fixture listed in
`unidentified_fixtures[]` with `missing_operations: ["OPT_INTO_SHIFT", "START_SHIFT"]`.

## Outputs

**1 → `test_data_manifest.json`**
- `epic_id`, `manifest_version`, `source_plan_version`, `identified_at`
- `records[]` — one `test_data_output` object per `(scenario_id, fixture_id)`
- `unidentified_fixtures[]` — `fixture_id`, `scenario_ids[]`, `reason` (`NO_DOMAIN_MATCH` | `NO_CATEGORY_MATCH` | `UNSUPPORTED_OPERATION` | `CATALOG_UNAVAILABLE`), `missing_operations[]`
- `identification_summary` — per-status counts, `unidentified`, `skipped_db_infra`, `needs_human_review[]`, `domains_seen[]`

**2 → `enriched_automation_plan.json`** (write as a new file; never edit the input plan in place)
For each fixture, write the records to a **`test_data_output` field on the fixture itself**, as a
sibling of `required_state`:

```json
{
  "fixture_id": "FIX-CARDPAY-001",
  "description": "...",
  "required_state": { ... },
  "test_data_output": [ { <record>, ... } ]
}
```

Not nested under an `output` wrapper — `test_data_output` is the field name the contract uses, and a
wrapper adds a level downstream has to unwrap for nothing. Everything else in the plan is left
byte-identical: no edits to test classes, methods, `curl_reference`, `required_state`, or
`response_fields_used`. Enrichment is additive.

A fixture that lands in `unidentified_fixtures[]` gets `test_data_output: null` — no `test_data_output` is
emitted for it, so no downstream stage tries to provision something TDP cannot serve.

## Action audit (debugging) → `run_log.json`

Record every action taken during the run — knowledge reads, each MCP call, the validation-gate
decision, operation lookups, status resolution, prompt generation — in order, with the outcome and
elapsed time. Write it to **`run_log.json`**, a third output alongside the manifest and the enriched
plan.

**It does not go into `test_data_output`, and therefore never into the enriched plan.** Two reasons:
the enriched plan is a provisioning contract that downstream stages consume, and debug data there is
noise; and a fixture used by 14 scenarios would carry 14 identical copies of its own audit.

Scope each entry with `fixture_id`; omit it for run-level setup steps (knowledge load, catalog reads).

| `step` | `fixture_id` | `action` | `target` | `result` |
|---|---|---|---|---|
| 1 | — | `read_knowledge` | `references/customer/index.md` | 8 categories, 2 disabled |
| 2 | — | `read_operation_catalog` | TestBuddy `tools/list` | 47 tools |
| 3 | FIX-001 | `get_supported_category` | `TestDataAgent_get_supported_category` | `CUSTOMER_WITH_GO_PAY`, 15 candidates, 16435ms |
| 4 | FIX-001 | `validate_gate` | knowledge vocabulary + `isEnabled` | ACCEPT: corroborated by `GO_PAY` |
| 5 | FIX-001 | `resolve_status` | decision table | `TDP_HYBRID_FALLBACK` |

`actual_test_data` is **not populated by this stage** — provisioning owns it, and per the RFC it
stays absent from identification output entirely.

## Guardrails
- **TestBuddy unreachable aborts the run** (see Preflight) — never express an infrastructure failure as a data verdict, and never emit partial output. Knowledge gaps degrade instead: continue, cap confidence at `medium`, and record the gap in `run_log.json`. Degradation must always be visible.
- **Never invent a category name.** It must be verbatim from `TestDataAgent_get_supported_category`. If the catalog is unreachable, stop and report `CATALOG_UNAVAILABLE` — do not guess a plausible name.
- **Never accept a category the signals do not corroborate.** The matcher has no no-match answer; an unvalidated category is a silent mis-provision. Reject, null the category, and record the proposal as an `identification_steps` entry.
- **Never invent an operation name.** It must be verbatim from `get_supported_operations` or the live `<Domain>Agent_*` inventory. A needed capability with no tool is a `missing_operations` entry, never an operation.
- **Never invent identifiers or values** — polygon IDs, customer IDs, service-area IDs come from `required_state` / `config` / a preceding operation's output.
- **No secrets or PII anywhere** — signals and prompts carry categories and states only. Never a real card number, token, phone number or account number. Sensitive states are described, not populated.
- **Identification only** — call no create, mutate, lease or recharge tool. Provisioning is `test-data-provision`.
- Skip fixtures with `required_state.entity: DB_INFRA` — Testcontainers / migration fixtures are not TDP-served. Count them as `skipped_db_infra`.
- One record per `(scenario_id, fixture_id)`; the same fixture reused across scenarios produces one record per scenario, all under that fixture's single `output`.
- `test_data_type_signals[]` must be traceable to the fixture text — do not enrich the fixture with state the plan never asked for.
- `count` never exceeds what `required_state.count` states; default `1`, never `0`.
- The status enum is exactly the **five** values in the decision table. `TDP_HYBRID_SUPPORTED` and `TDP_COMPLETE_FALLBACK` are **superseded** — they appear only in older RFC sample JSON and must never be emitted. Map them to `TDP_HYBRID_FALLBACK` and `TDP_NOT_SUPPORTED` if encountered in an input.

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
