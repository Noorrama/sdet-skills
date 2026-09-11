---
name: backend-test-plan-generator
description: >
  Full Phase A → B lifecycle orchestrator. Single invocation handles all four modes —
  upstream-context (first run, runs all missing extractors then generates the full SDET plan),
  code-change-context (post-build, runs code-change-extractor then generates delta scenarios),
  doc-change-context (PRD/RFC updated, re-runs the stale extractor then fully regenerates),
  and review (applies human feedback from qa_analysis.md). Stops at the human review gate in
  all modes — does not chain into automation-plan-generator.
version: 4
disable-model-invocation: true
---

# Backend SDET Plan Generator (Phase A → B Orchestrator)

You are sequencing Phase A extractor skills, the code-change-extractor, the
doc-change-extractor, and the sdet-plan-generator into one run. You own **mode detection,
ordering, confirmation prompts, and handoff** — you do not re-implement any skill's logic.
If you find yourself re-deriving an AC, re-reading an RFC contract, or re-classifying a code
diff, stop: those decisions belong to the individual skills.

---

## Absolute rules (violating any is a critical failure)

1. **Never skip the human review gate.** Stop after `sdet-plan-generator` emits its output in
   any mode. Do not chain into `automation-plan-generator`.
2. **Mode detection runs first, before any file read or user prompt.** The mode governs which
   steps execute — do not skip it or guess.
3. **Run stages in the exact order for the detected mode. Stop on the first REJECT.**
4. **Idempotency is mandatory.** Skip any extractor whose output already exists and is valid
   JSON. Never overwrite a valid context file without an explicit `--rerun` flag.
5. **All confirmation gates are blocking.** Never proceed silently when a required or expected
   input is absent — ask the user first.
6. **Reject, don't degrade.** Write `orchestrator_run_log.json` naming the failed stage with
   the stage's own reject payload verbatim. Do not paraphrase.
7. **All outputs follow `common/versioning/SKILL.md`.** Write `{artifact}_v{N}.json` and keep
   `{artifact}.json` as the current pointer.
8. **Mode names are canonical.** Use exactly: `upstream-context`, `code-change-context`,
   `doc-change-context`, `review`. These match `sdet-plan-generator`'s `generation_mode` field.

---

## Step 0 — Mode detection (ALWAYS FIRST)

Check the run output directory in **priority order** — use the first match:

| Priority | Condition | Mode | Steps that run |
|---|---|---|---|
| 1 (highest) | `sdet_plan.json` present **AND** `qa_analysis.md` present **AND** `### Feedback` section has content beyond the placeholder | **review** | Step 0 → Step R |
| 2 | `sdet_plan.json` absent | **upstream-context** | Step 0 → Steps U1–U8 |
| 3 | `sdet_plan.json` present **AND** user signals a doc update (via `--doc-updated` flag or updated doc file path provided as arg) | **doc-change-context** | Step 0 → Steps D1–D4 |
| 4 | `sdet_plan.json` present **AND** (`code_change_context.json` present **OR** user provides a GitLab diff) | **code-change-context** | Step 0 → Steps C1–C5 |
| 5 (error) | `sdet_plan.json` present, no feedback, no signal | **Error** | Stop — surface guidance |

Report the detected mode before doing anything else:

```
Mode detected: upstream-context — no sdet_plan.json found, running full extraction and generation.
```
```
Mode detected: code-change-context — sdet_plan.json present, code-change signal available.
```
```
Mode detected: doc-change-context — PRD/RFC updated, will re-extract and regenerate.
```
```
Mode detected: review — qa_analysis.md contains feedback to apply.
```

**On Error mode:**
```
⛔ Cannot determine mode.
sdet_plan.json exists but no feedback is in qa_analysis.md and no change signal was provided.

Choose one:
  A. Add feedback to qa_analysis.md → ## Human Review → ### Feedback
     → re-invoke (triggers review mode)
  B. Re-invoke with --doc-updated prd=/path/to/updated.pdf (or rfc=...)
     → triggers doc-change-context mode (re-extracts and fully regenerates)
  C. Provide a GitLab diff or code_change_context.json (post-build)
     → re-invoke (triggers code-change-context mode)
  D. Run with --rerun to re-generate the full plan from scratch
     → re-invoke (triggers upstream-context mode, overwrites existing plan)
```

**When review mode and a code-change signal coexist:** run review first. After clearing the
feedback section, the next invocation picks up `code_change_context.json`. Note this in the run log.

---

## UPSTREAM-CONTEXT PATH — Full extraction + plan generation

Runs when: `sdet_plan.json` is absent.

### Step U1 — Resolve directories

