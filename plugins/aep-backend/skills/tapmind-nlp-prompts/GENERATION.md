# Generation pipeline — automation_plan → suite TapMind test

Companion to `SKILL.md` §G. Follow this when producing runnable suite tests from
an automation plan (any feature — rules are schema-generic).

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
 3. Batch verify — tapmind_verify_prompt({ prompts, productGroup, targetServiceId, dryRunLlm })
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

- Scenario-level `curl_reference` uses `{{FIX-xxx.fieldName}}` — map to `${memory.fieldName}` after fixture bind / `saveMemory`.
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

### Memory

Walk prompts in order. Only reference `${memory.x}` if an earlier prompt has `save … as x` or setup called `saveMemory("x", …)`. Unresolvable placeholders → flag, do not invent names.

### Secrets

Never inline tokens/secrets into prompts. `saveMemory` from env / fixture first (§7).

## 3. Verify (batch)

```json
{
  "prompts": ["prompt 1", "prompt 2"],
  "productGroup": "<module>",
  "targetServiceId": "<service_name>",
  "dryRunLlm": true
}
```

- One call per scenario with the **full** list (planner sees sequence + memory names).
- Apply LLM/suggested rewrites into `correctedSteps` (`change: "reworded"`).
- Re-ingest curls via `tapmind_ingest_curl` when verify shows no matching operation.

If the MCP wrapper only accepts a single `prompt` string, call once per item **in list order** and merge results — prefer the real list API when available.

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
@Test(description = "…", groups = {"…"})
@TestInfo(countryName = "…", projectId = "…", suiteId = "…", testCaseIds = {"…"}, owner = "…")
public void <method_name>() {
    // lines from finalized prompts (+ setup / guards)
}
```

Do not invent `projectId` / `suiteId` / `testCaseIds`. Empty owner → `owner = ""`. Empty ids → `testCaseIds = {}` only if the suite annotation allows; otherwise omit IDs until known.

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
- [ ] Batch verify clean or residual flags documented
- [ ] If executed: one shared `conversationId`; memory refs resolve
- [ ] `@Test` description matches scenario intent
- [ ] `@TestInfo` only contains real suite IDs (or explicit empties)
- [ ] `tapmindTest.lines` are drop-in Java statements
