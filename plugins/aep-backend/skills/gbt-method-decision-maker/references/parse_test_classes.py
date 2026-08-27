#!/usr/bin/env python3
"""Parse GBT test / assertion / data-provider classes into a structural summary.

Emits the `method_summaries`, `assertion_summaries` and `data_provider_summaries`
blocks of method_decisions.json so `gbt-method-decision-maker` never has to count
data-provider columns by eye. Judgement (which method a scenario belongs to) stays
with the model; this script only does the mechanical parsing.

stdlib only, by design: javalang does not accept Java 17 (records, sealed types,
switch expressions, text blocks), all of which appear in gojek-backend-tests.
Parsing is regex + brace matching over a comment-and-string-masked copy of the
source, which is why `--repo` files are read but never rewritten.

Usage
-----
  python3 parse_test_classes.py --plan automation_plan_enriched.json --repo .gbt_repo
  python3 parse_test_classes.py --files A.java B.java --repo .gbt_repo

Exit codes: 0 ok (including partial), 2 bad invocation, 3 nothing parseable.
Never exits non-zero merely because a row list could not be parsed — that case is
reported as `rows_parsed: false` so the caller can reject deliberately.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# ── masking ────────────────────────────────────────────────────────────────────
# A copy of the source with comments and string/char literals replaced by spaces
# (length-preserving, so every offset stays valid against the original).


def mask(src: str) -> str:
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        two = src[i:i + 2]
        if two == "//":
            j = src.find("\n", i)
            j = n if j == -1 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif two == "/*":
            j = src.find("*/", i + 2)
            j = n if j == -1 else j + 2
            for k in range(i, j):
                out[k] = " "
            i = j
        elif src[i:i + 3] == '"""':                      # Java 17 text block
            j = src.find('"""', i + 3)
            j = n if j == -1 else j + 3
            for k in range(i, j):
                out[k] = " "
            i = j
        elif c in '"\'':
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == c:
                    j += 1
                    break
                if src[j] == "\n":                        # unterminated; bail out
                    break
                j += 1
            for k in range(i, min(j, n)):
                out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


def match_block(masked: str, open_idx: int) -> Optional[int]:
    """Index just past the `}` closing the `{` at open_idx, or None."""
    depth = 0
    for i in range(open_idx, len(masked)):
        if masked[i] == "{":
            depth += 1
        elif masked[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def split_top(text: str, sep: str) -> List[str]:
    """Split on `sep` only at nesting depth 0 (respects (), {}, [], <>)."""
    parts, buf, depth = [], [], 0
    pairs = {"(": ")", "{": "}", "[": "]", "<": ">"}
    closers = set(pairs.values())
    for ch in text:
        if ch in pairs:
            depth += 1
        elif ch in closers:
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts]


def split_top_spans(masked: str, sep: str) -> List[Tuple[int, int]]:
    """Depth-0 split points as (start, end) spans into `masked`.

    Structure is decided on the masked copy; the caller slices the ORIGINAL with
    these spans. Mixing the two (splitting original text on masked offsets) is
    what makes a comma inside a `//` comment look like a row separator.
    """
    spans, depth, start = [], 0, 0
    pairs = {"(": ")", "{": "}", "[": "]", "<": ">"}
    closers = set(pairs.values())
    for i, ch in enumerate(masked):
        if ch in pairs:
            depth += 1
        elif ch in closers:
            depth = max(0, depth - 1)
        elif ch == sep and depth == 0:
            spans.append((start, i))
            start = i + 1
    spans.append((start, len(masked)))
    return spans


# ── annotations & members ─────────────────────────────────────────────────────

# signature: modifiers, optional generic return, name, (params)
# Method discovery is a linear scan, not a regex.
#
# The obvious signature regex — modifiers, then a lazy return type, then
# `name(params) {` — makes whitespace matchable by two adjacent quantifiers
# (`(?:…|\s)+` and `([…\s]+?)`). Every position that is not a method then
# backtracks exponentially, and parsing a few hundred GBT classes goes from
# under a second to minutes. Scanning for `(` … `)` … `{` and reading backwards
# for the name is unambiguous and linear.
NOT_A_METHOD = {"if", "while", "for", "switch", "catch", "synchronized", "return",
                "new", "try", "do", "else", "assert", "throw", "super", "this",
                "record", "yield"}
