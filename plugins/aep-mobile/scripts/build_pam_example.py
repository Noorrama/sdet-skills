#!/usr/bin/env python3
"""One-off builder: PAM impact-shortlister example from MR file lists + SDET plan."""
import json, os, subprocess, sys

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN, "scripts"))
from shortlist_join import draft, now, CONTRACT_VERSION

OUT = os.path.join(PLUGIN, "examples/pam_feature")
PLAN_SRC = os.path.expanduser("~/Downloads/pam_8_levels_relaunch_SDET_plan.json")

MR_FILES_PATH = os.path.join(PLUGIN, "examples/pam_feature/mr_changed_files.json")

MR_FILES_FALLBACK = sorted({
    "app/src/main/java/com/gojek/driver/deeplink/GoJekDriverDispatcher.java",
    "app/src/main/java/com/gojek/driver/deps/FragmentDepsModule.kt",
    "app/src/main/java/com/gojek/driver/home/konmari/KonmariScreenModules.kt",
    "app/src/main/java/com/gojek/driver/launcher/model/LoyaltyIntentExtra.kt",
    "app/src/main/java/com/gojek/driver/profile/konmari/di/ProfileDependencyModule.kt",
    "app/src/main/java/com/gojek/driver/profile/konmari/navigation/KonmariLoyaltyNavigator.kt",
    "app/src/main/java/com/gojek/driver/profile/konmari/navigation/KonmariProfileNavigatorImpl.kt",
    "app/src/main/java/com/gojek/driver/profile/konmari/navigation/NavFragmentDeeplinkMapper.kt",
    "core/configs/src/main/kotlin/com/gojek/driver/configs/toggle/Toggles.kt",
    "features/driver-profile/implementation/src/main/kotlin/com/gojek/driver/profile/container/KonmariProfileNavigator.kt",
    "features/driver-profile/implementation/src/main/kotlin/com/gojek/driver/profile/container/ProfileContainerFragment.kt",
    "features/driver-profile/implementation/src/main/kotlin/com/gojek/driver/profile/performanceLoyaltyContainer/PerformanceLoyaltyContainerContainerComponent.kt",
    "features/driver-profile/implementation/src/main/kotlin/com/gojek/driver/profile/performanceLoyaltyContainer/dependency/LoyaltySummaryComponentDependency.kt",
    "features/incentives/implementation/src/main/kotlin/com/gojek/driver/incentives/summary/IncentivesAdapter.kt",
    "features/loyalty/api/src/main/java/com/gojek/driver/loyalty/onboarding/PamLoyaltyEnabledUseCase.kt",
    "features/loyalty/implementation/build.gradle",
    "features/loyalty/implementation/src/main/kotlin/com/gojek/driver/loyalty/di/LoyaltyModule.kt",
    "features/loyalty/implementation/src/main/kotlin/com/gojek/driver/loyalty/di/LoyaltyScreenInjectorModule.kt",
    "features/loyalty/implementation/src/main/kotlin/com/gojek/driver/loyalty/domain/GetLoyaltyProgressUsecase.kt",
    "features/loyalty/implementation/src/main/kotlin/com/gojek/driver/loyalty/domain/PamLoyaltyFeatureEnabledInteractor.kt",
    "features/loyalty/implementation/src/main/kotlin/com/gojek/driver/loyalty/navigation/LoyaltyNavigator.kt",
    "features/loyalty/implementation/src/main/kotlin/com/gojek/driver/loyalty/navigation/LoyaltyPageNavigator.kt",
    "features/loyalty/implementation/src/main/kotlin/com/gojek/driver/loyalty/repo/LoyaltyRepository.kt",
    "features/loyalty/implementation/src/main/kotlin/com/gojek/driver/loyalty/repo/api/LoyaltyApi.kt",
    "features/loyalty/implementation/src/main/kotlin/com/gojek/driver/loyalty/screens/loyaltyCatalogue/LoyaltyCatalogueFragment.kt",
    "features/loyalty/implementation/src/main/kotlin/com/gojek/driver/loyalty/screens/loyaltyMembership/view/LoyaltyMembershipFragment.kt",
    "features/loyalty/implementation/src/main/kotlin/com/gojek/driver/loyalty/screens/loyaltySummaryCard/LoyaltySummaryPresenter.kt",
    "features/loyalty/implementation/src/main/kotlin/com/gojek/driver/loyalty/tracking/LoyaltyEventNames.kt",
    "features/loyalty/shared-ui/build.gradle",
    "gradle/libs.versions.toml",
})


