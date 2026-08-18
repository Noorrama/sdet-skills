#!/usr/bin/env python3
"""
Extract module -> TestRail project/suite constants from a test automation
repo, and merge with the BrowserStack facts we know (some verified live via
the BrowserStack MCP this session, some found hardcoded in the repo).

Multi-repo, sibling-key convention: this plugin already draws on THREE
automation repos -- gojek-mobile-tests ("gmt", the original), tapmind-
mobile-tests (a separate NLP framework, added by a different session via
its own extract_tapmind_nav_index.py, living entirely under its own
`tapmind_source` / `tapmind_modules` keys), and now gtf-mobile-tests
("gtf", this script's new addition). gmt's `consumer_super_app` /
`separate_projects` are read DIRECTLY (flat, top-level) by the already-
shipped regression-extractor SKILL.md, so this script never nests them --
gtf instead gets its own sibling top-level key, `gtf_source`, exactly the
same pattern tapmind already established with `tapmind_source`. Only gmt's
own two top-level keys and `app_id_to_modules` are touched when repo_key is
"gmt"; only `gtf_source` and `app_id_to_modules` are touched when repo_key
is "gtf" -- `tapmind_source` and any other existing keys are loaded and
passed through untouched either way (merge-on-write).

Scope rules (verified against the real repos before writing this):
  - Dynamically finds every .java file containing a String constant whose
    name contains PROJECT_ID or SUITE_ID (not a fixed file list -- so a
    file added later is picked up automatically). Confirmed this matches
    all 16 known constants files in gmt, plus gtf's single
    ProjectConstants.java (gopay-consumer-app), with zero manual curation.
  - Excludes int constants (e.g. CucumberExecutionListenerContants.java,
    which holds column-index ints for parsing Cucumber Examples rows, not
    project/suite ids) -- the regex only matches `String NAME = "value"`.
  - Also does a repo-wide sweep for literal "PR-<digits>" BrowserStack
    project identifiers wherever they appear (confirmed exactly 2 exist in
    gmt: PR-176 in transport, PR-143 in driverapp; confirmed ZERO exist
    anywhere in gtf).
  - Known facts NOT derivable by static analysis are supplied as constants
    below, each with its provenance noted, so a reader can tell what was
    verified live vs found in code vs still unknown:
      * TestRail project 107 == BrowserStack project PR-176 (gmt). Verified
        live via the BrowserStack MCP (listFolders/listTestCases on
        PR-176): its 36 top-level folders ARE the module namespaces for the
        whole consumer super-app.
      * driverapp (gmt) resolves its BrowserStack project PER CASE at
        runtime via `lumosClient.getProjectIdFromTestCaseId(testCaseId)` --
        there is no single static project id for driverapp; PR-143 is only
        the hardcoded ultimate fallback used when that lookup fails.
      * gtf's 4 TestRail project ids (GOPAY_MOBILE=166, GW_MOBILE=172,
        INSURANCE_MOBILE=3031149, CX_MOBILE=283, all from
        gopay-consumer-app/.../ProjectConstants.java) have NOT been
        confirmed against BrowserStack at all -- zero literal "PR-" strings
        exist anywhere in gtf-mobile-tests to even hint at one. (Note:
        3031149 also appears verbatim in the existing `tapmind_source`
        block for module "gopay-consumer-app" -- a real cross-repo
        agreement worth surfacing to whoever confirms these, not treated as
        confirmation by this script.)
      * gtf's gopay-merchant-app module has NO constants file of any kind
        (confirmed: zero PROJECT_ID/SUITE_ID matches, zero literal "PR-"
        strings). Its 5 test cases are tagged directly with `@C<digits>` on
        the Cucumber scenario (a THIRD id-embedding convention, distinct
        from both gmt's Examples-table columns and gtf's own
        gopay-consumer-app @TestInfo annotations) with no project/suite id
        anywhere alongside them -- the case ids are known but which
        TestRail/BrowserStack project they live under is not recorded
        anywhere in gtf. (TapMind's `tapmind_source` already reports a
        confirmed-ish project id, 168, for its own `gopaymerchant` module --
        that remains the primary automation source for this app_id; gtf is
        a secondary, not-yet-linkable source.)
      * gtf's gopay-kyc-mob-web module has no case-id mechanism of any kind
        (confirmed: zero PROJECT_ID / SUITE_ID / @TestInfo / @C<digits>
        matches across all 23 of its .java files). It is a web
        (Chrome-driven) KYC flow, not an Android/iOS app module, and is not
        one of the 5 canonical app_ids.

Run: python3 extract_project_map.py <repo_root> <repo_key> <output.json>
"""
import sys, os, re, json, subprocess, datetime

