# StoryTeller — Technical Design Document

_Version 1.0 | 2026-04-22 | Author: Loki (with Gili)_

---

## 1. Product Summary

StoryTeller is a web app that helps AWS Solution Architects create engaging Hebrew YouTube videos. Users provide source material (URLs, PDFs, presentations, free text), and an AI agent plans, structures, and scripts videos optimized for audience retention and virality.

**Key capabilities:**
- Content ingestion from multiple source types + agent-driven web research
- Trend analysis and virality coaching (topic framing, hook formulas, posting timing)
- Engagement-optimized video structure (3-7 min per video, auto-split into series when needed)
- Full Hebrew script or outline generation (agent thinks in English, outputs in Hebrew)
- Conversational editing — user and agent iterate on the output
- Review mode for existing scripts

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (React SPA)                  │
│                                                         │
│  CopilotKit UI + AG-UI Protocol                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │ Chat     │ │ Sidebar  │ │ File     │ │ Generative│  │
│  │ Panel    │ │ History  │ │ Upload   │ │ UI Cards  │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
│                         │                               │
│            HTTPS (streaming)                            │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│               API LAYER (API Gateway + Lambda)          │
│                                                         │
│  POST /chat          — agent conversation               │
│  POST /auth/verify   — email validation                 │
│  GET  /sessions      — list user sessions               │
│  GET  /sessions/:id  — load session history             │
│                                                         │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│            AGENT LAYER (AgentCore Runtime)               │
│                                                         │
│  Strands Agent (Python)                                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │ System Prompt: YouTube methodology + virality    │   │
│  │                                                  │   │
│  │ Tools:                                           │   │
│  │  ├── content_fetch    (Firecrawl → URL scrape)   │   │
│  │  ├── pdf_extract      (pdfplumber)               │   │
│  │  ├── pptx_extract     (python-pptx)              │   │
│  │  ├── web_research     (Perplexity sonar-pro)     │   │
│  │  ├── trend_analysis   (Perplexity deep research) │   │
│  │  ├── session_manager  (DynamoDB CRUD)            │   │
│  │  └── export_document  (markdown generation)      │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  Model: Claude Sonnet 4.6 on Bedrock                    │
│  Memory: AgentCore Memory (per-user sessions)           │
│                                                         │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    DATA & SERVICES                       │
│                                                         │
│  DynamoDB ─── sessions table (user, conversation, name) │
│  S3 ──────── uploaded files (PDFs, PPTXs)               │
│  Secrets Mgr ── firecrawl/api-key, perplexity/api-key   │
│  Bedrock ──── Claude Sonnet 4.6 (converse-stream)       │
│  AgentCore Memory ── conversation history per user      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Component Details

### 3.1 Frontend — React SPA with CopilotKit

**Framework:** React (Vite) + CopilotKit + Tailwind CSS

**Why CopilotKit:**
- AG-UI protocol for bidirectional agent ↔ UI communication
- Generative UI: agent can render interactive cards (topic framings as selectable options, progress status blocks, structured outlines)
- Built-in chat panel, conversation threading, file upload/download
- Static SPA — no server-side rendering needed
- Connects directly to our FastAPI/Lambda backend

**Key UI components:**

| Component | Purpose |
|-----------|---------|
| Chat panel | Main agent conversation |
| Conversation sidebar | History of named sessions |
| Email gate | Landing page: textbox → reject non-`@amazon.com` |
| File drop zone | Upload PDF, PPTX, or paste URLs |
| Progress status area | Inline agent progress updates during research |
| Topic framing cards | Interactive selection of agent-suggested angles |
| Outline preview | Structured view of video outline with sections |

**Auth flow:**
1. User enters email address in textbox
2. Frontend validates `@amazon.com` domain (client-side + server-side)
3. No password, no Cognito — just email as user identifier
4. Session stored in DynamoDB keyed by email
5. (Phase 2: migrate to Cognito with SSO)

### 3.2 API Layer — API Gateway + Lambda

