#!/usr/bin/env python3
"""Connector + prototype-reaction resolution on top of spatial_scan.

Every FigJam connector endpoint / reaction destination is resolved to a SCREEN:
  endpoint is the screen itself        -> that screen
  endpoint is a layer inside a screen  -> that screen + the layer as trigger element
  endpoint is a label chip             -> the screen the chip labels
  endpoint is a caption/banner/decor   -> UNRESOLVED (reported, never guessed)

Direction comes from arrowhead stroke caps, not draw order.
Output: flow_edges.json (edges + unresolved + stats).
"""

import json
import sys
from collections import Counter

import spatial_scan as sp


def build_world(path):
    d = sp.load(path)
    page = d['nodes'][0]
    boards = sp.collect_board_nodes(page)
    screen_w, screen_h = sp.calibrate(boards)
    cls = sp.classify(boards, screen_w, screen_h)

    # ownership: any descendant id -> its board node (sections excluded: their
    # children are board nodes themselves)
    own = {}
    for b in boards:
        if b['type'] == 'SECTION':
            own[b['id']] = b
            continue
        def mark(n):
            own[n['id']] = b
            for c in n.get('children', []):
                mark(c)
        mark(b['node'])

    # global chip -> screen map (association is local geometry, grouping-free)
    chip_of, box_members = sp.associate(
        {'chips': cls['chips'], 'var_boxes': cls['var_boxes'],
         'containers': cls['containers']},
        cls['screens'], screen_w, screen_h)
    screen_of_chip = {}
    for sid, chs in chip_of.items():
        for ch in chs:
            screen_of_chip[ch['id']] = sid
    screens_by_id = {s['id']: s for s in cls['screens']}
    world = {'box_members': box_members, 'screen_h': screen_h}
    return d, page, boards, cls, own, screen_of_chip, screens_by_id, \
        screen_w, screen_h, world


def resolve_endpoint(node_id, own, screen_of_chip, screens_by_id, world=None):
    """-> (screen_board | None, via, trigger_node_id | None)"""
    b = own.get(node_id)
    if b is None:
        return None, 'MISSING_NODE', None
    kind = b.get('kind', b['type'])
    if kind == 'SCREEN':
        trig = node_id if node_id != b['id'] else None
        return b, 'SCREEN' if trig is None else 'ELEMENT_IN_SCREEN', trig
    if kind == 'CHIP':
        sid = screen_of_chip.get(b['id'])
        if sid:
            return screens_by_id[sid], 'CHIP_LABEL', None
        # a screen-shaped text artifact labelling nothing (notification mock,
        # toast) is a node in its own right, not a failure
        if b.get('text'):
            return b, 'ARTIFACT', None
        return None, 'CHIP_UNLABELLED', None
    if world:
        # dashed variant box -> the screen(s) it encloses
        if b['id'] in world['box_members'] and world['box_members'][b['id']]:
            sid = world['box_members'][b['id']][0]
            return screens_by_id[sid], 'VARIANT_BOX', None
        # banner -> the screens it fronts: below it, inside its x-span. Same
        # ≤8 cap as sections — a lane header over a whole band pins nothing.
        if kind == 'BANNER' and world.get('screen_h'):
            sh = world['screen_h']
            under = [s for s in screens_by_id.values()
                     if b['x'] - 0.2 * b['h'] <= s['x'] + s['w'] / 2
                     <= b['x'] + b['w'] + 0.2 * b['h']
                     and b['y'] <= s['y'] <= b['y'] + b['h'] + 6 * sh]
            if under and len(under) <= 8:
                entry = min(under, key=lambda s: (s['y'], s['x']))
                return entry, 'BANNER_SCOPE', None
            if under:
                return None, f'BANNER_AMBIGUOUS({b.get("text","")[:40]}, ' \
                             f'{len(under)} screens)', None
        # (sub)section -> its entry screen, but only when the section is small
        # enough that "this group" pins down a screen. A connector attached to a
        # 100-screen section carries no per-screen information — the export has
        # no attachment position on section endpoints, so resolving one would
        # fabricate a source/destination (caught on MPS 10882:10702).
        if kind == 'SECTION':
            inside = [s for s in screens_by_id.values()
                      if b['x'] <= s['x'] + s['w'] / 2 <= b['x'] + b['w']
                      and b['y'] <= s['y'] + s['h'] / 2 <= b['y'] + b['h']]
            if inside and len(inside) <= 8:
                entry = min(inside, key=lambda s: (s['y'], s['x']))
                return entry, 'SECTION_ENTRY', None
            if inside:
                return None, f'SECTION_AMBIGUOUS({b["name"] or "unnamed"}, ' \
                             f'{len(inside)} screens)', None
    return None, f'NON_SCREEN:{kind}', None