# Modifiers are OPTIONAL: interface fields (DriverPlatformTestRailConfig,
# DPTestRailConfig, SuiteConstants) declare `String X = "..."` with no
# `static final` at all -- Java implies it for interface members.
ID_CONST_RE = re.compile(r'(?:(?:public|private|protected|static|final)\s+)*String\s+([A-Za-z0-9_]*(?:PROJECT|SUITE)_ID[A-Za-z0-9_]*)\s*=\s*"([^"]*)"')
PR_RE = re.compile(r'"(PR-\d+)"')

# Modules that are shared infrastructure, not testable feature areas -- they
# never own regression cases of their own. Shared across both repos (both
# gmt and gtf have top-level commons/build/gradle dirs).
INFRA_MODULES = {"commons", "build", "gradle", "log", "helper", "scripts"}


def is_commented_out(text: str, match_start: int) -> bool:
    """True if the line containing this match starts with // once stripped
    of leading whitespace. Confirmed necessary: icp/SCPTestRailConfig.java
    (gmt) has a commented-out `//String SCP_SUITE_ID = "16259";` right above
    the live (blank) declaration."""
    line_start = text.rfind("\n", 0, match_start) + 1
    line_end = text.find("\n", match_start)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].lstrip().startswith("//")

# --- gmt known facts, not derivable from static analysis alone (see docstring) ---
CONSUMER_SUPER_APP = {
    "browserstack_project": "PR-176",
    "browserstack_project_numeric": "2880292",
    "testrail_project": "107",
    "verified": "live, via BrowserStack MCP listFolders(PR-176) -- 36 top-level folders match the module namespaces below",
    "folders": {
        "gofood":             {"booking": 28796662, "discovery": 28796102, "expansion": 28796829, "group_order": 30945403, "free_meal": 28797551, "food_fulfilment": 28797554},
        "transport":          {"partnership": 28796253, "gocorp": 28796308, "iron_bank_growth": 28796414, "booking_experience": 28796341, "journeys": 28796820, "two_wheeler": 30304163, "four_wheeler": 30304164,
                                 "live_tracking": 28796541, "location_places": 28797391},
        "logistics":          {"gosend": 28796556, "gobox": 28796767, "goshop": 28796803},
        "gomart":             {"gomart": 28797431},
        "customer-platforms": {"voucher_discovery": 28796895, "subscriptions": 28796907, "home": 28797004, "archived_pilot": 28796867},
        "icp":                {"identity": 28797331, "comms_gojek_user": 28797135, "comms_user_user": 28797181},
        "helpcenter":         {"helpcenter": 28797278, "chatbot": 28797257},
        "gamification":       {"gamification": 28797510},
        "ads-promo-platform": {"ads_and_promo": 28797521},
    },
}

DRIVERAPP_NOTE = {
    "browserstack_project": None,
    "resolution": "PER-CASE at runtime via lumosClient.getProjectIdFromTestCaseId(testCaseId), see driverapp/src/test/java/io/gojek/driverapptest/utils/UITestRailHelper.java",
    "static_fallback_pr_id": "PR-143",
    "note": "No single project id applies to all driverapp cases -- resolve per case_number via Lumos; PR-143 is only the hardcoded fallback when that lookup fails. Confirmed by human review to also apply to driver-platforms and driver-platform-android (same TestRail project 122, same BrowserStack project ids).",
}
DRIVER_APP_MODULES = ["driverapp", "driver-platforms", "driver-platform-android"]

KNOWN_BROWSERSTACK_PROJECTS_GMT = {
    "gopay": {"browserstack_project": "PR-173", "verified": "human-confirmed, seen live in BrowserStack"},
}

