---
name: backend-tapmind-nlp-prompts
description: >-
  Write, fix, or generate real TapMind NLP test-step prompts —
  `TapMind.runStep(...)` / `TapMind.assertStep(...)` — and convert
  automation_plan scenarios into suite-ready Java tests with @Test /
  @TestInfo. Use when the user is writing/debugging a TapMind prompt,
  mentions TapMind / runStep / assertStep / bind_select / "entry where" /
  verify-only steps / grpc / grpcurl / grpc.invoke / rpc_alias, OR when given
  automation_plan.json, existing Java tests, BrowserStack test-case steps, a test-case sheet,
  or sdet_plan step_descriptions to generate prompts, batch-verify them,
  run steps via MCP, and emit corrected suite test methods. Also use when
  converting BrowserStack / source-file test cases to NLP, rewriting vague
  saves like "save basetoken from response" into JSONPath form
  (`save $.data.base_token as basetoken`) via /v1/db/preview +
  tapmind_verify_prompt declared_bindings — see TESTCASE_TO_NLP.md.
  Two intake paths (plan vs code/test-case) merge into one shared NLP core — see §G.
  Before generating, scan for existing TapMind.runStep tests
  (NLP_COVERAGE.md) so only missing scenarios are emitted.
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
| **Reference** | Hand-writing / debugging one prompt | Corrected prompt string(s) using §§0–10 (rewrite grpcurl → §3.8). On `400 invalid_request_body`, apply §8.1.1 sparse-body checklist before blaming memory. Artifact path §G.A.2 — no plan approval gate. |
| **TC → NLP** | BrowserStack case or source-file steps (often path-less saves) | Path-enriched `prompts[]` via `TESTCASE_TO_NLP.md`, then §G.B |
| **Generate** | Plan (`automation_plan.json`) **or** artifact (Java / BS steps / `sdet_plan`) | Ordered `prompts[]` per scenario or target method |
| **Verify + run** | After generate — **both paths** | Corrected `prompts[]` + per-step verdicts via MCP |
| **Suite convert** | After prompts verified (and optionally run) — **both paths** | Java method with `@Test` / `@TestInfo` + `runStep`/`assertStep` lines |

**Intake paths:** §G.A (reference + TDP differ) → **shared core** §G.B (coverage, grammar,
registry, MCP, suite convert). Detail: `GENERATION.md`. Coverage: `NLP_COVERAGE.md`.
Fixture reuse: `FIXTURE_REUSE.md`. Control plane: `CONTROL_PLANE.md`.
Test-case / BS path enrichment: **`TESTCASE_TO_NLP.md`**. Grammar: §§0–10 below.

---

## Pipeline parity with coded GBT

NLP generation reuses the same upstream gates where they apply. Mapping:

| Coded skill | NLP equivalent |
|---|---|
| `dedup-generator` | Honour `is_dedup: true` on plan |
| `gbt-method-decision-maker` | `NLP_COVERAGE.md` → `nlp_method_decisions.json` |
| `gbt-test-code-generator` skip `exact_match` | Skip scenarios already covered by `TapMind.runStep` |
| `gbt-test-code-generator` approval gate | Plan path only — scenario `status: approved` (`NLP_COVERAGE.md`) |
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

## G. Generation mode — two intake paths, one NLP core

### G.0 Path overview

```
                    ┌─ Plan-driven (§G.A.1) ── approval + enriched TDP
  Intake (varies) ──┤
                    └─ Artifact-driven (§G.A.2) ── infer TDP from code/steps

                              ▼ merge

  Shared core (§G.B) ── coverage scan → prompts → registry/Swagger → MCP verify/run → suite convert
```

