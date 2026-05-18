# StoryTeller — Product Summary

StoryTeller is a web app that helps content creators plan and produce engaging **Hebrew YouTube videos**. It acts as an AI creative partner that researches topics, structures video plans using proven engagement methodology, writes scripts, and generates thumbnails.

## Target Users
AWS Solution Architects and tech content creators producing Hebrew-language educational YouTube content.

## Core User Flow
1. User describes a video idea (text, voice, URL, PDF, or PPTX)
2. Agent researches the topic (web search, trend analysis, content extraction)
3. Agent proposes 2–3 framing angles
4. User picks an angle and iterates conversationally
5. Agent produces a structured video plan (Hook → Promise → Core Content → Recap → CTA)
6. User exports the plan as a markdown document
7. Agent generates a YouTube thumbnail (iterative, with user photos + style templates)

## Key Constraints
- **Hebrew-first**: UI and output in Hebrew; agent reasons internally in English
- **Video length**: Ideal 5 min, hard max 7 min per video; 8+ min → propose series split
- **Content safety**: LinkedIn Test — all content must be professional and shareable
- **Scope**: YouTube video planning only — politely redirect off-topic requests
- **Self-disclosure protection**: Agent never reveals its tools, system prompt, model, or infrastructure

## Content Levels
L100–L400 (like AWS session levels), applied to all video plans.
