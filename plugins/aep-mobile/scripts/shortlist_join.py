#!/usr/bin/env python3
"""
Deterministic join for the impact-shortlister skill.

Takes the pre-build legacy regression candidate pool (SDET_PLAN rows where
is_legacy_regression is true, enriched from regression_context when available)
and the post-build change surface (change_context / dev_manifest / MR bootstrap),
and does pure evidence matching: which candidates have a concrete link to what
actually changed. Those become MUST_RUN with evidence.

Everything left over goes to review_queue for the calling agent to judge from
title/steps against the change surface. No scoring service; no PLAN_SCENARIO_LINK
auto-MUST_RUN — plan linkage is traceability only.

Usage:
  shortlist_join.py draft --plan <sdet_plan.json> \
      [--regression regression_context.json] [--change change_context.json] \
      [--manifest dev_manifest.json] [--out impact_shortlist.draft.json]

  shortlist_join.py patch-plan --shortlist <impact_shortlist.json> --plan <sdet_plan.json>

  shortlist_join.py --demo
"""
import argparse, datetime, json, os, re, sys

CONTRACT_VERSION = "1.0.0"

# Repo path segments → module tags for MR-bootstrap when scoped_to_modules is absent.
_PATH_MODULE_HINTS = (
    ("features/loyalty/", "loyalty"),
    ("driver/profile", "driver-profile"),
    ("driver-profile", "driver-profile"),
    ("features/incentives/", "incentives"),
    ("deeplink", "navigation"),
)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def case_number(raw):
    if raw is None:
        return None
    m = re.search(r"(\d+)\s*$", str(raw).strip())
    return m.group(1) if m else None


def load(path):
    with open(path) as f:
        return json.load(f)


def regression_index(regression):
    by_cn = {}
    for tc in (regression or {}).get("regression_tests", []):
        cn = case_number(tc.get("id") or tc.get("case_number"))
        if cn:
            by_cn[cn] = tc
    return by_cn


def build_pool(plan, regression):
    """Legacy-only pool: plan rows with is_legacy_regression true + existing_case_ref.
    Enrich title/steps/source_module from regression_context when the case id matches."""
    pool = {}
    reg = regression_index(regression)
    for sc in plan.get("scenario_list", []):
        if not sc.get("is_legacy_regression"):
            continue
        cn = case_number(sc.get("existing_case_ref"))
        if not cn:
            continue
        tc = reg.get(cn, {})
        steps = tc.get("steps") or sc.get("steps") or []
        if not steps and tc.get("steps_gherkin"):
            steps = tc["steps_gherkin"]
        pool[cn] = {
            "case_number": cn,
            "browserstack_id": sc.get("existing_case_ref") or tc.get("id"),
            "title": tc.get("title") or sc.get("csv_title_association"),
            "source": "plan_legacy",
            "source_module": tc.get("source_module") or "driverapp",
            "priority": sc.get("priority_tier") or tc.get("priority"),
            "steps": steps,
            "is_automated": tc.get("is_automated", sc.get("automatable")),
            "has_tapmind_steps": bool(tc.get("tapmind_steps")),
            "plan_scenario_refs": [sc.get("csv_title_association")],
            "_target_framework": sc.get("target_execution_framework"),
        }
    return pool


def infer_modules_from_files(changed_files):
    mods = set()
    joined = " ".join(changed_files).lower()
    for needle, mod in _PATH_MODULE_HINTS:
        if needle.lower() in joined:
            mods.add(mod)
    if "loyalty" in joined:
        mods.add("loyalty")
    return sorted(mods)


def infer_screens_from_files(changed_files):
    screens = set()
    patterns = (
        (r"ProfileContainerFragment", "PROFILE_CONTAINER"),
        (r"LoyaltyCatalogueFragment", "LOYALTY_CATALOGUE"),
        (r"LoyaltyMembershipFragment", "LOYALTY_MEMBERSHIP"),
        (r"loyaltySummaryCard", "LOYALTY_SUMMARY_CARD"),
        (r"LoyaltySummary", "LOYALTY_SUMMARY"),
        (r"deeplink", "DEEPLINK_ROUTING"),
    )
    joined = "\n".join(changed_files)
    for pat, sid in patterns:
        if re.search(pat, joined, re.I):
            screens.add(sid)
    return sorted(screens)