| Stage | Plan-driven | Artifact-driven |
|---|---|---|
| **Reference** | `automation_plan.json` — `scenario_id`, `step_descriptions`, fixtures | Existing `@Test`, BrowserStack steps, RestAssured/setup, or single prompt |
| **TDP** | `test_buddy_prompt` / `test_data_output`; skip `tdp_not_ready` | Infer from setup/helpers/curl; `NEEDS_REVIEW` if `saved <key>` unresolved |
| **Approval** | `status: approved` or `run.json` `keep` | User intent — no plan status gate |
| **Coverage scan** | Same — `NLP_COVERAGE.md` | Same |
| **Prompt grammar** | Same — §§2–10 | Same |
| **Registry / Swagger** | Same — `CONTROL_PLANE.md` | Same |
| **MCP verify + run** | Same | Same |
| **Suite convert** | Same — `FIXTURE_REUSE.md` | Same — preserve existing `@TestInfo` when migrating |

---

### G.A Intake (varies by path)

#### G.A.1 Plan-driven — `automation_plan.json`

Per `automation_scenarios[]` entry, read:

| Need | Field |
|---|---|
| Identity | `scenario_id`, `description`, `requirement_ref` |
| Class / method | `package`, `test_class`, `method_name`, `test_layer` |
| Pinning | `module` (PDG), `service_name` |
| API | `endpoint`, scenario-level `curl_reference` (prefer over step curl — FIX-scoped) |
| gRPC alias | `GET /v1/grpc/targets` — match grpcurl host:port; or `# alias:` in curl |
| Steps | `step_descriptions[]` → `step`, `action`, `expected_result`, optional `curl_reference` |
| Fixtures | `test_data[].fixture_id`, `required_state`, `response_fields_used` |
| Modifiers | `tags[]`, `execution_hints`, `is_dedup`, **`status`** / `approval_status` |
| Suite meta | `existing_testcase_ids[]` + `browserstack_test_id` — both propagated from `sdet_plan`, often empty/null pre-sync. No `countryName`/`projectId`/`suiteId`/`owner`/`groups` field exists on the plan. |
| TDP (enriched) | `test_data[].test_data_output`, plan `test_data_payloads[]` |

**Gates (plan only):** generate only when `status: "approved"` (or `run.json` `keep`). Skip
`draft`, `tdp_not_ready`, `is_dedup`, plan tags `deferred` / `skip` / `manual`. Plan-level
`"status": "draft"` does **not** override per-scenario `"approved"`. See `NLP_COVERAGE.md`.

**TDP:** use `test_buddy_prompt` from `test_data_output` when present; prefer
`TDP_SUPPORTED`; `TDP_OPERATION_FALLBACK` may run with `NEEDS_REVIEW` on primary fixtures.
Skip when `{{FIX-…}}` is unresolved (`tdp_not_ready`).

Set `tapmindTest.source.kind` → `"automation_plan"`.

If suite meta is missing, leave `@TestInfo` empty — do **not** invent BrowserStack/TestRail IDs.

#### G.A.2 Artifact-driven — code / test case / reference

Use when the user points at an **existing test**, **BrowserStack case**, a **test-case sheet**
(e.g. `sdet_testcases.csv` — `Id`/`Title`/`Preconditions`/`Steps`/`Expected Result` columns,
same shape as a BrowserStack case pre-upload), **`sdet_plan` steps without enrichment**, or a
**single prompt** to fix — not a batch from an enriched plan.

**Path enrichment (required for BS / sheet / vague saves):** follow **`TESTCASE_TO_NLP.md`**
before §G.B — fetch cases from file or BrowserStack MCP, detect path-less language
(`save basetoken from response`), resolve JSONPath via `POST /v1/db/preview` +
`tapmind_verify_prompt` `declared_bindings`, emit `save $.data.base_token as basetoken`.

| Need | Source |
|---|---|
| Target method | User path, `@TestInfo.testCaseIds`, or class#method |
| Steps | Normalize to `action` + `expected_result`: RestAssured calls, `@Step`, BS step text, sheet `Steps`/`Expected Result` columns (1:1 numbered), or prompt under edit — then **`TESTCASE_TO_NLP.md`** |
| Setup / TDP | `@BeforeMethod`, helpers, `CustomerHelper`, inline tokens, curl `Authorization`, sheet `Preconditions` column |
| Pinning | Existing `runStep(..., pdg, service)`, test package/module, or user |
| Suite meta | **Preserve** from existing class when migrating — do not overwrite known `@TestInfo` |
| Coded coverage | Existing non-TapMind `@Test` on same endpoint — primary signal for migration |

