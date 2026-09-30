# Generation pipeline — two intake paths, one NLP core

Companion to `SKILL.md` §G. Control plane: `CONTROL_PLANE.md`. Coverage: **`NLP_COVERAGE.md`**.

## Intent vs tool routing

Prompt style is protocol-specific. REST uses plain intent (§3.1); gRPC uses §3.8 explicit
prefix; Redis/DB/Kafka use §3.5. See `SKILL.md` → **Intent vs tool routing**.

| Plan signal | Generation action |
|---|---|
| REST / HTTP (curl or OpenAPI-backed) | §3.1 execute (+ optional `\| verify: HTTP 2xx`) → **one** §3.4 detail verify-only |
| `curl_reference` starts with `grpcurl` | §3.8 invoke (+ optional `\| verify: status is OK`) → **one** detail §3.4 |
| Same gRPC/HTTP resource re-check | §3.4 verify-only (no new execute) |
| Poll / wait on gRPC/HTTP state | §3.2 — repeat full fetch; keep poll condition on fetch prompt |
| Redis / DB / Kafka | §3.5 prefixes only |
| Stub / call-log with no tool grammar | `NEEDS_REVIEW` |

Never rewrite a gRPC step into a fake REST prompt.

### Execute vs detail verify split (required)

For each happy-path API step, `prompts[]` must contain **at most 2** prompts:

1. **Execute** — action (+ `save … as`) + optional bare success `| verify: HTTP 2xx` / `status is OK`
2. **Detail** — **one** §3.4 verify-only with all field/business asserts from `expected_result`

**Forbidden:** `execute` → `Verify HTTP 2xx` → `Verify $.a` → `Verify $.b` (multiple verify-only).
Verify-only reuses `lastVerdict.executionTraces()` (`SyncRunPipeline`); chaining verify-only
after one execute is unreliable. See `SKILL.md` §3.1.1.

Negative expected status: execute, then **one** verify-only for error status/message.

## Pipeline

```
                         ┌── Plan: automation_plan.json (+ test_data_payloads)
  INTAKE (varies) ───────┤
                         └── Artifact: Java @Test / BS steps / sdet_plan / single prompt
                                    │
                    Plan gates ─────┤ status approved, tdp_not_ready, is_dedup
                    Artifact gates ─┤ infer TDP, unresolved_data_dependency
                    Path enrich ────┤ TESTCASE_TO_NLP.md (BS/file + declared_bindings)
                                    ▼
              SHARED CORE (both paths)
                                    │
         0a. NLP coverage scan → nlp_method_decisions.json
                                    │
         0b. GET /v1/grpc/targets (if grpcurl steps) — VPN on failure
                                    │
         1. Filter (exact_match / collision / deferred / skip / manual)
                                    │
         2. Generate prompts[] — grammar SKILL.md §§2–10
                                    │
         3. Sequential verify — tapmind_verify_prompt (one prompt per call)
                                    │  no REST op → NEEDS_REVIEW; GET /v1/targets
         4. Sequential execute — tapmind_run_nlp_command; reuse conversationId
                                    │  400 invalid_request_body → §8.1.1
         5. Suite convert — @Test / @TestInfo + runStep; FIXTURE_REUSE helpers
                                    │
         nlp_suite_tests.json + skipped[] (+ optional .java)
```

### Artifact path enrichment (before step 2)

When steps come from BrowserStack or a sheet and use path-less saves
(`save basetoken from response`), run **`TESTCASE_TO_NLP.md`** first:

1. Intake file or BrowserStack `listTestCases`
2. `POST /v1/db/preview` — confirm ingested op
3. `tapmind_verify_prompt` (`dryRunLlm: true`) — read `declared_bindings`
4. Rewrite to `save $.path as <name>` (e.g. `save $.data.base_token as basetoken`)
5. Continue shared core above

## 1. Scenario filter (path-aware)

Apply in order — first match wins:

| Condition | Path | Action |
|---|---|---|
| Not approved (`status` ≠ `approved`, no `run.json` `keep`) | Plan | Skip — `not_approved` |
| Required `{{FIX-…}}` unresolved | Plan | Skip — `tdp_not_ready` |
| `saved <key>` with no setup source | Artifact | Skip — `unresolved_data_dependency` |
| `is_dedup: true` | Plan | Skip — `is_dedup` |
| `exact_match` in `nlp_method_decisions` | Both | Skip — `exact_match` |
| `method_name_collision` | Both | Skip + `NEEDS_REVIEW` |
| `undecidable` | Both | Skip — `undecidable` |
| tag `deferred` / `skip` / `manual` | Plan | Skip |
| `partial_match` | Both | Delta prompts only; append-only convert |
| otherwise | Both | Full prompts + create or migrate |

## 2. Prompt generation rules (generic — both paths)

### Prefer scenario curl + fixtures (plan) or extracted curl (artifact)

