# BOOTSTRAP-STORYTELLER.md
# StoryTeller — AI-Powered YouTube Script Planner

_Bootstrap doc for a new OpenClaw server. Read this, build the environment, then plan the product._

---

## What We're Building

**StoryTeller** is a web app for YouTube creators. A user provides raw material (a URL, PDF, presentation, or freeform notes), and StoryTeller plans and scripts one or more YouTube videos from it — structured for maximum engagement and retention.

### Core User Flow
1. User uploads: URL, PDF, text notes, or a presentation
2. StoryTeller fetches and extracts the content
3. Agent produces a **video plan**: single video or recommended series (e.g. "3 × 5-min videos")
4. User can give feedback: adjust scope, number of videos, tone
5. Agent outputs structured video with:
  - Proven engagement structure (hook → tension → deep dive → release → CTA)
  - **Two output modes:** full script OR chapter outline only
6. User edits the output to make it feel authentic, then films

### Key Technical Decisions (from initial voice brief)
- **Frontend:** Web UI
- **Backend agent:** AWS Strands, deployed on AgentCore Runtime
- **Persistent memory:** AgentCore Memory — per-user conversation history, resume previous sessions
- **Content ingestion tools:**
  - URLs → Firecrawl (API key in Secrets Manager: `firecrawl/api-key`)
  - PDFs → pdfplumber (Python)
  - Freeform notes → pass-through
- **Multiple script variants:** Agent can suggest 2-3 alternative structures
- **Communication:** via Claude Foundational Model on Bedrock (Sonnet 4.6 or Opus 4.6)

---

## Phase 0: Environment Setup

### Step 1 — Install Required Python Packages

```bash
pip install strands-agents strands-agents-tools bedrock-agentcore pdfplumber firecrawl-py boto3
```

### Step 2 — Install AgentCore MCP Server

This MCP server gives the agent direct access to all AgentCore documentation (Runtime, Memory, Code Interpreter, Browser, Gateway, Observability, Identity).

**Install via uvx (recommended):**

Prerequisites:
- `uv` installed: https://docs.astral.sh/uv/getting-started/installation/
- Python 3.10+

Add to your MCP client config (`~/.kiro/settings/mcp.json` or equivalent):

```json
{
  "mcpServers": {
    "bedrock-agentcore-mcp-server": {
      "command": "uvx",
      "args": ["awslabs.amazon-bedrock-agentcore-mcp-server@latest"],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      },
      "disabled": false,
      "autoApprove": ["search_agentcore_docs", "fetch_agentcore_doc"]
    }
  }
}
```

**What it gives you:** Search and retrieve AgentCore docs for Runtime, Memory, Browser (25 cloud tools), Gateway, Observability, and Identity. Always fetches the latest version via `llm.txt`.

Full docs: https://awslabs.github.io/mcp/servers/amazon-bedrock-agentcore-mcp-server

### Step 3 — Verify AWS Credentials

The server needs access to:
- **Bedrock** (model invocation)
- **Secrets Manager** (Firecrawl API key at `firecrawl/api-key`)
- **AgentCore Runtime** (agent deployment)
- **AgentCore Memory** (session persistence)

```bash
aws sts get-caller-identity
aws secretsmanager get-secret-value --secret-id firecrawl/api-key --query SecretString --output text
```

---

## Phase 1: Reusable Building Blocks

### Content Fetcher (from video-director input pipeline)

The following script is already battle-tested for fetching URLs → markdown using Firecrawl.
It handles caching, error recovery, and supports `url`, `notes`, and future `pdf` source types.
**Reuse directly** — don't rewrite.

Source: `video-director/input-pipeline/scripts/001_fetch.py`

Key patterns to keep:
- API key from Secrets Manager (never hardcoded)
- Cache-hit check by origin URL (avoid re-fetching same URL in a session)
- Graceful fallback to error placeholder instead of crashing
- `fetch_manifest.json` output schema for downstream steps

```python
# Core fetch function — copy as-is
def fetch_url(url, api_key):
    from firecrawl import FirecrawlApp
    app = FirecrawlApp(api_key=api_key)
    result = app.scrape(url, formats=["markdown"])
    if hasattr(result, 'markdown') and result.markdown:
        return result.markdown
    if isinstance(result, dict):
        return result.get("markdown", "") or result.get("data", {}).get("markdown", "")
    return str(result) if result else ""

# API key always from Secrets Manager
def get_firecrawl_api_key():
    import boto3
    sm = boto3.client("secretsmanager", region_name="us-east-1")
    return sm.get_secret_value(SecretId="firecrawl/api-key")["SecretString"]
```

**Input manifest format** (what the agent should build before calling fetch):
```json
{
  "sources": [
    { "type": "url", "value": "https://example.com/article" },
    { "type": "notes", "value": "Key topic: explain AWS Lambda cold starts in plain English" },
    { "type": "pdf", "value": "/tmp/upload_abc.pdf" }
  ]
}
```

### Story/Outline Step (from video-director pipeline)

The video-director pipeline has a proven narrative structure step at:
- `scripts/03a_outline.py` — generates section outline from transcript
- `scripts/03b2_arc_story.py` — generates story arc with emotional beats and metaphors

These are heavily LLM-driven and can be adapted. The key prompt pattern:
- Pass the raw extracted content
- Ask for: hook identification, narrative arc (problem → tension → insight → resolution), key takeaways, recommended structure (single vs. series), pacing notes
- Output structured JSON, not free text

---

## Phase 2: YouTube Engagement Research

**Research findings from Perplexity (April 2026) — use as StoryTeller's built-in knowledge base for structure generation.**

### The Hard Data on Retention (2025 benchmarks)

