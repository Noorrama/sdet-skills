#!/usr/bin/env python3
"""Deterministic anomaly checks over a single `adb shell uiautomator dump` XML file.

Usage: lint.py <pagesource.xml> [--locale id-ID]

Prints a JSON array of findings to stdout. Each finding has no `step`/`node` — the caller
(the skill, mid-run) fills those in since only it knows which trace node this dump belongs to.
Deterministic and free: same input always produces the same output, no model call involved.
"""
import json
import re
import sys
import xml.etree.ElementTree as ET

RESOURCE_KEY_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+){1,}$")
TRUNCATION_RE = re.compile(r"(…|\.\.\.)\s*$")
LATIN_WORD_RE = re.compile(r"^[A-Za-z0-9 .,!?'\"-]+$")


def parse_bounds(bounds_str):
    m = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", bounds_str or "")
    if not m:
        return None
    x1, y1, x2, y2 = (int(v) for v in m.groups())
    return (x1, y1, x2, y2)


def is_interactive(el):
    return el.get("clickable") == "true" or el.get("long-clickable") == "true"


def load_nodes(xml_path):
    tree = ET.parse(xml_path)
    nodes = []
    root_bounds = None
    for el in tree.getroot().iter("node"):
        b = parse_bounds(el.get("bounds"))
        if b is None:
            continue
        if root_bounds is None:
            root_bounds = b  # first <node> in document order is the top-level container
        nodes.append({
            "text": el.get("text") or "",
            "desc": el.get("content-desc") or "",
            "cls": el.get("class") or "",
            "resid": el.get("resource-id") or "",
            "clickable": is_interactive(el),
            "bounds": b,
        })
    return nodes, (root_bounds or (0, 0, 0, 0))


def intersects(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return ax1 < bx2 and bx1 < ax2 and ay1 < by2 and by1 < ay2


def area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def finding(ftype, severity, title, detail, evidence):
    return {
        "severity": severity,
        "confidence": "high",
        "source": "lint",
        "type": ftype,
        "title": title,
        "detail": detail,
        "evidence": evidence,
    }


def check_truncated_text(nodes):
    out = []
    for n in nodes:
        if n["text"] and TRUNCATION_RE.search(n["text"]):
            out.append(finding(
                "truncated-text", "low", "Text ends in an ellipsis",
                "Copy may be clipped rather than intentionally shortened.",
                repr(n["text"]),
            ))
    return out


def check_overlapping(nodes):
    out = []
    interactive = [n for n in nodes if n["clickable"] and area(n["bounds"]) > 0]
    for i in range(len(interactive)):
        for j in range(i + 1, len(interactive)):
            a, b = interactive[i], interactive[j]
            if intersects(a["bounds"], b["bounds"]):
                out.append(finding(
                    "overlapping-elements", "medium",
                    "Two interactive elements overlap",
                    "Overlapping tap targets can make one element unreachable or cause mis-taps.",
                    f"{a['resid'] or a['desc'] or a['text']!r} @ {a['bounds']} overlaps "
                    f"{b['resid'] or b['desc'] or b['text']!r} @ {b['bounds']}",
                ))
    return out


def check_missing_a11y_label(nodes):
    out = []
    for n in nodes:
        if n["clickable"] and not n["text"].strip() and not n["desc"].strip():
            out.append(finding(
                "missing-a11y-label", "medium",
                "Interactive element has no text or accessibility label",
                "Screen readers and appium element-selection both rely on text/content-desc.",
                f"class={n['cls']!r} resource-id={n['resid']!r} bounds={n['bounds']}",
            ))
    return out


def check_broken_image(nodes):
    out = []
    for n in nodes:
        if "image" not in n["cls"].lower():
            continue
        w, h = n["bounds"][2] - n["bounds"][0], n["bounds"][3] - n["bounds"][1]
        if w <= 0 or h <= 0:
            out.append(finding(
                "broken-image", "medium", "Image element has zero-size bounds",
                "Likely a failed image load rather than an intentionally hidden element.",
                f"resource-id={n['resid']!r} bounds={n['bounds']}",
            ))
        elif "placeholder" in n["resid"].lower():
            out.append(finding(
                "broken-image", "low", "Image element uses a placeholder resource id",
                "May indicate the real image never loaded.",
                f"resource-id={n['resid']!r}",
            ))
    return out


def check_untranslated(nodes, locale):
    out = []
    for n in nodes:
        t = n["text"].strip()
        if not t:
            continue
        if RESOURCE_KEY_RE.match(t):
            out.append(finding(
                "untranslated-string", "high",
                "Raw resource key is visible in the UI",
                f"Text looks like an untranslated resource key rather than copy: {t!r}",
                t,
            ))
        elif locale and locale.lower().startswith("id") and LATIN_WORD_RE.match(t) and len(t.split()) >= 2:
            out.append(finding(
                "untranslated-string", "low",
                "Latin-only copy on a locale=id-ID screen",
                "May be untranslated English copy; verify against the expected locale.",
                t,
            ))
    return out


def check_offscreen(nodes, screen):
    _, _, max_x, max_y = screen
    out = []
    for n in nodes:
        if not n["clickable"]:
            continue
        x1, y1, x2, y2 = n["bounds"]
        if x2 <= 0 or y2 <= 0 or x1 >= max_x or y1 >= max_y:
            out.append(finding(
                "offscreen-element", "medium",
                "Interactive element renders outside the visible viewport",
                f"Viewport is 0,0 to {max_x},{max_y}; element cannot be tapped as a user would.",
                f"resource-id={n['resid']!r} bounds={n['bounds']}",
            ))
    return out


def main():
    args = sys.argv[1:]
    if not args:
        print("usage: lint.py <pagesource.xml> [--locale id-ID]", file=sys.stderr)
        sys.exit(2)
    xml_path = args[0]
    locale = None
    if "--locale" in args:
        locale = args[args.index("--locale") + 1]

    nodes, screen = load_nodes(xml_path)
    findings = []
    findings += check_truncated_text(nodes)
    findings += check_overlapping(nodes)
    findings += check_missing_a11y_label(nodes)
    findings += check_broken_image(nodes)
    findings += check_untranslated(nodes, locale)
    findings += check_offscreen(nodes, screen)
    print(json.dumps(findings, indent=2))


if __name__ == "__main__":
    main()
