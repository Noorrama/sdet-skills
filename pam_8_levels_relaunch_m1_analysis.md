# SDET Analysis — PAM 8 Levels Relaunch (M1)

**Feature Key:** `pam_8_levels_relaunch_m1`  
**App:** gojek-driver (GoPartner Driver)  
**Team:** All teams (no team dimension in PRD)  
**Milestone:** M1  
**RFC:** [FE] PAM Level 8 RFC — ID: _not stated_ (Jira DRV-1981..1984, DRV-2017) — Status: In Review  
**Analysis Date:** 2026-08-25  
**SDET Plan File:** `pam_8_levels_relaunch_m1_SDET_plan.json`  
**Test Cases File:** `pam_8_levels_relaunch_m1_test_cases.csv`  

## Inputs & Open Points

Generated from the PRD, RFC, and an existing BrowserStack regression suite (30 PAM-8 cases in `PR-143 / Driver Incentives > Loyalty > PAM 8 Level`). The design export was **DEGRADED** (no geometry), so screen/element scenarios were derived from PRD+RFC copy rather than design tokens. No implementation plan (`plan_context.json`) was supplied. **23 open points below — 15 need an answer before the tests can fully cover the feature.** A list of open points is the normal result of planning from work-in-progress docs.

### Inputs

| Context | Status | Detail |
|---|---|---|
| prd_context.json | Present (PARTIAL) | 9 requirements, 6 boundary conditions, 2 flags |
| rfc_context.json | Present (PARTIAL) | scope, 2 flags, 5 risks, API contracts, lifecycle, 8 open questions |
| design_context.json | Present but **DEGRADED** | preflight BLOCKED — export lacks formatVersion 2 + geometry; screens[]/ui_flow[]/elements[] empty; ambiguity HIGH |
| plan_context.json | Not supplied | no impl plan — test hooks / view-model change surface excluded |
| regression_context.json | Present (PARTIAL) | 54 cases; 30 PAM-8 cases reused for dedup; deeplink dictionary + variant dims |

### Open Points

