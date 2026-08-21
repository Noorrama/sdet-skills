#!/usr/bin/env python3
"""Phase B merge: apply LLM enrichment onto the Phase A skeleton, enforcing the
no-invention contract, then re-validate against design_context.schema.json.

Enrichment input (phase_b_out.jsonl, one JSON object per screen):
{
  "screen_id": "...",                     # must exist in the skeleton
  "elements": [{                          # NEW elements only
     "source_ref": "...",                 # MUST be a packet candidate id
     "purpose": "add_to_cart",            # lower_snake, no suffix
     "role": "BUTTON|INPUT|LABEL|TOGGLE|TAB|LIST|IMAGE|LINK|DROPDOWN|SLIDER|CAROUSEL|CONTAINER|OTHER",
     "label": "...",
     "validations_and_edge_cases": ["..."]
  }],
  "element_updates": [{                   # refinements of existing elements
     "element_id": "...", "label": "...", "role": "...",
     "validations_and_edge_cases": ["..."]
  }],
  "state_kind_map": {"<state>": "<KIND>"},# only states currently OTHER
  "screen_validations": ["..."],          # appended to screen_notes
  "ambiguity": {"rating": "LOW|MEDIUM|HIGH", "reason": "..."}   # optional
}

Rules enforced here, not trusted from the model:
  - screens and ui_flow are immutable
  - a new element's source_ref must appear in the packet candidate list
  - element_id built HERE from screen_id + purpose + role suffix
  - state_kind_map may only upgrade OTHER states, to enum values only
"""

import json
import os
import re
import sys

PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                           '..', '..', '..'))
SCHEMA_PATH = os.path.join(PLUGIN_ROOT, 'schemas', 'design_context.schema.json')

ROLE_SUFFIX = {'BUTTON': '_btn', 'INPUT': '_input', 'LABEL': '_label',
               'TOGGLE': '_toggle', 'TAB': '_tab', 'LIST': '_list',
               'IMAGE': '_img', 'LINK': '_link', 'DROPDOWN': '_dropdown',
               'SLIDER': '_slider', 'CAROUSEL': '_carousel',
               'CONTAINER': '_container', 'OTHER': '_ctrl'}
KINDS = {'DEFAULT', 'LOADING', 'EMPTY', 'ERROR', 'SUCCESS', 'OFFLINE', 'DISABLED',
         'PERMISSION_DENIED', 'DARK_THEME', 'LIGHT_THEME', 'LOCALE_VARIANT',
         'RTL', 'OTHER'}


def lower_snake(s):
    s = re.sub(r'[^0-9A-Za-z]+', '_', s).strip('_')
    return re.sub(r'_+', '_', s).lower() or 'element'


