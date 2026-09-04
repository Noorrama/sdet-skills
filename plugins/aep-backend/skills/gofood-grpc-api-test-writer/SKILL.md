---
name: gofood-grpc-api-test-writer
description: >-
  Use this skill when writing, adding, or extending gRPC backend automation tests in the gofood
  module of gojek-backend-tests — the OpenAPI / web-order surface under
  gofood/src/test/java/tests/expansion/openApi/**. Trigger it whenever the target is a gofood
  gRPC call: a grpcurl command, a gofood.consumer.v1 / gofood.portal.v1 service and method, a
  generated proto request such as OrderServiceOuterClass.GetOrderRequest, or a request naming
  OpenapiClient, OpenapiController, IGrpcServiceEndpoint, GRPCCurlBuilder, or GRPCCurlsBuilder.
  Do NOT use it for gofood REST work — that is gofood-api-test-writer — and do not use it for
  gopay gRPC, which is gopay-grpc-api-test-writer.
---

# gofood gRPC API Test Writer — OpenAPI / web-order surface

**Prerequisites:** `backend-automation/SKILL.md`, then
`backend-automation/references/grpc-transport-contract.md`. For the annotation contract,
`backend-automation/references/test-annotation-rules.md`. This file covers only the gofood gRPC
surface; the REST side of gofood — including most of the `openapi` package — is
`gofood-api-test-writer`.

## The surface is small and exactly enumerated

Ten endpoint classes. `serviceEndpoints/openapi/**` also holds ~40 **REST** classes, so folder
membership proves nothing — this table is the inventory.

| Endpoint | Interface | Curl builder | Security scan |
|---|---|---|---|
| `order/GetOrderEndPoint` | `restidioms…IGrpcServiceEndpoint` | `restidioms.security.utility.GRPCCurlBuilder` | **active** |
| `order/ListOrder/ListOrderEndPoint` | `restidioms…IGrpcServiceEndpoint` | `restidioms…GRPCCurlBuilder` | **active** |
| `discount/ListOffersEndPoint` | `restidioms…IGrpcServiceEndpoint` | `restidioms…GRPCCurlBuilder` | **active** |
| `order/CreateOrderEndPoint` | `utils.IGrpcServiceEndpoint` | `utils.GRPCCurlsBuilder` | commented out |
| `order/GetMaskedDriverNumberEndPoint` | `utils.IGrpcServiceEndpoint` | `utils.GRPCCurlsBuilder` | commented out |
| `outlet/GetOutletEndPoint` | `utils.IGrpcServiceEndpoint` | `utils.GRPCCurlsBuilder` | commented out |
| `outlet/ListOutletEndPoint` | `utils.IGrpcServiceEndpoint` | `utils.GRPCCurlsBuilder` | commented out |
| `outlet/SearchOutletEndPoint` | `utils.IGrpcServiceEndpoint` | `utils.GRPCCurlsBuilder` | commented out |
| `pricing/EstimateEndPoint` | `utils.IGrpcServiceEndpoint` | `utils.GRPCCurlsBuilder` | commented out |
| `cancelPortal/PortalCancellationEndPoint` | `utils.IGrpcServiceEndpoint` | `utils.GRPCCurlsBuilder` | commented out |

**Status of each pattern**

- `restidioms…IGrpcServiceEndpoint` + `GRPCCurlBuilder` + active security scan — **current**. Use
  for genuinely new endpoints.
- `utils.IGrpcServiceEndpoint` + `GRPCCurlsBuilder` + commented-out scan — **legacy but live**,
  7 of 10 endpoints. Do not migrate it. Do not "fix" the commented-out scan line.
- Streaming — **does not exist**. Every RPC here is unary. A streaming scenario is
  `NEEDS_REVIEW`.

## The layer chain

```
@Test (tests/expansion/openApi/**, extends base.GoFoodTestBase)
  → asserts/openApi/Assert*.java            (static, field-by-field on proto getters)
  → controllers/openapi/OpenapiController   (try/catch; success vs *WithException variants)
      → clients/openapi/OpenapiClient       (ONE ManagedChannel; a stub accessor per RPC)
          → serviceEndpoints/openapi/**     (implements one of the two IGrpcServiceEndpoint)
              → generated proto stub        (gofood.consumer.v1.*Grpc.newBlockingStub)
```

Proto request construction sits beside it, not in it:
`requestbodybuilders/openapi/*RequestBodyBuilder` — inherited on `GoFoodTestBase` as
`orderServiceRequestBodyBuilder`, `getPricingServiceRequestBodyBuilder()`, etc.

### The two interfaces differ in exactly one thing

`body()` — and `body()` is **for curl logging only**. The real RPC always sends the typed proto
message held as a field on the endpoint.

```java
// utils.IGrpcServiceEndpoint  (legacy)          // restidioms…IGrpcServiceEndpoint (current)
String url();                                    String url();
String host();                                   String host();
Metadata headers();                              Metadata headers();
String body();                                   RequestBody body() throws InvalidProtocolBufferException;
default Map<Object,Object> auth();
```

Current form:

```java
@Override
public RequestBody body() throws InvalidProtocolBufferException {
    return new RequestBody(GetOrderEndPoint.class, JsonFormat.printer().print(getOrderRequest));
}
```

`JsonFormat` is permitted **here and only here**. Using it to construct a request, or to read a
response, is forbidden.

### Endpoint shape (canonical: `GetOrderEndPoint`)

```java
public class GetOrderEndPoint implements IGrpcServiceEndpoint {
    private OrderServiceOuterClass.GetOrderRequest getOrderRequest;   // typed proto, kept as a field

    @Override public String url()  { return "gofood.consumer.v1.OrderService/GetOrder"; }
    @Override public String host() { return GoFoodProperties.openApiHost; }   // never a literal host

    @Override public Metadata headers() {
        Metadata header = new Metadata();
        header.put(Metadata.Key.of("api-client", Metadata.ASCII_STRING_MARSHALLER), "tokopedia-client");
        header.put(Metadata.Key.of("partner-user-id", Metadata.ASCII_STRING_MARSHALLER), partnerUserId);
        …
        return header;
    }
}
```

`url()` is the `package.Service/Method` identity — not an HTTP path. `host()` **must** come from
`GoFoodProperties`; the port (443) is fixed inside `OpenapiClient`, not in the endpoint.

### Client — one channel, a stub accessor per RPC

`OpenapiClient` builds a single `ManagedChannel` in its constructor:

```java
channel = NettyChannelBuilder.forAddress(GoFoodProperties.openApiHost, 443)
        .sslContext(GrpcSslContexts.forClient()
                .trustManager(InsecureTrustManagerFactory.INSTANCE).build())
        .build();
```

Each RPC gets an accessor returning a stub with metadata attached:

```java
public OrderServiceGrpc.OrderServiceBlockingStub getOrderStub(
        OrderServiceOuterClass.GetOrderRequest req, String location, String locale,
        String countryCode, String timeZone, String partnerUserId) {
    GetOrderEndPoint ep = new GetOrderEndPoint(req, location, locale, countryCode, timeZone, partnerUserId);
    new GRPCCurlBuilder(ep).logging("GetOrder");                 // pair with the interface
    GoFoodSecurityHelper.runSecurityScanIfRequiredForGrpc(ep);   // current pattern only
    return MetadataUtils.attachHeaders(OrderServiceGrpc.newBlockingStub(channel), ep.headers());
}
```

**Channel lifecycle:** the channel is created once per `OpenapiClient` and **never shut down** —
there is no `shutdown()` or `awaitTermination()` anywhere in gofood. That is the module's actual
behaviour. The rule that follows is: **never build a `ManagedChannel` in a test or a controller.**
Construct `OpenapiController` (which owns a client) and use its methods. Do not add a shutdown
call that no sibling has, and do not add per-test channels "to be safe" — that is the leak.

### Controller — success and failure are separate methods

```java
// success: returns the proto response; swallows exceptions and returns null
public OrderOuterClass.Order getOrder(…) {
    OrderOuterClass.Order orderResponse = null;
    try {
        orderResponse = openApiClient.getOrderStub(…).getOrder(getOrderRequest);
        Reporter.log("Get Order Response --- \n" + orderResponse.toString(), true);
        return orderResponse;
    } catch (Exception e) {
        Reporter.log("Exception Stacktrace " + e.getMessage(), true);
        return orderResponse;
    }
}

// failure: returns the gRPC status DESCRIPTION as a String
public String listOrderWithException(…) {
    try {
        …
        return listOrderResponse.toString();
    } catch (Exception e) {
        String errorMessage = null;
        if (Status.fromThrowable(e).getCode() == Status.INVALID_ARGUMENT.getCode()) {
            errorMessage = Status.fromThrowable(e).getDescription();
        }
        return errorMessage;
    }
}
```

Naming for failure variants is inconsistent and both forms are live: `*WithException`
(`estimateWithException`, `createOrderWithException`, `listOrderWithException`) and
`*WithErrorHandling` (`createOrderWithErrorHandling`, `getMaskedDriverNumberWithErrorHandling`,
`searchOutletWithErrorHandling`, `listOffersResponseWithErrorHandling`). **Match the sibling for
the service you are touching**; do not standardise.

**The success methods return `null` on failure rather than throwing.** A happy-path test that gets
a null back will fail with an unhelpful NPE. That is existing behaviour — do not "fix" it, but do
not write a negative test against a success method either: use the failure variant.

## Writing a negative test

Assert the **status description string** the controller returns. This is the live pattern:

```java
String res = openapiController.getMaskedDriverNumberWithErrorHandling(request, "123");
Assert.assertEquals(res, "customer unauthorized");
```

Never assert an HTTP status code. If the failure variant you need does not exist, add one to
`OpenapiController` modelled on the nearest sibling, gating on the specific
`Status.<CODE>.getCode()` the scenario expects. Never invent the description text — it must come
from a real observed response; if you don't have one, leave a `// TODO(agent-pm):` and say so.

## Test-class conventions

- `extends base.GoFoodTestBase`; construct `OpenapiController` in `@BeforeMethod`.
- One test class per RPC — `GetOrderTest`, `ListOutletTest`, `SearchOutletTest`,
  `GetMaskedDriverNumberTest`. A new RPC gets a new class in `tests/expansion/openApi/**`
  (`createorder/`, `estimate/`, `mpsTest/` are existing sub-packages by area).
- `@Test(groups = {GoFoodCategories.<constant>})` — live values here are
  `GOFOOD_EXPANSION_OPENAPI_TENCENT` and `GOFOOD_OPEN_API_SMOKE`. Never a raw string.
- `@TestInfo(projectId = TestRailConfig.GO_FOOD_PROJECT_ID, suiteId = TestRailConfig.OPEN_API,
  testCaseIds = {…}, owner = "first.last@gojek.com")` — present on essentially every test here.
  Never invent a TestRail id or an owner.
- `@FoodTestDataManager(needsNewDriver = true)` when the flow needs a pooled driver.
- Async settling uses Awaitility (`await().atMost(Constants.TIME_OUT, SECONDS)
  .pollInterval(Constants.POLLING_INTERVAL, SECONDS).until(…)`), re-reading through the controller
  inside the lambda. Not `Thread.sleep`.
- Assertions on proto responses go in `asserts/openApi/Assert*.java` as static methods taking the
  proto objects. Inline `Assert.assertEquals(response.getState().toString(), …)` also exists for
  small state checks — match the sibling.

## Building requests

Through the inherited builder, never by hand:

```java
OrderServiceOuterClass.GetOrderRequest req =
        orderServiceRequestBodyBuilder.getOrderRequest(createOrderResponse.getTenantUid(),
                                                       createOrderResponse.getNumber());
```

Inside a builder, nested messages are composed with generated builders
(`MoneyOuterClass.Money.newBuilder().setCurrencyCode(cc).setUnits(units).build()`). Adding a field
to an existing request means adding a `.setX(...)` in the builder method (or a new overload), not
constructing the proto in the test.

## Protos live in this repo

`gofood/src/main/proto/**`, managed by `buf` (`buf.yaml`, `buf.lock`, dep on
`buf.build/googleapis/googleapis`), compiled by the protobuf Gradle plugin — protoc `3.17.3`,
grpc-java `1.43.0` (`gofood/build.gradle`). Generated sources are added to the main source set.

**A new proto field is a proto change first.** Edit the `.proto`, rebuild so the generated class
carries the field, then use it. Never hand-edit anything under the generated output directory, and
never reference a field that the generated class does not have — it will not compile, which is the
correct outcome. Changing protoc/grpc versions is out of scope for a test task: flag it.

## Definition of Ready

- The RPC is identified as `package.Service/Method` plus request and response proto types.
- Those generated types exist and are reachable from `gofood/src/main/proto/**`.
- If extending an existing RPC, its endpoint class is identified, along with **which of the two
  interfaces** it implements.
- A real TestRail id and owner, or an explicit decision to leave a marked placeholder.

## Definition of Done

- `./gradlew :gofood:compileTestJava` passes.
- Request built via a `*RequestBodyBuilder`; response read via generated getters.
- Endpoint implements the same interface as its sibling, paired with the matching curl builder.
- Metadata via `Metadata.Key.of(…, ASCII_STRING_MARSHALLER)`; `host()` from `GoFoodProperties`.
- No new `ManagedChannel`; no channel shutdown added.
- Negative tests assert the gRPC status description, not an HTTP status.
- `@Test(groups=…)` uses a `GoFoodCategories` constant; `@TestInfo` fully populated.
- Summary states what was reused, extended, created, and every placeholder left.

## Reject / NEEDS_REVIEW

| Condition | Action |
|---|---|
| `unresolvable_proto_type` | The named request/response type does not exist in the generated sources. Reject — do not stub it. |
| Streaming RPC requested | No live streaming pattern exists in gofood. `NEEDS_REVIEW`. |
| Endpoint's interface ambiguous | The sibling uses neither interface, or both appear. Stop and ask. |
| New proto field not yet generated | Blocked on a proto change. Report; do not fabricate the field. |
| protoc / grpc-java version change needed | Out of scope for a test task. `NEEDS_REVIEW`. |

## Forbidden

- Building a request from JSON, or reading a response with Jackson / `deserialize(X.class)`.
- `JsonFormat` anywhere except `body()` curl logging.
- A handwritten request/response POJO when a generated proto type exists.
- Creating a `ManagedChannel` in a test, controller, or new client.
- Asserting an HTTP status code, or reusing a REST `RequestHandler`/`IServiceEndpoint` for a gRPC
  call.
- Migrating a `utils.IGrpcServiceEndpoint` endpoint to the newer interface, or uncommenting the
  dormant security-scan lines, as a side effect of an unrelated task.
- Hardcoding the OpenAPI host, port, or any credential.
- Inventing a proto message, field, RPC, enum value, error description, TestRail id, or owner.

## Compile check

```
./gradlew :gofood:compileTestJava
```
