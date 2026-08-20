---
name: mobile-task-extractor
description: Normalize the Dev team's task-generation tree (Milestone → Epic → User Story → Task, from the PRD/RFC/design) into task_context.json — the PRIMARY DRIVER of the SDET_PLAN (RFC §2.4). Captures the work tree, acceptance criteria, per-task deep-link routing + observable state, cross-track dependencies, and task↔requirement↔screen traceability, PLUS the feature-level test hooks/screens/flags that let NLP steps reach a screen without a full UI walk. App-agnostic.
---

# Mobile Task Extractor — PRIMARY DRIVER (all 5 GoTo apps)

The primary driver for the SDET_PLAN (RFC §2.4 *Task Generation → QA*). The Dev "task generation"
team breaks a release into a JIRA tree (Milestone → Epic → User Story → Task) from the PRD, RFC and
design. This skill normalizes that tree into `task_context.json` — the hierarchy, acceptance
criteria, per-task routing/observable state, cross-track dependencies, and traceability back to the
PRD requirement/AC — and supplies the **test hooks** the navigation layer relies on (deeplinks /
state-injection), so automation can jump to the target screen instead of walking the whole UI.

## Config
`config/<app>.json` → `deeplink_scheme`; set `task_context.app = app_id`.

## Reads
The Dev-team input JSON conforming to `schemas/task_input.schema.json` — a tree of `milestones` +
`epics[] → user_stories[] → tasks[]`, plus `source_refs` and optional per-epic `implementation_hints`.
Hand that contract to the task-generation team so their export is well-formed. Fall back to a raw
JIRA export if the contract isn't yet adopted. Cross-reference `prd_context.json` / `rfc_context.json`
when available to confirm `requirement_id` (PRD `req_id`) and flag keys.

## Model
Fast tier — Composer 2.5. Escalate to reasoning if the tree/dependency graph is complex; scenario
quality downstream depends on this.

## Extract (→ task_context.schema.json)
1. **Tree** — `milestones`; `epics` (epic_id/title/goal/milestone_id); nested `user_stories`
   (user_story_id, title, `requirement_id` = PRD `req_id`, `acceptance_criteria` each with
   `acceptance_criteria_id`); nested `tasks` — tag each with its `track`
   (android/ios/flutter/backend/design/qa/infra/other), carry `deep_link`, `observable_state`,
   `dependencies`, `mr_refs`. Keep only QA-relevant fields; drop JIRA admin metadata
   (status/points/assignee/sprint/labels).
2. **Per-epic plan signals** — `change_summary`, `target_modules`, `screens_touched`, `view_models`,
   `new_components`, `flag_keys`, `test_hooks` (deeplink/flag-override/state-injection) — from the
   epic's `implementation_hints` when supplied; otherwise infer from task text.
3. **traceability** — for each task, map `user_story_id`, `requirement_id`, `acceptance_criteria_ids`
   and `screen_ids`.
4. **blocking_dependencies** — roll up cross-track blocking edges (e.g. a mobile task blocked by a
   backend task) so QA sequencing is explicit.
5. **stats** — counts `by_type`, `by_track` plus `total_epics`/`total_stories`/`total_tasks`.

## Definition of Ready — reject/flag if (RFC §2.4)
- A story has no acceptance criteria → `blocking_issues`.
- `source_refs` is missing a PRD/RFC/design link the tasks clearly derive from → `open_questions`.
- A dependency links a `task_id` not present in the tree → `blocking_issues`.
- A P0 task has no `deep_link`, no `observable_state`, or uses a flag not in the epic's `flag_keys`
  → `testability_gaps`.

## Guardrails
Be precise; don't invent hooks/tasks/links/requirements. Unknowns go to `open_questions`,
`blocking_issues`, or `testability_gaps` — never fabricate. Output valid JSON only, conforming to
`schemas/task_context.schema.json`.

## Downstream consumers
`sdet-plan-generator` (ingests `task_context.json` as the PRIMARY DRIVER, optional/graceful).
