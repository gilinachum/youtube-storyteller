# StoryTeller — Functional Requirements

_Version 4.1 | 2026-05-10 | Single source of truth for all features_

---

## 1. Authentication & Access

| ID | Requirement | Status |
|----|-------------|--------|
| AUTH-1 | Cognito email/password login | ✅ Done |
| AUTH-2 | Any valid email accepted (no domain restrictions) | ✅ Done |
| AUTH-3 | JWT tokens in localStorage (access + ID + refresh) | ✅ Done |
| AUTH-4 | Logout clears tokens | ✅ Done |
| AUTH-5 | JWT auth on AgentCore Runtime (custom authorizer → Cognito) | ✅ Done |
| AUTH-6 | Admin-only user registration (self-signup disabled) | ✅ Done |

---

## 2. Chat Interface

| ID | Requirement | Status |
|----|-------------|--------|
| CHAT-1 | Welcome message on new session (capabilities as bullet list) | ✅ Done |
| CHAT-2 | Hebrew RTL layout (Heebo font) | ✅ Done |
| CHAT-3 | Dark theme (gray-950 background) | ✅ Done |
| CHAT-4 | Markdown rendering (headers, bold, bullets, code, blockquotes) | ✅ Done |
| CHAT-5 | Code blocks render LTR with horizontal scroll | ✅ Done |
| CHAT-6 | Enter to send, Shift+Enter for newline | ✅ Done |
| CHAT-7 | Auto-growing textarea (up to 200px) | ✅ Done |
| CHAT-8 | Smart auto-scroll (follows stream; stops if user scrolls up) | ✅ Done |
| CHAT-9 | Real-time streaming (SSE via AgentCore Runtime) | ✅ Done |
| CHAT-10 | Inline progress indicators (pulsing bar with tool labels) | ✅ Done |
| CHAT-11 | Keepalive markers during long tool calls (stripped from display) | ✅ Done |
| CHAT-12 | Error messages displayed inline (⚠️ prefix) | ✅ Done |
| CHAT-13 | Stop generation button (AbortController) | ✅ Done |
| CHAT-14 | Mobile stream resilience (partial save + tab-focus recovery) | ✅ Done |

---

## 3. Voice Input

| ID | Requirement | Status |
|----|-------------|--------|
| VOICE-1 | Microphone recording button in chat input | ✅ Done |
| VOICE-2 | Recording indicator (pulsing dot + "מקליט...") | ✅ Done |
| VOICE-3 | Cancel recording button (discard without sending) | ✅ Done |
| VOICE-4 | Send recording button (stop + transcribe) | ✅ Done |
| VOICE-5 | Transcription via Amazon Transcribe (async: start + poll) | ✅ Done |
| VOICE-6 | Transcribed text placed in textarea (not auto-sent) | ✅ Done |
| VOICE-7 | "מתמלל הודעה קולית..." overlay during transcription | ✅ Done |
| VOICE-8 | Supports long recordings (async pattern, no 29s limit) | ✅ Done |
| VOICE-9 | Language auto-detection (Hebrew/English) | ✅ Done |

---

## 4. Session Management

| ID | Requirement | Status |
|----|-------------|--------|
| SESS-1 | Auto-create new session on first message | ✅ Done |
| SESS-2 | Agent auto-names sessions in Hebrew (via name_session tool) | ✅ Done |
| SESS-3 | Session sidebar listing (sorted by updated_at desc) | ✅ Done |
| SESS-4 | Load session history from sidebar | ✅ Done |
| SESS-5 | "שיחה חדשה" button | ✅ Done |
| SESS-6 | Session sharing by email (POST /sessions/{id}/share) | ✅ Done |
| SESS-7 | Shared sessions visible in recipient's sidebar (👥 icon) | ✅ Done |
| SESS-8 | "משותפת" badge on shared sessions | ✅ Done |
| SESS-9 | Share modal with list of current shares | ✅ Done |
| SESS-10 | Session data persisted in DynamoDB | ✅ Done |
| SESS-11 | Sidebar refreshes after agent names session | ✅ Done |

---

## 5. File Upload & Management