**No plan approval gate.** User request = intent to generate / convert / fix.

**TDP inference (artifact path):**

| Signal | Action |
|---|---|
| Step/curl needs bearer token or entity id | Add TDP `runStep` or call existing `*TapMindTestBase` helper |
| Existing Java setup provisions data | Convert to helper + TDP `runStep`, or keep `saveMemory(env)` (§7) |
| `saved <key>` referenced with no prior save in method/base | Flag `NEEDS_REVIEW: unresolved_data_dependency` — do not invent ids |
| Hardcoded token/id in coded test | Flag `NEEDS_REVIEW: migrate_to_tdp` — §7 |
| Enriched `test_buddy_prompt` available (hybrid) | May reuse buddy prompt even without plan batch |

**Normalize coded tests before §G.B:** extract HTTP/gRPC calls → action prompts; Java/AssertJ
asserts → separate §3.4 verify-only prompts (§3.1.1); shared setup → helper candidates (`FIXTURE_REUSE.md`).

Set `tapmindTest.source.kind` → `"coded_migration"` | `"browserstack_case"` | `"reference"` |
`"sdet_plan"`.

**Reference mode** (one prompt): apply §§0–10 + MCP verify if asked; add TDP only when the
prompt references unsaved memory keys.

#### G.A.3 Upstream prerequisites (by path)

| Skill | Plan-driven | Artifact-driven |
|---|---|---|
| `dedup-generator` | Yes — honour `is_dedup` | No |
| `test-data-generator` + payloads | When plan has `{{FIX-…}}` | Optional — runtime TDP via `runStep` |
| `run.json` / approval | Yes for batch suite write | No — explicit user intent |
| Read target Java file | Optional (coverage) | **Yes** when migrating coded test |
| `gbt-method-decision-maker` | **Yes, primary** — reuse `method_decisions.json` (`NLP_COVERAGE.md`) | Useful — detect coded `exact_match` |

---

### G.B Shared NLP core (both paths)

#### G.B.1 Coverage scan (before prompt generate)

Run **`NLP_COVERAGE.md`** on the target module test tree. Write `nlp_method_decisions.json`.

**Lookup anchors** (path-specific, scan logic same):

| Path | Primary keys |
|---|---|
| Plan | `scenario_id`, plan `method_name`, plan `existing_testcase_ids[]` / `browserstack_test_id` |
| Artifact | `@TestInfo.testCaseIds`, existing method name, endpoint from coded test |

Do not generate for `exact_match`. For `partial_match`, delta steps only. Never overwrite a
non-TapMind method that occupies `method_name`. Flag `NEEDS_REVIEW: coded_coverage_exists` when
migrating and coded test already covers the scenario.

#### G.B.2 Generate all prompts first (no MCP)

For each accepted target, emit ordered `prompts[]` using grammar §§2–10:

0. If any step has grpcurl `curl_reference`, `GET …/v1/grpc/targets` once per batch
   (`CONTROL_PLANE.md`). On HTTP failure → VPN message; do not guess aliases.
1. Resolve placeholders: plan `{{FIX-xxx.field}}` → **`saved <field>`** after TDP/helper bind;
   artifact path → same after inferred setup (§4).
2. Classify each step and **split execute vs verify** (§3.1.1 — default for generation):
   - grpcurl → §3.8 action prompt (optional bare success `| verify: status is OK` only)
   - HTTP curl / clear HTTP action → §3.1 action (+ optional bare success `| verify: HTTP 2xx`)
   - Then **one** §3.4 verify-only prompt with all detail asserts from `expected_result`
   - Redis/Kafka/DB → §3.5
   - Same resource re-check (already fetched) → §3.4 only (still one prompt)
   - wait/poll → §3.2 (must include fetch; keep poll assert on the fetch prompt)
   - no TapMind grammar → omit; flag `NEEDS_REVIEW`
