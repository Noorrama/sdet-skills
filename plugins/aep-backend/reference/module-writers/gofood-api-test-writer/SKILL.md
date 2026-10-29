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

**Prerequisite:** read `backend-automation/SKILL.md` first if you haven't already this task — it
defines the common module-identification, local-framework-discovery, search-before-create,
never-invent-data, and compile-check workflow. This file only covers what's specific to gofood on
top of that. Also read `backend-automation/references/extending-an-existing-api.md` when the cURL
targets an endpoint that already has tests, and
`backend-automation/references/environment-specific-test-data.md` before adding any test-data id.

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
  exist and are common in the older content/merchant areas (e.g.
  `MerchantOperationalHoursTests.RESTAURANT_ID`). **Do not read that as licence to add one.** It is
  the weakest of the module's test-data mechanisms — check the four below first, and never invent
  a UUID that doesn't exist in the target environment.
- Pooled dynamic customer/driver data via the `testdata.FoodTestDataManager` annotation
  (`needsNewDriver`, `needsGopayCustomer`, etc.) processed in `GoFoodTestBase.setUpBeforeMethod`.

### Environment-specific ids — four mechanisms coexist, check the feature area

gofood resolves environment-dependent test data four different ways. Find which one your feature
area uses **before** writing a constant; read
`backend-automation/references/environment-specific-test-data.md` for the general rule.

| Mechanism | Where | Use for |
|---|---|---|
| Interface + per-environment impls | `src/main/java/constants/` — `I<Domain>Constants` + `<Domain>ConstantsQa`/`<Domain>ConstantsInt` behind a `<Domain>Constants` holder that switches on `System.getenv("INFRA")` (default `qa`; `tencent`/`integration`/`staging` → Int) | provisioned entity ids in the feature areas that have it |
| Env properties | `src/main/resources/{qa,integration,config}.properties` via `commons.PropertiesReader` / `GoFoodProperties` | hosts and service URLs, always |
| Env-keyed test data | `utils/gofood_testdata_env/**` | the dine-in / conversion / openAPI areas |
| Runtime pooling | `@FoodTestDataManager`, `poolingUtility.getTDPCustomer(...)` | customers and drivers — no constant at all |

Where a `<Domain>Constants` holder exists, its own contents show the split you must preserve:
plain literals for enum/protocol values, locales, country and app-version headers, and
deliberately-invalid ids (`"abcd"`-style) that resolve nowhere by design; `ENVIRONMENT_CONSTANTS.getX()`
for every provisioned id. Adding a provisioned id means a getter on the interface **and** an
implementation in **both** the `…Qa` and `…Int` classes — missing one is a compile error, which is
the point. If the value isn't provisioned yet, the placeholder and the `// TODO:` go in the
per-environment classes; the public constant name stays clean, never `DUMMY_`/`TODO_`.

Don't carry one feature area's mechanism across to another that doesn't use it.

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

`GROUP`, `PROJECT` and `SUITE` below stand in for the real constant names — substitute them from
the tables in this section.

```java
@Test(groups = {GoFoodCategories.GROUP}, description = "<human-readable intent>")
@TestInfo(projectId = TestRailConfig.PROJECT, suiteId = TestRailConfig.SUITE,
          testCaseIds = {"<real id>"}, owner = "first.last@gojek.com")
public void verifySomething() {}
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

### Fixture setup from enriched plan (`test_data_output`)

Cross-module rules: `reference/fixture-acquisition-from-tdi/SKILL.md`. Gofood-specific:

Codegen reads TDI output on each `test_data[]` entry. Use **status**, not class defaults:

| `test_data_status` | Generated setup |
|---|---|
| `TDP_SUPPORTED` | **AEP pool** — `foodTestDataController.setAEPPoolCustomer(CustomerType.<enum>)` where the enum matches `test_data_details.tdp_test_data_category` (same pattern as `MafCashierSettlementTest`, `NonMafVoucherTest`, …). Optional: `@FoodTestDataManager(needsGopayCustomer = true)` only when siblings use that for the same category. |
| `TESTBUDDY_SUPPORTED` · `TESTBUDDY_HYBRID_FALLBACK` · `TESTBUDDY_OPERATION_FALLBACK` | When `test_buddy_prompt` is non-null: **TDP2 NLP** — `TDP2Request` + `TDP2Controller.getTDP2Response(req)` with `req.setMessage(test_buddy_prompt)`, `req.setClient("GoFood")`, and `conversationId` as in `OrderHistoryTests` / `GetTenantOrderTests`. For **hybrid**, run pool first if `tdp_test_data_category` is set, then TDP2. Bind `TDP2Response` into `customer_aep` / bearer fields the test already uses (see OpenAPI expansion tests). |
| `TDP_PARTIAL` / `TDP_NOT_SUPPORTED` | Pool and/or TDP2 only for the served portion; `TODO(agent-pm)` for gaps — do not use vanilla `customer_aep.get()` as a silent substitute. |

Imports: `testdatapool.tdp2.controller.TDP2Controller`, `testdatapool.tdp2.request.TDP2Request`,
`testdatapool.tdp2.response.tdp2response.TDP2Response` (match the import path used in the
nearest sibling file — gofood tests vary slightly by package).

### Test-class placement — one endpoint, one class

gofood follows the repo-wide convention strictly: each feature folder under `tests/**` holds one
test class per endpoint, named for that endpoint. A new endpoint gets a new class beside its
siblings, even when a closely-related class sits in the same folder — a different path (or the
same path with a different method) is a different endpoint. Needing a resource another class
creates is not a reason to live in that class: create it in your own method through the inherited
controller, as the sibling classes already do, and clean up inline at method end.

### Request-body DTOs — class-level Lombok, no hand-written constructor

Request bodies here are `@Getter @Setter @Builder` at class level, fields in raw snake_case, plus
`@JsonInclude`/`@JsonIgnoreProperties` where needed. Some older ones *also* carry a hand-written
constructor that happens to match the all-args signature. **Adding a field to one of those breaks
that coincidence** — Lombok's class-level `@Builder` only generates an all-args constructor when
none is declared. Delete the hand-written constructor (check `rg 'new <Class>\(' gofood/src` first;
these usually have zero callers) rather than demoting `@Builder` onto a new constructor. Both code
shapes are in `backend-automation/references/extending-an-existing-api.md`.

When adding an *optional* field to a DTO existing tests already use, add
`@JsonInclude(JsonInclude.Include.NON_NULL)` in the same change — otherwise every existing caller
starts sending `"your_field": null`.

### Failure-path controllers pin one status — check it before reusing

The `*Failure` methods on gofood controllers hardcode one expected status per method. If your
scenario expects a different status — a new validation path returning 400 where the method pins
422, say — add an overload taking the expected status. Do not loosen the existing assertion into
`assertTrue(a || b)`; several methods in this module already do that, and it lets a test expecting
400 pass on a 404. Treat those as a wart to avoid, not the convention to copy.

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
