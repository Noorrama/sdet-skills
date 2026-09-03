# Impact Shortlister — Validation Summary (2 Features)

**Skill:** `mobile-postbuild` → `impact-shortlister` subagent + `scripts/shortlist_join.py`  
**Date:** 2026-08-24  
**Features tested:** PAM 8 Levels (Driver) · Save Group for Group Orders (GoFood Consumer)

---

## Verdict

| Question | Answer |
|----------|--------|
| **Is the skill working as expected?** | **Yes** — deterministic matching, legacy-only pool, dedupe by case ID, MR bootstrap, and `new_scenarios_to_run` all behaved correctly on both features. |
| **Will it work generically?** | **Yes, with preconditions** — any EPIC that has (1) legacy rows in the SDET plan, (2) a change surface (`change_context` or MR bootstrap), and (3) overlapping title/steps vs changed code. Agent judgment handles ambiguous cases; no external scoring required. |
| **Agent judgment exercised?** | **No on either run** — all legacy candidates had deterministic evidence (`review_queue` was empty). |

---

## How we tested (common flow)

```
SDET plan (legacy rows)  +  regression_context (enrichment)
         +
change surface (MR bootstrap → change_context.bootstrap.json)
         │
         ▼
shortlist_join.py draft  →  must_run + review_queue
         │
         ▼ (agent if review_queue non-empty)
impact_shortlist.json  +  SDET plan roll-up
```

**Production path (not used in these runs):** `dev_manifest` → `code-change-extractor` → `change_context.json` (richer locators/APIs).

**Test path used:** GitLab MR *changes* API → union of `changed_files` → bootstrap change surface.

---

## Test 1 — PAM 8 Levels Relaunch (Driver)

| Field | Value |
|-------|-------|
| **App** | `gojek-driver` |
| **Feature key** | `pam_8_levels_relaunch` |
| **GitLab project** | `gojek-mobile/driver-app` |
| **SDET plan** | `pam_8_levels_relaunch_SDET_plan.json` |
| **Change surface** | MR bootstrap (`gitlab_mr_diff`) |
| **Artifacts** | `examples/pam_feature/` |

### MRs used (5)

