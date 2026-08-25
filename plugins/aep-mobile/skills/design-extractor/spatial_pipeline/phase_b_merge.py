#!/usr/bin/env python3
"""Phase B merge: apply LLM enrichment onto the Phase A skeleton, enforcing the
no-invention contract, then re-validate against design_context.schema.json.

Enrichment input (phase_b_out.jsonl, one JSON object per screen):
{
  "screen_id": "...",                     # must exist in the skeleton
  "elements": [{                          # NEW elements only
     "source_ref": "...",                 # MUST be a packet candidate id
     "purpose": "add_to_cart",            # lower_snake, no suffix; copy the
                                          # candidate's suggested_purpose
                                          # unless you have a clearly more
                                          # specific name — NEVER a generic
                                          # like element_container
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
  "ambiguity": {"rating": "LOW|MEDIUM|HIGH", "reason": "..."}   # optional;
                                          # an OBJECT, never a boolean. HIGH
                                          # requires a non-empty reason (it
                                          # becomes a blocking issue a PM
                                          # must be able to answer)
}

Rules enforced here, not trusted from the model:
  - screens and ui_flow are immutable
  - every model-supplied field is type-checked; a malformed field (wrong
    JSON shape) is rejected with a reason — rejections feed escalations —
    and the merge continues instead of crashing
  - a new element's source_ref must appear in the packet candidate list
  - element_id built HERE from screen_id + purpose + role suffix
  - state_kind_map may only upgrade OTHER states, to enum values only

Collision handling (deterministic, no model call): when a proposed purpose+role
collides with an element_id already on the screen, this is a naming problem,
not a semantic one, so it is repaired here rather than dropped or escalated.
  - same source_ref already owns that element_id -> harmless re-proposal
    (e.g. Phase A's own connector-trigger scan got there first), skip quietly
  - different source_ref wants the same slot -> re-derive the purpose from
    that candidate's OWN text/name (almost always more distinctive than
    whatever generic purpose the model picked) instead of the model's value;
    if that still collides, append a short deterministic suffix from the
    source_ref itself. Always terminates, always the same output for the
    same input. Counted separately (applied['auto_repaired']) so the merge
    report stays honest about what the model authored vs what the script
    recovered. The source_ref suffix is unique per candidate, so every
    distinct candidate always lands a slot; REJECTED duplicates remain only
    for true re-proposals of a slot another candidate owns under every name.
The same re-derivation runs, without waiting for a collision, when the model's
purpose is a generic placeholder (element_container, element_label, ...): the
candidate's own text is a better name by construction.
Source_ref repair (deterministic): a model sometimes truncates an instance
node id ('12054:76356' for 'I12054:76356;1085:7511'). When the given ref is
not a candidate but is a substring of EXACTLY ONE candidate id, it snaps to
that candidate; an ambiguous or absent match still rejects.
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


# a purpose that names the widget kind instead of what it is FOR — carries no
# information beyond the role suffix, and collides across candidates
GENERIC_PURPOSE = re.compile(
    r'^(element|item|control|component|frame|group|content|section|region|'
    r'text|label|button|btn|container|img|image|icon|link|list|input|toggle|'
    r'title|value|option|card|cell|row)'
    r'(_(container|label|img|image|icon|btn|button|link|list|toggle|input|'
    r'ctrl|element|item|text|title|value|option|card|cell|row))?$')


def derived_purpose(cand):
    """Purpose from the candidate's own export text/name — never invented."""
    if cand.get('suggested_purpose'):
        return cand['suggested_purpose'][:40]
    src = (cand.get('text') or cand.get('name') or '').strip()
    return lower_snake(src)[:40] if src else ''


def ref_suffix(source_ref):
    return re.sub(r'[^0-9a-z]', '', source_ref.lower())[-6:]


