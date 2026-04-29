# StoryTeller — Technical Design

_Version 2.0 | 2026-04-25_

---

## 1. Architecture

```
┌─────────────────────────────────────────────────────┐
│               FRONTEND (React + Vite + Tailwind)    │
│  Hebrew RTL · Dark theme · Streaming chat           │
│  Voice recording · File upload · Session sidebar    │
└──────────────────────┬──────────────────────────────┘
                       │ HTTPS
                       ▼
┌─────────────────────────────────────────────────────┐
│          API GATEWAY (REST + Cognito JWT)            │
│                                                     │
│  POST /chat-stream ──► AgentCore Runtime (HTTP      │
│     (ResponseTransferMode: STREAM, 15min timeout)   │
│  POST /transcribe ──► Lambda (start Transcribe job) │
│  GET  /transcribe/{job} ──► Lambda (poll result)    │
│  POST /auth/verify · GET /sessions · POST /upload   │
└──────────────────────┬──────────────────────────────┘
                       │
          ┌────────────┼────────────────┐
          ▼            ▼                ▼
┌──────────────┐ ┌──────────┐ ┌──────────────────┐
│  AgentCore   │ │  Lambda  │ │    Lambda         │
│  Runtime     │ │  (API)   │ │  (Transcribe)     │
│              │ │          │ │                    │
│ Strands Agent│ │ auth.py  │ │ Start/poll Amazon  │
│ + sub-agents │ │ sessions │ │ Transcribe jobs    │
│              │ │ upload   │ │                    │
└──────┬───────┘ └────┬─────┘ └────────────────────┘
       │              │
       ▼              ▼
┌─────────────────────────────────────────────────────┐
│                   DATA & SERVICES                    │
│                                                     │
│  DynamoDB: storyteller-sessions, storyteller-messages│
│  S3: uploads, frontend, profile photos, templates   │
│  Secrets Manager: tavily, perplexity, firecrawl,    │
│                   gcp/gemini-api-key                 │
│  Bedrock: Claude Sonnet 4.6 (converse-stream)       │
│  Amazon Transcribe: voice → text                    │
│  Gemini Flash Preview: thumbnail generation (planned)│
│  Cognito: user pool (shared)                        │
└─────────────────────────────────────────────────────┘
```

---

## 2. Agent Architecture

### Main Agent
- **SDK:** Strands Agents
- **Model:** `us.anthropic.claude-sonnet-4-6` on Bedrock (max_tokens: 8192)
- **Runtime:** AgentCore Runtime (direct code deploy, ARM64, 15min idle, 8hr max)
- **System prompt:** YouTube methodology + virality coaching + self-disclosure protection

### Sub-Agents

| Sub-Agent | Pattern | preserve_context | Purpose |
|-----------|---------|-------------------|---------|
| Research | `Agent.as_tool()` | `False` | One-shot web research + trend analysis |
| Thumbnail _(planned)_ | `Agent.as_tool()` | `True` | Iterative thumbnail design + generation |
| Photo Inspector _(planned)_ | `Agent.as_tool()` | `False` | One-shot: describe uploaded photo (emotions, composition) |

#### Sub-Agent Context Preservation

Strands `Agent.as_tool(preserve_context=True)` keeps the sub-agent's conversation history across multiple invocations within the same parent session. This means:

- **Research sub-agent** (`preserve_context=False`): Stateless. Each research request starts fresh — no accumulated context bloat.
- **Thumbnail sub-agent** (`preserve_context=True`): Stateful. When user says "make the text bigger" or "try a different color", the sub-agent remembers the previous generation context, prompt history, and iterations. This is essential for iterative visual design.

The sub-agent's context lives in the parent agent's process memory (AgentCore Runtime session). On cold restart, only the parent agent's DynamoDB history is reloaded — sub-agent context is lost. This is acceptable because thumbnail iterations within a single session flow are the primary use case.

### Agent Tools

| Tool | Implementation | Purpose |
|------|---------------|---------|
| `content_fetch` | Raw HTTP | URL → markdown |
| `web_research` | Tavily API | Web search with sources |
| `trend_analysis` | Perplexity sonar-pro | Deep research |
| `pdf_extract` | pdfplumber + S3 | PDF → text |
| `pptx_extract` | python-pptx + S3 | PowerPoint → text |
| `export_document` | S3 upload + presigned URL | Download video plan |
| `name_session` | DynamoDB write | Auto-name in Hebrew |
| `deep_research` | Research sub-agent | Orchestrated multi-tool research |
| `generate_thumbnail` _(planned)_ | Thumbnail sub-agent | Iterative thumbnail creation |

