#!/usr/bin/env python3
"""Build save-group-for-group-orders impact-shortlister example from GoHost MRs + SDET plan."""
import json, os, re, shutil, sys, urllib.request, urllib.error

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PLUGIN = os.path.join(REPO_ROOT, "plugins", "aep-mobile")
sys.path.insert(0, os.path.join(PLUGIN, "scripts"))
from shortlist_join import draft, now, CONTRACT_VERSION

OUT = os.path.join(PLUGIN, "examples/save_group_feature")
PLAN_SRC = os.path.expanduser("~/Downloads/save-group-for-group-orders_SDET_plan.json")
MR_FILES_PATH = os.path.join(OUT, "mr_changed_files.json")
PROJECT = "mobile%2FGoHost"
MRS = [54280, 54308, 54317, 54169, 54196, 54170, 54222, 54232, 54311]


def load_dotenv(path):
    if not os.path.isfile(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def gitlab_token():
    load_dotenv(os.path.join(REPO_ROOT, ".env"))
    return os.environ.get("GITLAB_READ_TOKEN_FOR_AGENT") or os.environ.get("GITLAB_TOKEN") or ""


def fetch_mr_files():
    token = gitlab_token()
    if not token:
        raise SystemExit("No GitLab token — set GITLAB_READ_TOKEN_FOR_AGENT in skills/.env")
    files, meta = set(), []
    for mr in MRS:
        url = f"https://source.golabs.io/api/v4/projects/{PROJECT}/merge_requests/{mr}/changes"
        req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
        try:
            with urllib.request.urlopen(req) as r:
                d = json.load(r)
            f = {c.get("new_path") or c.get("old_path") for c in d.get("changes", [])
                 if c.get("new_path") or c.get("old_path")}
            files.update(f)
            meta.append({"mr": mr, "title": d.get("title"), "state": d.get("state"), "files": len(f)})
        except urllib.error.HTTPError as e:
            meta.append({"mr": mr, "error": e.code, "body": e.read().decode()[:300]})
    return sorted(files), meta


def infer_from_plan(plan):
    rfc = (plan.get("unmapped_extractor_data") or {}).get("rfc", {})
    apis = [{"endpoint": a["endpoint"]} for a in rfc.get("api_contract_changes", []) if a.get("endpoint")]
    flags = ["isSaveGroupEnabled", "release_food_go_save_group"]
    screens = [
        "GROUP_ORDER_LANDING", "SHARED_CART", "SHARE_TRAY",
        "GROUP_ORDER_LANDING_PAGE", "INVITE_FRIENDS",
    ]
    return apis, flags, screens


def build_regression(plan):
    """Enrichment from legacy scenario rows in the plan itself."""
    tests = []
    seen = set()
    for sc in plan.get("scenario_list", []):
        if not sc.get("is_legacy_regression"):
            continue
        ref = sc.get("existing_case_ref")
        cn = re.search(r"(\d+)\s*$", str(ref or ""))
        if not cn:
            continue
        cn = cn.group(1)
        if cn in seen:
            continue
        seen.add(cn)
        tests.append({
            "id": ref if str(ref).startswith("TC") else f"TC-{cn}",
            "case_number": cn,
            "title": sc.get("csv_title_association"),
            "source_module": "gofood-group-order",
            "priority": sc.get("priority_tier"),
            "steps": sc.get("steps") or [],
            "is_automated": sc.get("automatable", False),
        })
    return {"extraction_status": "COMPLETE", "app": "gojek-consumer",
            "feature_key": plan.get("feature_metadata", {}).get("feature_key"),
            "module_namespace": ["gofood-group-order"],
            "regression_tests": tests}


def agent_finalize(d, plan):
    shortlisted = list(d["must_run"])
    deselected = []
    scope = (plan.get("scope_summary") or "").lower()
    surface = d["change_surface"]
    api_hay = " ".join(surface.get("api_endpoints") or []).lower()

    for item in d["review_queue"]:
        hay = " ".join([item.get("title") or ""] + (item.get("steps") or [])).lower()
        related = any(k in hay for k in (
            "group order", "share tray", "invite", "social group", "shared cart",
            "group cart", "invite friends", "landing page",
        ))
        api_related = any(a.lower() in hay for a in (surface.get("api_endpoints") or []))
        file_related = any(k in hay for k in (
            "group", "share", "invite", "cart", "tray", "social",
        )) and any(k in " ".join(surface.get("changed_files") or []).lower() for k in (
            "grouporder", "group-order", "invite", "share", "social",
        ))
        if related or api_related or file_related:
            shortlisted.append({
                **item,
                "run_tier": "SHOULD_RUN",
                "reason_codes": ["AGENT_JUDGED_RELEVANT"],
                "evidence": {},
                "explanation": (
                    "Legacy case exercises Group Order landing, share tray, or shared cart flows "
                    "that overlap the Save Group MR surface (group-order modules, invite/share APIs)."
                ),
                "source": "plan_legacy",
            })
        else:
            deselected.append({
                "test_id": item["test_id"],
                "case_number": item["case_number"],
                "title": item["title"],
                "reason_code": "NO_IMPACT_SIGNAL",
                "explanation": "No overlap with changed group-order/share/invite files or APIs in this EPIC.",
            })

    pool = d["candidate_pool_size"]
    sel = len(shortlisted)
    buckets = {"GMT_JAVA": [], "TAPMIND_NLP": [], "MANUAL": [], "UNKNOWN_AUTOMATED": []}
    for t in shortlisted:
        buckets.setdefault(t.get("execution_target", "MANUAL"), []).append(t["test_id"])

    fm = plan.get("feature_metadata", {})
    notes = []
    if pool == 0:
        notes.append({
            "field": "candidate_pool",
            "reason": "No is_legacy_regression:true rows with existing_case_ref in SDET plan.",
            "action": "Mark legacy regression cases in the plan before running impact-shortlister.",
            "follow_up": "NEEDS_ANSWER",
        })

    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": now(),
        "extraction_status": "COMPLETE" if pool and not d["unresolved_ids"] else ("LIMITED" if pool == 0 else "PARTIAL"),
        "extraction_notes": notes,
        "feature_metadata": {
            "feature_key": fm.get("feature_key"),
            "epic_ref": fm.get("feature_key"),
            "app": "gojek-consumer",
            "platform": "cross-platform",
            "module_namespace": fm.get("module_namespace"),
        },
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


def main():
    global paths
    os.makedirs(OUT, exist_ok=True)
    plan = json.load(open(PLAN_SRC))
    files, meta = fetch_mr_files()
    json.dump(files, open(MR_FILES_PATH, "w"), indent=2)
    json.dump(meta, open(os.path.join(OUT, "mr_meta.json"), "w"), indent=2)

    apis, flags, screens = infer_from_plan(plan)
    change = {
        "contract_version": "1.0.0",
        "generated_at": now(),
        "app": "gojek-consumer",
        "epic_ref": "save-group-for-group-orders",
        "platform": "cross-platform",
        "bootstrap_from_mr": True,
        "merge_requests": [f"!{m}" for m in MRS],
        "changed_files": files,
        "scoped_to_modules": ["gofood-group-order"],
        "changed_screens": screens,
        "flags": flags,
        "api": apis,
        "cr_risks": [],
        "elements": [],
        "id_compliance": {"status": "NOT_RUN"},
    }
    regression = build_regression(plan)

    paths = {
        "plan": os.path.join(OUT, "save_group_for_group_orders_sdet_plan.json"),
        "regression": os.path.join(OUT, "regression_context.json"),
        "change": os.path.join(OUT, "change_context.bootstrap.json"),
        "draft": os.path.join(OUT, "impact_shortlist.draft.json"),
        "final": os.path.join(OUT, "impact_shortlist.json"),
    }
    shutil.copy2(PLAN_SRC, paths["plan"])
    json.dump(regression, open(paths["regression"], "w"), indent=2)
    json.dump(change, open(paths["change"], "w"), indent=2)

    d = draft(plan, regression, change, None)
    json.dump(d, open(paths["draft"], "w"), indent=2)
    final = agent_finalize(d, plan)
    json.dump(final, open(paths["final"], "w"), indent=2)

    print(json.dumps({
        "mr_files": len(files),
        "pool": d["candidate_pool_size"],
        "must_run": len(d["must_run"]),
        "review_queue": len(d["review_queue"]),
        "shortlisted": final["selection_summary"]["shortlisted_count"],
        "deselected": final["selection_summary"]["deselected_count"],
        "out": paths["final"],
    }, indent=2))


if __name__ == "__main__":
    main()
