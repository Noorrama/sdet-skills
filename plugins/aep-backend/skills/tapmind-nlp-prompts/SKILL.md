---
name: backend-tapmind-nlp-prompts
description: >-
  Write, fix, or generate real TapMind NLP test-step prompts —
  `TapMind.runStep(...)` / `TapMind.assertStep(...)` — and convert
  automation_plan scenarios into suite-ready Java tests with @Test /
  @TestInfo. Use when the user is writing/debugging a TapMind prompt,
  mentions TapMind / runStep / assertStep / bind_select / "entry where" /
  verify-only steps / grpc / grpcurl / grpc.invoke / rpc_alias, OR when given
  automation_plan.json (or sdet_plan
  step_descriptions) to generate prompts, batch-verify them, run steps
  via MCP, and emit corrected suite test methods. Before generating, scan
  for existing TapMind.runStep tests (NLP_COVERAGE.md) so only missing
  scenarios are emitted — same dedup discipline as gbt-test-code-generator.
  This is the actual
  TapMind SDK grammar — not the Allure `@Step("Given/When/Then ...")`
  labels used by backend-test-code-generator.
---

# TapMind NLP Prompt Writing

This is the **single canonical guide** for writing `TapMind.runStep(...)` prompts against the
real TapMind control-plane SDK, and for **generating suite-ready tests** from
`automation_plan.json`.

> **Not the same thing as `backend-test-code-generator`'s "TapMind NLP conventions".** That
> skill's `@Step("Given/When/Then ...")` annotations are Allure reporting labels on
> traditionally-written Java — they never call the real `TapMind.runStep(...)` SDK. This skill
> documents the actual SDK grammar and the generation → verify → run → suite-convert pipeline.

## Modes

| Mode | When | Output |
|---|---|---|
| **Reference** | Hand-writing / debugging one prompt | Corrected prompt string(s) using §§0–10 (rewrite grpcurl → §3.8). On `400 invalid_request_body`, apply §8.1.1 sparse-body checklist before blaming memory. |
| **Generate** | Given `automation_plan.json` (preferred) or `sdet_plan` steps | Ordered `prompts[]` per `scenario_id` |
| **Verify + run** | After generate, using backend MCP TapMind tools | Corrected `prompts[]` + per-step verdicts |
| **Suite convert** | After prompts are verified (and optionally run) | Java method with `@Test` / `@TestInfo` + `runStep`/`assertStep` lines |

Pipeline detail: `GENERATION.md`. Coverage / dedup: `NLP_COVERAGE.md`. Control plane:
`CONTROL_PLANE.md`. Grammar: §§0–10 below.

---

## Pipeline parity with coded GBT

NLP generation reuses the same upstream gates where they apply. Mapping:

| Coded skill | NLP equivalent |
|---|---|
| `dedup-generator` | Honour `is_dedup: true` on plan |
| `gbt-method-decision-maker` | `NLP_COVERAGE.md` → `nlp_method_decisions.json` |
| `gbt-test-code-generator` skip `exact_match` | Skip scenarios already covered by `TapMind.runStep` |
| `gbt-test-code-generator` approval gate | Scenario `status: approved` first (`NLP_COVERAGE.md`) |
| Module profile + Endpoint/Client/Controller | `module` (PDG) + `service_name` + plain-English prompts |
| `test-data-generator` payloads | `saveMemory` + `saved <key>` before steps |
| Compile + `test-code-validator` | MCP verify + optional execute + §8.1.1 body check |

Memgraph enrichment, assertion-helper edits, and data-provider row changes remain in the
coded path. NLP suite convert is **create** or **append-only** `runStep` lines per
`NLP_COVERAGE.md`.

---

## Control plane access (MCP + HTTP)

**Two MCP tools only** for verify and execute:

| MCP tool | Purpose |
|---|---|
| `tapmind_verify_prompt` | Correct / dry-run one prompt |
| `tapmind_run_nlp_command` | Run one prompt; reuse `conversationId` across steps |

Registry lookups (gRPC targets, static proto, REST targets) use **HTTP GET** to the control
plane — not additional MCP tools. Full host list, allowed Swagger controllers, and VPN
guidance: **`CONTROL_PLANE.md`**.

| Environment | Host |
|---|---|
| Integration | `tapmind-backend-i.golabs.io` |
| QA | `tapmind-backend-q.golabs.io` |

Swagger: `https://<host>/swagger-ui/index.html` — use **gRPC Targets**, **gRPC Static Proto**,
**target-registry-controller**, **verify-prompt-controller**, **nlp-command-controller**, and
**verify-schema-controller** only. Do **not** call ingest, database, or cache controllers.

On connectivity / `INTERNAL_ERROR` → tell the user to connect to the respective VPN and retry
(see `CONTROL_PLANE.md`).

---

## Intent vs tool routing (by protocol)

Prompt style depends on protocol. REST uses plain-English intent; gRPC, Redis, DB, and Kafka
use explicit tool-selector prefixes TapMind already routes.

```
REST:  plain-English intent → match ingested op → rest.invoke
gRPC:  §3.8 prefix → grpc.invoke (rpc_alias from GET /v1/grpc/targets)
Infra: §3.5 prefix → redis | db | kafka
```

| Protocol | Prompt style | Don't |
|---|---|---|
| REST / HTTP | §3.1 intent from `action` + `expected_result` | Mention ingest type ("OpenAPI…", "curl-ingested…") |
| gRPC | §3.8 `call mcp grpc grpc.invoke for rpc_alias: …` | Paste raw grpcurl dumps; guess `rpc_alias` from hostname |
| Redis / DB / Kafka | §3.5 exact prefix | Use §3.5 pattern for REST |
| Unknown / no registry entry | Flag `NEEDS_REVIEW` | Invent REST intent for a gRPC step |