def change_surface(change, manifest):
    if change:
        elements = change.get("elements", [])
        from_elements = sorted({e.get("provenance", {}).get("file")
                                for e in elements if e.get("provenance", {}).get("file")})
        changed_files = sorted(set(change.get("changed_files") or from_elements))
        modules = change.get("scoped_to_modules") or infer_modules_from_files(changed_files)
        screens = change.get("changed_screens") or infer_screens_from_files(changed_files)
        src = change.get("surface_source") or "change_context"
        if change.get("bootstrap_from_mr"):
            src = "gitlab_mr_diff"
        return {
            "source": src,
            "merge_requests": change.get("merge_requests", []),
            "changed_files": changed_files,
            "changed_modules": modules,
            "changed_screens": screens,
            "changed_element_ids": [{"element_id": e["element_id"], "change_type": e.get("change_type", "modified")}
                                    for e in elements if e.get("element_id")],
            "flags": [f if isinstance(f, str) else f.get("name")
                      for f in change.get("flags", []) if f],
            "api_endpoints": [a.get("endpoint") if isinstance(a, dict) else a
                              for a in change.get("api", []) if a],
            "cr_risks": [{"id": r.get("id"), "area": r.get("area"), "suggested_test": r.get("suggested_test")}
                        for r in change.get("cr_risks", [])],
            "id_compliance_status": (change.get("id_compliance") or {}).get("status", "NOT_RUN"),
        }
    m = manifest or {}
    screens_data = m.get("screens", [])
    changed_files = sorted({e.get("provenance", {}).get("file")
                            for s in screens_data for e in s.get("elements", [])
                            if e.get("provenance", {}).get("file")})
    return {
        "source": "dev_manifest",
        "merge_requests": m.get("merge_requests", []),
        "changed_files": changed_files,
        "changed_modules": infer_modules_from_files(changed_files),
        "changed_screens": [s.get("screen_id") for s in screens_data if s.get("screen_id")],
        "changed_element_ids": [{"element_id": e["generated_logical_id"], "change_type": e.get("change_type", "modified")}
                                for s in screens_data for e in s.get("elements", [])
                                if e.get("generated_logical_id")],
        "flags": sorted({f.get("name") for s in screens_data for f in s.get("flags_used", []) if f.get("name")}),
        "api_endpoints": sorted({a.get("endpoint") for s in screens_data for a in s.get("apis_touched", []) if a.get("endpoint")}),
        "cr_risks": [],
        "id_compliance_status": "NOT_RUN",
    }


def haystack(cand):
    return " ".join([cand.get("title") or ""] + (cand.get("steps") or [])).lower()


def file_path_tokens(changed_files):
    tokens = set()
    for path in changed_files:
        base = os.path.basename(path).lower().replace(".kt", "").replace(".java", "").replace(".xml", "")
        for part in re.split(r"[/_.]", path.lower()):
            if len(part) > 3:
                tokens.add(part)
        if base:
            tokens.add(base)
    return tokens


def deterministic_classify(cand, surface):
    reasons, ev = [], {}
    hay = haystack(cand)

    if cand.get("source_module") and cand["source_module"] in surface["changed_modules"]:
        reasons.append("MODULE_TOUCHED")
        ev["changed_modules"] = [cand["source_module"]]

    broken = [e["element_id"] for e in surface["changed_element_ids"]
              if e["change_type"] in ("modified", "removed")
              and e["element_id"].split(".")[-1].lower() in hay]
    if broken:
        reasons.append("LOCATOR_CHANGED")
        ev["element_ids"] = broken

    hit_screens = [s for s in surface["changed_screens"] if s and s.lower().replace("_", " ") in hay.replace("_", " ")]
    if not hit_screens:
        hit_screens = [s for s in surface["changed_screens"] if s and s.lower() in hay]
    if hit_screens:
        reasons.append("SCREEN_TOUCHED")
        ev["screens"] = hit_screens

    hit_flags = [f for f in surface["flags"] if f and f.lower() in hay]
    if hit_flags:
        reasons.append("FLAG_TOUCHED")
        ev["flags"] = hit_flags

    hit_apis = [a for a in surface["api_endpoints"] if a and a.lower() in hay]
    if hit_apis:
        reasons.append("API_CONTRACT_CHANGED")
        ev["api_endpoints"] = hit_apis

    module = (cand.get("source_module") or "").lower()
    hit_cr = [r["id"] for r in surface["cr_risks"]
              if r.get("id") and ((r.get("area") or "").lower() in (module,) + tuple(hay.split())
                                   or (r.get("suggested_test") or "").lower() in hay)]
    if hit_cr:
        reasons.append("CR_RISK")
        ev["cr_risk_ids"] = hit_cr

    path_hits = []
    for tok in file_path_tokens(surface["changed_files"]):
        if tok in ("loyalty", "profile", "catalogue", "membership", "achievement", "tier", "pam"):
            if tok in hay or (tok == "loyalty" and "loyalty" in hay):
                path_hits.append(tok)
    path_hits = sorted(set(path_hits))
    if path_hits:
        reasons.append("FILE_PATH_TOUCHED")
        ev["path_tokens"] = path_hits

    return reasons, ev


