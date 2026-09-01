#!/usr/bin/env python3
"""
Validate code-change-extractor output against its schema.

Usage:
  python3 validate.py <code_change_context.json> [<more.json> ...]

The reconciliation findings are an embedded `reconciliation` object inside
code_change_context.json (null/absent for extraction-only runs), so there is a
single schema to validate against.

Reports and exits non-zero on failure; does not block callers that ignore the code.
"""
import json
import os
import sys

try:
    import jsonschema
except ImportError:
    sys.exit("jsonschema not installed: pip install jsonschema")

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.normpath(os.path.join(HERE, "..", "..", "..", "schemas", "code_change_context.schema.json"))


def validate(path):
    with open(path) as f:
        doc = json.load(f)
    with open(SCHEMA) as f:
        schema = json.load(f)
    jsonschema.validate(doc, schema)
    print(f"OK   {os.path.basename(path)} -> code_change_context.schema.json")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ok = True
    for path in sys.argv[1:]:
        try:
            validate(path)
        except (jsonschema.ValidationError, json.JSONDecodeError) as e:
            ok = False
            print(f"FAIL {os.path.basename(path)}: {e.message if hasattr(e, 'message') else e}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
