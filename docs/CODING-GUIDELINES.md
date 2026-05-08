# StoryTeller — Coding & Operations Guidelines

Rules extracted from real incidents, lessons learned, and project conventions.
Loaded at session start; followed for every code change, bug fix, or feature.

---

## Workflow Rules

### Dev First, Always
- **Every change ships to dev first.** Verify it works end-to-end before touching prod.
- **Never deploy to prod directly** — even "trivial" fixes.
- **After prod deploy:** Smoke-test the live URL (not just Lambda invoke).

### Reproduce Before Fixing
- When a bug is reported, **reproduce it first** — via unit test, Lambda invoke, or Playwright.
- Write the failing test BEFORE writing the fix. Then the fix makes it pass.
- If you can't reproduce it, you don't understand it yet.

### Work Clean
- Changes belong in version control unless it's a throwaway experiment.
- **Always read the project README** before working on a project — it has architecture, scripts, and conventions.
- One logical change = one commit. Don't mix unrelated fixes.
- Run `tsc --noEmit` (frontend) + `cdk synth --quiet` (infra) before committing.

### Test Coverage
- Every bug fix gets a unit test that would have caught it.
- Every new feature gets tests for happy path + at least one error case.
- Run existing tests before pushing to confirm no regressions.

---

## Security — Hard Rules

- **Never open S3 buckets to public.** Serve through CloudFront with OAC.
- **Never expose Lambda functions publicly.** Always behind API Gateway + auth.
- **Never make API Gateway endpoints public without auth.** Cognito authorizer (dev) or Lambda authorizer (prod). Everything fronted by CloudFront.
- **Never hardcode secrets.** Secrets Manager for secrets, SSM for config.
- **Never echo/print credentials in logs or chat messages.**
- **Never use programmatic credentials for console federation.**

---

## AWS Best Practices (Adopted)

### Lambda
- Initialize SDK clients and DB connections **outside** the handler — reuse across invocations.
- Use keep-alive directives for persistent connections (Lambda purges idle ones).
- Never use recursive Lambda invocations — can spiral costs uncontrollably.
- Write idempotent handlers — duplicate events must produce the same result.
- For SQS event sources: function timeout must be < queue's Visibility Timeout.

### S3
- Enable versioning on important buckets (protects against accidental deletes).

### DynamoDB (General)
- Design for single-table where possible — access patterns drive schema.
- Use composite sort keys for flexible queries.
- Store large items (>400KB) in S3, reference via DDB attribute.
- Use TTL for automatic cleanup of expired data.

### CDK / IaC (General)
- Write unit tests (fine-grained assertions) for every construct.
- Use snapshot tests to catch unintended template drift.
- One construct = one logical unit of infrastructure.
- Separate stateful (DDB, S3) from stateless (Lambda, API GW) stacks.
- Use `cdk diff` before every deploy to preview changes.
- Pin CDK library versions — avoid unexpected breaking changes.
- Never store secrets in CDK context or `cdk.json` — use Secrets Manager references.
- Use `RemovalPolicy.RETAIN` on stateful resources (tables, buckets).

### Monitoring
- Set up CloudWatch Alarms on key metrics (errors, duration P95, throttles).
- Use AWS Cost Anomaly Detection for early billing alerts.
- Use dead-letter queues (DLQ) on async Lambda invocations.

---

## Bedrock & AgentCore

### Model Calling
- Use `ConverseStream` API (not `InvokeModel`) — unified interface, streaming, tool-use built-in.
- Use prompt caching (`cachePoint`) for system prompts + tool definitions — saves cost on repeated context (min 1024 tokens, 5-min TTL).
- Monitor `InvocationThrottles` CloudWatch metric — throttling masquerades as latency.

### AgentCore Runtime
- **`update_agent_runtime` is FULL-REPLACE.** Always `get_agent_runtime` first, then spread ALL fields back.
- Always include `authorizerConfiguration` + `requestHeaderConfiguration` in every runtime update (omitting = wiping JWT auth).
- Runtime session IDs must be ≥33 characters — use UUID format.
- Always pass `X-Session-Id` header from client — without it, each request spawns a new runtime session (Memory re-reads all history = expensive).
- `list_events` maxResults capped at 100 — implement pagination for longer conversations.
- Keep agent deployment package small — large ZIPs increase cold start time.
- Default execution timeout is 5 min — set appropriately for your use case.

### Strands SDK
- Use `as_tool()` pattern for sub-agents — gives parent a callable tool with typed input/output.
- Session manager is stored as `_session_manager` (private attr) — access via `agent._session_manager`.
- Use streaming with keepalive events for long-running turns — prevents client timeout (API GW 29s limit).
- Catch tool exceptions gracefully — unhandled exceptions crash the agent loop and return partial responses.

---

## AWS / Infrastructure (Project-Specific)

