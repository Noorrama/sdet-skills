# Generation pipeline — automation_plan → suite TapMind test

Companion to `SKILL.md` §G. Control plane hosts, allowed HTTP APIs, and VPN rules:
`CONTROL_PLANE.md`.

## Intent vs tool routing

Prompt style is protocol-specific. REST uses plain intent (§3.1); gRPC uses §3.8 explicit
prefix; Redis/DB/Kafka use §3.5. See `SKILL.md` → **Intent vs tool routing**.

| Plan signal | Generation action |
|---|---|
| REST / HTTP (curl or OpenAPI-backed) | Intent §3.1 / §3.4 — planner routes to `rest.invoke` when op is ingested |
| `curl_reference` starts with `grpcurl` | §3.8 — resolve `rpc_alias` from `GET /v1/grpc/targets` (host:port match) |
| Same gRPC method re-check, no new request | §3.4 verify-only starter word |
| Poll / wait on gRPC state | §3.2 — must repeat full §3.8 fetch, not verify-only |
| Redis / DB / Kafka | §3.5 prefixes only (TapMind requires them today as tool selectors) |
| Stub / queue / call-log inspect with no tool | `NEEDS_REVIEW` — same honesty rule |

Never rewrite a gRPC step into a fake REST prompt just to make generation succeed.

## Pipeline

```
automation_plan.json
        │
        ▼
 0. If any grpcurl steps: GET https://<host>/v1/grpc/targets (host from CONTROL_PLANE.md)
    → host:port → rpc_alias map. On failure → VPN message; stop guessing.
    Optional: GET /v1/grpc/static-proto/aliases when reflection disabled
        │
        ▼
 1. Filter scenarios (skip is_dedup / deferred / skip / manual)
        │
        ▼
 2. Generate prompts[] for every step (grammar in SKILL.md §§2–10)
        │
        ▼
 3. Sequential verify — tapmind_verify_prompt({ prompt, productGroup, targetServiceId, dryRunLlm }), one call per prompt
        │  rewrites → update prompts[] → re-verify
        ▼
 4. Sequential execute — tapmind_run_nlp_command one prompt at a time
        │  step1 → capture conversationId → pass on steps 2…N
        ▼
 5. Suite convert — @Test / @TestInfo + TapMind.runStep / assertStep lines
        │
        ▼
   nlp_suite_tests.json  (+ optional .java snippets / report trace)
```

## 1. Scenario filter

| Condition | Action |
|---|---|
| `is_dedup: true` | Skip |
| tag `deferred` / `skip` / `manual` | Skip (record reason) |
| tag `provisional` / `underspecified` or expected_result contains `TBD` | Generate + mark assertions provisional; flag `NEEDS_REVIEW` on weak verifies |
| otherwise | Generate |

## 2. Prompt generation rules (generic)

### Prefer scenario curl + fixtures

- Scenario-level `curl_reference` uses `{{FIX-xxx.fieldName}}` — after fixture bind / `saveMemory`, reference as natural **`saved fieldName`** (not `${memory.fieldName}`).
- Step-level curl may still use `$ACCESS_TOKEN` / `{session_id}` — treat as intent only when scenario curl exists.
- `module` → PDG; `service_name` → `targetServiceId` / `runStep(..., pdg, service)`.

### gRPC alias resolution (HTTP only — not MCP)

Before generating §3.8 prompts, call control plane HTTP (see `CONTROL_PLANE.md`):

1. `GET https://tapmind-backend-i.golabs.io/v1/grpc/targets` (integration) or
   `GET https://tapmind-backend-q.golabs.io/v1/grpc/targets` (QA).
2. Parse grpcurl host and port from `curl_reference`.
3. Match to alias (exact host+port; respect `-plaintext` → tls false).
4. Optional override: first line `# alias: gami-orbit-grpc` in `curl_reference`.
5. If no match → flag `NEEDS_REVIEW: no rpc_alias for <host>:<port>`.
6. If HTTP unreachable / `INTERNAL_ERROR` → **Please connect to the respective VPN** and retry.

When `reflection_enabled: false`, read `GET /v1/grpc/static-proto/aliases`.

**Conversion alone does not need MCP** — grpcurl → §3.8 string is local + HTTP lookup.

### Step classifier

| Signal | Form |
|---|---|
| `curl_reference` starts with `grpcurl` | §3.8 `call mcp grpc grpc.invoke for rpc_alias: …` |
| Non-empty HTTP curl (or clear HTTP action) | §3.1 `<action> \| verify: <expected>` |
| Action mentions redis | §3.5 `Run redis …` |
| Action mentions kafka produce/consume | §3.5 kafka prefix |
| Action is DB row/table/query read | §3.5 `Run query … on DB '…'` |
| Same resource re-check, no new curl/request, prior step was HTTP or gRPC fetch | §3.4 verify-only starter word |
| Wait / poll / drain queue (e2e/reliability) | §3.2 polling overload; must include fetch (§3.1 or §3.8) |
| Stub call-log / job-queue inspect with no tool grammar | Do not emit runnable prompt; `NEEDS_REVIEW` |

### Memory

Walk prompts in order. Only reference a key if an earlier prompt has `save … as x` or setup called `saveMemory("x", …)`. **Emit `saved x`** (or `as saved x` / `equals saved x` / `from the saved x`) — do **not** default to `${memory.x}` in generated prompts. Planner expands `saved x` → `${memory.x}` internally. Unresolvable placeholders → flag, do not invent names.

