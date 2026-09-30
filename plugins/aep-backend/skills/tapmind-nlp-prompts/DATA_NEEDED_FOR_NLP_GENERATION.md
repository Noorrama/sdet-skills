# NLP Step Generation — Data Needed (both intake paths)

Scope: `tapmind-nlp-prompts` generate / verify / suite-convert. See `SKILL.md` §G,
`GENERATION.md`, `NLP_COVERAGE.md`, `CONTROL_PLANE.md`.

## Why

Intake (plan or artifact) → normalize steps → TDP decision → shared NLP core → suite Java.

## Path selection

| Path | Primary input | TDP source | Approval |
|---|---|---|---|
| **Plan-driven** | `automation_plan.json` | `test_data_output`, `test_buddy_prompt`, `test_data_payloads` | `status: approved` / `run.json` |
| **Artifact-driven** | Java `@Test`, BS steps, `sdet_plan`, single prompt | Infer from setup/code/curl | User intent |

After intake merges, **all rows below marked "Both"** apply identically.

## Data needed — plan-driven

| Data | Source | Use |
|---|---|---|
| Action / expected | `step_descriptions[]` | §3.1 execute (+ optional success) + **one** §3.4 detail verify-only |
| Scenario curl | `curl_reference` | FIX placeholders → `saved <field>` |
| Fixtures | `test_data[]` | TDP buddy prompt |
| Approval | `status`, `run.json` | Gate before generate |
| Plan dedup | `is_dedup` | Skip |
| TDP enrichment | `test_data_output`, `test_data_payloads` | `tdp_not_ready` skip |
| Class / method / PDG | plan fields | Suite convert |
| Suite meta | `existing_testcase_ids[]` + `browserstack_test_id` (no `countryName`/`projectId`/`suiteId`/`owner` on plan) | `@TestInfo.testCaseIds`; rest left empty |

## Data needed — artifact-driven

| Data | Source | Use |
|---|---|---|
| Target method | User path / `testCaseIds` | Coverage anchor |
| Steps | RestAssured, `@Step`, BS text, sheet | Normalize → action + expected; path-enrich via **`TESTCASE_TO_NLP.md`** |
| BrowserStack case | MCP `listTestCases` (+ `listFolders`) | Intake when source is TM, not a local file |
| Setup | `@BeforeMethod`, helpers, inline ids | TDP inference |
| PDG / service | package, existing `runStep(..., pdg, service)` | MCP pinning + `/v1/db/preview` |
| Ingested op match | `POST /v1/db/preview` | Confirm method/path exists for PDG |
| JSONPath bindings | `tapmind_verify_prompt` → `declared_bindings` | Rewrite `save X from response` → `save $.path as X` |
| Suite meta | **Existing class** | Preserve `@TestInfo` |
| Coded test body | Java file | Migration source; coded cross-check |

## Data needed — shared core (both paths)

| Data | Source | Use |
|---|---|---|
| gRPC rpc_alias | `GET /v1/grpc/targets` | §3.8 |
| REST targets | `GET /v1/targets` | Missing spec diagnosis |
| Static proto | `GET /v1/grpc/static-proto/aliases` | reflection off |
| Control plane host | `CONTROL_PLANE.md` | Registry + MCP |
| Existing NLP coverage | repo scan (`NLP_COVERAGE.md`) | exact_match / partial_match |
| Prompt grammar | SKILL.md §§2–10 | Generate |
| MCP verify / run | `tapmind_verify_prompt`, `tapmind_run_nlp_command` | Validate + execute |
| Shared helpers | `FIXTURE_REUSE.md` | Dedupe setup lines |

## MCP usage (two tools only — both paths)

| Phase | Tool |
|---|---|
| Verify | `tapmind_verify_prompt` |
| Execute | `tapmind_run_nlp_command` |

## HTTP usage (registry — both paths)

| Endpoint | Use |
|---|---|
| `GET /v1/grpc/targets` | gRPC alias map |
| `GET /v1/targets` | REST service map / missing op check |
| `GET /v1/grpc/static-proto/aliases` | Static proto |
| `POST /v1/db/preview` | Artifact path — confirm ingested op (`TESTCASE_TO_NLP.md`) |
| Swagger UI | Human-readable spec inventory |

**Do not** call ingest, database mutate, or cache controllers. Ingest only on explicit user request.

On connectivity failure → VPN message (`CONTROL_PLANE.md`).

## Skill files

| File | Role |
|---|---|
| `SKILL.md` | Grammar + §G dual paths |
| `GENERATION.md` | Pipeline fork/merge |
| `TESTCASE_TO_NLP.md` | BS / file intake + JSONPath enrichment → §G.B |
| `NLP_COVERAGE.md` | Path-specific gates + shared coverage scan |
| `FIXTURE_REUSE.md` | Shared helpers (both paths) |
| `CONTROL_PLANE.md` | MCP + Swagger (both paths) |
| `DATA_NEEDED_FOR_NLP_GENERATION.md` | This file |
