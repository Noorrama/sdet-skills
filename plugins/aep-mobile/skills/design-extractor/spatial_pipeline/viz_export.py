#!/usr/bin/env python3
"""Emit viz_data.json: board replica (groups, screens, chips, banners, boxes)
+ resolved flow edges, for the HTML verification artifact.

Optionally takes the finished design_context.json as a 4th argument: its
ENTRY pseudo-node edges then mark the entry screens' frames in the replica
(kind EXPLICIT_LABEL vs INFERRED topology, plus the entry condition), so a
reviewer can see where the flow starts without opening the JSON."""

import json
import sys
from collections import defaultdict

import spatial_scan as sp


# keep in sync with phase_a.ENTRY_RE — the explicit entry-label signal
import re
ENTRY_RE = re.compile(
    r'\bentry\s*point\b|\b(?:1st|first)\s*time\b|\bstart\s*here\b', re.I)


def entry_marks(context_path, chip_label, frame_scope):
    """(frame node id -> {'k': 'L'|'T', 'c': condition, 's': screen_id},
    entry screen count). A collapsed entry screen can span dozens of
    state-variant frames; marking them all reads as dozens of entry points,
    so only the frames carrying the entry EVIDENCE are marked — a chip whose
    title matches the entry label, or membership in a flow-cluster/persona
    banner whose text does (frame_scope: frame id -> banner texts) — falling
    back to the screen's primary frame when no frame-level evidence exists
    (topology-inferred entries always take the fallback). 'L' = ENTRY_LABEL
    (explicit designer signal), 'T' = ENTRY_TOPOLOGY (inferred)."""
    ctx = json.load(open(context_path))
    by_sid = {}
    for e in ctx.get('ui_flow', []):
        if e.get('from_screen_id') == 'ENTRY':
            by_sid[e['to_screen_id']] = {
                'k': 'T' if e.get('edge_source') == 'ENTRY_TOPOLOGY' else 'L',
                'c': e.get('condition', ''), 's': e['to_screen_id']}
    marks = {}
    for s in ctx.get('screens', []):
        m = by_sid.get(s['screen_id'])
        if not m:
            continue
        refs = [r for r in (s.get('source_refs')
                            or [s.get('source_ref')]) if r]
        labelled = [r for r in refs
                    if ENTRY_RE.search(chip_label.get(r, ''))
                    or any(ENTRY_RE.search(t)
                           for t in frame_scope.get(r, ()))]
        for r in labelled or refs[:1]:
            marks[r] = m
    return marks, len(by_sid)


