#!/usr/bin/env python3
"""
Extract nav_index.json (per module): case_number -> navigation facts, used to
backfill weak/empty human-written BrowserStack steps.

Two source formats, both verified against the real repo before writing this:

TestNG (@TestInfo / @GBTTestRail):
  - testCaseIds has THREE distinct value shapes in this codebase, all handled:
      1. array:       testCaseIds = {"4528335","4528337"}          (2375 occurrences)
      2. double-pipe:  testCaseIds = "1293424||617014"              (367 occurrences)
      3. bare single:  testCaseIds = "2708336"                      (827 occurrences)
    (Cucumber uses a fourth shape -- comma-separated -- see below.)
  - @TestInfo/@GBTTestRail can be commented out (`//    @TestInfo(...)`,
    confirmed real in transport/.../BookingCancelNotificationsTest.java) --
    these are SKIPPED, not extracted, or the nav_index would offer dead
    test ids as if they were live.
  - The annotation is matched with a balanced-paren scanner, not a naive
    `[^)]*` regex, so a value containing a nested `(` cannot truncate the
    match early.
  - "Navigation" extracted from the method body is a best-effort HEURISTIC,
    not a guaranteed-complete reconstruction: it captures (a) any deeplink
    literal used in the body, (b) any reference to a *Deeplink(s) enum
    member (e.g. GopayDeeplinks.ScanQR), and (c) the first N distinct
    page-object method calls in the body, in order. Free-form Java method
    bodies are not structured data -- this is stated explicitly in the
    output so nobody mistakes it for a guaranteed-complete step list.

Cucumber (.feature):
  - Only features with a "Testcase Id" column in an Examples table are
    indexable by case_number. Confirmed: 93/98 driverapp features have it;
    5 driverapp features and all 47 gofood features do not (gofood routes
    by Gherkin tag only) -- those are reported as NOT INDEXABLE, not
    silently skipped.
  - An Examples cell can hold multiple comma-separated ids
    (e.g. "3054639,3054650") -- each becomes its own nav_index key, all
    pointing at the same Background + Scenario steps.
  - Steps = Background: (applies file-wide) + the owning Scenario Outline's
    own Given/When/Then/And lines, verbatim including <placeholder> tokens.

Run: python3 extract_nav_index.py <repo_root> <output_dir>
Writes one file per module: <output_dir>/<module>.json
"""
import sys, os, re, json, subprocess, datetime, collections

DEEPLINK_LITERAL_RE = re.compile(r'gojek(?:staging)?(?:sg)?://[A-Za-z0-9_\-/.?=&%]*')
DEEPLINK_ENUM_RE = re.compile(r'\b([A-Z][A-Za-z0-9]*Deeplinks?)\.([A-Za-z_][A-Za-z0-9_]*)')
METHOD_CALL_RE = re.compile(r'\.([a-z][A-Za-z0-9_]*)\s*\(')
NOISE_METHODS = {
    "get", "equals", "hashCode", "toString", "println", "print", "format",
    "assertTrue", "assertFalse", "assertEquals", "assertNotNull", "assertNull",
    "of", "valueOf", "builder", "build", "add", "put", "size", "isEmpty",
    "getClass", "iterator", "stream", "collect", "trim", "split", "contains",
}

ANNOT_START_RE = re.compile(r'@(TestInfo|GBTTestRail)\s*\(')
TESTCASEIDS_ARRAY_RE = re.compile(r'testCaseIds?\s*=\s*\{([^}]*)\}')
TESTCASEIDS_STRING_RE = re.compile(r'testCaseIds?\s*=\s*"([^"]*)"')
TEST_DESC_RE = re.compile(r'@Test\([^)]*?description\s*=\s*"([^"]*)"', re.DOTALL)
METHOD_SIG_RE = re.compile(
    r'(?:public|private|protected)?\s*(?:static\s+)?void\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?:throws\s+[A-Za-z0-9_.,\s]+)?\{'
)


def is_commented_out(text: str, pos: int) -> bool:
    line_start = text.rfind("\n", 0, pos) + 1
    line_end = text.find("\n", pos)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].lstrip().startswith("//")


def find_matching_close_paren(text: str, open_paren_idx: int) -> int:
    """open_paren_idx points AT the '(' immediately after @TestInfo/@GBTTestRail."""
    depth = 1
    i = open_paren_idx + 1
    n = len(text)
    while i < n and depth > 0:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        i += 1
    return i - 1  # index of the matching ')'


