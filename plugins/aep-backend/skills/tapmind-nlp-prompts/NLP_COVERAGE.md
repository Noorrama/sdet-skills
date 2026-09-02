# NLP coverage & dedup — parity with coded GBT pipeline

Companion to `GENERATION.md`. The coded path (`gbt-method-decision-maker` →
`gbt-test-code-generator`) already refuses to duplicate existing `@Test` methods. This skill
must do the same for **`TapMind.runStep` / `TapMind.assertStep`** tests — otherwise redundant
methods may be emitted.

**Two intake paths** (`SKILL.md` §G): plan-driven vs artifact-driven (code / test case).
**Coverage scan below applies to both.** Approval and enriched-TDP gates apply to **plan path
only**.

## Upstream skills (by path)

| Skill | Plan-driven | Artifact-driven | NLP use |
|---|---|---|---|
| `dedup-generator` (method mode) | **Yes** | No | Honour `is_dedup: true` |
| `test-data-generator` + payloads | When `{{FIX-…}}` | Optional | Buddy prompt / `saveMemory` |
| Human review (`run.json`) | **Yes** for batch suite write | No | Plan approval only |
| Read target Java | Optional | **Yes** when migrating | Extract setup + steps |
| `gbt-method-decision-maker` | **Yes, primary** (when plan is enriched) | Useful | Coded coverage — reuse `method_decisions.json`, don't re-grep |
| `tapmind_ingest_*` (MCP) | Either path | Either path | Explicit user request only |

Do **not** re-implement Memgraph enrichment for NLP-only flows unless comparing against coded
coverage; the scan below is TapMind-specific and file-based.

---

## Plan-driven gates only (before coverage scan)

Apply when intake is **`automation_plan.json`** batch generate / suite write. **Skip this
section** for artifact-driven flows (single test migration, reference fix, BS steps) — user
intent is the gate.

### Scenario approval gate

Matches `gbt-test-code-generator` rule 1a. On enriched plans, TDP fixture output is provisioned
only for `status: "approved"` scenarios.

Resolve per scenario, **first hit wins**:

| Source | Generate when | Otherwise |
|---|---|---|
| `run.json` → `review.per_scenario[<scenario_id>]` | `"keep"` | Skip — `reason: not_approved` |
| Scenario `status` or `approval_status` | `"approved"` | Skip — `reason: not_approved` |
| Plan top-level `status` only (no per-scenario status on **any** scenario) | `"approved"` | Skip all — plan not approved |
| None of the above | — | Skip — `reason: no_approval_record` |

**Enriched-plan rule:** per-scenario `status` is independent. Plan-level `"draft"` does **not**
block scenarios whose own `status` is `"approved"`.

**Fail closed:** `draft` is not “generate anyway”.

### TDP readiness (enriched plans with `test_data[]`)

After approval passes, before prompt generate:

| Check | Skip when |
|---|---|
| `curl_reference` / steps use `{{FIX-xxx.field}}` | Fixture `test_data_output` null/empty **and** no row in `test_data_payloads` for `FIX-xxx` |
| Enriched output present | Prefer `TDP_SUPPORTED`; `TDP_OPERATION_FALLBACK` may run — flag `NEEDS_REVIEW` on primary actor fixtures |

Skip reason: `tdp_not_ready`. Do not invent bearer tokens or merchant ids.

Re-check approval before writing Java to disk on plan batch writes.

---

## Artifact-driven gates (before coverage scan)

Apply when intake is **existing Java**, **BrowserStack steps**, **`sdet_plan` without
enrichment**, or **reference prompt fix**. No `status: approved` check.

### Data dependency gate

| Check | Action |
|---|---|
| Step/curl needs auth token or entity id | Emit TDP `runStep` or reuse `*TapMindTestBase` helper |
| `saved <key>` with no prior save in method/base/helpers | Flag `NEEDS_REVIEW: unresolved_data_dependency` |
| Hardcoded token/id in source | Flag `NEEDS_REVIEW: migrate_to_tdp` (§7) |
| Optional enriched buddy prompt available | May use — not required |

Skip reason for blocked targets: `unresolved_data_dependency` (not `not_approved`).

---

## Pipeline step: NLP coverage scan (both paths)

For every target that passed **path-specific intake gates**, with `is_dedup: false` (plan) and
not tagged `deferred` / `skip` / `manual` (plan):

### 1. Resolve target files

