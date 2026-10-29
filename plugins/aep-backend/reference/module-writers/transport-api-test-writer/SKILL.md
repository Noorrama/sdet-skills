---
name: transport-api-test-writer
description: >-
  Use this skill whenever the user wants to write, add, or scaffold backend API automation tests
  in the transport module of gojek-backend-tests (transport/src/test/java/**, covering ride-hailing
  booking (rideService/FBON), pickup/dispatch, tracking, driver karma/tipping, profitability/
  payments, GoCorp, and rentals). Trigger this any time the user gives a cURL, endpoint definition,
  or API doc targeting a transport host/path and asks for a new test case, test class,
  Endpoint/Client/Controller/DTO, or feature folder. Also use it when the user references
  TransportController, TransportTestBase, BookingFlowController, BaseApiEndPoint, or
  RSCustomerPool.
---

# transport API Automation Test Writer

**Prerequisite:** read `.claude/skills/backend-automation/SKILL.md` first if you haven't already
this task — it defines the common module-identification, local-framework-discovery,
search-before-create, never-invent-data, and compile-check workflow. This file only covers what's
specific to transport on top of that.

**Note on `transport/README.md`:** it is ~4 years stale (claims Java 1.8/"Gradle 1.8.0_222"; the
module is actually on Java 17 — confirmed via `build.gradle`'s `--add-opens java.base/... //Mandatory
for JDK17` comment and the repo's Gradle 8.3 wrapper). Its service list is still roughly accurate,
but do not trust its build/version claims. This is a live example of "verify documentation before
trusting it" from the common skill.

## Architecture

```
TestNG @Test  →  Flow Controller (controllers.flowControllers.*, orchestrates multiple API calls
                                   using cached state from a prior step, e.g. BookingFlowController)
                     →  API Controller (controllers.apiControllers.*, one per domain, e.g.
                                         BookingApiController — reached directly by tests that don't
                                         need orchestration)
                         →  Client (clients.*, mirrors serviceEndpoints/ by vertical; some call
                                     endpoint.call() directly, bypassing clients.BaseClient)
                             →  Endpoint (restidioms.serviceEndpoints.*, extends
                                          restidioms.BaseApiEndPoint<T>, which implements
                                          IServiceEndpoint and does the RestAssured call itself
                                          inside call())
```

Every test class extends `testBases/TransportTestBase.java`, which itself extends
`controllers.TransportController` — a Lombok `@Delegate`-based aggregator of ~30 API controllers.
This means test methods call controller methods **unqualified** (e.g. `makeBooking(...)`,
`v2Estimates(...)`) — they're delegated through inheritance, not imported. Even the framework's
own code comments flag at least one delegated field (`TransportControllerUtil`) as something that
"should not be consumed outside TransportController... only if the use case outweighs any other
alternative approach" — be cautious about adding new delegated fields to this god-object rather
than calling the more specific controller/client directly.

## Local Client/Endpoint/Controller pattern

- `clients.BaseClient` (a thin RestAssured `RequestSpecification` wrapper) exists but is a
  **minority/legacy pattern** — most Clients (e.g. `V1MakeBookingClient`) bypass it entirely and
  call `new XyzApiEndPoint(request).call()` directly, since `BaseApiEndPoint.call()` does the
  RestAssured dispatch itself. Check the sibling Client before assuming either shape.
- Endpoints extend `restidioms.BaseApiEndPoint<T>` (`url()`, `httpMethod()`, `userType()`), which
  itself `implements restidioms.security.core.template.IServiceEndpoint` — confirming the shared
  interface convention holds here, just via this module's own abstract base.
- Request construction for complex flows goes through `builders/BaseBuilders/ApiRequestBuilder`
  and `ApiRequestHeadersBuilder` (auth, `X-App-Version`, `Gojek-Service-Area`, `Gojek-Country-Code`,
  `Gojek-Timezone`, etc.) rather than being built inline in the Controller.

## Request/response conventions

- Predominantly `@Getter`/`@Setter` (not `@Data`); `@Builder` on request-body builders.
- `@JsonIgnoreProperties(ignoreUnknown = true)` is standard on response DTOs (extends
  `entities.BaseResponse`). Some request fields use `@JsonProperty(...)` or
  `net.minidev.json.annotate.JsonIgnore` for computed-but-not-serialized fields.
- **Response DTOs commonly bundle their own assertion helper methods** (e.g.
  `V1MakeBookingResponse.assertErrorInvalidPayment()`, `.assertErrorConcurrentBooking()`) — check
  whether the response type you're using already has one before writing an inline assertion or a
  separate helper class.
- A **divergent legacy pattern** also exists: separate `SuccessResponse`/`ErrorResponse`
  (and even `Error401Response`) classes per HTTP outcome (`entities/BFFDriverProfile/*`,
  `entities/DriverTransactions/*`), instead of one response class with an `errors` list. Match
  whichever shape the specific feature area you're extending already uses.

## Authentication

- Bearer token formatting: `restidioms.security.utility.RequestHandler.getBearerTokenString(token)`
  (external, from the shared dependency) — used via `ApiRequestHeadersBuilder().withAuthorization(...)`.
- Customer pool: `testData.customers.customers.RSCustomerPool` (borrow/return via
  `statemanager.RHSBorrowManager`) — don't create a fresh customer per test if a pooled one fits.
- **Driver login here intentionally diverges from the shared login helper** — `LoginApiController.loginDriver`'s
  own code comment says: *"Implementation here is optimised for RHS and hence should not be
  directly swapped with loginDriver from gojek-commons LoginController."* Don't "fix" this by
  swapping in the gojek-commons version; it's a deliberate divergence, not an oversight.

## Test-data conventions

- **Dominant pattern**: `dataProviders.testIterator.TransportFlowsDataProvider` (`@DataProvider(name = "transportFlowsGenerator")`),
  driven by reflection-visible custom annotations (`@TestData`, `@FilterBy`, `@Sampling` from
  `dataProviders/annotations/*`) rather than a literal `Object[][]` — read the target test method's
  annotations to understand what data it'll actually receive.
- Secondary: CSV-driven `@DataProvider`s reading fixtures from `src/test/resources/testData/**`
  cross-checked against golden JSON under `src/test/resources/verificationData/**`.
  Fixed/small case spaces use literal `Object[][]` arrays directly (e.g.
  `dataProviders.serviceTypes.ServiceTypesDataProvider`).

### Fixture setup from enriched plan (`test_data_output`)

Load `reference/fixture-acquisition-from-tdi/SKILL.md` first — `TDP_SUPPORTED` → pool,
`TESTBUDDY_*` + non-null `test_buddy_prompt` → TDP2 NLP. This module:

| Status | Transport APIs |
|---|---|
| `TDP_SUPPORTED` | `RSCustomerPool` borrow/return via `RHSBorrowManager` (see Authentication). Map `tdp_test_data_category` to the pool category siblings use. |
| `TESTBUDDY_*` | `tests.testutils.TDP2Helper.createAndLoginCustomer(prompt)` / `createAndLoginDriver(prompt)` (`setClient("cartography")`), or `TDP2Controller.getTDP2Response` with `client` `"transport"` in e2e (`TransportBookingFlowTest`). Pass `test_buddy_prompt` as `message` verbatim. |

## Validation patterns

- Negative assertions check `getHttpStatusCode()` plus `getErrors().get(0).getCode()`/`.getMessage()`
  directly on the response DTO — never status code alone for a business-rule failure.
- **Both `org.junit.Assert` and `org.testng.Assert` appear in sibling test classes in the same
  package** with no enforced standard — match whichever the specific file you're editing uses; a
  `SoftAssert` field is also available on `TransportTestBase` if you want to collect multiple
  failures.
- **Three separate hand-rolled async/retry loops solve overlapping problems** — don't invent a
  fourth. Pick the one matching what you're actually waiting for:
  `BookingApiController.waitUntilFBONState`/`waitUntilBookingStatus` (business-state polling, `Thread.sleep`-based),
  `clients.bookingExperience.fbon.V1BookingDetailsClient.executeWithRetry` (HTTP-status-only retry),
  `db.paymentProcessor.PaymentProcessorDBClient.getAndWaitLogsByOrderNumber` (DB-row-count polling).
- **Some DB-log assertions are commented out in real tests** (`GopayCoinsPaymentTests.java` has
  ~15 lines of commented-out `PaymentProcessorDBClient` assertions per method) — don't copy the
  surrounding pattern assuming the assertion call itself is active; check.

## Canonical tests (read these directly, don't guess)

- `src/test/java/tests/regression/bookingExperience/rideService/makeBooking/MakeBookingTest.java`
  + `controllers/flowControllers/BookingFlowController.makeBooking` — the best example of the
  orchestrated multi-controller flow pattern, with 3 distinct negative cases
  (invalid payment / insufficient balance / concurrent-booking-limit) in one file.
- `src/test/java/tests/regression/bookingExperience/rideService/drivernotfound/DriverNotFoundTest.java`
  + `controllers/apiControllers/FBONApiController.v1BookingDetails` — canonical example of the
  business-state polling pattern (`waitUntilFBONState`).

## Module-specific pitfalls

- Don't assume `clients.BaseClient` is used — most Clients bypass it.
- Don't "fix" `LoginApiController.loginDriver`'s divergence from the shared login helper — it's
  intentional.
- Don't add a 4th hand-rolled retry loop — reuse one of the three that already exist for the
  matching layer (business-state / HTTP-status / DB-row-count).
- Don't assume `org.junit.Assert` or `org.testng.Assert` is "the standard" — match the file.

## Legacy/dead patterns that must not be copied

- `clients.BaseClient` as a universal base — most Clients don't use it; `BaseApiEndPoint.call()`
  doing the dispatch directly is the more common shape.
- Separate `SuccessResponse`/`ErrorResponse`/`Error401Response` DTOs per outcome
  (`entities/BFFDriverProfile/*`, `entities/DriverTransactions/*`) — the single-response-with-`errors`-list
  shape (`V1MakeBookingResponse`) is the more current convention; only match the split-DTO shape if
  the specific feature area you're extending already uses it.
- Commented-out DB-log assertions in `GopayCoinsPaymentTests` and similar files — inert, not a
  template to restore without checking why it was disabled.

## Test-method contract (mandatory — verified counts over `transport/src/test/java`)

Read `backend-automation/references/test-annotation-rules.md` first. **transport has the strictest
and most unusual annotation contract in the repo** — five method-level annotations, two of them
validated at runtime and two with attributes that are compile-mandatory. Do not carry any other
module's test shape here.

### The five-annotation stack — this is the module's signature

```java
@Test(groups = {TransportCategories.X, TransportCategories.Y},
      dataProvider = "transportFlowsGenerator",
      dataProviderClass = TransportFlowsDataProvider.class)
@TestData(journeyType = JourneyType.…, customerType = CustomerType.…)
@FilterBy(features = {@Feature(featureType = FeatureType.…, featureStatus = Toggle.ENABLED,
                              bookingType = BookingType.NORMAL)},
          languages = {Language.ENGLISH},
          paymentOptions = {PaymentOption.CASH})
@TestInfo(testCaseIds = {"…"}, owner = GojekEngineer.<NAME>_EMAIL, projectId = "", suiteId = "")
@Ownership(testCaseId = "…", author = GojekEngineer.<NAME>, ownerSquad = GojekSquad.<SQUAD>)
@Sampling(byCountry = true)
public void someTest(TransportFlowsDataProviderRow transportFlow) { … }
```

Measured counts: `@TestInfo` 2301, `@Ownership` 2300, `@FilterBy` 1862, `@TestData` 1858,
`@Sampling` 1369. **Class-level annotations: none** (only `@Slf4j` on some classes).

Definitions live in `transport/src/main/java/dataProviders/annotations/`.

### Three hard enforcement points

1. **Runtime validation.** `TransportFlowsDataProvider.java:81` calls
   `this.testMethodHelper.validateMandatoryTestMethodAnnotations(method)`. Omitting `@TestData` or
   `@FilterBy` on a `transportFlowsGenerator` test **throws at runtime**.
2. **`@FilterBy.languages()` and `@FilterBy.paymentOptions()` have no defaults** — omitting either
   is a **compile error**. `features()`, `countries()`, `platforms()` do have defaults.
3. **`@Ownership.testCaseId()` has no default** — also compile-mandatory.

### `@TestInfo` in transport — always empty project/suite

```java
@TestInfo(testCaseIds = {"2824416","4594314"}, owner = GojekEngineer.TONY_BASIL_EMAIL,
          projectId = "", suiteId = "")
```

- **`projectId=""` and `suiteId=""` always.** Confirmed across all 319 files (2,221 sites). There is
  **no `TestRailConfig` in this module**. Populating them is the deviation, not the norm.
- Attribute order is `testCaseIds, owner, projectId, suiteId` here — not the repo-typical order.
- `owner` = one of 46 `GojekEngineer.<NAME>_EMAIL` **String** constants
  (`constants/domainmodel/test/GojekEngineer.java`).
- `countryName()` is never set.

### You must set the owner TWICE, in two different forms

The same file declares both String constants and a richer **enum** of the same name:

```java
@TestInfo(owner = GojekEngineer.TONY_BASIL_EMAIL, …)          // String constant
@Ownership(author = GojekEngineer.TONY_BASIL, ownerSquad = GojekSquad.…)  // enum constant
```

`@TestInfo` takes the `_EMAIL` String; `@Ownership.author` takes the bare enum (which carries name,
Slack handle, role and quotas via `EngineerBuilder`). Getting these two crossed will not compile.

### `@Test` attributes

```
groups            always present, from utils.TransportCategories
dataProvider / dataProviderClass   always paired for flow tests
description      1009
enabled           690   <- heavily used to park tests per-environment
priority          130
invocationCount     2
retryAnalyzer       1   <- essentially never inline
dependsOnMethods    0   <- never
```

Retry comes from `listeners.AnnotationTransformer` + `listeners.RetryAnalyzer` (registered in
`build.gradle`) and from `BaseApiEndPoint.call()` itself. Do not add an inline `retryAnalyzer`.

Groups come from **one single class**, `transport/src/main/java/utils/TransportCategories.java`
(contrast: driver-platform has 38 per-service files), organised in comment blocks naming the owning
PIC. Naming is `<AREA>_SMOKE` / `<AREA>_REGRESSION` plus cross-cutting tags
(`CLOUD_MIGRATION_TRANSPORT_TESTS`, `SG_NEW_LITE_APP_SMOKE`, `PANDA`). **Tests normally list 3-5
groups** so one method serves smoke + regression + migration suites.

### You usually write NO data provider

**94% of transport tests use the single reflective provider `transportFlowsGenerator`.** You do not
hand-write `Object[][]` rows — you *declare your data needs* through `@TestData` / `@FilterBy` /
`@Sampling` and receive a `TransportFlowsDataProviderRow` parameter. Writing a local
`@DataProvider` is the exception, not the default.

`@Debug(dataproviderIndex = …, serviceTypes = {…})` exists to pin one row locally — **local dev
only, never commit it.**

### Assertions live ON the response DTO

There is **no `assertions/` package** in transport. Response DTOs carry their own assertion methods:

```java
response.assertBookingCreatedSuccess();
```

When you add a response DTO, add its assertion methods to the DTO itself, extending
`entities.BaseResponse`. Do not create an external assertions class.

### Base class — a `@Delegate` god object

`TransportTestBase extends TransportController`, and `TransportController` aggregates ~35
controllers via Lombok `@Delegate`. Consequently tests call controller methods **bare**, with no
receiver. This is the documented pattern but the module's own comments flag parts of it as risky —
see the architecture section above before adding new methods to it.

### Compile check

```
./gradlew :transport:compileTestJava
```
