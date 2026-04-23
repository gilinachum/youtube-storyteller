# StoryTeller — Functional Requirements Specification

_Version 3.0 | 2026-04-22 | Tracks all implemented + planned requirements_

---

## 1. Overview

StoryTeller is a web app that helps content creators plan engaging Hebrew YouTube videos. Users provide topics, source material (URLs, PDFs, presentations), and the AI agent researches, plans, structures, and scripts videos optimized for audience retention and virality.

---

## 2. Authentication & Access

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| AUTH-1 | Cognito email/password login | ✅ Done | User pool `<YOUR_COGNITO_POOL_ID>` |
| AUTH-2 | Any valid email accepted | ✅ Done | No domain restrictions |
| AUTH-3 | JWT tokens stored in localStorage | ✅ Done | Access + ID + refresh tokens |
| AUTH-4 | Logout clears tokens | ✅ Done | |
| AUTH-5 | JWT auth on AgentCore Runtime | ✅ Done | Custom JWT authorizer pointing to Cognito |
| AUTH-6 | Admin-only user registration | ✅ Done | Self-signup disabled |

---

## 3. Chat Interface

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| CHAT-1 | Welcome message on new session | ✅ Done | Shows agent capabilities, prompts "על מה הסרטון הבא שלך? 🚀" |
| CHAT-2 | Hebrew RTL layout | ✅ Done | Full RTL with Heebo font |
| CHAT-3 | Dark theme | ✅ Done | Gray-950 background |
| CHAT-4 | Markdown rendering in agent responses | ✅ Done | Headers, bold, bullets, code, blockquotes |
| CHAT-5 | Input placeholder "כתוב לי כאן..." | ✅ Done | |
| CHAT-6 | Enter to send, Shift+Enter for newline | ✅ Done | |
| CHAT-7 | Auto-growing textarea | ✅ Done | Up to 200px |
| CHAT-8 | Auto-scroll to new messages | ✅ Done | Smooth scroll |
| CHAT-9 | Real-time streaming (SSE) | ✅ Done | Text streams token-by-token via AgentCore Runtime |
| CHAT-10 | Inline progress indicators | ✅ Done | Pulsing bar showing tool labels (🔍 מחפש באינטרנט...) |
| CHAT-11 | Error messages displayed inline | ✅ Done | ⚠️ prefix in assistant bubble |
| CHAT-12 | Stop generation button | ✅ Done | AbortController cancels stream |
| CHAT-13 | Voice input (microphone recording) | 🔲 Planned | Record → Transcribe → send as text |

---

## 4. Session Management

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| SESS-1 | Auto-create new session on first message | ✅ Done | UUID generated client-side |
| SESS-2 | Agent auto-names sessions in Hebrew | ✅ Done | Via `name_session` tool |
| SESS-3 | Session sidebar listing | ✅ Done | Sorted by updated_at desc |
| SESS-4 | Load session history from sidebar | ✅ Done | Fetches messages from DynamoDB |
| SESS-5 | "שיחה חדשה" button | ✅ Done | Resets to welcome message |
| SESS-6 | Session sharing by email | ✅ Done | POST /sessions/{id}/share |
| SESS-7 | Shared sessions visible in recipient's sidebar | ✅ Done | Shows 👥 icon |
| SESS-8 | "משותפת" badge on shared sessions | ✅ Done | Brand-colored pill badge |
| SESS-9 | Share modal with list of current shares | ✅ Done | |
| SESS-10 | Session data persisted in DynamoDB | ✅ Done | PK: email, SK: session_id |
| SESS-11 | Sidebar refreshes after agent names session | ✅ Done | Immediate + 2s delayed re-fetch |

---

## 5. File Upload & Management

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FILE-1 | Upload button (📎) in chat input area | ✅ Done | Paperclip icon |
| FILE-2 | Supported formats: PDF, PPTX, PPT, TXT, MD, DOC, DOCX | ✅ Done | Validated client + server |
| FILE-3 | Upload via presigned S3 URL | ✅ Done | POST /upload → presigned PUT URL |
| FILE-4 | Files stored at `uploads/{email}/{session_id}/{file_id}-{filename}` | ✅ Done | |
| FILE-5 | Attached files shown as chips above input | ✅ Done | With ✕ to remove |
| FILE-6 | File references passed to agent in message | ✅ Done | `[קובץ מצורף: filename (s3_key)]` |
| FILE-7 | Files tracked in DynamoDB session record | ✅ Done | |
| FILE-8 | Files panel with badge count in header | ✅ Done | |
| FILE-9 | Click file to download (presigned GET URL) | ✅ Done | |
| FILE-10 | File type icons (📕📊📄) | ✅ Done | |
| FILE-11 | Delete files via API | ✅ Done | |