def arrow_direction(conn):
    def is_arrow(cap):
        return cap and cap.startswith('ARROW')
    s, e = conn.get('connectorStartStrokeCap'), conn.get('connectorEndStrokeCap')
    if is_arrow(e) and not is_arrow(s):
        return 'FORWARD'
    if is_arrow(s) and not is_arrow(e):
        return 'REVERSED'
    if is_arrow(s) and is_arrow(e):
        return 'AMBIGUOUS'
    return 'UNDIRECTED'


def screen_label(b, screen_of_chip_inv):
    labels = screen_of_chip_inv.get(b['id'])
    if labels:
        return labels[0]
    if b.get('kind') == 'CHIP' and b.get('text'):
        return b['text'][:60]
    return b['name']


def main(path, out_path):
    d, page, boards, cls, own, screen_of_chip, screens_by_id, \
        screen_w, screen_h, world = build_world(path)

    # invert chip map for display labels
    inv = {}
    for chid, sid in screen_of_chip.items():
        ch = next(c for c in cls['chips'] if c['id'] == chid)
        inv.setdefault(sid, []).append(sp.deep_text(ch['node'], 80))

    edges, unresolved = [], []

    # --- connectors
    conns = [n for n, *_ in sp.walk_abs(page) if n['type'] == 'CONNECTOR']
    for c in conns:
        a_id = (c.get('connectorStart') or {}).get('endpointNodeId')
        b_id = (c.get('connectorEnd') or {}).get('endpointNodeId')
        A, via_a, trig_a = resolve_endpoint(a_id, own, screen_of_chip, screens_by_id,
                                            world) if a_id else (None, 'FLOATING', None)
        B, via_b, trig_b = resolve_endpoint(b_id, own, screen_of_chip, screens_by_id,
                                            world) if b_id else (None, 'FLOATING', None)
        direction = arrow_direction(c)
        label = (c.get('text') or {}).get('characters', '').strip()

        if A and B and A['id'] != B['id']:
            if direction == 'REVERSED':
                A, B, trig_a, trig_b, via_a, via_b = B, A, trig_b, trig_a, via_b, via_a
            edges.append({
                'kind': 'CONNECTOR',
                'relation': 'VARIANT_LINK' if 'VARIANT_BOX' in (via_a, via_b)
                            else 'NAVIGATION',
                'connector_id': c['id'],
                'from_screen': A['id'], 'from_label': screen_label(A, inv),
                'to_screen': B['id'], 'to_label': screen_label(B, inv),
                'trigger_node_id': trig_a,
                'condition': label,
                'direction': direction,
                'from_via': via_a, 'to_via': via_b,
            })
        else:
            unresolved.append({
                'kind': 'CONNECTOR', 'connector_id': c['id'],
                'condition': label, 'direction': direction,
                'start': {'node_id': a_id, 'via': via_a,
                          'board': A['id'] if A else None,
                          'board_name': (own.get(a_id) or {}).get('name'),
                          'text': sp.deep_text(own[a_id]['node'], 60) if a_id in own else None},
                'end': {'node_id': b_id, 'via': via_b,
                        'board': B['id'] if B else None,
                        'board_name': (own.get(b_id) or {}).get('name'),
                        'text': sp.deep_text(own[b_id]['node'], 60) if b_id in own else None},
                'reason': 'SELF_LOOP' if (A and B and A['id'] == B['id'])
                          else f'start={via_a} end={via_b}',
            })

    # --- prototype reactions
    def walk_reactions(n):
        yield from ((n, r) for r in n.get('reactions', []))
        for ch in n.get('children', []):
            yield from walk_reactions(ch)

    for n, r in walk_reactions(page):
        acts = r.get('actions') or ([r['action']] if r.get('action') else [])
        for act in acts:
            dest = act.get('destinationId')
            if not dest:
                continue
            src_b = own.get(n['id'])
            A = src_b if src_b and src_b.get('kind') == 'SCREEN' else None
            Bb, via_b, _ = resolve_endpoint(dest, own, screen_of_chip, screens_by_id,
                                            world)
            trigger = (r.get('trigger') or {}).get('type', '')
            if A and Bb and A['id'] != Bb['id']:
                edges.append({
                    'kind': 'REACTION',
                    'source_node_id': n['id'],
                    'from_screen': A['id'], 'from_label': screen_label(A, inv),
                    'to_screen': Bb['id'], 'to_label': screen_label(Bb, inv),
                    'trigger_node_id': n['id'] if n['id'] != A['id'] else None,
                    'trigger': trigger,
                    'condition': '',
                    'navigation': act.get('navigation', ''),
                    'from_via': 'SCREEN', 'to_via': via_b,
                })
            else:
                unresolved.append({
                    'kind': 'REACTION', 'source_node_id': n['id'],
                    'source_name': n.get('name'), 'trigger': trigger,
                    'destination_id': dest,
                    'reason': 'SELF_LOOP' if (A and Bb and A['id'] == Bb['id'])
                              else ('SOURCE_NOT_IN_SCREEN' if not A else f'dest={via_b}'),
                })

    # dedupe identical reaction edges (variants repeat the same wiring)
    seen, deduped = set(), []
    for e in edges:
        key = (e['from_screen'], e['to_screen'], e.get('trigger_node_id'),
               e['condition'], e['kind'])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)

    stats = {
        'connectors_total': len(conns),
        'reaction_actions_with_destination':
            sum(1 for e in edges if e['kind'] == 'REACTION')
            + sum(1 for u in unresolved if u['kind'] == 'REACTION'),
        'edges_resolved': len(deduped),
        'edges_connector': sum(1 for e in deduped if e['kind'] == 'CONNECTOR'),
        'edges_reaction': sum(1 for e in deduped if e['kind'] == 'REACTION'),
        'unresolved': len(unresolved),
        'unresolved_reasons': Counter(u['reason'].split(' ')[0] if ' ' in u['reason']
                                      else u['reason'] for u in unresolved).most_common(),
        'direction_mix': Counter(e.get('direction', 'n/a') for e in deduped
                                 if e['kind'] == 'CONNECTOR').most_common(),
        'labelled_conditions': sum(1 for e in deduped if e['condition']),
    }

    with open(out_path, 'w') as f:
        json.dump({'stats': stats, 'edges': deduped, 'unresolved': unresolved},
                  f, indent=1, ensure_ascii=False)

    print(json.dumps(stats, indent=1, ensure_ascii=False))
    print('\nsample edges:')
    for e in deduped[:12]:
        cond = f"  [{e['condition']}]" if e['condition'] else ''
        print(f"  {e['kind'][:4]} {e['from_label'][:34]!r} -> {e['to_label'][:34]!r}"
              f"{cond} via {e['from_via']}/{e['to_via']}")
    print('\nsample unresolved:')
    for u in unresolved[:8]:
        print(' ', json.dumps(u, ensure_ascii=False)[:160])


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('usage: connector_resolve.py <export.json> [flow_edges.json]')
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'flow_edges.json')
