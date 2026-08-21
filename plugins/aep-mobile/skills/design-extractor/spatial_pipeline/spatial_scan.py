#!/usr/bin/env python3
"""Spatial-relationship scanner for "Export Design Raw JSON" (formatVersion 2)
Figma exports. Stage 1 of the spatial-first design-context pipeline.

Deterministic, color-free, convention-agnostic. Every threshold is derived from
the data itself (modal portrait-frame size), so it adapts to any Figma file that
draws screens as repeated same-width frames on a board.

Pipeline:
  1. absolutize      - cumulative parent offsets -> absolute page coords
  2. collect boards  - nodes that live directly on the page or inside a SECTION
  3. calibrate       - modal screen width/height from portrait frames
  4. classify        - SCREEN / CHIP / BANNER / CAPTION / CONTAINER_BOX /
                       VARIANT_BOX (dashed) / CONNECTOR / DECOR
  5. group           - explicit SECTIONs + gap-based union-find for loose nodes
  6. lanes           - per group: rows by TOP-LINE clustering, attached
                       sub-rows (dialog shelves), vertical columns inside rows
  7. associate       - chip->screen, band/cluster banner->screen, left
                       caption->row, dashed/container box->screen set

`analyze(path)` returns the full structured result; `main()` prints a digest.
"""

import json
import sys
from collections import Counter, defaultdict

# ---------------------------------------------------------------- load & absolutize

def load(path):
    with open(path) as f:
        return json.load(f)


def walk_abs(node, ox=0.0, oy=0.0, parent=None, depth=0):
    """Yield (node, abs_x, abs_y, parent, depth). Child coords are parent-relative."""
    ax = ox + node.get('x', 0)
    ay = oy + node.get('y', 0)
    yield node, ax, ay, parent, depth
    for c in node.get('children', []):
        yield from walk_abs(c, ax, ay, node, depth + 1)


def deep_text(node, limit=200):
    out = []
    def w(n):
        if len(' '.join(out)) > limit:
            return
        if 'characters' in n:
            out.append(n['characters'])
        for c in n.get('children', []):
            w(c)
    w(node)
    return ' '.join(out).strip()


def deep_texts(node, cap=6):
    """Distinct text runs in document order (title line vs status line of a chip)."""
    out = []
    def w(n):
        if len(out) >= cap:
            return
        if 'characters' in n and n['characters'].strip():
            out.append(n['characters'].strip())
        for c in n.get('children', []):
            w(c)
    w(node)
    return out


def chip_struct(node):
    """A label chip carries a title and often a change-status line.
    Status comes from the component's Type variant when present (authoritative),
    else from a second text run that repeats a known status vocabulary."""
    texts = deep_texts(node)
    title = texts[0] if texts else ''
    status = None
    vp = node.get('variantProperties') or {}
    t = vp.get('Type')
    if t and t != '-':
        status = t
    elif len(texts) > 1 and texts[-1].lower() in (
            'new screen', 'changes', 'existing', 'updated', 'removed'):
        status = texts[-1]
    if status and title.lower() != status.lower():
        # some chips render title and status concatenated; strip a trailing copy
        if title.lower().endswith(' ' + status.lower()):
            title = title[: -len(status) - 1].rstrip()
    return title, status


# ---------------------------------------------------------------- board node collection

def collect_board_nodes(page):
    """Board nodes = direct children of the PAGE or of any SECTION (any depth).
    Everything deeper is screen-internal detail and irrelevant to layout."""
    boards = []
    for node, ax, ay, parent, depth in walk_abs(page):
        if parent is None:
            continue
        if parent['type'] in ('PAGE', 'SECTION'):
            boards.append({
                'node': node, 'id': node['id'], 'name': node.get('name', ''),
                'type': node['type'],
                'x': ax, 'y': ay,
                'w': node.get('width', 0) or 0, 'h': node.get('height', 0) or 0,
                'parent_id': parent.get('id'), 'parent_type': parent['type'],
                'parent_name': parent.get('name', ''),
            })
    return boards