**Why Lambda (not direct AgentCore endpoint):**
- AgentCore Runtime doesn't expose a public HTTP endpoint
- Lambda handles auth validation, session routing, and request shaping
- API Gateway provides HTTPS, throttling, and CORS for the SPA

**Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/auth/verify` | Validate `@amazon.com` email, return session token |
| `POST` | `/chat` | Stream agent response (SSE) for a conversation turn |
| `GET` | `/sessions` | List user's named conversations |
| `GET` | `/sessions/{id}` | Load conversation history |
| `POST` | `/upload` | Upload file to S3, return reference key |

**Lambda runtime:** Python 3.13, arm64

### 3.3 Agent Layer — Strands on AgentCore Runtime

**Agent SDK:** Strands Agents (`strands-agents`)
**Model:** `anthropic.claude-sonnet-4-6-v1:0` on Bedrock (cost-effective for iterative conversation; Opus available for complex analysis if needed)
**Deployment:** AgentCore Runtime (serverless microVM, up to 8hr sessions)

#### System Prompt Structure

The system prompt is the core of StoryTeller's intelligence. It contains:

1. **Role definition** — You are a YouTube video planning expert specializing in Hebrew tech content
2. **YouTube methodology** — The full engagement framework from the bootstrap doc (7-part structure, hook formulas, retention data, danger zones)
3. **Virality coaching rules** — Always analyze trends, suggest topic combinations, recommend framing angles
4. **Language rules** — Think and plan in English internally; all user-facing output in Hebrew (unless user requests English)
5. **Video constraints** — 3-7 minutes per video; if content exceeds 7 min, propose a series (1 overview + 2-5 topic videos)
6. **Conversation behavior** — Greet user, explain capabilities, show progress during research, auto-name conversations, offer 2-3 variants based on material richness
7. **Output formats** — Outline mode (Hebrew bullet points per section with timing) or full script mode (natural spoken Hebrew)

#### Agent Tools

| Tool | Implementation | Purpose |
|------|---------------|---------|
| `content_fetch` | Firecrawl API (`/v1/scrape`) | URL → clean markdown |
| `pdf_extract` | `pdfplumber` | PDF → text extraction |
| `pptx_extract` | `python-pptx` | PowerPoint → slide text + notes |
| `web_research` | Tavily API (advanced search) | Search web for context, sources, competitive landscape |
| `trend_analysis` | Perplexity API (`sonar-pro`) | Deep synthesis on what's trending in user's topic area |
| `session_name` | DynamoDB update | Auto-name the conversation based on topic discussed |
| `export_document` | Python string formatting | Generate clean markdown output with chapters, timestamps, SEO tags |

#### Tool API Keys

All from Secrets Manager (never hardcoded):
- `firecrawl/api-key` — Firecrawl scraping
- `tavily/api-key` — Web search (Tavily)
- `perplexity/api-key` — Trend analysis + synthesis (Perplexity)
- Bedrock — IAM role (no key)

### 3.4 Data Layer

#### DynamoDB — Sessions Table

```
Table: storyteller-sessions
PK: email (String)         — user email
SK: session_id (String)    — UUID
Attributes:
  - name (String)          — agent-generated conversation name
  - created_at (String)    — ISO timestamp
  - updated_at (String)    — ISO timestamp
  - status (String)        — active | archived
  - language (String)      — he | en (default: he)
  - metadata (Map)         — topic, source_type, video_count, etc.
```

#### DynamoDB — Messages Table

```
Table: storyteller-messages
PK: session_id (String)    — matches sessions table SK
SK: timestamp (String)     — ISO timestamp + sequence
Attributes:
  - role (String)          — user | assistant | system
  - content (String)       — message text
  - tool_calls (List)      — tool invocations (if any)
  - ui_elements (Map)      — generative UI card data (if any)
