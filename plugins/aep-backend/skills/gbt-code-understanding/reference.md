# GBT Code Understanding — Reference

## Example workflow map (Phase 2 / Phase 5)

```
Create Customer
  -> Create Policy
  -> Approve Policy
  -> Fetch Policy
  -> Verify Status
  -> Delete Test Data
```

## Example API dependency graph (Phase 3)

```
POST /users
  -> GET /users/{id}
  -> PATCH /users/{id}
  -> DELETE /users/{id}
```

## Workflow construction checklist (Phase 5)

- Setup APIs: resources that must exist before the workflow under test.
- Main APIs: the workflow the test cases actually exercise.
- Verification APIs: endpoints needed to assert the result.
- Cleanup APIs: data removal so the test is repeatable and isolated.

## How the provided inputs map to phases

| Input | Phase | Source in app |
|-------|-------|---------------|
| EXEMPLARS | 1 | `gbt_repo.fetch_pattern_exemplars(module)` |
| EXISTING MATCHES | 1, 4 | `gbt_repo.find_existing_endpoint(api)` |
| SWAGGER REFERENCES | 3 | `swagger_parser.references_for_apis(url, apis)` |
| SERVICE-REPO REFERENCES | 2 | `service_repo.analyze(url, apis)` |
| TEST CASES | 4, 5 | reviewed cases (source of truth) |