3. First-touch vs repeat-touch (§3.4).
4. Track memory keys — **`saved <key>`**, not `${memory.<key>}` (§4).
5. Unknown scalar vs array → flag; do not guess `save $.path` vs `entry where`.
   Path-less saves from BS/sheet → resolve via **`TESTCASE_TO_NLP.md`** (`declared_bindings`)
   before emitting; never leave `save <field> from response` in `prompts[]`.
6. **Do not** emit `action | verify: status + full body fields…` mega-prompts.
7. **Do not** emit multiple consecutive verify-only prompts after one execute — see §3.1.1.

Output shape:

```json
{
  "scenario_id": "SC-…",
  "pdg": "<module>",
  "target_service_id": "<service_name>",
  "prompts": ["…", "…"],
  "flags": []
}
```

(`scenario_id` optional on artifact path — use method name or testCaseId as manifest key.)

#### G.B.3 Verify one prompt at a time, then run one-by-one

Use **only** MCP `tapmind_verify_prompt` and `tapmind_run_nlp_command` (`CONTROL_PLANE.md`).
Do not use `grpc_invoke`, ingest, postgres, or redis MCP in this pipeline.

**Verify (sequential):** one prompt per call:

```json
{
  "prompt": "<prompts[i]>",
  "productGroup": "<module>",
  "targetServiceId": "<service_name>",
  "dryRunLlm": true
}
```

Apply `corrected_test_prompt` / `corrected_verify_prompt` → re-verify until clean or
`NEEDS_REVIEW`. Cross-check `declared_bindings` against memory-key tracking (§4).

**Execute (sequential):** `tapmind_run_nlp_command` — reuse `conversationId` from step 1.

If `no tool_call.target` → `GET /v1/grpc/targets`; flag `NEEDS_REVIEW` if unregistered.
If REST verify shows no matching op → `NEEDS_REVIEW` — check `GET /v1/targets`; ingest only
when user explicitly asks.

Record `correctedSteps[]`: `{ n, text, change: "reworded"|"inserted", was, why }`.

#### G.B.4 Suite convert — `@Test` / `@TestInfo` + step lines

After prompts are finalized (verified, optionally executed), convert to a suite method.

**Annotation contract:**

```java
@Test(description = "<scenario description>", groups = {"<group>"})
@TestInfo(countryName = "<COUNTRY>", projectId = "<PROJECT>", suiteId = "<SUITE>", testCaseIds = {"<ID>"}, owner = "<email-or-empty>")
```

**Field mapping**

| Annotation | Plan-driven source | Artifact-driven source |
|---|---|---|
| `@Test.description` | `description` / `requirement_ref` | Preserve existing or derive from test intent |
| `@Test.groups` | `tags[]` / `test_layer` (no plan `groups` field) | Preserve existing groups |
| `@TestInfo.testCaseIds` | `existing_testcase_ids[]` + `browserstack_test_id` (often empty/null pre-sync) | Preserve existing `@TestInfo.testCaseIds` |
| `@TestInfo.countryName` / `projectId` / `suiteId` / `owner` | No plan field — leave empty, do not invent | **Preserve** from existing class when present |
| method name | `method_name` | Existing method name when migrating |
| class / package | `test_class`, `package` | Existing class when migrating |

**Method body conversion**

| Prompt role | Java line |
|---|---|
| Action / poll / tool | `TapMind.runStep("…");` or pdg/service/polling overloads |
| Final assertion | `TapMind.assertStep("…", "…");` when helpful |
| Setup / repeated steps | `provision…()` / `create…()` / `fetch…()` on `*TapMindTestBase` |
| Inserted guards | Extra `runStep(...)` with `kind: guard` |

Machine form (`tapmindTest`):