```

#### S3 — File Uploads

```
Bucket: storyteller-uploads-{account_id}
Prefix: uploads/{email}/{session_id}/
Lifecycle: 30-day expiration
Encryption: AES-256
Public access: blocked
```

### 3.5 AgentCore Memory

Used for semantic memory across sessions — the agent can recall:
- User's preferred topics and style
- Past video plans (to avoid repetition and suggest series continuations)
- Feedback patterns (e.g., "this user always wants shorter hooks")

This is supplementary to DynamoDB session history. AgentCore Memory provides semantic search over past interactions, not just chronological replay.

---

## 4. Conversation Flow (Detailed)

```
USER                          AGENT                         SERVICES
 │                              │                              │
 ├─ Opens app, enters email ───►│                              │
 │                              ├─ Validate @amazon.com ──────►│ API
 │◄── Welcome + capabilities ───┤                              │
 │                              │                              │
 ├─ "I want to make a video    │                              │
 │   about AgentCore Memory"   │                              │
 │   + attaches PDF ──────────►│                              │
 │                              ├─ Extract PDF ───────────────►│ pdfplumber
 │                              ├─ [Status: Extracting PDF]    │
 │                              ├─ Research topic ────────────►│ Perplexity
 │                              ├─ [Status: Researching trends]│
 │                              ├─ Analyze + frame topic       │
 │◄── "I found 3 angles:       │                              │
 │     1. [card] Problem-first  │                              │
 │     2. [card] Tutorial       │                              │
 │     3. [card] Myth-busting"  │                              │
 │     + "I also found X is     │                              │
 │     trending — add to        │                              │
 │     sources?" ───────────────┤                              │
 │                              │                              │
 ├─ "Option 1, and yes add it" ►│                              │
 │                              ├─ Generate outline            │
 │                              ├─ [Status: Building outline]  │
 │◄── Video outline (Hebrew):   │                              │
 │    Hook (0-15s): ...         │                              │
 │    Promise (15-30s): ...     │                              │
 │    ... (full structure)      │                              │
 │    Est. duration: 5:30       │                              │
 │    ────────────────────────  │                              │
 │    "Want full script or      │                              │
 │     adjustments?"            │                              │
 │                              │                              │
 ├─ "Make the hook stronger,   │                              │
 │   then give me full script" ►│                              │
 │                              ├─ Revise + generate script    │
 │                              ├─ Auto-name: "AgentCore       │
 │                              │   Memory — Problem-First"    │
 │◄── Full Hebrew script        │                              │
 │    + chapter timestamps      │                              │
 │    + thumbnail suggestions   │                              │
 │    + SEO tags (Hebrew)       │                              │
 │                              │                              │
