# StoryTeller — YouTube Video Planning Assistant

AI-powered assistant for planning engaging Hebrew YouTube videos. Built with **Strands Agents** on **AWS Bedrock AgentCore**, React frontend via **CloudFront**, and serverless APIs on **Lambda**.

## What it does

- 🔍 **Research** — web search, trend analysis, content extraction from URLs/PDFs
- 📝 **Plan** — structured video plans with engagement-optimized hooks, pacing, and CTAs
- 🎯 **Coach** — virality coaching, topic framing, retention optimization
- 🎙️ **Voice** — record voice messages, auto-transcribed to text
- 🎨 **Thumbnails** _(coming soon)_ — AI-generated YouTube thumbnails with iterative design
- 📄 **Export** — download plans as markdown documents

## Documentation

| Doc | What it covers |
|-----|---------------|
| [docs/PRODUCT.md](docs/PRODUCT.md) | What StoryTeller does, user flow, design principles |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | All functional requirements (current + planned) |
| [docs/TECHNICAL-DESIGN.md](docs/TECHNICAL-DESIGN.md) | Architecture, data model, sub-agents, streaming |
| [docs/LONG-RUNNING-JOBS.md](docs/LONG-RUNNING-JOBS.md) | Generic jobs system for async work (transcription, video analysis) — three-Lambda architecture with frontend polling |

## Architecture

```
CloudFront → S3 (React SPA)
     │
     └→ API Gateway → Lambda (auth, sessions, upload, transcribe)
                │
                └→ AgentCore Runtime (Strands Agent)
                        │
                        ├── Research sub-agent (web + trends)
                        ├── Tavily, Perplexity, Firecrawl
                        ├── PDF/PPTX extraction
                        └── Thumbnail sub-agent (planned, Gemini)
     │
     ├→ Cognito (JWT auth)
     ├→ DynamoDB (sessions, messages)
     ├→ S3 (uploads, exports, profile photos)
     └→ Amazon Transcribe (voice input)
```

## Project Structure

```
storyteller/
├── docs/                    # Product, requirements, technical design
├── agent/                   # Strands agent + sub-agents + tools
│   ├── runtime_app.py       # AgentCore entrypoint (streaming + keepalive)
│   ├── main.py              # Agent factory
│   ├── system_prompt.py     # System prompt
│   ├── research_agent.py    # Research sub-agent
│   └── tools/               # content_fetch, web_research, pdf_extract, etc.
├── api/                     # Lambda handlers
│   ├── auth.py, sessions.py, upload.py, transcribe.py
├── frontend/                # React + Vite + Tailwind (Hebrew RTL, dark theme)
├── infra/                   # CDK stacks (Data, Auth, Api, Frontend)
├── tests/                   # Unit tests (moto) + E2E live tests
├── scripts/                 # deploy.sh, deploy-frontend.sh, test.sh
└── .env.example             # Environment template
```

## Quick Start

```bash
# Install Python deps
uv sync

# Install frontend deps
cd frontend && npm install && cd ..

# Copy and fill env vars
cp .env.example .env
# Edit .env with your AWS values

# Run unit tests
./scripts/test.sh

# Deploy everything
./scripts/deploy-all.sh
```

## Scripts

| Script | What it does |
|--------|-------------|
| `scripts/deploy.sh` | Deploy agent to AgentCore + restore JWT auth |
| `scripts/deploy-frontend.sh` | Build + S3 sync + CloudFront invalidation |
| `scripts/deploy-all.sh` | Both of the above |
| `scripts/test.sh` | Unit tests (moto, fast) |
| `scripts/test-e2e.sh` | Playwright browser tests |
| `scripts/check-agent.sh` | Verify agent status/auth/env |

## Environment Variables

Set in `.env` (gitignored):

| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | API Gateway URL |
| `VITE_COGNITO_REGION` | Cognito region |
| `VITE_COGNITO_CLIENT_ID` | Cognito app client ID |
| `AGENT_RUNTIME_ID` | AgentCore runtime ID |
| `FRONTEND_URL` | CloudFront URL |
| `CDK_DEFAULT_ACCOUNT` | AWS account ID |
| `CDK_DEFAULT_REGION` | AWS region |

Agent runtime env vars (set via deploy script):
`MESSAGES_TABLE`, `SESSIONS_TABLE`, `UPLOAD_BUCKET`, `BEDROCK_MODEL_ID`, `BEDROCK_REGION`

## Testing

- **41 unit tests** — mocked with moto (DynamoDB, S3)
- **6 E2E live tests** — 3 positive (URL planning, topic planning, long content split) + 3 negative (off-topic, prompt injection, inappropriate content)
- **5 Playwright tests** — browser-based login, chat, session management

---

_Built by Gili · Powered by AWS Bedrock, Strands Agents, and AgentCore_
