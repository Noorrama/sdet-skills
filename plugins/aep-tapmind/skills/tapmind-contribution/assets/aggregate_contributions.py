#!/usr/bin/env python3
"""Aggregate TapMind MR descriptions into a team contribution table.

Usage:
  aggregate_contributions.py --team-config config/teams/aep-consumer.yaml \\
      --mrs /path/to/mrs.json --start 2025-10-01 --end 2025-10-31

Input JSON: list of objects with keys:
  iid, author (username), merged_at (ISO-8601), description, web_url (optional)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from parse_mr_description import PlatformCounts, merge_into_totals, parse_description


def _parse_day(s: str) -> date:
    return date.fromisoformat(s[:10])


def _parse_merged_at(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _in_range(merged_at: str, start: date, end: date) -> bool:
    d = _parse_merged_at(merged_at).date()
    return start <= d <= end


def load_team_config(path: Path) -> tuple[str, dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    if yaml is None:
        sys.exit("PyYAML required: pip install pyyaml")
    doc = yaml.safe_load(text)
    team = doc.get("team", "team")
    members = {}
    for m in doc.get("members", []):
        handle = str(m["gitlab_handle"]).lstrip("@").lower()
        members[handle] = m.get("name", handle)
    return team, members


def render_table(
    team: str,
    start: date,
    end: date,
    members: dict[str, str],
    totals: dict[str, PlatformCounts],
) -> str:
    lines = [
        f"**{team}** — test cases added from merged MRs in "
        f"`{start.isoformat()}` … `{end.isoformat()}` (UTC dates on `merged_at`)",
        "",
        "| Member | GitLab | Android | iOS | Total |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    grand_a = grand_i = 0
    for handle in sorted(members.keys(), key=lambda h: members[h].lower()):
        name = members[handle]
        c = totals.get(handle, PlatformCounts())
        total = c.android + c.ios
        grand_a += c.android
        grand_i += c.ios
        lines.append(
            f"| {name} | @{handle} | {c.android} | {c.ios} | {total} |"
        )
    lines.append(
        f"| **Team total** | | **{grand_a}** | **{grand_i}** | **{grand_a + grand_i}** |"
    )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team-config", required=True, type=Path)
    ap.add_argument("--mrs", required=True, type=Path)
    ap.add_argument("--start", required=True, help="YYYY-MM-DD inclusive")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD inclusive")
    ap.add_argument("--json-out", type=Path, help="optional summary JSON path")
    args = ap.parse_args()

    team, members = load_team_config(args.team_config)
    member_handles = set(members.keys())
    start, end = _parse_day(args.start), _parse_day(args.end)
    if end < start:
        sys.exit("--end must be on or after --start")

    mrs = json.loads(args.mrs.read_text(encoding="utf-8"))
    totals: dict[str, PlatformCounts] = {}
    used_mrs = []

    for mr in mrs:
        merged_at = mr.get("merged_at") or ""
        if not merged_at or not _in_range(merged_at, start, end):
            continue
        author = (mr.get("author") or mr.get("author_username") or "").lower()
        desc = mr.get("description") or ""
        pr = parse_description(desc, author)
        roster_in_desc = pr.by_handle.keys() & member_handles
        if (
            author not in member_handles
            and not roster_in_desc
            and not (
                author in member_handles
                and (pr.unassigned.android or pr.unassigned.ios)
            )
        ):
            continue
        merge_into_totals(totals, pr, member_handles, author)
        used_mrs.append(
            {
                "iid": mr.get("iid"),
                "author": author,
                "merged_at": merged_at,
                "web_url": mr.get("web_url"),
            }
        )

    table = render_table(team, start, end, members, totals)
    print(table)

    if args.json_out:
        payload = {
            "team": team,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "members": members,
            "counts": {
                h: {"android": totals.get(h, PlatformCounts()).android,
                    "ios": totals.get(h, PlatformCounts()).ios}
                for h in members
            },
            "mrs_included": used_mrs,
        }
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
