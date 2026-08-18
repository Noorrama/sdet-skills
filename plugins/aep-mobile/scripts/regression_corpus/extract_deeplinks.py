#!/usr/bin/env python3
"""
Extract the deeplink dictionary from gojek-mobile-tests into deeplinks.json.

Scope rules (verified against the real repo before writing this):
  - Candidate files: filename contains "deeplink" (case-insensitive), extension
    .java / .yaml / .yml.
  - A .java candidate is a DICTIONARY (not a test class) iff it has zero
    `@Test(` occurrences. Verified on 8 known files: every real dictionary
    (DriverDeeplinks, GojekConsumerDeeplinks, GoFoodDeeplinks, ...) has 0;
    every real test class (GoCarDeepLinkTest, NewDeepLinksTest, ...) has >=1.
    Dictionaries live in both src/main and src/test (driverapp keeps its
    dictionary under src/test), so the split is NOT src/main vs src/test.
  - A .yaml/.yml candidate is only kept if it actually contains a gojek
    scheme string ("gojek://" or similar) -- this is a content check, not a
    filename check, because at least one *.json file matching "*deeplink*"
    by name (logistics Deeplinks.json) is unrelated test user-data, not a
    URL dictionary. The same content check is applied to .java files as a
    second gate after the @Test( gate.
  - Value normalisation: the repo contains at least one confirmed typo,
    "gojek:/gopay/friends" (single slash). Any value starting with a known
    scheme with a missing slash is corrected.
  - Bare prefixes (CONSUMER_ANDROID = "gojek://" with nothing after) are
    kept separately under "prefixes", not mixed into a module's screen list.

Run: python3 extract_deeplinks.py <repo_root> <output.json>
"""
import sys, os, re, json, subprocess, datetime

# Every app-facing URL scheme actually used in the repo, confirmed by a
# repo-wide `grep -rhoE '"[a-zA-Z]+://'` sweep (not just the obvious
# gojek/gojekstaging ones). An earlier version of this script only knew
# about the 4 consumer-app schemes and silently produced ZERO entries for
# driverapp -- its whole dictionary (DriverDeeplinks.java, 36+ entries) uses
# "gojekdriver://", which isn't a variant of "gojek://", it's a distinct
# scheme, and it fell through both the known-scheme check AND the bare-path-
# fragment fallback (that fallback's regex doesn't allow ":", so a string
# containing "://" can never accidentally match it either). The same sweep
# also found "gopartner://" (driverapp's current brand-name scheme) and
# "gopaystaging://" (gopay-consumer's own iOS scheme, distinct from the
# shared "gojekstaging://"). Excluded from this list on purpose: "bs://"
# (a BrowserStack build-path check, not a deeplink), and generic
# "http(s)://"/"media://"/"mongodb://" (infra protocols, not app deeplinks).
#
# Repeated the same sweep on gtf-mobile-tests (a second, separate repo --
# see --repo-key below) and found four more real schemes: "gopay://" (bare,
# never appears in gojek-mobile-tests but is literal here), "gopaystaging://"
# (shared name, different app), "gopaysandbox://" (this repo's other
# environment variant -- paired positionally with gopaystaging as the
# enum's 2nd constructor arg, so no special "staging in name" handling is
# needed for it), "gopaybackdoor://" (a real backdoor-login utility link),
# and "ktbs://" (a Kitabisa-donation partner deeplink, found only as an
# inline string in test-data/helper code, never in an actual dictionary
# file -- included for completeness in case that changes).
SCHEMES = ("gojek://", "gojekstaging://", "gojeksg://", "gojekstagingsg://",
           "gojekdriver://", "gopartner://", "gopaystaging://",
           "gopay://", "gopaysandbox://", "gopaybackdoor://", "ktbs://")
# Case variants of the same schemes are used inconsistently in places
# (confirmed: "GoJekDriver://", "GojekDriver://", "gojekdriver://" all occur).
# Classification below is done against v.lower() so any of these are
# recognised; the ORIGINAL casing is always preserved in stored values.
SCHEMES_LOWER = tuple(s.lower() for s in SCHEMES)
# Order matters: try the LONGEST scheme name first, so "gojekstaging:/x" is
# matched against the gojekstaging typo before the shorter "gojek" one could
# (wrongly) match a prefix of it. Each pattern requires the single slash to
# NOT be followed by another slash, so an already-correct "gojek://x" (which
# also starts with the literal substring "gojek:/") is never touched -- this
# was a real bug in an earlier version of this script (confirmed against the
# repo: it turned correct "gojek://gofood/..." into "gojek:///gofood/...").
TYPO_PATTERNS = [
    (re.compile(r'^gojekstagingsg:/(?!/)', re.I), "gojekstagingsg://"),
    (re.compile(r'^gojekstaging:/(?!/)', re.I), "gojekstaging://"),
    (re.compile(r'^gojeksg:/(?!/)', re.I), "gojeksg://"),
    (re.compile(r'^gojekdriver:/(?!/)', re.I), "gojekdriver://"),
    (re.compile(r'^gojek:/(?!/)', re.I), "gojek://"),
    (re.compile(r'^gopartner:/(?!/)', re.I), "gopartner://"),
    (re.compile(r'^gopaystaging:/(?!/)', re.I), "gopaystaging://"),
    (re.compile(r'^gopaysandbox:/(?!/)', re.I), "gopaysandbox://"),
    (re.compile(r'^gopaybackdoor:/(?!/)', re.I), "gopaybackdoor://"),
    (re.compile(r'^gopay:/(?!/)', re.I), "gopay://"),
]