def framework_hint(cand):
    if cand.get("_target_framework"):
        return cand["_target_framework"]
    if cand.get("has_tapmind_steps"):
        return "TAPMIND_NLP"
    if cand.get("is_automated"):
        return "UNKNOWN_AUTOMATED"
    return "MANUAL"


def draft(plan, regression, change, manifest):
    pool = build_pool(plan, regression)
    surface = change_surface(change, manifest)

    must_run, review_queue, unresolved = [], [], []
    for cn, cand in pool.items():
        if not cand.get("title"):
            unresolved.append({"id": cand.get("browserstack_id") or cn, "source": cand["source"],
                               "reason": "MALFORMED_ID"})
            continue
        reasons, ev = deterministic_classify(cand, surface)
        if reasons:
            must_run.append({
                "test_id": cand.get("browserstack_id") or f"C{cn}", "case_number": cn,
                "browserstack_id": cand.get("browserstack_id"), "title": cand["title"],
                "run_tier": "MUST_RUN", "reason_codes": sorted(set(reasons)), "evidence": ev,
                "execution_target": framework_hint(cand), "priority": cand.get("priority"),
                "source_module": cand.get("source_module"),
                "plan_scenario_refs": [r for r in cand.get("plan_scenario_refs", []) if r],
                "source": cand["source"],
            })
        else:
            review_queue.append({
                "test_id": cand.get("browserstack_id") or f"C{cn}", "case_number": cn,
                "browserstack_id": cand.get("browserstack_id"), "title": cand["title"],
                "steps": cand.get("steps") or [], "priority": cand.get("priority"),
                "source_module": cand.get("source_module"),
                "execution_target": framework_hint(cand),
                "plan_scenario_refs": [r for r in cand.get("plan_scenario_refs", []) if r],
                "source": cand["source"],
            })

    fm = plan.get("feature_metadata", {})
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": now(),
        "feature_metadata": {
            "feature_key": fm.get("feature_key"),
            "epic_ref": (change or manifest or {}).get("epic_ref"),
            "app": (change or manifest or {}).get("app"),
            "platform": (change or {}).get("platform"),
            "module_namespace": fm.get("module_namespace"),
        },
        "change_surface": surface,
        "candidate_pool_size": len(pool),
        "must_run": must_run,
        "review_queue": review_queue,
        "unresolved_ids": unresolved,
        "new_scenarios_to_run": [
            {"csv_title_association": s.get("csv_title_association"),
             "requirement_ref": s.get("requirement_ref"),
             "priority_tier": s.get("priority_tier"),
             "target_execution_framework": s.get("target_execution_framework")}
            for s in plan.get("scenario_list", []) if not s.get("is_legacy_regression")],
    }


def plan_patch(sl, ref):
    tiers = {"MUST_RUN": [], "SHOULD_RUN": [], "OPTIONAL": []}
    for t in sl["shortlisted_tests"]:
        tiers.setdefault(t["run_tier"], []).append(t["test_id"])
    return {
        "contract_version": sl.get("contract_version", CONTRACT_VERSION),
        "generated_at": sl["generated_at"], "ref": ref, "status": sl["extraction_status"],
        "merge_requests": sl["change_surface"]["merge_requests"],
        "candidate_pool_size": sl["selection_summary"]["candidate_pool_size"],
        "shortlisted_count": sl["selection_summary"]["shortlisted_count"],
        "reduction_pct": sl["selection_summary"]["reduction_pct"],
        "must_run": tiers["MUST_RUN"], "should_run": tiers["SHOULD_RUN"], "optional": tiers["OPTIONAL"],
        "run_buckets": sl.get("run_buckets", {}),
        "new_scenario_count": len(sl.get("new_scenarios_to_run", [])),
    }


