---
name: backend-sdet-plan-generator
description: Generate the backend SDET test plan from extracted context files. Three modes: Pass 1 (pre-build, 4 context files), Pass 2 (post-build, adds code_change_context), Re-trigger (doc change, patches affected scenarios). Outputs sdet_plan.json, qa_analysis.md, and sdet_testcases.csv. RFC drives completeness, PRD drives priority, Tasks drive classification, regression drives deduplication.
---

# Backend SDET Plan Generator

Synthesise all extracted context into a structured test plan for human review before code generation begins.

## Model
Reasoning tier — Opus

## Modes of operation

| Mode | Trigger | Inputs | Output scope |
|---|---|---|---|
| Pass 1 | Pre-build, first run | prd + rfc + tasks + regression context | Full scenario set |
| Pass 2 | Post-build, Epic QA Ready | All Pass 1 inputs + `code_change_context` | Delta scenarios only (`is_delta: true`) |
| Re-trigger | Upstream doc changed | Existing `sdet_plan.json` + `doc_change_context` + human feedback | Patch affected scenarios only |

## Reads

| File | Read for |
|---|---|
| `rfc_context.json` | validation_sequence (business rules), flows, edge_cases, error_codes, contracts (all protocols), feature_flags, risk_areas, non_functional_requirements, extraction_gaps, open_questions, provenance |
| `prd_context.json` | Acceptance criteria, business error classification, scenario priority (P0/P1/P2), out-of-scope flows |
| `tasks_context.json` | test_layer per story (authoritative), api_contract (authoritative endpoint + schema), validation_constraints (implementation confirmation), preconditions (contributing input for writing sdet_plan preconditions) |
| `regression_context.json` | Active non-legacy non-flaky tests — deduplication signal |
| `code_change_context.json` | Pass 2 only — new endpoints, new error mappings, new validation rules not in RFC |

## Ownership contract — A = authoritative (wins conflicts), C = contributes

This is the RFC's formal A/C matrix applied per dimension. When sources conflict, A wins. C sources confirm or add detail but never override A.

| Dimension | Authoritative (A) | Contributing (C) |
|---|---|---|
| API endpoints + schema | `tasks_context.api_contract` (route, request_fields, response_fields) | `rfc_context.contracts.rest[]` · `code_change_context` |
| Business logic / validation rules | `rfc_context.validation_sequence` (ordered steps, constraints, failure codes) | `tasks_context.validation_constraints` · `code_change_context` |
| Acceptance criteria + error scenarios | `prd_context` (business classification, AC list) | `tasks_context` (impl error code strings) · `rfc_context.error_codes[]` · `code_change_context` |
| Test layer assignment | `tasks_context.test_layer` per story | `rfc_context.validation_sequence[].layer` (signal only — do not use to assign test_layer) |
| Package / class naming | `tasks_context` component + package | — |
| Test-data / preconditions | `sdet_plan.json` — **this output is authoritative once written** | `prd_context` (business state) · `tasks_context.preconditions` · `rfc_context.flows[].trigger` |
| Scenario priority | `prd_context` priority · `rfc_context.risk_areas[].priority` (P0 escalates) | `tasks_context` story priority |
| Protocol contracts (gRPC, Kafka) | `rfc_context.contracts.grpc[]` / `kafka[]` | `code_change_context` |
| Feature flag behaviour | `rfc_context.feature_flags[]` | `tasks_context` (implementation of the flag) |

### Field-level reading contract

**READ FROM `rfc_context` (A) for business logic and scenario completeness:**

