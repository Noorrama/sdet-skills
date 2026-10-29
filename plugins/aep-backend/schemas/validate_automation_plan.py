#!/usr/bin/env python3
"""Validate automation_plan.json: JSON Schema + fixture config key policy."""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("validate_automation_plan: install jsonschema (pip install jsonschema)", file=sys.stderr)
    sys.exit(2)

FORBIDDEN_CONFIG_KEYS = frozenset(
    {
        "catalog_category_unconfirmed",
        "payment_method_to_be_identified",
        "needs_tdp_confirmation",
        "litmus_experiment",
        "litmus_variant",
        "experiment",
        "is_enabled",
    }
)


def collect_config_violations(plan: dict) -> list[str]:
    errors: list[str] = []
    for scenario in plan.get("automation_scenarios") or []:
        sid = scenario.get("scenario_id", "?")
        for entry in scenario.get("test_data") or []:
            fid = entry.get("fixture_id", "?")
            cfg = (entry.get("required_state") or {}).get("config")
            if not isinstance(cfg, dict):
                continue
            for key in cfg:
                if key in FORBIDDEN_CONFIG_KEYS:
                    errors.append(
                        f"{sid} / {fid}: forbidden config key '{key}' "
                        "(use to_be_identified: true for TDI handoff)"
                    )
                elif key.startswith("litmus_"):
                    errors.append(
                        f"{sid} / {fid}: forbidden config key '{key}' "
                        "(Litmus belongs in preconditions[])"
                    )
                elif key.endswith("_to_be_identified") and key != "to_be_identified":
                    errors.append(
                        f"{sid} / {fid}: forbidden config key '{key}' (use to_be_identified only)"
                    )
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <automation_plan.json>", file=sys.stderr)
        return 2

    schema_path = Path(__file__).resolve().parent / "automation_plan.schema.json"
    plan_path = Path(sys.argv[1])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    try:
        jsonschema.validate(plan, schema)
    except jsonschema.ValidationError as e:
        print(f"JSON Schema validation failed: {e.message}", file=sys.stderr)
        return 1

    violations = collect_config_violations(plan)
    if violations:
        print("automation_plan config policy failed:", file=sys.stderr)
        for line in violations:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print("automation_plan: schema ok, config policy ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