# gtf has zero known BrowserStack project ids -- no listProjects MCP tool and
# zero literal "PR-" strings anywhere in the repo to even guess from.
KNOWN_BROWSERSTACK_PROJECTS_GTF = {}

GTF_NO_CONSTANTS_NOTES = {
    "gopay-merchant-app": (
        "Case ids ARE known (5 scenarios tagged directly with @C<digits> on "
        "the Cucumber Scenario line, e.g. @C4524928 -- see "
        "src/test/resources/features/main.feature), but NO project/suite id "
        "of any kind exists anywhere in this module or its neighbours. "
        "TapMind's gopaymerchant (project 168, see tapmind_source) remains "
        "the primary automation source for the gopay-merchant app_id; this "
        "is a secondary source pending PIC confirmation of a project id."
    ),
    "gopay-kyc-mob-web": (
        "No case-id mechanism of any kind (confirmed: zero PROJECT_ID / "
        "SUITE_ID / @TestInfo / @C<digits> matches across all 23 .java "
        "files). This is a Chrome-driven web KYC flow, not an app module -- "
        "not mapped to any of the 5 canonical app_ids."
    ),
}

# Rewritten in full on every run regardless of repo_key -- small, fully
# hand-verified, and spans repos by design, so partial-merge logic for it
# would be pure overhead. Must reproduce gmt's `modules` and the existing
# `tapmind_modules` entries verbatim (owned by a different, already-shipped
# extractor) alongside the new `gtf_modules` additions.
APP_ID_TO_MODULES = {
    "gojek-consumer": {
        "modules": ["gofood", "transport", "logistics", "gomart", "customer-platforms",
                    "icp", "helpcenter", "gamification", "ads-promo-platform", "gopay"],
        "note": "9 modules share BrowserStack project PR-176 (TestRail 107); 'gopay' is a 10th module for the same app binary (package com.gojek.app) filed under its own TestRail project 138 -- query it separately, it is not part of PR-176.",
    },
    "gojek-driver": {
        "modules": ["driverapp", "driver-platforms", "driver-platform-android"],
        "note": "All three share TestRail project 122 (confirmed via DP_PROJECT_ID / Cucumber Examples project id). driverapp is the primary Cucumber suite; the other two are older TestNG suites for the same app.",
    },
    "gopay-consumer": {
        "modules": ["gopay-consumer"],
        "gtf_modules": ["gopay-consumer-app"],
        "note": "Standalone GoPay app, confirmed by exact android_package match (com.gojek.gopay) for the gmt module. ALSO tested from gtf-mobile-tests via gopay-consumer-app -- package variants com.gojek.gopay.sandbox / com.gojek.gopay.nightly.staging (same app, staging/nightly builds). gtf has 4 TestRail projects for it (GOPAY_MOBILE=166, GW_MOBILE=172, INSURANCE_MOBILE=3031149, CX_MOBILE=283), none yet confirmed against BrowserStack -- note 3031149 also appears in tapmind_source's gopay-consumer-app entry, a cross-repo agreement worth flagging to whoever confirms these.",
    },
    "gofood-merchant": {
        "modules": [],
        "note": "NO_COVERAGE in gojek-mobile-tests (no GoFood Merchant / GoBiz app UI automation here; the only 'gobiz' references are consumer/driver-side helpers hitting GoBiz's backend). Confirmed gtf-mobile-tests has the same zero-coverage result (same style of incidental-reference-only search). HOWEVER the tapmind-mobile-tests repo DOES cover this app -- module 'gofoodmerchantapp', project id 174 (see tapmind_source below). Use the TapMind corpus (config/nav_index/tapmind/, including its project_map.json) as the automation source for this app_id.",
        "tapmind_modules": ["gofoodmerchantapp"],
    },
    "gopay-merchant": {
        "modules": [],
        "gtf_modules": ["gopay-merchant-app"],
        "note": "NO_COVERAGE in gojek-mobile-tests (zero gopaymerchant references). TapMind DOES cover this app -- module 'gopaymerchant', project id 168 (see tapmind_source below) -- and remains the primary automation source. gtf-mobile-tests ALSO has 5 case ids for it (via @C<digits> Cucumber tags, package com.gojek.gopaymerchant.stg -- a near-match, not exact, to gopay-merchant.json's com.gojek.gopay.merchant, needs PIC confirmation) but no project/suite id is recorded anywhere in gtf for this module, so treat it as a secondary source pending that confirmation, not a replacement for TapMind.",
        "tapmind_modules": ["gopaymerchant"],
    },
}