| Field | What it drives in scenario generation |
|---|---|
| `validation_sequence[]` | Happy-path + failure + boundary scenarios per step |
| `flows[].type + outcome` | One scenario per flow; `type` → tag; `outcome` → assertion prose |
| `edge_cases[]` | One scenario per edge case; `inferred: true` → mark `provisional: true` |
| `error_codes[]` | Cross-story error scenario dedup; `is_retriable: true` → add retry-behaviour scenario |
| `contracts.rest[]` | API-level scenarios per endpoint; skip if `underspecified: true` |
| `contracts.grpc[]` | gRPC method scenarios (happy + error + stream interruption if not unary) |
| `contracts.kafka[]` | Producer → message-published scenario; consumer → processing scenario; `dlq` set → poison-message scenario |
| `contracts.other[]` | Scheduled worker / DB-direct / migration scenarios per trigger |
| `feature_flags[]` | flag_on + flag_off pair; `kill_switch: true` → kill-switch scenario |
| `risk_areas[]` | P0 risk → force P0 on covering scenario; uncovered P0 → generate scenario + surface in gaps |
| `non_functional_requirements.performance_targets[]` | Load scenario per entry (see NFR rules below) |
| `non_functional_requirements.nfr_statements[]` | Qualitative NFR scenarios from prose (see NFR rules below) |
| `non_functional_requirements.security_compliance[]` | Data masking + auth + compliance scenarios |
| `non_functional_requirements.reliability_targets[]` | Timeout + retry-exhaustion + circuit-breaker scenarios |
| `extraction_gaps[]` | Blocking gate — see section below |
| `open_questions[]` | Deferred scenarios — see section below |
| `provenance` | Staleness warning in qa_analysis.md if `extracted_at` is stale |

**READ FROM `prd_context` (A) for priority and business error classification:**
- Acceptance criteria → scenario list (Given/When/Then)
- Error scenarios → what the business expects to fail; authoritative for error classification even if RFC does not name the error
- Priority signal → P0/P1/P2 per AC
- Out-of-scope markers → do not generate scenarios for flagged flows

**READ FROM `tasks_context` (A) for test layer and endpoint schema:**
- `test_layer` per story → authoritative for all scenarios in that story; do not infer test_layer from `rfc_context.validation_sequence[].layer`
- `api_contract.route + method` → authoritative endpoint; cross-check with `rfc_context.contracts.rest[].path` and flag drift in qa_analysis.md
- `api_contract.request_fields + response_fields` → authoritative schema; use for precondition field names in step_descriptions
- `validation_constraints[]` → confirms RFC rules are implemented; adds implementation-specific error code strings as C input — does not override `validation_sequence` rule order or logic

**READ FROM `code_change_context` (C) — Pass 2 only:**
- New endpoints not in RFC → new component scenarios; flag as `rfc_gap`
- New error handling → new negative scenarios
- New feature flags → new flag-state scenarios

## Conflict resolution

| Conflict | Resolution |
|---|---|
| `tasks_context.api_contract.route` ≠ `rfc_context.contracts.rest[].path` | tasks wins; flag drift in qa_analysis.md RFC ↔ Tasks conflicts section |
| `tasks_context.test_layer` ≠ layer implied by `rfc_context.validation_sequence[].layer` | tasks wins unconditionally; RFC layer is a signal, not an assignment |
| `rfc_context.error_codes[]` error name ≠ `tasks_context.api_contract.error_codes` string | tasks wins for the exact code string; RFC wins for the business condition that triggers it — combine both |
| PRD marks a flow out-of-scope but RFC has validation steps for it | PRD wins; do not generate; note in coverage_summary.rfc_gaps[] |
| `rfc_context.validation_sequence` rule conflicts with `tasks_context.validation_constraints` rule | RFC wins for rule logic and order; tasks wins for implementation fields (exact class name, field path) |
| `rfc_context.risk_areas[priority: P0]` but PRD assigns P1 to the same scenario | Escalate to P0; flag in qa_analysis.md for human review |

## Blocking gates — check before generating any scenario

Run in order. Blocked areas must not produce scenarios.

| Check | Action |
|---|---|
| `rfc_context.extraction_gaps[blocking: true]` | Do not generate scenarios for the affected `field` path; add entry in `coverage_summary.rfc_gaps[]` with `blocked_by_extraction_gap: true` |
| `rfc_context.approach_finalised: false` | Generate scenarios but mark all contract-derived assertions `provisional: true`; add warning in qa_analysis.md |
| `rfc_context.contracts.rest[underspecified: true]` | Skip concrete request/response assertions for that endpoint; generate a placeholder scenario with `tags: ["underspecified"]` |
| `rfc_context.open_questions[]` not empty | For each question add a deferred scenario with `tags: ["deferred"]`, `source_ref` pointing to the question; do not block other scenarios |
| `rfc_context.provenance` stale (extracted_at old relative to current date) | Surface warning in qa_analysis.md: "rfc_context was extracted on {extracted_at} — verify RFC has not changed since extraction" |