| Follow-up | Field | What we found | Next step |
|---|---|---|---|
| NEEDS_ANSWER | `prd_context.rollout_plan.timeline` | [inherited PRD] No explicit M1 app-release date/sprint timeline; Mitra Juara Tahunan first cycle 2027 Lebaran. | Confirm M1 target release date with PM Petrick Kluivert Tambunan. |
| NEEDS_ANSWER | `prd_context.feature_flags` | [inherited PRD] Two entry-point cohort configs referenced; formal flag identifiers not defined in PRD body (RFC supplies giab_pam_revamp, is_point_swadaya_kilat_enabled). | Confirm flag names/config keys with Engineering (Yatin/Ashish). |
| NEEDS_ANSWER | `prd_context.business_requirements[7].target_module` | [inherited PRD] M1-08 internal tool named only as 'Internal portal / Stargate portal'; no formal module. | Confirm internal module name with Engineering. |
| NEEDS_ANSWER | `prd_context.business_requirements[*].expected_ui_copy` | [inherited PRD] Full finalized copy deck not provided; key ID strings only. | Obtain final copy deck from UX Writer (Iqbal Dwiharianto) before execution. |
| NEEDS_ANSWER | `prd_context.boundary_conditions[3].proposed_default` | [inherited PRD] 2028 red-card end-month pending PM decision; M1 scope unclear. | Get PM confirmation on 2028 future-year end-month scope. Scenario BC-future2028 expected result left open. |
| NEEDS_ANSWER | `prd_context.applicable_service_types` | [inherited PRD] Exhaustive list of eligible service types for the core M1 experience not stated. | Confirm full applicable service-type list with PM. |
| NEEDS_ANSWER | `rfc_context.rfc_id` | [inherited RFC] No explicit RFC ID; Jira DRV-1981..1984, DRV-2017 referenced. | Confirm official RFC ID with Yonathan. |
| NEEDS_ANSWER | `rfc_context.compatibility_mandates[0].min_supported_app_version` | [inherited RFC] No min supported app version / explicit N-1 policy; only 'current loyalty page shouldn't be impacted'. | Confirm min app version and N-1 behavior with Engineering. |
| NEEDS_ANSWER | `rfc_context.platform_specific.ios` | [inherited RFC/OQ-01] Only Android Kotlin class names given; iOS class/file names and parity unspecified. App targets android+ios, so iOS scenarios cannot bind accessibility IDs. | Confirm iOS implementation/screen identifiers with Engineering. Scenarios use Platform=Cross-Platform pending this. |
| NEEDS_ANSWER | `rfc_context.api_contract_changes[2]/OQ-03` | [inherited RFC] Benefit page endpoint ambiguous: table lists /v1/loyalty/benefit but AC states /v2/loyalty/rewards. | Confirm which endpoint the benefit page calls with Yonathan/Soumya. |
| NEEDS_ANSWER | `rfc_context.cross_cutting_concerns.observability.clickstream_events/OQ-02` | [inherited RFC] PAM event tracker (DRV-2017) referenced but no event names/schema. No telemetry scenarios generated per Telemetry Rules (provenance). | Request event tracker spec (DRV-2017). Then generate >=1 verification per event. |
| NEEDS_ANSWER | `rfc_context.open_questions[OQ-06]` | [inherited RFC] Legend/Perintis badge dark-mode compatibility unresolved. | Confirm dark-mode logo compatibility with design (Eveline Irene Anton). theming_darkmode left blocked. |
| NEEDS_ANSWER | `design_context.screens` | [inherited design] design_context extraction_status=DEGRADED: preflight BLOCKED (export missing formatVersion 2 + geometry). screens[]/ui_flow[]/elements[] all empty. Screen/element scenarios derived from PRD+RFC, not design. | Re-export Figma with geometry (Export Design Raw JSON >=0.5.0) and re-run design-extractor, then regenerate element_locator_handoff. |
| NEEDS_ANSWER | `design_context.project_context.overall_ambiguity_rating` | [inherited design] overall_ambiguity_rating=HIGH — screen/element-derived scenarios need design confirmation before automation. | Confirm screens/flows once design is re-extracted. |
| NEEDS_ANSWER | `element_locator_handoff` | Design DEGRADED — no real element_id/screen_id or per-platform locators available. Handoff emitted empty rather than with guessed tokens. | Populate from design + code-change-extractor once design is re-exported. |
| WORTH_CHECKING | `rfc_context.open_questions[OQ-07]` | [inherited RFC] Any/All operator logic for benefit config not finalized. | Confirm whether AND/OR benefit-eligibility logic is in scope; may add benefit-config combination scenarios. |
| WORTH_CHECKING | `regression_context.deeplink_dictionary` | [inherited regression] gojekdriver://loyalty/catalogue (new LoyaltyCatalogueFragment) not yet in repo deeplink dictionary; sourced from RFC navigation_changes[0].deep_link (rung 1b). | Confirm the catalogue deeplink once the screen lands in the repo. |
| WORTH_CHECKING | `regression_context.browserstack_project` | [inherited regression] driverapp modules map to browserstack_project=null (per-case Lumos); static fallback PR-143 used. | Confirm the BrowserStack project before any SYNC upload. |
| WORTH_CHECKING | `scenario_list[*].driver_type` | DriverType is unrestricted for most requirements; regression corpus splits on DriverType [IDBike, IDCar]. Fixtures were NOT fanned per row to avoid detonating the suite; confirm the feature behaves identically across IDBike/IDCar or fan out at code-gen. | Confirm DriverType parity, or fan out fixtures across IDBike/IDCar. |
| WORTH_CHECKING | `scenario_list[*].automation_steps` | automation_steps are a consolidated action+verification sequence in TapMind dialect; the code-gen stage owns exact constants, credential tokens, toggle names and setup scaffolding. | No action — informational for the downstream code-gen stage. |
| FYI | `prd_context.success_metrics.tech_metrics` | [inherited PRD] Tech Metrics row empty. | Request Tech Metrics from Engineering. |
| FYI | `coverage_audit` | coverage_audit block is rendered in <feature_key>_analysis.md (Section 0) rather than in the JSON: sdet_plan.schema.json v this release does not define a top-level coverage_audit property and sets additionalProperties:false, so embedding it would fail validation. | No action — see analysis.md Coverage Audit table. |
| FYI | `environment.schemas_path` | schemas/ is absent under the skill directory; resolved from the plugin version root (aep-mobile/0.10.1/schemas/). Validation used those. | Reinstall/update the aep-mobile plugin if schema resolution fails on re-run. |

_NEEDS_ANSWER — someone has to supply this. WORTH_CHECKING — produced, but confirm it. FYI — the document doesn't cover this; no action needed._

**Not covered by this plan:** M1-08 (internal Stargate CSV-upload portal) is a backend/admin web tool, out of mobile FE scope. No clickstream/telemetry scenarios (DRV-2017 has no event schema — OQ-02). No dark-mode badge scenario (OQ-06 unresolved). iOS-specific accessibility bindings are deferred (OQ-01 — iOS impl undefined); scenarios run Cross-Platform pending iOS identifiers.

**Shared across apps:** none — this PRD/RFC/design set is single-app (gojek-driver).

## Section 0 — Selected Test Coverage Categories