---

## 6. Mobile / Responsive

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| MOB-1 | Sidebar hidden on mobile (< lg) | ✅ Done | |
| MOB-2 | Hamburger menu (☰) to open sidebar | ✅ Done | |
| MOB-3 | Sidebar as slide-in drawer from right (RTL) | ✅ Done | Dark backdrop |
| MOB-4 | Auto-close on session select / new chat | ✅ Done | |
| MOB-5 | Desktop: sidebar always visible | ✅ Done | |

---

## 7. AI Agent

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| AGT-1 | Strands Agent on AgentCore Runtime (Sonnet 4.6) | ✅ Done | `us.anthropic.claude-sonnet-4-6` |
| AGT-2 | YouTube methodology system prompt (7-part structure) | ✅ Done | Hook formulas, retention data |
| AGT-3 | Virality coaching rules | ✅ Done | Topic combos, CTR, timing |
| AGT-4 | Hebrew output / English reasoning | ✅ Done | |
| AGT-5 | Tool: content_fetch — URL → markdown | ✅ Done | Raw HTTP requests |
| AGT-6 | Tool: web_research — Tavily search | ✅ Done | Sources + synthesized answer |
| AGT-7 | Tool: trend_analysis — Perplexity sonar-pro | ✅ Done | Deep research |
| AGT-8 | Tool: pdf_extract — PDF text extraction | ✅ Done | pdfplumber, supports S3 paths |
| AGT-9 | Tool: pptx_extract — PPTX text + notes | ✅ Done | python-pptx, supports S3 paths |
| AGT-10 | Tool: export_document — markdown video plan | ✅ Done | |
| AGT-11 | Tool: name_session — auto-name in Hebrew | ✅ Done | |
| AGT-12 | Video duration: 3-7 min, auto-split series | ✅ Done | |
| AGT-13 | Offer 2-3 framing angles per topic | ✅ Done | |
| AGT-14 | Streaming progress events (tool labels) | ✅ Done | JSON inline in SSE stream |
| AGT-15 | Conversation flow: ask for materials first | ✅ Done | Never skip to research |
| AGT-16 | Scope boundaries: YouTube planning only | ✅ Done | Politely redirects off-topic |
| AGT-17 | PR guidelines: LinkedIn Test for content safety | ✅ Done | No hit pieces, no competitor attacks |
| AGT-18 | Content levels L100-L400 | ✅ Done | AWS-style levels + audience dimensions |
| AGT-19 | Agent caching (warm/cold sessions) | ✅ Done | In-process dict, DynamoDB for cold restart |
| AGT-20 | DynamoDB message persistence | ✅ Done | Every message saved, independent of Runtime lifecycle |

---

## 8. API Endpoints

| ID | Endpoint | Method | Purpose | Status |
|----|----------|--------|---------|--------|
| API-1 | `/auth/verify` | POST | Cognito JWT validation | ✅ Done |
| API-2 | `/chat` | POST | Legacy async chat (job polling) | ✅ Done (fallback) |
| API-3 | `/chat/{job_id}` | GET | Poll job status | ✅ Done (fallback) |
| API-4 | `/stream` | POST | SSE streaming via AgentCore Runtime | ✅ Done |
| API-5 | `/sessions` | GET | List sessions (own + shared) | ✅ Done |
| API-6 | `/sessions/{id}` | GET | Session messages + files | ✅ Done |
| API-7 | `/sessions/{id}/share` | POST | Share session with email | ✅ Done |
| API-8 | `/sessions/{id}/files/{file_id}` | GET | Presigned download URL | ✅ Done |
| API-9 | `/upload` | POST | Request presigned upload URL | ✅ Done |
| API-10 | `/upload` | GET | List files for session | ✅ Done |
| API-11 | `/upload` | DELETE | Delete a file | ✅ Done |
| API-12 | `/transcribe` | POST | Voice transcription (Transcribe) | 🔲 Planned |

---

