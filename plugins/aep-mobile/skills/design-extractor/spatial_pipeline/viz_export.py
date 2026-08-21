#!/usr/bin/env python3
"""Emit viz_data.json: board replica (groups, screens, chips, banners, boxes)
+ resolved flow edges, for the HTML verification artifact."""

import json
import sys
from collections import defaultdict

import spatial_scan as sp


def main(path, edges_path, out_path):
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
                items.append({'k': 'SCREEN', 'id': b['id'], 'x': b['x'], 'y': b['y'],
                              'w': b['w'], 'h': b['h'],
                              't': chip_label.get(b['id'], b['name'])[:60],
                              'n': b['name'][:40]})
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

    out = {'screen_size': [screen_w, screen_h],
           'stats': fe['stats'], 'groups': out_groups,
           'edges': edges, 'unresolved': unresolved}
    with open(out_path, 'w') as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"groups={len(out_groups)} edges={len(edges)} "
          f"unresolved={len(unresolved)} bytes={len(json.dumps(out))}")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit('usage: viz_export.py <export.json> <flow_edges.json> [viz_data.json]')
    main(sys.argv[1], sys.argv[2],
         sys.argv[3] if len(sys.argv) > 3 else 'viz_data.json')
