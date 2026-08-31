# NLP coverage & dedup — parity with coded GBT pipeline

Companion to `GENERATION.md`. The coded path (`gbt-method-decision-maker` →
`gbt-test-code-generator`) already refuses to duplicate existing `@Test` methods. This skill
must do the same for **`TapMind.runStep` / `TapMind.assertStep`** tests — otherwise redundant
methods may be emitted.

## Upstream skills (run before NLP generate)

| Skill | Required? | NLP use |
|---|---|---|
| `dedup-generator` (method mode) | **Yes** — on `automation_plan.json` | Honours `is_dedup: true`; never regenerate flagged scenarios |
| `test-data-generator` + `test_data_payloads` merge | When plan has `{{FIX-…}}` | Resolve fixtures → `saveMemory` / `saved <key>` (§4, §7) |
| Human review gate (`run.json`) | **Yes** for suite convert / repo write | Same per-scenario approval rules as `gbt-test-code-generator` rule 1a |
| `gbt-method-decision-maker` | Optional cross-check | If verdict is `exact_match` for same `method_name` + endpoint, prefer NLP skip unless user wants TapMind migration |
| `tapmind_ingest_curl` / `tapmind_ingest_openapi` (MCP) | When verify shows no REST op | **Explicit user request only** — not auto in pipeline (`CONTROL_PLANE.md`) |

Do **not** re-implement Memgraph enrichment for NLP-only flows unless comparing against coded
coverage; the scan below is TapMind-specific and file-based.

## Scenario approval gate (run first — before coverage scan)

NLP generate, verify, and suite convert apply **only** to approved scenarios. This matches
`gbt-test-code-generator` rule 1a. On enriched plans (e.g. `enriched_automation_plan_v6.json`),
TDP fixture output is provisioned only for `status: "approved"` scenarios — generating for
`draft` scenarios produces unrunnable tests (null `test_data_output`, unresolved `{{FIX-…}}`).

Resolve per scenario, **first hit wins**:

| Source | Generate when | Otherwise |
|---|---|---|
| `run.json` → `review.per_scenario[<scenario_id>]` | `"keep"` | Skip — `reason: not_approved` |
| Scenario `status` or `approval_status` (when plan carries per-scenario status) | `"approved"` | Skip — `reason: not_approved` (`draft`, `changes_requested`, etc.) |
| Plan top-level `status` only (no per-scenario status on **any** scenario) | `"approved"` | Skip all — plan not approved |
| None of the above | — | Skip — `reason: no_approval_record` |

**Enriched-plan rule:** when scenarios carry their own `status` field, **each row is judged
independently**. Plan-level `"status": "draft"` does **not** block scenarios whose own
`status` is `"approved"`. Example: `GOFOOD-SG-M5` with plan `draft` and 3 scenarios
`approved` → generate **only those 3**, skip the 57 `draft`.

**Fail closed:** missing `review.per_scenario` entry is not implicit keep. `draft` is not
“generate anyway”.

### TDP readiness (enriched plans with `test_data[]`)

After approval passes, before prompt generate:

| Check | Skip when |
|---|---|
| `curl_reference` / steps use `{{FIX-xxx.field}}` | Fixture `test_data_output` is null/empty **and** no row in plan `test_data_payloads` for `FIX-xxx` |
| Enriched output present | Prefer fixtures with `test_data_status: TDP_SUPPORTED`; `TDP_OPERATION_FALLBACK` may run but flag `NEEDS_REVIEW` on primary actor fixtures |

Skip reason: `tdp_not_ready`. Do not invent bearer tokens or merchant ids.

## Pipeline step: NLP coverage scan (before prompt generate)

For every scenario that passed **approval + TDP** gates, with `is_dedup: false` and not tagged
`deferred` / `skip` / `manual`:

### 1. Resolve target files

Search the GBT repo (or paths from plan `package` + `test_class`):

```bash
# Primary: plan anchors
rg -l "class <test_class>" --glob "*.java" <module_test_root>

# Secondary: TapMind methods for same endpoint / service
rg -l "TapMind\.(runStep|assertStep)" --glob "*Test*.java" <module_test_root>
```

Open candidate classes named in `automation_plan.json` (`package`, `test_class`, `method_name`).

### 2. Parse existing NLP tests

For each `@Test` method in candidates, extract:

| Signal | How |
|---|---|
| Method name | `@Test` method identifier |
| Description | `@Test(description = "…")` |
| Case ids | `@TestInfo(testCaseIds = {…})` |
| TapMind steps | String literals inside `TapMind.runStep("…")` / `assertStep("…")` |
| Endpoint hint | Plan `endpoint` or curl host/path in prompts |
| Scenario id | `description` containing `SC-…` / `AC-…` if present |