```json
{
  "className": "<test_class>",
  "methodName": "<method_name>",
  "source": {
    "kind": "automation_plan | coded_migration | browserstack_case | reference | sdet_plan",
    "scenarioRef": "<scenario_id or testCaseId>",
    "requirementRef": "<requirement_ref or empty>"
  },
  "lines": [
    { "code": "TapMind.runStep(\"…\");", "kind": "step", "fromStep": 1 },
    { "code": "provisionHostNoGroupAndGroupOrderMerchant();", "kind": "helper-call" }
  ]
}
```

#### G.B.5 Output contract

Return per target (not free-form prose):

1. `nlp_method_decisions` verdict (or ref to shared file)
2. `prompts[]` — post-verify if MCP used
3. `correctedSteps[]` — if any rewrites
4. `tapmindTest` — metadata + `lines[]` (`action`: `create` | `append`)
5. `skipped[]` — every filtered scenario/target with reason
6. Optional Java snippet

**Ingest (outside pipeline, both paths):** flag `NEEDS_REVIEW` when verify shows no REST op.
Ingest only on explicit user request (`tapmind_ingest_curl` / `tapmind_ingest_openapi`).

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

### 1.5 Shared step helpers (reuse common patterns)

Do **not** paste the same `runStep` into every `@Test` — TDP fixtures **or any repeated
step** (auth headers, create session, fetch details, gRPC preamble). Extract to **`protected`
methods on the module `*TapMindTestBase`**. Details: **`FIXTURE_REUSE.md`** (step & fixture reuse).

```java
provisionDefaultCustomer();
createGroupOrderSessionEveryonPaysEqually();
TapMind.runStep("Verify social_group is absent …");  // scenario-specific only
```

Suite convert: fingerprint prompts across the batch; emit `sharedHelpers[]` + `helper-call`
lines for duplicates and shared prefixes — not repeated strings per method.

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
| 1 | Standard action (execute) | `runStep("<action>")` — saves OK; optional bare success `| verify: HTTP 2xx` | `runStep("Create a CASH booking and save $.order_number as orderNumber \| verify: HTTP 2xx");` |
| 1b | Detail asserts (verify-only) | **One** `runStep("Verify …")` on prior execute evidence | All body/field checks in that single prompt |
| 2 | Poll until a state changes | `runStep(prompt, maxAttempts, intervalMs)` | `runStep("fetch booking ... verify status is confirmed", 5, 3000);` |
| 3 | Search a list & save a value | `save <field> from the <list> entry where <field> equals <value> as <var>` | `runStep("Get payment options … and save token from the payment_options entry where type equals GOPAY_WALLET as gopayWalletToken");` |
| 4 | Verify-only (reuse previous response) | Starts with `verify`/`assert`/`validate`/`check`/`expect` | `runStep("Verify booking status is CONFIRMED and $.order_number is not null");` |
| 5 | Direct DB / Redis / Kafka call | `run query ...` / `run redis ...` / `produce to kafka ...` / `consume from kafka ...` | `runStep("Run redis GET 'driver:active_session:123'");` |
| 6 | Pin to a specific PDG / service | `runStep(prompt, pdg)` / `runStep(prompt, pdg, targetServiceId)` | `runStep("Get driver details", "transport-pdg", "driver-service");` |
| 7 | Assert with a custom failure message | `assertStep(prompt, failureMessage)` | `assertStep("Verify status is 200", "Order creation failed!");` |
| 8 | gRPC unary invoke | `call mcp grpc grpc.invoke for rpc_alias: … service: … Method: … request: …` | See §3.8 |

---

## 3. Detailed guide by call type

### 3.1 Standard action (execute)

```
<action description> [and save $.path as <name>] [| verify: HTTP 2xx]
```
```java
runStep("Get a customer from TDP");
runStep("Create a CASH booking and save $.order_number as orderNumber | verify: HTTP 2xx");
```

