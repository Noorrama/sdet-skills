#!/usr/bin/env python3
"""
Orchestrator: run all three extractors against gojek-mobile-tests and write
the checked-in corpus files the regression-extractor skill reads.

This script only greps/regexes files on disk -- it never sends repo content
through a model, so the cost of a full run is a few seconds of CPU, not
tokens. It is meant to become the CI job on gojek-mobile-tests (regenerate
on merge to main), not something run by hand per feature.

Run: python3 build_corpus.py <path-to-gojek-mobile-tests> <path-to-plugins/aep-mobile/config>
"""
import sys, os, subprocess, json

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    if len(sys.argv) != 3:
        print("usage: build_corpus.py <repo_root> <config_out_dir>")
        sys.exit(1)
    repo_root, config_dir = sys.argv[1], sys.argv[2]
    nav_dir = os.path.join(config_dir, "nav_index")
    os.makedirs(config_dir, exist_ok=True)

    steps = [
        ["python3", os.path.join(HERE, "extract_deeplinks.py"), repo_root, os.path.join(config_dir, "deeplinks.json")],
        ["python3", os.path.join(HERE, "extract_project_map.py"), repo_root, os.path.join(config_dir, "browserstack_project_map.json")],
        ["python3", os.path.join(HERE, "extract_nav_index.py"), repo_root, nav_dir],
    ]
    for cmd in steps:
        print(f"\n$ {' '.join(cmd)}")
        subprocess.run(cmd, check=True)

    print("\nDone. Files written under:", config_dir)


if __name__ == "__main__":
    main()