# ---------------------------------------------------------------- calibration

def calibrate(boards):
    """Modal (width, height) of portrait frame-likes = the device screen size."""
    widths = Counter()
    for b in boards:
        if b['type'] in ('FRAME', 'GROUP', 'INSTANCE', 'COMPONENT') \
           and b['h'] > b['w'] > 0 and b['node'].get('children'):
            widths[round(b['w'])] += 1
    if not widths:
        return None, None
    screen_w = widths.most_common(1)[0][0]
    heights = Counter(round(b['h']) for b in boards
                      if abs(b['w'] - screen_w) <= screen_w * 0.05 and b['h'] > b['w'])
    screen_h = heights.most_common(1)[0][0]
    return screen_w, screen_h


# ---------------------------------------------------------------- classification

def classify(boards, screen_w, screen_h):
    wtol = screen_w * 0.15
    screens, chips, banners, captions = [], [], [], []
    var_boxes, containers, connectors, decor, subsections = [], [], [], [], []

    for b in boards:
        t, w, h = b['type'], b['w'], b['h']
        if t == 'CONNECTOR':
            connectors.append(b); continue
        if t == 'SECTION':
            subsections.append(b); continue
        if b['node'].get('dashed'):
            var_boxes.append(b); continue

        text = deep_text(b['node']) if t != 'RECTANGLE' else ''
        b['text'] = text

        is_framey = t in ('FRAME', 'GROUP', 'INSTANCE', 'COMPONENT', 'RECTANGLE')
        # screen: about one screen wide, at least half a screen tall
        if is_framey and abs(w - screen_w) <= wtol and h >= screen_h * 0.5:
            b['kind'] = 'SCREEN'; screens.append(b); continue
        # banner: text-bearing, spans >= 1.8 screens, short
        if t != 'RECTANGLE' and text and w >= screen_w * 1.8 and h <= screen_h * 0.45:
            b['kind'] = 'BANNER'; banners.append(b); continue
        # chip: about screen-wide, short, text-bearing
        if t != 'RECTANGLE' and text and abs(w - screen_w) <= wtol and h <= screen_h * 0.3:
            b['kind'] = 'CHIP'; chips.append(b); continue
        if t == 'TEXT':
            b['kind'] = 'CAPTION'; captions.append(b); continue
        if is_framey and w > screen_w * 1.5 and h > screen_h * 0.5:
            b['kind'] = 'CONTAINER?'; containers.append(b); continue
        b['kind'] = 'DECOR'; decor.append(b)

    return dict(screens=screens, chips=chips, banners=banners, captions=captions,
                var_boxes=var_boxes, containers=containers, connectors=connectors,
                decor=decor, subsections=subsections)


# ---------------------------------------------------------------- grouping (level 1)

class UF:
    def __init__(self, n): self.p = list(range(n))
    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]; i = self.p[i]
        return i
    def union(self, a, b): self.p[self.find(a)] = self.find(b)


def spatial_groups(items, gap):
    """Union-find on bboxes expanded by `gap`."""
    n = len(items)
    uf = UF(n)
    for i in range(n):
        a = items[i]
        ax0, ay0 = a['x'] - gap, a['y'] - gap
        ax1, ay1 = a['x'] + a['w'] + gap, a['y'] + a['h'] + gap
        for j in range(i + 1, n):
            c = items[j]
            if c['x'] < ax1 and c['x'] + c['w'] > ax0 and \
               c['y'] < ay1 and c['y'] + c['h'] > ay0:
                uf.union(i, j)
    groups = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(items[i])
    return list(groups.values())


# ---------------------------------------------------------------- lanes (level 2)

def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def band_rows(screens, screen_h):
    """Horizontal swim lanes by TOP-LINE clustering: sort screen tops, split
    where the gap exceeds half a screen height. Interval-overlap merging is
    wrong here — scroll screens taller than one device height bridge
    unrelated shelves transitively."""
    order = sorted(screens, key=lambda s: s['y'])
    rows, cur = [], [order[0]]
    for s in order[1:]:
        if s['y'] - cur[-1]['y'] > screen_h * 0.5:
            rows.append(cur); cur = [s]
        else:
            cur.append(s)
    rows.append(cur)
    return [sorted(r, key=lambda s: s['x']) for r in rows]


