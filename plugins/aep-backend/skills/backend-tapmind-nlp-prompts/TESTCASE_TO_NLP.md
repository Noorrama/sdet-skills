# Test case → NLP steps (path enrichment)

Companion to `SKILL.md` §G.A.2. Use when intake is a **source file** (sheet / CSV /
coded steps) or **BrowserStack Test Management** case, and steps need rewriting into
TapMind NLP — especially vague field language without JSONPath.

After enrichment, continue with shared core **`SKILL.md` §G.B** (coverage → generate →
verify → run → suite convert). Grammar: §§2–10. Control plane: `CONTROL_PLANE.md`.

## When to use

| Trigger | Example |
|---|---|
| Convert BS / sheet case to NLP | "convert this BrowserStack case to TapMind steps" |
| Vague save / extract | `save basetoken from response` |
| `@TapmindAutoMode` prep | Steps must be NLP-ready before BS-driven execute |
| Artifact path without plan | CSV / Java / `sdet_plan` steps only |

**Not** for plan-driven batch from enriched `automation_plan.json` (use §G.A.1) unless a
step still has a path-less save.

## Pipeline

```
  Source file  ─┐
                ├─► normalize steps ─► path enrich ─► prompts[] ─► §G.B
  BrowserStack ─┘         │                  │
                          │                  ├─ POST /v1/db/preview (op match)
                          │                  └─ tapmind_verify_prompt → declared_bindings
                          └─ action + expected_result
```

## 1. Intake

### 1.1 Source file

Accept any of:

| Format | Fields to read |
|---|---|
| CSV / sheet | `Id`/`Title`/`Preconditions`/`Steps`/`Expected Result` (BS pre-upload shape) |
| Markdown / text | Numbered steps + expected results |
| Java `@Test` | RestAssured / `@Step` / comments — same normalize rules as §G.A.2 |
| `sdet_plan` / `step_descriptions` | `action` + `expected_result` |

Normalize each row to:

```json
{ "n": 1, "action": "<raw step text>", "expected_result": "<raw expected or empty>" }
```

### 1.2 BrowserStack Test Management

1. Resolve `project_identifier` (`PR-*`). If unknown → BrowserStack MCP
   `askBrowserStackAI` (product `tm`) for projects, then `listFolders` if scoping by folder.
2. `listTestCases` with `project_identifier` (+ optional `folder_id`, filters, page `p`).
3. Pick case(s) by id / name the user named. Read **steps** + **expected results** +
   preconditions from the case payload (same conceptual columns as the sheet).
4. Set `tapmindTest.source.kind` → `"browserstack_case"` and
   `scenarioRef` → BrowserStack case id.
5. Propagate id into `@TestInfo.testCaseIds` on suite convert — do not invent other suite
   meta.

Do **not** use the BrowserStack **AI Prompt** column as step source for `@TapmindAutoMode`
— that mode runs **Steps** as `TapMind.runStep(step)` (`SKILL.md` §1.3).

## 2. Detect vague field language

A clause needs path enrichment when it saves or asserts a field **without** a `$.…` path
(and without a valid `entry where` array bind).

| Vague (rewrite) | Already NLP-ready (keep) |
|---|---|
| `save basetoken from response` | `save $.data.base_token as basetoken` |
| `save basetoken as basetoken` | `save token from the payment_options entry where …` |
| `extract accessToken from the response` | `Verify $.success is true` |
| `verify status is success` (field sense unclear) | `Verify HTTP 2xx` / `Verify status is 200` |

Patterns (case-insensitive):

- `save <field> from (the )?response`
- `save <field> as <name>` with no `$`
- `extract <field> (from …)?`
- `get <field> from (the )?response`
- verify of a body field by bare name when the API envelope is nested (`data.` / `body.`)

**Do not guess** scalar `save $.path` vs `entry where` when shape is unknown — resolve via
§3, else `NEEDS_REVIEW`.

## 3. Resolve JSONPath (priority order)

Need `productGroup` (PDG) and preferably `targetServiceId` before calling control plane.

### 3.1 Match ingested op — `POST /v1/db/preview` (read-only)

Swagger: `#/database-query-controller/preview_1`

```bash
curl -sS -X POST \
  "http://tapmind-backend-i.golabs.io/v1/db/preview?pdg=<pdg>&serviceId=<svc>&method=<METHOD>&path=<path>"
```

| Query | Required | Use |
|---|---|---|
| `pdg` | yes | Product group |
| `serviceId` | no | Pin service |
| `method` | no | `GET`/`POST`/… |
| `path` | no | API path (as ingested) |

