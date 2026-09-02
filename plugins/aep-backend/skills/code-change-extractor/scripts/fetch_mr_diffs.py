#!/usr/bin/env python3
"""
Fetch aggregated per-service MR diffs + CR notes for a backend Epic.

Input : one or more GitLab MR URLs (args, or --file with one URL per line, or stdin).
        The agent discovers these URLs from Jira (Atlassian MCP: epic -> children ->
        remote links) and passes them here.
Output: a single JSON document on stdout (or --out FILE), grouped per MR/service, with
        the three-dot diff vs merge-base (GitLab `changes` API already diffs vs the
        merge-base) plus human review notes.

Fetch strategy: REST API first, glab CLI fallback.
  REST  : needs GITLAB_TOKEN in the environment. Host is taken from each MR URL
          (override / default with GITLAB_HOST). Token is read from the env only and
          is never printed or written to the output.
  glab  : used when GITLAB_TOKEN is absent or a REST call fails and `glab` is on PATH
          and already authenticated.

# SECURITY: the GitLab token is loaded from the GITLAB_TOKEN environment variable.
# TODO: Securely load this value from an environment variable or secrets vault. Do not hardcode.

Usage:
  python3 fetch_mr_diffs.py <mr_url> [<mr_url> ...] [--out diffs.json]
  python3 fetch_mr_diffs.py --file mr_urls.txt --out diffs.json
  echo "https://gitlab.example.com/gojek/wallet-service/-/merge_requests/42" | python3 fetch_mr_diffs.py
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_HOST = os.environ.get("GITLAB_HOST", "").rstrip("/")

# Repos that are TEST code, not the system under test — their MRs are never the
# subject of a code-diff run and must be excluded even if passed directly.
# Matched against any segment of the project path (case-insensitive).
EXCLUDED_REPO_SEGMENTS = {"gojek-backend-tests"}


def is_excluded_project(project_path):
    segs = {s.lower() for s in project_path.split("/")}
    return bool(segs & EXCLUDED_REPO_SEGMENTS)


def parse_mr_url(url):
    """Split a GitLab MR URL into (host, project_path, iid)."""
    u = urllib.parse.urlparse(url.strip())
    host = f"{u.scheme}://{u.netloc}" if u.netloc else DEFAULT_HOST
    # path form: /<group>/<subgroup?>/<project>/-/merge_requests/<iid>
    marker = "/-/merge_requests/"
    if marker not in u.path:
        raise ValueError(f"Not an MR URL (missing {marker!r}): {url}")
    proj_part, iid_part = u.path.split(marker, 1)
    project_path = proj_part.strip("/")
    iid = iid_part.strip("/").split("/")[0]
    return host, project_path, iid


def _rest_get(host, path, token):
    api = f"{host}/api/v4/{path}"
    req = urllib.request.Request(api, headers={"PRIVATE-TOKEN": token})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_rest(host, project_path, iid, token):
    enc = urllib.parse.quote(project_path, safe="")
    changes = _rest_get(host, f"projects/{enc}/merge_requests/{iid}/changes", token)
    try:
        notes = _rest_get(host, f"projects/{enc}/merge_requests/{iid}/notes?per_page=100", token)
    except urllib.error.HTTPError:
        notes = []
    return changes, notes


def _glab(args):
    out = subprocess.run(["glab"] + args, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "glab failed")
    return out.stdout


def fetch_glab(project_path, iid):
    enc = urllib.parse.quote(project_path, safe="")
    changes = json.loads(_glab(["api", f"projects/{enc}/merge_requests/{iid}/changes"]))
    try:
        notes = json.loads(_glab(["api", f"projects/{enc}/merge_requests/{iid}/notes?per_page=100"]))
    except Exception:
        notes = []
    return changes, notes


def normalise(url, changes, notes):
    service = changes.get("references", {}).get("full") or url
    project_path = None
    web = changes.get("web_url", "")
    if "/-/merge_requests/" in web:
        project_path = web.split("/-/merge_requests/")[0].split("//", 1)[-1].split("/", 1)[-1]
    diffs = [
        {
            "old_path": c.get("old_path"),
            "new_path": c.get("new_path"),
            "new_file": c.get("new_file"),
            "deleted_file": c.get("deleted_file"),
            "renamed_file": c.get("renamed_file"),
            "diff": c.get("diff"),
        }
        for c in changes.get("changes", [])
    ]
    review_notes = [
        {
            "author": (n.get("author") or {}).get("username"),
            "body": n.get("body"),
            "type": n.get("type"),  # DiffNote = line-level review comment; null = general discussion
            "resolvable": n.get("resolvable"),
            "resolved": n.get("resolved"),  # False -> open thread (see reconciliation rule F)
            "path": (n.get("position") or {}).get("new_path"),  # file a diff note is anchored to
        }
        for n in notes
        if not n.get("system")  # drop system events (label add, assignee, etc.)
    ]
    return {
        "url": url,
        "project": project_path,
        "service": (project_path or "").rstrip("/").split("/")[-1] or None,
        "iid": changes.get("iid"),
        "title": changes.get("title"),
        "state": changes.get("state"),
        "target_branch": changes.get("target_branch"),
        "merge_base": (changes.get("diff_refs") or {}).get("base_sha"),
        "changed_files": len(diffs),
        "diffs": diffs,
        "notes": review_notes,
    }


def collect_urls(args):
    urls = list(args.urls)
    if args.file:
        with open(args.file) as f:
            urls += [ln for ln in (l.strip() for l in f) if ln and not ln.startswith("#")]
    if not urls and not sys.stdin.isatty():
        urls += [ln for ln in (l.strip() for l in sys.stdin) if ln and not ln.startswith("#")]
    return urls


def main():
    ap = argparse.ArgumentParser(description="Fetch per-service MR diffs + CR notes for an Epic.")
    ap.add_argument("urls", nargs="*", help="GitLab MR URLs")
    ap.add_argument("--file", help="File with one MR URL per line")
    ap.add_argument("--out", help="Write JSON here instead of stdout")
    args = ap.parse_args()

    urls = collect_urls(args)
    if not urls:
        ap.error("no MR URLs provided (args, --file, or stdin)")

    token = os.environ.get("GITLAB_TOKEN")
    have_glab = shutil.which("glab") is not None
    results, errors, excluded = [], [], []

    for url in urls:
        try:
            host, project_path, iid = parse_mr_url(url)
        except ValueError as e:
            errors.append({"url": url, "error": str(e)})
            continue

        # Test-automation repos are never the system under test.
        if is_excluded_project(project_path):
            excluded.append({"url": url, "project": project_path, "reason": "test-automation repo (excluded)"})
            continue

        changes = notes = None
        # REST first
        if token and host:
            try:
                changes, notes = fetch_rest(host, project_path, iid, token)
            except Exception as e:
                errors.append({"url": url, "stage": "rest", "error": str(e)})
        # glab fallback
        if changes is None and have_glab:
            try:
                changes, notes = fetch_glab(project_path, iid)
            except Exception as e:
                errors.append({"url": url, "stage": "glab", "error": str(e)})

        if changes is None:
            errors.append({"url": url, "error": "no fetch method succeeded (set GITLAB_TOKEN or authenticate glab)"})
            continue
        results.append(normalise(url, changes, notes or []))

    doc = {
        "fetched_mrs": results,
        "services": sorted({r["service"] for r in results if r.get("service")}),
        "excluded": excluded,
        "errors": errors,
    }
    if not results:
        # Distinguish "insufficient input" from a transient fetch failure so the
        # skill can reject clearly. All candidates excluded (or none supplied) =>
        # insufficient; otherwise the fetch itself failed.
        doc["insufficient_input"] = (len(excluded) == len(urls))
    out = json.dumps(doc, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out + "\n")
        msg = f"wrote {len(results)} MR(s), {len(doc['services'])} service(s)"
        if excluded:
            msg += f", excluded {len(excluded)} test-repo MR(s)"
        print(f"{msg} -> {args.out}", file=sys.stderr)
    else:
        print(out)
    # non-zero exit when nothing usable was fetched (insufficient input or fetch failure)
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