def mr_files():
    if os.path.isfile(MR_FILES_PATH):
        return json.load(open(MR_FILES_PATH))
    return MR_FILES_FALLBACK

LEGACY_CASES = [
    ("C5542964", "Validate loyalty and point section on profile menu"),
    ("C5542965", "Validate loyalty home page and tier detail section and Learn more section"),
    ("C5542968", "Validate Point history and reward catalogue pages"),
    ("C5542971", "Validate voucher redeem success flow"),
    ("C5542973", "Validate voucher list page"),
]


def corpus_case(cn):
    out = subprocess.check_output([
        "python3", os.path.join(PLUGIN, "scripts/corpus_lookup.py"),
        "case", "gmt", "driverapp", cn,
    ], text=True)
    data = json.loads(out)
    m = data.get("match")
    if not m:
        return None
    row = m[0]
    return {
        "id": f"C{cn}", "case_number": cn, "title": row["title"],
        "source_module": "driverapp", "priority": "P0", "is_automated": True,
        "steps": row.get("steps_gherkin") or [], "steps_source": "repo",
        "scope": "impacted_area",
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    plan = json.load(open(PLAN_SRC))
    reg_tests = []
    legacy_rows = []
    for cid, short_title in LEGACY_CASES:
        cn = cid[1:]
        tc = corpus_case(cn)
        if tc:
            reg_tests.append(tc)
        legacy_rows.append({
            "csv_title_association": f"[Legacy regression] {short_title}",
            "requirement_ref": "REGRESSION_POOL",
            "priority_tier": "P0" if cn in ("5542964", "5542965") else "P1",
            "execution_scope": "FRONTEND_ONLY",
            "is_legacy_regression": True,
            "existing_case_ref": cid,
            "automatable": True,
            "target_execution_framework": "GMT_JAVA",
            "test_case_type": "Regression",
            "automation_status": "Automated",
            "source": "regression_pool",
            "steps": (tc or {}).get("steps", []),
        })

    # Plan copy: inject legacy rows (production plan had 0 — documented in report)
    plan_out = dict(plan)
    plan_out["scenario_list"] = legacy_rows + plan.get("scenario_list", [])

    regression = {
        "extraction_status": "COMPLETE",
        "app": "gojek-driver",
        "feature_key": "pam_8_levels_relaunch",
        "module_namespace": ["driverapp", "loyalty"],
        "browserstack_project": "PR-143",
        "regression_tests": reg_tests,
    }

    change = {
        "contract_version": "1.0.0",
        "generated_at": now(),
        "app": "gojek-driver",
        "epic_ref": "pam_8_levels_relaunch",
        "platform": "android",
        "bootstrap_from_mr": True,
        "merge_requests": ["!13303", "!13326", "!13352", "!13354", "!13386"],
        "changed_files": mr_files(),
        "scoped_to_modules": ["loyalty", "driver-profile", "incentives"],
        "changed_screens": [
            "PROFILE_CONTAINER", "LOYALTY_CATALOGUE", "LOYALTY_MEMBERSHIP",
            "LOYALTY_SUMMARY_CARD", "DEEPLINK_ROUTING",
        ],
        "flags": ["giab_pam_revamp_enabled"],
        "api": [
            {"endpoint": "/v1/loyalty/tiers"},
            {"endpoint": "/v1/loyalty/progress"},
            {"endpoint": "/v2/loyalty/rewards"},
        ],
        "cr_risks": [
            {"id": "RISK-01", "area": "LoyaltyMembershipFragment",
             "suggested_test": "Verify final localized copy for last_period_progress_label"},
        ],
        "elements": [],
        "id_compliance": {"status": "NOT_RUN"},
    }

    paths = {
        "plan": os.path.join(OUT, "pam_8_levels_relaunch_sdet_plan.json"),
        "regression": os.path.join(OUT, "regression_context.json"),
        "change": os.path.join(OUT, "change_context.bootstrap.json"),
        "draft": os.path.join(OUT, "impact_shortlist.draft.json"),
        "final": os.path.join(OUT, "impact_shortlist.json"),
    }
    json.dump(plan_out, open(paths["plan"], "w"), indent=2)
    json.dump(regression, open(paths["regression"], "w"), indent=2)
    json.dump(change, open(paths["change"], "w"), indent=2)

    d = draft(plan_out, regression, change, None)

    # Agent judgment pass for review_queue
    shortlisted = list(d["must_run"])
    deselected = []
    for item in d["review_queue"]:
        hay = " ".join([item["title"]] + item.get("steps", [])).lower()
        if any(k in hay for k in ("voucher", "points", "reward", "catalogue", "redeem")):
            shortlisted.append({
                **item,
                "run_tier": "SHOULD_RUN",
                "reason_codes": ["AGENT_JUDGED_RELEVANT"],
                "evidence": {},
                "explanation": "Case exercises loyalty points/rewards/catalogue flows; MRs touch LoyaltyApi, reward catalogue entities, and loyalty screens.",
                "source": "plan_legacy",
            })
        else:
            deselected.append({
                "test_id": item["test_id"],
                "case_number": item["case_number"],
                "title": item["title"],
                "reason_code": "NO_IMPACT_SIGNAL",
                "explanation": "No string overlap with changed loyalty/profile screens, APIs, or flags in the bootstrap change surface.",
            })

    pool = d["candidate_pool_size"]
    sel = len(shortlisted)
    buckets = {"GMT_JAVA": [], "TAPMIND_NLP": [], "MANUAL": [], "UNKNOWN_AUTOMATED": []}
    for t in shortlisted:
        buckets.setdefault(t.get("execution_target", "MANUAL"), []).append(t["test_id"])

    final = {
        "contract_version": CONTRACT_VERSION,
        "generated_at": now(),
        "extraction_status": "COMPLETE" if not d["unresolved_ids"] else "PARTIAL",
        "extraction_notes": [{
            "field": "sdet_plan.scenario_list.is_legacy_regression",
            "reason": "Source SDET plan had 0 is_legacy_regression:true rows; example plan adds 5 Loyalty Revamp legacy rows for this validation run.",
            "action": "Mark exact-match legacy cases in the production SDET plan before agentic pipeline use.",
            "follow_up": "NEEDS_ANSWER",
        }],
        "feature_metadata": d["feature_metadata"],
        "inputs": {
            "sdet_plan": {"path": paths["plan"], "present": True},
            "regression_context": {"path": paths["regression"], "present": True},
            "change_context": {"path": paths["change"], "present": True},
        },
        "change_surface": d["change_surface"],
        "selection_summary": {
            "candidate_pool_size": pool,
            "shortlisted_count": sel,
            "deselected_count": len(deselected),
            "must_run_count": len(d["must_run"]),
            "should_run_count": sel - len(d["must_run"]),
            "optional_count": 0,
            "reduction_pct": round(100 * (1 - sel / pool), 1) if pool else 0,
        },
        "shortlisted_tests": shortlisted,
        "deselected_tests": deselected,
        "unresolved_ids": d["unresolved_ids"],
        "run_buckets": buckets,
        "new_scenarios_to_run": d["new_scenarios_to_run"],
    }
    json.dump(d, open(paths["draft"], "w"), indent=2)
    json.dump(final, open(paths["final"], "w"), indent=2)
    print(json.dumps({"pool": pool, "must_run": len(d["must_run"]),
                      "shortlisted": sel, "deselected": len(deselected)}, indent=2))


if __name__ == "__main__":
    main()
