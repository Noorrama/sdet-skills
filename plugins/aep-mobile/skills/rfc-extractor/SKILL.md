---
name: mobile-rfc-extractor
description: Extract comprehensive technical context from a mobile RFC into rfc_context.json — scope, experimentation flags, architectural risks, compatibility mandates, rollout plan, API contracts, state management, navigation/deep links, local data changes, platform-specific details, permissions, offline behavior, accessibility impacts, lifecycle considerations, dependency changes, notification changes, cross-cutting concerns, and open questions. App-agnostic; optional (only when an RFC exists). Tells the SDET_PLAN where to concentrate depth, which flags/N-1 versions to parameterise, and what mobile-specific edge cases to cover.
---

# Mobile RFC Extractor (all 5 GoTo apps)

Distils the RFC into the risk/scope/technical signals that shape test prioritisation and mobile-specific scenario generation. Skipped when an EPIC has no RFC.

## Config
`config/<app>.json` → set `rfc_context.app = app_id`.

## Reads
RFC document (Lark/Confluence/PDF) — **single input**. This skill reads only the RFC. Cross-references against PRD and design are handled downstream by the `sdet-plan-generator`, which ingests all extractor outputs and performs gap analysis.

## Model
Fast tier — Haiku / Composer 2.5. Escalate to reasoning only if the RFC is long/ambiguous or contains complex architectural trade-off analysis.

---

## Extract (→ rfc_context.schema.json)

### Top-Level Metadata
- `rfc_id`, `rfc_title`, `rfc_url`, `rfc_status` — from the RFC header/metadata table.
- `extracted_at` — ISO timestamp of extraction run.
- `extractor_version` — skill version (currently `"1.0.0"`).

### Core Technical Sections

1. **scope** — `affected_services`, `affected_modules`, `affected_screens`, `target_platforms`, `change_type`, `platform_dimension`. Map from RFC's "Requirements" and "Solution" sections.

2. **experimentation_matrix** — Each feature flag/experiment with `flag_key`, `variants`, `default_variant`, `gated_module`, `gated_approach`, `kill_switch`. Extract from dedicated Experimentation/Feature Flag sections. Include Litmus, Firebase, or custom flag systems.

3. **architectural_risks** — `risk_id`, `description`, `severity`, `affected_modules`, `mitigation`, `testability_note`. Extract from explicit "Risks" sections. Also extract from "Cons" listed under each solution approach — these are implicit risks. Always include a `testability_note` suggesting how QA can verify the risk/mitigation.

4. **compatibility_mandates** — `min_supported_app_version`, `min_os_version`, `degrade_strategy`, `n_minus_1_behavior`, `upgrade_path`. Extract from backward compatibility sections.

5. **rollout_plan** — `environment_order`, `percentage_ramp` (array of percentage/criteria/duration), `rollback_triggers`, `rollback_strategy`, `kill_switch_flag`, `canary_metrics`.

6. **api_contract_changes** — `endpoint`, `method`, `change_type` (NEW/MODIFIED/DEPRECATED), `request_shape`, `response_shape`, `new_error_codes`, `breaking_change`. Empty array `[]` if the RFC explicitly has no API (e.g., Litmus-driven features).

7. **state_management_changes** — `entity`, `change_type`, `new_fields`, `removed_fields`, `state_transitions` (from/to/trigger). Extract from flow diagrams and state machine descriptions.

### Mobile-Specific Sections (Rule 7 — `inferred_from_prose`)

These sections may or may not have dedicated RFC sections. When the information is extracted from a **dedicated section** (e.g., "Navigation", "Deep Links"), set `inferred_from_prose: false`. When **inferred from prose** in other sections (e.g., flow descriptions, open questions, PRD requirements), set `inferred_from_prose: true`.

8. **navigation_changes** — `change_type` (NEW_SCREEN/NEW_DEEP_LINK/MODIFIED_FLOW), `screen_id`, `deep_link`, `deep_link_params`, `parent_flow`, `entry_points`.

9. **local_data_changes** — `storage_type` (ROOM/SHARED_PREFS/CACHE/PERSISTENCE/etc.), `change_type`, `entity_or_key`, `migration_version`, `migration_strategy`, `data_loss_risk`, `rollback_safe`.

10. **platform_specific** — Per-platform (`android`, `ios`, `flutter`) implementation notes, SDK versions, modules/targets, parity status.

11. **permissions_required** — `permission` (manifest string), `platform`, `purpose`, `is_new`, `deny_behavior`, `rationale_shown`.

12. **offline_behavior** — `offline_capable`, `sync_strategy` (FAIL_FAST/CACHE_FIRST/QUEUE_AND_SYNC/OFFLINE_FIRST), `cached_data_ttl`, `offline_ui_state`, `reconnection_behavior`, `partial_sync_handling`.

