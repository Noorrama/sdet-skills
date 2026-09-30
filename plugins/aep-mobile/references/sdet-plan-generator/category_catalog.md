# Category Catalog

The auto/extra partition is computed **solely** from the presence/values of schema fields across the supplied contexts — it is feature-independent. For each category: evaluate its trigger; if it fires → `auto_selected` (with the field as `reason`); if it does not → `optional_extras.feature_adjacent`. Universal hygiene categories with no schema trigger live in `optional_extras.fe_baseline`, gated by an applicability predicate.

## A. Detection Rules (AUTO when the field fires)

| Category | AUTO when |
|---|---|
| `functional` / `positive` | `prd.business_requirements[]` non-empty **or** `design.screens[]` non-empty |
| `negative_error` | `prd.boundary_conditions[]` has invalid/edge entries **or** any `rfc.api_contract_changes[].error_codes` |
| `boundary` | `prd.boundary_conditions[]` non-empty |
| `permission` | `rfc.permissions_required[]` non-empty **or** any design element's `validations_and_edge_cases` mentions a permission |
| `interruption_network` | `rfc.api_contract_changes[]` non-empty **or** any `task_context` task has an `observable_state` **or** `rfc.offline_behavior.offline_capable`/`sync_strategy` **or** a network/remote-asset `architectural_risk` |
| `interruption_lifecycle` (background/process-death) | `rfc.lifecycle_considerations[]` non-empty **or** design has interactive elements (input/toggle/form/carousel) **or** any `task_context.epics[].view_models[]` non-empty |
| `local_data_migration` (N-1) | `rfc.local_data_changes[]` with non-null `migration_version`/`migration_strategy` **or** `rfc.compatibility_mandates[]` non-empty |
| `feature_flag_killswitch` | `rfc.experimentation_matrix[]` **or** `prd.feature_flags[]` **or** any `task_context.epics[].flag_keys[]` non-empty |
| `deep_link_nav` | any `task_context.epics[].test_hooks[]` with `type == "deeplink"` (**or** any task-level `deep_link`) **or** any `rfc.navigation_changes[].deep_link` non-null |
| `telemetry_clickstream` | `prd.clickstream_events[]` **or** `rfc.cross_cutting_concerns.observability.clickstream_events[]` non-empty |
| `localization_regional` | `prd.applicable_countries.length > 1` **or** multiple locales / localized copy in design |
| `platform_variance` | `prd.applicable_platforms.length > 1` **or** `rfc.platform_specific.android`/`.ios` non-null **or** `rfc.scope.target_platforms.length > 1` |
| `theming_darkmode` | design theme-state variants **or** an `open_question` matching theme/dark-mode |
| `accessibility` | `rfc.accessibility_impacts[]` non-empty |
| `non_functional_perf` | `rfc.cross_cutting_concerns.performance` has any non-null target/impact |
| `offline` | `rfc.offline_behavior.offline_capable == true` **or** a `sync_strategy` present |

> A category whose trigger does NOT fire → `optional_extras.feature_adjacent` (rationale = the field checked was empty/absent). A missing context file simply means its triggers cannot fire — no failure.

## B. FE-Baseline Extras Library (`fe_baseline` pool; offer only when the predicate matches)

| Group | Categories | Offer only if… |
|---|---|---|
| `session_auth` | `multi_device_concurrent_login`, `forced_signout_mid_flow`, `session_expiry`, `logout_during_flow` | feature needs auth/identity (design uses login/AuthSDK, or `prd.target_personas` require an account) |
| `app_upgrade` | `n_minus_1_upgrade`, `fresh_vs_upgrade`, `uninstall_reinstall`, `data_migration` | app ships incrementally (always true for the 5 GoTo apps) |
| `device_env` | `rotation`, `split_screen`, `font_scaling`, `low_storage`, `low_battery`, `system_locale_tz_change` | screens not locked-portrait in `config.<app>.json` |
| `os_interruptions` | `incoming_call`, `notification_shade`, `background_foreground`, `permission_revoked_runtime`, `network_flip` | any interactive/networked screen |
| `nav_gesture` | `hardware_back`, `deeplink_tamper`, `up_navigation`, `restore_after_death` | any multi-screen flow |
| `privacy_security` | `screenshot_screenrecord`, `background_snapshot_mask`, `clipboard_exposure`, `log_leakage` | UI shows sensitive data (`rfc…data_sensitivity`, balance/PII) |
| `a11y_baseline` | `screenreader_traversal`, `contrast`, `touch_target` | any interactive screen |
| `l10n_baseline` | `rtl`, `string_truncation`, `number_date_currency` | `config.<app>.json` supports the relevant locale surface |
| `resilience` | `double_tap_debounce`, `offline_cold_start`, `empty_error_states` | any networked/stateful screen |

> When a `fe_baseline` extra is selected, generate best-effort hygiene scenarios, stamp `source: "fe_baseline"`, and note in `analysis.md` that expected behavior is not spec-derived and needs PM/dev confirmation.

## C. CSV *Type of Test Case* mapping

Category Catalog drives `coverage_category` (internal). Tester-facing categorisation is
`test_case_type` → CSV **Type of Test Case**. See `scenario_economy.md` §4 for the full
Happy Path / Negative / Boundary / … taxonomy and when to combine rows.