Ask for two inputs if not provided in args:

| Input | Prompt | Default |
|---|---|---|
| **Source docs directory** | "Which directory contains your PRD, RFC, and task breakdown files?" | Must be specified |
| **Run output directory** | "Where should context files and the plan be written?" | `qa-artifacts/<epic-slug>/` under working directory |

Confirm before proceeding:
```
Source docs : /path/to/docs/
Run output  : qa-artifacts/gofood-sg-m5/
Proceeding with upstream-context mode…
```

---

### Step U2 — Scan and classify source docs

List the source docs directory. Classify each file by filename signal — do not read content.

| Doc type | Filename signals (case-insensitive) | Extractor |
|---|---|---|
| PRD | `prd`, `product requirement`, `product spec` | `prd-extractor` |
| RFC | `rfc`, `adr`, `design doc`, `technical design`, `tech design` | `rfc-extractor` |
| Tasks | `task`, `breakdown`, `jira`, `story`, `ticket` | `tasks-extractor` |
| Regression source | `regression`, `test case`, `browserstack` (JSON/CSV) | `regression-extractor` |

Supported types: `.pdf`, `.docx`, `.doc`, `.md`, `.json`, `.csv`.

When classification is **ambiguous** or a required type has **no match**, show candidates and
ask the user before running any extractor. When **multiple files match one type**, ask which
to use. Never guess.

---

### Step U3 — Check for existing context files

Scan the run output directory for already-present and valid-JSON context files:

| File | Skip extractor if present and valid |
|---|---|
| `prd_context.json` | `prd-extractor` |
| `rfc_context.json` | `rfc-extractor` |
| `tasks_context.json` | `tasks-extractor` |
| `regression_context.json` | `regression-extractor` |

Report before running anything:
```
Context file scan:
  prd_context.json        ✅ present — skipping prd-extractor
  rfc_context.json        ❌ missing — will run rfc-extractor
  tasks_context.json      ✅ present — skipping tasks-extractor
  regression_context.json ❌ missing — see Step U4
```
A file that exists but fails JSON parse is treated as absent.

---

### Step U4 — Regression context gate

Runs only when `regression_context.json` is absent. Check in order:

1. Regression source file present in source docs dir (Step U2 matched it) → spawn the `regression-extractor` agent.
2. BrowserStack MCP reachable → spawn the `regression-extractor` agent.
3. Neither → ask:

```
regression_context.json is missing. No regression source file or BrowserStack MCP
connection is available.

Without it:
  • All scenarios will have is_legacy_regression: false
  • Dedup matching will be skipped
  • Blast-radius testGroups will be absent from the signoff run

Proceed without regression context? (yes / no)
```

Record the answer in `orchestrator_run_log.json` under `regression_context_gate.user_decision`.

---

### Step U5 — Run Phase A extractors

Spawn only missing extractor agents, in this fixed order:

| # | Agent | Prompt params | Output |
|---|---|---|---|
| 1 | `prd-extractor` | `source_file=<PRD path> output_dir=<dir>` | `prd_context_v{N}.json` + `prd_context.json` |
| 2 | `rfc-extractor` | `source_file=<RFC path> output_dir=<dir> prd_context_path=<dir>/prd_context.json` | `rfc_context_v{N}.json` + `rfc_context.json` |
| 3 | `tasks-extractor` | `source_dir=<tasks dir> output_dir=<dir>` | `tasks_context_v{N}.json` + `tasks_context.json` |
| 4 | `regression-extractor` | `source_file=<file or omit> output_dir=<dir>` | `regression_context_v{N}.json` + `regression_context.json` |

On **REJECT**: write to `orchestrator_run_log.json`, stop, surface:
```
⛔ [extractor] rejected — halted.
Reason: <extractor's own reject payload>
Fix the source and re-invoke. Already-generated context files will be reused.
```

---

### Step U6 — DoR pre-validation

Fast gate before the Opus generation pass:

| Check | Pass | On fail |
|---|---|---|
| All 4 context files present (or regression waived) | Files parse as JSON | STOP |
| `prd_context` has ≥ 1 `acceptance_criteria` | `len > 0` | STOP — re-run prd-extractor |
| `rfc_context` has at least one non-`not_specified` contract | Any contract with `ready` or `draft` status | WARN, continue |
| `tasks_context` has `api_contract` and `test_layer` | Both keys non-empty | STOP — re-run tasks-extractor |
| `regression_context` (if present) has `resolvedServices[]` | Array present | STOP — re-run regression-extractor |

---

### Step U7 — Invoke `sdet-plan-generator` (upstream-context)

