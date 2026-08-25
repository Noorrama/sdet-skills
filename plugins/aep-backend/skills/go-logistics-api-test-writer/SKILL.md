---
name: go-logistics-api-test-writer
description: >-
  Use this skill whenever the user wants to write, add, or scaffold backend API automation
  tests in the go-logistics module of gojek-backend-tests (go-logistics/src/test/java/**,
  covering GoSend, GoKilat/consignor, GoBox, GoShop, and TMS). Trigger this any time the user
  gives a cURL command, an endpoint/Swagger definition, or API documentation and asks for a new
  test case, test class, Endpoint/Client/Controller/DTO, or a new feature folder — even if they
  don't name the pattern explicitly. Also use it when the user references LogisticsProperties,
  IServiceEndpoint, ConsumerHeaders, GologisticBaseHelper, TMSClient, IAPIResponse,
  processAPIRequest, or asks to follow the TMS/GoKilat/GoSend/GoShop test pattern. This skill
  knows the layered convention (Endpoint -> DTOs -> Client -> Controller -> Assertions -> TestNG
  test) actually proven across this module's 703 existing `@Test` methods, including where it
  diverges from the module's own (unfinished, largely unused) Kotlin "modern" rewrite, and
  should be consulted before writing any new Java/Kotlin file here.
---

# go-logistics API Automation Test Writer

**Prerequisite:** read `.claude/skills/backend-automation/SKILL.md` first (or `.cursor/skills/backend-automation/SKILL.md` — same file) if you haven't already this task. It defines the common module-identification, local-framework-discovery, search-before-create, never-invent-data, and compile-check workflow. This file only covers what's specific to go-logistics on top of that.

`go-logistics` is a large (991 main Java files, 142 test files, ~100 abandoned Kotlin files), TestNG/Gradle backend API test
module covering five product verticals for Gojek Logistics: **TMS** (trip/route/shipment
management), **GoKilat / consignor / store** (partner store bookings, pricing, driver tipping),
**GoSend consumer** (consumer bookings, serviceability, saved addresses), **GoBox**, and
**GoShop**. It has grown organically over years, so each vertical has its own base-test-class
chain and its own corner of the DTO/endpoint/client tree, but they all share the same underlying
call-chain contract and the same TestNG/assertion/test-data idioms. Match what you write to
those idioms — that's what keeps a new test indistinguishable from the other 703 `@Test` methods already
there.

**Read `references/architecture.md` before touching an unfamiliar vertical** — it has the full
layer-by-layer breakdown, the env/country switching system, the auth flow, and a documented
gotcha (the TMS gateway-prefix quirk) that will 404 a new endpoint if you get it wrong. Read
`references/templates.md` for copy-pasteable full code for every layer. Read
`references/modern-kotlin-pattern.md` only if you're deliberately extending GoShop's Kotlin
layer or the user explicitly asks for the Refactoring.md-style rewrite — see the callout below
for why that path needs extra caution.

## The one non-obvious thing to internalize first

`go-logistics/Refactoring.md` describes an in-progress migration from a legacy pattern
(`Response`, `BaseHelper().adapter`) to a "modern" one (`IAPIResponse`, `processAPIRequest`,
`deserializeKt`). **This migration is real but incomplete in a specific, important way**: the
only place it's actually *finished* is a Kotlin scaffold under `src/main/kotlin/goShop/{clients,
controllers,endpoints}/**` — and as of this writing, **no test class in the repo calls into that
Kotlin layer**. Every real GoShop test still calls the older `controller.GoShopController` /
`clients.goShop.GoShopClient` (same domain, different package, never migrated). So:

- The **proven, dominant, safe-by-default pattern across all five verticals** — including
  GoShop — is: Java `IServiceEndpoint` endpoint class + Java Client (often `extends BaseClient`)
  + Java Controller (deserializes the response into a typed DTO) + Java TestNG test. This is
  what the 703 existing `@Test` methods do and what CI actually exercises. **Default to this** unless told
  otherwise.
- One piece of the "modern" direction *is* already live and worth adopting even in new legacy-
  style code: have your **Client** method call `requestHandler.processAPIRequest(endpoint)` and
  return `IAPIResponse` rather than the older `processRequest(...)` -> raw RestAssured `Response`.
  Many existing Client classes already do this (`TMSClient`, `RHSClient`, `GoShopConsumerClient`),
  and it gives your Controller a clean `response.deserialize(YourDto.class)` (Jackson) or
  `response.deserializeKt(YourDto::class.java)` (Moshi, only if the DTO is a Kotlin data class)
  one-liner instead of hand-rolled `.as(Class)` + manual status-code plumbing.
  `IAPIResponse.getStatusCode().getCode()` is also the idiom used everywhere for negative/error
  path assertions, even inside otherwise-legacy test files.
- Only go fully Kotlin (`BaseConsumerEndpoint`, `goShop.clients/controllers` style) if the user
  explicitly wants the Refactoring.md convention for new GoShop work, or is extending that
  specific Kotlin tree already. If you do, **tell the user this path has no existing test
  coverage precedent in this repo** and verify it compiles and runs before considering it done —
  see `references/modern-kotlin-pattern.md` for the exact shape and a known interop pitfall
  (missing `@JvmOverloads` on Kotlin default parameters breaks Java callers silently until
  someone tries to use them).

## Ground truth that already exists — check this before writing anything

`go-logistics/` root already has machine-generated mapping docs from a prior schema-scanning
effort: `KILAT_API_TEST_MAPPING.md`, `GOSEND_API_TEST_MAPPING.md`, `TMS_API_TEST_MAPPING.md`,
`GOBOX_API_TEST_MAPPING.md` (endpoint -> test class(es) -> request/response DTO), and their
`*_API_SCHEMA.md` counterparts (also viewable via `api-schema-viewer.html`). **Always check the
relevant mapping doc for the vertical you're touching first** — it tells you immediately whether
an endpoint is already covered (extend the existing test class/Controller/Client rather than
duplicating it) or is genuinely new. These docs may drift from the code over time; treat them as
a fast first-pass index, not a substitute for reading the actual test class before extending it.

## Inputs to gather from the user first

1. **Which vertical / which existing feature folder.** From the URL path or host in a cURL
   (`.../gokilat/v10/...` -> GoKilat/store, `.../tms/...` -> TMS, GoShop/GoSend consumer paths,
   GoBox), or an explicit folder like `src/test/java/tms/shipments/`. This tells you which base
   test class chain and which sibling Endpoint/Client/Controller/Assertion files to match.
2. **The cURL (or Swagger/API doc) + a sample response.** Read the URL, method, headers, and
   request/response shape directly off this. If a response field doesn't exist yet in the
   repo's DTO, add it — don't silently drop it.
3. **Scenarios** — positive and negative cases to cover, and which countries (`id`/`vn`/`th`,
   sometimes `sg`) matter. If the user hands you a TestRail/case-ID list, use the real IDs in
   `@TestInfo(testCaseIds = {...})`. If they hand you PRD acceptance-criteria bullets instead,
   derive one scenario per distinct "given/should/must" statement and restate the breakdown back
   to them before writing code if it's ambiguous. Never invent a fake-looking TestRail ID —
   leave a clearly marked placeholder and say so.
4. If any of this is missing and can't be inferred by reading the target package's sibling
   files, ask — don't guess at auth requirements, business-rule numeric bounds, or expected
   error text.

## The layered call chain

```
TestNG @Test method
  -> Assertion class method(s)      (verify/check/validate*, TestNG Assert/SoftAssert only)
  -> Controller method              (builds request DTO/body, calls Client, deserializes response)
      -> Client method              (holds ConsumerHeaders/auth, builds Endpoint, calls RequestHandler)
          -> Endpoint class         (url/httpMethod/headers/pathParameters/queryParameters/body)
              -> RequestHandler     (external, aep-backend-core — the only place RestAssured is called;
                                      processRequest() -> Response [legacy] or
                                      processAPIRequest() -> IAPIResponse [preferred for new Clients])
```

Request/response shapes live in DTO classes under `src/main/java/dto/**` (Lombok + Jackson) or,
for GoShop's Kotlin corner, `src/main/kotlin/goShop/**` (Moshi data classes). Test data/fixtures
live under `src/test/resources/<vertical>/{templates,testData}/**`. See
`references/architecture.md` for full detail on every layer and `references/templates.md` for
runnable examples of each.

## Decision tree: from a cURL / endpoint / Swagger doc to a finished test

1. **Identify the vertical** from the URL/host (see step 1 above).
2. **Check the vertical's `*_API_TEST_MAPPING.md`** at `go-logistics/` root. Endpoint already
   listed -> go to Case 1. Not listed / genuinely new -> Case 2.
3. **Case 1 — extending an existing feature:**
   - Open the mapped test class(es) and its base class. Follow its exact conventions (imports,
     `@BeforeMethod`/`@BeforeTest` fixture setup, `groups = {TestGroups.X}`, `@TestInfo`,
     `@Ownership`).
   - Add one `@Test` method per new scenario, named `verify<Behavior>`.
   - Reuse the existing Controller/Client method. Only touch the Client/Endpoint/DTOs if the new
     scenario needs a request/response shape they don't support yet (e.g. a new optional field)
     — extend rather than duplicate.
   - Reuse the assertion class already used by sibling tests in that file; add a new method to
     it if the new scenario's expected shape isn't covered.
   - If new fixture values are needed (case JSON, template JSON, phone numbers, lat/longs), add
     them to the existing per-country test-data files/folders rather than hardcoding literals in
     the test method.
4. **Case 2 — brand-new endpoint/feature**, build in this order:
   1. **URL constant** — add to `src/main/java/properties/LogisticsProperties.java` under the
      right vertical's comment block, `String.format("%s/path/{param}", someHost)` with path
      params as `{name}` placeholders. Pick the *correct host constant* — see the TMS
      gateway-prefix gotcha in `references/architecture.md` before assuming which one.
   2. **Endpoint class** — new file under `src/main/java/endpoint/<vertical>/<feature>/`,
      implementing `IServiceEndpoint` (or extending an existing vertical base like
      `BaseStoreEndpoint`/`DriverBaseEndPoint` if one already fits). Override `url()`,
      `httpMethod()`, and whichever of `headers()`/`pathParameters()`/`queryParameters()`/
      `body()` differ from a no-op default.
   3. **Request/response DTOs** — `src/main/java/dto/<vertical>/<feature>/{request,response}/`,
      Lombok `@Data` + `@JsonIgnoreProperties(ignoreUnknown = true)`, `@JsonProperty("snake_case")`
      wherever the JSON field name differs from (or would collide as a Java keyword with) the
      field name. Nested JSON objects become nested (usually top-level, sometimes static-inner)
      classes with the same annotations.
   4. **Client method** — add to the vertical's existing `<Vertical>Client` class (or create one
      if the vertical genuinely has none yet). Build the Endpoint, thread through the shared
      `ConsumerHeaders`/auth object already used by sibling methods, call
      `requestHandler.processAPIRequest(endpoint)`, return `IAPIResponse`.
   5. **Controller method** — add to the vertical's existing `<Domain>Controller` (flat package,
      `src/main/java/controller/`). Deserialize via `response.deserialize(YourResponseDto.class)`
      (wrap the checked `JsonProcessingException`). Do not embed assertions here if you can help
      it — Refactoring.md's explicit direction, even though a lot of legacy code doesn't follow
      it; put assertions in the test/assertion layer instead.
   6. **Assertion class method(s)** — add to the relevant `src/test/java/assertions/<domain>/`
      class. Accept a `SoftAssert` parameter (don't instantiate one inside the assertion class —
      that's the safer of the two conventions found in this codebase), assert status code
      together with the specific error code/message for negative cases, and let the *test method*
      call `.assertAll()` once at the end.
   7. **Test data** (if the case space is more than 2-3 fixed cases) — a `@DataProvider` in the
      vertical's `*BaseTest`, reading a JSON case-array file via `ReadFile.readFileAsString(...)`
      + `Utilities.convertJsonToListDTO(...)`. For a handful of fixed cases, an inline
      `Object[][]` in the `@DataProvider` method is fine and matches existing convention.
   8. **Test class** — new or extended file under `src/test/java/<vertical>/<feature>/`,
      extending the closest existing base class for that vertical (see
      `references/architecture.md` for the four hierarchies — TMS, GoKilat/store,
      GoSend/GoShop/GoBox/Dispatch's shared `GologisticBaseHelper`). One `@Test` per scenario,
      `groups = {TestGroups.X}` (add a new `TestGroups.kt` constant if none fits — never a raw
      string literal), `@TestInfo(...)` + `@Ownership(...)`, `retryAnalyzer = RetryAnalyzer.class`
      only if the scenario is genuinely timing/flaky-prone (driver assignment polling, etc.).
5. **Auth**: don't invent a login flow. Reuse `GologisticBaseHelper.provideConsumer()` /
   `provideConsumerWithPayment(country, paymentType)` (GoSend/GoShop/GoBox/Dispatch) or
   `LoginHelper.getConsumerFromPoolAndLogin(UserType)` directly, or the vertical's existing
   driver-header builder for driver-side calls. See `references/architecture.md` for which one
   applies where, and the direct-vs-Kong-gateway driver-token distinction for TMS.
6. **Ask the user** for anything you can't responsibly derive: a real TestRail case ID, which
   countries to cover, and any business-rule bounds/error text the cURL+sample response doesn't
   reveal — don't invent plausible-looking numbers or error strings.

## Conventions to always follow

- **TestNG, not JUnit.** `org.testng.annotations.Test/BeforeMethod/BeforeTest/DataProvider`,
  `org.testng.Assert` / `org.testng.asserts.SoftAssert`. No AssertJ, no Hamcrest, no JSON-schema
  validation library — this codebase asserts field-by-field against deserialized DTOs, always.
- Every `@Test` carries a `groups` array referencing `common.constants.test.TestGroups` constants
  (never a raw string), and a `@TestInfo(projectId=, suiteId=, owner=, testCaseIds={...})` +
  `@Ownership(author = GojekEngineer.X)` pair for TestRail traceability. If you don't have a real
  case ID, leave an obvious placeholder and say so — don't fabricate one.
- Method names: `verify<Scenario>` (test methods), `verify/check/validate<Thing>` (assertion
  methods) — descriptive, one behavior per test method.
- DTOs: Lombok `@Data` + `@JsonIgnoreProperties(ignoreUnknown = true)` is the default for Java;
  reach for Lombok `@Builder` only when the object is constructed once from scratch in code
  (not when it's loaded from a JSON template and then mutated field-by-field — that's the
  dominant case, and plain setters are the existing convention there).
- Client methods return `IAPIResponse` via `processAPIRequest(endpoint)` for anything new — don't
  introduce a third response-handling style.
- Negative tests assert **status code together with a specific error code/message**, never
  status code alone for a business-rule failure. Match whichever error-shape convention the
  vertical already uses (GoShop's `code`/`message`/`message_title` triad vs. TMS's
  `code`/`message` pair) rather than inventing a new one.
- Country-specific fixtures: check whether the directory you're adding to uses a
  `countries/{id,vn,th}/` subfolder or an `_id.json`/`_vn.json`/`_th.json` filename suffix, and
  match it — both conventions coexist in different parts of the tree.
- Use `SkipException` (not a failing assertion) when a test precondition genuinely can't be met
  (an unrelated upstream 422, a required ID that never got generated) — an accepted idiom here.
- Use the real user/consumer pools (`LoginHelper`, `consumers_with_country_codes.json`) and
  `com.github.javafaker.Faker` + `utilities.PhoneNoGenerator` for synthetic data — never hardcode
  a phone number, token, or lat/long inline in a data-provider-driven test.

## Anti-patterns to avoid (found in the existing codebase — don't copy these habits)

- **Silent non-assertions**: `Reporter.log(...)`-ing an expected-vs-actual check instead of
  actually asserting it. Always assert.
- **`@Test(enabled = false)`** as a long-term way to "disable" a broken/flaky test, left in the
  suite indefinitely. If a new test turns out to be flaky/broken, say so to the user rather than
  silently disabling it this way.
- **Commented-out `@Test`/`@BeforeTest`/assertion lines** left in place instead of deleted.
- **Dead mechanisms**: the custom `utilities/testRail/@TestRail` annotation and its listener are
  fully superseded by `@TestInfo` + the external `GenericTestRailListener` — don't use the old
  one. Gson `@SerializedName` imports appear in a few DTOs but are unused dead weight — Jackson
  (`ObjectMapper`/`@JsonProperty`) is the real Java serializer; don't add new Gson annotations.
- **Positional-argument footguns with Kotlin defaults**: `goShop.controllers.
  NearByMerchantsControllerV1` calls its client with two same-typed `Int` args in the wrong
  order (an undetected latent bug, because nothing exercises that code path with a test). If you
  write or call Kotlin functions with multiple adjacent same-typed parameters, use named
  arguments.
- Hardcoded lat/long/IDs mixed into an otherwise data-provider-driven test class — keep it
  consistent within the file.

## After writing the code

Verify every abstract method required by `IServiceEndpoint` is implemented and that DTO field
names/annotations match the sample response exactly. For the compile-check and reused-vs-created
summary steps, see the common skill — the go-logistics-specific Gradle commands are:
`./gradlew :go-logistics:runTests -Dtag=<TestGroups constant> -Denv=integration -Dcountry=<id|vn|th>`
or `./gradlew :go-logistics:singleTest -DtestName=<name> --tests "<FQCN>"`.

## Test-method contract (mandatory — verified)

Read `backend-automation/references/test-annotation-rules.md` first.

### Real module size (corrected)

991 main Java files, **142 test files, 74 containing `@Test`, 703 `@Test` methods**. Earlier
versions of this skill said "1,100+ test files / ~1,000 tests" — that conflated main sources with
tests. Calibrate your expectations accordingly.

### Base class

`extends helpers.GologisticBaseHelper` — **44 of ~90** `extends` sites in `src/test`. Then
`BaseHelper` (9), `TMSBaseTest` (5), `ShipmentBaseTest` (4), `GoSendBaseHelper` (4).

### The annotation block

```java
@Test(groups = {TestGroups.<GROUP>}, description = "…")
@TestInfo(projectId = SuiteConstants.<AREA>_PROJECT_ID, suiteId = SuiteConstants.<AREA>_BACKEND,
          testCaseIds = {"<real id>"}, owner = "first.last@gojek.com")
@Ownership(...)            // used in part of the module — match the sibling file
public void verifySomething() {
```

`projectId`/`suiteId` come from **`constants.SuiteConstants`** (`src/test/java/constants/SuiteConstants.java`):
`CEG_PROJECT_ID` (198), `TMS_PROJECT_ID` (56), `PEG_PROJECT_ID` (51), `GTL_LPS_PROJECT_ID` (24);
suites `CEG_GOSEND_BACKEND_MAIN_SUITE_ID` (132), `TMS_BACKEND` (56), `PEG_BACKEND` (49),
`CEG_GOSHOP_BACKEND_SUITE_ID` (30). **Never raw string literals** — an earlier template in this
skill taught that and it was wrong.

`owner` has two competing forms here: quoted email literal (306) and `GojekEngineer.*_EMAIL` (33).
Prefer the quoted literal to match the majority, unless the sibling file uses the constant.

`countryName` — go-logistics uses the bare string literal `"indonesia"` when it sets it at all
(18 sites). `customer-platforms` uses a constant for the same attribute; do not cross them.

**Gotcha:** `TestGroups` constant *names* do not match their tag strings. Always reference the
constant, and check its value before assuming what `-Dtag` will select.

### Framework facts (corrected)

- `IServiceEndpoint` is **not** in this repo — 148 `implements IServiceEndpoint` files in
  `src/main` bind to `restidioms.security.core.template.IServiceEndpoint` inside the external
  `com.gojek.aep-backend-core:core:4.13.1` jar (pinned at `build.gradle:226`).
- `BaseClient` is `core.BaseClient` from that **same external jar** (26 importers), not from
  `gojek-commons` (1 importer). `extends BaseClient` covers **27 of 35** client files — it is
  **dominant, not legacy**.
- `processAPIRequest`/`IAPIResponse` is already the established convention at **174 vs 12**
  occurrences (~94%), not an aspiration to adopt.
- **`SoftAssert` is used in 103 files here** — the highest in the repo (scp: 0, payment-core: 3).
  Do not carry this habit into those modules.

### Undocumented sixth test area

`src/test/java/workflows/` — 15 files, the 4th largest test package. Earlier versions of this
skill's decision tree could not route to it. If your cURL is a multi-step orchestration rather than
a single endpoint, look there for the sibling pattern.

### Compile check

```
./gradlew :go-logistics:compileTestJava
```