def main(context_path, packets_path, enrich_path, out_path):
    context = json.load(open(context_path))
    screens = {s['screen_id']: s for s in context['screens']}
    packets = {}
    with open(packets_path) as f:
        for line in f:
            p = json.loads(line)
            packets[p['screen_id']] = p

    rejected, applied = [], {'elements': 0, 'updates': 0, 'kinds': 0,
                             'validations': 0, 'ambiguity': 0}
    escalations = []
    with open(enrich_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            sid = e.get('screen_id')
            scr = screens.get(sid)
            pkt = packets.get(sid)
            if not scr or not pkt:
                rejected.append((sid, 'UNKNOWN_SCREEN'))
                continue
            cand_ids = {c['id'] for c in pkt['candidates']}
            existing = {el['element_id'] for el in scr['elements']}

            for ne in e.get('elements', []):
                if ne.get('source_ref') not in cand_ids:
                    rejected.append((sid, f"element source_ref {ne.get('source_ref')} "
                                          "not a packet candidate"))
                    continue
                role = ne.get('role', 'OTHER')
                if role not in ROLE_SUFFIX:
                    rejected.append((sid, f'bad role {role}'))
                    continue
                purpose = lower_snake(ne.get('purpose', ''))[:40]
                suffix = ROLE_SUFFIX[role]
                if not purpose.endswith(suffix.lstrip('_')):
                    purpose += suffix
                eid = f'{sid}.{purpose}'
                if eid in existing:
                    rejected.append((sid, f'duplicate element_id {eid}'))
                    continue
                cand = next(c for c in pkt['candidates'] if c['id'] == ne['source_ref'])
                scr['elements'].append({
                    'element_id': eid, 'source_ref': ne['source_ref'],
                    'type': cand['type'], 'role': role,
                    'label': (ne.get('label') or cand.get('text')
                              or cand['name'])[:80],
                    'states_represented': [],
                    'interactions': [],
                    'validations_and_edge_cases':
                        [v[:300] for v in ne.get('validations_and_edge_cases', [])][:6],
                })
                existing.add(eid)
                applied['elements'] += 1

            for up in e.get('element_updates', []):
                el = next((x for x in scr['elements']
                           if x['element_id'] == up.get('element_id')), None)
                if not el:
                    rejected.append((sid, f"update for unknown {up.get('element_id')}"))
                    continue
                if up.get('label'):
                    el['label'] = up['label'][:80]
                if up.get('role') in ROLE_SUFFIX:
                    el['role'] = up['role']
                for v in up.get('validations_and_edge_cases', [])[:6]:
                    if v not in el['validations_and_edge_cases']:
                        el['validations_and_edge_cases'].append(v[:300])
                applied['updates'] += 1

            km = e.get('state_kind_map', {})
            if km:
                kinds = []
                for st in scr['screen_states']:
                    cur_kinds = scr.get('state_kinds', [])
                    new = km.get(st)
                    kinds.append(new if new in KINDS else None)
                merged = {k for k in scr.get('state_kinds', []) if k != 'OTHER'}
                merged |= {k for k in kinds if k}
                if any(km.get(st) not in KINDS for st in km):
                    rejected.append((sid, 'state_kind outside enum ignored'))
                if not merged:
                    merged = {'OTHER'}
                scr['state_kinds'] = sorted(merged)
                applied['kinds'] += 1

            sv = e.get('screen_validations', [])
            if sv:
                extra = ' — '.join(v[:300] for v in sv[:5])
                scr['screen_notes'] = (scr['screen_notes'] + ' — ' + extra).strip(' —')
                applied['validations'] += 1

            amb = e.get('ambiguity')
            if amb and amb.get('rating') in ('LOW', 'MEDIUM', 'HIGH'):
                applied['ambiguity'] += 1
                if amb['rating'] == 'HIGH':
                    context['project_context']['blocking_issues'].append(
                        f"{sid}: {amb.get('reason', 'high ambiguity')[:200]}")
                    escalations.append({'screen_id': sid,
                                        'reason': 'HIGH ambiguity: '
                                                  + amb.get('reason', '')[:200]})

    # escalation list: HIGH-ambiguity screens, ambiguous phase-A collapses,
    # and screens whose enrichment the contract rejected — the only screens a
    # stronger model should ever be spent on.
    seen_esc = {x['screen_id'] for x in escalations}
    for s2 in context['screens']:
        if 'AMBIGUOUS COLLAPSE' in s2.get('screen_notes', '') \
           and s2['screen_id'] not in seen_esc:
            escalations.append({'screen_id': s2['screen_id'],
                                'reason': 'ambiguous generic-name collapse (phase A)'})
            seen_esc.add(s2['screen_id'])
    for sid2, why in rejected:
        if sid2 and sid2 not in seen_esc:
            escalations.append({'screen_id': sid2,
                                'reason': f'enrichment rejected: {why[:160]}'})
            seen_esc.add(sid2)
    with open(os.path.join(os.path.dirname(os.path.abspath(out_path)),
                           'escalations.json'), 'w') as f:
        json.dump(escalations, f, indent=1, ensure_ascii=False)

    # prune empty OPTIONAL fields — dead weight for the 68K-token consumer.
    # screen_states / elements / interactions / validations stay: schema-required.
    for s in context['screens']:
        if s.get('state_kinds') == []:
            del s['state_kinds']
        for el in s['elements']:
            if el.get('states_represented') == []:
                del el['states_represented']

    with open(out_path, 'w') as f:
        json.dump(context, f, indent=1, ensure_ascii=False)
    print(json.dumps({'applied': applied, 'rejected': len(rejected),
                      'escalations': len(escalations)}, indent=1))
    for r in rejected[:15]:
        print('  REJECTED', r)
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
    a = sys.argv[1:]
    main(a[0] if a else 'design_context.json',
         a[1] if len(a) > 1 else 'phase_b_packets.jsonl',
         a[2] if len(a) > 2 else 'phase_b_out.jsonl',
         a[3] if len(a) > 3 else 'design_context.enriched.json')
