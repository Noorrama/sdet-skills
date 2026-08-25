#!/usr/bin/env python3
"""Compute exact token usage/cost for the CURRENT Claude Code session by reading its own
transcript JSONL directly, instead of asking the user for `/cost` or guessing.

Claude Code writes one line per turn to
~/.claude/projects/<cwd with "/" -> "-">/<session-id>.jsonl
and $CLAUDE_CODE_SESSION_ID names the running session, so this is derivable with no
user interaction. A single API turn can appear as more than one JSONL line (one per
content block) sharing the same assistant message id and identical `usage` — dedupe by
message id before summing, or a multi-tool-call turn overcounts by 2-3x.

Usage: session-usage.py [--cwd DIR] [--session-id ID] [--transcript PATH]
Prints JSON: {model, inputTokens, outputTokens, cacheReadTokens, cacheWriteTokens,
              costUsd, costEstimated: false}
Exits non-zero with a message on stderr if the transcript can't be found or parsed —
the caller should fall back to asking the user for `/cost`, or the formula in
design-notes.md, rather than treat a failure here as zero cost.
"""
import argparse
import json
import os
import sys

# $ per MTok. Update alongside design-notes.md's "Token cost estimate" table when pricing
# changes — Sonnet 5's promo rate ($2/$10) is explicitly time-boxed (through 2026-08-31).
BASE_PRICING = {
    "claude-sonnet-5": {"input": 2.0, "output": 10.0},
    "claude-opus-5": {"input": 5.0, "output": 25.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}
CACHE_READ_MULT = 0.1
CACHE_WRITE_5M_MULT = 1.25
CACHE_WRITE_1H_MULT = 2.0


def project_dir_name(cwd):
    return cwd.replace("/", "-")


def find_transcript(cwd, session_id, explicit_path):
    if explicit_path:
        return explicit_path
    if not session_id:
        raise SystemExit("no session id given and $CLAUDE_CODE_SESSION_ID is unset")
    path = os.path.expanduser(
        f"~/.claude/projects/{project_dir_name(cwd)}/{session_id}.jsonl"
    )
    if not os.path.isfile(path):
        raise SystemExit(f"no transcript at {path}")
    return path


def aggregate(transcript_path):
    seen_ids = set()
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0}
    model = None
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = d.get("message")
            if not isinstance(msg, dict):
                continue
            usage = msg.get("usage")
            if not usage:
                continue
            msg_id = msg.get("id")
            if msg_id in seen_ids:
                continue  # same API turn logged again for another content block
            seen_ids.add(msg_id)
            model = msg.get("model", model)
            totals["input"] += usage.get("input_tokens", 0) or 0
            totals["output"] += usage.get("output_tokens", 0) or 0
            totals["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
            cc = usage.get("cache_creation") or {}
            totals["cache_write_5m"] += cc.get("ephemeral_5m_input_tokens", 0) or 0
            totals["cache_write_1h"] += cc.get("ephemeral_1h_input_tokens", 0) or 0
    return model, totals


def cost_usd(model, totals):
    prices = BASE_PRICING.get(model)
    if not prices:
        return None  # unknown model — don't fabricate a number
    mtok = 1_000_000
    return (
        totals["input"] * prices["input"] / mtok
        + totals["output"] * prices["output"] / mtok
        + totals["cache_read"] * prices["input"] * CACHE_READ_MULT / mtok
        + totals["cache_write_5m"] * prices["input"] * CACHE_WRITE_5M_MULT / mtok
        + totals["cache_write_1h"] * prices["input"] * CACHE_WRITE_1H_MULT / mtok
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--session-id", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    ap.add_argument("--transcript")
    args = ap.parse_args()

    path = find_transcript(args.cwd, args.session_id, args.transcript)
    model, totals = aggregate(path)
    cache_write = totals["cache_write_5m"] + totals["cache_write_1h"]
    result = {
        "model": model,
        "inputTokens": totals["input"],
        "outputTokens": totals["output"],
        "cacheReadTokens": totals["cache_read"],
        "cacheWriteTokens": cache_write,
        "costUsd": cost_usd(model, totals),
        "costEstimated": False,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