IDENT_CHARS = set("_$")
TYPE_CHARS = set("_$.<>[],?")
MODIFIERS = {"public", "protected", "private", "static", "final", "synchronized",
             "abstract", "native", "default", "strictfp", "transient", "volatile"}


def word_before(masked: str, idx: int) -> Optional[Tuple[int, str]]:
    """`(start, word)` of the identifier ending just before `idx`, else None."""
    j = idx - 1
    while j >= 0 and masked[j] in " \t\r\n":
        j -= 1
    end = j + 1
    while j >= 0 and (masked[j].isalnum() or masked[j] in IDENT_CHARS):
        j -= 1
    if end <= j + 1:
        return None
    return j + 1, masked[j + 1:end]


def anno_args(raw: Optional[str]) -> Dict[str, str]:
    """`(groups = {A,B}, description = "x")` -> {'groups': '{A,B}', ...}.

    A single unnamed argument is returned under the key `_value`.
    """
    if not raw:
        return {}
    inner = raw.strip()[1:-1].strip()
    if not inner:
        return {}
    out: Dict[str, str] = {}
    for part in split_top(inner, ","):
        if "=" in part and re.match(r"^\s*\w+\s*=", part):
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
        else:
            out.setdefault("_value", part)
    return out


def unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def brace_list(v: str) -> List[str]:
    v = v.strip()
    if v.startswith("{") and v.endswith("}"):
        v = v[1:-1]
    return [unquote(x) for x in split_top(v, ",") if x.strip()]


def at_name_before(masked: str, k: int) -> Optional[Tuple[int, str]]:
    """`(index_of_@, name)` for an `@Name` ending just before `k`, else None.

    Deliberately a bounded backward scan rather than an anchored regex over
    `masked[:k]` — that form both copies and rescans the whole prefix for every
    annotation on every method, which turns this file into an O(n^2) parser and
    takes minutes on a few hundred classes instead of a second.
    """
    j = k - 1
    while j >= 0 and masked[j] in " \t\r\n":
        j -= 1
    end = j + 1
    while j >= 0 and (masked[j].isalnum() or masked[j] == "_"):
        j -= 1
    if j >= 0 and masked[j] == "@" and end > j + 1:
        return j, masked[j + 1:end]
    return None


def preceding_annotations(src: str, masked: str, sig_start: int) -> Dict[str, Optional[str]]:
    """Annotations directly above a signature, walked backwards.

    Scanning back to the nearest `}`/`;` does not work: TestNG annotations contain
    braces themselves (`groups = {X}`, `testCaseIds = {"1"}`), so that heuristic
    cuts the annotation block in half and loses `@Test` entirely. Instead, step
    back over one balanced `(...)` at a time and require an `@name` in front of it.
    """
    annos: Dict[str, Optional[str]] = {}
    i = sig_start
    while True:
        j = i - 1
        while j >= 0 and masked[j] in " \t\r\n":
            j -= 1
        if j < 0:
            break
        if masked[j] == ")":
            depth, k = 0, j
            while k >= 0:
                if masked[k] == ")":
                    depth += 1
                elif masked[k] == "(":
                    depth -= 1
                    if depth == 0:
                        break
                k -= 1
            if k < 0:
                break
            head = at_name_before(masked, k)
            if not head:
                break
            annos.setdefault(head[1], src[k:j + 1])
            i = head[0]
        elif masked[j].isalnum() or masked[j] == "_":
            head = at_name_before(masked, j + 1)
            if not head:
                break
            annos.setdefault(head[1], None)
            i = head[0]
        else:
            break
    return annos