---

## 3. Streaming Architecture

### Request Flow
```
Frontend → API GW → AgentCore Runtime → Strands Agent → Bedrock
                                              ↓
                                    yield chunks (SSE)
                                    yield __PROGRESS__ (tool events)
                                    yield __KEEPALIVE__ (idle prevention)
                                              ↓
Frontend ← API GW ← AgentCore Runtime (streamed response)
```

### Key Design Decisions
- **ResponseTransferMode: STREAM** on API GW REST API — lifts the 29s timeout
- **Integration timeout: 15 minutes** — supports long research sessions
- **Keepalive markers** — sent every 5s during tool execution to prevent connection drops
- **Progress events** — `__PROGRESS__{"type":"progress","tool":"...","label":"..."}` inline in stream
- **Frontend strips** both `__KEEPALIVE__` and `__PROGRESS__` before rendering

---

## 4. Voice Transcription (Async Pattern)

```
Frontend                    API Gateway              Lambda              Transcribe
   │                            │                       │                     │
   ├─ POST /transcribe ────────►├──────────────────────►│                     │
   │  (base64 audio)            │                       ├─ upload to S3 ─────►│
   │                            │                       ├─ start job ─────────►
   │◄─ {job_name} ─────────────┤◄──────────────────────┤  (return immediately)│
   │                            │                       │                     │
   │  (poll every 2s)           │                       │                     │
   ├─ GET /transcribe/{job} ───►├──────────────────────►│                     │
   │◄─ {status: IN_PROGRESS} ──┤◄──────────────────────┤◄─ check job ────────┤
   │  ...                       │                       │                     │
   ├─ GET /transcribe/{job} ───►├──────────────────────►│                     │
   │◄─ {status: COMPLETED,     ┤◄──────────────────────┤◄─ get transcript ───┤
   │    text: "..."}            │                       │  (cleanup S3 + job) │
   │                            │                       │                     │
   ├─ Place text in textarea    │                       │                     │
```

No 29s timeout — client polls until complete (up to 2 minutes).

---

## 5. Observability

### AgentCore Observability (ADOT)

StoryTeller uses **AgentCore's built-in observability** via AWS Distro for OpenTelemetry (ADOT), not standalone OTEL.

**How it works:**
- `observability.enabled: true` in `.bedrock_agentcore.yaml`
- AgentCore Runtime auto-instruments the agent via ADOT sidecar — no manual setup in code
- `strands-agents[otel]` provides Strands-native OTEL trace emission
- `aws-opentelemetry-distro>=0.10.0` included as dependency
- CloudWatch Transaction Search enabled (one-time account setup)

