---
name: backend-prd-extractor
description: Extract product intent from a backend PRD into prd_context.json, from a QA/test-design perspective. Reads the PRD end-to-end — body AND review comment thread — and maps requirements (business + product), GIVEN/WHEN/THEN acceptance criteria with a verifiable flag, boundary values and edge cases, undecided decisions with contingent option branches, comment resolutions, feature flags, the end-to-end flow with its failure states, and a Definition-of-Ready gate. Feeds sdet-plan-generator with scenario priority, risk weighting, boundary/negative scenarios, out-of-scope suppression, and which criteria are actually assertable.
---

# Backend PRD Extractor (QA lens)

Convert a backend PRD into a schema-compliant, **test-design-ready** `prd_context.json` for the backend SDET pipeline. You are not summarising the PRD for a product reader — you are turning it into the **test oracle contract** that `sdet-plan-generator` uses to decide *what to assert, at what priority, and what it must NOT assert yet.*

> **The QA question behind every field is: "Can I write a deterministic test from this — and if not, why not?"** A criterion you can assert becomes a scenario. A criterion you cannot assert (ambiguous, conflicting default, contingent on an unresolved decision) is worth *more* to QA than a clean one — it is a bug in the spec that must be surfaced, not smoothed over. Extract everything; flag everything you cannot verify.

## Reads
The PRD document — path passed as an argument, or the latest PRD MD / Confluence / Lark / PDF export in the feature folder. Read the **entire** document: body, tables, appendices, footnotes, diagram captions, **and the review comment thread**. On real PRDs the comment thread is where defaults get changed, flags get renamed, and decisions are left open — a body-only read will miss the highest-value QA signal.

**Large / raw exports.** A raw Confluence/Lark export can be tens of MB and won't fit in one read. Do NOT skim the first page and stop. Instead: (1) get the outline first (`grep -n "^#\|^##\|Scope\|Out of scope\|Flow\|Logic\|Edge\|Fallback\|Decision\|Experiment\|Metric\|Risk"`), then (2) read section-by-section with `Read` offsets/limits, extracting as you go, and (3) read the comment thread separately. Never fabricate content for a section you could not read — flag it in `needs_clarification` with `reason: non_extractable`.

## Model
Fast tier — Haiku. Escalate to a reasoning model when the PRD has an undecided design fork (option A/B), conflicting defaults, or a long comment thread that changes the body — i.e. exactly the cases QA cares about most.

## Extraction workflow (two passes)

**Pass 1 — Read the whole PRD, extract nothing.** Build the map a tester needs:
- What behaviour changes? What is the *old* behaviour (the regression baseline) vs the *new*?
- Who are the actors and what is the end-to-end flow? Where can it fail?
- What are the thresholds, defaults, and flags? Where does the PRD state the *same* default twice with *different* values?
- What decisions are still open? Does the comment thread resolve, clarify, or leave them open?
- What is explicitly out of scope — and does any later section contradict that?

**Pass 2 — Extract into the schema, keeping traceability.** Give every requirement, criterion, and decision a stable id and cross-link them (`story_ref`, `requirement_ref`, `related_open_decision`). Traceability is what lets the SDET plan prove coverage and lets a re-trigger patch only the affected scenarios. When a value is unstated, conflicting, or unverifiable, **record it in `needs_clarification` — never invent it.**

## What to extract

