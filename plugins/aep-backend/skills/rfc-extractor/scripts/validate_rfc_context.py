#!/usr/bin/env python3
"""
validate_rfc_context.py — hard pre-write gate for rfc_context.json.

The RFC extractor must run this before declaring an extraction done. It splits
findings into two classes:

  MECHANICAL (blocking) — schema violations and structural inconsistencies that
    are never a judgement call: bad enum values (e.g. a validation_sequence
    `layer` outside controller/service/repository/db/gateway), wrong types,
    missing required keys, additionalProperties, forbidden legacy keys,
    unresolved cross-references, non-contiguous numbering, risks not P0-first,
    prd_drift_flags/prd_drift_status disagreement, jira_epic reusing the RFC id,
    protocols_used<->contracts consistency (a declared protocol with no contract
    entry, or contracts missing one of the four protocol keys), and stable shape
    (every expected top-level key present — empty/null allowed, key absent is
    not). These MUST be fixed in the JSON before it is written — the fix is
    mechanical.

  GROUNDEDNESS (report-only) — semantic gaps (a named contract with no shape, an
    underspecified flag). These stay as extraction_gaps and are surfaced in the
    readout, never silently swallowed. This script does not judge groundedness;
    that stays with the extractor + CI.

  LINT (report-only warnings) — likely-but-not-certain consistency slips that are
    a judgement call, so they warn instead of blocking: e.g. an `in_scope` item
    that carries a deferred/conditional marker or names a deferred milestone
    (in_scope is committed scope only). Warnings never change the exit code.

Exit code: 0 when there are no mechanical errors, 1 otherwise. Stdlib + jsonschema.

Usage:
    python3 validate_rfc_context.py <rfc_context.json> [<rfc_context.schema.json>]

If the schema path is omitted, it is resolved relative to this script
(../../../schemas/rfc_context.schema.json from the plugin layout).
"""
import sys, os, json, re

FORBIDDEN_KEYS = {
    "api_contracts", "error_contract", "error_scenarios", "db_schema",
    "sequence_flows", "flows", "edge_cases", "data_model_changes",
    "sla_nfr", "observability", "needs_clarification", "is_approach_finalised",
    "service", "feature_name", "scope",
}

# every top-level key the artifact must always carry (empty array / null allowed
# where the source has nothing — the key itself must still be present). Keep in
# sync with rfc_context.schema.json properties.
EXPECTED_KEYS = (
    "id", "status", "approach_finalised", "prd_ref", "jira_epic", "author",
    "approver", "service_name", "related_docs", "in_scope", "out_of_scope",
    "requirements", "milestones", "protocols_used", "contracts",
    "rejected_alternatives", "error_codes", "validation_sequence",
    "business_logic", "db_schema_changes", "user_flows",
    "cross_service_dependencies", "service_level_changes", "feature_flags",
    "risk_areas", "non_functional_requirements", "team_ownership",
    "extraction_gaps", "open_questions", "prd_drift_flags", "prd_drift_status",
    "provenance",
)

# phrases that mark work as deferred / conditional rather than committed "now" scope
DEFERRED_MARKERS = (
    "will not implement", "will not build", "not built now", "not building now",
    "deferred", "only if", "for m2", "preferred for m2", "conditional",
)


def _default_schema_path():
    here = os.path.dirname(os.path.abspath(__file__))
    # scripts/ -> rfc-extractor -> skills -> aep-backend -> schemas/
    cand = os.path.normpath(os.path.join(here, "..", "..", "..", "schemas", "rfc_context.schema.json"))
    return cand


def _contiguous(nums):
    return list(nums) == list(range(1, len(nums) + 1))


