#!/usr/bin/env python3
"""
Extract a TapMind nav_index (per module) + project map from the
tapmind-mobile-tests repo.

Why a SECOND extractor (extract_nav_index.py already exists):
  - gojek-mobile-tests is GMT (Appium+TestNG) / Cucumber. Its navigation lives
    in deeplink literals + page-object METHOD NAMES, which extract_nav_index.py
    captures.
  - tapmind-mobile-tests is the TapMind NLP framework. Its steps live INSIDE the
    string arguments of runStep("...") plus a small set of setup helpers
    (login*/openDeeplink/set*Toggle/controlNetwork). extract_nav_index.py would
    capture the call NAMES (runStep, loginToDriver) and throw away the actual
    step text -- useless for authoring automation_steps. This extractor captures
    the ordered step SEQUENCE verbatim instead.

Join key: TapMind's @TestInfo(projectId=..., suiteId=..., testCaseIds={...})
carries the BrowserStack project/suite/case ids STATICALLY (unlike GMT's
per-case Lumos lookup). projectId/suiteId/countryName are usually constant
NAMES; we resolve them against `public static final String NAME = "VALUE"`
declarations found in the same module, and keep the raw name if unresolved.

The captured tapmind_steps[] is a best-effort, order-preserving heuristic over a
free-form Java method body -- stated in _meta so nobody treats it as a verified,
complete script.

Run: python3 extract_tapmind_nav_index.py <tapmind_repo_root> <config_root>
Writes: <config_root>/tapmind/nav_index/<module>.json  (one per module)
        <config_root>/tapmind/project_map.json          (module -> observed ids)
"""
import sys, os, re, json, subprocess, datetime, collections

ANNOT_START_RE = re.compile(r'@(TestInfo|GBTTestRail)\s*\(')
TESTCASEIDS_ARRAY_RE = re.compile(r'testCaseIds?\s*=\s*\{([^}]*)\}')
TESTCASEIDS_STRING_RE = re.compile(r'testCaseIds?\s*=\s*"([^"]*)"')
KV_RE = {
    "project_id": re.compile(r'projectId\s*=\s*([A-Za-z_][A-Za-z0-9_.]*|"[^"]*")'),
    "suite_id":   re.compile(r'suiteId\s*=\s*([A-Za-z_][A-Za-z0-9_.]*|"[^"]*")'),
    "country":    re.compile(r'countryName\s*=\s*([A-Za-z_][A-Za-z0-9_.]*|"[^"]*")'),
}
TEST_DESC_RE = re.compile(r'@Test\([^)]*?description\s*=\s*"([^"]*)"', re.DOTALL)
METHOD_SIG_RE = re.compile(
    r'(?:public|private|protected)?\s*(?:static\s+)?void\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?:throws\s+[A-Za-z0-9_.,\s]+)?\{'
)
CONST_RE = re.compile(r'static\s+final\s+String\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"([^"]*)"')

# a call is "of interest" when its name is one of these or matches a pattern
CALL_NAME_RE = re.compile(r'(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\s*\(')
INTEREST_EXACT = {"runStep", "openDeeplink", "controlNetwork"}
def is_interesting_call(name: str) -> bool:
    if name in INTEREST_EXACT:
        return True
    low = name.lower()
    if "login" in low:                      # loginToDriver, loginWithRegisteredMerchant, ...
        return True
    if name.startswith("set") and name.endswith("Toggle"):  # setDriverToggle, ...
        return True
    return False


def is_commented_out(text: str, pos: int) -> bool:
    line_start = text.rfind("\n", 0, pos) + 1
    return text[line_start:pos].lstrip().startswith("//")


def find_close(text: str, open_idx: int, opench: str, closech: str, cap=40000) -> int:
    depth = 1
    i = open_idx + 1
    n = min(len(text), open_idx + cap)
    while i < n and depth > 0:
        c = text[i]
        if c == opench:
            depth += 1
        elif c == closech:
            depth -= 1
        i += 1
    return i - 1


