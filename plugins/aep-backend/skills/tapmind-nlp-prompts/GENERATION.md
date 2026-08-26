# Generation pipeline — automation_plan → suite TapMind test

Companion to `SKILL.md` §G. Follow this when producing runnable suite tests from
an automation plan (any feature — rules are schema-generic).

## Intent vs tool routing

Prompts are **protocol-agnostic intent**. Do not encode ingest type or MCP tool names in the
string. TapMind matches the ingested operation and selects the tool (`rest.invoke`,
`grpc.invoke`, redis, db, kafka, …). See `SKILL.md` → **Intent vs tool routing**.

| Plan signal | Generation action |
|---|---|
| REST / HTTP (curl or OpenAPI-backed) | Intent §3.1 / §3.4 — planner routes to `rest.invoke` when op is ingested |
| Redis / DB / Kafka | §3.5 prefixes only (TapMind requires them today as tool selectors) |
| gRPC (or any protocol **not** in planner `tools_catalog`) | Do **not** invent NLP grammar. Flag `NEEDS_REVIEW: no catalogued NLP tool for <protocol>`. Optional: side-path MCP `grpc_invoke` outside `runStep` |
| Stub / queue / call-log inspect with no tool | `NEEDS_REVIEW` — same honesty rule |

Never rewrite a gRPC step into a fake REST prompt just to make generation succeed.

## Pipeline

```
automation_plan.json
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

### Step classifier

| Signal | Form |
|---|---|
| Non-empty curl (or clear HTTP action) | §3.1 `<action> \| verify: <expected>` |
| Action mentions redis | §3.5 `Run redis …` |
| Action mentions kafka produce/consume | §3.5 kafka prefix |
| Action is DB row/table/query read | §3.5 `Run query … on DB '…'` |
| Same resource re-check, no new curl, prior step was HTTP fetch of it | §3.4 verify-only starter word |
| Wait / poll / drain queue (e2e/reliability) | §3.2 polling overload; must include fetch |
| Stub call-log / job-queue inspect with no tool grammar | Do not emit runnable prompt; `NEEDS_REVIEW` |
| gRPC / protocol not in planner catalog | Intent optional for humans; **no** invented `Run grpc …`; `NEEDS_REVIEW` (or direct MCP outside NLP) |

### Memory

Walk prompts in order. Only reference a key if an earlier prompt has `save … as x` or setup called `saveMemory("x", …)`. **Emit `saved x`** (or `as saved x` / `equals saved x` / `from the saved x`) — do **not** default to `${memory.x}` in generated prompts. Planner expands `saved x` → `${memory.x}` internally. Unresolvable placeholders → flag, do not invent names.

### Secrets

Never inline tokens/secrets into prompts. `saveMemory` from env / fixture first, then `saved <key>` in the prompt (§7).

## 3. Verify (sequential — one prompt per call)

The exposed `tapmind_verify_prompt` MCP tool takes a single `prompt` string, not a list —
it always wraps it as a one-element list before calling the backend, even though the
backend's own `/v1/runs/verifyPrompt` endpoint accepts a batch `prompts[]`. Call once per
prompt, in list order:

```json
{
  "prompt": "<prompts[i]>",
  "productGroup": "<module>",
  "targetServiceId": "<service_name>",
  "dryRunLlm": true
}
```

- Apply that call's `corrected_test_prompt` / `corrected_verify_prompt` into `correctedSteps` (`change: "reworded"`).
- `status: "NEEDS_CLARIFICATION"` + `clarifying_question` in the response → flag `NEEDS_REVIEW`, don't guess.
- Re-ingest curls via `tapmind_ingest_curl` when verify shows no matching operation.

If a batch overload (`prompts: string[]`) is ever exposed on the MCP tool, prefer it — one
call per scenario's full list lets the planner see the whole sequence + memory names at once.

## 4. Execute (sequential)

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

Optional side checks: `postgres_query` / `redis_get` / `invoke` when expected_result is infra and NLP cannot assert it — attach evidence; may insert a corrected step.

Failures → reword or insert setup (`change: "inserted"`) → re-verify affected prompts → continue with same conversation when possible.

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
