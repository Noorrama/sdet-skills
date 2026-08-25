# Impact Shortlister — PAM Validation Report

**Feature:** PAM 8 Levels Relaunch (`pam_8_levels_relaunch`)  
**App:** Gojek Driver (`gojek-driver`)  
**Generated:** 2026-08-24  
**MRs analyzed:** !13303, !13326, !13352, !13354, !13386 (120 unique changed files)

---

## Security notice

A GitLab personal access token was shared in chat to fetch MR diffs. **Rotate that token immediately** in GitLab (`Settings → Access Tokens`) and avoid pasting tokens into LLM sessions. Use environment variables (`GITLAB_TOKEN`) or Cursor secrets instead.

---

## 1. Skill changes made

### `scripts/shortlist_join.py`

| Change | Before | After |
|--------|--------|-------|
| **Candidate pool** | All `regression_context` cases + any `existing_case_ref` | **Only** plan rows with `is_legacy_regression: true` **and** `existing_case_ref` |
| **regression_context role** | Pool source | **Enrichment only** (title, steps, tapmind_steps by case id) |
| **PLAN_SCENARIO_LINK** | Auto-`MUST_RUN` | **Removed** — plan link is traceability via `plan_scenario_refs`, not evidence |
| **MR bootstrap** | Not supported | Infers modules/screens from `changed_files`; new reason code `FILE_PATH_TOUCHED` |
| **new_scenarios_to_run** | No `existing_case_ref` | All non-legacy scenarios (`is_legacy_regression: false`) |

### `skills/impact-shortlister/SKILL.md`

- Documented legacy-only pool, MR bootstrap path, removed PLAN_SCENARIO_LINK auto-MUST_RUN.
- Linked to this report as the worked example.

### `schemas/impact_shortlist.schema.json`

- Added `FILE_PATH_TOUCHED` reason code and `path_tokens` evidence field.
- Removed `PLAN_SCENARIO_LINK` from reason code enum.
- Added `plan_legacy` source enum value.

### New artifacts

| Path | Purpose |
|------|---------|
| `examples/pam_feature/` | Full PAM validation bundle |
| `examples/pam_feature/mr_changed_files.json` | 120 files unioned from 5 GitLab MRs |
| `examples/pam_feature/change_context.bootstrap.json` | MR-sourced change surface (until code-change-extractor runs) |
| `examples/pam_feature/regression_context.json` | Loyalty Revamp cases for enrichment |
| `examples/pam_feature/pam_8_levels_relaunch_sdet_plan.json` | Plan copy with 5 legacy rows injected (see §3) |
| `examples/pam_feature/impact_shortlist.json` | **Final shortlist output** |
| `scripts/build_pam_example.py` | Reproducible builder (re-run after MR/plan updates) |

---

## 2. Important finding: production PAM SDET plan gap

Your file `pam_8_levels_relaunch_SDET_plan.json` (Downloads) has:

- **36 scenarios**, all `is_legacy_regression: false`
- **9 partial-overlap** `existing_case_ref` links (C5542964, C5542965) — these are *related* cases, not legacy pool entries

Under the confirmed legacy-only rule, the shortlister would produce **`candidate_pool_size: 0`** and `extraction_status: LIMITED`.

For this validation run, we injected **5 Loyalty Revamp legacy rows** into the example plan copy (cases the regression-extractor identified in the Loyalty Revamp BrowserStack folder). **Before production use, the SDET plan must mark exact-match legacy cases with `is_legacy_regression: true`.**

---

## 3. Generated output summary

**File:** `examples/pam_feature/impact_shortlist.json`

| Metric | Value |
|--------|-------|
| Candidate pool (legacy) | 5 |
| Shortlisted | 5 |
| Deselected | 0 |
| Reduction | 0% (small pool; all touched loyalty/profile) |
| New scenarios to run (non-legacy) | 36 |
| Change surface source | `gitlab_mr_diff` (120 files, 5 MRs) |

### Shortlisted legacy tests

| Case ID | Title | Tier | Why selected |
|---------|-------|------|--------------|
| **C5542964** | Validate loyalty and point section on profile menu | MUST_RUN | MRs modify `ProfileContainerFragment`, loyalty summary card, profile navigation. Case steps: profile icon → loyalty sections → points. `FILE_PATH_TOUCHED`: loyalty, profile. |
| **C5542965** | Validate loyalty home page and tier detail and Learn more | MUST_RUN | MRs add `LoyaltyCatalogueFragment`, `LoyaltyMembershipFragment`, `/v1/loyalty/tiers`. Case: profile → loyalty detail → tier list → learn more. |
| **C5542968** | Validate Point history and reward catalogue pages | MUST_RUN | MR !13354 adds `LoyaltyRewardCatalogueEntity`, rewards API `/v2/loyalty/rewards`. Case: points tab → reward catalogue navigation. |
| **C5542971** | Validate voucher redeem success flow | MUST_RUN | Loyalty points/redeem surfaces touched; `LoyaltyApi` and repository changed across MRs. Adjacent to new benefits page but same loyalty stack. |
| **C5542973** | Validate voucher list page | MUST_RUN | Same loyalty points/voucher stack as above; profile → points → vouchers flow overlaps changed loyalty module. |