## Scenario generation rules

### RFC validation_sequence — business logic (A)

For each step:
- **Happy path** — step succeeds with valid inputs → `tags: ["happy_path"]`
- **Failure** — one negative scenario per `failure_error_code` the step can produce → `tags: ["negative"]`
- **Boundary** — quantitative constraints in `constraint` field (min/max/edge) → `tags: ["boundary"]`

Use `tasks_context.test_layer` for the story that implements this step — never infer test_layer from `validation_sequence[].layer`.

### RFC flows — end-to-end scenario paths

For each flow:
- One scenario covering the full step sequence
- `tags`: `happy_path` | `fallback` | `deviation` — match `flows[].type`
- Assertion prose: use `flows[].outcome` verbatim as the expected result

### RFC edge_cases

- One scenario per edge case
- `inferred: true` → add `provisional: true`; note in qa_analysis.md as "extractor-inferred, verify against RFC"
- `validation_step_ref` set → mark scenario as related to the parent step scenario

### RFC contracts — gRPC

For each `contracts.grpc[]` entry:
- Happy path: valid request → correct response → `test_layer: component`
- Error: dependency unavailable → correct gRPC status code asserted
- `streaming_type != unary` → add stream-interruption scenario

### RFC contracts — Kafka

For each `contracts.kafka[]` entry:
- `produces_to` → message-published scenario: trigger operation, assert message on topic with correct schema
- `consumes_from` → message-received scenario: publish test message, assert correct service side effect
- `dlq` set → poison-message scenario: malformed message → assert routed to DLQ, not silently dropped
- `delivery_guarantee: exactly_once` → duplicate-message scenario: assert exactly-once semantics hold

### RFC contracts — other (workers, DB-direct, migration pipelines)

For each `contracts.other[]` entry:
- One scenario per `trigger`; `test_layer: integration`
- `frequency` contains deadline → add deadline-breach scenario (simulate delay past deadline, assert correct behaviour)

### RFC feature_flags

For each flag:
- `flag_on` scenario + `flag_off` scenario → `tags: ["flag_on"]` / `tags: ["flag_off"]`
- `kill_switch: true` → kill-switch scenario: enable flag, assert feature fully disabled
- Use `gated_behavior` as the assertion description

### RFC risk_areas — priority escalation

- `P0` risk with no covering scenario → generate one; `priority: P0`
- `P0` risk with existing scenario → force that scenario to `priority: P0`
- `P1` risk → ensure covering scenario exists at `priority: P1` minimum
- All uncovered P0 risks → surface in `coverage_summary.rfc_gaps[]`

### RFC non_functional_requirements

**performance_targets[]** — structured load signals:
- `throughput_tps` or `throughput_ops_per_day` present → load scenario: note target TPS as assertion parameter; `tags: ["load", "nfr"]`
- `concurrency_ceiling` present → concurrency scenario: at `safe_tps` assert 0% failure; if `degraded_onset_tps` set, add second scenario asserting documented failure behaviour
- `slo_deadline` present → deadline-breach scenario: simulate slow execution past deadline, assert system handles it correctly; `tags: ["nfr", "reliability"]`

**nfr_statements[]** — qualitative NFR prose:
- Read each statement for intent signal:
  - "eliminate deadlocks / race conditions" → concurrent-write scenario; `tags: ["concurrency", "nfr"]`
  - "data integrity / balance consistency" → consistency-assertion scenario; `tags: ["nfr"]`
  - "resumable after failure" → failure-and-resume scenario; `tags: ["reliability", "nfr"]`
  - "near-zero-downtime rollout" → rollout-cutover scenario; `tags: ["nfr"]`
- Do not generate duplicate scenarios if a structured `performance_targets[]` entry already covers the same NFR

**security_compliance[]** — one scenario per entry:
- `data_masking` → assert target field absent or masked in response body AND logs; `tags: ["security", "nfr"]`
- `auth` → expired-token scenario + missing-token scenario; `tags: ["security", "negative"]`
- `PCI-DSS` → card PAN must not appear in API response or log output; `tags: ["security", "compliance", "nfr"]`
- `GDPR` → personal data handling assertion per requirement description