| Category | Tier | Selected? | Why |
|---|---|---|---|
| functional | Auto | ✅ (locked) | prd.business_requirements[] = 9 requirements |
| boundary | Auto | ✅ (locked) | prd.boundary_conditions[] = 6 entries |
| negative_error | Auto | ✅ (locked) | prd.boundary_conditions edge/blank states + rfc.api_contract_changes[] failure handling |
| interruption_network | Auto | ✅ (locked) | rfc.api_contract_changes[] + offline_behavior.sync_strategy=FAIL_FAST + RISK-01/03 |
| interruption_lifecycle | Auto | ✅ (locked) | rfc.lifecycle_considerations[0].event = APP_UNINSTALL_REINSTALL |
| local_data_migration | Auto | ✅ (locked) | rfc.compatibility_mandates[] non-empty + local_data_changes[0] NEW_KEY pam_achievement_tab_red_dot_seen |
| feature_flag_killswitch | Auto | ✅ (locked) | rfc.experimentation_matrix[] = giab_pam_revamp, is_point_swadaya_kilat_enabled |
| deep_link_nav | Auto | ✅ (locked) | rfc.navigation_changes[0].deep_link = gojekdriver://loyalty/catalogue |
| platform_variance | Auto | ✅ (locked) | prd.applicable_platforms = [android, ios] |
| theming_darkmode | Auto | ✅ (locked) | open_question OQ-06 matches dark-mode (Legend/Perintis badges) |
| non_functional_perf | Auto | ✅ (locked) | rfc.cross_cutting_concerns.performance.memory_impact non-null (~120-item progress_history) |
| offline | Auto | ✅ (locked) | rfc.offline_behavior.sync_strategy = FAIL_FAST |
| permission | Extra — feature-adjacent | ☐ | rfc.permissions_required[] absent |
| telemetry_clickstream | Extra — feature-adjacent | ☐ | clickstream_events referenced (DRV-2017) but no event schema — cannot author names |
| localization_regional | Extra — feature-adjacent | ☐ | prd.applicable_countries length 1 (Indonesia) |
| accessibility | Extra — feature-adjacent | ☐ | rfc.accessibility_impacts[] absent |
| session_auth:multi_device_concurrent_login | Extra — fe_baseline | ☐ | personas require a logged-in driver account |
| device_env:rotation | Extra — fe_baseline | ☐ | portrait-lock unconfirmed (no config) |
| os_interruptions:background_foreground | Extra — fe_baseline | ☐ | interactive/networked screens |
| nav_gesture:hardware_back | Extra — fe_baseline | ☐ | multi-screen PAM flow |
| privacy_security:screenshot_screenrecord | Extra — fe_baseline | ☐ | point balance / performance history is sensitive |
| a11y_baseline:screenreader_traversal | Extra — fe_baseline | ☐ | interactive screens |
| resilience:empty_error_states | Extra — fe_baseline | ☐ | networked/stateful screens |

_QA selected **no** optional extras (no preference → AUTO-only baseline per the Step 0 fallback). `fe_baseline` scenarios would be hygiene, not spec-backed._

### Coverage Audit