**gRPC `rpc_alias`:** resolve before generating §3.8 prompts — `GET https://<host>/v1/grpc/targets`
(Swagger: gRPC Targets; host from `CONTROL_PLANE.md`), match grpcurl `host:port` to a registered
alias. Optional override: `# alias: <name>` as the first line of `curl_reference`. When
`reflection_enabled: false`, check `GET /v1/grpc/static-proto/aliases`. If lookup fails →
`NEEDS_REVIEW: no rpc_alias for <host>:<port>`. If HTTP fails → VPN message from
`CONTROL_PLANE.md`.

**gRPC verify/execute:** only via `tapmind_verify_prompt` and `tapmind_run_nlp_command` — never
direct `grpc_invoke` MCP. If execute returns `no tool_call.target`, check gRPC targets registry
over HTTP; target may be unregistered.

---

## G. Generation mode — automation suite → TapMind test

### G.1 Inputs (prefer `automation_plan.json`)

Per `automation_scenarios[]` entry, read:

| Need | Field |
|---|---|
| Identity | `scenario_id`, `description`, `requirement_ref` |
| Class / method | `package`, `test_class`, `method_name`, `test_layer` |
| Pinning | `module` (PDG), `service_name` |
| API | `endpoint`, scenario-level `curl_reference` (prefer over step curl — FIX-scoped) |
| gRPC alias | `GET /v1/grpc/targets` — match grpcurl host:port; or `# alias:` in curl |
| Steps | `step_descriptions[]` → `step`, `action`, `expected_result`, optional `curl_reference` |
| Fixtures | `test_data[].fixture_id`, `required_state`, later `response_fields_used` |
| Modifiers | `tags[]`, `execution_hints`, `is_dedup`, **`status`** / `approval_status` |
| Suite meta (when present in plan/context) | `groups`, `test_info` / `countryName`, `projectId`, `suiteId`, `testCaseIds`, `owner` |
| TDP (enriched plans) | `test_data[].test_data_output`, plan `test_data_payloads[]` |

**Generate only when** the scenario passes the approval gate in `NLP_COVERAGE.md` (`status:
"approved"` or equivalent). Skip all other scenarios — on enriched plans, TDP exists only for
approved rows. Plan-level `"status": "draft"` does not override per-scenario `"approved"`.

Skip when `is_dedup: true`, `nlp_method_decisions` says `exact_match`, failed approval/TDP
gates, or tags include `deferred` / `skip` / `manual`.

If suite meta is missing, leave `@TestInfo` fields as empty strings / empty arrays — do **not** invent BrowserStack/TestRail IDs.

### G.1.5 Coverage scan (before G.2)

Run **`NLP_COVERAGE.md`** on the target module test tree. Write `nlp_method_decisions.json`.
Do not generate prompts for `exact_match` scenarios. For `partial_match`, generate only delta
steps. Never overwrite a non-TapMind method that already occupies `method_name`.

### G.2 Generate all prompts first (no MCP)

For each scenario, emit an ordered `prompts[]` (one string per step) using the grammar in §§2–10:

0. If any step has a grpcurl `curl_reference`, `GET https://<control-plane-host>/v1/grpc/targets`
   once (per batch; host from `CONTROL_PLANE.md`) and build host:port → alias map. On HTTP
   failure → VPN message; do not guess aliases.
1. Prefer scenario-level `curl_reference` + `test_data` for placeholders (`{{FIX-xxx.field}}` → natural **`saved <field>`** after fixture / `saveMemory` bind — see §4).
2. Classify each step (generic — not domain-specific):
   - `curl_reference` starts with `grpcurl` → §3.8 gRPC invoke
   - non-empty HTTP curl → §3.1 API action `| verify: …`
   - Redis/Kafka/DB verbs + no curl → §3.5
   - re-check same resource (HTTP or gRPC), no new curl/request → §3.4 verify-only
   - wait/poll or e2e+reliability wait → §3.2 (must include fetch — §3.1 action or full §3.8)
   - stub/queue/log inspect with no TapMind grammar → omit from runnable prompts; flag `NEEDS_REVIEW`
3. First-touch vs repeat-touch by resource + step order (§3.4).
4. Track memory keys across the list — never invent a name not saved earlier. Reference bound keys as **`saved <key>`**, not `${memory.<key>}` (§4).
5. Unknown scalar vs array shape → flag; do not guess `save $.path` vs `entry where`.

Output shape after generate:

```json
{
  "scenario_id": "SC-…",
  "pdg": "<module>",
  "target_service_id": "<service_name>",
  "prompts": ["…", "…"],
  "flags": []
}
```

### G.3 Verify one prompt at a time, then run one-by-one

Use **only** MCP tools `tapmind_verify_prompt` and `tapmind_run_nlp_command` (see
`CONTROL_PLANE.md`). Do not use `grpc_invoke`, ingest, postgres, or redis MCP tools in this
pipeline.

**Verify (sequential):** `tapmind_verify_prompt` — one `prompt` string per call:

```json
{
  "prompt": "<prompts[i]>",
  "productGroup": "<module>",
  "targetServiceId": "<service_name>",
  "dryRunLlm": true
}
```

