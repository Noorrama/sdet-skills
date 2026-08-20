---
name: gofood-api-test-writer
description: >-
  Use this skill whenever the user wants to write, add, or scaffold backend API automation tests
  in the gofood module of gojek-backend-tests (gofood/src/test/java/**, covering merchant/
  moderator content, ordering, discovery, haggler pricing, cashier, group orders, meal planning,
  and the OpenAPI/web-order gRPC surface). Trigger this any time the user gives a cURL, endpoint
  definition, or API doc targeting a gofood host/path and asks for a new test case, test class,
  Endpoint/Client/Controller/DTO, or feature folder. Also use it when the user references
  GoFoodTestBase, GoFoodSecurityHelper, OpenapiController, ModeratorClient, or IGrpcServiceEndpoint.
---

# gofood API Automation Test Writer

**Prerequisite:** read `.claude/skills/backend-automation/SKILL.md` first if you haven't already
this task — it defines the common module-identification, local-framework-discovery,
search-before-create, never-invent-data, and compile-check workflow. This file only covers what's
specific to gofood on top of that.

## Architecture — two coexisting paradigms, pick the right one

gofood has real, genuine REST **and** gRPC testing, plus two REST generations mid-migration.
**Confirm which one the target API is before picking a template.**

**REST (dominant, ~450+ test files):**
```
TestNG @Test  →  (asserts inline via Google Truth, OR a asserts/*.java helper)
                     →  Controller (controllers.*, asserts status + deserializes)
                         →  Client (clients.*, some extend clients.base.GoFoodBaseClient)
                             →  Endpoint (serviceEndpoints.*, implements
                                          restidioms.security.core.template.IServiceEndpoint)
                                 →  RequestHandler.processAPIRequest(endpoint)  →  IAPIResponse
```

**gRPC (narrow, ~22 test files, all under `tests/expansion/openApi/**` — the "OpenAPI"/tencent
web-order surface only, not a module-wide pattern):**
```
TestNG @Test  →  asserts/openApi/AssertGetOrder.java (field-by-field on generated proto getters)
                     →  controllers.openapi.OpenapiController (catches exceptions, has
                                                                *WithException variants)
                         →  clients.openapi.OpenapiClient (single ManagedChannel via
                                                            NettyChannelBuilder; blocking stub
                                                            per call via
                                                            MetadataUtils.attachHeaders(...))
                             →  serviceEndpoints.openapi.* (implements IGrpcServiceEndpoint —
                                                             see the interface-duplication warning
                                                             below)
```

**Legacy wrapper style (still delegated-into, not deprecated, ~46 files):** `wrappers/goFoodClientWrappers/*ClientWrapper`
classes, `@Delegate`d into `base.GoFoodTestBase`, calling a `*Client` directly with **no Controller
layer at all**. If you're extending a feature area whose sibling tests all use a `*ClientWrapper`,
match that shape rather than introducing a Controller where none exists for that area.

## Local Client/Endpoint/Controller pattern

- `base.GoFoodTestBase` is the one shared base test class used by most (not all) test classes —
  it wires up dozens of REST controllers/clients/wrappers **and** the gRPC `OpenapiController` in
  the same `@BeforeClass`. Some tests (e.g. content/moderator tests) are plain classes with no
  base at all — check the sibling file in your target package.
- REST Endpoints implement `IServiceEndpoint` (directly or via a vertical base like
  `BaseModeratorMerchantEndpoint` → `BaseModeratorEndpoint`, which centralizes headers once).
- REST Clients: some extend `clients.base.GoFoodBaseClient` (holds a shared
  `RequestHandler requestHandler = new RequestHandler(true)`), others don't — check the sibling.
- **Two separate `IGrpcServiceEndpoint` interfaces coexist mid-migration**: `utils.IGrpcServiceEndpoint`
  (local, older, used by most gRPC endpoints like `EstimateEndPoint`/`CreateOrderEndPoint`) vs.
  `restidioms.security.core.template.IGrpcServiceEndpoint` (shared, newer, used by `GetOrderEndPoint`/
  `ListOrderEndPoint`) — even two different curl-logging builders (`utils.GRPCCurlsBuilder` vs.
  `restidioms.security.utility.GRPCCurlBuilder`) are used side by side in the same `OpenapiClient`.
  **Match whichever interface the specific gRPC call you're extending already uses** — don't pick
  one as "the standard" and rewrite the other.

## Request/response conventions

- REST: Lombok `@Getter`/`@Builder` with **nested static builder classes mirroring the JSON shape**
  (e.g. `UpdateOperationalHoursRequestBody.OperationalHours.Days.Slots`), co-located with the
  Endpoint in the same package. Deserialization is `response.deserialize(X.class)` (newer) or
  `response.as(X.class)` (older wrapper style) — both are live, match the sibling.
- Field names often mirror raw JSON snake_case directly (`open_time`, `merchant_uuid`) rather than
  camelCase + `@JsonProperty` — check the sibling DTO before assuming you need an explicit mapping.
- gRPC: real generated proto types from `src/main/proto/gofood/{consumer,core,portal,types,errors}/v1/*.proto`,
  builder-constructed (`OrderServiceOuterClass.CreateOrderRequest.newBuilder()...build()`), request
  bodies for curl-logging only are converted via `com.google.protobuf.util.JsonFormat.printer().print(...)`
  — the actual RPC call always uses the typed proto message, not JSON.

## Authentication

- Customer/driver bearer tokens: `clients.LoginClientWrapper.loginViaGoAuth(Customer, boolean)` /
  `driverGoAuthLogin(Driver)` → `GoAuthController` → stored in `ScenarioContext`.
- gRPC OpenAPI consumer auth is **not** a bearer token — it's gRPC `Metadata` headers per call
  (`partner-user-id`, `user-email`, `gojek-user-id`, `api-client`, etc.), built in the Endpoint's
  `headers()`.
- Merchant/internal moderator calls use plain internal headers with **no token at all**
  (`Go-Id`, `Go-User-Type: merchant`, `Go-User-Roles`, etc., via `MerchantRequestParams`) — this
  is the internal-trust model for that area; don't add a bearer token where the sibling has none.

## Test-data conventions

- `@DataProvider`s (63 files), e.g. `testData/goFood/expansion/bundles/ExpansionDataProvider.java`.
- JSON fixtures are relatively rare (~13 files) under `src/test/resources/`, loaded via
  `GoFoodTestBase.loadJson(fileName)`.
- Hardcoded restaurant/merchant UUIDs as `static final String` fields directly in test classes
  are the norm for this module (e.g. `MerchantOperationalHoursTests.RESTAURANT_ID`) — this matches
  existing convention here (unlike some other modules), but still never invent a UUID that doesn't
  exist in the target environment; copy a real one from a sibling test or ask.
- Pooled dynamic customer/driver data via the `testdata.FoodTestDataManager` annotation
  (`needsNewDriver`, `needsGopayCustomer`, etc.) processed in `GoFoodTestBase.setUpBeforeMethod`.

## Validation patterns

- REST: status-code-only negative assertions exist, but the richer pattern additionally
  deserializes and asserts the error body (e.g. `verifyV4Error(response.deserialize(...), "field", "message")`).
- gRPC: no HTTP status — catch the thrown exception, `Status.fromThrowable(e)`, assert
  `.getCode()` (e.g. `Status.INVALID_ARGUMENT`) and `.getDescription()` (sometimes split on `" - "`
  to extract the human-readable message — see `OpenapiController.*WithException` methods).
- DB: `db/WaiterServiceQueries.java` (raw SQL via `dbhelpers.MySqlService`), consumed through
  `helper/DbValueAssertions.java`, `@Delegate`d into `GoFoodTestBase`.
- Kafka: not a raw consumer — validated via an internal Firehose HTTP proxy
  (`FireHoseKafkaController.getKafkaPacketUsingSequenceNumber(...)`), polling by sequence number
  and diffing against a golden JSON fixture (`tests.kafkalogs.discovery.JSONValidation.validate`).

## Canonical tests (read these directly, don't guess)

- `src/test/java/tests/expansion/openApi/GetOrderTest.java` (`verifyOrderResponse`) +
  `controllers.openapi.OpenapiController.getOrder` — the one clean, fully-migrated gRPC example
  using the shared `restidioms.security.core.template.IGrpcServiceEndpoint`; use this, not a
  `utils.IGrpcServiceEndpoint`-based sibling, as your gRPC template.
- `src/test/java/tests/content/restaurant/MerchantOperationalHoursTests.java` +
  `controllers.content.MerchantRestaurantController` — canonical "new structure" REST example with
  co-located nested-builder DTOs and inline Google-Truth assertions.

## Module-specific pitfalls

- Don't assume every gRPC endpoint uses the same `IGrpcServiceEndpoint` — check the sibling.
- Don't add a bearer token to an internal moderator-endpoint call that has none in its siblings.
- Don't treat the `*ClientWrapper` layer as deprecated-and-removable — it's still actively
  `@Delegate`d into `GoFoodTestBase` and used by real tests; only avoid it for genuinely new work
  where the "new structure" Controller/Client/Endpoint pattern applies.

## Legacy/dead patterns that must not be copied

- `wrappers/goFoodClientWrappers/*ClientWrapper` — legacy, still live/delegated, not dead, but not
  the pattern to imitate for brand-new feature areas (use Controller/Client/Endpoint instead).
- The `utils.IGrpcServiceEndpoint` / `restidioms...IGrpcServiceEndpoint` duplication is an
  unfinished migration, not a deliberate two-tier design — don't "pick a side" and refactor
  unrelated files; just match whichever the specific endpoint you're touching already uses.

## Test-method contract (mandatory — verified counts over `gofood/src/test/java`)

Read `backend-automation/references/test-annotation-rules.md` for the annotation contract itself.
This section is the gofood-specific instantiation of it. Every number below is a measured count.

### Base class

`extends base.GoFoodTestBase` — 280 of the `extends` sites in `tests/`. It `implements ITest`, is
`@Getter @Setter`, and pre-instantiates **~60 controller and `*RequestBodyBuilder` fields** in
`@BeforeClass setUpBeforeClass()`. **Do not `new` a controller in a gofood test** — inherit it.

Exception: if your feature already has a domain base test class, chain to it instead of jumping
straight to the root (real chain: `MealPlanTests → MerchantCatalogTests →
MerchantCatalogInternalTests → GoFoodTestBase`). Other domain bases: `SearchTestBase` (12),
`MarkdownBaseTest` (9).

### The annotation block

```java
@Test(groups = {GoFoodCategories.<GROUP>}, description = "<human-readable intent>")
@TestInfo(projectId = TestRailConfig.<PROJECT>, suiteId = TestRailConfig.<SUITE>,
          testCaseIds = {"<real id>"}, owner = "first.last@gojek.com")
public void verifySomething() {
```

- `groups` is **mandatory** (2267 uses, always present) and must reference a constant from
  `src/test/java/utils/GoFoodCategories.java` — never a raw string. Groups feed
  `includeGroups systemProperties["tag"]` in `gofood/build.gradle:141`, so a wrong/missing group
  means the test never runs in CI. Common values: `DISCOVERY` (307),
  `MODERATOR_REGRESSION` (132), `GOFOOD_EXPANSION_OPENAPI_TENCENT` (117),
  `MARKDOWN_REGRESSION` (107), `GOURMET_REGRESSION` (92), `MODERATOR_SMOKE` (80),
  `GOFOOD_GROUP_ORDER` (40).
- Use **`description =`** (592) — **not** `testName =` (52). This is inverted in `marketplace`; do
  not carry that habit across.
- **`retryAnalyzer` is never used in gofood (0 occurrences).** Retries belong in the controller via
  Failsafe. Do not add one.
- Also available: `enabled =` (371), `dataProvider =` (285), `dataProviderClass =` (147),
  `priority =` (43), `dependsOnMethods =` (18).

### `@TestInfo` values — from `src/main/java/config/TestRailConfig.java`

gofood has **no `SuiteConstants`** and **no `OWNER_*` constants** — `owner` is a quoted
`"first.last@gojek.com"` literal (2021 uses). Pairing rule:

| Feature area | `projectId` | typical `suiteId` |
|---|---|---|
| consumer / booking / discovery | `GO_FOOD_PROJECT_ID` (1599) | `GOFOOD_GROWTH`, `DISCOVERY`, `BOOKING_HAGGLER`, `BOOKING_WAITER`, `GROUP_ORDER` |
| merchant portal (gourmet, moderator, onboarder, fmoi, godfather) | `GOFOOD_MERCHANT_PROJECT_ID` (473) | `MERCHANT_EXCELLENCE_MODERATOR`, `MERCHANT_EXCELLENCE_GOURMET` |
| OpenAPI / web-order | `GO_FOOD_PROJECT_ID` | `OPEN_API` (349) |

Several suite constants are empty strings in source (`OPEN_API`, `DISCOVERY`,
`MERCHANT_EXCELLENCE_*`) — that is expected; still reference the named constant, not `""`.

### Method naming — follow the surrounding package, both styles are live

- merchant-content family: `snake_case` (`cru_menu_group`, `create_and_deactivate_meal_plan`)
- consumer family: `lowerCamelCase` `verify…`/`create…` (`verifySuccessListGroupOrders`,
  `createGOFailureForClosedResto`)

### Assertions

| style | files | when |
|---|---|---|
| hard `org.testng.Assert` | 339 | **default** |
| Google Truth `assertThat` | 71 | local convention inside `tests/content/**` only |
| `SoftAssert` | 20 | rare; `protected SoftAssert softAssert` exists on the base, re-created per method |

### Body shape (AAA, no comment banners)

1. **Arrange** — read ids/tokens off inherited ThreadLocals (`customer_aep.get().getUserId()`,
   `.getBearerToken()`) or `poolingUtility.getTDPCustomer(...)`; build the payload with the
   inherited `<Domain>RequestBodyBuilder`.
2. **Act** — one inherited-controller call.
3. **Assert** — `Assert.assertEquals(...)` on business fields, or a static
   `<Response>.assert<X>(response)`.
4. **Cleanup** — inline at method end (e.g. `groupOrderController.leaveGroupOrder(...)`), on top of
   the base class `@AfterMethod`.

### Pooled test data

`@FoodTestDataManager(...)` is an **annotation** (`gofood/src/main/java/testdata/FoodTestDataManager.java:10`
— `public @interface`), not a manager class. `GoFoodTestBase.setUpBeforeMethod(Method)` reads it
reflectively to lease a pooled customer/driver into `customer_aep` / `driver_aep`, and
`@AfterMethod` releases them. Add it when your test needs a real pooled consumer.

There is **no class named `RequestBodyBuilder`** — only per-domain
`requestbodybuilders/<domain>/<Domain>RequestBodyBuilder.java` (static methods).

### Secrets and TLS — two patterns not to imitate

1. **`gofood/.run/gofood-sample-test-run-using-local-jar.run.xml` is git-tracked and carries
   `FORTKNOX_TOKEN` and `REPORT_PORTAL_API_TOKEN` env entries.** Do not add tokens to `.run/` files,
   and do not copy that file as a template for a new run configuration. Read secrets from the
   environment or Fortknox at runtime:
   `// TODO: Securely load this value from an environment variable or secrets vault. Do not hardcode.`
   If you notice a committed token while working, report its **path only** to the user so it can be
   rotated — never quote the value.
2. **`GoFoodTestBase` calls `relaxedHTTPSValidation()`, which disables TLS verification JVM-wide** for
   every test that extends it (~280 classes). That is existing behaviour you inherit; do not add
   further `relaxedHTTPSValidation()` calls, and never rely on it for a new host — fix the trust
   store instead.

### Compile check

```
./gradlew :gofood:compileTestJava
```
