#!/usr/bin/env python3
"""Screen-identity disambiguation: does one frame NAME mean one screen?

Phase A collapses a proto-screen run to its frame name and then merges every
proto sharing that name across the whole board. Teams reuse generic frame
names ("Landing", "MPS", "Dialog", "Overlay") for screens belonging to
different flows, so that merge silently fuses distinct screens: on the GoFood
Group Order board one MPS screen held 59 frames from 15 groups and 22 chip
titles.

The split rule, validated against the design team's own same/different calls
on labelled frame pairs across 4 boards (identity_labels.json; measured by
identity_audit.py):

    two frames of the same base identity are the SAME screen when
      (1) their CONTROL SETS agree — Jaccard >= SPLIT_THRESHOLD, or
      (2) they share a flow context AND one carries a chip the designer wrote
          as a state of that screen ("Loading", "Empty", "MPS - Scroll")
    grouping is transitive; frames the relation never links are different
    screens

Why the control set and not the obvious alternatives:

  * Control set = the visible text of the frame's interactive layers, which is
    what a test actually targets. Whole-frame text similarity is worse than
    useless here (0.70 between two frames the designers call different screens,
    because both render the same background chrome) and component-name
    similarity is degenerate (1.00 between two unrelated dialogs — every screen
    instantiates the same design-system Button/Text/Icon).
  * The explicit-state escape hatch keeps an empty-vs-filled input variant
    ("masukkan kode" -> "marsela1194") on one screen when the designer labelled
    it a state, without letting a shared context glue genuinely different
    screens together — context alone re-merges everything transitively.
  * A frame showing a dialog over a screen IS a different screen by the design
    team's own call (GoFood 11011:48756 vs 10950:27992), so a dialog-state
    frame with its own control set splits, and that is intended.

Anything the rule cannot separate stays merged and is reported. Over-splitting
is the worse failure: a fabricated `MPS__SOME_BANNER` screen breaks the
element_id join to change_context, while an over-merge is visible in review.
"""

import re

import spatial_scan as sp

SPLIT_THRESHOLD = 0.3
STRONG_THRESHOLD = 0.6

CONTROL_NAME = re.compile(
    r'button|btn|cta|field|input|search bar|toggle|switch|tab|checkbox|radio|'
    r'chip|dropdown|select|link|cell|row item|list item', re.I)

# Spec / annotation / asset material: frames that DOCUMENT a screen instead of
# being one. Excluded from screens[] and ui_flow (design-team call: "it is
# explaining design of existing screen, so it should be excluded").
SPEC_LABEL = re.compile(
    r'\bspecs?\b|specification|annotation|redline|guideline|\bassets?\b', re.I)

_CLOCK = re.compile(r'^\d{1,2}[:.]\d{2}')
_DIGITS = re.compile(r'\d[\d.,]*')

# Chip wording that reads as a STATE of the screen, not another screen.
STATE_WORD = re.compile(
    r'\b(default|filled|empty|loading|shimmer|skeleton|error|failed|success|'
    r'offline|disabled|permission|dark|light|rtl|scroll|typing|keyboard|'
    r'expanded|collapsed|tooltip|pagination|variant|entry point|1st time|'
    r'first time)\b|^\s*(en|id)\s*$', re.I)


def norm(s):
    return re.sub(r'\s+', ' ', (s or '')).strip()


def control_labels(node, cap=4000):
    """Visible text of every interactive layer in the frame: components whose
    name reads as a control, plus anything carrying a prototype reaction. The
    status-bar clock is dropped — it is not a control."""
    out, stack, seen = set(), [node], 0
    while stack and seen < cap:
        n = stack.pop()
        seen += 1
        interactive = (n.get('type') in ('INSTANCE', 'COMPONENT')
                       and CONTROL_NAME.search(norm(n.get('name')))) \
            or n.get('reactions')
        if interactive:
            t = norm(sp.deep_text(n, 40)).lower()
            if t and len(t) <= 40 and not _CLOCK.match(t):
                # digits are DATA, not identity: a "30%" loader and a "60%"
                # loader are one screen, and "marsela1194" in a filled field
                # is not a different control from "marsela2201"
                out.add(_DIGITS.sub('#', t))
        stack.extend(n.get('children') or ())
    return out


