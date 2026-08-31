# NLP coverage & dedup — parity with coded GBT pipeline

Companion to `GENERATION.md`. The coded path (`gbt-method-decision-maker` →
`gbt-test-code-generator`) already refuses to duplicate existing `@Test` methods. This skill
must do the same for **`TapMind.runStep` / `TapMind.assertStep`** tests — otherwise NLP
generation looks easier on paper but ships redundant methods.

## Why NLP should beat coded (design intent)

| Coded GBT cost | NLP advantage |
|---|---|
| Endpoint → Client → Controller → DTO → Assertion layers | One English sentence per step |
| Module profile + 4-step reuse protocol | Plan fields `module` / `service_name` pin PDG |
| Fabricating controller methods is a top failure mode | No fabricated Java calls — planner routes |
| Data-provider row vs new method judgement | Extra scenario → extra `runStep` lines in same method |
| Compile + validator fix loops | MCP verify + optional execute before suite convert |

NLP wins on **speed and surface area**, not on skipping gates. Reuse the same upstream
artifacts (`automation_plan.json`, dedup flags, review approval, fixtures).

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

## Pipeline step: NLP coverage scan (before prompt generate)

For every scenario with `is_dedup: false` and not tagged `deferred` / `skip` / `manual`:

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

## Review gate (same fail-closed rules as coded)

Before suite convert or writing Java to disk, resolve per-scenario approval:

| Source | Approved when |
|---|---|
| `run.json` → `review.per_scenario[<scenario_id>]` | `"keep"` |
| Scenario `status` / `approval_status` | `"approved"` |
| Plan top-level `status` | `"approved"` (all scenarios without per-row entry) |
| None present | **Skip** — absence is not approval |

Record skips in `nlp_suite_tests.json` / manifest with `reason`:
`not_approved` | `exact_match` | `is_dedup` | `undecidable`.

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
{"scenario_id": "SC-009", "reason": "not_approved", "detail": "missing from review.per_scenario"}
```

## Definition of done (coverage)

- [ ] `nlp_method_decisions.json` exists for every non-`is_dedup` scenario
- [ ] Zero `exact_match` scenarios in `nlp_suite_tests.json` output
- [ ] No `method_name_collision` without `NEEDS_REVIEW` flag
- [ ] Skipped counts reconcile: plan scenarios = generated + skipped