def members(src: str, masked: str) -> List[Dict[str, Any]]:
    """Every method with a body: its annotations, params, and body text."""
    found: List[Dict[str, Any]] = []
    n = len(masked)
    pos = 0
    while True:
        p = masked.find("(", pos)
        if p == -1:
            break
        pos = p + 1
        # 1. balanced close paren
        depth, q = 0, p
        while q < n:
            if masked[q] == "(":
                depth += 1
            elif masked[q] == ")":
                depth -= 1
                if depth == 0:
                    break
            q += 1
        if q >= n:
            continue
        # 2. optional `throws …`, then the body brace
        r = q + 1
        while r < n and masked[r] in " \t\r\n":
            r += 1
        if masked.startswith("throws", r):
            r += 6
            while r < n and masked[r] not in "{;":
                r += 1
        if r >= n or masked[r] != "{":
            continue
        # 3. method name, read backwards from the open paren
        j = p - 1
        while j >= 0 and masked[j] in " \t\r\n":
            j -= 1
        name_end = j + 1
        while j >= 0 and (masked[j].isalnum() or masked[j] in IDENT_CHARS):
            j -= 1
        name = masked[j + 1:name_end]
        if not name or name in NOT_A_METHOD or not (name[0].isalpha() or name[0] in IDENT_CHARS):
            continue
        # 4. a return type must precede it (this is what rejects `new Foo() {`,
        #    control statements, and anonymous-class bodies)
        k = j
        while k >= 0 and masked[k] in " \t\r\n":
            k -= 1
        type_end = k + 1
        while k >= 0 and (masked[k].isalnum() or masked[k] in TYPE_CHARS):
            k -= 1
        rtype = masked[k + 1:type_end].strip()
        if not rtype or rtype in NOT_A_METHOD:
            continue
        end = match_block(masked, r)
        if end is None:
            continue
        # 5. step back over `public static final …` so the annotation walk starts
        #    above the modifiers rather than colliding with them
        sig_start = k + 1
        while True:
            w = word_before(masked, sig_start)
            if w and w[1] in MODIFIERS:
                sig_start = w[0]
            else:
                break
        found.append({
            "name": name,
            "return_type": rtype,
            "params": [x for x in split_top(masked[p + 1:q], ",") if x],
            "annotations": preceding_annotations(src, masked, sig_start),
            "body": src[r:end],
        })
        pos = end          # skip the body; nested calls are not members
    return found


def param_names(params: List[str]) -> List[str]:
    out = []
    for p in params:
        toks = p.replace("...", " ").split()
        if toks:
            out.append(toks[-1])
    return out


# ── body analysis ─────────────────────────────────────────────────────────────

# GBT asserts through `import static` far more often than through a receiver:
# `assertEquals(a, b, "msg")` and `verifyXResponse(res)` are the norm, not
# `Assert.assertEquals(...)`. A receiver-only regex reads a fully-asserted method
# as assertion-free and hands back a spurious no_match, so both forms are matched
# and bare names are resolved against the file's static imports.
CALL = re.compile(r"\b(?:(\w+)\s*\.\s*)?((?:assert|verify|fail|expect)\w*)\s*\(")
FLOW_CALL = re.compile(r"\b(\w*(?:Controller|Client|Helper|DbClient|Manager))\s*\.\s*(\w+)\s*\(")
STATIC_IMP = re.compile(r"import\s+static\s+([\w.]+(?:\.\*)?)\s*;")


def static_imports(src: str) -> Tuple[Dict[str, str], List[str]]:
    """`import static a.b.FooAssertions.verifyX;` -> ({'verifyX': 'FooAssertions'}, [])."""
    exact: Dict[str, str] = {}
    wildcard: List[str] = []
    for m in STATIC_IMP.finditer(src):
        parts = m.group(1).split(".")
        if len(parts) < 2:
            continue
        if parts[-1] == "*":
            wildcard.append(parts[-2])
        else:
            exact[parts[-1]] = parts[-2]
    return exact, wildcard


def call_args(body: str, masked: str, at: int) -> List[str]:
    """All arguments of the call whose `(` sits at `at`, depth-counted on masked."""
    depth, start = 0, None
    for i in range(at, len(masked)):
        ch = masked[i]
        if ch == "(":
            depth += 1
            if depth == 1:
                start = i + 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                if start is None:
                    return []
                inner_m, inner_o = masked[start:i], body[start:i]
                return [inner_o[s:e].strip() for s, e in split_top_spans(inner_m, ",")]
    return []