def attach_subrows(rows, screen_h, row_caps):
    """A row directly below another, with every screen x-overlapping some screen
    of that row (dialog cards, detail popups under their parent), is an ATTACHED
    sub-row, not an independent swim lane. A row carrying its own left caption
    is an independent lane by declaration and is never attached.
    Returns {row_index: parent_index}."""
    attached = {}
    for i, row in enumerate(rows):
        if i == 0 or row_caps.get(i):
            continue
        parents = set()
        ok = True
        for s in row:
            hit = None
            for j in range(i - 1, -1, -1):
                if j in attached and attached[j] != j:
                    continue
                for p in rows[j]:
                    if overlap(s['x'], s['x'] + s['w'], p['x'], p['x'] + p['w']) \
                       >= 0.5 * s['w'] and \
                       0 <= s['y'] - (p['y'] + p['h']) <= screen_h * 1.2:
                        hit = j
                        break
                if hit is not None:
                    break
            if hit is None:
                ok = False
                break
            parents.add(hit)
        if ok and len(parents) == 1:
            attached[i] = parents.pop()
    return attached


def row_columns(row, screen_w):
    """Vertical sub-lanes inside a row: split on x-gap > 0.6 screen width."""
    cols, cur = [], [row[0]]
    for s in row[1:]:
        prev = cur[-1]
        if s['x'] - (prev['x'] + prev['w']) > screen_w * 0.6:
            cols.append(cur); cur = [s]
        else:
            cur.append(s)
    cols.append(cur)
    return cols


# ---------------------------------------------------------------- associations

def associate(cls, screens, screen_w, screen_h):
    # chip -> nearest screen below with >=50% x-overlap
    chip_of = {}
    for ch in cls['chips']:
        best, bd = None, None
        for s in screens:
            xo = overlap(ch['x'], ch['x'] + ch['w'], s['x'], s['x'] + s['w'])
            if xo < 0.5 * min(ch['w'], s['w']):
                continue
            dy = s['y'] - (ch['y'] + ch['h'])
            if -ch['h'] <= dy <= screen_h * 0.5 and (bd is None or dy < bd):
                best, bd = s, dy
        if best:
            chip_of.setdefault(best['id'], []).append(ch)
    # container/variant boxes -> screens whose center they contain
    def contained(box):
        ids = []
        for s in screens:
            cx, cy = s['x'] + s['w'] / 2, s['y'] + s['h'] / 2
            if box['x'] <= cx <= box['x'] + box['w'] and \
               box['y'] <= cy <= box['y'] + box['h'] and s['id'] != box['id']:
                ids.append(s['id'])
        return ids
    box_members = {b['id']: contained(b) for b in cls['var_boxes'] + cls['containers']}
    return chip_of, box_members


def banner_scope(banners, screens, screen_w):
    """Assign each screen to the banner it sits under.

    Two banner levels, split per group from the data itself:
    band headers = banners spanning >= 50% of the group's screen span
    (fallback: the taller height class when two height classes exist).
    Band headers segment the group vertically; cluster headers scope by
    x-span + nearest-above, but only inside their own band segment."""
    band_of, cluster_of = {}, {}
    if not screens:
        return band_of, cluster_of
    span = max(s['x'] + s['w'] for s in screens) - min(s['x'] for s in screens)
    wide = [b for b in banners if b['w'] >= 0.5 * span and b['w'] >= screen_w * 3]
    if not wide and banners:
        hs = sorted({round(b['h']) for b in banners})
        if len(hs) > 1 and hs[-1] >= 1.5 * hs[0]:
            wide = [b for b in banners if b['h'] >= hs[-1] * 0.9]
    wide.sort(key=lambda b: b['y'])
    narrow = [b for b in banners if b not in wide]

    def segment(y):
        i = 0
        for k, b in enumerate(wide):
            if b['y'] < y:
                i = k + 1
        return i

    for s in screens:
        cy, cx = s['y'] + s['h'] / 2, s['x'] + s['w'] / 2
        seg = segment(cy)
        if seg > 0:
            band_of[s['id']] = wide[seg - 1]
        best, bd = None, None
        for b in narrow:
            if segment(b['y'] + b['h'] / 2) != seg:
                continue
            if b['x'] - screen_w * 0.2 <= cx <= b['x'] + b['w'] + screen_w * 0.2 and b['y'] < cy:
                dy = cy - b['y']
                if bd is None or dy < bd:
                    best, bd = b, dy
        if best:
            cluster_of[s['id']] = best
    return band_of, cluster_of


