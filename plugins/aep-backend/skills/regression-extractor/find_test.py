#!/usr/bin/env python3
"""Find regression test cases for the service described by an RFC context.

Reads `service_name` from an rfc_context.json, looks that service up in one or
more `<module>_regression.json` catalogues, and emits the union of the matching
`testCaseIds` entries as a JSON list of unique test case objects, written to
`test_cases.json` (override with -o, or `-o -` to print to stdout).

RFC service names are written in kebab-case (`meal-scheduler`) while the
catalogues use PascalCase keys (`MealSchedulerOrderService`) and camelCase
`serviceName` values (`mealSchedulerOrder`), and the two are often not the same
name — the catalogue entry is usually more specific. Matching therefore walks a
ladder of strategies (exact -> prefix -> token subset -> substring -> fuzzy) and
stops at the first tier that produces hits, so a loose tier only kicks in when
nothing tighter matched.

Usage:
    python3 find_test.py rfc_context.json gofood
    python3 find_test.py rfc_context.json gofood gopay -o found_tests.json
    python3 find_test.py rfc_context.json all --include-related
    python3 find_test.py rfc_context.json gofood -o -    # stdout
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

DEFAULT_REGRESSION_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = Path("test_cases.json")

# Suffixes that carry no identity — dropped before comparing names.
NOISE_TOKENS = {"service", "svc", "api", "apis", "server", "backend"}

# Loose tiers need a name with some substance behind it, or short generic names
# like "base" would match half the catalogue.
MIN_FUZZY_LENGTH = 5


def split_tokens(name: str) -> list[str]:
    """`MealSchedulerOrderService` / `meal-scheduler` -> ['meal', 'scheduler', ...]."""
    spaced = re.sub(r"[^A-Za-z0-9]+", " ", name)
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", spaced)
    spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", spaced)
    tokens = [t.lower() for t in spaced.split() if t]
    trimmed = [t for t in tokens if t not in NOISE_TOKENS]
    return trimmed or tokens


def normalize(name: str) -> str:
    """Fold a service name to a comparable form: `meal-scheduler` -> `mealscheduler`."""
    return "".join(split_tokens(name))


@dataclass(frozen=True)
class Alias:
    """One comparable spelling of a service name."""

    raw: str
    norm: str
    tokens: tuple[str, ...]

    @staticmethod
    def of(raw: str) -> "Alias":
        tokens = split_tokens(raw)
        return Alias(raw=raw, norm="".join(tokens), tokens=tuple(tokens))


@dataclass
class Match:
    service_key: str
    entry: dict[str, Any]
    tier_index: int
    score: float
    matched_on: str
    wanted: str

    @property
    def tier(self) -> str:
        return TIER_NAMES[self.tier_index]


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def score_pair(wanted: Alias, candidate: Alias, fuzzy_threshold: float) -> tuple[int, float] | None:
    """Rank one wanted/candidate pair. Returns (tier index, score) or None.

    Lower tier index = tighter match. Tier 0 is exact; tiers 1-4 progressively
    relax, and only fire for names long enough to be meaningful.
    """
    if not wanted.norm or not candidate.norm:
        return None

    # Tier 0 — identical once folded.
    if wanted.norm == candidate.norm:
        return 0, 1.0

    substantial = len(wanted.norm) >= MIN_FUZZY_LENGTH and len(candidate.norm) >= MIN_FUZZY_LENGTH
    if not substantial:
        return None

    # Tier 1 — one token list is a leading run of the other:
    # meal-scheduler -> mealSchedulerOrder.
    short, long_ = sorted((wanted.tokens, candidate.tokens), key=len)
    if short and long_[: len(short)] == short:
        return 1, len(short) / len(long_)

    # Tier 2 — every token of one appears in the other, order ignored:
    # meal-scheduler -> orderMealScheduler.
    wset, cset = set(wanted.tokens), set(candidate.tokens)
    if wset and cset and (wset <= cset or cset <= wset):
        return 2, len(wset & cset) / max(len(wset), len(cset))

    # Tier 3 — raw substring containment, for names that tokenise differently:
    # mealscheduler -> gofoodmealschedulerv2.
    if wanted.norm in candidate.norm or candidate.norm in wanted.norm:
        shorter, longer = sorted((wanted.norm, candidate.norm), key=len)
        return 3, len(shorter) / len(longer)

    # Tier 4 — edit-distance similarity, catching typos and plural drift.
    ratio = _ratio(wanted.norm, candidate.norm)
    if ratio >= fuzzy_threshold:
        return 4, ratio

    return None


TIER_NAMES = ["exact", "prefix", "token-subset", "substring", f"fuzzy"]


def aliases_for_entry(service_key: str, entry: dict[str, Any]) -> list[Alias]:
    """Every spelling of a catalogue entry worth comparing against."""
    raws = [service_key]
    service_name = entry.get("serviceName")
    if isinstance(service_name, str) and service_name.strip():
        raws.append(service_name.strip())
    seen: dict[str, Alias] = {}
    for raw in raws:
        alias = Alias.of(raw)
        seen.setdefault(alias.norm, alias)
    return list(seen.values())


def match_services(
    catalogue: dict[str, Any],
    wanted_names: Iterable[str],
    fuzzy_threshold: float,
    max_tier: int,
) -> tuple[list[Match], list[tuple[float, str]]]:
    """Best-tier matches plus the nearest misses (for diagnostics when empty)."""
    wanted = [Alias.of(name) for name in wanted_names]
    wanted = [w for w in wanted if w.norm]

    # Keyed by wanted name: each name gets its own tier ladder, so an exact hit
    # for one service does not suppress a prefix hit for another.
    per_wanted: dict[str, list[tuple[int, Match]]] = {w.raw: [] for w in wanted}
    near_misses: list[tuple[float, str]] = []

    for service_key, entry in catalogue.items():
        if not isinstance(entry, dict):
            continue

        best_ratio = 0.0
        for want in wanted:
            best: tuple[int, Match] | None = None
            for candidate in aliases_for_entry(service_key, entry):
                best_ratio = max(best_ratio, _ratio(want.norm, candidate.norm))
                result = score_pair(want, candidate, fuzzy_threshold)
                if result is None:
                    continue
                tier, score = result
                if tier > max_tier:
                    continue
                match = Match(
                    service_key=service_key,
                    entry=entry,
                    tier_index=tier,
                    score=score,
                    matched_on=candidate.raw,
                    wanted=want.raw,
                )
                if best is None or (tier, -score) < (best[0], -best[1].score):
                    best = (tier, match)
            if best is not None:
                per_wanted[want.raw].append(best)
        near_misses.append((best_ratio, service_key))

    matches: dict[str, Match] = {}
    for scored in per_wanted.values():
        if not scored:
            continue
        # Only surface the tightest tier this name produced.
        best_tier = min(tier for tier, _ in scored)
        for tier, match in scored:
            if tier != best_tier:
                continue
            kept = matches.get(match.service_key)
            if kept is None or (tier, -match.score) < (kept.tier_index, -kept.score):
                matches[match.service_key] = match

    if not matches:
        near_misses.sort(reverse=True)
        return [], near_misses[:5]

    return sorted(matches.values(), key=lambda m: (-m.score, m.service_key)), []


def read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        sys.exit(f"error: file not found: {path}")
    except json.JSONDecodeError as exc:
        sys.exit(f"error: {path} is not valid JSON: {exc}")


def get_service_names(rfc: Any, include_related: bool) -> list[str]:
    """Service names to search for, primary `service_name` first."""
    if not isinstance(rfc, dict):
        sys.exit("error: rfc context must be a JSON object")

    raw = rfc.get("service_name")
    if raw is None:
        sys.exit("error: rfc context has no 'service_name' field")

    candidates = raw if isinstance(raw, list) else [raw]
    names = [str(n).strip() for n in candidates if str(n).strip()]
    if not names:
        sys.exit("error: rfc context has an empty 'service_name'")

    if include_related:
        for field in ("service_level_changes", "cross_service_dependencies"):
            for item in rfc.get(field) or []:
                if isinstance(item, dict):
                    related = str(item.get("service") or "").strip()
                    if related:
                        names.append(related)

    return list(dict.fromkeys(names))


def resolve_modules(modules: list[str], regression_dir: Path) -> list[str]:
    """Expand `all` to every catalogue present; validate the rest."""
    available = sorted(
        p.name[: -len("_regression.json")]
        for p in regression_dir.glob("*_regression.json")
    )
    if any(m.lower() == "all" for m in modules):
        if not available:
            sys.exit(f"error: no *_regression.json files in {regression_dir}")
        return available

    unknown = [m for m in modules if m not in available]
    if unknown:
        sys.exit(
            f"error: no regression catalogue for module(s) {', '.join(unknown)} "
            f"in {regression_dir}. Available: {', '.join(available) or 'none'}"
        )
    return modules


def dedupe_key(test_case: Any) -> str:
    """Stable identity for a test case object so duplicates collapse."""
    if isinstance(test_case, dict):
        # Prefer real identifiers when present, so the same case listed under two
        # services with differing incidental fields still collapses to one.
        ident = [test_case.get(k) for k in ("id", "method_name", "name")]
        if any(v not in (None, "") for v in ident):
            return json.dumps(ident, sort_keys=True, ensure_ascii=False)
    return json.dumps(test_case, sort_keys=True, ensure_ascii=False)


def collect_test_cases(
    rfc_path: Path,
    modules: list[str],
    regression_dir: Path,
    with_source: bool,
    fuzzy_threshold: float,
    max_tier: int,
    include_related: bool,
) -> list[Any]:
    service_names = get_service_names(read_json(rfc_path), include_related)
    log = lambda msg: print(msg, file=sys.stderr)
    log(f"searching for: {', '.join(service_names)}")

    seen: set[str] = set()
    test_cases: list[Any] = []
    matched_any = False

    for module in modules:
        catalogue = read_json(regression_dir / f"{module}_regression.json")
        if not isinstance(catalogue, dict):
            sys.exit(f"error: {module}_regression.json must be a JSON object of services")

        matches, near_misses = match_services(
            catalogue, service_names, fuzzy_threshold, max_tier
        )
        if not matches:
            hint = ", ".join(f"{name} ({ratio:.2f})" for ratio, name in near_misses)
            log(f"  {module}: no match" + (f" — closest: {hint}" if hint else ""))
            continue

        matched_any = True
        for match in matches:
            raw_cases = match.entry.get("testCaseIds") or []
            if not isinstance(raw_cases, list):
                log(f"  {module}/{match.service_key}: 'testCaseIds' is not a list, skipped")
                continue

            added = 0
            for test_case in raw_cases:
                key = dedupe_key(test_case)
                if key in seen:
                    continue
                seen.add(key)
                if with_source and isinstance(test_case, dict):
                    test_case = {
                        **test_case,
                        "module": module,
                        "service": match.service_key,
                    }
                test_cases.append(test_case)
                added += 1

            log(
                f"  {module}/{match.service_key}: {len(raw_cases)} test cases "
                f"({added} new) [{match.tier} match on '{match.matched_on}' "
                f"<- '{match.wanted}', score {match.score:.2f}]"
            )

    if not matched_any:
        log(
            "no service matched in any module — try --include-related, "
            "a lower --fuzzy-threshold, or `all` as the module"
        )

    return test_cases


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find regression test cases for an RFC's service.",
    )
    parser.add_argument(
        "rfc_positional",
        nargs="?",
        metavar="RFC_CONTEXT",
        help="path to rfc_context.json",
    )
    parser.add_argument(
        "modules_positional",
        nargs="*",
        metavar="MODULE",
        help="one or more module names, or 'all' to scan every catalogue",
    )
    parser.add_argument("--rfc", help="path to rfc_context.json")
    parser.add_argument("--modules", nargs="+", default=[], help="one or more module names")
    parser.add_argument(
        "--regression-dir",
        type=Path,
        default=DEFAULT_REGRESSION_DIR,
        help="directory holding <module>_regression.json (default: this script's dir)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="where to write the JSON list (default: %(default)s); use '-' for stdout",
    )
    parser.add_argument(
        "--with-source",
        action="store_true",
        help="annotate each test case with its module and service",
    )
    parser.add_argument(
        "--exact",
        action="store_true",
        help="only accept exact name matches (disables the fallback tiers)",
    )
    parser.add_argument(
        "--max-tier",
        choices=TIER_NAMES,
        default=TIER_NAMES[-1],
        help="loosest matching tier to allow (default: %(default)s)",
    )
    parser.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=0.8,
        help="similarity ratio required by the fuzzy tier (default: %(default)s)",
    )
    parser.add_argument(
        "--include-related",
        action="store_true",
        help="also search services named in service_level_changes / "
        "cross_service_dependencies",
    )
    args = parser.parse_args()

    rfc = args.rfc or args.rfc_positional
    if not rfc:
        parser.error("an rfc_context.json path is required")

    modules = list(dict.fromkeys(args.modules_positional + args.modules))
    if not modules:
        parser.error("at least one module name is required (or 'all')")
    modules = resolve_modules(modules, args.regression_dir)

    max_tier = 0 if args.exact else TIER_NAMES.index(args.max_tier)

    test_cases = collect_test_cases(
        Path(rfc),
        modules,
        args.regression_dir,
        args.with_source,
        args.fuzzy_threshold,
        max_tier,
        args.include_related,
    )
    payload = json.dumps(test_cases, indent=2, ensure_ascii=False)

    if str(args.output) == "-":
        print(payload)
        print(f"{len(test_cases)} unique test cases", file=sys.stderr)
    else:
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"wrote {len(test_cases)} unique test cases to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