| ID | Requirement | Status |
|----|-------------|--------|
| FILE-1 | Upload button (📎) in chat input | ✅ Done |
| FILE-2 | Supported: PDF, PPTX, PPT, TXT, MD, DOC, DOCX | ✅ Done |
| FILE-3 | Upload via presigned S3 URL | ✅ Done |
| FILE-4 | Files at `uploads/{email}/{session_id}/{file_id}-{filename}` | ✅ Done |
| FILE-5 | Attached files shown as chips with ✕ remove | ✅ Done |
| FILE-6 | File references passed to agent in message | ✅ Done |
| FILE-7 | Files tracked in DynamoDB session record | ✅ Done |
| FILE-8 | Files panel with badge count in header | ✅ Done |
| FILE-9 | Click file to download (presigned GET URL) | ✅ Done |
| FILE-10 | File type icons (📕📊📄) | ✅ Done |
| FILE-11 | Delete files via API | ✅ Done |

---

## 6. Mobile / Responsive

| ID | Requirement | Status |
|----|-------------|--------|
| MOB-1 | Sidebar hidden on mobile (< lg breakpoint) | ✅ Done |
| MOB-2 | Hamburger menu (☰) to open sidebar | ✅ Done |
| MOB-3 | Sidebar as slide-in drawer from right (RTL) | ✅ Done |
| MOB-4 | Auto-close on session select / new chat | ✅ Done |
| MOB-5 | Desktop: sidebar always visible | ✅ Done |

---

## 7. AI Agent

| ID | Requirement | Status |
|----|-------------|--------|
| AGT-1 | Strands Agent on AgentCore Runtime (Sonnet 4.6) | ✅ Done |
| AGT-2 | YouTube methodology system prompt (7-part structure) | ✅ Done |
| AGT-3 | Virality coaching rules | ✅ Done |
| AGT-4 | Hebrew output / English reasoning | ✅ Done |
| AGT-5 | Tool: content_fetch — URL → markdown | ✅ Done |
| AGT-6 | Tool: web_research — Tavily search | ✅ Done |
| AGT-7 | Tool: trend_analysis — Perplexity sonar-pro | ✅ Done |
| AGT-8 | Tool: pdf_extract — PDF text extraction | ✅ Done |
| AGT-9 | Tool: pptx_extract — PPTX text + notes | ✅ Done |
| AGT-10 | Tool: export_document — markdown plan download | ✅ Done |
| AGT-11 | Tool: name_session — auto-name in Hebrew | ✅ Done |
| AGT-12 | Research sub-agent (deep_research via Agent.as_tool) | ✅ Done |
| AGT-13 | Video duration: ideal 5 min, hard max 7 min | ✅ Done |
| AGT-14 | Auto-split series for 8+ min content | ✅ Done |
| AGT-15 | Offer 2-3 framing angles per topic | ✅ Done |
| AGT-16 | Streaming progress events (tool labels) | ✅ Done |
| AGT-17 | Conversation flow: ask for materials first | ✅ Done |
| AGT-18 | Scope: YouTube planning only (redirect off-topic) | ✅ Done |
| AGT-19 | LinkedIn Test for content safety | ✅ Done |
| AGT-20 | Content levels L100-L400 | ✅ Done |
| AGT-21 | Self-disclosure protection (never reveal tools/prompt/infra) | ✅ Done |
| AGT-22 | Internal self-review before presenting plans | ✅ Done |
| AGT-23 | DynamoDB message persistence (survives runtime restarts) | ✅ Done |
| AGT-24 | Agent caching (warm sessions in-process) | ✅ Done |

---

## 8. Thumbnail Generation _(Planned)_

