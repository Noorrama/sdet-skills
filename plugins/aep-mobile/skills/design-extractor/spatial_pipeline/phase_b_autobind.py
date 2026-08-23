#!/usr/bin/env python3
"""Deterministic element auto-bind + light-packet builder — the token-lean
default for Phase B.

With candidates deduped and each carrying a deterministic suggested_purpose
(phase_b_packets), promoting a candidate to an element no longer needs a
model: purpose, label, and source_ref are already decided, and the role is a
closed keyword heuristic on the candidate's own layer name. This script does
exactly that, emitting a synthetic enrichment file (autobind_out.jsonl) in
the SAME contract phase_b_merge already enforces — so the merge stays the
single validator and the no-invention guarantee holds by construction.

What still needs a model is language, not selection: turning designer notes
into validations, resolving leftover OTHER state kinds, and flagging genuine
ambiguity. For that it also writes light packets (phase_b_light.jsonl) —
screen_id, states, notes, screen_notes, NO candidates — only for screens
that actually have notes, an OTHER state kind, or an ambiguity flag. On the
GoFood board this shrinks the LLM input from ~520KB/9 agents to a few dozen
KB for 2-3 agents.

Decoration filtering is deterministic and conservative: drop status-bar
clocks, and textless layers whose names say divider/shimmer/spacer/etc or
are default layer names. A candidate with real text is always kept — an
assertable label beats a false negative.

Usage: phase_b_autobind.py <phase_b_packets.jsonl>
                           [autobind_out.jsonl] [phase_b_light.jsonl]
Then:  phase_b_merge.py <context> <packets> autobind_out.jsonl <out>
       (and merge the LLM's light output the same way, additively).
"""

import json
import re
import sys

DECOR_NAME = re.compile(
    r'divider|separator|shimmer|skeleton|spacer|status ?bar|home indicator|'
    r'scroll ?(bar|indicator)?$|page control|notch|backdrop|background|'
    r'^bg[ _\d]*$|^line[ _\d]*$|^vector[ _\d]*$|^ellipse[ _\d]*$|'
    r'^rectangle[ _\d]*$|^union[ _\d]*$|^mask[ _\d]*$', re.I)
DEFAULT_NAME = re.compile(
    r'^(frame|group|rectangle|content|section|component|instance)[ _\d]*$',
    re.I)
CLOCK = re.compile(r'^\d{1,2}:\d{2}$')
# component-library icon instances (payments/24/ic_card, ic_close, icon/...):
# decorative unless they carry text of their own
ICON_NAME = re.compile(r'/ic_|^ic_|\bicons?\b|/\d{2}/', re.I)

ROLE_RULES = [
    (r'button|btn\b|cta\b', 'BUTTON'),
    (r'input|field|search bar|text ?box', 'INPUT'),
    (r'toggle|switch|radio|checkbox', 'TOGGLE'),
    (r'\btab\b', 'TAB'),
    (r'\blist\b|\bcell\b|\bcard\b', 'LIST'),
    (r'\blink\b', 'LINK'),
    (r'image|\bimg\b|illustration|artwork|photo|avatar', 'IMAGE'),
    (r'dropdown|select\b', 'DROPDOWN'),
    (r'carousel', 'CAROUSEL'),
]


def role_for(cand):
    name = (cand.get('name') or '').lower()
    for pat, role in ROLE_RULES:
        if re.search(pat, name):
            return role
    return 'LABEL' if cand['type'] == 'TEXT' else 'OTHER'


def keep(cand):
    name = (cand.get('name') or '').strip()
    text = (cand.get('text') or '').strip()
    if CLOCK.fullmatch(text):
        return False                      # status-bar clock labels nothing
    if text:
        return True                       # real text is always assertable
    if not name or DECOR_NAME.search(name) or DEFAULT_NAME.fullmatch(name) \
            or ICON_NAME.search(name):
        return False
    return True


def main(packets_path, out_path, light_path):
    stats = {'screens': 0, 'elements_autobound': 0,
             'candidates_skipped': 0, 'light_packets': 0}
    with open(packets_path) as f, open(out_path, 'w') as fo, \
            open(light_path, 'w') as fl:
        for line in f:
            p = json.loads(line)
            stats['screens'] += 1
            els = []
            for c in p.get('candidates', []):
                if not keep(c) or not c.get('suggested_purpose'):
                    stats['candidates_skipped'] += 1
                    continue
                els.append({'source_ref': c['id'],
                            'purpose': c['suggested_purpose'],
                            'role': role_for(c),
                            'label': (c.get('text') or c.get('name'))[:80]})
            stats['elements_autobound'] += len(els)
            fo.write(json.dumps({'screen_id': p['screen_id'],
                                 'elements': els}, ensure_ascii=False) + '\n')
            needs_language = (p.get('notes')
                              or 'OTHER' in p.get('state_kinds', [])
                              or 'AMBIGUOUS' in p.get('screen_notes', ''))
            if needs_language:
                stats['light_packets'] += 1
                light = {k: p[k] for k in
                         ('screen_id', 'screen_name', 'screen_states',
                          'state_kinds', 'notes', 'screen_notes') if k in p}
                fl.write(json.dumps(light, ensure_ascii=False) + '\n')
    print(json.dumps(stats, indent=1))


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        sys.exit('usage: phase_b_autobind.py <phase_b_packets.jsonl> '
                 '[autobind_out.jsonl] [phase_b_light.jsonl]')
    main(a[0],
         a[1] if len(a) > 1 else 'autobind_out.jsonl',
         a[2] if len(a) > 2 else 'phase_b_light.jsonl')