Apply that call's `corrected_test_prompt` / `corrected_verify_prompt` → update `prompts[i]` →
re-verify that prompt until clean or flag `NEEDS_REVIEW` (response `status:
"NEEDS_CLARIFICATION"` + `clarifying_question`). The response's `declared_bindings` also lists
the memory keys the planner actually resolved for that step (`saved <key>` / `${memory.x}`) —
cross-check against your own memory-key tracking (§4) rather than assuming.

> If a batch overload (`prompts: string[]`) is ever exposed on the MCP tool, prefer it — one
> call per scenario's full list lets the planner see the whole sequence + memory names at once,
> which catches cross-step issues that one-at-a-time verification can't.

**Execute (sequential):** `tapmind_run_nlp_command` — one prompt at a time. Reuse
`conversationId` from step 1 on steps 2…N.

If execute fails with `no tool_call.target` or missing gRPC routing → `GET /v1/grpc/targets` via
HTTP on the same environment host; flag `NEEDS_REVIEW` if alias/host is not registered.

Record corrections as `correctedSteps[]`: `{ n, text, change: "reworded"|"inserted", was, why }`.

### G.4 Suite convert — `@Test` / `@TestInfo` + step lines

After prompts are finalized (verified, and optionally executed), convert into a suite method.

**Annotation contract** (emit exactly this shape; fill from plan/suite meta):

```java
@Test(description = "<scenario description>", groups = {"<group>"})
@TestInfo(countryName = "<COUNTRY>", projectId = "<PROJECT>", suiteId = "<SUITE>", testCaseIds = {"<ID>"}, owner = "<email-or-empty>")
```

Example (from a validated suite scenario):

```java
@Test(description = "PAM 8 Levels catalogue presents monthly, yearly and special recognition (8 levels), not only monthly performance", groups = {"driverTest"})
@TestInfo(countryName = "INDONESIA", projectId = "MARKETPLACE_DRIVER_PLATFORM", suiteId = "DRIVER_APP_FRONTEND", testCaseIds = {"C5542965"}, owner = "")
```

**Field mapping**

| Annotation | Source |
|---|---|
| `@Test.description` | `description` (fallback: scenario name / `requirement_ref`) |
| `@Test.groups` | suite `groups` if present; else derive from `tags` / `test_layer` (e.g. `"driverTest"`, `"P0"`) — never invent product suite names |
| `@TestInfo.countryName` | suite / tasks context |
| `@TestInfo.projectId` | suite / tasks context |
| `@TestInfo.suiteId` | suite / tasks context |
| `@TestInfo.testCaseIds` | suite / BrowserStack / TestRail IDs when known; else `{}` |
| `@TestInfo.owner` | suite owner or `""` |
| method name | `method_name` |
| class / package | `test_class`, `package` |

**Method body conversion** (from finalized `prompts[]` + any MCP run corrections):

| Prompt role | Java line |
|---|---|
| Action / poll / tool | `TapMind.runStep("<prompt>");` or with pdg/service/polling overloads (§3.2, §3.6) |
| Final assertion focus | `TapMind.assertStep("<prompt>", "<failure message>");` when a custom message helps |
| Setup (secrets / fixtures) | `saveMemory(...)` / TDP resolve **before** prompts that need `saved <key>` |
| Inserted guards from run | Extra `runStep(...)` lines with `kind: guard` in the ledger |

Also emit machine form for reports / downstream generators (`tapmindTest`):

```json
{
  "className": "<test_class>",
  "methodName": "<method_name>",
  "package": "<package>",
  "description": "<@Test description>",
  "groups": ["\"<group>\""],
  "testInfo": {
    "countryName": "…",
    "projectId": "…",
    "suiteId": "…",
    "testCaseIds": ["…"],
    "owner": ""
  },
  "source": {
    "kind": "automation_plan",
    "scenarioRef": "<scenario_id>",
    "requirementRef": "<requirement_ref>"
  },
  "lines": [
    { "code": "TapMind.runStep(\"…\");", "kind": "step", "fromStep": 1 }
  ]
}
```

### G.5 Output contract (generation mode)

Return per scenario (not free-form prose):

1. `nlp_method_decisions` verdict (or reference to shared file)
2. `prompts[]` — ordered NLP strings (post-verify if MCP was used)
3. `correctedSteps[]` — if any rewrites/inserts
4. `tapmindTest` — suite metadata + convertible `lines[]` (`action`: `create` | `append`)
5. `skipped[]` at batch level — every filtered scenario with reason
6. Optional Java snippet: annotations + method signature + body lines

Consumers (`test-code-generator`, report skill) drop `lines[]` into the method body mechanically.

**Ingest (outside pipeline):** when verify returns no matching REST operation, flag
`NEEDS_REVIEW`. If the user explicitly asks to ingest, use MCP `tapmind_ingest_curl` (requires
`curl` + `promptExample` + `serviceId` + `productGroup`) or `tapmind_ingest_openapi`, then
re-run verify — never auto-ingest during generate.

---

## 0. What TapMind actually does (30-second version)

TapMind is a test SDK + backend service. Instead of writing Java/RestAssured code for every
API call, you write **one plain-English sentence** describing the action (and optionally what
to check), and pass it to `TapMind.runStep("...")`. Under the hood, TapMind:

1. Reads your sentence and figures out which API it maps to.
2. Calls that API for you.
3. Runs any checks you described (`verify: ...`).
4. Fails the test (like a normal assertion) if a check doesn't match.

You never write the HTTP call yourself — you only describe what should happen, in the exact
phrasing patterns below. **The phrasing matters** — TapMind is a planner, not a general
chatbot, so it only reliably understands the sentence shapes documented here.