## 9. Infrastructure

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| INF-1 | CDK for all infrastructure | ✅ Done | 3 stacks: Data, Api, Frontend |
| INF-2 | Bedrock AgentCore Runtime for agent | ✅ Done | Direct code deploy, 15min idle timeout |
| INF-3 | Lambda functions: arm64, Python 3.13 | ✅ Done | auth, sessions, upload, stream-proxy |
| INF-4 | DynamoDB: sessions + messages tables | ✅ Done | On-demand billing |
| INF-5 | S3: uploads bucket (private) | ✅ Done | Block all public access |
| INF-6 | S3: frontend bucket (CloudFront OAC) | ✅ Done | |
| INF-7 | CloudFront with SPA rewrite | ✅ Done | Viewer-request function |
| INF-8 | API Gateway with Cognito authorizer | ✅ Done | |
| INF-9 | Secrets Manager: tavily, perplexity, firecrawl API keys | ✅ Done | |
| INF-10 | Cognito user pool (shared) | ✅ Done | `<YOUR_COGNITO_POOL_ID>` |

---

## 10. Testing

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| TEST-1 | Unit test suite (pytest + moto) | ✅ Done | 38 tests, all mocked |
| TEST-2 | test_runtime_app.py — payload, sessions, cache, streaming | ✅ Done | 12 tests |
| TEST-3 | test_system_prompt.py — structure, guardrails, levels | ✅ Done | 11 tests |
| TEST-4 | test_tools.py — PDF, S3 resolution, tool imports | ✅ Done | 8 tests |
| TEST-5 | test_api.py — auth, sessions, upload handlers | ✅ Done | 5 tests |
| TEST-6 | test_e2e.py — Playwright browser tests | ✅ Done | 5 tests (integration) |
| TEST-7 | Scripts: test.sh, test-e2e.sh | ✅ Done | |

---

## 11. Scripts & Deployment

| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/deploy.sh` | Deploy agent + restore JWT auth | ✅ Done |
| `scripts/deploy-frontend.sh` | Build + S3 sync + CF invalidation | ✅ Done |
| `scripts/deploy-all.sh` | Agent + frontend combined | ✅ Done |
| `scripts/test.sh` | Run unit tests | ✅ Done |
| `scripts/test-e2e.sh` | Run E2E browser tests | ✅ Done |
| `scripts/check-agent.sh` | Verify agent status/auth/env | ✅ Done |

---

## 12. Data Model

### Sessions Table (`storyteller-sessions`)
```
PK: email (String)
SK: session_id (String)
Attributes:
  - name: String (agent-generated Hebrew name)
  - created_at / updated_at: String (ISO timestamp)
  - status: String (active | archived)
  - files: List<{file_id, filename, s3_key, content_type, uploaded_at}>
  - shared_with: List<String> (emails)
```

### Messages Table (`storyteller-messages`)
```
PK: session_id (String)
SK: timestamp (String)
Attributes:
  - role: String (user | assistant)
  - content: String
```

---

## 13. Deployment Resources

| Resource | Value |
|----------|-------|
| AWS Account | <YOUR_AWS_ACCOUNT_ID> |
| Region | us-east-1 |
| Frontend URL | https://<YOUR_CLOUDFRONT_DOMAIN> |
| API URL | <YOUR_API_URL> |
| AgentCore Runtime | <YOUR_AGENT_RUNTIME_ID> |
| CloudFront Distribution | <YOUR_CF_DISTRIBUTION_ID> |
| Cognito User Pool | <YOUR_COGNITO_POOL_ID> |
| CDK Stacks | StoryTellerData, StoryTellerApi, StoryTellerFrontend |

---

## 14. Planned / Future

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FUT-1 | Voice input (microphone → Transcribe → text) | 🔴 High | Record in browser, send audio, transcribe, display as user message |
| FUT-2 | AgentCore observability (OTEL/ADOT) | Medium | Strands has built-in support |
| FUT-3 | Thumbnail generation (Bedrock image models) | Low | |
| FUT-4 | YouTube API integration (analytics) | Low | |
| FUT-5 | Reusable templates from successful plans | Low | |
| FUT-6 | Custom domain + ACM certificate | Medium | |
| FUT-7 | CORS tightening to CloudFront domain only | Medium | |
| FUT-8 | Document export (PDF / Google Docs) | Medium | |

---

_This document is the single source of truth for regenerating the application._
_Last updated: 2026-04-22 21:00 UTC_
