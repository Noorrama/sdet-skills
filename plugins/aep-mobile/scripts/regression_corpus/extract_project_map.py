#!/usr/bin/env python3
"""
Extract module -> TestRail project/suite constants from gojek-mobile-tests,
and merge with the BrowserStack facts we know (some verified live via the
BrowserStack MCP this session, some found hardcoded in the repo).

Scope rules (verified against the real repo before writing this):
  - Dynamically finds every .java file containing a String constant whose
    name contains PROJECT_ID or SUITE_ID (not a fixed file list -- so a
    file added later is picked up automatically). Confirmed this matches
    all 16 known constants files with zero manual curation.
  - Excludes int constants (e.g. CucumberExecutionListenerContants.java,
    which holds column-index ints for parsing Cucumber Examples rows, not
    project/suite ids) -- the regex only matches `String NAME = "value"`.
  - Also does a repo-wide sweep for literal "PR-<digits>" BrowserStack
    project identifiers wherever they appear (confirmed exactly 2 exist in
    the whole repo: PR-176 in transport, PR-143 in driverapp).
  - Known facts NOT derivable by static analysis are supplied as constants
    below, each with its provenance noted, so a reader can tell what was
    verified live vs found in code vs still unknown:
      * TestRail project 107 == BrowserStack project PR-176. Verified live
        via the BrowserStack MCP (listFolders/listTestCases on PR-176):
        its 36 top-level folders ARE the module namespaces for the whole
        consumer super-app (GoFood, Transport, Logistics, Quick Commerce,
        Customer/Communication/Care Platform, Identity, Gamification,
        Ads&Promo, Food Fulfilment, Carto).
      * driverapp resolves its BrowserStack project PER CASE at runtime via
        `lumosClient.getProjectIdFromTestCaseId(testCaseId)`
        (driverapp/.../utils/UITestRailHelper.java) -- there is no single
        static project id for driverapp; PR-143 is only the hardcoded
        ultimate fallback used when that lookup fails.
      * gopay (138), gopay-consumer (139), driver-platforms/driver-
        platform-android (122), campaign-manager (186) have NOT been
        confirmed against BrowserStack yet -- no listProjects MCP tool
        exists to enumerate all ~150 projects, and none of these appeared
        in the PR-176 folder tree, so they are presumed separate projects
        with unknown PR- ids.

Run: python3 extract_project_map.py <repo_root> <output.json>
"""
import sys, os, re, json, subprocess, datetime

# Modifiers are OPTIONAL: interface fields (DriverPlatformTestRailConfig,
# DPTestRailConfig, SuiteConstants) declare `String X = "..."` with no
# `static final` at all -- Java implies it for interface members. An
# earlier version of this script required literal "static final String"
# and silently missed all three files. Confirmed fix against source.
ID_CONST_RE = re.compile(r'(?:(?:public|private|protected|static|final)\s+)*String\s+([A-Za-z0-9_]*(?:PROJECT|SUITE)_ID[A-Za-z0-9_]*)\s*=\s*"([^"]*)"')
PR_RE = re.compile(r'"(PR-\d+)"')

# Modules that are shared infrastructure, not testable feature areas -- they
# never own regression cases of their own, so they should never appear as an
# "unresolved project" in the output.
INFRA_MODULES = {"commons", "build", "gradle", "log", "helper", "scripts"}


def is_commented_out(text: str, match_start: int) -> bool:
    """True if the line containing this match starts with // once stripped
    of leading whitespace. Confirmed necessary: icp/SCPTestRailConfig.java
    has a commented-out `//String SCP_SUITE_ID = "16259";` right above the
    live (blank) declaration -- naive regex would have picked up the dead
    value as if it were current."""
    line_start = text.rfind("\n", 0, match_start) + 1
    line_end = text.find("\n", match_start)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].lstrip().startswith("//")

# --- known facts, not derivable from static analysis alone (see docstring) ---
CONSUMER_SUPER_APP = {
    "browserstack_project": "PR-176",
    "browserstack_project_numeric": "2880292",
    "testrail_project": "107",
    "verified": "live, via BrowserStack MCP listFolders(PR-176) -- 36 top-level folders match the module namespaces below",
    # Keys here are REAL top-level gojek-mobile-tests directory names (verified
    # against `os.listdir(repo_root)`), because the script below excludes a
    # module from "separate_projects" by checking membership in this dict --
    # an earlier version used invented group labels ("quick_commerce",
    # "food_fulfilment") that don't match any repo directory, so gomart was
    # wrongly reported as an unresolved separate project even though it is
    # confirmed (both by GO_MART_PROJECT_ID=107 in the repo AND by the live
    # BrowserStack folder tree) to be one of PR-176's own folders.
    # "food_fulfilment" (BrowserStack folder 28797554) is merged into gofood,
    # since its TestRail id (FOOD_FULFILMENT_ID=19543) lives inside
    # GoFoodProjectDetails.java, not a separate module.
    # "goshop" (BrowserStack folder 28796803, "Quick Commerce - GoShop") is
    # merged into logistics, since GoShop's code lives under
    # logistics/src/main/resources/goShop -- there is no top-level `goshop`
    # repo directory.
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
    # "Carto - Live tracking" (28796541) and "Carto - Location Places" (28797391)
    # were first assumed to have no repo counterpart. Checked: real code exists
    # at transport/.../tests/livetracking/search/ppoisearch and
    # transport/.../pages/poicard, so they were folded into transport above
    # instead of being left in an "unmatched" bucket. Kept as a code comment
    # (not a live JSON field) purely as a trail of that check for a future
    # re-run of this script to reference.
}