def jaccard(a, b):
    return len(a & b) / len(a | b) if (a or b) else 1.0


def context_of(m):
    """The frame's flow context: finest non-empty spatial label it sits under.
    Empty string means the board gives no context — never a split reason."""
    if norm(m['cluster']):
        return norm(m['cluster'])
    if norm(m['band']):
        return norm(m['band'])
    if norm(m['group_name']) and m['group_kind'] != 'LOOSE':
        return norm(m['group_name'])
    return ''


def is_spec_frame(m):
    return any(SPEC_LABEL.search(lab) for lab in
               (m['group_name'], m['band'], m['cluster'],
                m['subsection_name'] or '') if lab)


def is_state_chip(chip, base):
    """Chip that qualifies the base screen rather than naming another one —
    the designer's own statement that this frame is a STATE."""
    c = norm(chip)
    if not c:
        return False
    if c.lower().startswith(base.lower()):
        # "MPS - Scroll" states the screen and its state; a chip that is JUST
        # the screen name states no state at all.
        return bool(c[len(base):].strip(' -–—/'))
    return bool(STATE_WORD.search(c))


def split_frames(frames, base, meta, node_of, threshold=SPLIT_THRESHOLD):
    """Partition frames of ONE base identity into screens.

    Grouping runs two passes on control-set similarity. A STRONG pair
    (Jaccard >= STRONG_THRESHOLD) merges transitively — that much agreement
    is the same screen whatever else is nearby. Weaker agreement merges only
    when the cluster AVERAGE clears SPLIT_THRESHOLD. Plain single linkage
    over-merges (dialogs share generic buttons — "ok, got it" alone chained
    two dialogs the design team calls different screens) and plain complete
    linkage under-merges (one weak pair inside a 59-frame MPS cluster blocked
    a frame the team calls the same screen).

    Only a frame carrying its OWN chip seeds a screen; a frame that is
    unlabelled or chip-labelled as a state ("Loading", "MPS - Scroll") attaches
    to the cluster it best matches, so a state variant never becomes its own
    screen even when its control set is nothing like the default state's. On a
    board where nobody chipped anything, the flow context takes over as the
    seed: one context is one screen, and the control comparison can still
    merge two contexts back together.

    Returns ([[frame_id, ...], ...] ordered by size then id, pairwise sims).
    """
    keys = sorted(frames)
    ctrl = {k: control_labels(node_of[k]) for k in keys if k in node_of}
    ctx = {k: context_of(meta[k]) for k in keys}
    sims = {}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            sims[(a, b)] = round(jaccard(ctrl.get(a, set()),
                                         ctrl.get(b, set())), 3)

    def sim(a, b):
        return sims[(a, b)] if (a, b) in sims else sims.get((b, a), 1.0)

    # A frame only SEEDS a screen when the designer gave it a chip of its own
    # that is not a state qualifier. An unlabelled frame, or one chip-labelled
    # as a state, is a variant of a screen someone else seeded — it attaches,
    # it never creates.
    variant = {k: is_state_chip(meta[k]['chip_title'], base)
               or not norm(meta[k]['chip_title']) for k in keys}
    if all(variant.values()):
        # Nobody chipped anything, so the flow context is the only evidence:
        # frames under ONE context are one screen (six "30% / 60%" loader
        # copies are not six screens), and frames under different contexts are
        # candidates the control comparison below can still merge back.
        atoms = {}
        for k in keys:
            if ctx[k]:
                atoms.setdefault(ctx[k], []).append(k)
        clusters = [sorted(v) for v in atoms.values()]
        variant = {k: not ctx[k] for k in keys}
        if not clusters:
            return [sorted(keys)], sims
    else:
        clusters = [[k] for k in keys if not variant[k]]

    # --- pass 1: strong pairs merge transitively. A control set that agrees
    # this closely is the same screen regardless of what else is around.
    changed = True
    while changed:
        changed = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                if any(sim(x, y) >= STRONG_THRESHOLD
                       for x in clusters[i] for y in clusters[j]):
                    clusters[i] = sorted(clusters[i] + clusters[j])
                    del clusters[j]
                    changed = True
                    break
            if changed:
                break

    # --- pass 2: weaker agreement merges only on the cluster AVERAGE
    merged = True
    while merged:
        merged = False
        best = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                pairs = [sim(x, y) for x in clusters[i] for y in clusters[j]]
                if pairs and sum(pairs) / len(pairs) >= threshold:
                    score = (sum(pairs) / len(pairs), -i, -j)
                    if best is None or score > best[0]:
                        best = (score, i, j)
        if best:
            _, i, j = best
            clusters[i] = sorted(clusters[i] + clusters[j])
            del clusters[j]
            merged = True

    # --- variant frames (unlabelled, or chip-labelled as a state) attach
    for k in keys:
        if not variant[k]:
            continue
        # best control-set match wins; a shared flow context only breaks ties
        cand = [(max(sim(k, x) for x in c),
                 any(ctx[x] == ctx[k] for x in c) if ctx[k] else False,
                 len(c), [-int(p) for p in c[0].replace(':', '-').split('-')],
                 idx)
                for idx, c in enumerate(clusters)]
        if cand:
            cand.sort(reverse=True)
            idx = cand[0][-1]
            clusters[idx] = sorted(clusters[idx] + [k])
        else:
            clusters.append([k])

    out = sorted(clusters, key=lambda g: (-len(g), g[0]))
    return out, sims