**Generation default:** keep detailed body/schema asserts **off** the action line — use §3.1.1.
Optional bare success on the action (`| verify: HTTP 2xx` / `status is 200` / gRPC `status is OK`)
is allowed so the success check shares the same run as the execute evidence.

> An action with **no** success `| verify:` and **no** following verify-only prompt asserts
> nothing — the call can error and the step still PASS.

**Saving a plain top-level field (not inside a list):** just say `save $.path as <name>` — do
**not** use "entry where" here, that phrase is only for searching inside an array (§3.3).

```java
runStep("Get a customer from TDP and save $.data.customer_id as custId");
```

Match the phrasing to the actual data shape: scalar/top-level field → `save $.path as name`;
value inside a list → `entry where field equals value` (§3.3). Using the wrong one for the
shape you actually have is a common source of a prompt silently not parsing as intended.

### 3.1.1 Split execute vs detail verify (required for generation)

Control plane (`SyncRunPipeline.hasReusableEvidence`): verify-only reuses
`conversation.lastVerdict().executionTraces()` — evidence from the **last run that still
carries execution traces**. Safe documented pattern: **one execute → one verify-only**.

**Forbidden in generation:** chaining multiple verify-only prompts after one execute
(`Verify HTTP 2xx` then `Verify $.field…`). The second+ verify-only is unreliable against
oracle evidence binding (verify-only does not re-fetch; it re-judges last verdict traces).

For each happy-path API step, emit **exactly 2 prompts**:

| Order | Prompt role | Form | Example |
|---|---|---|---|
| 1 | **Execute (+ optional success)** | §3.1 / §3.8 (+ saves). Bare success `| verify:` OK | `Create … and save $.order_number as orderNumber \| verify: HTTP 2xx` |
| 2 | **Detail (one verify-only)** | §3.4 — **all** body / field / business asserts in **this one** prompt | `Verify $.order_number starts with 'RB-' and booking status is CONFIRMED` |

```java
// Preferred — TWO prompts
runStep("Create a CASH booking and save $.order_number as orderNumber | verify: HTTP 2xx");
runStep("Verify $.order_number starts with 'RB-' and booking status is CONFIRMED");
```

Alternative (success folded into the single detail verify-only):

```java
runStep("Create a CASH booking and save $.order_number as orderNumber");
runStep("Verify HTTP 2xx and $.order_number starts with 'RB-' and booking status is CONFIRMED");
```

**Why split execute from detail:** MCP runs one prompt per call. Mega-prompt
`action | verify: 2xx and $.a and $.b` hides whether the call or a field assert failed.

**Why not execute → success verify-only → detail verify-only:** second verify-only can fail or
mis-bind — put success on the execute line **or** inside the **same** detail verify-only.

| `expected_result` | Emit |
|---|---|
| Success + field checks | Execute (+ optional `\| verify: HTTP 2xx`); **one** verify-only with all fields |
| Success status only | Execute with `\| verify: HTTP 2xx` — no second prompt |
| Negative / expected error | Execute; **one** verify-only `Verify status is 4xx and …` |
| Setup / TDP / helper | Execute-only; no scenario detail verifies on helpers |

```java
// BAD — multiple consecutive verify-only after one execute
runStep("Create a CASH booking");
runStep("Verify HTTP 2xx");
runStep("Verify $.order_number starts with 'RB-'");
runStep("Verify booking status is CONFIRMED");
```

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
runStep("Set default payment option with body token as saved gopayWalletToken",
    "gopay", "payment-options-service");