# Maps the 5 canonical `app_id` values (plugins/aep-mobile/config/<app_id>.json,
# used everywhere else in this plugin) to the repo module(s) that test them.
# This is a DIFFERENT vocabulary from the repo's own module names, and the
# mapping is not 1:1 or obvious -- verified by cross-checking each module's
# actual Android package string (grep '"com.gojek.[a-zA-Z.]*"') against each
# app config's declared android_package, not by name-guessing:
#   - "gopay" module (TestRail 138) uses package com.gojek.app -- the SAME
#     package as gojek-consumer, not a separate app. Its deeplinks are also
#     path fragments under the gojek:// scheme (gojek://gopay/...), never a
#     bare gopay:// scheme. So it is GoPay-the-wallet-*inside*-Gojek, filed
#     under its own TestRail project (138) for organisational reasons, but
#     it is gojek-consumer's app binary, not gopay-consumer's.
#   - "gopay-consumer" module (TestRail 139) uses package com.gojek.gopay --
#     an EXACT match to gopay-consumer.json's android_package. This is the
#     standalone GoPay app.
#   - "driverapp", "driver-platforms", "driver-platform-android" all show
#     com.gojek.partner / com.gojek.driver.* packages and all three share
#     TestRail project 122 -- confirmed the same app (gojek-driver / GoPartner)
#     split across three repo modules (Cucumber-based + two older TestNG
#     suites), not three different apps.
#   - "gofood-merchant" (GoBiz) and "gopay-merchant" have NO UI automation in
#     this repo at all. A repo-wide search for "gobiz" turns up only
#     consumer/driver-side test HELPERS that call GoBiz's backend API to set
#     up merchant-side state for a consumer test (e.g. GoBizAPISteps.java) --
#     none of it is GoFood Merchant's own app UI. "gopaymerchant" /
#     "gopay-merchant" / "gopay.merchant" has zero occurrences of any kind.
#     Both are flagged as NO_COVERAGE rather than silently left unmapped.
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
        "note": "Standalone GoPay app, confirmed by exact android_package match (com.gojek.gopay). Its automation uses the gopaystaging:// scheme (iOS/staging-build convention), not the gopay:// scheme declared in gopay-consumer.json -- that config value may describe the production scheme, which the staging-build automation would not use directly; treat as a config/repo naming difference to confirm, not an error in either file.",
    },
    "gofood-merchant": {
        "modules": [],
        "note": "NO_COVERAGE: no GoFood Merchant (GoBiz) app UI automation exists in gojek-mobile-tests. The only 'gobiz' references are consumer/driver-side test helpers calling GoBiz's backend API, not merchant-app tests. A regression check for this app cannot use this repo/BrowserStack project as a source.",
    },
    "gopay-merchant": {
        "modules": [],
        "note": "NO_COVERAGE: zero occurrences of gopaymerchant/gopay-merchant/gopay.merchant anywhere in gojek-mobile-tests. A regression check for this app cannot use this repo/BrowserStack project as a source.",
    },
}


# driver-platforms and driver-platform-android share TestRail project 122
# with driverapp (confirmed: DP_PROJECT_ID=122 in both their own constants
# files) and were confirmed by a human reviewer to resolve to the SAME
# BrowserStack project ids as driverapp -- so all three get the identical
# per-case Lumos resolution, not three separate (and two of them null)
# entries.
DRIVERAPP_NOTE = {
    "browserstack_project": None,
    "resolution": "PER-CASE at runtime via lumosClient.getProjectIdFromTestCaseId(testCaseId), see driverapp/src/test/java/io/gojek/driverapptest/utils/UITestRailHelper.java",
    "static_fallback_pr_id": "PR-143",
    "note": "No single project id applies to all driverapp cases -- resolve per case_number via Lumos; PR-143 is only the hardcoded fallback when that lookup fails. Confirmed by human review to also apply to driver-platforms and driver-platform-android (same TestRail project 122, same BrowserStack project ids).",
}
DRIVER_APP_MODULES = ["driverapp", "driver-platforms", "driver-platform-android"]

