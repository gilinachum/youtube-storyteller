# StoryTeller — Tech Stack & Build System

## Language & Runtime
- **Python**: 3.13 (managed via `uv`, virtual env at `.venv/`)
- **Node.js**: For frontend tooling (npm)

## Backend
- **Web framework**: FastAPI (Lambda handlers in `api/`)
- **AI Agent SDK**: Strands Agents (`strands-agents[otel]`)
- **Agent Runtime**: AWS Bedrock AgentCore (direct code deploy, ARM64)
- **AI Model**: `us.anthropic.claude-sonnet-4-6` via Bedrock ConverseStream API
- **Research tools**: Tavily (web search), Perplexity sonar-pro (trend analysis), Firecrawl
- **Thumbnail generation**: Google Gemini Flash Preview (`google-genai`)
- **PDF extraction**: pdfplumber
- **PPTX extraction**: python-pptx

## Frontend
- **Framework**: React 19 + TypeScript
- **Build tool**: Vite 8
- **Styling**: Tailwind CSS 3 + PostCSS
- **UI components**: Shadcn
- **Markdown rendering**: react-markdown + remark-gfm
- **Auth**: amazon-cognito-identity-js
- **Layout**: Hebrew RTL, dark theme (gray-950), Heebo font

## AWS Services
- **Compute**: Lambda (ARM64, Python 3.13, 256MB), AgentCore Runtime
- **API**: API Gateway REST (streaming mode, 15min timeout)
- **Auth**: Cognito user pool + JWT authorizer
- **Database**: DynamoDB (`storyteller-sessions`, `storyteller-messages`, `storyteller-jobs`)
- **Storage**: S3 (uploads, exports, profile photos, frontend, templates)
- **CDN**: CloudFront (SPA rewrite, OAC, media cookie auth)
- **Voice**: Amazon Transcribe (async job pattern)
- **Secrets**: Secrets Manager (tavily, perplexity, firecrawl, gcp/gemini-api-key)
- **Observability**: CloudWatch GenAI dashboard via ADOT auto-instrumentation
- **IaC**: AWS CDK (4 stacks: Data, Auth, Api, Frontend)

## Testing
- **Unit tests**: pytest + moto (DynamoDB/S3 mocking)
- **E2E live tests**: custom scripts against live AWS
- **Browser tests**: Playwright

## Common Commands

```bash
# Python deps (always use uv, activate .venv first)
uv sync
source .venv/bin/activate

# Run unit tests
./scripts/test.sh
# or directly:
pytest tests/ -v

# Run E2E tests (requires live AWS)
./scripts/test-e2e.sh

# Frontend dev server (run manually in terminal)
cd frontend && npm run dev

# Frontend type check
cd frontend && npx tsc --noEmit

# Frontend build
cd frontend && npm run build

# Deploy agent to AgentCore + restore JWT auth
./scripts/deploy.sh dev
./scripts/deploy.sh prod

# Deploy frontend (build + S3 sync + CloudFront invalidation)
./scripts/deploy-frontend.sh dev

# Deploy everything
./scripts/deploy-all.sh dev

# Safe runtime env var update (NEVER call update_agent_runtime directly)
python3 scripts/update_runtime_env.py KEY=value
python3 scripts/update_runtime_env.py --remove OLD_KEY

# Check agent status/auth/env
./scripts/check-agent.sh

# CDK synth (preview infra changes)
cd infra && cdk synth --context stage=dev --quiet

# CDK diff (preview before deploy)
cd infra && cdk diff --context stage=dev
```

## Key Config Files
- `.env` — local environment variables (gitignored); copy from `.env.example`
- `pyproject.toml` — Python project + dependencies
- `pytest.ini` — pytest configuration
- `frontend/package.json` — frontend dependencies
- `cdk-outputs-dev.json` / `cdk-outputs-prod.json` — deployed stack outputs

## Environment Variables (`.env`)
| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | API Gateway URL |
| `VITE_COGNITO_REGION` | Cognito region |
| `VITE_COGNITO_CLIENT_ID` | Cognito app client ID |
| `AGENT_RUNTIME_ID` | AgentCore runtime ID |
| `FRONTEND_URL` | CloudFront URL |
| `CDK_DEFAULT_ACCOUNT` | AWS account ID |
| `CDK_DEFAULT_REGION` | AWS region |

Agent runtime env vars (set via deploy script): `UPLOAD_BUCKET`, `BEDROCK_MODEL_ID`, `BEDROCK_REGION`, `AGENTCORE_MEMORY_ID`

## Critical Rules
- **Never call `update_agent_runtime` directly** — use `scripts/update_runtime_env.py` or `deploy.sh`. It is full-replace; omitting fields wipes JWT auth.
- **DynamoDB table names are fixed** across dev/prod (different regions, no collision). No table name env vars needed.
- **App version** is derived from git tags via `git describe --tags --always` at build time.
- **Dev first, always** — every change ships to dev before prod.