def main(context_path, packets_path, enrich_path, out_path):
    context = json.load(open(context_path))
    screens = {s['screen_id']: s for s in context['screens']}
    packets = {}
    with open(packets_path) as f:
        for line in f:
            p = json.loads(line)
            packets[p['screen_id']] = p

    rejected, applied = [], {'elements': 0, 'updates': 0, 'kinds': 0,
                             'validations': 0, 'ambiguity': 0,
                             'auto_repaired': 0}
    escalations = []
    with open(enrich_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            if not isinstance(e, dict):
                rejected.append((None, 'enrichment line not an object'))
                continue
            sid = e.get('screen_id')
            scr = screens.get(sid)
            pkt = packets.get(sid)
            if not scr or not pkt:
                rejected.append((sid, 'UNKNOWN_SCREEN'))
                continue
            cand_ids = {c['id'] for c in pkt['candidates']}
            existing = {el['element_id']: el.get('source_ref')
                        for el in scr['elements']}

            elems = e.get('elements', [])
            if not isinstance(elems, list):
                rejected.append((sid, 'elements not a list'))
                elems = []
            for ne in elems:
                if not isinstance(ne, dict):
                    rejected.append((sid, 'element entry not an object'))
                    continue
                ref = ne.get('source_ref')
                ref = ref if isinstance(ref, str) else ''
                if ref not in cand_ids:
                    # truncated-id repair: unique substring match snaps to
                    # the real candidate; ambiguous/absent still rejects
                    hits = [c for c in cand_ids if len(ref) >= 6 and ref in c]
                    if len(hits) == 1:
                        ref = hits[0]
                        applied['auto_repaired'] += 1
                    else:
                        rejected.append((sid, f'element source_ref '
                                              f'{ne.get("source_ref")} '
                                              'not a packet candidate'))
                        continue
                role = ne.get('role', 'OTHER')
                if not isinstance(role, str) or role not in ROLE_SUFFIX:
                    rejected.append((sid, f'bad role {role!r}'))
                    continue
                cand = next(c for c in pkt['candidates'] if c['id'] == ref)
                suffix = ROLE_SUFFIX[role]

                def with_suffix(p):
                    return p if p.endswith(suffix.lstrip('_')) \
                        else f'{p}{suffix}'

                purpose = ne.get('purpose', '')
                purpose = lower_snake(
                    purpose if isinstance(purpose, str) else '')[:40]
                repaired = False
                if GENERIC_PURPOSE.fullmatch(purpose):
                    better = derived_purpose(cand)
                    if better and not GENERIC_PURPOSE.fullmatch(better):
                        purpose, repaired = better, True
                eid = f'{sid}.{with_suffix(purpose)}'
                if eid in existing:
                    if existing[eid] == ref:
                        continue          # harmless re-proposal, skip quietly
                    better = derived_purpose(cand)
                    if better:
                        eid = f'{sid}.{with_suffix(better)}'
                        repaired = True
                    if eid in existing and existing[eid] != ref:
                        # last resort: source_ref-derived suffix — unique per
                        # candidate, so this always lands a free slot
                        eid = f'{sid}.' + with_suffix(
                            f'{purpose[:26]}_{ref_suffix(ref)}')
                        repaired = True
                    if eid in existing:
                        if existing[eid] == ref:
                            continue      # same candidate under either name
                        rejected.append((sid, f'duplicate element_id {eid}'))
                        continue
                label = ne.get('label')
                vecs = ne.get('validations_and_edge_cases', [])
                if not isinstance(vecs, list):
                    vecs = []
                scr['elements'].append({
                    'element_id': eid, 'source_ref': ref,
                    'type': cand['type'], 'role': role,
                    'label': ((label if isinstance(label, str) else None)
                              or cand.get('text') or cand['name'])[:80],
                    'states_represented': [],
                    'interactions': [],
                    'validations_and_edge_cases':
                        [v[:300] for v in vecs if isinstance(v, str)][:6],
                })
                existing[eid] = ref
                if repaired:
                    applied['auto_repaired'] += 1
                else:
                    applied['elements'] += 1

            ups = e.get('element_updates', [])
            if not isinstance(ups, list):
                rejected.append((sid, 'element_updates not a list'))
                ups = []
            for up in ups:
                if not isinstance(up, dict):
                    rejected.append((sid, 'element_update entry not an object'))
                    continue
                el = next((x for x in scr['elements']
                           if x['element_id'] == up.get('element_id')), None)
                if not el:
                    rejected.append((sid, f"update for unknown {up.get('element_id')}"))
                    continue
                if isinstance(up.get('label'), str) and up['label']:
                    el['label'] = up['label'][:80]
                if isinstance(up.get('role'), str) and up['role'] in ROLE_SUFFIX:
                    el['role'] = up['role']
                uvecs = up.get('validations_and_edge_cases', [])
                if not isinstance(uvecs, list):
                    uvecs = []
                for v in uvecs[:6]:
                    if isinstance(v, str) \
                       and v not in el['validations_and_edge_cases']:
                        el['validations_and_edge_cases'].append(v[:300])
                applied['updates'] += 1

            km = e.get('state_kind_map', {})
            if not isinstance(km, dict):
                rejected.append((sid, 'state_kind_map not an object'))
                km = {}
            if any(not isinstance(v, str) for v in km.values()):
                rejected.append((sid, 'state_kind values must be strings'))
                km = {k: v for k, v in km.items() if isinstance(v, str)}
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
            if not isinstance(sv, list):
                rejected.append((sid, 'screen_validations not a list'))
                sv = []
            sv = [v for v in sv if isinstance(v, str)]
            if sv:
                extra = ' — '.join(v[:300] for v in sv[:5])
                scr['screen_notes'] = (scr['screen_notes'] + ' — ' + extra).strip(' —')
                applied['validations'] += 1

            amb = e.get('ambiguity')
            if amb is False:
                amb = None    # explicit "no ambiguity" — harmless, accept
            if amb is not None and not isinstance(amb, dict):
                # a bare boolean/string here once crashed the merge; malformed
                # ambiguity is a contract violation like any other — reject it
                # (rejections feed escalations) and keep merging
                rejected.append((sid, 'ambiguity must be an object: '
                                      '{"rating": "LOW|MEDIUM|HIGH", '
                                      '"reason": "..."}'))
                amb = None
            if amb:
                rating = amb.get('rating')
                reason = amb.get('reason')
                reason = reason.strip() if isinstance(reason, str) else ''
                if rating not in ('LOW', 'MEDIUM', 'HIGH'):
                    rejected.append((sid, f'ambiguity rating {rating!r} '
                                          'not LOW/MEDIUM/HIGH'))
                elif rating == 'HIGH' and not reason:
                    # HIGH becomes a blocking issue a PM must answer; without
                    # a reason there is no question to answer
                    rejected.append((sid, 'HIGH ambiguity requires a reason'))
                else:
                    applied['ambiguity'] += 1
                    if rating == 'HIGH':
                        context['project_context']['blocking_issues'].append(
                            f"{sid}: {reason[:200]}")
                        escalations.append({'screen_id': sid,
                                            'reason': 'HIGH ambiguity: '
                                                      + reason[:200]})

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