### IAM
- **Permissions are part of the feature — not an afterthought.** Whenever you add, change, or remove functionality: ask what AWS actions the runtime component (Lambda, ECS task, EC2) needs, and update its IAM role accordingly. Adding a DDB read? Grant `GetItem`. Removing an S3 write? Revoke `PutObject`. Silent `AccessDenied` errors are the #1 cause of "works in dev" bugs.
- **When a Lambda calls a new AWS service for the first time, always add the grant in the same CDK commit as the code change.**
- Use `storyteller-*` wildcard for DynamoDB policies (tables have fixed names across environments).
- Check BOTH the CDK-managed policy AND manually-attached inline policies on the runtime role.

### AgentCore Runtime
- **`update_agent_runtime` is FULL-REPLACE.** Always `get_agent_runtime` first, then spread ALL fields back. Omitting `authorizerConfiguration` = wiping JWT auth.
- **Never call `update_agent_runtime` directly** — use `scripts/update_runtime_env.py` or `deploy.sh`.
- **`agentcore deploy` also wipes authorizer config.** `deploy.sh` re-applies it automatically in the post-deploy step.
- Runtime caches processes for 15 min (idle timeout). Config changes don't take effect until the cached process expires.

### DynamoDB
- Table names are fixed: `storyteller-sessions`, `storyteller-messages`, `storyteller-jobs`.
- Same names in dev (us-west-2) and prod (us-east-1) — different regions, no collision.
- No `MESSAGES_TABLE` / `SESSIONS_TABLE` env vars needed for AgentCore — code defaults match.
- Always paginate Scans (1MB limit per call).
- Reserved words in expressions → use `ExpressionAttributeNames`.

### CDK / CloudFormation
- Cross-stack exports block table renames. Use inline IAM with ARN wildcards instead of `grant_read_write_data()` to avoid export dependencies.
- `RemovalPolicy.RETAIN` keeps orphaned resources — remember to delete old tables after migration.
- Changing `table_name` = REPLACEMENT (new table, not rename). Plan data migration.
- Always `cdk diff` before `cdk deploy` to preview changes.
- Deploy order matters: API stack first (remove imports), then data stack (remove exports).

### CloudFront
- Invalidate `/*` after every frontend deploy.
- Custom domains need alias + ACM cert — CDK updates can wipe manual config.
- SPA routing: viewer-request CF Function for path rewriting.

---

## StoryTeller-Specific

### Code Defaults
- Agent code defaults to correct table/bucket names. Only `UPLOAD_BUCKET` needs an env var (auto-generated bucket name).
- `AGENTCORE_MEMORY_ID` must be set on runtime (per-environment memory store).
- `BEDROCK_REGION` must match the deployment region.

### Versioning
- App version is derived from **git tags** via `git describe --tags --always` at build time.
- Exported as `VITE_APP_VERSION` during frontend build (shown as a subtle badge in bottom-right corner).
- **Tag every meaningful release** with semver: `git tag v1.1.0 && git push --tags`.
- Format: `v<major>.<minor>.<patch>` — between tags, `git describe` produces `v1.0.0-3-gabcdef`.
- If no tag exists, falls back to `0.0.0-<short-hash>`.
- Use the version to correlate bug reports with deployed code.

### Deploy Checklist
1. `cd frontend && npx tsc --noEmit` — catch type errors
2. `cd infra && cdk synth --context stage=dev --quiet` — catch CDK issues  
3. `grep -rn 'password\|secret\|token\|api.key' --include='*.ts' --include='*.py'` — no secrets
4. `pytest tests/` — unit tests pass
5. `./scripts/deploy.sh dev` — deploys infra + agent + restores auth
6. Smoke test the live dev URL

### Session Sharing
- Sessions use email as partition key + session_id as sort key.
- `shared_with` is a list attribute on the session item.
- Shared users can read (scan with `contains` filter) but cannot delete.
- Dedup before appending to `shared_with` (read-then-write, not ConditionExpression).

### Frontend
- RTL Hebrew UI — `justify-end` in Tailwind = LEFT (logical end, counterintuitive).
- ReactMarkdown needs `remark-gfm` plugin for tables.
- `VITE_AUTH_MODE` switches between cognito/federate at build time.
- Auth headers are always async (`await authHeaders()`).

---

## Common Mistakes to Avoid

| Mistake | What happens | Prevention |
|---------|-------------|-----------|
| Omit fields in `update_agent_runtime` | JWT auth wiped, 403 on all requests | Use `update_runtime_env.py` |
| `ConditionExpression` catch with wrong exception class | Silently falls through to fallback | Use read-then-write pattern |
| DDB `contains` in ConditionExpression with generic `except` | Duplicates created | Always handle `ClientError` specifically |
| Change `table_name` in CDK without migration plan | Empty new table, data lost in old | Migrate data before/after deploy |
| `sed` with Unicode in Python files | Breaks characters | Use `edit` tool |
| Deploy without re-applying AgentCore auth | Production down | Always use `deploy.sh` |
| Test with short session IDs | AgentCore rejects (needs ≥33 chars) | Use UUID format |
| `|| echo` on critical deploy commands | Failures silently swallowed | Never suppress exit codes |

---

_Updated: 2026-05-06. Source: real incidents from project history._