def analyse(body: str, imports: Tuple[Dict[str, str], List[str]]) -> Dict[str, Any]:
    exact, wildcard = imports
    mb = mask(body)
    flow: List[str] = []
    asserts: List[Dict[str, str]] = []
    helpers: List[Dict[str, Any]] = []
    for m in FLOW_CALL.finditer(mb):
        call = f"{m.group(1)}.{m.group(2)}(...)"
        if call not in flow:
            flow.append(call)
    for m in CALL.finditer(mb):
        recv, meth = m.group(1), m.group(2)
        if meth == "assertAll":
            continue
        args = call_args(body, mb, mb.index("(", m.end() - 1))
        # Where does this call actually live?
        if recv and recv[:1].isupper():
            origin, qualified = recv, meth
        elif recv:
            origin, qualified = recv, f"{recv}.{meth}"
        else:
            origin = exact.get(meth, "")
            qualified = meth
        is_helper = meth.startswith("verify") or origin.endswith("Assertions")
        if is_helper:
            entry = {
                "assertion_class": origin,
                "assertion_method": meth,
                # False means the helper's class could not be resolved from imports;
                # the caller must locate it before trusting the method's assertions.
                "resolved": bool(origin) or not wildcard,
                "args": args,
            }
            if entry not in helpers:
                helpers.append(entry)
        else:
            asserts.append({
                "target": args[0] if args else "",
                "assertion_type": qualified,
                "expected": args[1] if len(args) > 1 else "",
                "message": args[2] if len(args) > 2 else "",
            })
    return {
        "flow": flow,
        "assertions": asserts,
        "assertion_helpers_called": helpers,
        "uses_soft_assert": "SoftAssert" in mb or ".assertAll()" in mb,
    }


# ── data providers ────────────────────────────────────────────────────────────

def provider_rows(body: str) -> Tuple[List[Dict[str, Any]], bool]:
    """Rows of a `new Object[][]{{...},{...}}` provider.

    Returns (rows, parsed). `parsed=False` means the provider builds its rows
    dynamically (loops, builders, stream) — the caller must not guess.
    """
    mb = mask(body)
    m = re.search(r"new\s+Object\s*\[\s*\]\s*\[\s*\]\s*\{", mb)
    if not m:
        return [], False
    start = mb.index("{", m.end() - 1)
    end = match_block(mb, start)
    if end is None:
        return [], False
    base = start + 1
    outer_m = mb[base:end - 1]
    rows: List[Dict[str, Any]] = []
    idx = 0
    for s, e in split_top_spans(outer_m, ","):
        chunk_m = outer_m[s:e].strip()
        if not chunk_m:
            continue                      # trailing comma, or a comment-only line
        chunk_o = body[base + s:base + e]
        lo = chunk_o.find("{")
        hi = chunk_o.rfind("}")
        if lo == -1 or hi <= lo:
            return rows, False            # not a literal matrix; do not guess
        inner_m = mask(chunk_o)[lo + 1:hi]
        values = [chunk_o[lo + 1 + vs:lo + 1 + ve].strip()
                  for vs, ve in split_top_spans(inner_m, ",")]
        rows.append({"row_index": idx, "values": [unquote(v) for v in values if v.strip()]})
        idx += 1
    return rows, bool(rows)


# ── per-file dispatch ─────────────────────────────────────────────────────────

def class_name(path: str) -> str:
    return os.path.basename(path)[:-5] if path.endswith(".java") else os.path.basename(path)


def parse_file(root: str, rel: str) -> Optional[Dict[str, Any]]:
    full = rel if os.path.isabs(rel) else os.path.join(root, rel)
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except OSError as exc:
        return {"path": rel, "error": f"unreadable: {type(exc).__name__}: {exc}"}
    mb = mask(src)
    imports = static_imports(src)
    tests, providers, helpers = [], [], []
    for mem in members(src, mb):
        annos = mem["annotations"]
        info = analyse(mem["body"], imports)
        if "Test" in annos:
            a = anno_args(annos["Test"])
            tests.append({
                "method_name": mem["name"],
                "groups": brace_list(a.get("groups", "")),
                "description": unquote(a.get("description", "")),
                "parameters": param_names(mem["params"]),
                "flow": info["flow"],
                "assertions": info["assertions"],
                "assertion_helpers_called": info["assertion_helpers_called"],
                "uses_soft_assert": info["uses_soft_assert"],
                "data_provider": {
                    "data_provider_method": unquote(a.get("dataProvider", "")),
                    "data_provider_class": unquote(a.get("dataProviderClass", "")).replace(".class", ""),
                },
            })
        elif "DataProvider" in annos:
            a = anno_args(annos["DataProvider"])
            rows, parsed = provider_rows(mem["body"])
            providers.append({
                "data_provider_method": mem["name"],
                "declared_name": unquote(a.get("name", mem["name"])),
                "parallel": a.get("parallel", "false").strip() == "true",
                "rows": rows,
                "rows_parsed": parsed,
            })
        elif re.search(r"\bassert", mem["name"], re.I) or re.search(r"\bverify", mem["name"], re.I) \
                or info["assertions"]:
            helpers.append({
                "assertion_method": mem["name"],
                "soft": info["uses_soft_assert"],
                "asserts": info["assertions"],
                "params": param_names(mem["params"]),
            })
    return {"path": rel, "class": class_name(rel), "tests": tests,
            "providers": providers, "assertion_methods": helpers}