def validate(ctx_path, schema_path):
    errors = []    # mechanical / blocking
    warnings = []  # lint / report-only

    with open(ctx_path) as f:
        d = json.load(f)
    with open(schema_path) as f:
        schema = json.load(f)

    # 1) JSON Schema (enums, types, required, additionalProperties)
    try:
        import jsonschema
        v = jsonschema.Draft7Validator(schema)
        for e in sorted(v.iter_errors(d), key=lambda e: list(e.absolute_path)):
            path = "/".join(str(p) for p in e.absolute_path) or "(root)"
            errors.append(f"[schema] {path}: {e.message}")
    except ImportError:
        errors.append("[schema] jsonschema not installed — cannot run the schema gate; install it or validate elsewhere")

    # 2) Forbidden legacy keys
    for k in d:
        if k in FORBIDDEN_KEYS:
            errors.append(f"[forbidden-key] top-level '{k}' is a legacy/renamed key — remove or rename")

    # 3) Cross-reference integrity
    codes = {e.get("code") for e in d.get("error_codes", [])}
    steps = {s.get("step") for s in d.get("validation_sequence", [])}
    for s in d.get("validation_sequence", []):
        fec = s.get("failure_error_code")
        if fec and fec not in codes:
            errors.append(f"[xref] validation_sequence step {s.get('step')}: failure_error_code '{fec}' not in error_codes[]")
    for b in d.get("business_logic", []):
        ref = b.get("validation_step_ref")
        if ref is not None and ref not in steps:
            errors.append(f"[xref] business_logic {b.get('id')}: validation_step_ref {ref} not a validation_sequence step")

    # 4) Numbering: contiguous 1..N
    for arr in ("in_scope", "out_of_scope"):
        ids = [x.get("id") for x in d.get(arr, []) if isinstance(x, dict)]
        if ids and not _contiguous(ids):
            errors.append(f"[numbering] {arr} ids not contiguous 1..N: {ids}")
    vs = [s.get("step") for s in d.get("validation_sequence", [])]
    if vs and not _contiguous(vs):
        errors.append(f"[numbering] validation_sequence steps not contiguous 1..N: {vs}")
    for i, flow in enumerate(d.get("user_flows", [])):
        fs = [st.get("step") for st in flow.get("steps", [])]
        if fs and not _contiguous(fs):
            errors.append(f"[numbering] user_flows[{i}] '{flow.get('name')}' steps not contiguous 1..N: {fs}")
    oq = [q.get("id") for q in d.get("open_questions", []) if isinstance(q, dict)]
    if oq and not _contiguous(oq):
        errors.append(f"[numbering] open_questions ids not contiguous 1..N: {oq}")
    nfr = d.get("non_functional_requirements", {}) or {}
    st = [t.get("id") for t in nfr.get("sla_nfr_targets", []) if isinstance(t, dict)]
    if st and not _contiguous(st):
        errors.append(f"[numbering] non_functional_requirements.sla_nfr_targets ids not contiguous 1..N: {st}")

    # 5) Risks P0-first
    order = {"P0": 0, "P1": 1, "P2": 2}
    pr = [order.get(r.get("priority"), 9) for r in d.get("risk_areas", [])]
    if pr != sorted(pr):
        errors.append(f"[risk-order] risk_areas not ordered P0-first: {[r.get('priority') for r in d.get('risk_areas', [])]}")

    # 6) prd_drift_flags <-> prd_drift_status consistency
    flags = d.get("prd_drift_flags", None)
    status = d.get("prd_drift_status", None)
    if flags is None and status not in (None, "not_assessed"):
        errors.append(f"[drift] prd_drift_flags is null but prd_drift_status='{status}' (expected 'not_assessed')")
    if isinstance(flags, list) and status == "not_assessed":
        errors.append("[drift] prd_drift_flags is a list (compared) but prd_drift_status='not_assessed'")

    # 7) jira_epic must not reuse the RFC's own id / tracking link (blocking).
    #    The header's `RFC` row links the doc's own key — that is `id`, not a
    #    delivery epic. If no distinct epic exists, jira_epic must be null.
    epic, rid = d.get("jira_epic"), d.get("id")
    if isinstance(epic, str) and isinstance(rid, str) and rid.strip():
        e_norm, r_norm = epic.strip().lower(), rid.strip().lower()
        if e_norm == r_norm or re.search(r"\b" + re.escape(r_norm) + r"\b", e_norm):
            errors.append(
                f"[jira-epic] jira_epic '{epic}' reuses the RFC's own id/tracking link "
                f"'{rid}' — a delivery epic must be distinct; set null if none stated"
            )

    # 8) in_scope is committed scope only — LINT (report-only) any item that
    #    carries a deferred marker or names a milestone that is itself deferred.
    deferred_ms = set()
    for m in d.get("milestones", []):
        if not isinstance(m, dict):
            continue
        blob = " ".join(str(m.get(k, "")) for k in ("scope", "timeline")).lower()
        if any(mk in blob for mk in DEFERRED_MARKERS):
            mid = m.get("id")
            if mid:
                deferred_ms.add(str(mid).lower())
    for x in d.get("in_scope", []):
        if not isinstance(x, dict):
            continue
        low = str(x.get("item", "")).lower()
        marker = next((mk for mk in DEFERRED_MARKERS if mk in low), None)
        ms_hit = next((mid for mid in deferred_ms
                       if re.search(r"\b" + re.escape(mid) + r"\b", low)), None)
        if marker or ms_hit:
            why = f"marker '{marker}'" if marker else f"names deferred milestone '{ms_hit.upper()}'"
            warnings.append(
                f"[in-scope-deferred] in_scope #{x.get('id')} looks like deferred/conditional "
                f"work ({why}) — in_scope is committed scope only; move it to milestones "
                f"(trigger in timeline) and/or out_of_scope"
            )

    # 9) protocols_used <-> contracts consistency (blocking + lint).
    #    The schema does not require `contracts`, so a whole contracts object (or
    #    a single protocol's array) can be dropped while protocols_used still
    #    advertises the protocol — the exact class of bug where declared REST/
    #    other endpoints never make it into the artifact. Catch it here.
    def _bucket(p):
        return {"rest": "rest", "grpc": "grpc", "kafka": "kafka"}.get(str(p).strip().lower(), "other")
    protos = d.get("protocols_used", []) or []
    contracts = d.get("contracts", None)
    if protos and not isinstance(contracts, dict):
        errors.append(
            f"[contracts] protocols_used={protos} but no contracts object is present — "
            f"add a contracts object with an entry for each declared protocol"
        )
    if isinstance(contracts, dict):
        for key in ("rest", "grpc", "kafka", "other"):
            if key not in contracts:
                errors.append(
                    f"[contracts] contracts.{key} key is missing — contracts must always carry "
                    f"all four protocol keys (empty array if unused)"
                )
        declared = {_bucket(p) for p in protos}
        for p in protos:
            key = _bucket(p)
            if not contracts.get(key):
                errors.append(
                    f"[contracts] protocols_used lists '{p}' but contracts.{key} is empty/missing — "
                    f"every declared protocol needs >=1 contract entry (or drop it from protocols_used)"
                )
        for key in ("rest", "grpc", "kafka", "other"):
            if contracts.get(key) and key not in declared:
                warnings.append(
                    f"[contracts-undeclared] contracts.{key} has entries but '{key}' is not in "
                    f"protocols_used — add it to protocols_used or move the entries"
                )

    # 10) Stable shape (blocking) — every expected top-level key must be PRESENT.
    #     Empty array / null is fine where the source genuinely has nothing, but
    #     the key itself must exist. additionalProperties:false bounds the shape
    #     from above; this bounds it from below, so a whole section can never be
    #     silently dropped and downstream never hits a missing field. Content
    #     correctness / non-emptiness is NOT judged here (that is the extractor's
    #     coverage cross-walk + CI golden tests).
    for key in EXPECTED_KEYS:
        if key not in d:
            errors.append(
                f"[shape] top-level key '{key}' is missing — the artifact must always carry the "
                f"full key set (empty array / null is fine when the source has nothing, but the "
                f"key itself must be present)"
            )

    return errors, warnings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 validate_rfc_context.py <rfc_context.json> [<schema.json>]", file=sys.stderr)
        sys.exit(2)
    ctx = sys.argv[1]
    schema = sys.argv[2] if len(sys.argv) > 2 else _default_schema_path()
    errs, warns = validate(ctx, schema)
    if warns:
        print(f"LINT WARNINGS ({len(warns)}) — review, non-blocking:")
        for w in warns:
            print("  - " + w)
    if errs:
        print(f"MECHANICAL ERRORS ({len(errs)}) — fix in the JSON before writing:")
        for e in errs:
            print("  - " + e)
        sys.exit(1)
    print("OK — no mechanical errors (schema + cross-refs + numbering + ordering all pass).")
    sys.exit(0)
