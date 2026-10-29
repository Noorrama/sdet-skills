---
name: driver-platform-api-test-writer
description: >-
  Use this skill whenever the user wants to write, add, or scaffold backend API automation tests
  in the driver-platform module of gojek-backend-tests (driver-platform/src/test/java/**,
  covering driver onboarding/KYD, driver wallet/passbook/swadaya, driver incentives/segmentation,
  driver support (hogwarts/commrad), active booking, fleet/vehicle onboarding, and goAgent).
  Trigger this any time the user gives a cURL, endpoint definition, or API doc targeting a
  driver-platform host/path and asks for a new test case, test class, Endpoint/Client/Controller/
  DTO, or feature folder. Also use it when the user references DPDriverServiceController,
  DriverSerivceClientInternal, HeaderHelper, DriverStateManager, SecurityHelper, or asks to follow
  the driver-service/passbook/swadaya test pattern.
---

# driver-platform API Automation Test Writer

**Prerequisite:** read `.claude/skills/backend-automation/SKILL.md` first if you haven't already
this task — it defines the common module-identification, local-framework-discovery,
search-before-create, never-invent-data, and compile-check workflow. This file only covers what's
specific to driver-platform on top of that.

## Architecture

```
TestNG @Test  →  Assertion helper (assertions.<serviceArea>Assertions.*, static methods)
                     →  Controller (controller.*, no shared base — plain classes)
                         →  Client (client.*, mostly plain classes; only 5 of ~48 extend
                                     clients.BaseClient from gojek-commons)
                             →  Endpoint (entities.<service>.endpoint.*, implements
                                          restidioms.security.core.template.IServiceEndpoint)
                                 →  RequestHandler.processAPIRequest(endpoint)  →  IAPIResponse
```

Package layout under `src/main/java`: `entities/<service>/{endpoint,request,response}` (422/372/419
files respectively) is where nearly everything lives — driverservice, SelfOnboarding, kyd,
driverWalletService, passbook, swadaya, swadayaFinance, segmentation, commrad, hogwarts,
activeBooking, fleet, vesus, goAgent (its own large sub-tree with data/dataProvider/helpers/kafka/db).
Tests mirror this under `src/test/java/tests/<service>/{componentTests,e2eTest}`, plus
`assertions/<service>Assertions/` and `dataProvider/<Service>/`.

## Local Client/Endpoint/Controller pattern

- **No universal `BaseClient`.** Only `CommradServiceClient`, `CherryServiceClient`,
  `SegmenterActorServiceClient`, `SegmentationServiceClient`, `SegmenterServiceClient` extend the
  shared `clients.BaseClient` (from `gojek-commons`). Everything else (`DriverSerivceClientInternal`,
  `PassbookServiceClient`, etc. — the large majority) is a plain class: build the `*Endpoint`,
  call `SecurityHelper.runSecurityScanIfRequired(endpoint, boolean)`, then
  `new RequestHandler().processAPIRequest(endpoint)`. **Check the sibling Client file in the same
  service area before assuming either shape.**
- Endpoints implement `IServiceEndpoint` directly; `url()` pulls from `properties.DriverPlatformPropertiesInternal`
  (e.g. `DriverPlatformPropertiesInternal.getDriverProfileUrl = String.format("%s/gojek/internal/drivers/{driverId}", driverServiceHost)`).
- Controllers are plain classes (`controller.DPDriverServiceController`, `PassBookServiceController`,
  `CommradServiceController`) — build/accept the request, call the Client, deserialize, stamp
  `httpStatusCode`. **Some controllers branch on status code before attempting deserialization**
  (e.g. `getDriverProfile` returns an empty response DTO on 404 rather than trying to deserialize
  an error body into the success shape) — check whether the endpoint you're calling needs this,
  don't assume it always deserializes unconditionally.

## Request/response conventions

- `@Getter`/`@Setter` (910 files) is more common than `@Data` (174 files); `@Builder` in 569 files.
- Response DTOs extend `entities.BaseResponse` (from `gojek-commons`) and carry
  `@JsonIgnoreProperties(ignoreUnknown = true)` + `@NoArgsConstructor`.
  Header DTOs use `@JsonProperty("client-id")`-style mapping for hyphenated header names.
- **A residual non-Lombok legacy style survives in isolated files** — e.g.
  `entities/SelfOnboarding/response/LeadModeResponse.java` has fully hand-written getters/setters,
  no Lombok at all. Don't copy this shape for new DTOs; it's a leftover, not the convention.

## Authentication

- **There is no single "log a driver in for real" helper actually in use.** A genuine OAuth
  login helper exists (`utilities/DriverLoginUtil.driverGoAuthLoginAndGetAccessToken(...)`) but has
  **zero call sites** in `src/test/java` — do not use it as your example.
- The real, live convention is header-spoofing: `entities.HeaderHelper.getKongAuthenticatedDriverHeader(String driverId)`
  (68 call sites) builds `ownerId`/`ownerType`/`kong-authenticated=true` + app/platform headers,
  simulating an already-Kong-authenticated request without a real token.
- Server-to-server calls use `HeaderHelper.getDefaultDriverServiceHeaders()` /
  `getBlockDriverHeaders()` / `getWalletProfileHeaders()` — different `client-id`/`pass-key` pairs
  **per endpoint family**, sourced from `DriverPlatformPropertiesInternal`. Check the exact header
  method the nearest sibling Endpoint uses; don't assume one pair works everywhere.

## Test-data conventions

- **Newer, structured approach (prefer this for new tests):** `helper.testData.driver.DriverStateManager.setupDriver(DriverProfileConfig.builder()...)`
  drives a driver into a required state (`driverProviderSource`, `driverType`, `isDriverBlocked`,
  etc.) via `mutators/*` and `providers/fetchStrategy/*`. Tear down with
  `DriverStateManager.teardownAllDrivers()` (see `DriverServiceBaseTests` `@AfterSuite`).
- Older/parallel: `@DataProvider`s under `dataProvider/DriverService/` and `dataProvider/DriverServiceDataProviders.java`,
  plus JSON fixtures under `src/test/resources/testdata/<service>/**` and `responses/<service>/**`
  (including JSON-schema files used by `response.validateJsonSchema(...)`).
- **Never hardcode a driver ID/passkey literal** — a real, checked-in violation of this exists in
  `tests/driverService/GetDriverClientNPassKey.java` (a hardcoded driver ID and a DB-fetched
  credential asserted as a literal). Do not add to this pattern; use `DriverStateManager` or the
  data providers instead.

### Fixture setup from enriched plan (`test_data_output`)

Load `reference/fixture-acquisition-from-tdi/SKILL.md` first. This module:

| Status | driver-platform APIs |
|---|---|
| `TDP_SUPPORTED` | `BookingHelper.getDriverFromTestDataPool` / `getCustomerFromTestDataPool`; `TestDataPoolController.getTestData` with requesting module `"DriverPlatform"`. Map `tdp_test_data_category` to `DriverType` / customer category. |
| `TESTBUDDY_*` | `TDP2Controller.getTDP2Response` **only if a sibling in this module already does**; otherwise wrap the prompt via pool helpers above or `TODO(agent-pm)`. Prefer `DriverStateManager` after the entity is acquired. |

## Validation patterns

- Both status-only (`Assert.assertEquals(response.httpStatusCode, HttpStatuses.NOT_FOUND.getCode())`)
  and status+error-body (`assertEquals(getErrorCode(), "DRIVER_NOT_FOUND")`,
  `assertEquals(getMessage(), "Driver not found")`) negative assertions coexist — match the nearest
  sibling assertion method in `assertions/driverServiceAssertions/`, don't invent new error text.
- `constants.api.HttpStatuses` (enum-like, `.getCode()`) and raw `org.apache.http.HttpStatus.SC_*`
  are both used, sometimes in the same file — either is acceptable, match the surrounding lines.
- **DB validation is real and live**: `helper/database/*DbClient.java` (`DriverServiceDbClient`,
  `PassbookDbClient`, `SwadayaDbClient`, etc.) use Spring `JdbcTemplate` via
  `utils.dataStores.sql.DBUtilities.getDB(DBName.X).getJdbcTemplate()`.
- **Kafka validation infrastructure exists but is currently disabled everywhere it's wired**:
  `kafka.ActiveBookingsLogKafkaAssertions` is real code, but every real call site in
  `tests/activebooking/*` is commented out with an explicit "Kafka for active booking service is
  not validated due to no consumer present" comment. If you copy a sibling active-booking test,
  notice this and don't assume the commented-out call means "add it back" without checking whether
  a consumer now exists.
- Async waits are plain `Thread.sleep(...)` (e.g. `Thread.sleep(5000)` before re-fetching a
  profile after setup) — no Awaitility usage found. Match the sibling wait duration/placement.

## Canonical tests (read these directly, don't guess)

- `src/test/java/tests/driverService/componentTests/GetDriverProfileTests.java` +
  `controller.DPDriverServiceController.getDriverProfile` — canonical GET example, including the
  branch-on-404-before-deserializing pattern and both status-only and status+body negative
  assertions in the same file (`GetDriverProfileAssertions.java`).
- `src/test/java/tests/driverService/componentTests/PostBlockDriverTest.java` +
  `controller.DPDriverServiceController.blockDriver` — canonical POST example, including the
  newer `DriverStateManager`-based test-data setup and a 3rd negative-assertion variant
  (`DriverServiceAssertions.verifyDeleteBlockDriverErrorcaseResponse`, status+non-empty-error-list).

## Module-specific pitfalls

- Don't assume `clients.BaseClient` — check the sibling Client file first (see above).
- Don't use `DriverLoginUtil` as your auth example — it's dead code with zero call sites.
- Don't copy a commented-out Kafka assertion call verbatim expecting it to run.
- Don't hardcode a driver ID or credential — use `DriverStateManager`/data providers.

## Legacy/dead patterns that must not be copied

- `entities/SelfOnboarding/response/LeadModeResponse.java`-style hand-written-getter DTOs (no
  Lombok) — legacy, not the convention for new DTOs.
- `utilities/DriverLoginUtil` — unused real-OAuth helper; header-spoofing via `HeaderHelper` is
  what's actually live.
- Commented-out `ActiveBookingsLogKafkaAssertions` calls in `tests/activebooking/*` — infrastructure
  exists, validation is currently inert.

## Test-method contract (mandatory — verified counts over `driver-platform/src/test/java`)

Read `backend-automation/references/test-annotation-rules.md` for the annotation contract itself.
This section is the driver-platform-specific instantiation. Every number below is measured.

### Base class — always a per-service base, never nothing

**Every test class extends a per-service `*TestBase`/`*BaseTests`**, which itself usually extends
`tests.DriverPlatformTestBase`. Measured `extends` counts:

| Base | uses |
|---|---|
| `DriverServiceBaseTests` | 62 |
| `BffServiceTestBase` | 38 |
| `RakamServiceTestBase` | 35 |
| `PassbookServiceTestBase` | 33 |
| `SwadayaFinanceTestBase` | 31 |
| `HogwartsTestBase` | 31 |
| `SelfOnboardingTestBase` | 22 |
| `SwadayaTestBase` | 19 |
| `DriverPlatformTestBase` (root) | 16 |
| `VesusServiceTestBase` / `DriverServiceTestBase` | 14 |

The root (`tests/DriverPlatformTestBase.java`) provides `scenarioContext`,
`dpDriverServiceController`, `driverServiceController`, `driverTestDataHelper` via
`@BeforeClass setup()`, and closes DB connections in `@AfterSuite`.

Per-service bases add their own controllers/helpers as `protected` fields initialised inline, and
several `implements ITest` with a `@BeforeMethod beforeMethod(Method, Object[], ITestContext)` that
builds the reported test name from **data-provider column 0**. That is why column 0 is a
`String testName` (see below) — if you omit it the report shows bare method names.

### Class-level annotations: normally NONE

No `@Listeners`, no `@Ownership`, no `@TestData` — 0 files use `@Ownership`/`@TestData`/`@FilterBy`/
`@Sampling` (those are **transport-only**). `@BeforeClass` appears in only 4 test files;
`@BeforeMethod` in 80, nearly all base classes.

### The annotation block

```java
@TestInfo(projectId = TestRailConfig.DRIVER_PLATFORM_PROJECT_ID,
          suiteId = TestRailConfig.DRIVER_PAYOUT_TEST_SUITE_ID,
          testCaseIds = {"<real id>"}, owner = TestRailConfig.OWNER_<NAME>)
@Test(groups = {<Service>TestCategories.<GROUP>}, description = "<usually the method name>",
      dataProvider = "<methodName>", dataProviderClass = <Service>DataProvider.class)
public void getV1SomethingSomething(String testName, ...) {
```

Newest code puts **`@TestInfo` first, then `@Test`** (`@Test` first is also common — either is
accepted here).

- `groups` **always present** (1396) and always from `src/test/java/utils/<Service>TestCategories.java`
  (38 such files) — never a raw string.
- `description` near-always present (1167), and by convention is **literally the test-method name**.
- `dataProvider` + `dataProviderClass` are **always paired** (~1100 uses).
- `enabled = false` (171) is the module's way of parking flaky/blocked tests.
- `priority` (67) occasionally.
- **`retryAnalyzer` is never used inline (0)** — retry comes from `utilities.RetryListener` +
  `utilities.RetryAnalyzer` wired at the Gradle/suite level, and from Failsafe `RetryPolicy` inside
  controllers/assertions. **`dependsOnMethods` (0) and `invocationCount` (0) are never used.**

### `@TestInfo` values — `src/main/java/config/TestRailConfig.java`

- `projectId` is **always** `TestRailConfig.DRIVER_PLATFORM_PROJECT_ID`. No exceptions worth copying.
- `suiteId` picks the feature area: `DRIVER_PAYOUT_TEST_SUITE_ID` (482, dominant),
  `DRIVER_ONBOARDING_TEST_SUITE_ID` (117), `DRIVER_PLATFORM_TEST_SUITE_ID` (111),
  `DRIVER_SENTINEL_TEST_SUITE_ID` (6).
- **`owner` MUST be one of the 19 `TestRailConfig.OWNER_*` constants — never a raw email literal.**
  This is stricter than `gofood`/`marketplace`, which use quoted literals. If the right person has
  no constant, add one to `TestRailConfig` rather than inlining a string.
- `countryName()` is never set in this module.
- `testCaseIds` is always an array; `{""}` appears 8 times for un-triaged tests.

### Assertions — the test does NOT assert fields

**Assertions live in a dedicated test-side class**: `src/test/java/assertions/<Service>Assertions.java`
(32 root files + 5 sub-packages). A test method calls one or more
`<service>Assertions.verifyXxx(...)` and asserts nothing itself (an occasional `Assert.assertFalse`
for a loop-local guard is tolerated).

Inside those assertion classes the canonical shape is a **soft/hard mix**: a `SoftAssert` for the
field-by-field body checks plus hard `Assert.*` for structural preconditions, with a
`RetryUtil().getRetryPolicyForAssertionError(delay, count)` Failsafe policy as a class field for
eventually-consistent checks.

If you add a new endpoint, add its `verify<Endpoint><Case>Response(...)` method to the existing
`<Service>Assertions` class — do not start asserting inline in the test.

### Data providers

- Location: **`src/test/java/dataProvider/`** — singular, lowercase `d`.
- One class per service: `<Service>DataProvider.java` (more common) or `<Service>DataProviders.java`.
  Two large services also have per-endpoint files under `dataProvider/DriverService/` (18 files)
  and `dataProvider/QuiverService/`.
- No base class, no class-level annotations.
- `@DataProvider(name = "<exactTestMethodName>")`, add `parallel = true` when rows are independent.
- Return type **`Object[][]`** (dominant). Typed row objects only in the goAgent sub-framework and
  `SwadayaDataProviderRow`.
- **Column 0 is a `String testName`** in SCREAMING_SNAKE (e.g. `"DEDUCTION_HISTORY_SUCCESS_ID_ID"`),
  consumed by the base class `beforeMethod` for report naming.

### Method naming & AAA

- BFF/swadaya style: **method name == data-provider name == `description` value**
  (`getV1SwadayaFinanceProgramsSubscriptionsDeductionsPagination`).
- driverservice style: `verify` prefix (`verifyPostV3InternalDriver`).
- Negative/variant suffixes in use: `...ErrorFlows`, `...Pagination`, `...Timezone`,
  `...SuccessResponse`.
- **Arrange** `XxxRequestBuilder.build(...)` + setters for the varying field →
  **Act** one `controller.<method>(request, expectedStatus)` →
  **Assert** one or more `<service>Assertions.verifyXxx(...)`.
- Cross-service verification (call the upstream service to derive expected values) is idiomatic
  here, not a smell.

### Compile check

```
./gradlew :driver-platform:compileTestJava
```