CONST_RE = re.compile(r'static\s+final\s+String\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"([^"]*)"')
# enum member: NAME("val1"[, "val2"][, ...])   -- capture up to first 2 string args
ENUM_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*"([^"]*)"(?:\s*,\s*"([^"]*)")?')


def fix_typo(v: str) -> str:
    for pat, good in TYPO_PATTERNS:
        if pat.match(v):
            return pat.sub(good, v, count=1)
    return v


def looks_like_deeplink_value(v: str) -> bool:
    if not v or " " in v or len(v) > 400:
        return False
    if any(v.lower().startswith(s) for s in SCHEMES_LOWER) or any(pat.match(v) for pat, _ in TYPO_PATTERNS):
        return True
    # bare path fragment: no scheme, but slash-separated, no obvious non-url junk
    return bool(re.match(r'^[a-zA-Z0-9_\-/.?=&%]+$', v)) and "/" in v.strip("/")


def resolve_android_ios(raw: str):
    """Classify by scheme, case-insensitively, preserving original casing in
    the returned value. Any scheme with "staging" in its name is treated as
    the iOS variant (matches the repo's own convention: gojekstaging,
    gojekstagingsg, gopaystaging are all iOS-side); everything else is
    Android-side. A bare fragment (no scheme at all) is derived under both
    of the two primary consumer prefixes, same as before."""
    raw = fix_typo(raw)
    low = raw.lower()
    for scheme in SCHEMES_LOWER:
        if low.startswith(scheme):
            return (None, raw) if "staging" in scheme else (raw, None)
    # bare fragment -> derive both using the two primary consumer prefixes
    frag = raw.lstrip("/")
    return f"gojek://{frag}", f"gojekstaging://{frag}"


def is_bare_prefix(v: str) -> bool:
    v = fix_typo(v)
    return v.lower() in SCHEMES_LOWER


def find_candidate_files(repo_root: str):
    out = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        if "/.git" in dirpath or "/build/" in dirpath + "/" or dirpath.endswith("/build"):
            dirnames[:] = [d for d in dirnames if d != "build"]
            if "/.git" in dirpath:
                continue
        if ".git" in dirpath.split(os.sep):
            continue
        for fn in filenames:
            low = fn.lower()
            if "deeplink" not in low:
                continue
            if low.endswith(".java") or low.endswith(".yaml") or low.endswith(".yml"):
                out.append(os.path.join(dirpath, fn))
    return out


def module_of(repo_root: str, path: str) -> str:
    rel = os.path.relpath(path, repo_root)
    return rel.split(os.sep)[0]


def parse_java(path: str, text: str):
    """Return (prefixes: dict, entries: list[(name, raw, android, ios)])."""
    if text.count("@Test(") > 0:
        return {}, []  # a real test class, not a dictionary
    prefixes = {}
    entries = []
    for m in CONST_RE.finditer(text):
        name, val = m.group(1), m.group(2)
        val = fix_typo(val)
        if not looks_like_deeplink_value(val) and not is_bare_prefix(val):
            continue
        if is_bare_prefix(val):
            prefixes[name] = val
            continue
        android, ios = resolve_android_ios(val)
        entries.append((name, val, android, ios))
    for line in text.splitlines():
        m = ENUM_RE.match(line)
        if not m:
            continue
        name, v1, v2 = m.group(1), m.group(2), m.group(3)
        v1f = fix_typo(v1) if v1 else v1
        if v2:  # explicit (android, ios) pair
            v2f = fix_typo(v2)
            if looks_like_deeplink_value(v1f) or looks_like_deeplink_value(v2f):
                entries.append((name, v1f, v1f if looks_like_deeplink_value(v1f) else None,
                                 v2f if looks_like_deeplink_value(v2f) else None))
            continue
        if not v1f:
            continue
        if is_bare_prefix(v1f):
            prefixes[name] = v1f
            continue
        if looks_like_deeplink_value(v1f):
            android, ios = resolve_android_ios(v1f)
            entries.append((name, v1f, android, ios))
    return prefixes, entries


def parse_yaml_simple(text: str):
    """Minimal parser for the confirmed shape:
       Name:
         gojek:
           android: "..."
           ios: "..."
    No external yaml dependency -- indentation-based, matches only this shape.
    """
    entries = []
    lines = text.splitlines()
    cur_name = None
    cur_android = cur_ios = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0 and stripped.endswith(":"):
            if cur_name and (cur_android or cur_ios):
                entries.append((cur_name, cur_android or cur_ios, cur_android, cur_ios))
            cur_name = stripped[:-1]
            cur_android = cur_ios = None
        elif "android:" in stripped:
            mm = re.search(r'android:\s*"([^"]*)"', stripped)
            if mm and mm.group(1):
                cur_android = fix_typo(mm.group(1))
        elif "ios:" in stripped:
            mm = re.search(r'ios:\s*"([^"]*)"', stripped)
            if mm and mm.group(1):
                cur_ios = fix_typo(mm.group(1))
    if cur_name and (cur_android or cur_ios):
        entries.append((cur_name, cur_android or cur_ios, cur_android, cur_ios))
    return entries


def git_sha(repo_root: str):
    try:
        return subprocess.check_output(["git", "-C", repo_root, "rev-parse", "HEAD"],
                                        text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def main():
    # <repo_root> <repo_key> <output.json> -- repo_key namespaces this repo's
    # results under out["repos"][repo_key], merged into any existing file
    # rather than overwriting it, so running this for "gtf" never wipes out
    # "gmt"'s already-extracted data (and vice versa). This plugin now draws
    # on two separate automation repos (gojek-mobile-tests="gmt",
    # gtf-mobile-tests="gtf") with different module sets and different
    # deeplink-scheme families -- see SCHEMES above.
    repo_root, repo_key, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    files = find_candidate_files(repo_root)

    modules = {}
    repo_prefixes = {}
    files_scanned = 0
    files_contributed = 0
    files_skipped_no_scheme = []
    files_skipped_test_class = []

    for path in files:
        files_scanned += 1
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue

        # Content gate: does this file contain ANY recognised scheme at all?
        # An earlier version of this check hardcoded "gojek" specifically --
        # correct for gojek-mobile-tests, but it would have silently
        # rejected gtf-mobile-tests' entire deeplink dictionary, none of
        # which contains the substring "gojek" anywhere (its schemes are
        # gopay/gopaystaging/gopaysandbox/gopaybackdoor/ktbs).
        low = text.lower()
        if not any(s in low for s in SCHEMES_LOWER):
            files_skipped_no_scheme.append(os.path.relpath(path, repo_root))
            continue

        mod = module_of(repo_root, path)
        rel = os.path.relpath(path, repo_root)

        if path.lower().endswith(".java"):
            if text.count("@Test(") > 0:
                files_skipped_test_class.append(rel)
                continue
            prefixes, entries = parse_java(path, text)
        else:
            prefixes, entries = {}, parse_yaml_simple(text)

        if prefixes:
            repo_prefixes.update(prefixes)
        if entries:
            files_contributed += 1
            bucket = modules.setdefault(mod, {})
            for name, raw, android, ios in entries:
                rec = bucket.setdefault(name, {"raw": raw, "source_files": []})
                if android:
                    rec["android"] = android
                if ios:
                    rec["ios"] = ios
                if rel not in rec["source_files"]:
                    rec["source_files"].append(rel)

    total_entries = sum(len(v) for v in modules.values())

    out = {"_meta": {"repos": {}}, "repos": {}}
    if os.path.exists(out_path):
        try:
            out = json.load(open(out_path))
        except (json.JSONDecodeError, OSError):
            pass  # start fresh rather than fail on a corrupted prior file
    out.setdefault("_meta", {}).setdefault("repos", {})
    out.setdefault("repos", {})

    out["_meta"]["repos"][repo_key] = {
        "generated_by": "extract_deeplinks.py",
        "generated_from_repo_sha": git_sha(repo_root),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "files_scanned": files_scanned,
        "files_contributed": files_contributed,
        "files_skipped_no_scheme_found": len(files_skipped_no_scheme),
        "files_skipped_as_test_class": len(files_skipped_test_class),
        "total_entries": total_entries,
        "modules_covered": sorted(modules.keys()),
    }
    out["repos"][repo_key] = {
        "prefixes": dict(sorted(repo_prefixes.items())),
        "modules": {m: dict(sorted(v.items())) for m, v in sorted(modules.items())},
    }

    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, sort_keys=False)

    print(f"[{repo_key}] Scanned {files_scanned} candidate files.")
    print(f"  contributed entries from {files_contributed} files")
    print(f"  skipped (no recognised scheme found): {len(files_skipped_no_scheme)}")
    print(f"  skipped (real @Test( class, not a dictionary): {len(files_skipped_test_class)}")
    print(f"Total deeplink entries: {total_entries} across {len(modules)} modules")
    print(f"Wrote {out_path} (repos: {sorted(out['repos'].keys())})")
    if files_skipped_no_scheme:
        print("\nFiles matched 'deeplink' by name but skipped (no recognised scheme found) -- review manually:")
        for r in files_skipped_no_scheme:
            print(f"  - {r}")


if __name__ == "__main__":
    main()
