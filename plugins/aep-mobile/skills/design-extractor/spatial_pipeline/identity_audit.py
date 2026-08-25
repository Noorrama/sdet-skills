#!/usr/bin/env python3
"""Read-only identity-contest audit — P0 of the collapse-disambiguation work.

Phase A gives a multi-frame proto its FRAME NAME as identity and then merges
every proto sharing that name across the whole board. When a team reuses a
generic frame name ("Landing", "MPS") for screens that belong to different
flows, that merge is wrong: one screen ends up holding several distinct
screens' frames, states, and elements.

This script changes nothing. It measures the problem and SIMULATES the
proposed discriminator ladder so the ladder can be tuned on evidence before
any collapse code is touched:

  contested base = a screen whose collapsed frames span more than one flow
                   cluster or more than one group

  per frame, the ladder picks the first rung that applies:
    SPEC      frame carries no chip and no cluster inside a label-less or
              loose group (component specs, asset dumps, draft clusters)
    L0_STATE  chip starts with the base name ("MPS - Scroll") or reads as a
              state word ("Loading") -> same screen, chip is a state
    L1_CHIP   chip is an unprefixed, non-state title ("GoFood history")
              -> that chip title is the real screen identity
    L2_CLUSTER / L3_BAND / L4_GROUP
              no chip to go on: scope the base by the finest non-empty
              spatial label the frame sits under
    UNRESOLVED nothing separates it -> would stay merged and be escalated

Also reports lane-replica candidates: (band, cluster) lanes whose identity
sets overlap by Jaccard >= 0.5, i.e. the same screens redrawn under a
different precondition. Those must NEVER be split (they are scenario
variants) and are the guard-rail case for the L2+ rungs.

Usage: identity_audit.py <export.json> [--out <audit.json>] [--app <app_id>]
       identity_audit.py --batch <board1.json> <board2.json> ...
"""

import json
import os
import re
import sys
from collections import defaultdict

import phase_a
import spatial_scan as sp

# A chip that reads as a state, not as a screen name. phase_a.state_kind
# covers the enum-mapped words; these are the board dialect extras seen on
# the validated boards (chips like "Scroll", "Expanded", "Tooltip").
STATEISH = re.compile(
    r'\b(scroll|shimmer|skeleton|typing|keyboard|expanded|collapsed|tooltip|'
    r'pagination|variant|non variant|entry point|1st time|first time)\b', re.I)
CONDITIONAL = re.compile(r'^\s*(when|if|with|without|after|before)\b', re.I)


def norm(s):
    return re.sub(r'\s+', ' ', (s or '')).strip()


def is_state_chip(chip, base):
    """Chip that qualifies the base screen rather than naming a new one."""
    c = norm(chip)
    if not c:
        return True                                   # nothing to go on
    if c.lower().startswith(base.lower()):
        return True                                   # "MPS - Scroll"
    if phase_a.state_kind(c) != 'OTHER':
        return True                                   # Loading / Empty / EN
    if STATEISH.search(c) or CONDITIONAL.match(c):
        return True
    return False


def scope_of(m):
    """Finest non-empty spatial label the frame sits under, with its rung."""
    if norm(m['cluster']):
        return 'L2_CLUSTER', norm(m['cluster'])
    if norm(m['band']):
        return 'L3_BAND', norm(m['band'])
    if norm(m['group_name']) and m['group_kind'] != 'LOOSE':
        return 'L4_GROUP', norm(m['group_name'])
    return 'UNRESOLVED', ''


CONTROL_NAME = re.compile(
    r'button|btn|cta|field|input|search bar|toggle|switch|tab|checkbox|radio|'
    r'chip|dropdown|select|link|cell|row item|list item', re.I)


def control_labels(node, cap=4000):
    """The frame's CONTROL SET: visible text of every interactive layer —
    components whose name reads as a control, plus anything carrying a
    prototype reaction. This is what a test actually targets, and it is the
    only fingerprint that matched the design team's own same/different calls:
    full-text similarity measures background chrome (0.70 between two
    genuinely different screens) and component-name similarity measures the
    design system (1.00 between two unrelated dialogs)."""
    out, stack, seen = set(), [node], 0
    while stack and seen < cap:
        n = stack.pop()
        seen += 1
        nm = norm(n.get('name'))
        interactive = (n.get('type') in ('INSTANCE', 'COMPONENT')
                       and CONTROL_NAME.search(nm)) or n.get('reactions')
        if interactive:
            t = norm(sp.deep_text(n, 40)).lower()
            if t and len(t) <= 40:
                out.add(t)
        stack.extend(n.get('children') or ())
    return out