**Plan, when enriched:** reuse `gbt-method-decision-maker`'s `method_decisions.json` — it already
read `scenario_gbt_context.test_methods_calling_endpoint[]` (written by
`automation-plan-test-enricher`) into exact `{test_file, test_method}` coded-coverage pairs. This
is the primary signal; do not re-derive it by grepping `test_class` (often empty on
draft/unenriched scenarios).

```bash
# Plan, only when unenriched / method_decisions.json unavailable — fallback
rg -l "class <test_class>" --glob "*.java" <module_test_root>

# Artifact: user path or testCaseId
rg -l "<testCaseId>" --glob "*Test*.java" <module_test_root>

# Both: TapMind methods for same endpoint / service
rg -l "TapMind\.(runStep|assertStep)" --glob "*Test*.java" <module_test_root>
```

Open the coded-coverage files `method_decisions.json` (or the fallback grep) named — those are
the candidates step 2 parses for existing **TapMind** coverage specifically (coded non-TapMind
coverage is already resolved by `method_decisions.json` itself).

### 2. Parse existing NLP tests

| Signal | How |
|---|---|
| Method name | `@Test` method identifier |
| Description | `@Test(description = "…")` |
| Case ids | `@TestInfo(testCaseIds = {…})` |
| TapMind steps | `TapMind.runStep("…")` / `assertStep("…")` literals |
| Endpoint hint | Plan `endpoint` or curl host/path in prompts / coded test |
| Scenario id | `SC-…` / `AC-…` in description if present |

Ignore Allure `@Step("Given/When/Then …")` on non-TapMind tests.

### 3. Verdict (mirror coded `method_decisions.json`)

| Verdict | Meaning | Generate prompts? | Suite convert? |
|---|---|---|---|
| `exact_match` | Existing TapMind method covers steps + expected_result | No | No |
| `partial_match` | Same class/endpoint, missing asserts or steps | Yes — delta only | Append |
| `method_name_collision` | `method_name` taken by **non-TapMind** test | Flag `NEEDS_REVIEW` | Do not overwrite |
| `no_match` | No TapMind coverage | Yes | New method or full replace per user |
| `undecidable` | Repo/path missing or unparseable | No | Skip + TODO |

**Identity shortcuts (any one → `exact_match`):**

- Plan `method_name` = existing TapMind `@Test` with matching intent
- `@TestInfo` ids match
- `scenario_id` in existing `@Test(description = "…")`
- Artifact: same method + endpoint already has equivalent `runStep` verifies

When coded `exact_match` and NLP `no_match` disagree → `NEEDS_REVIEW: coded_coverage_exists`.

### 4. Output: `nlp_method_decisions.json`

```json
{
  "epic_id": "<from plan or user context>",
  "intake_path": "plan | artifact",
  "scan_root": "<module test src path>",
  "decisions": [
    {
      "scenario_id": "SC-001",
      "verdict": "exact_match",
      "covering_method": "com.example.FooTest#testBar",
      "signals": ["method_name match"],
      "confidence": "high"
    }
  ],
  "skipped": []
}
```

## Dedup layers (do not conflate)

| Layer | Mechanism | Scope |
|---|---|---|
| Plan dedup | `is_dedup: true` | Plan path only |
| Repo coverage | This file | Both paths |
| Coded cross-check | `gbt-method-decision-maker` | Both — stronger on artifact migration |

## Partial match — append-only suite convert

1. Open existing method; never rename or delete lines.
2. Emit only new `runStep` / `assertStep` / `saveMemory` lines.
3. Set `"action": "append"` in manifest.

## Manifest skipped reasons (required)

```json
{"scenario_id": "SC-007", "reason": "exact_match", "detail": "FooTest#testBar"}
{"scenario_id": "SC-008", "reason": "is_dedup", "detail": "plan dedup"}
{"scenario_id": "SC-009", "reason": "not_approved", "detail": "plan path only"}
{"scenario_id": "SC-010", "reason": "tdp_not_ready", "detail": "plan path only"}
{"target": "FooTest#testBar", "reason": "unresolved_data_dependency", "detail": "artifact path"}
```

## Definition of done (coverage)

- [ ] `nlp_method_decisions.json` exists for every in-scope target
- [ ] Zero `exact_match` scenarios in output manifest
- [ ] No `method_name_collision` without `NEEDS_REVIEW`
- [ ] Skipped counts reconcile: in-scope targets = generated + skipped
