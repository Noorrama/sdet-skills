# TapMind control plane — MCP + HTTP access

This skill uses **two MCP tools** for NLP verify/execute. Everything else uses **read-only
HTTP** against the TapMind control plane (curl or shell), not extra MCP servers.

## MCP tools (only these)

| MCP tool | Backend endpoint | Use |
|---|---|---|
| `tapmind_verify_prompt` | `POST /v1/runs/verifyPrompt` | Dry-run / correct one prompt at a time |
| `tapmind_run_nlp_command` | `POST /v1/nlp/command` | Execute one prompt at a time; reuse `conversationId` |

**Do not** call `grpc_invoke`, `tapmind_ingest_curl`, `postgres_query`, `redis_get`, or other
MCP tools from this skill unless the user explicitly asks outside the NLP pipeline.

gRPC §3.8 prompts are verified and executed **only** through the two tools above. The planner
inside `tapmind_run_nlp_command` routes to `grpc.invoke` internally — never bypass with a
direct gRPC MCP call.

## Control plane hosts

| Environment | Host | Swagger UI |
|---|---|---|
| Integration | `tapmind-backend-i.golabs.io` | `https://tapmind-backend-i.golabs.io/swagger-ui/index.html` |
| QA | `tapmind-backend-q.golabs.io` | `https://tapmind-backend-q.golabs.io/swagger-ui/index.html` |
| Local dev | `localhost:8080` | `http://localhost:8080/swagger-ui/index.html` |

Pick host from plan `environments[]`, tasks context, or user instruction. Default to
**integration** when unknown.

Base URL pattern: `https://<host>` (or `http://localhost:8080` locally).

## Allowed HTTP controllers (read + registry lookup)

Use **GET** for lookups during prompt generation. **Do not** call ingest, database, or cache
controllers from this skill.

### gRPC Targets (`#/gRPC%20Targets`)

| Method | Path | Use |
|---|---|---|
| GET | `/v1/grpc/targets` | List all aliases → build host:port → `rpc_alias` map |
| GET | `/v1/grpc/targets/{alias}` | Confirm one alias before generate/execute |

```bash
curl -sS "https://tapmind-backend-i.golabs.io/v1/grpc/targets"
curl -sS "https://tapmind-backend-i.golabs.io/v1/grpc/targets/gami-orbit-grpc"
```

### gRPC Static Proto (`#/gRPC%20Static%20Proto`)

| Method | Path | Use |
|---|---|---|
| GET | `/v1/grpc/static-proto` | Proto alias summaries |
| GET | `/v1/grpc/static-proto/aliases` | Aliases with compiled proto (when reflection off) |
| GET | `/v1/grpc/static-proto/{alias}/versions/{version}` | Proto set detail |

Read-only from this skill — do not upload or delete proto sets unless the user explicitly
requests registry maintenance.

### Target Registry (`#/target-registry-controller`)

| Method | Path | Use |
|---|---|---|
| GET | `/v1/targets` | REST service → URL map (for HTTP prompt pinning / diagnostics) |

### Verify Prompt (`#/verify-prompt-controller`)

| Method | Path | Use |
|---|---|---|
| POST | `/v1/runs/verifyPrompt` | Prefer MCP `tapmind_verify_prompt`; direct HTTP only if MCP unavailable |

### NLP Command (`#/nlp-command-controller`)

| Method | Path | Use |
|---|---|---|
| POST | `/v1/nlp/command` | Prefer MCP `tapmind_run_nlp_command`; direct HTTP only if MCP unavailable |

### Verify Schema (`#/verify-schema-controller`)

| Method | Path | Use |
|---|---|---|
| POST | `/v1/verify/schema` | Explicit response schema validation (§9 case 2) |

## Forbidden from this skill

Do **not** call these controllers or MCP tools during generate / verify / run / convert:

- Ingest (OpenAPI, curl ingest, spec ingest)
- Database / Postgres controllers
- Redis / cache controllers
- `tapmind_ingest_curl`, `grpc_invoke`, `postgres_query`, `redis_get` as workflow steps

If REST verify shows no matching operation, flag `NEEDS_REVIEW` — do not auto-ingest.

## VPN / connectivity errors

On **connection refused**, **timeout**, **502/503**, or body containing `INTERNAL_ERROR` /
`unexpected internal error` from control-plane HTTP or MCP:

> **Cannot reach TapMind control plane.** Please connect to the respective VPN
> (integration → corporate VPN for `tapmind-backend-i.golabs.io`, QA → VPN for
> `tapmind-backend-q.golabs.io`) and retry.

Do not retry blindly or invent registry data.

## gRPC execute failures

If `tapmind_run_nlp_command` returns errors like `no tool_call.target set` or missing gRPC
target:

1. `GET /v1/grpc/targets` on the same environment host — confirm `rpc_alias` exists and
   host/port matches the grpcurl.
2. If missing → `NEEDS_REVIEW: register gRPC target via PUT /v1/grpc/targets/{alias}`
   (user/admin action; not done by this skill automatically).
3. If alias exists but execute still fails → check VPN and static proto when
   `reflection_enabled: false`.

## grpcurl → prompt (no MCP needed for conversion)

Conversion is local grammar (§3.8) + optional HTTP registry lookup:

```
grpcurl -plaintext -d '{"user_id":"8427051",...}' \
  grpc-gami-orbit-cgk.service.q.gojek.com:80 orbit.v1.RewardService/InitTaskProgress
        │
        ├─ GET /v1/grpc/targets → rpc_alias: gami-orbit-grpc
        └─ emit §3.8 prompt string
        │
        ├─ tapmind_verify_prompt (optional test)
        └─ tapmind_run_nlp_command (optional test)
```
