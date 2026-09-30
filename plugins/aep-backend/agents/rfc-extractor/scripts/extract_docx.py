#!/usr/bin/env python3
"""
extract_docx.py — DOCX ingestion for the rfc-extractor (Phase A).

A .docx is a zip. Its narrative text lives in word/document.xml, but Block
Diagrams / Sequence Diagrams / architecture drawings are stored as IMAGES in
word/media/ and referenced from the XML via relationship ids. A naive text-only
pass (reading only <w:t>) silently drops every diagram — which then gets
mislabeled as a `missing_from_source` gap even though the diagram IS in the doc.

This helper avoids that: it walks the document in order and emits
  - paragraphs (with heading level prefixes)
  - tables (as `[TABLE] a | b [/TABLE]`)
  - an INLINE marker at each image's real position:
        [IMAGE: image7.jpeg -> <out_dir>/image7.jpeg | anchor: "Sequence Diagram"]
    where `anchor` is the nearest preceding heading/non-empty paragraph, so the
    caller knows which diagram belongs to which section.
It also copies every word/media/* file out to <out_dir> so they can be Read
(Read renders images), and prints a normalised-text sha256 for provenance.

Review comments (word/comments.xml + word/commentsExtended.xml) live OUTSIDE
word/document.xml and are NOT part of the body walk, yet they routinely carry
the decisions that resolve an RFC's open threads. This helper extracts them
too — author, date, resolved/open state, and thread (reply) structure — into a
separate <stem>.comments.txt with its own hash, and prints a thread-ordered
readout so the caller always ingests them.

Usage:
    python3 extract_docx.py <file.docx> <out_dir>

Writes <out_dir>/<docx-stem>.txt, <out_dir>/<docx-stem>.comments.txt (when the
doc has comments), and <out_dir>/media/*. Prints a summary, the body
`sha256:<hex>` normalised-text hash, and a separate comments hash to stdout.
Stdlib only (no python-docx).
"""
import sys, os, zipfile, re, hashlib, unicodedata, shutil
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"
W15 = "{http://schemas.microsoft.com/office/word/2012/wordml}"


def _text(el):
    return "".join(t.text or "" for t in el.iter(f"{W}t"))


def _comments(z):
    """Extract review comments from word/comments.xml (+ threading/resolved state
    from word/commentsExtended.xml when present).

    Word review comments live OUTSIDE word/document.xml, so the body walk never
    sees them — yet they routinely carry the design decisions that resolve an
    RFC's open threads (chosen approach, idempotency keys, deferred milestones).
    Returns an ordered list of dicts: {id, author, date, initials, text, paraId,
    parentParaId, done}. `done` is True/False when commentsExtended marks the
    thread resolved, else None. Threads are reconstructed by parentParaId.
    """
    try:
        croot = ET.fromstring(z.read("word/comments.xml"))
    except KeyError:
        return []
    # paraId -> resolved/thread info from commentsExtended.xml (optional part)
    ext = {}
    try:
        eroot = ET.fromstring(z.read("word/commentsExtended.xml"))
        for ce in eroot.iter(f"{W15}commentEx"):
            pid = ce.get(f"{W15}paraId")
            if pid:
                ext[pid] = {
                    "parent": ce.get(f"{W15}paraIdParent"),
                    "done": ce.get(f"{W15}done") in ("1", "true"),
                }
    except KeyError:
        pass
    out = []
    for c in croot.iter(f"{W}comment"):
        # a comment can span multiple paragraphs; use the first paragraph's
        # w14:paraId as the thread key (that is what commentsExtended references)
        first_p = c.find(f"{W}p")
        para_id = first_p.get(f"{W14}paraId") if first_p is not None else None
        info = ext.get(para_id, {})
        out.append({
            "id": c.get(f"{W}id"),
            "author": c.get(f"{W}author") or "",
            "date": c.get(f"{W}date") or "",
            "initials": c.get(f"{W}initials") or "",
            "text": _text(c).strip(),
            "paraId": para_id,
            "parentParaId": info.get("parent"),
            "done": info.get("done"),
        })
    return out