| Item | Type | Covered By | Status |
|---|---|---|---|
| M1-01 | Requirement | End-to-end: Profile PAM banner to 8 Levels Catalogue to Cek level saya; PAM 8 Levels entry point visible on Profile page when feature enabled; 8 Levels Informational Catalogue page happy path (tiers, benefits, colors); 8 Levels intro page shows Syarat and Keuntungan sections with CTA; Error state on 8 Levels Catalogue when tiers API fails; Empty state on 8 Levels Catalogue when tiers API returns no data; 8 Levels Catalogue tier with no benefits shows correctly | Covered |
| M1-02 | Requirement | End-to-end: Profile PAM banner to 8 Levels Catalogue to Cek level saya; Navigation from PAM entry point banners on Profile page; Access 8 Levels intro via Performance page 'Cek level saya' entry | Covered |
| M1-03 | Requirement | Poin Swadaya component appears on Level Saya page (relocated from Profile); Loyalty/Performance page UI and its new components render; Tapping total point balance navigates to Swadaya Voucher list | Covered |
| M1-04 | Requirement | End-to-end: Profile PAM banner to 8 Levels Catalogue to Cek level saya; Loyalty/Performance page UI and its new components render; Tab switching on Loyalty/Performance page is click-only; App state maintained on PAM pages after backgrounding; Loyalty/Performance state persists after navigating away and back; Pencapaian saya tab loads the yearly progress tracker when selected | Covered |
| M1-05 | Requirement | Pencapaian saya yearly progress calendar renders in-progress state (several years); Pencapaian saya shows achieved state for a year with 12/12 Juara months; Pencapaian saya shows Andalan and Harapan monthly visual cues for a mixed-tier year; My Achievement tab for a year with a broken Juara streak (11/12); My Achievement tab for a year with no performance data (x icons); My Achievement tab does not show years before 2018; Empty state on My Achievement tab for a new driver with no history; Year-0 ending month equals year-1 starting month (green/red highlight); 5 year / 10 year badge hint on 4-year / 9-year Juara streak; Future years shown up to 2028 with locked visual cue, none beyond; PAM pages behavior during network loss and recovery; Loading states on all PAM-related screens (shimmer) | Covered |
| M1-06 | Requirement | End-to-end: Loyalty page to Keuntungan & pencapaian Anda benefit page; My Benefits page UI and functionality for a driver with multiple achieved tiers; My Benefits page for a monthly-tier-only driver shows monthly benefits; Error state on My Benefits page when rewards API fails; Benefit page: tap a reward to view its details | Covered |
| M1-07 | Requirement | Special recognition badges displayed on Profile page (Legend, 5 Tahun); Special recognition badges for Juara 10 Tahun and Perintis Jalan (orange group); Pre-2017 driver 5/10 year badge shown in historical achievement year; Profile page when driver has no special recognition badges; Profile page badge limit of 3 components when eligible for more | Covered |
| M1-08 | Requirement | — | Blocked — Internal admin web portal, not a mobile FE surface — out of Frontend Focus scope; no mobile scenario generated. |
| M1-09 | Requirement | Point Swadaya component shown on Profile page for SDF/Kilat/Box driver; PAM revamp entry point not shown for excluded driver types | Covered |
| giab_pam_revamp | Feature flag | Old loyalty UI shown on Profile when giab_pam_revamp disabled (kill switch); PAM revamp entry point not shown for non-ID drivers; Degrade path: existing loyalty experience preserved when giab_pam_revamp disabled (geo ID-only) | Covered |
| is_point_swadaya_kilat_enabled | Feature flag | is_point_swadaya_kilat_enabled toggle controls Point Swadaya on Profile for SDF cohort | Covered |
| APP_UNINSTALL_REINSTALL | Lifecycle | Red dot on Pencapaian saya tab reappears after uninstall/reinstall | Covered |
| M1-08 (Internal Stargate portal CSV upload) | Blocked item | — | Blocked — Internal admin web portal, not a mobile FE surface — out of Frontend Focus scope; no mobile scenario generated. |
| theming_darkmode (Legend/Perintis badge dark mode) | Blocked item | — | Blocked — OQ-06 OPEN — dark-mode badge compatibility undefined; expected behavior not specified. |
| telemetry_clickstream (DRV-2017) | Blocked item | — | Blocked — OQ-02 OPEN — no event names/schema; provenance rule forbids inventing event names. |
| BC[3] 2028 red-card end-month | Blocked item | — | Blocked — PRD boundary_conditions[3].proposed_default pending PM (M1 scope unconfirmed) — scenario BC-future2028 generated with expected result left as an open point. |

### Coverage Balance

| Positive (business/use-case) | Non-positive (negative, boundary, hygiene) | Positive % | Action taken |
|---|---|---|---|
| 23 | 22 | 51.1% | regenerated_positives — added 7 business/alternate-path scenarios on a documented second pass to cross 50% (23/45=0.511) |

### Regression Coverage

