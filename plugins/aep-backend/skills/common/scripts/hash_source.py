#!/usr/bin/env python3
"""Normalise text and emit sha256:… for Phase A provenance.source_content_hash.

Usage:
  python hash_source.py path/to/extracted.txt
  textutil -convert txt -stdout RFC.docx | python hash_source.py -
"""

from __future__ import annotations

import hashlib
import sys
import unicodedata
from pathlib import Path


def normalise(text: str) -> bytes:
    text = unicodedata.normalize("NFKC", text)
    lines = [line.rstrip() for line in text.splitlines()]
    body = "\n".join(lines)
    if body and not body.endswith("\n"):
        body += "\n"
    return body.encode("utf-8")


def hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: hash_source.py <file|->", file=sys.stderr)
        return 2
    src = argv[1]
    if src == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(src).read_text(encoding="utf-8", errors="replace")
    print(hash_bytes(normalise(raw)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
