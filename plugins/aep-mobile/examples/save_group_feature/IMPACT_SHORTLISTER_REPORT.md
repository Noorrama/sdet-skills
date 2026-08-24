# Impact Shortlister — Save Group for Group Orders Validation

**Feature:** Save Group for Group Orders M5 (`save-group-for-group-orders`)  
**App:** Gojek Consumer (`gojek-consumer`)  
**Repo:** `mobile/GoHost`  
**Generated:** 2026-08-24

---

## Summary

| Metric | Value |
|--------|-------|
| Legacy candidate pool | **3** unique cases (from 5 plan rows) |
| Shortlisted | **3** (all MUST_RUN) |
| Deselected | 0 |
| New scenarios (always run) | 68 |
| MRs analyzed | 9 (!54169–!54317) |
| Changed files (union) | 59 |
| Change surface source | `gitlab_mr_diff` bootstrap |

**Output:** `examples/save_group_feature/impact_shortlist.json`

Unlike PAM, this plan already has proper **`is_legacy_regression: true`** rows — no plan patching required.

---

## MRs analyzed

| MR | Author area | Title | State | Files |
|----|-------------|-------|-------|-------|
| !54280 | Ian | Group Order M5 3_dots_logic | merged | 5 |
| !54308 | — | add_to_social_group_flow | merged | 23 |
| !54317 | — | GO shared cart social group entry point UI | opened | 4 |
| !54169 | Ian | Move add item & add saved group indicator | merged | 13 |
| !54196 | Ian | 3 dots with actions (except add to social) | merged | 16 |
| !54170 | Siddhant | Litmus config for Group Order M5 (Save Group) | merged | 3 |
| !54222 | Siddhant | Standalone UI components for Save Group selected state | merged | 2 |
| !54232 | Siddhant | Standalone Social Group card UI for AOS | merged | 5 |
| !54311 | Siddhant | Wire Social Group chat entry point into AOS | opened | 12 |

Token loaded from `skills/.env` → `GITLAB_READ_TOKEN_FOR_AGENT`.

---

## Legacy pool (from SDET plan)

5 plan rows marked `is_legacy_regression: true` → **3 unique** BrowserStack refs:

| Case ID | Plan scenarios (count) | Area |
|---------|------------------------|------|
| **TC-302383** | 1 | GO landing — "Groups you can invite" |
| **TC-302484** | 3 | Share Tray (pre-GO, post-GO, BAU empty) |
| **TC-302761** | 1 | Shared Cart three-dots / Remove from Group Order |

The script dedupes by case number; one pool entry per unique legacy case ID.

---

## Shortlisted tests — why each was selected

### TC-302383 — Landing page / Social Groups invite section

**Tier:** MUST_RUN  
**Reason codes:** `MODULE_TOUCHED`, `SCREEN_TOUCHED`, `FILE_PATH_TOUCHED`

**Evidence:**
- Module `gofood-group-order` touched across MRs
- Screens `GROUP_ORDER_LANDING`, `GROUP_ORDER_LANDING_PAGE`
- MR files include `SaveGroupSection.kt`, `SocialGroupCard.kt`, `GroupOrderConfig.kt`

**Why:** Landing-page saved-group UI is core M5 scope; MRs add Save Group section and social group cards on the GO landing flow.

---

### TC-302484 — Share Tray flows (3 plan variants, 1 legacy case ID)

**Tier:** MUST_RUN  
**Reason codes:** `MODULE_TOUCHED`, `SCREEN_TOUCHED`, `FILE_PATH_TOUCHED`

**Evidence:**
- Screen `SHARE_TRAY`
- MR files include `GroupShareTray.kt` (explicitly called out in RFC as existing tray being extended/deprecated)

**Why:** All three plan variants exercise Share Tray behaviour; merged code heavily touches `GroupShareTray.kt` and invite/social-group flows (!54308 add_to_social_group).

---

### TC-302761 — Shared Cart three-dots / Remove from Group Order

**Tier:** MUST_RUN  
**Reason codes:** `MODULE_TOUCHED`, `SCREEN_TOUCHED`, `FILE_PATH_TOUCHED`

**Evidence:**
- Screen `SHARED_CART`
- Path tokens: `cart`, `gofood`
- MRs: `GFDGroupOrderSharedCartActivity.kt`, `GroupOrderSharedCartViewModel.kt`, `GroupOrderSharedCartActionProcessor.kt`, !54280/!54196 three-dots logic

**Why:** Shared cart member actions and 3-dot menu are direct MR targets (Ian’s !54196, !54280).

---

## Change surface highlights

**Modules:** `gofood-group-order`

**Key file areas (59 files):**
- `food-grouporder/` — shared cart VM, presentation, API models, Save Group UI
- `GroupShareTray.kt`, `SaveGroupSection.kt`, `SocialGroupCard.kt`
- `food-fbon/` — AOS social group widget, post-booking transformers
- `GroupOrderConfig.kt` / `GroupOrderConstants.kt` — Litmus toggle

**APIs (from plan RFC, used in bootstrap):**
- `POST /gofood/meal-scheduler/v1/group-order-sessions` (+ `invite_social_group_id`)
- `POST .../invite` (mutually exclusive social vs history ids)
- `GET .../group-order-sessions/{id}` (+ `social_group` object)
- `POST .../invite-social-group-members` (new)

**Flags:** `isSaveGroupEnabled`, `release_food_go_save_group`

---

## Re-run locally

```bash
# From repo root — reads skills/.env automatically
python3 plugins/aep-mobile/scripts/build_save_group_example.py
```

Artifacts land in `plugins/aep-mobile/examples/save_group_feature/`.

---

## Notes

1. **0% reduction** is expected when the legacy pool is small (3 cases) and all three clearly touch group-order/share/cart MR surface.
2. **Production path:** replace `change_context.bootstrap.json` with real output from `code-change-extractor` when dev manifest lands — adds locator-level `LOCATOR_CHANGED` matching.
3. **TC-302484** maps to 3 distinct plan scenarios; pool dedupes to one case ID — all three behaviours are covered by the same legacy automation case.