| Scenario | Existing Case | Relationship |
|---|---|---|
| PAM 8 Levels entry point visible on Profile page when feature enabled | TC-766712 | Duplicate — documented, not re-created |
| 8 Levels Informational Catalogue page happy path (tiers, benefits, colors) | TC-766717 | Duplicate — documented, not re-created |
| 8 Levels intro page shows Syarat and Keuntungan sections with CTA | TC-766717 | Related — new variant still generated |
| Navigation from PAM entry point banners on Profile page | TC-766713 | Duplicate — documented, not re-created |
| Access 8 Levels intro via Performance page 'Cek level saya' entry | TC-766713 | Related — new variant still generated |
| Poin Swadaya component appears on Level Saya page (relocated from Profile) | TC-766721 | Related — new variant still generated |
| Loyalty/Performance page UI and its new components render | TC-766721 | Duplicate — documented, not re-created |
| Tapping total point balance navigates to Swadaya Voucher list | TC-766722 | Duplicate — documented, not re-created |
| Tab switching on Loyalty/Performance page is click-only | TC-766724 | Duplicate — documented, not re-created |
| Pencapaian saya yearly progress calendar renders in-progress state (several years) | TC-766725 | Duplicate — documented, not re-created |
| Pencapaian saya shows achieved state for a year with 12/12 Juara months | TC-766726 | Duplicate — documented, not re-created |
| Pencapaian saya shows Andalan and Harapan monthly visual cues for a mixed-tier year | TC-766725 | Related — new variant still generated |
| My Benefits page UI and functionality for a driver with multiple achieved tiers | TC-766731 | Duplicate — documented, not re-created |
| My Benefits page for a monthly-tier-only driver shows monthly benefits | TC-766733 | Duplicate — documented, not re-created |
| Special recognition badges displayed on Profile page (Legend, 5 Tahun) | TC-766734 | Duplicate — documented, not re-created |
| Special recognition badges for Juara 10 Tahun and Perintis Jalan (orange group) | TC-766734 | Related — new variant still generated |
| Point Swadaya component shown on Profile page for SDF/Kilat/Box driver | TC-453496 | Related — new variant still generated |
| Old loyalty UI shown on Profile when giab_pam_revamp disabled (kill switch) | TC-766714 | Duplicate — documented, not re-created |
| is_point_swadaya_kilat_enabled toggle controls Point Swadaya on Profile for SDF cohort | TC-766715 | Related — new variant still generated |
| PAM revamp entry point not shown for non-ID drivers | TC-766716 | Duplicate — documented, not re-created |
| PAM revamp entry point not shown for excluded driver types | TC-766715 | Duplicate — documented, not re-created |
| Error state on 8 Levels Catalogue when tiers API fails | TC-766718 | Duplicate — documented, not re-created |
| Empty state on 8 Levels Catalogue when tiers API returns no data | TC-766719 | Duplicate — documented, not re-created |
| 8 Levels Catalogue tier with no benefits shows correctly | TC-766720 | Duplicate — documented, not re-created |
| Error state on My Benefits page when rewards API fails | TC-766732 | Duplicate — documented, not re-created |
| My Achievement tab for a year with a broken Juara streak (11/12) | TC-766727 | Duplicate — documented, not re-created |
| My Achievement tab for a year with no performance data (x icons) | TC-766728 | Duplicate — documented, not re-created |
| My Achievement tab does not show years before 2018 | TC-766729 | Duplicate — documented, not re-created |
| Empty state on My Achievement tab for a new driver with no history | TC-766730 | Duplicate — documented, not re-created |
| Year-0 ending month equals year-1 starting month (green/red highlight) | TC-766740 | Duplicate — documented, not re-created |
| 5 year / 10 year badge hint on 4-year / 9-year Juara streak | TC-766741 | Duplicate — documented, not re-created |
| Pre-2017 driver 5/10 year badge shown in historical achievement year | TC-766734 | Related — new variant still generated |
| Profile page when driver has no special recognition badges | TC-766735 | Duplicate — documented, not re-created |
| Profile page badge limit of 3 components when eligible for more | TC-766736 | Duplicate — documented, not re-created |
| Red dot on Pencapaian saya tab reappears after uninstall/reinstall | TC-766723 | Duplicate — documented, not re-created |
| PAM pages behavior during network loss and recovery | TC-766737 | Duplicate — documented, not re-created |
| App state maintained on PAM pages after backgrounding | TC-766739 | Duplicate — documented, not re-created |
| Loading states on all PAM-related screens (shimmer) | TC-766738 | Duplicate — documented, not re-created |
| Degrade path: existing loyalty experience preserved when giab_pam_revamp disabled (geo ID-only) | TC-766714 | Duplicate — documented, not re-created |
| Loyalty/Performance state persists after navigating away and back | TC-766724 | Related — new variant still generated |
| Pencapaian saya tab loads the yearly progress tracker when selected | TC-766725 | Related — new variant still generated |
| Benefit page: tap a reward to view its details | TC-766731 | Related — new variant still generated |

### Indirectly Impacted Regression Cases

Loyalty/points cases that share screens with the PAM revamp but whose specific flow is not directly modified — include in the regression run.

| Case ID | Title |
|---|---|
| C5542964 | [AUT_B_326][AUT_C_326] Verify Profile -> Loyalty Summary -> Points Page |
| C5542965 | [AUT_B_327][AUT_C_327] Verify Loyalty Home -> Tier List -> Tier Details |
| C5542966 | [AUT_B_327][AUT_C_327] Verify Loyalty Home -> Help Center (deeplink) |
| C5542967 | Verify Points Page -> Point History -> Pagination & Help Center |
| C5542968 | [AUT_B_328][AUT_C_328] Verify Points Page -> Point History -> Empty State |
| C5542969 | Verify Points Page -> Point History -> Internet Error State |
| C5542970 | Verify Points Page -> Point History -> Generic Error State |
| C5542971 | [AUT_B_329][AUT_C_329] Verify Points -> Voucher List -> Voucher Detail -> Redeem -> Success -> Points Refresh |
| C5542972 | Verify Voucher Redemption Failure and Recovery |
| C5542973 | [AUT_B_330][AUT_C_330] Verify Redeemed Voucher appears in My Active Voucher top list |
| C5543025 | Verify Profile -> Loyalty Summary -> Points Page -> When driver completes the order |
| TC-319628 | [AUT_B_332][AUT_C_332] Validate point history tab |
| TC-319531 | [AUT_B_331][AUT_C_331] Validate voucher more details page |
| C4552777 | Get Driver Tier Progress V1 |
| C4552778 | Get Driver Tier Progress V2 - for SG only |
| C4552779 | Get Driver Tier Info |
| C4552780 | Get Driver Tier Rewards |
| C4552781 | Get Driver Tier Summary |
| C4552782 | Get Driver Tier Details |

## Section 1 — Missing Input Context

