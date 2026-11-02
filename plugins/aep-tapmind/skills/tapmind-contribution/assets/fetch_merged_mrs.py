#!/usr/bin/env python3
"""Fetch merged GitLab MRs for tapmind-mobile-tests (REST fallback when MCP is unavailable).

Requires GITLAB_TOKEN with read_api on source.golabs.io and project access.

Usage:
  GITLAB_TOKEN=... python3 fetch_merged_mrs.py \\
    --team-config ../config/teams/aep-consumer.yaml \\
    --start 2025-10-01 --end 2025-10-31 --out /tmp/mrs.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def _parse_day(s: str) -> date:
    return date.fromisoformat(s[:10])


def _merged_date(iso: str) -> date:
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def load_config(path: Path) -> tuple[str, str, set[str]]:
    if yaml is None:
        sys.exit("PyYAML required: pip install pyyaml")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    host = doc.get("gitlab_host", "source.golabs.io")
    project = doc.get("project_path", "aep/tapmind-mobile-tests")
    handles = {
        str(m["gitlab_handle"]).lstrip("@").lower() for m in doc.get("members", [])
    }
    return host, project, handles


def api_get(base: str, token: str, path: str, params: dict) -> list:
    q = urllib.parse.urlencode(params)
    url = f"{base}/api/v4{path}?{q}"
    req = urllib.request.Request(
        url, headers={"PRIVATE-TOKEN": token, "User-Agent": "tapmind-contribution-skill"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team-config", required=True, type=Path)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    token = os.environ.get("GITLAB_TOKEN", "").strip()
    if not token:
        sys.exit("GITLAB_TOKEN is not set")

    host, project_path, roster = load_config(args.team_config)
    start, end = _parse_day(args.start), _parse_day(args.end)
    if end < start:
        sys.exit("--end must be on or after --start")

    base = f"https://{host}"
    encoded = urllib.parse.quote(project_path, safe="")

    page = 1
    collected = []
    while True:
        try:
            batch = api_get(
                base,
                token,
                f"/projects/{encoded}/merge_requests",
                {
                    "state": "merged",
                    "order_by": "updated_at",
                    "sort": "desc",
                    "per_page": "50",
                    "page": str(page),
                },
            )
        except urllib.error.HTTPError as e:
            sys.exit(f"GitLab API error {e.code}: {e.reason} (check token and project access)")
        if not batch:
            break
        stop = False
        for mr in batch:
            merged_at = mr.get("merged_at")
            if not merged_at:
                continue
            md = _merged_date(merged_at)
            if md < start:
                stop = True
                break
            if md > end:
                continue
            author = (mr.get("author") or {}).get("username", "").lower()
            if author not in roster:
                continue
            collected.append(
                {
                    "iid": mr.get("iid"),
                    "author": author,
                    "merged_at": merged_at,
                    "description": mr.get("description") or "",
                    "web_url": mr.get("web_url"),
                }
            )
        if stop:
            break
        page += 1
        if page > 40:
            break

    args.out.write_text(json.dumps(collected, indent=2), encoding="utf-8")
    print(f"Wrote {len(collected)} MR(s) to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