def split_case_ids(annot: str):
    m = TESTCASEIDS_ARRAY_RE.search(annot)
    if m:
        return [x.strip().strip('"').strip() for x in m.group(1).split(",") if x.strip().strip('"').strip()]
    m = TESTCASEIDS_STRING_RE.search(annot)
    if m:
        raw = m.group(1)
        if "||" in raw:
            return [x.strip() for x in raw.split("||") if x.strip()]
        return [raw.strip()] if raw.strip() else []
    return []


def resolve(tok: str, consts: dict):
    """A projectId/suiteId/country token is a "literal", a CONST name, or a
    dotted ClassName.CONST reference -- resolve the last segment against the
    module constant map; keep the raw token if unresolved."""
    if tok is None:
        return None
    if tok.startswith('"') and tok.endswith('"'):
        return tok[1:-1]
    if tok in consts:
        return consts[tok]
    if "." in tok:                       # DriverProjectConfig.MARKETPLACE_DRIVER_PLATFORM
        last = tok.rsplit(".", 1)[-1]
        if last in consts:
            return consts[last]
    return tok  # unresolved -> keep the name so it is visible, not silently dropped


def clean_arg(raw: str) -> str:
    """Light clean of a call's raw argument text into a readable step line."""
    s = raw.strip()
    # collapse Java string concat: "a" + var + "b"  ->  a<var>b-ish, keep readable
    s = re.sub(r'"\s*\+\s*', "", s)
    s = re.sub(r'\s*\+\s*"', "", s)
    s = s.replace('\\"', '"')
    s = s.strip().strip(",").strip()
    # unwrap a single fully-quoted literal
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    return s.strip()


def extract_steps(body: str):
    """Ordered list of {kind, text} for every interesting call in the body."""
    steps = []
    for m in CALL_NAME_RE.finditer(body):
        name = m.group(1)
        if not is_interesting_call(name):
            continue
        open_paren = m.end() - 1
        close = find_close(body, open_paren, "(", ")")
        arg = clean_arg(body[open_paren + 1:close])
        if name == "runStep":
            steps.append({"kind": "nlp", "text": arg})
        elif name == "openDeeplink":
            steps.append({"kind": "deeplink", "text": arg})
        elif name == "controlNetwork":
            steps.append({"kind": "network", "text": arg})
        elif "login" in name.lower():
            steps.append({"kind": "login", "text": f"{name}({arg})" if arg else f"{name}()"})
        else:  # toggle
            steps.append({"kind": "toggle", "text": f"{name}({arg})"})
    return steps


def module_constants(files):
    consts = {}
    for p in files:
        try:
            t = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for cm in CONST_RE.finditer(t):
            consts.setdefault(cm.group(1), cm.group(2))
    return consts


def process_file(path, rel, mod, consts, index, module_ids, stats):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return
    for am in ANNOT_START_RE.finditer(text):
        if is_commented_out(text, am.start()):
            stats["skipped_commented"] += 1
            continue
        open_paren = am.end() - 1
        close_paren = find_close(text, open_paren, "(", ")")
        annot = text[am.start():close_paren + 1]
        case_ids = split_case_ids(annot)
        if not case_ids:
            stats["no_case_ids"] += 1
            continue
        def kv(key):
            m = KV_RE[key].search(annot)
            return resolve(m.group(1), consts) if m else None
        project_id = kv("project_id")
        suite_id = kv("suite_id")
        country = kv("country")
        if project_id:
            module_ids[mod]["project_ids"].add(project_id)
        if suite_id:
            module_ids[mod]["suite_ids"].add(suite_id)

        tail = text[close_paren:close_paren + 2000]
        dm = TEST_DESC_RE.search(tail)
        title = dm.group(1) if dm else None
        sm = METHOD_SIG_RE.search(text, close_paren)
        method_name, steps = None, []
        if sm:
            method_name = sm.group(1)
            brace = sm.end() - 1
            body = text[brace:find_close(text, brace, "{", "}")]
            steps = extract_steps(body)

        for cid in case_ids:
            index.setdefault(cid, []).append({
                "module": mod,
                "title": title,
                "method": method_name,
                "source_file": rel,
                "project_id": project_id,
                "suite_id": suite_id,
                "country": country,
                "tapmind_steps": steps,
                "framework": "TAPMIND_NLP",
            })
            stats["case_ids_found"] += 1