def git_sha(repo_root: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", repo_root, "rev-parse", "HEAD"],
                                        text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def module_of(repo_root: str, path: str) -> str:
    return os.path.relpath(path, repo_root).split(os.sep)[0]


def find_constants_files(repo_root: str):
    hits = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        if ".git" in dirpath.split(os.sep) or "build" in dirpath.split(os.sep):
            continue
        for fn in filenames:
            if not fn.endswith(".java"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                text = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for m in ID_CONST_RE.finditer(text):
                if not is_commented_out(text, m.start()):
                    hits.append((path, text))
                    break
    return hits


def find_pr_ids(repo_root: str):
    found = {}
    for dirpath, dirnames, filenames in os.walk(repo_root):
        if ".git" in dirpath.split(os.sep) or "build" in dirpath.split(os.sep):
            continue
        for fn in filenames:
            if not fn.endswith(".java"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                text = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for m in PR_RE.finditer(text):
                if is_commented_out(text, m.start()):
                    continue
                pr = m.group(1)
                rel = os.path.relpath(path, repo_root)
                found.setdefault(pr, set()).add(rel)
    return {k: sorted(v) for k, v in found.items()}


def scan_modules(repo_root: str):
    modules = {}
    for path, text in find_constants_files(repo_root):
        mod = module_of(repo_root, path)
        rel = os.path.relpath(path, repo_root)
        for m in ID_CONST_RE.finditer(text):
            if is_commented_out(text, m.start()):
                continue
            name, val = m.group(1), m.group(2)
            bucket = modules.setdefault(mod, {"testrail_ids": {}, "source_files": []})
            if rel not in bucket["source_files"]:
                bucket["source_files"].append(rel)
            if val:
                bucket["testrail_ids"][name] = val
            else:
                bucket["testrail_ids"].setdefault(name, None)
    return modules


def build_gmt(repo_root: str, modules: dict):
    modules_covered_by_super_app = set(CONSUMER_SUPER_APP["folders"].keys())
    separate_projects = {}

    for mod in DRIVER_APP_MODULES:
        entry = dict(DRIVERAPP_NOTE)
        entry["testrail_ids"] = modules.get(mod, {}).get("testrail_ids", {})
        entry["source_files"] = modules.get(mod, {}).get("source_files", [])
        separate_projects[mod] = entry

    for mod, data in sorted(modules.items()):
        if mod in modules_covered_by_super_app or mod in DRIVER_APP_MODULES or mod in INFRA_MODULES:
            continue
        entry = {
            "browserstack_project": None,
            "testrail_ids": data["testrail_ids"],
            "source_files": data["source_files"],
        }
        if mod in KNOWN_BROWSERSTACK_PROJECTS_GMT:
            entry.update(KNOWN_BROWSERSTACK_PROJECTS_GMT[mod])
        separate_projects[mod] = entry

    all_top_dirs = [d for d in os.listdir(repo_root)
                     if os.path.isdir(os.path.join(repo_root, d))
                     and not d.startswith(".") and d not in INFRA_MODULES]
    for mod in all_top_dirs:
        if mod in modules_covered_by_super_app or mod in separate_projects:
            continue
        separate_projects[mod] = {
            "browserstack_project": None,
            "testrail_ids": {},
            "source_files": [],
            "note": "no PROJECT_ID/SUITE_ID constants found in this module -- join by tag/title only",
        }

    return CONSUMER_SUPER_APP, separate_projects


def build_gtf(repo_root: str, modules: dict):
    separate_projects = {}
    for mod, data in sorted(modules.items()):
        if mod in INFRA_MODULES:
            continue
        entry = {
            "browserstack_project": None,
            "testrail_ids": data["testrail_ids"],
            "source_files": data["source_files"],
        }
        if mod in KNOWN_BROWSERSTACK_PROJECTS_GTF:
            entry.update(KNOWN_BROWSERSTACK_PROJECTS_GTF[mod])
        separate_projects[mod] = entry

    all_top_dirs = [d for d in os.listdir(repo_root)
                     if os.path.isdir(os.path.join(repo_root, d))
                     and not d.startswith(".") and d not in INFRA_MODULES]
    for mod in all_top_dirs:
        if mod in separate_projects:
            continue
        separate_projects[mod] = {
            "browserstack_project": None,
            "testrail_ids": {},
            "source_files": [],
            "note": GTF_NO_CONSTANTS_NOTES.get(mod, "no PROJECT_ID/SUITE_ID constants found in this module -- join by tag/title only"),
        }
    return separate_projects


def main():
    repo_root, repo_key, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    if repo_key not in ("gmt", "gtf"):
        sys.exit(f"unknown repo_key {repo_key!r}, expected 'gmt' or 'gtf'")

    modules = scan_modules(repo_root)
    pr_ids_found = find_pr_ids(repo_root)

    try:
        with open(out_path) as f:
            out = json.load(f)
    except (OSError, json.JSONDecodeError):
        out = {}
    out.setdefault("_meta", {}).setdefault("generated_per_repo", {})

    out["_meta"]["generated_per_repo"][repo_key] = {
        "generated_by": "extract_project_map.py",
        "generated_from_repo_sha": git_sha(repo_root),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "constants_files_found": sum(len(v["source_files"]) for v in modules.values()),
        "literal_PR_ids_found_repo_wide": pr_ids_found,
    }
    out["_meta"]["note"] = (
        "consumer_super_app (gmt) + its folder ids are a LIVE-VERIFIED fact "
        "from the BrowserStack MCP, not derived from static scan. "
        "separate_projects (gmt), gtf_source.separate_projects (gtf), and "
        "tapmind_source (tapmind) are all derived purely from static scan "
        "and need BrowserStack-side confirmation (no listProjects MCP tool "
        "exists to auto-verify)."
    )

    if repo_key == "gmt":
        consumer_super_app, separate_projects = build_gmt(repo_root, modules)
        out["consumer_super_app"] = consumer_super_app
        out["separate_projects"] = separate_projects
        summary_projects = separate_projects
    else:
        separate_projects = build_gtf(repo_root, modules)
        out["gtf_source"] = {
            "note": "Second automation source repo (gtf-mobile-tests, GoPay-focused: gopay-consumer-app, gopay-merchant-app, gopay-kyc-mob-web). Namespaced separately, same pattern as tapmind_source, because gmt's consumer_super_app/separate_projects are read directly by the shipped regression-extractor SKILL.md and must not change shape. Regenerated by extract_project_map.py.",
            "separate_projects": separate_projects,
        }
        summary_projects = separate_projects

    out["app_id_to_modules"] = APP_ID_TO_MODULES  # spans all repos, rewritten in full every run

    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, sort_keys=False)

    unresolved = [m for m, v in summary_projects.items() if v.get("browserstack_project") is None and m not in DRIVER_APP_MODULES]
    print(f"[{repo_key}] Constants files found: {out['_meta']['generated_per_repo'][repo_key]['constants_files_found']}")
    print(f"[{repo_key}] Literal PR- ids found repo-wide: {pr_ids_found}")
    if repo_key == "gmt":
        print(f"[{repo_key}] Modules under the consumer super-app (PR-176): {len(CONSUMER_SUPER_APP['folders'])}")
    print(f"[{repo_key}] Separate-project modules: {len(summary_projects)}")
    print(f"[{repo_key}]   of which BrowserStack project id NOT yet confirmed: {len(unresolved)} -> {unresolved}")
    no_coverage = [a for a, v in APP_ID_TO_MODULES.items() if not v["modules"] and not v.get("gtf_modules") and not v.get("tapmind_modules")]
    print(f"Canonical apps with NO test coverage in ANY repo: {no_coverage}")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