def find_matching_close_brace(text: str, open_brace_idx: int, max_scan: int = 20000) -> int:
    depth = 1
    i = open_brace_idx + 1
    n = min(len(text), open_brace_idx + max_scan)
    while i < n and depth > 0:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return i - 1


def split_case_ids(annotation_text: str):
    """Return a list of case_number strings from a testCaseIds= value in any
    of the three confirmed shapes (array / double-pipe string / bare string)."""
    m = TESTCASEIDS_ARRAY_RE.search(annotation_text)
    if m:
        return [x.strip().strip('"').strip() for x in m.group(1).split(",") if x.strip().strip('"').strip()]
    m = TESTCASEIDS_STRING_RE.search(annotation_text)
    if m:
        raw = m.group(1)
        if "||" in raw:
            return [x.strip() for x in raw.split("||") if x.strip()]
        return [raw.strip()] if raw.strip() else []
    return []


def extract_body_facts(body: str, cap_calls: int = 15):
    deeplinks = sorted(set(DEEPLINK_LITERAL_RE.findall(body)))
    enum_refs = sorted(set(f"{cls}.{member}" for cls, member in DEEPLINK_ENUM_RE.findall(body)))
    calls = []
    seen = set()
    for m in METHOD_CALL_RE.finditer(body):
        name = m.group(1)
        if name in NOISE_METHODS or name in seen:
            continue
        seen.add(name)
        calls.append(name)
        if len(calls) >= cap_calls:
            break
    return deeplinks, enum_refs, calls


def process_testng_file(path: str, rel: str, mod: str, index: dict, stats: dict):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return

    for am in ANNOT_START_RE.finditer(text):
        annot_kind = am.group(1)
        if is_commented_out(text, am.start()):
            stats["skipped_commented_annotations"] += 1
            continue
        open_paren = am.end() - 1
        close_paren = find_matching_close_paren(text, open_paren)
        annot_text = text[am.start():close_paren + 1]

        case_ids = split_case_ids(annot_text)
        if not case_ids:
            stats["annotations_with_no_case_ids"] += 1
            continue

        # description: prefer the @Test(...) that follows this annotation
        tail = text[close_paren:close_paren + 2000]
        desc_m = TEST_DESC_RE.search(tail)
        title = desc_m.group(1) if desc_m else None

        sig_m = METHOD_SIG_RE.search(text, close_paren)
        deeplinks, enum_refs, calls = [], [], []
        method_name = None
        if sig_m:
            method_name = sig_m.group(1)
            brace_idx = sig_m.end() - 1
            body_end = find_matching_close_brace(text, brace_idx)
            body = text[brace_idx:body_end]
            deeplinks, enum_refs, calls = extract_body_facts(body)

        for cid in case_ids:
            record = {
                "module": mod,
                "title": title,
                "method": method_name,
                "source_file": rel,
                "annotation": annot_kind,
                "deeplinks_literal": deeplinks,
                "deeplinks_enum_ref": enum_refs,
                "page_object_calls_heuristic": calls,
                "framework": "GMT_JAVA",
            }
            index.setdefault(cid, []).append(record)
            stats["testng_case_ids_found"] += 1