### Secrets

Never inline tokens/secrets into prompts. `saveMemory` from env / fixture first, then `saved <key>` in the prompt (§7).

## 3. Verify (sequential — MCP only)

Use **`tapmind_verify_prompt` only** — one prompt per call (`CONTROL_PLANE.md`). Do not use
ingest MCP tools when verify shows no matching REST operation; flag `NEEDS_REVIEW` instead.

```json
{
  "prompt": "<prompts[i]>",
  "productGroup": "<module>",
  "targetServiceId": "<service_name>",
  "dryRunLlm": true
}
```

- Apply that call's `corrected_test_prompt` / `corrected_verify_prompt` into `correctedSteps` (`change: "reworded"`).
- `status: "NEEDS_CLARIFICATION"` + `clarifying_question` → flag `NEEDS_REVIEW`, don't guess.
- gRPC: verify §3.8 prompt through this same MCP tool — not `grpc_invoke`.

If a batch overload (`prompts: string[]`) is ever exposed on the MCP tool, prefer it.

## 4. Execute (sequential — MCP only)

Use **`tapmind_run_nlp_command` only** — one prompt per call. gRPC §3.8 prompts execute here;
the planner routes to `grpc.invoke` internally.

```json
{
  "command": "<prompts[i]>",
  "pdg": "<module>",
  "targetServiceId": "<service_name>",
  "conversationId": "<from previous step, omit on first>"
}
```

| Step | conversationId |
|---|---|
| First | omit / null — capture id from response |
| Later | **must** pass the same id |

On `no tool_call.target` or gRPC routing errors → `GET /v1/grpc/targets` over HTTP; if alias
missing, flag `NEEDS_REVIEW` (target registration is admin/user action).

On HTTP **`400 invalid_request_body`** (or similar validation errors) after a create/update
prompt that used indexed body overrides (`array[i].field = …`):

1. Inspect the executed **request body** from the run result / control-plane log.
2. If the object only contains the fields the prompt named (sparse body), apply **SKILL.md
   §8.1.1** — name required sibling constants (e.g. `channel`) or switch to whole-object
   phrasing. Do **not** first assume `saved <key>` failed when values are already substituted.
3. `tapmind_verify_prompt` PASS is **not** sufficient proof the body is complete; body_defaults
   merge gaps only appear at execute time.

Failures → reword or insert setup (`change: "inserted"`) → re-verify → continue with same
`conversationId` when possible. Do not call postgres/redis/ingest MCP tools as workarounds.

## 5. Suite convert

### Annotations (exact shape)

```java
@BeforeMethod(alwaysRun = true)
public void tapMindSetup(Method method) throws Exception {
    TapMind.setUp(method); // PDG from PDG env (CI); tapmind.pdg property only if env unset
}

@Test(description = "…", groups = {"…", "TAPMIND"})
@TestInfo(countryName = "…", projectId = "…", suiteId = "…", testCaseIds = {"…"}, owner = "…")
public void <method_name>() throws Exception {
    // TapMind.runStep lines only — do not repeat setUp(String testId) when BeforeMethod uses setUp(method)
}
```

Do not invent `projectId` / `suiteId` / `testCaseIds`. Do **not** duplicate BS case ids in
`TapMind.setUp("<bs-case-id>")` when `@TestInfo(testCaseIds=…)` is already present unless
traceability in TapMind logs is explicitly required (see SKILL.md §1.1). Use ids from the target
suite only — never copy case ids from another module's tests.
Empty owner → `owner = ""`. Empty ids → `testCaseIds = {}` only if the suite annotation allows; otherwise omit IDs until known.

### Line kinds

| kind | When |
|---|---|
| `direct-api` | `saveMemory`, TDP helpers, non-NLP SDK setup |
| `step` | `TapMind.runStep("…")` |
| `assert` | `TapMind.assertStep("…", "…")` |
| `guard` | Inserted conditional / interruption handling from a live run |

### Artifact: `nlp_suite_tests.json`

```json
{
  "epic_id": "<from automation_plan>",
  "scenarios": [
    {
      "scenario_id": "SC-…",
      "status": "generated | verified | executed | partial | skipped",
      "prompts": ["…"],
      "correctedSteps": [],
      "tapmindTest": {
        "package": "…",
        "className": "…",
        "methodName": "…",
        "description": "…",
        "groups": ["\"…\""],
        "testInfo": {
          "countryName": "…",
          "projectId": "…",
          "suiteId": "…",
          "testCaseIds": [],
          "owner": ""
        },
        "source": {
          "kind": "automation_plan",
          "scenarioRef": "SC-…",
          "requirementRef": "…"
        },
        "lines": []
      },
      "flags": []
    }
  ]
}
```

Report skill (separate) can render PAM-style `trace.json` / `report.html` from execute evidence + this artifact.

## 6. Definition of done (per scenario)

- [ ] `prompts[]` length matches runnable steps (non-NEEDS_REVIEW)
- [ ] Verify pass (per-prompt calls) clean or residual flags documented
- [ ] If executed: one shared `conversationId`; memory refs resolve
- [ ] `@Test` description matches scenario intent
- [ ] `@TestInfo` only contains real suite IDs (or explicit empties)
- [ ] `tapmindTest.lines` are drop-in Java statements
