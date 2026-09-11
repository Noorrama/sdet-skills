---
name: gopay-grpc-api-test-writer
description: >-
  Use this skill when writing, adding, or extending gRPC backend automation tests in the gopay
  module of gojek-backend-tests — the payment-tooling surface under
  gopay/src/test/java/paymentTooling/** covering OMS, Boomerang, Emoney, PRS/PSRS/RPS, Citadel,
  clearing & settlement, points, VA, standing instructions and the Subscription Engine. Trigger it
  whenever the target is a gopay gRPC call: a grpcurl command, a com.gopay.* service and RPC, a
  generated proto request such as CreateWalletProfileRequest, or a request naming
  AbstractGrpcClientConnection, a *ClientConnection, a *ServiceClient, or a paymentTooling test
  base. Do NOT use it for gopay REST/miniapp work under userJourneyTests/userspend/** — that is
  gopay-api-test-writer — and do not use it for gofood gRPC, which is gofood-grpc-api-test-writer.
---

# gopay gRPC API Test Writer — paymentTooling surface

**Prerequisites:** `backend-automation/SKILL.md`, then
`backend-automation/references/grpc-transport-contract.md`.

**Also mandatory, and they live in the GBT repo:**
`gopay/.gitlab/skills/qa-intern/qa-intern.md` and `gopay/.gitlab/skills/qa-intern/MISTAKES_LOG.md`.
Read both before writing. `qa-intern.md` declares itself mandatory and routes to nine playbook
files under `playbooks/` — **none of those files exist on disk**; the directory contains only
those two `.md` files. Do not fabricate their content and do not silently route around the gap:
if a task turns on guidance that only a missing playbook would give, say so and mark it
`NEEDS_REVIEW`. The two files that do exist carry real, enforceable rules — several are
reproduced below because they bite hardest on gRPC work.

**The REST/miniapp architecture from `userJourneyTests/userspend/**` does not apply here.** No
`IServiceEndpoint`, no `RequestHandler`, no HTTP status. Different stack entirely.

## The layer chain

```
@Test (paymentTooling/<domain>/**, extends a per-domain test base)
  → assertions:  com.gopay.backendtests.assertions.**        (assert<X>(request, response))
  → helper:      com.gopay.backendtests.helpers.<domain>.*Helper
                   · build methods  → return the proto request
                   · execute methods → fire the RPC, return the proto response
      → client:  com.gopay.backendtests.clients[.<domain>].<Svc>Client
          → connection: <Svc>ClientConnection extends AbstractGrpcClientConnection<…BlockingStub>
              → pooled channel → generated blocking stub
```

All of `com.gopay.backendtests.**` is in-repo main source under `gopay/src/main/java/`.

### Connection — pooled, config-driven, never a raw channel

```java
public class <Svc>ClientConnection
        extends AbstractGrpcClientConnection<<Svc>Grpc.<Svc>BlockingStub> {

    public static ServiceConnectionPoolConfig getServiceConnectionPoolConfig() {
        ApplicationConfiguration config = Figaro.configure(new HashSet<>(asList(
                "CONSUL_CLIENT_HOST", "CONSUL_CLIENT_PORT",
                "<SVC>_NAME", "<SVC>_POOL_NAME", "<SVC>_GRPC_DEADLINE",
                "<SVC>_CONNECTION_POOL_SIZE", "<SVC>_CONNECTION_POOL_MIN_IDLE",
                "<SVC>_CONNECTION_POOL_MAX_IDLE", "CONSUL_OVERLOAD_THRESHOLD_PERCENT",
                "<SVC>_CONNECTION_POOL_MAX_WAIT_MILLIS",
                "<SVC>_CONNECTION_POOL_READ_MAX_WAIT_MILLIS")));

        ServiceConnectionPoolConfigBuilder builder = new ServiceConnectionPoolConfigBuilder()
                .setGrpcCallDeadline(config.getValueAsLong("<SVC>_GRPC_DEADLINE"))
                … pool sizing …;

        return config.getValueAsBoolean("<SVC>_SERVICE_USE_DIRECT_CONNECTION", false)
            ? builder.createDirectGrpcConnectionPoolConfig(poolName, host, port)     // direct
            : builder.createGrpcConsulConnectionPoolConfig(poolName, consulHost,     // default
                                                            consulPort, serviceName);
    }

    @Override
    protected <Svc>Grpc.<Svc>BlockingStub createStub(Channel channel) {
        return <Svc>Grpc.newBlockingStub(channel);
    }
}
```

Everything environment-specific — service name, host, port, deadline, pool sizing — is a **named
Figaro key**, resolved at runtime. **Never a literal host, port, or deadline in Java.** Service
discovery is Consul by default; `<SVC>_SERVICE_USE_DIRECT_CONNECTION` switches to a direct
host/port. Deadlines are configured on the pool (`setGrpcCallDeadline`), not per call with
`stub.withDeadlineAfter(...)` — no live code does the latter.

**Channel lifecycle is the pool's.** `connection.execute(...)` borrows and returns. Never build a
`ManagedChannel`, never call `shutdown()`, never hold a stub across calls.

### Client — metadata, execution, logging

```java
public static <Svc>BlockingStub stubWithHeaders(<Svc>BlockingStub stub,
                                                String requestId, String correlationId) {
    Metadata headers = new Metadata();
    headers.put(Metadata.Key.of("Request-ID", Metadata.ASCII_STRING_MARSHALLER), requestId);
    headers.put(Metadata.Key.of("Correlation-ID", Metadata.ASCII_STRING_MARSHALLER), correlationId);
    return stub.withInterceptors(MetadataUtils.newAttachHeadersInterceptor(headers));
}

public GenericResponse cancel(Order request, String requestId, String correlationId) {
    printLog("Cancel Request: " + request);
    try {
        GenericResponse resp = connection.execute(stub ->
                stubWithHeaders(stub, requestId, correlationId)).cancel(request);
        printLog("Cancel Response: " + resp);
        return resp;
    } catch (GrpcClientException e) {
        printLog("Received error: " + e.getMessage());
        return GenericResponse.newBuilder().setSuccess(false)
                .addErrors(0, GoPayErrors.Error.newBuilder().setCause(e.getMessage()).build())
                .build();
    }
}
```

Note `withInterceptors(MetadataUtils.newAttachHeadersInterceptor(...))` — gopay's form.
(gofood uses the older `MetadataUtils.attachHeaders(...)`; do not swap them.) `Request-ID` and
`Correlation-ID` are the common pair; per-service metadata varies — copy the sibling client.
Logging is `GopayLogger.log(getClass().getName(), msg)` dumping request and response.

### Two live failure shapes — pick by what the client does

This is the single most important thing to get right, and it is **per client**.

| Client behaviour | How the test asserts | Prevalence |
|---|---|---|
| Catches `GrpcClientException` and returns a synthesized error response | assert on the response's error fields — `getSuccess()`, `getErrorsList()`, or a domain assertion like `assertions.assertInvalidMerchantIdDefaultWalletCreationError(response)` | **dominant** — `GrpcClientException` appears in 51 files |
| Lets the exception propagate | `Assert.expectThrows(StatusRuntimeException.class, …)` then assert the status | 4 files, e.g. `paymentTooling/emoney/UserServiceTest` |

```java
// propagating form — live in UserServiceTest
StatusRuntimeException ex = Assert.expectThrows(StatusRuntimeException.class,
        () -> userServiceHelper.getWalletProfilesByWalletIdResponse(request));
assertEquals(ex.getStatus().getCode().value(), 5, "GRPC code mismatch");
assertEquals(ex.getStatus().getCode().name(), "NOT_FOUND", "GRPC error mismatch");
```

**Open the client before writing a negative test.** If it catches `GrpcClientException`, no
exception will ever reach your test and `expectThrows` will fail; if it propagates, asserting on
response fields will NPE. Never assert an HTTP status in either case.

## Test-class conventions

- `extends` the **per-domain** test base — `OMSTestBase`, `EmoneyTestBase`, `BaseSubscriptionTest`,
  `BaseRPS`, `BaseSubscriptionBatchProcessorTest`, `BaseStandingInstructionServiceTest`,
  `BaseRefundTest`, `TestBaseForPoints`. Use the one your domain's siblings use; it wires the
  helpers, country config and data providers.
- `@Test(groups = {Categories.<X>, TestFlow.<POSITIVE|NEGATIVE>, Cluster.<X>},
  description = "…")`. Groups are constants from `com.gopay.backendtests.utils.Categories`,
  `utils.analytics.TestFlow` and `…utils.Cluster` — never raw strings. Groups drive CI selection;
  a wrong group means the test never runs and never fails.
- **`@TestInfo` is optional on this surface** — 360 of 2021 `@Test` methods carry it (36 of 136
  files). This is a real exception to the repo-wide rule. Match the sibling class: if the class
  uses it, populate all four attributes with real values; if it does not, do not add it. Never
  invent a TestRail id or owner to satisfy the general rule.
- Per-test correlation ids are generated, not fixed:
  `requestId = "Automation-" + method.getName() + "-" + RandomStringUtils.randomAlphanumeric(6);`
  in `@BeforeMethod(alwaysRun = true)`.
- One test class per RPC/service area, following the domain package.

## Rules carried over from qa-intern (they bite hardest here)

- **MISTAKE-007 — assertion placement.** Domain-object assertions belong in an `*Assertion` class
  under `com.gopay.backendtests.assertions.**`; the test calls `assertion.assertXxx(...)`. Only
  preconditional sanity checks stay inline. Grep your new test for `Assert.`/`assertEquals`/
  `assertTrue` — every hit on domain state must move.
- **MISTAKE-016 — build vs execute.** A setup helper that constructs a request **returns the
  request**; a separate thin execute helper fires the RPC. Never bake the send into the builder —
  it blocks idempotency, amend, retry and duplicate-request scenarios that need to mutate and
  replay the same proto. Live shape: `userServiceHelper.createUserService(...)` returns
  `CreateWalletProfileRequest`; `userServiceHelper.createEmoneyWalletResponse(request)` sends it.
- **MISTAKE-015 — async waits.** `Thread.sleep` (and `@SneakyThrows` added to allow it) is
  forbidden for eventual state. Poll with the existing `retryPolicy(...)`/Failsafe helper, with
  **both the read and the assert inside** the retried block. Reuse the repo's helper; don't add
  your own.
- **MISTAKE-008 / 012 — helper duplication and placement.** Before adding a helper, check whether
  an existing one differs only in a navigation path (collapse to one parametric helper), and put
  shared setup in the shared service helper, not in a single test class.

## Protos come from published artifacts, not this repo

gopay depends on generated proto **jars**, pinned in `gopay/build.gradle`:

```gradle
implementation 'com.gopay:gopay-wallet-client-proto:9.17.0-RELEASE'
implementation 'com.gopay:citadel_proto:4.28.0-RELEASE'
…
force 'com.gopay:payment_provider_proto:7.62.0-RELEASE'   // in resolutionStrategy
```

grpc `1.53.0`, protobuf-java `3.21.0`, several coordinates pinned via `resolutionStrategy.force`.

**Proto version-update workflow.** Adding a field that a newer proto release contains means
bumping that artifact's version in `gopay/build.gradle` — and if the coordinate is under
`resolutionStrategy.force`, bumping it **there too**, or the force silently wins and your new
field stays absent. Only bump to a version you have verified exists in the artifact repository.
**Never guess a version string.** If you cannot verify it, stop and mark `NEEDS_REVIEW`. Bumping a
shared proto affects every consumer in the module, so call it out explicitly rather than folding
it into a test MR.

## Definition of Ready

- The RPC is identified as fully-qualified service + method, with request/response proto types.
- The generated types resolve from a declared `com.gopay:*proto` dependency.
- The owning `<Svc>Client` / `<Svc>ClientConnection` is identified — or its absence confirmed.
- **The client's failure behaviour is known** (catches `GrpcClientException` vs propagates).
- The domain test base and its `Categories`/`Cluster` constants are identified.
- `qa-intern.md` and `MISTAKES_LOG.md` have been read.

## Definition of Done

- `./gradlew :gopay:compileTestJava` passes.
- Request built by a helper **build** method returning the proto; execution separate.
- Response read via generated getters; domain assertions in an `*Assertion` class.
- Negative test matches the client's actual failure shape.
- No `ManagedChannel`, no `shutdown()`, no `Thread.sleep`, no literal host/port/deadline.
- Groups from real constants; `@TestInfo` matching the sibling class's convention.
- Summary lists reused / extended / created layers and every placeholder.

## Reject / NEEDS_REVIEW

| Condition | Action |
|---|---|
| `unresolvable_proto_type` | Type not present in any declared proto artifact. Reject — never stub it. |
| Client failure behaviour ambiguous | Client neither clearly catches nor clearly propagates. Stop and ask. |
| Missing playbook | Task depends on one of the nine absent `playbooks/` files. `NEEDS_REVIEW`. |
| Proto bump with unverified version | `NEEDS_REVIEW`. Never guess a `-RELEASE` string. |
| Streaming RPC requested | No live streaming pattern in gopay. `NEEDS_REVIEW`. |
| New Figaro key required | Config keys are environment-provisioned; adding one is not a test change. Report it. |

## Forbidden

- Applying the REST/miniapp stack (`IServiceEndpoint`, `RequestHandler`, HTTP status) here.
- Creating a `ManagedChannel` or calling `shutdown()` — the pool owns the channel.
- `stub.withDeadlineAfter(...)` — deadlines are pool config; no live code does this.
- A handwritten request/response DTO where a generated proto type exists.
- `Thread.sleep` as an async wait.
- Literal hosts, ports, deadlines, credentials, account ids, payment instruments, or wallet ids.
- Inventing a proto version, message, field, RPC, enum value, TestRail id, or owner.
- Editing generated protobuf sources, or anything under `gopay/src/generated/`.
- Copying gofood's gRPC shape (single channel, `attachHeaders`, JSON curl logging) into gopay.

## Compile check

```
./gradlew :gopay:compileTestJava
```