def process_feature_file(path: str, rel: str, mod: str, index: dict, stats: dict, not_indexable: list):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return

    lines = text.splitlines()
    background_steps = []
    in_background = False
    scenarios = []  # list of dicts: {title, steps[], examples_header, examples_rows[]}
    cur = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Background:"):
            in_background = True
            continue
        if stripped.startswith("Scenario Outline:") or stripped.startswith("Scenario:"):
            in_background = False
            cur = {"title": stripped.split(":", 1)[1].strip(), "steps": [], "examples_header": None, "examples_rows": []}
            scenarios.append(cur)
            continue
        if stripped.startswith(("Given ", "When ", "Then ", "And ", "But ")):
            if in_background:
                background_steps.append(stripped)
            elif cur is not None:
                cur["steps"].append(stripped)
            continue
        if stripped.startswith("Examples:"):
            # A Scenario Outline can have MANY Examples: blocks (confirmed:
            # one real file has 11 in a row). Each block has its OWN header
            # row. An earlier version of this parser only reset the header
            # once per SCENARIO, not per BLOCK -- so every Examples table
            # after the first had its header row fed in as if it were a
            # DATA row, producing a fake case "Testcase Id" (the literal
            # column label) that collided across every affected scenario in
            # the module and accumulated hundreds of unrelated records under
            # one bogus key. Resetting here, per block, is the fix.
            if cur is not None:
                cur["examples_header"] = None
            continue
        if stripped.startswith("|") and cur is not None:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if cur["examples_header"] is None:
                if any("Testcase" in c or "Project" in c for c in cells):
                    cur["examples_header"] = cells
                # else: a header-less/unexpected block -- skip until we see
                # a recognisable header, rather than guessing column order.
                continue
            # Defensive check: a genuine data row's case-id cell should look
            # like digits/commas, never repeat the column label itself. This
            # catches any further block-boundary mis-detection even if the
            # structural fix above has a gap this script's author didn't see.
            tc_idx_guess = next((i for i, h in enumerate(cur["examples_header"]) if "testcase" in h.lower()), None)
            if tc_idx_guess is not None and tc_idx_guess < len(cells):
                cell_val = cells[tc_idx_guess]
                if cell_val and not re.match(r'^[0-9,\s]+$', cell_val):
                    stats["cucumber_rows_rejected_bad_case_id_cell"] += 1
                    continue
            cur["examples_rows"].append(cells)
            continue

    file_had_ids = False
    for sc in scenarios:
        header = sc["examples_header"]
        if not header:
            continue
        try:
            tc_idx = next(i for i, h in enumerate(header) if "testcase" in h.lower())
        except StopIteration:
            continue
        file_had_ids = True
        full_steps = list(background_steps) + list(sc["steps"])
        for row in sc["examples_rows"]:
            if tc_idx >= len(row):
                continue
            raw_ids = row[tc_idx]
            for cid in [x.strip() for x in raw_ids.split(",") if x.strip()]:
                record = {
                    "module": mod,
                    "title": sc["title"],
                    "source_file": rel,
                    "steps_gherkin": full_steps,
                    "framework": "CUCUMBER",
                }
                index.setdefault(cid, []).append(record)
                stats["cucumber_case_ids_found"] += 1

    if not file_had_ids:
        not_indexable.append(rel)


def git_sha(repo_root: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", repo_root, "rev-parse", "HEAD"],
                                        text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def main():
    repo_root, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)

    per_module_index = collections.defaultdict(dict)
    stats = collections.Counter()
    not_indexable_features = []

    for dirpath, dirnames, filenames in os.walk(repo_root):
        if ".git" in dirpath.split(os.sep) or "build" in dirpath.split(os.sep):
            continue
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, repo_root)
            mod = rel.split(os.sep)[0]
            if fn.endswith(".java"):
                stats["java_files_scanned"] += 1
                process_testng_file(path, rel, mod, per_module_index[mod], stats)
            elif fn.endswith(".feature"):
                stats["feature_files_scanned"] += 1
                process_feature_file(path, rel, mod, per_module_index[mod], stats, not_indexable_features)

    sha = git_sha(repo_root)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    total_case_ids = 0
    files_written = []
    for mod, index in sorted(per_module_index.items()):
        if not index:
            continue
        out = {
            "_meta": {
                "generated_by": "extract_nav_index.py",
                "generated_from_repo_sha": sha,
                "generated_at": now,
                "module": mod,
                "case_ids_indexed": len(index),
                "warning": "deeplinks_literal / deeplinks_enum_ref / case ids are exact regex extractions. page_object_calls_heuristic and steps_gherkin are best-effort navigation aids, NOT a guaranteed-complete or verified-correct step list -- method bodies and Gherkin text are free-form, unlike the structured id/deeplink data.",
            },
            "cases": index,
        }
        path = os.path.join(out_dir, f"{mod}.json")
        with open(path, "w") as f:
            json.dump(out, f, indent=2, sort_keys=False)
        files_written.append(path)
        total_case_ids += len(index)

    print(f"Java files scanned: {stats['java_files_scanned']}")
    print(f"Feature files scanned: {stats['feature_files_scanned']}")
    print(f"Commented-out @TestInfo/@GBTTestRail skipped: {stats['skipped_commented_annotations']}")
    print(f"Annotations with no parseable testCaseIds: {stats['annotations_with_no_case_ids']}")
    print(f"TestNG case-id entries indexed: {stats['testng_case_ids_found']}")
    print(f"Cucumber case-id entries indexed: {stats['cucumber_case_ids_found']}")
    print(f"Total distinct (module, case_number) keys: {total_case_ids}")
    print(f"Feature files with NO Testcase Id column (not indexable by case_number): {len(not_indexable_features)}")
    print(f"Wrote {len(files_written)} module files to {out_dir}")


if __name__ == "__main__":
    main()