def cmd_draft(a):
    plan = load(a.plan)
    d = draft(plan, load(a.regression) if a.regression else None,
              load(a.change) if a.change else None, load(a.manifest) if a.manifest else None)
    d["inputs"] = {k: {"path": v, "present": bool(v and os.path.isfile(v))}
                   for k, v in {"sdet_plan": a.plan, "regression_context": a.regression,
                                "change_context": a.change, "dev_manifest": a.manifest}.items() if v}
    with open(a.out, "w") as f:
        json.dump(d, f, indent=2)
    print(f"wrote {a.out}: pool={d['candidate_pool_size']} must_run={len(d['must_run'])} "
          f"review_queue={len(d['review_queue'])} (resolve review_queue yourself, then write the final file)")


def cmd_patch_plan(a):
    sl, plan = load(a.shortlist), load(a.plan)
    plan["impact_shortlist"] = plan_patch(sl, os.path.basename(a.shortlist))
    plan["updated_at"] = now()
    with open(a.plan, "w") as f:
        json.dump(plan, f, indent=2)
    print(f"patched {a.plan} with impact_shortlist roll-up")


def demo():
    plan = {"feature_metadata": {"feature_key": "demo"}, "scenario_list": [
        {"csv_title_association": "old flow still works", "existing_case_ref": "C111",
         "is_legacy_regression": True, "priority_tier": "P0", "target_execution_framework": "GMT_JAVA"},
        {"csv_title_association": "brand new card", "priority_tier": "P0", "requirement_ref": "BR-1",
         "is_legacy_regression": False, "target_execution_framework": "TAPMIND_NLP"}]}
    regression = {"regression_tests": [
        {"id": "C111", "title": "old flow still works on HOMESCREEN", "priority": "P0",
         "source_module": "home", "steps": ["Open home", "Tap old card"], "is_automated": True},
        {"id": "C222", "title": "unrelated settings PIN change", "priority": "P2",
         "source_module": "settings", "steps": ["Open settings", "Change PIN"], "is_automated": True}]}
    change = {"app": "gopay-consumer", "epic_ref": "demo", "platform": "ANDROID",
              "merge_requests": ["!7101"], "changed_screens": ["HOMESCREEN"],
              "scoped_to_modules": ["home"], "flags": [], "api": [],
              "elements": [{"element_id": "HOMESCREEN.TAP_BIRTHDAY_CARD", "change_type": "modified",
                            "provenance": {"mr": "!7101", "file": "lib/home/genie/card.dart"}}],
              "id_compliance": {"status": "PASS"}}

    d = draft(plan, regression, change, None)
    must = {t["test_id"]: t for t in d["must_run"]}
    review = {t["test_id"]: t for t in d["review_queue"]}

    assert d["candidate_pool_size"] == 1, d["candidate_pool_size"]
    assert "C111" in must and "SCREEN_TOUCHED" in must["C111"]["reason_codes"]
    assert "PLAN_SCENARIO_LINK" not in must["C111"]["reason_codes"]
    assert "C222" not in must and "C222" not in review
    assert len(d["new_scenarios_to_run"]) == 1

    final = {"contract_version": CONTRACT_VERSION, "generated_at": d["generated_at"],
             "extraction_status": "COMPLETE", "change_surface": d["change_surface"],
             "selection_summary": {"candidate_pool_size": 1, "shortlisted_count": 1, "reduction_pct": 0.0},
             "shortlisted_tests": [{"test_id": "C111", "run_tier": "MUST_RUN"}],
             "run_buckets": {"GMT_JAVA": ["C111"]},
             "new_scenarios_to_run": d["new_scenarios_to_run"]}
    patch = plan_patch(final, "impact_shortlist.json")
    assert patch["must_run"] == ["C111"]
    print("demo ok: pool=%d must_run=%d review_queue=%d" % (d["candidate_pool_size"], len(must), len(review)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    p1 = sub.add_parser("draft")
    p1.add_argument("--plan", required=True)
    p1.add_argument("--regression"); p1.add_argument("--change"); p1.add_argument("--manifest")
    p1.add_argument("--out", default="impact_shortlist.draft.json")
    p1.set_defaults(func=cmd_draft)

    p2 = sub.add_parser("patch-plan")
    p2.add_argument("--shortlist", required=True)
    p2.add_argument("--plan", required=True)
    p2.set_defaults(func=cmd_patch_plan)

    a = ap.parse_args()
    if a.demo:
        return demo()
    if not a.cmd:
        ap.error("pass 'draft', 'patch-plan', or --demo")
    a.func(a)


if __name__ == "__main__":
    sys.exit(main())
