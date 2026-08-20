#!/usr/bin/env python3
"""
Targeted corpus lookup — returns ONLY the requested record from the large
nav_index / deeplinks files. Called by the regression-extractor skill instead
of model-written python one-liners, so the model can't accidentally Read a
3.6MB file into context.

Usage:
  corpus_lookup.py case   <repo> <module> <case_number>
  corpus_lookup.py deeplinks <repo> <module>
  corpus_lookup.py project-map

Examples:
  python3 corpus_lookup.py case gmt gofood 2879733
  python3 corpus_lookup.py case tapmind gofood 556941
  python3 corpus_lookup.py deeplinks gmt gofood
  python3 corpus_lookup.py project-map
"""
import sys, json, os

PLUGIN_ROOT = os.environ.get(
    "CLAUDE_PLUGIN_ROOT",
    os.path.join(os.path.dirname(__file__), ".."),
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
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