- **`plan_context.json` (not supplied):** no implementation plan. Test hooks (`method:deeplink`/`hook_id`), changed view-models, and the code-change surface are excluded. Navigation was resolved via the RFC deep link (`gojekdriver://loyalty/catalogue`) and the regression deeplink dictionary (`gojekdriver://loyalty/home`), plus a corpus-corroborated Profile login+tap preamble.
- **`design_context.json` (DEGRADED):** the Figma export lacked formatVersion 2 + geometry, so the spatial pipeline was BLOCKED. No screens, elements, states, or `ui_flow` were available. Consequences: `element_locator_handoff` is **empty** (no android_resource_id / ios_accessibility_identifier / flutter_key), UI-copy assertions rely on PRD strings, and screen-derived scenarios need design confirmation before automation (ambiguity HIGH).

## Section 2 — Cross-Stage Gap Analysis

### PRD vs Figma Gaps

| Req | Severity | Gap |
|---|---|---|
| M1-01..M1-09 | CRITICAL_BLOCKER | design_context is DEGRADED (preflight BLOCKED — export lacks formatVersion 2 + geometry). No screens, elements, states or ui_flow are available, so every PRD screen (8 Levels Catalogue, Level Saya tabs, Pencapaian calendar, Benefit page, Profile badges) is un-verifiable against design. All scenario steps were derived from PRD+RFC copy strings, not from design tokens. |
| M1-05 | WARNING | Yearly calendar copy ('Awal periode YYYY' green start, 'Akhir periode YYYY' red end, '{X} dari 12 kali jadi Mitra Juara') is dynamic; no design frame available to confirm placement/colours or the 3-year top-row layout. |
| M1-01..M1-09 | WARNING | Full finalized copy deck not supplied (PRD note) — UI-copy assertions use the ID strings present in the PRD only; confirm against the UX Writer's deck. |

### PRD vs RFC Gaps

| Req | Gap |
|---|---|
| M1-02/M1-09 | PRD calls SDF/Kilat/Box Point Swadaya 'P0 scope' (M1-09) while RFC experimentation_matrix scopes is_point_swadaya_kilat_enabled under 'Out of scope M1'. Confirm whether M1-09 ships in M1. |
| feature_flags | PRD names cohort configs generically (pam_8_levels_entry_point_cohort_config, cek_level_saya_performance_page_cohort_config); RFC names giab_pam_revamp + is_point_swadaya_kilat_enabled. Reconcile flag identities. |
| M1-06 | Benefit page endpoint conflict (OQ-03): PRD/RFC screen table lists /v1/loyalty/benefit but AC states /v2/loyalty/rewards. Reported as a gap, not silently resolved. |
| M1-01..M1-09 | PRD applicable_platforms=[android, ios] but RFC only names Android Kotlin classes; iOS parity/identifiers undefined (OQ-01). |

### RFC vs Implementation Plan Gaps

| RFC | Gap |
|---|---|
| [FE] PAM Level 8 RFC | No plan_context.json (impl plan) supplied — cannot verify that RISK-01..05 (include_special_tiers param, group ordering, missing-data x-icons, catalogue-flag reuse, local red-dot), the SHARED_PREFS key pam_achievement_tab_red_dot_seen, NTP-based year selection, and required screens/view-models are accounted for in implementation. Verify against the dev's change_context post-build. |

## Section 3 — Architectural & Testability Risks

| Risk ID | Severity | Description | Testing Implication |
|---|---|---|---|
| RISK-01 | High (inferred) | Both /v1/loyalty/tiers and /v1/loyalty/progress APIs require the additional query parameter include_special_tiers=true to include special tier data (5yr, 10yr, Legend, Perintis). If this parameter is omitted from either call, special tiers will not appear in the UI silently. | Call /v1/loyalty/tiers and /v1/loyalty/progress without include_special_tiers=true; verify that special tiers (Juara 5 Tahun, Juara 10 Tahun, Legend, Perintis) are absent from the catalogue UI. Then call with the parameter and verify all 8 levels appear. |
| RISK-02 | Medium | The group field ordering in the /v1/loyalty/tiers API response directly controls FE badge grouping logic. Contiguous items with the same group value are visually grouped; a different value starts a new group. A change in BE ordering silently breaks FE grouping without an error. | Test with an API response where tier items alternate group values (e.g., monthly, tahunan, monthly) and verify FE does not incorrectly merge them. Test that Bulanan/Tahunan/Penghargaan Spesial use green color and Penghormatan Tertinggi uses orange. |
| RISK-03 | High (inferred) | The yearly progress tracker (Pencapaian saya tab) depends on backdated performance data loaded via CSV. If data is missing for a driver for a specific month or year, the FE must handle this with x-icon states. Risk: crash or incorrect empty state if missing-data handling is incomplete. | Test with accounts that have no data for specific years in progress_history; verify x icons appear per month. Test with accounts with no historical data at all (pre-2018 drivers); verify empty state displays. Test with backdated data starting from 2016. |
| RISK-04 | Medium (inferred) | LoyaltyCatalogueFragment is reused for two distinct flows: the 8-level programme catalogue (entry from Profile Page) and the benefit/achievement page (entry from Loyalty Page). A flag passed from the calling page determines which content to render. Incorrect flag handling silently renders the wrong content. | Navigate to LoyaltyCatalogueFragment from both entry points (Profile Page PAM banner and Loyalty Page benefit banner); verify distinct content and API calls (v1/tiers vs v2/rewards) for each flow. |
| RISK-05 | Low (inferred) | The red dot on the Pencapaian saya (Achievement) tab is stored locally and reset on clear cache, clear data, or app reinstall. This means the first-time indicator reappears after reinstall, which may confuse returning users. | Install app, open the Pencapaian saya tab to dismiss the red dot, uninstall and reinstall, verify red dot reappears. |

