# StoryTeller — YouTube Video Planning Assistant

Hebrew-first AI assistant for planning YouTube video content. Built with **Strands Agents** on **AWS Bedrock AgentCore**, React frontend served via **CloudFront**, and serverless APIs on **Lambda**.

## Architecture

```
CloudFront ──► S3 (React SPA)
     │
     └──► API Gateway ──► Lambda (auth, sessions, upload, stream-proxy)
                              │
                              └──► Bedrock AgentCore Runtime (Strands Agent)
                                       │
                                       ├── Tavily (web research)
                                       ├── Trend analysis
                                       ├── PDF/PPTX extraction
                                       └── Content fetch
     │
     └──► Cognito (JWT auth)
     │
     └──► DynamoDB (sessions, messages)
     │
     └──► S3 (file uploads)
```

## Project Structure

```
storyteller/
├── agent/                  # Strands agent (deployed to AgentCore)
│   ├── runtime_app.py      # Main entrypoint — streaming, session mgmt
│   ├── main.py             # Agent factory (create_agent)
│   ├── system_prompt.py    # System prompt builder
│   ├── prompts/            # Prompt markdown files (methodology, virality)
│   └── tools/              # Agent tools
│       ├── web_research.py
│       ├── trend_analysis.py
│       ├── pdf_extract.py
│       ├── pptx_extract.py
│       ├── content_fetch.py
│       ├── export_document.py
│       └── session_manager.py
├── api/                    # Lambda handlers
│   ├── auth.py             # Cognito JWT verification
│   ├── sessions.py         # Session CRUD
│   ├── upload.py           # File upload (presigned URLs)
│   ├── chat.py             # Legacy sync chat
│   └── stream_proxy.py     # SSE stream proxy to AgentCore
├── frontend/               # React + Vite + Tailwind
│   └── src/
│       ├── components/
│       │   ├── Chat.tsx        # Main chat + streaming logic
│       │   ├── ChatMessages.tsx # Message rendering + progress
│       │   ├── ChatInput.tsx   # Input with file upload
│       │   ├── Sidebar.tsx     # Session list
│       │   └── ...
│       ├── api.ts           # API client
│       └── cognito.ts       # Cognito auth
├── infra/                  # CDK infrastructure
│   ├── app.py
│   └── stacks/
├── tests/                  # Test suite
│   ├── conftest.py         # Shared fixtures (moto, DynamoDB, S3)
│   ├── test_runtime_app.py # Agent runtime tests
│   ├── test_system_prompt.py # System prompt validation
│   ├── test_tools.py       # Tool unit tests
│   ├── test_api.py         # Lambda handler tests
│   └── test_e2e.py         # Browser E2E tests (Playwright)
├── pyproject.toml
└── pytest.ini
```

## Setup

### Prerequisites

- Python 3.13+ with [uv](https://github.com/astral-sh/uv)
- Node.js 20+ (frontend)
- AWS CLI configured
- Bedrock AgentCore CLI (`uv add bedrock-agentcore[strands-agents]`)

### Install dependencies

```bash
# Agent + API (Python)
uv sync

# Frontend
cd frontend && npm install
```

### Environment variables

The agent runtime needs these (set via `agentcore deploy --env`):

| Variable | Description |
|---|---|
| `MESSAGES_TABLE` | DynamoDB table for message history |
| `SESSIONS_TABLE` | DynamoDB table for session metadata |
| `UPLOAD_BUCKET` | S3 bucket for file uploads |
| `BEDROCK_MODEL_ID` | Model to use (e.g. `us.anthropic.claude-sonnet-4-6`) |
| `BEDROCK_REGION` | AWS region for Bedrock |

## Scripts

All scripts are in `scripts/` and executable:

| Script | What it does |
|---|---|
| `./scripts/deploy.sh` | Deploy agent to AgentCore Runtime + restore JWT auth |
| `./scripts/deploy-frontend.sh` | Build frontend, sync to S3, invalidate CloudFront |
| `./scripts/deploy-all.sh` | Deploy agent + frontend in one go |
| `./scripts/test.sh` | Run unit tests (accepts pytest args, e.g. `-v`, `-k "parse"`) |
| `./scripts/test-e2e.sh` | Run Playwright E2E tests against deployed app |
| `./scripts/check-agent.sh` | Check agent status, JWT auth, and env vars |

## Testing

### Run unit tests (fast, no AWS needed)

```bash
uv run pytest tests/ --ignore=tests/test_e2e.py -v
```

Uses [moto](https://github.com/getmoto/moto) to mock DynamoDB and S3.

### Test coverage breakdown

| File | Tests | What's covered |
|---|---|---|
| `test_runtime_app.py` | 12 | Payload parsing, DynamoDB sessions/messages, history injection, agent cache, streaming format |
| `test_system_prompt.py` | 9 | Prompt structure, scope boundaries, conversation flow, language rules, guardrails |
| `test_tools.py` | 8 | PDF extraction, S3 file resolution, tool importability, session naming |
| `test_api.py` | 5 | Auth handler, sessions listing, file upload presigned URLs |
| `test_e2e.py` | 5 | Login flow, message send/receive, new chat (requires Playwright + deployed app) |

### Run E2E tests (needs deployed app + Playwright)

```bash
APP_URL=https://your-cloudfront-url TEST_EMAIL=user@example.com TEST_PASSWORD=pass \
  uv run pytest tests/test_e2e.py -v -m integration
```

## Deploy

### Agent (Bedrock AgentCore)

```bash
uv run agentcore deploy \
  --env MESSAGES_TABLE=storyteller-messages \
  --env SESSIONS_TABLE=storyteller-sessions \
  --env UPLOAD_BUCKET=<your-bucket> \
  --env BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6 \
  --env BEDROCK_REGION=us-east-1 \
  -auc
```

> ⚠️ AgentCore deploy resets JWT auth. Re-apply the custom JWT authorizer after each deploy.

### Frontend

```bash
cd frontend
npm run build
aws s3 sync dist/ s3://<frontend-bucket>/ --delete
aws cloudfront create-invalidation --distribution-id <dist-id> --paths "/*"
```

### Infrastructure

```bash
cd infra
cdk deploy --all
```

## Key Design Decisions

- **Streaming SSE** — Agent yields text chunks + progress events inline. Progress events are JSON objects (`{type:"progress", tool:"...", label:"..."}`) that the frontend renders as a progress bar.
- **Agent caching** — One agent instance per `email:session_id`, reused across requests. DynamoDB history injected on cold start.
- **Cognito JWT** — Single user pool shared across apps. AgentCore Runtime uses custom JWT authorizer.
- **Hebrew-first** — UI, system prompt, and all agent output in Hebrew. Internal reasoning in English.
- **Scope boundaries** — Agent restricted to YouTube video planning only. Politely redirects off-topic requests.