def _rels(z):
    """rId -> media basename (e.g. 'image7.jpeg')."""
    out = {}
    try:
        rroot = ET.fromstring(z.read("word/_rels/document.xml.rels"))
    except KeyError:
        return out
    for rel in rroot:
        rid = rel.get("Id")
        tgt = rel.get("Target", "")
        if "media/" in tgt:
            out[rid] = os.path.basename(tgt)
    return out


def _image_ids(paragraph):
    """rIds of images embedded in this paragraph, in order (a:blip r:embed / v:imagedata)."""
    ids = []
    for blip in paragraph.iter(f"{A}blip"):
        rid = blip.get(f"{R}embed") or blip.get(f"{R}link")
        if rid:
            ids.append(rid)
    # legacy VML fallback
    for im in paragraph.iter("{urn:schemas-microsoft-com:vml}imagedata"):
        rid = im.get(f"{R}id")
        if rid:
            ids.append(rid)
    return ids


def extract(src, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    media_dir = os.path.join(out_dir, "media")
    os.makedirs(media_dir, exist_ok=True)
    z = zipfile.ZipFile(src)
    rels = _rels(z)

    # copy media out so the caller can Read the diagrams
    media_written = []
    for name in z.namelist():
        if name.startswith("word/media/"):
            base = os.path.basename(name)
            with z.open(name) as fsrc, open(os.path.join(media_dir, base), "wb") as fdst:
                shutil.copyfileobj(fsrc, fdst)
            media_written.append(base)

    root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(f"{W}body")
    lines = []
    image_index = []  # (media_basename, anchor_text)
    last_anchor = "(document start)"

    def anchor_from(txt, style):
        # headings and short bold-ish captions make the best anchors
        return txt.strip() or last_anchor

    def walk(el):
        nonlocal last_anchor
        for child in el:
            tag = child.tag
            if tag == f"{W}p":
                style = ""
                pPr = child.find(f"{W}pPr")
                if pPr is not None:
                    ps = pPr.find(f"{W}pStyle")
                    if ps is not None:
                        style = ps.get(f"{W}val", "")
                txt = _text(child)
                prefix = ""
                if style.lower().startswith("heading"):
                    lvl = "".join(c for c in style if c.isdigit())
                    prefix = "#" * (int(lvl) if lvl else 1) + " "
                if txt.strip():
                    lines.append(prefix + txt)
                    last_anchor = txt.strip()
                # images anchored in this paragraph
                for rid in _image_ids(child):
                    base = rels.get(rid)
                    if not base:
                        continue
                    rel_path = os.path.join(media_dir, base)
                    lines.append(f'[IMAGE: {base} -> {rel_path} | anchor: "{last_anchor}"]')
                    image_index.append((base, last_anchor))
            elif tag == f"{W}tbl":
                lines.append("[TABLE]")
                for row in child.findall(f"{W}tr"):
                    cells = [
                        " ".join(_text(p) for p in tc.findall(f"{W}p")).strip()
                        for tc in row.findall(f"{W}tc")
                    ]
                    # tables can also embed images
                    imgs = []
                    for tc in row.findall(f"{W}tc"):
                        for rid in _image_ids(tc):
                            base = rels.get(rid)
                            if base:
                                imgs.append(base)
                                image_index.append((base, last_anchor))
                    line = " | ".join(cells)
                    if imgs:
                        line += " " + " ".join(
                            f'[IMAGE: {b} -> {os.path.join(media_dir, b)} | anchor: "{last_anchor}"]'
                            for b in imgs
                        )
                    lines.append(line)
                lines.append("[/TABLE]")
            else:
                walk(child)

    walk(body)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    stem = os.path.splitext(os.path.basename(src))[0]
    txt_path = os.path.join(out_dir, stem + ".txt")
    with open(txt_path, "w") as f:
        f.write(text)

    # normalised-text hash for provenance (NFKC, strip trailing ws, trailing newline).
    # IMPORTANT: reduce each [IMAGE: base -> <path> | anchor: ...] marker's path to its
    # basename before hashing, so the content hash is independent of the extraction
    # out_dir (otherwise the same source hashes differently per run — breaking staleness).
    hash_src = re.sub(
        r'(\[IMAGE: [^\]]*?-> )([^|\]]+?)( \| anchor:)',
        lambda m: m.group(1) + os.path.basename(m.group(2).strip()) + m.group(3),
        text,
    )
    norm = unicodedata.normalize("NFKC", "\n".join(l.rstrip() for l in hash_src.split("\n")))
    if not norm.endswith("\n"):
        norm += "\n"
    digest = "sha256:" + hashlib.sha256(norm.encode()).hexdigest()

    # review comments (word/comments.xml) — outside the body, but often resolve
    # the RFC's open threads. Write to a SEPARATE file with its own hash so the
    # body hash stays stable, and print a thread-ordered readout.
    comments = _comments(z)
    comments_path = None
    comments_digest = None
    if comments:
        by_para = {c["paraId"]: c for c in comments if c["paraId"]}
        clines = []
        for c in comments:
            depth = 0
            parent = c.get("parentParaId")
            seen = set()
            while parent and parent in by_para and parent not in seen:
                seen.add(parent)
                depth += 1
                parent = by_para[parent].get("parentParaId")
            state = ""
            if c["done"] is True:
                state = " [RESOLVED]"
            elif c["done"] is False:
                state = " [OPEN]"
            reply = "  (reply)" if c.get("parentParaId") else ""
            indent = "    " * depth
            clines.append(
                f'{indent}- [id={c["id"]}] {c["author"]} @ {c["date"]}{state}{reply}\n'
                f'{indent}  {c["text"]}'
            )
        comments_text = "\n".join(clines) + "\n"
        comments_path = os.path.join(out_dir, stem + ".comments.txt")
        with open(comments_path, "w") as f:
            f.write(comments_text)
        cnorm = unicodedata.normalize("NFKC", "\n".join(l.rstrip() for l in comments_text.split("\n")))
        if not cnorm.endswith("\n"):
            cnorm += "\n"
        comments_digest = "sha256:" + hashlib.sha256(cnorm.encode()).hexdigest()

    print(f"text_file: {txt_path}")
    print(f"media_dir: {media_dir}")
    print(f"chars: {len(text)}  lines: {len(text.splitlines())}")
    print(f"media_files: {len(media_written)}  inline_image_anchors: {len(image_index)}")
    print(f"normalised_text_sha256: {digest}")
    print(f"comments: {len(comments)}", end="")
    if comments:
        authors = sorted({c["author"] for c in comments if c["author"]})
        n_open = sum(1 for c in comments if c["done"] is False)
        n_resolved = sum(1 for c in comments if c["done"] is True)
        print(f"  (authors: {', '.join(authors)}; resolved={n_resolved}, open={n_open}, unknown={len(comments)-n_open-n_resolved})")
        print(f"comments_file: {comments_path}")
        print(f"comments_sha256: {comments_digest}")
        print("--- review comments (READ these; author replies resolve open threads) ---")
        for c in comments:
            state = "[RESOLVED]" if c["done"] is True else ("[OPEN]" if c["done"] is False else "")
            reply = " (reply)" if c.get("parentParaId") else ""
            print(f'  [id={c["id"]}] {c["author"]} {state}{reply}: {c["text"][:160]}')
    else:
        print()
    if image_index:
        print("--- image anchors (READ these to reconstruct diagrams) ---")
        for base, anchor in image_index:
            print(f'  {base}  <-  "{anchor}"')
    # orphan media (present but not anchored in body order) — still Read them
    anchored = {b for b, _ in image_index}
    orphans = [m for m in media_written if m not in anchored]
    if orphans:
        print(f"--- media present but not anchored in body ({len(orphans)}) ---")
        print("  " + ", ".join(orphans))
    return txt_path, media_dir, image_index


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python3 extract_docx.py <file.docx> <out_dir>", file=sys.stderr)
        sys.exit(2)
    extract(sys.argv[1], sys.argv[2])