**What you get:**
- Trace visualizations in [CloudWatch GenAI Observability dashboard](https://console.aws.amazon.com/cloudwatch/home#gen-ai-observability)
- Session-correlated spans (via `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`)
- Built-in AgentCore metrics: session count, latency, duration, token usage, error rates
- Strands agent spans: tool calls, model invocations, sub-agent calls
- Custom span metrics and error breakdowns

**Log groups:**
- Runtime logs: `/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT`
- Traces: `aws/spans` (CloudWatch Transaction Search)

---

## 6. Thumbnail Generation Design _(Planned)_

### Architecture

```
Main Agent
  │
  ├─ User: "make me a thumbnail"
  │
  ├─ Main agent calls thumbnail sub-agent (preserve_context=True)
  │     │
  │     ├─ Sub-agent proposes concept (text description)
  │     ├─ User approves / modifies
  │     ├─ Sub-agent calls Gemini Flash Preview API:
  │     │    - Text prompt (English)
  │     │    - Reference images: user photo(s) from profile
  │     │    - Style guide: template thumbnail or existing series thumbnail
  │     │    - Size: 1280×720
  │     ├─ Returns generated image → displayed inline
  │     ├─ User: "make text bigger" → sub-agent iterates (context preserved)
  │     └─ Final thumbnail saved to session
  │
  └─ Continue with video planning...
```

### User Photos Profile
- **Upload:** Same mechanism as file upload (presigned S3 URL)
- **Storage:** `profile/{email}/photos/{file_id}-{filename}`
- **Metadata:** `profile/{email}/photos.json` — array of `{file_id, filename, description, emotions, uploaded_at}`
- **Auto-describe:** On upload, a one-off sub-agent inspects the image and writes the description (focusing on emotional expression, pose, setting)
- **Agent suggestion:** When generating a thumbnail, the agent reviews available profile photos and suggests which ones fit

### Style Templates
- **Storage:** `templates/thumbnails/{template_id}.png`
- **Metadata:** `templates/thumbnails/templates.json` — `[{id, name, description, style_notes}]`
- **Admin-managed:** Files dropped into S3 folder (no UI for admin)
- **Flow:** Agent shows 3 template options → user picks one or requests custom → generation proceeds with style reference

### Series Continuity
- User provides an existing thumbnail (upload or from previous session)
- Sub-agent uses it as a style guide image in Gemini prompt
- Only text/minor elements change — visual style maintained

### Limits
- **70 generations per session** (soft limit — agent warns and can be overridden)
- **Gemini API key:** `gcp/gemini-api-key` in Secrets Manager

---

## 7. Data Model

### DynamoDB Tables

**storyteller-sessions**
```
PK: email (String)    SK: session_id (String)
Attributes: name, created_at, updated_at, status, files[], shared_with[]
```

**storyteller-messages**
```
PK: session_id (String)    SK: timestamp (String)
Attributes: role, content
```

### S3 Layout
```
{upload_bucket}/
├── uploads/{email}/{session_id}/{file_id}-{filename}    # Session files
├── voice/{email}/{session_id}/{file_id}.webm             # Voice recordings (temp)
├── profile/{email}/photos/{file_id}-{filename}           # User photos (permanent)
├── profile/{email}/photos.json                           # Photo metadata
├── templates/thumbnails/{template_id}.png                # Style templates
├── templates/thumbnails/templates.json                   # Template metadata
└── exports/{email}/{session_id}/{filename}               # Exported documents
```

---

## 8. Infrastructure (CDK)

| Stack | Resources |
|-------|-----------|
| StoryTellerData | DynamoDB tables (sessions, messages) |
| StoryTellerAuth | Cognito user pool + client |
| StoryTellerApi | API Gateway, Lambda functions (auth, sessions, upload, transcribe), AgentCore integration |
| StoryTellerFrontend | S3 bucket, CloudFront distribution, OAC, viewer-request function |

### Key Config
- All Lambda: ARM64, Python 3.13, 256MB
- API GW: REST API with CORS, Cognito authorizer
- AgentCore: direct code deploy, 15min idle timeout, 8hr max lifetime
- CloudFront: SPA rewrite, cache invalidation on deploy
- Deploy script auto-restores JWT authorizer (AgentCore deploy resets it)

---

## 9. Cost Estimate

| Component | Per Session |
|-----------|------------|
| Bedrock Sonnet 4.6 (~5 turns, ~8K in / ~4K out) | ~$0.10 |
| Tavily (2-3 calls) | ~$0.01 |
| Perplexity (1 trend analysis) | ~$0.005 |
| Amazon Transcribe (voice input) | ~$0.005 |
| Gemini thumbnail generation (3-5 images) | ~$0.05 |
| Lambda + DynamoDB + S3 | ~$0.003 |
| **Total per session** | **~$0.17** |

---

## 10. Project Structure

```
storyteller/
├── docs/                    # Documentation
│   ├── PRODUCT.md           # What StoryTeller does
│   ├── REQUIREMENTS.md      # All functional requirements
│   └── TECHNICAL-DESIGN.md  # This document
├── agent/                   # Strands agent (deployed to AgentCore)
│   ├── runtime_app.py       # Entrypoint — streaming, keepalive, DynamoDB
│   ├── main.py              # Agent factory (create_agent)
│   ├── system_prompt.py     # System prompt builder
│   ├── research_agent.py    # Research sub-agent
│   ├── prompts/             # Methodology + virality markdown
│   └── tools/               # Agent tools
├── api/                     # Lambda handlers
│   ├── auth.py
│   ├── sessions.py
│   ├── upload.py
│   └── transcribe.py        # Async voice transcription
├── frontend/                # React + Vite + Tailwind
│   └── src/
│       ├── components/
│       ├── api.ts
│       └── cognito.ts
├── infra/                   # CDK stacks
│   └── stacks/
├── tests/                   # Unit + E2E tests
├── scripts/                 # Deploy + test scripts
├── .env                     # Local config (gitignored)
├── .env.example             # Template
├── pyproject.toml
└── README.md
```

---

_For product-level overview, see [PRODUCT.md](PRODUCT.md). For detailed requirements, see [REQUIREMENTS.md](REQUIREMENTS.md)._