## 1. Minimal setup (once per test class)

**PDG resolution (SDK `resolveAndSetUp`):** `PDG` **environment variable first**, then
`tapmind.pdg` system property as fallback. CI and Gradle test tasks should export
`PDG=<squad>` — do **not** set `System.setProperty("tapmind.pdg", …)` in `@BeforeMethod` when
`PDG` is already provided (the property is ignored in that case).

| Variable / property | Required | Role |
|---|---|---|
| `PDG` env | Yes (or property fallback) | Product group for control-plane routing |
| `INFRA` env | No | `integration`/`tencent` → integration env; else `qa` |
| `TAPMIND_CONTROL_PLANE_URL` env / `tapmind.control.plane.url` property | No | Override control-plane host |
| `TAPMIND_SERVICE_TOKEN` env / `tapmind.service.token` property | No | Service auth token |

```java
@BeforeMethod(alwaysRun = true)
public void beforeMethod(Method method) throws Exception {
    TapMind.setUp(method);
}
```

Local IDE only (when `PDG` env is unset): module `TapMindTestSupport.configure()` may set
`tapmind.pdg` as fallback — prefer exporting `PDG` in the run configuration instead.

Then, inside a `@Test` method, just call:

```java
TapMind.runStep("Get a customer from TDP");
```

### 1.1 Setup overloads

Both overloads call the same `resolveAndSetUp(testId)` and send `testId` to the control plane as
`test_session_name` (via `InitiateRequest`). This label is for TapMind run tracing only — it does
**not** wire BrowserStack execution; `@TestInfo(testCaseIds = …)` handles that separately.

| Overload | Session name shape | When to use |
|---|---|---|
| `TapMind.setUp(method)` | `<testMethodName>-<random5>` (e.g. `createOrderHappyPath-x7k2m`) | **Default** — use from `@BeforeMethod`; unique per invocation (parallel, retries, dataProvider rows) |
| `TapMind.setUp(String testId)` | literal `<testId>` you pass (e.g. `"12345678"`) | Optional — when you explicitly want TapMind logs grep-able by a fixed label (often a BrowserStack case id); avoid duplicating the same id already on `@TestInfo` unless traceability is the goal |

Examples above are **placeholders** — use your suite's real `@Test` method names and `@TestInfo`
`testCaseIds`; do not copy ids or method names from another module's tests.

**Mixed classes** (only some tests use TapMind): scope `@BeforeMethod` to the `TAPMIND` TestNG group:

```java
@BeforeMethod(alwaysRun = true, groups = {TestGroups.TAPMIND})
public void tapMindSetup(Method method) throws Exception {
    TapMind.setUp(method);
}
```

When every test in the class uses TapMind, a shared base class with that `@BeforeMethod` is fine.

### 1.2 When to use TapMind vs keep Java

| Good for NLP | Keep Java (or hybrid) |
|---|---|
| Single HTTP GET/POST with JSON envelope checks | Multi-step flows needing cross-step `save … as` memory (e.g. widget → progress → claim) |
| Strategy / auth / 404-style negative GETs | Numeric delta asserts (progress increased by N seconds) |
| Ingested curl/OpenAPI under your PDG | gRPC unary calls via §3.8 (resolve `rpc_alias` from `/v1/grpc/targets` first) |

### 1.3 `@TapmindAutoMode` (BrowserStack-driven)

`@TapmindAutoMode` fetches **BrowserStack Steps** and runs each as `TapMind.runStep(step)` — not the
`AI Prompt` column. Steps must be plain NLP sentences (§3.8 for gRPC — not raw grpcurl dumps),
JavaDoc, or `TapMind.runStep("…")` wrappers). Requires `@TestInfo` + `BROWSERSTACK_API_KEY`.

### 1.4 Verify-prompt API shape (control plane)

REST body for `POST /v1/runs/verifyPrompt` (MCP `tapmind_verify_prompt` wraps one prompt at a time):

```json
{
  "product_group": "<pdg>",
  "target_service_id": "<service_id>",
  "dry_run_llm": false,
  "prompts": [{ "prompt": "Get order details for order id 12345" }]
}
```

---

## 2. Quick reference: types of `runStep` calls

| # | Purpose | Phrasing / SDK signature | Example |
|---|---|---|---|
| 1 | Standard action + optional check | `runStep("<action> \| verify: <check>")` | `runStep("Get a customer from TDP");` |
| 2 | Poll until a state changes | `runStep(prompt, maxAttempts, intervalMs)` | `runStep("fetch booking ... verify status is confirmed", 5, 3000);` |
| 3 | Search a list & save a value | `save <field> from the <list> entry where <field> equals <value> as <var>` | `runStep("Get payment options with intent EWALLET_QR_COINS and save token from the payment_options entry where type equals GOPAY_WALLET as gopayWalletToken");` |
| 4 | Verify-only (reuse previous response) | Starts with `verify`/`assert`/`validate`/`check`/`expect` | `runStep("Verify booking status is CONFIRMED");` |
| 5 | Direct DB / Redis / Kafka call | `run query ...` / `run redis ...` / `produce to kafka ...` / `consume from kafka ...` | `runStep("Run redis GET 'driver:active_session:123'");` |
| 6 | Pin to a specific PDG / service | `runStep(prompt, pdg)` / `runStep(prompt, pdg, targetServiceId)` | `runStep("Get driver details", "transport-pdg", "driver-service");` |
| 7 | Assert with a custom failure message | `assertStep(prompt, failureMessage)` | `assertStep("Verify status is 200", "Order creation failed!");` |
| 8 | gRPC unary invoke | `call mcp grpc grpc.invoke for rpc_alias: … service: … Method: … request: …` | See §3.8 |

