#!/usr/bin/env python3
"""Validate charters.json and render charters.md — the approval-gate artifact.

Two jobs, both deterministic so the model never spends tokens on them:
  1. Schema + sanity validation. Exits non-zero on anything that would make the gate
     meaningless (a charter citing no source test case, a mission that isn't in charter
     form, duplicate ids, a timebox outside sane bounds).
  2. Renders charters.md.

Usage: render-charters.py <run-dir>
Reads  <run-dir>/charters.json, writes <run-dir>/charters.md
"""
import json
import re
import sys
from pathlib import Path

PRIORITIES = ("P0", "P1", "P2", "P3")
STATUSES = ("proposed", "approved", "dropped", "running", "done", "timeboxed", "aborted")
REQUIRED = (
    "id", "mission", "area", "source_test_case_ids", "rationale", "priority", "probes",
    "timebox", "data_needs", "preconditions", "risk_areas", "out_of_scope", "status",
    "focus_area", "oracle",
)

# The focus-area ids in goal-driven-exploration/references/focus-areas.md. A charter names exactly
# one: `charter = one documented flow x one focus area -> one question`. That product is what
# keeps charters small and countable; without it, synthesis drifts back into "explore the whole
# booking lifecycle", which is a test plan wearing a charter's clothes.
FOCUS_AREAS = (
    "lifecycle-background", "lifecycle-kill", "permission-denial", "nav-back",
    "deeplink-midflow", "rapid-input", "network-loss", "orientation", "locale-switch",
    "interrupt-call", "token-expiry",
)
# Focus areas with no confirmed way to induce their own condition. A charter built on one of
# these runs, finds nothing, and reports as covered - the worst outcome this skill can produce.
UNVERIFIED_FOCUS_AREAS = ("token-expiry",)

# Charter size. A charter is ONE question, ONE setup, ONE risk axis - 15-20 minutes of work.
# The old bounds (5-120 steps / 2-90 min) permitted the 45-minute multi-axis charters that the
# source PRD's own appendix is full of ("explore the full delivery journey across resto types and
# payment methods, probing driver lifecycle and GoClub accrual"). Those are unfalsifiable: a human
# runs the happy path and stops, an agent burns its budget reaching checkout and probes nothing.
# Anything bigger than this is two charters.
STEPS_MIN, STEPS_MAX = 15, 30
MINUTES_MIN, MINUTES_MAX = 8, 20

# Selection strategies (references/scoping.md 3.5) — which cases fed synthesis. "recent-failures"
# is named in the source PRD but not implemented; it is deliberately absent so a plan can't claim
# it ran.
STRATEGIES = ("all", "priority", "coverage-gap", "stale-docs", "recently-changed", "folder-diff")
# A probe has to name something real — a URI, a key, a state, a threshold — or the sub-run invents
# its own entry point and the charter's whole subject gets skipped. This is how a deep-link charter
# ends up never opening a deep link.
VAGUE_VERB = re.compile(
    r"^\s*(?:explore|test|check|verify|validate|try|examine|assess|review|investigate)\b", re.I)
# Signals that a probe names something concrete. Deliberately case-SENSITIVE: an earlier version
# folded these into one re.I regex, which silently made [A-Z]{2,} match lowercase and meant the
# check never fired on anything.
CONCRETE = (
    re.compile(r"://"),            # gojek://gocar
    re.compile(r"[a-z]_[a-z]"),    # max_scheduled_rides
    re.compile(r"[A-Z]{2,}"),      # FDS, OTW, PSV, BCS
    re.compile(r"\d"),             # 50 m, 1 km, 4 active
    re.compile(r"[\"'`]"),         # quoted UI copy
    re.compile(r"\s[A-Z]"),        # GoPay, Order, Scheduled — a proper noun past word one
)


def is_vague(probe):
    """Vague = opens with a hedge verb and names nothing concrete anywhere in the sentence."""
    s = str(probe)
    return bool(VAGUE_VERB.match(s)) and not any(rx.search(s) for rx in CONCRETE)
# The classic Bach/Bolton charter form. Enforced as a shape, not as prose style — a charter
# that reads "Verify that the user can cancel a ride" is a test case with a costume on, and the
# whole point of this skill is that the output is charters. See references/charter-grammar.md.
MISSION_RE = re.compile(r"^Explore\s+.+\bwith\b\s+.+\bto discover\b\s+.+", re.I | re.S)


