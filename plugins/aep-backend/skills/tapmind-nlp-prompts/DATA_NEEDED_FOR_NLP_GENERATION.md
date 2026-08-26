# NLP Step Generation — Data Needed & Skill Changes

Scope: `tapmind-nlp-prompts` generation / verify / suite-convert modes.
Primary input is **`automation_plan.json`**. See `SKILL.md` §G, `GENERATION.md`, and
`CONTROL_PLANE.md`.

## Why

Go from automation scenario data → real `runStep`/`assertStep` prompts → MCP verify → MCP run
→ suite Java with `@Test` / `@TestInfo`.

## Data needed per scenario

| Data | Preferred source | Grammar / suite use |
|---|---|---|
| Action text | `automation_scenarios[].step_descriptions[].action` | §3.1 action |
| Expected result | `…step_descriptions[].expected_result` | §3.1 verify / §3.4 |
| Step order | `…step_descriptions[].step` | first-touch vs verify-only |
| Step curl (optional) | `…step_descriptions[].curl_reference` | grpcurl → §3.8 |
| Scenario curl (preferred) | `automation_scenarios[].curl_reference` | FIX-scoped HTTP or grpcurl |
| gRPC rpc_alias | HTTP `GET /v1/grpc/targets` on control plane host | §3.8 |
| gRPC service / method | grpcurl `Service/Method` | §3.8 |
| gRPC request body | grpcurl `-d` JSON | §3.8 `request:` |
| Static proto | HTTP `GET /v1/grpc/static-proto/aliases` | when reflection off |
| Control plane host | `environments[]` / user / tasks context | `CONTROL_PLANE.md` |
| PDG / service | `…module` / `…service_name` | MCP `productGroup` / `targetServiceId` |
| Class / method | `…package` / `…test_class` / `…method_name` | suite convert |
| Fixtures / tags / TestInfo | plan + suite context | as before |

## MCP usage (two tools only)

| Phase | Tool | Notes |
|---|---|---|
| Verify | `tapmind_verify_prompt` | One prompt per call; REST and gRPC §3.8 |
| Execute | `tapmind_run_nlp_command` | One prompt per call; reuse `conversationId` |

## HTTP usage (registry lookup — not MCP)

| Phase | Endpoint | Host |
|---|---|---|
| gRPC alias | `GET /v1/grpc/targets` | `tapmind-backend-i.golabs.io` or `-q.golabs.io` |
| Static proto | `GET /v1/grpc/static-proto/aliases` | same |
| REST targets | `GET /v1/targets` | same |
| Schema check | `POST /v1/verify/schema` | explicit validation only (§9) |

Swagger: `https://<host>/swagger-ui/index.html` — allowed controllers listed in
`CONTROL_PLANE.md`. **Do not** call ingest, database, or cache controllers.

On HTTP/MCP connectivity failure → ask user to connect to respective VPN and retry.

## Skill files

| File | Role |
|---|---|
| `SKILL.md` | Grammar + generation §G |
| `GENERATION.md` | Pipeline |
| `CONTROL_PLANE.md` | Hosts, Swagger, MCP vs HTTP, VPN |
| `DATA_NEEDED_FOR_NLP_GENERATION.md` | This field map |