## Section 4 — Open Questions & Clarifications

### Blocked — Awaiting PM / Design Input

| ID | Question | Test Impact |
|---|---|---|
| OQ-06 | Are the Legend and Perintis Jalan badge logos compatible with dark mode? GoPartner will support dark mode in the near future. | Dark mode rendering tests for special recognition badges cannot be validated without design confirmation of logo compatibility. |
| OQ-07 | Should 'Any and All operator logic' be added as an AC to the benefit display config (referenced in Petrick's comment on the benefit/reward config setup in Stargate)? | If operator-based benefit eligibility logic is added, additional test scenarios are required to cover AND/OR condition combinations in the benefit config. |
| DESIGN-BLK | Re-export Figma with geometry (Export Design Raw JSON >=0.5.0) — design pipeline BLOCKED, no screens/elements. | Screen/element scenarios unverified; element_locator_handoff empty. |

### Blocked — Awaiting Dev / RFC Author Input

| ID | Question | Test Impact |
|---|---|---|
| OQ-01 | The RFC only names Android Kotlin class files. What are the equivalent iOS class/file names and SwiftUI/UIKit targets for LoyaltyCatalogueFragment, LoyaltyMembershipFragment, and ProfileContainerFragment changes? | iOS test scenarios cannot be written with correct screen identifiers and accessibility IDs without iOS implementation details. |
| OQ-02 | What are the specific clickstream event names, triggers, and payload shapes for the PAM 8 Level event tracker (Jira DRV-2017)? | Cannot write analytics/clickstream validation test scenarios without the event schema. |
| OQ-03 | Does the benefit page (LoyaltyCatalogueFragment in benefit flow) call /v1/loyalty/benefit or /v2/loyalty/rewards? The screen table lists /v1/loyalty/benefit but the AC explicitly states 'Fetch new API v2/loyalty/rewards'. | API contract tests and mock data setup depend on knowing which endpoint the benefit page actually calls. |

### Resolved — Unblocked for Testing

| ID | Resolution | Test Action |
|---|---|---|
| OQ-04 | Resolved: year entries are still shown. For missing months, BE sends x icon. For a fully missing year, all 12 months show x icons following the same logic as 'yearly Juara not achieved'. | Covered in the relevant M1-05/M1-06 scenarios |
| OQ-05 | Resolved: 'We keep the current BE logic to determine {Month}{Year}' — monthly badge follows the existing calendar-month logic, not the Lebaran cycle. | Covered in the relevant M1-05/M1-06 scenarios |
| OQ-08 | Resolved: yes, ordered from earliest year to today. Test should assert ascending order of year values in progress_history[]. | Covered in the relevant M1-05/M1-06 scenarios |

### Additional Clarifications Needed (for PM)

- **Clickstream payload schema** (DRV-2017): event names, triggers, attributes — none defined. No telemetry tests generated.
- **Final copy deck** (UX Writer Iqbal Dwiharianto): full ID copy across all PAM screens.
- **M1 release date / sprint timeline** (PM Petrick Kluivert Tambunan).
- **Flag identity reconciliation:** PRD cohort-config names vs RFC `giab_pam_revamp` / `is_point_swadaya_kilat_enabled`.
- **Benefit endpoint** (OQ-03): `/v1/loyalty/benefit` vs `/v2/loyalty/rewards`.

## Section 5 — SDET Readiness & Testing Plan

### SDET Readiness

| Item | Value |
|---|---|
| Design ambiguity | **HIGH** — screen/element scenarios need design confirmation before automation |
| Element locators | Not available (design DEGRADED) — automation binding blocked |
| iOS readiness | Blocked (OQ-01) — iOS impl/identifiers undefined |

### Environment Requirements

| Item | Specification |
|---|---|
| App | GoPartner Driver (gojek-driver), Indonesia build |
| Environment | QA (release candidate) |
| Kill switch | `giab_pam_revamp` (Firebase config) — enabled for feature, disabled for degrade path |
| Secondary flag | `is_point_swadaya_kilat_enabled` (SDF/Kilat/Box Point Swadaya) |
| Locale / TZ | id-ID, Asia/Jakarta (WIB); year selection uses **NTP** time, not device clock |

### Test Data Requirements

| Tag | Description |
|---|---|
| `id_driver` | Active GoPartner driver in Indonesia, GoRide/GoCar service type, giab_pam_revamp enabled |
| `pam_revamp_on` | Active GoPartner driver in Indonesia, GoRide/GoCar service type, giab_pam_revamp enabled |
| `goride_gocar` | Active GoPartner driver in Indonesia, GoRide/GoCar service type, giab_pam_revamp enabled |
| `eligible_tier` | Driver eligible for at least one recognition tier (e.g. Juara) |
| `perf_entry_cohort` | Driver in the cohort configured to see the Performance-page 'Cek level saya' entry |
| `has_swadaya_points` | Active GoPartner driver holding a non-zero Swadaya point balance |
| `multi_year_history` | Driver with progress_history spanning several years (2018-2023), current period in progress |
| `in_progress` | Driver with progress_history spanning several years (2018-2023), current period in progress |
| `achieved_full_year` | Driver with a progress_history year where all 12 eligibility months are Juara |
| `mixed_tier_months` | Non-MJG driver with a year mixing Andalan / Harapan / Juara months |
| `multi_tier_rewards` | Driver eligible for multiple achieved tiers with rewards (Juara, Legend) |
| `monthly_only` | Driver with only a monthly tier achieved (e.g. Andalan) |
| `special_badges` | Driver eligible for Legend and Juara 5 Tahun recognition |
| `sdf_kilat_box` | Active driver on SDF, Kilat, or Box service type with Swadaya points |
| `pam_revamp_off` | Active GoPartner driver, ID, GoRide/GoCar, giab_pam_revamp disabled |
| `non_id_driver` | Active driver in Singapore (non-ID), SgCar service type |
| `excluded_type` | Active driver on an excluded service type (Fleet/SDF/Kilat) |
| `mock_api` | Mocked API response as described in preconditions |
| `boundary` | My Achievement tab for a year with a broken Juara streak (11/12) |
| `pre_2017` | Pre-2017 driver eligible for MJ 5 Tahun / 10 Tahun by backdated calculation |
| `long_term_recognition` | Pre-2017 driver eligible for MJ 5 Tahun / 10 Tahun by backdated calculation |
| `no_special_badges` | Driver not eligible for any special recognition |
| `badge_limit` | Driver eligible for all four special recognitions (limit test) |
| `fresh_install` | Driver on a fresh app install (local red-dot state cleared) |
| `network_toggle` | Driver with a network connection that can be toggled off and on |
| `backgrounding` | Driver on a PAM page, app can be backgrounded and restored |
| `throttled_network` | Driver on a throttled network connection |
| `degrade_path` | Active GoPartner driver, ID, giab_pam_revamp disabled |
| `reward_details` | Driver eligible for an achieved tier with reward details |

> **DriverType fan-out:** the regression corpus splits on `DriverType [IDBike, IDCar]`. Fixtures were not fanned per row to avoid detonating the suite — confirm parity across IDBike/IDCar or fan out at code-gen time.

### Device Matrix

- Android: Pixel 7 (primary), one low-end device for throttled-network/loading states.
- iOS: iPhone 14 — **pending OQ-01** (iOS implementation identifiers).

### Dependencies Before Test Execution

- Re-export Figma with geometry and re-run design-extractor (unblocks element locators).
- Final copy deck from UX Writer.
- iOS class/accessibility identifiers (OQ-01).
- Clickstream event spec (OQ-02) if telemetry coverage is required.
- Confirm benefit endpoint (OQ-03).

### Execution Guidelines

- **API error/empty states:** use a proxy tool (Charles/mitmproxy) to force 5xx or empty `tiers[]`/`progress_history[]` on `/v1/loyalty/tiers`, `/v1/loyalty/progress`, `/v2/loyalty/rewards`; verify retry vs empty screens.
- **`include_special_tiers=true` (RISK-01):** call `/tiers` and `/progress` without the param and verify special tiers (5yr/10yr/Legend/Perintis) are absent; then with the param and verify all 8 appear.
- **Missing-data x-icons (RISK-03):** mock a year with empty `monthly_progress` and verify all 12 slots show the x icon.
- **Red-dot reinstall (RISK-05):** view the Pencapaian saya tab to dismiss the red dot, then `adb uninstall`/reinstall and verify it reappears.
- **Backgrounding:** background via home, or `adb shell am kill` for process-death, and verify tab/scroll state on restore.
- **NTP year:** verify the center year of the 3-year row uses NTP time, not a changed device clock.
