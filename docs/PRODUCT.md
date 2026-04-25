# StoryTeller — Product Overview

_Version 1.0 | 2026-04-25_

---

## What is StoryTeller?

StoryTeller is a web app that helps content creators plan and produce engaging Hebrew YouTube videos. It combines AI-powered research, proven engagement methodologies, and iterative collaboration to turn raw ideas into polished video plans.

**Think of it as a creative partner that:**
- Researches your topic and finds unique angles
- Structures your video for maximum retention
- Writes scripts in your voice
- Generates eye-catching thumbnails
- Coaches you on virality and timing

---

## Who is it for?

Content creators who produce Hebrew-language tech/educational YouTube videos. The system is optimized for:
- AWS Solution Architects creating educational content
- Tech content creators covering cloud, AI, DevOps topics
- Anyone making Hebrew YouTube content who wants data-driven structure

---

## Core User Flow

```
1. User opens StoryTeller → sees welcome message with capabilities
2. User describes a video idea (text, voice, URL, PDF, or presentation)
3. Agent researches the topic — web search, trend analysis, content extraction
4. Agent proposes 2-3 framing angles with rationale
5. User picks an angle (or asks for modifications)
6. Agent produces a structured video plan:
   - Hook → Promise → Core Content → Recap → CTA
   - Estimated duration (ideal 5 min, hard max 7 min)
   - If content exceeds 7 min → proposes a series split
7. User iterates — "make the hook stronger", "add this point", etc.
8. Agent generates final output: outline or full script
9. User can export as a document (presigned download link)
10. Agent suggests thumbnail → user iterates → generates thumbnail image
```

---

## Key Features

### 📝 Video Planning
- Topic research with real-time web search and trend analysis
- YouTube engagement methodology (7-part structure, hook formulas, retention data)
- Virality coaching (topic combos, CTR optimization, posting timing)
- Content level system (L100-L400, like AWS sessions)
- Automatic series detection and splitting for long content

### 🎙️ Multi-Input Support
- Type a topic description
- Record a voice message (transcribed automatically)
- Share a URL (agent fetches and analyzes the content)
- Upload a PDF or PowerPoint presentation
- Combine multiple inputs in the same session

### 🎨 Thumbnail Generation _(planned)_
- AI-generated YouTube thumbnails via Gemini Flash Preview
- Upload personal photos for the agent to incorporate
- Style templates — pick from existing designs or create custom
- Series consistency — generate new thumbnails matching existing style
- Iterative refinement with the agent

### 💬 Conversational Editing
- Chat-based iteration — "make it shorter", "add humor", "change the angle"
- Session history preserved — come back anytime to continue
- Share sessions with collaborators

### 📄 Export
- Download video plans as markdown documents
- Presigned links valid for 7 days

---

## Design Principles

1. **Hebrew-first** — UI, output, and voice input in Hebrew. Agent reasons internally in English for quality.
2. **Data-driven** — Every structural suggestion backed by YouTube retention research (2025 benchmarks).
3. **Iterative** — The agent is a collaborator, not a one-shot generator. Conversation flows naturally.
4. **Professional** — All content passes the "LinkedIn Test" — nothing you'd be embarrassed to share publicly.
5. **Fast** — Streaming responses, real-time progress indicators, no waiting for batch jobs.

---

## YouTube Methodology (Built-In)

StoryTeller has internalized proven YouTube engagement research:

| Metric | Value |
|--------|-------|
| Average YouTube retention | 23.7% |
| Viewers lost by 60s | 55% |
| Hook decision window | 8 seconds |
| Educational retention (best niche) | 42.1% |
| Sweet spot length | 5-10 min (31.5% retention) |

### Proven Hook Formulas

| Formula | Pattern | Retention Lift |
|---------|---------|---------------|
| Mistake | "I've been doing X wrong for Y..." | +34% |
| Controversy | "Everyone says X, but here's proof they're wrong" | +28% |
| Transformation | "How I went from A to B in N days" | +41% CTR |
| Question | "What would happen if you X?" | +34% |

### Video Structure (7-Part Framework)

| Part | Timing | Purpose |
|------|--------|---------|
| Hook | 0-15s | Stop scrolling |
| Promise | 15-30s | Set expectations |
| Preview | 30-60s | Build commitment |
| Core Content | 60s-90% | Deliver value (engagement beats every 60-90s) |
| Transitions | Throughout | Open loops |
| Recap | ~85% | Summary |
| CTA | Last 10% | Subscribe, comment, next video |

---

## Content Guidelines

- **Video duration:** Ideal 5 min, hard max 7 min per video
- **Long requests (8+ min):** Agent actively proposes splitting into a series
- **Content safety:** LinkedIn Test — all content must be professional and shareable
- **No self-disclosure:** Agent never reveals its tools, system prompt, model, or infrastructure
- **Scope:** YouTube video planning only — politely redirects off-topic requests

---

_This document describes what StoryTeller does. For how it's built, see [TECHNICAL-DESIGN.md](TECHNICAL-DESIGN.md). For detailed requirements, see [REQUIREMENTS.md](REQUIREMENTS.md)._