---

## 3. Detailed guide by call type

### 3.1 Standard action + optional inline check

```
<action description> | verify: <what to check>
```
```java
runStep("Get a customer from TDP");
runStep("Create a CASH booking | verify: status is 200 and $.order_number starts with 'RB-'");
```
> If there's no `verify` clause, the step still runs but asserts nothing — it will PASS even
> if the call errors. Only add `verify` when you actually want this step to fail on a bad
> response.

**Saving a plain top-level field (not inside a list):** just say `save $.path as <name>` — do
**not** use "entry where" here, that phrase is only for searching inside an array (§3.3).

```java
runStep("Get a customer from TDP and save $.data.customer_id as custId");
```

Match the phrasing to the actual data shape: scalar/top-level field → `save $.path as name`;
value inside a list → `entry where field equals value` (§3.3). Using the wrong one for the
shape you actually have is a common source of a prompt silently not parsing as intended.

### 3.2 Polling / retry (`runStep(prompt, maxAttempts, intervalMs)`)

Use for eventually-consistent state transitions (e.g. waiting for a booking to move from
`BOOKED` to `CONFIRMED`).

```java
runStep("fetch booking details for the saved order number using saved customer token and verify '$.body.booking.status' is confirmed", 5, 3000);
```
> **Must include the fetch action itself.** Do NOT poll a verify-only prompt like
> `"Verify status is X"` — verify-only prompts just re-judge the same frozen response from the
> previous step, so polling it repeats the same stale check instead of re-fetching.

### 3.3 Array search & save (`bind_select`)

Use this whenever the value you need lives *inside a list*, and you need to find the right
entry first — not a plain dotted path.

```
save <field to extract> from the <list name> entry where <filter field> equals <filter value> as <variable_name>
```

**`<list name>`** is the JSON array field name in the response (e.g. `payment_options`), not a
query-param name and not a full path like `data.payment_options`.

**Query / intent ≠ row filter.** If the call takes a query like `intent=EWALLET_QR_COINS`, that
value belongs only in the action clause. The `entry where <field> equals <value>` clause must use
the **response row field** (e.g. `type equals GOPAY_WALLET`). Never copy the intent/query value
into `where type equals …` — they are different fields and a wrong filter saves nothing (the step
may still PASS if there is no `verify:`).

```java
// Combined: call API with a query intent + save from a list by a different response field
runStep("Get payment options with intent EWALLET_QR_COINS, header User-ID: saved userId "
    + "and save token from the payment_options entry where type equals GOPAY_WALLET as gopayWalletToken",
    "gopay", "payment-options-service");

// Presence check + save (same response)
runStep("Verify payment_options contains type GOPAY_WALLET; save token from the payment_options entry where type equals GOPAY_WALLET as gopay_token");

// Filtering by a value saved earlier
runStep("save driver_name from the drivers entry where driver_id equals saved driverId as matched_driver_name");
```

**Nested (two-level) array search** — e.g. pick an estimate by `service_type`, then a payment
method inside it by `payment_method_type`:
```
"save the pricing_token from the estimates entry where service_type equals 1, then from its payment_methods entry where payment_method_type equals CASH"
```

> **Always use the phrase "entry where [field] equals [value]".** Don't write
> `payment_options.type` — TapMind needs the word **"entry"** to know you're searching a list.
> When the filter value is itself a saved variable, write `saved <variableName>` — never
> quote it as a literal string like `'paymentMethod'` (that searches for the literal text
> `paymentMethod`, not the value you saved, and silently returns nothing).

**Presence-only check** (confirm a match exists, without saving anything):
```java
runStep("verify payment_options contains an entry with type GOPAY_WALLET");
```

**Later steps** must reuse the exact `as <name>`:
```java
runStep("Set default payment option with body token as saved gopayWalletToken | verify: status is 200 and success is true",
    "gopay", "payment-options-service");
```

### 3.4 Verify-only steps (reuse the previous response, no re-fetch)

If a previous step already called an API and you only want to assert something on that same
response, start the prompt with one of these five words:

**`verify` / `assert` / `validate` / `check` / `expect`**

```java
runStep("Create a CASH booking");                                   // Step 1: makes the call
runStep("Verify the booking status is CONFIRMED and $.order_number is not null"); // Step 2: checks it, no new call
```
> The prompt **must start directly** with one of those 5 words. `"Please verify..."` or
> `"Can you check..."` will NOT be treated as verify-only — TapMind will plan it as a brand-new
> API call and may re-fetch (possibly getting different data).

### 3.5 Direct tool execution (DB / Redis / Kafka)

These skip the usual "which API is this" planning and go straight to the named tool. The
prompt must start with the exact prefix.

```java
runStep("Run query 'SELECT status FROM drivers WHERE driver_id = ''957378666''' on DB 'driver_service'");
runStep("Run redis GET 'driver:active_session:957378666'");
runStep("Produce to kafka topic 'driver-location-events' with key saved driverId and payload '{\"lat\": -6.2, \"long\": 106.8}'");
runStep("Consume from kafka topic 'order-status-events' where order_id equals saved orderNumber");
```

### 3.8 gRPC invoke (`grpc.invoke`)