def die(errors):
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)


def validate(doc):
    errors, warnings = [], []
    charters = doc.get("charters")
    if not isinstance(charters, list) or not charters:
        die(["charters.json has no 'charters' array, or it is empty"])

    seen_ids, seen_missions = set(), {}
    seen_cells = {}          # (area, focus_area) -> charter id; the coverage matrix's cell key
    for i, c in enumerate(charters):
        tag = c.get("id") or f"charters[{i}]"
        for k in REQUIRED:
            if k not in c:
                errors.append(f"{tag}: missing required field '{k}'")
        if not all(k in c for k in ("id", "mission", "timebox")):
            continue

        if c["id"] in seen_ids:
            errors.append(f"{tag}: duplicate charter id")
        seen_ids.add(c["id"])

        if not MISSION_RE.match(c["mission"].strip()):
            errors.append(
                f"{tag}: mission is not in charter form. Expected "
                f"'Explore <area> with <resources> to discover <information>', got: "
                f"{c['mission']!r}"
            )

        # Dedupe check across charters — near-identical missions mean the synthesis phase
        # produced N variations of one charter instead of N charters.
        key = re.sub(r"[^a-z0-9 ]", "", c["mission"].lower())
        key = " ".join(sorted(set(key.split()) - {"explore", "with", "to", "discover", "the", "a", "an"}))
        for other_id, other_key in seen_missions.items():
            a, b = set(key.split()), set(other_key.split())
            if a and b and len(a & b) / len(a | b) > 0.7:
                warnings.append(f"{tag}: mission overlaps heavily with {other_id} — possible duplicate")
        seen_missions[c["id"]] = key

        # Same area AND same focus area = the same cell of the coverage matrix, which means the
        # same question asked twice. The lexical mission check above only catches duplicates that
        # happen to be worded alike; this catches the ones that aren't. It's an error rather than
        # a warning because the fix is free - move one charter to an uncovered cell and get real
        # coverage for the same budget.
        cell = (c.get("area"), c.get("focus_area"))
        if all(cell) and c.get("status") != "dropped":
            if cell in seen_cells:
                errors.append(
                    f"{tag}: duplicates {seen_cells[cell]} - both are '{cell[0]}' x '{cell[1]}', "
                    f"the same coverage-matrix cell. N charters must be N different questions. "
                    f"Move this one to an uncovered cell."
                )
            else:
                seen_cells[cell] = c["id"]

        if not c.get("source_test_case_ids"):
            errors.append(
                f"{tag}: source_test_case_ids is empty. Every charter must trace to at least one "
                f"fetched BrowserStack case — that traceability is the point of this skill, and an "
                f"untraceable charter is an invented one."
            )
        if c.get("priority") not in PRIORITIES:
            errors.append(f"{tag}: priority must be one of {PRIORITIES}, got {c.get('priority')!r}")
        if c.get("status") not in STATUSES:
            errors.append(f"{tag}: status must be one of {STATUSES}, got {c.get('status')!r}")

        probes = c.get("probes") or []
        if len(probes) < 2:
            errors.append(
                f"{tag}: needs at least 2 probes — concrete openers naming real artifacts from "
                f"source-cases.json (a deep link URI, a config key, an account state, a "
                f"threshold). Got {len(probes)}. A charter that can't name what it needs is not "
                f"runnable; see references/charter-grammar.md."
            )
        elif len(probes) < 3:
            warnings.append(f"{tag}: only {len(probes)} probes — 3-6 is the useful range")
        for pr in probes:
            if is_vague(pr):
                errors.append(
                    f"{tag}: probe names nothing concrete: {pr!r}. Name the actual URI / key / "
                    f"state / value the probe uses."
                )

        risks = c.get("risk_areas") or []
        if risks and not any(
            re.search(r"\b(?:C\d{6,}|TC-\d{4,})\b", str(r)) for r in risks
        ):
            warnings.append(
                f"{tag}: no risk area cites a source case — the list may be all speculation. "
                f"Quote and cite where a case carries an observed note; prefix the rest "
                f"'Hypothesis:'."
            )

        fa = c.get("focus_area")
        if fa not in FOCUS_AREAS:
            errors.append(
                f"{tag}: focus_area must be exactly one of {FOCUS_AREAS}, got {fa!r}. A charter is "
                f"one documented flow crossed with one focus area; see "
                f"references/charter-grammar.md."
            )
        elif fa in UNVERIFIED_FOCUS_AREAS:
            warnings.append(
                f"{tag}: focus_area '{fa}' has no confirmed lever - nothing can actually induce "
                f"its condition yet. The charter will run, find nothing, and report as covered. "
                f"Confirm the lever first or pick another focus area."
            )

        oracle = c.get("oracle") or []
        if isinstance(oracle, str):
            oracle = [oracle]
        if len(oracle) < 2:
            errors.append(
                f"{tag}: oracle needs at least 2 clauses - concrete statements of what must be "
                f"true after the focus area is applied ('cart contents unchanged', 'no re-auth "
                f"prompt'). Got {len(oracle)}. Without an oracle a manual tester reports 'seemed "
                f"fine' and an agent has no basis to call anything a bug."
            )
        for cl in oracle:
            if is_vague(cl):
                errors.append(
                    f"{tag}: oracle clause names nothing checkable: {cl!r}. Say what must be true, "
                    f"concretely."
                )

        tb = c["timebox"]
        if not isinstance(tb, dict) or "steps" not in tb or "minutes" not in tb:
            errors.append(f"{tag}: timebox must be {{'steps': int, 'minutes': int}}")
        else:
            if not (STEPS_MIN <= tb["steps"] <= STEPS_MAX):
                errors.append(
                    f"{tag}: timebox.steps={tb['steps']} outside {STEPS_MIN}..{STEPS_MAX}. "
                    f"{'Split this charter - it is trying to cover more than one question.' if tb['steps'] > STEPS_MAX else 'Too small to reach its area and probe anything.'}"
                )
            if not (MINUTES_MIN <= tb["minutes"] <= MINUTES_MAX):
                errors.append(
                    f"{tag}: timebox.minutes={tb['minutes']} outside {MINUTES_MIN}..{MINUTES_MAX}. "
                    f"{'Split this charter into two, each with its own focus area.' if tb['minutes'] > MINUTES_MAX else 'Too small to be worth a setup.'}"
                )

    strat = doc.get("run", {}).get("strategy")
    if strat is not None:
        strat_list = [strat] if isinstance(strat, str) else list(strat)
        for s in strat_list:
            if s not in STRATEGIES:
                errors.append(
                    f"run.strategy contains {s!r}, which is not one of {STRATEGIES}. "
                    f"('recent-failures' appears in the PRD but is not implemented — a plan must "
                    f"not claim it ran.)"
                )

    if errors:
        die(errors)
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)


