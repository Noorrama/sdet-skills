# gRPC prompt test — InitTaskProgress

## Input grpcurl

```bash
grpcurl -plaintext -d '{"user_id":"8427051","group_id":"1","task_ids":["2","4"]}' \
  grpc-gami-orbit-cgk.service.q.gojek.com:80 orbit.v1.RewardService/InitTaskProgress
```

## Step 1 — Alias lookup (HTTP, not MCP)

```bash
# QA example
curl -sS "https://tapmind-backend-q.golabs.io/v1/grpc/targets"

# Integration example
curl -sS "https://tapmind-backend-i.golabs.io/v1/grpc/targets"
```

Match host `grpc-gami-orbit-cgk.service.q.gojek.com` port `80` → `gami-orbit-grpc`.

If curl fails → connect to respective VPN and retry (`CONTROL_PLANE.md`).

Override without lookup: `# alias: gami-orbit-grpc` as first line of curl_reference.

## Step 2 — Generated prompts (§3.8 + §3.1.1)

**Two prompts max** — success on the execute line; detail in **one** verify-only.
Do **not** chain `Verify status is OK` then another `Verify $.field…`.

```
call mcp grpc grpc.invoke for rpc_alias: gami-orbit-grpc service: orbit.v1.RewardService Method: InitTaskProgress request: {"user_id":"8427051","group_id":"1","task_ids":["2","4"]} | verify: status is OK
```

Optional detail (single verify-only — all field asserts here):

```
Verify $.progress_id is not null
```

## Step 3 — Verify each prompt (MCP: tapmind_verify_prompt only)

```json
{
  "prompt": "call mcp grpc grpc.invoke for rpc_alias: gami-orbit-grpc service: orbit.v1.RewardService Method: InitTaskProgress request: {\"user_id\":\"8427051\",\"group_id\":\"1\",\"task_ids\":[\"2\",\"4\"]} | verify: status is OK",
  "productGroup": "<pdg>",
  "targetServiceId": "<service_name>",
  "dryRunLlm": true
}
```

Then the detail verify-only (if any) as a separate MCP verify call.

## Step 4 — Execute (MCP: tapmind_run_nlp_command only)

Execute the invoke (+ success) first; capture `conversationId`; then execute the **one** detail
verify-only with the same `conversationId` so it reuses `lastVerdict.executionTraces()`.

```json
{
  "command": "<execute prompt with | verify: status is OK>",
  "pdg": "<pdg>",
  "targetServiceId": "<service_name>"
}
```

```json
{
  "command": "Verify $.progress_id is not null",
  "pdg": "<pdg>",
  "targetServiceId": "<service_name>",
  "conversationId": "<from previous step>"
}
```

If error `no tool_call.target set` → gRPC target not registered; check
`GET /v1/grpc/targets` on the same environment host.

**Do not** use `grpc_invoke` MCP for this workflow — execute goes through NLP command only.