def main(path, edges_path, out_path, context_path=None):
    d = sp.load(path)
    page = d['nodes'][0]
    boards = sp.collect_board_nodes(page)
    screen_w, screen_h = sp.calibrate(boards)
    cls = sp.classify(boards, screen_w, screen_h)

    chip_of, box_members = sp.associate(
        {'chips': cls['chips'], 'var_boxes': cls['var_boxes'],
         'containers': cls['containers']},
        cls['screens'], screen_w, screen_h)
    chip_label = {}
    for sid, chs in chip_of.items():
        chip_label[sid] = sp.deep_text(chs[0]['node'], 60)
    if context_path:
        meta = sp.analyze(path)['screen_meta']
        frame_scope = {fid: [t for t in (m.get('cluster'), m.get('band')) if t]
                       for fid, m in meta.items()}
        entries, entry_screens = entry_marks(context_path, chip_label,
                                             frame_scope)
    else:
        entries, entry_screens = {}, 0

    # top-level group of every board entry: nearest ancestor section chain -> page
    sec_by_id = {b['id']: b for b in boards if b['type'] == 'SECTION'}

    def top_group(b):
        cur = b
        while cur['parent_type'] == 'SECTION':
            parent = sec_by_id.get(cur['parent_id'])
            if parent is None:
                break
            cur = parent
        return cur if cur['type'] == 'SECTION' else None

    top_sections = [b for b in boards
                    if b['type'] == 'SECTION' and b['parent_type'] == 'PAGE']

    drawable = cls['screens'] + cls['chips'] + cls['banners'] + cls['captions'] \
        + cls['var_boxes'] + cls['containers']
    loose = [b for b in drawable if top_group(b) is None]
    loose_clusters = sp.spatial_groups(loose, gap=screen_w * 1.5) if loose else []

    groups = []
    for sec in sorted(top_sections, key=lambda s: -s['w'] * s['h']):
        members = [b for b in drawable if (top_group(b) or {}).get('id') == sec['id']]
        groups.append({'name': sec['name'] or '(unnamed section)',
                       'id': sec['id'], 'kind': 'SECTION',
                       'x': sec['x'], 'y': sec['y'], 'w': sec['w'], 'h': sec['h'],
                       'members': members})
    for i, cl in enumerate(sorted(loose_clusters,
                                  key=lambda c: -len([b for b in c
                                                      if b.get('kind') == 'SCREEN']))):
        x0 = min(b['x'] for b in cl); y0 = min(b['y'] for b in cl)
        x1 = max(b['x'] + b['w'] for b in cl); y1 = max(b['y'] + b['h'] for b in cl)
        groups.append({'name': f'Loose cluster {i}', 'id': f'loose-{i}',
                       'kind': 'LOOSE', 'x': x0, 'y': y0,
                       'w': x1 - x0, 'h': y1 - y0, 'members': cl})

    screen_group = {}
    out_groups = []
    for g in groups:
        items = []
        subsecs = [s for s in boards if s['type'] == 'SECTION'
                   and s['parent_type'] == 'SECTION'
                   and (top_group(s) or {}).get('id') == g['id']]
        for s in subsecs:
            items.append({'k': 'SUBSECTION', 'id': s['id'], 'x': s['x'], 'y': s['y'],
                          'w': s['w'], 'h': s['h'], 't': s['name'][:40]})
        for b in g['members']:
            k = b.get('kind')
            if k == 'SCREEN':
                screen_group[b['id']] = g['id']
                item = {'k': 'SCREEN', 'id': b['id'], 'x': b['x'], 'y': b['y'],
                        'w': b['w'], 'h': b['h'],
                        't': chip_label.get(b['id'], b['name'])[:60],
                        'n': b['name'][:40]}
                m = entries.get(b['id'])
                if m:
                    item['e'] = m['k']
                    item['es'] = m['s']
                    if m['c']:
                        item['ec'] = m['c'][:80]
                items.append(item)
            elif k == 'BANNER':
                items.append({'k': 'BANNER', 'id': b['id'], 'x': b['x'], 'y': b['y'],
                              'w': b['w'], 'h': b['h'], 't': b.get('text', '')[:70]})
            elif k == 'CAPTION':
                items.append({'k': 'CAPTION', 'id': b['id'], 'x': b['x'], 'y': b['y'],
                              'w': b['w'], 'h': b['h'], 't': b.get('text', '')[:60]})
            elif b in cls['var_boxes']:
                items.append({'k': 'VBOX', 'id': b['id'], 'x': b['x'], 'y': b['y'],
                              'w': b['w'], 'h': b['h'], 't': ''})
        out_groups.append({'name': g['name'], 'id': g['id'], 'kind': g['kind'],
                           'x': g['x'], 'y': g['y'], 'w': g['w'], 'h': g['h'],
                           'screens': sum(1 for i2 in items if i2['k'] == 'SCREEN'),
                           'items': items})

    fe = json.load(open(edges_path))
    pos = {s['id']: s for s in cls['screens']}
    for c in cls['chips']:            # ARTIFACT endpoints are chips
        pos.setdefault(c['id'], c)
    edges = []
    for e in fe['edges']:
        a, b = pos.get(e['from_screen']), pos.get(e['to_screen'])
        if not a or not b:
            continue
        edges.append({
            'g': screen_group.get(e['from_screen'])
                 or screen_group.get(e['to_screen']),
            'g2': screen_group.get(e['to_screen']),
            'x1': a['x'] + a['w'] / 2, 'y1': a['y'] + a['h'] / 2,
            'x2': b['x'] + b['w'] / 2, 'y2': b['y'] + b['h'] / 2,
            'rel': e.get('relation', 'NAVIGATION'),
            'cond': e.get('condition', ''),
            'fl': e['from_label'][:46], 'tl': e['to_label'][:46],
            'via': f"{e['from_via']}→{e['to_via']}",
            'cid': e.get('connector_id', e.get('source_node_id', '')),
        })

    unresolved = [{'id': u.get('connector_id', ''),
                   'reason': u['reason'],
                   'start': (u.get('start') or {}).get('text')
                            or (u.get('start') or {}).get('board_name') or '',
                   'end': (u.get('end') or {}).get('text')
                          or (u.get('end') or {}).get('board_name') or '',
                   'cond': u.get('condition', '')}
                  for u in fe['unresolved'] if u['kind'] == 'CONNECTOR']

    entry_frames = sum(1 for g2 in out_groups for i2 in g2['items']
                       if i2['k'] == 'SCREEN' and i2.get('e'))
    out = {'screen_size': [screen_w, screen_h],
           'stats': fe['stats'], 'groups': out_groups,
           'edges': edges, 'unresolved': unresolved,
           'entry_frames': entry_frames, 'entry_screens': entry_screens}
    with open(out_path, 'w') as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"groups={len(out_groups)} edges={len(edges)} "
          f"unresolved={len(unresolved)} entry_screens={entry_screens} "
          f"entry_frames={entry_frames} bytes={len(json.dumps(out))}")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit('usage: viz_export.py <export.json> <flow_edges.json> '
                 '[viz_data.json] [design_context.json]')
    main(sys.argv[1], sys.argv[2],
         sys.argv[3] if len(sys.argv) > 3 else 'viz_data.json',
         sys.argv[4] if len(sys.argv) > 4 else None)