| Section | What to capture | Where it maps |
|---|---|---|
| Metadata | Title, PRD id (slug if none), readiness, owner (NOT comment authors), team, source path | `title`, `id`, `readiness`, `owner`, `team`, `source_ref` |
| Scope | Explicit in-scope and out-of-scope bullets, verbatim | `in_scope[]`, `out_of_scope[]` |
| **Personas & prereqs** | **User personas — distinct journeys/states, not teams.** Examples: "Fresh Lead" (new), "Existing User (Resigned)", "Deleted Account". Capture actor states/preconditions that branch the flow. | `personas[]`, `persona_prerequisites[]` |
| Applicability | Service verticals (Food …) and country gating | `applicable_service_types[]`, `applicable_countries[]` |
| End-to-end flow | **Multiple flows**: happy path, persona-specific paths, deviation paths (retry, fallback). Ordered steps (actor + action, numbered) showing where paths diverge. Failure/edge outcomes labeled by persona. | `user_flows[]` (name, trigger, steps[], failure_states[] with persona_ref) |
| Involved teams | Each team the flow touches and its role (per-branch role if the design is forked) | `involved_teams[]` |
| User stories | *As a [persona] I want [goal] so that [benefit].* **Map to the personas extracted above.** Assign `US-001…` if unnumbered | `user_stories[]` |
| **Requirements** | Pair the **business_requirement** (why) with the **product_requirement** (concrete, testable what). **Map to affected persona(s) via `story_ref`.** Tag owning team | `requirements[]` |
| **Acceptance criteria** | One per testable rule, as **GIVEN/WHEN/THEN**, copying the PRD's operators verbatim. Set **`verifiable`** honestly. **Include persona-specific ACs when paths diverge** | `acceptance_criteria[]` |
| **Boundary values** | Every threshold/default (legacy value, new default, clamp, compare operator) — copied, never derived | `boundary_values[]` |
| **Boundary conditions** | Edge-case table rows with their expected default behaviour; carry "example only" notes | `boundary_conditions[]` |
| Feature flags | **All** flag/field names — including competing candidate names for the same flag | `feature_flags[]` |
| Business error scenarios | User-facing failures: trigger → message → recovery | `error_codes[]` |
| NFR | Quantitative latency/throughput/uptime/security targets only | `non_functional_requirements[]` |
| **Open decisions** | Unresolved decisions with a testing impact; `blocking` if the oracle is undefined until resolved | `open_decisions[]` |
| **Approach branches** | When a blocking decision forks the design into mutually exclusive options | `approach_branches` |
| **Comment resolutions** | Decisions/clarifications mined from the review thread. **Show what was ambiguous, what's now clear, and how SDET plan uses this.** NOT passive recording — active guidance. | `comment_resolutions[]` |
| Risk areas | High-value/high-risk flows | `risk_areas[]` |
| Success / rollout | Metrics and rollout/experiment ramp if stated | `rollout_plan`, (metrics → `risk_areas`/`needs_clarification` if only qualitative) |
| **Needs clarification** | Every gap, ambiguity, conflict, and non-verifiable criterion — the Definition-of-Ready gate | `needs_clarification[]` |

## QA field-level guidance