| MR | Title (short) | State |
|----|---------------|-------|
| [!13303](https://source.golabs.io/gojek-mobile/driver-app/-/merge_requests/13303) | PAM Loyalty Entrypoint | merged |
| [!13326](https://source.golabs.io/gojek-mobile/driver-app/-/merge_requests/13326) | Add Loyalty catalogue screen | merged |
| [!13352](https://source.golabs.io/gojek-mobile/driver-app/-/merge_requests/13352) | Monthly and Yearly achievement view | merged |
| [!13354](https://source.golabs.io/gojek-mobile/driver-app/-/merge_requests/13354) | Loyalty My Benefit Screen | merged |
| [!13386](https://source.golabs.io/gojek-mobile/driver-app/-/merge_requests/13386) | PAM Loyalty Event Tracker | merged |

**Changed files (union):** 120  
**Inferred modules:** `loyalty`, `driver-profile`, `incentives`

### Legacy pool & results

| Metric | Value |
|--------|-------|
| Plan `is_legacy_regression: true` in source plan | **0** (gap — see note) |
| Legacy pool used in test | **5** (injected Loyalty Revamp rows in example plan) |
| Shortlisted | **5** / 5 (`MUST_RUN`) |
| Deselected | 0 |
| `review_queue` | 0 |
| New scenarios (always run) | 36 |
| Primary reason code | `FILE_PATH_TOUCHED` (loyalty, profile) |

### Shortlisted cases

| Case | Reason |
|------|--------|
| C5542964 | Profile loyalty/points — `ProfileContainerFragment`, loyalty summary |
| C5542965 | Loyalty home/tiers — `LoyaltyCatalogueFragment`, `LoyaltyMembershipFragment` |
| C5542968 | Point history / reward catalogue — rewards API surface |
| C5542971 | Voucher redeem — loyalty points stack |
| C5542973 | Voucher list — loyalty points stack |

**Execution target:** GMT_JAVA (Cucumber `LoyaltyRevamp.feature`)

### PAM caveat

Production SDET plan had **no** `is_legacy_regression: true` rows — shortlister would return `candidate_pool_size: 0` / `LIMITED` until the plan marks legacy cases correctly.

---

## Test 2 — Save Group for Group Orders (GoFood)

| Field | Value |
|-------|-------|
| **App** | `gojek-consumer` |
| **Feature key** | `save-group-for-group-orders` |
| **GitLab project** | `mobile/GoHost` |
| **SDET plan** | `save-group-for-group-orders_SDET_plan.json` |
| **Change surface** | MR bootstrap + RFC APIs/flags from plan |
| **Artifacts** | `examples/save_group_feature/` |
| **Token** | `GITLAB_READ_TOKEN_FOR_AGENT` from `skills/.env` |

### MRs used (9)

| MR | Owner | Title (short) | State | Files |
|----|-------|---------------|-------|-------|
| [!54280](https://source.golabs.io/mobile/GoHost/-/merge_requests/54280) | — | Group Order M5 3_dots_logic | merged | 5 |
| [!54308](https://source.golabs.io/mobile/GoHost/-/merge_requests/54308) | — | add_to_social_group_flow | merged | 23 |
| [!54317](https://source.golabs.io/mobile/GoHost/-/merge_requests/54317) | — | shared cart social group entry UI | opened | 4 |
| [!54169](https://source.golabs.io/mobile/GoHost/-/merge_requests/54169) | Ian | saved group indicator | merged | 13 |
| [!54196](https://source.golabs.io/mobile/GoHost/-/merge_requests/54196) | Ian | 3 dots actions | merged | 16 |
| [!54170](https://source.golabs.io/mobile/GoHost/-/merge_requests/54170) | Siddhant | Litmus config Save Group | merged | 3 |
| [!54222](https://source.golabs.io/mobile/GoHost/-/merge_requests/54222) | Siddhant | Save Group selected state UI | merged | 2 |
| [!54232](https://source.golabs.io/mobile/GoHost/-/merge_requests/54232) | Siddhant | Social Group card UI AOS | merged | 5 |
| [!54311](https://source.golabs.io/mobile/GoHost/-/merge_requests/54311) | Siddhant | Wire Social Group chat into AOS | opened | 12 |

**Changed files (union):** 59  
**Module:** `gofood-group-order`  
**Key paths:** `GroupShareTray.kt`, `SaveGroupSection.kt`, `GFDGroupOrderSharedCart*`, `SocialGroupCreatedWidget.kt`

### Legacy pool & results

| Metric | Value |
|--------|-------|
| Plan `is_legacy_regression: true` rows | **5** |
| Unique case IDs (after dedupe) | **3** |
| Shortlisted | **3** / 3 (`MUST_RUN`) |
| Deselected | 0 |
| `review_queue` | 0 |
| New scenarios (always run) | 68 |
| Reason codes | `MODULE_TOUCHED` + `SCREEN_TOUCHED` + `FILE_PATH_TOUCHED` |

### Legacy plan rows → unique cases

| Case ID | Plan rows | Area |
|---------|-----------|------|
| TC-302383 | 1 | GO landing — Groups you can invite |
| TC-302484 | **3** (duplicate ref) | Share Tray variants (pre-GO, post-GO, BAU empty) |
| TC-302761 | 1 | Shared Cart three-dots menu |

**5 plan rows → 3 runs** (same BrowserStack ID = one pool entry).

### Shortlisted cases

| Case | Screens / evidence |
|------|-------------------|
| TC-302383 | `GROUP_ORDER_LANDING` — SaveGroupSection, SocialGroupCard |
| TC-302484 | `SHARE_TRAY` — GroupShareTray.kt, invite flow MRs |
| TC-302761 | `SHARED_CART` — shared cart VM, 3-dot logic MRs |

**Execution target:** TAPMIND_NLP

---

## Side-by-side comparison

| | PAM (Driver) | Save Group (GoFood) |
|---|-------------|---------------------|
| App | gojek-driver | gojek-consumer |
| Repo | driver-app | GoHost |
| MRs | 5 | 9 |
| Changed files | 120 | 59 |
| Legacy pool | 5 | 3 unique (5 plan rows) |
| Shortlisted | 5 | 3 |
| Agent judgment used | No | No |
| Plan legacy flags OK | No (needed injection) | Yes |
| Change surface | MR bootstrap only | MR bootstrap + plan RFC APIs/flags |

---

## What worked generically (both runs)

1. **Legacy-only pool** — only `is_legacy_regression: true` + `existing_case_ref`
2. **Dedupe by case ID** — TC-302484 × 3 plan rows → 1 run
3. **Deterministic MUST_RUN** — reproducible reason codes + evidence
4. **MR bootstrap** — no `change_context.json` required for dry-run
5. **`new_scenarios_to_run`** — all non-legacy scenarios carried through
6. **Cross-app** — Driver (Kotlin/Fragments) and Consumer (GoFood/KMP) both matched

---

## Known limits (v1)

| Limit | Impact |
|-------|--------|
| MR bootstrap coarser than `change_context` | No `LOCATOR_CHANGED` until code-change-extractor runs |
| Small legacy pool | 0% reduction when all candidates clearly touch changed module |
| Plan must mark legacy correctly | Empty pool if no `is_legacy_regression: true` (PAM lesson) |
| Agent judgment not exercised yet | Need a feature with larger pool + partial overlap to validate `review_queue` |
| No SmartScope / file→test index | Corpus-scale re-ranking deferred |

---

## Recommendation

**Ready for agentic pipeline integration** with these gates:

1. SDET plan must include **`is_legacy_regression: true`** for exact-match legacy cases before post-build shortlist.
2. Prefer **`change_context.json`** from code-change-extractor when dev manifest is available.
3. Use **MR bootstrap** only for early validation or when change extractor has not run.
4. Wire a downstream consumer (CI / orchestrator) to read `impact_shortlist.json` + `new_scenarios_to_run`.

---

## Re-run commands

```bash
# PAM
python3 plugins/aep-mobile/scripts/build_pam_example.py

# Save Group (reads skills/.env)
python3 plugins/aep-mobile/scripts/build_save_group_example.py

# Generic draft
python3 plugins/aep-mobile/scripts/shortlist_join.py draft \
  --plan <feature>_sdet_plan.json \
  --regression regression_context.json \
  --change change_context.bootstrap.json \
  --out impact_shortlist.draft.json
```

---

## Full reports

- PAM: `examples/pam_feature/IMPACT_SHORTLISTER_REPORT.md`
- Save Group: `examples/save_group_feature/IMPACT_SHORTLISTER_REPORT.md`
- Script explainer: `skills/impact-shortlister/SHORTLIST_JOIN_EXPLAINER.md`
