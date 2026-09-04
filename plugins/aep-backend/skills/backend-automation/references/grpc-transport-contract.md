# gRPC transport contract and routing

The shared pipeline was built for REST. This file defines how a gRPC scenario travels through it
without being coerced into HTTP fields, and the small set of rules that are verified to hold for
**both** gRPC modules. Everything else is module-specific and lives in the module skill.

> Only two modules have a live gRPC test surface: `gopay` (`src/test/java/paymentTooling/**`) and
> `gofood` (`src/test/java/tests/expansion/openApi/**`). Their architectures are **materially
> different** — see "What is NOT common" below before assuming anything transfers.

## Deciding the transport

Answer in this order. Stop at the first definite hit.

| Signal | Verdict |
|---|---|
| The cURL/API doc is `grpcurl`, or names a `package.Service/Method` path | **gRPC** |
| The contract names a proto message type, or a `.proto` file / `*_proto` artifact | **gRPC** |
| The target path is `gopay/src/test/java/paymentTooling/**` | **gRPC** (gopay) |
| The target path is `gofood/src/test/java/tests/expansion/openApi/**` | **check** — this package holds REST *and* gRPC (see the gofood skill's inventory); resolve by the endpoint, not the folder |
| A plain `curl` with an HTTP verb, URL path and HTTP status | **REST** |
| Ambiguous | **Do not guess.** Grep for the service name in the module's `serviceEndpoints`/`clients`; if still unresolved, ask. A gRPC scenario generated as REST compiles and fails at runtime. |

**Presence of `.proto` files or generated stubs proves nothing.** A module can carry a full proto
build with zero live consumers (`scp` has 62 `.proto` files and no gRPC tests at all). Confirm a
real test-class consumer before treating a surface as live.

## Routing

| Module | Transport | Skill |
|---|---|---|
| `gopay` | REST / miniapp (`userJourneyTests/userspend/**`) | `gopay-api-test-writer` |
| `gopay` | gRPC (`paymentTooling/**`) | `gopay-grpc-api-test-writer` |
| `gofood` | REST | `gofood-api-test-writer` |
| `gofood` | gRPC (OpenAPI/web-order) | `gofood-grpc-api-test-writer` |
| any other module | either | no gRPC skill exists — do fresh discovery per `backend-automation`, and do not assume either module's shape transfers |

## The transport-aware scenario contract

A gRPC scenario carries these fields instead of the REST ones. Emit them in `rfc_context`,
`gbt_context`, `automation_plan` and `method_decisions` wherever a REST scenario would carry
`http_method`/`path`/`headers`/`request_dto`/`response_dto`/`http_status`.

```json
{
  "protocol": "grpc",
  "module": "gopay",
  "grpc_service": "fully.qualified.ServiceName",
  "rpc_method": "MethodName",
  "request_type": "fully.qualified.Request",
  "response_type": "fully.qualified.Response",
  "proto_reference": "path or dependency coordinate",
  "rpc_type": "unary",
  "expected_status": "OK"
}
```

**Field rules**

- `protocol` — `"grpc"` or `"rest"`. **Absent means `"rest"`**, so every existing REST plan keeps
  working unchanged. Never write `"protocol": "rest"` into an existing plan just to be explicit;
  absence is the backward-compatible default.
- `grpc_service` + `rpc_method` together are the endpoint identity, and they are what
  `gbt-context-builder` matches on. They replace `http_method` + `path` entirely.
- `request_type` / `response_type` — fully-qualified **generated** Java types. If you cannot name
  a real generated type, that is a reject (`unresolvable_proto_type`), not a TODO — a handwritten
  DTO standing in for a generated proto is a defect, not a placeholder.
- `proto_reference` — for `gofood`, the in-repo `.proto` path; for `gopay`, the Gradle artifact
  coordinate. The two modules source protos completely differently.
- `rpc_type` — `"unary"` only, unless the module skill documents a live streaming pattern. **No
  streaming pattern exists in either module today**; a streaming scenario is
  `NEEDS_REVIEW`, not something to improvise.
- `expected_status` — an `io.grpc.Status.Code` name (`OK`, `INVALID_ARGUMENT`, `NOT_FOUND`, …).
  Never an HTTP status number. Note that a non-OK status is not always how a module surfaces
  failure — read the module skill first.

**Never populate for a gRPC scenario:** `http_method`, `url`/`path`, HTTP `headers`,
`request_dto`, `response_dto`, `http_status`. A gRPC call has no URL path and no HTTP status; the
nearest equivalents are the service/method pair and the gRPC status code, and they are not
interchangeable.

## Rules verified to hold in BOTH modules

These are the only ones. Everything else differs.

1. **Requests are built with generated protobuf builders** —
   `X.newBuilder().setField(...).build()`. Never a handwritten POJO, never JSON parsed into a
   request.
2. **Responses are read through generated getters** — `response.getField()`,
   `response.getRepeatedList()`, `getXCount()`. Never Jackson, never `deserialize(X.class)`.
3. **Metadata is built with `Metadata.Key.of(name, Metadata.ASCII_STRING_MARSHALLER)`** and
   attached to the stub. REST header helpers and bearer-token conventions do not apply.
4. **Blocking stubs only.** Both modules use `newBlockingStub` exclusively; no async or future
   stub appears in any live test. Do not introduce one.
5. **Never hardcode a host, port, or credential.** Each module resolves these through its own
   config layer — different layers, same prohibition.
6. **Never edit generated protobuf sources**, and never invent a proto message, field, RPC, or
   enum value. If the field you need does not exist in the generated type, the proto has not been
   updated — that is a blocker to report, not something to work around.
7. **Reuse the existing client/connection object.** Neither module creates a channel per test.
8. **Search before creating.** An existing stub accessor, helper, or controller method for your
   RPC almost certainly exists; grep for the RPC name before adding a layer.

## What is NOT common — do not transfer between modules

| Concern | `gopay` | `gofood` |
|---|---|---|
| Channel | pooled, via `AbstractGrpcClientConnection` | one `ManagedChannel` per client object |
| Config | Figaro keys (Consul or direct) | `GoFoodProperties` + port 443 |
| Layers | Connection → Client → Helper → Assertions | Endpoint → Client → Controller → asserts |
| Failure surfacing | usually a populated error field on the response; sometimes `StatusRuntimeException` | controller returns the status **description string** |
| Proto source | published `com.gopay:*-proto` artifacts | in-repo `src/main/proto`, `buf`-managed |
| `@TestInfo` | on a minority of tests | on essentially all tests |
| Curl logging | `GopayLogger` request/response dump | two different `GRPCCurl*Builder`s, paired to the endpoint interface |

Read the module skill. Applying the other module's shape produces code that compiles and is wrong.
