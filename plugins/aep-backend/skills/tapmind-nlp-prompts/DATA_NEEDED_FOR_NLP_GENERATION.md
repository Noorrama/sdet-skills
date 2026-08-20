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
| Step curl (optional) | `…step_descriptions[].curl_reference` | intent hint |
| Scenario curl (preferred) | `automation_scenarios[].curl_reference` | FIX-scoped API shape |
| Endpoint | `…endpoint` | ingest / pin |
| PDG / service | `…module` / `…service_name` | §3.6 + MCP `productGroup` / `targetServiceId` |
| Class / method | `…package` / `…test_class` / `…method_name` | suite convert |
| Description | `…description` | `@Test(description = …)` |
| Tags | `…tags[]` | skip / provisional / negative / poll |
| Fixtures | `…test_data[]` | memory / secrets phrasing |
| Suite groups | plan/context `groups` (else derive carefully from tags) | `@Test(groups = …)` |
| TestInfo | plan/context `test_info` / suite registry | `@TestInfo(countryName, projectId, suiteId, testCaseIds, owner)` |
| Response field shape | **Often missing** | §3.1 vs §3.3 — flag, don't guess |
| Bound memory keys | Derived by walking prior `save … as X` | §4 |
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
| Verify | `tapmind_verify_prompt` | **full** `prompts: string[]` per scenario |
| Execute | `tapmind_run_nlp_command` | **one** command per call; reuse `conversationId` |
| Ingest | `tapmind_ingest_curl` | when verify finds no matching API |
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