# gopay's BrowserStack project id, confirmed by a human reviewer (its test
# cases are visibly filed under PR-173 in BrowserStack) -- not derivable by
# static analysis, since the repo only hardcodes a literal "PR-" string for
# transport (176) and driverapp's fallback (143).
KNOWN_BROWSERSTACK_PROJECTS = {
    "gopay": {"browserstack_project": "PR-173", "verified": "human-confirmed, seen live in BrowserStack"},
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
    """Repo-wide sweep for literal BrowserStack "PR-<digits>" strings, with file context."""
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


def main():
    repo_root, out_path = sys.argv[1], sys.argv[2]

    modules = {}
    for path, text in find_constants_files(repo_root):
        mod = module_of(repo_root, path)
        rel = os.path.relpath(path, repo_root)
        matched_any = False
        for m in ID_CONST_RE.finditer(text):
            if is_commented_out(text, m.start()):
                continue
            matched_any = True
            name, val = m.group(1), m.group(2)
            bucket = modules.setdefault(mod, {"testrail_ids": {}, "source_files": []})
            if rel not in bucket["source_files"]:
                bucket["source_files"].append(rel)
            if val:  # skip blanks like HOME_MOBILE_SUITE_ID = ""
                bucket["testrail_ids"][name] = val
            else:
                bucket["testrail_ids"].setdefault(name, None)

    pr_ids_found = find_pr_ids(repo_root)

    modules_covered_by_106 = set(CONSUMER_SUPER_APP["folders"].keys())
    separate_projects = {}

    # driverapp is handled unconditionally: it legitimately has zero
    # PROJECT_ID/SUITE_ID constants files (ids live per-feature in Cucumber
    # Examples tables instead), so it never appears in `modules` -- an
    # earlier version of this script only special-cased driverapp INSIDE
    # the `for mod, data in modules.items()` loop, which meant the special
    # case never actually ran and driverapp fell through to the generic
    # "no constants found" stub below, losing the Lumos-resolver note.
    # driver-platforms and driver-platform-android get the identical
    # treatment (see DRIVER_APP_MODULES docstring above).
    for mod in DRIVER_APP_MODULES:
        entry = dict(DRIVERAPP_NOTE)
        entry["testrail_ids"] = modules.get(mod, {}).get("testrail_ids", {})
        entry["source_files"] = modules.get(mod, {}).get("source_files", [])
        separate_projects[mod] = entry

    for mod, data in sorted(modules.items()):
        if mod in modules_covered_by_106 or mod in DRIVER_APP_MODULES or mod in INFRA_MODULES:
            continue
        entry = {
            "browserstack_project": None,
            "testrail_ids": data["testrail_ids"],
            "source_files": data["source_files"],
        }
        if mod in KNOWN_BROWSERSTACK_PROJECTS:
            entry.update(KNOWN_BROWSERSTACK_PROJECTS[mod])
        separate_projects[mod] = entry

    # gopay_later and any module with zero constants files still gets a stub,
    # so a lookup miss is visible rather than silently absent.
    all_top_dirs = [d for d in os.listdir(repo_root)
                     if os.path.isdir(os.path.join(repo_root, d))
                     and not d.startswith(".") and d not in INFRA_MODULES]
    for mod in all_top_dirs:
        if mod in modules_covered_by_106 or mod in separate_projects:
            continue
        separate_projects[mod] = {
            "browserstack_project": None,
            "testrail_ids": {},
            "source_files": [],
            "note": "no PROJECT_ID/SUITE_ID constants found in this module -- join by tag/title only",
        }

    out = {
        "_meta": {
            "generated_by": "extract_project_map.py",
            "generated_from_repo_sha": git_sha(repo_root),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "constants_files_found": sum(len(v["source_files"]) for v in modules.values()),
            "literal_PR_ids_found_repo_wide": pr_ids_found,
            "note": "consumer_super_app + its folder ids are a LIVE-VERIFIED fact from the BrowserStack MCP, not derived from this static scan -- see CONSUMER_SUPER_APP docstring for how/when it was verified. Everything under separate_projects is derived purely from this scan and needs BrowserStack-side confirmation (no listProjects MCP tool exists to auto-verify).",
        },
        "consumer_super_app": CONSUMER_SUPER_APP,
        "separate_projects": separate_projects,
        "app_id_to_modules": APP_ID_TO_MODULES,
    }

    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, sort_keys=False)

    unresolved = [m for m, v in separate_projects.items() if v.get("browserstack_project") is None and m not in DRIVER_APP_MODULES]
    print(f"Constants files found: {out['_meta']['constants_files_found']}")
    print(f"Literal PR- ids found repo-wide: {pr_ids_found}")
    print(f"Modules under the consumer super-app (PR-176): {len(CONSUMER_SUPER_APP['folders'])}")
    print(f"Separate-project modules: {len(separate_projects)}")
    print(f"  of which BrowserStack project id NOT yet confirmed: {len(unresolved)} -> {unresolved}")
    no_coverage = [a for a, v in APP_ID_TO_MODULES.items() if not v["modules"]]
    print(f"Canonical apps with NO test coverage in this repo: {no_coverage}")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
