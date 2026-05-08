---
name: thumbnail-design
description: Design YouTube thumbnails — iterative generation with style templates, user photos, and text overlays. Use when the user asks to create, modify, or iterate on a thumbnail.
---

# Thumbnail Design

## Process

1. **Understand the concept** — what's the video about, what emotion to convey
2. **Propose a concept** — describe what the thumbnail should contain:
   - Main visual element (person, product, diagram)
   - Text overlay (2-5 words max, high contrast)
   - Color scheme and mood
   - Composition (rule of thirds, focal point)
3. **Get user approval** on the concept
4. **Generate** — use `design_thumbnail` tool
5. **Iterate** — refine based on feedback (the tool preserves context)

## Design Principles

- **Size:** 1280x720px (16:9 ratio) — YouTube standard
- **Text:** Maximum 5 words, readable at mobile size (phone screen)
- **Faces:** Close-up faces with expressive emotions get higher CTR
- **Colors:** High contrast, saturated — stand out in feed
- **Composition:** Subject on one side, text on the other (rule of thirds)
- **Branding:** Consistent style across series videos

## Style Templates

The user may have uploaded style templates. When available:
- Reference their existing thumbnail style
- Match colors, fonts, layout patterns
- For series videos: same template, different text/subject

## User Photos

Users upload personal photos for use as reference. When generating:
- Use the user's face/appearance as reference
- Match their typical presentation style
- Can combine with different backgrounds/effects

## Iteration Patterns

Common refinement requests:
- "הגדל את הטקסט" → make text bigger
- "שנה צבעים" → change color scheme  
- "תוסיף את הפנים שלי" → add user's face
- "תעשה כמו הסרטון הקודם" → match previous thumbnail style
- "יותר דרמטי" → more dramatic expression/contrast

## Important

- Always confirm concept before generating (saves API calls)
- The tool maintains conversation context — refer to previous iterations
- If user provides a reference thumbnail from another video, analyze its style first
