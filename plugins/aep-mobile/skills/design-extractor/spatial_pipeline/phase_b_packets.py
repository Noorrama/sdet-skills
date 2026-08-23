#!/usr/bin/env python3
"""Phase B packet builder.

Phase B is the constrained LLM pass: it enriches the Phase A skeleton (element
labels/roles, validations from designer notes, state_kind for OTHER states,
per-screen ambiguity) but may not invent structure. To keep it grounded, each
screen gets a packet holding ONLY what the LLM may cite:

  candidates[]  - layers inside the screen's frames an element may bind to
                  (id, name, type, text, component variants); element source_ref
                  MUST come from this list. Candidates repeating the same
                  (name, type, text) across a screen's state-variant frames are
                  collapsed to the first instance (instance_count says how
                  many), and each carries a deterministic suggested_purpose
                  derived from its own text/name, uniquified within the screen
                  - the enrichment model should copy it unless it has a clearly
                  more specific name
  notes[]       - caption/annotation texts spatially adjacent to the screen's
                  frames (within one screen-width), verbatim
  states, existing elements, edges touching the screen

Output: phase_b_packets.jsonl (one packet per screen, flow-relevant first).
"""

import json
import re
import sys

import spatial_scan as sp


def lower_snake(s):
    s = re.sub(r'[^0-9A-Za-z]+', '_', s).strip('_')
    return re.sub(r'_+', '_', s).lower()


def dedupe_and_suggest(cands):
    """Collapse candidates repeating the same (name, type, text) — the same
    control drawn again in another state-variant frame — and stamp each
    survivor with a deterministic, screen-unique suggested_purpose derived
    from its own text/name. Keeps input order, so output is reproducible."""
    out, by_key, taken = [], {}, {}
    for c in cands:
        key = (c.get('name', ''), c['type'], c.get('text', ''))
        if key in by_key:
            by_key[key]['instance_count'] = \
                by_key[key].get('instance_count', 1) + 1
            continue
        base = lower_snake(c.get('text') or c.get('name') or '')[:36]
        if base:
            n = taken.get(base, 0) + 1
            taken[base] = n
            c['suggested_purpose'] = base if n == 1 else f'{base}_{n}'
        by_key[key] = c
        out.append(c)
    return out


def candidates_for(frame, screen_h, cap=40):
    out = []
    def walk(n, depth):
        if len(out) >= cap or depth > 5:
            return
        for c in n.get('children', []):
            h = c.get('height') or 0
            texty = (c.get('characters') or '').strip()
            is_control = (c['type'] == 'INSTANCE' and h <= screen_h * 0.35) or \
                         (c['type'] == 'TEXT' and texty)
            if is_control:
                entry = {'id': c['id'], 'name': c.get('name', '')[:60],
                         'type': c['type']}
                t = sp.deep_text(c, 60) if c['type'] == 'INSTANCE' else texty[:60]
                if t:
                    entry['text'] = t
                vp = c.get('variantProperties')
                if vp:
                    entry['variants'] = vp
                out.append(entry)
                if c['type'] == 'INSTANCE':
                    continue          # don't descend into component internals
            walk(c, depth + 1)
    walk(frame, 0)
    return out


def main(export_path, context_path, out_path):
    world = sp.analyze(export_path)
    screen_h = world['screen_size'][1]
    cls = world['cls']
    context = json.load(open(context_path))

    frames = {}
    for b in cls['screens'] + cls['chips']:
        frames[b['id']] = b

    notes_pool = cls['captions'] + cls['decor'] + cls['containers']

    def nearby_notes(refs, radius):
        got, seen = [], set()
        boxes = [frames[r] for r in refs if r in frames]
        for n in notes_pool:
            txt = (n.get('text') or sp.deep_text(n['node'], 300)).strip()
            if not txt or n['id'] in seen:
                continue
            for b in boxes:
                if abs((n['x'] + n['w'] / 2) - (b['x'] + b['w'] / 2)) <= radius + b['w'] \
                   and abs((n['y'] + n['h'] / 2) - (b['y'] + b['h'] / 2)) <= radius + b['h']:
                    got.append({'id': n['id'], 'text': txt[:300]})
                    seen.add(n['id'])
                    break
        return got[:12]

    edge_touch = {}
    for e in context['ui_flow']:
        for k in ('from_screen_id', 'to_screen_id'):
            edge_touch.setdefault(e[k], []).append(
                {k2: e[k2] for k2 in ('from_screen_id', 'to_screen_id',
                                      'condition', 'navigation_kind')
                 if k2 in e})

    packets = []
    radius = world['screen_size'][0] * 1.0
    for s in context['screens']:
        refs = s['source_refs']
        cands, seen_ids = [], set()
        for r in refs[:6]:                       # cap: 6 representative frames
            b = frames.get(r)
            if not b:
                continue
            for c in candidates_for(b['node'], screen_h):
                if c['id'] not in seen_ids:
                    seen_ids.add(c['id'])
                    cands.append(c)
        cands = dedupe_and_suggest(cands)
        packets.append({
            'screen_id': s['screen_id'], 'screen_name': s['screen_name'],
            'screen_states': s['screen_states'], 'state_kinds': s['state_kinds'],
            'existing_elements': [
                {'element_id': el['element_id'], 'label': el['label'],
                 'role': el.get('role'), 'source_ref': el.get('source_ref')}
                for el in s['elements']],
            'edges': edge_touch.get(s['screen_id'], [])[:12],
            'candidates': cands[:60],
            'notes': nearby_notes(refs, radius),
            'screen_notes': s['screen_notes'],
        })

    packets.sort(key=lambda p: (-len(p['edges']), -len(p['candidates'])))
    with open(out_path, 'w') as f:
        for p in packets:
            f.write(json.dumps(p, ensure_ascii=False) + '\n')
    sizes = [len(json.dumps(p)) for p in packets]
    print(f"{len(packets)} packets, {sum(sizes)//1024}KB total, "
          f"max {max(sizes)//1024}KB, {sum(1 for p in packets if p['edges'])} flow-relevant")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('usage: phase_b_packets.py <export.json> '
                 '[design_context.json] [phase_b_packets.jsonl]')
    main(sys.argv[1],
         sys.argv[2] if len(sys.argv) > 2 else 'design_context.json',
         sys.argv[3] if len(sys.argv) > 3 else 'phase_b_packets.jsonl')
