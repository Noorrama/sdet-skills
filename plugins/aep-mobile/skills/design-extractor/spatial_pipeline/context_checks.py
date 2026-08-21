#!/usr/bin/env python3
"""Referential self-checks for design_context.json — everything the JSON schema
cannot express. Direct successor of the old check_design_context.py idea: a
model (or a bug) can emit a schema-valid file that still contradicts itself,
so phase_a and phase_b_merge both run these after schema validation.

Also runnable standalone:  python3 context_checks.py <design_context.json>
"""

import json
import re
import sys

ELEMENT_ID = re.compile(r'^[A-Z0-9_]+\.[a-z0-9_]+(\.[a-z0-9_]+)?$')


def check(context):
    """Returns a list of failure strings; empty = clean."""
    fails = []
    screens = context.get('screens', [])
    ids = [s['screen_id'] for s in screens]
    id_set = set(ids)
    if len(ids) != len(id_set):
        dup = sorted({i for i in ids if ids.count(i) > 1})
        fails.append(f'duplicate screen_id: {dup}')

    seen_refs = {}
    for s in screens:
        for r in s.get('source_refs', []):
            if r in seen_refs and seen_refs[r] != s['screen_id']:
                fails.append(f"frame {r} owned by two screens: "
                             f"{seen_refs[r]} and {s['screen_id']}")
            seen_refs[r] = s['screen_id']
        el_ids = set()
        for el in s.get('elements', []):
            eid = el['element_id']
            if not ELEMENT_ID.fullmatch(eid):
                fails.append(f'element_id fails pattern: {eid}')
            if not eid.startswith(s['screen_id'] + '.'):
                fails.append(f"element {eid} not prefixed by its screen "
                             f"{s['screen_id']}")
            if eid in el_ids:
                fails.append(f'duplicate element_id in screen: {eid}')
            el_ids.add(eid)
            for it in el.get('interactions', []):
                dst = it.get('destination_screen_id')
                if dst and dst not in id_set:
                    fails.append(f'{eid} interaction destination '
                                 f'{dst} is not a screen')
                if dst == s['screen_id']:
                    fails.append(f'{eid} interaction self-loops to its own '
                                 f'screen (guard says omit)')

    edge_keys = set()
    for e in context.get('ui_flow', []):
        fr, to = e['from_screen_id'], e['to_screen_id']
        for sid in (fr, to):
            if sid not in id_set:
                fails.append(f'ui_flow references unknown screen {sid}')
        if fr == to:
            fails.append(f'ui_flow self-loop on {fr}')
        trig = e.get('trigger_element_id')
        if trig:
            scr = next((s for s in screens if s['screen_id'] == fr), None)
            if scr and trig not in {el['element_id']
                                    for el in scr.get('elements', [])}:
                fails.append(f'ui_flow trigger {trig} missing from '
                             f'{fr}.elements')
        key = (fr, to, e.get('condition', ''), trig or '',
               e.get('source_ref', ''))
        if key in edge_keys:
            fails.append(f'duplicate ui_flow edge {fr}->{to} '
                         f'[{e.get("condition", "")}]')
        edge_keys.add(key)

    pc = context.get('project_context', {})
    for b in pc.get('blocking_issues', []):
        if not b or not b.strip():
            fails.append('empty string in blocking_issues')
    if context.get('extraction_status') == 'OK' and context.get('extraction_gaps'):
        fails.append('extraction_status OK but extraction_gaps non-empty')
    return fails


def run(context, label=''):
    fails = check(context)
    for f in fails:
        print(f'CHECK FAIL{f" [{label}]" if label else ""}: {f}')
    if not fails:
        print('referential checks: OK')
    return not fails


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('usage: context_checks.py <design_context.json>')
    ok = run(json.load(open(sys.argv[1])))
    sys.exit(0 if ok else 1)