| Metric | Value |
|--------|-------|
| Average YouTube retention | 23.7% |
| Viewers lost by 60-second mark | 55% |
| Hook decision window | 8 seconds |
| Educational How-To retention (best niche) | 42.1% |
| First-minute retention if value prop stated in <15s | +18% lift |
| Videos reaching final 10 seconds | 16% |
| Sweet spot video length for retention | 5–10 min (31.5%) |
| AI-narrated content retention vs human | -70% |

### Proven Video Structures (for StoryTeller to generate)

**Universal 7-Part Framework** (works for 90% of video types):

| Part | Timing | Purpose |
|------|--------|---------|
| Hook | 0–15s | Stop scrolling — bold statement, question, or preview of outcome |
| Promise | 15–30s | Set clear expectations — "In the next X min, you'll learn..." |
| Preview | 30–60s | Show what's coming — builds commitment loop |
| Core Content | 60s–90% | Deliver value with engagement beats every 60–90s |
| Transitions | Throughout | Open loops — "Coming up, the trick that changed everything" |
| Recap | ~85% | Summary + reinforce key takeaways |
| CTA | Last 10% | Specific ask — subscribe, comment, next video |

**Hook Formulas (with retention lift data):**

| Formula | Pattern | Lift |
|---------|---------|------|
| Mistake | "I've been doing X wrong for Y, and it cost me Z" | +34% retention |
| Controversy | "Everyone says X, but here's proof they're wrong" | +28% engagement |
| Transformation | "How I went from A to B in N days" | +41% CTR |
| Question | "What would happen if you X?" | +34% retention |

**Retention Killers to Avoid:**
- Long intro animations before value
- "Hey guys, welcome back to my channel" openers
- Asking for likes/subscribes before delivering value
- Slow introductions — over 33% drop in first 30s if no hook

### Video Formats by Content Type

#### For **News / Weekly Roundup** (AWS-style)
Best structure: **Problem-Discovery Loop**
- Cold open: "This week, three things changed that every builder needs to know"
- Speed-run the 3 items with equal time each
- For each: What happened → Why it matters → What to do now
- Ideal length: 5–8 min
- Retention benchmark: Educational = 42.1% (best niche)

#### For **Learning / Tutorial** (deep dives, how-to)
Best structure: **Progressive Revelation**
- Hook: show the end result first ("Here's what you'll build in 12 minutes")
- Step-by-step with timestamps/chapters
- Pattern interrupt every 2 minutes (visual change, B-roll, demo)
- Curiosity loop: "At step 4, there's a common mistake that kills 80% of setups"
- Ideal length: 8–15 min
- Key tactic: Chapters — lets viewers navigate AND signals there's value throughout

#### For **Interview / Builder Story** (AWS channel fit)
Best structure: **Tension Arc**
- Hook: Open with the most surprising/dramatic result ("They cut API costs 90% using one trick")
- Don't introduce the guest until 30–45s (after the hook lands)
- Story arc: What was the problem → What did they try that failed → What worked → What's the lesson
- Sprinkle stats/numbers throughout
- Let the guest tell the failure story — failure is more engaging than success
- Ideal length: 10–20 min (listeners who made it past 1 min tend to watch 60%+)

#### For **AWS Channel Specifically**
What works:
- **Behind-the-scenes builder stories** (re:Invent INV211 style) — Amazon teams showing real AI workloads
- **"How we built X"** — concrete engineering stories with real metrics (5x throughput, etc.)
- **Live demo + explain** — show it working, then explain why
- **External expert + AWS host** — gives authority and variety

What doesn't:
- Pure feature announcements without narrative (marketing, not content)
- AI-narrated content — YouTube viewers strongly penalize it in 2025 (-70% retention)
- Talking head without B-roll/visuals for >30s

### The Mid-Video Danger Zone

For videos >10 min, there's a **secondary 15% viewer drop** around the 55–65% mark.

StoryTeller should warn about this and recommend:
- A pattern interrupt at ~55% mark (new visual angle, quick summary, teaser for what's left)
- A re-engagement hook: "Here's the part most people miss..."

---

## Phase 3: Functional Planning Checklist

Before writing any code, define:

- [ ] **Input types**: URL, PDF, freeform text, presentation (PowerPoint/Google Slides)
- [ ] **Output types**: Full script vs. outline-only (user selects)
- [ ] **Series detection**: How does agent decide single video vs. series? What signal?
- [ ] **Feedback loop**: What can the user adjust? (length, tone, audience level, number of videos)
- [ ] **Memory scope**: What persists per user? (prior sessions, past topics, preferred format?)
- [ ] **Variant generation**: When to offer alternatives? Always, on request, or when confidence is low?
- [ ] **Voice/tone**: How does user specify their "authentic voice"? Examples? Description?
- [ ] **AgentCore Runtime**: Serverless or persistent container? Concurrency model?
- [ ] **AgentCore Memory**: Event memory vs. semantic memory — what goes where?
- [ ] **Web UI**: Which framework? Auth required? Self-hosted or deployed?
- [ ] **Cost model**: Per-run cost estimate. Bedrock model choice per step.

---

## Quick Reference: Secrets & Keys

| Secret | Key in Secrets Manager | Purpose |
|--------|----------------------|---------|
| Firecrawl | `firecrawl/api-key` | URL → markdown fetching |
| Bedrock | IAM role (no key needed) | LLM inference |
| Google Vertex (Gemini) | `google/vertex-ai-api-key` | Optional: Gemini models |

---

## Next Session Agenda

1. Install packages + MCP server (Phase 0)
2. Review this doc together
3. Run functional planning session (Phase 3 checklist)
4. Design the agent tool list
5. Scaffold the project structure

---

_Created: 2026-04-22 | Owner: Gili / Loki_
