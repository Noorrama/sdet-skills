#!/usr/bin/env python3
"""Phase A: deterministic design_context skeleton from a v2 Figma export.

Consumes spatial_scan.analyze() + connector_resolve edges and emits:
  design_context.json         - schema-conformant skeleton (screens collapsed,
                                states, ui_flow, deterministic elements)
  phase_a.report.json         - every judgment call: protos, merges, state
                                transitions, variant links, exclusions,
                                unresolved endpoints, ambiguity flags

Collapse rules (user-validated on the GoFood Group Order board):
  proto-screen  = consecutive same-frame-name run inside one column
  identity      = frame name for a multi-frame proto;
                  chip title for a single-frame proto whose chip does not
                  start with the frame name; frame name otherwise
  states        = chip titles (frame-name prefix stripped), scenario sections
                  prefix their title: "<scenario> — <chip title>"
  scenario      = sub-section (or unnamed sub-section's banner) whose screens'
                  identities also exist outside it: precondition, not screens
  attached rows = overlays; their edges are OVERLAY navigation
  self-loops after collapse = state transitions, never ui_flow
"""

import json
import os
import re
import sys
from collections import defaultdict

import spatial_scan as sp
import connector_resolve as cr

PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                           '..', '..', '..'))
SCHEMA_PATH = os.path.join(PLUGIN_ROOT, 'schemas', 'design_context.schema.json')

STATUS_WORDS = {'new screen', 'changes', 'existing', 'updated', 'removed'}


def upper_snake(s):
    s = re.sub(r'[^0-9A-Za-z]+', '_', s).strip('_')
    return re.sub(r'_+', '_', s).upper() or 'UNNAMED'


def lower_snake(s):
    s = re.sub(r'[^0-9A-Za-z]+', '_', s).strip('_')
    return re.sub(r'_+', '_', s).lower() or 'element'


STATE_KIND_PATTERNS = [
    (r'\b(default|filled)\b', 'DEFAULT'), (r'\b(loading|shimmer|skeleton)\b', 'LOADING'),
    (r'\bempty\b', 'EMPTY'), (r'\b(error|failed|failure)\b', 'ERROR'),
    (r'\b(success|done|confirmed)\b', 'SUCCESS'), (r'\boffline\b', 'OFFLINE'),
    (r'\bdisabled\b', 'DISABLED'), (r'\bpermission\b', 'PERMISSION_DENIED'),
    (r'\bdark\b', 'DARK_THEME'), (r'^\s*(en|id)\s*$', 'LOCALE_VARIANT'),
    (r'\brtl\b', 'RTL'),
]


def state_kind(state):
    s = state.lower()
    for pat, kind in STATE_KIND_PATTERNS:
        if re.search(pat, s):
            return kind
    return 'OTHER'


def element_label(node, screen_h):
    """A trigger the size of a control gets its visible text; a trigger that is
    a large region gets its layer name — deep text of a region starts with the
    status bar ('9:41 …') and labels nothing."""
    name = node.get('name', '')
    generic = bool(re.fullmatch(r'(Frame|Group|Rectangle|Content|Section)[ _\d]*',
                                name or ''))
    if (node.get('height') or 0) <= screen_h * 0.35:
        return sp.deep_text(node, 60) or name
    return name if not generic else (name or 'region')


def role_for(node):
    name = (node.get('name') or '').lower()
    t = node.get('type')
    if any(k in name for k in ('button', 'btn', 'cta')):
        return 'BUTTON', '_btn'
    if any(k in name for k in ('input', 'field', 'search bar')):
        return 'INPUT', '_input'
    if 'toggle' in name or 'switch' in name:
        return 'TOGGLE', '_toggle'
    if 'tab' in name:
        return 'TAB', '_tab'
    if 'list' in name or 'cell' in name or 'card' in name:
        return 'LIST', '_list'
    if t == 'TEXT':
        return 'LABEL', '_label'
    return 'BUTTON', '_btn'   # a connector trigger is a tap target by definition