def fingerprint(node, cap=1200):
    """Visible text of the whole frame — kept for the diagnostic comparison
    against control_labels, never as the split gate."""
    texts, inst = set(), set()
    stack, seen = [node], 0
    while stack and seen < cap:
        n = stack.pop()
        seen += 1
        if n.get('type') in ('INSTANCE', 'COMPONENT'):
            nm = norm(n.get('name'))
            if nm:
                inst.add(nm.lower())
        ch = norm(n.get('characters'))
        if ch and len(ch) <= 60:
            texts.add(ch.lower())
        stack.extend(n.get('children') or ())
    return texts or inst


def representative(frames, node_of):
    """Deterministic per-bucket sample: the frame carrying the most content."""
    return max(frames, key=lambda r: (len(fingerprint(node_of[r])), r))


def jaccard(a, b):
    return len(a & b) / len(a | b) if (a or b) else 1.0


def single_linkage(keys, sim, threshold):
    """Merge buckets transitively while similarity >= threshold. Returns list
    of merged key-groups, deterministic in input order."""
    parent = {k: k for k in keys}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if sim.get((a, b), 0.0) >= threshold:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    out = defaultdict(list)
    for k in keys:
        out[find(k)].append(k)
    return list(out.values())



def connector_frames(path):
    """[(frame_a_id, frame_b_id)] for every connector whose both endpoints
    resolve to a board frame, plus the set of frames any connector touches."""
    (_, page, boards, cls, own, screen_of_chip, screens_by_id,
     _sw, _sh, cworld) = phase_a.cr.build_world(path)
    pairs, touched = [], set()
    for c in [n for n, *_ in sp.walk_abs(page) if n['type'] == 'CONNECTOR']:
        a = (c.get('connectorStart') or {}).get('endpointNodeId')
        b = (c.get('connectorEnd') or {}).get('endpointNodeId')
        A = phase_a.cr.resolve_endpoint(a, own, screen_of_chip, screens_by_id,
                                        cworld)[0] if a else None
        B = phase_a.cr.resolve_endpoint(b, own, screen_of_chip, screens_by_id,
                                        cworld)[0] if b else None
        for X in (A, B):
            if X:
                touched.add(X['id'])
        if A and B:
            pairs.append((A['id'], B['id'], c['id']))
    return pairs, touched