Spawn the `sdet-plan-generator` agent with prompt:
```
output_dir=<run output directory>
```
It detects `upstream-context` mode (no `sdet_plan.json`) and runs full scenario generation.
Do not pass or modify any context file — the agent reads all inputs directly from `output_dir`.

---

### Step U8 — Stop at human review gate ⛔

```
✅ SDET plan written → <output-dir>/sdet_plan_v{N}.json  [mode: upstream-context]
   Scenarios   : N total  (N automatable / N manual-deferred)
   Open decisions: N

Next steps:
  1. Review qa_analysis.md — read the analysis and generated scenarios.
  2. Fill ## Human Review → ### Feedback in qa_analysis.md.
  3. Re-invoke /aep-backend:backend-test-plan-generator — triggers review mode.
  4. After plan is approved, invoke /aep-backend:code-gen-orchestrator — it dispatches automation plan generation and every later stage as subagents.
```

---

## CODE-CHANGE-CONTEXT PATH — Post-build delta generation

Runs when: `sdet_plan.json` is present AND a code-change signal is available.

Post-build milestone: code is merged, `sdet_plan.json` already exists from the upstream-context
run. This path adds delta scenarios (`is_delta: true`) for new/changed endpoints and validation
rules not present in the PRD/RFC at plan time.

### Step C1 — Resolve run output directory

Ask if not provided. Default: same directory as the existing `sdet_plan.json`.

---

### Step C2 — Acquire code-change context

Check whether `code_change_context.json` already exists in the output directory:

- **Present and valid** → skip to Step C3.
- **Absent** → ask the user for the code-change source:

```
code-change-context mode requires code_change_context.json.

Provide one of:
  A. Path to a GitLab unified diff file (aggregated Epic MR diffs, not individual commits)
  B. Paste the diff directly into the chat
  C. GitLab MR URLs for the Epic (I will read them)

Which do you have?
```

Once the source is confirmed, spawn the `code-change-extractor` agent with prompt:
```
source=<diff file path | pasted diff | MR URLs>
output_dir=<run output directory>
```
It produces `code_change_context_v{N}.json` + `code_change_context.json`. It extracts:
new/changed endpoints, validation rules, error mappings, DB changes, feature flags, proto
changes — filtering out logging, formatting, and unit test changes. Do not re-implement
that logic here.

**On agent REJECT:** stop and surface the reject. Do not spawn `sdet-plan-generator`.

---

### Step C3 — DoR pre-validation (code-change-context)

| Check | Pass | On fail |
|---|---|---|
| `sdet_plan.json` present and `status != "draft"` | Plan was reviewed before this run | WARN — delta on un-reviewed base; confirm with user |
| `code_change_context.json` present and non-empty | At least one category has entries | STOP — nothing to delta-generate |
| `tasks_context.json` present | Used by sdet-plan-generator for layer classification | WARN if absent, continue |

---

### Step C4 — Invoke `sdet-plan-generator` (code-change-context)

Spawn the `sdet-plan-generator` agent with prompt:
```
output_dir=<run output directory>
```
It detects code-change-context mode from the presence of `sdet_plan.json` +
`code_change_context.json` and generates only delta scenarios.

Outputs: updated `sdet_plan_v{N}.json` (delta scenarios appended) + `sdet_plan.json`.

---

### Step C5 — Stop at human review gate ⛔

```
✅ Delta generation complete → <output-dir>/sdet_plan_v{N}.json  [mode: code-change-context]
   Delta scenarios added : N  (all is_delta: true)
   Existing scenarios    : unchanged

Next steps:
  1. Review the delta scenarios in qa_analysis.md.
  2. Fill ## Human Review → ### Feedback.
  3. Re-invoke /aep-backend:backend-test-plan-generator — triggers review mode.
```

---

## DOC-CHANGE-CONTEXT PATH — PRD or RFC updated

Runs when: `sdet_plan.json` is present AND the user signals a doc update via `--doc-updated`
flag or by providing an updated doc file path as an argument.

**Design principle:** no doc-change-extractor, no diff analysis. Instead — re-run the relevant
extractor(s) on the updated doc to produce a fresh versioned context file, then invoke
`sdet-plan-generator` in `upstream-context` mode for a full regeneration. Re-extraction +
full regeneration is simpler and more token-efficient than extracting a diff and patching.

### Step D1 — Resolve doc update source and output directory

Read the args for which doc(s) changed:

| Flag | Meaning | Extractor to re-run |
|---|---|---|
| `--doc-updated prd=<path>` | PRD was updated | `prd-extractor` |
| `--doc-updated rfc=<path>` | RFC was updated | `rfc-extractor` |
| `--doc-updated prd=<path> rfc=<path>` | Both updated | `prd-extractor`, then `rfc-extractor` |