def render(doc):
    run = doc.get("run", {})
    charters = doc["charters"]
    active = [c for c in charters if c["status"] != "dropped"]
    total_steps = sum(c["timebox"]["steps"] for c in active)
    total_min = sum(c["timebox"]["minutes"] for c in active)

    folders = ", ".join(f["name"] for f in run.get("folders", [])) or "—"
    L = []
    L.append(f"# Charter plan — {run.get('scopeLabel', 'exploration')}\n")
    L.append(
        f"**Project** `{run.get('project', '?')}`"
        f"{' — ' + run['projectName'] if run.get('projectName') else ''}  \n"
        f"**Folders** {folders}  \n"
        f"**Source cases ingested** {run.get('casesIngested', '?')}  \n"
        f"**Selection strategy** {', '.join([run['strategy']] if isinstance(run.get('strategy'), str) else run.get('strategy', [])) or 'all'}  \n"
        f"**Charters** {len(active)} active"
        f"{f' ({len(charters) - len(active)} dropped)' if len(charters) != len(active) else ''}  \n"
        f"**Run mode** {run.get('runMode', '?')} · **Themes** {', '.join(run.get('themes', [])) or '?'}  \n"
        f"**Total budget** {total_steps} steps / ~{total_min} min\n"
    )
    L.append(
        "> Nothing has touched a device yet. Review below, then tell me which charters to run.\n"
        "> You can drop, reorder, retimebox, or rewrite any charter before execution.\n"
    )

    L.append("\n| # | Priority | Area | Focus area | Source cases | Budget |")
    L.append("|---|---|---|---|---|---|")
    for c in charters:
        mark = "~~" if c["status"] == "dropped" else ""
        L.append(
            f"| {c['id']} | {c['priority']} | {mark}{c['area']}{mark} | `{c.get('focus_area', '—')}` | "
            f"{len(c['source_test_case_ids'])} | {c['timebox']['steps']}s / {c['timebox']['minutes']}m |"
        )

    # --- Coverage grid: areas (rows) x focus areas (columns).
    #
    # This is the artifact worth putting in front of a release manager, and it's why a charter
    # names exactly one focus area. A flat charter list can only show what you ARE testing; the
    # grid shows what you are NOT. An empty cell at "Payment x network-loss" is a specific,
    # actionable gap. Only columns actually in use are rendered - the full 11-wide matrix is
    # mostly noise on a 5-charter plan.
    used_focus = [f for f in FOCUS_AREAS if any(
        c.get("focus_area") == f and c["status"] != "dropped" for c in charters)]
    if used_focus:
        areas = sorted({c["area"] for c in active})
        L.append("\n### Coverage grid — area × focus area\n")
        L.append("| Area | " + " | ".join(f"`{f}`" for f in used_focus) + " |")
        L.append("|---" * (len(used_focus) + 1) + "|")
        for a in areas:
            cells = []
            for f in used_focus:
                ids = [c["id"] for c in active if c["area"] == a and c.get("focus_area") == f]
                cells.append(", ".join(ids) if ids else "·")
            L.append(f"| {a} | " + " | ".join(cells) + " |")
        L.append(
            "\n> `·` is an **untested** combination, not a passing one. Cells are what this plan "
            "covers; the blanks are what it doesn't. Widen the plan or accept the gap explicitly "
            "— but decide, rather than discovering it after the run.\n"
        )

    # Test-data summary. Grouped so the user sees "two charters need a low-balance customer" once,
    # and can correct the ask here rather than after a device has been provisioned against it.
    recipes = {}
    for c in active:
        dn = c["data_needs"]
        r = dn.get("recipe") if isinstance(dn, dict) else dn
        recipes.setdefault(r or "—", []).append(c["id"])
    L.append("\n### Test data\n")
    L.append("| Recipe | Charters |")
    L.append("|---|---|")
    for r, ids in sorted(recipes.items()):
        L.append(f"| `{r}` | {', '.join(ids)} |")
    L.append(
        "\n> Recipes are resolved from TDP at run time and are **unverified** unless "
        "`references/test-data-recipes.md` says otherwise — check the asks above are ones TDP can "
        "actually satisfy. A charter that runs against the wrong customer produces findings that "
        "look real and aren't.\n"
    )

    L.append("\n---\n")
    for c in charters:
        drop = " *(dropped)*" if c["status"] == "dropped" else ""
        L.append(f"## {c['id']} · {c['area']} · {c['priority']}{drop}\n")
        L.append(f"> {c['mission']}\n")
        L.append(f"**Focus area.** `{c.get('focus_area', '—')}` — the condition injected during "
                 f"this charter (see `goal-driven-exploration/references/focus-areas.md`)\n")
        L.append(f"**Why this charter.** {c['rationale']}\n")
        L.append(f"**Traces to.** {', '.join(c['source_test_case_ids'])}\n")
        dn = c["data_needs"]
        recipe = dn.get("recipe") if isinstance(dn, dict) else dn
        L.append(f"**Test data.** `{recipe}`" + (f" — {dn['notes']}" if isinstance(dn, dict) and dn.get("notes") else "") + "\n")
        for label, key in (("Probes", "probes"),
                           ("Preconditions", "preconditions"),
                           ("Oracle — what must be true, or it's a bug", "oracle"),
                           ("Risk areas", "risk_areas"),
                           ("Out of scope", "out_of_scope")):
            items = c.get(key) or []
            if isinstance(items, str):
                items = [items]
            L.append(f"**{label}.**" + ("".join(f"\n- {i}" for i in items) if items else " —") + "\n")
        L.append(f"**Timebox.** {c['timebox']['steps']} steps / {c['timebox']['minutes']} min\n")
    return "\n".join(L) + "\n"


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: render-charters.py <run-dir>")
    run_dir = Path(sys.argv[1])
    src = run_dir / "charters.json"
    if not src.is_file():
        sys.exit(f"missing {src}")
    doc = json.loads(src.read_text(encoding="utf-8"))
    validate(doc)
    out = run_dir / "charters.md"
    out.write_text(render(doc), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