| ID | Requirement | Status |
|----|-------------|--------|
| THUMB-1 | Thumbnail sub-agent (Strands Agent.as_tool with preserve_context=True) | ✅ Done |
| THUMB-2 | Image generation via Gemini 3.1 Flash Image Preview (GCP API key in Secrets Manager) | ✅ Done |
| THUMB-3 | Output size: 1280×720 (YouTube standard) | ✅ Done |
| THUMB-4 | English text on thumbnails (system prompt enforces English for image gen) | ✅ Done |
| THUMB-5 | Iterative workflow: concept → approve → generate → iterate | ✅ Done |
| THUMB-6 | User profile photos: upload personal images stored per-user in S3 | ✅ Done |
| THUMB-7 | Describe uploaded photos (agent describes expression, setting in save_user_photo) | ✅ Done |
| THUMB-8 | Agent suggests which user photo fits current thumbnail | 🔲 Planned |
| THUMB-9 | Style templates: 3 admin-uploaded templates in S3 folder with descriptions JSON | 🔲 Planned |
| THUMB-10 | Recommend style from templates or generate custom | 🔲 Planned |
| THUMB-11 | Series support: generate new thumbnail matching existing style, change text | 🔲 Planned |
| THUMB-12 | Use existing thumbnail as style guide (image-to-image reference) | 🔲 Planned |
| THUMB-13 | Combine reference images (user photo + style guide) in single generation | 🔲 Planned |
| THUMB-14 | Soft limit: 70 image generations per session | 🔲 Planned |
| THUMB-15 | Agent suggests thumbnail after video plan is ready | ✅ Done |
| THUMB-16 | User can request thumbnail at any stage independently | ✅ Done |
| THUMB-17 | Welcome message mentions thumbnail generation capability | ✅ Done |
| THUMB-18 | Generated thumbnails displayed inline in chat | ✅ Done |
| THUMB-19 | Download generated thumbnails | 🔲 Planned |
| THUMB-20 | Image upload intent recognition: profile photo vs content — ask if ambiguous | ✅ Done |
| THUMB-21 | Gemini 3.1 Flash Image Preview for generation | ✅ Done |

---