def load_app_config(app):
    """Returns (config_or_None, gap_or_None). The scripts run fine on their
    built-in role vocabulary; a missing config is reported, never fatal."""
    if not app:
        return None, None
    p = os.path.join(PLUGIN_ROOT, 'config', f'{app}.json')
    try:
        with open(p) as f:
            return json.load(f), None
    except Exception:
        return None, {
            'field': 'ENVIRONMENT',
            'reason': f'cannot read {p} — element IDs are unverified against '
                      'the app naming convention and may not join to real '
                      'locators at code-gen.',
            'action': 'run `claude plugin update aep-mobile@aep`, restart, re-run',
            'severity': 'DEGRADED'}


def build(path, app=None):
    app_cfg, cfg_gap = load_app_config(app)
    world = sp.analyze(path)
    meta = world['screen_meta']
    screen_w, screen_h = world['screen_size']

    # ---- edges from connector_resolve (same world building blocks)
    (_, page, boards, cls, own, screen_of_chip, screens_by_id,
     _sw, _sh, cworld) = cr.build_world(path)
    conns = [n for n, *_ in sp.walk_abs(page) if n['type'] == 'CONNECTOR']
    raw_edges, unresolved = [], []
    for c in conns:
        a_id = (c.get('connectorStart') or {}).get('endpointNodeId')
        b_id = (c.get('connectorEnd') or {}).get('endpointNodeId')
        A, via_a, trig_a = cr.resolve_endpoint(a_id, own, screen_of_chip,
                                               screens_by_id, cworld) \
            if a_id else (None, 'FLOATING', None)
        B, via_b, trig_b = cr.resolve_endpoint(b_id, own, screen_of_chip,
                                               screens_by_id, cworld) \
            if b_id else (None, 'FLOATING', None)
        direction = cr.arrow_direction(c)
        label = (c.get('text') or {}).get('characters', '').strip()
        if A and B and A['id'] != B['id']:
            if direction == 'REVERSED':
                A, B, trig_a, trig_b, via_a, via_b = B, A, trig_b, trig_a, via_b, via_a
            raw_edges.append(dict(cid=c['id'], A=A, B=B, trig=trig_a,
                                  label=label, direction=direction,
                                  via_a=via_a, via_b=via_b))
        else:
            unresolved.append(dict(
                connector_id=c['id'], condition=label, direction=direction,
                start=dict(node_id=a_id, via=via_a,
                           name=(own.get(a_id) or {}).get('name'),
                           text=sp.deep_text(own[a_id]['node'], 60) if a_id in own else None),
                end=dict(node_id=b_id, via=via_b,
                         name=(own.get(b_id) or {}).get('name'),
                         text=sp.deep_text(own[b_id]['node'], 60) if b_id in own else None),
                reason='SELF_LOOP' if (A and B and A['id'] == B['id'])
                       else f'start={via_a} end={via_b}'))

    # ---- decision-box contraction (schema edge_source: CONNECTOR_CONTRACTED)
    # A non-screen board node whose text asks a question, with incoming
    # connectors and >=2 outgoing ones, is a decision box drawn between two
    # screens. Contract every in x out pair so the branch condition attaches
    # to the screens it belongs to; the box itself never becomes a screen.
    dir_ends = {}
    for c in conns:
        a = (c.get('connectorStart') or {}).get('endpointNodeId')
        bb = (c.get('connectorEnd') or {}).get('endpointNodeId')
        if cr.arrow_direction(c) == 'REVERSED':
            a, bb = bb, a
        dir_ends[c['id']] = (a, bb)
    consumed = set()
    for box in cworld.get('boards', boards):
        kind = box.get('kind', box['type'])
        if kind in ('SCREEN', 'CHIP') or box['type'] in ('SECTION', 'CONNECTOR'):
            continue
        qtext = ' '.join((box.get('text') or sp.deep_text(box['node'], 120)).split())
        if '?' not in qtext:
            continue
        node_ids = {box['id']} | {n['id'] for n, *_ in sp.walk_abs(box['node'])}
        ins = [c for c in conns if dir_ends[c['id']][1] in node_ids]
        outs = [c for c in conns if dir_ends[c['id']][0] in node_ids]
        if not ins or len(outs) < 2:
            continue
        question = re.sub(r'\s+\?', '?', qtext[:120]).rstrip()
        for ic in ins:
            A, via_a, trig_a = cr.resolve_endpoint(dir_ends[ic['id']][0], own,
                                                   screen_of_chip, screens_by_id,
                                                   cworld)
            if not A:
                continue
            in_label = (ic.get('text') or {}).get('characters', '').strip()
            for oc in outs:
                B, via_b, _ = cr.resolve_endpoint(dir_ends[oc['id']][1], own,
                                                  screen_of_chip, screens_by_id,
                                                  cworld)
                if not B or B['id'] == A['id']:
                    continue
                value = (oc.get('text') or {}).get('characters', '').strip()
                cond = f'{question} — {value}' if value else question
                if in_label:
                    cond = f'{in_label} / {cond}'
                raw_edges.append(dict(
                    cid=oc['id'], A=A, B=B, trig=trig_a, label=cond,
                    direction='FORWARD', via_a=via_a, via_b=via_b,
                    decision=dict(question=question, value=value,
                                  node_id=box['id'])))
                consumed.update((ic['id'], oc['id']))
    if consumed:
        unresolved = [u for u in unresolved
                      if u.get('connector_id') not in consumed]

    # ---- proto-screens: consecutive same-frame-name run inside one column
    protos = []
    for g in world['groups']:
        for r in g['rows']:
            for col in r['columns']:
                run = []
                for s in col:
                    if run and s['name'] == run[-1]['name']:
                        run.append(s)
                    else:
                        if run:
                            protos.append(run)
                        run = [s]
                if run:
                    protos.append(run)

    # ---- identity + per-frame state
    frame_state, frame_identity, excluded = {}, {}, []
    for run in protos:
        head = run[0]
        m0 = meta[head['id']]
        # draft material: loose cluster with no labels at all
        if m0['group_kind'] == 'LOOSE' and not m0['group_has_labels']:
            excluded.extend((s['id'], 'DRAFT_LOOSE_CLUSTER', s['name']) for s in run)
            continue
        if len(run) > 1:
            identity = head['name']
        else:
            title = m0['chip_title']
            if title and not title.lower().startswith(head['name'].lower()):
                identity = title
            elif head['type'] == 'RECTANGLE' and not title:
                excluded.append((head['id'], 'REFERENCE_IMAGE_NO_CHIP', head['name']))
                continue
            else:
                identity = head['name']
        for s in run:
            m = meta[s['id']]
            title = m['chip_title']
            state = title
            if state and state.lower().startswith(identity.lower()):
                state = state[len(identity):].lstrip(' -–—/').strip()
            if state and state.lower() == identity.lower():
                state = ''
            scen = m['subsection_name'] or \
                (m['cluster'] if m['subsection_id'] else '')
            frame_identity[s['id']] = identity
            frame_state[s['id']] = f'{scen} — {state}' if scen and state \
                else (scen or state)

    # cross-board merge by normalized identity
    screens_out = {}
    merges = defaultdict(list)
    for run in protos:
        for s in run:
            if s['id'] not in frame_identity:
                continue
            identity = frame_identity[s['id']]
            sid = upper_snake(identity)
            merges[sid].append(s['id'])
            m = meta[s['id']]
            e = screens_out.setdefault(sid, {
                'screen_id': sid, 'screen_name': identity,
                'source_ref': s['id'], 'source_refs': [],
                'node_class': 'SCREEN', 'classified_by': 'GEOMETRY',
                'screen_states': [], 'state_kinds': [],
                'elements': [], 'screen_notes': '',
                '_attached': m['attached'], '_bands': set(), '_status': set(),
            })
            e['source_refs'].append(s['id'])
            st = frame_state[s['id']]
            if st and st not in e['screen_states']:
                e['screen_states'].append(st)
            if m['band']:
                e['_bands'].add(m['band'])
            if m['chip_status']:
                e['_status'].add(m['chip_status'])

    frame_to_sid = {}
    for sid, e in screens_out.items():
        for fid in e['source_refs']:
            frame_to_sid[fid] = sid

    # ---- artifact pseudo-screens (notification mocks that carry flow edges)
    for e in raw_edges:
        for side in ('A', 'B'):
            b = e[side]
            if b.get('kind') == 'CHIP' and b['id'] not in frame_to_sid:
                title, _ = sp.chip_struct(b['node'])
                ident = title or b['name']
                sid = upper_snake(ident)
                frame_to_sid[b['id']] = sid
                if sid not in screens_out:
                    screens_out[sid] = {
                        'screen_id': sid, 'screen_name': ident,
                        'source_ref': b['id'], 'source_refs': [b['id']],
                        'node_class': 'SCREEN', 'classified_by': 'GEOMETRY',
                        'screen_states': [], 'state_kinds': [],
                        'elements': [],
                        'screen_notes': 'Cross-channel artifact drawn on the '
                                        'board (push notification / toast), '
                                        'not an in-app screen frame.',
                        '_attached': False, '_bands': set(), '_status': set(),
                    }

    # ---- ui_flow: map edges onto collapsed screens
    ui_flow, state_transitions, variant_links = [], [], []
    edges_by_key = {}
    for e in raw_edges:
        fa, fb = e['A']['id'], e['B']['id']
        if 'VARIANT_BOX' in (e['via_a'], e['via_b']):
            variant_links.append(dict(connector_id=e['cid'],
                                      from_frame=fa, to_frame=fb))
            continue
        sa, sb = frame_to_sid.get(fa), frame_to_sid.get(fb)
        if not sa or not sb:
            unresolved.append(dict(connector_id=e['cid'], condition=e['label'],
                                   reason='ENDPOINT_FRAME_EXCLUDED',
                                   start=dict(node_id=fa), end=dict(node_id=fb)))
            continue
        if sa == sb:
            state_transitions.append(dict(
                connector_id=e['cid'], screen_id=sa,
                from_state=frame_state.get(fa, ''), to_state=frame_state.get(fb, ''),
                condition=e['label']))
            continue
        scen = ''
        if fa in (meta or {}):
            scen = meta[fa]['subsection_name'] or \
                (meta[fa]['cluster'] if meta[fa]['subsection_id'] else '')
        condition = ' / '.join(x for x in (scen, e['label']) if x)
        kind = 'OVERLAY' if screens_out[sb].get('_attached') else 'NAVIGATE'
        key = (sa, sb, condition, e['trig'] or '')
        if key in edges_by_key:
            continue
        edge = {'from_screen_id': sa, 'to_screen_id': sb,
                'condition': condition, 'navigation_kind': kind,
                'edge_source': 'CONNECTOR_CONTRACTED' if e.get('decision')
                               else 'CONNECTOR',
                'confidence': 'EXPLICIT', 'source_ref': e['cid']}
        if e.get('decision'):
            edge['decision_question'] = e['decision']['question']
            if e['decision']['value']:
                edge['decision_value'] = e['decision']['value']
            edge['decision_node_id'] = e['decision']['node_id']
        if e['direction'] != 'FORWARD':
            edge['edge_direction_source'] = \
                'ARROWHEAD_REVERSED' if e['direction'] == 'REVERSED' else e['direction']
        edges_by_key[key] = (edge, e)
        ui_flow.append(edge)

    # ---- deterministic elements from connector triggers
    for edge, e in edges_by_key.values():
        trig = e['trig']
        if not trig:
            continue
        node = own[trig]['node'] if trig in own else None
        # find the literal trigger node inside the screen subtree
        tnode = None
        for n, *_ in sp.walk_abs(e['A']['node']):
            if n['id'] == trig:
                tnode = n
                break
        if tnode is None:
            continue
        scr = screens_out[edge['from_screen_id']]
        role, suffix = role_for(tnode)
        label = element_label(tnode, screen_h)
        # a connector glued to the status-bar clock labels nothing — keep the
        # edge, skip the element
        if re.fullmatch(r'\d{1,2}:\d{2}', label.strip()):
            continue
        purpose = lower_snake(label)[:40]
        if not purpose.endswith(suffix.lstrip('_')):
            purpose = f'{purpose}{suffix}'
        element_id = f"{scr['screen_id']}.{purpose}"
        el = next((x for x in scr['elements'] if x['element_id'] == element_id), None)
        if el is None:
            el = {'element_id': element_id, 'source_ref': trig,
                  'type': tnode.get('type', ''), 'role': role,
                  'label': label[:60],
                  'states_represented': [],
                  'interactions': [], 'validations_and_edge_cases': []}
            scr['elements'].append(el)
        el['interactions'].append({
            'trigger': 'tap',
            'action': f"Navigates to {edge['to_screen_id']}"
                      + (f" when {edge['condition']}" if edge['condition'] else '')
                      + f" (connector {e['cid']})",
            'connector_id': e['cid'],
            'destination_node_id': e['B']['id'],
            'destination_screen_id': edge['to_screen_id'],
        })
        edge['trigger_element_id'] = element_id

    # ---- ambiguity + gaps
    blocking, gaps = [], []
    if cfg_gap:
        gaps.append(cfg_gap)
    for u in unresolved:
        if u.get('condition'):
            blocking.append(
                f"Connector {u['connector_id']} labelled '{u['condition']}' could not "
                f"be resolved to screens ({u['reason']}); the flow it describes is "
                f"missing from ui_flow.")
    amb = [u for u in unresolved if 'SECTION_AMBIGUOUS' in u.get('reason', '')]
    if amb:
        gaps.append({'field': 'ui_flow',
                     'reason': f"{len(amb)} connectors attach to whole sections "
                               "with no per-screen position in the export.",
                     'action': 'Re-attach these connectors to specific frames in '
                               'Figma, or confirm they are section-level notes.',
                     'severity': 'DEGRADED'})
    gaps.append({'field': 'ui_flow',
                 'reason': 'All 179 prototype-reaction destinations point outside '
                           'this export (component-library wiring); connectors are '
                           'the only flow source on this board.',
                 'action': 'None — informational.',
                 'severity': 'INFO'})
    nondesc = [sid for sid in screens_out
               if re.fullmatch(r'(FRAME|GROUP|RECTANGLE|SCREEN|CONTENT)(_\d+)?',
                               sid)]
    if nondesc:
        gaps.append({'field': 'screens',
                     'reason': 'Screens with non-descriptive ids (default layer '
                               'names, no label chip): ' + ', '.join(sorted(nondesc)),
                     'action': 'Name the frame or add a screen label chip in Figma.',
                     'severity': 'INFO'})
    if excluded:
        gaps.append({'field': 'screens',
                     'reason': f'{len(excluded)} board nodes excluded: pasted '
                               'reference screenshots without label chips and '
                               'unlabeled loose draft clusters.',
                     'action': 'Label them with screen chips if they are real screens.',
                     'severity': 'INFO'})
    # ambiguity rating counts SUBSTANTIVE unresolved only: a connector tethering
    # an annotation note to a screen is documentation, not lost navigation (the
    # schema itself: "an annotation tether is not behaviour"). Substantive =
    # carries a branch label, or failed on an ambiguous/missing target.
    substantive = [u for u in unresolved
                   if u.get('condition')
                   or any(k in u.get('reason', '')
                          for k in ('AMBIGUOUS', 'MISSING_NODE', 'FLOATING'))]
    unres_ratio = len(substantive) / max(1, len(conns))
    rating = 'HIGH' if unres_ratio > 0.3 else \
             'LOW' if unres_ratio < 0.05 and not blocking else 'MEDIUM'

    env = world['envelope']
    screens_list, ambiguous_collapses = [], []
    for sid in sorted(screens_out):
        e = dict(screens_out[sid])
        bands = e.pop('_bands'); status = e.pop('_status'); e.pop('_attached')
        notes = []
        if bands:
            notes.append('Lane(s): ' + ' | '.join(sorted(bands)))
        if status:
            notes.append('Change status per design: ' + ', '.join(sorted(status)))
        e['state_kinds'] = sorted({state_kind(s) for s in e['screen_states']}) \
            if e['screen_states'] else []
        # ambiguous collapse: many frames merged under one name whose state
        # qualifiers share no vocabulary — possibly distinct surfaces
        firsts = {s.split(' — ')[-1].split()[0].lower()
                  for s in e['screen_states'] if s.strip()}
        if len(e['source_refs']) >= 4 and len(firsts) >= max(3, len(e['screen_states']) // 2) \
           and all(k == 'OTHER' for k in e['state_kinds']):
            ambiguous_collapses.append(sid)
            notes.append('AMBIGUOUS COLLAPSE: state names share no vocabulary — '
                         'these frames may be distinct surfaces drawn under one '
                         'generic frame name; review before automation.')
        e['screen_notes'] = ' — '.join(notes)
        screens_list.append(e)
    for sid in ambiguous_collapses:
        blocking.append(
            f"Screen {sid} collapses {len(screens_out[sid]['source_refs'])} frames "
            f"whose state names share no vocabulary — confirm they are states of "
            f"one screen, not distinct screens under a generic frame name.")

    context = {
        'extraction_status': 'DEGRADED' if any(
            g['severity'] == 'DEGRADED' and g['field'] == 'ENVIRONMENT'
            for g in gaps) else 'INCOMPLETE',
        'extraction_gaps': gaps,
        **({'app': app} if app else {}),
        'design_source': {
            'file_name': env['file']['name'], 'page_name': env['file']['page'],
            'scope': env['scope'], 'exported_at': env['exportedAt'],
            'max_depth': env['export']['maxDepth'],
            'node_count': env['export']['nodeCount'],
            'truncated_count': env['export']['truncatedCount'],
            'has_geometry': True,
            'truncated_nodes': env['export'].get('truncatedNodes', [])[:20],
        },
        'visual_analysis_scratchpad':
            f"Spatial-first read: {len(world['groups'])} board groups, "
            f"{len(screens_list)} screens after collapsing "
            f"{sum(len(v) for v in merges.values())} frames "
            f"(calibrated device frame {screen_w}x{screen_h}). Swim lanes: persona "
            f"bands (Large banners), flow clusters (Medium banners), row captions "
            f"as cart-state lanes; scenario sub-sections read as preconditions. "
            f"{len(ui_flow)} navigation edges from {len(conns)} connectors; "
            f"prototype reactions all point outside the export.",
        'project_context': {
            'overall_ambiguity_rating': rating,
            'blocking_issues': blocking,
        },
        'screens': screens_list,
        'ui_flow': ui_flow,
    }

    report = {
        'protos': [{'identity': frame_identity.get(r[0]['id']),
                    'frames': [s['id'] for s in r]}
                   for r in protos if r[0]['id'] in frame_identity],
        'merges': {k: v for k, v in merges.items() if len(v) > 1},
        'state_transitions': state_transitions,
        'variant_links': variant_links,
        'ambiguous_collapses': ambiguous_collapses,
        'excluded_nodes': [dict(id=i, reason=r, name=n) for i, r, n in excluded],
        'unresolved_connectors': unresolved,
        'counters': {
            'connectors_total': len(conns),
            'edges_emitted': len(ui_flow),
            'state_transition_connectors': len(state_transitions),
            'variant_link_connectors': len(variant_links),
            'unresolved_connectors': len(unresolved),
            'screens_emitted': len(screens_list),
            'frames_collapsed': sum(len(v) for v in merges.values()),
            'elements_deterministic': sum(len(s['elements']) for s in screens_list),
        },
    }
    return context, report


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Phase A deterministic extractor')
    ap.add_argument('export', help='Figma "Export Design Raw JSON" v2 file')
    ap.add_argument('--app', default=None,
                    help='app id (gojek-consumer, ...) — stamped on the context')
    ap.add_argument('--out', default='.',
                    help='workdir for design_context.json + phase_a.report.json')
    args = ap.parse_args()

    context, report = build(args.export, app=args.app)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, 'design_context.json'), 'w') as f:
        json.dump(context, f, indent=1, ensure_ascii=False)
    with open(os.path.join(args.out, 'phase_a.report.json'), 'w') as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    print(json.dumps(report['counters'], indent=1))
    try:
        import jsonschema
        jsonschema.validate(context, json.load(open(SCHEMA_PATH)))
        print('schema: VALID')
    except ImportError:
        print('schema: NOT CHECKED — jsonschema missing (pip install jsonschema)')
    except Exception as ex:
        print('schema: FAILED —', str(ex)[:400])
    import context_checks
    if not context_checks.run(context):
        sys.exit(1)


if __name__ == '__main__':
    main()
