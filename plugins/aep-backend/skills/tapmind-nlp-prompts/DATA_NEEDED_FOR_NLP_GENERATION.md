# NLP Step Generation — Data Needed & Skill Changes

Scope: `tapmind-nlp-prompts` generation / verify / suite-convert modes.
Primary input is **`automation_plan.json`** (carries `step_descriptions` from sdet_plan
plus class/method/service/fixture fields). `sdet_plan.json` alone is a fallback.

See `SKILL.md` §G and `GENERATION.md` for the runtime pipeline.

## Why

`tapmind-nlp-prompts` used to be a human reference only. Goal: go from automation
suite scenario data → real `runStep`/`assertStep` prompts → batch verify → sequential
run → suite Java with `@Test` / `@TestInfo`.

## Data needed per scenario

| Data | Preferred source | Grammar / suite use |
|---|---|---|
| Action text | `automation_scenarios[].step_descriptions[].action` | §3.1 action |
| Expected result | `…step_descriptions[].expected_result` | §3.1 verify / §3.4 |
| Step order | `…step_descriptions[].step` | first-touch vs verify-only |
| Step curl (optional) | `…step_descriptions[].curl_reference` | intent hint; grpcurl → §3.8 |
| Scenario curl (preferred) | `automation_scenarios[].curl_reference` | FIX-scoped API shape or grpcurl |
| gRPC rpc_alias | `GET /v1/grpc/targets` (host:port match) or `# alias:` in curl | §3.8 `rpc_alias:` |
| gRPC service / method | grpcurl last arg `Service/Method` | §3.8 `service:` / `Method:` |
| gRPC request body | grpcurl `-d` JSON | §3.8 `request:` |
| Static proto (no reflection) | `GET /v1/grpc/static-proto/aliases` | invoke-time schema for alias |
| Endpoint | `…endpoint` | ingest / pin |
| PDG / service | `…module` / `…service_name` | §3.6 + MCP `productGroup` / `targetServiceId` |
| Class / method | `…package` / `…test_class` / `…method_name` | suite convert |
| Description | `…description` | `@Test(description = …)` |
| Tags | `…tags[]` | skip / provisional / negative / poll |
| Fixtures | `…test_data[]` | memory / secrets phrasing |
| Suite groups | plan/context `groups` (else derive carefully from tags) | `@Test(groups = …)` |
| TestInfo | plan/context `test_info` / suite registry | `@TestInfo(countryName, projectId, suiteId, testCaseIds, owner)` |
| Response field shape | **Often missing** | §3.1 vs §3.3 — flag, don't guess |
| Bound memory keys | Derived by walking prior `save … as X` / `saveMemory` | §4 — reference as `saved X`, not `${memory.X}` |
| Secrets | Not in schema | §7 `saveMemory` from env |

## Suite annotation contract

Emit:

```java
@Test(description = "…", groups = {"…"})
@TestInfo(countryName = "…", projectId = "…", suiteId = "…", testCaseIds = {"…"}, owner = "…")
```

Never invent BrowserStack/TestRail IDs. Empty owner → `owner = ""`.

## MCP usage

| Phase | Tool | Shape |
|---|---|---|
| gRPC alias lookup | Control plane `GET /v1/grpc/targets` | host:port → alias before §3.8 generate |
| gRPC static proto | Control plane `GET /v1/grpc/static-proto/aliases` | when target has reflection disabled |
| Verify | `tapmind_verify_prompt` | **one** `prompt` string per call, looped in list order (backend `/v1/runs/verifyPrompt` supports a `prompts[]` batch; exposed tool doesn't yet) |
| Execute | `tapmind_run_nlp_command` | **one** command per call; reuse `conversationId` |
| Execute (gRPC direct) | `grpc_invoke` | same fields as §3.8 (`rpcAlias`, `service`, `method`, `request`) — used by planner behind §3.8 NLP |
| Ingest | `tapmind_ingest_curl` | when verify finds no matching REST API |
| Side-check | `postgres_query` / `redis_get` / `invoke` | infra expected_results |

## Schema / ownership notes

- `automation_plan.schema.json` now includes `service_name`, `module`, `curl_reference`, etc. Prefer it over older gap notes.
- Response typing / explicit memory registry still absent upstream — skill flags instead of guessing.
- Whether `test-code-generator` consumes `nlp_suite_tests.json` or calls this skill inline is an integration decision outside this skill's grammar docs.

## Skill files in this folder

| File | Role |
|---|---|
| `SKILL.md` | Grammar §§0–10 + generation modes §G |
| `GENERATION.md` | Full generate → verify → run → suite-convert pipeline |
| `DATA_NEEDED_FOR_NLP_GENERATION.md` | This field map |
