#!/usr/bin/env python3
"""Deterministic preflight for the design-extractor skill.

Run this INSTEAD of writing ad-hoc envelope-checking code — every mechanical
preflight check lives here so no model (of any tier) ever has to script one:

  environment   jsonschema importable?
  input         export parses, export.formatVersion == 2, geometry present,
                truncatedCount, truncatedNodes sample
  app hints     file name/page, top-level SECTION names, [Bracket] frame-name
                prefixes with counts — raw evidence for the app-set decision
                (the decision itself stays with the agent; this script never
                guesses an app)
  config        config/<app>.json readable when --app given
  schema        schemas/design_context.schema.json readable

Output: one JSON object on stdout —
  status  OK | DEGRADED | BLOCKED   (BLOCKED = spatial pipeline cannot run)
  checks  per-check verdicts
  gaps    ready-made extraction_gaps entries to copy into the context
  app_hints  the raw evidence listed above

Exit code 0 unless the export file itself is unreadable/unparseable (exit 1) —
a BLOCKED-but-parseable export still exits 0 so the caller can emit the
degraded context the skill requires instead of stopping.

Usage: preflight.py <export.json> [--app <app_id>]
"""

import json
import os
import re
import sys
from collections import Counter

PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                           '..', '..', '..'))
SCHEMA_PATH = os.path.join(PLUGIN_ROOT, 'schemas', 'design_context.schema.json')


def main(export_path, app=None):
    out = {'status': 'OK', 'checks': {}, 'gaps': [], 'app_hints': {}}

    def degrade(level):
        order = ['OK', 'DEGRADED', 'BLOCKED']
        if order.index(level) > order.index(out['status']):
            out['status'] = level

    # -- environment
    try:
        import jsonschema                                   # noqa: F401
        out['checks']['jsonschema'] = 'ok'
    except ImportError:
        out['checks']['jsonschema'] = 'missing'
        degrade('DEGRADED')
        out['gaps'].append({
            'field': 'ENVIRONMENT',
            'reason': 'jsonschema not importable — schema validation will be '
                      'skipped (phase_a prints a warning instead).',
            'action': 'pip install jsonschema (or run aep-mobile:setup)',
            'severity': 'DEGRADED'})

    # -- input
    try:
        with open(export_path) as f:
            d = json.load(f)
        out['checks']['parse'] = 'ok'
    except Exception as ex:
        out['checks']['parse'] = f'FAILED: {ex}'
        out['status'] = 'BLOCKED'
        print(json.dumps(out, indent=1, ensure_ascii=False))
        return 1

    exp = d.get('export') or {}
    fv = exp.get('formatVersion')
    out['checks']['formatVersion'] = fv
    nodes = d.get('nodes') or []
    has_geometry = bool(nodes) and any(
        k in (nodes[0] if isinstance(nodes[0], dict) else {})
        for k in ('x', 'y', 'width', 'height', 'children'))
    out['checks']['geometry'] = 'present' if has_geometry else 'ABSENT'
    if fv != 2 or not has_geometry:
        degrade('BLOCKED')
        out['gaps'].append({
            'field': 'design_source',
            'reason': f'export formatVersion={fv!r}, geometry '
                      f'{"present" if has_geometry else "absent"} — the '
                      'spatial pipeline requires formatVersion 2 with '
                      'geometry.',
            'action': 'Re-export with the "Export Design Raw JSON" Figma '
                      'plugin >= 0.5.0.',
            'severity': 'BLOCKING'})

    trunc = exp.get('truncatedCount', 0)
    out['checks']['truncatedCount'] = trunc
    if trunc:
        degrade('DEGRADED')
        out['gaps'].append({
            'field': 'design_source',
            'reason': f'{trunc} nodes truncated in the export: '
                      f'{exp.get("truncatedNodes", [])[:10]}',
            'action': 'Re-export with a higher depth limit, or confirm the '
                      'truncated subtrees are decorative.',
            'severity': 'DEGRADED'})

    # -- app hints (evidence only; the app-set decision stays with the agent)
    fi = d.get('file') or {}
    out['app_hints']['file_name'] = fi.get('name')
    out['app_hints']['file_page'] = fi.get('page')
    sections, prefixes = [], Counter()
    if nodes and isinstance(nodes[0], dict):
        for c in nodes[0].get('children', []):
            if c.get('type') == 'SECTION' and c.get('name'):
                sections.append(c['name'])
            m = re.match(r'\[([^\]]+)\]', c.get('name') or '')
            if m:
                prefixes[m.group(1)] += 1
    out['app_hints']['top_level_sections'] = sections[:20]
    out['app_hints']['bracket_prefixes'] = dict(prefixes.most_common(10))
    out['app_hints']['known_app_ids'] = sorted(
        f[:-5] for f in os.listdir(os.path.join(PLUGIN_ROOT, 'config'))
        if f.endswith('.json') and not f.startswith(('_', 'app-config'))
        and f not in ('deeplinks.json', 'browserstack_project_map.json'))

    # -- config
    if app:
        p = os.path.join(PLUGIN_ROOT, 'config', f'{app}.json')
        try:
            with open(p) as f:
                json.load(f)
            out['checks']['app_config'] = 'ok'
        except Exception:
            out['checks']['app_config'] = f'unreadable: {p}'
            degrade('DEGRADED')
            out['gaps'].append({
                'field': 'ENVIRONMENT',
                'reason': f'cannot read {p} — element IDs are unverified '
                          'against the app naming convention.',
                'action': 'reinstall/update the aep-mobile plugin and restart your editor, '
                          'restart, re-run',
                'severity': 'DEGRADED'})
    else:
        out['checks']['app_config'] = 'skipped (no --app)'

    # -- schema
    try:
        with open(SCHEMA_PATH) as f:
            json.load(f)
        out['checks']['schema_file'] = 'ok'
    except Exception:
        out['checks']['schema_file'] = f'unreadable: {SCHEMA_PATH}'
        degrade('DEGRADED')
        out['gaps'].append({
            'field': 'ENVIRONMENT',
            'reason': f'cannot read {SCHEMA_PATH}',
            'action': 'reinstall/update the aep-mobile plugin and restart your editor, '
                      're-run',
            'severity': 'DEGRADED'})

    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    app = None
    if '--app' in sys.argv:
        app = sys.argv[sys.argv.index('--app') + 1]
    if not args:
        sys.exit('usage: preflight.py <export.json> [--app <app_id>]')
    sys.exit(main(args[0], app))
