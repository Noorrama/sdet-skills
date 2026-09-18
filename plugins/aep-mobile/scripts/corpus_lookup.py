#!/usr/bin/env python3
"""
Targeted corpus lookup — returns ONLY the requested record from the large
nav_index / deeplinks files. Called by the regression-extractor skill instead
of model-written python one-liners, so the model can't accidentally Read a
3.6MB file into context.

Usage:
  corpus_lookup.py case      <repo> <module> <case_number>
  corpus_lookup.py deeplinks <repo> <module>
  corpus_lookup.py project-map
  corpus_lookup.py nav-step  <repo> <module> <keyword> [<max_results>]

Examples:
  python3 corpus_lookup.py case gmt gofood 2879733
  python3 corpus_lookup.py case tapmind gofood 556941
  python3 corpus_lookup.py deeplinks gmt gofood
  python3 corpus_lookup.py project-map
  python3 corpus_lookup.py nav-step gmt driverapp "quick view"
  python3 corpus_lookup.py nav-step gmt driverapp "go online" 5
"""
import sys, json, os

PLUGIN_ROOT = (
    os.environ.get("CURSOR_PLUGIN_ROOT")
    or os.environ.get("CLAUDE_PLUGIN_ROOT")
    or os.path.join(os.path.dirname(__file__), "..")
)
CONFIG = os.path.join(PLUGIN_ROOT, "config")


def case_lookup(repo: str, module: str, case_number: str) -> None:
    path = os.path.join(CONFIG, "nav_index", repo, f"{module}.json")
    if not os.path.isfile(path):
        print(json.dumps({"error": f"not found: {path}"}))
        sys.exit(1)
    with open(path) as f:
        data = json.load(f)
    record = data.get("cases", {}).get(str(case_number))
    if record is None:
        print(json.dumps({"match": None, "case_number": case_number}))
    else:
        print(json.dumps({"match": record, "case_number": case_number}))


def deeplinks_lookup(repo: str, module: str) -> None:
    path = os.path.join(CONFIG, "deeplinks.json")
    if not os.path.isfile(path):
        print(json.dumps({"error": f"not found: {path}"}))
        sys.exit(1)
    with open(path) as f:
        data = json.load(f)
    entries = data.get("repos", {}).get(repo, {}).get("modules", {}).get(module, {})
    flat = {k: (v.get("android") or v.get("raw")) for k, v in entries.items()}
    print(json.dumps(flat))


def project_map() -> None:
    path = os.path.join(CONFIG, "browserstack_project_map.json")
    if not os.path.isfile(path):
        print(json.dumps({"error": f"not found: {path}"}))
        sys.exit(1)
    with open(path) as f:
        print(f.read())


def nav_step_lookup(repo: str, module: str, keyword: str, max_results: int = 10) -> None:
    """Search nav_index for step strings matching keyword; never reads the whole file into context."""
    path = os.path.join(CONFIG, "nav_index", repo, f"{module}.json")
    if not os.path.isfile(path):
        print(json.dumps({"error": f"not found: {path}"}))
        sys.exit(1)
    with open(path) as f:
        data = json.load(f)

    keyword_lower = keyword.lower()
    seen: set = set()
    matches: list = []

    for case_list in data.get("cases", {}).values():
        for case in (case_list if isinstance(case_list, list) else [case_list]):
            for step in (case.get("steps_gherkin") or case.get("steps") or []):
                step_str = str(step).strip()
                if keyword_lower in step_str.lower() and step_str not in seen:
                    seen.add(step_str)
                    matches.append(step_str)
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break
        if len(matches) >= max_results:
            break

    print(json.dumps({"keyword": keyword, "matches": matches, "count": len(matches)}))


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "case" and len(sys.argv) == 5:
        case_lookup(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "deeplinks" and len(sys.argv) == 4:
        deeplinks_lookup(sys.argv[2], sys.argv[3])
    elif cmd == "project-map":
        project_map()
    elif cmd == "nav-step" and len(sys.argv) >= 5:
        max_r = int(sys.argv[5]) if len(sys.argv) >= 6 else 10
        nav_step_lookup(sys.argv[2], sys.argv[3], sys.argv[4], max_r)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