```

---

## 5. Deployment Architecture

### Phase 1 (MVP) — Serverless on AWS

| Component | Service | Spec |
|-----------|---------|------|
| Frontend | S3 + CloudFront | Static React SPA, HTTPS |
| API | API Gateway (REST) + Lambda | Python 3.13, arm64, 256MB |
| Agent | AgentCore Runtime | Strands agent, microVM |
| Memory | AgentCore Memory | Per-user semantic memory |
| Sessions | DynamoDB | On-demand capacity |
| Files | S3 | 30-day lifecycle |
| Secrets | Secrets Manager | Firecrawl, Perplexity keys |
| Model | Bedrock | Claude Sonnet 4.6 |
| CDN | CloudFront | SPA hosting + viewer-request rewrite |
| Auth | Email validation | `@amazon.com` only |

### Phase 2 (Future)

- Cognito authentication with Amazon SSO
- Document export (Google Docs / PDF)
- Filming guidance mode
- Multi-language support beyond Hebrew/English
- Analytics dashboard (which topics perform best)
- Team features (shared video library)

---

## 6. Cost Estimate (Per Session)

| Component | Est. Cost per Session |
|-----------|----------------------|
| Bedrock Sonnet 4.6 (~5 turns, ~8K input / ~4K output tokens) | ~$0.10 |
| Tavily search (2-3 calls) | ~$0.01 |
| Perplexity sonar-pro (1 trend analysis) | ~$0.005 |
| Firecrawl scrape (1-2 URLs) | ~$0.01 |
| Lambda (5 invocations, ~10s each) | ~$0.001 |
| DynamoDB (R/W) | ~$0.001 |
| AgentCore Runtime | TBD (preview pricing) |
| **Total per session** | **~$0.13** |

Extremely cost-effective for the value delivered.

---

## 7. Project Structure

```
projects/storyteller/
├── BOOTSTRAP-STORYTELLER.md     # Original bootstrap doc
├── TECHNICAL-DESIGN.md          # This document
├── pyproject.toml               # Python deps (uv)
├── uv.lock
│
├── agent/                       # Strands agent
│   ├── main.py                  # Agent entrypoint
│   ├── system_prompt.py         # System prompt builder
│   ├── tools/
│   │   ├── content_fetch.py     # Firecrawl URL scraping
│   │   ├── pdf_extract.py       # PDF text extraction
│   │   ├── pptx_extract.py      # PowerPoint extraction
│   │   ├── web_research.py      # Perplexity search
│   │   ├── trend_analysis.py    # Perplexity trend research
│   │   ├── session_manager.py   # DynamoDB session ops
│   │   └── export_document.py   # Markdown output generation
│   ├── prompts/
│   │   ├── methodology.md       # YouTube engagement framework
│   │   └── virality.md          # Virality coaching rules
│   └── .bedrock_agentcore.yaml  # AgentCore deployment config
│
├── api/                         # Lambda handlers
│   ├── chat.py                  # POST /chat — stream agent
│   ├── auth.py                  # POST /auth/verify
│   ├── sessions.py              # GET /sessions, /sessions/:id
│   └── upload.py                # POST /upload
│
├── frontend/                    # React SPA
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ChatPanel.tsx
│   │   │   ├── ConversationSidebar.tsx
│   │   │   ├── EmailGate.tsx
│   │   │   ├── FileUpload.tsx
│   │   │   ├── ProgressStatus.tsx
│   │   │   ├── TopicFramingCard.tsx
│   │   │   └── OutlinePreview.tsx
│   │   ├── hooks/
│   │   │   └── useStoryTeller.ts
│   │   └── lib/
│   │       └── api.ts
│   └── public/
│
├── infra/                       # CDK deployment
│   ├── app.py
│   ├── stacks/
│   │   ├── api_stack.py
│   │   ├── frontend_stack.py
│   │   ├── agent_stack.py
│   │   └── data_stack.py
│   └── cdk.json
│
└── scripts/                     # Dev utilities
    ├── dev-agent.sh             # Local agent dev server
    └── seed-test-data.py        # Test data for development
```

---

## 8. Development Phases

### Phase 1: Agent Core (Week 1-2)
- [ ] System prompt with full YouTube methodology
- [ ] Strands agent with all 7 tools
- [ ] Local dev server with hot reload (`agentcore dev`)
- [ ] Test: URL input → topic framing → outline → Hebrew script

### Phase 2: API + Data (Week 2-3)
- [ ] DynamoDB tables (sessions + messages)
- [ ] Lambda handlers (chat streaming, auth, sessions)
- [ ] API Gateway with CORS
- [ ] S3 bucket for file uploads
- [ ] File upload → agent ingestion pipeline

### Phase 3: Frontend (Week 3-4)
- [ ] CopilotKit SPA scaffold (Vite + React)
- [ ] Email gate component
- [ ] Chat panel with streaming
- [ ] Conversation sidebar with auto-naming
- [ ] File upload/drop zone
- [ ] Generative UI cards (topic framing, progress)

### Phase 4: Integration + Deploy (Week 4-5)
- [ ] CDK stacks for all infrastructure
- [ ] AgentCore Runtime deployment
- [ ] CloudFront distribution for SPA
- [ ] End-to-end testing
- [ ] Internal launch to SA team

---

## 9. Open Questions for Later

1. **Thumbnail generation** — should the agent also generate thumbnail images? (Bedrock image models)
2. **Analytics** — track which video structures lead to better retention? (requires YouTube API integration)
3. **Collaboration** — multiple SAs co-editing the same video plan?
4. **Templates** — save successful video structures as reusable templates?
5. **Voice input** — let SAs describe their topic via voice in the web UI? (already have Transcribe working)

---

_Next step: Start building Phase 1 — the Strands agent with system prompt and tools._