13. **accessibility_impacts** — Per `screen_id`: `change_description`, `content_descriptions_required`, `focus_order_defined`, `dynamic_content_announced`.

14. **lifecycle_considerations** — `event` (PROCESS_DEATH/CONFIG_CHANGE/BACKGROUND_FOREGROUND/APP_UNINSTALL_REINSTALL), `affected_screen`, `expected_behavior`, `state_preservation` (FULL_RESTORE/PARTIAL_RESTORE/RESTART_FLOW/NO_RESTORE).

15. **dependency_changes** — `dependency_name`, `change_type` (NEW/UPGRADED/EXISTING/REMOVED), `old_version`, `new_version`, `breaking_changes`, `initialization_changes`, `test_impact`.

16. **notification_changes** — `type` (PUSH/LOCAL/IN_APP), `channel_id`, `trigger`, `payload_shape`, `deep_link_on_tap`, `background_task`.

### Cross-Cutting

17. **cross_cutting_concerns** — `observability` (new_metrics, new_alerts, clickstream_events), `security` (auth_changes, data_sensitivity, certificate_pinning_changes), `performance` (latency_targets, app_size_impact, memory_impact, battery_impact, startup_time_impact).

18. **open_questions** — `question_id`, `question`, `owner`, `status` (OPEN/RESOLVED/DEFERRED), `impact_on_testing`. Extract from "Open Questions" sections. Also capture questions embedded in italic/bold answers within the RFC.

> **Note:** `prd_cross_refs` and `design_cross_refs` are **not populated by this skill**. These fields exist in the schema for the `sdet-plan-generator` to populate during its cross-stage gap analysis, where it compares `rfc_context.json` against `prd_context.json` and `design_context.json`. This skill should omit these fields from its output.

---

## Extraction Rules

### Rule 1: Faithful extraction only
Extract what the RFC states. Do not invent risks, endpoints, or constraints not present in the document.

### Rule 2: Approach-aware extraction
RFCs often present multiple approaches with one marked "Preferred" or "Selected". Extract details from the **selected/preferred approach only** for the primary output. Capture rejected approaches as context in `architectural_risks` if they reveal important trade-offs.

### Rule 3: Risk extraction from Pros/Cons
Every "Cons" bullet under a selected approach is a potential `architectural_risk`. Convert the con into a risk with appropriate severity and a testability note.

### Rule 4: Deprecated section handling
Sections marked "Deprecated" in the RFC should be noted but not extracted into the primary output. If a deprecated section (e.g., "API Deprecated") means `api_contract_changes` is empty, set it to `[]` explicitly.

### Rule 5: Open question answers
When open questions have inline answers (typically in bold/italic), extract both the question and the answer. Set status to `RESOLVED` if answered, `OPEN` if unanswered, `DEFERRED` if explicitly deferred.

### Rule 6: Contract/data structure extraction
When the RFC includes JSON contracts or data schemas (e.g., Litmus payloads, API responses), use these to inform `state_management_changes` fields and `api_contract_changes` shapes.

### Rule 7: `inferred_from_prose` marker
For mobile-specific sections (8–16), set `inferred_from_prose: false` when extracted from a dedicated RFC section, and `true` when the information is synthesized from prose in other sections (e.g., flow descriptions, open questions). This tells downstream consumers the confidence level of the extraction.

---

## Definition of Ready — reject/flag if
- Impact/blast-radius absent (no scope section or no affected screens listed)
- No backward compatibility statement (N-1 behavior undefined)
- Risks unrated (no severity on any risk)
- No rollback strategy defined
- Feature flags mentioned but not documented with variants/defaults
- No solution approach clearly marked as selected/preferred when multiple are presented

## Guardrails
- Do not infer risks not stated — unknowns go to `open_questions` with `impact_on_testing`.
- `inferred_from_prose` must be set correctly — never omit this field on mobile-specific sections.
- Empty arrays `[]` are valid when the RFC explicitly has no items for a section (e.g., no API changes). Do not omit the key.
- Output valid JSON only, conforming to `schemas/rfc_context.schema.json`.
- Do not populate `prd_cross_refs` or `design_cross_refs` — these are filled downstream by `sdet-plan-generator`.

## Validate
```
python3 -c "import json,jsonschema; jsonschema.validate(
  json.load(open('rfc_context.json')),
  json.load(open('schemas/rfc_context.schema.json')))"
```

## Downstream consumers
- **sdet-plan-generator** — uses `experimentation_matrix` for flag toggle scenarios, `api_contract_changes` for contract tests, `local_data_changes` for migration scenarios, `permissions_required` for permission grant/deny scenarios, `lifecycle_considerations` for process death/config change scenarios, `architectural_risks` for risk-focused P0 tests.
- **test-data-provisioner** — uses `api_contract_changes` shapes and `state_management_changes` to determine test data requirements.