gRPC steps use an explicit MCP tool prefix (like §3.5 for Redis/Kafka). Resolve `rpc_alias`
via HTTP `GET /v1/grpc/targets` on the control plane host (`CONTROL_PLANE.md`) before writing
the prompt. Verify and run the prompt only through `tapmind_verify_prompt` /
`tapmind_run_nlp_command` — not direct gRPC MCP.

**Template:**

```
call mcp grpc grpc.invoke for rpc_alias: <alias> service: <fq.service> Method: <Method> request: <json> [| verify: <checks>]
```

**grpcurl → prompt parsing:**

| grpcurl part | Prompt field |
|---|---|
| `-d '{…}'` or `-d @file` body | `request:` JSON object |
| Last arg `pkg.Service/Method` | `service:` + `Method:` |
| Host before service arg (`host:port`) | Lookup → `rpc_alias:` via `/v1/grpc/targets` |
| `# alias: name` first line in curl_reference | Use as `rpc_alias` (skip host lookup) |
| `-H 'key: value'` metadata | Fold into request or omit unless required |

**Example** — input grpcurl:

```bash
grpcurl -plaintext -d '{"user_id":"8427051","group_id":"1","task_ids":["2","4"]}' \
  grpc-gami-orbit-cgk.service.q.gojek.com:80 orbit.v1.RewardService/InitTaskProgress
```

Registered target `gami-orbit-grpc` → host `grpc-gami-orbit-cgk.service.q.gojek.com`, port `80`:

```java
runStep("call mcp grpc grpc.invoke for rpc_alias: gami-orbit-grpc service: orbit.v1.RewardService "
    + "Method: InitTaskProgress request: {\"user_id\":\"8427051\",\"group_id\":\"1\",\"task_ids\":[\"2\",\"4\"]} "
    + "| verify: status is OK");
```

With save (same rules as HTTP §3.1 / §3.3):

```java
runStep("call mcp grpc grpc.invoke for rpc_alias: gami-orbit-grpc service: orbit.v1.RewardService "
    + "Method: InitTaskProgress request: {\"user_id\":\"saved userId\",\"group_id\":\"1\",\"task_ids\":[\"2\",\"4\"]} "
    + "and save $.progress_id as progressId");
```

**After the invoke clause, HTTP rules apply unchanged:**

| Concern | gRPC behavior |
|---|---|
| Re-check same response | §3.4 verify-only (`Verify $.field is …`) |
| Poll until state changes | §3.2 — repeat full §3.8 fetch, not verify-only |
| Scalar save | `save $.path as name` in action clause |
| Array save | `entry where field equals value as name` (§3.3) |
| Later request fields | `saved key` in request JSON (§4) |
| Secrets | `saveMemory` first; never inline in request (§7) |

**Reference / correction mode:** rewrite raw grpcurl dumps, JavaDoc, or `TapMind.runStep("grpcurl …")`
wrappers into §3.8 format. Resolve `rpc_alias` via targets registry before emitting the fix.

### 3.6 Pin a step to a specific PDG / service

If TapMind resolves the wrong API for your prompt, or you know exactly which service it should
hit, pin it explicitly:

```java
TapMind.runStep(prompt, pdg);
TapMind.runStep(prompt, pdg, targetServiceId);
TapMind.runStep(prompt, pdg, targetServiceId, maxAttempts, intervalMs);
```
```java
runStep("Get customer profile", "transport-pdg");
runStep("Fetch driver location", "transport-pdg", "driver-tracking-service");
```

### 3.7 Assert with a custom failure message

`assertStep` wraps `runStep` — if the step fails, you get a clean assertion message instead of
a generic error.

```java
TapMind.assertStep(prompt, failureMessage);
TapMind.assertStep(prompt, pdg, failureMessage);
```
```java
assertStep("Verify order created successfully with 200 code and $.order_number starts with 'RB-'",
           "Booking creation failed or returned an invalid order number!");
```

---

## 4. Memory: saving and reusing values

Every value you `save ... as <name>` in a prompt is stored in memory for later steps, or from
plain Java:

```java
saveMemory("bookingId", "BK-100234");
saveMemory("localeTemplateName", templateName + "_default");
String bookingId = TapMind.getValueFromMemory("bookingId");
String bookingId = TapMind.getValueFromMemory("bookingId", "defaultIfMissing");
```

**Preferred reference form (generation + hand-writes):** use the natural-language
**`saved <exactKey>`** phrasing — not `${memory.<exactKey>}`.

The planner compiles `saved <key>` → `${memory.<key>}` internally. Same bound key, clearer
NLP. Works for values saved via prior `save … as <key>` **or** Java `saveMemory("<key>", …)`.

| Prefer (generation) | Also valid (SDK / older tests) |
|---|---|
| `… default = saved localeTemplateName …` | `… default = ${memory.localeTemplateName} …` |
| `… name = saved localeTemplateName …` | `… name = ${memory.localeTemplateName} …` |
| `… token as saved gopayWalletToken …` | `… token as ${memory.gopayWalletToken} …` |
| `… where type equals saved paymentMethod …` | `… where type equals ${memory.paymentMethod} …` |
| `… using saved customer token …` | `… using ${memory.customerToken} …` |
| `… from the saved estimateAmount …` | `… from ${memory.estimateAmount} …` |

```java
// After saveMemory("localeTemplateName", …) / saveMemory("whatsappAuth", …):
runStep(
    "Create a whatsapp template with template_name = saved templateName, "
        + "templates array having exactly one object with channel = whatsapp "
        + "and default = saved localeTemplateName and without the id and en fields, "
        + "and whatsapp_templates array having exactly one object with "
        + "name = saved localeTemplateName, category = UTILITY and language = id, "
        + "with header Authorization: saved whatsappAuth",
    "communication-platform", "notification-gateway");
```