## 9. API Endpoints

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/auth/verify` | POST | Cognito JWT validation | ✅ Done |
| `/chat-stream` | POST | SSE streaming via AgentCore Runtime | ✅ Done |
| `/sessions` | GET | List sessions (own + shared) | ✅ Done |
| `/sessions/{id}` | GET | Session messages + files | ✅ Done |
| `/sessions/{id}/share` | POST | Share session with email | ✅ Done |
| `/sessions/{id}/files/{file_id}` | GET | Presigned download URL | ✅ Done |
| `/upload` | POST | Request presigned upload URL | ✅ Done |
| `/upload` | GET | List files for session | ✅ Done |
| `/upload` | DELETE | Delete a file | ✅ Done |
| `/transcribe` | POST | Start voice transcription job | ✅ Done |
| `/transcribe/{job_name}` | GET | Poll transcription status | ✅ Done |

---

## 10. Infrastructure

| ID | Requirement | Status |
|----|-------------|--------|
| INF-1 | CDK for all infrastructure (4 stacks) | ✅ Done |
| INF-2 | Bedrock AgentCore Runtime (direct code deploy) | ✅ Done |
| INF-3 | Lambda: arm64, Python 3.13 | ✅ Done |
| INF-4 | DynamoDB: sessions + messages tables | ✅ Done |
| INF-5 | S3: uploads bucket (private, blocked public access) | ✅ Done |
| INF-6 | S3: frontend bucket (CloudFront OAC) | ✅ Done |
| INF-7 | CloudFront with SPA viewer-request rewrite | ✅ Done |
| INF-8 | API Gateway with Cognito authorizer | ✅ Done |
| INF-9 | API Gateway streaming (ResponseTransferMode: STREAM) | ✅ Done |
| INF-10 | Secrets Manager: tavily, perplexity, firecrawl, GCP API keys | ✅ Done |
| INF-11 | CloudFront /media/* behavior → uploads S3 bucket via OAC | ✅ Done |
| INF-12 | CloudFront Function: media auth (st-auth cookie, JWT format check) | ✅ Done |
| INF-13 | Full UUID in media filenames (prevents path guessing) | ✅ Done |
| INF-14 | st-auth cookie set on login (Secure, SameSite=Lax, path=/media) | ✅ Done |
| INF-11 | Cognito user pool (shared) | ✅ Done |
| INF-12 | AgentCore Observability (ADOT auto-instrumentation → CloudWatch GenAI dashboard) | ✅ Done |

---

## 11. Testing

| ID | Requirement | Status |
|----|-------------|--------|
| TEST-1 | Unit tests (pytest + moto) — 41 tests | ✅ Done |
| TEST-2 | E2E live tests (6 cases: 3 positive, 3 negative) | ✅ Done |
| TEST-3 | Playwright browser tests (5 tests) | ✅ Done |

---

## 12. Data Model

### Sessions Table (`storyteller-sessions`)
```
PK: email (String)
SK: session_id (String)
Attributes: name, created_at, updated_at, status, files[], shared_with[]
```

### Messages Table (`storyteller-messages`)
```
PK: session_id (String)
SK: timestamp (String)
Attributes: role (user|assistant), content
```

### User Photos
```
S3: media/photos/{email}/{uuid}.{ext}
S3: media/photos/{email}/photos.json  — [{file_id, filename, s3_key, description, uploaded_at}]
```
Full UUID in filename prevents guessing individual files.

### Thumbnail Templates _(Planned)_
```
S3: templates/thumbnails/{template_id}.png
S3: templates/thumbnails/templates.json — [{id, name, description, style_notes}]
```

### Generated Thumbnails
```
S3: media/thumbnails/{email}/{session_id}/thumb-{uuid}.png
CloudFront: /media/thumbnails/{email}/{session_id}/thumb-{uuid}.png
```
Full UUID in filename prevents guessing. Served via CloudFront with cookie auth.

---

## 13. Public Sharing & URL Routing

| ID | Requirement | Status |
|----|-------------|--------|
| PUB-1 | URL updates to `/s/{session_id}` on session select (bookmarkable) | 🔲 Planned |
| PUB-2 | Direct load from URL: `/s/{id}` opens that session | 🔲 Planned |
| PUB-3 | Session `visibility` attribute: `private` (default) / `public` | 🔲 Planned |
| PUB-4 | Owner can toggle visibility in share modal | 🔲 Planned |
| PUB-5 | Copy shareable link button when public | 🔲 Planned |
| PUB-6 | Public sessions: any logged-in user with link can view (read-only) | 🔲 Planned |
| PUB-7 | Viewer sees read-only UI (no input bar, "📖 שיחה לקריאה בלבד" banner) | 🔲 Planned |
| PUB-8 | Public sessions do NOT appear in viewer's sidebar | 🔲 Planned |
| PUB-9 | Block chat-stream for viewer-only users | 🔲 Planned |
| PUB-10 | Viewers can export/download session content | 🔲 Planned |
| PUB-11 | Remove collaborator (unshare by email) | 🔲 Planned |
| PUB-12 | `PATCH /sessions/{id}/visibility` endpoint (owner only) | 🔲 Planned |
| PUB-13 | `DELETE /sessions/{id}/share/{email}` endpoint (owner only) | 🔲 Planned |
| PUB-14 | GSI on session_id for direct lookups (replaces shared scan) | 🔲 Planned |
| PUB-15 | Access field in session response: `owner` / `collaborator` / `viewer` | 🔲 Planned |

---

## 14. Long-Term Memory

### Architecture

Two-tier memory system using AgentCore Memory:
- **Tier 1 — Long-term memory (lightweight):** Session summaries + user preferences extracted automatically from conversations. Remembers *what* was discussed in *which* session, plus persistent user knowledge.
- **Tier 2 — On-demand detail extraction (sub-agent tool):** When exact details are needed from a past session, a one-shot sub-agent loads the original session's full conversation from short-term memory and extracts precisely the details requested.

Retrieval trigger: **Option B** — do not retrieve memory on cold open. Retrieve only after the user's first message, using semantic search matched to their intent.

### Memory Strategies

| Strategy | Purpose | Type |
|----------|---------|------|
| Session Summaries | Compact recap of each session (topic, decisions, outcomes) | Built-in |
| User Preferences | Content style, audience, thumbnail style, structural preferences | Built-in (Phase 1), Custom override (Phase 2) |

### System Prompt Guidance

The agent's system prompt includes instructions to:
- Quote relevant memory when it influences a decision (e.g., "בפעם הקודמת בחרת בזווית 2 מתוך 3 — רוצה גישה דומה?")
- Reference memory naturally in Hebrew, not as raw data dumps
- Never fabricate memories — if unsure, say so

### Use Cases

#### Personalization (cross-session user knowledge)

| ID | Requirement | Status |
|----|-------------|--------|
| MEM-1 | Remember content style preferences (e.g., L200, humor, hook-first) | 🔲 Planned |
| MEM-2 | Remember target audience (e.g., Israeli DevOps engineers, 25-40) | 🔲 Planned |
| MEM-3 | Remember channel facts (subscriber count, niche, posting frequency) | 🔲 Planned |
| MEM-4 | Remember thumbnail style preferences (colors, layout, text style) | 🔲 Planned |

#### Continuity (knowing what happened before)

| ID | Requirement | Status |
|----|-------------|--------|
| MEM-5 | Recall what topics were covered in past sessions | 🔲 Planned |
| MEM-6 | Avoid duplicate suggestions — don't propose topics the user already rejected | 🔲 Planned |
| MEM-7 | Reference previous decisions ("last time you chose angle 2 out of 3") | 🔲 Planned |
| MEM-8 | Continue multi-session projects ("cloud security series, this is part 3") | 🔲 Planned |

#### Cross-session detail retrieval (Tier 2 — sub-agent tool)

| ID | Requirement | Status |
|----|-------------|--------|
| MEM-9 | Reproduce thumbnail style from another session ("same design as the K8s video") | 🔲 Planned |
| MEM-10 | Reuse script structure from a previous session ("same format as last time") | 🔲 Planned |
| MEM-11 | Reference specific research findings from another session | 🔲 Planned |
| MEM-12 | Reuse exported plan as template for a new video | 🔲 Planned |
| MEM-13 | Generic detail extraction: user mentions something from a past session → agent identifies the session via long-term memory → `recall_session_details` tool loads the full conversation via short-term memory → one-shot sub-agent extracts and returns the precise details needed | 🔲 Planned |

#### Agent self-improvement

| ID | Requirement | Status |
|----|-------------|--------|
| MEM-14 | Learn which planning approaches the user approves (tables vs. narrative, 2 vs. 5 options) | 🔲 Planned |
| MEM-15 | Learn which thumbnail prompts produce good results — reduce iteration cycles | 🔲 Planned |
| MEM-16 | Learn which research depth the user expects (shallow scan vs. deep dive) | 🔲 Planned |

### Tool: `recall_session_details`

A new agent tool for on-demand cross-session detail extraction.

**Flow:**
1. User mentions something from a past session (e.g., "אותו סטייל טאמבנייל כמו בסשן של Kubernetes")
2. Agent searches long-term memory (session summaries) to identify the relevant session ID
3. Agent calls `recall_session_details(session_id, query)` — e.g., `query="thumbnail design details: colors, fonts, layout, Gemini prompt used, user photo"`
4. Tool internally: loads the full session conversation from short-term memory (ListEvents), passes it to a one-shot sub-agent with the query, sub-agent extracts and returns structured details
5. Agent uses the returned details to fulfill the user's request

**Why this pattern:**
- No need to predict and index every possible detail type upfront
- Long-term memory stays lightweight (summaries + preferences)
- Exact details are extracted on-demand from the raw conversation
- Works for any detail type: thumbnails, scripts, research, decisions, prompts

**Constraint:** Depends on short-term memory TTL (365 days). After expiry, raw session is gone — only the summary survives.

---

## 15. Future / Backlog

| ID | Requirement | Priority |
|----|-------------|----------|
| FUT-1 | Custom domain + ACM certificate | Medium |
| FUT-2 | CORS tightening to CloudFront domain only | Medium |
| FUT-3 | YouTube API integration (analytics) | Low |
| FUT-4 | Reusable templates from successful plans | Low |
| FUT-5 | Document export to PDF / Google Docs | Medium |
| FUT-6 | Review sub-agent (quality gate before presenting plans) | Low |
| FUT-7 | SEO sub-agent (optimize titles, descriptions, tags) | Low |

---

## 16. YouTube Video Analysis

| ID | Requirement | Status |
|----|-------------|--------|
| YT-1 | Tool: analyze_youtube_video — Gemini 3.1 Flash video understanding | 🔲 Planned |
| YT-2 | Accepts youtube.com/watch, youtu.be, youtube.com/shorts URLs | 🔲 Planned |
| YT-3 | Returns structured JSON: summary, topics, structure, style, audience level | 🔲 Planned |
| YT-4 | Optional focus parameter for targeted analysis | 🔲 Planned |
| YT-5 | User-initiated: analyze video when URL is shared | 🔲 Planned |
| YT-6 | Proactive: analyze YouTube URLs found during deep_research (top 2-3) | 🔲 Planned |
| YT-7 | System prompt instructs agent to offer analysis when user mentions existing videos | 🔲 Planned |
| YT-8 | Graceful errors for private/age-restricted/too-long videos | 🔲 Planned |
| YT-9 | Uses existing GCP API key from Secrets Manager (gcp/gemini-api-key) | 🔲 Planned |
| YT-10 | Insights presented in Hebrew, conversationally (not raw JSON dump) | 🔲 Planned |

---

_Last updated: 2026-04-25_