If neither is provided, ask:
```
Which document was updated?
  A. PRD — provide the new file path
  B. RFC — provide the new file path
  C. Both — provide both file paths
```

Run output directory: same directory as the existing `sdet_plan.json` unless overridden.

---

### Step D2 — Re-run the stale extractor(s)

Spawn only the extractor agent(s) for the updated doc(s). **Force re-run even if the context
file is present** — the doc changed, so the existing file is stale.

| Updated doc | Agent | Prompt params | Output |
|---|---|---|---|
| PRD | `prd-extractor` | `source_file=<new PRD path> output_dir=<dir>` | `prd_context_v{N}.json` + `prd_context.json` (new version) |
| RFC | `rfc-extractor` | `source_file=<new RFC path> output_dir=<dir> prd_context_path=<dir>/prd_context.json` | `rfc_context_v{N}.json` + `rfc_context.json` (new version) |

The extractor writes a new versioned file alongside the old one — the prior version is
preserved. The current pointer (`prd_context.json` / `rfc_context.json`) is updated to point
to the new version, which is what `sdet-plan-generator` will read.

On **REJECT**: stop and surface the reject. Do not invoke `sdet-plan-generator`.

Surface version bump before continuing:
```
doc-change-context — extractor(s) refreshed.
  prd_context.json → prd_context_v{N}.json  (was v{N-1})
  rfc_context.json → rfc_context_v{N}.json  (was v{N-1})
Proceeding to full plan regeneration…
```

---

### Step D3 — Invoke `sdet-plan-generator` (upstream-context)

Spawn the `sdet-plan-generator` agent with prompt:
```
output_dir=<run output directory>
```
With the fresh context files in place and no `code_change_context.json`, it detects
`upstream-context` mode and regenerates the full scenario set. The prior `sdet_plan.json`
is superseded — a new versioned file is written.

Outputs: `sdet_plan_v{N}.json` (full regeneration) + `sdet_plan.json`.

---

### Step D4 — Stop at human review gate ⛔

```
✅ Plan regenerated → <output-dir>/sdet_plan_v{N}.json  [mode: doc-change-context]
   Full regeneration from updated context — all scenarios re-derived.
   Prior plan preserved at sdet_plan_v{N-1}.json for diff reference.

Next steps:
  1. Diff sdet_plan_v{N}.json vs sdet_plan_v{N-1}.json to see what changed.
  2. Review qa_analysis.md and fill ## Human Review → ### Feedback.
  3. Re-invoke /aep-backend:backend-test-plan-generator — triggers review mode.
```

---

## REVIEW PATH — Apply human feedback

Runs when: `sdet_plan.json` + `qa_analysis.md` with `### Feedback` content are both present.

### Step R — Invoke `sdet-plan-generator` (review)

No extractor agents run. Spawn the `sdet-plan-generator` agent with prompt:
```
output_dir=<run output directory>
```
It reads `qa_analysis.md` feedback and patches `sdet_plan.json` accordingly.

Outputs: updated `sdet_plan_v{N}.json` + `sdet_plan.json`.

After completion, surface:
```
✅ Review complete → sdet_plan_v{N}.json  [mode: review]
   Scenarios added    : N
   Scenarios modified : N
   Scenarios deprecated: N
   Plan status        : <approved | draft | in_review>

If status is "approved":
  → Invoke /aep-backend:code-gen-orchestrator to continue to Phase C.
If status is still "draft" or "in_review":
  → More feedback needed — repeat the review cycle.
```

---

## Run log — `orchestrator_run_log.json`

Append to this file throughout the run. Key fields:

```json
{
  "skill": "aep-backend:backend-test-plan-generator",
  "invoked_at": "<ISO8601>",
  "mode": "upstream-context | code-change-context | doc-change-context | review",
  "run_output_dir": "<path>",
  "source_docs_dir": "<path — null for code-change-context/doc-change-context/review>",
  "steps": [ ... ],
  "outcome": "COMPLETED | STOPPED_REVIEW_GATE | REJECTED | ERROR"
}
```

---

## What this skill does NOT own

| Concern | Owner |
|---|---|
| AC extraction | `prd-extractor` |
| Validation sequence, RFC contracts | `rfc-extractor` |
| Test layer assignment, API contract | `tasks-extractor` |
| Regression blast-radius | `regression-extractor` |
| Code diff signal extraction | `code-change-extractor` |
| Team resolution, scenario generation, CSV | `sdet-plan-generator` |
| Post-approval automation plan | `automation-plan-generator` (separate, gated) |
| Test data provisioning | `test-data-identification` (separate, human-gated) |