Always use the **exact** `as <name>` / `saveMemory` key. A guessed name won't match
`available_memory_keys` and fails at plan time. Do **not** invent keys; do **not** mix a
wrong spelling (`locale_template_name` vs `localeTemplateName`).

---

## 5. TDP fixture calls ("Get a customer/driver from TDP")

For TDP fixture steps, TapMind's response only actually contains `accessToken` and
`customerId`/`driverId`. **Only assert on those two fields.** Asserting anything else (e.g.
`vehicle_type`) fails with a vague `NEEDS_REVIEW` instead of a clean failure, because that
field was never in the response to begin with.

---

## 6. "One of" multiple allowed values

If a field can legitimately be one of several values, group them into a single check —
never write it as separate `verify` clauses for the same field (those get ANDed together and
will always fail, since a field can't equal two things at once).

```java
// Wrong — always fails
runStep("verify status is ACTIVE and verify status is PENDING");

// Right
runStep("verify status is one of ACTIVE, PENDING, or COMPLETED");
```

---

## 7. Handling secrets (auth tokens, client secrets, etc.)

API specs never store secrets. If an API needs one, fetch and save it in Java **first**, then
reference it in the prompt as **`saved <key>`** — never paste the raw secret into the prompt
string itself.

```java
saveMemory("clientSecret", System.getenv("SOME_SECRET_ENV_VAR")); // TODO: load from your actual secrets source, don't hardcode
runStep("Hit login methods api with phone_number +628210274599, country_code 62 and header X-ClientSecret as saved clientSecret");
```

---

## 8. Editing request shape inline (headers / query params)

You can tweak the request for a single call directly in the prompt — no need to touch the API
spec:

```java
runStep("Hit get order api without any order_number param");                       // drop a query param
runStep("Hit estimate api with token as customer_token and header X-AppVersion:4.78.0"); // add/override a header
runStep("Hit estimate api with only header 'X-AppVersion'");                        // send ONLY this header (drops the rest)
```

### 8.1 Overriding nested / cross-referenced array fields in the body

Some endpoints need the same value written to several nested fields at once — e.g. an
array of objects, or fields that cross-reference each other by id/name across different
parts of the body. Describing the intent with one generic field name (e.g. "template_name")
only overrides a field with that *exact* key. It will NOT propagate into nested/array
fields that use a different key name, even if they logically hold "the same" value — those
fields silently fall back to the spec's example values instead of failing.

**How to spot it:** after running, check the executor log for a line like:
`references identifier(s) [...] that are not defined by any 'name'/'id' entry elsewhere
in the request body — likely a partially filled array`. That WARN means your override
landed on the wrong field, and the fields that actually needed the value are still using
spec examples.

**Fix:** don't rely on one generic field name — name the exact JSON key path for every
field that must carry the value:

```
Create <resource> with <arrayA>[<idx>].<key> = saved value, <arrayB>[<idx>].<key> = saved value, ...
```

(e.g. for a create-template endpoint where `templates[0].id/en/default` must all match a
`name` inside `whatsapp_templates[]`, set those paths **and** required siblings such as
`templates[0].channel = whatsapp` — see §8.1.1 — rather than saying only "template_name = ...".)

This indexed-path override isn't a formally documented grammar feature (unlike header/query
param edits above) — it works because the planner matches literal key names. Always verify
against the executor log after running; don't assume it took effect.

#### 8.1.1 Sparse body trap (indexed overrides drop required siblings)

Naming only the fields you care about (`templates[0].id = …`, `templates[0].en = …`) can
make the planner emit a **sparse** array element that contains **only those keys**. Spec
`body_defaults` merge is **not guaranteed** — required sibling fields the prompt never named
(e.g. `channel`, `category`, `language`, `components`) may be omitted entirely.

**How to spot it (Reference / debug mode):**

1. Read the executed **Request Body** (SDK console / control-plane `HttpToolInvoker` log).
2. If the array object has only the overridden keys — e.g.
   `templates:[{id,en,default}]` with no `channel`, or
   `whatsapp_templates:[{name},{name}]` with no `category`/`language`/`components` —
   this is a sparse-body failure, **not** a memory / auth / routing bug.
3. Match the API error to the missing key:
   - `400 missing channel` → `templates[i].channel` absent
   - `400 invalid default template` → `templates[i].default` absent or points at a name
     with no matching `whatsapp_templates[].name`
   - `400` / schema errors on incomplete `whatsapp_templates[]` → only `.name` was set

**Fix (prefer in this order):**

1. **Whole-object phrasing** (keeps body_defaults merge more often):
   ```
   templates array having exactly one object with channel = whatsapp
   and id = saved idTemplateName and en = saved enTemplateName
   and default = saved defaultTemplateName
   ```
2. **If you must use indexed paths**, name **every required field** on that object —
   including constants, not only `saved …` values:
   ```
   templates[0].channel = whatsapp,
   templates[0].id = saved idTemplateName,
   templates[0].en = saved enTemplateName,
   templates[0].default = saved defaultTemplateName,
   …
   ```
3. After a create `400 invalid_request_body`, **do not** blame `saved <key>` first —
   diff the request body against required schema fields; sparse indexed overrides are the
   primary suspect.

**WhatsApp create checklist** (notification-gateway `/v1/template-management/create`):