def git_sha(root):
    try:
        return subprocess.check_output(["git", "-C", root, "rev-parse", "HEAD"],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def main():
    repo_root, config_root = sys.argv[1], sys.argv[2]
    nav_dir = os.path.join(config_root, "tapmind", "nav_index")
    os.makedirs(nav_dir, exist_ok=True)

    # test java files per module (for @TestInfo extraction) + all java files per
    # module (for constant resolution -- project/suite id constants often live
    # in src/main, not src/test).
    files_by_mod = collections.defaultdict(list)        # test files only
    const_files_by_mod = collections.defaultdict(list)  # all java files
    for dirpath, dirnames, filenames in os.walk(repo_root):
        parts = dirpath.split(os.sep)
        if ".git" in parts or "build" in parts:
            continue
        for fn in filenames:
            if not fn.endswith(".java"):
                continue
            p = os.path.join(dirpath, fn)
            mod = os.path.relpath(p, repo_root).split(os.sep)[0]
            const_files_by_mod[mod].append(p)
            if f"src{os.sep}test" in dirpath:
                files_by_mod[mod].append(p)

    per_module_index = collections.defaultdict(dict)
    module_ids = collections.defaultdict(lambda: {"project_ids": set(), "suite_ids": set()})
    stats = collections.Counter()

    global_consts = module_constants([p for fs in const_files_by_mod.values() for p in fs])

    for mod, files in files_by_mod.items():
        consts = {**global_consts, **module_constants(const_files_by_mod[mod])}  # module-local wins
        for p in files:
            rel = os.path.relpath(p, repo_root)
            process_file(p, rel, mod, consts, per_module_index[mod], module_ids, stats)

    sha = git_sha(repo_root)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    written = 0
    for mod, index in sorted(per_module_index.items()):
        if not index:
            continue
        out = {
            "_meta": {
                "generated_by": "extract_tapmind_nav_index.py",
                "source_repo": "tapmind-mobile-tests",
                "generated_from_repo_sha": sha,
                "generated_at": now,
                "module": mod,
                "case_ids_indexed": len(index),
                "warning": "tapmind_steps is a best-effort, order-preserving capture of runStep()/openDeeplink()/login*/toggle/controlNetwork calls from a free-form Java method body -- NOT a verified, complete script. project_id/suite_id resolved from module constants where possible.",
            },
            "cases": index,
        }
        with open(os.path.join(nav_dir, f"{mod}.json"), "w") as f:
            json.dump(out, f, indent=2, sort_keys=False)
        written += 1

    project_map = {
        "_meta": {
            "generated_by": "extract_tapmind_nav_index.py",
            "source_repo": "tapmind-mobile-tests",
            "generated_from_repo_sha": sha,
            "generated_at": now,
            "note": "Observed @TestInfo projectId/suiteId values per module, resolved from module constants. project_id N is TapMind's BrowserStack project id; verify against BrowserStack PR-<N> before treating as authoritative. This is a SUPERSET source: TapMind covers merchant apps (gopaymerchant, gofoodmerchantapp) that gojek-mobile-tests does not.",
        },
        "modules": {
            mod: {
                "project_ids": sorted(v["project_ids"]),
                "suite_ids": sorted(v["suite_ids"]),
            }
            for mod, v in sorted(module_ids.items()) if v["project_ids"] or v["suite_ids"]
        },
    }
    with open(os.path.join(config_root, "tapmind", "project_map.json"), "w") as f:
        json.dump(project_map, f, indent=2, sort_keys=False)

    print(f"Modules with tests: {len(files_by_mod)}")
    print(f"Commented @TestInfo skipped: {stats['skipped_commented']}")
    print(f"Annotations with no case ids: {stats['no_case_ids']}")
    print(f"case-id entries indexed: {stats['case_ids_found']}")
    print(f"nav_index module files written: {written}")
    print(f"project_map modules: {len(project_map['modules'])}")


if __name__ == "__main__":
    main()