def caption_rows(captions, rows, screens):
    """Left row-captions: TEXT left of every screen in the group, y-overlapping a row."""
    if not screens:
        return {}
    min_x = min(s['x'] for s in screens)
    out = {}
    for i, row in enumerate(rows):
        ry0 = min(s['y'] for s in row); ry1 = max(s['y'] + s['h'] for s in row)
        for c in captions:
            if c['x'] + c['w'] <= min_x + 1 and \
               overlap(c['y'], c['y'] + c['h'], ry0, ry1) >= 0.5 * c['h']:
                out.setdefault(i, []).append(c)
    return out


# ---------------------------------------------------------------- full analysis

def analyze(path):
    """Full deterministic spatial read of one export.

    Returns dict with:
      envelope, screen_size, cls (classification lists),
      groups: [{name, id, kind, x, y, w, h, rows: [{screens, captions,
                attached_to, columns}], ...}],
      screen_meta: {screen_board_id: {chip_title, chip_status, band, cluster,
                    row_caption, group_id, group_name, attached,
                    subsection_id, subsection_name, column_key}}
    """
    d = load(path)
    page = d['nodes'][0]
    boards = collect_board_nodes(page)
    screen_w, screen_h = calibrate(boards)
    cls = classify(boards, screen_w, screen_h)

    chip_of, box_members = associate(
        {'chips': cls['chips'], 'var_boxes': cls['var_boxes'],
         'containers': cls['containers']},
        cls['screens'], screen_w, screen_h)

    # top-level group of every board entry
    sec_by_id = {b['id']: b for b in boards if b['type'] == 'SECTION'}

    def top_group(b):
        cur = b
        while cur['parent_type'] == 'SECTION':
            parent = sec_by_id.get(cur['parent_id'])
            if parent is None:
                break
            cur = parent
        return cur if cur['type'] == 'SECTION' else None

    drawable = cls['screens'] + cls['chips'] + cls['banners'] + cls['captions'] \
        + cls['var_boxes'] + cls['containers']
    loose = [b for b in drawable if top_group(b) is None]
    loose_clusters = spatial_groups(loose, gap=screen_w * 1.5) if loose else []

    groups = []
    for sec in sorted((b for b in boards if b['type'] == 'SECTION'
                       and b['parent_type'] == 'PAGE'),
                      key=lambda s: (s['y'], s['x'])):
        members = [b for b in drawable if (top_group(b) or {}).get('id') == sec['id']]
        groups.append({'name': sec['name'] or '(unnamed section)', 'id': sec['id'],
                       'kind': 'SECTION', 'x': sec['x'], 'y': sec['y'],
                       'w': sec['w'], 'h': sec['h'], 'members': members})
    for i, cl in enumerate(loose_clusters):
        x0 = min(b['x'] for b in cl); y0 = min(b['y'] for b in cl)
        x1 = max(b['x'] + b['w'] for b in cl); y1 = max(b['y'] + b['h'] for b in cl)
        has_labels = any(b.get('kind') in ('CHIP', 'BANNER', 'CAPTION') for b in cl)
        groups.append({'name': f'Loose cluster {i}', 'id': f'loose-{i}',
                       'kind': 'LOOSE', 'x': x0, 'y': y0, 'w': x1 - x0,
                       'h': y1 - y0, 'members': cl, 'has_labels': has_labels})

    screen_meta = {}
    for g in groups:
        screens = [b for b in g['members'] if b.get('kind') == 'SCREEN']
        if not screens:
            g['rows'] = []
            continue
        banners = [b for b in g['members'] if b.get('kind') == 'BANNER']
        captions = [b for b in g['members'] if b.get('kind') == 'CAPTION']
        # a screen-width TEXT that labels no screen is a row caption, not a chip
        chips_here = [b for b in g['members'] if b.get('kind') == 'CHIP']
        labelled = {c['id'] for lst in chip_of.values() for c in lst}
        captions = captions + [c for c in chips_here
                               if c['type'] == 'TEXT' and c['id'] not in labelled]

        band_of, cluster_of = banner_scope(banners, screens, screen_w)
        rows = band_rows(screens, screen_h)
        row_caps = caption_rows(captions, rows, screens)
        attached = attach_subrows(rows, screen_h, row_caps)

        g['rows'] = []
        for i, row in enumerate(rows):
            cols = row_columns(row, screen_w)
            g['rows'].append({'screens': row, 'columns': cols,
                              'captions': row_caps.get(i, []),
                              'attached_to': attached.get(i)})
            for ci, col in enumerate(cols):
                for s in col:
                    chs = chip_of.get(s['id'], [])
                    title, status = chip_struct(chs[0]['node']) if chs else ('', None)
                    sub = sec_by_id.get(s['parent_id']) \
                        if s['parent_type'] == 'SECTION' and \
                        s['parent_id'] != g['id'] else None
                    screen_meta[s['id']] = {
                        'chip_title': title, 'chip_status': status,
                        'band': deep_text(band_of[s['id']]['node'], 100)
                                if s['id'] in band_of else '',
                        'cluster': deep_text(cluster_of[s['id']]['node'], 100)
                                   if s['id'] in cluster_of else '',
                        'row_caption': ' / '.join(
                            c.get('text', '').replace('\n', ' ')
                            for c in row_caps.get(i, [])),
                        'group_id': g['id'], 'group_name': g['name'],
                        'group_kind': g['kind'],
                        'group_has_labels': g.get('has_labels', True),
                        'attached': i in attached,
                        'row_index': i, 'column_key': f"{g['id']}/r{i}/c{ci}",
                        'subsection_id': sub['id'] if sub else None,
                        'subsection_name': (sub['name'] or '') if sub else None,
                    }

    return {'envelope': {'exportedAt': d.get('exportedAt'), 'scope': d.get('scope'),
                         'file': d.get('file'), 'export': d.get('export')},
            'screen_size': (screen_w, screen_h), 'cls': cls,
            'chip_of': chip_of, 'box_members': box_members,
            'groups': groups, 'screen_meta': screen_meta}


# ---------------------------------------------------------------- digest

def main(path):
    world = analyze(path)
    screen_w, screen_h = world['screen_size']
    print(f"calibrated screen size: {screen_w}x{screen_h}")
    for k, v in world['cls'].items():
        print(f"  {k:12s}: {len(v)}")
    for g in world['groups']:
        ns = sum(1 for r in g['rows'] for _ in r['screens'])
        if not ns:
            continue
        print(f"\n=== {g['kind']} {g['name']!r} — {ns} screens, {len(g['rows'])} rows")
        for i, r in enumerate(g['rows']):
            caps = ' / '.join(c.get('text', '').replace('\n', ' ')[:30]
                              for c in r['captions']) or '-'
            att = f" ATTACHED->row{r['attached_to']}" if r['attached_to'] is not None else ''
            print(f"  row{i:2d} y={min(s['y'] for s in r['screens']):>7.0f} "
                  f"caption[{caps[:36]:36s}] cols={[len(c) for c in r['columns']]}{att}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('usage: spatial_scan.py <export.json>')
    main(sys.argv[1])