# ── plan-driven collection ────────────────────────────────────────────────────

def files_from_plan(plan: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, str]]]:
    wanted, skipped = [], []
    for s in plan.get("automation_scenarios", []):
        sid = s.get("scenario_id", "<no id>")
        if s.get("is_dedup"):
            continue
        ctx = s.get("scenario_gbt_context")
        if not isinstance(ctx, dict):
            skipped.append({"scenario_id": sid, "reason": "no scenario_gbt_context"})
            continue
        if "error" in ctx:
            skipped.append({"scenario_id": sid, "reason": ctx["error"]})
            continue
        for pair in ctx.get("test_methods_calling_endpoint") or []:
            f = pair.get("test_file") if isinstance(pair, dict) else None
            if f and f not in wanted:
                wanted.append(f)
        for key in ("test_assertions", "test_data_providers"):
            for item in ctx.get(key) or []:
                f = item.get("file") if isinstance(item, dict) else item
                if isinstance(f, str) and f.endswith(".java") and f not in wanted:
                    wanted.append(f)
    return wanted, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=os.environ.get("GBT_REPO_PATH", ".gbt_repo"))
    ap.add_argument("--plan", help="enriched automation plan; collects files from scenario_gbt_context")
    ap.add_argument("--files", nargs="*", default=[], help="explicit .java paths (repo-relative)")
    ap.add_argument("--out", help="write JSON here instead of stdout")
    args = ap.parse_args()

    if not args.plan and not args.files:
        print("need --plan or --files", file=sys.stderr)
        return 2
    if not os.path.isdir(args.repo):
        print(f"repo not found: {args.repo}", file=sys.stderr)
        return 2

    targets, skipped = list(args.files), []
    if args.plan:
        try:
            with open(args.plan, encoding="utf-8") as fh:
                plan = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"plan unreadable: {exc}", file=sys.stderr)
            return 2
        from_plan, skipped = files_from_plan(plan)
        targets += [t for t in from_plan if t not in targets]

    parsed = [p for p in (parse_file(args.repo, t) for t in targets) if p]
    errors = [p for p in parsed if "error" in p]
    good = [p for p in parsed if "error" not in p]

    method_summaries, assertion_summaries, provider_summaries = [], [], []
    for f in good:
        if f["tests"]:
            method_summaries.append({"class": f["class"], "path": f["path"], "methods": f["tests"]})
        if f["assertion_methods"]:
            assertion_summaries.append({"assertion_class": f["class"], "path": f["path"],
                                        "methods": f["assertion_methods"]})
        for pr in f["providers"]:
            provider_summaries.append({"data_provider_class": f["class"], "path": f["path"], **pr})

    unparsed = [f"{p['data_provider_class']}#{p['data_provider_method']}"
                for p in provider_summaries if not p["rows_parsed"]]

    out = {
        "method_summaries": method_summaries,
        "assertion_summaries": assertion_summaries,
        "data_provider_summaries": provider_summaries,
        "parse_report": {
            "files_requested": len(targets),
            "files_parsed": len(good),
            "test_methods_found": sum(len(f["tests"]) for f in good),
            "unreadable_files": errors,
            "providers_with_unparsed_rows": unparsed,
            "scenarios_without_context": skipped,
        },
    }
    text = json.dumps(out, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"{len(good)}/{len(targets)} files parsed, "
              f"{out['parse_report']['test_methods_found']} @Test methods -> {args.out}",
              file=sys.stderr)
    else:
        print(text)
    if not good and targets:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
