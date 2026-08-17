#!/usr/bin/env python3
"""
Orchestrator: run all three extractors against one or more test automation
repos and write the checked-in corpus files the regression-extractor skill
reads (deeplinks.json, browserstack_project_map.json, nav_index/<repo_key>/).

This script only greps/regexes files on disk -- it never sends repo content
through a model, so the cost of a full run is a few seconds of CPU, not
tokens. It is meant to become the CI job on each repo (regenerate on merge
to main), not something run by hand per feature.

Each extractor merges its repo's section into the existing output file, so
running one repo never destroys another repo's already-written data.

Run: python3 build_corpus.py <config_out_dir> gmt=<path-to-gojek-mobile-tests> gtf=<path-to-gtf-mobile-tests>
(any subset/order of repo_key=repo_root pairs is fine -- only the given repos are (re)generated)
"""
import sys, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    if len(sys.argv) < 3:
        print("usage: build_corpus.py <config_out_dir> <repo_key>=<repo_root> [<repo_key>=<repo_root> ...]")
        sys.exit(1)
    config_dir = sys.argv[1]
    repos = []
    for arg in sys.argv[2:]:
        repo_key, _, repo_root = arg.partition("=")
        if not repo_root or repo_key not in ("gmt", "gtf"):
            sys.exit(f"bad arg {arg!r}, expected gmt=<path> or gtf=<path>")
        repos.append((repo_key, repo_root))

    nav_dir = os.path.join(config_dir, "nav_index")
    os.makedirs(config_dir, exist_ok=True)

    for repo_key, repo_root in repos:
        steps = [
            ["python3", os.path.join(HERE, "extract_deeplinks.py"), repo_root, repo_key, os.path.join(config_dir, "deeplinks.json")],
            ["python3", os.path.join(HERE, "extract_project_map.py"), repo_root, repo_key, os.path.join(config_dir, "browserstack_project_map.json")],
            ["python3", os.path.join(HERE, "extract_nav_index.py"), repo_root, repo_key, nav_dir],
        ]
        for cmd in steps:
            print(f"\n$ {' '.join(cmd)}")
            subprocess.run(cmd, check=True)

    print("\nDone. Files written under:", config_dir)


if __name__ == "__main__":
    main()