def name_group(base, frames, meta, taken, siblings=(), controls=None):
    """Screen id + name for one split group.

    Naming order: a chip title the whole group agrees on (the designer's own
    words for this screen), else the base name qualified by the group's
    dominant flow context. Returns (screen_id, screen_name, named_by)."""
    counts = {}
    for f in frames:
        c = norm(meta[f]['chip_title'])
        if c and not c.lower().startswith(base.lower()):
            counts[c] = counts.get(c, 0) + 1
    # the chip names the screen only when it labels MOST of the group — one
    # stray chip inside eighteen frames is not this screen's name
    if len(counts) == 1:
        title, n = next(iter(counts.items()))
        if n * 2 >= len(frames):
            sid = _upper_snake(title)
            if sid and sid not in taken:
                return sid, title, 'CHIP'
    ctxs = {}
    for f in frames:
        c = context_of(meta[f])
        if c:
            ctxs[c] = ctxs.get(c, 0) + 1
    if ctxs:
        ctx = max(sorted(ctxs), key=lambda c: (ctxs[c], -len(c)))
        suffix = _upper_snake(ctx)
        sid = _upper_snake(base)
        if suffix and suffix != sid:
            cand = f'{sid}__{suffix}'[:120]
            if cand not in taken:
                return cand, f'{base} — {ctx}', 'CONTEXT'
    # last resort before an ordinal: a control this group has and its
    # siblings do not — an id a reviewer can still recognise in Figma
    sid = _upper_snake(base)
    if controls:
        mine = set().union(*(controls.get(f, set()) for f in frames)) \
            if frames else set()
        others = set().union(*(controls.get(f, set()) for f in siblings)) \
            if siblings else set()
        unique = sorted(mine - others, key=lambda t: (len(t), t))
        for t in unique:
            cand = f'{sid}__{_upper_snake(t)}'[:120]
            if _upper_snake(t) and cand not in taken:
                return cand, f'{base} — {t}', 'CONTROL'
    n = 2
    while f'{sid}__{n}' in taken:
        n += 1
    return f'{sid}__{n}', f'{base} ({n})', 'ORDINAL'


def _upper_snake(s):
    s = re.sub(r'[^0-9A-Za-z]+', '_', s or '').strip('_')
    return re.sub(r'_+', '_', s).upper()
