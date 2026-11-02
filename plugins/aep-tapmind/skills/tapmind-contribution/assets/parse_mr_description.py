#!/usr/bin/env python3
"""Parse TapMind MR descriptions for per-platform test-case counts.

Pure parsing — no network. Used by aggregate_contributions.py and unit-style fixtures.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CONTRIBUTIONS_HEADING = re.compile(
    r"^\s*#{2}\s+test case contributions\s*$", re.IGNORECASE | re.MULTILINE
)
PLATFORM_HEADING = re.compile(
    r"^\s*#{3,5}\s+(android|ios)\s*$", re.IGNORECASE | re.MULTILINE
)
HANDLE_HEADING = re.compile(
    r"^\s*#{3,5}\s+@([a-zA-Z0-9._-]+)\s*$", re.MULTILINE
)
BULLET = re.compile(r"^\s*(?:[-*]|\d+\.)\s+\S", re.MULTILINE)
CONTRIBUTORS_LINE = re.compile(
    r"contributors?\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE
)
MENTION = re.compile(r"@([a-zA-Z0-9._-]+)")


@dataclass
class PlatformCounts:
    android: int = 0
    ios: int = 0

    def add(self, platform: str, n: int) -> None:
        key = platform.lower()
        if key == "android":
            self.android += n
        elif key == "ios":
            self.ios += n


@dataclass
class ParseResult:
    by_handle: dict[str, PlatformCounts] = field(default_factory=dict)
    unassigned: PlatformCounts = field(default_factory=PlatformCounts)
    used_legacy_layout: bool = False


def _count_bullets(text: str) -> int:
    return len(BULLET.findall(text))


def _section_slice(body: str, start: int, end: int | None) -> str:
    return body[start:end if end is not None else len(body)]


def _handles_from_contributors_line(block: str) -> list[str]:
    m = CONTRIBUTORS_LINE.search(block)
    if not m:
        return []
    return [h.lower() for h in MENTION.findall(m.group(1))]


def parse_description(description: str, mr_author: str | None = None) -> ParseResult:
    """Return per-handle Android/iOS counts parsed from an MR description."""
    body = description or ""
    result = ParseResult()
    author = (mr_author or "").lower()

    m_contrib = CONTRIBUTIONS_HEADING.search(body)
    if m_contrib:
        block_start = m_contrib.end()
        next_h2 = re.search(r"^\s*#{2}\s+\S", body[block_start:], re.MULTILINE)
        block_end = block_start + next_h2.start() if next_h2 else len(body)
        block = body[block_start:block_end]
        return _parse_contributions_block(block, result)

    # Legacy: any ### Android / ### iOS sections; attribute to MR author only.
    platforms = list(PLATFORM_HEADING.finditer(body))
    if not platforms or not author:
        return result

    result.used_legacy_layout = True
    for i, pm in enumerate(platforms):
        platform = pm.group(1).lower()
        start = pm.end()
        end = platforms[i + 1].start() if i + 1 < len(platforms) else len(body)
        chunk = _section_slice(body, start, end)
        n = _count_bullets(chunk)
        if n:
            result.by_handle.setdefault(author, PlatformCounts()).add(platform, n)
    return result


def _parse_contributions_block(block: str, result: ParseResult) -> ParseResult:
    default_handles = _handles_from_contributors_line(block)
    if not default_handles and block.strip():
        # Single author MR: platform sections without explicit handle → unassigned bucket
        pass

    # Split on handle subheadings (#### @user)
    handle_markers = list(HANDLE_HEADING.finditer(block))
    if handle_markers:
        for i, hm in enumerate(handle_markers):
            handle = hm.group(1).lower()
            start = hm.end()
            end = handle_markers[i + 1].start() if i + 1 < len(handle_markers) else len(block)
            sub = block[start:end]
            _accumulate_platform_sections(sub, handle, result)
        return result

    # No per-handle headings: apply contributors line or leave unassigned
    target = default_handles[0] if len(default_handles) == 1 else None
    if len(default_handles) > 1:
        # Multiple handles but no subsections — count once, split evenly not supported; use unassigned
        target = None
    _accumulate_platform_sections(block, target, result)
    return result


def _accumulate_platform_sections(
    text: str, handle: str | None, result: ParseResult
) -> None:
    platforms = list(PLATFORM_HEADING.finditer(text))
    if not platforms:
        return
    for i, pm in enumerate(platforms):
        platform = pm.group(1).lower()
        start = pm.end()
        end = platforms[i + 1].start() if i + 1 < len(platforms) else len(text)
        chunk = text[start:end]
        n = _count_bullets(chunk)
        if not n:
            continue
        if handle:
            result.by_handle.setdefault(handle, PlatformCounts()).add(platform, n)
        else:
            result.unassigned.add(platform, n)


def merge_into_totals(
    totals: dict[str, PlatformCounts],
    parse: ParseResult,
    member_handles: set[str],
    mr_author: str,
) -> None:
    """Merge parse result into running totals for configured team members."""
    author = mr_author.lower()

    for handle, counts in parse.by_handle.items():
        if handle not in member_handles:
            continue
        totals.setdefault(handle, PlatformCounts())
        totals[handle].android += counts.android
        totals[handle].ios += counts.ios

    if parse.unassigned.android or parse.unassigned.ios:
        if author in member_handles:
            totals.setdefault(author, PlatformCounts())
            totals[author].android += parse.unassigned.android
            totals[author].ios += parse.unassigned.ios