All five are **automated GMT/Cucumber** tests in `LoyaltyRevamp.feature` → execution target **GMT_JAVA**.

### What was NOT shortlisted

With only 5 legacy candidates and broad loyalty MR changes, nothing was deselected. In a larger pool (e.g. full Loyalty Revamp folder ~30 cases), cases about unrelated driver flows (settings, trips, KYC) would land in `review_queue` and be deselected with `NO_IMPACT_SIGNAL` after agent judgment.

### New scenarios (always run)

All **36** PAM plan scenarios with `is_legacy_regression: false` are carried in `new_scenarios_to_run` — brand-new PAM 8 Levels coverage (catalogue, Pencapaian Saya calendar, badges, flags, deeplinks). Impact analysis does not skip these.

---

## 4. MR change surface (what merged)

| MR | Title | Key touchpoints |
|----|-------|-----------------|
| !13303 | PAM Loyalty Entrypoint | Profile PAM banner, `giab_pam_revamp_enabled`, loyalty summary card |
| !13326 | Loyalty catalogue screen | `LoyaltyCatalogueFragment`, `/loyalty/catalogue` deeplink, `/v1/loyalty/tiers` |
| !13352 | Monthly/Yearly achievement view | `LoyaltyMembershipFragment`, `/v1/loyalty/progress`, achievement calendar |
| !13354 | Loyalty My Benefit Screen | `/v2/loyalty/rewards`, reward catalogue entity |
| !13386 | PAM Loyalty Event Tracker | Analytics on catalogue/membership/summary |

**Inferred modules:** `loyalty`, `driver-profile`, `incentives`  
**APIs:** `/v1/loyalty/tiers`, `/v1/loyalty/progress`, `/v2/loyalty/rewards`  
**Flag:** `giab_pam_revamp_enabled`

---

## 5. Why this shortlister will work for any feature

### Design principles

1. **Bounded pool** — Only human-approved legacy cases from the SDET plan (`is_legacy_regression: true`). Never the full 7000-test corpus. EPIC-scoped by construction.

2. **Two-tier, auditable selection**
   - **Deterministic tier** (`shortlist_join.py`): reproducible evidence matching. Same inputs → same MUST_RUN set.
   - **Agent tier**: one judgment pass on `review_queue` with required explanations. No opaque scoring formula.

3. **Progressive change-surface quality**
   - **Production:** `change_context.json` from code-change-extractor (locators, flags, APIs, CR risks, id_compliance).
   - **Testing/bootstrap:** GitLab MR file lists + plan/RFC metadata (`FILE_PATH_TOUCHED`, inferred screens/modules).
   - Quality improves automatically when dev manifest lands — no skill rewrite.

4. **Safe defaults**
   - Empty pool → `LIMITED`, not "skip regression"
   - `MUST_RUN` never demoted
   - Every deselection recorded in `deselected_tests`
   - `id_compliance: FAIL` widens (don't deselect on soft judgment)

5. **Separation of concerns**
   - Selects **which existing case IDs to run**
   - Does not generate tests or bind automation methods
   - `new_scenarios_to_run` keeps the full run set complete alongside legacy picks

### When it works best

- SDET plan correctly marks legacy duplicates during pre-build dedup
- `regression_context.json` available for rich title/steps
- Post-build `change_context.json` available (element-level matching)

### Known limits (v1)

- No SmartScope/Lumos file→test index (future corpus-scale problem)
- MR bootstrap is coarser than element-level change_context
- Module-level `MODULE_TOUCHED` can over-select if pool is too broad (mitigated by legacy-only pool)
- Requires `is_legacy_regression: true` in plan — **PAM production plan needs fixing**

---

## 6. How to re-run

```bash
# Rebuild PAM example (needs GITLAB_TOKEN for fresh MR fetch, or uses cached mr_changed_files.json)
python3 plugins/aep-mobile/scripts/build_pam_example.py

# Or manual draft step:
python3 plugins/aep-mobile/scripts/shortlist_join.py draft \
  --plan plugins/aep-mobile/examples/pam_feature/pam_8_levels_relaunch_sdet_plan.json \
  --regression plugins/aep-mobile/examples/pam_feature/regression_context.json \
  --change plugins/aep-mobile/examples/pam_feature/change_context.bootstrap.json \
  --out plugins/aep-mobile/examples/pam_feature/impact_shortlist.draft.json
```

---

## 7. Recommended next steps

1. **Rotate the GitLab token** shared in chat.
2. **Fix PAM SDET plan:** mark exact-match Loyalty Revamp cases as `is_legacy_regression: true` (not just partial-overlap `existing_case_ref`).
3. **Run code-change-extractor** when dev manifest is ready → replace `change_context.bootstrap.json` with real `change_context.json` for locator/API-level matching.
4. **Wire downstream consumer** (CI regression runner or orchestrator) to read `impact_shortlist.json` + `new_scenarios_to_run`.