| Must be present | Typical miss when prompt only sets |
|---|---|
| `templates[0].channel = whatsapp` | `templates[0].id/en/default = saved …` |
| `templates[0].default` = a name that exists in `whatsapp_templates[].name` | EN-only create that sets `en` but omits `default` |
| Each `whatsapp_templates[i]` has `name` (+ defaults for category/language/components) | `whatsapp_templates[i].name = saved …` only → skeleton `{name}` rows |

`tapmind_verify_prompt` alone often **cannot** catch this — it checks planner shape, not
whether body_defaults will merge at execute time. Always inspect the live request body after
`tapmind_run_nlp_command` / a real run when create returns `invalid_request_body`.

---

## 9. Response schema validation

Two independent mechanisms — know which one applies to your API:

1. **Automatic** — only for APIs ingested from an OpenAPI/Swagger spec. You don't write
   anything; schema validation runs on its own. Does **not** apply to curl-ingested APIs.
2. **Explicit (works for any API)** — bring your own JSON Schema file and call it directly:
   ```java
   TapMind.verifySchema("src/test/resources/schemas/booking-response.schema.json", TapMind.getLastResponseBody());
   ```
   Throws an `AssertionError` with the exact violations if the response doesn't match.

---

## 10. Common mistakes to avoid

| Don't write | Write instead | Why |
|---|---|---|
| `data.payment_options.type equals GOPAY` | `payment_options entry where type equals GOPAY` | TapMind needs the word **"entry"** to know it's searching a list. |
| `... with intent EWALLET_QR_COINS ... where type equals EWALLET_QR_COINS` | `... with intent EWALLET_QR_COINS ... where type equals GOPAY_WALLET` | **Query intent ≠ response `type`.** Intent is a request query; `type` is a field on each list row. Reusing the intent value in `where` matches no rows and saves nothing. |
| `where type equals GOPAY_WALLET` but later `${memory.gopay_token}` when you saved `as gopayWalletToken` | Use the exact `as <name>` everywhere | Memory keys are exact; a different spelling is unbound. |
| `verify state is A and state is B` | `verify state is one of A, B` | Separate checks are ANDed — always fails for a single field. |
| Guessed variable name, e.g. `as customerToken` when you never saved it | The exact name used in the earlier `save ... as <name>` | Hallucinated names won't match what was actually stored. |
| `${memory.localeTemplateName}` after `saveMemory("localeTemplateName", …)` in **generated** prompts | `saved localeTemplateName` (or `as saved …` / `equals saved …`) | Preferred NLP form; planner expands `saved X` → `${memory.X}`. `${memory.x}` still works but is not the generation default. |
| `[?(@.type=='paymentMethod')]` (quoting a variable name as a literal) | `entry where type equals saved paymentMethod` | Quoting filters for that literal text, not the saved value — matches nothing, silently saves empty. |
| `"Please verify status is 200"` after an earlier fetch | `"Verify status is 200"` | Only prompts that **start with** verify/assert/validate/check/expect are verify-only; extra words in front cause a needless re-fetch. |
| `runStep("Verify status is 200", 5, 2000)` (polling a verify-only prompt) | `runStep("fetch order details ... and verify status is 200", 5, 2000)` | Verify-only prompts don't re-fetch, so polling just re-checks the same stale response. |
| Asserting `vehicle_type` on a "Get a customer/driver from TDP" step | Only assert `accessToken` / `customerId` / `driverId` | Other fields aren't in the TDP response — see §5. |
| Pasting a raw secret into the prompt string | `saveMemory(...)` first, then `saved <key>` in the prompt | See §7. |
| Loading strict assertions onto a shared setup step (e.g. a "create booking" step other scenarios also reuse as a precondition) | Keep setup steps assertion-free (or a bare `status is 200`); put the detailed checks in the dedicated verify-only step for that specific scenario | Over-asserting a shared step breaks reuse by other scenarios (e.g. negative tests) that need that same step's evidence to look different. |
| `data.whatsapp_templates.provider is X` (dotted path into a list) | `whatsapp_templates contains an entry with provider X` | Same "entry" rule as above — a scalar dotted path can't reach into a list. |
| One generic field name (e.g. "template_name = X") when the schema actually needs the value on several nested/cross-referenced fields | Name each real field path explicitly: `arrayA[0].key = X, arrayB[1].key = X, ...` | A generic/wrapper field name only overrides an exact key match — nested or cross-referenced fields with different key names silently keep spec-example defaults instead of erroring. See §8.1. |
| `templates[0].id/en/default = saved …` without `templates[0].channel = whatsapp` (or equivalent required siblings) | Whole-object phrasing **or** name every required field including constants — see §8.1.1 | Indexed overrides can emit a **sparse** object; body_defaults may not fill `channel` / category / components → API `400 missing channel` (or similar). |
| Blaming `saved <key>` / memory when create returns `invalid_request_body` | Diff request body vs required schema fields first (§8.1.1) | Memory substitution often worked; the body is simply missing required keys the prompt never named. |
| Relying on `tapmind_verify_prompt` PASS as proof the create body is complete | Run once and inspect Request Body / curl in the log | Verify checks planner routing; sparse body_defaults merge only shows up at execute time. |
| Raw grpcurl command as the prompt | §3.8 `call mcp grpc grpc.invoke for rpc_alias: …` | Planner expects structured gRPC grammar, not a shell grpcurl line. |
| Guessing `rpc_alias` from hostname substring | Lookup `GET /v1/grpc/targets` by host:port | Unregistered alias fails at invoke time. |