Ignore Allure `@Step("Given/When/Then …")` on non-TapMind tests — those are coded tests, not NLP.

### 3. Verdict (mirror coded `method_decisions.json`)

Emit one row per scenario in `nlp_method_decisions.json`:

| Verdict | Meaning | Generate prompts? | Suite convert? |
|---|---|---|---|
| `exact_match` | Same `method_name` exists with `TapMind.runStep` lines covering scenario steps + expected_result | No | No — record covering method |
| `partial_match` | Same class/endpoint, method exists but missing asserts or steps | Yes — only delta prompts | Append lines to existing method |
| `method_name_collision` | `method_name` taken by a **non-TapMind** test | Flag `NEEDS_REVIEW` | Do not overwrite |
| `no_match` | No TapMind method covers this scenario | Yes | New `@Test` method |
| `undecidable` | Target repo/path missing or class unparseable | No | Skip + TODO |

**`exact_match` bar (same as coded):** calling the same endpoint is not enough — existing
`runStep` verify clauses must already assert the scenario's `expected_result`. A happy-path
NLP test does not `exact_match` a new negative scenario.

**Identity shortcuts (any one is sufficient for `exact_match`):**

- Plan `method_name` equals an existing `@Test` method with TapMind lines and matching intent
- Plan `testCaseIds` / `@TestInfo` ids already on an existing TapMind `@Test`
- Plan `scenario_id` appears in an existing `@Test(description = "…")`

### 4. Output: `nlp_method_decisions.json`

```json
{
  "epic_id": "<from automation_plan>",
  "scan_root": "<module test src path scanned>",
  "decisions": [
    {
      "scenario_id": "SC-001",
      "verdict": "exact_match",
      "covering_method": "com.example.FooTest#testBar",
      "signals": ["method_name match", "3 runStep lines cover step_descriptions"],
      "confidence": "high"
    },
    {
      "scenario_id": "SC-002",
      "verdict": "no_match",
      "covering_method": null,
      "signals": ["no TapMind.runStep in test_class"],
      "confidence": "high"
    }
  ],
  "skipped": []
}
```

## Review gate (suite convert / repo write)

Re-check the same approval resolution above before writing Java to disk. No second standard —
the table in **Scenario approval gate** is authoritative.

Record skips in `nlp_suite_tests.json` / manifest with `reason`:
`not_approved` | `no_approval_record` | `tdp_not_ready` | `exact_match` | `is_dedup` | `undecidable`.

## Dedup layers (do not conflate)

| Layer | Mechanism | Scope |
|---|---|---|
| Plan dedup | `dedup-generator` → `is_dedup: true` | Duplicate scenarios **in the plan** |
| Repo coverage | This file → `nlp_method_decisions.json` | Duplicate scenarios **already in repo** |
| Coded cross-check | `gbt-method-decision-maker` `exact_match` | Same scenario covered by **Java** test — skip NLP unless migrating |

When coded `exact_match` and NLP `no_match` disagree, flag `NEEDS_REVIEW: coded_coverage_exists`
— do not emit a second test without reviewer intent to migrate to TapMind.

## Partial match — append-only suite convert

When `verdict: partial_match`:

1. Open existing method; never rename or delete lines.
2. Emit only new `TapMind.runStep` / `assertStep` / `saveMemory` lines in `tapmindTest.lines`.
3. Set `"action": "append"` in manifest (not `"create"`).

## Manifest skipped reasons (required)

Every non-generated scenario must appear under `skipped[]`:

```json
{"scenario_id": "SC-007", "reason": "exact_match", "detail": "FooTest#testBar already has TapMind steps"}
{"scenario_id": "SC-008", "reason": "is_dedup", "detail": "dedup-generator canonical SC-001"}
{"scenario_id": "SC-009", "reason": "not_approved", "detail": "scenario status is draft"}
{"scenario_id": "SC-010", "reason": "tdp_not_ready", "detail": "FX-SG-HOST-OWNER-01 test_data_output null"}
```

## Definition of done (coverage)

- [ ] `nlp_method_decisions.json` exists for every non-`is_dedup` scenario
- [ ] Zero `exact_match` scenarios in `nlp_suite_tests.json` output
- [ ] No `method_name_collision` without `NEEDS_REVIEW` flag
- [ ] Skipped counts reconcile: plan scenarios = generated + skipped
