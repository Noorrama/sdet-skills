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
