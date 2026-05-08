---
name: video-review
description: Review and analyze an uploaded video or its transcript — identify strengths, weaknesses, pacing issues, messaging clarity, and suggest improvements. Use when a user uploads a video for feedback or asks to analyze an existing recording.
---

# Video Review & Analysis

## Scope

Analyzing an existing video or its transcript to provide actionable feedback:
- Reviewing a user's recorded presentation before publishing
- Analyzing a webinar recording for improvements
- Transcribing and critiquing a conference talk
- Extracting a structure/outline from an existing video
- Comparing against best practices for the session type

## Process

1. **Receive the video/audio** — user uploads file
2. **Transcribe** — use `start_transcription` if not already transcribed
3. **Read transcript** — use `read_file` to access the full text
4. **Analyze** — apply the relevant framework based on session type
5. **Deliver feedback** — structured, actionable, prioritized

## Analysis Framework

### Structure Analysis
- Is there a clear opening hook? How long before the core content?
- Are the key messages identifiable? How many? (ideal: 3-5)
- Is there a logical flow? Does each section build on the previous?
- Is there a clear conclusion with takeaways?
- Are transitions between sections smooth?

### Engagement Analysis
- Are there pattern interrupts? How frequent?
- Does the speaker ask questions or invite participation?
- Are there stories, anecdotes, or real-world examples?
- Is there variety (demo, slides, whiteboard, discussion)?
- Are there moments of surprise, humor, or emotion?

### Messaging Clarity
- Can you summarize the talk in one sentence? If not, it's unclear.
- Are technical concepts explained before being used?
- Is jargon defined or avoided?
- Are analogies used effectively?
- Is the "so what?" clear for each section?

### Pacing & Timing
- Overall pace: too fast? too slow? uneven?
- Are there unnecessary repetitions or tangents?
- Time allocation: is the most important content getting the most time?
- Are there long stretches without visual changes or interaction?
- Does the ending feel rushed or drawn out?

### Delivery (if video available)
- Voice: monotone vs. varied? Volume appropriate?
- Filler words: "um", "uh", "so", "like" — frequency?
- Eye contact: reading slides vs. engaging audience?
- Energy level: flat? appropriate? too intense?
- Body language: open and confident?

### Slide/Visual Quality (if applicable)
- Text density — too much text per slide?
- Readability — font size, contrast, clutter?
- Are visuals meaningful or decorative?
- Are code examples readable?
- Is there a consistent visual style?

## Feedback Delivery Format

Structure feedback as:

### 📊 Overall Assessment
- One-line summary
- Rating: ⭐ (1-5) per dimension
- Top 3 strengths
- Top 3 areas for improvement

### ✅ What Works Well
- Specific moments/quotes that are effective
- Structural choices that work
- Engagement techniques used well

### 🔧 Suggestions for Improvement
Prioritized list:
1. **High impact, easy fix** — do these first
2. **High impact, harder** — worth the effort
3. **Nice to have** — if time permits

For each suggestion:
- What the issue is (with timestamp/quote reference)
- Why it matters
- Specific recommendation for how to fix it

### 📝 Restructured Outline (optional)
If the structure needs significant rework, propose an alternative outline showing what a better version could look like.

## Analysis By Session Type

Apply different emphasis based on what kind of session is being reviewed:

| Session Type | Primary Focus |
|---|---|
| Conference talk | Structure, messaging clarity, time management |
| Workshop recording | Exercise clarity, pacing, participant inclusion |
| Webinar | Engagement (high dropout risk), visual variety |
| Internal presentation | Actionability, relevance to audience, conciseness |
| YouTube video | Hook, retention, thumbnail-worthiness, SEO |

## Important Notes

- Be constructive, not harsh — the goal is improvement, not criticism
- Lead with strengths before weaknesses
- Be specific — "slide 3 has too much text" not "your slides are bad"
- Offer alternatives — don't just say what's wrong, suggest what's better
- Consider the speaker's experience level — different feedback for beginners vs. experts
- If it's in Hebrew: provide feedback in Hebrew naturally
- Reference specific transcript moments (quote the text)
- If the user plans to re-record: focus on structure and content changes
- If it's already published: focus on learnings for next time