Response: `api_specs[]`, `few_shots[]`, `intent_exemplars[]`. Use to confirm the step maps
to an ingested op and to pick `service_id` / utterance hints. Host from
`CONTROL_PLANE.md` (prefer `http://` when TLS MITM fails locally).

If preview returns no matching `api_specs` → `NEEDS_REVIEW: no ingested op` (do not
auto-ingest).

### 3.2 Bindings from verify — MCP `tapmind_verify_prompt` (preferred for paths)

Call with the **action prompt still containing the vague save**, `dryRunLlm: true`:

```json
{
  "prompt": "Generate CPM QR and save basetoken from response as basetoken",
  "productGroup": "<pdg>",
  "targetServiceId": "<service>",
  "dryRunLlm": true
}
```

(or HTTP `POST /v1/runs/verifyPrompt` with `prompts: [{ "prompt": "…" }]` — same shape).

Read each `step_suggestions[]` entry:

| Field | Use |
|---|---|
| `declared_bindings` | **Source of truth** for memory key → JSONPath |
| `corrected_test_prompt` | Wording / op intent; may still lack `$.` — merge with bindings |
| `status` | Prefer `PASS`; on fail, fix intent or flag `NEEDS_REVIEW` |

**Rewrite rule:** for each binding `name → path`, emit NLP save as:

```
save <path> as <name>
```

Example (live integration verify):

| Input | `declared_bindings` | Enriched NLP |
|---|---|---|
| `… save basetoken from response as basetoken` | `{"basetoken": "$.data.base_token"}` | `… and save $.data.base_token as basetoken` |

If verify returns a corrected prompt that still says `save base_token from the response as
basetoken` **without** `$.`, substitute using `declared_bindings` — do not ship the
path-less form.

### 3.3 Optional live probe

When bindings are empty but the op is known: run `tapmind_run_nlp_command` once (execute
only, no vague save), walk the response JSON for keys matching the field name
(case-insensitive / snake vs camel), build `$.…` path, then re-verify. Prefer §3.2 when
bindings exist.

### 3.4 Still ambiguous

Flag `NEEDS_REVIEW: unresolved_json_path:<field>` — do **not** invent `$.data.<field>`.

## 4. Emit prompts for §G.B

After enrichment:

1. Apply §3.1.1 split: execute (+ optional `| verify: HTTP 2xx`) → **one** detail verify-only.
2. Memory refs: later steps use `saved <exactKey>` (§4), not `${memory.…}`.
3. Array values: only `entry where` (§3.3) — never a dotted path into a list.
4. Set `source.kind`: `browserstack_case` | `coded_migration` | `sdet_plan` | `reference`.
5. Hand off to §G.B (coverage scan, MCP verify/run, suite convert).

Output per case (before suite convert):

```json
{
  "scenarioRef": "<case id or method>",
  "pdg": "<pdg>",
  "target_service_id": "<service>",
  "raw_steps": [{ "n": 1, "action": "…", "expected_result": "…" }],
  "prompts": ["… enriched …"],
  "path_enrichment": [
    {
      "n": 1,
      "was": "save basetoken from response as basetoken",
      "bindings": { "basetoken": "$.data.base_token" },
      "became": "save $.data.base_token as basetoken"
    }
  ],
  "flags": []
}
```

## 5. Common rewrite table

| Don't write (test-case style) | Write (TapMind NLP) |
|---|---|
| `save basetoken from response` | `save $.data.base_token as basetoken` (path from bindings) |
| `save order_number from response as orderNumber` | `save $.order_number as orderNumber` (or `$.data.…` if nested) |
| `verify basetoken is not null` | `Verify $.data.base_token is not null` |
| `save token from payment_options where type=GOPAY` | `save token from the payment_options entry where type equals GOPAY_WALLET as gopayWalletToken` |
| Bare step without success check | Execute `\| verify: HTTP 2xx` **or** one following `Verify …` |

## 6. Definition of done (enrichment stage)

- [ ] Steps loaded from file or BrowserStack
- [ ] Vague saves/asserts detected
- [ ] Op confirmed via `/v1/db/preview` when method/path known (or flagged)
- [ ] Each vague field resolved via `declared_bindings` (or `NEEDS_REVIEW`)
- [ ] Every save in `prompts[]` uses `save $.… as <name>` or `entry where … as <name>`
- [ ] Ready for §G.B — no path-less `save <field> from response` left