runStep("Verify HTTP 2xx");
runStep("Verify success is true");
```

### 3.4 Verify-only steps (reuse the previous response, no re-fetch)

If a previous step already called an API and you only want to assert something on that same
response, start the prompt with one of these five words:

**`verify` / `assert` / `validate` / `check` / `expect`**

Default after an execute step (§3.1.1): **exactly one** verify-only prompt with all remaining
asserts (include HTTP 2xx here only if it was not already on the execute line).

```java
runStep("Create a CASH booking and save $.order_number as orderNumber | verify: HTTP 2xx");
runStep("Verify the booking status is CONFIRMED and $.order_number is not null"); // one detail prompt
```
> The prompt **must start directly** with one of those 5 words. `"Please verify..."` or
> `"Can you check..."` will NOT be treated as verify-only — TapMind will plan it as a brand-new
> API call and may re-fetch (possibly getting different data).

> **Do not** chain `Verify HTTP 2xx` then another `Verify $.field…` — verify-only reuses
> `lastVerdict.executionTraces()`; multiple consecutive verify-only prompts after one execute
> are forbidden in generation (§3.1.1).

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

**Template (generation default):**

```
call mcp grpc grpc.invoke for rpc_alias: <alias> service: <fq.service> Method: <Method> request: <json> [| verify: status is OK]
```

Then §3.1.1: **one** detail verify-only with remaining field asserts. Do **not** chain
`Verify status is OK` as its own prompt then another verify-only for fields.

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
    + "and save $.progress_id as progressId | verify: status is OK");
runStep("Verify $.progress_id is not null");
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
| `save basetoken from response` / `save basetoken as basetoken` | `save $.data.base_token as basetoken` (path from `declared_bindings`) | Test-case wording has no JSONPath — resolve via `TESTCASE_TO_NLP.md` before generate. |
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
| Loading strict assertions onto a shared setup step (e.g. a "create booking" step other scenarios also reuse as a precondition) | Keep setup steps assertion-free; put success on execute or in the single detail verify-only (§3.1.1) | Over-asserting a shared step breaks reuse by other scenarios (e.g. negative tests) that need that same step's evidence to look different. |
| `Create … \| verify: HTTP 2xx and $.a is X and $.b is Y` (one mega-prompt) | Execute (+ optional `\| verify: HTTP 2xx`); then **one** `Verify $.a is X and $.b is Y` (§3.1.1) | Combined mega-prompts hide which check failed. |
| Execute then `Verify HTTP 2xx` then another `Verify $.field…` | Put success on execute **or** in the same detail verify-only — never chain verify-onlys | Verify-only reuses `lastVerdict.executionTraces()`; second+ verify-only after one execute is unreliable. |
| `data.whatsapp_templates.provider is X` (dotted path into a list) | `whatsapp_templates contains an entry with provider X` | Same "entry" rule as above — a scalar dotted path can't reach into a list. |
| One generic field name (e.g. "template_name = X") when the schema actually needs the value on several nested/cross-referenced fields | Name each real field path explicitly: `arrayA[0].key = X, arrayB[1].key = X, ...` | A generic/wrapper field name only overrides an exact key match — nested or cross-referenced fields with different key names silently keep spec-example defaults instead of erroring. See §8.1. |
| `templates[0].id/en/default = saved …` without `templates[0].channel = whatsapp` (or equivalent required siblings) | Whole-object phrasing **or** name every required field including constants — see §8.1.1 | Indexed overrides can emit a **sparse** object; body_defaults may not fill `channel` / category / components → API `400 missing channel` (or similar). |
| Blaming `saved <key>` / memory when create returns `invalid_request_body` | Diff request body vs required schema fields first (§8.1.1) | Memory substitution often worked; the body is simply missing required keys the prompt never named. |
| Relying on `tapmind_verify_prompt` PASS as proof the create body is complete | Run once and inspect Request Body / curl in the log | Verify checks planner routing; sparse body_defaults merge only shows up at execute time. |
| Raw grpcurl command as the prompt | §3.8 `call mcp grpc grpc.invoke for rpc_alias: …` | Planner expects structured gRPC grammar, not a shell grpcurl line. |
| Guessing `rpc_alias` from hostname substring | Lookup `GET /v1/grpc/targets` by host:port | Unregistered alias fails at invoke time. |
| Same `runStep` or shared step prefix in every `@Test` | `provision…()` / `create…()` / `fetch…()` on `*TapMindTestBase` | Any repeated pattern — not only TDP. `FIXTURE_REUSE.md`. |