- Plan: `{{FIX-xxx.fieldName}}` → **`saved fieldName`** after TDP/helper bind.
- Artifact: extract from RestAssured/coded test or step curl; same memory rules (§4).
- `module` → PDG; `service_name` → `targetServiceId` / `runStep(..., pdg, service)`.

### gRPC alias resolution (HTTP only — both paths)

1. `GET https://tapmind-backend-i.golabs.io/v1/grpc/targets` (integration) or `-q` (QA).
2. Match grpcurl host:port → alias.
3. Optional: `# alias: …` first line in `curl_reference`.
4. No match → `NEEDS_REVIEW: no rpc_alias for <host>:<port>`.
5. HTTP unreachable → VPN message (`CONTROL_PLANE.md`).

### Step classifier

| Signal | Form |
|---|---|
| grpcurl | §3.8 execute (+ optional `\| verify: status is OK`) → **one** detail §3.4 |
| HTTP curl / HTTP action | §3.1 execute (+ optional `\| verify: HTTP 2xx`) → **one** detail §3.4 |
| redis / kafka / db | §3.5 |
| Same resource re-check | §3.4 verify-only only |
| wait / poll | §3.2 with fetch (exception: assert may stay on poll fetch) |
| no TapMind grammar | `NEEDS_REVIEW` |

**Forbidden in generation:**
- Mega-prompt `action | verify: status + full body fields…`
- Multiple consecutive verify-only after one execute (§3.1.1)

### Memory & secrets

Walk prompts in order. Emit **`saved x`** — not `${memory.x}`. Unresolvable → flag.
Secrets: `saveMemory` first (§7).

## 3. Verify (sequential — MCP only — both paths)

Use **`tapmind_verify_prompt` only** (`CONTROL_PLANE.md`).

```json
{
  "prompt": "<prompts[i]>",
  "productGroup": "<module>",
  "targetServiceId": "<service_name>",
  "dryRunLlm": true
}
```

- Apply corrections → re-verify until clean or `NEEDS_REVIEW`.
- gRPC: verify §3.8 through this tool — not `grpc_invoke`.
- No matching REST op: `GET /v1/targets` via Swagger; flag missing spec — do not auto-ingest.

## 4. Execute (sequential — MCP only — both paths)

Use **`tapmind_run_nlp_command` only**. Reuse `conversationId`.

On `no tool_call.target` → `GET /v1/grpc/targets`. On `400 invalid_request_body` → §8.1.1.

## 5. Suite convert (both paths)

### Annotations

```java
@BeforeMethod(alwaysRun = true)
public void tapMindSetup(Method method) throws Exception {
    TapMind.setUp(method);
}

@Test(description = "…", groups = {"…", "TAPMIND"})
@TestInfo(countryName = "…", projectId = "…", suiteId = "…", testCaseIds = {"…"}, owner = "…")
public void <method_name>() throws Exception {
    // runStep / helper-call lines
}
```

- **Plan path:** fill `@TestInfo` from plan/suite context or empty.
- **Artifact path:** preserve existing `@TestInfo` when migrating.

### Line kinds

| kind | When |
|---|---|
| `direct-api` | `saveMemory`, non-NLP SDK setup |
| `helper-call` | `provision…();` / `create…();` / `fetch…();` |
| `step` | Scenario-specific `TapMind.runStep("…")` |
| `assert` | `TapMind.assertStep("…", "…")` |
| `guard` | Inserted from live run |

Batch convert: fingerprint prompts → `sharedHelpers[]` (`FIXTURE_REUSE.md`).

### Artifact: `nlp_suite_tests.json`

```json
{
  "epic_id": "<from plan or context>",
  "intake_path": "plan | artifact",
  "skipped": [],
  "scenarios": [
    {
      "scenario_id": "SC-…",
      "status": "generated | verified | executed | partial | skipped",
      "prompts": ["…"],
      "tapmindTest": {
        "source": {
          "kind": "automation_plan | coded_migration | browserstack_case | reference | sdet_plan",
          "scenarioRef": "…"
        },
        "lines": []
      }
    }
  ]
}
```

## 6. Definition of done (per target — both paths)

- [ ] `nlp_method_decisions.json` verdict recorded
- [ ] Path-specific intake gates passed (or documented skip)
- [ ] Happy-path API steps: execute (+ optional bare success) → **one** detail verify-only (§3.1.1)
- [ ] Artifact/BS path-less saves enriched (`TESTCASE_TO_NLP.md`) — no `save <field> from response` left
- [ ] No mega-prompt `action | verify: status + body fields…`
- [ ] No chain of multiple verify-only prompts after one execute
- [ ] `prompts[]` length matches runnable steps
- [ ] Verify pass or flags documented
- [ ] If executed: shared `conversationId`; memory refs resolve
- [ ] `@TestInfo` preserved (artifact) or honestly empty (plan)
- [ ] `tapmindTest.lines` are drop-in Java
- [ ] Skipped targets in manifest `skipped[]`