def audit(path, app=None):
    context, report = phase_a.build(path, app=app)
    world = sp.analyze(path)
    meta = world['screen_meta']
    node_of = {}
    for g in world['groups']:
        for r in g['rows']:
            for s in r['screens']:
                node_of[s['id']] = s.get('node', s)
    pairs, touched = connector_frames(path)

    # a group nothing points at and nothing labels is spec/asset material
    group_flow, group_chips = defaultdict(bool), defaultdict(bool)
    for fid, m in meta.items():
        if fid in touched:
            group_flow[m['group_id']] = True
        if norm(m['chip_title']):
            group_chips[m['group_id']] = True

    def is_spec(m):
        return not group_flow[m['group_id']] and not group_chips[m['group_id']]

    # ---- lane replica candidates (the never-split guard)
    lane_ids = defaultdict(set)
    for s in context['screens']:
        for fid in s.get('source_refs', []):
            m = meta.get(fid)
            if not m:
                continue
            lane_ids[(norm(m['band']), norm(m['cluster']))].add(s['screen_id'])
    lanes = [(k, v) for k, v in lane_ids.items() if len(v) >= 2 and any(k)]
    replicas = []
    for i in range(len(lanes)):
        for j in range(i + 1, len(lanes)):
            a, b = lanes[i][1], lanes[j][1]
            jac = len(a & b) / len(a | b)
            if jac >= 0.5:
                replicas.append(dict(lane_a=list(lanes[i][0]),
                                     lane_b=list(lanes[j][0]),
                                     jaccard=round(jac, 2),
                                     shared=sorted(a & b)[:8]))
    replicas.sort(key=lambda r: -r['jaccard'])

    # ---- self-loop context: connectors phase_a demoted to state
    # transitions because both endpoints collapsed into one screen. Split by
    # whether the two frames sit in the same flow context or not — a
    # cross-context pair is a navigation edge the merge swallowed.
    frame_sid = {}
    for s in context['screens']:
        for fid in s.get('source_refs', []):
            frame_sid[fid] = s['screen_id']
    loops = defaultdict(list)
    for a, b, cid in pairs:
        if frame_sid.get(a) and frame_sid.get(a) == frame_sid.get(b) and a != b:
            ma, mb = meta.get(a), meta.get(b)
            if not ma or not mb:
                continue
            if norm(ma['cluster']) != norm(mb['cluster']):
                kind = 'CROSS_CLUSTER'
            elif norm(ma['band']) != norm(mb['band']):
                kind = 'CROSS_BAND'
            elif ma['column_key'] != mb['column_key']:
                kind = 'CROSS_COLUMN'
            else:
                kind = 'SAME_COLUMN'
            loops[kind].append(dict(screen_id=frame_sid[a], connector_id=cid,
                                    frames=[a, b],
                                    contexts=[norm(ma['cluster']) or norm(ma['band']),
                                              norm(mb['cluster']) or norm(mb['band'])]))

    # ---- contested bases + the two candidate split policies
    contested, counters = [], defaultdict(int)
    for s in context['screens']:
        refs = [r for r in s.get('source_refs', []) if r in meta]
        if len(refs) < 2:
            continue
        groups = {norm(meta[r]['group_name']) for r in refs}
        clusters = {norm(meta[r]['cluster']) for r in refs}
        if len(groups) < 2 and len(clusters) < 2:
            continue
        base = s['screen_name']
        spec = [r for r in refs if is_spec(meta[r])]
        flow = [r for r in refs if r not in set(spec)]

        # POLICY_SCOPE: split by finest spatial label; name a bucket after its
        # chip when the bucket's chips agree on one unprefixed, non-state title
        scope_buckets = defaultdict(list)
        for r in flow:
            rung, key = scope_of(meta[r])
            scope_buckets[(rung, key)].append(r)
        scope_out = []
        for (rung, key), rs in sorted(scope_buckets.items(),
                                      key=lambda kv: -len(kv[1])):
            chips = {norm(meta[r]['chip_title']) for r in rs
                     if not is_state_chip(meta[r]['chip_title'], base)}
            if len(chips) == 1:
                pid = phase_a.upper_snake(chips.pop())
                named = 'CHIP'
            elif len(scope_buckets) == 1:
                pid, named = s['screen_id'], 'BASE'
            else:
                pid = f"{s['screen_id']}__{phase_a.upper_snake(key)}" if key \
                    else s['screen_id']
                named = 'SCOPE'
            scope_out.append(dict(proposed_id=pid, rung=rung, named_by=named,
                                  frames=len(rs), label=key,
                                  sample_refs=sorted(rs)[:4]))
            counters[f'scope_{rung}'] += len(rs)

        # POLICY_CONTENT: scope buckets whose CONTENT agrees are the same
        # screen under a different precondition; only content-divergent
        # buckets are genuinely different screens. Threshold swept, not fixed.
        keys = sorted(scope_buckets, key=lambda k: (-len(scope_buckets[k]), k))
        fps = {k: fingerprint(node_of[representative(scope_buckets[k], node_of)])
               for k in keys}
        sim = {}
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                sim[(a, b)] = round(jaccard(fps[a], fps[b]), 3)
        content_screens = {f'T{int(t * 100)}': len(single_linkage(keys, sim, t))
                           for t in (0.4, 0.5, 0.6, 0.7, 0.8)}

        # POLICY_CONTROL: cluster the FRAMES themselves (scope ignored) by
        # control-set similarity, single-linkage. Frame-level because the
        # design team's calls cross cluster boundaries in both directions:
        # two frames in different clusters can be one screen, and two frames
        # in one cluster can be different screens.
        ctrl = {r: control_labels(node_of[r]) for r in flow}
        ctrl_cov = sum(1 for v in ctrl.values() if v)
        fkeys = sorted(flow)
        fsim = {}
        for i, x in enumerate(fkeys):
            for y in fkeys[i + 1:]:
                fsim[(x, y)] = round(jaccard(ctrl[x], ctrl[y]), 3)
        control_screens = {f'C{int(t * 100)}':
                           len(single_linkage(fkeys, fsim, t))
                           for t in (0.2, 0.3, 0.4, 0.5, 0.6)}

        # POLICY_CHIP: any unprefixed, non-state chip is its own screen
        chip_buckets = defaultdict(list)
        for r in flow:
            t = norm(meta[r]['chip_title'])
            chip_buckets[('BASE', '') if is_state_chip(t, base)
                         else ('CHIP', t)].append(r)

        contested.append(dict(
            screen_id=s['screen_id'], screen_name=base, frames=len(refs),
            states=len(s.get('screen_states', [])),
            elements=len(s.get('elements', [])),
            distinct=dict(groups=len(groups), clusters=len(clusters),
                          bands=len({norm(meta[r]['band']) for r in refs}),
                          chips=len({norm(meta[r]['chip_title']) for r in refs}),
                          columns=len({meta[r]['column_key'] for r in refs})),
            spec_frames=len(spec),
            policy_scope_screens=len(scope_out),
            policy_chip_screens=len(chip_buckets),
            policy_content_screens=content_screens,
            policy_control_screens=control_screens,
            control_coverage=[ctrl_cov, len(flow)],
            control_sim_spread=dict(
                min=min(fsim.values()) if fsim else None,
                median=(sorted(fsim.values())[len(fsim) // 2] if fsim else None),
                max=max(fsim.values()) if fsim else None),
            bucket_similarity=dict(
                pairs=len(sim),
                min=min(sim.values()) if sim else None,
                median=(sorted(sim.values())[len(sim) // 2] if sim else None),
                max=max(sim.values()) if sim else None),
            bucket_similarity_detail=[
                dict(a=a[1] or a[0], b=b[1] or b[0], jaccard=v)
                for (a, b), v in sorted(sim.items(), key=lambda kv: kv[1])[:6]],
            unresolved=any(b['rung'] == 'UNRESOLVED' for b in scope_out),
            proposed_scope=scope_out))
        counters['spec'] += len(spec)
    contested.sort(key=lambda c: -c['frames'])

    def projected(field):
        return (len(context['screens']) - len(contested)
                + sum(c[field] for c in contested))

    return dict(
        board=os.path.basename(path),
        envelope=dict(file_name=(world['envelope'].get('file') or {}).get('name'),
                      nodes=(world['envelope'].get('export') or {}).get('nodeCount')),
        screens_total=len(context['screens']),
        edges_total=len(context['ui_flow']),
        contested_count=len(contested),
        contested_frames=sum(c['frames'] for c in contested),
        spec_frames=counters['spec'],
        projected_screens=dict(
            today=len(context['screens']),
            policy_scope=projected('policy_scope_screens'),
            policy_chip=projected('policy_chip_screens'),
            policy_content={t: (len(context['screens']) - len(contested)
                                + sum(c['policy_content_screens'][t]
                                      for c in contested))
                            for t in ('T40', 'T50', 'T60', 'T70', 'T80')},
            policy_control={t: (len(context['screens']) - len(contested)
                                + sum(c['policy_control_screens'][t]
                                      for c in contested))
                            for t in ('C20', 'C30', 'C40', 'C50', 'C60')}),
        control_coverage=[sum(c['control_coverage'][0] for c in contested),
                          sum(c['control_coverage'][1] for c in contested)],
        swallowed_edges={k: len(v) for k, v in sorted(loops.items())},
        swallowed_edge_samples=(loops.get('CROSS_CLUSTER', [])
                                + loops.get('CROSS_BAND', []))[:12],
        unresolved_bases=[c['screen_id'] for c in contested if c['unresolved']],
        scope_rung_frames={k: v for k, v in sorted(counters.items())
                           if k.startswith('scope_')},
        lane_replica_candidates=replicas[:20],
        contested=contested)


def digest(a):
    p = a['projected_screens']
    print(f"════ {a['board']}  ({a['envelope']['nodes']} nodes)  "
          f"screens={a['screens_total']} edges={a['edges_total']}")
    print(f"  contested {a['contested_count']} bases / "
          f"{a['contested_frames']} frames · spec-material {a['spec_frames']} "
          f"frames")
    print(f"  projected screens: today {p['today']} · "
          f"POLICY_SCOPE {p['policy_scope']} · POLICY_CHIP {p['policy_chip']}")
    print(f"  POLICY_CONTENT (all text) by threshold: {p['policy_content']}")
    print(f"  POLICY_CONTROL (control set) by threshold: {p['policy_control']}"
          f"  coverage {a['control_coverage'][0]}/{a['control_coverage'][1]} frames")
    print(f"  swallowed edges (same screen after collapse): "
          f"{a['swallowed_edges'] or '{}'}")
    print(f"  scope rungs {a['scope_rung_frames']}")
    if a['unresolved_bases']:
        print(f"  UNRESOLVED bases: {', '.join(a['unresolved_bases'])}")
    print(f"  lane replica candidates: {len(a['lane_replica_candidates'])}")
    for c in a['contested'][:6]:
        print(f"    {c['screen_id']:26s} {c['frames']:3d}f  "
              f"scope->{c['policy_scope_screens']:2d} chip->"
              f"{c['policy_chip_screens']:2d} control{c['policy_control_screens']}"
              f"  J[{c['bucket_similarity']['min']}..{c['bucket_similarity']['max']}]  "
              + ', '.join(f"{b['proposed_id']}×{b['frames']}"
                          f"[{b['named_by']}]" for b in c['proposed_scope'][:4]))



def check_labels(labels_path, board_dir):
    """Regression gate: replay the design team's same/different calls through
    the real screen_identity.split_frames used by phase_a. Prints one line per
    label; exit code is non-zero on any mismatch."""
    import phase_a
    import screen_identity as si
    spec = json.load(open(labels_path))
    by_board = defaultdict(list)
    for lab in spec['labels']:
        by_board[lab['board']].append(lab)
    fails = 0
    for board, labs in sorted(by_board.items()):
        path = os.path.join(board_dir, board)
        context, report = phase_a.build(path)
        world = sp.analyze(path)
        meta = world['screen_meta']
        node_of = {}
        for g in world['groups']:
            for r in g['rows']:
                for s in r['screens']:
                    node_of[s['id']] = s.get('node', s)
        sid_of = {r: s['screen_id'] for s in context['screens']
                  for r in s.get('source_refs', [])}
        for lab in labs:
            a, b = lab['a'], lab['b']
            got = sid_of.get(a) == sid_of.get(b) and sid_of.get(a) is not None
            ok = got == lab['same']
            fails += not ok
            print(f"  {'PASS' if ok else 'FAIL'}  {board[:28]:28s} {a} / {b}  "
                  f"expected {'SAME' if lab['same'] else 'DIFFERENT':9s} "
                  f"got {'SAME' if got else 'DIFFERENT'} "
                  f"[{sid_of.get(a)} / {sid_of.get(b)}]")
    print(f"\n{len(spec['labels']) - fails}/{len(spec['labels'])} labels reproduced")
    return fails


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    out = None
    if '--out' in args:
        i = args.index('--out')
        out = args[i + 1]
        del args[i:i + 2]
    app = None
    if '--app' in args:
        i = args.index('--app')
        app = args[i + 1]
        del args[i:i + 2]
    if args and args[0] == '--check-labels':
        labels = args[1] if len(args) > 1 else os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'identity_labels.json')
        board_dir = args[2] if len(args) > 2 else os.path.expanduser('~/Downloads')
        sys.exit(1 if check_labels(labels, board_dir) else 0)

    batch = args[0] == '--batch'
    paths = args[1:] if batch else args[:1]

    results = []
    for p in paths:
        try:
            a = audit(p, app=app)
        except Exception as ex:
            print(f"════ {os.path.basename(p)}  FAILED — {str(ex)[:200]}")
            continue
        results.append(a)
        digest(a)
    if out:
        with open(out, 'w') as f:
            json.dump(results if batch else results[0], f, indent=1,
                      ensure_ascii=False)
        print(f"\nwrote {out}")


if __name__ == '__main__':
    main()