**reliability_targets[]** — one scenario per entry per relevant field:
- `timeout_ms` → slow-downstream scenario: inject latency above `timeout_ms`, assert timeout fires and correct error is surfaced
- `retry_count` → retry-exhaustion scenario: downstream fails `retry_count + 1` times, assert final error is surfaced correctly and no infinite loop
- `circuit_breaker_error_rate_pct` → circuit-breaker-activation scenario: sustain error rate above threshold, assert circuit opens and fallback activates; `tags: ["reliability", "nfr"]`

### PRD acceptance criteria — error scenarios (A)

- Each PRD AC → one scenario minimum
- PRD error classification is authoritative: if PRD says 409 for duplicate card, generate that scenario regardless of whether RFC names the error
- If RFC already has a matching scenario → link via `source_ref`, do not duplicate

### Pass 2 — code_change_context (C)

- New endpoint not in RFC → component scenario + `rfc_gap` flag
- New validation rule not in RFC → scenario + `rfc_gap` flag
- New error mapping → negative scenario
- All Pass 2 scenarios: `is_delta: true`

## Ownership note — sdet_plan.json is authoritative for preconditions

Once `sdet_plan.json` is written and approved by a human:
- It becomes the authoritative (A) source for test-data needs and preconditions per the RFC's A/C matrix
- PRD and tasks were contributing (C) inputs used to write this plan; the plan now owns the output
- Downstream skills (automation-plan-generator, test-data-generator) read preconditions from `sdet_plan.json`
- They do NOT re-read `prd_context`, `rfc_context`, or `tasks_context` for preconditions or fixture decisions

## Output → sdet_plan.json

Schema root:
- `feature_name`, `plan_version`, `generation_mode: pass1|pass2|retrigger`
- `scenarios[]` — each with:
  - `scenario_id`, `name`, `description`
  - `test_layer: component|integration|e2e`
  - `priority: P0|P1|P2`
  - `source: RFC|PRD|CODE_DIFF|RETRIGGER`, `source_ref`
  - `provisional: boolean` — true when `approach_finalised: false` or `edge_case.inferred: true`
  - `is_delta`, `is_legacy_regression`, `is_dedup`
  - `step_descriptions[]` — `step`, `action`, `curl_reference`, `expected_result`
  - `preconditions[]`, `fixture_ids[]`
  - `tags[]` — `happy_path|negative|boundary|flag_on|flag_off|e2e|load|concurrency|security|reliability|compliance|nfr|deferred|underspecified|provisional`
- `coverage_summary` — `total`, `by_layer`, `by_priority`, `rfc_steps_covered`, `rfc_steps_total`, `rfc_gaps[]`

## Output → qa_analysis.md

Human-readable summary for SDET + PM review gate:
- Total scenarios by layer and priority
- RFC coverage % (scenarios / validation steps)
- Gaps — RFC steps with no scenario, blocked extraction gaps, provisional scenarios
- New vs existing regression coverage
- Risk areas and their covering scenarios; uncovered P0 risks flagged
- RFC ↔ Tasks contract conflicts (endpoint drift, schema drift)
- Open questions surfaced as deferred scenarios
- Provenance staleness warning if applicable

## Output → sdet_testcases.csv

Flat CSV for BrowserStack upload after human approval.
Columns: `scenario_id, name, test_layer, priority, tags, is_delta, is_legacy_regression`

## Pass 2 rules

- Output only `is_delta: true` scenarios — do not regenerate the full plan
- Trace each code diff signal to an existing RFC validation step where possible

## Re-trigger rules

- Read existing `sdet_plan.json` — do not regenerate unaffected scenarios
- Apply only the delta from `doc_change_context.json`
- Output only added/modified/deprecated scenarios with `change_reason` field

## Validate

`jsonschema.validate(output, schemas/sdet_plan.schema.json)`

## Log

Total scenarios, RFC coverage %, gaps count, blocked gaps count, provisional count, delta count (Pass 2/Re-trigger).