- **Acceptance criteria are GIVEN/WHEN/THEN, and `verifiable` is not decoration.** Set `verifiable: true` only when a deterministic assertion can be written *today* from the PRD alone. Set `verifiable: false` when the oracle is undefined — a conflicting default, an ambiguous operator, an experiment treatment the PRD says is "example only", or a criterion gated on an unresolved `open_decision`. Every `verifiable: false` MUST have a matching `needs_clarification` entry explaining the blocker. This flag is how the SDET plan avoids writing a test that "passes" against a spec that hasn't been decided.
- **Copy operators and thresholds verbatim.** `>=`, `>`, `<= 0`, `> 9` are different tests. Never normalise `>= min` into `> min-1`. Boundary-value analysis lives or dies on the exact operator.
- **Boundary values vs boundary conditions.** `boundary_values` = the named numbers/defaults (legacy `dish_list > 9`, new default `2`, clamp rule, compare operator). `boundary_conditions` = the edge-case *rows* with expected behaviour (`dish_list = 0 → Do not show`). Together they are the negative/boundary scenario seeds — extract both.
- **Competing flag names are a finding, not a pick.** If the PRD (or a comment) uses `enable_see_all_flag`, `force_enable_see_all_flag`, and `always_show_see_all` for the same concept, list **all three** in `feature_flags` and raise an `open_decision` for the canonical name. Silently choosing one hides an integration-contract risk.
- **Conflicting defaults are the highest-value QA finding.** When the same default is stated twice with different values (e.g. `min_dish_count` default = 9 in §4.2 but = 2 in the Fallback Strategy), record **both** as `boundary_values`, raise a `blocking` `open_decision`, add a `needs_clarification` with `reason: conflicting`, and mark any AC that depends on it `verifiable: false`. Do not pick a winner.
- **Undecided design forks → `approach_branches`, keep BOTH paths.** When a blocking decision splits the design into mutually exclusive options (Option A vs Option B), tag branch-only requirements/ACs with `[Option X only]` in their text, list shared refs in `shared_requirement_refs` / `shared_acceptance_criteria_refs`, and list each option's exclusive refs under `branches[]`. While `status: undecided`, the SDET plan must hold parallel contingent paths — do **not** treat either branch as the sole oracle. If the PRD (or a `resolves` comment) locks one option, set `status: resolved`, `chosen_branch`, and drop the other branch's refs.
- **Mine the comment thread; grade each comment.** `resolves` = an authoritative decision (treat as fact, note what it changes). `clarifies` = context that explains intent but does **not** lock a decision (do not act on it as if resolved). `unanswered` = an open question or a rename suggestion with no acceptance (leave the decision open). Always keep a short verbatim `quote` and the `affects` refs so the decision is traceable.
- **"Example, not for treatment" is a trap — label it.** If the PRD or a comment says an edge-case column / config is illustrative only, capture it in `boundary_conditions` with that note in `proposed_default`, and add an AC with `verifiable: false` if anything might read it as a treatment. This prevents the SDET plan from asserting a non-existent A/B arm.
- **Out-of-scope is a first-class output — and check it for contradictions.** Record every exclusion. If a later section (or an option's treatment) contradicts the exclusion, keep the exclusion AND raise a `blocking` `open_decision` + `needs_clarification` for the conflict.
- **Owner ≠ comment author.** The people commenting on the PRD are reviewers, not the DRI. Leave `owner: null` unless the body names one.
- **NFR numbers are copied, never invented.** "should be fast" is not a latency target — put it in `needs_clarification`, not `non_functional_requirements`.

## Output → prd_context.json

Root fields (see `schemas/prd_context.schema.json` for the authoritative shape). Required: `title`, `requirements`, `acceptance_criteria`, `needs_clarification` (arrays may be empty only after a genuine check).

- `id`, `title` (required), `priority`, `readiness`, `owner`, `team[]`, `pdg[]`, `milestones[]`, `summary`, `source_ref`
- `in_scope[]`, `out_of_scope[]`
- **`user_flows[]`** — `name`, `trigger`, `steps[]` (required: `step`=integer, `actor`, `action`), `failure_states[]` (`name`, `outcome`, optional `persona_ref`)
- `personas[]`, `persona_prerequisites[]`, `applicable_countries[]`, `applicable_service_types[]`, `rollout_plan`
- `involved_teams[]` — `team`, `role`
- `user_stories[]` — `id`, `description`, optional `owner`/`team`
- `requirements[]` (required) — `id`, `product_requirement` (required), `business_requirement`, `story_ref`, `team`
- `acceptance_criteria[]` (required) — `id`, `condition` (GIVEN/WHEN/THEN), `verifiable` (required bool), `requirement_ref`, `story_ref`
- `boundary_values[]` — `name`, `value`, `requirement_ref`
- `boundary_conditions[]` — `edge_case_description`, `proposed_default`, `requirement_ref`
- `error_codes[]` — business/user-facing errors (technical codes belong to the RFC extractor)
- `feature_flags[]` — all names, including competing candidates
- `non_functional_requirements[]`
- `open_decisions[]` — `id`, `decision`, `blocking`
- `approach_branches` — `decision_ref`, `status: undecided|resolved`, `chosen_branch`, `rule`, `shared_*_refs[]`, `branches[]`
- `comment_resolutions[]` — `id`, `status: resolves|clarifies|unanswered`, `topic`, `quote`, `affects[]` (specific item refs like REQ-003, AC-041, not generic categories), `related_open_decision`, **`what_was_ambiguous`** (original PRD gap), **`what_is_now_clear`** (resolution from thread), **`implication_for_sdet`** (how SDET plan uses this to refine requirements/ACs or lock decisions)
- `risk_areas[]` — `risk`, `severity`, `mitigation`
- `needs_clarification[]` (required) — `field`, `reason: missing_from_source|ambiguous|non_verifiable|conflicting|contradictory|non_extractable`, `blocking`, `detail`

## Worked micro-example (from the "See All" PRD)

> PRD §5: *"if enable_see_all_flag == true: show see_all when dish_list.size >= min_dish_count_for_see_all."* §4.2: *"min_dish_count_for_see_all default = 9."* Fallback Strategy: *"Missing threshold → use default (2)."* §6: undecided whether **MLS** (Option A) or **Gateway** (Option B) reads Litmus. Comment: *"This is example for understanding, not for treatment."*

```json
{
  "user_flows": [
    { "name": "Happy Path", "trigger": null,
      "steps": [
        { "step": 1, "actor": "User", "action": "Views list of dishes" },
        { "step": 2, "actor": "MLS", "action": "Evaluates enable_see_all_flag and min_dish_count" },
        { "step": 3, "actor": "MLS", "action": "Shows 'See All' button when threshold met" },
        { "step": 4, "actor": "User", "action": "Clicks 'See All' to expand list" }
      ],
      "failure_states": [
        { "name": "dish_list = 0", "outcome": "Do not show 'See All' button", "persona_ref": null }
      ]
    }
  ],
  "requirements": [
    { "id": "REQ-003", "story_ref": "US-001", "team": "MLS",
      "business_requirement": "When the flag is on, apply a configurable threshold instead of the hard-coded > 9 rule.",
      "product_requirement": "If enable_see_all_flag == true: show_see_all = true when dish_list.size >= min_dish_count_for_see_all." }
  ],
  "acceptance_criteria": [
    { "id": "AC-001", "requirement_ref": "REQ-003", "story_ref": "US-001", "verifiable": true,
      "condition": "GIVEN enable_see_all_flag == true AND dish_list.size >= min_dish_count_for_see_all WHEN MLS evaluates show_see_all THEN show_see_all = true." },
    { "id": "AC-006", "requirement_ref": "REQ-006", "story_ref": "US-001", "verifiable": false,
      "condition": "GIVEN min_dish_count_for_see_all is missing WHEN MLS applies fallback THEN it uses default (2)." }
  ],
  "boundary_values": [
    { "name": "legacy show_see_all threshold", "value": "dish_list > 9", "requirement_ref": "REQ-004" },
    { "name": "min_dish_count default (§4.2 Backward Compatibility)", "value": "9", "requirement_ref": "REQ-005" },
    { "name": "min_dish_count default when missing (Fallback Strategy)", "value": "2", "requirement_ref": "REQ-006" }
  ],
  "boundary_conditions": [
    { "requirement_ref": "REQ-007", "edge_case_description": "dish_list = 0", "proposed_default": "Do not show" },
    { "requirement_ref": "REQ-007", "edge_case_description": "User click 'see all' Config 1 vs Config 2 (SDMC)", "proposed_default": "example for understanding, not for treatment" }
  ],
  "feature_flags": ["enable_see_all_flag", "force_enable_see_all_flag", "always_show_see_all"],
  "open_decisions": [
    { "id": "OD-001", "decision": "Who reads Litmus — Option A (MLS-only) vs Option B (GW-controlled).", "blocking": true },
    { "id": "OD-003", "decision": "Canonical default for missing min_dish_count — 9 (§4.2) vs 2 (Fallback).", "blocking": true }
  ],
  "approach_branches": {
    "decision_ref": "OD-001", "status": "undecided", "chosen_branch": null,
    "rule": "Emit parallel contingent Option A/B paths while undecided; collapse to chosen_branch once OD-001 locks.",
    "shared_requirement_refs": ["REQ-003", "REQ-004", "REQ-005"],
    "shared_acceptance_criteria_refs": ["AC-001"],
    "branches": [
      { "id": "Option A", "label": "MLS-only Experiment", "requirement_refs": ["REQ-009"], "acceptance_criteria_refs": ["AC-013"] },
      { "id": "Option B", "label": "GW-controlled Experiment", "requirement_refs": ["REQ-002"], "acceptance_criteria_refs": ["AC-010"] }
    ]
  },
  "comment_resolutions": [
    { "id": "CR-001", "status": "resolves", "topic": "SDMC Config 1/2 as treatment",
      "quote": "This is example for understanding ,not for treatment", "affects": ["boundary_conditions[SDMC row]", "AC-012"],
      "related_open_decision": null,
      "what_was_ambiguous": "Is User click 'see all' Config 1 vs Config 2 (SDMC row) a real treatment arm in the feature design?",
      "what_is_now_clear": "No — SDMC Config 1/2 is illustrative only, not a real A/B treatment. Do not assert different behaviour per config.",
      "implication_for_sdet": "Mark AC-012 verifiable:false if it reads SDMC configs as distinct arms. Do not generate paired SDMC Config 1 vs Config 2 scenarios." }
  ],
  "needs_clarification": [
    { "field": "boundary_values[min_dish_count default]", "reason": "conflicting", "blocking": true,
      "detail": "§4.2 default = 9 vs Fallback Strategy default = 2; AC-006 not verifiable until OD-003 locks." },
    { "field": "feature_flags", "reason": "ambiguous", "blocking": true,
      "detail": "enable_see_all_flag / force_enable_see_all_flag / always_show_see_all name the same flag; see OD-002." },
    { "field": "open_decisions[OD-001]", "reason": "ambiguous", "blocking": true,
      "detail": "Approach undecided — keep both Option A/B contingent paths; do not lock a single oracle." }
  ]
}
```

## Guardrails
- **Faithful extraction only.** Extract what is stated. Conflicts, gaps, and unverifiable rules go to `needs_clarification` — never guess a value to make a criterion look testable.
- **Every acceptance criterion sets `verifiable`, and every `verifiable: false` has a `needs_clarification` entry.**
- **Every acceptance criterion traces to a requirement and/or a user story.**
- **Boundary thresholds and operators are copied verbatim, never derived.**
- **`out_of_scope` is a first-class output**; contradictions with it are `blocking` open decisions.
- **Undecided forks keep both branches** — do not collapse `approach_branches` to one option until the PRD locks it.
- Include empty arrays only after a genuine check. Output **valid JSON only**, conforming to the schema. No prose outside the JSON file.

## Definition of Ready — a PRD is NOT ready for a deterministic SDET plan if any of these are true (record each in `needs_clarification`, `blocking: true`, and do not silently proceed)
- A blocking `open_decision` is unresolved (e.g. an undecided Option A/B fork) — the oracle is undefined.
- The same threshold/default is stated with two different values.
- A flag/field has competing candidate names with no canonical pick.
- A P0/P1 requirement has no acceptance criterion, or its criterion is `verifiable: false`.
- The PRD has no explicit out-of-scope section, or out-of-scope conflicts with a later section.
- An "experiment treatment" is illustrative only ("example, not for treatment") but read as a real arm.
- NFR language is qualitative ("fast", "reliable") with no number.

## Validate
Validate the output against the schema before handing off:
`jsonschema.validate(output, schemas/prd_context.schema.json)`

Do not treat "I confirmed it's valid JSON" as validation — that only checks syntax, not the schema. Fix any reported field and re-validate until it passes.

## Downstream consumers
- **sdet-plan-generator** — uses `requirements` + `acceptance_criteria` for coverage; **`verifiable: false` criteria and `blocking` `needs_clarification` gate deterministic scenario generation** for the affected area; `boundary_values` + `boundary_conditions` + `user_flow.failure_states` seed boundary/negative scenarios; `feature_flags` seed flag_on/flag_off pairs; `approach_branches` (while `undecided`) drive **parallel contingent** scenario paths per option; `out_of_scope` suppresses scenario generation; `risk_areas` drive P0/P1/P2 weighting; **`comment_resolutions` actively guide the plan**: each resolution shows what PRD ambiguity was resolved (`what_was_ambiguous`), what is now clear (`what_is_now_clear`), and how to apply the resolution to refine requirements/ACs or lock decisions (`implication_for_sdet`). Resolutions with `status: resolves` are authoritative; `clarifies` provide context but do not lock decisions; `unanswered` leave decisions open.

## Log
One-line summary: requirements, acceptance criteria (and how many are `verifiable: false`), boundary values/conditions, feature flags, open decisions (blocking count), approach-branch status, comment resolutions, and `needs_clarification` (blocking count) flagged.
